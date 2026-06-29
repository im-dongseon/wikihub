# /wi

특정 vault의 변경 사항을 wiki에 통합한다. 본 playbook은 agent-agnostic(Hermes·codex-cli·gemini-cli·copilot 등 어떤 CLI agent로도 실행 가능).

## 호출

```
<agent_invocation> "/wi --vault <vault_id>"
```

- **트리거**: systemd timer (정상 주기) 또는 사용자 수동 호출
- **vault_id**: `wikihub.yaml`의 `vaults[*].id` 중 하나
- **단일 진입점**: ADR-0006 (unified orchestration). agent가 mechanical phase(script subprocess) + semantic phase 둘 다 책임

## 사전 조건

- `wikihub.yaml`이 `instance.root`(기본 `/opt/wikihub`)에 존재
- `vaults[<vault_id>]`가 `enabled: true`
- 해당 vault의 OAuth credentials(ADR-0003) 유효
- `wiki/sources/<vault_id>/`, `wiki/entities/`, `wiki/concepts/`, `wiki/analyses/` 디렉토리 존재 (없으면 생성)

## 출력 언어 정책 (Step 4 semantic phase 의 LLM 호출 공통)

본 playbook 의 Step 4 (entity·concept 추출 + frontmatter 1줄 요약 작성) 의 LLM 응답에서:

- **출력 언어 = 한국어** (wiki 의 source 본문이 한국어 위주, ADR-0001 vault-prefix link 도 한국어 entity/concept 명 정합).
- **한자 (漢字) 감지 시 한글로 변환** — deepseek-v4-pro / minimax 등 일부 모델이 동음이의 한국어를 한자 표기로 출력하는 결함 (Hermes OCI 실증, 2026-05-20, lint.md 와 동일). 예: "기획(企劃)" → "기획"; "권한(權限)" → "권한". 고유명사 (인명·지명·조직명 중 한국 외 출처) 는 예외 허용.
- **영어 약어** (OKR, PM, CRM, API 등) 는 그대로 유지.

본 정책은 lint.md 의 "출력 언어 정책" 와 동일 — 운영 model (yaml `agent.models.wi`) 의 한자 출력 결함 대비.

## 절차

### Step 0. per-vault flock 가드 (race 가드)

`wikihub-ingest@<vault_id>.service` (timer 주기) + 메인테이너 수동 `systemctl --user start wikihub-ingest@<vault_id>` + Hermes 채팅의 `/wi --vault <vault_id>` 직접 호출 사이의 동일 vault 중복 실행 race 차단. 진행 중 ingest 가 있으면 즉시 exit 0 (no-op).

```bash
exec 200>"$WIKIHUB_HOME/.wi-<vault_id>.lock"
flock -n 200 || { echo "ingest (vault=<vault_id>) 이미 진행 중 — exit 0 (race 가드)"; exit 0; }
# lock 은 process 종료 시 자동 해제 (kernel-managed)
```

`flock -n` 은 non-blocking — lock 획득 fail 시 즉시 exit. systemd 가 success 로 처리 (다음 timer fire 자연 재시도). race window 0% 회피 (lint.md Step 0 와 동일 패턴).

**scope = per-vault** (lock 파일명에 `<vault_id>` 접미). multi-vault 병렬 ingest 허용 — `wikihub.yaml.operations.max_concurrent_vaults` 정책 정합. 본 lock 은 Step 1~6 전체를 cover하므로, Step 2 의 `vault-fetch.py` 가 보유한 기존 `_state/<vault>/.lock` 이 보호하지 못하던 Step 1 (`pending_ingest.json` attempts 증가) · Step 4 (LLM entity·concept 추출) · Step 5 (`log.md` append) · Step 6 (`pending_ingest.json` 삭제) 의 race window 가 본 lock 으로 닫힌다.

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

**script의 책임** (ADR-0035 정본):
- vault type별 구현 (F3 gdrive_api / F6 directory)
- `rclone lsjson <remote>: --recursive` subprocess (vault type=gdrive_api, ADR-0035). vault-fetch.py 가 내부에서 rclone backend (Drive API files.list) 를 호출하여 ID·MimeType·ModTime·Path 포함 JSON listing 획득
- `mount_diff.compute_diff(listing, file_map)` — file_map(source_id 키) 과 diff. 분류: created · modified · renamed · deleted
- false-deleted 가드 — listing 0건 또는 삭제 비율 > `false_delete_threshold` 시 Retryable 발화
- 변경된 파일 read → rclone mount FS `open()` (ADR-0025 Path C+ 유지)
- Binary 파일(`.pptx`/`.docx`/`.xlsx`/`.pdf`): 텍스트 추출 (wiki-schema.md §extraction tool 매핑 참조)
- 텍스트 파일 그대로 / Google 네이티브(`.gdoc`·`.gsheet`·`.gslides`): rclone mount export-formats 경유 binary → extraction dispatch
- `wiki/sources/<vault_id>/<path>.<ext>.md` 작성 (frontmatter + body, 단일 파일 모델)
- `_state/<vault_id>/file_map.json`·`last_sync.json` atomic 갱신 (ADR-0007 all JSON, ADR-0035: cursor.json 폐기)
- 결과를 **stdout 에 JSON 으로 출력** (정본 schema 아래 참조)

**Bootstrap 가드 폐기 (ADR-0035)**:
- cursor 모델 자체 폐기 — lsjson full snapshot 가 매 사이클의 진리. `_state/<vault_id>/file_map.json` 이 비어있으면 모든 listing 항목이 `created` 로 자연 분류 → first-run = bootstrap.
- `--bootstrap` 플래그 + `bootstrap_allowed` yaml key 모두 폐기.

**script stdout JSON schema (정본 — B1)**:

```json
{
  "vault_id": "<string, 필수, wikihub.yaml.vaults[*].id와 일치>",
  "has_changes": "<bool, 필수>",
  "changed": [
    {
      "source_relpath": "<string, 필수, vault 내 POSIX 상대경로 (예: 'meetings/2026-Q1.pptx')>",
      "wiki_path": "<string, 필수, instance.root 기준 상대 (예: 'wiki/sources/gdrive/meetings/2026-Q1.pptx.md')>",
      "operation": "<enum 'created'|'modified'|'renamed', 필수 — ADR-0035: renamed 추가>",
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

**script 에러 분류 정책 (ADR-0035 정본 — rclone stderr 매핑)**:

| 조건 | reason 패턴 | exit code |
|---|---|---|
| OAuth 만료/무효 | `oauth2: token expired` / `invalid_grant` / `401 Unauthorized` | 2 (Fatal, vault scope) |
| quota / rate limit | `userRateLimitExceeded` / `rateLimitExceeded` / `quotaExceeded` | 75 (Retryable) |
| network / timeout | `connection refused` / `no such host` / `i/o timeout` | 75 (Retryable) |
| listing 0건 + file_map 비어있지 않음 | mount/auth 부분 장애 가드 | 75 (Retryable, retry_after=300s) |
| 삭제 비율 > `false_delete_threshold` | listing partial 의심 가드 | 75 (Retryable, retry_after=300s) |
| rclone.conf 부재 / 권한 위반 / remote 미등록 | credentials.assert_rclone_config | 2 (Fatal) |
| rclone binary 부재 | install.sh 미수행 | 2 (Fatal) |

상세 매핑은 `scripts/lib/rclone.py:classify_rclone_error` 참조.

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
   - 동의어 처리는 frontmatter `aliases` 필드 — ADR-0039 (v0.1.8 신설)
3. 각 entity·concept에 대해:
   - **alias 인식 (ADR-0039)**: 본문 form 의 lowercase 가 기존 page 의 frontmatter `aliases` 셋 (lowercase normalize) 1+ 공통 → 기존 page 로 간주. `referenced_by` 만 추가 (alias 셋 미변경, stub 생성 skip — LLM 재생성 무한 loop 차단)
   - `wiki/entities/<name>.md` 또는 `wiki/concepts/<name>.md` 존재 (위 alias 인식 포함) → frontmatter `referenced_by`에 source 경로 추가 (set semantics — 중복 X)
   - 없음 → 새 stub 페이지 생성 (frontmatter `type: entity|concept` + `aliases: [<본문 form>]` + 본문은 1줄 요약, `referenced_by: [<source>]`)
     - **권한 설정**: stub write 직후 `chmod 644 "<path>"` 실행. 신규 파일은 `_atomic_write`의 mktemp 기본값 600이므로 명시적 644 보정 필요.
4. **analyses는 갱신 안 함** — `/wh-query`가 분석 저장 트리거 (별도 명령)
5. **referenced_by 정리는 set semantics**: 추가만, 제거 안 함. 새 본문에서 사라진 entity의 orphan ref는 `/wl`가 책임 (--apply 시 archive)

각 `deleted[*]`에 대해:

1. 해당 wiki 경로 = `wiki/sources/<vault_id>/<path>.md`
2. **이미 script가 삭제 처리** (script는 file_map 기준 wiki source 파일도 같이 삭제)
3. agent는 entities/concepts의 `referenced_by`에서 해당 source 경로 제거 (남는 reference 0건이면 entity·concept 페이지 자체는 보존 — `/wl`가 고아 페이지 판단)

**Source 페이지 본문·frontmatter는 절대 수정 안 함** (책임 경계: source = script, entities/concepts = agent)

### Step 5. log.md append

`wiki/sources/<vault_id>/log.md` 끝에 항목 추가 (timezone = `wikihub.yaml.instance.timezone`):

```markdown
## YYYY-MM-DD HH:MM:SS KST

- **Trigger**: systemd timer | manual
- **Listing**: <file_map_count_before> → <listing_count> (ADR-0035: cursor 라인 폐기 — lsjson full snapshot)
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
| `_state/<vault_id>/file_map.json`·`last_sync.json` | script | 갱신 (ADR-0035: cursor.json 폐기) |
| `_state/<vault_id>/pending_ingest.json` | agent | 작성 (Step 3) → 삭제 (Step 6) |
| `wiki/entities/<name>.md`, `wiki/concepts/<name>.md` | agent | 생성·갱신 |
| `wiki/sources/<vault_id>/log.md` | agent | append |
| `wiki/index.md` | **본 명령은 수정 안 함** (ADR-0005 — `/wl` 책임) | — |
| `wiki/analyses/` | **본 명령은 수정 안 함** (`/wh-query` 책임) | — |
| `graphify-out/` | **본 명령은 수정 안 함** (graphify rebuild = `/wl` Step 9 chain, ADR-0036 §D6) | — |

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
- script 가 file_map (source_id 키) 을 영속화 — 동일 ModTime 의 entry 는 unchanged 로 skip 되어 idempotent (ADR-0035)

## 동시성

- **Step 0 per-vault flock** (`$WIKIHUB_HOME/.wi-<vault_id>.lock`) — systemd timer · 메인테이너 수동 `systemctl start` · Hermes 채팅의 `/wi` 직접 호출 사이의 동일 vault 중복 실행을 일괄 차단. `vault-fetch.py` 의 기존 `_state/<vault>/.lock` 은 Step 2 진입 시점부터 보호이므로, 본 Step 0 lock 이 Step 1·4·5·6 race window 까지 cover.
- vault별 systemd unit 이 `Type=oneshot` → 동일 vault timer 중복 발화는 systemd 자체에서도 드롭 (Step 0 lock 의 보강 layer, F1 §4.6.5).
- 다중 vault 간 직렬화는 `wikihub.yaml.operations.max_concurrent_vaults` 정책 (F4 결정 — agent-agnostic 명명으로 ADR-0012 정합. F1 §4.6.5의 `hermes_concurrency` 키명은 본 명으로 supersede). Step 0 lock 은 per-vault 이므로 본 정책에 직교.

## 관련 ADR

- ADR-0001 vault namespace + `[[link]]` 단축형 금지
- ADR-0002 agent CLI subprocess (`hermes -z`)
- ADR-0005 wiki/index.md 갱신은 `/wl`가, log는 vault별
- ADR-0006 unified orchestration (본 playbook이 mechanical + semantic 둘 다)
- ADR-0007 state는 all JSON (`pending_ingest.json` 형식)
