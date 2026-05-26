# ADR-0033: skill namespace prefix lock — `wh-` (hyphen)

- **Status**: Accepted
- **Date**: 2026-05-18
- **Feature**: features/20260518_hermes_adapter
- **Supersedes**: ADR-0011
- **Superseded by**: 없음

## Context

ADR-0011 (2026-05-13) 은 skill namespace prefix 를 `wh:` (colon, default) + `wh-` (hyphen, fallback) 으로 lock. fallback policy 는 install.sh 가 colon escape 이슈 시 자동 치환.

F5 feature 의 Hermes docs 실측 (2026-05-18) 결과:
- Hermes 의 SKILL.md docs 예시는 모두 하이픈 (`duckduckgo-search`, `deploy-k8s`) — colon 미예시.
- Hermes 의 skill name character 제약 명시적 documentation 없음.
- slash-command dispatch 의 colon prefix 호환성 미보장.

ADR-0011 의 default `wh:` 은 운영 시 Hermes dispatch 실패 가능성. fallback policy (자동 `wh-` 치환) 가 사실상 default 동작이 될 가능성이 높아짐. spec 의 정확성 + 운영자 mental model 일관성 위해 default 자체를 `wh-` 로 lock 결정 필요.

## Considered Options

- **(α) `wh-` default lock + ADR-0011 supersede**: F5 의 보수적 선결정 — Hermes 의 colon 부분 동작 여부와 무관하게 정본 default 를 hyphen 으로. operator override 는 yaml 의 `agent.skill_prefix` 로 가능.
- **(β) Step 3 VM 실측 후 결정**: colon 동작 확인 시 ADR-0011 의 `wh:` default 유지, 미동작 시 ADR-0011 supersede. — Step 2 종료 시점에 정본 상태 미정 → 설계서 v2 의 §5 전체 일관성 깨짐 (R3-CR3-1-CRIT-1).
- **(γ) `wh_` (underscore)**: ADR-0011 의 (γ) 후보 — Hermes 미예시. 채택 시 추가 검증 부담.

> 옵션 상세는 [features/20260518_hermes_adapter/analysis_and_design.md §5.4.1](../../features/20260518_hermes_adapter/analysis_and_design.md) 참조.

## Decision

**채택**: (α) `wh-` default lock + ADR-0011 supersede.

### skill 등록 명칭 (정본)

| 명령 | skill 이름 |
|---|---|
| /wh-ingest | `wh-ingest` |
| /wh-lint | `wh-lint` |
| /wh-query | `wh-query` |
| /wh-graphify | `wh-graphify` |
| /wh-setup | `wh-setup` |

### yaml schema

```yaml
agent:
  skill_prefix: "wh-"   # default — ADR-0033 lock
```

operator override: `wikihub.yaml.agent.skill_prefix: "wh:"` 또는 다른 값 가능. install.sh 의 `_migrate_agent_schema` 가 `wh:` 잔존 detect 시 명시 confirm 후 `wh-` 로 patch (operational drift fix).

### agent 호출 예 (정본)

```bash
hermes chat --skills wh-ingest --quiet --query "/wh-ingest --vault gdrive"
hermes chat --skills wh-lint --quiet --query "/wh-lint"
hermes chat --skills wh-lint --quiet --query "/wh-lint --apply"
hermes chat --skills wh-query --quiet --query "/wh-query 지난주 회의록"
hermes chat --skills wh-graphify --quiet --query "/wh-graphify"
hermes chat --skills wh-setup --quiet --query "/wh-setup"
```

### colon 호환 (Note)

Step 3 VM 실측에서 Hermes 가 `wh:` colon prefix 도 받는 것 확인 시:
- ADR-0033 의 Decision 변경 없음 — default `wh-` 유지.
- 본 ADR 의 Notes 섹션에 "Hermes 가 `wh:` 도 호환. operator override (`agent.skill_prefix: wh:`) 동작 검증 완료" 추가.
- ADR-0011 의 fallback 의미는 ADR-0033 의 default 와 일치 — semantic 일관성 유지.

## Consequences

- **긍정**:
  - 운영자 mental model 일관 — README·spec·ADR·wiki-schema 모두 `wh-` 표기.
  - Hermes docs 미지원 colon 의 dispatch 실패 위험 제거.
  - operator override 가 yaml 로 가능 — 미래의 다른 prefix convention 도입 호환.
  - ADR-0011 의 fallback policy 가 default 로 승격 — 운영 시 fallback trigger 의 불확실성 제거.

- **부정/제약**:
  - ADR-0011 의 `wh:` (Slack/Discord convention semantic 우위) 포기. semantic value 우위는 v0.2.x 의 다른 agent (Slack-integrated tools) 도입 시 재평가.
  - 기존 운영자 wikihub.yaml 의 `skill_prefix: "wh:"` 잔존 → `_migrate_agent_schema` 의 1회성 schema lift 필요. operator confirm 부담.

- **후속 영향**:
  - **ADR-0011** Status → Superseded by ADR-0033 + 본 ADR 의 `Supersedes: ADR-0011` 양방향 link.
  - **ADR-0012** §systemd unit 생성 예 의 `hermes -z "/wh:ingest"` → `hermes chat --skills wh-ingest --quiet --query "/wh-ingest"` 정합 (ADR-0012 §Decision 갱신 Note).
  - **ADR-0023** install snippet 의 prerequisite 안내 — `wh-` 표기 일관.
  - **`_system/wiki-schema.md`** L:319-324 orchestration table + L:340·L:347 의 `wh:` 잔존 site 일괄 갱신.
  - **`_system/commands/*.md`** 5건의 §호출 line 의 prefix 갱신.
  - **`README.md`** L:179 의 표기 정합.
  - **재검토 트리거**: 어떤 LLM agent CLI 가 colon prefix 를 강제 (다른 syntax 거부) 도입 시 본 ADR 재검토.

## Note (2026-05-26, ADR-0041 cross-reference) — systemd unit ↔ Hermes skill layer 분리

[ADR-0041](0041-systemd-prefix-realign.md) 가 systemd unit prefix 를 `wikihub-*` 로 lock (mount@/ingest@/lint/graphify 4 unit 일관). 본 ADR-0033 의 Hermes skill prefix `wh-` 와 **다른 abstraction layer** — 두 layer 모두 독립적으로 prefix 정합:

| Layer | Prefix | 정합 ADR |
|---|---|---|
| Hermes skill (LLM 호출 unit) | `wh-` | **ADR-0033 (본 ADR)** |
| systemd unit (OS service) | `wikihub-` | ADR-0041 |

호출 chain (systemd ExecStart 단일 라인) — `wikihub-lint.service` (systemd) → `hermes chat --skills wh-lint --quiet --yolo --query "/wh-lint"` (skill). 두 layer 의 직접 매핑은 ExecStart 한 줄로 표현 → prefix 통일 안 해도 명료. 본 ADR-0033 의 결정 변경 없음 — 단지 ADR-0041 이 systemd layer 의 prefix 결정을 별도 ADR 로 분리 명시.
