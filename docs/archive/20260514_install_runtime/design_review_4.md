# F4 design review R8 (general-purpose SRE — v4 검증)

- 리뷰어: general-purpose SRE (R8) — claude-opus-4-7, fresh context
- 대상: `features/20260514_install_runtime/analysis_and_design.md` v4 (855 lines)
- 이전 라운드 참조: `design_review_2.md` (R6, general-purpose SRE), `design_review_1.md` (R5, feature-dev:code-reviewer)
- 독립성 선언: R6 의 결론을 답습하지 않고, v4 가 R5·R6 의 권고를 채택하는 과정에서 surface 한 새로운 결함 + F1/F2/F3 정본과의 정합성 + v4 가 incomplete 한 lift 를 본인 시각으로 평가했다. v4 본문 + F1 archive §4.6.6/§4.8 + F2 setup.md + F3 의 `scripts/lib/*` 실 코드를 입력으로 사용.
- 범위: production reliability·observability·failure recovery·security·idempotency 5축. R6 가 잡은 CRIT 3 + HIGH 8 의 v4 fix 가 회귀를 도입했는지 + v4 가 incomplete 한 lift 가 무엇인지가 본 라운드의 핵심.

> **종합**: v4 의 surgical lift (Restart= 제거 + `SuccessExitStatus=0 75` + `OnFailure=ops-alert.service`) 는 R6 의 CRIT-R6-1/2/3 을 spec 수준에서 해소한다. 그러나 **fix 자체가 fatal loop 의 형태를 systemd 내부 (RestartSec=60) 에서 운영자 알림 채널 (ops-alert.service 의 매 timer cycle 발동) 로 옮겼을 뿐**, 알람 중복 억제·idempotent dedup 의 책임이 spec 어디에도 lock 되지 않았다. 또한 **ops-alert.py 의 input 인 `_state/*/last_failure.json` 의 producer 가 F3 결과물에 부재** — v4 가 만든 ops-alert.service 는 호출은 되지만 read 할 상태가 없다. 이는 **CRIT 수준의 정합 결함**으로 Step 3 진입 차단. 그리고 F1 §4.6.6 의 fatal 알림 **이중 경로** 중 Hermes-측 (`agent.notify_on_fatal=true` + `notify_via_hermes_optional`) 이 v4 어디에도 매핑되지 않아 정본 lift 가 incomplete. HIGH 수준의 정합 결함 4건, MED 7건, NIT 다수.

---

## 1. 차단 이슈 (CRIT — Step 3 진입 차단)

### CRIT-R8-1 [Reliability / SpecMismatch] `ops-alert.service` 의 input 인 `_state/*/last_failure.json` producer 가 F3 결과물에 부재 — ops-alert 가 read 할 상태 없음 (`analysis_and_design.md` §4.2 ops-alert.service.template / F1 archive §4.6.6 L1102~1120)

**무엇이**: v4 §4.2 의 `ops-alert.service` spec:

```ini
ExecStart={venv_path}/bin/python {wikihub_home}/scripts/ops-alert.py
```

본문 L636: "스크립트 책임: `_state/*/last_failure.json` 수집 → `operations.fatal_webhook_url` POST".

F1 archive §4.6.6 (L1102~1120) 의 `notify_via_systemd_onfailure(err)` 함수가 정본 producer — `last_failure.json` 을 atomic write 로 영속화. 이 함수는 sync 코드(`gdrive-sync.py` 또는 `vault-fetch.py`) 안에서 fatal 직전에 호출되어야 ops-alert 의 input 이 만들어진다.

그러나 `/Users/1004790/workspace/wikihub/scripts/` 의 F3 결과물을 grep 한 결과:
```
$ grep -rn "last_failure" /Users/1004790/workspace/wikihub/scripts/
# (출력 없음)
```

즉 **F3 가 `last_failure.json` 영속화 책임을 ingest 코드에 lift 하지 않았다**. F1 archive §4.6.6 가 ingest.py 의 fatal handler 안에 `notify_via_systemd_onfailure(err)` 호출을 명시했지만, F3 의 `scripts/lib/sync.py` 또는 `vault-fetch.py` 어디에도 fatal 시 last_failure.json write 가 없음.

**왜 위험한가** (운영 시나리오):
- vault A 가 OAuth fatal → exit 2 → systemd 가 `OnFailure=ops-alert.service` 발동 → ops-alert.py 가 `_state/gdrive/last_failure.json` 을 read 시도 → 파일 없음 → ops-alert 가 빈 payload 또는 stale payload (이전 fatal 의 잔존) 를 fatal_webhook 으로 POST. 운영자는 "fatal 발생" 만 알게 되고 vault·reason·remediation 미상.
- 또는 ops-alert.py 가 input 파일 부재 시 silent exit 0 → fatal 사건 자체가 무성 (operations.fatal_webhook_url 설정에도 불구). v0.1.0 acceptance 의 fatal 알림 경로 자체가 깨짐.
- 이는 **systemd 의 OnFailure 가 작동해도 사람에게 도달 못 함** — 운영자 입장에서 "왜 sync 가 멈춰 있는데 알림이 안 오지?" 의 silent failure.

**왜 v4 가 놓쳤나** (추정): v4 가 F1 §4.8.2 의 unit ini 패턴만 lift 하고, F1 §4.6.6 의 코드 측 fatal handler (즉 producer) 의 F4 → F3 잔존 책임을 surface 하지 않았다. v4 §5 의 lift 매트릭스에 F3 의 fatal handler 책임이 없다.

**어떻게 고칠까** — 두 가지 동시 보강:
1. **F3 후속 작업 (또는 본 F4 의 spec 확장)**: `scripts/lib/sync.py` 또는 `scripts/vault-fetch.py` 의 fatal handler 가 `_state/{vault_id}/last_failure.json` 을 atomic write 하는 책임을 명시. F1 §4.6.6 의 `notify_via_systemd_onfailure(err)` 정본 lift. v4 §4.x 신설 또는 plan 의 F3 후속 light feature 로 분기.
2. **v4 §4.2 ops-alert.service 의 input contract 명시**: ops-alert.py 가 `_state/*/last_failure.json` 부재 시 동작 (skip vs warning) 을 spec 수준에서 lock. v4 본문이 "수집" 만 명시 — 부재·stale·partial 의 모든 분기 spec 없음.
3. **V<N> verification 추가** — V14 "fatal 사건 발생 시 `last_failure.json` write → ops-alert.py read → webhook 도달 의 end-to-end 검증" 신설.

**스펙 수정 위치**: §4.2 ops-alert.service 직후에 4.2.x "fatal producer ↔ consumer contract" 단락 추가. §6 V<N> 표에 V14 추가. ADR-0021 또는 신규 ADR (예: ADR-0024 — fatal 알림 producer/consumer contract) 발의.

---

### CRIT-R8-2 [Reliability / Observability] fatal loop 의 형태가 systemd 내부 → ops-alert.service 발동 매 timer cycle 로 이전 — alarm fatigue + 알림 dedup 책임 부재 (`analysis_and_design.md` §4.2 service template / §3.5 [E] v4 변경)

**무엇이**: R6 의 CRIT-R6-1 (RestartSec=60 으로 인한 60초 fatal loop) 을 v4 가 `Restart=` 제거로 해소. 그러나 **`OnFailure=ops-alert.service` 는 살아있고 timer 의 `OnUnitInactiveSec={sync_interval_sec}s` 가 sync_interval 마다 fire 한다**. v4 §4.2 본문 L601~603:

> "exit 75 는 다음 timer fire 에서 자연 재시도, exit 2 는 OnFailure 가 ops-alert 발동 + 다음 timer 도 시도.
>  운영자가 cursor·credentials 등 개입 전까지 fatal 사이클이 계속 반복될 수 있음 — ops-alert 가 통지 책임."

운영 시나리오 (sync_interval_sec=600 = 10분, default):
- 09:00 OAuth refresh_token 만료 → exit 2 → ops-alert 발동 → telegram 1건 도달
- 09:10 timer fire → 같은 exit 2 → ops-alert 발동 → telegram 2건
- 09:20, 09:30, … 운영자가 개입 (= credentials scp + chmod 600) 전까지 10분마다 telegram
- 야간에 발생 시 운영자가 자고 일어나면 5~8 시간 × 6 = 30~48 건 telegram 누적

**왜 v3 와 비교 시 더 나아진 점 + 못 잡은 점**:
- v3 의 `RestartSec=60` + `StartLimitBurst=5` → 5분 동안 5건 telegram + 그 후 start-limit-hit (CRIT-R6-2) 로 stuck. 즉 v3 는 알람 5건만 + stuck.
- v4 는 stuck 없음 + 10분마다 영원히 알람. **합계 알람 건수는 v4 가 훨씬 많음** — alert fatigue 의 표준 시나리오 (alerting 의 dedup + suppression 부재).
- v4 의 lift 가 systemd 수준의 "재시도 burst" 만 차단 + 알림 수준의 dedup 미도입.

**SRE 표준 (정합 비교)**:
- prometheus alertmanager 의 `repeat_interval` (12h default) 같은 지수 backoff 또는 fixed-interval dedup.
- ops-alert.py 자체가 `_state/{vault_id}/last_failure.json` 의 `occurred_at` + 직전 알림 시각 비교 후 (예: 1시간 내 같은 reason 은 skip) 의 책임.

**v4 spec 부재**:
- ops-alert.py 의 dedup 책임 spec 없음. v4 §4.2 본문에 "스크립트 책임: `_state/*/last_failure.json` 수집 → POST. webhook 미설정 시 no-op" 만 — dedup 또는 rate limit 책임 없음.
- 즉 Step 3 구현자가 dedup 을 임의 결정 가능 (또는 안 만들 수 있음).

**왜 위험한가**:
- 야간 호출이 24/7 daemon SRE 에서 가장 큰 운영자 부담. spec 부재가 곧 회귀 위험.
- alarm fatigue → 운영자가 다음번 "진짜 fatal" 을 무시할 위험 (사회적 회피 반응).
- 이 결함은 R6 의 CRIT-R6-1 fix 가 incomplete 했다는 의미 — fix 가 fatal loop 의 한쪽 (systemd) 만 차단하고 다른 쪽 (알림 채널) 은 그대로.

**어떻게 고칠까** (spec 수준, Step 3 진입 전):
1. **v4 §4.2 ops-alert.service 의 책임 본문에 dedup spec 추가**:
   - ops-alert.py 가 `_state/{vault_id}/.alert_state.json` (또는 last_failure.json 의 `last_alerted_at` 필드) 을 read 후, 같은 reason 의 직전 알림이 N분 이내면 skip.
   - default N = 3600s (1h). 운영자 override = `operations.fatal_alert_repeat_interval_sec` yaml 키.
   - 운영자가 cursor/credentials 개입 후 last_failure.json 을 삭제 또는 reason 변경 시 자연 reset.
2. **alternative — systemd 측 RateLimit**:
   - service unit 에 `[Unit] StartLimitIntervalSec=3600 StartLimitBurst=1` 를 ops-alert.service 에 추가 (ingest service 가 아니라 ops-alert 자체에).
   - systemd 가 1시간에 ops-alert 1회만 trigger 허용 + 이후 `start-limit-hit` 로 skip. CRIT-R6-2 의 stuck 위험은 ops-alert 자체이므로 사이클 회복 시 운영자가 `reset-failed ops-alert.service` 수동 호출 — 그러나 ops-alert 의 stuck 은 fatal alarm 누락이 아니므로 acceptable.
3. **권장 = 옵션 1** — yaml 운영자 override 가능 + reset 이 last_failure.json 의 자연 변화에 묶임. systemd 내부 RateLimit 는 운영자가 reset-failed 명령을 알아야 하는 부담.

**스펙 수정 위치**: §4.2 ops-alert.service spec 본문에 dedup 책임 1단락 추가. wikihub.yaml.example §4.3 의 `operations.fatal_alert_repeat_interval_sec` 키 추가. V<N> 에 dedup 동작 검증 항목 추가.

---

### CRIT-R8-3 [SpecMismatch / Reliability] F1 §4.6.6 fatal 알림 **이중 경로** 중 Hermes-측 경로가 v4 어디에도 매핑 안 됨 — `agent.notify_on_fatal=true` 의 실 호출 책임 부재 (`analysis_and_design.md` §4.3 / F1 archive §4.6.6 L1159~1170 / ADR-0012 L41)

**무엇이**: F1 archive §4.6.6 L1159~1170 의 fatal 알림 동작 우선순위:

```
VaultSyncFatal 발생
   │
   ├─ (1) notify_via_hermes_optional(err, cfg)   # best-effort, Hermes 살아 있어야 도달
   ├─ (2) notify_via_systemd_onfailure(err)       # 항상 영속화. systemd가 후속 발동
   └─ sys.exit(2)
                 │
                 ▼ (systemd가 인지)
           ops-alert.service 트리거 → webhook 전송
```

F1 정본은 **두 경로 모두 best-effort**:
- 경로 (1) Hermes-측: `agent.notify_on_fatal=true` 일 때 sync.py 가 Hermes 의 oneshot subprocess (`hermes -z "/ops alert ..."`) 로 직접 알림 trigger. Hermes 채널 (Telegram bot polling) 로 즉시 도달.
- 경로 (2) systemd-측: `last_failure.json` write + ops-alert.service trigger.

ADR-0012 L41:
```yaml
notify_on_fatal: true         # ADR-0002·F1 §4.6.6
```

v4 의 wikihub.yaml.example §4.3 L691: `notify_on_fatal: true` — yaml 키만 존재. 그러나:
- v4 §4.2 service template 에 Hermes-측 알림의 systemd 측 책임 (예: `[Service] Environment=AGENT_NOTIFY_ON_FATAL=true` 또는 sync.py 가 yaml read 후 자체 trigger) 미명시.
- v4 §5 의 lift 매트릭스에 ADR-0012 의 `notify_on_fatal` 항목 매핑 없음.
- F3 의 `scripts/lib/sync.py` 또는 `vault-fetch.py` 가 Hermes-측 notify 호출하는지 확인:
  ```
  $ grep -rn "notify_via_hermes\|notify_on_fatal" /Users/1004790/workspace/wikihub/scripts/
  # (출력 없음)
  ```
  즉 **F3 도 Hermes-측 notify 책임을 구현 안 함**.

**결과**: v0.1.0 운영에서 fatal 사건 발생 시:
- Hermes 채널 (Telegram bot) 로 즉시 알림 — **도달 안 함** (코드 부재).
- ops-alert.service 가 last_failure.json read → webhook POST — **도달 안 함** (CRIT-R8-1 의 producer 부재).

즉 **fatal 알림 0건 도달** — v0.1.0 acceptance 의 silent failure 다중점 회귀.

**왜 위험한가** (운영 시점):
- 운영자가 "어? sync 가 멈춰 있는데 알림이 왜 안 오지?" → systemctl --user status 수동 확인이 마지막 안전망 (F1 §4.6.6 L1172) → 운영자가 daemon 운영 표면을 매일 polling 하는 부담.
- 본 결함은 CRIT-R8-1 과 결합 시 fatal 알림 채널 전체가 dead — 24/7 SRE 표준의 가장 큰 결함 형태.

**어떻게 고칠까** (Step 3 진입 전 spec lock):
1. **v4 §5 lift 매트릭스에 ADR-0012 `notify_on_fatal` 항목 추가** — F3 후속 또는 F4 의 책임 명시:
   - F3 의 `scripts/lib/sync.py` 또는 `vault-fetch.py` 의 fatal handler 가 (a) Hermes-측 oneshot notify, (b) systemd-측 last_failure.json write 둘 다 호출.
   - 본 책임이 F3 의 잔존 결함이면 F3 후속 light feature 로 분기 + v4 §6 의 V<N> 에 "fatal 이중 경로 도달 검증" 추가.
2. **CRIT-R8-1 + CRIT-R8-3 통합 — fatal handler 의 책임 명세 ADR 발의**:
   - ADR-0024 (가칭) — "fatal 알림 이중 경로 contract: Hermes notify (best-effort) + last_failure.json write (always) + ops-alert dedup".
   - F3 의 fatal handler 가 호출하는 두 함수 (`notify_via_hermes_optional`, `notify_via_systemd_onfailure`) 의 contract + ops-alert.py 의 input contract 모두 본 ADR 에서 lock.
3. **v0.1.0 의 minimal acceptable**: 경로 (2) systemd-측만 구현하고 (1) Hermes-측은 v0.2.x 로 명시 deferred. 단 v4 본문이 "둘 다 best-effort, 운영자가 systemctl 수동 확인이 최종 안전망" 을 명시.

**스펙 수정 위치**: §4.3 yaml.example 의 `notify_on_fatal` 주석에 "v0.1.0 미구현 — F3 후속" 또는 "F4 spec 확장" lock. §5 lift 매트릭스에 ADR-0012 매핑 추가. §6 V<N> V14·V15 추가.

---

## 2. HIGH (Step 3 진입 전 spec 보강)

### HIGH-R8-1 [SpecMismatch / Idempotency] `bootstrap_allowed` 환원의 atomic write 책임 — F3 `lib/state.py` 의 fsync 패턴과 정합 미명시 (`analysis_and_design.md` §3.5 [E] L216~219, §4.4 4.5.1 step 4 / `scripts/lib/state.py` L23~39)

**무엇이**: v4 §3.5 [E] L216~219 / §4.4 4.5.1 step 4:
> "`wikihub.yaml` 의 해당 vault `bootstrap_allowed: true` → `false` 로 atomic write. yaml writer 는 `/wh:setup` 의 새 책임 (Step 3 구현 시 `scripts/lib/config_writer.py` 또는 `/wh:setup` 자체 helper)."

F3 결과물의 `scripts/lib/state.py` L23~39 의 atomic write 패턴:
```python
# HIGH-R4-1: fsync 추가 — OCI ARM unexpected reboot 시 zero-length 파일 회피.
# `os.replace` 는 rename 만 atomic — tmpfile 내용 자체의 disk durability 는 fsync 가 보장.
...
os.fsync(f.fileno())
```

**v4 의 결함**:
- "atomic write" 라고만 명시하고 **fsync 의무화 안 함**. F3 의 R4 라운드에서 OCI ARM unexpected reboot 시 zero-length 파일 회귀를 잡았는데 (HIGH-R4-1), v4 의 yaml writer 가 같은 패턴을 lift 하는지 미보장.
- yaml writer 가 fsync 누락 시 OCI 의 unexpected reboot (host migration 도중 등) 가 `bootstrap_allowed: true` 인 채로 reset 가능 → 다음 사이클에서 vault-fetch.py 가 또 bootstrap 모드 진입 (cursor 있는데 bootstrap_allowed=true).
- F3 의 vault-fetch.py 가 이런 inconsistent state 를 fatal 처리하는지 retryable 처리하는지 미확인 (v4 §3.5 L219 가 "F3 의 sync 가 bootstrap 가드로 fatal 발생" 으로 추정 명시만).

**왜 위험한가**:
- OCI free tier 가 host migration 빈번 → 부분 yaml write 잔존 가능성 production 확률 0 아님.
- silent recovery 시 운영자가 "왜 첫 ingest 가 다시 prompt 되지?" 또는 "왜 bootstrap 모드로 재실행되지?" 디버깅 시 OCI reboot timestamp 와 yaml mtime 의 cross-check 필요 — 운영 디버깅 비용.

**어떻게 고칠까** (spec 수준):
- v4 §4.4 4.5.1 step 4 에 "yaml writer 는 F3 의 `lib/state.py:_atomic_write_json` 의 fsync 패턴을 lift (`os.fsync(f.fileno())` 포함)" 명시.
- 또는 `scripts/lib/config_writer.py` 를 신설하지 말고 기존 `lib/state.py` 의 atomic write helper 를 yaml writer 에도 재사용 — DRY + 검증된 패턴 lift.
- §4.4 4.5.3 의 §`실패 처리` 표에 "yaml writer 의 fsync 실패" 분기 추가 (현재 "yaml writer 실패" 만 — fsync 부재 시 lost write).

---

### HIGH-R8-2 [SpecMismatch] F2 setup.md L54 의 치환 변수 목록이 v4 새 변수 (`{venv_path}`, `{credentials_path}`, `{wikihub_home}`) 갱신 안 됨 — `/wh:setup` Python helper 가 어디서 read 하는지 미명시 (`analysis_and_design.md` §4.2 / `_system/commands/setup.md` L54~60)

**무엇이**: F2 setup.md L54~60 의 치환 변수 목록 (정본):
```
- {vault_id}, {sync_interval_sec}, {lint_interval_hours},
  {instance_root}, {agent_invocation}, {skill_prefix}
```

v4 §4.2 의 service template 이 추가로 사용하는 새 변수:
- `{venv_path}` (Environment=PATH, ExecStart of ops-alert)
- `{credentials_path}` (Environment=GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE)
- `{wikihub_home}` (ExecStart of ops-alert.service)

**v4 의 incomplete lift**:
- v4 §4.2 가 service template 에서 새 변수 사용 — 그러나 setup.md L54 의 정본 목록 갱신 spec 없음.
- v4 §4.3 venv 경로 사이드카 `.venv_path` 만 명시 — credentials_path / wikihub_home 의 source 미명시.
- credentials_path source: wikihub.yaml.vaults[*].options.credentials_path (per-vault) — 이 경우 vault별 unit 마다 다른 Environment 라 B2 substitution 자연. 하지만 **`~` expansion 책임이 누가 갖는지 미명시** — yaml read 측 (Python helper) 인지 systemd Environment= 인지. systemd `Environment=` directive 는 `~` expansion 미지원 → Python helper 가 `os.path.expanduser` 먼저 호출 후 substitution 해야 함.
- wikihub_home source: install.sh 가 `~/wikihub` 에 clone 한 위치 — `/wh:setup` 이 어디서 read 하는지 미명시 (`.venv_path` 와 같은 사이드카가 필요 vs `WIKIHUB_HOME` env vs hardcode).

**왜 위험한가**:
- Step 3 구현자가 새 변수 substitution 을 임의 결정 → systemd unit 의 ExecStart 또는 Environment 가 unexpanded literal (`~/...`) 채로 작성될 위험.
- systemd 가 `~/` literal 을 home 으로 expand 안 함 → ExecStart 실패 → 운영자가 "왜 ops-alert.service 가 안 도는지" 디버깅 시 systemd-analyze verify 부재 시 surface 어려움.

**어떻게 고칠까**:
- v4 §4.4 4.5.3 의 setup.md 갱신 폭 단락에 "L54 의 치환 변수 목록에 `{venv_path}`, `{credentials_path}`, `{wikihub_home}` 추가 + 각각의 source (사이드카 / yaml / 사이드카) 명시" 추가.
- v4 §4.3 venv 사이드카 spec 옆에 `.wikihub_home` 사이드카 또는 install.sh 가 `~/wikihub/.install_marker` 에 wikihub_home 자체를 기록 — `/wh:setup` 이 본 marker 의 위치로 cwd 추정.
- credentials_path 의 `~` expansion: Python helper 의 substitution 시 `pathlib.Path(value).expanduser()` 호출 후 string 화 lock.

---

### HIGH-R8-3 [Reliability / OperationalRisk] `/wh:setup --enable` 재호출 시 boot 보류된 vault 의 prompt 재진입 분기 부재 (`analysis_and_design.md` §3.5 [E] v4 순서 역전 / §4.4 4.5.1)

**무엇이**: v4 §3.5 [E] L208~210 의 새 흐름:
> "4. 첫 ingest 성공한 vault 만 `systemctl --user enable --now <vault_id>-ingest.timer` 호출. 실패한 vault 는 unit 파일은 남기되 timer enable 보류 — 운영자가 진단 후 수동 enable."

운영 시나리오 (5 vault, 1 fatal):
- 09:00 `/wh:setup --enable` 호출
- vault A·B·C·D 성공 → timer enable
- vault E 의 first ingest 가 exit 2 → timer enable 보류 + 안내 "수동 enable 권장"
- 10:00 운영자가 vault E 의 credentials 수정 후 `/wh:setup --enable` 재호출

**v4 의 spec gap**:
- 재호출 시 vault A~D 의 prompt 가 다시 뜨는가? v4 §4.4 4.5.1 의 "입력 조건" L711 = "enabled vault 중 `bootstrap_allowed: true` 인 vault 가 1개 이상". A~D 는 이미 false 환원 → prompt skip. E 는 true (운영자가 수동 reset 안 했으면) → prompt 진입. 정합.
- 그러나 **운영자가 vault E 의 yaml 만 수정 후 호출 시 prompt 가 모두 skip 될 위험**: 운영자가 첫 호출 후 vault E 의 bootstrap_allowed 를 다시 true 로 수정 안 하면 — 그리고 v4 가 timer enable 보류 시 bootstrap_allowed 환원 안 함 (왜냐하면 exit 2 시 환원은 안 함, v4 §4.4 4.5.3 의 "Step 6 yaml writer 실패" 와 다른 분기) — 그러면 vault E 의 bootstrap_allowed 는 여전히 true → prompt 재진입 가능. 정합.
- **결함**: 운영자가 vault E 의 timer 를 수동 enable (`systemctl --user enable --now <E>-ingest.timer`) 한 후 `/wh:setup --enable` 재호출 안 한다면 → bootstrap_allowed 가 true 인 채로 timer 가 매 사이클마다 bootstrap 모드로 vault-fetch 호출 → cursor 있는데 bootstrap mode 진입의 inconsistent state. v4 §3.5 L219 가 "F3 의 sync 가 bootstrap 가드로 fatal 발생" 추정만.

**왜 위험한가** (운영 디버깅 비용):
- 운영자 수동 enable 후 첫 사이클이 fatal — 운영자가 "왜 fix 후에도 fatal 이지?" 디버깅 시 bootstrap_allowed 환원 누락이 표면화 안 됨 (yaml 한 줄, hide-in-plain-sight).
- v4 의 흐름 역전 fix 가 "수동 enable" 분기에서 정합 깨짐 — fix 자체가 운영자의 정상 회복 경로를 끊은 회귀.

**어떻게 고칠까**:
- v4 §4.4 4.5.1 step 5 의 timer enable 직전 또는 직후에 bootstrap_allowed 환원 책임을 명시 — exit 0 / 75 시만 환원 (현재 spec), 수동 enable 시는 별도 책임 매트릭스 필요.
- 또는 vault-fetch.py 가 bootstrap mode + cursor 존재 + bootstrap_allowed=true 의 inconsistent state 를 detect 시 fatal 대신 warning + bootstrap mode 자동 skip (= incremental mode 진입) + last_sync.json 에 self-heal 기록. F3 후속 또는 본 F4 의 책임 확장.
- 또는 운영자 안내 강화 — v4 §4.4 4.5.3 의 "Step 6 첫 ingest exit 2" 행에 "운영자 수동 enable 전 yaml 의 bootstrap_allowed: false 환원 필수" 명시.

---

### HIGH-R8-4 [OperationalRisk] OCI host migration 시 user systemd manager 의 fd 유지 보장 미명시 — V12 검증 항목 부족 (`analysis_and_design.md` §3.4 [D] / §6 V12)

**무엇이**: v4 §6 V12:
> "OCI ARM Ubuntu 인스턴스 (macOS dev box 검증 불가) 에서 `sudo reboot` 후 5분 내 timer fire + last_sync.json 진행 관찰"

V12 가 검증하는 시나리오:
- `sudo reboot` — graceful shutdown + 명시적 boot.
- 그러나 OCI free tier 의 host migration 또는 OCI hypervisor 의 panic 시 시나리오는 **다른 fail mode**:
  - host migration: VM 상태 (memory + fd + sockets) 가 새 host 로 transfer 또는 cold boot.
  - hypervisor panic: 가상 VM 의 power-cycle (uncoordinated shutdown).
- D1 (user-level + linger) 의 invariant 가 두 fail mode 에서도 작동하는가?

**v4 spec 부재**:
- §3.4 [D] 의 V12 fail mode 4건 (i)·(ii)·(iii)·(iv) 명시. 그 중 (iii) = "OCI 의 host migration 이 user session 끊으면서 linger 무효화". 그러나 **V12 검증 절차가 host migration 시뮬레이션 안 함** — `sudo reboot` 만.
- OCI 의 host migration 은 운영자가 trigger 불가 (OCI 측이 maintenance window 안에서만 발생). 즉 V12 가 "검증 완료" 라고 마킹돼도 host migration 시 invariant 보장 안 됨 — silent 정합 결함.

**왜 위험한가**:
- v0.1.0 acceptance ("OS reboot 후 사람 개입 없이 자동 재기동") 가 host migration 도 cover 한다고 plan.md L8 명시 ("maintenance reboot, OCI host migrate, unexpected power-off 모두 포함"). V12 검증이 그 중 1개만 cover.
- host migration 발생 시 (예: OCI free tier ARM 의 maintenance) silent failure → 운영자 인지 어려움.

**어떻게 고칠까** (spec 수준):
- V12 의 검증 절차에 "host migration 또는 unexpected power-off" 시뮬레이션 추가: OCI Console 의 "Stop instance (force)" 후 "Start" 로 cold-boot 재현. 또는 `echo b > /proc/sysrq-trigger` (SysRq 강제 reboot — kernel panic 시뮬레이션).
- V12 가 fail mode 별 별도 sub-verification (V12a graceful, V12b uncoordinated, V12c host-migration-proxy) 으로 분리.
- ADR-0021 본문에 "OCI host migration 의 fail mode 별 fallback 시점 + D2 회귀 trigger 조건" 명시.

---

### HIGH-R8-5 [DesignGap / SpecMismatch] F1 §4.8.5 (로깅·관측) lift 부재 — install.sh / /wh:setup 의 자체 log 라우팅 미정 (`analysis_and_design.md` §4.1 / R6 MED-R6-4 의 v4 미반영)

**무엇이**: F1 archive §4.8.5 (L1515~1520) 정본:
> "stdout/stderr: logging.dir 하위 파일로 append + systemd journal (이중 라우팅 여부는 F4 에서 단일 선택). journal 활용: journalctl --user -u {unit} --since '1 hour ago' 으로 timer 사이클별 결과 추적"

R6 MED-R6-4 의 권고: install.sh 자체의 log file 정책 (`~/.local/share/wikihub/install.log` 자체 append).

**v4 의 incomplete lift**:
- v4 §4.2 의 service template 에 `StandardOutput=` / `StandardError=` directive 없음 — systemd 의 default = journal. F1 의 "단일 선택" 결정이 v4 어디에도 없음.
- v4 §4.1 install.sh 의 자체 log 정책 부재 — R6 MED-R6-4 의 권고 미반영.
- install.sh 가 curl-pipe 모드일 때 운영자 terminal close 시 log lost → 운영 trail 부재.
- ops-alert.service 가 발동돼도 ops-alert.py 의 stdout/stderr 가 어디로 가는지 미명시 — journal default 추정만. F1 L1445~1446 은 `/opt/wikihub/logs/ops-alert.log` append — v4 는 미언급.

**왜 위험한가**:
- 24/7 daemon 의 가장 기본 SRE 요구 = 모든 운영 event 의 trail. 부분 표면화 시 incident postmortem 불가.
- v4 의 lift 가 unit template 본문만 — F1 §4.8.5 의 결정 (logging.dir 단일 vs journal 이중) 미해소.

**어떻게 고칠까**:
- v4 §4.2 service / timer / ops-alert.service template 모두에 `StandardOutput=journal` + `StandardError=journal` 명시 (F1 의 단일 선택을 journal 로 lock — file append 는 v0.2.x 의 logging.dir 관측 도구 결정에 위임).
- v4 §4.1 Step 0 또는 Step 1 에 install.sh 자체 log: `exec > >(tee -a "$HOME/.local/share/wikihub/install.log") 2>&1` lift (R6 MED-R6-4 의 권고 채택).
- ADR-0021 또는 신규 ADR (예: ADR-0024 — logging routing) 발의.

---

### HIGH-R8-6 [DesignGap] lint·disk-watch unit 의 v4 정본화 부재 — "후속 §4.6 으로 정의" 만 (`analysis_and_design.md` §4.2 L648)

**무엇이**: v4 §4.2 L648:
> "lint·disk-watch unit 도 동일 패턴으로 별도 template (Step 3 에서 본 draft 와 함께 작성). lint 는 timer interval = `operations.lint_interval_hours`. disk-watch 는 F4 의 별도 §4.6 으로 후속 정의 (`operations.disk.*` 활성 시만)."

**v4 의 incomplete spec**:
- F2 setup.md L50 정본: "단일 `lint.service` + `lint.timer`, 단일 `ops-alert.service`, 조건부 (operations.disk.* 활성): `disk-watch.service` + `disk-watch.timer`".
- v4 §4.2 가 vault-ingest + ops-alert 만 정본 — lint / disk-watch 는 "동일 패턴" 으로만 위임 + disk-watch 는 "§4.6 후속" — 그러나 v4 본문에 §4.6 자체가 없음 (§4.5 가 끝).
- §6 V<N> 의 V13 등에도 lint 의 첫 enable 검증 없음. v4 §3.5 L210 = "lint.timer / ops-alert.service 는 항상 enable" — 그러나 lint.service / lint.timer template 의 spec 없음.

**왜 위험한가**:
- Step 3 구현자가 lint unit 의 ExecStart / SuccessExitStatus / TimeoutStartSec 를 임의 결정 → vault-ingest 와 다른 정책 표면 (예: lint 에 `Restart=on-failure` 회귀 시 R6 의 CRIT-R6-1 회귀).
- disk-watch 의 spec 부재 → operations.disk.* 활성 시 운영자가 enable 못 함.

**어떻게 고칠까**:
- v4 §4.2 에 lint.service / lint.timer / disk-watch.service / disk-watch.timer template 4건 모두 명시 (F1 archive §4.8.2 L1456~1486 의 disk-watch 정본 lift 가능).
- 또는 §4.2.x 신설로 본 4 unit 의 spec 분리 + "vault-ingest 와 동일 정책 — SuccessExitStatus=0 75, Restart= 미설정, OnFailure=ops-alert.service" 명시.
- §6 V<N> 에 lint timer + (조건부) disk-watch timer 의 첫 enable + 사이클 검증 추가.

---

### HIGH-R8-7 [Reliability / OperationalRisk] Step 6 SLA 미정의 — 60s prompt timeout + 15min first ingest 의 운영자 대기 부담 (`analysis_and_design.md` §4.4 4.5.1 / §4.2 TimeoutStartSec)

**무엇이**: v4 §4.4 4.5.1 step 1:
> "vault 'gdrive' 의 첫 ingest 를 지금 실행하시겠습니까? [Y/n] (default Y, 60s timeout → Y)"

v4 §4.2 service template: `TimeoutStartSec=15min`.

운영 시나리오 (vault 3개, 평균 first ingest = 5min):
- 09:00 운영자가 `/wh:setup --enable` 호출 → vault gdrive prompt 60s 대기 (또는 즉시 Y)
- 09:00:30 Y → vault-fetch.py --bootstrap gdrive 5min
- 09:05:30 종료 → vault nas prompt 60s
- 09:06:30 Y → vault-fetch.py --bootstrap nas 10min
- 09:16:30 종료 → vault dropbox prompt 60s
- 09:17:30 Y → vault-fetch.py --bootstrap dropbox 15min (timeout)

**v4 의 SLA 결함**:
- 운영자가 `/wh:setup --enable` 호출 후 30~45분 동안 SSH 세션 holding. 야간/장거리 SSH 시 broken pipe 위험.
- prompt 가 vault 별로 직렬 (4.5.1 step 1 "vault 별로 한 번") → 첫 vault 처리 중 다음 vault prompt 대기.
- v4 본문에 "Step 6 자체의 max duration" 또는 "background mode" spec 없음.

**왜 위험한가**:
- 운영자가 SSH 세션 holding 동안 connection drop 시 `/wh:setup` process group 이 어디로 가는가? hangup 시 ingest 중단 + 다음 vault 의 prompt 미진입.
- 또는 운영자가 `--run-first-ingest` flag 로 비대화 모드 진입 시 30~45분 silent — fail-loud 원칙 위반.

**어떻게 고칠까**:
- v4 §4.4 4.5.1 에 "Step 6 의 max duration = vault 수 × TimeoutStartSec + 60s × vault 수" 추정 + 운영자 안내 (예: "긴 SSH 세션 — tmux/screen 권장" 또는 "background 진행").
- 또는 Step 6 의 동작을 "prompt 모두 받은 후 background 로 첫 ingest 실행 + nohup 패턴 + 결과는 journal 또는 progress 파일" 로 spec 분기.
- v4 §6 V13 에 "Step 6 의 SSH disconnect 시 동작" 검증 추가.

---

### HIGH-R8-8 [SpecMismatch] ops-alert.sh → ops-alert.py 변경의 ADR 부재 — F1 archive 의 결정 lift 가 silent (`analysis_and_design.md` §4.2 / F1 archive §4.8.2 L1443)

**무엇이**: F1 archive §4.8.2 L1443:
```ini
ExecStart=/opt/wikihub/scripts/ops-alert.sh
```

v4 §4.2 ops-alert.service:
```ini
ExecStart={venv_path}/bin/python {wikihub_home}/scripts/ops-alert.py
```

**v4 의 결정 lift 추적 부재**:
- F1 의 `.sh` 가 v4 에서 `.py` 로 변경됨. 이는 결정 — venv 의존 + Python 으로 yaml + webhook POST + dedup 처리 가능. 그러나 **v4 §3 결정 목록 8건 [A]~[H] 어디에도 ops-alert 의 언어 선택 결정 없음**.
- v4 §5 lift 매트릭스에도 본 결정 매핑 없음.
- 운영 결과: venv 손상 시 (예: pip install 실패 시 venv 의 site-packages 가 partial) ops-alert.py 도 import 실패 → silent (ops-alert.service exit 1) → systemd 의 OnFailure recursion 안 됨 (의도) 이지만 운영자 알림 부재.
- F1 의 `.sh` 패턴은 venv 무관 → 본 회귀 fail mode 가 venv 와 묶이지 않음.

**왜 위험한가**:
- ops-alert.service 의 단일 책임 = fatal 알림 전달. 본 service 자체가 venv 의존 시 venv 손상 → fatal 알림 silent + venv 손상은 fatal 알림 trigger 대상이 아님 (운영자가 install.sh 수동 호출 단계).
- 즉 v4 의 결정 (Python 채택) 이 운영 fail mode 표면을 늘렸음 — F1 의 sh 패턴이 의도적 minimal 의존이었던 가능성.

**어떻게 고칠까**:
- v4 §3 에 결정 [I] 또는 [J] (ops-alert 언어 선택) 명시 lock + ADR 발의 (예: ADR-0025 — ops-alert 언어/의존 모델).
- 옵션 A: `.py` 유지 + venv 손상 시 fallback sh 별도 emit ("ops-alert-fallback.sh" 가 `[Service] OnFailure=ops-alert-fallback.service` 추가).
- 옵션 B: `.sh` 회귀 (F1 정합) + minimal `curl` + `jq` 의존 — venv 무관. dedup 책임은 `flock` + `find -mtime` 패턴으로 구현 가능.
- v4 §3 에 본 결정 + 본 trade-off 명시.

---

## 3. MED (Step 3 도중 또는 자가 검증)

### MED-R8-1 [Observability] Step 6 의 prompt 가 background mode 또는 비대화 mode 진입 시 progress 보고 부재 (`analysis_and_design.md` §4.4 4.5.1~4.5.2)

비대화 모드 (`--run-first-ingest`) 시 30~45분 silent — vault 별 progress (예: "vault gdrive: 5min elapsed, 50 files processed") 가 stdout 또는 progress 파일에 emit 되지 않음. v4 4.5.1 step 2 의 "stdout JSON 보고" 는 vault-fetch.py 종료 후만 — 진행 중 보고 없음.

**fix**: 4.5.1 step 2 에 "vault-fetch.py 의 progress stdout 을 `/wh:setup` 이 그대로 forward (line-buffered)" 또는 "background mode 시 `_state/<vault>/setup_progress.json` 주기적 write" 명시.

---

### MED-R8-2 [Reliability] `vault-fetch.py --bootstrap` 의 fcntl.flock 이 `/wh:setup` Step 6 의 첫 호출에서 잡힘 — 운영자가 동시에 timer enable 시 race (`analysis_and_design.md` §4.4 4.5.1 / `scripts/vault-fetch.py` L100)

vault-fetch.py L100 의 `fcntl.flock(LOCK_EX|LOCK_NB)` 가 state_dir/.lock 에 걸려 있음. Step 6 의 `vault-fetch.py --bootstrap` 호출이 lock 보유 중 — 운영자가 별도 터미널에서 동일 vault 의 timer 를 `systemctl --user start <vault>-ingest.service` 수동 호출하면 LOCK_NB 실패 → vault-fetch.py 가 즉시 exit 75 (VaultSyncRetryable). 정합이지만 운영자 인지 어려움.

**fix**: v4 §4.4 4.5.1 step 2 의 안내에 "Step 6 진행 중 동일 vault 의 systemctl --user start 수동 호출은 lock conflict 로 exit 75" 명시.

---

### MED-R8-3 [Security] credentials_path 의 `~` expansion 시 운영자 user 와 service user 의 정합 (`analysis_and_design.md` §4.2 / §3.4 [D])

v4 §4.2 Environment=GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE={credentials_path}. `~/wikihub-instance/.credentials/token_gdrive.json` 의 `~` 가 어느 user 의 home 인가:
- D1 (user-level + linger): `~` = 운영자 user (예: ubuntu). credentials owner = ubuntu, chmod 600 → systemd user manager (ubuntu) 가 read 가능. 정합.
- D2 fallback (system-level + service user `wikihub`): `~` = service user wikihub 의 home (/home/wikihub 또는 /opt/wikihub). 운영자가 dev box 에서 scp 시 owner = 운영자 user (ubuntu) → service user (wikihub) read 불가 (chmod 600 owner-only). D2 마이그레이션 절차에 owner 변경 명시 (§3.4 [D] u5 d) 하지만 **운영자의 scp 절차 갱신 미명시**: dev box → server scp 후 ssh 로 `sudo chown wikihub:wikihub /home/wikihub/wikihub-instance/.credentials/token_gdrive.json` + `sudo chmod 600 ...` 추가.

**fix**: §3.4 [D] D2 fallback 절차에 운영자 scp 후 chown 명령 명시.

---

### MED-R8-4 [Reliability] `daemon-reload` 후 unit 변경 직후의 timer fire 보장 (`analysis_and_design.md` §4.4 4.5.1 step 4~5)

v4 4.5.1 step 5 의 `systemctl --user enable --now <vault>-ingest.timer` 호출 직전에 step 4 의 `daemon-reload` 안 했으면 unit 변경이 systemd 에 미반영. 그러나 v4 §3.5 L207 = "systemd unit 파일 *작성* + daemon-reload (Step 2·4)" — 즉 daemon-reload 는 step 2~4 사이에 이미 호출. 정합.

다만 **첫 ingest 실패 후 운영자가 yaml 수정 + `/wh:setup --enable` 재호출 시 unit 파일 재작성 + daemon-reload 의 멱등성**: v4 §4.4 4.5.3 의 멱등 보장 단락 미명시 (setup.md L154 의 "unit 파일은 매번 덮어쓰기" 정본 lift 만).

**fix**: 4.5.1 의 멱등 동작 1단락 명시.

---

### MED-R8-5 [Reliability] `--branch <ref>` 가 `latest` 외 ref (예: `main`) 사용 시 clean install 의 변경 추적 부재 (`analysis_and_design.md` §4.1 Step 2)

`BRANCH="${BRANCH:-latest}"` + `git clone --branch "$BRANCH" --depth 1`. 운영자가 베타 테스트 시 `--branch main` 으로 호출하면 매 install 마다 main 의 HEAD (mutable) 를 clone — 운영자가 "어느 commit 으로 설치됐는지" 추적 어려움.

**fix**: install.sh Step 2 의 clone 직후 `cd "$WIKIHUB_HOME" && git rev-parse HEAD` 결과를 `~/wikihub/.install_commit` 사이드카에 기록 + Step 8 안내에 표시.

---

### MED-R8-6 [Observability] systemd-analyze verify 자가 검증 부재 (`analysis_and_design.md` §4.2)

v4 §4.2 의 service / timer template 의 syntax 정합을 Step 3 구현 직후 검증할 도구 미명시. `systemd-analyze --user verify ~/.config/systemd/user/{unit}.service` 가 OCI 의 표준 도구. 운영 invariant.

**fix**: §4.4 4.5.1 step 2 또는 §6 V<N> 에 "systemd-analyze --user verify 모든 unit" 검증 단계 추가. /wh:setup 의 step 4 직후 자동 호출 가능.

---

### MED-R8-7 [Reliability] `Step 2·4` numbering 충돌 — v4 §3.5 L207 vs §4.4 4.5.1 의 step 번호 어긋남 (`analysis_and_design.md` §3.5 L207 / §4.4 4.5.1)

v4 §3.5 L207 = "systemd unit 파일 작성 + daemon-reload (Step 2·4)". v4 §4.4 4.5.1 의 step 번호 = step 1~5 (별개 체계). 두 번호 체계가 동시 사용 — 독자 혼란.

**fix**: §3.5 의 "Step 2·4" 표기를 setup.md 의 정본 Step 번호 (1~5 + 신설 6) 로 통일.

---

## 4. LOW / NIT

### LOW-R8-1 [DocMismatch] v4 §4.4 의 sub-section 번호 (`#### 4.5.1`) 와 §4.4 표기 불일치 (`analysis_and_design.md` §4.4 / §4.5)

v4 §4.4 의 header = "### 4.4 `_system/commands/setup.md` Step 6 spec (v4 신설 — R5 §2.7)". 그 안의 sub-section header = `#### 4.5.1`, `#### 4.5.2`, `#### 4.5.3` — §4.4 인데 4.5.x 번호. §4.5 `scripts/auth_gdrive.py` 와 충돌.

**fix**: §4.4 의 sub-section 을 `#### 4.4.1`, `#### 4.4.2`, `#### 4.4.3` 로 수정.

---

### LOW-R8-2 [Observability] §4.2 service / timer template 에 `StandardOutput=` directive 부재 — HIGH-R8-5 의 sub-항목

(HIGH-R8-5 와 통합 처리 가능 — 본 항목 별도 issue 아님)

---

### NIT-R8-1 [Docs] §1 의 "F1·F2·F3 archive" 참조에 `features/archive/` 경로 표기 — v4 §9 참조 단락과 정합 (`analysis_and_design.md` §9 L851)

§9 = "features/archive/20260513_v030_initial_architecture/" 정확 표기. §1 본문 = "F1 archive" 추상 — 첫 진입 독자에게 경로 부재. minor.

---

### NIT-R8-2 [Docs] `loginctl enable-linger` 의 sudo 필요 표기가 §4.1 Step 1 (sudo pre-check) 과 Step 7 (실 호출) 두 군데에 분산 — 단일 단락으로 통합 권장

---

## 5. v4 fix 정합성 평가 (R5·R6 권고 vs v4 실제 lock)

| 라운드 | 권고 ID | 권고 요지 | v4 lock 여부 | 평가 |
|---|---|---|---|---|
| R5 | §2.1 | `{venv_path}` source 명시 | 부분 (사이드카 `.venv_path`) | `{credentials_path}`, `{wikihub_home}` 미해소 → HIGH-R8-2 |
| R5 | §2.2 | Step 0 PIPE_MODE export 누락 무한루프 | 완전 (`$BASH_SOURCE[0]` 단독) | OK |
| R5 | §2.3 | `--update` flag 의미 lock | 완전 (제거) | OK |
| R5 | §2.7 | setup.md Step 6 spec | 완전 (§4.4 신설) | 단 sub-section 번호 LOW-R8-1, SLA 미정 HIGH-R8-7 |
| R5 | §2.8 | bootstrap_allowed 환원 책임 | 부분 (책임자 명시) | fsync 정합 미명시 → HIGH-R8-1 |
| R5 | §2.13 | RestartPreventExitStatus / SuccessExitStatus | 완전 (SuccessExitStatus=0 75) | OK |
| R5 | §2.14 | GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE env | 완전 | OK (단 `{credentials_path}` source HIGH-R8-2) |
| R6 | CRIT-R6-1 | exit 2 무한 재시도 | 완전 (Restart= 제거) | spec 수준 OK. 단 알람 채널 fatal loop 옮김 → CRIT-R8-2 |
| R6 | CRIT-R6-2 | StartLimit stuck | 완전 (Restart= 제거로 limit 우회) | OK |
| R6 | CRIT-R6-3 | 첫 ingest fatal loop | 완전 (흐름 역전) | 단 운영자 수동 enable 분기 결함 → HIGH-R8-3 |
| R6 | HIGH-R6-3 | OnBootSec 60s → 2min | 완전 (2min) | OK |
| R6 | HIGH-R6-6 | OnUnitActiveSec → OnUnitInactiveSec | 완전 | OK |
| R6 | HIGH-R6-7 | TimeoutStartSec + OnFailure + ops-alert spec | 부분 | ops-alert.service 정의는 OK, 그러나 producer 부재 → CRIT-R8-1, Hermes 이중 경로 부재 → CRIT-R8-3 |
| R6 | HIGH-R6-4 | mutable tag 위협 모델 | 완전 (§3.8 매트릭스) | OK |
| R6 | MED-R6-4 | install.sh log file 정책 | **미반영** | HIGH-R8-5 로 격상 (24/7 daemon SRE 표준) |

**판정**:
- R5 의 5건 CRIT lock 모두 완전 — v4 가 R5 권고를 충실히 반영.
- R6 의 CRIT 3건 spec 수준 완전 — 그러나 **fix 가 새로운 결함 표면을 만들었다**:
  - CRIT-R6-1 fix → CRIT-R8-2 (알람 채널 fatal loop)
  - CRIT-R6-3 fix → HIGH-R8-3 (수동 enable 분기)
  - HIGH-R6-7 fix → CRIT-R8-1 + CRIT-R8-3 (ops-alert 의 input 부재 + Hermes 경로 부재)
- R6 의 MED 8건 중 MED-R6-4 (install.sh log) 미반영 — 본 라운드에서 HIGH-R8-5 로 격상.
- R6 의 HIGH-R6-8 (multi-vault 직렬화) v4 반영 여부 — §4.2 본문에 "v0.1.0 시점에는 미영향" 추정만 — partial. MED 또는 LOW 로 잔존.

**v4 의 incomplete lift 패턴**:
- F1 archive §4.8.2 의 unit ini 패턴 → 완전 lift (CRIT-R6-1·6·7 해소).
- F1 archive §4.8.5 (로깅·관측) → **lift 부재** (HIGH-R8-5).
- F1 archive §4.8.3 (Overlap 방지 검증 표) → v4 본문 미인용 (단 spec 수준은 oneshot 으로 자연 보장 — 회귀 위험 낮음).
- F1 archive §4.6.6 (fatal 이중 경로) → **lift 부재** (CRIT-R8-1 + CRIT-R8-3).
- F1 archive §4.8.4 (다중 vault 직렬화) → "v0.1.0 미영향" 추정만, MED 잔존.

---

## 6. SRE 관점 강점 (R8 본인 시각)

본 검토는 결함 surface 목적이지만 다음은 production-grade SRE 표준 만족:

1. **흐름 역전 (Step 6 → timer enable)** — CRIT-R6-3 fix 의 spec lock 이 SRE 의 "fail closed" 원칙 정합. 첫 ingest 성공 전까지 timer 가 닫혀 있음 = 운영자 명시 승인 후에만 자동화 진입.
2. **`Restart=` 제거 + `SuccessExitStatus=0 75`** — systemd 와 timer 의 책임 분리 정합 + F1 archive §4.8.2 lift. exit 75 가 success 로 분류되므로 systemd 의 failure count 도 깔끔.
3. **safety guard 3개 (ADR-0023)** — 시스템 path / `.git` / origin remote 의 layered defense 가 SRE 의 destructive operation 표준 정합.
4. **`Persistent=true` + `OnBootSec=2min` + `AccuracySec=1min`** — F1 lift 가 cloud-init + network-online 의 OCI 운영 절차와 정합.
5. **`bootstrap_allowed` 자동 환원** — 운영자 책임을 spec 수준에서 자동화. R5 §2.8 의 권고 채택.
6. **`scripts/ops-alert.py` 의 venv 의존 + Python** — webhook POST + JSON parse + dedup 구현이 sh 보다 쉬움 (단 venv 손상 시 silent failure 가 HIGH-R8-8 의 trade-off).
7. **V12 fail mode 별 fallback 절차 (D2)** — disaster recovery 의 사전 정의 = SRE 표준.
8. **clean install pattern (`rm -rf` + `git clone`)** — update idempotency 가 SRE 의 "state-resetting deploy" 정합. 운영 state 분리 (`~/wikihub-instance`) 가 본 패턴의 안전 전제.

---

## 7. 종합 권고

### Step 3 진입 차단 (CRIT — v5 에서 lock 필수)

| ID | 요지 | spec 수정 위치 |
|---|---|---|
| **CRIT-R8-1** | ops-alert.py 의 input `last_failure.json` producer 부재 — F3 또는 F4 책임 명시 | §4.2 + §5 lift 매트릭스 + ADR 발의 (가칭 ADR-0024) |
| **CRIT-R8-2** | fatal loop 가 알람 채널로 이전 — ops-alert.py 의 dedup spec lock | §4.2 ops-alert 책임 본문 + yaml.example 의 `fatal_alert_repeat_interval_sec` 키 |
| **CRIT-R8-3** | Hermes-측 이중 경로 lift 부재 — `agent.notify_on_fatal` 의 실 호출 책임 명시 | §5 lift 매트릭스 + §6 V14·V15 + ADR-0024 |

### Step 3 진입 전 spec 보강 (HIGH — v5 에서 같이 처리)

| ID | 요지 |
|---|---|
| HIGH-R8-1 | bootstrap_allowed 환원의 fsync 정합 — F3 lib/state.py 패턴 lift |
| HIGH-R8-2 | setup.md L54 치환 변수 목록에 `{venv_path}`, `{credentials_path}`, `{wikihub_home}` 추가 + source 명시 + `~` expansion 책임 lock |
| HIGH-R8-3 | 운영자 수동 enable 분기의 bootstrap_allowed 정합 — vault-fetch.py 의 inconsistent state self-heal 또는 운영자 안내 강화 |
| HIGH-R8-4 | V12 의 host migration 시뮬레이션 추가 — V12a/V12b/V12c 분리 |
| HIGH-R8-5 | install.sh 자체 log 정책 + systemd unit 의 StandardOutput= directive 명시 (F1 §4.8.5 lift) |
| HIGH-R8-6 | lint·disk-watch unit 의 정본 spec 신설 — §4.2 확장 |
| HIGH-R8-7 | Step 6 SLA 정의 — max duration / SSH disconnect 분기 / background mode 옵션 |
| HIGH-R8-8 | ops-alert 언어 선택 ADR 발의 (Python vs sh) — venv 의존 trade-off |

### Step 3 도중 또는 자가 검증 (MED)

| ID | 요지 |
|---|---|
| MED-R8-1 | Step 6 progress 보고 |
| MED-R8-2 | fcntl.flock race 안내 |
| MED-R8-3 | D2 fallback scp 후 chown 명시 |
| MED-R8-4 | daemon-reload 멱등 명시 |
| MED-R8-5 | install.sh 의 `--branch` 추적 사이드카 |
| MED-R8-6 | systemd-analyze verify 자가 검증 |
| MED-R8-7 | step numbering 통일 |

### LOW / NIT

| ID | 요지 |
|---|---|
| LOW-R8-1 | §4.4 sub-section 번호 |
| LOW-R8-2 | (HIGH-R8-5 흡수) |
| NIT-R8-1 | F1 archive 참조 경로 |
| NIT-R8-2 | sudo 안내 통합 |

### 종합 판정

design v4 의 surgical lift 의도와 R5·R6 권고 채택은 production-grade 진입 방향으로 정렬되어 있다. 그러나 **CRIT 3건 — ops-alert 의 input producer 부재 (CRIT-R8-1), 알람 채널 fatal loop (CRIT-R8-2), Hermes 이중 경로 부재 (CRIT-R8-3) — 은 fatal 알림 채널 자체가 v0.1.0 운영에서 dead 가 되는 결함**이다. 이는 R6 의 CRIT-R6-1 fix 가 fatal loop 의 형태를 systemd 내부에서 알람 채널로 옮겼고 + HIGH-R6-7 fix 가 ops-alert.service 의 ini 만 lift 하고 input contract 는 미해소했기 때문이다. **F1 archive §4.6.6 의 정본 (fatal handler 의 이중 호출 + last_failure.json producer) 을 F3 의 sync.py / vault-fetch.py 에 lift 하는 후속 작업이 본 F4 의 v5 또는 F3 후속 light feature 로 분기 필수.**

알림 채널이 dead 인 24/7 daemon 의 운영 시나리오:
- vault 가 fatal 인지조차 알 수 없음 — 운영자가 매일 `systemctl --user status` 수동 확인 (F1 §4.6.6 L1172 의 최종 안전망) 의 비용을 매일 지불.
- v0.1.0 acceptance ("OS reboot 후 사람 개입 없이 sync 자동 재기동") 는 satisfied — 그러나 그 안에서 fatal 발생 시 사이클이 영원히 멈춤 + 운영자 미인지.
- 이는 acceptance invariant 의 narrow read — F1 archive 의 정본 운영 모델은 "사이클 + 알림 두 invariant" 였음. v4 가 사이클 invariant 만 lock 하고 알림 invariant 를 silent drop.

**v5 에서 CRIT 3건 + HIGH 8건 lock 후 Step 3 진입 권장**. HIGH-R8-5·6 은 F1 archive §4.8 의 surgical lift 만 — 추가 검증 부담 작음. CRIT 3건은 ADR 1건 (ADR-0024 — fatal 알림 contract) + F3 후속 light feature 분기 또는 F4 spec 확장으로 cover. SRE 시각의 가장 큰 finding 은 R6 의 fix 가 **incomplete** 한 측면을 잡았다는 것: spec 수정만으로 운영 결함이 silent 하게 다른 곳으로 옮겨 갈 수 있다는 SRE 의 표준 패턴.

추정 명시:
- F3 의 `scripts/lib/sync.py` 에 fatal handler 가 `last_failure.json` write 책임을 lift 하지 않았음은 grep 으로 확인 (`grep -rn "last_failure" /Users/1004790/workspace/wikihub/scripts/` 결과 없음). F3 의 R4 라운드 또는 archive 단계에서 surface 됐을 가능성 있으나 본 R8 검토자가 F3 review 문서를 전수 검증하지 않음 — Step 3 진입 전 F3 archive 의 review 문서 + sync.py 코드 cross-check 권장.
- v0.1.0 의 운영자가 메인테이너 1인 (Single Maintainer Operator) — alarm fatigue 의 영향이 prod scale 보다 작을 수 있음. 그러나 메인테이너 1인이 24/7 daemon 의 fatal 알림 0건 도달을 acceptable 으로 볼 가능성은 낮음 (운영자의 일상 신뢰 = 알림 수신 기대).
- OCI host migration 의 실제 빈도 (HIGH-R8-4) 는 OCI free tier ARM 의 maintenance 통계 추정 — 본 R8 검토자가 OCI SLA 문서를 확인 못 함. 통상 cloud free tier 의 unscheduled maintenance 는 분기당 1~2회 추정.
- ops-alert.py 의 dedup 책임 (CRIT-R8-2) 의 v0.1.0 acceptable 한 default (1h vs 12h) 는 운영자 선호에 따라 다름 — yaml override 가능으로 spec 하면 충분.
