# Design Review 2 — graphify_usage_review (operational/scope)

- **Reviewer**: subagent (general-purpose, operational/scope perspective)
- **Date**: 2026-05-19

## 종합 평가

본 context.md 의 격차 식별은 분석으로서는 합리적이나 **즉시 fix 4건의 operational justification 이 비대칭**이다. v0.1.0 미배포 + 실 데이터 부재 상태에서 4건 중 #1·#3 은 "지금 운영에서 발생할 것이 확정된" surgical fix 이지만 #2·#4 는 "혹시 운영자가 혼란할까봐" 의 §Note 보강 — Karpathy §2 Simplicity First 의 "200줄을 50줄로" 정신과 정확히 반대로 "지금 0줄로 충분한 것에 §Note 5~10줄 추가" 패턴이다. ADR-0036 §D4 가 Pass 3 churn 을 이미 결정의 정본으로 lock 했고 graphify.md L83 §Note 도 갱신됐는데 lint.md / query.md 양쪽에 동일 trivia 를 echo 하는 것은 spec drift 의 source 만 증식시킨다. **§8 Atomic Change 관점에서 본 cleanup 은 "graphify 사용 패턴 클리닝" 단일 주제가 아니라 (a) ignore 정책 plumbing + (b) playbook §Note 보강 + (c) v0.2.x 트리거 환기 — 세 다른 목적을 하나로 묶은 것**으로 보인다. 분리 검토 권장.

## Karpathy §2 위반 위험

| 즉시 fix | 분류 | 근거 |
|---|---|---|
| #1 `.graphifyignore` 추가 | 사후 대응 (justified) | `_lint/report.md` overwrite + vault별 `log.md` append 는 spec 으로 확정된 entity-noise source. graphify 가 본 파일들의 timestamp / 이력 텍스트를 entity 로 추출하면 god-node 후보로 surface — 운영 데이터 없이도 결정 가능 |
| #2 lint Step 9 §Note (churn 인지) | **사전 대응 (over-engineering 위험)** | ADR-0036 §D4 가 이미 정본. 운영자가 lint report 의 `N → M` drift 를 보고 patch trigger 할 가능성은 추측. **실제 운영 후 surface 시 추가가 정답** |
| #3 ingest.md §Note (graphify 미사용) | 사후 대응 (marginal) | playbook 간 책임 경계 명시는 self-documenting 가치 있음. 단 "v0.2.x 트리거 환기" 까지 본문에 박는 것은 ADR-0036 후속 영향 절 echo — drop 후보 |
| #4 query.md §Note (Leiden v0.2.x) | **사전 대응 (가장 약함)** | 미구현 기능을 §Note 로 박는 것 자체가 "혹시 잊을까봐" 패턴. v0.2.x 트리거 매트릭스는 context.md / HISTORY.md 가 이미 정본 |

#2 + #4 는 Karpathy "Surgical Changes — 인접 코드 자발적 개선 금지" 와도 충돌. 사용자 요청은 graphify 사용 패턴 검토였지 playbook §Note 증식이 아니다.

## 운영 비용 평가

context.md 의 ingest (B) v0.1.0 default + (A)/(C) v0.2.x 분류는 **정합**. 근거:

- (A) 매 ingest cycle (10 min 주기) graphify --update 호출은 Pass 3 Anthropic API 비용을 lint 24h 1회 → 144회/일 (10min × 24h × 6) 로 폭증. 운영자 base 의 cost upper bound 가 ADR-0036 §D6 의 "24h 1회" 가정에서 정확히 144× scale up — v0.1.0 의 cost 모델 자체가 무효화된다.
- (C) adaptive `changed_count > threshold` 는 threshold 결정에 운영 데이터 필요 — chicken-and-egg, v0.2.x 트리거 정합.
- 24h latency 의 wh-query 정확도 영향은 **실 운영 데이터 없이는 판단 불가**. context.md 가 (B) 를 default 로 묶어두고 surface 시 (C) 격상으로 처리하는 결정은 Simplicity First 정합.

## 즉시 fix 4건 — operational 평가

| # | 항목 | 운영 가치 | sim violation 위험 |
|---|---|---|---|
| 1 | `.graphifyignore` 에 `**/log.md` + `**/_lint/report.md` | high | no |
| 2 | lint.md Step 9 §Note (Pass 3 churn) | low | **yes** — ADR-0036 §D4 와 중복 |
| 3 | ingest.md §Note (graphify 미사용) | medium | marginal — "v0.2.x 트리거 환기" 부분만 drop |
| 4 | query.md §Note (Leiden / bridge / centrality v0.2.x) | low | **yes** — 미구현 기능 §Note 박기 |

`**/_lint/report.md` 는 ADR-0036 §D3 의 `_lint/` 디렉토리 전체 제외와 중복일 수 있음 — 검증 필요 (디렉토리 패턴이 하위 파일까지 cover 하면 #1 의 두 번째 항목 drop).

## Atomic Change 정합

4건은 하나의 feature 가 아니다:

- **#1** 은 `.graphifyignore` template 변경 — install/setup 산출물.
- **#2·#4** 는 playbook §Note 추가 — documentation drift 방지.
- **#3** 은 playbook 간 책임 경계 명시 — architectural clarification.

같은 release window (v0.1.3) 의 ADR-0036 통합 cleanup 으로 묶는 것은 **HISTORY.md 의 graphify_integration 항목에 §Note 보강으로 흡수**가 정합. 별도 feature ID 발급 + Step 3 구현은 §8 Atomic Change 위반. 단일 commit / sub-section 으로 처리하고 본 review feature 자체를 archive 종료 후보로 권장.

## 우선순위 권장

| 분류 | 항목 |
|---|---|
| **즉시 (v0.1.3 cleanup)** | #1 만 — `.graphifyignore` 의 `**/log.md` 추가. `_lint/report.md` 는 디렉토리 패턴 중복 검증 후 결정 |
| **다음 release (실 운영 데이터 surface 후)** | #2 (churn drift 가 운영자 혼란 실제 발생 시), context.md 의 v0.2.x 트리거 4건 (Leiden / adaptive / community 추적 / CLI query subcommand) |
| **drop** | #4 (미구현 §Note 박기), #3 의 "v0.2.x 트리거 환기" 부분 (책임 경계 1줄만 유지), #2 의 lint.md 추가 §Note (ADR-0036 §D4 reference 1줄로 대체 가능) |

**핵심 권장**: v0.1.0 미배포 + 실 데이터 부재 상태에서 §Note 증식은 spec drift 의 source 만 만든다. ADR-0036 §D4 / §D6 가 이미 정본 — playbook 은 ADR reference 만 두고 §Note 본문 echo 회피. #1 단일 항목으로 cleanup 범위 축소 + HISTORY graphify_integration 항목에 §Note 보강으로 흡수가 §8 Atomic Change + §2 Simplicity First 양쪽 정합.
