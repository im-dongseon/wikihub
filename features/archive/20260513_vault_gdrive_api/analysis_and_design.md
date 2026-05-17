# Analysis & Design: vault_gdrive_api

- **Feature ID**: `20260513_vault_gdrive_api`
- **작성일**: 2026-05-13 (KST)
- **선행 feature**: F1 (`v030_initial_architecture`), F2 (`wikihub_schema_v1`) — 둘 다 archive
- **정본 입력**: F2 `_system/commands/ingest.md` §Step 2 (JSON contract), F2 `_system/wiki-schema.md` (frontmatter·파일명·extraction tool 표), ADR-0001/0003/0006/0007/0014
- **approved**: 2026-05-13

### Revision Log

| Version | Date | 변경 요지 |
|---|---|---|
| v1 | 2026-05-13 | 결정 7건(A·B·C·D·E·F·G) + Step 3 verification points 명시 |
| v2 | 2026-05-13 | 멀티모델 design review 2건(design_review_1.md feature-dev:code-reviewer, design_review_2.md F3 implementer 관점) 결과 27건 전수 반영. R1 high·med·low(H1·H2·M1~M3·L1·L2·Q1~Q3 10건) + R2 critical(B1~B6 6건) + SIG 6 + OPS 5. 추가 모듈: lib/config.py(B1), lib/exceptions.py(B6 — VaultSyncRetryable·VaultSyncFatal F1 §4.2.3 lift). state schema 종합표 신설(B3). lib/gws.py·lib/errors.py signature·regex 시작점 명시(B4·B5). cursor 부재 vs empty stub 의미 해소(B2). changed[] entry full schema 정본(H2). wiki-schema·ingest.md의 pickle 참조 ADR-0014 정합으로 갱신(H1, _system/ 정본 동기화). last_sync.json 작성 정책(Q2). exclude_shared_with_me changes API post-filter(Q3). V9 추가(bootstrap files.list). 추가 ADR 발의 없음(B5·B6는 spec 명시로 충분, ADR-0017 잠정은 V4 후로 유지) |

---

## 1. 배경 · 목적

본 feature는 wikihub의 **첫 코드 산출 feature**. F1·F2의 spec을 Python 구현으로 실체화. ADR-0014에 따라 Drive 접근은 `gws` CLI (subprocess) 기반.

산출물: `scripts/vault-fetch.py` (단일 진입점) + `scripts/lib/` (공통 모듈, 추후 F6 재사용)

F3은 mechanical layer 책임만 — semantic phase(entities·concepts·analyses 갱신)는 F5(`hermes_adapter`)가 담당.

---

## 2. 결정 종합 (7건)

### 2.1 [A] gws 인터페이스 — 웹 docs + 구조적 추론

웹 docs 확인 결과:
- gws는 Google Discovery Service 런타임 파싱 → Drive API 모든 메서드 자동 노출
- 인자: `--params '<JSON>'` 형식으로 API 파라미터 전달
- 출력: structured JSON to stdout
- exit code: 0/1/2/3/4/5 (성공/API/auth/validation/discovery/internal)
- credentials: `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` 환경변수 — **JSON 형식**

**가정 (Step 3 verification 필요)**:

| 항목 | 가정 |
|---|---|
| `changes.list` 명령 | `gws drive changes list --params '{"pageToken":"<token>","pageSize":100,"includeRemoved":true}'` |
| 출력 JSON | `{"changes": [...], "newStartPageToken": "...", "nextPageToken": "..."}` (Drive API v3 정합) |
| `changes.getStartPageToken` 명령 | `gws drive changes get-start-page-token` (첫 sync 부트스트랩) |
| `files.export` 명령 | `gws drive files export --params '{"fileId":"...","mimeType":"text/markdown"}'` → stdout으로 export 결과 |
| `files.get` 명령 (binary) | `gws drive files get --params '{"fileId":"...","alt":"media"}'` → stdout binary 또는 `--output <path>` |
| stderr 형식 | gws 일반 패턴 추정: HTTP error 발생 시 `"<level>: <method> <status> <reason>"` 같은 1행 — Step 3 실증 |

**Step 3 verification commands** (구현 시 dev box에서 실행 후 spec 갱신):
```bash
gws drive changes list --help
gws drive files export --help
gws schema drive.changes.list       # 정확한 인자 schema
gws drive changes get-start-page-token --params '{}'  # 실제 출력 확인
```

### 2.2 [B] 모듈 구조 — `scripts/` + `scripts/lib/`

F2 plan.md 제안 그대로:

```
scripts/
├── vault-fetch.py             # 단일 entry: argparse + main()
├── auth_gdrive.py             # macOS dev box용 1회성 OAuth (출력 = JSON, ADR-0014 정합)
├── requirements.txt           # 의존성 명시 (runtime)
├── requirements-dev.txt       # 의존성 명시 (macOS dev box only — google-auth-oauthlib, pytest)
└── lib/
    ├── __init__.py
    ├── config.py              # wikihub.yaml load + 스키마 검증 (B1)
    ├── exceptions.py          # VaultSyncRetryable·VaultSyncFatal (F1 §4.2.3 lift, B6)
    ├── state.py               # atomic JSON write·load (cursor·file_map·last_sync·retry·pending_ingest)
    ├── credentials.py         # OAuth JSON load + 권한 600 확인 (token refresh는 gws 담당)
    ├── gws.py                 # gws subprocess wrapper (signature 정본 — B4 아래)
    ├── errors.py              # gws exit code + stderr → exit 75/2 분류 (regex 시작점 — B5 §2.3)
    ├── extraction.py          # binary → text 추출 dispatch (python-pptx 등)
    ├── frontmatter.py         # source 페이지 frontmatter 작성 (wiki-schema.md A1 자료형 표 정합)
    └── sync.py                # vault sync orchestration (changes.list → fetch → write → state 갱신)

tests/                         # repo root 기준 (B6 implementer 권장 — sys.path import)
├── test_state.py
├── test_errors.py
├── test_extraction.py
├── test_credentials.py
├── test_frontmatter.py
├── test_sync.py
└── fixtures/                  # 샘플 .pptx, .docx, gws stderr 샘플 등
```

#### B1 lift — `lib/config.py` 책임

```python
# lib/config.py
@dataclass
class Config:
    instance_root: Path
    timezone: str
    vaults: dict[str, VaultConfig]          # key: vault_id
    operations: OperationsConfig
    agent: AgentConfig

@dataclass
class VaultConfig:
    id: str
    type: str                                # 'gdrive_api' | 'directory'
    enabled: bool
    sync_interval_sec: int
    local_path: Path
    options: dict                            # type별 옵션 (credentials_path, root_folder_id 등)

def load_wikihub_yaml(path: Path = None) -> Config:
    """default path: /opt/wikihub/wikihub.yaml. dev box override는 환경변수 WIKIHUB_YAML"""
```

vault-fetch.py 진입 시점에 `cfg = load_wikihub_yaml(); vault_cfg = cfg.vaults[vault_id]` 패턴. 스키마 위반 시 `VaultSyncFatal`.

#### B6 lift — `lib/exceptions.py` F1 §4.2.3 lift

```python
# lib/exceptions.py
class VaultSyncRetryable(Exception):
    def __init__(self, vault_id: str, retry_after_sec: int, reason: str):
        self.vault_id = vault_id
        self.retry_after_sec = retry_after_sec
        self.reason = reason
        super().__init__(f"[{vault_id}] retryable: {reason}")

class VaultSyncFatal(Exception):
    def __init__(self, vault_id: str, reason: str, remediation: str):
        """vault_id는 필수 (F1 §4.2.3·notify 경로용)"""
        self.vault_id = vault_id
        self.reason = reason
        self.remediation = remediation
        super().__init__(f"[{vault_id}] fatal: {reason}")
```

raise 사이트 모두 `vault_id=` keyword arg 전달 (F1 §4.6.6 notify 경로에서 사용).

#### B4 정본 — `lib/gws.py` signature

```python
# lib/gws.py
from dataclasses import dataclass
import subprocess
import json
from typing import Any

@dataclass
class GwsResult:
    returncode: int
    stdout: str               # raw stdout (JSON 파싱은 호출자 책임 — gws가 항상 JSON은 아님)
    stderr: str
    duration_ms: int

def run_gws(
    args: list[str],                    # 예: ['drive', 'changes', 'list']
    params: dict | None = None,         # 예: {'pageToken': '...', 'pageSize': 100}
    *,
    timeout_sec: int = 300,
    env_extra: dict[str, str] | None = None,
) -> GwsResult:
    """
    gws subprocess 호출. CWD는 invoker(이 함수 호출자) 기준.
    
    환경변수:
    - GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE: install.sh가 systemd unit으로 주입.
      vault-fetch.py 자체는 env 안 만짐.
    - env_extra는 dev box 수동 호출 시 oneshot override용.
    
    Returns: GwsResult (returncode + raw stdout/stderr + 측정 시간)
    
    Raises:
    - subprocess.TimeoutExpired (호출자가 catch → VaultSyncRetryable 매핑)
    - FileNotFoundError (gws binary 미설치 — OPS 안내)
    """
    cmd = ['gws'] + args
    if params is not None:
        cmd += ['--params', json.dumps(params)]
    # subprocess.run with text=True, capture_output=True ...
```

**규약**:
- `args`는 list (shell injection 차단)
- `params`는 dict — `json.dumps`로 변환해 `--params`로 전달
- `stdout`은 raw string (호출자가 `json.loads` 또는 텍스트로 처리)
- gws binary 부재(`FileNotFoundError`) → vault-fetch.py가 `VaultSyncFatal('gws 미설치', remediation='install.sh 재실행')` 발생

PYTHONPATH 처리:
- vault-fetch.py 상단에 `sys.path.insert(0, os.path.dirname(__file__))` 1줄 → `from lib import state, gws, ...`
- install.sh가 systemd unit에 `Environment=PYTHONPATH=/opt/wikihub/scripts` 주입 (F4 책임)

F6(`vault_directory`) 재사용 가능 모듈: `state.py`, `errors.py` (vault-agnostic 부분), `extraction.py`, `frontmatter.py`.

→ ADR-0016 (모듈 구조) **잠정 발의 보류** — 본 결정은 spec 명시로 충분 (F3 단독 결정 + F6 시점에 재검토 시 ADR 발의)

### 2.3 [C] error 분류 매핑 — abstract interface + 추정 default

`lib/errors.py`의 핵심 함수:

```python
def classify_gws_error(returncode: int, stderr: str) -> tuple[int, str, str]:
    """
    gws subprocess 결과를 wikihub exit code로 매핑.
    
    Returns: (wikihub_exit_code, severity, reason)
        wikihub_exit_code: 0 | 75 | 2
        severity: 'success' | 'retryable' | 'fatal'
        reason: 진단 메시지
    """
```

**Default 매핑 표 (Step 3 verification 후 정본 확정)**:

| gws returncode | gws stderr 패턴 (추정) | wikihub exit | severity | 비고 |
|---|---|---|---|---|
| 0 | — | 0 | success | 정상 종료 |
| 1 | `"403"` + `"userRateLimitExceeded"`/`"rateLimitExceeded"`/`"quotaExceeded"` | 75 | retryable | F1 §4.7.5 quota |
| 1 | `"403"` + `"insufficientPermissions"`/`"forbidden"` | 2 | fatal | scope 회수 |
| 1 | `"401"` | 2 | fatal | token 무효 또는 client_secret rotation |
| 1 | `"5"` 시작 (5xx) | 75 | retryable | 서버 오류 |
| 1 | `"network"` / `"timeout"` / `"connection"` | 75 | retryable | 네트워크 일시 장애 |
| 1 | 위 패턴 모두 미매치 | 2 | fatal | **alert 우선 — 안전 default** |
| 2 | — (gws auth error) | 2 | fatal | credentials 만료/무효 |
| 3 | — (validation error) | 2 | fatal | vault-fetch.py 호출 버그 |
| 4 | — (discovery error) | 2 | fatal | gws 자체 문제 |
| 5 | — (internal error) | 2 | fatal | gws 자체 문제 |

**Resilience 정책 (M1 정합)**: stderr 패턴 미매치 시 Fatal로 격상 + **`reason` 필드에 raw gws stderr (첫 500자) 포함** (정확한 진단 보존). Step 3 V4 verification에서 미매치 패턴 관측 시 즉시 ADR-0017 후보 매핑 행으로 기록.

**v0.1.0 starting regex (B5 정합)** — `lib/errors.py` 구현 시 출발점 (Step 3 V4 후 refine):

```python
# lib/errors.py
import re
from typing import Literal

GWS_API_ERROR_PATTERNS = [
    # (pattern, severity, exit_code)
    (re.compile(r'\b403\b.*(userRateLimitExceeded|rateLimitExceeded|quotaExceeded)', re.IGNORECASE), 'retryable', 75),
    (re.compile(r'\b403\b.*(insufficientPermissions|forbidden)', re.IGNORECASE), 'fatal', 2),
    (re.compile(r'\b401\b'), 'fatal', 2),
    (re.compile(r'\b5\d{2}\b'), 'retryable', 75),
    (re.compile(r'(timeout|connection|network)', re.IGNORECASE), 'retryable', 75),
]

def classify_gws_error(returncode: int, stderr: str) -> tuple[int, str, str]:
    if returncode == 0:
        return (0, 'success', '')
    if returncode == 1:
        for pat, sev, exit_c in GWS_API_ERROR_PATTERNS:
            if pat.search(stderr):
                return (exit_c, sev, stderr[:500])
        # 미매치 — Fatal + raw stderr 보존
        return (2, 'fatal', f'gws unrecognized: {stderr[:500]}')
    # exit 2~5 모두 Fatal
    return (2, 'fatal', f'gws exit {returncode}: {stderr[:500]}')
```

위 regex는 **시작점**. Step 3 V4 verification에서 실제 stderr 샘플 관측 후 갱신. ADR-0017 발의 시점에 정본화.

→ ADR-0017 **잠정 발의 (gws stderr 패턴 매칭 표)** — Step 3 verification 후 Status `Accepted` 전환

### 2.4 [D] OAuth credentials handling — JSON 포맷 + token-scp 패턴 유지

ADR-0003 + ADR-0014 호환 (옵션 α 채택):

**`scripts/auth_gdrive.py` (macOS dev box 전용)**:

```python
# 의사 코드
def main(client_secret_path, out_token_path):
    """
    OAuth flow 후 token을 gws-compatible JSON으로 작성.
    
    Output JSON (gws GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE 호환):
    {
      "type": "authorized_user",
      "client_id": "<from client_secret>",
      "client_secret": "<from client_secret>",
      "refresh_token": "<from OAuth flow>"
    }
    """
    flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
    creds = flow.run_local_server(port=0)
    
    token_data = {
        "type": "authorized_user",
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token,
    }
    out_token_path.write_text(json.dumps(token_data, indent=2))
    out_token_path.chmod(0o600)
```

**운영 절차** (F1 §4.7.1~3 lift, 포맷만 변경):
1. macOS dev box에서 `auth_gdrive.py` 실행 → `token_gdrive.json` 작성 (pickle 아님)
2. `scp token_gdrive.json user@oci:/opt/wikihub/.credentials/`
3. server: `chmod 600 /opt/wikihub/.credentials/token_gdrive.json`
4. `wikihub.yaml`: `vaults[*].options.credentials_path: /opt/wikihub/.credentials/token_gdrive.json`
5. F4 install.sh가 systemd unit에 `Environment=GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=<path>` 주입

**Step 3 verification**: 실제 token JSON 포맷이 gws에 호환되는지 1회 호출 (`gws drive about get --params '{}'` 같은 light call로 검증).

**`lib/credentials.py` 책임** (서버 측):
- file 존재 확인 + 권한 600 확인 (F2 setup.md §Step 1 호환)
- env var는 systemd unit이 주입 → vault-fetch.py는 직접 read 안 함, gws subprocess가 알아서 사용
- token refresh: gws가 내부 처리 (gws가 refresh_token으로 access_token 갱신 — Python wrapper는 관여 안 함)
- **`lib/credentials.py` 범위 밖 (M3 정합)**: F2 setup.md §Step 1의 OAuth light call(`gws drive about get`)은 `/wh:setup` 구현(F4)이 직접 gws 호출로 검증. `lib/credentials.py`는 token validity API call 안 함

### 2.5 [E] Bootstrap 흐름

F2 ingest.md §Step 2 + F1 §4.4.6 lift:

```python
# vault-fetch.py 의사 흐름
def sync(vault_id, bootstrap_flag):
    cursor = load_cursor(vault_id)
    
    if not cursor:  # 첫 sync 또는 _state/ 소실
        if not wikihub_yaml.vaults[vault_id].options.bootstrap_allowed:
            raise VaultSyncFatal(
                reason="cursor 없음 + bootstrap 비활성",
                remediation="bootstrap_allowed: true 설정 + --bootstrap 플래그",
            )
        if not bootstrap_flag:
            raise VaultSyncFatal(
                reason="bootstrap 허용됐으나 --bootstrap 플래그 누락",
                remediation="명시 의도 확인 후 --bootstrap 재실행",
            )
        # bootstrap 모드: changes 없음 → files.list로 전체 스캔
        cursor = bootstrap_initial_cursor()  # gws drive changes get-start-page-token 호출
        all_files = list_all_files(vault_id)  # gws drive files list (페이지네이션)
        result = process_files(all_files, operation='created')
    else:
        # 증분 sync: changes.list
        changes = list_changes(cursor)
        result = process_changes(changes)
    
    save_cursor(vault_id, result.new_cursor)
    emit_json_to_stdout(result)
```

**bootstrap 시 root_folder_id 적용**: `wikihub.yaml.vaults[*].options.root_folder_id` 설정 시 `files.list` 쿼리에 `q: "'<folder_id>' in parents"` 추가 → 신뢰 디렉토리만 스캔.

**증분 sync 시**: changes API는 root_folder_id 필터링이 자연스럽지 않음 (changes는 user-level). post-filter로 source_relpath가 root_folder_id 하위인지 확인 후 처리.

**`exclude_shared_with_me` 적용 (Q3 정합)**:
- bootstrap(`gws drive files list`): query에 `q: "sharedWithMe=false"` 추가
- 증분(`gws drive changes list`): API 직접 필터 없음 → **post-filter** — changes 응답의 각 `file.shared` 또는 `file.ownedByMe` 확인 후 처리. 본 정책 위반 항목은 skip + log

**B2 해소 — `cursor.json` 부재 vs empty stub 의미**:

F2 setup.md §Step 1은 초기 state 파일 생성 시 `cursor.json = {"vault_id": ..., "cursor": "", "cursor_updated_at": null}` 작성. F3 §2.5의 `if not cursor:` 는 이 stub과 진정한 absent를 어떻게 구분?

**정본 결정**: bootstrap 가드는 **`cursor.json` 파일 부재** 또는 **`cursor` 필드가 빈 문자열**(즉 `""`)을 동등하게 "cursor 없음"으로 취급. 즉:

```python
def has_cursor(state) -> bool:
    return bool(state.get('cursor', '').strip())   # "" 또는 None 둘 다 False
```

setup.md의 stub은 의도적 empty (메인테이너에게 "여기 vault_id 가 등록됐다"는 신호만). Bootstrap 가드는 stub인지 진짜 absent인지 무관 — `cursor` 값이 빈 경우 동일하게 처리.

**B3 해소 — `_state/{vault}/` 5개 파일 schema 종합표** (F3 정본):

| 파일 | initial state (setup.md §Step 1 작성) | 갱신 시점 | 갱신 주체 |
|---|---|---|---|
| `cursor.json` | `{"vault_id": "<id>", "vault_type": "<type>", "cursor": "", "cursor_updated_at": null}` | 매 sync 사이클 끝 | `lib/state.py.save_cursor` |
| `file_map.json` | `{"vault_id": "<id>", "updated_at": null, "files": {}}` | 매 sync 사이클 끝 | `lib/state.py.save_file_map` |
| `last_sync.json` | **setup.md 초기 작성 안 함 (Q2)** — 첫 sync 후 생성 | 매 sync 사이클 끝 (has_changes 무관) | `lib/state.py.save_last_sync` |
| `retry.json` | `{"vault_id": "<id>", "next_id": 1, "queue": []}` | retry 추가/삭제 시 | `lib/state.py.save_retry` |
| `pending_ingest.json` | **never initialized** — ingest playbook Step 3에서 작성 | agent (F5) 책임 | F3 미작성 |

**Q2 해소 — `last_sync.json` 작성 정책**:
- vault-fetch.py가 **매 사이클 종료 시 last_sync.json overwrite** (has_changes=true·false 무관)
- 형식: F1 §4.4.3 lift — `vault_id`·`started_at`·`finished_at`·`duration_ms`·`cursor_before`·`cursor_after`·`changed[]`·`deleted[]`
- F2 setup.md §Step 1의 초기 state 파일 목록에 없음 → 첫 sync 후 자연 생성 (F3 책임)

**`changed[]` entry full schema (H2 정합 — vault-fetch.py stdout JSON 정본)**:

| 필드 | 자료형 | 필수 | 출처 |
|---|---|---|---|
| `source_relpath` | string | ✓ | vault 내 POSIX 상대경로 (예: `meetings/2026-Q1.pptx`) |
| `wiki_path` | string | ✓ | `instance.root` 기준 상대 (예: `wiki/sources/gdrive/meetings/2026-Q1.pptx.md`). `lib/sync.py`가 wiki-schema.md §A2 rule로 계산 |
| `operation` | string enum | ✓ | `created` \| `modified` |
| `source_id` | string \| null | ✓ | gdrive_api는 Drive file ID, directory는 null |
| `source_mtime` | string | ✓ | UTC ISO 8601 |
| `bytes_written` | int | ✓ | 다운로드한 바이트 (binary 원본 또는 export 결과). 추출 실패 시 0 |

### 2.6 [F] Binary extraction dispatch

F2 wiki-schema.md §A3 extraction tool 표 lift. `lib/extraction.py`:

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class ExtractionResult:
    body_text: str               # 추출된 본문 (실패 시 '[extraction failed: <reason>]')
    tool: str                    # 'python-pptx' | 'python-docx' | 'openpyxl' | 'pdfminer.six' | 'gws-export' | 'passthrough'
    tool_version: str            # 도구의 __version__ (gws-export는 gws --version)
    extraction_status: str       # 'success' | 'failed'
    reason: str                  # 실패 시 진단

# L1 정합: gws-export 항목별 export MIME 명시
EXTRACTION_DISPATCH = {
    'application/vnd.openxmlformats-officedocument.presentationml.presentation':
        ('python-pptx', extract_pptx),
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
        ('python-docx', extract_docx),
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
        ('openpyxl', extract_xlsx),
    'application/pdf':
        ('pdfminer.six', extract_pdf),

    # Google native — wiki-schema.md §A3 정합:
    'application/vnd.google-apps.document':
        ('gws-export', lambda p: export_via_gws(p, mime='text/markdown')),   # → .gdoc.md
    'application/vnd.google-apps.spreadsheet':
        ('gws-export', lambda p: export_via_gws(p, mime='text/csv')),         # → .gsheet.md (body = csv)
    'application/vnd.google-apps.presentation':
        ('gws-export', lambda p: export_via_gws(p, mime='text/plain')),       # → .gslides.md

    'text/markdown': ('passthrough', extract_text),
    'text/plain': ('passthrough', extract_text),
}

def extract(file_path: Path, mime_type: str) -> ExtractionResult:
    """File path → 추출 텍스트 + 메타. 매핑 없는 MIME은 ExtractionResult(status='failed', reason='unsupported MIME: ...')"""
```

**파일명 규약** (wiki-schema.md §A2 lift):
- binary: `<relpath>.<ext>.md` (예: `meetings/Q1.pptx.md`)
- 텍스트(`.md`): `<relpath>.md` (`.md` 중복 회피)
- Google native: `<relpath>.<virtual_ext>.md` (예: `policies/onboarding.gdoc.md`)

**추출 실패 처리** (wiki-schema.md §A3 정합):
- frontmatter 정상 + body = `[extraction failed: <reason>]`
- file_map.json 정합성 유지 → `/wh:lint`가 retry·archive 결정

**의존성** (`scripts/requirements.txt`):
```
python-pptx>=0.6.21
python-docx>=1.1.0
openpyxl>=3.1.0
pdfminer.six>=20231228
PyYAML>=6.0
```

### 2.7 [G] Test 전략

**Unit test (mocked gws)** — pytest 기본:
- `lib/state.py`: atomic write·load·corrupt 시나리오
- `lib/errors.py`: gws exit + stderr → wikihub exit 매핑 (대부분 테이블)
- `lib/extraction.py`: 각 형식별 fixture 파일로 추출
- `lib/credentials.py`: JSON load + 권한 검증

**Integration test (mocked gws subprocess)**:
- vault-fetch.py end-to-end: changes.list mocked stdout → 다운로드 → wiki 페이지 작성 → state 영속화 → JSON emit
- mocking 방식: `subprocess.run` patch 또는 PATH에 mock binary

**E2E test (real gws + sandbox Workspace)**:
- 1회성 dev box 실증 (Step 3 마지막에)
- Workspace 계정에 test folder 1개 + 3~5 파일 (pptx·md·gdoc 혼합)
- `gws drive changes list` 실호출 → 결과 schema 검증 → spec 재조정

**CI**: 본 feature는 CI 미설정 (wikihub v0.1.0 단계). 메인테이너 수동 `pytest` 실행 가정.

**Test 디렉토리 위치 (SIG 정합)**: repo root `tests/` (scripts/ 외부). pytest는 root에서 실행: `cd /opt/wikihub && python -m pytest tests/`. `sys.path`는 `tests/conftest.py`에서 `scripts/` 추가.

**E2E test 사전 조건 (L2 정합)**: 
- Step 3 시작 전 메인테이너가 **test Workspace + `wikihub-test/` 폴더 + fixture 파일** 준비
- fixture: 3~5 파일 (pptx·md·gdoc 혼합) — `wikihub.yaml.vaults.test.options.root_folder_id`로 격리
- **V4 의도적 403 trigger는 별도 OAuth client 또는 권한 회수 후 복구 절차** — production credentials 손상 차단
- plan.md §사전 조건 보강 (Task #42)

#### OPS — 운영 가정 명시

**stdout/stderr 분리 정책 (OPS 정합)**:
- **stdout**: vault-fetch.py가 JSON 1줄만 emit (ingest.md §Step 2 contract). 다른 출력 절대 금지
- **stderr**: 모든 진단·로그·예외 출력은 stderr로 (agent가 stdout JSON parse 시 noise 차단)
- Python logging은 stderr로 redirect (logging.basicConfig(stream=sys.stderr)). print()는 stderr 명시: `print(..., file=sys.stderr)`

**dev box 수동 호출 절차 (OPS 정합)**:
```bash
cd /opt/wikihub  # 또는 dev box mirror
export GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=/path/to/token_gdrive.json
export PYTHONPATH=/opt/wikihub/scripts
python scripts/vault-fetch.py --vault gdrive 2>sync.log >result.json
cat result.json   # stdout (JSON contract)
tail sync.log     # stderr (진단)
```

**filename sanitization (OPS 정합)**:
- vault relpath의 special char (공백·non-ASCII·`/`·...) → wiki path 변환 시 그대로 보존 (wiki-schema.md §A2 정합)
- 단 systemd ExecStart의 prompt 인자(`vault_id`)는 `^[a-z0-9_]+$` regex 강제 (setup.md §Step 2.x 정합)

**V1~V5 timing — verification 책임 (OPS 정합)**: 
- Step 3 진입 직후 1순위로 V1·V2·V3·V5 1회 실행 → 결과 따라 spec refine
- V4(stderr 패턴) + V8(의존성) 은 코드 작성 중 incremental 검증
- V6·V7은 install.sh 설계 시점(F4)으로 이관 가능

---

## 3. F1·F2 결정 lift 매트릭스

| F1·F2 결정 | F3 구현 측면 |
|---|---|
| ADR-0001 vault namespace | source 페이지 `wiki/sources/{vault}/...` 작성. frontmatter `source.vault` |
| ADR-0001 `[[link]]` 단축형 금지 | 본 feature는 link 작성 안 함 (semantic phase = F5). source 페이지 본문은 추출 텍스트 그대로 |
| ADR-0003 OAuth | `auth_gdrive.py` (JSON 출력) + `lib/credentials.py` (서버 측 검증). pickle → JSON 변경(2.4) |
| ADR-0006 unified orchestration | `vault-fetch.py`는 agent의 subprocess 도구. systemd → agent → vault-fetch.py |
| ADR-0007 all JSON | `lib/state.py`가 5개 state 파일 atomic JSON write |
| ADR-0013 entity·concept 추출 | **F3 책임 아님** — F5 semantic phase |
| ADR-0014 gws CLI | `lib/gws.py`가 subprocess wrapper. Python google-api-python-client 사용 안 함 |
| F2 ingest.md §Step 2 JSON contract | `vault-fetch.py` stdout 정본 schema 준수 |
| F2 wiki-schema.md §A1 frontmatter 자료형 | `lib/frontmatter.py`가 yaml 출력 시 string 통일 (YAML native date·datetime 금지) |
| F2 wiki-schema.md §A2 파일명 규약 | `lib/sync.py`가 vault relpath → wiki path 변환 |
| F2 wiki-schema.md §A3 extraction 표 | `lib/extraction.py` dispatch 테이블 |
| F2 wiki-schema.md §시간·timezone 정책 | mtime·synced_at은 UTC ISO 8601. log.md는 F5 책임 |
| F2 wiki-schema.md §신뢰 경계 | `vaults[*].options.exclude_shared_with_me: true`·`root_folder_id` 필터 적용 — bootstrap 시 `files.list` query에 `sharedWithMe=false`, 증분 시 changes API post-filter (Q3 정합 §2.5) |
| ADR-0014 reversal propagation (H1) | **F3 scope**: `_system/wiki-schema.md` `.credentials/` 행을 `token_{vault}.json`으로 + `_system/commands/ingest.md` error table의 `pickle.loads 예외` 행을 `JSON token load 예외`로. 둘 다 1-line surgical 수정 — Task #40에서 완료 |

---

## 4. 미결 사항 / Step 3 verification points

| # | 항목 | 확인 방법 (Step 3) |
|---|---|---|
| V1 | `gws drive changes list` 정확한 인자·출력 schema | `gws schema drive.changes.list` + 실호출 1회 |
| V2 | `gws drive files export` 출력 방식 (stdout vs --output 강제) | 실호출 |
| V3 | `gws drive files get --params '{"alt":"media"}'` binary 다운로드 가능 여부 | 실호출 |
| V4 | gws stderr 패턴 (HTTP error 시 정확한 형식) | 의도적 403/401 trigger 후 stderr 캡처 → `lib/errors.py` 매핑 refine |
| V5 | gws credentials JSON 정확한 schema | `auth_gdrive.py` 출력 → `gws drive about get` 1회 호출 성공 확인 |
| V6 | gws version pinning 값 (ADR-0015 후보) | `gws --version` 확인 + 안정성 평가 → install.sh의 pinned 버전 |
| V7 | root_folder_id 필터링이 changes API에서 동작하는지 (또는 post-filter 필요한지) | 실호출 |
| V8 | binary 추출 도구 의존성 호환성 (Python 3.11+) | requirements.txt 설치 후 단위 테스트 |
| V9 | `gws drive files list` 정확한 인자·페이지네이션 schema (bootstrap 전용) | `gws schema drive.files.list` + 실호출. nextPageToken 루프 검증 |

→ V1~V5·V9 결과 따라 본 문서 §2.3·2.4·2.5 spec refine. V6 결과 따라 ADR-0015 발의. V4 결과 따라 ADR-0017 정본화.

---

## 5. 신규 ADR 후보

| ID | 트리거 | Status |
|---|---|---|
| ADR-0015 | gws version pinning 값 — Step 3 V6 verification 후 발의 | 잠정 |
| ADR-0016 | Python 모듈 구조 — 본 단계에서 spec 명시로 충분 → **ADR 발의 안 함** (v0.2.x에서 package 진화 필요 시 재검토) | 보류 |
| ADR-0017 | gws stderr 패턴 매칭 표 — Step 3 V4 verification 후 발의 | 잠정 |

---

## 6. Definition of Done

- [x] **Step 1 (plan)**: `plan.md` 작성 + 확정
- [x] **Step 2 (analysis & design)**: 본 문서
- [ ] **Step 2 사용자 승인**: 본 문서 상단에 `approved: YYYY-MM-DD` 마커 (Step 3 시작 전)
- [ ] **Step 2 멀티모델 design review** (권장, 선택): F1·F2 패턴 따라 2건
- [x] **F3 scope `_system/` 정본 동기화 (H1)**: `_system/wiki-schema.md` + `_system/commands/ingest.md` pickle → JSON propagation (Q1 정합) — Task #40에서 완료
- [ ] **Step 3 implementation**:
  - [ ] `scripts/auth_gdrive.py` + JSON 출력
  - [ ] `scripts/vault-fetch.py` 진입 스크립트
  - [ ] `scripts/lib/{config,exceptions,state,credentials,gws,errors,extraction,frontmatter,sync}.py` 9개 모듈 (B1·B6 추가)
  - [ ] `scripts/requirements.txt` + `scripts/requirements-dev.txt`
  - [ ] `tests/test_*.py` 단위 + integration (`tests/fixtures/` 포함)
  - [ ] gws 인터페이스 V1~V9 verification 결과 본 문서·ADR로 reflection
- [ ] **Step 4 code review** (권장): 멀티모델 (Claude·Gemini·Codex 등)
- [ ] **Step 5 deployment**: **생략** (plan.md 선언 — F4 통합 시 자연 deploy)
- [ ] **Feature 종료 처리**: ADR 검증(0015·0017 Accepted 전환) + `git mv` archive

---

## 7. 참조

- F1 archive: `features/archive/20260513_v030_initial_architecture/`
- F2 archive: `features/archive/20260513_wikihub_schema_v1/`
- F2 정본 spec: `_system/commands/ingest.md`, `_system/wiki-schema.md`, `_system/commands/setup.md`
- ADR: `docs/adr/` (0001·0003·0006·0007·0014 직접 의존)
- gws docs: <https://github.com/googleworkspace/cli> (Step 3 추가 verification)
- WikiCurate v0.2.6 binary 처리 reference: `/Users/1004790/workspace/wikicurate/_system/wiki-schema.md` (PDF·DOCX·XLSX 추출 패턴)
