# Review Context — graphify usage in query/lint/ingest

## 배경

ADR-0036 (commit `6e2dbea`) 에서 graphify CLI 를 PyPI `graphifyy` 로 확정 + install.sh 통합 완료. v0.1.0 미배포 상태.

이제 graphify 가 wikihub 의 3개 playbook (`_system/commands/{query,lint,ingest}.md`) 에서 어떻게 활용되는지 검토 — 격차 식별 + cleanup 후보 + v0.2.x 트리거 후보 분류.

## 현재 활용 매트릭스

| playbook | graphify 사용 위치 | 활용도 |
|---|---|---|
| query.md | Step 1 (검색 자원 detect), Step 2 (1-hop 인접 enumerate) | 중간 — graph.json + GRAPH_REPORT.md 둘 다 활용 |
| lint.md | Step 3 (고아 페이지 detection), **Step 9 (사이클 마지막 graphify 자동 호출)** | 중간 — graphify 의 단일 trigger 진입점 |
| ingest.md | **사용 안 함** | 없음 |

## 발견된 격차

### query.md
1. Leiden community detection 미활용 (graphify 가 제공 — 검색 그룹화 가능).
2. Bridge nodes (cluster 간 핵심 자료) 미활용.
3. god nodes / high-centrality 단순 활용 (20 초과 시 우선만).
4. graphify CLI 의 query subcommand 직접 호출 패턴 검토 안 됨.

### lint.md
1. Step 9 호출 순서 정합 OK (Step 3·4 stub 생성 후 graphify rebuild).
2. **Pass 3 non-deterministic churn** 이 lint report 의 "graph rebuilt: N nodes, M edges" 사이클 간 drift 일으킬 가능성 — ADR-0036 §D4 정합 §Note 부재.
3. community / god node 변동 추적 미수행.
4. graphify 결과 자체 검증 (노드 수 vs wiki page 수) 부재 — Pass 3 부분 실패 감지 불가.

### ingest.md
1. graphify 무관 — 새 source 가 graph 에 반영되기까지 최대 24h 지연 (lint timer 주기).
2. Trade-off 옵션:
   - (A) ingest 후 graphify --update 즉시 호출 — Pass 3 cost 매 sync.
   - **(B) 현재** (lint timer 만) — cost 통제 + 24h latency.
   - (C) `changed_count > threshold` 시만 graphify --update — adaptive.
3. v0.1.0 default (B) 정합 (ADR-0036 §D6 timer 통제 정합).
4. ingest 가 vault 별 `log.md` append — graphify 가 본 파일 entity 분석 대상으로 보면 noise. `.graphifyignore` 에 `**/log.md` 추가 검토 가치.

## 즉시 fix 후보 (v0.1.3 cleanup window 내)

| # | 항목 | 변경 위치 |
|---|---|---|
| 1 | `.graphifyignore` 에 `**/log.md` + `**/_lint/report.md` 추가 | `_system/templates/wiki/.graphifyignore` |
| 2 | lint.md Step 9 §Note — Pass 3 churn 인지 + N/M drift 정상 명시 | `_system/commands/lint.md` |
| 3 | ingest.md 에 graphify 미사용 §Note 추가 (lint chain 책임 + v0.2.x 트리거 환기) | `_system/commands/ingest.md` |
| 4 | query.md Step 1 §Note — Leiden community / bridge / centrality 활용은 v0.2.x | `_system/commands/query.md` |

## v0.2.x 검토 트리거

| 항목 | 발의 조건 |
|---|---|
| query 의 Leiden community / bridge node 활용 | 실 운영 query 응답 품질 데이터 surface 후 |
| ingest 의 adaptive `--update` (옵션 C) | source 갱신 후 query latency 가 사용자 불편으로 surface |
| lint 의 community / god node 변동 추적 | 운영 데이터 수개월 후 변동 패턴 진단 가치 surface |
| graphify CLI query subcommand 직접 호출 | graphify CLI 의 query 기능 release status 확인 후 |

## 리뷰 요청

본 분석의 (1) 격차 식별 적정성, (2) 즉시 fix 4건의 정당성 + 누락 / 과잉, (3) v0.2.x 트리거 분류 정합성, (4) Karpathy §2 Simplicity First 위반 여부 (즉시 fix 가 over-engineering 인지) 평가.
