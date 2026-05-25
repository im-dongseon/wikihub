approved: 2026-05-25 (사용자 위임 — "step4 까지 자동 진행" 지시)

# Analysis & Design — wikihub_monitor

작성일: 2026-05-25 (KST)
작업자: wikihub maintainer
연계 plan: `plan.md`

---

## 1. 분석

### 1.1 배경

운영자 측에서 wh-ingest / wh-lint 사이클이 매 시간/3시간 단위로 자동 실행되지만, **운영자가 매번 journalctl 을 확인해야 결과를 알 수 있는 상태**. 무소식이 좋은 소식이라는 운영 모드는 (a) 실패 누적이 운영자 인지 없이 진행될 위험과 (b) ops-alert (fatal 만 발화) 와 일상 가시성 사이의 간극 존재.

본 feature 는 일상 운영 가시성 layer 신설:
- **12hr 윈도우 정기 보고서** — 매일 09:00 / 21:00 KST 에 wh-ingest + wh-lint(+graphify chain) 실행 결과를 한 번에 보고
- ops-alert (fatal 즉시 알림, exit 2 발화) 와 분리된 채널 — 성공/실패/skip 을 모두 summary
- 정적 보고서 — LLM 없이 journalctl 파싱 + 결정적 포맷

### 1.2 D1 정정 이력

| 시점 | 결정 | 근거 |
|---|---|---|
| 초기 (AskUserQuestion) | Hermes 스킬 + LLM 자연어 요약 | ingest/lint 와 일관 (Hermes 스킬 패턴) |
| 사용자 재검토 (2026-05-25) | **Python 직접 + 정적 보고서** | (1) ops-alert.py + ingest/lint/graphify 의 결정적 report 패턴 정합, (2) LLM token cost 0, (3) latency / 디버깅, (4) `_lint/report.md` 가 이미 결정적이므로 monitor 가 LLM 재요약하는 건 정합 깨는 일 |

본 design 은 정정된 D1 (Python 직접) 기준.

### 1.3 현행 진단 (관련 결함)

| ID | 진단 | 근거 |
|---|---|---|
| M1 | 일상 운영 가시성 layer 부재 — ops-alert 이 fatal 만 발화, 성공/skip/non-fatal 실패는 운영자가 journal 확인해야 함 | ops-alert.py 의 발화 조건 = exit 2 (Fatal) 만 (vault@.service 의 SuccessExitStatus=0 75 정합) |
| M2 | `wikihub-lint.service` 의 graphify chain 결과가 `_lint/report.md` 에 라인 단위 기록되나 운영자가 파일 열어봐야 surface | `lint.md:162-194` 의 graphify partial failure / timeout / skipped 마커 |
| M3 | multi-vault 미래 도입 시 vault 별 sync 결과 가시성 더 떨어짐 — 현행 단일 vault 가정에서도 surface 필요 | `wikihub-vault@*.service` instance template 패턴 |
| M4 | systemd OnCalendar 의 TZ 처리가 ad-hoc — `Persistent=true` + `Asia/Seoul` 명시 흐름 미정립 | 현행 lint/vault timer 모두 monotonic (interval-based), OnCalendar 미사용 |

### 1.4 영향받는 정본/코드 파일 (v3 정정)

| 파일 | 변경 성격 | 라인 |
|---|---|---|
| `_system/systemd/wikihub-monitor.service.template` (신규) | oneshot, EnvironmentFile=-%h/.config/wikihub/env, ExecStart=Python 직접. exit code 분리 (C2-R1 흡수) | +25 |
| `_system/systemd/wikihub-monitor.timer.template` (신규) | OnCalendar 09,21:00 Asia/Seoul, Persistent=true, AccuracySec=1min | +15 |
| `scripts/wikihub_monitor.py` (신규) | journalctl 수집 (`@epoch` since, `--no-pager`, `--lines=10000` cap, `subprocess.run timeout=30`) + 보고서 생성 + telegram 발송 + 파일 저장 | +250~300 |
| `scripts/lib/telegram.py` (신규) | `send_telegram(bot_token, chat_id, text, parse_mode=None, timeout_sec=10)` — ops-alert.py 에서 추출 + parse_mode 옵션화 | +50 |
| `scripts/ops-alert.py` | `send_telegram` / `format_telegram_message` 를 lib/telegram.py 로 이동 + import + parse_mode="HTML" 명시 호출 | +5/-50 |
| `scripts/lib/config.py` (**C2-R2 신규 추가**) | `OperationsConfig.monitor_enabled: bool = True` field 추가 + `_parse_operations` 갱신 | +3 |
| `install.sh` `_step8_systemd_render` + `_systemd_stop/start_*` + `try-restart` (**M6-R2 정확화**) | wikihub-monitor.{service,timer} 4 위치 추가 (render / stop list / start list / try-restart glob) | +20 |
| ~~`scripts/render_systemd_units.py`~~ (**C3-R2 정정**) | **변경 0** — glob 자동 발견 (`tpl_dir.glob("*.template")` line 352) + `wikihub_src` substitution 이미 존재 (line 212) | 0 |
| `wikihub.yaml.example` `operations` | `monitor_enabled: true` + `monitor_report_vault: <vid>` (default 첫 vault) + `monitor_report_subpath: project/wikihub/report` default 추가 | +5 |
| `install.sh` `_migrate_agent_schema` Group B | `B_monitor_enabled` + `B_monitor_report_vault` + `B_monitor_report_subpath` 부재 시 default 자동 추가 | +15 |
| `docs/adr/0037-telegram-alert-channel.md` | §"후속 영향" 1 줄 cross-link | +2 |

**총: +390 / -50 (net +340)**. v1 +290 → v3 +340 (사용자 §2.3 보고서 파일 저장 + C2-R2 config.py + M6-R2 install.sh 4 위치).

### 1.5 ADR 신설 여부

검토:
- 본 feature 는 **운영 가시성 layer 추가** — 아키텍처 선택 (예: LLM vs 정적 결정) 은 D1 에서 surface 했지만 본 feature 의 정본은 plan.md + design.md 자체. ADR 신설 불필요.
- 단 `scripts/lib/telegram.py` 분리는 향후 다른 module (예: weekly summary, alert digest) 도 재사용 가능한 helper — 아키텍처 결정으로 격상 가능. 그러나 본 feature 범위에서 ADR 까지 격상은 over-engineering.
- ADR-0037 (텔레그램 alert channel) 에 §"후속 영향" 1 줄로 cross-link 만 추가.

**결론**: ADR 신설 미생성. ADR-0037 footnote 1 줄.

---

## 2. 설계

### 2.1 systemd unit

#### 2.1.1 `_system/systemd/wikihub-monitor.service.template`

```ini
[Unit]
Description=WikiHub monitor — 12hr 윈도우 운영 보고서 (wikihub_monitor)
After=network-online.target
Wants=network-online.target
# OnFailure=ops-alert.service — monitor 가 부트스트랩 실패 (exit 2) 시만 발화 (C2-R1).
# runtime 실패 (telegram 발송 fail 등 = exit 75) 는 SuccessExitStatus 정합 → 미발화.
OnFailure=ops-alert.service

[Service]
Type=oneshot
WorkingDirectory={wikihub_home}
ExecStartPre=/bin/mkdir -p {wikihub_home}
Environment=PATH={venv_path}/bin:/usr/local/bin:/usr/bin:/bin
Environment=WIKIHUB_YAML={wikihub_home}/wikihub.yaml
Environment=WIKIHUB_SRC={wikihub_src}
# ADR-0037 — TELEGRAM_ALERT_BOT_TOKEN + TELEGRAM_ALERT_CHAT_ID 재사용
EnvironmentFile=-%h/.config/wikihub/env
ExecStart={venv_path}/bin/python {wikihub_src}/scripts/wikihub_monitor.py
SuccessExitStatus=0 75
TimeoutStartSec=60
SyslogIdentifier=wikihub-monitor

# Restart= 미설정 — oneshot, timer 책임.
# [Install] 미작성 — timer 가 trigger.
```

설계 결정 (v3 — Reviewer 1 흡수):
- `Type=oneshot` — lint/vault 패턴 정합
- `SuccessExitStatus=0 75` — exit 75 (Retryable, 예: 텔레그램 transient fail) 도 success 로 분류. 12hr 후 다음 fire 자연 재시도.
- **`OnFailure=ops-alert.service`** (v3 정정, C2-R1 흡수) — exit 2 (부트스트랩 실패: venv/import/config 결함) 만 발화. exit 75 (runtime 실패: telegram 발송 fail) 는 SuccessExitStatus 로 흡수되어 ops-alert 미발화. **재귀 회피 + 운영 black hole 회피 동시 달성**. monitor.py 의 exit code 정책: bootstrap fail = 2 / runtime success-with-warn = 75 / 정상 = 0.
- `TimeoutStartSec=60` — canonical syntax (M1-R2). journalctl + telegram + 파일 저장 합쳐서 60초 충분.

#### 2.1.2 `_system/systemd/wikihub-monitor.timer.template`

```ini
[Unit]
Description=WikiHub monitor timer — 매일 09:00, 21:00 KST

[Timer]
Unit=wikihub-monitor.service
OnCalendar=*-*-* 09,21:00:00 Asia/Seoul
Persistent=true
AccuracySec=1min

[Install]
WantedBy=timers.target
```

설계 결정:
- **단일 timer** (Q1 default) — `09,21:00:00` 의 `,` syntax 가 systemd 가 자연 지원. morning/evening 분리보다 단순.
- **`Asia/Seoul` TZ suffix** (Q2 default) — systemd 242+ 의 OnCalendar TZ suffix 지원 (`OnCalendar=*-*-* HH:MM:SS Asia/Seoul`). install.sh 가 이미 ALLOW_NON_UBUNTU=0 default 라 systemd 버전 충분.
- **`Persistent=true`** — 시스템 휴면/재부팅 시 마지막 fire 시점 보존, 누락된 fire 시점에 catch-up. 단 윈도우 정의가 "지난 12 시간" 단순이라 catch-up 도 그 시점의 12hr 윈도우.
- **`AccuracySec=1min`** — 09:00 ± 1min, 21:00 ± 1min 범위. lint 의 15min 보다 빡빡 (보고서 시간 안정성).

### 2.2 `scripts/wikihub_monitor.py` 구조

#### 2.2.1 모듈 구조 (v3)

```python
# wikihub_monitor.py 의 sys.path bootstrap (M3-R2, pending_monitor.py:21-24 정합)
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from lib.config import load_wikihub_yaml  # noqa: E402
from lib.telegram import send_telegram     # noqa: E402

# 함수 구조
├── main() → exit code 0/2/75
├── _setup_logging()                           # ops-alert.py 패턴
├── load_yaml_config()                         # config.py 의 Config dataclass 재사용 (C2-R2: monitor_* fields 포함)
├── collect_journal(unit, since_epoch)         # journalctl --user -u <unit> -o json --no-pager --lines=10000 --since "@<epoch>"
├── parse_runs(entries)                        # MESSAGE_ID=39f53479... 종료 entry 식별 + EXIT_STATUS / _SYSTEMD_UNIT_RESULT 1차 분류
├── extract_failure_reason(run_entries)        # journalctl PRIORITY (3=err, 4=warn) 의 마지막 5줄 + 100 chars cap
├── extract_graphify_status(lint_run)          # `_lint/report.md` tail 1차 (C4-R2) + journal MESSAGE 2차 보강
├── format_report(...) → str
├── write_report_file(report_text, window_end, cfg)  # vault 안 `YYYYMMDD__HH_mm.md` write (사용자 §2.3)
├── send_report(bot_token, chat_id, text)      # lib/telegram 의 send_telegram(parse_mode=None) + 4000 cap + truncate marker (M5-R2)
└── (entrypoint)
```

#### 2.2.2 흐름 (main) — v3

```python
def main() -> int:
    # 1. config load — bootstrap fail 시 exit 2 (OnFailure → ops-alert 발화, C2-R1)
    try:
        cfg = load_yaml_config()
    except Exception as e:
        log.error("config load 실패: %s — bootstrap fail", e)
        return 2

    if not cfg.operations.monitor_enabled:  # C2-R2: OperationsConfig.monitor_enabled
        log.info("operations.monitor_enabled = false — skip")
        return 0

    bot_token = os.environ.get("TELEGRAM_ALERT_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_ALERT_CHAT_ID", "").strip()
    if not (bot_token and chat_id):
        log.warning("TELEGRAM_ALERT_BOT_TOKEN/CHAT_ID 미설정 — monitor skip (Q7 default)")
        return 0

    # 2. 윈도우 — H1-R2: TZ 무관 @epoch 형식
    window_end = datetime.now(tz=KST)
    window_start = window_end - timedelta(hours=12)
    since_epoch = int(window_start.timestamp())  # journalctl --since "@<epoch>"

    # 3. vault_ids — C1-R2: Config.vaults 가 dict[str, VaultConfig]
    vault_ids = [vid for vid, v in cfg.vaults.items() if v.enabled]

    # 4. collect — H3-R2: subprocess timeout=30, H4-R2: --lines=10000 cap, H2-R2: --no-pager
    ingest_entries_per_vault = {
        vid: collect_journal(f"wikihub-vault@{vid}.service", since_epoch)
        for vid in vault_ids
    }
    lint_entries = collect_journal("wikihub-lint.service", since_epoch)

    # 5. parse — M4-R2: MESSAGE_ID 종료 entry 식별
    ingest_results = {vid: parse_runs(entries) for vid, entries in ingest_entries_per_vault.items()}
    lint_results = parse_runs(lint_entries)
    # lint run 별로 graphify 상태 부가 (C4-R2: _lint/report.md tail 1차)
    for lint_run in lint_results:
        lint_run.graphify_status = extract_graphify_status(lint_run, cfg)

    # 6. format + write file (사용자 §2.3) + send (M5-R2 truncate marker)
    report = format_report(ingest_results, lint_results, window_start, window_end)
    try:
        write_report_file(report, window_end, cfg)  # write fail = warn only, monitor 계속
    except Exception as e:
        log.warning("보고서 파일 write 실패: %s — telegram 발송 계속", e)

    ok = send_report(bot_token, chat_id, report)
    if not ok:
        log.warning("telegram 발송 실패 — 12hr 후 자연 재시도 (H5-R2 명시)")
        return 75  # Retryable, SuccessExitStatus 정합. journal WARN 만 surface.

    return 0
```

#### 2.2.3 `collect_journal` 구현 (H1~H4-R2 흡수)

```python
def collect_journal(unit: str, since_epoch: int) -> list[dict]:
    """journalctl --user -u <unit> -o json --no-pager --lines=N --since @epoch.

    H1-R2: TZ 무관 @epoch 형식.
    H2-R2: --no-pager (ops-alert.py 패턴 정합).
    H3-R2: subprocess timeout=30.
    H4-R2: --lines=10000 hard cap (메모리 폭증 가드).
    """
    cmd = [
        "journalctl", "--user", "-u", unit, "-o", "json",
        "--no-pager", "--lines=10000", "--since", f"@{since_epoch}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    if result.returncode != 0:
        log.warning("journalctl 실패 unit=%s exit=%d stderr=%s", unit, result.returncode, result.stderr[:200])
        return []
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
```

#### 2.2.3 `IngestEntry` / `LintEntry` dataclass

```python
@dataclass
class ServiceRun:
    timestamp: datetime         # service 시작 시각
    success: bool               # exit 0 또는 75 = True; exit 2 또는 그 외 = False
    exit_code: int              # journalctl 의 EXIT_STATUS 또는 _SYSTEMD_UNIT_RESULT
    reason: str | None          # 실패 시 추출 사유, 성공 시 None
    # lint 전용
    graphify_status: Literal["success", "skipped", "timeout", "partial", "unknown"] | None = None
```

### 2.3 보고서 파일 저장 (사용자 추가 요구, 2026-05-25)

**경로**: `$WIKIHUB_HOME/vault/<report_vault_id>/<report_subpath>/YYYYMMDD__HH_mm.md`

| 항목 | 결정 |
|---|---|
| **저장 위치** | `$WIKIHUB_HOME/vault/{vault_id}/{subpath}/` — rclone mount 안의 sub-path. gdrive 동기화 → 다른 디바이스/웹에서 보고서 history 접근 가능 |
| **파일명 timestamp** | `YYYYMMDD__HH_mm.md` (24시간제, KST, 더블 언더스코어 + 콜론→언더스코어). 예: `20260525__09_00.md`, `20260525__21_00.md`. **Windows 호환** (POSIX 와 모두 valid) |
| **vault_id default** | `operations.monitor_report_vault` yaml toggle (default = `vaults[0].id`, 즉 첫 vault) |
| **subpath default** | `operations.monitor_report_subpath` yaml toggle (default = `project/wikihub/report`) |
| **write timing** | telegram 발송 **전에** `.tmp` write → atomic rename. 발송 실패해도 파일 보존 (12hr 후 다음 fire 가 자연 보고) |
| **write 실패 처리** | mkdir/write fail 시 warn + telegram 만 발송 (file write 가 monitor 의 critical path 아님) |
| **파일 형식** | Markdown — 텔레그램 메시지와 동일 본문을 ```` ``` ```` codeblock 으로 wrap + 헤더 한 줄 (시각 / 윈도우) |
| **retention** | monitor 가 자체 정리 안 함 — gdrive 또는 운영자가 수동. backlog 등록 권고 (예: 90일 이전 보고서 자동 cleanup) |

**파일명 Windows 호환**: 사용자 2차 정정 (2026-05-25) — `YYYYMMDD_HH:mm.md` (콜론 포함, Windows 비호환) → `YYYYMMDD__HH_mm.md` (언더스코어, POSIX + Windows + gdrive 모두 valid). backlog 등록 불요.

#### 마크다운 파일 본문 예시

````markdown
# WikiHub Monitor — 2026-05-25 09:00 (KST)

윈도우: 2026-05-24 21:00 ~ 2026-05-25 09:00 (12hr)

```
wh-ingest [vault: gdrive]
  2026-05-24 21:00 : 성공
  ...
wh-lint (lint + graphify chain)
  2026-05-24 21:30 (lint/graphify) : 성공 / 성공
  ...
```
````

텔레그램 메시지 = codeblock 안의 내용만 (plain text). 마크다운 파일 = 헤더 한 줄 + 윈도우 한 줄 + codeblock.

### 2.4 보고서 포맷 (사용자 제시 + 명료화)

```
🔭 WikiHub Monitor — 2026-05-25 (KST)
윈도우: 2026-05-25 09:00 ~ 21:00 (12hr)

wh-ingest [vault: gdrive]
  2026-05-25 09:00 : 성공
  2026-05-25 10:00 : 성공
  2026-05-25 11:00 : 실패 (exit 2, rclone mount stale — mount@gdrive 재시작 필요)
  2026-05-25 12:00 : 성공
  ...
  2026-05-25 20:00 : 성공
  (윈도우 내 12회 실행 — 성공 11 / 실패 1)

wh-lint (lint + graphify chain)
  2026-05-25 09:30 (lint/graphify) : 성공 / 성공
  2026-05-25 12:30 (lint/graphify) : 성공 / skipped (yaml toggle)
  2026-05-25 15:30 (lint/graphify) : 성공 / timeout (exit 124)
  2026-05-25 18:30 (lint/graphify) : 성공 / 성공
  (윈도우 내 4회 실행 — lint 성공 4 / graphify 성공 2 · skipped 1 · timeout 1)
```

**라인 단위 규칙**:
- 헤더: 보고서 시각 + 윈도우 범위
- 섹션 분리: `wh-ingest [vault: <vid>]`, `wh-lint (lint + graphify chain)`
- 행: `YYYY-MM-DD HH:MM : 상태 [(원인)]` — lint 는 `HH:MM (lint/graphify) : 상태1 / 상태2`
- 섹션 끝: `(윈도우 내 N회 실행 — 카운트 요약)` 1줄
- 빈 윈도우: `(12hr 동안 실행 없음)`

**HTML escape 처리**: send_telegram 의 parse_mode 가 monitor 호출 시 `None` (plain text) → escape 불요. lib/telegram.py 분리로 가능.

### 2.4 telegram helper 분리 결정

**채택: scripts/lib/telegram.py 신설 + ops-alert.py 가 import**

```python
# scripts/lib/telegram.py
def send_telegram(
    bot_token: str,
    chat_id: str,
    text: str,
    parse_mode: str | None = None,   # ops-alert = "HTML", monitor = None
    timeout_sec: int = 10,
) -> bool:
    """Telegram bot 으로 message 전송. ADR-0037 §D1.

    parse_mode=None 면 plain text (escape 불필요).
    parse_mode="HTML" 면 HTML 태그 + < > & escape 책임은 caller.
    """
    ...
```

**근거**:
- ops-alert.py 의 send_telegram 이 parse_mode "HTML" 고정 → monitor 의 plain text 메시지 (`<vault: gdrive>` 등) 가 HTML 로 잘못 해석될 위험
- helper 분리하면 ops-alert.py 가 parse_mode="HTML" 명시 호출, monitor 가 parse_mode=None 호출
- 향후 weekly digest 등 다른 telegram channel 도 같은 helper 재사용

### 2.5 실패 원인 추출 정책

journalctl 의 한 service run = 시작~종료 사이 entries (MESSAGE + EXIT_STATUS + _SYSTEMD_UNIT_RESULT).

**핵심 fields** (`journalctl -o json` 출력):
- `MESSAGE` — 로그 본문
- `EXIT_STATUS` — exit code (success 시 0, retryable 75, fatal 2)
- `_SYSTEMD_UNIT_RESULT` — `success`, `failed`, `timeout`, ...
- `__REALTIME_TIMESTAMP` — 마이크로초 epoch

**원인 추출 단계** (실패 entry 발견 시):
1. EXIT_STATUS 또는 `_SYSTEMD_UNIT_RESULT` 로 1차 분류
2. journal entries 의 마지막 ERROR/WARNING MESSAGE 5줄 추출
3. lint 의 경우 `_lint/report.md` 의 마지막 partial failure 마커 ("graphify chain skipped", "graph rebuild timeout", "graphify partial failure 의심") 부가 정보 첨부
4. 길이 cap 100 chars per reason (보고서 폭증 방지)

**graphify 상태 분기 (lint 전용) — v3 (C4-R2 + H3-R1 흡수)**:

graphify 결과 정본은 `_lint/report.md` — lint.md Step 9 가 결정적 마커 라인 기록. journal MESSAGE 는 stdout/stderr 캡쳐 의존 → 불안정. 1차 자료원 = report.md, 2차 보강 = journal.

1. **1차 (정본): `_lint/report.md` tail 마지막 20줄 grep**:
   - `graphify chain skipped (yaml toggle)` → `skipped`
   - `graph rebuild timeout` → `timeout` (※ H3-R1: lint Step 9 의 `timeout 300 graphify` wrapper 가 흡수해 lint.service EXIT_STATUS 는 0. EXIT_STATUS 124 분기는 잘못 — report.md 마커가 정본)
   - `graphify partial failure 의심: N=<N>, M=<M>, ratio=<r>` → `partial` (+ ratio 부가)
   - 위 3 마커 모두 부재 + graphify_enabled=true → `success`
   - graphify_enabled=false → `skipped (yaml toggle)`

2. **2차 (보강): journal MESSAGE pattern matching** (report.md 위치 부재 또는 read fail 시 fallback):
   - 같은 키워드 grep — 단 신뢰성 낮음. log.warning("report.md 부재 — journal 보강 사용") 명시.

**report.md 위치 결정 (Step 3 검증)**:
- 후보 A: `{wikihub_home}/wiki/_lint/report.md` (lint.md:13 "wiki/_lint/report.md" 표현)
- 후보 B: `{vault.local_path}/_lint/report.md` — vault 별
- Step 3 에서 lint.md 본문 + 실제 OCI 운영 환경 검증.

### 2.6 multi-vault 처리

현행 v0.1.x = 단일 vault 가정이나, vault@<vid> instance template 패턴 정합:

- vault_ids 리스트 = `wikihub.yaml.vaults[*].id` 전체 순회
- 보고서 섹션 = `wh-ingest [vault: <vid>]` 별 분리 (vault 별 sub-section)
- 단일 vault 시 1 섹션, multi-vault 시 N 섹션
- vault 별 카운트 요약 라인

### 2.7 install.sh / render_systemd_units.py 변경 — v3 (C3-R2 + M6-R2 흡수)

#### install.sh 4 위치 (M6-R2)

| 위치 | 변경 |
|---|---|
| `_systemd_stop_before_update` (~line 1587) | reset-failed list 에 `wikihub-monitor.service wikihub-monitor.timer` 추가 |
| `_systemd_start_after_update` (~line 1637) | `systemctl --user start wikihub-monitor.timer` 라인 추가 |
| `try-restart` glob (~line 1685) | `wikihub-monitor.timer` 추가 |
| `_step9_systemd_setup` (또는 enable 영역, line 검증 필요) | `systemctl --user enable wikihub-monitor.timer` 라인 추가 |

#### render_systemd_units.py — **변경 0** (C3-R2)

- line 352 `templates: list[Path] = sorted(tpl_dir.glob("*.template"))` — glob 자동 발견
- line 212 `"wikihub_src": str(wikihub_src)` — substitution 이미 존재
- `_PER_VAULT_PATTERN = re.compile(r"@\.[^/]+\.template$")` — `wikihub-monitor.service.template` 가 매치 안 됨 → singleton 자동 분류

→ template 2 파일만 `_system/systemd/` 에 추가하면 끝.

### 2.8 wikihub.yaml.example + ADR-0037 cross-link

#### wikihub.yaml.example operations 절

```yaml
operations:
  lint_interval_hours: 3
  graphify_enabled: true
  monitor_enabled: true                  # v0.1.8 신설 — false 시 wikihub-monitor.timer 발화 안 함 (wikihub_monitor 보고서 비활성). systemd timer 자체는 enable 되지만 service 가 즉시 exit 0 (config gate).
```

#### install.sh `_migrate_agent_schema` Group B

```bash
# v0.1.8 신설 — operations.monitor_enabled 부재 시 true 자동 추가
if "monitor_enabled" not in operations:
    flags.append("B_monitor_enabled")
# yaml_writer.py 의 default ensure 에서:
"monitor_enabled": True,
```

info log case 추가: `B_monitor_enabled) info "  - [v0.1.8] operations.monitor_enabled 부재 → true 추가" ;;`

#### ADR-0037 §"후속 영향" 1 줄

```markdown
- 2026-05-25: `wikihub_monitor` (v0.1.8) 가 같은 env 키 (`TELEGRAM_ALERT_BOT_TOKEN` + `TELEGRAM_ALERT_CHAT_ID`) 재사용. `scripts/ops-alert.py` 의 `send_telegram` / `format_telegram_message` 가 `scripts/lib/telegram.py` 로 추출됨 (parse_mode 옵션화). 호출부 그대로.
```

### 2.9 연계 룰/스킬 정합성

| 연계 대상 | 정합 확인 | 조치 |
|---|---|---|
| ADR-0037 (텔레그램 alert channel) | env 키 재사용, parse_mode 옵션화 | §후속 영향 1 줄 |
| ADR-0024 (ops-alert) | monitor 가 fatal channel 과 분리된 가시성 layer — 의미 충돌 없음 | 변경 없음 |
| ADR-0036 (graphify CLI) §D6 | lint Step 9 chain (graphify single-source) — monitor 가 그대로 read | 변경 없음 |
| ADR-0023 (sparse-checkout) | `WIKIHUB_SPARSE_PATHS` = `_system scripts install.sh wikihub.yaml.example README.md LICENSE` — scripts/ 하위 모두 포함됨 | 변경 없음 |
| ADR-0030 (`_resolve_ref` chain) | 본 feature 와 무관 | 변경 없음 |
| `_system/commands/*` | 본 feature 신규 스킬 안 만듦 (D1 정정) — _system/commands/ 변경 없음 | 변경 없음 |
| `features/backlog.md` | 본 feature 항목 없음 | 추가 불요 |

---

## 3. 개정 범위 요약

§1.4 표 그대로. **총 +340 / -50 (net +290)**. install.sh `_migrate_agent_schema` 의 `B_monitor_enabled` 1 항목 추가 + render_systemd_units.py 의 monitor unit render + scripts/wikihub_monitor.py 본체 (~250 줄) + scripts/lib/telegram.py 추출 (~50 줄).

---

## 4. 미결 사항 (잔여)

| ID | 미결 사항 | reasonable default | Step 3 결정 |
|---|---|---|---|
| Q9 | journalctl `--user` vs system-level — `wikihub-monitor.service` 가 user systemd 라서 `--user` 명시 필요 | `journalctl --user -u <unit> -o json --since "<datetime>"` (lint/vault 와 정합) | (a) |
| Q10 | 실패 reason cap 길이 | 100 chars | (a) |
| Q11 | Telegram message 길이 cap — Telegram bot API 한 메시지 4096 chars limit | 4000 chars cap, 초과 시 truncate + "..." 또는 multi-message 분할 (현행 ops-alert 도 미처리 — backlog 등록 권고) | cap 4000 + truncate, 분할은 backlog |
| Q12 | 첫 install 후 단일 vault 가 yaml 미등록 상태에서 monitor 실행 시 동작 | vault_ids 빈 리스트 → "wh-ingest: vault 미등록" 라인 + lint 만 보고 | (a) |
| Q13 | Telegram parse_mode escape — `<` `>` `&` 가 plain text 에 자연 등장 시 (예: `vault: <unknown>`) — parse_mode=None 이라 escape 불요 | parse_mode=None 일 때 escape 미수행, telegram 이 plain text 로 처리 | 확인 — parse_mode None 시 Telegram API spec 검증 |
| Q14 | Telegram 발송 실패 시 운영자 인지 경로 (H5-R2) | exit 75 + journal `log.warning` 명시. 운영자가 `journalctl --user -u wikihub-monitor -p warning --since "24h ago"` 로 발견 가능. 12hr 후 자연 재시도 | (a) journal WARN 만 — 채택 |
| Q15 | ops-alert 와 같은 채널 이중 noise (C1-R1) | 보고서의 실패 라인 끝에 `[ops-alert 발화됨: <reason>]` 마커 — 운영자가 같은 fatal 의 두 번째 알람임을 인지 | (a) 마커 추가 — 채택 |

**잔여 미결**: Q9~Q15 모두 default 채택. Step 3 진입 시 1차 검증.

---

## 5. Definition of Done

- [ ] `_system/systemd/wikihub-monitor.service.template` 작성 — Type=oneshot, EnvironmentFile, ExecStart=python, SuccessExitStatus=0 75, SyslogIdentifier=wikihub-monitor
- [ ] `_system/systemd/wikihub-monitor.timer.template` 작성 — OnCalendar=*-*-* 09,21:00:00 Asia/Seoul, Persistent=true
- [ ] `scripts/wikihub_monitor.py` 작성 — main / collect_journal / parse_* / format_report / send_report, exit code 0/75/2
- [ ] `scripts/lib/telegram.py` 신설 — `send_telegram(parse_mode: str | None = None, ...)` + `format_telegram_alert_message` (기존 ops-alert format 보존)
- [ ] `scripts/ops-alert.py` 갱신 — import 변경 + parse_mode="HTML" 명시 호출 + format_telegram_message 이동
- [ ] `install.sh` `_step8_systemd_render` 영역 — monitor.{service,timer} render + enable
- [ ] `scripts/render_systemd_units.py` — monitor unit render 추가
- [ ] `install.sh` `_migrate_agent_schema` Group B — `B_monitor_enabled` flag + info log + yaml writer default
- [ ] `wikihub.yaml.example` — `operations.monitor_enabled: true` 추가
- [ ] `docs/adr/0037-telegram-alert-channel.md` §"후속 영향" 1 줄 cross-link
- [ ] V 검증: VM 또는 OCI 에서 `systemctl --user start wikihub-monitor.service` ad-hoc trigger → 보고서 텔레그램 수신 확인 (Step 5 직전 또는 후속)
- [ ] bash -n install.sh + py_compile wikihub_monitor.py + py_compile lib/telegram.py + py_compile lib/config.py + py_compile ops-alert.py 모두 pass (O3-R2 추가)
- [ ] `_lint/report.md` 위치 정합 검증 — `{wikihub_home}/wiki/_lint/report.md` 또는 `{vault.local_path}/_lint/report.md` 중 lint.md 정본과 정합 (C4-R2)
- [ ] 보고서 파일 저장 — `$WIKIHUB_HOME/vault/<vid>/<subpath>/YYYYMMDD__HH_mm.md` atomic write, mkdir guard
- [ ] OnFailure=ops-alert.service 명시 + exit code 정책 0/2/75 (C2-R1)
- [ ] backlog 등록: BL-N1 (Telegram 4000 cap multi-message 분할), BL-N2 (monitor 보고서 retention/cleanup), BL-N3 (lint.service running 중 monitor fire 시 진행 중 entries 처리, O5-R2)
- [ ] Step 4 멀티 리뷰어 통과
- [ ] Step 5 5 액션 squash → v0.1.8 → canary force-update
- [ ] Feature 종료 archive 이동

---

## 6. 버전 이력

### v1 — 2026-05-25 (초안, D1 정정 후)

D1 (Hermes 스킬 + LLM 요약) → Python 직접 정정 흡수. 정적 보고서 포맷 (사용자 제시) + scripts/lib/telegram.py 분리 + multi-vault sub-section + 실패 원인 추출 정책 (3-단계).

### v2 — 2026-05-25 (사용자 추가 요구: 보고서 파일 저장)

§2.3 신설 — `$WIKIHUB_HOME/vault/<vid>/<subpath>/YYYYMMDD_HH:mm.md`. yaml toggle `monitor_report_vault` / `monitor_report_subpath`. atomic write. monitor critical path 아님 (write fail = warn only).

### v3 — 2026-05-25 (Step 2.5 멀티 리뷰어 흡수 + 파일명 정정 + approved)

**사용자 추가 정정 (2회차)**: 파일명 `YYYYMMDD_HH:mm.md` (콜론) → `YYYYMMDD__HH_mm.md` (언더스코어). Windows 호환 — backlog 등록 권고 (이전 v2 의) 자연 해소.

**Reviewer 1 (메소드론/ADR 정합)**:
- **C1** ops-alert 와 동일 채널 noise 이중화 → §4 Q15 신설, 보고서에 `[ops-alert 발화됨]` 마커 (default 채택)
- **C2** monitor.service silent dead → §2.1.1 `OnFailure=ops-alert.service` + exit code 분리 (bootstrap=2, runtime=75, success=0) 채택
- **H1** Telegram 4000 cap truncate → §5 DoD BL-N1 backlog 등록 명시
- **H2** Persistent catch-up 윈도우 시맨틱 — §2.1.2 `Persistent=true` 설명에 catch-up 시 윈도우가 fire 시점 기준 12hr 컴퓨트로 어긋남 흡수 (Q4 default 정합)
- **H3** EXIT_STATUS 124 분기 부정확 → §2.5 graphify 분기를 `_lint/report.md` tail 정본 / journal 보강 으로 재배치 (C4-R2 와 통합)

**Reviewer 2 (구현 가능성)**:
- **C1** `Config.vaults` dict iter → §2.2.2 `[vid for vid, v in cfg.vaults.items() if v.enabled]` 정정
- **C2** `OperationsConfig.monitor_enabled` field 부재 → §1.4 표 갱신 + §5 DoD py_compile lib/config.py 추가
- **C3** `render_systemd_units.py` glob 자동 → §2.7 변경 0 정정 (이전 +20 → 0)
- **C4** graphify 자료원 = `_lint/report.md` 정본 → §2.5 분기 재배치 (H3-R1 통합)
- **H1** TZ `@epoch` → §2.2.2 + §2.2.3 `since_epoch` + `--since "@<epoch>"` 채택
- **H2** `--no-pager` → §2.2.3 collect_journal 명시
- **H3** subprocess timeout 30s → §2.2.3 명시
- **H4** journal 메모리 폭증 → `--lines=10000` cap 채택
- **H5** 발송 실패 인지 → §4 Q14 신설 (journal WARN + 12hr 자연 재시도)
- **M1** `60sec` → `60` canonical 정정
- **M3** sys.path bootstrap → §2.2.1 pending_monitor.py 패턴 정합 명시
- **M4** MESSAGE_ID 종료 entry 식별 → §2.2.1 parse_runs 명시
- **M5** truncate marker → §5 DoD 명시
- **M6** install.sh 4 위치 정확화 → §2.7 표 갱신

**O 범위 외 사항**: BL 등록 (4000 cap 분할 / 보고서 retention / 진행 중 entries 처리), plan.md §1 작업 분류 정정 (Hermes → Python 직접) — 이미 완료.

approved: 2026-05-25 — 사용자 "step4 까지 자동 진행" 위임. Step 3 진입.

### v4 — 2026-05-25 (Step 4 code review 흡수)

**Code review 1 (구현 정확성)**:
- **C1** dead code `extract_graphify_status:230-232` (hasattr+pass) → 제거
- **H1** lint_label exit_code None-guard → format_report 의 lint 라인을 ingest 와 같은 가드 패턴으로 통일
- **H2** _resolve_report_path 의 cfg.instance_root 무시 → `_resolve_wikihub_home` 신설 (4 단계 우선순위)
- **H3** service template `WIKIHUB_HOME` env 부재 → `Environment=WIKIHUB_HOME={wikihub_home}` 추가
- **M1** dead import `field` 제거
- **M2** design §M6 enable 권고 정합 인정 (lint.timer 도 동일 패턴)

**Code review 2 (운영 안전성)**:
- **H1** graphify_status 모든 lint_run 동일 값 leak → 마지막 run 만 정확 status, 나머지 "unknown (overwrite)" surface
- **H2** monitor.service OnFailure silent → `_emit_bootstrap_alert` 신설, bootstrap catch 안에서 직접 telegram alert
- **M1** monitor.timer enable 부재 → backlog 등록 (lint.timer 도 동일 결함이라 별도 cleanup feature)
- **M3** WIKIHUB_HOME env (R1-H3 와 동일, 흡수)
- **L1** MESSAGE_ID `fc2e22bc...` 가 coredump UUID → 부정확한 ID 제거, `_SYSTEMD_UNIT_RESULT` / `EXIT_STATUS` 1차 자료원 명시
- **L7** dead code (R1-C1 와 동일, 흡수)

**범위 외 → backlog 추가 (BL-N4~N6)**:
- BL-N4 monitor self-health surface (L9 — 12hr 보고서 누락 인지)
- BL-N5 timer enable catalog 정비 (M1 — lint/pending-monitor/monitor 일괄)
- BL-N6 subprocess env scrub (M4 — security hardening)

py_compile + smoke test pass. design.md v4 = code 흡수 후 상태 정합.
