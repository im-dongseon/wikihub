# Design Review 1 — graphify_usage_review (architectural)

- **Reviewer**: subagent (general-purpose, architectural perspective)
- **Date**: 2026-05-19

## 종합 평가

분석의 매트릭스 구성과 책임 경계(ingest = mechanical+semantic, lint = wiki-wide hygiene, query = read+analyses) 인지는 정확하다. 그러나 "발견된 격차" 의 몇 항목은 **격차가 아니라 의도된 경계**다 — 특히 ingest 의 graphify 무사용. 즉시 fix 4건은 전반적으로 §Note/문서 보강 수준에 머물러 Karpathy §2 Simplicity First 위반 위험은 낮으나, fix #1 의 적용 위치가 ADR-0036 §D3 와 충돌(중복 정의)할 소지가 있다. v0.2.x 분류는 대체로 정합하지만 lint Step 9 의 **graphify 자체 검증** 1건은 v0.1.x 처리가 정합이다.

## 격차 식별의 정합성

- **query.md (Leiden / bridge / centrality 미활용)**: 진짜 격차이지만 wiki 가 N=수십 규모일 v0.1.0 시점에서는 community detection 가치가 surface 안 됨. "운영 데이터 surface 후" 트리거는 정합.
- **lint.md Pass 3 churn 인지 부재**: 진짜 격차. ADR-0036 §D4 가 명시한 "operational normal" 이 lint.md 본문에 일절 lift 안 됨 — 운영자가 cycle 간 N/M drift 를 panic 으로 오인할 운영 결함.
- **lint.md "graphify 결과 자체 검증 (노드 수 vs wiki page 수)"**: 진짜 격차. Pass 3 부분 실패 (LLM rate limit, 일부 entity 추출 누락) 가 silent 로 통과해 graph drift 가 누적될 risk. 컨텍스트가 본 항목을 v0.2.x 로 미룬 것은 **과소평가**.
- **ingest.md "graphify 무관"**: 격차 아님. ADR-0006 §Decision 의 책임 경계 (`ingest` = mechanical+semantic, graph rebuild = `lint` 사이클) + ADR-0036 §D6 (timer cost upper bound) 둘 다와 정합. 24h latency 는 의도된 design.
- **ingest 의 `log.md` graphify noise**: 진짜 격차이나 fix 위치가 §D3 와 충돌 — 아래 참조.

## 즉시 fix 4건 평가

| # | 항목 | 평가 | 사유 |
|---|---|---|---|
| 1 | `.graphifyignore` 에 `**/log.md` + `**/_lint/report.md` 추가 | **modify** | ADR-0036 §D3 가 `_lint/` 디렉토리 전체를 이미 ignore — `**/_lint/report.md` 는 중복. `**/log.md` 는 정합. 또한 변경 위치가 `_system/templates/wiki/.graphifyignore` 라고 적혔는데 §D3 는 `wiki/.graphifyignore` 를 `install.sh` 또는 `wh-setup` 이 배치하도록 lock — 템플릿 path 가 실제 존재하는지 확인 필요 |
| 2 | lint.md Step 9 §Note — Pass 3 churn 인지 + N/M drift 정상 명시 | **accept** | ADR-0036 §D4 의 "operational normal" 을 playbook 에 lift — 운영자 panic 방지. 정당성 명확 |
| 3 | ingest.md §Note (graphify 미사용 + lint chain 책임 환기) | **accept** | 격차 자체는 아니지만 책임 경계의 명시화는 self-documenting 가치 있음. 메소드론 §3 Step 3 자가 검증의 "명령어 간 논리적 충돌 없음" 보강 |
| 4 | query.md Step 1 §Note — community/bridge/centrality 는 v0.2.x | **accept** | 격차 인지의 명시화. 향후 v0.2.x 트리거 발의 시 ADR 추적성 확보 |

## 누락 / 과잉

- **누락**: lint.md Step 9 의 **graphify 결과 자체 검증** (graph.json 노드 수 vs wiki 페이지 수의 sanity check). Pass 3 의 silent partial failure 가 query 정확도를 점진 저하시키는 운영 risk — v0.1.x 안에서 cheap check (노드 수가 wiki page 수의 일정 비율 이하면 ops-alert) 1줄 추가가 적정.
- **과잉**: fix #1 의 `**/_lint/report.md` — `_lint/` 가 §D3 default 에 이미 있어 중복. `log.md` 만 추가가 minimal.

## v0.2.x 트리거 분류

- **query Leiden / bridge / centrality 활용**: 정합. wiki 규모와 운영 데이터 surface 가 선행 조건.
- **ingest adaptive `--update` (옵션 C)**: 정합. latency 가 사용자 불편으로 surface 되기 전 도입은 ADR-0036 §D6 의 cost 통제 모델 위반.
- **lint community / god node 변동 추적**: 정합. 운영 데이터 수개월 후가 적정.
- **graphify CLI query subcommand 직접 호출**: 정합 — upstream release status 의존.

## 우선순위 권장

- **즉시 (v0.1.x cleanup)**: fix #1 (단 `log.md` 만), #2, #3, #4 + **누락 항목 (graphify 결과 self-check)** 추가. 모두 §Note 또는 1줄 수준 — Karpathy §2 위반 risk 무.
- **다음 release**: 없음 (cleanup 단일 wave 권장).
- **v0.2.x**: 컨텍스트의 4개 트리거 그대로.

## ADR-0005 정책과의 정합 — 별도 의견

query.md 의 Leiden community 활용 검토는 ADR-0005 의 "graphify primary, wiki/index.md fallback" 정책에 영향 **없음**. 본 정책은 *어느 자료를 1차로 read 할지* 의 결정이고, community detection 은 graphify 자료 내부에서 추가 분석을 할지의 결정이라 layer 가 다르다. ADR-0005 §Note 갱신 불필요.
