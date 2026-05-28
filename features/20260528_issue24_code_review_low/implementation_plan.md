# Issue #24 — install_scope_reduction 코드 리뷰 LOW 5건 Implementation Plan

**Feature ID**: 20260528_issue24_code_review_low
**Target Version**: v0.1.9 (다음 patch)
**작업 분류**: 문서 개선 (trivial) — 코드 수정 최소화
**적용 단계**: Step 4 (검토) 생략, Step 5 (배포) 생략 (문서 변경만 해당)

---

## LOW-A: ADR-0031 §Decision B — `os.path.expanduser` 적용 시점 명시

### 배경
ADR-0031 §Decision B 표의 patching 조건에서 "env 값과 yaml 값 불일치 시"라고 기술되어 있으나, `os.path.expanduser` 적용 시점이 명시되지 않아 `~/wikihub` vs `/Users/ds.im/wikihub` 같은 표현 차이로 인한 비교 오류 가능성이 존재합니다.

### 변경 대상
1. `docs/adr/0031-yaml-template-materialization.md` — Decision B 표 근처 (L96~102)
2. `_system/commands/setup.md` — Step 0.2

### 변경 전/후 diff

#### 1. docs/adr/0031-yaml-template-materialization.md

**Before** (L96~102):
```markdown
| 필드 | source | patching 조건 |
|---|---|---|
| `instance.root` | `$WIKIHUB_INSTANCE_ROOT` env (install.sh export 또는 `/wh:setup` 호출 env) | env 값과 yaml 값 불일치 시 |
| `vaults[*].local_path` | `<instance.root>/vault/<vault.id>` | 파생값과 yaml 값 불일치 시 |
| `vaults[*].options.credentials_path` | `<instance.root>/.credentials/sa_<vault.id>.json` | 파생값과 yaml 값 불일치 시 |
| `operations.gws_min_version` | **`$WIKIHUB_HOME/_system/INSTALLED_VERSIONS.json` 의 `gws` 필드** (install.sh `_install_gws` 가 작성) — file 부재 시 `gws --version` stdout fallback | yaml 값이 빈 문자열 또는 install gws 보다 낮을 때 |
```

**After**:
```markdown
| 필드 | source | patching 조건 |
|---|---|---|
| `instance.root` | `$WIKIHUB_INSTANCE_ROOT` env (install.sh export 또는 `/wh:setup` 호출 env) | env 값과 yaml 값 불일치 시 (**비교 전 양쪽 `os.path.expanduser()` 적용 — `~/wikihub` vs `/home/user/wikihub` 표현 차이 방지**) |
| `vaults[*].local_path` | `<instance.root>/vault/<vault.id>` | 파생값과 yaml 값 불일치 시 (동일 expanduser 적용) |
| `vaults[*].options.credentials_path` | `<instance.root>/.credentials/sa_<vault.id>.json` | 파생값과 yaml 값 불일치 시 (동일 expanduser 적용) |
| `operations.gws_min_version` | **`$WIKIHUB_HOME/_system/INSTALLED_VERSIONS.json` 의 `gws` 필드** (install.sh `_install_gws` 가 작성) — file 부재 시 `gws --version` stdout fallback | yaml 값이 빈 문자열 또는 install gws 보다 낮을 때 |
```

#### 2. _system/commands/setup.md

**Before** (Step 0.2 Case A, L60~62):
```markdown
2. **Derived 필드 patching** (ADR-0031 §Decision B catalog, ADR-0035 — credentials_path/gws_min_version 폐기):
   - `instance.root` → `$WIKIHUB_HOME` env
   - `vaults[*].local_path` → `<instance.root>/vault/<vault.id>`
```

**After**:
```markdown
2. **Derived 필드 patching** (ADR-0031 §Decision B catalog, ADR-0035 — credentials_path/gws_min_version 폐기):
   - `instance.root` → `$WIKIHUB_HOME` env
   - `vaults[*].local_path` → `<instance.root>/vault/<vault.id>`
   - **비교 시 `os.path.expanduser()` 적용 필수** — `~/wikihub` vs `/home/user/wikihub` 등 tilde 확장 표현 차이로 인한 false drift 방지
```

---

## LOW-B: setup.md "실패 처리" 표 — schema version mismatch (exit 2) 행 추가

### 배경
ADR-0031 §Decision E에서 schema version mismatch 시 exit 2를 명시했으나, setup.md의 "실패 처리" 표에 해당 행이 누락되어 있습니다.

### 변경 대상
`_system/commands/setup.md` — 실패 처리 표 (L269~280)

### 변경 전/후 diff

**Before** (L269~280):
```markdown
## 실패 처리

| 실패 시점 | 동작 |
|---|---|
| wikihub.yaml 스키마 위반 | stdout 보고 + exit 1. unit 동기화 안 함 |
| rclone.conf 무효 (일부 vault) | 해당 vault의 unit은 생성하되 enable 권장에서 제외. 보고 + exit 0 |
| rclone.conf 무효 (모든 vault) | 보고 + exit 1 (운영 시작 불가 상태) |
| systemd unit 파일 쓰기 실패 | exit 2 (권한 의심) |
| daemon-reload 실패 | exit 2 + ops-alert 트리거 |
| agent skill 갱신 실패 | 보고 + exit 0 (skill 동작 자체에는 영향 없을 가능성. 다음 호출에서 재시도) |
| Step 6 첫 ingest exit 2 | timer enable 보류 + 사용자 안내 + 보고에 "timer 비활성" 명시 + exit 0 (Step 6 자체는 정상 종료) |
```

**After**:
```markdown
## 실패 처리

| 실패 시점 | 동작 |
|---|---|
| wikihub.yaml 스키마 위반 | stdout 보고 + exit 1. unit 동기화 안 함 |
| **schema version mismatch (operational v ≠ example v)** | **stdout 보고 + exit 2 + ops-alert 트리거. unit 동기화 안 함 (ADR-0031 §Decision E)** |
| rclone.conf 무효 (일부 vault) | 해당 vault의 unit은 생성하되 enable 권장에서 제외. 보고 + exit 0 |
| rclone.conf 무효 (모든 vault) | 보고 + exit 1 (운영 시작 불가 상태) |
| systemd unit 파일 쓰기 실패 | exit 2 (권한 의심) |
| daemon-reload 실패 | exit 2 + ops-alert 트리거 |
| agent skill 갱신 실패 | 보고 + exit 0 (skill 동작 자체에는 영향 없을 가능성. 다음 호출에서 재시도) |
| Step 6 첫 ingest exit 2 | timer enable 보류 + 사용자 안내 + 보고에 "timer 비활성" 명시 + exit 0 (Step 6 자체는 정상 종료) |
```

---

## LOW-C: ADR-0023 §Clone scope — LICENSE 행 표현 강화

### 배경
ADR-0023의 Fetch list 표에서 LICENSE 행의 사유가 "install ≠ redistribution"을 명시하지 않아 법적 의미가 모호합니다.

### 변경 대상
`docs/adr/0023-install-script-distribution-curl-pipe.md` — L103

### 변경 전/후 diff

**Before** (L103):
```markdown
| `LICENSE` | legal · convention — MIT 의 redistribution scope 가 운영 타깃엔 strict 적용 안 되지만 OSS 관례로 포함 (LOW-S1 design review) |
```

**After**:
```markdown
| `LICENSE` | legal · convention — **install ≠ redistribution**: MIT 라이선스의 redistribution 조항은 소스 코드 재배포에 적용되며, 운영 서버에 install.sh로 설치하는 행위는 redistribution이 아님. 단, OSS 관례·라이선스 고지 의무 준수 차원에서 포함 (LOW-S1 design review) |
```

---

## LOW-D: install.sh `_step8_guide` — fresh/update 경로별 안내 분리

### 배경
`_step8_guide` 함수는 fresh install 시에만 호출되지만, update path에 대한 광범위한 안내가 포함되어 있어 stylistic 불일치가 발생합니다. fresh path 범위에 맞게 정합해야 합니다.

### 변경 대상
`install.sh` — `_step8_guide` 함수 (L1234~1312)

### 변경 전/후 diff

**Before** (L1281~1291):
```bash
업데이트는 같은 명령 한 번 더 (ADR-0010 + ADR-0030):
  curl -fsSL https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh | bash

[install/update 동작 — dual-mode (ADR-0030)]
  detect: $WIKIHUB_SRC/_system/VERSION + .git AND → update path / 미만족 → fresh path.
  update path: unstaged guard → systemd stop (15min grace) → git fetch + reset → render →
               daemon-reload → systemd start → verify. 실패 시 자동 rollback (직전 ref 복귀).
  fresh path: clean wipe + clone (ADR-0023 보존). user 파일 (instance.root) 미터치.
  명시적 재설치: install.sh --force-fresh (5초 confirm + 3중 safety guard).
  특정 버전 pin: install.sh --version v0.1.0 (rollback 포함).
```

**After**:
```bash
업데이트는 같은 명령 한 번 더 (ADR-0010 + ADR-0030):
  curl -fsSL https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh | bash
  (detect: $WIKIHUB_SRC/_system/VERSION + .git 존재 → update path 자동 진입)
```

**삭제 대상** (L1284~1291):
```markdown
[install/update 동작 — dual-mode (ADR-0030)]
  detect: ...
  update path: ...
  fresh path: ...
  명시적 재설치: ...
  특정 버전 pin: ...
```

**사유**: `_step8_guide`는 fresh install 시에만 호출되므로 update path 상세 안내는 불필요. update path는 `install.sh --help` 또는 `docs/`에서 참조하도록 유도.

---

## LOW-E: `scripts/lib/config.py` L118-122 warning 로그 systemd journal 도달 검증

### 배경
`config.py`의 warning 로그(`_log.warning(...)`)가 systemd journal에 도달하는지 검증이 필요합니다. 코드 수정은 불필요하며, V12 시나리오 검증만 수행합니다.

### 검증 대상
`scripts/lib/config.py` L118~122:
```python
_log.warning(
    "vault '%s': mount_path (%s) != local_path (%s) — default 패턴 아님. "
    "bind-mount/ramdisk/multi-vault layout 의도가 아니면 yaml 정합 확인 권장.",
    vid, mount_path, local_path,
)
```

### 검증 시나리오 (V12)

| 단계 | 명령 | 기대 결과 |
|---|---|---|
| 1 | `wikihub.yaml`에서 `vaults[0].options.mount_path`를 `local_path`와 다른 값으로 설정 | — |
| 2 | `systemctl --user start wikihub-ingest@<vault_id>.service` | — |
| 3 | `journalctl --user -u wikihub-ingest@<vault_id>.service --since '1min ago' \| grep "mount_path"` | warning 메시지 출력 확인 |

### 산출물
- 검증 결과를 `features/20260528_issue24_code_review_low/v12_verification.md`에 기록
- 검증 실패 시에만 코드 수정 (Python logging → systemd journal forwarding 확인)

---

## 요약

| 항목 | 변경 유형 | 대상 파일 | 코드 수정 필요 |
|---|---|---|---|
| LOW-A | 문서 보강 | ADR-0031, setup.md | 아니오 |
| LOW-B | 문서 보강 | setup.md | 아니오 |
| LOW-C | 문서 보강 | ADR-0023 | 아니오 |
| LOW-D | 스크립트 수정 | install.sh | 예 (안내 텍스트 축소) |
| LOW-E | 검증만 | — | 아니오 (검증 후 필요 시) |

## Definition of Done

- [ ] LOW-A: ADR-0031 + setup.md에 `os.path.expanduser` 적용 시점 명시 완료
- [ ] LOW-B: setup.md 실패 처리 표에 schema version mismatch 행 추가 완료
- [ ] LOW-C: ADR-0023 LICENSE 행에 "install ≠ redistribution" 명시 완료
- [ ] LOW-D: `_step8_guide`에서 update path 상세 안내 제거 완료
- [ ] LOW-E: V12 시나리오 검증 완료 (결과 기록)
