# ADR-0037: Alert pipeline architecture — multi-channel dispatch + periodic monitor

- **Status**: Superseded
- **Date**: 2026-05-20
- **Feature**: features/archive/20260520_alert_pipeline_overhaul
- **Supersedes**: 없음 (ADR-0024 complement — fatal alert contract 는 그대로, dispatch architecture 만 확장)
- **Superseded by**: ADR-0040 (2026-05-26) — §D2 (wikihub-pending-monitor systemd unit) + 2026-05-25 wikihub_monitor follow-up 폐기. §D1 (Telegram channel for ops-alert) + §D4 (env file pattern) + §D5 (ADR-0024 cross-reference) 의 결정 본의는 ADR-0040 으로 carry-over (ops-alert 단독 운영).

## Context

ADR-0024 (fatal alert contract) 가 정의:
- **trigger**: systemd `OnFailure=ops-alert.service` (vault@/mount@/lint 의 모든 fail)
- **dispatch**: `scripts/ops-alert.py` 가 `_state/<vault>/last_failure.json` collect + `operations.fatal_webhook_url` POST
- **dedup**: `alerted_at` + `alerted_failed_count` (24h reminder)

v0.1.5 OCI 운영 (2026-05-20) 에서 두 한계 surface:

1. **single-channel dispatch**: webhook URL 만 지원. 운영자 일상 channel (Telegram bot) 이 default 가 아님. Hermes 가 OCI 측에서 ops-alert.py 패치로 Telegram 통합 + 발송 검증 완료.
2. **trigger layer 의 즉시성만 보유**: `OnFailure` 가 service fail 시 즉시 발화. 그러나 vault@.service 가 retry 사이클 안에서 attempts=1,2,3... 누적 중인 동안 (정상 분류) alert 부재. attempts ≥ max_attempts (5 cycle ≈ 50min) 도달 시점에만 fatal alert — surface 가 늦거나, monitor 가 cron 으로 별도 운영자 책임이었음 (Hermes 가 30분 cron 으로 pending file age 검사 검증).

## Considered Options

### O1. alert channel 확장 — Telegram 추가

- **(α1) webhook 만 유지** (ADR-0024 기존). Telegram 통합 안 함.
- **(β1) Telegram 추가 + webhook 병행** (둘 다 설정 시 둘 다 발송). — **채택**.
- (γ1) webhook 폐기, Telegram 만 — backward-compat 깸. 운영자 기존 webhook 설정 무효화.

### O2. age-based alert trigger 도입

- **(α2) attempts 기반만 유지** (ADR-0024 기존). pending stuck 의 빠른 surface 부재.
- **(β2) 별도 systemd timer + service 신설 (architectural)** — **채택**. wikihub-pending-monitor.timer (30분 주기) → pending_monitor.py → pending age 검사 → last_failure.json 갱신 → ops-alert.service 호출.
- (γ2) ops-alert.py 안에 age 검사 통합 — ops-alert 는 OnFailure trigger 기반이라 periodic 호출 불일치.
- (δ2) cron 으로 외부 처리 (운영자 책임) — Hermes 가 검증한 패턴이나 wikihub spec 외부 — 운영자 자유.

### O3. alert payload schema

- **(α3) ADR-0024 schema 유지** (vault_id / severity / scope / reason / remediation / first_failed_at / last_failed_at / failed_count) — **채택**. Telegram format 은 별도 함수가 HTML 변환.
- (β3) Telegram-specific schema 별도 정의 — 두 channel 분기 복잡도 증가.

### O4. Telegram secret 관리

- **(α4) `~/.config/wikihub/env` 의 env var** (`TELEGRAM_ALERT_BOT_TOKEN` + `TELEGRAM_ALERT_CHAT_ID`) — **채택**. ADR-0036 §D2 의 EnvironmentFile 패턴과 정합. ops-alert.service 에 `EnvironmentFile=-%h/.config/wikihub/env` 추가.
- (β4) yaml `operations.telegram.*` 안에 plain text — secret 을 yaml 에 두면 git tracking risk. 회피.
- (γ4) 별도 secret 파일 — 새 layer 추가 = over-engineering.

## Decision

**채택 조합**: (β1) Telegram + webhook 병행 + (β2) 별도 monitor systemd unit + (α3) schema 유지 + (α4) env var.

### D1. Telegram channel (`ops-alert.py` 갱신)

- `send_telegram(bot_token, chat_id, text, timeout_sec=10)` — Telegram bot API POST, HTML format.
- `format_telegram_message(instance, alerts)` — alert list 를 HTML message 로 변환.
- `main()` 의 dispatch 로직: webhook + Telegram 병행 (한쪽이라도 성공 시 alerted_at 갱신).
- env: `TELEGRAM_ALERT_BOT_TOKEN` + `TELEGRAM_ALERT_CHAT_ID`. 양쪽 미설정 + `fatal_webhook_url` 미설정 시 journal only (기존 behavior 유지).
- `_system/systemd/ops-alert.service` 에 `EnvironmentFile=-%h/.config/wikihub/env` 추가 (lenient prefix — 파일 부재 OK).

### D2. wikihub-pending-monitor systemd unit (architectural)

- `_system/systemd/wikihub-pending-monitor.{service,timer}.template` 신설.
- timer: `OnBootSec=10min`, `OnActiveSec=10min`, `OnUnitInactiveSec=30min` (lint.timer 패턴 차용 — ADR-0023/0030 정합).
- service: oneshot, `ExecStart=python scripts/pending_monitor.py`. `OnFailure` 미설정 — pending_monitor.py 가 항상 exit 0 + ops-alert recursion 회피 패턴.
- `scripts/pending_monitor.py`:
  1. yaml load → enabled vault 순회
  2. `$WIKIHUB_HOME/_state/<vault_id>/pending_ingest.json` mtime age 검사
  3. age > `operations.pending_alert_age_sec` (default 3600s = 1h) → 해당 vault 의 `last_failure.json` 갱신 (scope="ingest_pending") + `systemctl --user start ops-alert.service` 호출
  4. ops-alert.py 의 dedup mechanism (alerted_failed_count + 24h reminder) 가 자연 적용

### D3. yaml schema

```yaml
operations:
  pending_alert_age_sec: 3600    # default 1h. vault pending_ingest.json 이 N초 이상 stuck 시 alert
```

`OperationsConfig` dataclass 에 `pending_alert_age_sec: int = 3600` 추가. `_parse_operations` 가 yaml 에서 읽음.

### D4. install.sh 통합

- `_step5_instance_dirs` 의 env template 에 `TELEGRAM_ALERT_BOT_TOKEN=...` + `TELEGRAM_ALERT_CHAT_ID=...` 예시 + bot 생성 안내 (@BotFather).
- `_systemd_stop_before_update` + `_systemd_start_after_update` 에 wikihub-pending-monitor.timer 추가.
- `_step8_systemd_render` 의 try-restart 에도 pending-monitor.timer 추가.
- `_step8_guide` 에 운영 진단 + Telegram 검증 명령 안내.

### D5. ADR-0024 cross-reference

ADR-0024 §Note 1줄 — "v0.1.5 에 multi-channel + periodic monitor 추가됨 (ADR-0037 §D1·D2)". ADR-0024 본문 미수정 — contract 의무 (failure → alert) 그대로.

## Consequences

### 긍정

- 운영자 일상 channel (Telegram) 으로 alert 즉시 가시화 — journal only 시나리오 해소.
- attempts-based alert 의 surface 지연 (50min) 보강 — age-based monitor 가 1h threshold 로 더 빠른 surface (또는 attempts mechanism 보다 빠르거나, attempts 와 별도 path).
- 운영자가 cron 별도 관리 안 함 — wikihub spec 차원에 통합.
- webhook + Telegram 병행 — 한쪽 실패해도 다른 쪽 발송.

### 부정 / 제약

- Telegram bot token / chat_id 는 secret — operator 가 `~/.config/wikihub/env` 채움 + Hermes `terminal.env_passthrough` 정합 책임.
- pending_monitor 가 ops-alert.service 호출 → ops-alert 가 자기 자신을 trigger 하는 recursion risk — pending_monitor.py + ops-alert.py 모두 항상 exit 0 + StartLimitBurst 로 mitigation. 운영 후 검증 필요.
- wikihub-pending-monitor.service 도 systemd unit 1개 추가 — render 부담 + 운영자 mental model 1개 추가. 효익 대비 acceptable.

### 후속 영향

- ADR-0024 §Note 1줄 추가 (cross-reference).
- `wikihub.yaml.example` 의 `operations.pending_alert_age_sec` (default 3600) 신설.
- `_system/commands/setup.md` maintainer catalog 갱신.
- install.sh env template + start/stop sequence + render + try-restart + step8_guide 모두 갱신.
- pending_monitor.py 가 lint 의 last_failure age 검사 까지 확장 가능 — v0.1.5 minimal scope 에선 vault pending 만. 운영 후 surface 시 추가.
- 2026-05-25: `wikihub_monitor` (v0.1.8) 추가 — 12hr 윈도우 운영 보고서 (매일 09:00 / 21:00 KST). ops-alert.py 의 `send_telegram` / `format_telegram_alert_message` 가 `scripts/lib/telegram.py` 로 추출됨 (parse_mode 옵션화: ops-alert = `"HTML"`, monitor = `None`).
- 2026-05-25 (v0.1.8 follow-up): env key 의미 명확화 — `TELEGRAM_ALERT_BOT_TOKEN` / `TELEGRAM_ALERT_CHAT_ID` → **`TELEGRAM_MONITOR_BOT_TOKEN` / `TELEGRAM_MONITOR_CHAT_ID`** 일괄 rename. ops-alert (fatal alert) + wikihub_monitor (12hr 보고서) 둘 다 운영 "모니터링" 채널이라는 의미 통일. 본문의 historical Decision (D1/D4) 표현은 보존 (당시 결정 시점 사실). 운영자는 `~/.config/wikihub/env` 의 키 이름 갱신 필요 — install.sh `_step5_instance_dirs` env template 이 새 키 이름으로 안내.

### 재검토 트리거

- pending_monitor 의 30분 주기가 운영 데이터 surface 후 너무 자주 / 드물면 yaml `operations.pending_monitor_interval_min` 토글 도입.
- Telegram + webhook 외 채널 (Slack, Discord, email) needs 시 dispatch 추상화 (channel abstraction layer).
- pending_monitor 의 lint failure age 확장 — `operations.lint_failure_alert_age_sec` 도입.

## Cross-references

- **complement**: ADR-0024 (fatal alert contract) — 본 ADR 이 dispatch + trigger layer 확장. ADR-0024 의 contract 의무 정본.
- **연계 정합**: ADR-0023 (install.sh distribution), ADR-0030 (update workflow), ADR-0032 (Hermes skill registration — Telegram env passthrough), ADR-0036 (graphify — `~/.config/wikihub/env` 자료 layer 패턴).
- **본 ADR 의 분석 정본**: [features/archive/20260520_alert_pipeline_overhaul/analysis_and_design.md](../../features/archive/20260520_alert_pipeline_overhaul/analysis_and_design.md)
- **2026-05-20 검토 자료**: Hermes OCI 패치 (ops-alert.py Telegram 통합 + 30분 cron pending-check) 의 wikihub spec 차원 정본화.
