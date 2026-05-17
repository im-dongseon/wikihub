# /wh:ingest

특정 vault의 변경 사항을 wiki에 통합한다. 본 playbook은 agent-agnostic(Hermes·codex-cli·gemini-cli·copilot 등 어떤 CLI agent로도 실행 가능).

## 호출

```
<agent_invocation> "/wh:ingest --vault <vault_id>"
```

- **트리거**: systemd timer (정상 주기) 또는 사용자 수동 호출
- **vault_id**: `wikihub.yaml`의 `vaults[*].id` 중 하나
- **단일 진입점**: ADR-0006 (unified orchestration). agent가 mechanical phase(script subprocess) + semantic phase 둘 다 책임

## 사전 조건

- `wikihub.yaml`이 `instance.root`(기본 `/opt/wikihub`)에 존재
- `vaults[<vault_id>]`가 `enabled: true`
- 해당 vault의 OAuth credentials(ADR-0003) 유효
- `wiki/sources/<vault_id>/`, `wiki/entities/`, `wiki/concepts/`, `wiki/analyses/` 디렉토리 존재 (없으면 생성)

## 절차

### Step 1. pending_ingest.json 확인 (부분 실패 복구)

`_state/<vault_id>/pending_ingest.json` 존재 시:

1. 파일 read → `changed`, `deleted` 추출 (Step 3 schema 정합)
2. `attempts` += 1. `wikihub.yaml.operations.retry.max_attempts`(default 5) 초과 시:
   - `pending_ingest.json` → `pending_ingest.dead.<utc_iso>.json` 이동 (증거 보존)
   - ops-alert 트리거 + systemd OnFailure
   - exit 2 (Fatal)
3. **script subprocess 호출 건너뜀** — 이전 사이클의 mechanical phase는 이미 완료된 상태
4. **source 파일 무결성 점검 (B2 정합)**: pending이 가리키는 wiki_path 파일의 source_mtime이 pending.changed[*].source_mtime과 다르면 (= 그 사이 새 sync로 source 페이지가 또 갱신됨), 본문 read 결과 우선 사용 + log.md에 "source mtime drift detected" 노트 (정책: 항상 최신 본문 신뢰 — set semantics 의존)
5. Step 4(semantic phase)로 점프
6. pending 처리 완료 후, 본 사이클 내에서 **새 vault 변경이 있을 가능성을 위해 Step 2 추가 호출** (F1 §4.6.4의 "pending 처리 후 새 sync 진행" 의도 보존). script가 changes.list 결과 0건이면 Step 3 has_changes=false 분기

`pending_ingest.json` 없으면 Step 2로.

### Step 2. Mechanical phase — script subprocess

```bash
python /opt/wikihub/scripts/vault-fetch.py --vault <vault_id>
```

**script의 책임**:
- vault type별 구현(F3 gdrive_api / F6 directory)
- `gws drive changes list` subprocess (vault type=gdrive_api, ADR-0014). vault-fetch.py가 내부에서 `gws` CLI 호출 + JSON parse + state 영속화. 메인테이너 `google-api-python-client` 직접 호출 없음
- 변경된 파일 다운로드 → `/opt/vault-<vault_id>/`
- Binary 파일(`.pptx`/`.docx`/`.xlsx`/`.pdf`): 텍스트 추출 (wiki-schema.md §extraction tool 매핑 참조)
- 텍스트 파일 그대로 / Google 네이티브(`.gdoc`·`.gsheet`·`.gslides`): API export → 텍스트
- `wiki/sources/<vault_id>/<path>.<ext>.md` 작성 (frontmatter + body, 단일 파일 모델)
- `_state/<vault_id>/cursor.json`·`file_map.json`·`last_sync.json` atomic 갱신 (ADR-0007 all JSON)
- 결과를 **stdout에 JSON으로 출력** (정본 schema 아래 참조)

**Bootstrap 가드 (F1 §4.4.6 lift, O3)**:
- `cursor.json` 부재 시 (첫 sync 또는 `_state/` 소실):
  - `wikihub.yaml.vaults[*].options.bootstrap_allowed` = `false` (default) → script exit 2 (Fatal) — remediation: "bootstrap_allowed: true + --bootstrap 플래그로 1회성 실행 후 false 환원"
  - `bootstrap_allowed: true` + script `--bootstrap` CLI 플래그 둘 다 있어야 전체 스캔 허용 (의도하지 않은 부트스트랩 차단)

**script stdout JSON schema (정본 — B1)**:

```json
{
  "vault_id": "<string, 필수, wikihub.yaml.vaults[*].id와 일치>",
  "has_changes": "<bool, 필수>",
  "changed": [
    {
      "source_relpath": "<string, 필수, vault 내 POSIX 상대경로 (예: 'meetings/2026-Q1.pptx')>",
      "wiki_path": "<string, 필수, instance.root 기준 상대 (예: 'wiki/sources/gdrive/meetings/2026-Q1.pptx.md')>",
      "operation": "<enum 'created'|'modified', 필수>",
      "source_id": "<string|null, 필수, gdrive_api는 Drive file ID, directory는 null>",
      "source_mtime": "<string, 필수, UTC ISO 8601 'YYYY-MM-DDTHH:MM:SS+00:00'>",
      "bytes_written": "<int, 필수, 다운로드 바이트 수 — 메트릭용>"
    }
  ],
  "deleted": [
    "<string, vault 내 source_relpath의 list (wiki path 아님 — script가 wiki source 파일도 함께 삭제)>"
  ],
  "duration_ms": "<int, 필수, script start → JSON emit 시점까지>"
}
```

위 schema는 F1 §4.2.2의 `ChangedFile` dataclass를 lift (`source_mtime`·`source_id`·`bytes_written` 모두 포함). F3 구현자는 본 schema를 정본으로.

**script exit code**:
- `0` = 성공 (변경 있음 또는 no-op 둘 다)
- `75` (EX_TEMPFAIL) = VaultSyncRetryable — 다음 사이클에서 재시도. agent는 `pending_ingest.json` 미작성 후 exit 0
- `2` = VaultSyncFatal — agent도 즉시 exit 2 (notify + ops-alert)

**script 에러 분류 정책 (F1 §4.7.5 정본 lift — A6)**:

| HTTP/조건 | reason 필드 | exit code |
|---|---|---|
| 403 | `userRateLimitExceeded` / `rateLimitExceeded` / `quotaExceeded` | 75 (Retryable) |
| 403 | `insufficientPermissions` / `forbidden` | 2 (Fatal, scope 회수) |
| 401 | — | 2 (Fatal, token 무효 또는 client_secret rotation) |
| 5xx | — | 75 (Retryable) |
| 네트워크 timeout | — | 75 (Retryable) |
| `cursor.json` 부재 + bootstrap_allowed=false | — | 2 (Fatal — 위 Bootstrap 가드) |
| JSON token load 예외 (credentials 파손, ADR-0014) | — | 2 (Fatal) |

자세한 cascading scenarios는 F1 archive §4.7.5 참조.

### Step 3. has_changes 분기

`script.has_changes == false`:
- **Step 5(log.md append)로 jump** — status=skipped 항목 작성
- exit 0 (LLM 추론 없이 조기 종료)

`script.has_changes == true`:
- `pending_ingest.json` 영속화 (Step 4 진입 직전, atomic write):
  ```json
  {
    "vault_id": "<vault_id>",
    "queued_at": "<utc_iso>",
    "attempts": 1,
    "changed": [...],   // script 출력 그대로 lift
    "deleted": [...]
  }
  ```
- Step 4 진행

> **§Step 3·5 관계 (A7)**: Step 5는 status enum(`success`/`skipped`/`failure`) 무관 단일 entry. has_changes=false는 Step 5로 직접 jump → status=skipped 항목 1줄 작성 + exit 0. has_changes=true는 Step 4·5·6 순차.

### Step 4. Semantic phase — entities·concepts 갱신

각 `changed[*]`에 대해:

1. `wiki_path` 파일 read (script가 작성한 source 페이지의 추출 본문 + frontmatter)
2. **entity·concept 추출 — ADR-0013 정책 정본**:
   - entity = 고유명사 (인물·조직·제품·프로젝트)
   - concept = 보통명사·추상 개념 (방법론·용어·프레임워크)
   - 둘 다 아니면 추출 안 함 (false positive < false negative)
   - 본문 1회 이상 명시 언급 (passing mention 제외)
   - 1줄 요약은 **본문 발췌만** — 외부 지식 generation 금지 (신뢰 경계, ADR-0013 §3)
   - 동의어는 가장 자주 쓰인 표기 1개만 (alias 정책은 future ADR)
3. 각 entity·concept에 대해:
   - `wiki/entities/<name>.md` 또는 `wiki/concepts/<name>.md` 존재 → frontmatter `referenced_by`에 source 경로 추가 (set semantics — 중복 X)
   - 없음 → 새 stub 페이지 생성 (frontmatter `type: entity|concept` + 본문은 1줄 요약, `referenced_by: [<source>]`)
4. **analyses는 갱신 안 함** — `/wh:query`가 분석 저장 트리거 (별도 명령)
5. **referenced_by 정리는 set semantics**: 추가만, 제거 안 함. 새 본문에서 사라진 entity의 orphan ref는 `/wh:lint`가 책임 (--apply 시 archive)

각 `deleted[*]`에 대해:

1. 해당 wiki 경로 = `wiki/sources/<vault_id>/<path>.md`
2. **이미 script가 삭제 처리** (script는 file_map 기준 wiki source 파일도 같이 삭제)
3. agent는 entities/concepts의 `referenced_by`에서 해당 source 경로 제거 (남는 reference 0건이면 entity·concept 페이지 자체는 보존 — `/wh:lint`가 고아 페이지 판단)

**Source 페이지 본문·frontmatter는 절대 수정 안 함** (책임 경계: source = script, entities/concepts = agent)

### Step 5. log.md append

`wiki/sources/<vault_id>/log.md` 끝에 항목 추가 (timezone = `wikihub.yaml.instance.timezone`):

```markdown
## YYYY-MM-DD HH:MM:SS KST

- **Trigger**: systemd timer | manual
- **Cursor**: `<token-prev>` → `<token-new>`
- **Changed**: N files
  - `meetings/2026-Q1.pptx` (modified) → [[gdrive/meetings/2026-Q1.pptx]]
- **Deleted**: M files
  - `old/archive.md`
- **Script duration**: 12.4s
- **Semantic duration**: 34.7s
- **Entities updated**: 5 (created 2, ref-added 3)
- **Concepts updated**: 2 (created 1, ref-added 1)
- **Status**: success
```

상태별 변형:
- `Status: skipped` — has_changes=false (Script duration만, Semantic 줄 생략)
- `Status: failure` — script exit 75 또는 semantic 실패 (Reason 줄 추가)

### Step 6. pending_ingest.json 삭제

Step 5까지 무에러 완료 시:
- `pending_ingest.json` 삭제 (다음 사이클이 fresh start)
- exit 0

## 출력 산출물

| 변경 대상 | 주체 | 본 사이클 |
|---|---|---|
| `/opt/vault-<vault_id>/...` | script | 변경된 원본 파일 다운로드 |
| `wiki/sources/<vault_id>/...` | script | 변경된 source 페이지 (단일 파일 모델) |
| `_state/<vault_id>/cursor.json`·`file_map.json`·`last_sync.json` | script | 갱신 |
| `_state/<vault_id>/pending_ingest.json` | agent | 작성 (Step 3) → 삭제 (Step 6) |
| `wiki/entities/<name>.md`, `wiki/concepts/<name>.md` | agent | 생성·갱신 |
| `wiki/sources/<vault_id>/log.md` | agent | append |
| `wiki/index.md` | **본 명령은 수정 안 함** (ADR-0005 — `/wh:lint` 책임) | — |
| `wiki/analyses/` | **본 명령은 수정 안 함** (`/wh:query` 책임) | — |

## 실패 처리

| 실패 시점 | 동작 |
|---|---|
| script exit 75 (Retryable) | pending_ingest.json 미작성. 다음 사이클에서 script 재시도. log.md `Status: failure` |
| script exit 2 (Fatal) | notify 이중 경로 발동(`agent.notify_on_fatal` 경로 + systemd OnFailure ops-alert.service). pending 미작성. exit 2 |
| semantic phase 오류 | pending_ingest.json은 그대로(또는 attempts +=1 후 그대로). 다음 사이클에서 Step 1로 진입 → 재시도 |
| pending attempts ≥ max_attempts | `pending_ingest.dead.<ts>.json` 격리 + notify + exit 2 |
| log.md append 실패 (disk full 등) | semantic은 성공했으므로 pending 삭제하고 log 실패만 stderr 출력 + exit 1 (운영자 확인 필요) |

## 멱등성 보장

- 동일 source 파일에 대한 entity 참조는 set semantics (중복 제거)
- pending 재처리 시 같은 source를 다시 읽어도 entity referenced_by에 중복 추가 안 됨
- script가 cursor를 영속화하므로 script 재실행 시 같은 변경을 다시 다운로드해도 vault 파일 덮어쓰기 = idempotent

## 동시성

- vault별 systemd unit이 Type=oneshot → 같은 vault의 /wh:ingest 중복 실행 차단 (F1 §4.6.5)
- 다중 vault 간 직렬화는 wikihub.yaml `operations.max_concurrent_vaults` 정책 (F4 결정 — agent-agnostic 명명으로 ADR-0012 정합. F1 §4.6.5의 `hermes_concurrency` 키명은 본 명으로 supersede)

## 관련 ADR

- ADR-0001 vault namespace + `[[link]]` 단축형 금지
- ADR-0002 agent CLI subprocess (`hermes -z`)
- ADR-0005 wiki/index.md 갱신은 `/wh:lint`가, log는 vault별
- ADR-0006 unified orchestration (본 playbook이 mechanical + semantic 둘 다)
- ADR-0007 state는 all JSON (`pending_ingest.json` 형식)
