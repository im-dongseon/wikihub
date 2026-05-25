# Plan — wikihub_monitor

작성일: 2026-05-25 (KST)
작업자: wikihub maintainer

## 1. 작업 분류

**기능 (신규 Python 스크립트 + systemd timer)** — `scripts/wikihub_monitor.py` (정적 보고서 생성) + systemd timer (OnCalendar 09:00/21:00 KST) + 12hr 윈도우 journal 파싱 + 텔레그램 발송 + 보고서 파일 저장 (vault 안). ※ D1 정정 후 분류 (D1 history: Hermes 스킬 → Python 직접).

## 2. 타겟 버전 브랜치

**v0.1.8** — 현재 v0.1.8 누적 path 의 5번째 feature. release batch 전 함께 묶음.

- 작업 브랜치: `feature/wikihub_monitor` (from `origin/v0.1.8`, 분기 완료)
- 새 메소드론(branch_strategy_formalize) 첫 본격 적용 — `feature/<id>` 브랜치 분기 + Step 5 squash 흐름

## 3. 적용 단계 선언

| 단계 | 수행 여부 | 사유 |
|---|---|---|
| Step 2 Design | **수행** | 신규 스킬 + systemd template + install.sh render 변경 다수 영역 — 정합성 보장 필요 |
| Step 2 Design Review | **수행** (멀티 리뷰어) | LLM token cost / 보고서 포맷 / TZ 처리 등 결정 다수 |
| Step 3 Implementation | **수행** | _system/commands/monitor.md 신설 + scripts/ helper + systemd template + install.sh render |
| Step 4 Code Review | **수행** (멀티 리뷰어) | 신규 systemd unit + LLM cost gating + telegram failure handling 검증 |
| Step 5 Deployment | **수행** | _system/ 변경 → 5 액션 git workflow (squash → v0.1.8 + canary force-update) |

## 4. 예상 영향 범위 (D1 정정 반영)

| 영역 | 변경 성격 | 예상 라인 |
|---|---|---|
| ~~`_system/commands/monitor.md`~~ | **삭제 (D1 정정)** — Hermes 스킬 안 만듦. Python 직접 호출. | — |
| `_system/systemd/wikihub-monitor.service.template` | 신규 — oneshot, EnvironmentFile, ExecStart=python wikihub_monitor.py | +25 |
| `_system/systemd/wikihub-monitor.timer.template` | 신규 — OnCalendar 09,21:00 Asia/Seoul, Persistent=true | +15 |
| `scripts/wikihub_monitor.py` | 신규 — journalctl 직접 파싱 + 정적 보고서 생성 + telegram 발송 (전 흐름 self-contained) | +200~250 |
| `scripts/lib/telegram.py` (가칭) | 신규 — ops-alert.py 의 send_telegram 추출 + 공용화 (Step 2 에서 분리/재사용 결정) | +30 |
| `install.sh` `_step8_systemd_render` 영역 | 변경 — wikihub-monitor.{service,timer} render + enable | +10 |
| `scripts/render_systemd_units.py` | 변경 — monitor unit render (substitution 없이 단순 path 보간만) | +20 |
| `wikihub.yaml.example` | 변경 — `operations.monitor_enabled: true` default 추가 | +3 |
| `ADR-0037` (텔레그램 alert channel) | §"후속 영향" 1 줄 cross-link (wikihub_monitor 가 같은 env 키 재사용) | +2 |

총: +300~350 / -0 (신규 위주). D1 정정으로 Hermes 스킬 spec 150~200 줄 절감 + Python 본체로 50~100 줄 흡수.

## 5. 메소드론 적용 여부

본 절차 적용 — 신규 feature 이고 trivial 아님.

## 6. 사용자 결정 (이미 확정)

| ID | 항목 | 결정 |
|---|---|---|
| D1 | 구현 방식 | **Python 직접** (`scripts/wikihub_monitor.py`) — 정적 보고서 생성. 사용자 재검토 2026-05-25: ops-alert.py + ingest/lint/graphify 의 결정적 report 패턴 정합, LLM token cost 0, 디버깅 쉬움. ※ 초기 결정 = Hermes 스킬 + LLM 요약 → 사용자 의견 검토 후 정정 |
| D2 | 텔레그램 env | **기존 `TELEGRAM_ALERT_BOT_TOKEN` + `TELEGRAM_ALERT_CHAT_ID` 재사용** (ADR-0037 정합) |
| D3 | scope | **wh-ingest + wh-lint 만**. wh-graphify 는 wh-lint Step 9 chain 으로 호출되므로 wh-lint 보고서에 graphify 결과 포함 표시 |
| D4 | 타겟 버전 | **v0.1.8 누적** (default) |

### D3 코드베이스 검증 (2026-05-25, 사용자 요청)

| 검증 항목 | 출처 | 결과 |
|---|---|---|
| `_system/systemd/` 에 graphify unit 존재 | `ls _system/systemd/` | 부재 — graphify 독립 systemd timer 없음 |
| ingest.md 가 graphify 호출 여부 | `_system/commands/ingest.md:205` | 부재 — "graphify rebuild = /wh-lint Step 9 chain, ADR-0036 §D6" 명시 |
| lint.md Step 9 graphify chain | `_system/commands/lint.md:162-183` | 확인 — `<agent_invocation> "/wh-graphify"` |
| graphify_enabled default | `wikihub.yaml.example:37`, `install.sh:892` | `true` — false 시 lint Step 9 skip (운영자 cost toggle) |
| render_systemd_units.py 의 wh-graphify | line 141 `_WIKIHUB_SKILLS` | Hermes SKILL.md materialize 대상만 — systemd unit 생성 안 함 |

**결론**: graphify 는 wh-lint Step 9 chain 으로만 호출되는 single-source design (ADR-0036 §D6). `wikihub-lint.service` journal 에 lint + graphify 결과가 함께 기록됨. monitor 수집 단위:

| Service | journal SyslogIdentifier | 포함 결과 |
|---|---|---|
| `wikihub-vault@*` (ingest, 1 instance per vault) | `wikihub-vault-{vid}` | ingest 만 |
| `wikihub-lint.service` (lint + graphify chain) | `wikihub-lint` | lint + graphify (chain) |

운영자 yaml 의 `operations.graphify_enabled: false` 케이스: lint journal 에 "graphify chain skipped (yaml toggle)" 1줄만 기록됨. monitor 가 이를 surface (보고서에 "graphify 스킵됨" 명시).

## 7. 미결 사항 (Step 2 에서 결정)

| ID | 미결 사항 |
|---|---|
| Q1 | timer 구현 — `OnCalendar=*-*-* 09,21:00:00 Asia/Seoul` 단일 timer vs morning/evening 분리. 전자가 단순, 후자는 윈도우 인자 차별화 명시 가능 |
| Q2 | 시간대 처리 — systemd OnCalendar 의 TZ suffix (`Asia/Seoul`) vs service `Environment=TZ=Asia/Seoul`. systemd 242+ 에서 OnCalendar TZ suffix 지원 |
| Q3 | journal 수집 구현 — (a) `scripts/wikihub_monitor.py` 가 journalctl 수집 → JSON 출력 → Hermes 가 요약 (b) monitor.md 의 LLM 이 직접 bash 로 journalctl 호출 (a 가 결정적 데이터 + LLM token 절약, b 가 단순) |
| Q4 | 윈도우 정의 — (a) `journalctl --since "12 hours ago"` 단순화 (b) timer fire 시점 별 정확 윈도우 계산 (09:00 fire = 전날 21:00 ~ 09:00, 21:00 fire = 당일 09:00 ~ 21:00). (a) 가 정합 충분 (timer 가 정확히 12h 간격) |
| Q5 | 보고서 포맷 — (a) plain text (ops-alert.py 와 정합, Telegram parse_mode 없음) (b) MarkdownV2 (구조화 표시 풍부, escape 처리 비용) |
| Q6 | LLM 비용 가드 — journal 출력이 12hr 누적이면 길어질 수 있음. token 사전 truncation/sampling 정책 필요 여부 |
| Q7 | 환경변수 부재 시 동작 — (a) skip + warn (no-op, journal log) (b) fail-fast (exit 1, ops-alert 발화) |
| Q8 | wikihub.yaml toggle — `operations.monitor_enabled: true` default 추가 vs install.sh 가 무조건 enable. yaml toggle 이 운영자 friendly |

## 8. Definition of Done (Plan)

- [ ] `_system/commands/monitor.md` 작성 — Hermes 스킬 spec, 한국어 보고서 출력, telegram 발송
- [ ] `_system/systemd/wikihub-monitor.{service,timer}.template` 작성 — OnCalendar 09,21:00 KST
- [ ] `scripts/wikihub_monitor.py` 또는 monitor.md 내장 bash (Q3 결정)
- [ ] `scripts/lib/telegram.py` 공용 helper (선택, ops-alert.py 와 의존 분리)
- [ ] `install.sh` + `render_systemd_units.py` substitution + render + enable 흐름 추가
- [ ] `wikihub.yaml.example` 에 `operations.monitor_enabled` toggle (Q8 결정 시)
- [ ] V 검증: VM 또는 OCI 에서 monitor.service 1회 ad-hoc trigger (`systemctl --user start wikihub-monitor`) → 보고서 텔레그램 수신 확인
- [ ] Step 4 멀티 리뷰어 통과
- [ ] Step 5 5 액션 squash → v0.1.8 → canary force-update
- [ ] Feature 종료 archive 이동

## 9. ADR 신설 여부

기존 ADR 과의 관계:
- ADR-0037 (텔레그램 alert channel) — 본 feature 가 같은 env 키 재사용. 신설 ADR 불필요, ADR-0037 §"후속 영향" 에 1 줄 cross-link 권장
- ADR-0023 (sparse-checkout) — `WIKIHUB_SPARSE_PATHS` 에 신규 scripts 추가 시 영향. 본 변경은 scripts/ 하위 새 파일 추가만 — sparse 가 디렉토리 단위라 자동 포함됨, 변경 불요

**Step 2 에서 재확인**: ADR 신설 필요 여부 (timer KST 정책 / LLM cost gating 등이 별도 결정 가치 있다면 ADR-NNNN 발급).
