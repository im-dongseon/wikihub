---
approved: 2026-05-19
---

# Analysis & Design — rclone_remote_path

## 1. 배경 및 목적

2026-05-19 OCI 실증: vault-fetch.py(v0.1.1) 의 lsjson 이 mount 와 다른 scope 를 조회하는 결함 surface. user 보고 (Hermes log):

> mount 는 `gdrive:wikihub` → `/home/ubuntu/wikihub/vault/gdrive`, gdrive:wikihub 는 비어있는 폴더 (ingest 테스트용)
> rclone.conf: `[gdrive]` remote 1개
> wikihub.yaml: `rclone_remote_name: gdrive`, `root_folder_id: "1CuN..."` (ADR-0035 폐지된 SA 방식)
>
> 문제: lsjson 이 `gdrive:` (Drive 루트) 조회 — mount 와 scope 불일치

본 변경 목적:
- mount 와 lsjson 의 scope 명시적 정합화 — `<remote>:<path>` spec 통일.
- ADR-0035 미반영 잔재 (`root_folder_id`) 폐기 — SA 시절 trust boundary narrow 용. OAuth + mount root 시절엔 mount path 자체가 boundary.
- `mount` source path 부재 시 멱등 생성 (rclone mkdir) 추가.

## 2. 현행 진단

### 결함 1 — rclone_remote_name 의미 불충분

`wikihub.yaml.vaults[*].options.rclone_remote_name: gdrive` 1필드 → 두 곳에서 동일 scope 사용:

| 위치 | 호출 | 효과 |
|---|---|---|
| `_system/systemd/wikihub-mount@.service.template:16` | `rclone mount {remote}: {wikihub_home}/vault/%i` | Drive 루트 전체 mount |
| `scripts/lib/rclone.py:175` | `args = ["lsjson", f"{remote}:"]` | Drive 루트 lsjson |

OCI 실증 mount 가 `gdrive:wikihub` 로 운영되려면 1필드로는 표현 불가. 두 곳 모두 sub-path 인지 가능한 spec 으로 격상 필요.

### 결함 2 — root_folder_id dead config

ADR-0029 (SA 시절) 의 §Decision: "vault 폴더만 명시 공유 (SA Editor)" — 즉 SA 가 owner 가 아니므로 owner 시야로 보면 SA 가 접근 가능한 폴더 ID 로 trust boundary 좁힐 필요. ADR-0035 가 SA 폐기 + OAuth user 가 mount source path 자체로 boundary 좁힘 (mount 가 `<remote>:<path>` 이면 그 sub-tree 만 노출).

현재 `scripts/lib/mount_diff.py:13` 주석:
> "``root_folder_id`` — lsjson 호출 자체가 ``<remote>:`` 단위라 사후 filter. ... v0.1.0 은 ``exclude_shared_with_me`` 만 적용"

코드에서 root_folder_id 는 활성 사용 없음. yaml.example L24 에 빈 문자열로 잔존 — dead config.

### 결함 3 — mount source path 사전 부재 시 mount fail

`gdrive:wikihub` 같은 sub-path mount 시 source 폴더가 사전 부재면 rclone mount 가 빈 directory 표시 또는 fail (rclone 버전 의존). user 운영 편의: mkdir 멱등 호출로 사전 보장.

## 3. 개정 범위

| 파일 | 변경 | 성격 |
|---|---|---|
| `wikihub.yaml.example` | `root_folder_id` 제거 + `rclone_remote_path` 추가 | schema 변경 |
| `scripts/lib/rclone.py` | `lsjson(remote, *, path: str = "", ...)` 인자 추가 | API 확장 (backward-compat — 기본값 빈문자열 = 기존 동작) |
| `scripts/lib/sync.py` | `lsjson(remote, path=remote_path, ...)` 전달 | call-site |
| `scripts/lib/mount_diff.py` | root_folder_id 주석 정리 (실증 반영) | 문서 |
| `scripts/_helpers/render_systemd_units.py` | `_cross_vault_subs` 에 `remote_path_for_<vid>` 추가 | placeholder |
| `_system/systemd/wikihub-mount@.service.template` | `ExecStartPre={rclone_bin} mkdir {remote_name_for_%i}:{remote_path_for_%i}` 추가 + `ExecStart ... mount {remote_name_for_%i}:{remote_path_for_%i} ...` | unit spec |
| `_system/commands/setup.md` | derived fields catalog 갱신 (`root_folder_id` 제거 + `rclone_remote_path` 추가) | playbook |
| `_system/wiki-schema.md` | trust boundary 표 갱신 (`root_folder_id` 행 → mount root 행) | spec doc |
| `docs/adr/0035-rclone-only-unified-oauth.md` | §Note 추가 (본 변경 사유) | 결정 정본 |
| `docs/adr/0027-...md`, `docs/adr/0031-...md` | root_folder_id 언급 §Note (역사 보존) | 갱신 |
| `tests/test_sync.py`, `tests/test_mount_diff.py` (필요 시) | lsjson signature change 반영 | 테스트 |

## 4. 개정 전/후 비교

### yaml.example (v3 schema — minor bump)

Before:
```yaml
options:
  root_folder_id: ""              # Drive 의 vault root folder ID...
  exclude_shared_with_me: true
  max_file_size_mb: 50
  false_delete_threshold: 0.3
  mount_path: ~/wikihub/vault/gdrive
  rclone_remote_name: gdrive
  rclone_rc_port: 5572
```

After:
```yaml
options:
  exclude_shared_with_me: true
  max_file_size_mb: 50
  false_delete_threshold: 0.3
  mount_path: ~/wikihub/vault/gdrive
  rclone_remote_name: gdrive             # ~/.config/rclone/rclone.conf 의 remote 이름
  rclone_remote_path: wikihub            # remote 내 sub-path (빈 문자열이면 remote 루트). mount + lsjson 공통 scope
  rclone_rc_port: 5572
```

### lsjson signature

Before:
```python
def lsjson(remote: str, *, recursive=True, ...) -> list[dict]:
    args = ["lsjson", f"{remote}:"]
```

After:
```python
def lsjson(remote: str, *, path: str = "", recursive=True, ...) -> list[dict]:
    spec = f"{remote}:{path}" if path else f"{remote}:"
    args = ["lsjson", spec]
```

### systemd mount template

Before:
```ini
ExecStartPre=-/bin/fusermount3 -uz {wikihub_home}/vault/%i
ExecStartPre=/bin/mkdir -p {wikihub_home}/vault/%i
ExecStart={rclone_bin} mount {remote_name_for_%i}: {wikihub_home}/vault/%i \
  --vfs-cache-mode minimal \
  ...
```

After:
```ini
ExecStartPre=-/bin/fusermount3 -uz {wikihub_home}/vault/%i
ExecStartPre=/bin/mkdir -p {wikihub_home}/vault/%i
ExecStartPre=-{rclone_bin} mkdir {remote_name_for_%i}:{remote_path_for_%i}
ExecStart={rclone_bin} mount {remote_name_for_%i}:{remote_path_for_%i} {wikihub_home}/vault/%i \
  --vfs-cache-mode minimal \
  ...
```

- `ExecStartPre=-{rclone_bin} mkdir ...`: `-` prefix 로 exit code 무시 (이미 존재 시 OK).
- `remote_path_for_%i` 가 빈 문자열이면 `gdrive:` 로 자연 fallback — `rclone mkdir gdrive:` 은 noop.

## 5. 결정 정리 (ADR-0035 §Note)

본 변경은 ADR-0035 의 §Decision (β2 lsjson) + Architectural intent (mount = trust boundary) 의 정합 보강. SA 폐기에 따라 sub-path scope 표현 자체가 새 schema 의무가 됨. ADR-0035 §Note 로 기록:

- root_folder_id 폐기 — ADR-0035 가 mount root 를 trust boundary 로 격상한 결정과 정합. 미운영 (v0.1.0 첫 배포 직전) 이라 마이그레이션 0.
- rclone_remote_path 신설 — mount + lsjson 의 scope 통일. 빈 문자열 default 로 backward-compat (기존 yaml.example 의 `gdrive:` 동작 유지).

별도 ADR 신설 안 함 — ADR-0035 의 §Decision 본문 변경 없음, §Note 로 부속 schema 명시.

## 6. 연계 룰/스킬 정합성 검토

- **ADR-0027 (rclone/gws 책임 분리)**: §Decision 본문 `mount_path`, `rclone_remote_name`, `rclone_rc_port` 명시. ADR-0035 가 본 ADR 을 superseded 상태. 본 변경의 새 필드 (`rclone_remote_path`) 는 ADR-0035 영역. ADR-0027 본문 변경 없음.
- **ADR-0031 (yaml template materialization)**: §Decision B catalog 가 derived 4필드 (instance.root, vaults[*].local_path, rclone_remote_name, mount_path) 명시. `rclone_remote_path` 는 maintainer 책임 필드 (derived 아님) — catalog 영향 없음. 단 L69, L113 의 root_folder_id 언급은 historical 컨텍스트로 §Note 추가.
- **systemd unit render 정합**: `_cross_vault_subs` 가 `remote_path_for_<vid>` 추가 시 동일 메커니즘 (per-vault dict 색인) → 새 placeholder 의도 정확히 표현.
- **credentials.py assert_rclone_config**: remote name 단위로 rclone.conf section 검증 — `rclone_remote_path` 영향 없음. 그대로 유지.

## 7. 미결 사항

없음.

## 8. Definition of Done

- [ ] `wikihub.yaml.example` 에서 `root_folder_id` 제거 + `rclone_remote_path` 추가됨.
- [ ] `scripts/lib/rclone.py` 의 `lsjson` 이 `path: str = ""` 인자 수용.
- [ ] `scripts/lib/sync.py` 가 yaml options 의 `rclone_remote_path` 를 lsjson 에 전달.
- [ ] `scripts/_helpers/render_systemd_units.py` 의 `_cross_vault_subs` 가 `remote_path_for_<vid>` 추가.
- [ ] mount template 이 `mkdir` ExecStartPre 추가 + `mount` 인자에 `:path` 포함.
- [ ] mount_diff.py 주석에서 root_folder_id 행 제거.
- [ ] `_system/commands/setup.md` 와 `_system/wiki-schema.md` 에서 root_folder_id 잔재 정리 + 새 필드 반영.
- [ ] ADR-0035 §Note (본 변경) 추가, ADR-0027/0031 의 root_folder_id 언급 §Note 추가 (역사 보존).
- [ ] 기존 lsjson 호출 테스트 (`tests/test_sync.py` 등) 가 `path=""` default 로 통과 + 새 path 인자 케이스 1건 추가.
- [ ] `features/HISTORY.md` 항목 append.
- [ ] feature dir archive 이동.
