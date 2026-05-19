# Plan — install_robustness (v0.1.4)

- **작업 분류**: 운영 (install.sh 흐름의 두 결함 closure)
- **적용 단계 선언**:
  - Step 1 (Plan): 본 문서
  - Step 2 (Analysis & Design): 수행 (간소)
  - Step 3 (Implementation): 수행 — install.sh 2곳 + HISTORY + VERSION
  - **Step 4 (Review): 생략** — 단일 의도 (curl-pipe 시 migration / fresh 후 timer restart) closure. 외부 인터페이스 미변경. 50줄 이하.
  - Step 5 (Deployment): 수행 — `_system/` 미변경이나 install.sh 변경 → v0.1.4 patch bump. push (force 아님 — fast-forward + 새 tag).
- **예상 영향 범위**:
  - `install.sh` — (1) `_migrate_agent_schema:745` 에 `[[ -t 0 ]]` 추가, (2) `_step8_systemd_render:1542` 의 daemon-reload 후 `try-restart` 추가
  - `_system/VERSION` 0.1.3 → 0.1.4
  - `features/HISTORY.md` 신규 entry
- **메소드론 적용 여부**: 적용. v0.1.3 release window 의 self-fix 가 또 self-fix 필요한 상태이므로 별도 release 로 분리.

## 배경 (한 문장)

v0.1.3 의 두 fix (in-place `--yolo` migration + `OnActiveSec` 추가) 가 default 호출 경로 (`curl | bash`) + `--force-fresh` 경로에서 각각 무력화. Hermes OCI 운영 중 2026-05-19 surface — migration prompt 가 pipe stdin EOF 로 자동 N 거부 + fresh 후 timer 가 daemon-reload 만 받고 restart 안 돼 "active since" stale → OnActiveSec=5min 이미 과거 → lint NEXT="-" 영원히 대기.
