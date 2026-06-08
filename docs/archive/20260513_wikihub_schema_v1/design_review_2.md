# Design Review 2 — F3/F5 implementer perspective

- **Reviewer**: general-purpose subagent acting as F3+F5 implementer
- **Date**: 2026-05-13
- **Target**: F2 (`wikihub_schema_v1`) — `_system/wiki-schema.md` + `_system/commands/*.md` + `_system/VERSION` + ADR-0005~0012

## Verdict

전체적으로 **F3/F5 시작은 가능하지만 무재조율 완료는 어렵다**. wiki-schema·playbook은 책임 경계와 데이터 흐름을 잘 잡았으나, (1) F3가 작성해야 하는 source 페이지 frontmatter의 자료형, (2) script ↔ agent 사이의 JSON contract, (3) entity/concept 추출 heuristic, (4) `pending_ingest.json` 재진입 시 source 파일 변경 추적 — 네 영역의 명세 부재로 두 명의 implementer가 같은 spec을 읽고도 호환되지 않는 코드를 만들 위험이 큼. Blocker 5건은 Step 3 진입 전에 본 F2 안에서 해소를 권한다 (별도 ADR 1건 필요).

---

## Critical implementation blockers

### B1. script subprocess JSON contract의 필드 자료형 미정의 — `ingest.md` §Step 2

**Implementer question**: F3가 script를 짤 때 `changed[*].source_relpath`는 항상 POSIX 슬래시인가? `wiki_path`는 `instance.root` 기준 상대인가 절대인가? `operation`은 `created`/`modified` 둘인가 `deleted`도 포함하는가 (F1 §4.2.2는 `created|modified` 둘만 인정하고 deleted는 별도 list)? `duration_ms`는 script 시작~JSON emit 시점인가, sync 자체 시간만인가?

**Current spec**: `ingest.md` §Step 2의 JSON 예시는 `source_relpath`, `wiki_path`, `operation`, `duration_ms` 4개 키만 보여줌. enum·자료형·필수 여부 명세 없음. `deleted`는 string list로만 표시되어 wiki_path인지 source_relpath인지 모호 (예시는 `"old/archive.md"`로 source_relpath처럼 보이지만 wiki에서 삭제할 페이지 = wiki_path여야 일관).

**Gap**:
- `changed[*]` 필드 자료형 표 (string/int/enum)
- `operation` enum 값 닫힘 (`created` | `modified` 둘? 아니면 `deleted`까지?)
- `deleted` 항목의 의미론: source_relpath인가 wiki_path인가? (script는 wiki sources 파일을 같이 지운다고 `ingest.md` §Step 4가 명시하므로 source_relpath가 자연스럽지만 spec 미명시)
- 필수 vs 선택 키 (예: `bytes_written`이 F1 §4.2.2에는 있는데 F2 ingest.md JSON 예시에는 없음 — 어느 게 정본?)
- F1 §4.2.2 `ChangedFile` dataclass (`source_mtime`, `source_id`, `bytes_written` 포함)와의 관계 — F2가 superset인지 subset인지

**Recommendation**: `ingest.md` §Step 2에 다음 추가:
```
script stdout JSON schema (정본):
{
  "vault_id": str (필수, wikihub.yaml.vaults[*].id와 일치),
  "has_changes": bool (필수),
  "changed": [
    {
      "source_relpath": str (POSIX, vault 내 상대경로, 필수),
      "wiki_path": str (instance.root 기준 상대 — 예: "wiki/sources/gdrive/..."),
      "operation": "created" | "modified" (필수, enum 닫힘),
      "source_id": str | null (gdrive_api는 str, directory는 null),
      "source_mtime": str (UTC ISO 8601, 필수),
      "bytes_written": int (필수, 메트릭용)
    }
  ],
  "deleted": [str] (필수, vault 내 source_relpath의 list — wiki path 아님),
  "duration_ms": int (필수, script start ~ JSON emit)
}
```
F1 §4.2.2 ChangedFile을 lift할 거라면 명시. lift 안 할 거면 차이 표.

### B2. `pending_ingest.json` 재진입 시 source 페이지 무결성 미정의 — `ingest.md` §Step 1·4

**Implementer question**: pending이 attempts=1 상태에서 재실행될 때, 이전 사이클의 mechanical phase는 끝났다고 했는데 — 그동안 사용자가 vault에서 같은 파일을 또 수정해 source 페이지가 또 갱신될 수도 있다. agent가 semantic phase 재실행 시 read하는 `wiki_path` 파일이 pending 작성 시점과 다를 수 있는데 이게 의도된 동작인가? entity referenced_by가 이전 mtime 기준 본문 entity를 보고 추가됐다면 새 mtime 본문에선 사라진 entity의 ref가 남는다.

**Current spec**: §Step 1은 "이전 사이클의 mechanical phase는 이미 완료된 상태" — script 호출 skip. §Step 4는 `wiki_path` read 후 entity 추출.

**Gap**: 시점 불일치. 두 해석 가능:
- (A) pending 재진입 시 source 파일 read = 항상 최신 상태로 OK (set semantics + 멱등성 가정)
- (B) pending이 가리키는 source 파일이 별도 sync로 또 갱신됐을 가능성을 어떻게 다룰지

또한 vault-A에서 동일 파일이 빠르게 두 번 수정 → 첫 사이클 mechanical 성공 + semantic 실패 → pending 보존 → 두 번째 timer 사이클에서 script가 또 mechanical 처리 (changes.list가 새 변경 가져옴) → source 페이지 또 덮어쓰기. 이때 script 호출 skip 정책 (§Step 1 항목 2)이 새 변경을 누락한다. F1 §4.6.4가 "pending 재처리 후 새 sync 진행"이라 했는데 F2는 `pending_ingest.json` 존재 시 mechanical을 통째로 skip — F1·F2 의도 차이.

**Recommendation**: `ingest.md` §Step 1에 다음 추가:
```
pending 재처리는 semantic phase만 재실행한다. 단,
- 본 cycle에서 새 vault 변경이 발생했다면 (= 다음 timer에서 script가 새 changes 인지),
  pending 처리 완료 후 같은 사이클 내에서 script 1회 추가 호출 (F1 §4.6.4 ".pending 처리 후 새 sync 진행" 의도 보존)
- 또는 명시적으로 "pending 사이클은 semantic만, 새 변경은 다음 timer에서" 정책 선택

또한:
- pending 재진입 시 `wiki_path` 파일의 source_mtime이 pending.changed[*].source_mtime과 다르면 (= 그 사이 sync가 또 갱신), 본문 read 결과 우선 사용 + log.md에 "source mtime drift detected" 노트
- entity referenced_by는 set semantics → 추가만, 제거 없음. 이전 본문에서 추출된 entity가 새 본문에서 사라지면 orphan ref 발생 — /wh:lint가 cleanup 책임 (현재 spec은 "고아 페이지 판단"으로만 표현, ref drift는 미언급)
```
의도가 (A)면 단순화. 단 명시적 결정 필요 → **ADR-0013 후보** (잠정 ADR-0014 "log rotation"보다 우선 처리).

### B3. entity·concept 추출 heuristic 미정의 — `ingest.md` §Step 4, `lint.md` §Step 3

**Implementer question**: F5가 semantic phase의 prompt를 짤 때, "인물·조직·제품·프로젝트" vs "개념·용어·방법론"을 LLM이 어떻게 구분하라고 가이드해야 하나? OKR이 concept인지 entity인지 두 implementer가 다른 답을 낼 가능성 농후. stub의 1줄 요약은 어디서 추출하나 (source 본문에서 nearby sentence vs LLM이 generate)?

**Current spec**:
- ingest.md §Step 4: "**entity 추출**: 인물·조직·제품·프로젝트 등 고유 항목" / "**concept 추출**: 개념·용어·방법론"
- lint.md §Step 3: "LLM이 식별한 entity·concept"
- wiki-schema.md `entities/` = "인물·조직·제품·프로젝트 hub", `concepts/` = "개념·용어·방법론 hub"

**Gap**:
- LLM에게 줄 system prompt의 정본 미정의 (F5가 prompt를 짤 때 표준이 없음)
- entity/concept 경계 사례 (예: "강남스타일" = entity? concept? "OKR" = concept이라고 schema가 예시했지만 reasoning 미설명)
- 1줄 요약 source 정책: source 본문에서 발췌 vs LLM이 외부 지식으로 generate (후자는 신뢰 경계 §S4 위반 가능 — agent의 출력에 외부 지식이 섞이면 출처 미상)
- 추출 최소 신뢰도 (예: 한 번만 언급된 단어도 entity로? 본문에서 N회 이상만?)
- 한국어·영어 표기 정규화 (예: "Hong Gil-dong" vs "홍길동")

**Recommendation**: `wiki-schema.md`에 다음 섹션 추가 (또는 별도 `_system/extraction-policy.md` 신규):
```
## entity·concept 추출 정책 (semantic phase 정본)

분류 규칙:
- entity: 고유명사 (Proper noun). 이름이 있는 개별 객체.
  - 인물 (홍길동, John Doe), 조직 (전략기획팀, Anthropic),
    제품 (Claude, iPhone), 프로젝트 (Q1 OKR Initiative)
- concept: 보통명사·개념 (Common noun · abstract idea).
  - 방법론 (애자일, OKR), 용어 (KPI, ARR),
    프레임워크 (BPMN, ADR)
- 모호 시: 위 둘 어디에도 안 맞으면 추출 안 함 (false positive < false negative)

추출 임계:
- source 본문에서 1회 이상 명시적 언급 (passing mention 제외 — "etc."·헤더 link 제외)
- 한국어/영어 동의어는 가장 자주 쓰인 표기를 canonical, 다른 표기는 추후 ADR (현 v0.1.0은 단일 표기)

1줄 요약 source:
- source 본문에서 가장 인접한 정의·설명 문장 발췌 (외부 지식 generation 금지 — 신뢰 경계 §S4)
- 본문에 없으면 "<entity name> — (1 source 참조)" 같은 자리 표시만

LLM prompt template (semantic phase 정본):
[F5가 본 정책을 구현하는 system prompt 작성. 본 spec은 정책만 정의, prompt 표현은 F5 책임]
```
별도 ADR이 적절 (entity/concept 분류는 운영 결정 — ADR-0013로 발의 권장).

### B4. systemd unit ExecStart의 quote-handling 미정의 — `setup.md` §Step 2

**Implementer question**: agent_invocation = `agent.binary` + `agent.oneshot_args` (공백 join), 그 뒤에 prompt를 append하면 unit ini 파일에는 어떻게 들어가나? 프롬프트에 공백·따옴표가 있을 때 systemd ExecStart parser가 옳게 split하는지 F4 implementer가 어떻게 검증하나?

**Current spec**: setup.md §Step 2 — "template 치환 변수: `{agent_invocation}` — `agent.binary` + `agent.oneshot_args` 공백 join". ADR-0012 — `ExecStart={agent.binary} {agent.oneshot_args[*]} "<prompt>"` (예: `/usr/local/bin/hermes -z "/wh:ingest --vault gdrive"`).

**Gap**:
- systemd ExecStart는 shell이 아니라 자체 parser → `"..."` 인용 시 한 token으로 묶임. 단 vault_id에 특수문자 들어가면? (스키마 검증이 `[a-z0-9_]`만 허용하면 OK인데 wikihub.yaml schema가 정규식 명시 안 함)
- oneshot_args가 `["-z"]`처럼 단일 토큰이 아니라 `["chat", "-q"]` 같은 다중 토큰일 때 공백 join 후에도 systemd가 옳게 split하는지 (예: hermes의 chat-query 모드는 F1 §4.6.3에 있었음 — F2에선 oneshot_args로 표현 가능)
- custom agent type에서 메인테이너가 `oneshot_args: ["--prompt-from-stdin"]` 처럼 stdin 모드를 설정하면 prompt append 모델이 깨짐 — F4/F5 implementer가 알아야 할 한계

**Recommendation**: ADR-0012 또는 setup.md에 다음 추가:
```
### ExecStart 조립 규약 (F4·F5 정본)

ExecStart 라인 형식 (systemd parser 기준):
ExecStart={agent.binary} {oneshot_args 공백 join} "{prompt}"

규칙:
- prompt 전체는 systemd "..." 1개 토큰으로 감싸야 함 (slash·공백·인자 모두 포함)
- prompt 내부에 큰따옴표가 들어가면 안 됨 (escape 미지원 가정 — 현 v0.1.0은
  slash command 인자 자체에 큰따옴표 없음 가정. 발생 시 ADR-0014 발의)
- oneshot_args 다중 토큰 예: ["chat", "-q"] → `hermes chat -q "/wh:..."`
- oneshot_args가 빈 list면 binary 직후 prompt — `agent "/wh:..."` (PATH 단일 토큰)
- prompt에 입력 stdin이 필요한 custom agent (stdin 입력 모드)는 v0.1.0 미지원,
  메인테이너가 wrapper script + binary path로 우회 (ADR-0012 §재검토 트리거)

vault_id·prompt 인자 sanitization:
- vault_id: ^[a-z][a-z0-9_]*$ — wikihub.yaml 스키마 검증에서 강제 (setup.md §Step 1)
- /wh:query 인자는 사용자 자유 입력 — daemon은 stdin/socket으로 전달 (systemd unit
  ExecStart에는 안 들어감 — daemon이 별도 dispatch). v0.1.0 query는 systemd timer
  대상 아니므로 본 규약 영향 없음
```

### B5. install.sh skill 등록 메커니즘 dispatch 명세 부재 — ADR-0010 §install.sh의 동작 step 8

**Implementer question**: F4가 install.sh를 짤 때, hermes·codex·gemini·copilot 각각에 skill을 어떻게 등록하나? skill_prefix가 `wh:`인데 hermes는 어떤 명령으로 등록하는가 (`hermes skill add ...`?). 등록 실패의 정확한 detection 시그널 (exit code? stderr 패턴?) 은? fallback `wh-`로 retry 트리거는 어떤 조건인가?

**Current spec**:
- ADR-0010 step 8: "agent에 wh: skill 등록 (agent별 메커니즘 dispatch)" — dispatch 자체가 미정의
- ADR-0011: "install.sh가 agent CLI에 `wh:` namespace로 skill 등록 시도 → 등록 실패 또는 콜론 escape 이슈 발생 시 `wh-` 로 fallback 자동 시도"

**Gap**:
- agent별 등록 명령 미명세 (각 agent CLI 문서를 F4가 직접 조사해야 함 — agent-agnostic spec의 한계)
- 등록 실패 detection 조건 (exit code? stderr keyword? prefix가 그냥 등록됐는데 invocation 시점에 비로소 실패한다면 install.sh는 모름)
- skill 등록의 idempotency (install.sh를 update 모드로 두 번째 호출하면 기존 skill 덮어쓰기인가 skip인가)
- skill 등록 실패의 user-facing 모드: install.sh가 exit 0인가 (skill 없이도 install 자체는 성공)? exit 1인가 (skill = install의 필수 산출물)?

**Recommendation**: ADR-0010에 다음 추가 또는 별도 ADR로 발의:
```
### install.sh skill 등록 dispatch (F4 정본 — agent별 분기)

hermes: `hermes skill add --name wh:<cmd> --playbook /opt/wikihub/_system/commands/<cmd>.md`
codex:  TBD — F4가 codex-cli 문서 확인 후 본 표 갱신
gemini: TBD
copilot: TBD
custom: 메인테이너가 wikihub.yaml.agent.skill_register_cmd 직접 명시 (v0.1.0 미지원, future)

등록 실패 감지:
- 시도 1: skill_prefix = `wh:`로 등록
- exit code != 0 OR stderr에 "invalid name"·"colon"·"namespace" 키워드 포함 → 시도 2
- 시도 2: skill_prefix = `wh-`로 등록 + wikihub.yaml.agent.skill_prefix = `"wh-"` 기록
- 두 번 모두 실패 → install.sh stderr 경고 + wikihub.yaml에 `agent.skill_prefix: null` 기록
  → /wh:setup이 보고 + 메인테이너가 수기로 register

미검증 agent (codex/gemini/copilot):
- v0.1.0은 hermes만 검증. 다른 type은 install.sh가 prompt + "검증되지 않음" 경고 후 진행
- F4가 매핑 TBD 항목 채우는 시점에 본 ADR 갱신 (Status 변경 없이 §dispatch 표만 update)
```

---

## Significant ambiguities (should clarify before F3/F5 start)

### A1. source 페이지 frontmatter 필드 자료형 — wiki-schema.md §Frontmatter

**Implementer question**: F3 script가 `source_mtime`을 frontmatter에 쓸 때 string인가 datetime 노드인가? YAML 1.2의 `2026-05-13T01:55:12+00:00`는 native timestamp로 파싱되는데 wiki-schema는 string 가정인가? `created: 2026-05-13`는 date type, `source_mtime: 2026-05-13T01:55:12+00:00`은 datetime type — 혼재 의도 명시 필요.

**Current spec**: wiki-schema.md §위키 페이지 형식의 sources/ frontmatter 예시만 있음. 자료형·정규식 미명시.

**Gap**:
- `created`/`updated` 형식 = `YYYY-MM-DD` (date) — 명시 필요
- `source_mtime`/`last_synced_at`/`extracted_at` 형식 = `YYYY-MM-DDTHH:MM:SS+00:00` (UTC ISO 8601) — §시간·timezone 정책에 표가 있지만 frontmatter 컨텍스트와 연결 명시 부족
- `tags`/`referenced_by` = string list. 빈 리스트는 `[]` (flow style)인가 `null` 생략인가
- `extraction.tool` enum (`python-pptx`, `python-docx`, `openpyxl`, `pdfminer.six` 등)?
- `extraction.tool_version` 형식 = semver? Python pkg `__version__` raw?

**Recommendation**: wiki-schema.md §위키 페이지 형식에 자료형 표 추가. YAML 1.2 native timestamp 사용 권장 안 함 (string 통일 — sync·agent·grep 디버깅 일관).

### A2. `wiki/sources/{vault}/{path}.{ext}.md` 파일명 규약 — wiki-schema.md §디렉토리 구조

**Implementer question**: vault 원본이 `meetings/2026-Q1.pptx`일 때 wiki 파일명은 `meetings/2026-Q1.pptx.md` (단일 파일 모델). 원본이 `notes/idea.md`일 때는? `notes/idea.md.md`? 아니면 `notes/idea.md`?

**Current spec**: §디렉토리 구조에 `{path}.{ext}.md` 명시. §`[[link]]` 규약에 "source는 원본 확장자 포함 (예: `.pptx`) — 단일 파일 모델에서 파일명이 `{path}.{ext}.md`이므로 트레일링 `.md`만 생략" 명시.

**Gap**:
- 원본이 이미 `.md`인 경우의 처리 (vault에 markdown 파일이 들어 있고 sync가 그대로 작성 — `.md.md` 회피 정책)
- Google native 파일 (`.gdoc`·`.gsheet`·`.gslides`) — Drive UI에는 확장자 안 보임, API는 `mimeType`만. 어떤 확장자를 wiki 파일명에 쓰나? (export MIME에 따라 `.md`·`.csv`·`.txt`)
- 파일명에 공백·한국어·non-ASCII 처리 (Drive는 허용, filesystem도 허용. 그러나 `[[gdrive/회의록 (Q1).pptx]]` 같은 link에서 wikilink parser가 공백 split 안 하는지 unverified)

**Recommendation**: wiki-schema.md에 다음 표 추가:
```
| 원본 형식 | 추출 결과 | wiki 파일명 |
|---|---|---|
| binary (`.pptx`, `.docx`, `.xlsx`, `.pdf`) | 추출 텍스트 | `<relpath>.<ext>.md` (예: `meetings/2026-Q1.pptx.md`) |
| 텍스트 (`.md`, `.txt`) | 본문 그대로 | `<relpath>.md` (`.md` 중복 회피 — `notes/idea.md`는 그대로) |
| Google native (`.gdoc`/`.gsheet`/`.gslides`) | API export MIME에 따라 텍스트 | `<relpath>.<export_ext>.md` (예: `policies/onboarding.gdoc.md` — `.gdoc`는 Drive 가상 확장자) |
| 기타 (예: `.csv`, `.json`) | 본문 그대로 또는 표 렌더 | `<relpath>.<ext>.md` |

[[link]] 형식 (재확인):
- binary: `[[gdrive/meetings/2026-Q1.pptx]]` (트레일링 `.md`만 생략)
- 텍스트 `.md`: `[[gdrive/notes/idea]]` (원본 `.md`도 생략)
- Google native: `[[gdrive/policies/onboarding.gdoc]]` (가상 ext 보존)
```

### A3. binary 추출 도구 dispatch 표 — wiki-schema.md frontmatter `extraction.tool`

**Implementer question**: F3 script가 `.pptx`/`.docx`/`.xlsx`/`.pdf`를 추출할 때 어떤 라이브러리를 정본으로 쓰나? 추출 실패 시 (encrypted PDF, password-protected docx)?

**Current spec**: wiki-schema.md frontmatter 예시 — `extraction.tool: python-pptx, tool_version: 0.6.21`. ingest.md §Step 2 — "Binary 파일(`.pptx`/`.docx`/`.xlsx`/`.pdf`): 텍스트 추출". 도구 dispatch 표 없음.

**Gap**:
- ext → tool 매핑 정본
- 추출 실패 → wiki 페이지 작성 안 함인가, "추출 실패" 메시지 본문으로 작성인가
- F1 archive에는 `.pptx` python-pptx 예시만 있음, `.pdf`·`.xlsx`·`.docx`는 implementor 책임

**Recommendation**: wiki-schema.md §위키 페이지 형식에:
```
extraction.tool 매핑 (F3 정본):

| 원본 형식 | tool | fallback (실패 시) |
|---|---|---|
| .pptx | python-pptx | (실패) — wiki 페이지 작성, body = "[extraction failed: <reason>]" |
| .docx | python-docx | 동일 |
| .xlsx | openpyxl | 동일 |
| .pdf | pdfminer.six | (실패: encrypted) — body = "[extraction failed: encrypted PDF]" |
| Google Doc | Drive API export (MIME=text/markdown) | (실패) — body = "[export failed: <reason>]" |
| Google Sheet | Drive API export (MIME=text/csv) | 동일 |
| Google Slide | Drive API export (MIME=text/plain) | 동일 |

추출 실패도 wiki 페이지 작성은 진행 (frontmatter는 정상 + body는 실패 메시지). 이렇게 해야:
- file_map.json 정합성 유지
- /wh:lint가 본 페이지를 보고 retry 또는 archive 결정 가능
- entity/concept 추출은 빈 본문이므로 자연스럽게 skip
```

### A4. graphify CLI 버전 fallback 정책 — graphify.md §Step 1

**Implementer question**: "버전이 너무 오래되어 `GRAPH_REPORT.md` 미생성 가능성 시: stderr 경고 + 진행" — F5가 어떻게 "너무 오래"를 판단하나? minimum version 기준이 spec에 없음.

**Current spec**: graphify.md §Step 1 — "버전이 너무 오래되어 ..."

**Gap**:
- minimum supported version (`graphify >= ?.?.?`)
- `graphify --version` 출력 포맷 (확정?)
- "오래됨" 판단 후에도 진행 가능한지의 정책 — 결국 GRAPH_REPORT.md 없이도 wiki/index.md 폴백이 작동하므로 진행은 OK

**Recommendation**: graphify.md §Step 1에 `MIN_GRAPHIFY_VERSION = "x.y.z"` 정본 명시. install.sh가 venv에 lock 버전 설치하므로 mismatch는 메인테이너 수동 개입 케이스 — 이 경우 F5 implementer가 어떻게 처리할지 결정 (현 spec은 "진행"만 명시, 따라서 OK이지만 minimum 명시는 필수).

### A5. analyses heuristic의 실제 분류 규칙 — query.md §Step 5

**Implementer question**: F5가 query를 받았을 때, "이건 비교 질의" vs "이건 단순 사실 조회"를 어떻게 분류하나? LLM에 분류 prompt를 보내는가, 정규표현으로 키워드 매칭하는가? 사용자가 "저장해" 명시한 케이스의 trigger 키워드 정본은?

**Current spec**: query.md §Step 5는 두 카테고리만 명시 (저장 대상 / 저장 안 함). 카테고리별 예시 4가지씩. 실제 의사결정 알고리즘 미명세.

**Gap**:
- 분류 메커니즘: LLM heuristic vs rule-based
- 사용자 명시 trigger 키워드의 정본 ("저장해", "분석 페이지로 남겨줘", "기록해", "save", "remember" 등 다국어·동의어 처리)
- 경계 사례: "Q1 회의록 비교"는 "Q1 회의록 보여줘"의 변형인가 비교 질의인가
- false positive (저장 안 해야 하는데 저장) vs false negative 비용 트레이드오프 — 어느 쪽이 운영상 안전한가

**Recommendation**: query.md §Step 5에 LLM 분류 prompt 가이드 + 사용자 명시 trigger 키워드 목록(한국어/영어 union). 또는 v0.1.0 안전 default: "사용자 명시 키워드만 저장, 다른 경우는 모두 ephemeral" → 운영 후 false negative 빈도 보고 자동 분류 도입 결정. 후자를 권장 (false positive로 analyses 양산이 stub noise 누적과 합쳐지면 self-maintaining 목표 훼손).

### A6. F1 §4.7.5 Drive 403 분기 lift 누락 — ingest.md §실패 처리

**Implementer question**: ingest.md §실패 처리 표는 "script exit 75/2"만 분기. F1 §4.7.5는 Drive 403을 reason 파싱으로 Retryable(quota) vs Fatal(권한 회수)로 분류 명시. F3 implementer는 F1 spec을 봐야 함을 알아야 하지만 본 F2에는 reference 없음 → 본 결정이 F1·F2 어느 정본인가?

**Current spec**: ingest.md §실패 처리 — script exit code만. wiki-schema.md §신뢰 경계 — F1 §4.5.5 lift됨. F1 §4.7.5는 lift 안 됨.

**Gap**: F1 §4.7.5 403 분기·HTTP 401·token revoked 처리가 F2에 lift되지 않음. F3 implementer가 본 F2만 보고 구현 시 분기를 통째로 누락 → 모든 403을 Retryable 또는 Fatal로 통일해버릴 위험.

**Recommendation**: ingest.md §Mechanical phase에 한 줄 추가:
```
script의 에러 분류 정책 (F1 §4.7.5 정본):
- HTTP 403 + reason in {userRateLimitExceeded, rateLimitExceeded, quotaExceeded} → exit 75 (Retryable)
- HTTP 403 + reason in {insufficientPermissions, forbidden} → exit 2 (Fatal)
- HTTP 401 → exit 2 (Fatal, token 무효)
- HTTP 5xx, 네트워크 timeout → exit 75 (Retryable)
- 자세한 표는 F1 archive §4.7.5 참조
```

### A7. log.md no-op append 트랜잭션 시멘틱 — ingest.md §Step 3·5

**Implementer question**: has_changes=false 케이스에서 §Step 3은 "log.md에 no-op 항목 append + exit 0" 명시. §Step 5는 (has_changes=true 사이클 가정으로 보임) status별 변형으로 "skipped — has_changes=false (Script duration만, Semantic 줄 생략)" 표시. 둘이 같은 것? §Step 3 분기에서 §Step 5가 호출되는 것?

**Current spec**: §Step 3 본문 - "log.md에 no-op 항목 append → exit 0". §Step 5 본문 - "Status: skipped — has_changes=false ..."

**Gap**: §Step 3과 §Step 5의 관계 명시 부재. F5 implementer는 (A) §Step 3에서 별도 mini log append + 종료, (B) §Step 3은 fast path 분기 표시이고 실제 append는 §Step 5 코드를 호출 둘 다 가능. log.md 포맷 일관성을 위해 (B)가 자연스러우나 spec은 (A)처럼 읽힘.

**Recommendation**: §Step 3 - "Step 5로 jump (status=skipped 항목 append) → exit 0"로 명시. 또는 §Step 5가 status enum 무관하게 호출되는 단일 entry임을 §절차 개요에 명시.

---

## Acceptable for v0.1.0 (defer to F3/F5 implementation)

다음은 spec이 의도적으로 deferral한 항목 + deferral 안전 검증:

- **분류 결정 (`/wh:query` analyses heuristic 세부)** — A5에서 보고했듯 v0.1.0은 단순 default (명시 keyword만) 권장. 자동 분류는 운영 후 결정으로 안전 deferral 가능
- **graphify minimum version 정확한 숫자** — install.sh가 venv에 pinned 설치하면 mismatch 없음. minimum이라는 *개념*만 명시되면 (A4) 구체 숫자는 F4가 결정 가능
- **`/wh:lint --apply` 인터랙티브 모드** — lint.md §Step 7이 "v0.1.0 초기는 일괄 적용" 명시 — 명시적 deferral. 안전
- **다중 vault 동시성 직렬화 메커니즘 (`operations.hermes_concurrency: serial` 실현)** — F1 §4.8.4에서 (i)/(ii)/(iii) 세 옵션 surface. F2 단일 vault 가정 — F4·F5 검토 후 결정. 안전 deferral (단일 vault 환경에서는 동작에 영향 없음)
- **`/wh:lint` 자동 호출 graphify 실패 시 부분 lint 결과 저장 여부** — lint.md §Step 9 명시 (graphify 실패가 lint를 fail시키지 않음). 안전
- **`pending_ingest.dead.<ts>.json` 정리 정책** — ingest.md §Step 1만 격리 명시, retention 정책은 미정 — 메인테이너 수기 정리 가정으로 안전 deferral (단 추후 ADR-0014 후보로 surface)
- **codex/gemini/copilot 매핑 검증** — ADR-0012가 명시적으로 "F4·F5 검증 시점에 확정". 안전 deferral (단 "user-facing 실패 모드"는 ADR-0012에 추가 권장 — B5 참조)

---

## What's well-specified

- **wiki/ 디렉토리 책임 매트릭스** — wiki-schema.md §책임 매트릭스. sync vs agent의 write 권한이 페이지별로 명료. F3·F5 분리 가능
- **ADR-0001 vault namespace + `[[link]]` 규약** — sources만 prefix 강제, entities/concepts/analyses는 단축형. 충돌 정책 disambiguator. F5의 link 검증 로직(lint.md §Step 2)이 이 규약만 보면 구현 가능
- **5종 state 파일 형식 (ADR-0007)** — all JSON + atomic write + tmpfile/os.replace 패턴. retry.json 스키마는 ADR-0007에 완전 명시. cursor·file_map·last_sync는 F1 §4.4.1~3 lift됨 (단 F2에 직접 명시 부재는 cross-ref 부담 — minor)
- **/wh:lint 권한 매트릭스 (ADR-0008 + lint.md)** — 자동/`--apply` 분류 표가 결정론적. F5가 봐서 모호 없음
- **ADR-0006 unified orchestration의 책임 분리** — script subprocess vs agent semantic phase의 boundary가 ingest.md §Step 2·4에서 명확
- **wikihub.yaml의 single source of truth + lifecycle (ADR-0010 표)** — install.sh와 /wh:setup의 책임 분할 명료. 신규 install vs update vs yaml 편집의 경로가 표로 정리됨
- **/wh:setup의 fail-fast 정책** — setup.md §Step 1의 검증 항목별 실패 처리 (스키마 위반 = 전체 중단, OAuth 일부 무효 = 해당 vault만 제외)
- **README structure (wiki-schema.md §디렉토리 구조)** — 한 페이지에 instance.root 이하 전체 구조 + 외부 vault 위치까지 명시. F3 구현 시 mental model 충분
- **<agent_invocation> placeholder (ADR-0012)** — agent-agnostic 어휘를 위한 일관 표기. spec 전체에 적용됨

---

## Operational readiness gaps

신규 메인테이너가 본 spec만 보고 install → configure → operate을 완수할 수 있나? 다음 갭이 있음.

### O1. install.sh의 첫 실행 경로가 메인테이너 가시 부재

- spec은 install.sh 결과물의 형태(`_system/`·`scripts/` fetch 등)만 정의. 메인테이너가 첫 호출 시 어떤 prompt가 뜨는지, OS 검증 항목이 뭔지, 실패 시 어떻게 복구하는지 미정의 — F4 산출물이지만 본 F2 spec 안에서 "install.sh가 무엇을 점검하기로 약속하는가" precondition만이라도 명시 필요
- 권장: ADR-0010에 "install.sh precondition (Ubuntu 22.04+ ARM, python3.11+, curl, optional git)" 정도 minimum spec 추가

### O2. OAuth 1회 인증 절차의 cross-doc reference

- F1 §4.7.1~3에 메인테이너 7단계 + macOS dev box 발급 + scp 절차가 있음. F2는 ADR-0003 인용만 — 신규 메인테이너가 본 F2만 보면 "OAuth pickle을 어디서 가져오는지" 가시 부재
- 권장: wiki-schema.md §참조 또는 setup.md §사전 조건에 "OAuth pickle 발급 절차는 F1 archive §4.7 또는 docs/runbooks/oauth-setup.md (F4 산출물) 참조" 한 줄

### O3. 첫 부팅 + 첫 ingest의 bootstrap 가드 (F1 §4.4.6 lift 부재)

- F1 §4.4.6의 `bootstrap_allowed` + `--bootstrap` CLI 플래그 가드 (Drive 10만 파일 자동 스캔 차단) — 본 F2에는 lift 없음
- ingest.md §사전 조건은 "OAuth credentials 유효" 정도만. cursor 없는 첫 ingest의 정책 미명시
- F3 implementer가 본 F2만 보고 구현 시 첫 ingest에서 통째 스캔할 위험 → quota 폭주
- 권장: ingest.md §사전 조건 또는 §Mechanical phase에 한 줄 추가:
  ```
  cursor.json 부재 시 (첫 sync 또는 _state 소실):
  - wikihub.yaml의 vaults[*].options.bootstrap_allowed = false (default) → script exit 2 (Fatal)
  - 메인테이너가 의도적 bootstrap 시: bootstrap_allowed: true + script --bootstrap 플래그 동시 (F1 §4.4.6)
  ```

### O4. /wh:lint --apply 호출의 운영 트리거 명시 부재

- lint.md §호출은 "메인테이너가 wiki/_lint/report.md read 후 의도적 수동 호출". 단 report.md가 일별로 overwrite되므로 메인테이너가 report를 매일 봐야 하는 운영 부담 + ADR-0008 §Consequences "report 누적 → 메인테이너가 안 보면 의미 없음" 자체 인정
- 권장: setup.md §보고 또는 별도 runbook에 "report.md 갱신을 Telegram으로 알림" 같은 push 메커니즘 명시 — 또는 ADR-0008 §부정/제약을 "v0.1.0은 push 없음, 메인테이너 자발적 확인" 명시적 deferral

### O5. update install.sh 재실행의 영향 명시

- ADR-0010 step 6 "user 파일 보존" 보장은 있음. 단 update 시 install.sh가 _system/을 통째 갱신할 때 메인테이너가 작성한 wikihub.yaml에 이전 버전 키만 있으면? schema migration 정책 부재
- 권장: wikihub.yaml의 `version: 1` 키와 install.sh의 schema check 관계 명시 — version mismatch 시 메인테이너에게 migration guide URL 안내 또는 fail-fast

### O6. 운영 중 vault 추가 절차 가시 부재

- ADR-0009 §호출 시점 "신규 vault 등록 후 (메인테이너가 yaml에 vault 추가 → `/setup`)" 한 줄만. 메인테이너 시점에서 step-by-step (yaml 추가 → OAuth pickle 발급 → scp → /wh:setup → enable) 누락
- F4 단계에서 docs/runbooks/add-vault.md로 명문화 가능. 단 본 F2가 spec 정본인 이상 setup.md 또는 wiki-schema.md §참조에 "신규 vault 추가 runbook: F4 산출물 예정" 표시 권장

### O7. agent-agnostic 클레임의 실제 검증 — codex-cli/gemini-cli 사용자 시나리오

- ADR-0011·0012가 `wh:` prefix + agent.binary/oneshot_args 분리로 agent-agnostic 구조 잡음. 단 v0.1.0은 hermes만 검증됨 (ADR-0012 §Consequences 명시)
- codex-cli 사용자가 본 spec만 보고 wikihub를 install하면:
  1. install.sh에서 agent type = codex 선택
  2. ADR-0012의 default mapping `["exec"]` 적용 → wikihub.yaml에 기록
  3. /wh:setup이 systemd unit 생성: `ExecStart=codex exec "/wh:ingest --vault X"`
  4. 실제 codex가 `exec` 인자를 안 받으면 (또는 prompt를 마지막 인자로 안 받으면) systemd timer가 매번 실패
  5. 메인테이너는 systemd journal로 발견 → wikihub.yaml의 agent.oneshot_args 수기 수정 + /wh:setup 재호출
- 위 시나리오의 user-facing 실패 모드가 spec에 없음. 권장: ADR-0012 §부정/제약에 "검증되지 않은 agent 사용 시 1차 systemd unit 실패 → journal로 detect + yaml.agent.oneshot_args 수기 조정" 추가 + install.sh가 미검증 type 선택 시 explicit 경고

### O8. ingest의 처음부터 끝까지 dry-run 검증 도구 부재

- 신규 메인테이너가 OAuth pickle + wikihub.yaml + /wh:setup까지 완료한 뒤, 첫 timer 발사 전에 "이 vault에서 sync가 옳게 동작하는가"를 검증할 도구가 명시 부재 (setup.md §Step 1의 OAuth `creds.valid`만으로는 실제 changes.list 권한·root_folder_id 접근 가능 여부 미검증)
- 권장: setup.md §Step 1에 OAuth 토큰 valid 확인 후 `drive.about.get` 같은 light API 호출로 실권한 검증 1단계 추가 — 또는 별도 `<agent_invocation> "/wh:ingest --vault X --dry-run"` mode를 v0.1.0 또는 후속 ADR로 발의

---

## 요약 — F3/F5 시작 전 권장 순서

1. **Blocker 해소** (B1~B5): F2 내부에서 spec 추가 + ADR-0013 1건 발의 (entity/concept 추출 정책)
2. **Ambiguity 명시** (A1~A7): wiki-schema.md frontmatter 자료형 표, source 파일명 규약, extraction tool 매핑 — 본 review의 권장 추가 사항을 F2 안에서 정리
3. **Operational gap** (O1~O8): F4 산출물 docs/runbooks/* 의 외형 부분만 본 F2가 reference (실제 작성은 F4)
4. 이후 F3·F5 분리 가능 — F3는 ingest.md §Step 2 (script subprocess JSON contract)만 명세 잡히면 단독 진행 가능, F5는 §Step 4·log.md 포맷·entity/concept 정책만 잡히면 단독 진행 가능

본 review가 권장한 spec 변경 부피는 wiki-schema.md ~30줄·ingest.md ~20줄·setup.md ~10줄 + ADR-0013 1개 (entity/concept extraction policy). 작업 1일 분량으로 추정. 본 review의 priority blocker 5건만 해소되면 F3/F5는 무재조율 진행 가능.
