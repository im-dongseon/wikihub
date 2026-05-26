# ADR-0040: wikihub-monitor / wikihub-pending-monitor 폐기 — ops-alert 단독 운영

- **Status**: Accepted
- **Date**: 2026-05-26
- **Feature**: features/20260526_monitor_services_remove
- **Supersedes**: ADR-0037 (alert pipeline architecture — multi-channel dispatch + periodic monitor)
- **Superseded by**: 없음

## Context

ADR-0037 (v0.1.5, 2026-05-20) 가 ADR-0024 (fatal alert contract) 를 complement 하기 위해 두 architectural 결정 추가:

- **§D2**: `wikihub-pending-monitor.{service,timer}` 신설 — 30분 주기 `pending_ingest.json` age 검사 → threshold 위반 시 `last_failure.json` 갱신 + ops-alert.service 호출. ADR-0024 `OnFailure` attempts 기반 alert 의 surface 지연 (50min) 보강.
- **§D1**: ops-alert.service 에 Telegram channel 추가 (webhook 병행). `~/.config/wikihub/env` 의 `TELEGRAM_ALERT_*` (이후 v0.1.8 follow-up 으로 `TELEGRAM_MONITOR_*` rename) 로 secret 관리.

ADR-0037 §"후속 영향" (2026-05-25, v0.1.8 follow-up) 가 `wikihub_monitor` 추가:

- `wikihub-monitor.{service,timer}` 신설 — 12hr 운영 보고서 (매일 09:00 / 21:00 KST). bootstrap fail (exit 2) 만 ops-alert 발화, runtime fail (exit 75) 은 자연 재시도.
- `send_telegram` / `format_telegram_alert_message` 함수를 `scripts/lib/telegram.py` 로 추출 + `parse_mode` 옵션화 (ops-alert = HTML, wikihub_monitor = plain).
- env key 의미 통일을 위해 `TELEGRAM_ALERT_*` → `TELEGRAM_MONITOR_*` rename.

**문제**: v0.1.5 ~ v0.1.8 운영 6주차 시점에 두 monitor unit 의 추가 surface 가 ops-alert (ADR-0024 attempts 기반) 가 못 잡는 결함을 실제로 잡았다는 evidence 가 부재. 두 layer 모두 hypothesis 단계에 머무름:

- `wikihub-pending-monitor` 의 age-based surface 가 1h vs attempts-based 50min 으로 surface 시점 큰 차이 없음.
- `wikihub-monitor` 의 12hr 보고서가 운영자 noise 만 증가시키고 conditional alert 의미 (exit 2 만 발화) 가 모호.

**비용**:
- systemd render 부담 — 4 unit 추가 (template render + try-restart + reset-failed + enable list).
- 운영자 mental model — `pending_alert_age_sec`, `monitor_enabled`, `monitor_report_vault`, `monitor_report_subpath` 4 yaml 필드 + 2 env key 관리.
- 코드 부담 — `scripts/wikihub_monitor.py` (~470 line), `scripts/pending_monitor.py` (~110 line), `scripts/lib/telegram.py` (~80 line) 유지.

Karpathy §2 Simplicity — 효익 부재 + 비용 확인 → 폐기 정공법.

## Considered Options

- **(α) ADR-0037 유지** — 두 monitor unit + telegram lib + yaml 4 필드 + env key MONITOR rename 모두 유지. 운영 evidence 누적 후 재평가.
- **(β) 두 monitor unit 폐기, telegram helper 만 lib 유지** — wikihub_monitor / pending_monitor + 4 yaml 필드 제거. `scripts/lib/telegram.py` 는 ops-alert.py 단독 caller 로 유지.
- **(γ) 두 monitor unit + telegram lib 모두 폐기, ops-alert 로 inline** — **채택**. lib 단일 caller 추상화 비용 회수 + parse_mode 옵션화 (wikihub_monitor 대응) 자체 제거.

> 옵션 상세 비교는 [features/20260526_monitor_services_remove/analysis_and_design.md](../../features/20260526_monitor_services_remove/analysis_and_design.md) §결정 참조.

## Decision

**채택**: (γ) 두 monitor unit + telegram lib 모두 폐기. telegram helper 는 ops-alert.py 로 inline 회수.

**이유**:
- 운영 evidence 부재 + 비용 확인 — Karpathy §2 Simplicity 정공법.
- ops-alert (ADR-0024 fatal alert contract) 의 attempts-based + Telegram channel 만으로 fatal alert layer 충분.
- single caller lib 의 추상화 비용 회수 — `parse_mode` 옵션화는 wikihub_monitor 대응 산물 → 함께 폐기.

**기각**:
- (α) 비용/효익 비대칭이 6주차 운영에서 surface 됨 — 유지 결정 사유 부재.
- (β) `scripts/lib/telegram.py` 가 ops-alert.py 단독 caller 인 상태로 lib 유지 = Karpathy §2 위반.

### Carry-over from ADR-0037

ADR-0037 의 다음 결정 본의는 ADR-0040 으로 carry-over (ops-alert 단독 운영 형태로):

| ADR-0037 결정 | Carry-over 상태 |
|---|---|
| §D1: Telegram channel (webhook 병행) | **유지** — ops-alert.py 가 webhook + Telegram 병행 발송 (한쪽 성공 시 alerted_at 갱신). `format_telegram_alert_message` + `send_telegram` 함수는 ops-alert.py 안으로 inline 회수, `parse_mode="HTML"` 고정 (옵션화 제거). |
| §D2: wikihub-pending-monitor systemd unit (architectural) | **폐기** — `_system/systemd/wikihub-pending-monitor.{service,timer}.template` + `scripts/pending_monitor.py` 제거. age-based surface 회복은 §재검토 트리거 항목으로 deferred. |
| §D3: yaml `operations.pending_alert_age_sec` | **폐기** — pending_monitor 부재로 의미 소멸. yaml.example + `OperationsConfig` 에서 제거. ADR-0032 §Note Group B catalog 에서도 자연 제거. |
| §D4: install.sh 통합 (env template + start/stop sequence) | **유지 (subset)** — env template 의 Telegram bot 안내 + ops-alert.service 의 `EnvironmentFile=` 그대로. start/stop sequence 의 monitor 항목만 제거. |
| §D5: ADR-0024 cross-reference | **유지** — ADR-0024 § (Note 2026-05-20) 를 본 ADR-0040 reference 로 1줄 보강. |
| 2026-05-25 follow-up: `TELEGRAM_ALERT_*` → `TELEGRAM_MONITOR_*` rename | **유지 (관성)** — wikihub_monitor 가 사라져 의미적 명분은 소멸했으나 operator `~/.config/wikihub/env` 수동 갱신 부담 회피를 위해 키 이름 그대로 유지. install.sh env template 의 주석 + `_system/systemd/ops-alert.service` 의 EnvironmentFile 주석에 historical 사유 명시. |
| 2026-05-25 follow-up: `scripts/lib/telegram.py` 추출 + `parse_mode` 옵션화 | **폐기** — single caller lib 회수 + parse_mode 고정. |

## Consequences

### 긍정

- systemd unit 6 → 4 (mount@ / wikihub-ingest@ / wikihub-lint / wikihub-graphify / ops-alert / 4 monitor unit 폐기 → 5 unit 만). 운영자 mental model 단순화.
- 코드 ~660 라인 감소 (`wikihub_monitor.py` 470 + `pending_monitor.py` 110 + `lib/telegram.py` 80 ≈ 660).
- yaml `operations` 4 필드 제거 (`pending_alert_age_sec`, `monitor_enabled`, `monitor_report_vault`, `monitor_report_subpath`).
- install.sh 의 stop / reset-failed / start / try-restart 4 위치 단순화 + banner 1 라인 제거.

### 부정 / 제약

- `pending_ingest.json` age 기반 surface 부재로 회귀 — operator 가 vault sync 실패를 ADR-0024 attempts 기반 alert (50min) 까지 기다리는 케이스. 운영 데이터 surface 후 재도입 검토 트리거.
- 12hr 운영 보고서 부재로 회귀 — operator 가 journal 진단 명령 (`journalctl --user -t wikihub-ops-alert --since '24h ago'`) 으로 자기 운용. install.sh banner 의 운영 진단 명령 안내 보존.
- `TELEGRAM_MONITOR_*` env key 의미 부정확성 (fatal alert layer 만 남았는데 MONITOR prefix) — install.sh env template 주석으로 historical 명시. v0.2.x major rename 시 정정 고려.

### 후속 영향

- ADR-0024 § (Note 2026-05-20) 끝에 1줄 추가 — "2026-05-26 (ADR-0040): ADR-0037 §D2 + wikihub_monitor follow-up 폐기. ops-alert.service 의 Telegram channel + EnvironmentFile= 만 ADR-0040 으로 carry-over."
- `docs/adr/README.md` index — ADR-0037 Status 갱신 + ADR-0040 entry 추가.
- `wikihub.yaml.example` operations 4 필드 삭제.
- `scripts/lib/config.py` `OperationsConfig` 4 필드 + `_parse_operations` 4 라인 삭제.
- install.sh upgrade migration block 추가 — monitor unit 이 enable 된 기존 instance (v0.1.5 ~ v0.1.8 + v0.1.9 canary) 의 `wikihub-monitor.{service,timer}` + `wikihub-pending-monitor.{service,timer}` 4 unit 을 stop + 2 timer disable (orphan 회피). `.service` 는 enable 대상 아니라 disable 미호출.
- `render_systemd_units.py` legacy_singletons catalog 에 4 monitor unit 추가 — operator 의 `~/.config/systemd/user/` 에서 stale unit 파일 자동 삭제 (`systemctl disable` 은 symlink 만 제거하지 unit 파일 자체는 남기는 한계 보완).
- `_system/systemd/ops-alert.service` 의 EnvironmentFile 주석 갱신 — ADR-0037 §D1 → ADR-0040 (carry-over of ADR-0037 §D1) + env key `TELEGRAM_ALERT_*` → `TELEGRAM_MONITOR_*` 정합.
- `README.md` 의 `wikihub-monitor` 항목 1건 삭제 + 버전 highlight 정정 (ADR-0040 supersede narrative 명시).
- `docs/adr/0032-hermes-skill-registration-policy.md` §Note Group B catalog 에서 `pending_alert_age_sec` 항목 자연 제거 (yaml.example single source of truth 정합).

### 재검토 트리거

- 운영 데이터 surface — pending_ingest stuck 결함 또는 vault 운영 통계 needs 재발생 시 (a) ops-alert.py 안에 light pending-age 검사 통합 (별도 timer 없이 OnFailure 호출 시점에 검사), 또는 (b) 외부 모니터링 (uptime-kuma, healthchecks.io) 으로 운영자 자유 도구 채택. 별도 systemd timer 재도입은 마지막 옵션.
- `TELEGRAM_MONITOR_*` → `TELEGRAM_ALERT_*` rename 은 v0.2.x major bump 시점에 operator env migration 자동화와 함께 처리.

## Cross-references

- **Supersedes**: [ADR-0037](0037-alert-pipeline-architecture.md) — alert pipeline architecture.
- **complement**: [ADR-0024](0024-fatal-alert-contract.md) — fatal alert contract. ADR-0040 은 ADR-0024 의 dispatch (webhook + Telegram) 와 secret 관리 (EnvironmentFile) 만 carry-over.
- **연계 정합**: [ADR-0023](0023-install-script-distribution-curl-pipe.md) (install.sh distribution), [ADR-0030](0030-update-workflow-orchestration.md) (update workflow — 본 ADR 의 upgrade migration block).
- **본 ADR 의 분석 정본**: [features/20260526_monitor_services_remove/analysis_and_design.md](../../features/20260526_monitor_services_remove/analysis_and_design.md)
