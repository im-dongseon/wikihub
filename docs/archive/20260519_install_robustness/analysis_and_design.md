---
approved: 2026-05-19
---

# Analysis & Design — install_robustness (v0.1.4)

## 1. 배경 및 목적

v0.1.3 가 두 결함 closed 의도:
1. `_migrate_agent_schema` 에 in-place `--yolo` insert 분기 추가 (v0.1.0~v0.1.2 → v0.1.3+ upgrade path).
2. `wikihub-vault@.timer` / `lint.timer` template 에 `OnActiveSec` 추가 + `Persistent=true` 제거 (daemon-reload 후 timer 미발화 결함).

2026-05-19 OCI 운영 (Hermes report) — 두 fix 모두 default 호출 경로에서 무력화:

### 결함 1 — migration prompt 가 pipe stdin 에서 자동 N

`install.sh:745-752`:
```bash
if [[ -z "${WIKIHUB_NONINTERACTIVE:-}" ]]; then
    echo "F5 migration: ... 진행? [y/N]"
    read -r reply
    [[ "${reply,,}" == "y" || ... ]] || { warn "schema migration 거부"; return 0; }
fi
```

ADR-0023 의 default invocation `curl -fsSL .../install.sh | bash` → stdin = pipe → `read -r reply` 즉시 EOF (빈 input) → default N → migration 거부 → yaml 의 `--yolo` 미반영 → render 결과 unit 의 `--yolo` 누락.

### 결함 2 — fresh 후 timer restart 부재

`install.sh:1542` `_step8_systemd_render` 의 흐름:
1. render unit files (with new template)
2. `systemctl --user daemon-reload`
3. (return — start 안 함)

`--force-fresh` 또는 fresh 경로에서:
- 이미 enable+start 상태였던 timer 의 unit file 갱신됨
- daemon-reload 가 새 정의 read 하나 **active unit 의 "active since" 미갱신** (systemd 의 standard 동작 — daemon-reload 는 restart 아님)
- OnActiveSec=5min 가 stale active-since 기준 → 이미 과거 → trigger 미발화
- lint timer 가 daemon-reload 후 fire 안 함 → inactive 시점 없음 → OnUnitInactiveSec 도 baseline 부재 → NEXT="-"
- vault timer 는 600s 주기로 fire 해 inactive 시점 새로 생김 → NEXT 정상

update path 는 `_systemd_stop_before_update` + `_systemd_start_after_update` 로 명시 stop/start 수행 → 결함 미surface. fresh / --force-fresh 만 결함.

## 2. 결정 (간단)

### D1. migration prompt 의 TTY-aware 자동 진행

`-t 0` 검사 추가 — stdin 이 tty 가 아닐 때 (curl pipe / cron / Hermes subprocess) 자동 진행. `WIKIHUB_NONINTERACTIVE` env 검사도 보존 (운영자 명시 override).

migration 자체는 backup (`.wikihub-bak.<ts>`) 생성 + 보수적 transformation (schema lift + flag insert) — 자동 진행 safety risk 낮음.

### D2. `_step8_systemd_render` post-render `try-restart`

daemon-reload 직후 `systemctl --user try-restart` 명시 호출:
```bash
systemctl --user try-restart wikihub-mount@*.service \
    wikihub-vault@*.timer wikihub-lint.timer 2>/dev/null || true
```

- `try-restart`: 이미 active 인 unit 만 restart, inactive 면 no-op. 안전.
- update path 의 `_systemd_stop_before_update + _systemd_start_after_update` 와 redundant 처럼 보이나 — update path 에서는 stop 상태라 `try-restart` no-op → 영향 없음.
- fresh / --force-fresh 에서는 이미 running 인 timer 가 restart → "active since" fresh → OnActiveSec=5min 정상 trigger.
- `wikihub-mount@*.service` 도 포함 — mount unit 도 daemon-reload 후 갱신된 template 적용 위함.

## 3. 개정 범위

| 파일 | 변경 |
|---|---|
| `install.sh:745` | `[[ -t 0 ]]` 조건 추가 |
| `install.sh:1542` | daemon-reload 직후 `try-restart` 호출 추가 |
| `_system/VERSION` | 0.1.3 → 0.1.4 |
| `features/HISTORY.md` | v0.1.4 entry |

## 4. 미결 사항

없음.

## 5. Definition of Done

- [ ] `_migrate_agent_schema` 의 prompt 가 `[[ -t 0 ]]` 일 때만 fire, 아니면 자동 진행.
- [ ] `_step8_systemd_render` 가 daemon-reload 후 `try-restart` 호출.
- [ ] VERSION 0.1.4 + HISTORY entry.
- [ ] pytest 회귀 57 pass 유지.
- [ ] feature dir archive 이동.
