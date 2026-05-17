# Design Review 2 — F3 Implementer perspective

- **Reviewer**: general-purpose subagent acting as Step 3 implementer
- **Date**: 2026-05-13
- **Target**: F3 (`vault_gdrive_api`) — plan.md + analysis_and_design.md

## Verdict

설계는 **대부분 implementation-ready**이고 모듈 경계·외부 인터페이스·dispatch 표·error 분류 결정 골격이 분명하다. 그러나 **6건의 critical blocker**가 있어 현 상태로 Step 3을 시작하면 즉시 designer에게 되돌아가야 한다. 그중 가장 영향이 큰 것은 (a) `wikihub.yaml` 로딩 모듈의 부재(코드는 `wikihub_yaml.vaults[vault_id].options.bootstrap_allowed` 같은 객체 액세스를 가정하지만 그 객체를 만드는 모듈이 spec에 없음), (b) `lib/state.py`가 다루는 5개 state 파일의 **정본 schema 위치 불일치** (cursor·file_map·last_sync는 어디에도 v0.1.0 정본이 없음 — F1 archive의 변경된 구조 + setup.md의 일부만 명시), (c) F3 첫 실행이 `cursor.json`을 **이미 setup.md가 빈 stub으로 작성한 상태**에서 진입한다는 사실이 F3 design에 반영되지 않음 (bootstrap 분기 로직이 "파일 없음" vs "파일 있지만 cursor 빈 문자열" 두 케이스를 구분 안 함).

## Critical implementation blockers

#### 1. `wikihub.yaml` 로딩·검증 모듈이 lib에 없음 — §2.2 / §2.5

**Implementer question**: `vault-fetch.py` 또는 `lib/sync.py`가 `wikihub.yaml.vaults[vault_id].options.bootstrap_allowed`를 어떻게 얻나? 직접 PyYAML로 파싱? 별도 lib 모듈? schema 검증은 누가?

**Current spec**:
- §2.5 의사 코드에서 `wikihub_yaml.vaults[vault_id].options.bootstrap_allowed` 사용 (객체 액세스 가정)
- §2.2 모듈 트리에 `lib/config.py` 또는 `lib/wikihub_yaml.py` **없음**
- `requirements.txt`에는 `PyYAML>=6.0` 있음 (로딩 수단은 있지만 위치 미정)
- F1 §4.2.5의 `load_wikihub_yaml()` helper는 archive 코드로 lift 대상 아님 명시 없음

**Gap**:
1. 모듈 위치 미정 (`lib/config.py` 신설? `vault-fetch.py` main에 인라인?)
2. `vaults[vault_id]`로 dict-by-id 조회 — yaml은 list of dicts (`vaults: [- id: gdrive ...]`). list-to-by-id 변환 책임 위치 미정
3. setup.md Step 1에서 schema 검증 책임이 `/wh:setup`에 있지만, F3 vault-fetch.py가 **재검증 안 한다는 결정**이 design에 없음 — 메인테이너가 `/wh:setup` 우회하고 vault-fetch.py 직접 호출 시 어떻게 되는가?
4. `instance.root` (예: `/opt/wikihub`) 해석은 어디서 — vault-fetch.py CWD? yaml의 instance.root? 환경변수?

**Recommendation**: 
- `lib/config.py` 모듈 추가 명시. 책임: PyYAML safe_load + vault dict-by-id 변환 + 최소 키 존재 검증(`vaults[*].id`·`type`·`options.credentials_path`·`options.bootstrap_allowed`·`instance.root`). schema 전체 검증은 `/wh:setup` 책임이라는 boundary 명시.
- vault-fetch.py가 `wikihub.yaml` 위치를 어떻게 찾는지: design 후보 (a) 환경변수 `WIKIHUB_ROOT` (F4 install.sh가 주입), (b) `--config <path>` CLI 인자 (테스트 가능성↑), (c) 고정 `/opt/wikihub/wikihub.yaml`. 본 결정이 §4 V verification list에 없는 missing decision.

#### 2. `cursor.json` "빈 stub" vs "부재" 두 케이스 — §2.5 vs setup.md Step 1

**Implementer question**: setup.md §Step 1 L2 정본은 신규 vault에 `cursor.json = {"vault_id": "<id>", "vault_type": "<type>", "cursor": "", "cursor_updated_at": null}`을 작성한다. F3 design §2.5 의사 코드는 `cursor = load_cursor(vault_id); if not cursor:` 로 분기. 빈 stub의 `cursor.cursor == ""`은 truthy/falsy 어느 쪽? load 결과 자체는 dict이므로 `if not cursor:` False — 코드대로면 bootstrap 가드를 통과 못 하고 빈 cursor로 `gws drive changes list --params '{"pageToken": ""}'` 호출됨.

**Current spec**:
> ```python
> if not cursor:  # 첫 sync 또는 _state/ 소실
>     if not wikihub_yaml.vaults[vault_id].options.bootstrap_allowed:
>         raise VaultSyncFatal(...)
> ```
> "**bootstrap 시 root_folder_id 적용**" — bootstrap 분기에서 `gws drive changes get-start-page-token` 호출

**Gap**: ingest.md §Step 2 "Bootstrap 가드"는 "`cursor.json` 부재 시"로 명시. setup.md L2는 처음부터 빈 stub 작성. 두 spec이 충돌한다. F3 분기 조건은 셋 중 무엇이어야 하나:
- (a) 파일 존재 여부만 본다 → setup.md L2의 stub과 모순 (stub 있으면 bootstrap 트리거 못 함)
- (b) `cursor.cursor == ""` (빈 문자열) 검사 → ingest.md 표현과 약간 다름
- (c) setup.md를 따라 stub이 항상 있다고 보고, 빈 cursor를 첫 sync로 해석 → 그러면 bootstrap_allowed 가드는 빈 cursor 케이스를 cover

**Recommendation**: F3 design에 "bootstrap 진입 조건" 1줄 명시 — `cursor.json 부재 OR cursor.cursor == ""`. 의사 코드 한 줄을 `if not cursor or not cursor.get("cursor"):` 로 수정. setup.md와 정합 확인. 둘 중 한 spec에 supersede 한 줄 추가.

#### 3. `lib/state.py` schema 정본의 location 흩어짐 — §2.2 / Lift 매트릭스

**Implementer question**: 5개 state 파일의 정본 schema가 spec 어디에 있나? 
- `cursor.json` → setup.md L2 (3개 필드만), F1 §4.4.1 (4개 필드, 다름)
- `file_map.json` → setup.md L2 (3개 필드), F1 §4.4.2 (files dict의 value schema 추가)
- `last_sync.json` → **어디에도 v0.1.0 정본 없음** — F1 §4.4.3에 있으나 F1 archive
- `retry.json` → ADR-0007 (queue 항목 schema 명시) + setup.md L2 (top-level)
- `pending_ingest.json` → ingest.md §Step 3 (schema 명시)

**Current spec**: F3 design §3 lift 매트릭스는 "lib/state.py가 5개 state 파일 atomic JSON write"라고만 명시. 각 파일의 schema 정본 location reference 없음.

**Gap**: F3 implementer가 last_sync.json schema를 작성하려면 F1 archive를 읽어야 하지만, F1 archive는 영속 기록(수정 안 함)이고 본문에 "SQLite 모드"같은 ADR-0007이 supersede 한 내용이 섞여 있음. 어떤 부분을 lift하고 어떤 부분을 무시할지 implementer가 판단해야 함. 또 F1 §4.4.3의 `last_sync.json`은 "cursor_before/cursor_after" 필드를 갖는데 v0.1.0 정본 ingest.md §Step 2 stdout schema에는 cursor 필드가 없음(JSON contract와 last_sync.json schema 차이).

**Recommendation**: F3 design §2 또는 새 §2.8 (state schema 정본)에 5개 파일의 v0.1.0 schema를 명시. 안 그러면 F3 implementer가 사실상 spec writer가 된다. 또는 F2 wiki-schema.md에 state schema 절을 추가하고 F3가 reference. 둘 중 하나 결정 필요.

#### 4. `lib/gws.py` 인터페이스 시그니처 미정 — §2.1

**Implementer question**: `run_gws(...)` 의 정확한 시그니처는?

**Current spec**:
- §2.1: `gws drive changes list --params '{"pageToken":"<token>","pageSize":100,"includeRemoved":true}'` 명령 패턴 명시
- §2.2 모듈 트리: "gws subprocess wrapper (run_gws(cmd, params) → result)"

**Gap**: 
1. `cmd`는 list (`['drive', 'changes', 'list']`) vs string (`'drive changes list'`)?
2. `params` 는 dict (json.dumps internal) vs str (이미 직렬화)?
3. return: subprocess.CompletedProcess 그대로? 또는 parsed JSON dict + stderr str tuple?
4. **timeout**: design은 "agent's hermes timeout"만 언급 (§timeout_sec from wikihub.yaml). gws subprocess timeout은 별개 인자가 필요. 무한 hang 가능성 (e.g., 대용량 binary download). 권장 default 미정
5. **stdout 크기 처리**: `files.export` 또는 `files.get --alt media` 의 binary output을 stdout으로 받으면 capture_output=True가 메모리에 통째 적재. 50MB+ pptx도 통째 buffer? → `--output <path>` 강제하고 가정 명시 필요 (V2/V3 verification이 이를 cover하지만 v0.1.0 starting decision 부재)
6. **CWD/env**: gws가 `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` env var 의존. subprocess.run 호출 시 `env=os.environ.copy()`로 inherit? 또는 명시적 env dict? — design은 "systemd unit이 env 주입"만 언급, Python 측 inherit 가정 명시 없음

**Recommendation**: `run_gws(method: list[str], params: dict, *, timeout_sec: int = 120, output_path: Path | None = None) -> GwsResult`로 시그니처 명시. `GwsResult`는 `(returncode: int, stdout: str | bytes, stderr: str)` dataclass 또는 namedtuple. timeout default + env inherit 가정 + binary는 무조건 `output_path` 강제(stdout buffer 회피) 결정.

#### 5. `lib/errors.py` v0.1.0 starting regex 표 — §2.3

**Implementer question**: §2.3 stderr 패턴 표는 "추정"으로 적혀 있고 정확한 regex 문자열은 V4 verification 후 확정. 그런데 V4 verification은 Step 3 implementation 중에 일어남 → implementer가 V4 결과 받기 전에 `lib/errors.py` 골격을 쓰려면 placeholder가 필요. 어떤 starting 문자열을 코드에 넣어야 하나?

**Current spec**:
> | gws returncode | gws stderr 패턴 (추정) | wikihub exit | severity | 비고 |
> | 1 | `"403"` + `"userRateLimitExceeded"`/`"rateLimitExceeded"`/`"quotaExceeded"` | 75 | retryable | F1 §4.7.5 quota |

**Gap**:
1. 표는 "`"403"` 포함 + 키워드 포함" 같은 자연어 — Python regex 문자열로 변환 시 implementer 자유도가 너무 큼 (substring 매칭? word boundary? case-insensitive?)
2. 두 implementer가 같은 표를 보고 한 명은 `re.search(r"403.*rateLimitExceeded", stderr)`, 다른 한 명은 `"403" in stderr and "rateLimitExceeded" in stderr` 작성 가능 — 결과 호환 불가

**Recommendation**: §2.3을 starting regex 표로 변환 (Step 3 V4 verification 후 refine은 그대로 유지). 예:
```python
# v0.1.0 starting (Step 3 V4 후 refine)
QUOTA_RE = re.compile(r"\b40[03]\b.*(userRateLimitExceeded|rateLimitExceeded|quotaExceeded)", re.IGNORECASE | re.DOTALL)
SCOPE_RE = re.compile(r"\b403\b.*(insufficientPermissions|forbidden)", re.IGNORECASE | re.DOTALL)
AUTH_RE = re.compile(r"\b401\b", re.IGNORECASE)
SERVER_RE = re.compile(r"\b5\d{2}\b", re.IGNORECASE)
NET_RE = re.compile(r"\b(network|timeout|connection reset|connection refused)\b", re.IGNORECASE)
```
이 표가 코드의 starting point. V4 후 refine은 commit으로 추적. 또한 "패턴 모두 미매치 → Fatal" 정책을 `else: return (2, 'fatal', f'unmatched stderr: {stderr[:200]}')`로 명시.

#### 6. `VaultSyncRetryable`·`VaultSyncFatal` 예외 클래스 lift 결정 미명시 — §3 lift 매트릭스

**Implementer question**: F1 §4.2.3은 두 예외 클래스를 Python dataclass 형식으로 정의. F3 design은 §2.5 의사 코드에서 `VaultSyncFatal(reason=..., remediation=...)` 사용. F3가 이 dataclass를 lift하나? 어느 모듈에 정의? `lib/errors.py`? 별도 `lib/exceptions.py`?

**Current spec**:
- §2.5 의사 코드에서 `raise VaultSyncFatal(reason=..., remediation=...)` 만 사용 (vault_id 인자 누락 — F1 §4.2.3 시그니처는 `vault_id`가 필수 keyword)
- §2.2 모듈 트리: `errors.py` ("gws exit code 분류 → 75/2 매핑") — exception 클래스 정의 명시 없음
- §3 lift 매트릭스: F1 §4.2.3 lift 명시 없음

**Gap**: 
1. 예외 클래스 위치 미정 → implementer가 `lib/errors.py` 안에 정의? 별도?
2. F3 §2.5 의사 코드의 `VaultSyncFatal(reason=..., remediation=...)`은 F1 §4.2.3의 `vault_id` 필수 인자를 누락 — F3 lift 시 시그니처 변경 의도인가 아니면 의사 코드 오류인가?
3. `lib/errors.py classify_gws_error()`는 tuple `(exit_code, severity, reason)` 반환 — exception 발생은 어디서? `lib/sync.py`가 tuple 받아서 raise? raise 시 어떤 인자 매핑?
4. `__main__` (vault-fetch.py)에서 exception → sys.exit 매핑: `VaultSyncRetryable` → 75, `VaultSyncFatal` → 2, 그 외 → 1? — design에 없음

**Recommendation**: 
- §2.2 모듈 트리에 `lib/errors.py` 책임 추가: "VaultSyncRetryable·VaultSyncFatal 예외 클래스 정의 + classify_gws_error() helper"
- F1 §4.2.3 시그니처 그대로 lift 명시 (vault_id 필수). 또는 명시적으로 vault_id를 optional로 변경하고 그 결정을 본문에 기록
- vault-fetch.py main()의 try/except 패턴을 F1 §4.2.5에서 lift (대부분 그대로 사용 가능) — design에 한 줄 reference 추가

## Significant ambiguities (should clarify before Step 3)

#### 7. `lib/extraction.py` 각 함수 시그니처·반환 형식 — §2.6

**Current spec**: 
```python
def extract(file_path: Path, mime_type: str) -> ExtractionResult:
    """Returns: (body_text, tool, tool_version, extraction_status='success'|'failed', reason)"""
```

**Gap**: 
1. `ExtractionResult`가 dataclass인지 NamedTuple인지 dict인지 미정. 5개 필드 dict 반환이면 frontmatter.py가 그 dict를 받아 처리 — 인터페이스 contract 필요
2. 각 형식별 추출 로직 detail 부재:
   - `.pptx`: 슬라이드 제목만? 본문 텍스트도? F1 archive에는 v0.2.6 reference로 위임하나 v0.2.6 코드를 어디서 어떻게 보나? (`/Users/1004790/workspace/wikicurate/_system/wiki-schema.md` reference 있지만 그것도 schema 문서 — 코드 패턴은 별도)
   - `.xlsx`: F1 archive §A3는 "시트 이름 + 헤더 + row count"가 token saving 패턴 — F3가 lift 안 하면 row dump 50MB 가능. 명시 필요
   - `.pdf`: pdfminer.six의 `extract_text(path)` 단순 호출이면 OK. 단 encrypted PDF는 별도 처리 (wiki-schema.md A3 명시 — `[extraction failed: encrypted PDF]`)
3. `tool_version`: python-pptx의 `__version__` 식 접근법은 패키지마다 다를 수 있음 (pdfminer.six는 `pdfminer.__version__` 또는 `pkg_resources.get_distribution('pdfminer.six').version`). 일관 방법 미정
4. Google native export (`.gdoc`·`.gsheet`·`.gslides`)는 `gws drive files export`로 이미 텍스트 — 이 경우 extraction.py의 책임은 무엇? sync.py가 직접 처리? extraction.py가 dispatch하지만 "passthrough"?

**Recommendation**: 
- `ExtractionResult` dataclass 명시 (필드 5개 + 자료형)
- 각 추출 함수의 v0.2.6 reference 코드 lift 정확 위치 명시 (또는 "v0.2.6 reference 코드 그대로 lift" 명시)
- `.xlsx` 처리는 "시트 이름 + 헤더 + row count + 첫 10행" 같은 구체적 정책 또는 "full dump"로 결정
- `tool_version` 획득 방법 통일 (`importlib.metadata.version("python-pptx")` 권장)

#### 8. `lib/frontmatter.py` YAML emit 정책 구체화 — §3 lift 매트릭스

**Current spec**: "yaml 출력 시 string 통일 (YAML native date·datetime 금지)"

**Gap**:
1. `yaml.safe_dump`의 어떤 옵션 사용? `default_flow_style=False`(block)? `sort_keys=False`(insertion order)? `allow_unicode=True`(한글)?
2. 빈 list는 `[]` (flow style) vs `\n` (block empty) — wiki-schema.md A1은 "flow style 표기 통일"로 빈 리스트는 `[]` 명시. 그러면 default_flow_style=False는 inconsistent (빈 리스트도 `- ` 형식이 되거나 unspecified)
3. `2026-05-13` 같은 date-like string이 PyYAML 기본 dumper에서 native date로 emit 안 되도록 — `default_flow_style=False`만으로는 부족. `default_style='"'` 또는 명시적 `!!str` 태그 또는 custom dumper 필요
4. frontmatter delimiter (`---` 위아래)는 어떻게? PyYAML은 emit 안 하므로 frontmatter.py가 직접 `f"---\n{yaml_str}---\n{body}"` concat?

**Recommendation**: `lib/frontmatter.py` 의 구체 패턴 명시:
```python
import yaml
def emit_frontmatter(meta: dict) -> str:
    body = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, default_flow_style=False, width=1000)
    return f"---\n{body}---\n"
```
+ date-like string은 quote 강제 (`yaml.add_representer(str, ...)` 또는 명시적 `repr` 처리). 빈 list `[]` flow style 처리 — wiki-schema.md A1과 정합.

#### 9. `lib/sync.py` orchestration 단계별 sequence — §2.5

**Current spec**: bootstrap 분기 + 증분 분기 의사 코드는 있으나 각 분기 내 sequence는 high-level.

**Gap**:
1. "for each change: download → extract → write source page → update file_map" 의 정확한 순서:
   - file_map 갱신은 매 file 후? 또는 batch 후 한 번?
   - download 실패 시 다음 file 처리 continue? abort?
   - extraction 실패 시 wiki page는 "[extraction failed]" body로 작성 진행 (wiki-schema.md A3) — 그러나 download가 성공해야 binary가 vault에 보존됨. 순서: vault에 binary save → extract attempt → wiki page write (성공/실패 무관) → file_map 갱신
2. `changes.removed` 처리: 
   - script가 wiki source 파일 삭제 + vault의 binary 삭제 + file_map에서 제거 — 3개 step 순서
   - `deleted[*]`이 ingest.md stdout schema에 명시 (string list of `source_relpath`)
   - vault 외부 파일도 같이 삭제? wiki-schema.md 책임 매트릭스는 sync가 "다운로드·갱신"이라 삭제 권한도 있는 듯하지만 명시 없음
3. Pagination: `nextPageToken` 처리. 한 sync 사이클 = changes.list 여러 page 합쳐 single transaction? 또는 page 단위로 cursor 갱신? F1 §4.4.1 "atomic write"는 단일 cursor — 그러면 모든 page 끝난 후 한 번 영속화. 그런데 page 100 처리 중 SIGKILL 받으면 처음부터 다시 — 멱등성 보장하나? (다운로드 멱등 OK, file_map 갱신은 atomic write 안 했으니 partial 가능 — recovery는 다음 sync에서 같은 cursor 재실행이지만, file_map은 partial이 lost)
4. `bytes_written` 누적: download된 바이트 size 합산? 각 file metadata의 byte size 합산? wiki source page는 추출 텍스트 길이? — ingest.md §Step 2 schema: "다운로드 바이트 수 — 메트릭용" → 다운로드 size로 결정 가능하지만 명시 필요

**Recommendation**: §2.5 또는 새 §2.5.1로 sync.py orchestration sequence 표 작성:
```
1. cursor 분기 (bootstrap vs incremental)
2. changes 또는 files list 획득 (pagination 끝까지)
3. for each change:
   a. download (or export) → vault local_path 저장 (atomic — tmp + replace)
   b. extract → text 또는 [extraction failed: ...]
   c. wiki source page write (atomic)
   d. file_map in-memory mutation
4. bulk file_map atomic write (전체 처리 후 1회)
5. last_sync.json atomic write
6. cursor.json atomic write (가장 마지막 — 부분 실패 후 재시도 보장)
7. stdout JSON emit
```
정확한 partial-failure 의도까지 명시.

#### 10. Bootstrap 모드의 `files.list` pagination + filter — §2.5

**Current spec**: "bootstrap 모드: changes 없음 → files.list로 전체 스캔"

**Gap**:
1. `gws drive files list`의 인자 schema 미명시 (V1 verification에는 changes.list만 등장 — files.list도 V1에 추가 필요)
2. `q` 파라미터에 `'<folder_id>' in parents`는 직계 자식만 — 재귀 탐색은 별도 구현 (BFS/DFS로 폴더 트리 walk)
3. `exclude_shared_with_me: true` 적용: `q`에 `'me' in owners`로 가능하지만 명시 없음
4. `include_patterns`·`exclude_patterns` (F1 §4.3.1) 적용 시점 — list 결과를 post-filter? gws에서 prefilter? F3 design은 본 옵션을 lift 안 함 (V0.1.0 단순화로 무시?)

**Recommendation**: bootstrap files.list의 의사 코드 추가. include/exclude patterns은 v0.1.0 scope에서 빠지는지(F3에서 미구현 결정) 명시. V1에 files.list도 추가.

#### 11. `auth_gdrive.py` 의존성·SCOPES 검증 — §2.4

**Current spec**: 
- `from google_auth_oauthlib.flow import InstalledAppFlow` 사용
- `SCOPES`는 §4.7.6에서 lift — `['https://www.googleapis.com/auth/drive.readonly']` 단일
- argparse 인자: `--client-secret`·`--out` (plan.md 명시)

**Gap**:
1. `google-auth-oauthlib`은 runtime 의존? 또는 dev-only? OCI 서버에서 vault-fetch.py 실행 시 import 안 됨 — `auth_gdrive.py`만 import. 그런데 `requirements.txt`는 단일 파일이라 OCI 서버에도 설치됨. dev/runtime 분리 권장
2. `creds.client_id`·`creds.client_secret`·`creds.refresh_token`은 google-auth 라이브러리의 Credentials 객체 attribute — 실제 attribute 이름 검증 필요 (v2 라이브러리에서 `creds._client_id` 또는 `creds.client_id` — 변할 수 있음)
3. argparse 정확한 인자명: `--client-secret`은 dash형식, Python에서 `args.client_secret` 접근 — 또는 underscore? 또는 positional? — 명시 안 됨

**Recommendation**:
- `scripts/requirements.txt` (runtime) + `scripts/requirements-auth.txt` (dev only, google-auth-oauthlib) 또는 `requirements.txt` 안에 주석으로 분리. 결정 명시
- `argparse.ArgumentParser` 시그니처 예시 1줄 추가
- google-auth-oauthlib의 `creds` 객체 attribute는 V5 verification에 명시적으로 추가 (현재 V5는 token JSON schema 검증만 — attribute 접근 검증 분리)

#### 12. test 디렉토리 위치·fixture 패턴 — §2.7

**Current spec**: "pytest 기본", "mocked gws subprocess"

**Gap**:
1. 테스트 위치: `tests/` (repo root)? `scripts/tests/`? — plan.md는 `tests/test_vault_fetch.py` 명시 (repo root)
2. subprocess mock 패턴: `unittest.mock.patch('subprocess.run')` vs `pytest-mock` `mocker.patch` vs PATH에 fake gws 바이너리 — 결정 필요
3. fixture 파일: `tests/fixtures/sample.pptx` 등 위치 — repo에 binary commit OK? .gitignore? Git LFS?
4. sandbox Workspace 계정의 존재 가정 — 메인테이너가 이미 가지고 있나? 신규 발급 필요? V5 verification에 포함되나? E2E 테스트는 매번 실행? 1회성?
5. CI 미설정이라 manual `pytest` 가정 — 어떤 명령? `cd scripts && pytest tests/`? `pytest tests/`?

**Recommendation**: `tests/` 위치 + `tests/conftest.py` fixture (gws mock CompletedProcess factory) + `tests/fixtures/` 디렉토리 + `pytest-mock` 의존성 추가 (`requirements-dev.txt`). E2E는 "메인테이너 1회 수동 실행" 명시 (CI 외).

## Acceptable for v0.1.0 (defer to implementation discovery)

이 항목들은 설계가 의도적으로 defer했으며 implementer가 verification commands로 surface해도 사고 없이 진행 가능:

- **V1 (changes.list 인자 schema)**: gws의 동적 schema는 Step 3 첫 1시간에 `gws schema drive.changes.list`로 확인 가능. 결과가 가정과 다르면 sync.py의 list_changes() 함수만 변경 — 다른 모듈 영향 없음. **OK to defer.**
- **V2 (files.export 출력 방식)**: stdout vs `--output` 결정은 lib/gws.py 내부 1줄. **OK to defer.**
- **V3 (files.get binary 다운로드)**: 동일. **OK to defer.**
- **V6 (gws version pinning)**: ADR-0015로 발의 예정. F4 책임이 큼. F3 단독은 메인테이너 dev box의 brew 또는 npm 글로벌 버전으로 충분. **OK to defer.**
- **V7 (root_folder_id changes API 동작)**: post-filter fallback 명시되어 있음. **OK to defer.**
- **V8 (extraction 의존성 호환)**: requirements.txt 설치 1회로 surface. **OK to defer.**

단 V4 (stderr 패턴)는 blocker #5에 명시한 대로 v0.1.0 starting regex 표가 design에 필요. V5 (credentials JSON schema)는 blocker #11에 명시한 대로 attribute 접근까지 verification 확장 필요.

## What's implementation-ready

- **외부 인터페이스 (stdout JSON contract)**: ingest.md §Step 2가 정본. F3 sync.py가 그대로 emit 가능. 명확.
- **exit code 0/75/2 매핑**: ingest.md + design 의사 코드 + ADR-0014 + F1 §4.2.5 lift 가능. 명확.
- **모듈 분할 (§2.2)**: 7개 lib 모듈 + 2개 진입 스크립트 구조 명확. (단 blocker #1의 config.py 신설 필요)
- **OAuth pickle → JSON 전환 (§2.4)**: ADR-0014 호환 위해 JSON 포맷 결정 명확. 외부 운영 절차도 lift.
- **wiki-schema.md A2 파일명 규약**: binary `<relpath>.<ext>.md` 등 명확. 직접 lift 가능.
- **wiki-schema.md A3 extraction tool dispatch**: §2.6 dispatch 테이블 mime→tool 매핑 명확.
- **wiki-schema.md A1 frontmatter 자료형**: date는 string, list는 flow `[]` 명확 (단 blocker #8의 emit 정책 구체화 필요).
- **`pending_ingest.json` 작성·삭제는 agent 책임**: F3 vault-fetch.py가 다루지 않음 — boundary 명확.
- **신뢰 경계**: `exclude_shared_with_me`·`root_folder_id` 정책 source는 wiki-schema.md §신뢰 경계로 명확 (단 적용 구현은 blocker #10에 영향).

## Operational reality check

#### A. Dev box 첫 실행: 메인테이너가 vault-fetch.py를 어떻게 manual 실행하는가?

설계가 명시 안 한 가정: `python scripts/vault-fetch.py --vault gdrive --bootstrap`이 dev box에서 어떻게 동작?
- `WIKIHUB_ROOT` 환경변수? `/opt/wikihub/wikihub.yaml`이 dev box에 없음 → CWD 기반 path? `--config <path>` CLI 인자 (블로커 #1과 연동)?
- `_state/gdrive/` 디렉토리는? `/wh:setup`이 만들어준다는 전제 — 그러나 vault-fetch.py가 standalone 호출되면 setup이 안 돌았을 수 있음. fail-fast vs auto-create?
- `wiki/sources/gdrive/`도 같은 문제
- `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` env var를 dev box에서 어떻게 set? `export ...` manual? 메인테이너가 매번 기억?

이 모든 게 운영 측면에서 F3가 standalone runnable해야 dev box 검증이 가능한데 design은 systemd 환경만 가정. **권장**: design에 "dev box 수동 실행 절차" 1절 추가 (3-5줄). 또는 `--config <path>` CLI 인자 + auto-create directory 결정 + dev 환경변수 export 예시.

#### B. 첫 실행 후 stdout/stderr 운영자 가시성

설계가 명시 안 한 사항:
- 정상 종료 시 stdout = ingest.md JSON. stderr = ?
- 진행 로그(`processing meetings/Q1.pptx ...`)는 어디로? stderr? logging module to file?
- F4의 systemd unit이 `StandardOutput=append:logs/...` 할 텐데 그 logs/sync.log가 stdout JSON과 진행 로그가 섞인 형태로 누적될 가능성. agent (F5)는 stdout만 JSON parse하면 OK이지만 systemd journal/file은 mixed
- design은 "logging" 모듈 사용 의도가 없음 — print? `lib/log.py`?

**권장**: design에 "stdout = ingest.md JSON only, stderr = human-readable progress + warning, no third logging file from script"같은 1줄 결정. logging.basicConfig(stream=sys.stderr) 패턴 명시.

#### C. gws 미설치 환경에서의 fail-fast

`gws` CLI가 PATH에 없으면 `subprocess.run(['gws', ...])`가 `FileNotFoundError`. design은 이 경우 어떤 exit code? 2 (Fatal)? — implicit이지만 명시 권장. lib/gws.py의 첫 호출에서 catch 후 VaultSyncFatal로 분류 (remediation: "install gws — see F4 install.sh").

#### D. 파일명 special char 운영 위험

wiki-schema.md A2는 한글·공백 파일명 허용. Drive의 파일명에 `\`·`/`·newline·NUL이 들어가면 (Drive는 `/` 같은 char도 파일명에 가능 — slash escape) POSIX path로 변환 시 충돌. design은 이 sanitize 로직을 lib/sync.py 어디에 두는지 명시 없음. v0.1.0 v0.1.0에서 `\` 또는 `/` 포함 파일명을 어떻게 처리? skip? rename? — implementer가 추측해야 함.

**권장**: F3 design에 path sanitize 정책 1줄 — "POSIX 비호환 char (`/`·`\0`·newline) 포함 파일은 skip + stderr warning + file_map 미등록". 또는 v0.1.0 scope-out 명시.

#### E. 첫 commit + 미실행 상태에서 review 어려움

F3는 코드 산출물 약 800-1500 LOC 예상. Step 4 code review가 멀티모델인데 reviewer가 실제 실행 가능한 환경 없음 (gws + Drive 계정 + OAuth pickle 필요). review는 정적 분석 + spec 정합성만 가능. 메인테이너가 V1-V5 verification 결과를 design refresh + 이후 ADR-0017로 옮기는 시점 명확 필요 — code review 시점에 design이 v1 (Step 2 작성) 상태인지 v2 (V1-V5 후 refine) 상태인지. **권장**: Step 3 의 verification 절차를 "verification commit"으로 분리 (스타트 1 commit로 design.md update + ADR-0017 발의 + 그 후 본 code commit). Step 4 reviewer는 verification commit 결과를 정본으로 보고 리뷰.
