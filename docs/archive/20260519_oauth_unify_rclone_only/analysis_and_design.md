# Analysis & Design — OAuth 통일 + gws 폐기 (rclone 단독)

- **Feature**: 20260519_oauth_unify_rclone_only
- **Version**: v1 (2026-05-19)
- **연계**: [plan.md](./plan.md), `features/backlog.md` §I
- **approved**: 2026-05-19 (사용자 사전 일괄 승인 — 대화 전사 참조)

---

## 1. 배경 및 목적

### 1.1 직접 계기

2026-05-19 OCI 운영 검증에서 두 결함 surface:

1. **이슈 D** (백로그): SA 키로 rclone mount 시도 → `403 storageQuotaExceeded`. Personal Drive 에서 SA 는 storage quota 미할당 — write 불가. OAuth 로 긴급 전환하여 mount 안정화.
2. **이슈 I** (백로그): rclone mount(OAuth) 로 article/ 5건 업로드 → vault-fetch (SA gws `changes.list`) 사이클 2회 → 미감지. **인증 주체 비대칭이 changes feed 일관성을 깸**.

### 1.2 근본 분석

Drive `changes.list` 는 user-scoped feed — 호출 주체의 changes 만 반환. SA 와 OAuth user 의 changes feed 는 서로 격리됨.

```
rclone(OAuth, user) → 파일 생성 → user owned
gws(SA)            → changes.list → SA feed → user 의 변경 미포함 ❌
```

→ 인증 주체를 OAuth 로 통일하면 자연 해소. 그리고 양방향 동기화(쓰기) 가 필수인 v0.1.0 운영 시나리오에서는 **OAuth 가 유일 선택**.

### 1.3 목적

1. **인증 단일화** — rclone OAuth 로 통일. SA 폐기.
2. **도구 단일화** — gws CLI 폐기. 변경 감지·다운로드 모두 rclone 으로.
3. **ADR cascade 단순화** — 5건 supersede 로 v0.1.0 Drive 접근 모델 정본 1건 (ADR-0035) 으로 압축.

### 1.4 비-목표

- Workspace 전환 또는 OAuth Production 검증 — rclone 기본 client 가 이미 Production. 재검토 트리거: rclone 기본 client 의 정책 변경.
- Google native (`.gdoc`/`.gsheet`/`.gslides`) 본격 검증 — 현재 vault 에 미존재 (2026-05-19 실증). 매핑 코드는 유지하되 검증/테스트 v0.2.x deferred.
- state migration tooling — v0.1.0 미배포 시점이라 운영자 base 영향 0.

---

## 2. 현행 진단

### 2.1 SA 채택 (ADR-0029) 의 전제 오류

ADR-0029 §Decision L50 + §부정/제약 L79 가 모순:

> §Decision: "SA 이메일을 vault 폴더에 **Editor** 공유 (rclone mount 의 write 가정 위한)"
> §부정/제약: "SA 가 ownedBy 가 될 수 없음 — read/write 는 가능하나 Storage 는 항상 메인테이너 계정 quota. v0.1.0 의 vault polling/mount 시나리오는 OK"

→ Personal Drive 에서는 SA 가 Storage quota 없어 **`403 storageQuotaExceeded` 즉시 발생** (백로그 D 실증). polling/read 만 가정한 결정 — w2a 등 쓰기 흐름 surface 시점에 깨짐.

### 2.2 책임 분리 (ADR-0027) 의 인증 비대칭

ADR-0027 §Decision 매트릭스가 rclone/gws 둘 다 SA·OAuth "둘 다 호환" 으로 봤지만, **실제 사용 시점엔 한 시스템 안에서 두 인증 주체가 공존**:

- rclone: OAuth (백로그 D 후)
- gws: SA (ADR-0029 그대로)

→ changes feed 비대칭 (§1.2). ADR-0027 §Considered Options L1 (rclone 단독) 기각 사유 4개를 §3 에서 재평가하면 모두 **무력화 또는 등가 대체 가능**.

### 2.3 gws 의 운영 부담

ADR-0014 §부정/제약 가 명시한 잠재 부담이 v0.1.0 운영 진입 시점에 surface:

- **alpha 의존성**: gws v0.22.5 의 subcommand 명명 변동 (백로그·V<N> Phase 2 결함 #8 — `get-start-page-token` → `getStartPageToken`)
- **stderr 패턴 매칭의 깨지기 쉬움**: ADR-0017 의 매핑 표가 gws 버전마다 갱신 필요
- **Discovery 동적 빌드**: gws 의 first call latency 가 인식되지 않은 영역

→ rclone v1.x stable 단독화로 alpha 부담 자체 제거.

### 2.4 lsjson 실증 (2026-05-19 OCI)

rclone v1.69.1 의 `rclone lsjson gdrive:` 출력:

```json
{"Path":"article","Name":"article","Size":0,"MimeType":"inode/directory",
 "ModTime":"2026-05-19T03:28:01.239Z","IsDir":true,"ID":"1G3rj3jMO2jzi07uMtbm9YTw_EUITbhxj"}
```

- `ID` (Drive fileId) 노출 → **rename 추적 가능**
- `MimeType` (Drive 원본) 노출 → **Google native 분기 가능**
- 인증: rclone.conf OAuth token → mount 와 동일 user → **changes feed 비대칭 자체 해소**

`rclone backend help drive` 출력 명령: get/set/shortcut/drives/untrash/copyid/exportformats/importformats/query/rescue. **`changes` 명령 부재** — ADR-0027 §Context 진단 v1.69.1 에서도 그대로 유효 → mount walk 가 아닌 **lsjson 전체 listing + file_map diff** 가 정본 메커니즘.

---

## 3. 개정 범위

### 3.1 변경 매트릭스

| 대상 | 변경 성격 | 라인 추정 |
|---|---|---|
| `scripts/lib/sync.py` | 재작성 (gws subprocess → lsjson diff) | ~600 → ~400 |
| `scripts/lib/gws.py` | 삭제 | -전체 |
| `scripts/lib/errors.py` | 삭제 (gws exit code 매핑) | -전체 |
| `scripts/lib/credentials.py` | 재구성 (SA 검증 폐기, rclone.conf 검증 유지) | ~115 → ~60 |
| `scripts/lib/rclone.py` | **신규** (lsjson subprocess wrapper) | +~120 |
| `scripts/lib/mount_diff.py` | **신규** (file_map diff + false-deleted 가드) | +~150 |
| `scripts/lib/state.py` | cursor 함수 제거, file_map schema migration helper | -~30 / +~20 |
| `scripts/vault-fetch.py` | 호출 흐름 갱신 (credentials_path → rclone.conf 단일) | ~190 → ~150 |
| `_system/wiki-schema.md` | Google native export 표 갱신 (gws → rclone) | 3줄 |
| `_system/commands/setup.md` | Step 1 gws 단계 폐기, gws_min_version 항목 폐기, Step 6 진입 조건 `bootstrap_allowed: true` → `enabled: true`, 책임표의 `.credentials/` chmod 행 폐기 | ~40 줄 |
| `_system/commands/ingest.md` | Step 2 흐름 갱신 (lsjson 기반) | ~20 줄 |
| `_system/systemd/wikihub-vault@.service` | `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` Env 제거 | 1줄 |
| `install.sh` | gws 다운로드/설치 단계 제거 (`_step4_gws`), `_step5_instance_dirs` 의 `~/.credentials/wikihub/` 생성·chmod 700·`*.json` 권한 enforce 폐기 (rclone.conf 만 — `_step45_rclone` 의 `_enforce_rclone_conf_perms` 가 책임), `GWS_BIN_DIR` → `LOCAL_BIN_DIR` rename, INSTALLED_VERSIONS.json 의 `gws` 키 제거 | ~120 줄 |
| `wikihub.yaml.example` | credentials_path 의미 변경, bootstrap_allowed/gws_min_version 폐기 | ~10 줄 |
| `tests/test_gws.py` | 삭제 | -전체 |
| `tests/test_sync.py` | 재작성 | ~700 → ~500 |
| `tests/test_credentials.py` | 재작성 (rclone.conf 검증) | ~70 → ~50 |
| `tests/test_mount_diff.py` | **신규** | +~200 |
| `docs/adr/0014/0015/0017/0027/0029` | Status `Accepted` → `Superseded` | 각 ~5 줄 |
| `docs/adr/0035-rclone-only-unified-oauth.md` | **신규** | +~150 줄 |

### 3.2 영향 받지 않는 영역 (정합 확인 완료)

- `scripts/lib/extraction.py` — mime 매핑은 동일 (Drive 원본 mimeType 그대로 사용)
- `scripts/lib/frontmatter.py` — source frontmatter 의 source_id 필드 의미 동일
- `scripts/lib/exceptions.py` — VaultSyncFatal/Retryable/FileFatal 그대로
- `scripts/lib/mount.py` — `assert_mount_alive` + `vfs_refresh` 유지
- `scripts/lib/notify.py` — Hermes notify stub 그대로
- F5 hermes adapter (`_system/skills/`) — 외부 인터페이스 (vault-fetch.py stdout JSON contract) 무변경
- `/wh-lint`, `graphify` — gws 직접 의존 없음
- ADR-0001 (source collision), ADR-0006 (unified orchestration), ADR-0007 (state JSON), ADR-0024 (fatal alert), ADR-0025 (rclone mount), ADR-0026 (vfs refresh), ADR-0034 (data-first layout) — 본 feature 와 무관, 그대로 유지

---

## 4. 개정 전/후 비교

### 4.1 변경 감지 메커니즘

**Before** (ADR-0027 Path C+):

```python
# scripts/lib/sync.py
result = run_gws(["drive", "changes", "list"], params={"pageToken": cursor, ...})
changes = json.loads(result.stdout).get("changes", [])
# changes 의 fileId · file dict 를 처리
```

- cursor 모델 (증분 추적). `gws drive changes getStartPageToken` 으로 cursor 발급
- bootstrap 시 `gws drive files list` pagination
- 인증: `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` env (SA JSON)
- 에러: ADR-0017 stderr 패턴 매핑

**After** (ADR-0035):

```python
# scripts/lib/rclone.py
result = run_rclone(["lsjson", "gdrive:", "--recursive"], timeout_sec=300)
listing = json.loads(result.stdout)  # list[dict with ID/MimeType/Path/ModTime/Size]

# scripts/lib/mount_diff.py
diff = compute_diff(listing, file_map, options)
# diff = {created: [...], modified: [...], renamed: [...], deleted: [...]}
```

- **cursor 폐기** — 매 사이클 full snapshot. listing 의 `ID` 가 file_map primary key
- bootstrap 자체 폐기 — first-run 은 file_map 비어있음 → 자연히 모두 created
- 인증: rclone.conf OAuth (mount 와 동일)
- 에러: rclone exit code + stderr 패턴 (rclone 자체 매핑 표 신규)

### 4.2 file_map schema

**Before** — primary key 는 `source_relpath`:

```json
{
  "vault_id": "gdrive",
  "files": {
    "claude-code-context-tools.md": {
      "source_id": "1G5yc7l...",
      "source_mtime": "2026-05-19T04:12:27Z",
      "wiki_path": "wiki/sources/gdrive/claude-code-context-tools.md",
      "bytes": 6130,
      "last_synced_at": "2026-05-19T08:00:00Z"
    }
  }
}
```

**After** — primary key 는 `source_id` (Drive fileId):

```json
{
  "vault_id": "gdrive",
  "files": {
    "1G5yc7ltNZXCnPndh981TUqy0iFg7-qV-": {
      "source_relpath": "claude-code-context-tools.md",
      "source_mtime": "2026-05-19T04:12:27Z",
      "wiki_path": "wiki/sources/gdrive/claude-code-context-tools.md",
      "bytes": 6130,
      "last_synced_at": "2026-05-19T08:00:00Z"
    }
  }
}
```

**근거**: rename 추적 정확성. Drive 의 `name` 은 user-mutable, `id` 는 stable. After 모델에서:

- listing 의 `ID` 가 file_map 에 있고 `Path` 가 다름 → **renamed**. wiki_path 도 갱신 + 이전 wiki page unlink
- listing 의 `ID` 가 file_map 에 있고 `Path`·`ModTime` 둘 다 같음 → **unchanged**
- listing 의 `ID` 가 file_map 에 있고 `ModTime` 다름 → **modified**
- listing 의 `ID` 가 file_map 에 없음 → **created**
- file_map 의 `id` 가 listing 에 없음 → **deleted** (가드 통과 시)

### 4.3 vault.options schema

**Before**:

```yaml
options:
  credentials_path: ~/.credentials/wikihub/sa_gdrive.json
  root_folder_id: ""
  exclude_shared_with_me: true
  max_file_size_mb: 50
  bootstrap_allowed: false
  mount_path: ~/wikihub/vault/gdrive
  rclone_remote_name: gdrive
  rclone_rc_port: 5572
```

**After**:

```yaml
options:
  # credentials_path 폐기 — rclone.conf 가 단일 인증 자료. 위치는 RCLONE_CONFIG env 또는 ~/.config/rclone/rclone.conf
  root_folder_id: ""                  # 의미 동일 (vault root 폴더). OAuth 후엔 빈 문자열도 정상 (전체 owned 파일)
  exclude_shared_with_me: true        # 의미 회복 (OAuth user 컨텍스트)
  max_file_size_mb: 50                # 동일
  # bootstrap_allowed 폐기 — cursor 모델 자체 폐기
  mount_path: ~/wikihub/vault/gdrive  # 동일 (mount + read 책임)
  rclone_remote_name: gdrive          # 동일 (lsjson + mount 둘 다 동일 remote 사용)
  rclone_rc_port: 5572                # 동일
  # neue:
  false_delete_threshold: 0.3         # listing diff 의 삭제 비율 임계치. 초과 시 abort (false-deleted 가드)
```

### 4.4 systemd unit

**Before** (`wikihub-vault@.service`):

```ini
Environment=GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE={credentials_path}
Environment=RCLONE_CONFIG={rclone_config_path}
ExecStart={venv_path}/bin/python {scripts_path}/vault-fetch.py --vault %i
```

**After**:

```ini
Environment=RCLONE_CONFIG={rclone_config_path}
ExecStart={venv_path}/bin/python {scripts_path}/vault-fetch.py --vault %i
```

→ env 1줄 제거. install.sh 의 unit render 도 단순화.

### 4.5 install.sh

**Before** Step 5 구성:

- 5.0 venv 생성
- 5.1 uv install python deps
- 5.2 `_step5_gws_install` — gws binary 다운로드 + version pin verify
- 5.3 `_step5_instance_dirs` — ~/.credentials/wikihub/ 생성
- 5.5 rclone install (5.5a binary + 5.5b conf perms + 5.5c rc port)
- ...

**After** Step 5 구성:

- 5.0 venv 생성
- 5.1 uv install python deps
- 5.2 **제거**
- 5.3 `_step5_instance_dirs` — rclone.conf 권한 chmod 0600 검증만 (~/.credentials/wikihub/ 폐기)
- 5.5 rclone install (동일 유지)

→ Step 5.2 통째 제거. INSTALLED_VERSIONS.json 의 `gws` 키도 제거.

---

## 5. 핵심 설계 — mount_diff 알고리즘

### 5.1 입력·출력

```python
# scripts/lib/mount_diff.py

@dataclass
class DiffEntry:
    operation: str   # 'created' | 'modified' | 'renamed' | 'deleted'
    source_id: str
    source_relpath: str           # 현재 사이클의 relpath
    prev_source_relpath: str | None  # renamed/deleted 시 이전 relpath
    mime_type: str
    mtime: str
    size: int

@dataclass
class DiffResult:
    entries: list[DiffEntry]
    listing_count: int
    file_map_count_before: int
    delete_ratio: float  # len(deleted) / file_map_count_before

def compute_diff(
    listing: list[dict],
    file_map: dict,
    *,
    root_folder_id: str | None,
    exclude_shared_with_me: bool,
) -> DiffResult: ...
```

### 5.2 알고리즘 (의사 코드)

```
1. listing 을 (ID -> entry) dict 로 인덱싱
2. file_map["files"] 도 (source_id -> meta) dict (After schema)
3. trust boundary filter (root_folder_id, exclude_shared_with_me) 적용
4. for each id in listing_dict:
     if id not in file_map:
         classify created
     elif file_map[id].source_relpath != listing[id].Path:
         classify renamed (prev_relpath=file_map[id].source_relpath)
     elif file_map[id].source_mtime != listing[id].ModTime:
         classify modified
     else:
         unchanged
5. for each id in file_map but not in listing:
     classify deleted (prev_relpath=file_map[id].source_relpath)
6. delete_ratio = deleted_count / file_map_count_before
   (file_map_count_before == 0 이면 0.0 으로 정의)
```

### 5.3 false-deleted 가드

```python
# scripts/vault-fetch.py 의 호출자
diff = compute_diff(listing, file_map, ...)

threshold = vault_cfg.options.get("false_delete_threshold", 0.3)
if diff.file_map_count_before > 0 and diff.delete_ratio > threshold:
    raise VaultSyncRetryable(
        vault_id=vault_id,
        retry_after_sec=300,
        reason=f"삭제 비율 {diff.delete_ratio:.0%} > 임계 {threshold:.0%} — listing partial 의심",
    )

if diff.listing_count == 0 and diff.file_map_count_before > 0:
    raise VaultSyncRetryable(
        vault_id=vault_id,
        retry_after_sec=300,
        reason="lsjson listing 0건 — mount/auth 부분 장애 의심",
    )
```

→ Retryable (exit 75) 로 systemd timer 가 다음 사이클 재시도. 연속 발화 시 ADR-0024 last_failure writer 가 escalate.

### 5.4 rename 처리 시 wiki_path 정합

```python
# sync.py 의 renamed 처리
old_wiki = instance_root / file_map["files"][source_id]["wiki_path"]
new_wiki_path = _compute_wiki_path(vault_id, new_source_relpath, mime_type)
old_wiki.unlink(missing_ok=True)
# 새 wiki page 는 write 흐름에서 _atomic_write_wiki_page 호출
```

renamed 는 created + delete 가 아니므로 source_id 보존. wiki_path 만 갱신.

### 5.5 rclone lsjson 인자

```bash
rclone lsjson \
  ${RCLONE_REMOTE}: \
  --recursive \
  --no-mimetype  # 단 MimeType 필드는 default 노출. --no-mimetype 미사용
  # --hash 미사용 (rename·modified 판단에 ModTime 충분)
  # --files-only 또는 --dirs-only 미사용 (IsDir 로 자체 필터)
```

timeout: 300초 (vault 크기 N~수천 가정). 초과 시 VaultSyncRetryable.

---

## 6. 연계 룰/스킬 정합성 검토

### 6.1 ADR cascade

| ADR | Before Status | After Status | After Note |
|---|---|---|---|
| ADR-0014 (gws CLI 채택) | Accepted | Superseded by ADR-0035 | 본문 유지 (역사적 맥락) |
| ADR-0015 (gws pinned version) | Accepted | Superseded by ADR-0035 | 본문 유지 |
| ADR-0017 (gws stderr 매핑) | Accepted | Superseded by ADR-0035 | 본문 유지 |
| ADR-0027 (rclone vs gws 책임 분리) | Accepted | Superseded by ADR-0035 | 본문 유지 — 단 §Considered Options 의 L1 기각 사유는 ADR-0035 §재평가 표에서 해체 |
| ADR-0029 (SA 인증) | Accepted | Superseded by ADR-0035 | 본문 유지 — §Note 에 2026-05-19 실증 (storageQuotaExceeded) 추가 권장 |
| ADR-0035 (rclone-only unified OAuth) | — | **신규 Accepted** | 본 feature 의 정본 |

### 6.2 무관·정합 확인된 ADR

- **ADR-0001** (source collision): mount_diff 가 같은 source_relpath 충돌 발생 시 정책 동일 적용 (source_id 우선)
- **ADR-0006** (unified orchestration): vault-fetch.py 의 외부 인터페이스 (stdout JSON contract) 무변경. subprocess 패턴 (rclone lsjson) 도 동일
- **ADR-0007** (state JSON): 5 state file 의 atomic JSON write 패턴 유지. cursor.json 만 폐기
- **ADR-0024** (fatal alert contract): vault scope writer 그대로. mount scope 도 그대로
- **ADR-0025** (rclone mount 채택): 그대로. lsjson 은 rclone backend 의 별도 호출 경로 — mount 와 무관
- **ADR-0026** (vfs refresh): 그대로. lsjson 은 backend 직접 호출이라 vfs cache 무관
- **ADR-0034** (data-first layout): 그대로. WIKIHUB_HOME / WIKIHUB_SRC 분리 정합

### 6.3 skill / command 정합

| 파일 | 변경 |
|---|---|
| `_system/commands/setup.md` Step 1 (gws 인증 검증) | 폐기 — rclone OAuth 검증으로 대체 |
| `_system/commands/setup.md` Step 0 (gws_min_version 비교) | 폐기 |
| `_system/commands/ingest.md` Step 2 (gws drive changes list) | rclone lsjson + mount_diff 로 갱신 |
| `_system/wiki-schema.md` Google native 표 L131/L151-153 | "gws drive files export" → "rclone mount `--drive-export-formats`" |
| F5 hermes adapter | 무관 (vault-fetch stdout JSON contract 무변경) |
| `/wh-lint`, graphify | 무관 (gws 직접 의존 없음 — 백로그 F 확인) |

### 6.4 기존 운영 자산 영향

- 운영 중인 OCI 서버의 file_map.json 은 Before schema (source_relpath 키) — first-run 시 file_map 자체를 폐기 (rm) 후 모든 파일이 created 로 분류되는 정상 흐름. 운영자 수동 작업 1회 (deploy 후 `rm -rf ~/wikihub/_state/gdrive/file_map.json ~/wikihub/_state/gdrive/cursor.json` 또는 install.sh 의 state migration step). → §7.1 미결사항으로 정리.

---

## 7. 미결 사항

### 7.1 state migration 방식

**옵션**:
- (S1) **자동 migration script** — install.sh 또는 vault-fetch.py 진입점에서 Before schema 감지 시 자동 변환 (source_relpath → source_id 키 재배열, source_id 정보는 기존 entries 의 source_id 필드에서 lift 가능)
- (S2) **수동 rm + first-run 재bootstrap** — 운영자가 `rm file_map.json cursor.json` 후 vault-fetch 가 모든 파일을 created 로 처리. wiki/sources/ 의 기존 페이지는 overwrite (frontmatter 의 source_id 가 동일하면 동일 file_map 엔트리 재생성)
- (S3) **신규 vault id** — 기존 vault 폐기, 신규 vault id 정의. wiki/sources/ 경로도 새로 시작

→ **권장**: (S2). v0.1.0 미배포 시점이므로 운영자 base 1명 (메인테이너) — 수동 rm 으로 충분. 자동 migration 은 코드 표면적만 늘림.

**ADR 추출**: 본 결정은 OAuth 통일과 별개 운영 결정이라 별도 ADR 필요. → **ADR-0036 (file_map schema migration policy)** 신규 검토. 단 결정 단순성을 고려해 ADR-0035 §Note 에 흡수 가능.

### 7.2 false_delete_threshold default 값

**옵션**:
- (T1) **0.3 (30%)** — 권장. 한 사이클에 30% 이상 삭제는 mount/auth 부분 장애 신호로 가정
- (T2) 0.5 (50%) — 보수적. 운영자 의도된 대량 삭제까지 abort 발화 위험
- (T3) 절대값 (예: "10개 초과") — 작은 vault 에서 부적합

→ **권장**: (T1). yaml 옵션으로 override 가능하게 둠.

**ADR 추출**: 운영 디테일 — ADR-0035 §Decision 본문에 포함. 별도 ADR 불요.

### 7.3 rename 임계 — Path+ID 모두 변경 시

Drive 에서 파일이 **삭제 + 새 fileId 로 재생성** 되면 (사용자가 동일 이름으로 새 파일 업로드) — Before 모델에서도 (delete + create) 로 분류됐음. After 모델도 동일 — listing 의 새 ID 가 file_map 에 없음 → created.

→ 정합. 별도 처리 불요.

### 7.4 Google native export-formats 의 mtime 안정성

rclone mount 가 `--drive-export-formats docx,xlsx,pptx,md` 로 변환한 파일의 mtime 이 변환 시점 mtime 인가 원본 Drive mtime 인가 — **미실증**.

- 만약 변환 시점 mtime 이면 모든 native 파일이 매 사이클 modified 분류 → 무한 ingest 사이클
- lsjson 은 backend 호출이라 Drive 원본 mtime 반환 가정이 자연스러우나 v1.69.1 의 실제 거동 확인 필요

→ **ADR 추출 검토**. 단 Google native 가 vault 에 미존재하므로 v0.1.0 운영 시작 시점엔 무영향. **v0.2.x deferred + ADR-0035 §Consequences 의 재검토 트리거에 명시**.

### 7.5 ADR 추출 결정

| 미결 항목 | ADR 처리 |
|---|---|
| §7.1 state migration | ADR-0035 §Note 흡수 (별도 ADR 불요) |
| §7.2 threshold default | ADR-0035 §Decision 본문 포함 |
| §7.3 Path+ID 동시 변경 | 정합 확인 — ADR 불요 |
| §7.4 native mtime 안정성 | ADR-0035 §Consequences 재검토 트리거 — v0.2.x deferred |

→ **본 feature 가 생성하는 ADR: ADR-0035 단일**.

---

## 8. Definition of Done

### 8.1 코드

- [ ] `scripts/lib/sync.py` 재작성 — gws import 제거, mount_diff 호출, file_map schema After 적용
- [ ] `scripts/lib/rclone.py` 신규 — `run_rclone()` subprocess wrapper, exit code/stderr 매핑
- [ ] `scripts/lib/mount_diff.py` 신규 — `compute_diff()` + DiffResult/DiffEntry dataclass
- [ ] `scripts/lib/credentials.py` 재구성 — `assert_credentials` 폐기, `assert_rclone_config` 유지
- [ ] `scripts/lib/state.py` 정리 — cursor 함수 4개 (initial_cursor, load_cursor, save_cursor, has_cursor) 제거
- [ ] `scripts/lib/gws.py`, `scripts/lib/errors.py` 삭제
- [ ] `scripts/vault-fetch.py` 호출 흐름 갱신 — `assert_credentials` 호출 제거, `false_delete_threshold` 가드

### 8.2 인프라

- [ ] `install.sh` 의 `_step5_gws_install` 및 INSTALLED_VERSIONS.json 의 gws 키 제거
- [ ] `_system/systemd/wikihub-vault@.service` 의 `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` Env 제거
- [ ] `wikihub.yaml.example` — credentials_path/bootstrap_allowed/gws_min_version 제거, false_delete_threshold 추가 (주석)

### 8.3 정본 문서

- [ ] `_system/wiki-schema.md` L131/L151-153 갱신
- [ ] `_system/commands/setup.md` Step 0 (gws_min_version), Step 1 (gws auth) 제거
- [ ] `_system/commands/ingest.md` Step 2 흐름 갱신

### 8.4 ADR

- [ ] `docs/adr/0035-rclone-only-unified-oauth.md` 신규 작성
- [ ] ADR-0014/0015/0017/0027/0029 Status `Superseded by ADR-0035` 갱신 + §Note 추가 (실증 결과)
- [ ] `docs/adr/README.md` 인덱스 갱신

### 8.5 테스트

- [ ] `tests/test_gws.py` 삭제
- [ ] `tests/test_sync.py` 재작성 — mount_diff 모킹 기반
- [ ] `tests/test_credentials.py` rclone.conf 검증 only
- [ ] `tests/test_mount_diff.py` 신규 — created/modified/renamed/deleted 4가지 분류 + false-delete 가드
- [ ] `pytest -x` 전체 통과

### 8.6 운영 검증 (Step 5 deployment 후)

- [ ] OCI 에서 `git pull` + `deploy.sh` 실행 후 systemd unit reload
- [ ] 운영자가 수동으로 `rm ~/wikihub/_state/gdrive/{cursor,file_map}.json` (ADR-0035 §Operational Note 절차)
- [ ] systemd timer 1회 fire → vault-fetch.py exit 0 + lsjson listing N 건 → 모두 created 로 처리
- [ ] w2a 로 새 .md 파일 1건 Drive 업로드 → 다음 사이클에서 created 로 감지 → wiki/sources/ 에 페이지 생성 (이슈 I 자체 해소 실증)
- [ ] **rename 회귀 시나리오**: Drive 에서 article/ 의 임의 파일 1건 rename (예: `a.md` → `b.md`) → 다음 사이클에서 `renamed` 분류 + `wiki/sources/gdrive/a.md` unlink + `wiki/sources/gdrive/b.md` write + file_map[source_id].source_relpath 갱신 확인
- [ ] **false-delete 가드 발화 시나리오**: Drive 에서 vault 의 전체 파일 수의 30% 이상을 임시 trash → 다음 사이클에서 `VaultSyncRetryable` 발화 (exit 75, "삭제 비율 ... > 임계 ..." 로그) + wiki/sources/ 무변경 → trash 복원 → 그 다음 사이클 정상 동작 (deleted 0건)
- [ ] 정상 동작 24h 관찰 — fatal 0건 + delete_ratio < `false_delete_threshold` (default 0.3) 유지 + listing_count 매 사이클 ±5% 범위 유지

### 8.7 Feature 종료

- [ ] `features/HISTORY.md` 항목 추가 — 생성 ADR ADR-0035 명시
- [ ] `features/20260519_oauth_unify_rclone_only/` → `features/archive/20260519_oauth_unify_rclone_only/` 이동

---

*이 분석및설계가 승인되면 (`approved: YYYY-MM-DD` 마커 + "Step 3 진행해줘"), Step 3 구현 시작.*
