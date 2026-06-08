---
approved: 2026-05-20
---

# Analysis & Design — alert_pipeline_overhaul (v0.1.5)

## 1. 배경 및 목적

### 진단

v0.1.5 시점 alert mechanism (ADR-0024):
- **trigger**: systemd `OnFailure=ops-alert.service` (vault@/mount@/lint 모두)
- **dispatch**: `ops-alert.py` 가 last_failure.json 수집 → `operations.fatal_webhook_url` POST. 미설정 시 journal only.

OCI 운영 (2026-05-20) 에서 surface 한 한계:
1. **Telegram channel 부재** — 운영자 일상 사용 channel (Telegram bot) 이 default 가 아니라 webhook 만. Hermes 가 ops-alert.py 패치로 Telegram 통합 검증 완료.
2. **age-based monitor 부재** — wikihub 의 attempts-based alert (vault@ attempts ≥ max_attempts ≈ 5 cycle ≈ 50min) 만 존재. age-based monitor 가 빠른 surface 가능. Hermes 가 cron job (30분 주기 pending_ingest age check) 으로 검증.

### 목적

본 feature 는 두 한계를 wikihub spec 차원에 통합:
- **multi-channel dispatch** (webhook + Telegram 병행)
- **periodic monitor unit** (age-based alert trigger)

## 2. 결정

### D1. Telegram channel — ops-alert.py 정본화

Hermes 의 OCI 패치 (`send_telegram` + `format_telegram_message` + `main()` 의 webhook/telegram 병행 로직) 를 wikihub `scripts/ops-alert.py` 에 통합.

- env: `TELEGRAM_ALERT_BOT_TOKEN` (bot token) + `TELEGRAM_ALERT_CHAT_ID` (chat ID)
- 양쪽 미설정 + `fatal_webhook_url` 미설정 시 journal only (기존 behavior 유지)
- 한쪽이라도 설정되면 발송 시도. 둘 다 설정되면 둘 다 발송 (병행).
- `_system/systemd/ops-alert.service` 에 `EnvironmentFile=-%h/.config/wikihub/env` 추가 (lenient prefix).

### D2. wikihub-pending-monitor systemd unit 신설

새 unit 2개 (singleton):
- `wikihub-pending-monitor.timer` — 30분 주기 (yaml `operations.pending_monitor_interval_min` 가능하나 v0.1.5 hardcoded)
- `wikihub-pending-monitor.service` — oneshot, `ExecStart=python scripts/pending_monitor.py`

`pending_monitor.py` 책임:
1. yaml 의 enabled vault list 순회
2. 각 vault 의 `$WIKIHUB_HOME/_state/<vault_id>/pending_ingest.json` 존재 시 mtime age 검사
3. age > `operations.pending_alert_age_sec` (default 3600s = 1h) → 해당 vault 의 `last_failure.json` 갱신 (scope=ingest_pending) + ops-alert.service start (systemctl --user start)
4. lint 의 last_failure.json age 검사 (별도 vault 무관) — age > `operations.lint_failure_alert_age_sec` 시 동일 처리
5. ops-alert.py 의 dedup mechanism (alerted_failed_count + 24h reminder) 이 자연 적용

### D3. yaml schema 보강

```yaml
operations:
  pending_alert_age_sec: 3600           # ingest pending 이 N초 이상 stuck 시 alert (default 1h)
  lint_failure_alert_age_sec: 3600      # lint 의 last_failure.json 이 N초 이상 stale 시 alert (default 1h)
```

### D4. ADR-0037 신설 (alert pipeline architecture)

- ADR-0024 (fatal alert contract) 와 complementary — ADR-0024 가 contract (failure → alert 의무), ADR-0037 이 dispatch + trigger layer architecture.
- §Decision: D1~D3 + alert pipeline 의 다중 channel + 다중 trigger layer 결정 정본.
- ADR-0024 §Note 1줄 — ADR-0037 cross-reference.

### D5. install.sh 통합

- `_step5_instance_dirs` 의 env template 에 `TELEGRAM_ALERT_BOT_TOKEN=...` + `TELEGRAM_ALERT_CHAT_ID=...` 예시 추가
- `_systemd_start_after_update` 에 `systemctl --user start wikihub-pending-monitor.timer` 추가
- `_step8_guide` 에 운영 진단 명령 + Telegram 설정 안내

## 3. 설계 — pending_monitor.py 구조

```python
def main():
    cfg = load_wikihub_yaml()
    instance_root = cfg.instance_root  # $WIKIHUB_HOME
    pending_age_sec = cfg.operations.pending_alert_age_sec  # default 3600
    lint_age_sec = cfg.operations.lint_failure_alert_age_sec  # default 3600

    triggered = False

    # 1. vault 별 pending age 검사
    for vault in cfg.vaults_enabled:
        pending_file = instance_root / "_state" / vault.id / "pending_ingest.json"
        if pending_file.exists():
            age = time.time() - pending_file.stat().st_mtime
            if age > pending_age_sec:
                # last_failure.json 갱신 — ops-alert 가 자연 collect
                _write_last_failure(vault, scope="ingest_pending", reason=f"pending {int(age)}s old (threshold {pending_age_sec}s)")
                triggered = True

    # 2. lint last_failure age 검사 (별도 monitor)
    # lint 의 last_failure.json 은 어디 저장? — 현재 design 검토 필요
    # vault state dir 와 별도 location. instance_root / "_state" / "__lint__" / "last_failure.json" 또는 vault 의 last_failure 와 같은 path 에 통합

    # 3. trigger 발생 시 ops-alert.service 호출
    if triggered:
        subprocess.run(["systemctl", "--user", "start", "ops-alert.service"], check=False, timeout=30)

    return 0  # 항상 0 — ops-alert recursion 회피 패턴 정합
```

### lint 의 last_failure 저장 위치 검토

현재 lint.md spec — `wiki/_lint/report.md` 만 저장. last_failure.json 같은 alert-trigger payload 부재. lint failure 시 systemd OnFailure 가 즉시 ops-alert 발화하나 age-based monitor 의 baseline 없음.

해결책:
- lint.service 의 ExecStop 또는 OnFailure hook 가 `_state/__lint__/last_failure.json` 작성
- 또는 pending_monitor.py 가 `systemctl --user is-failed wikihub-lint.service` 직접 query + 마지막 fail 시점 추출

복잡도 줄이려면: lint.service 가 ExecStopPost 로 last_failure.json 작성 (성공/실패 둘 다 — failure 면 reason 채움, success 면 file 삭제). pending_monitor 는 file 존재 + age 만 검사.

단 lint.service.template 변경 → 본 feature scope 확장. 또는 minimal scope 로 vault pending 만 처리하고 lint failure age 는 OnFailure 즉시 alert 만 의존 (현재 mechanism). v0.1.5 minimal scope.

**채택**: v0.1.5 의 pending_monitor 는 **vault pending age 만** 처리. lint failure age 는 OnFailure 즉시 alert 로 cover (기존 mechanism). lint age-based 는 운영 후 필요 surface 시 추가.

→ yaml schema 도 단순화: `pending_alert_age_sec` 만 (lint_failure_alert_age_sec 제거).

## 4. 미결 사항

없음. lint age-based 는 운영 데이터 surface 후 v0.1.6 검토 트리거.

## 5. Definition of Done

- [ ] `scripts/ops-alert.py` 가 Telegram + webhook 병행 발송
- [ ] `_system/systemd/ops-alert.service` 에 `EnvironmentFile=-%h/.config/wikihub/env`
- [ ] `scripts/pending_monitor.py` 신설 + vault pending age 검사 + ops-alert.service 호출
- [ ] `_system/systemd/wikihub-pending-monitor.{service,timer}.template` 신설
- [ ] `render_systemd_units.py` 가 pending-monitor singleton 정확히 render
- [ ] `wikihub.yaml.example` 의 `operations.pending_alert_age_sec` (default 3600) 추가
- [ ] `install.sh` env template 의 TELEGRAM_* 예시 + `_systemd_start_after_update` 의 pending-monitor enable
- [ ] `_system/commands/setup.md` catalog 갱신
- [ ] `docs/adr/0037-alert-pipeline-architecture.md` 신설 (Accepted)
- [ ] `docs/adr/0024-fatal-alert-contract.md` §Note 1줄 (ADR-0037 cross-reference)
- [ ] `docs/adr/README.md` index 갱신
- [ ] pytest 57 pass 회귀 + render dry-run (wikihub-pending-monitor.{service,timer} 정확 출력)
- [ ] feature dir archive 이동
- [ ] commit + v0.1.5 tag re-point (force-update) + latest force-update + push
