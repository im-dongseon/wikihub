# Analysis & Design — monitor_services_remove

approved: 2026-05-26

**Date:** 2026-05-26
**Feat ID:** monitor_services_remove
**Plan:** [plan.md](plan.md)

---

## 분석

### 배경 및 목적

v0.1.5 (ADR-0037 §D2) 에 도입된 `wikihub-pending-monitor` (pending_ingest.json age 검사) 와 v0.1.8 에 추가된 `wikihub-monitor` (12hr 운영 보고서) 두 systemd unit 을 폐기한다.

**사유 (사용자 결정 — 운영 부담 대비 효익 부족, Karpathy §2 Simplicity)**:
- 두 unit 모두 `ops-alert.service` (ADR-0024 fatal alert contract) 와 별도의 surface layer. 운영 6주차 시점에 두 layer 의 추가 surface 가 ops-alert 가 못 잡는 결함을 실제로 잡았다는 evidence 부재.
- `wikihub-monitor` 는 12hr 보고서를 매일 09:00/21:00 KST 2회 발송 — 운영자 noise 증가 + bootstrap fail (exit 2) 만 alert 발화하는 조건부 의미가 운영자에게 모호.
- `wikihub-pending-monitor` 는 30분 주기 pending age 검사 — ADR-0024 의 `OnFailure=ops-alert.service` (attempts ≥ max_attempts 시 발화) 와 surface 시점이 1h vs 50min 으로 큰 차이 없음. age-based 의 빠른 surface 효과가 가설 단계에 머무름.
- ops-alert (fatal contract) 만 유지 — ADR-0024 본의 정본 그대로.

### 현행 진단

| # | 파일 | 결함 / 변경 사유 | 근거 |
|---|---|---|---|
| 1 | `_system/systemd/wikihub-monitor.{service,timer}.template` (2) | 폐기 대상 unit template | 사용자 결정 |
| 2 | `_system/systemd/wikihub-pending-monitor.{service,timer}.template` (2) | 폐기 대상 unit template | 사용자 결정 |
| 3 | `scripts/wikihub_monitor.py` | 폐기 대상 unit 의 ExecStart 본체 | 사용자 결정 |
| 4 | `scripts/pending_monitor.py` | 폐기 대상 unit 의 ExecStart 본체 | 사용자 결정 |
| 5 | `scripts/lib/telegram.py` | 호출자 2 → 1 (ops-alert.py 단독) 으로 축소 | Karpathy §2 Simplicity — single caller lib 회수 |
| 6 | `install.sh:1282` (banner status guide) | `pending monitor` 진단 명령 안내 stale | grep |
| 7 | `install.sh:1614-1617` (stop sequence) | pending-monitor + monitor stop 호출 stale | grep |
| 8 | `install.sh:1636-1637` (reset-failed) | reset 대상 stale | grep |
| 9 | `install.sh:1670-1673` (start sequence) | pending-monitor + monitor start 호출 stale | grep |
| 10 | `install.sh:1719` (try-restart) | try-restart 대상 stale | grep |
| 11 | `install.sh:745-748` (env template) | `TELEGRAM_MONITOR_BOT_TOKEN/CHAT_ID` 명명은 ops-alert (fatal) 단독 의미로는 부정확하나 운영자 env 무수정 보장 위해 **유지** | 결정 §1 |
| 12 | `wikihub.yaml.example:47-49` | `pending_alert_age_sec` + `monitor_enabled` 두 키 stale | grep |
| 13 | `scripts/lib/config.py:60-62, 167-169` | `OperationsConfig` 의 `pending_alert_age_sec` + `monitor_enabled` 두 필드 stale | grep |
| 14 | `_system/commands/setup.md:153, 168-171, 177, 305` | enable list / 보고 출력 예시 stale | grep |
| 15 | `_system/commands/lint.md:172` | "wikihub_monitor 보고서 read" 안내 stale | grep |
| 16 | `_system/commands/lint.md:222` | "`wikihub_monitor` 의 D1 정정 정신 정합" precedent reference — wikihub_monitor 소멸 후 의미 불성립 | grep |
| 17 | `_system/commands/graphify.md:14` | "`wikihub_monitor` 의 D1 정정 ... 같은 정신" precedent reference 동상 | grep |
| 18 | `docs/adr/0037-alert-pipeline-architecture.md` | Status: Accepted → Superseded. §D2 + 2026-05-25 wikihub_monitor follow-up 결정 폐기. §D1 (Telegram channel for ops-alert) 부분만 carry-over → ADR-NNNN | 결정 §3 |
| 19 | `docs/adr/0024-fatal-alert-contract.md:210` | "pending-monitor systemd unit 신설" 언급 historical 로 잔존 OK — 다만 ADR-0037 supersede 사실 짧게 추가 | review |
| 20 | `docs/adr/README.md:94` | ADR-0037 index entry Status 갱신 + 신규 ADR index entry 추가 | 결정 §3 |
| 21 | `scripts/_helpers/render_systemd_units.py:336-337` | dead `pass` 분기 — Phase B (rename defect cleanup) 항목 | review C6 |

### 개정 범위

- **Deletion 6**: template 4 + script 2 (`scripts/wikihub_monitor.py`, `scripts/pending_monitor.py`).
- **Inline 1**: `scripts/lib/telegram.py` → `scripts/ops-alert.py` (single caller 흡수).
- **Surgical edit**: `install.sh` 5개 위치 + `wikihub.yaml.example` 2 라인 + `lib/config.py` 5 라인 + `commands/*.md` 3 파일 + `docs/adr/0037` Status + ADR README index + 신규 ADR-0040.
- **Phase B 흡수**: `render_systemd_units.py:336-337` dead pass, GLM/Mimo 가 지적한 rename defect 잔존분.

> ADR 번호 — 기존 ADR-0037 → 0038 (graphify env namespace) → 0039 (entity-concept alias) 까지 존재. **신규 = ADR-0040**.

## 설계

### 개정 전/후 비교

#### Before (현행)

```
systemd units (deployment):
  wikihub-mount@<vid>.service     (always)
  wh-ingest@<vid>.{service,timer} (per-vault)
  wh-lint.{service,timer}         (singleton)
  wikihub-graphify.service        (oneshot, lint Step 9 trigger)
  wikihub-monitor.{service,timer}     ← 폐기
  wikihub-pending-monitor.{service,timer}   ← 폐기
  ops-alert.service               (OnFailure dispatcher)

scripts (ExecStart 본체):
  scripts/vault_fetch.py / vault_ingest.py / lint.py / wikihub_graphify.sh / ops-alert.py
  scripts/wikihub_monitor.py        ← 폐기
  scripts/pending_monitor.py        ← 폐기
  scripts/lib/telegram.py           ← inline 회수 (ops-alert.py 흡수)

env keys (~/.config/wikihub/env):
  TELEGRAM_MONITOR_BOT_TOKEN        (ops-alert 단독 사용으로 회귀 — 키 이름은 유지)
  TELEGRAM_MONITOR_CHAT_ID

yaml.example operations:
  pending_alert_age_sec: 3600       ← 삭제
  monitor_enabled: true             ← 삭제
```

#### After

```
systemd units:
  wikihub-mount@<vid>.service
  wh-ingest@<vid>.{service,timer}
  wh-lint.{service,timer}
  wikihub-graphify.service
  ops-alert.service                 (유일한 alert layer — ADR-0024 정본)

scripts:
  scripts/vault_fetch.py / vault_ingest.py / lint.py / wikihub_graphify.sh
  scripts/ops-alert.py              (telegram helper inline 흡수)

env keys: (불변 — 운영자 ~/.config/wikihub/env 무수정)
  TELEGRAM_MONITOR_BOT_TOKEN
  TELEGRAM_MONITOR_CHAT_ID

yaml.example operations:
  (pending_alert_age_sec / monitor_enabled 삭제 — 다른 키들 그대로)
```

### 결정 (Open Q resolution)

#### 결정 §1 — `TELEGRAM_MONITOR_*` env 키 처리

**채택**: 키 이름 유지 (`TELEGRAM_MONITOR_BOT_TOKEN/CHAT_ID`).

**이유**:
- 운영자 `~/.config/wikihub/env` 마이그레이션 부담 회피 (`install.sh` 는 env 파일을 rewrite 안 함 — operator secret 보존 규약).
- 키 이름은 라벨일 뿐 — ops-alert 단독 사용으로 회귀해도 기능 영향 0.
- 의미적 부정확성 (MONITOR 명명이 fatal alert layer 만 남은 상황에 맞지 않음) 은 install.sh env 템플릿의 주석 (`# Alert channel — Telegram bot`) 으로 충분히 커버.

**기각**: `TELEGRAM_ALERT_*` 로 rename — operator env 파일 수동 갱신 필요 (v0.1.8 의 MONITOR rename 때 surface 한 동일 부담).

#### 결정 §2 — `scripts/lib/telegram.py` 처리

**채택**: ops-alert.py 로 inline 회수. `scripts/lib/telegram.py` 삭제.

**이유**:
- 호출자가 ops-alert.py 단독 — 별도 lib 모듈의 추상화 비용이 효익 초과 (Karpathy §2 Simplicity).
- `parse_mode` 옵션화는 wikihub_monitor 대응으로 도입된 것 — wikihub_monitor 소멸 후 ops-alert 만 `parse_mode="HTML"` 사용 → 옵션 자체 불요.
- `scripts/lib/` 디렉토리 자체는 보존 (`config.py` 등 다른 모듈 존재).

**기각**: lib 그대로 유지 — 단일 caller lib 는 navigation 비용만 발생.

#### 결정 §3 — ADR Status 처리

**채택**: ADR-0037 전체 Status: Accepted → Superseded. 신규 ADR-0040 신설.

ADR-0040 내용:
- **Decision**: ADR-0037 §D2 (pending-monitor systemd unit) + 2026-05-25 wikihub_monitor follow-up 폐기.
- **Carry-over**: ADR-0037 §D1 (Telegram channel for ops-alert), §D4 (env file pattern), §D5 (ADR-0024 cross-reference) 의 결정 본의는 ADR-0040 §"Carry-over from ADR-0037" 섹션으로 명시 포함 — ops-alert.service 의 Telegram 발송 + `EnvironmentFile=-%h/.config/wikihub/env` + ADR-0024 complement 관계는 그대로 유지.
- **Supersedes**: ADR-0037.

ADR-0024:
- §210 의 ADR-0037 cross-reference 줄 뒤에 1줄 추가 — "2026-05-26 (ADR-0040): ADR-0037 §D2 + wikihub_monitor follow-up 폐기. ops-alert.service 의 Telegram channel + EnvironmentFile= 만 ADR-0040 으로 carry-over."
- 본문 (contract 의무) 미수정.

ADR README index:
- ADR-0037 entry Status: Accepted → Superseded by ADR-0040.
- 신규 ADR-0040 entry 추가.

**이유**:
- CLAUDE.md §1 + ADR convention — "결정 변경 시 기존 ADR Status를 Superseded → 신규 ADR".
- ADR-0037 §D1 만 carry-over 하는 partial supersede 도 가능하나, §D2/D4/follow-up 의 결정이 ADR-0037 전체에 산재해 partial 표기가 reader confusion 유발 — 전체 supersede + carry-over 명시가 정공법.

### 연계 룰/스킬 정합성 검토

| 룰/스킬 | 영향 | 처리 |
|---|---|---|
| ADR-0024 (fatal alert contract) | dispatch architecture supersede chain 갱신만 | §210 1줄 add |
| ADR-0032 (Hermes skill registration) | `terminal.env_passthrough` 의 TELEGRAM env 통과 — 변경 없음 (키 이름 유지) | 무영향 |
| ADR-0035 (rclone-only unified) | 무관 | 무영향 |
| ADR-0036 (graphify CLI) | `wikihub_monitor D1 정정` precedent reference 가 graphify.md 에 잔존 — historical analogy 였으나 monitor 소멸 후 reader 혼란 가능 | graphify.md L14 의 reference 짧게 정리 (e.g. "deterministic bash 작업의 LLM wrapping over-engineering 회피" 만 남김) |
| ADR-0038 (graphify env namespace) | 무관 | 무영향 |
| ADR-0039 (entity-concept alias) | 무관 | 무영향 |
| `_system/skills/wh-*.frontmatter.yaml` | monitor 관련 skill 부재 | 무영향 |

### 미결 사항

없음. 3 Open Q 모두 결정 완료.

### Definition of Done

- [ ] **D1 — Deletion**: template 4 + script 2 + lib 1 = 총 7 파일 삭제 (`git status` 확인).
- [ ] **D2 — install.sh**: monitor / pending-monitor / pending_monitor / wikihub_monitor 참조 0건 (`grep -c` 검증). banner / stop / reset-failed / start / try-restart 5 위치 일관성.
- [ ] **D3 — yaml + config**: `wikihub.yaml.example` 의 `pending_alert_age_sec` + `monitor_enabled` 2 키 삭제. `scripts/lib/config.py` 의 `OperationsConfig` 두 필드 + `_parse_operations` 두 line 삭제.
- [ ] **D4 — ops-alert.py inline**: `scripts/lib/telegram.py` 의 `send_telegram` + `format_telegram_alert_message` 회수. parse_mode 옵션 제거 (HTML 고정). import 경로 정리.
- [ ] **D5 — commands docs**: setup.md / lint.md / graphify.md 의 monitor 언급 정리. lint Step 9 의 `wikihub_monitor D1 정정` precedent reference 정리.
- [ ] **D6 — ADR**: 신규 ADR-0040 신설 (Accepted, Supersedes ADR-0037). ADR-0037 Status: Superseded by ADR-0040. ADR-0024 §210 1줄 add. docs/adr/README.md index 갱신.
- [ ] **D7 — Phase B 흡수**: `render_systemd_units.py` dead pass 정리 + GLM/Mimo 지적 rename 흔적 6건 중 잔존분 (Phase A 후 grep 재실행으로 확정) 정리.
- [ ] **D8 — Verify**: `render_systemd_units.py` dry-run 출력에 monitor 부재 확인. `pytest` 통과. `grep -rn 'wikihub-monitor\|wikihub-pending-monitor\|wikihub_monitor\|pending_monitor\|pending_alert_age_sec\|monitor_enabled' install.sh _system scripts docs/adr | wc -l` 결과 0 (또는 ADR historical 언급만).
- [ ] **D9 — Code Review**: ≥ 2개 멀티모델 리뷰 (Step 4) — `features/20260526_monitor_services_remove/code_review_N.md`.

## 작업 시퀀싱

Phase A → Phase B 순. Phase A 가 같은 파일들을 touch 하므로 Phase B 의 4건 잔존분 중 일부 (lint.md L222 / graphify.md L14 등) 가 Phase A 의 D5 와 같은 commit 으로 흡수됨. 잔존 Phase B 작업 = `render_systemd_units.py:336-337` dead pass 단일 1건이면 Phase A commit 에 흡수, 2건 이상이면 별도 commit.

## 참조

- [plan.md](plan.md)
- [docs/adr/0037-alert-pipeline-architecture.md](../../docs/adr/0037-alert-pipeline-architecture.md)
- [docs/adr/0024-fatal-alert-contract.md](../../docs/adr/0024-fatal-alert-contract.md)
- [code_review_glm-5.1.md](../20260526_systemd_prefix_realign/code_review_glm-5.1.md)
- [code_review_mimo-v2.5-pro.md](../20260526_systemd_prefix_realign/code_review_mimo-v2.5-pro.md)

---

## v2 (2026-05-26, code_review_1 + code_review_2 반영)

approved: 2026-05-26

Step 4 멀티모델 리뷰 (code_review_1 — runtime correctness focus, code_review_2 — consistency + methodology focus) 결과 3 Critical + 5 Medium 결함 surface. 본 §v2 가 §개정 범위 + §DoD 보강.

### v1 결함 — §개정 범위 누락

원본 §"개정 범위" 표 (rows 6-21) 가 `_system/systemd/ops-alert.service` (file, not template) 와 `README.md` (top-level public-facing) 를 포함 안 함. 두 파일 모두 monitor / ADR-0037 § 잔존 참조 보유 → 운영자 visible 결함.

### v2 추가 변경

| # | 파일 | 변경 | 출처 |
|---|---|---|---|
| 22 | `_system/systemd/ops-alert.service:17-18` | ADR-0037 §D1 → ADR-0040 (carry-over of ADR-0037 §D1). `TELEGRAM_ALERT_*` → `TELEGRAM_MONITOR_*` (operator visible env key 정합) | review_2 C1 |
| 23 | `README.md:160` | `wikihub-monitor (v0.1.8)` 운영 항목 1줄 삭제 (`monitor_enabled` yaml 필드 인용 포함) | review_2 C2 |
| 24 | `README.md:19` | 버전 highlight 의 `wikihub-monitor (v0.1.8)` 항목 제거 + ADR-0040 supersede narrative 1줄 add ("monitor unit 은 ADR-0040 으로 폐기, Telegram channel 만 ops-alert 로 carry-over") | review_2 C2 (lower) |
| 25 | `docs/adr/0032-hermes-skill-registration-policy.md` (L248, L264, L299) | `operations.pending_alert_age_sec` 예시 인용 정리 — L248: `graphify_timeout_sec` 로 1-token 치환. L264: Group B catalog 항목 삭제 + 본 ADR-0040 cross-reference 1줄 add. L299: Cross-references 의 ADR-0037 → ADR-0040 갱신 | review_1 M1 + review_2 M2 |
| 26 | `docs/adr/0040-monitor-services-remove.md` (Carry-over 표) | §D2 (wikihub-pending-monitor systemd unit) 폐기 row 명시 추가. §D3 row 에 ADR-0032 §Note Group B catalog 자연 제거 1줄 add | review_2 M3 |
| 27 | `docs/adr/0040-monitor-services-remove.md:89` | "기존 v0.1.9 instance" 부정확 표현 정정 — "monitor unit 이 enable 된 기존 instance (v0.1.5 ~ v0.1.8 + v0.1.9 canary)". service / timer 의 stop·disable 동작 분리 명시 | review_2 M1 + review_1 L2 |
| 28 | `docs/adr/0040-monitor-services-remove.md` §"후속 영향" | 4 항목 추가 — renderer legacy_singletons / ops-alert.service 주석 갱신 / README 갱신 / ADR-0032 §Note 갱신 (review 작업 자체의 visibility 회복) | review_2 |
| 29 | `features/backlog.md:114-119` | ADR-0040 에 의해 자연 무효된 backlog 항목 5건 (BL-N1, N2, N3, N4) closed 표기 + BL-N5/N6 의 monitor 언급 부분 정리 | review_2 M4 |

### v2 DoD 추가

- [ ] **D10 — Step 5 HISTORY.md append**: squash 시점에 `features/HISTORY.md` 에 본 feature 항목 추가 — format 정합 (목적 / 로직 / 생성 ADR: ADR-0040 / 트레이드오프 / 결론 / 참조: `features/archive/20260526_monitor_services_remove/`). CLAUDE.md §3 Step 5 HISTORY.md 항목 형식 준수. 본 항목은 implementation 단계가 아닌 deploy 단계에서 수행 — recurring slippage 회피 위해 DoD 명시. | review_2 C3 |

### v1 결함 — §개정 범위 표 wording 정확성

- v1 §개정 범위 row 12 ("`wikihub.yaml.example:47-49` ... `pending_alert_age_sec` + `monitor_enabled` **두 키**") 가 실제 삭제 4 키 (`pending_alert_age_sec` + `monitor_enabled` + `monitor_report_vault` + `monitor_report_subpath`) 대비 undercounting. 본 §v2 정정 노트 — implementation 자체는 4 키 모두 삭제 정확 (config.py + yaml.example 둘 다 정합). | review_1 D3
- v1 §DoD D2 ("monitor 참조 0건") 가 intentional carry-over (install.sh upgrade migration block + env template historical comment + renderer legacy_singletons catalog) 미반영. 본 §v2 정정 — "활성 monitor 참조 0건 + intentional historical/migration 참조는 명시적 보존". `grep` 검증 시 정의된 의도된 hit 8건 (install.sh 4 + renderer 4) 은 통과. | review_2 M5

### Open Q (v2 단계에서 결정)

없음. 모든 review 결함이 surgical edit 으로 해소.
