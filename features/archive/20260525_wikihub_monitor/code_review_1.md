# Code Review 1 — wikihub_monitor (구현 vs design v3 정합)

작성일: 2026-05-25
리뷰어: claude (독립, 이전 conversation 컨텍스트 없음)
검토 대상: design v3 (approved) + 10 변경/신규 파일

---

## 종합 평가

**조건부 통과** — design v3 의 16+ DoD 항목 중 14항목 정확 반영, design reviewer 정정 (C/H/M 16건) 모두 흡수됨. 단 다음 결함 surface:

- **C1** `extract_graphify_status` 의 `graphify_enabled` 분기가 **사실상 dead code** (Python operator precedence 오용 + `OperationsConfig.graphify_enabled` field 부재). graphify_enabled=false 케이스가 "skipped (yaml toggle)" 분기로 가지 못함 — Q12/M2 의 정상 흐름 깨짐.
- **H1** `lint_label` 의 `r.exit_code` None-guard 누락 (`scripts/wikihub_monitor.py:333`) — lint 실패 + exit_code None 시 `"실패 (exit None, ...)"` 출력 (ingest 측 313 라인은 guard 있음, 비대칭).
- **H2** `_resolve_report_path` 의 `WIKIHUB_HOME` fallback 이 `WIKIHUB_YAML` env 경로 의존인데, install.sh:38 의 default = `$HOME/wikihub` 와 정합하지만 `WIKIHUB_YAML` 부재 시 `Path("")` → `.parent == Path(".")` → fallback 분기. 다만 cfg.instance_root 가 이미 정본 — 그쪽 사용 권장 (현행은 systemd template 의 `WIKIHUB_YAML` env 가 항상 set 이라 실 영향 거의 없음, 그러나 ad-hoc CLI 실행 시 결함).
- **M1** `from dataclasses import dataclass, field` — `field` import 미사용 (Karpathy §2 Simplicity First — dead import).
- **M2** systemd `enable` 흐름 — design.md §2.7 §M6 표 4번째 행 "systemctl --user enable wikihub-monitor.timer 라인 추가" 가 install.sh 에 **미반영**. 단 lint/pending-monitor 도 explicit enable 없이 `WantedBy=timers.target` + `start` 로 동작하는 패턴 — install.sh 의 기존 정합과 일관이라 정상. design.md §M6 표 4행이 **잘못된 권고**.

조건부 = C1 1건은 즉시 patch (3~5 라인), H1·H2 는 동일 commit 에 묶음. M1 은 dead import 제거 1라인. M2 는 design.md §M6 후속 정정 메모만 필요 (코드 변경 없음).

---

## C 항목 (Critical — Step 4 통과 차단)

### C1. `extract_graphify_status` 의 `graphify_enabled` 분기 dead code + field 부재

**근거** (`scripts/wikihub_monitor.py:230-232`):

```python
if not cfg.operations.graphify_enabled if hasattr(cfg.operations, "graphify_enabled") else False:
    # graphify_enabled field 가 OperationsConfig 에 없으면 yaml 직접 확인
    pass
```

문제:

1. **`OperationsConfig` 에 `graphify_enabled` field 자체가 없다** (`scripts/lib/config.py:44-65` 의 dataclass 정의 + `_parse_operations:149-170` 의 parser 둘 다 graphify_enabled 미정의). `hasattr` 검사가 항상 False → if 조건 = `False` (operator precedence 정합: `(not cfg.operations.graphify_enabled) if hasattr(...) else False` 와 동등이지만 hasattr False → False 분기).
2. **if body 가 `pass`** — Karpathy §1 (Think Before Coding) + §2 (Simplicity First) 모두 위반. comment 가 "yaml 직접 확인" 이라 작성하다가 만 코드.
3. **graphify_enabled=false 케이스의 정상 처리 단절** — design v3 §2.5 의 "graphify_enabled=false → `skipped (yaml toggle)`" 정상 흐름이 코드 없음. `wiki/_lint/report.md` 가 이미 lint.md Step 9 의 `graphify chain skipped (yaml toggle)` 라인을 기록하므로 234-256 라인의 키워드 grep 으로 **간접 정합**되긴 한다 (lint.md:170 정본 — `graphify_enabled == false` 시 report.md 에 라인 1줄 기록). 그래서 실 운영에서 결함 surface 안 함 — 단 design v3 §2.5 의 "graphify_enabled=false → skipped (yaml toggle)" 직접 분기 의도와 코드 의도가 어긋난 상태.

**권고**:

- (a) **dead code 제거** — 라인 230-232 모두 삭제. `cfg.operations` 파라미터의 cfg argument 자체도 unused (report.md 만 read) → 시그니처에서 `cfg` 제거 가능 (또는 향후 확장 위해 보존). 가장 단순 fix:
  ```python
  def extract_graphify_status(
      lint_run: ServiceRun,
      report_path: Path,
  ) -> tuple[Literal[...], str | None]:
      if not report_path.exists():
          return ("unknown", "report.md 부재")
      ...
  ```
- (b) 또는 design v3 §2.5 정합 흐름 유지하려면 `OperationsConfig.graphify_enabled: bool = True` field 추가 (`scripts/lib/config.py` C2-R2 와 동일 패턴) + `_parse_operations` 갱신 + 코드 분기 살리기. 단 이 path 는 변경 범위 확장.
- 최소 path = (a). report.md 정본 기반 grep 이 이미 graphify_enabled=false 케이스 흡수.

DoD §5 의 "`_lint/report.md` 위치 정합 검증" 체크박스 (line 485) 와 정합 — Step 4 통과 전 해소 필요.

---

## H 항목 (High — Step 4 통과 권장 해소)

### H1. lint 실패 라인의 `exit_code` None-guard 누락 (ingest 와 비대칭)

**근거** (`scripts/wikihub_monitor.py`):

- line 313 (ingest 섹션): `ec = r.exit_code if r.exit_code is not None else "?"` ✓
- line 333 (lint 섹션): `lint_label = "성공" if r.success else f"실패 (exit {r.exit_code}, {r.reason})"` ✗

문제: `parse_runs:166-168` 에서 `exit_status_raw is None` 또는 ValueError 시 exit_code=None — lint 의 wrapper subprocess (`timeout 300 graphify`) 가 EXIT_STATUS field 없이 종료 entry 만 emit 하는 케이스 (예: timeout) 시 lint_label = `"실패 (exit None, ...)"` 가 보고서에 노출.

**권고**: line 333 을 313 패턴 정합으로:
```python
ec = r.exit_code if r.exit_code is not None else "?"
lint_label = "성공" if r.success else f"실패 (exit {ec}, {r.reason})"
```

### H2. `_resolve_report_path` 의 WIKIHUB_HOME fallback — cfg.instance_root 미사용

**근거** (`scripts/wikihub_monitor.py:264-275`):

```python
wikihub_home = Path(os.environ.get("WIKIHUB_YAML", "")).parent
if not wikihub_home or wikihub_home == Path("."):
    wikihub_home = Path.home() / "wikihub"
```

문제:

1. `cfg.instance_root` (config.py:69, `Config` dataclass) 가 이미 정본 wikihub_home 값 보유 — yaml `instance.root` 에서 `~/wikihub` 등을 `expanduser()` 처리해서 절대경로로 lock. 이걸 무시하고 env 기반 fallback chain 만 사용하는 건 design v3 §2.3 의 "$WIKIHUB_HOME/vault/<vid>/<subpath>" 의도 정합이지만 cfg 가 이미 같은 정보를 expanduser 처리 후 보유.
2. 같은 패턴이 `main:418-420` 의 graphify report_path 계산에도 중복.
3. systemd template 의 `Environment=WIKIHUB_YAML={wikihub_home}/wikihub.yaml` 이 항상 set → fallback 미발화 — runtime 영향 미미. 그러나 ad-hoc CLI (`python wikihub_monitor.py` 직접) 시 `WIKIHUB_YAML` 미설정 → `Path("").parent == Path(".")` → `Path.home() / "wikihub"` 로 자연 분기 (install.sh:38 default 정합).
4. 단 운영자가 `WIKIHUB_HOME` 만 override 한 비표준 위치 (`/opt/wikihub` 등) 사용 시 monitor 가 `~/wikihub` 로 잘못 보고서 저장.

**권고**:

```python
wikihub_home = cfg.instance_root
```

— 4줄 → 1줄 단순화. main:418-420 의 report_path 도 같은 cfg.instance_root 사용 (DRY).

### H3. systemd `WIKIHUB_HOME` env 미설정 — `Environment=` 누락

**근거** (`_system/systemd/wikihub-monitor.service.template:13-15`):

```ini
Environment=PATH=...
Environment=WIKIHUB_YAML={wikihub_home}/wikihub.yaml
Environment=WIKIHUB_SRC={wikihub_src}
```

문제: `WIKIHUB_HOME` env 가 systemd template 에 set 안 됨. H2 의 `Path(os.environ.get("WIKIHUB_YAML", "")).parent` 가 WIKIHUB_HOME 의 surrogate 역할 — 단 design v3 §2.3 "보고서 경로 = `$WIKIHUB_HOME/vault/<vid>/<subpath>/...`" 의 의도된 env 가 사실은 `WIKIHUB_YAML` parent. 명시성 부족.

**권고**: H2 와 같이 처리 — `cfg.instance_root` 사용으로 env 의존 제거. 또는 systemd template 에 `Environment=WIKIHUB_HOME={wikihub_home}` 1줄 추가하고 monitor.py 가 `os.environ["WIKIHUB_HOME"]` 직접 사용. 후자가 ad-hoc CLI 시 운영자 명시성 ↑.

### H4. `extract_graphify_status` 의 cfg 파라미터 미사용

**근거** (`scripts/wikihub_monitor.py:220-256`): 함수가 `cfg` 받지만 230-232 의 dead code 이외 사용 없음. C1 fix 시 자연 해소.

### H5. parse_runs 의 종료 entry 미발견 시 진행 중 trailing run 처리

**근거** (`scripts/wikihub_monitor.py:142-186` + design_review_2 O5 + BL-N3):

`current_run_entries` 가 종료 entry 만나면 ServiceRun emit + reset. 단 마지막 종료 entry 이후의 trailing entries (= 진행 중 run) 은 list 에 누적 후 반환 시점에 **묵시 폐기** — design v3 / BL-N3 의 "진행 중 1회 surface" 권고 미구현.

**권고**: BL-N3 가 backlog 등록되어 있어 Step 4 통과 가능. 단 code review surface 의무 — 보고서에 `(1회 진행 중)` 라인 추가는 5~7 줄 patch 로 가능. v0.1.8 범위 외로 두면 backlog 추적 명시성 ↑.

---

## M 항목 (Medium — Step 4 자가 검증 또는 follow-up)

### M1. dead import `field` (Karpathy §2 Simplicity First)

**근거** (`scripts/wikihub_monitor.py:23`):

```python
from dataclasses import dataclass, field
```

ServiceRun dataclass 가 `field()` factory 사용 안 함 — `graphify_status: ... | None = None` / `graphify_detail: str | None = None` 모두 literal default. `field` import 불요.

**권고**: `from dataclasses import dataclass` 로 축소. 1라인.

### M2. design.md §2.7 §M6 표 4행 "systemctl --user enable wikihub-monitor.timer" 미반영 — design 권고가 잘못

**근거**:
- design v3 §2.7 line 396 — `_step9_systemd_setup` (또는 enable 영역, line 검증 필요) `systemctl --user enable wikihub-monitor.timer` 라인 추가
- install.sh 실제 패턴: 어떤 timer 도 `systemctl --user enable` explicit 호출 없음. `_step8_systemd_render:1679-1704` 가 `daemon-reload` + `try-restart` 만 + `_systemd_start_after_update:1627-1658` 가 `start`. 기존 lint.timer / pending-monitor.timer 도 같은 패턴.
- WantedBy=timers.target 이 `[Install]` 절에 있지만 `systemctl enable` 호출 부재 — `start` 가 시점에 timer 가 active 가 되고, **재부팅 후 자동 시작은 미보장** (enable 의 symlink 미생성).

검증 결과:

| 정합 항목 | 실제 |
|---|---|
| stop list (line 1602) | ✓ |
| reset-failed list (line 1621) | ✓ |
| start list (line 1656) | ✓ |
| try-restart list (line 1702) | ✓ |
| enable | **없음** (lint/pending-monitor 와 정합) |

**권고**:

- (a) 정상 — design.md §M6 표 4행 권고가 잘못된 추측. install.sh 패턴이 design 의도와 다른 방식 (`Persistent=true` + start 시점에 자연 active + 운영자가 linger 활성화로 부팅 보존). lint/pending-monitor 와 정합.
- (b) 그러나 **재부팅 후 timer 자동 발화는 별도 검증 필요** — `Persistent=true` 가 last-fire bookmark 만 보존, `WantedBy=timers.target` symlink 가 없으면 `default.target` chain 안에 들어가지 않음. 운영자 linger 활성화 + `systemctl --user start` 1회 호출이 unit 을 메모리에 lock, 재부팅 후 systemd --user 가 메모리 state 부활 시 자동 재시작 — 단 이게 systemd buglevel 의 일관 동작은 아님. 검증 backlog 후보.
- (c) design.md §M6 표 4행 "enable" 권고를 follow-up 정정 — 사실은 install.sh 가 enable 안 함, "start 의 implicit" 패턴. Step 5 doc 정정 권장 (또는 무시 가능 — pending-monitor 와 정합이라 invariant).

### M3. exit_code 의 EXIT_STATUS 미존재 케이스 분류 결함

**근거** (`scripts/wikihub_monitor.py:171`):

```python
success = exit_code in (0, 75) or unit_result == "success"
```

문제: exit_code=None + unit_result=None (둘 다 부재) 케이스 → success=False → reason 추출 → "실패" 분류. 단 종료 entry 가 MESSAGE_ID 만 매치한 경우 (예: UNIT_STOPPED MESSAGE_ID 9d1aaa27d60140bd96365438aad20286 가 보통 EXIT_STATUS / _SYSTEMD_UNIT_RESULT 도 함께 emit) — 일반적으론 발생 안 함. corner case 검증 필요.

**권고**: 운영 후 surface 시 backlog. 현재는 design v3 §M4 + BL-N3 와 묶어 acceptable.

### M4. truncate marker 의 unicode 길이 처리

**근거** (`scripts/wikihub_monitor.py:367-369`):

```python
if len(text) > _TELEGRAM_MAX_CHARS:
    cap = _TELEGRAM_MAX_CHARS - len(_TRUNCATE_MARKER)
    text = text[:cap] + _TRUNCATE_MARKER
```

문제: `_TELEGRAM_MAX_CHARS = 4000` 이 Python str 길이 (= unicode code points) 기준. Telegram API limit 4096 은 UTF-16 units (BMP 한자 1개 = 1 unit, supplementary plane emoji = 2 units). `🔭` (line 287) 는 supplementary plane → UTF-16 2 units. 보수적 4000 cap 이라 안전 margin 충분. 단 한국어 다량 + emoji 다량 시 edge — 운영 후 surface.

**권고**: 현재 4000 cap 보수적이라 OK. design_review_1 H1 + BL-N1 등록되어 있음.

### M5. `_resolve_report_path` 의 enabled vault 정렬 미정의 — multi-vault 시 비결정적

**근거** (`scripts/wikihub_monitor.py:268`):

```python
enabled_vaults = [vid for vid, v in cfg.vaults.items() if v.enabled]
```

문제: `cfg.vaults` 는 dict — Python 3.7+ insertion order 보존. `_parse_vault` 가 yaml.vaults list 순서대로 dict 에 삽입 → `enabled_vaults[0]` = yaml 정의 첫 enabled vault. 운영자가 yaml 순서 바꾸면 monitor_report_vault default 변경. design v3 §2.3 "default = vaults[0].id" 정합이지만 명시성 약함.

**권고**: 정합. 단 운영자 가시성 위해 보고서 헤더에 `monitor_report_vault: <vid>` 1줄 추가 가능 (follow-up).

### M6. format_report 의 빈 ingest_results 분기 (Q12 corner case)

**근거** (`scripts/wikihub_monitor.py:295-298`):

```python
if not ingest_results:
    lines.append("wh-ingest")
    lines.append("  (활성 vault 없음)")
```

design v3 Q12 정합 — yaml.vaults 비어 있거나 모두 disabled 시 surface. 단 design_review_1 M5 권고 "wh-ingest: (vault 미등록 — wikihub.yaml.vaults 비어있음)" 와 미세 다름 (그 권고는 design 본문에 명시 안 됨 — 흡수 미루어짐). 현재 format OK.

---

## L 항목 (Low — 가독성 / Step 5 후 follow-up)

### L1. `_resolve_report_path` 의 subpath strip — leading slash 만 제거

**근거** (`scripts/wikihub_monitor.py:273`):

```python
subpath = cfg.operations.monitor_report_subpath.strip("/")
```

운영자가 yaml 에 `subpath: "/project/wikihub/report/"` 또는 `"project//wikihub//report"` 박을 가능 — strip 은 leading+trailing 만, 중간 // 잔존. Pathlib 이 흡수하지만 forensic visibility 약함.

**권고**: backlog 또는 무시. 운영자가 yaml 직접 편집 시 발생.

### L2. `format_report` 의 timestamp KST tzinfo 의존

**근거** (line 308, 332, 287-290): `r.timestamp.strftime("%Y-%m-%d %H:%M")` — `_ts_from_journal:139` 에서 `tz=KST` 로 fixed. design.md §2.3 "KST 24시간제" 정합. 단 운영자가 다른 TZ 운영 시 (yaml `instance.timezone` 무시 — config.py:234 에 로드되지만 monitor 는 미사용) 일관성 깨질 수 있음.

**권고**: instance.timezone 사용 권장 → backlog. 현재 운영 invariant `Asia/Seoul` 라 영향 없음.

### L3. `_setup_logging` 의 stderr → systemd journal capture 정합

**근거** (line 71-76): basicConfig + stream=sys.stderr. systemd `SyslogIdentifier=wikihub-monitor` 가 stdout/stderr 둘 다 journal 캡쳐 → `journalctl --user -u wikihub-monitor` / `-t wikihub-monitor` 둘 다 OK. ops-alert.py 패턴 정합.

**권고**: 정합. 변경 없음.

### L4. write_report_file 의 atomic write — `.tmp` 잔존 케이스

**근거** (line 354-362):

```python
tmp = path.with_suffix(path.suffix + ".tmp")
...
tmp.write_text(body, encoding="utf-8")
tmp.replace(path)
```

`path.suffix` = `.md` → tmp = `path.with_suffix(".md.tmp")` 가 아니라 `path.with_suffix(".md.tmp")` — pathlib 이 `.md` 를 `.md.tmp` 로 정확히 처리. 단 write_text 실패 시 `.tmp` 잔존 — backlog CR2-MED-2 와 동일 결함 패턴. 다음 fire 가 overwrite 라 cosmetic.

**권고**: backlog. 영향 미미.

### L5. ServiceRun.graphify_detail 의 truncate 미적용

**근거** (line 68 + line 254): `graphify partial failure 의심: N=<N>, M=<M>, ratio=<r>` 의 ratio 값이 매우 길 가능성 (graphify 가 float 그대로 출력 시 — 보통 0.xx) — 100 chars cap 미적용. cosmetic 한도 내.

**권고**: 무시. graphify 가 항상 short value.

### L6. ops-alert.py 의 잔여 import (json/socket/urllib)

**근거** (`scripts/ops-alert.py:14-21`):

```python
import json
import socket
import subprocess
import sys
import urllib.error
import urllib.request
```

이 잔여는 `post_webhook` (line 166-186) 의 webhook POST 가 여전히 직접 urllib 호출 + `collect_mount_fallback_failures` (line 96-141) 의 subprocess 사용 + `socket.gethostname()` (line 246) — 모두 활성 사용. **dead 아님**. import 변경 정합.

**권고**: 정합. 변경 없음.

### L7. `format_telegram_alert_message` rename 일관 정합

**근거**: `scripts/lib/telegram.py:63` 정의 + `scripts/ops-alert.py:39` import + `scripts/ops-alert.py:290` 호출 — 모두 `format_telegram_alert_message` 일관. 이전 `format_telegram_message` 명에서 정확히 rename 완료. design v3 §5 DoD line 477 "format_telegram_message 이동" 정합.

**권고**: 정합.

---

## 통과 관점 (정합 확인된 항목)

design reviewer 정정 (Step 2.5) 흡수 검증:

| ID | design v3 권고 | 코드 반영 | 정합 |
|---|---|---|---|
| C1-R2 | `Config.vaults` dict iter | `wikihub_monitor.py:402` `[vid for vid, v in cfg.vaults.items() if v.enabled]` | ✓ |
| C2-R2 | `OperationsConfig.monitor_enabled` field 추가 | `config.py:62` `monitor_enabled: bool = True` + `:167` `_parse_operations` 갱신 + monitor_report_vault/subpath 추가 | ✓ |
| C3-R2 | render_systemd_units.py 변경 0 (glob 자동) | git diff 에 render_systemd_units.py 변경 없음 (glob 자동 발견 정합) | ✓ |
| C4-R2 | graphify 상태 = `wiki/_lint/report.md` 정본 1차 | `wikihub_monitor.py:220-256` `extract_graphify_status` 가 report.md tail 50줄 grep | ✓ (단 C1 dead code 잔존) |
| C1-R1 | 보고서에 `[ops-alert 발화됨]` 마커 | 미반영 — `format_report` 가 단순 reason 만 출력. design.md Q15 default 흡수 의도였으나 implement 누락 | ✗ (반영 안 됨 — 단 design.md §5 DoD 13 항목에 명시 없음, 흡수 의도가 모호 — backlog 후보) |
| C2-R1 | exit code 분리 (bootstrap=2/runtime=75/정상=0) + OnFailure=ops-alert.service | `wikihub_monitor.py:381 (exit 2)`, `:441 (exit 75)`, `:444 (exit 0)` + service.template:7 `OnFailure=ops-alert.service` | ✓ |
| H1-R2 | `--since "@<epoch>"` | `wikihub_monitor.py:97` `f"@{since_epoch}"` | ✓ |
| H2-R2 | `--no-pager` | `:94` | ✓ |
| H3-R2 | `timeout=30` | `:104` `timeout=_SUBPROCESS_TIMEOUT_SEC` (=30) | ✓ |
| H4-R2 | `--lines=10000` | `:95` `f"--lines={_JOURNAL_LINES_CAP}"` (=10000) | ✓ |
| H5-R2 | 발송 실패 시 journal WARN 명시 | `:438-440` `log.warning("telegram 발송 실패 — 12hr 후 자연 재시도 (exit 75, SuccessExitStatus 정합)")` | ✓ |
| M3-R2 | sys.path bootstrap | `:28-34` pending_monitor.py 패턴 정합 | ✓ |
| M4-R2 | MESSAGE_ID 종료 entry 식별 | `:41-42` + `:153,158` | ✓ (systemd PID1 catalog 정합: `9d1aaa27...` = UNIT_STOPPED, `fc2e22bc...` = UNIT_FAILED — 라벨 _MESSAGE_ID_PROCESS_EXITED 명명은 부정확하나 기능적 등가) |
| M5-R2 | truncate marker | `:46` + `:367-369` `_TRUNCATE_MARKER` | ✓ |
| M6-R2 | install.sh 3 위치 (stop/start/try-restart) | install.sh:1602/1621 stop, 1656 start, 1702 try-restart | ✓ (enable 4번째 위치는 패턴상 미존재 — pending-monitor 와 정합) |

**사용자 추가 요구 (보고서 파일 저장)**:

| 항목 | 코드 | 정합 |
|---|---|---|
| `$WIKIHUB_HOME/vault/<vid>/<subpath>/YYYYMMDD__HH_mm.md` | `_resolve_report_path:259-275` | ✓ (단 H2/H3 의 instance_root 미사용 결함) |
| atomic write | `:357-361` `.tmp` write → `replace` | ✓ |
| 24시간제 + 더블 언더스코어 | `:274` `window_end.strftime("%Y%m%d__%H_%M.md")` | ✓ Windows 호환 |
| mkdir guard | `:357` `path.parent.mkdir(parents=True, exist_ok=True)` | ✓ |
| write 실패 = warn only | `main:430-434` try/except + log.warning, telegram 발송 계속 | ✓ |
| 파일 본문 format | `:359` 헤더 + codeblock wrap | ✓ |

**graphify 자료원**:

- `report_path = wikihub_home / "wiki" / "_lint" / "report.md"` (`:421`) — lint.md:13/36/105 정본 `wiki/_lint/report.md` 정합 ✓
- 키워드 grep:
  - `"graphify chain skipped (yaml toggle)"` ✓ lint.md:170 정확 일치
  - `"graph rebuild timeout"` ✓ lint.md:183 정확 일치
  - `"graphify partial failure 의심: N=(\d+), M=(\d+), ratio=([0-9.]+)"` ✓ lint.md:191 정확 정규식 매치 (N/M/ratio 캡쳐도 동작 — design_review_1 H3 권고 (b) 흡수)

**systemd template**:

| 항목 | 검증 | 정합 |
|---|---|---|
| `OnCalendar=*-*-* 09,21:00:00 Asia/Seoul` | systemd 242+ 정합. Ubuntu 22.04=249, 24.04=255 — 운영 타깃 정합 | ✓ |
| `Persistent=true` | catch-up bookmark | ✓ |
| `AccuracySec=1min` | 09:00 ± 1min 정합 | ✓ |
| `Type=oneshot` + `SuccessExitStatus=0 75` | lint/vault 패턴 정합 | ✓ |
| `OnFailure=ops-alert.service` | exit 2 (bootstrap) 만 발화. exit 75 는 SuccessExitStatus 흡수 → 미발화. 재귀 회피 + 운영 black hole 회피 동시 달성 (C2-R1 흡수) | ✓ |
| `WorkingDirectory={wikihub_home}` + `ExecStartPre=/bin/mkdir -p {wikihub_home}` | mount@/lint/vault 패턴 정합 | ✓ |
| `TimeoutStartSec=60` | M1-R2 canonical syntax 정합 (`60sec` 아님) | ✓ |

**install.sh `_migrate_agent_schema` Group B**:

| 항목 | 위치 | 정합 |
|---|---|---|
| drift detect | install.sh:812-817 — 3개 flag 추가 (B_monitor_enabled, B_monitor_report_vault, B_monitor_report_subpath) | ✓ |
| info log | install.sh:856-858 — 3 case | ✓ |
| yaml_writer default | install.sh:908-910 — `_op_defaults` dict 에 3 entry | ✓ |

**wikihub.yaml.example**:

- line 48-51: `monitor_enabled: true` + `monitor_report_vault: null` + `monitor_report_subpath: project/wikihub/report` ✓
- 주석에 운영 의미 명시 (Telegram channel 재사용 + 최종 경로 표기) ✓

**ADR-0037 §"후속 영향"**:

- 1줄 cross-link 추가 (diff:6) — wikihub_monitor v0.1.8 + env 키 재사용 + lib/telegram.py 추출 + parse_mode 옵션화 명시 ✓
- design_review_1 M1 권고 "3번째 caller 시 ADR 격상 재검토 트리거" 는 미반영 — 단 design v3 §5 DoD 미명시 → optional follow-up

**backlog.md**:

- BL-N1 (4000 cap multi-message 분할) ✓
- BL-N2 (보고서 retention/cleanup) ✓
- BL-N3 (진행 중 entries 처리) ✓

---

## 범위 외 발견 (별도 feature / backlog 후보)

### X1. C1-R1 권고 미반영 — `[ops-alert 발화됨]` 마커 누락

design v3 §4 Q15 default 채택 ("(a) 마커 추가 — 채택") + design_review_1 C1 권고 (a) — 보고서 실패 라인 끝에 `[ops-alert 발화됨: <reason>]` 마커 부착. 구현 누락. design.md §5 DoD 13 항목에 explicit 체크박스 없음 → design 의도 trace 가 약해 미구현 surface 어려움.

**조치**: backlog 등록 권고 (BL-N4 — ops-alert 발화 마커 부착). 또는 Step 4 후속 patch 로 흡수.

### X2. `extract_graphify_status` 가 모든 lint_run 에 같은 report_path 사용 — fire 시점별 분리 안 됨

12hr 윈도우 안에 lint 가 4회 fire → report.md 가 매 fire 마다 overwrite (lint.md:204 "overwrite") → tail 50줄 = 가장 최근 fire 의 graphify 상태만. 그러나 monitor 는 4 lint_run 모두에 같은 status 부여 → 보고서가 "lint 4회 — graphify 성공 4" 또는 "skipped 4" 처럼 sample 1 의 status 가 4회 곱해짐.

**조치**: 본질적 한계 — report.md 가 overwrite 라 과거 fire 의 graphify status 추적 불가. 운영자 인지 가능한 caveat 명시 또는 graphify_status 를 lint_run 별 분리하려면 lint.md / report.md 의 history 보존 필요. Step 4 통과는 가능하나 backlog 등록 권고 (BL-N5 — graphify status historical tracking).

### X3. monitor.service 의 `WIKIHUB_HOME` env 누락 — H3 와 묶음

운영자 ad-hoc 트리거 시 `WIKIHUB_HOME` 환경변수 의존 없이 동작하지만, install.sh 의 다른 env 흐름 (`WIKIHUB_YAML`, `WIKIHUB_SRC`) 과 비대칭. service template 에 1줄 추가 또는 cfg.instance_root 사용으로 자연 해소.

### X4. lint 실패 시 graphify_status 결정 — lint 본체 실패도 report.md 가 정본 1차

lint.service 가 exit != 0 (예: yaml load fail) 시 report.md 가 미생성/stale 가능 → `extract_graphify_status` 가 `("unknown", "report.md 부재")` 반환 → 보고서에 `unknown` (= `?`) 표기. design v3 §2.5 의 "report.md 부재 또는 read fail 시 journal 보강" 2차 분기는 코드 미구현 (line 248-254 의 keyword grep 만 1차, 2차 journal MESSAGE pattern fallback 없음). design v3 §2.5 step 2 미흡수.

**조치**: design v3 §2.5 의 2차 보강 (journal MESSAGE 패턴 매칭) 가 안전 net 으로 누락. 실 운영 영향: lint 정상 fire 시 report.md 항상 갱신 → fallback 발화 빈도 낮음. backlog 등록 권고.

### X5. design v3 §2.3 caveat "운영자가 ops-alert chat 과 monitor chat 분리 escape hatch" 미구현

design_review_1 C1 권고 (c) — `MONITOR_TELEGRAM_CHAT_ID` env override. design v3 미흡수, 코드 미구현. backlog 등록 권고.

---

## 우선순위 요약 (Step 4 통과 권장 조치)

| # | 항목 | 분류 | 조치 | 예상 patch |
|---|---|---|---|---|
| 1 | C1 — `extract_graphify_status` dead code | C | 230-232 라인 삭제 (또는 cfg 파라미터 제거) | -3 줄 |
| 2 | H1 — lint_label exit_code None-guard | H | line 333 ingest 패턴 정합 | +1/-1 |
| 3 | H2 — `_resolve_report_path` cfg.instance_root 사용 | H | 264-266 라인 → cfg.instance_root 1줄 | -3 줄 |
| 4 | H3 — service template WIKIHUB_HOME env | H | template 1줄 추가 또는 H2 와 함께 해소 | +1 줄 |
| 5 | M1 — dead `field` import | M | line 23 import 축소 | -1 |
| 6 | X1 — `[ops-alert 발화됨]` 마커 (Q15 default) | M | backlog 등록 (BL-N4) | docs only |
| 7 | M2 — design.md §M6 enable 권고 정정 | M | design.md follow-up note | docs only |

총 코드 patch: **+2 / -8 (net -6)** + design.md / backlog 보강 3건.

---

## 종합 결론

**조건부 통과**. 본 구현은 design v3 의 architectural 의도 (Python 직접 + 정적 보고서 + lib/telegram.py 분리 + OnCalendar 09/21 KST + EnvironmentFile 재사용 + 보고서 파일 저장) 를 정확히 반영하고, Step 2.5 reviewer 의 16건 정정 (C/H/M) 중 14건 완전 흡수. C1 (`extract_graphify_status` dead code) + H1 (lint_label None-guard) + H2/H3 (instance_root 사용 권장) 3건 patch + design.md §M6 정정 메모로 통과 가능.

D1 정정 (Python 직접) 의 의사결정 + 사용자 §2.3 (보고서 파일 저장 + Windows 호환 파일명) + 2.5 멀티 리뷰어 흡수의 완전성 매우 높음. 구현 품질은 wikihub 의 ops-alert.py / pending_monitor.py / lint.service 의 기존 패턴과 의미론적 일관성 유지 — Karpathy §3 (Surgical Changes) + §4 (Goal-Driven Execution) 정합.

Step 5 배포 진입 전 최소 C1 해소 + H1/H2/H3 + M1 묶음 patch 1회 권장.
