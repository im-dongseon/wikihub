# Code Review 2 — wikihub_monitor (운영 안전성 + 보안 + OCI 실제 동작)

작성일: 2026-05-25
리뷰어: claude (서브에이전트, Plan)

---

## 종합 평가

design v3 운영 안전성·보안 측면 대체로 양호. ops-alert send_telegram 추출 + parse_mode 옵션화는 HTML escape 결함 격리 정합. systemd timer / Persistent / SuccessExitStatus 의 조합 의도와 정합. install.sh 3 위치 patch (stop/reset-failed/start/try-restart) 정합.

**High 2건 즉시 fix 권장** (H1 graphify_status leak + H2 monitor.service OnFailure silent).

---

## H 항목

### H1. graphify_status 가 모든 lint_run 에 동일 값 — `_lint/report.md` overwrite 모델 미고려

- 위치: `scripts/wikihub_monitor.py:417-425`
- 결함: report.md 는 lint cycle 별 overwrite. `for lint_run in lint_results: extract_graphify_status(lint_run, cfg, report_path)` 가 모든 run 에 같은 report.md read → graphify_status 가 항상 "마지막 cycle" 1개로 통일.
- 결과: 12hr 동안 lint 4회 (3회 성공, 마지막 1회 timeout) → 보고서가 4회 모두 timeout 으로 잘못 surface.
- 권장: 단 1회 호출 + 마지막 run 에만 적용. 나머지 run = "unknown (overwrite)" 또는 표시 다운그레이드.

### H2. monitor.service OnFailure 가 실질적 silent — ops-alert 가 last_failure.json 부재로 no-op

- 위치: `wikihub-monitor.service.template:7` + `ops-alert.py:202-212`
- 결함: monitor.py exit 2 → systemd OnFailure trigger → ops-alert.py `collect_last_failures` → monitor 의 last_failure.json 없음 → `log.info("no last_failure"); return 0`. **운영자 텔레그램 알림 없음**.
- 권장: monitor.py bootstrap fail catch 안에서 직접 send_telegram (env token 직접 read) 후 exit 2.

---

## M 항목

### M1. monitor.timer enable 부재 — reboot 후 timer 미동작 위험

- install.sh:1656 가 start 만, enable 부재. 단 lint.timer / pending-monitor.timer 도 동일 결함 (기존부터 잠재).
- 권장: 별도 cleanup feature 또는 setup.md `--enable` catalog 정비.

### M2. `_lint/report.md` tail 파싱이 lint windowing 무관 (H1 부분집합)

### M3. monitor.py 가 WIKIHUB_HOME env 직접 사용 안 함

- service template 에 `Environment=WIKIHUB_HOME={wikihub_home}` 추가 권장. monitor.py 가 `os.environ.get("WIKIHUB_HOME")` 우선 사용.

### M4. secret (TELEGRAM_ALERT_BOT_TOKEN) child subprocess env 전파

- 위험도 낮음 — single-user OCI 모델에서 race window 좁음. backlog.

---

## L 항목

- L1. MESSAGE_ID `fc2e22bc6ee647b6b90729ab34a250b1` 부정확 — coredump UUID (실제 design 의도 = "process exited"). 운영 영향 미미 (`_SYSTEMD_UNIT_RESULT` / `EXIT_STATUS` 가 1차).
- L2. boundary entry phantom merged run — 12hr 윈도우 1개 손실, 통계 영향 미미. backlog.
- L3. ServiceRun.timestamp 가 종료 시각인데 design 주석 "시작 시각" — cosmetic.
- L4. rclone FUSE mount 의 atomic rename — .tmp 부유. 무시 가능.
- L5. 보고서 파일 vault share scope 외부 노출 — wikihub.yaml.example 주석 1줄 권고.
- L7. extract_graphify_status:230-232 dead code (hasattr + pass).
- L9. SuccessExitStatus=75 → silent → monitor self-health 부재. backlog.

---

## 통과 관점

- systemd unit syntax Asia/Seoul + Persistent + AccuracySec 정합 (242+, Ubuntu 22.04+ 충족)
- OnCalendar comma syntax 정합
- bash -n + py_compile 4 파일 모두 pass
- secret 노출 검증 (보고서/log 미노출)
- EnvironmentFile=-%h/.config/wikihub/env 정합
- format_telegram_alert_message HTML escape 책임 분리 정합
- multi-vault journalctl unit name 정합
- race/동시성 — Type=oneshot + Active 상태 새 invocation 차단 정합

---

## 범위 외 (backlog 등록 권고)

- `/wh-setup --enable` timer enable catalog 정비 (M1 본질책)
- `_lint/report.md` append-with-cycle-marker 모델 (H1 본질책)
- subprocess env scrub (M4)
- monitor self-health surface (L9)
- boundary detection (L2)

---

## 결론

승인 가능. H1 + H2 squash 전 patch. M1 즉시 또는 hotfix. M2~M4 + L 대부분 backlog.
