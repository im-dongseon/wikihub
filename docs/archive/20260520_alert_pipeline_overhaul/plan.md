---
approved: 2026-05-20
---

# Plan — alert_pipeline_overhaul (v0.1.6)

- **작업 분류**: 기능 (alert pipeline 확장 — 새 channel + 새 trigger layer)
- **적용 단계 선언**:
  - Step 1 (Plan): 본 문서
  - Step 2 (Analysis & Design): 동 디렉토리 `analysis_and_design.md`
  - Step 3 (Implementation): ops-alert.py + pending_monitor.py + systemd templates + yaml + install.sh + render helper + setup.md + ADR §Note
  - **Step 4 (Review): 생략** — Hermes OCI 실증 데이터 자체가 실 검증 layer (Telegram 알림 송신 성공 + cron monitor 검증). 외부 인터페이스 변경: yaml 2 field 추가 (default 빈 dict / 1h), Telegram env var 도입 (operator-side).
  - Step 5 (Deployment): v0.1.6 patch bump + tag + latest force-update + push.
- **영향 범위**:
  - `scripts/ops-alert.py` — Telegram channel 통합 (`send_telegram` + `format_telegram_message` + webhook 병행 발송)
  - `scripts/pending_monitor.py` (신규) — vault pending age + lint failure age 검사
  - `_system/systemd/wikihub-pending-monitor.{service,timer}.template` (신규)
  - `_system/systemd/ops-alert.service` — `EnvironmentFile=-%h/.config/wikihub/env` 추가
  - `wikihub.yaml.example` — `operations.pending_alert_age_sec` + `lint_failure_alert_age_sec`
  - `scripts/_helpers/render_systemd_units.py` — pending-monitor singleton 처리
  - `install.sh` — env template 의 TELEGRAM_* + `_systemd_start_after_update` 의 pending-monitor enable + `_step8_guide` 안내
  - `_system/commands/setup.md` — catalog 갱신
  - `docs/adr/0037-alert-pipeline-architecture.md` (신규 — multi-channel dispatch + periodic monitor)
  - `docs/adr/0024-fatal-alert-contract.md` §Note (1줄 — ADR-0037 cross-reference)
  - `docs/adr/README.md` index 갱신
  - `_system/VERSION` 0.1.5 유지 (user 명시 — v0.1.5 wave 안 통합)
  - `features/HISTORY.md` v0.1.6 entry
- **메소드론 적용 여부**: 적용. architectural — 새 systemd unit + 새 script + ADR §Note.

## 배경 (한 문장)

v0.1.5 의 attempts-based alert (vault@/lint OnFailure → ops-alert) 가 webhook URL 만 지원 + age-based monitor 부재 → 운영자 가시성 부족. Hermes OCI 실증 (Telegram 발송 + cron pending-check) 패치 정본화 + wikihub spec 차원 통합.

## release 전략

user 명시 — v0.1.5 유지. 새 commit (main fast-forward push) + v0.1.5 annotated tag re-point (force-update) + latest force-update. main 자체는 force-push 없음 (안전).

VERSION 동일 — 동일 release window 의 architectural 보강으로 처리.
