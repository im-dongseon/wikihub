# Design Review 1 — feature-dev:code-reviewer

- **Reviewer**: feature-dev:code-reviewer subagent (Claude, context-fresh)
- **Date**: 2026-05-13
- **Target**: F3 (`vault_gdrive_api`) — plan.md + analysis_and_design.md

## Summary

F3 design은 대체로 일관되고 F2 spec과 ADR을 충실히 반영. 7개 결정(A~G)이 단위 단계로 통합됨: gws 가정은 Step 3 verification 항목으로 적절히 격리, JSON output contract은 ingest.md §Step 2와 field-for-field 일치, bootstrap 두-factor gate는 정확히 AND, ADR-0007 all-JSON 명령은 SQLite 누수 없이 준수. **High confidence 2건**이 Step 3 시작 전 해소 필요: (1) auth_gdrive.py의 credential format이 F2 `_system/` 정본의 `.pickle` 참조와 불일치, (2) JSON output contract의 `wiki_path` 필드 명시 누락. 추가로 medium 3건. 종합: **minor revisions** 필요.

## Findings

### High confidence — must fix before Step 3 implementation

#### H1. §2.4 [D] — Credential 포맷 pickle→JSON 변경이 F2 `_system/` 정본에 미반영

F3 §2.4는 credential format을 pickle→JSON (gws `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` 호환)로 변경. 기술적으로 옳음. 그러나 F2 정본 spec 파일들이 여전히 `.pickle` 참조:

- `_system/wiki-schema.md` line 53: `.credentials/` 디렉토리에 `token_{vault_id}.pickle`
- `_system/commands/ingest.md` line 101: error classification 행 `pickle.loads 예외 (credentials 파손) → 2 (Fatal)`

F3 design은 "포맷만 변경"이라 하나 이 두 `_system/` 라인 update를 F3 scope로 선언 안 함. DoD §6에도 없음.

**Impact**: Step 3 implementer는 auth_gdrive.py를 JSON으로 작성하지만 `_system/` spec은 `.pickle` 유지 → F5/F4 implementer 혼란. setup.md §Step 1 OAuth validation의 `pickle.loads` 행이 production에서 실패.

**Suggested fix**: F3 §3 lift matrix + §6 DoD에 추가 — "`_system/wiki-schema.md` `.credentials/` 행 `token_{vault_id}.pickle` → `token_{vault_id}.json`" + "`_system/commands/ingest.md` error 표 `pickle.loads 예외` → `JSON token load 예외 (credentials 파손)`". 둘 다 surgical 1-line.

---

#### H2. §2.6 [F] / §2.1 [A] — `changed[].wiki_path` 필드가 design output spec에서 trace 누락

F2 ingest.md §Step 2 정본 (line 71): `wiki_path`는 **필수** 필드.

F3 §2.6 `ExtractionResult` tuple은 `(body_text, tool, tool_version, extraction_status, reason)` — `wiki_path` 없음. §B 모듈 구조의 `sync.py`가 "vault relpath → wiki path 변환"을 담당한다고 §3 lift matrix에 있지만, F3 design 어디에도 `wiki_path` 값이 stdout JSON의 first-class 필드로 명시적으로 traced 안 됨. §2.5 bootstrap pseudocode의 `emit_json_to_stdout(result)`의 `result` schema도 spelled out 안 됨.

**Impact**: Step 3 implementer가 F3 design만 읽으면 `wiki_path`가 each `changed[]` entry의 필수 필드임을 인지 못 할 수 있음. 첫 코드 feature이므로 누락 위험 큼.

**Suggested fix**: §2.5 또는 §2.6에 `changed[]` entry spec table을 명시 추가 — 7개 필드(`source_relpath`, `wiki_path`, `operation`, `source_id`, `source_mtime`, `bytes_written`) 모두 나열 + `wiki_path`는 §A2 rule로 `sync.py`가 계산함을 명시.

---

### Medium confidence — should consider

#### M1. §2.3 [C] — "stderr 패턴 미매치 → Fatal" default의 blind spot

Design은 fail-safe 근거(false positive보다 over-alert 안전)는 옳지만, V4 verification 중 또는 gws upgrade 후 unknown stderr 패턴이 출현하면 immediate Fatal 처리 → 노이즈 알림. 미매치 시 `reason` 필드에 raw stderr를 어떻게 보존할지 spec 없음.

**Suggested fix**: §2.3 1줄 추가 — "미매치 시 `reason`에 raw gws stderr (첫 500자) 포함. Step 3 V4에서 미매치 패턴 관측 시 즉시 ADR-0017 후보 매핑 행으로 기록".

---

#### M2. §2.5 [E] — bootstrap의 `gws drive files list` 명령이 verification 목록에 없음

Bootstrap pseudocode `list_all_files(vault_id)`가 `gws drive files list (페이지네이션)` 호출 — 그러나 §4 V1~V8에 `files.list` 항목 없음. pagination 처리 + Drive API v3 응답 schema(`files: []`, `nextPageToken: ...`) verification 필요.

**Suggested fix**: §4 V9 추가 — "`gws drive files list` 명령 + 페이지네이션 schema 확인".

---

#### M3. §2.2 [B] — `lib/credentials.py` 책임이 `/wh:setup` 권한 검증과의 boundary 모호

Design은 `credentials.py`가 "file 존재 + 권한 600 확인"만, token validity check은 gws가 내부 처리. 그러나 F2 setup.md §Step 1은 `creds.valid` check + light API call(`drive.about.get`)을 명시. F4 implementer가 `/wh:setup`을 구현할 때 `credentials.py`의 `validate()` method가 있을 거라 가정할 수 있음.

**Suggested fix**: §2.4 credentials.py 책임 설명에 1줄 — "setup.md §Step 1 OAuth light call(`gws drive about get`)은 `credentials.py` 범위 밖 — `/wh:setup` 구현(F4)이 직접 gws 호출".

---

### Low confidence / nits — optional

#### L1. §2.6 [F] — Google Sheet export MIME type per-entry annotation 누락

EXTRACTION_DISPATCH dict에서 세 Google native 항목(`gdoc`, `gsheet`, `gslides`)이 모두 `'gws-export'`로만 표기. wiki-schema.md §A3는 sheet=`text/csv`, doc=`text/markdown`, slides=`text/plain` 명시. 구현 시 mismatch 가능.

**Suggested fix**: EXTRACTION_DISPATCH dict 주석에 per-type export MIME 명시.

---

#### L2. §2.7 — E2E test sandbox folder가 plan.md 사전 조건에 미명시

§2.7 "Workspace 계정에 test folder 1개 + 3~5 파일" — 그러나 plan.md §사전 조건에는 "Workspace 계정"만. V4 의도적 403 trigger가 production credentials를 손상시킬 위험.

**Suggested fix**: §2.7에 1줄 — "Step 3 시작 전 test Workspace에 `wikihub-test/` 폴더 + fixture 배치. V4 403 trigger는 별도 OAuth client 또는 권한 회수 후 복구 절차 포함".

---

## What I checked but found OK

- ADR-0007 all-JSON: lib/state.py 5개 파일 모두 커버, SQLite 누수 없음
- ADR-0014 gws isolation: lib/gws.py가 단독 subprocess wrapper, google-api-python-client는 auth_gdrive.py에서만 (Path A)
- ADR-0006 orchestration: vault-fetch.py는 agent의 도구로 정확히 positioning
- Bootstrap 두-factor gate: bootstrap_allowed + --bootstrap AND'd correctly
- JSON output contract 완성도 (wiki_path 제외): vault_id, has_changes, source_relpath, operation, source_id, source_mtime, bytes_written, deleted, duration_ms — 9 필드 모두 검증
- Frontmatter string-only YAML: §A1 enforcement 명시
- root_folder_id post-filter: changes API의 user-level 한계 정확히 인식
- PYTHONPATH handling: sys.path.insert + F4 systemd 주입 — 양쪽 환경 clean
- F4/F5 interface signals: env var·scripts 파일 목록·JSON contract 모두 명시됨
- ADR-0015·0017 잠정 / ADR-0016 보류 — lifecycle 정합
- gws 가정 realism: Discovery-based auto-exposure, --params 패턴, changes.list output schema — 모두 reasonable
- OAuth JSON schema (`authorized_user` format): 4-field 표준 Application Default Credentials format, V5 1회 verification로 충분

## Open questions for author

1. **F2 `_system/` update scope in F3 DoD**: H1의 두 `_system/` lines update가 F3 scope인지 F4 scope인지 명시 필요. setup.md `pickle.loads` 행이 잘못된 채 남으면 `/wh:setup` 구현이 혼란.

2. **`last_sync.json` 작성 여부**: §2.5 pseudocode는 `emit_json_to_stdout`·`save_cursor`만 — `last_sync.json` write 미언급. setup.md §Step 1 초기 state 파일 목록에 last_sync.json도 미포함. vault-fetch.py가 last_sync.json을 쓰는지 안 쓰는지 명시 필요.

3. **`exclude_shared_with_me` for changes API**: §3 lift matrix는 trust boundary filter 명시. files.list(bootstrap)는 `q: "sharedWithMe=false"` 가능. changes.list는 직접 필터 없음 → post-filter 필요. Design은 root_folder_id post-filter는 명시(§2.5)했으나 sharedWithMe는 미명시. Step 3 implementer가 trust boundary를 누락할 위험.
