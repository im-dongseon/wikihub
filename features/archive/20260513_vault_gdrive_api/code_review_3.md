# F3 코드 리뷰 R3 (수정 반영분 검증)

리뷰어: feature-dev:code-reviewer (R3)
대상: HEAD + working tree (5 modified + 1 new)
이전 라운드 참조: `features/20260513_vault_gdrive_api/code_review_1.md`, `code_review_2.md`

---

## 1. R1·R2 지적사항 28개 반영 검증

| # | 원래 항목 | 원래 분류 | 반영 상태 | 검증 근거 |
|---|---|---|---|---|
| 1 | CRIT-1: binary text=True 손상 | R1-H1 / R2-CRIT-1 | **부분 반영 (회귀 잔류)** | gws.py:51,86 `binary_output` 추가 + sync.py:351-358 binary 경로 OK. 그러나 `_download_to_vault:319` 에서 `saved = vault_local_path / name` — `name`이 unsanitized raw string 사용 (별도 NEW-1 참조) |
| 2 | CRIT-2: wiki page atomic write (fixed name tmp, try/finally 부재) | R2-CRIT-2 | **완전 반영** | sync.py:369-390 `_atomic_write_wiki_page` — `tempfile.mkstemp(prefix, suffix, dir)` + try/finally + os.replace. state.py:_atomic_write_json 패턴과 통일. |
| 3 | CRIT-3: directory traversal | R2-CRIT-3 | **완전 반영** | sync.py:64-65 `_INVALID_NAME_CHARS` + sync.py:230-249 `_sanitize_relpath` — `../`, 절대경로, control char(\x00-\x1f), backslash 모두 차단. test_sync.py:85-97 커버. |
| 4 | CRIT-4: cursor 순서 (partial-failure window) | R2-CRIT-4 | **완전 반영** | sync.py:572 per-file 처리 후 `save_file_map` 즉시 호출 + sync.py:615-617 루프 끝에서 `save_last_sync` 뒤에 `save_cursor` 순서. |
| 5 | CRIT-6 (I3): cursor가 last_sync 저장 후에 저장 | R1-I3 | **완전 반영** | sync.py:615-617 확인. `save_last_sync` → `save_cursor` 순서 정확. test_sync.py:297-299 I3 검증. |
| 6 | R1-I1: dead-code ternary (`er.tool if ... else er.tool`) | R1-I1 | **완전 반영** | sync.py:548 `extraction_tool=er.tool if er.extraction_status == "success" else None` |
| 7 | R1-I2: `.txt` wiki path 의도 명세 | R1-I2 | **완전 반영 (spec lock)** | sync.py:274 주석 `.txt 포함` + test_sync.py:42-44 `test_compute_wiki_path_txt_keeps_ext` — `.txt.md` 패턴 명시적 lock. |
| 8 | R1-H2 / R2-OBS-1: `%` interpolation → json.dumps | R1-H2 / R2-OBS-1 | **완전 반영** | vault-fetch.py:66-73 `json.dumps({...}, ensure_ascii=False)` + `sys.stdout.flush()`. |
| 9 | R1-L1: frontmatter.py `_StringDumper` 주석 | R1-L1 | **완전 반영** | frontmatter.py:14-20 주석이 "본 subclass에 한정 (PyYAML 다른 Dumper 영향 없음)" 으로 정정. |
| 10 | R1-L2 / R2-SIG-4: `_safe_version` importlib.metadata 기반 + PyPI 패키지명 | R1-L2 / R2-SIG-4 | **완전 반영** | extraction.py:26-37 `importlib.metadata.version(distribution_name)` — `"pdfminer.six"`, `"python-pptx"`, `"python-docx"` 등 PyPI 패키지명 직접 사용. |
| 11 | R1-L3: test_sync.py 부재 | R1-L3 | **완전 반영** | `tests/test_sync.py` 신규 433라인. |
| 12 | R2-SIG-1: last_sync.json 명시적 schema | R2-SIG-1 | **완전 반영** | sync.py:626-638 `_result_to_last_sync_dict` 명시적 dict. `cursor_before/after` 포함. |
| 13 | R2-SIG-2: removed 시 vault binary 미삭제 | R2-SIG-2 | **완전 반영** | sync.py:397-413 `_handle_removed` — wiki unlink + vault_local_path unlink. test_sync.py:371-433 커버. |
| 14 | R2-SIG-3: 파일 크기 cap 미비 | R2-SIG-3 | **완전 반영** | sync.py:307-317 `max_file_size_mb` 게이팅. `options.get("max_file_size_mb")` 로 config 연동. |
| 15 | R2-SIG-4: ImportError 반복 noise | R2-SIG-4 | **부분 반영** | `_safe_version` 정확한 패키지명 사용은 fix됨. 그러나 per-call import (50번 반복 ImportError) 캐싱은 미적용. R2는 startup probe 또는 캐시를 권장했으나 구현 없음. v0.1.0 acceptable으로 명시 선언은 없음. |
| 16 | R2-SIG-5: per-file error silent failure | R2-SIG-5 (OBS-3 연계) | **완전 반영** | sync.py:575-598 `VaultSyncRetryable` → `enqueue_retry` + `save_retry` + `continue`. `VaultSyncFatal` → re-raise. unknown → `log.exception` + `continue`. |
| 17 | R2-SIG-6: incremental root_folder_id post-filter 미구현 | R2-SIG-6 | **완전 반영** | sync.py:217-227 `_passes_trust_boundary` — `root_folder_id not in parents` 체크. test_sync.py:130-138 `test_trust_boundary_root_folder_no_match` 커버. |
| 18 | R2-OBS-2: sync 진행 로그 silent | R2-OBS-2 | **완전 반영** | sync.py:438, 484, 531 등 다수 `log.info` 추가. `_changes_list_iter:208`, `_files_list_iter:176` 완료 로그. |
| 19 | R2-OBS-3: retry queue 미연결 (dead code) | R2-OBS-3 | **완전 반영** | sync.py:580-588 `enqueue_retry` + `save_retry` 실제 호출. |
| 20 | R2-OBS-4: credentials ACL bit 미검증 | R2-OBS-4 | **미반영 (acceptable 선언)** | credentials.py:31 `st_mode & 0o777 != 0o600` 검증만. R2도 "v0.1.0 acceptable"로 명시. |
| 21 | R2-CRIT-4 관련 Incremental commit | R2-CRIT-4 권장 1 | **완전 반영 (Incremental persist 선택)** | 각 file 처리 후 `save_file_map` 즉시 호출. |
| 22 | R2 Q4: `saved_path` 반환값 제거 | R1 Q4 | **완전 반영** | sync.py:293 시그니처 `tuple[ExtractionResult, int]` — saved_path 제거. |
| 23 | R2-V7: root_folder_id 외 bootstrap q= 필터 | R2-V7 | **완전 반영** | `_files_list_iter:156` `'{root_folder_id}' in parents` q 파라미터. |
| 24 | R2 test gap: binary subprocess output | R2 test gap 1 | **미반영** | `test_gws.py`에 binary mock(`\x89PNG` header emit) 테스트 없음. 신규 test_sync.py에도 없음. |
| 25 | R2 test gap: path traversal | R2 test gap 4 | **완전 반영** | test_sync.py:85-97. |
| 26 | R2 test gap: mid-loop exception | R2 test gap 6 | **미반영** | 5개 changes 중 중간 실패 시 file_map/cursor 상태 검증 테스트 없음. |
| 27 | R2 test gap: assertion too lax (`<= 600`) | R2 test gap 8 | **미반영** | test_errors.py 는 이번 수정 범위 밖 — 기존 코드 그대로. |
| 28 | R2 test gap: last_sync stdout JSON 비교 | R2 test gap 10 | **부분 반영** | `test_result_to_stdout_json_minimum`은 exact field 검증. 그러나 last_sync.json과 stdout JSON의 schema 차이를 비교하는 통합 테스트 없음. |

---

## 2. 새 발견 (이번 라운드 추가)

### Critical

**[CRIT][SecRisk] `_download_to_vault` 내부에서 raw unsanitized `name` 사용 — traversal 차단 우회 가능**
(`scripts/lib/sync.py:304, 319`)

`sync()` 루프에서는 `source_relpath = _source_relpath(file_meta)` (= sanitized) 를 계산하지만, 이 값을 `_download_to_vault`에 전달하지 않습니다. 함수 내부에서 다시 `name = file_meta.get("name", fid)` (raw, line 304) 를 읽어 `saved = vault_local_path / name` (line 319) 경로를 직접 구성합니다.

leading slash인 Drive 파일명 (`/foo.md`) → `source_relpath = "foo.md"` (sanitized) + `saved = vault_local_path / "/foo.md"` = `/foo.md` (vault 외부 절대경로로 기록).

`_handle_removed`는 `vault_local_path / entry`(`= vault_local_path / "foo.md"`)를 unlink → 실제 저장 위치(`/foo.md`)와 불일치 → 삭제 실패 (silent, `missing_ok=True`).

수정: `_download_to_vault`에 `source_relpath: str` 파라미터를 추가하고, `name` 대신 그것을 파일 저장 경로로 사용하거나, 함수 내부에서도 `_sanitize_relpath`를 재적용.

신뢰도: **90**

---

### High

**[HIGH][Regression] `vault-fetch.py:80` — `credentials_path` 누락 오류 메시지에 `%` interpolation 잔류**
(`scripts/vault-fetch.py:80`)

```python
reason="vaults[%s].options.credentials_path 누락" % args.vault,
```

`args.vault`는 `^[a-z][a-z0-9_]*$` regex 검증 이후의 값이므로 실제 JSON injection 위험은 없습니다. 그러나 R1-H2 fix 의 불완전한 적용 사례. 같은 패턴이 `sync.py:463, 470`에도 있습니다.

신뢰도: **80**

**[HIGH][NewBug] `_sanitize_relpath` — `candidate.startswith("/")` 체크가 `lstrip("/")` 이후 도달 불가 dead code**
(`scripts/lib/sync.py:240-241`)

```python
candidate = raw.lstrip("/").strip()
if not candidate:
    return None
if candidate.startswith("/"):   # ← 이 조건은 절대 True가 될 수 없음
    return None
```

실질 보안 위험은 없으나, dead code 가 보안 로직에서 오해를 유발.

신뢰도: **85**

**[HIGH][NewBug] Google native export 의 saved 파일 ext 와 실 content 불일치**
(`scripts/lib/sync.py:332-338`)

CSV 텍스트를 `.gsheet` 파일에 저장. F3 범위에서는 동작하나, F5 entity extraction 연계 시 `extract(saved, mime)` 호출하면 `LOCAL_EXTRACTION_DISPATCH` 미스로 실패.

신뢰도: **80**

---

### Medium

**[MED][NewBug] `_handle_removed` — `vault_local_path / entry` 삭제 경로 불일치**
(`scripts/lib/sync.py:411`)

위 CRIT 항목의 downstream. silent skip (`missing_ok=True`). SIG-2 목표 미달.

신뢰도: **85**

**[MED][TestGap] `max_file_size_mb` 게이팅 테스트 없음**
(`tests/test_sync.py`)

SIG-3 fix 경로 검증 부재.

신뢰도: **90**

**[MED][TestGap] `binary_output=True` end-to-end 테스트 없음 — CRIT-1 fix 검증 불완전**
(`tests/test_sync.py`, `tests/test_gws.py`)

`test_gws.py` mock 은 텍스트만 emit. `\x89PNG` 같은 실제 binary bytes 의 round-trip 미검증.

신뢰도: **95**

**[MED][NewBug] `credentials_path` 검증 — `Path("")` 가 `"."`로 평가되어 진단 메시지 누락**
(`scripts/vault-fetch.py:76-77`)

`str(Path(""))` = `"."` → truthy → `if not str(...)` 조건 불충족. `IsADirectoryError` 로 나와서 진단 어려움.

신뢰도: **85**

---

### Low

**[LOW][NewBug] `_sanitize_relpath` — `"."` 단독 통과**
(`scripts/lib/sync.py:246-248`)

`Path(".").parts` = `(".",)` → `".."` `""` 어느 쪽에도 미스. `vault_local_path / "."` = vault_local_path 자체로 write 시도 → `IsADirectoryError`.

신뢰도: **80**

**[LOW][TestGap] mid-loop `VaultSyncRetryable` 시나리오 테스트 없음**
(`tests/test_sync.py`)

R2 test gap 6 미반영.

신뢰도: **90**

**[LOW][SpecMismatch] `_passes_trust_boundary` — `root_folder_id` direct parent only**
(`scripts/lib/sync.py:224`)

코드 주석에 `v0.2.x` 명시되어 있으나 설계서/ADR 에 결정 없음. 하위 폴더 구조 vault 에서 모든 파일 skip 가능 — 운영 시나리오에 따라 CRIT 상승.

신뢰도: **85**

---

## 3. 결론

### 배포 차단 여부: **예**

CRIT 신규 결함 1건 (R3-CRIT-1: `_download_to_vault` raw name 사용).

**즉시 수정 필요 (배포 전)**:

1. **[CRIT] `_download_to_vault` 내부 raw name 사용** — 함수 시그니처에 `source_relpath` 추가
2. **[HIGH] `_sanitize_relpath` dead code 정리**
3. **[MED] `credentials_path` 빈 문자열 미탐지 fix**
4. **[LOW] `_sanitize_relpath` — `"."` 단독 필터 추가**
5. **[LOW] `root_folder_id` direct-parent-only 제약 설계서/ADR 명시**

**다음 PR**:
- `binary_output=True` e2e 테스트
- `max_file_size_mb` 게이팅 테스트
- mid-loop `VaultSyncRetryable` 테스트
- `_safe_version` 캐싱 또는 acceptable 선언
- `root_folder_id` 다중 hop 명시

**무시 가능 (v0.1.0 scope 내)**:
- OBS-4 ACL bit 미검증
- SIG-4 import noise
- test_errors.py `<= 600` lax assertion
