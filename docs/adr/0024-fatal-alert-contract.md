# ADR-0024: fatal 알림 contract — last_failure.json + dedup + Hermes 이중 경로

- **Status**: Accepted
- **Date**: 2026-05-14 (v1) / 2026-05-15 (v9 본문 minor 갱신 — mount scope 추가)
- **Feature**: features/20260514_install_runtime
- **Supersedes**: 없음
- **Superseded by**: 없음

> **v9 minor 갱신 (2026-05-15)**: `last_failure.json` schema 의 `scope` 필드 enum 에 **`"mount"`** 추가. writer 책임에 `scripts/lib/mount.py` (Path C+ 신규 산출물) 의 두 분기 추가:
> - `_raise_mount_failure` — `assert_mount_alive` 의 Retryable 6회 연속 누적 시 Fatal escalate
> - `vfs_refresh` 의 OAuth error 패턴 매칭 시 Fatal 분기
>
> 이로써 R14-CRIT-1 (mount silent dead) + R13-CRIT-1 (vfs_refresh Q6 alert 체인) + R14-HIGH-4 (Retryable + Requires silent abort) 흡수. **mount-fail-recorder.service 같은 신규 systemd unit 도입 회피**. reader (`ops-alert.py`) 는 scope 분기 없음 — 동일 payload 형식. ops-alert.py 는 `last_failure.json` 부재 시 (mount@.service `StartLimitBurst` 초과 + `Requires=` cancel 로 vault@ 미실행 case) `journalctl --user -u wikihub-mount@<vid> --since '30min ago' --no-pager` 의 tail 을 `fallback_diagnostic` 필드로 첨부.
>
> supersede 아님 — 기존 schema 의 enum 확장 + writer 책임 분배 추가만. 본 ADR 본문 (Decision · Consequences) 갱신은 아래 §"v9 추가" 섹션 참조.

## Context

F4 의 v4 설계 review (R8 SRE) 가 finding — v4 의 `Restart=` 제거 surgical lift 가 systemd 내부 fatal loop 는 해소했지만 **fatal 알림 채널 자체가 dead**:

1. v4 §4.2 의 `OnFailure=ops-alert.service` 가 trigger 하는 `ops-alert.py` 의 input `_state/<vault_id>/last_failure.json` **producer 가 F3 코드에 부재** — vault-fetch.py 와 lib/* 어디에도 영속화 없음.
2. F1 archive §4.6.6 의 **fatal 이중 경로** (Hermes 채널 `notify_on_fatal=true` + Hermes-독립 webhook `ops-alert.service`) 중 Hermes 채널이 v4 에 매핑 없음.
3. 두 결함 결합 → fatal 발생 시 **알림 0건 도달** (systemd journal 만 남음).

또한 v4 의 `Restart=` 제거로 매 timer 사이클마다 fatal 반복 + ops-alert 매번 발화 → alarm fatigue (R7 NEW-7 = R8 CRIT-R8-2). dedup 정책 부재.

## Considered Options

- **(α) I1**: 알림 채널 모두 v0.2.x 로 미루기 — v0.1.0 은 journal 만.
- **(β) I2**: Hermes-독립 webhook (ops-alert) 만 — last_failure.json producer + ops-alert.py 신규. Hermes 채널은 v0.2.x.
- **(γ) I3**: 이중 경로 — last_failure.json producer + ops-alert + vault-fetch.py 가 fatal 시 Hermes notify 도 trigger.

> 옵션 상세는 [features/20260514_install_runtime/analysis_and_design.md §3.9](../../features/20260514_install_runtime/analysis_and_design.md) 참조.

## Decision

**채택**: (β) I2 (v0.1.0 minimum) + (γ) I3 마이그레이션 경로 lock.

### `last_failure.json` schema (`_state/<vault_id>/last_failure.json`)

```json
{
  "vault_id": "gdrive",
  "exit_code": 2,
  "severity": "fatal",
  "scope": "vault",
  "reason": "401 invalid_grant: refresh_token revoked",
  "remediation": "auth_gdrive.py 재실행 + scp 재전송",
  "source_id": null,
  "first_failed_at": "2026-05-14T01:30:00+00:00",
  "last_failed_at": "2026-05-14T01:30:00+00:00",
  "failed_count": 1,
  "alerted_at": null
}
```

- `first_failed_at`: 첫 fatal 시각 (보존). `last_failed_at`: 매 fatal 갱신.
- `failed_count`: 연속 fatal (success 1회로 리셋).
- `alerted_at`: ops-alert.py 가 webhook 발송 성공한 마지막 시각 (dedup 기준).

### Writer 책임 — `scripts/vault-fetch.py` 수정 (F4 산출물)

F3 의 `scripts/lib/state.py` 에 `save_last_failure()` + `clear_last_failure()` helper 추가 (둘 다 `_atomic_write_json` 패턴 — fsync 정합). vault-fetch.py 의 `except VaultSyncFatal` 직후 `save_last_failure` 호출, success 분기 직후 `clear_last_failure` 호출.

`VaultSyncFileFatal` 은 retry.json 이 정본 — last_failure.json 에는 기록 안 함 (ops-alert.py 가 retry.json 도 함께 수집).

### Reader 책임 — `scripts/ops-alert.py` (F4 산출물)

systemd `OnFailure=ops-alert.service` 가 trigger → ops-alert.py 가:
1. `_state/*/last_failure.json` 수집.
2. dedup 정책 적용 (아래 표).
3. `operations.fatal_webhook_url` 미설정이면 no-op (journal 만).
4. 설정 시 webhook POST + 성공 시 `alerted_at` 갱신.
5. exit code 항상 `0` — ops-alert 자체 실패는 silent (무한 OnFailure recursion 회피).

### Dedup 정책

| 조건 | 동작 |
|---|---|
| `last_failure.json` 부재 | first fatal — webhook 즉시 발송 + alerted_at 기록 |
| `alerted_at` null | first fatal 발송 실패 상태 — 즉시 재발송 시도 |
| `alerted_at` 있음 + `failed_count` 같음 | dedup hit — webhook skip (journal 만) |
| `alerted_at` 있음 + `failed_count` 증가 | resurfacing — webhook 발송 |
| `last_failed_at - alerted_at > 24h` | 일일 reminder — webhook 발송 |

### Hermes 채널 — v0.2.x 마이그레이션 경로

F4 가 `scripts/lib/notify.py` 신규 — `notify_via_hermes()` stub (v0.1.0 은 `log.info` 만). vault-fetch.py 가 `notify_on_fatal=true` 시 호출. v0.2.x 의 F5 (hermes_adapter) 가 stub 본문을 Telegram 통지로 채움.

**이유**:
- I1 은 v0.1.0 acceptance invariant 와 충돌 — fatal 인지 못 하면 cursor·credentials 진단 늦어짐.
- I3 의 Hermes 채널은 Hermes 자체 fail 시 누락 — F1 이 이중 경로 정본화한 것이 이 이유.
- I2 가 v0.1.0 minimum viable — webhook 미설정 시 no-op 으로 운영자 부담 0.
- dedup 의 alerted_at + failed_count 기준은 단순 + 정합 (운영자 진단 후 success → reset → 새 fatal 은 first 로 인식).

## Consequences

- **긍정**: fatal 채널 dead 결함 해소. alarm fatigue 회피 (dedup). v0.2.x 의 Hermes 채널 추가 시 시그니처 변경 없음 (stub 본문만 채움).
- **부정/제약**:
  - F3 의 `scripts/vault-fetch.py` 와 `scripts/lib/state.py` 가 F4 산출물 (수정 대상) — F3 archive 의 read-only 정책 일부 완화. ADR 본문에 명시.
  - ops-alert.service 가 venv 의존 — venv 손상 시 ops-alert 도 dead. v0.2.x 에서 shell fallback 추가 검토.
  - webhook URL 타입 user-agnostic (generic JSON POST) — Telegram/ntfy/healthchecks 모두 호환되지만 specific 어댑팅은 운영자 책임.
- **후속 영향**:
  - V10 verification 이 fatal 채널 정합 회귀 방지 (exit 2 → OnFailure → ops-alert.py 실행 + last_failure.json 영속화 확인).
  - F5 (hermes_adapter) 진입 시 `notify_via_hermes` stub 활성화 — 본 ADR supersede 가 아닌 stub 본문 갱신.

## v9 추가 (2026-05-15) — mount scope writer 확장

### Context (v9)

rclone mount + 변경 감지 도입 (ADR-0025·0026 참조 — ADR-0027 의 책임 분리는 ADR-0035 로 supersede 후 rclone 단독화, 본 §의 mount scope writer 책임 자체는 정합 유지) 으로 mount lifecycle 의 fatal case 가 추가됨:

1. **mount permanently failed (Retryable 누적)** — `assert_mount_alive` 가 매 사이클 Retryable raise. 6회 (1시간) 연속 누적 시 → 운영자 통지 필요
2. **rclone OAuth revoke** — `vfs_refresh` 가 rclone stderr 에 인증 관련 패턴 출현 시 → fatal escalate
3. **mount@.service StartLimitBurst 초과** — mount daemon 자체가 permanently failed. vault@ 가 `Requires=` cancel 로 ExecStart 미실행 → mount.py 미호출

case 1·2 는 `mount.py` 가 writer 책임. case 3 은 `mount@.service` 의 `OnFailure=ops-alert.service` 가 직접 trigger 하므로 `last_failure.json` 부재 → ops-alert.py 의 fallback diagnostic 책임.

### Decision (v9)

`last_failure.json` schema 의 `scope` 필드 enum 확장 + writer 책임 분배:

| scope | writer | trigger 분기 | 산출물 위치 |
|---|---|---|---|
| `"vault"` (기존) | `vault-fetch.py` | `except VaultSyncFatal` | F4 v1 |
| `"file"` (기존) | retry.json (별도 정본) | `VaultSyncFileFatal` | F3 |
| **`"mount"` (v9 신규)** | **`scripts/lib/mount.py`** | `_raise_mount_failure` (Retryable 누적) + `vfs_refresh` OAuth Fatal 분기 | F4 v9 (ADR-0025) |

### `last_failure.json` schema 갱신 (v9)

```json
{
  "vault_id": "gdrive",
  "exit_code": 2,
  "severity": "fatal",
  "scope": "vault" | "file" | "mount",         // v9 — "mount" 추가
  "reason": "...",
  "remediation": "...",
  "source_id": null,
  "first_failed_at": "...",
  "last_failed_at": "...",
  "failed_count": 1,
  "alerted_at": null
}
```

### Reader (`ops-alert.py`) — fallback diagnostic 책임 (v9 신규)

ops-alert.py 가 trigger 됐는데 `last_failure.json` 부재 또는 `last_failed_at` 가 30분 이상 stale 인 경우:

```python
# v9 fallback diagnostic (mount@.service OnFailure 가 직접 trigger 한 case)
fallback = subprocess.run(
    ["journalctl", "--user", "-u", f"wikihub-mount@{vault_id}.service",
     "--since", "30min ago", "--no-pager", "-n", "100"],
    capture_output=True, text=True, timeout=10, check=False,
).stdout
# webhook payload 의 `fallback_diagnostic` 필드로 첨부. webhook 미설정 시 stderr 출력.
```

### `_RCLONE_AUTH_PATTERNS` (mount.py 정본)

v9 starting regex (V18 검증 후 refine):

```python
_RCLONE_AUTH_PATTERNS = re.compile(
    r"(Token expired|invalid_grant|401 Unauthorized|oauth2.*invalid|"
    r"unauthorized_client|access_denied)",
    re.IGNORECASE,
)
```

### `MOUNT_RETRYABLE_FATAL_THRESHOLD` (mount.py 정본)

```python
MOUNT_RETRYABLE_FATAL_THRESHOLD = 6   # 약 1시간 @ 10min cycle
```

## v9 Cross-references

- ADR-0025 (rclone mount 채택) — mount lifecycle 의 fatal case 정의
- ADR-0027 (rclone vs gws 책임 분리) — mount.py 가 writer 책임의 정본
- features/20260514_install_runtime/analysis_and_design.md §10.4.1·§10.4.6·§10.4.7 — mount scope 의 case 분배 및 spec 코드

## Note (2026-05-18, feature `hermes_adapter` F5)

본 ADR 의 last_failure.json producer (vault-fetch.py 의 `save_last_failure`) 가 hermes 의 subprocess 로 호출되는 가정 유지 (ADR-0006 unified orchestration). F5 의 (α) 채택 (Hermes skill 등록) 이 본 가정 보존:

- ExecStart = `hermes chat --skills wh-ingest --quiet --query "/wh-ingest --vault X"` (F5 정합).
- Hermes 가 skill body 의 procedure (`_system/commands/ingest.md`) 를 LLM 으로 해석 → mechanical phase 에서 vault-fetch.py subprocess 호출 → last_failure.json producer 정상 작동.

### Hermes 미설치 시 dead chain 방지 (CR2-CRIT-1 해결)

Hermes binary 부재 시 systemd ExecStart 자체가 `203/EXEC` fail → vault-fetch.py 미도달 → last_failure.json producer 미실행 → ops-alert 의 fallback diagnostic 도 mount scope 한정이라 **fatal 알림 0건 도달** 위험.

F5 의 해결:
- install.sh `_step6_agent_skill` 의 Hermes detect gate — 부재 시 `SKIP_SYSTEMD_RENDER=1` → systemd unit render/enable 자체 skip → timer 미가동 → silent dead chain 회피.
- 운영자가 Hermes 설치 후 install.sh 재호출 시 정상 진입.

본 ADR 의 fatal 알림 contract 는 Hermes 설치 + 정상 dispatch 가정 하에 보존.

### v0.2.x — `notify_via_hermes()` stub 채움 (별도 feature)

본 ADR 의 §v0.2.x notify_via_hermes stub 은 F5 범위 밖 — 별도 v0.2.x feature 가 Telegram 통지 본문 채움. F5 는 invocation 정합 한정.

Status 변경 없음.

## Note (2026-05-20, feature `alert_pipeline_overhaul` v0.1.5)

본 ADR 의 contract (failure → alert 의무) 본문 그대로 유지. dispatch + trigger layer architecture 는 **ADR-0037 (alert pipeline architecture)** 가 confirm — Telegram channel 추가 (webhook 병행) + wikihub-pending-monitor systemd unit 신설 (age-based trigger). 본 ADR 의 §v0.2.x notify_via_hermes stub 도 ADR-0037 이 직접 Telegram bot API 호출로 대체 — stub 의도 일부 충족.

2026-05-26 (ADR-0040 Supersedes ADR-0037): wikihub-pending-monitor + wikihub_monitor 폐기 결정. ops-alert.service 의 Telegram channel (webhook 병행) + `EnvironmentFile=-%h/.config/wikihub/env` 만 ADR-0040 으로 carry-over. 본 ADR contract (failure → alert 의무) 본문 그대로 유지.
