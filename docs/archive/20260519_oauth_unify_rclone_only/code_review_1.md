# Code Review 1 — OAuth 통일 + gws 폐기 (rclone 단독)

- **Reviewer**: Claude Opus 4.7 (1M context) — 새 세션, 컨텍스트 초기화
- **Date**: 2026-05-19
- **대상 ref**: HEAD (작업 트리)
- **정본**: features/20260519_oauth_unify_rclone_only/analysis_and_design.md v1, docs/adr/0035-rclone-only-unified-oauth.md (Accepted, 2026-05-19)
- **pytest 결과**: **54 passed, 1 skipped** (`~/.local/bin/pytest tests/`, 0.07s)

---

## 종합 권고: **refine**

설계 매트릭스 (§3.1) 의 변경 항목은 대부분 반영됐고 핵심 알고리즘 (mount_diff, false-deleted 가드, source_id key migration, rename 처리) 도 ADR-0035 와 정합. 다만 ADR-0035 가 명시한 "단일화" 약속을 깨는 **잔존 흔적** (install.sh `_step5_instance_dirs` 가 `~/.credentials/wikihub/` 여전히 생성, mount.py 의 SA-기반 remediation 메시지, requirements.txt L2 의 gws 주석, wiki-schema.md L32·L69·L287 의 cursor·SA 흔적, setup.md L217·L289·L290-291 의 `bootstrap_allowed` 잔존, ingest.md L161 의 Cursor log) 가 HIGH·MED 다수. 배포 차단급 결함은 없으나 ADR-0035 cascade 의미가 운영자에게 일관 전달되지 않음 — refine 후 재리뷰.

---

## CRIT (배포 차단)

결함 없음.

---

## HIGH (정합 손상 또는 운영 위험)

### H1. install.sh `_step5_instance_dirs` 가 `~/.credentials/wikihub/` 여전히 생성·chmod 700 — ADR-0035 §"install.sh 단순화" 위반

**위치**: `install.sh:646-672` (`_step5_instance_dirs` 함수 전체)

**문제**: ADR-0035 §"install.sh 단순화" L136 가 명시:

> Step 5.3 `_step5_instance_dirs` 의 `~/.credentials/wikihub/` 생성 폐기 (rclone.conf 만 필요 — `~/.config/rclone/`)

그러나 현재 `_step5_instance_dirs` 는 여전히 (1) `mkdir -p $HOME/.credentials/wikihub`, (2) `chmod 700`, (3) `*.json` 파일들에 chmod 600 enforce 루프를 수행. ADR-0035 cascade 후엔 이 디렉토리에 SA JSON 이 배치될 일이 없는데 install 직후 빈 dir 가 매번 생성·검증됨 — "rclone.conf 단일 인증 자료" 라는 정본 약속과 운영자 멘탈 모델 충돌.

또한 `analysis_and_design.md` §4.5 After Step 5 spec 자체가 5.3 의 책임을 "rclone.conf 권한 chmod 0600 검증만" 으로 축소하라고 했는데, install.sh 에는 그 검증은 별도 `_enforce_rclone_conf_perms` (Step 4.5) 에 이미 있고 `_step5_instance_dirs` 는 잔여 SA 코드만 남음.

**권장 수정**:

```bash
_step5_instance_dirs() {
    mkdir -p "$WIKIHUB_HOME"
    # ADR-0035: ~/.credentials/wikihub/ 폐기. rclone.conf 단일 인증.
    # 권한 검증은 _step45_rclone 의 _enforce_rclone_conf_perms 가 책임.
    ok "Step 5 instance dir 확인 ($WIKIHUB_HOME)"
}
```

또는 함수 자체 제거 + `main()` 호출 라인 (L1594) 제거 — `_step45_rclone` 와 `mkdir -p $WIKIHUB_HOME` 만 남기면 충분.

---

### H2. `_system/commands/setup.md` L217·L289·L290-291: `bootstrap_allowed` / `.credentials/` 잔존

**위치**: `_system/commands/setup.md:217, 289, 290-291`

**문제 1 — L217**:

> **진입 조건**: `--enable` 플래그 + Step 1~5 통과 + `bootstrap_allowed: true` vault 1개 이상.

ADR-0035 §Decision (δ2) + `_system/commands/setup.md` L221 자체에 "bootstrap_allowed 폐기 후 cursor 의미 부재" 로 갱신한 부분과 정면 충돌. L217 의 "bootstrap_allowed: true vault 1개 이상" 조건이 그대로면 ADR-0035 후 모든 vault 가 false 인 yaml.example 정합에서 Step 6 자체가 trigger 안 됨 — 첫 ingest prompt 미발화 → ADR-0022 깨짐.

**문제 2 — L289-291** (install.sh ↔ /wh-setup 책임 표):

```
| `wikihub.yaml` (Step 6 — `bootstrap_allowed` 환원) | — | ✓ |
| `instance.root` mkdir + `.credentials/` chmod 700 | ✓ (`_step5_instance_dirs`) | — |
| credentials chmod 600 enforce | ✓ (`_step5_instance_dirs`) | — |
```

ADR-0035 cascade 후 `bootstrap_allowed` 환원 자체가 없음 (cursor 모델 폐기). `.credentials/` chmod 700 + credentials chmod 600 enforce 둘 다 폐기 (H1 항목).

**권장 수정**:

- L217: 조건에서 `bootstrap_allowed: true vault 1개 이상` 제거 → `+ enabled: true vault 1개 이상`.
- L289 행 삭제 (Step 6 의 bootstrap_allowed 환원 항목 자체).
- L290-291 두 행 삭제 (H1 정합).

---

### H3. `_system/wiki-schema.md` L32: `cursor.json` 가 _state schema 의 정본 디렉토리 트리에 잔존

**위치**: `_system/wiki-schema.md:31-37`

```
├── _state/{vault_id}/                # vault별 sync 영속 상태 (all JSON, ADR-0007)
│   ├── cursor.json
│   ├── file_map.json
...
```

**문제**: ADR-0035 §state schema 갱신 L113 명시 "`cursor.json` 폐기". setup.md / ingest.md 는 "cursor.json 폐기" 주석 갱신됐지만 wiki-schema.md 의 디렉토리 트리 (운영자가 자주 보는 정본) 는 그대로. ADR-0035 의 "운영자 수동 rm" remediation 도 `cursor.json` 을 명시 — 정본 schema 가 그 파일을 valid state 로 listing 하는 상태가 모순.

**권장 수정**: L32 라인 (`│   ├── cursor.json`) 삭제.

---

### H4. `_system/wiki-schema.md` L69 + L287: SA credentials 외부 격리 + `.credentials/*.pickle` 흔적

**위치**: `_system/wiki-schema.md:69, 287`

```
~/.credentials/wikihub/               # SA credentials 외부 격리 (ADR-0029 §Decision 갱신)
```

```
| `.credentials/*.pickle` | read + atomic refresh write (ADR-0003) | 미접근 |
```

**문제**: ADR-0029 가 Superseded by ADR-0035 이고 ADR-0035 가 `credentials_path` + `~/.credentials/wikihub/` 둘 다 폐기 정의했지만, wiki-schema.md 의 디렉토리 트리 + 파일 권한 표는 그대로. 운영자는 wiki-schema.md 가 정본 schema 이므로 이걸 보고 "여전히 `~/.credentials/wikihub/` 가 있어야 하는구나" 라고 오인.

**권장 수정**:

- L69 라인 (`~/.credentials/wikihub/  …`) 삭제.
- L287 행 (`.credentials/*.pickle`) 삭제.
- L286 부근 권한 표에서 ADR-0003 / ADR-0029 참조 정리.

---

### H5. `_system/commands/ingest.md` L161: `**Cursor**: <token-prev> → <token-new>` log.md 예시 잔존

**위치**: `_system/commands/ingest.md:155-171` (Step 5 log.md append 예시)

```markdown
## YYYY-MM-DD HH:MM:SS KST

- **Trigger**: systemd timer | manual
- **Cursor**: `<token-prev>` → `<token-new>`
- **Changed**: N files
```

**문제**: ADR-0035 cascade 가 cursor 모델 자체 폐기. log.md 의 `Cursor:` 라인이 정의된 입력 (cursor token) 자체가 없으므로 agent 가 무엇을 write 할지 미정의 — F2 ingest playbook 의 agent (Hermes) 가 이 라인을 빈 문자열로 채워 `Cursor: <> → <>` 와 같은 무의미 항목 발생.

**권장 수정**: L161 라인 삭제. 대신 `listing_count_before`/`listing_count_after` (sync.py 의 SyncResult 가 이미 산출) 를 사용하거나, 그냥 라인 자체 제거.

---

### H6. `scripts/requirements.txt` L2: gws CLI subprocess 주석이 정본인 양 남음

**위치**: `scripts/requirements.txt:1-2, 10-11`

```
# Runtime dependencies (OCI server)
# OAuth & Google Drive 접근은 gws CLI subprocess가 담당 (ADR-0014) — google-* lib는 dev only
...
# yaml round-trip writer (ADR-0031) — /wh:setup Step 0 의 template materialization +
# Step 6 의 bootstrap_allowed 환원이 단일 helper (`scripts/lib/yaml_writer.py`) 호출.
```

**문제**: requirements.txt 가 ADR-0014 + bootstrap_allowed 를 정본으로 명시 — 둘 다 supersede 됐는데 주석은 그대로. 신규 메인테이너가 venv deps 설치 시 첫 접하는 파일이 잘못된 모델을 광고함.

**권장 수정**: L2 주석을 `# OAuth & Google Drive 접근은 rclone CLI subprocess 가 담당 (ADR-0035) — google-* lib 미사용` 로 변경. L11 주석에서 `bootstrap_allowed 환원` 표현 제거 (Step 6 의 책임이 ADR-0035 후 단순화).

---

### H7. `scripts/lib/mount.py` L42-52, L256, L267-268: SA JSON remediation 메시지가 fatal alert payload 에 그대로 박힘

**위치**: `scripts/lib/mount.py:42-52, 246-268`

```python
# scripts/lib/mount.py:42-45
#   - "no such file or directory.*\.credentials/sa_" — credentials_path 파일 사라짐 (R15-M5
#     V<N> R15 리뷰 — 이전 `sa_` literal 은 Drive 폴더의 정상 파일명 `sa_report.docx` 에도
#     매칭하는 false positive 위험. `.credentials/sa_` 으로 narrow)

# L52
r"invalid_credentials|no such file or directory.*\.credentials/sa_"

# L254-258  fatal alert payload
"reason": f"rclone OAuth/SA revoked/corrupt: {error_snippet[:200]!r}",
"remediation": (
    f"SA JSON 갱신 (~/.credentials/wikihub/sa_{vault_id}.json) "
    f"+ chmod 0600 + systemctl --user restart wikihub-mount@{vault_id}.service"
),
```

**문제**: ADR-0035 후 `~/.credentials/wikihub/sa_<vid>.json` 경로 자체가 폐기. fatal 발생 시 ops-alert 에 전달되는 remediation 이 운영자에게 잘못된 복구 절차를 안내 ("SA JSON 갱신" — SA 자체가 폐기됐는데). 또한 stderr regex 의 `.credentials/sa_` literal 도 매칭 자체가 안 됨 (해당 경로 없음) → mount.py 의 rclone fatal pattern detection 이 실효성 떨어짐.

**참고**: analysis_and_design.md §3.2 (영향 받지 않는 영역) 에 mount.py 가 listing 됐지만 이는 "함수 signature 무변경" 이지 "내부 SA-스럼 메시지가 그대로여도 무관" 의 의미 아님 — over-implementation 의 반대 (under-implementation).

**권장 수정**:

- L42-45 주석: `~/.credentials/sa_` → rclone OAuth 컨텍스트로 갱신 ("`oauth2: token expired`" / "`invalid_grant`" 매칭 패턴 강화).
- L52 regex: `r"invalid_credentials|invalid_grant|oauth2: token expired"` 류로 갱신.
- L254-258: remediation 을 `setup.md §Step 5.5 — rclone config 재발급 + chmod 0600 ~/.config/rclone/rclone.conf` 로 변경.
- L267-268 도 동일하게 SA 흔적 제거.

---

## MED (개선 권고)

### M1. `scripts/lib/rclone.py:21` — `VaultSyncRetryable` import 누락 시 `lsjson()` timeout 케이스에서 NameError 위험 없음 (확인): 결함 없음. 단 unused symbol surfacing 검토.

`rclone.py` L19 `from typing import Any` 와 L17 `from dataclasses import dataclass` 는 사용됨. unused import 없음. classify_rclone_error 의 패턴 매칭은 정합. (예외 메시지 한국어/영어 혼용 일관성은 LOW)

### M2. `scripts/lib/mount_diff.py:64-78` — `_passes_filter` 가 dead hook

```python
def _passes_filter(item, *, exclude_shared_with_me: bool) -> bool:
    _ = exclude_shared_with_me
    return True
```

**문제**: 함수가 항상 True 반환 + 미사용 인자 underscore 처리. ADR-0035 §γ filter 책임을 lsjson default 동작에 위임한 결정 자체는 정합 (analysis_and_design.md §5 + L75 주석에 명시). 그러나 인터페이스만 존재하고 본체 로직이 없는 함수는 "future hook" 라는 표면적 약속만 남기고 호출 site 의 readability 만 떨어뜨림. Karpathy §2 (Simplicity First) 위반 — 요청 외 abstraction.

**권장 수정**: `_passes_filter` 함수 자체 제거. `compute_diff` 의 `listing_filtered` 구성을 `[item for item in listing if _is_indexable(item)]` 로 단순화. ADR-0035 hook 화 결정은 §5 주석에 한 줄로 보존.

### M3. `scripts/lib/sync.py:550-551` — SyncResult 의 `listing_count_before` 가 실제로는 `file_map_count_before`

```python
listing_count_before=diff.file_map_count_before,
listing_count_after=diff.listing_count,
```

**문제**: ADR-0035 §state schema 갱신 L114 가 명시 "`last_sync.json` 의 `cursor_before`/`cursor_after` 필드 제거 (또는 `listing_count_before`/`listing_count_after` 로 대체)". 의미상 두 field 는 "사이클 시작 시 listing 크기" vs "사이클 끝 시 listing 크기" 인데, 현재 코드는 before 자리에 file_map 크기 (이전 사이클의 결과) 를 박음.

전체 사이클이 single lsjson 호출이라 before/after 차이가 없는 자연 특성 — 그러나 이름이 의미 호도. `listing_count` (스칼라 1개) 또는 `file_map_count_before`/`listing_count` (2개, 명명 정확) 가 정합.

**권장 수정**: `last_sync.json` schema 의 두 키를 `file_map_count_before` + `listing_count` 로 rename. 또는 `listing_count` 단일 필드로 통합. ADR-0035 L114 의 "또는" 분기를 명확히.

### M4. `_handle_rename` 의 atomicity — old wiki unlink → new write 사이 partial 가시화 window

**위치**: `scripts/lib/sync.py:357-374`

```python
if prev_entry:
    old_wiki = instance_root / str(prev_entry.get("wiki_path", ""))
    if old_wiki.is_file():
        old_wiki.unlink(missing_ok=True)
        log.info("rename: unlink old wiki %s", old_wiki)
# 새 path 로 create/modify 흐름 재사용
_handle_create_or_modify(...)
```

**문제**: 다음 시나리오에서 wiki 가 partial state:

1. old wiki unlink 성공.
2. `_handle_create_or_modify` 내부 `_read_from_mount` 가 `VaultSyncRetryable` raise (mount 부재 / OSError).
3. 호출자 sync() 의 except 가 retry 큐 enqueue + 다음 entry 진행.

결과: 사이클 종료 시 old wiki 도 new wiki 도 둘 다 부재. wiki/sources/ 가 일시적 누락 (다음 사이클 재시도까지). 그리고 file_map[source_id] 의 wiki_path 가 이미 새 path 로 갱신됐다면 (`_handle_create_or_modify` 가 file_map 갱신 후 raise) 부정합 더 심함.

ADR-0035 §rename 처리 (analysis_and_design.md §5.4) 는 "renamed 는 created + delete 가 아니므로 source_id 보존. wiki_path 만 갱신" 이라고 명시 — 단일 atomic operation 가정.

**권장 수정**: rename 처리를 다음 순서로 재정렬:

```python
# 1. 새 path 로 read + write 먼저 (raise 시 old wiki 그대로 보존)
new_er, new_bytes = _read_from_mount(...)
_atomic_write_wiki_page(instance_root / new_wiki_path, new_page_text)
# 2. file_map 갱신
file_map["files"][source_id] = {...new wiki_path...}
# 3. 마지막에 old wiki unlink (state 정합 후)
if prev_entry and prev_entry["wiki_path"] != new_wiki_path:
    (instance_root / prev_entry["wiki_path"]).unlink(missing_ok=True)
# 4. save_file_map (atomic)
```

또는 unlink 를 마지막으로 옮기는 것만으로도 결함의 절반 (새 wiki 부재 윈도우) 해결.

### M5. false-deleted 가드 임계 비교 부등호 `>` 가 0.3 threshold 의 경계값 처리에 따라 모호

**위치**: `scripts/lib/sync.py:460`

```python
if diff.file_map_count_before > 0 and diff.delete_ratio > false_delete_threshold:
```

**문제**: ADR-0035 §ζ2 + analysis_and_design.md §5.3 둘 다 "초과" 라고 명시 — `>` 가 정합. 단 운영자가 임계값을 정확히 `0.0` 설정 (테스트 또는 의도적 sensitive 모드) 시 `delete_ratio = 0` (삭제 0건) 인 사이클은 통과해야 함. 현재 코드는 `delete_ratio > 0` 만 차단 — 0건 사이클은 정상 통과. 정합. 단 default 0.3 의 경계 값 (정확히 30% 삭제) 에서 통과/abort 결정이 운영자 의도와 다를 수 있음 (ADR-0035 가 ">30%" 라고 표기). 정합. 본 항목은 결함 없음 — 단 테스트 케이스에 경계값 (`delete_ratio == threshold`) 미커버.

**권장 수정**: tests/test_sync.py 에 `delete_ratio == threshold` 경계 케이스 추가 (현재 통과 동작 확인).

### M6. `classify_rclone_error` 의 fallback 이 unconditional VaultSyncFatal — Retryable 분류 누락 위험

**위치**: `scripts/lib/rclone.py:142-146`

```python
return VaultSyncFatal(
    vault_id=vault_id,
    reason=f"rclone exit {returncode}: {stderr_500}",
    remediation="rclone stderr 확인 후 setup.md §Step 5.5 또는 install.sh 재실행.",
)
```

**문제**: stderr 패턴 미매칭 시 default 가 Fatal — 안전 사이드 (운영자 즉시 인지) 이지만 ADR-0035 §γ3 unsupported 'change' subcommand 등 rclone 신규 버전이 internal error 로 종료할 경우 (`exit 1 + "internal error"` stderr) 매번 ops-alert 발화 → 운영자 노이즈. analysis_and_design.md §6 의 "rclone v1.x stable 단독화로 alpha 부담 자체 제거" 의 의도 (안정 운영) 와 약간 충돌.

**권장 수정**:
- rclone exit code 별 매핑 표를 추가 (rclone 의 `Exit Code 0-9` 공식 정의 활용). 예: exit 1 (Syntax) → Fatal, exit 5 (Temporary) → Retryable, exit 7 (Less serious) → Retryable.
- 또는 v0.2.x deferred 로 명시 (현재 default Fatal 의 안전 sided 가 v0.1.0 운영자 1명 base 에선 충분 — Karpathy §2 "200줄을 50줄로" 정합).

### M7. `tests/test_sync.py` — rename 처리 + retry queue 흐름 미커버

**문제**: test_sync.py 의 3 테스트 (`listing_zero`, `delete_ratio_exceeds`, `first_run_all_created`) 가 핵심 가드 + first-run 흐름은 커버. 그러나 ADR-0035 의 핵심 가치 중 하나인 **rename 처리** (M4 atomicity 도 관련) 가 sync orchestration 레벨 테스트로 없음. mount_diff 단위로는 `test_renamed_when_path_differs_same_id` 가 있으나, sync() 가 호출하는 `_handle_rename` 자체의 wiki page mv + file_map 갱신 흐름이 미검증.

**권장 수정**: tests/test_sync.py 에 다음 케이스 추가:

```python
def test_sync_rename_updates_file_map_and_wiki(tmp_path, monkeypatch):
    # file_map 에 id_a → original.md 등록, mount FS 에 renamed.md 만 존재
    # → wiki/sources/gdrive/original.md unlink + wiki/sources/gdrive/renamed.md write
    # → file_map[id_a].source_relpath == "renamed.md"
```

### M8. ingest.md L72 의 operation enum 갱신은 있으나 `deleted` 도 명시 필요

**위치**: `_system/commands/ingest.md:72`

```json
"operation": "<enum 'created'|'modified'|'renamed', 필수 — ADR-0035: renamed 추가>",
```

**문제**: enum 에 `deleted` 가 없음. sync.py 의 `ChangedFile.operation` 은 created/modified/renamed 만 — `deleted` 는 별도 list `deleted` 로 emit (sync.py L74). 정합. 단 ingest.md L78 의 `"deleted": [...]` 는 string list (relpath only) — schema 가 일관됨. 따라서 본 항목은 false-positive: 결함 없음. (M8 retract — 자체 검증.)

---

## LOW (nit / 스타일)

### L1. `scripts/lib/extraction.py` L5, L218: gws 흔적 주석

```python
# L5
- Google native (.gdoc/.gsheet/.gslides): gws drive files export — body 는 sync.py 가 호출

# L218
Google native 는 본 함수가 처리 안 함 (sync.py 가 gws export 후 ``extract_text`` 호출).
```

**문제**: rclone mount export-formats 로 대체된 시점에 주석 미갱신. 코드 자체는 mime 매핑만 — 동작 무영향. 단 docstring 이 호도.

**권장 수정**: L5 → "Google native (.gdoc/.gsheet/.gslides): rclone mount `--drive-export-formats` 가 mount FS 에서 직접 변환된 binary 제공". L218 → "rclone mount export-formats 로 변환된 binary 를 extract_text 가 처리".

### L2. `scripts/lib/sync.py` L30: `from .extraction import GWS_EXPORT_MIME` — 심볼명이 ADR-0035 cascade 후에도 GWS 접두사

**문제**: ADR-0035 가 gws 폐기를 명시했지만 mime 매핑 상수의 의미는 "Google Workspace native mime → ext" 로 유효. 즉 `GWS` 가 "gws CLI" 가 아닌 "Google Workspace" 약어 — 의미 보존 가능. 단 신규 코드 reader 가 혼란 가능 (gws CLI 폐기됐는데 왜 GWS_… 상수가?).

**권장 수정**: `GOOGLE_WORKSPACE_EXPORT_MIME` 또는 `GOOGLE_NATIVE_EXPORT_MIME` 으로 rename (find-replace 6개소). 또는 docstring 1줄로 의미 명시 ("GWS = Google Workspace mime, not gws CLI"). LOW 등급 — 동작 무영향.

### L3. `_system/systemd/wikihub-vault@.service.template` L39 주석의 `cursor·credentials` 잔존

```ini
# 운영자가 cursor·credentials 등 개입 전까지 fatal 사이클은 ops-alert dedup 정책 ...
```

**문제**: ADR-0035 후 cursor 도 credentials 도 없음 (rclone.conf 만). 사소한 doc drift.

**권장 수정**: `cursor·credentials` → `rclone.conf·yaml` 로 갱신.

### L4. `scripts/lib/exceptions.py` L21-22 docstring 의 gws 흔적

```python
예: OAuth 401 invalid_grant, gws auth/discovery 결함.
raise 시 sync 사이클은 *즉시 중단* — cursor advance 되지 않음.
```

**문제**: docstring 갱신 누락. 동작 무영향.

**권장 수정**: `gws auth/discovery 결함` → `rclone OAuth/network 결함`. `cursor advance 되지 않음` 는 모델 자체 폐기로 의미 부재 — `file_map 갱신 안 됨` 으로 변경.

### L5. `scripts/lib/mount.py` L11, L179: docstring 의 gws drive changes 흔적

```python
# L11
# ... gws drive changes list → _resolve_mount_path → _read_from_mount → ...

# L179
race window 차단 — gws changes 알린 변경분이 mount read 시점에 fresh content 보장.
```

**문제**: H7 의 일부. docstring 흐름 설명이 ADR-0027 시대.

**권장 수정**: `gws drive changes list` → `rclone lsjson` 로 갱신. L179 도 동일.

### L6. `scripts/lib/yaml_writer.py` L3: bootstrap_allowed 환원 주석

**문제**: H2 의 일부 — yaml_writer docstring 도 ADR-0035 후 Step 6 의 책임 단순화 미반영.

---

## 정합 확인된 강점

1. **mount_diff 알고리즘 정확성** (compute_diff): 4 분류 (created/modified/renamed/deleted) 가 ADR-0035 §state schema 갱신 정의와 비트 단위 일치. `_is_indexable` 의 IsDir + null ID 필터 정합. `delete_ratio` 의 `file_map_count_before == 0` 조기 0.0 반환 (zero-division 가드) 정확.
2. **false-deleted 가드** (sync.py L451-469): 두 가드 (listing 0건 + delete_ratio > threshold) 각각 별도 raise 로 fail-fast. 임계 비교 부등호 `>` 가 ADR-0035 "초과" 정의 정합. Retryable + retry_after=300s 가 systemd timer 의 다음 사이클 흡수 + ADR-0024 연속 발화 escalate 와 정합.
3. **rclone subprocess wrapper** (rclone.py): `RcloneBinaryMissing` 분리 + `subprocess.TimeoutExpired` → VaultSyncRetryable 매핑 + `classify_rclone_error` 의 3 분류 (auth/quota/network) 가 ADR-0035 §3 stderr 매핑 표와 정합. `start_new_session=True` 로 SIGTERM propagation 차단.
4. **assert_rclone_config** (credentials.py): 파일 존재 → 권한 0o600 → remote 등록 3단 검증 + 각각 별도 VaultSyncFatal 명시 reason. 환경변수 default 처리 (RCLONE_CONFIG → ~/.config/rclone/rclone.conf) 정합.
5. **state migration 안전성**: state.py 의 load_file_map 이 Before schema (source_relpath 키) 잔존 시 dict 그대로 반환 + compute_diff 가 file_map["files"] 의 key 를 source_id 로 가정하고 listing 의 ID 와 lookup → 모든 entry 가 created 분류 + 모든 prev entry 가 deleted 분류 → false-delete 가드가 abort. **운영자가 수동 rm 안 한 시점에 fail-loud** — ADR-0035 §"운영자 수동 state migration" 가정 충실 보존.
6. **외부 인터페이스 보존**: `result_to_stdout_json` (sync.py L580) 의 JSON contract 가 F2 ingest.md §Step 2 schema 와 일치 (vault_id/has_changes/changed[]/deleted[]/duration_ms). `operation` enum 에 `renamed` 추가됐고 ingest.md L72 가 ADR-0035 갱신 명시.
7. **ADR cascade**: ADR-0014/0015/0017/0027/0029 모두 Status `Superseded` + ADR-0035 새로 Accepted + docs/adr/README.md 인덱스 모두 정합 (L61-92 검증). ADR-0035 cross-references 절이 Supersedes / 무관 ADR 분류 명확.
8. **systemd unit template**: `wikihub-vault@.service.template` 의 `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` Env 제거됐고 L17 주석으로 ADR-0035 trace. 정합.
9. **render_systemd_units.py**: `_current_vault_subs` (L229-236) 에서 `credentials_path` 제거 + ADR-0035 trace 주석 + `sync_interval_sec` 만 잔존. 깔끔.
10. **테스트 커버리지 (커버 부분)**: test_mount_diff (9 cases) 가 4 분류 + delete_ratio + dir/null-id 필터 모두 커버. test_credentials (5 cases) 가 missing/wrong-perm/missing-remote/valid/env-default 케이스 커버. test_sync 의 3 케이스가 false-delete 가드 + first-run bootstrap 커버.

---

## pytest 실행 결과

```
$ ~/.local/bin/pytest tests/
============================= test session starts ==============================
platform darwin -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0
collected 55 items

tests/test_config.py .......                                             [ 12%]
tests/test_credentials.py .....                                          [ 21%]
tests/test_extraction.py .....s                                          [ 32%]
tests/test_frontmatter.py ....                                           [ 40%]
tests/test_mount_diff.py .........                                       [ 56%]
tests/test_state.py ............                                         [ 78%]
tests/test_sync.py ............                                          [100%]

======================== 54 passed, 1 skipped in 0.07s =========================
```

(skipped 1건은 `test_extraction.py` 의 pdfminer.six 의존 optional case — ADR-0035 무관)

---

## 우선순위 요약

| 등급 | # | 항목 | 차단성 |
|---|---|---|---|
| HIGH | 7 | H1 (install.sh credentials), H2 (setup.md bootstrap_allowed), H3 (wiki-schema cursor.json), H4 (wiki-schema .credentials/), H5 (ingest.md Cursor log), H6 (requirements.txt gws), H7 (mount.py SA remediation) | 배포 시 운영자 멘탈 모델 혼란 + fatal alert payload 오안내 |
| MED | 6 | M1 (false-positive — 제외), M2 (_passes_filter dead hook), M3 (listing_count naming), M4 (rename atomicity), M5 (boundary test), M6 (classify fallback), M7 (rename sync test 누락) | 개선 권고 — 운영 안정성 개선 |
| LOW | 6 | L1~L6 (docstring/주석 drift) | 동작 무영향, 일관성만 |

---

## 종합 평가

ADR-0035 의 핵심 정합 (lsjson + file_map source_id 키 + false-delete 가드 + cursor 폐기 + rclone.conf 단일) 은 모두 구현됨. 코드 품질·테스트도 양호. 다만 **HIGH 항목 7건이 모두 "정본 문서가 폐기된 모델을 광고" 패턴** — install.sh / setup.md / wiki-schema.md / ingest.md / requirements.txt / mount.py 가 ADR-0035 이전 모델을 그대로 가지고 있어, 본 feature 의 "ADR cascade 단순화" 정합 효과를 깎음. mount.py 의 SA JSON remediation 메시지 (H7) 는 운영 시 fatal alert payload 에 박혀 운영자에게 잘못된 복구 절차 안내 — 운영 위험 등급.

**refine 권고**: 위 HIGH 7건을 모두 처리한 후 재리뷰. MED 항목 중 M2·M4·M7 은 동일 사이클에서 처리 권장 (atomicity 결함 잠재). LOW 는 별도 cleanup feature 또는 본 사이클 마지막에 일괄.
