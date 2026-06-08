# Plan — lint_operations_improvements

작성일: 2026-05-25 (KST)
작업자: wikihub maintainer

## 1. 작업 분류

**운영 (operational hardening) + 버그 (timeout 종료)** — wh-lint cycle 의 운영 안정성 개선 3건 통합:
- I1 timeout 종료 결함 진단/완화 + wh-ingest timeout 정책 검토
- I2 lint report 의 case-variant + cross-category duplicates 정책 결정 + 자동 처리
- I3 wh-lint `--apply` 자동 실행 패턴 (1일 1회)

## 2. 타겟 버전 브랜치

**v0.1.8** (default — 5번째 누적 feature). 본 feature 가 v0.1.8 release batch 의 마지막 후보. 사용자 의도 redirect 가능.

작업 브랜치: `feature/lint_operations_improvements` (from `origin/v0.1.8`, 분기 완료).

## 3. 사용자 흐름 명시 (2026-05-25)

| 단계 | 진행 방식 |
|---|---|
| Step 1 plan | **사용자 검토 필수** — 본 문서 미결 항목 결정 후 자동 진행 신호 |
| Step 2 design + Step 2.5 review | **자동 진행** |
| Step 3 implementation | **자동 진행** |
| Step 4 code review (멀티 리뷰어) | **자동 진행** |
| Step 5 squash → v0.1.8 | **사용자 승인 필수** — 검토 통과 후 squash + canary force-update |
| Feature 종료 archive | Step 5 직후 자동 |

## 4. 이슈별 분석

### I1. wh-lint 300초 timeout 종료 + wh-ingest timeout 검토

**현행 timeout 정책** (코드베이스 검증):

| 위치 | 값 | 영향 |
|---|---|---|
| `wikihub.yaml.operations.lint_interval_hours` | 3 | lint timer 주기 (v0.1.6 default) |
| `wikihub.yaml.agent.timeout_sec` | 1200 (20분) | systemd TimeoutStartSec sync source (ADR-0032 §sub-4, v0.1.5 default 600→1200 DeepSeek 대응) |
| `lint.service.template:20` `TimeoutStartSec={timeout_start_sec}sec` | render 시 yaml 값 보간 | lint.service 전체 timeout |
| `lint.md:183` `timeout 300 graphify` wrapper | 300초 (5분) | graphify chain 만 |
| 운영자 보고 사례 | "wh-lint 300초 timeout 종료" | 진단 필요 |

**진단 미결 (Step 2 에서 결정)**:
- Q1-a: 운영자 보고의 300초 종료가 (i) graphify wrapper hit (정상 — lint 본체 계속) 인지 (ii) lint 본체 hang 인지 (iii) 다른 source (Hermes / LLM call) 인지 확인. 사용자 lint report 첨부 또는 journalctl 분석 필요.
- Q1-b: graphify timeout 300 wrapper 가 적절한지 — wiki 규모 누적 + LLM backend latency 의존. 늘리거나 yaml toggle 화 검토.
- Q1-c: wh-ingest timeout — vault@.service 의 TimeoutStartSec = `agent.timeout_sec` = 1200 그대로 적용. ingest 가 graphify 같은 별도 sub-timeout 없음. 보강 필요한지 검토.

**가설 (Step 2 분석)**:
- 사용자 lint report 의 마지막 line 이 `graph rebuild timeout` 이면 (i) 정상 (graphify wrapper hit, lint 본체 계속). 본 feature 가 timeout 늘리거나 yaml toggle 추가.
- lint 본체 hang 이면 (ii) Hermes agent 의 LLM 호출 timeout. agent.timeout_sec 가 1200 인데도 300 에서 종료? 운영자 yaml 의 실제 값 확인 필요.

### I2. lint report 의 duplicate 이슈

**보고된 결함**:
- **case-variant duplicates 7건**: `Claude-Code` / `claude-code`, `Cloudflare` / `cloudflare`, `Obsidian` / `obsidian` 등 — entity 이름의 대소문자만 다름
- **cross-category duplicates 20건**: 동일 이름이 entity 와 concept 양쪽에 존재 (`Docker`, `DeepSeek`, `Graphify`, `Telegram` 등)

**현행 lint 동작** (lint.md 검증):
- Step 4-5 의 entity/concept linkage 검증 + Step 6 의 dangling links — duplicate detection 없음
- Step 8 (`_lint/report.md`) — 본 7+20 건은 lint 가 **현재 감지 안 함**. 사용자가 별도 관찰 후 보고

**미결 항목** (Step 2):
- Q2-a: lint 가 duplicate 를 감지하도록 spec 보강 (Step 4-5 또는 신규 Step) — 필요?
- Q2-b: case normalization 정책 — (i) 모두 lowercase, (ii) 모두 kebab-case, (iii) 운영자 정의 alias map, (iv) 첫 등장 form 보존
- Q2-c: cross-category 정책 — (i) entity 우선 (concept 삭제 또는 merge), (ii) concept 우선, (iii) 운영자 결정 (lint 가 보고만)
- Q2-d: `--apply` 가 자동 처리 vs 보고만 — 위험도 분석. duplicate merge 는 정보 손실 가능 (link reference 갱신 + 본문 merge 필요)
- Q2-e: 본 feature 의 범위 — (i) detection 만 (Step 8 보고 항목 추가), (ii) detection + 정책 결정 + `--apply` 자동 처리, (iii) 별도 feature 분리

### I3. `--apply` 자동 실행 1일 1회

**현행 lint 동작**:
- default `wh-lint` (no flag) = 진단만, report.md 작성
- `wh-lint --apply` = 메인테이너 수동 호출 (lint.md:13 + line 125 — 일괄 적용, interactive 없음)
- lint.timer 가 3h 주기 fire — `wh-lint` (no flag) 만 실행

**제안**:
- 신규 systemd timer `wikihub-lint-apply.timer` — 1일 1회 (예: 매일 03:00 KST)
- ExecStart: `<agent_invocation> "/wh-lint --apply"`
- 또는 기존 lint.timer 에 day-of-week / hour-of-day gate 추가

**미결 항목** (Step 2):
- Q3-a: 별도 timer (`wikihub-lint-apply.{service,timer}`) vs 기존 lint.timer 의 cron-like gate
- Q3-b: fire 시각 — 03:00 KST (조용한 시간) vs 다른 시점
- Q3-c: `--apply` 의 위험 작업 (lint.md:114 "정보 손실 가능") — 자동화 시 운영자가 모르는 사이 wiki 변경. 안전망:
  - (i) 그대로 자동화 (운영자가 wikihub.yaml toggle `operations.lint_auto_apply: true` 명시 동의)
  - (ii) 안전 subset 만 자동화 (dangling links 만, 또는 archive 이동만)
  - (iii) `--apply --dry-run` 으로 변경 사항 미리 텔레그램 발송 후 운영자가 manual `--apply` 트리거
- Q3-d: yaml toggle 위치 — `operations.lint_auto_apply: true/false` (default false 운영자 명시 opt-in)
- Q3-e: wikihub_monitor 의 보고서에 lint --apply 자동 실행 결과 surface 여부

## 5. 적용 단계 선언

| 단계 | 수행 여부 | 사유 |
|---|---|---|
| Step 2 Design | **수행** | 3 이슈 통합 + 미결 다수 — 정합성 확보 필요 |
| Step 2 Design Review | **수행** (멀티 리뷰어) | 자동 `--apply` 의 운영 위험도 / duplicate merge 정책 / timeout 정책 각각 별도 리뷰 가치 |
| Step 3 Implementation | **수행** | lint.md spec 보강 + systemd timer 신규 + install.sh 변경 + wikihub_monitor.py 영향 검토 |
| Step 4 Code Review | **수행** (멀티 리뷰어) | lint.md spec drift 정합 / systemd unit 정확성 / yaml toggle ADR 정합 |
| Step 5 Deployment | **수행** | _system/commands/lint.md 변경 → squash → v0.1.8 → canary force-update |

## 6. 예상 영향 범위 (초안 — Step 2 에서 정밀화)

| 영역 | 변경 성격 | 예상 라인 |
|---|---|---|
| `_system/commands/lint.md` (I1+I2+I3) | spec 보강 — duplicate detection step + `--apply` 자동 모드 + timeout 정책 | +50~80 |
| `_system/systemd/wikihub-lint-apply.{service,timer}.template` (I3, 신설) | 일일 자동 apply | +40 |
| `scripts/render_systemd_units.py` (I1, render 변경) | glob 자동 발견 → 변경 0 (branch_strategy_formalize 정합) | 0 |
| `wikihub.yaml.example` (I1+I3) | `operations.lint_auto_apply`, `operations.graphify_timeout_sec` 등 | +5~10 |
| `scripts/lib/config.py` (yaml toggle field) | OperationsConfig 갱신 | +3~5 |
| `install.sh` `_migrate_agent_schema` (yaml drift) | Group B 신규 flag | +10 |
| `install.sh` systemd 3 위치 (stop/start/try-restart) | wikihub-lint-apply 추가 | +5 |
| `scripts/wikihub_monitor.py` (I2/I3 결과 surface) | duplicate count + lint-apply timer 결과 보고 | +20~40 |

**총 추정: +130~190 / -minimal**

## 7. 사용자 검토 결정 (2026-05-25 confirmed)

| ID | 결정 | 출처 |
|---|---|---|
| **D1** feature scope | **단일 feature** (3 이슈 통합) | 사용자 명시 |
| **D2** I2 duplicate 처리 | **detection + auto-normalize** — case-variant 는 **alias frontmatter 인식** 으로 무한 loop 회피, cross-category 는 entity 우선 merge | 사용자 명시 + Step 2.5 reviewer C2 흡수 정정 (2026-05-25): lowercase 강제가 product noun (MiniMax, DeepSeek 등) case 손상 + LLM 재생성 cycle 무한 loop 위험 → wiki-schema frontmatter 에 aliases 도입 |
| **D3** I3 --apply 자동화 안전망 | **yaml opt-in (전체 자동)** — `operations.lint_auto_apply: true` (default false). 활성화 시 매일 1회 contradiction 포함 모든 --apply 작업 자동 실행 | 사용자 명시 정정 (2026-05-25): wikihub 데이터 모델상 `wiki/` 는 sources (vault, immutable) 의 LLM derivative — contradiction reword 도 LLM 이 자기 생성 페이지 자기 갱신, 원본 변경 0. 위험 낮음. default false 는 운영자 opt-in 안전망 유지 |
| **D4** I1 timeout 정책 | **graphify timeout 300 → 900 (15분)** — yaml toggle `operations.graphify_timeout_sec` 신설, default 900 | 사용자 명시 ("timeout 시간 15분 지정") |
| **D5** 타겟 버전 브랜치 | **v0.1.8 누적** | 사용자 명시 |
| **Q1-a** I1 timeout 진단 자료원 | graphify 900 채택 (추정 기반 — graphify wrapper hit). wh-ingest agent.timeout_sec=1200 유지 (충분 가정). 운영자 실제 lint report 첨부 시 재진단 | default |
| **Q2-b** case normalization 규칙 | **모두 lowercase** — URL-friendly, filesystem stable, 운영자 멘탈 부담 낮음 | default |
| **Q2-c** cross-category 정책 | **entity 우선 merge** — concept 의 referenced_by 가 entity 로 병합. D2 auto-normalize 정합. 정보 손실 위험 surface (보고서 명시) | default, entity 가 일반적으로 더 구체적 의미 보존 |

> 위 default 중 사용자 redirect 원하는 항목 있으면 Step 2 진입 전 명시. 미명시 시 Step 2~4 자동 진행.

## 8. Definition of Done (Plan 단계)

- [ ] 사용자 검토 통과 — D1~D5 결정 confirmed
- [ ] Step 2~4 자동 진행 후 design v? + 구현 + code review 흡수
- [ ] Step 5 squash merge 전 사용자 최종 검토 + 승인
- [ ] squash → v0.1.8 + canary force-update + feature 브랜치 정리
- [ ] Feature archive 이동

## 9. ADR 신설 여부 검토 (Step 2 에서 재확인)

- **D3 (--apply 자동화)** — wiki 변경의 자동화 정책 결정. ADR 가치 가능.
- **D2 (duplicate normalization 정책)** — case + cross-category 결정 정본. ADR 가치 가능.
- D1, D4, D5 — 운영 결정, ADR 미생성 가능.

> Step 2 분석 후 ADR-NNNN 신설 여부 확정.

## 10. Methodology 적용

본 절차 적용 — non-trivial multi-issue 통합 feature.
