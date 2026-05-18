# ADR-0011: agent skill namespace prefix — `wh:`

- **Status**: Superseded
- **Date**: 2026-05-13
- **Feature**: features/20260513_wikihub_schema_v1
- **Supersedes**: 없음
- **Superseded by**: ADR-0033 (2026-05-18, F5 hermes_adapter — `wh-` hyphen lock)

## Context

wikihub의 agent 명령(`/ingest`·`/lint`·`/query`·`/graphify`·`/setup`)은 agent CLI(Hermes·codex-cli·gemini-cli·copilot 등)에 skill로 등록되어 호출된다. agent들은 동일 호스트에 여러 도구의 skill을 함께 등록할 가능성이 크고, 이름 충돌(예: 다른 도구도 `/ingest`를 등록)을 방지하기 위해 **namespace prefix** 필요.

또한 wikihub skill만 한눈에 식별·관리하기 위해서도 공통 prefix가 유용.

prefix 후보 문자:
- `:` (콜론) — Slack/Discord namespace convention. semantic
- `-` (하이픈) — kebab-case, 모든 환경 호환
- `_` (언더스코어) — 모든 환경 호환, 키 입력 약간 어려움
- `.` (점) — Java package convention, 일부 CLI에서 ambiguous (확장자처럼 보임)
- `/` (슬래시) — 이미 명령 prefix로 사용 중 — 사용 불가

## Considered Options

- **(α) `wh:` (default + 권장)**: Slack-style namespace. semantic. 일부 agent CLI에서 호환 확인 필요
- **(β) `wh-`**: kebab-case. 보편 호환
- **(γ) `wh_`**: snake_case. 보편 호환
- **(δ) prefix 없음**: skill 이름 그대로 (`ingest`, `lint`...). 충돌 위험

## Decision

**채택**: (α) `wh:` (default), `wh-` (fallback)

skill 등록 명칭 (정본):

| 명령 | skill 이름 |
|---|---|
| /wh:ingest | `wh:ingest` |
| /wh:lint   | `wh:lint`   |
| /wh:query  | `wh:query`  |
| /wh:graphify | `wh:graphify` |
| /wh:setup  | `wh:setup`  |

agent 호출 예:
```bash
hermes -z "/wh:ingest --vault gdrive"
agent -z "/wh:lint"
agent -z "/wh:lint --apply"
agent -z "/wh:query 지난주 회의록"
agent -z "/wh:graphify"
agent -z "/wh:setup"
```

**fallback policy**:
- install.sh가 agent CLI에 `wh:` namespace로 skill 등록 시도
- 등록 실패 또는 콜론 escape 이슈 발생 시 `wh-` 로 fallback 자동 시도 (install.sh가 처리)
- fallback 발생 시 install.sh가 명시적 경고 + `wikihub.yaml.agent.skill_prefix` 키에 실제 사용된 prefix 기록 (default `wh:`)
- agent 호출 시 prefix는 yaml에서 read

**이유**:

- **`wh:` semantic 우위**: Slack/Discord convention과 정합. 모던 agent CLI는 콜론을 namespace separator로 인식하는 trend
- **fallback이 안전망**: `wh-` 자동 대체로 환경 호환성 보장. 메인테이너 별도 대응 불필요
- **단일 문자 prefix**: agent CLI 자동완성·검색 효율
- **(δ) 기각**: 다른 도구의 skill과 충돌 위험. 운영 안전성 부족
- **`wh` 자체 선택 근거**: "wikihub"의 축약. 다른 도구와 prefix 충돌 가능성 낮음

> **참고**: agent의 one-shot 호출 syntax(`-z`, `exec`, `-p` 등)은 본 ADR과 별개 — ADR-0012에서 별도 결정(`wikihub.yaml.agent.invocation` 분리).

## Consequences

- **긍정**:
  - skill 이름 충돌 회피
  - wikihub skill 일괄 식별 가능 (agent CLI `list skills | grep ^wh`)
  - fallback policy로 환경 호환성 보장

- **부정/제약**:
  - 호출 시 prefix 입력 부담 (`/wh:ingest` 8자 vs `/ingest` 7자) — trivial
  - agent CLI별 namespace 처리 방식 다양 → install.sh 구현 dispatch 부담 (F4)
  - fallback 발생 시 user-facing skill 이름이 environment마다 다름 (`wh:ingest` vs `wh-ingest`) — yaml에 기록해서 추적

- **후속 영향**:
  - **F2 산출물 (`_system/commands/*.md`)**: 명령 본문에 `/wh:` prefix 명시. fallback 발생 시 prefix 치환은 agent runtime 책임
  - **F2 wikihub.yaml schema 추가**: `agent.skill_prefix` 키 (default `"wh:"`)
  - **F4 install.sh**: agent별 skill 등록 dispatch + 콜론 호환성 detect + fallback 적용 + yaml 갱신
  - **F4 systemd unit ExecStart**: `hermes -z "/wh:ingest --vault X"` 처럼 prefix 포함 (fallback 시에도 yaml의 prefix 사용)
  - **재검토 트리거**: 어떤 agent CLI도 콜론을 지원 안 하는 경우 본 ADR을 superseded 처리하고 `wh-` 또는 `wh_` 기본화
