# Design Review 2 — wikihub_monitor (구현 가능성 + 정확성)

작성일: 2026-05-25
리뷰어: claude (서브에이전트, Plan)

---

## 종합 평가

design v1 의 architectural 방향 정합하나 **구현 가능성 layer 에서 C 4건 + H 5건 + M 6건 결함**. 가장 큰 결함:

1. **`Config.vaults` 가 dict** — design.md `[v.id for v in cfg.vaults]` 가 AttributeError
2. **`OperationsConfig.monitor_enabled` field 부재** — yaml 추가만으론 코드가 못 읽음
3. **render_systemd_units.py 의 glob 자동 발견** — design §2.7 변경 불요 (코드 0 줄)
4. **graphify 상태 자료원** — `_lint/report.md` 가 정본, journal MESSAGE 보강

---

## C 항목 (Critical — 구현 차단)

### C1. `Config.vaults` 자료형 mismatch

`scripts/lib/config.py:67` 정의: `vaults: dict[str, VaultConfig]`. ops-alert.py:243 의 정합 사용 = `list(cfg.vaults.keys())`.

수정: `vault_ids = [vid for vid, v in cfg.vaults.items() if v.enabled]`

### C2. `OperationsConfig.monitor_enabled` 코드 부재

`scripts/lib/config.py` 의 `OperationsConfig` dataclass + `_parse_operations` 둘 다 갱신 필요.

```python
# OperationsConfig
monitor_enabled: bool = True
# _parse_operations
monitor_enabled=bool(ocfg.get("monitor_enabled", True)),
```

design.md §1.4 표 누락.

### C3. render_systemd_units.py 변경 위치 오해

render_systemd_units.py:352: `templates: list[Path] = sorted(tpl_dir.glob("*.template"))` — **glob 자동 발견**. 코드 변경 불요. 단 template 파일만 추가하면 자동 render.

design.md §2.7 의 "+20 라인" 추정 → **0~5 라인** 정도. 영향 추정 +290 → +270.

### C4. graphify 상태 자료원 모호

lint.md §Step 9 검증:
- `graphify chain skipped (yaml toggle)` — `_lint/report.md` 정본 기록
- `graph rebuild timeout` — report.md 정본
- `graphify partial failure 의심: N=<N>, M=<M>, ratio=<r>` — report.md 정본

journal MESSAGE 는 stdout/stderr 캡쳐 의존이라 불안정. **`_lint/report.md` 가 정본**.

수정안: design §2.5 의 graphify 상태 분기 = `_lint/report.md` tail 기반 1차 + journal MESSAGE 2차 보강. `_lint/report.md` 위치 검증 필요 (`{wikihub_home}/wiki/_lint/report.md` 가 정확한지).

---

## H 항목 (High)

### H1. `journalctl --since` TZ 처리

design.md `since_arg = window_start.strftime("%Y-%m-%d %H:%M:%S")` 가 systemd local time 해석. OCI server `/etc/timezone` 가 UTC 라면 12시간 어긋남.

권장: `--since "@<epoch_seconds>"` 형식 (TZ 무관).

### H2. `--no-pager` 누락

ops-alert.py:117 패턴 정합 — `--no-pager` 명시 권장.

### H3. `subprocess.run` timeout 누락

ops-alert.py:119 `timeout=10` 정합. monitor 는 12hr 윈도우 대량 entries 처리 → `timeout=30` 권장.

### H4. journal 출력 메모리 폭증

graphify retry loop / OOM 시 lint.service stderr 폭주 가능 (수 MB).

권장: `Popen` + `stdout.readline()` 루프, 또는 `--lines=10000` hard cap.

### H5. Telegram 발송 실패 → 보고 손실 인지 경로 부재

exit 75 분류 시 systemd success 처리 → journal "FAIL" 안 보임 → 12hr 보고 손실.

권장: journal WARN 명시 ("monitor send failed, will retry in 12hr") + 운영자가 `journalctl --user -u wikihub-monitor.service -p warning` 로 발견 가능.

---

## M 항목 (Medium)

### M1. `TimeoutStartSec=60sec` 표기 — canonical `60s` 또는 `60` 권장

### M2. `WIKIHUB_SRC` substitution — render_systemd_units.py:212 이미 존재 (검증 통과)

### M3. monitor.py 의 sys.path bootstrap 누락

pending_monitor.py:21-24 패턴 명시 — `_SCRIPTS_DIR = Path(__file__).resolve().parent; sys.path.insert(0, str(_SCRIPTS_DIR))`.

### M4. `journalctl -o json` field 안정성

`_SYSTEMD_UNIT_RESULT` / `EXIT_STATUS` 는 unit 종료 entry 에만 emit. `MESSAGE_ID=39f53479d3a045ac8e11786248231fbf` 으로 종료 entry 안정 식별.

### M5. Telegram 4000 cap truncate marker

design §2.3 끝에 truncate 시 marker — `\n\n[보고서 cap — journalctl --user -u wikihub-monitor 로 전체 확인]`.

### M6. install.sh 변경 위치 정확화

`_systemd_start_after_update` (line 1637), `_systemd_stop_before_update` (line 1587), `try-restart` glob (line 1685) 모두 `wikihub-monitor.timer` / `wikihub-monitor.service` 추가 필요. +10 → +20 정도.

---

## L 항목

- L1 EnvironmentFile `-` leading dash 정합
- L2 single-instance vault@<vid>.service query 정합
- L3 OnCalendar TZ suffix systemd 242+ 정합 (Ubuntu 22.04 = 249, 24.04 = 255)
- L4 `Persistent=true` catch-up 동작 정합 (12hr 윈도우 자연 컴퓨트)
- L5 ruamel.yaml dependency 정합
- L6 ADR-0023 sparse-checkout scripts/ 자동 포함

---

## 통과 관점

- §2.1.1 Type=oneshot + SuccessExitStatus + Restart 미설정 — lint/vault/pending-monitor 정합
- §2.4 telegram helper 분리 + parse_mode=None — HTML escape 결함 회피
- §2.6 multi-vault `[vault: <vid>]` 섹션 분리 — instance template 자연 일반화
- §2.8 install.sh `_migrate_agent_schema` Group B `B_monitor_enabled` — 기존 10 flag 패턴 자연 확장
- §2.9 ADR-0037 cross-link only (ADR 신설 회피) — 가시성 layer 의미 ADR 격상 가치 부족

---

## 범위 외 발견

### O1. plan.md §6 D3 검증 표 graphify single-source 확인 정확

### O2. plan.md §1 작업 분류 `(신규 Hermes 스킬 추가)` 잔존 — D1 정정 후 미수정. 정정 권장.

### O3. design §5 DoD `py_compile lib/config.py` 누락 — C2 정합.

### O4. backlog.md 의 retry 정책 / multi-message 분할 surface 권장.

### O5. lint.service running 중 monitor fire 시 진행 중 entries 처리

가드: `EXIT_STATUS` 부재 entry = 진행 중 → ServiceRun 등록 skip + "1회 진행 중" 라인.

---

## 참고 파일

- `scripts/pending_monitor.py` — 1:1 reference
- `scripts/ops-alert.py` line 185-226 — send_telegram 추출 대상
- `_system/systemd/wikihub-pending-monitor.service.template` — service template 1:1 참조
- `scripts/_helpers/render_systemd_units.py` line 212, 352 — substitution + glob
- `scripts/lib/config.py` — C1 + C2 정본
- `install.sh` line 766-919 (migrate), 1587-1606 (stop), 1637-1640 (start), 1684-1685 (try-restart) — M6
- `_system/commands/lint.md` line 167-194 — graphify 상태 마커 정본 (C4)
