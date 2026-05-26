# Backlog — v0.2.x 후속 작업

본 문서는 feature 작업 도중 surface 한 항목 중 **v0.2.x 이후로 deferred** 결정된 것들의 인덱스. feature 단위 작업이 본 backlog 의 항목을 picking 해서 새 feature_id 로 시작한다.

> closed 항목은 features/HISTORY.md 또는 features/archive/<feat_id>/ 로 흡수되므로 본 backlog 에서 정기적으로 제거된다.

## F4 install_runtime 산출

| ID | 영역 | 항목 | 해결 방향 (제안) |
|---|---|---|---|
| #G | rclone mount | `_system/systemd/wikihub-mount@.service.template` 의 ExecStart 가 yaml `vaults[*].options.root_folder_id` 를 `--drive-root-folder-id` flag 로 전파 안 함 — SA 가 본인 home (empty) 만 mount → 운영자 rclone.conf 직접 편집 필요 | `render_systemd_units.py` 의 `_cross_vault_subs` 에 `root_folder_id_for_{vid}` 추가 + mount template ExecStart substitution. yaml 의 빈 root_folder_id 케이스 fail-fast 또는 omit flag |

### R15·R16 Could 7건 (Step 4 code review)

`features/archive/20260514_install_runtime/code_review_3.md` (R15 internal consistency) + `code_review_4.md` (R16 SRE reliability) 의 backlog 항목.

| ID | 영역 | 항목 |
|---|---|---|
| R15-M4 | regex evidence | `_RCLONE_AUTH_PATTERNS` 의 SA key rotation·GCP project disabled·IAM revoke 패턴 미커버 — 운영 evidence 누적 후 surgical 추가 |
| R15-L4 | parsing | install.sh `rclone version` 의 `awk '{print $2}'` future-proof — 형식 변경 대비 |
| R15-L5 | yaml validation | yaml 내 `rclone_rc_port` 중복 검증 — config.py 의 `_parse_vault` 갱신 (v0.1.0 단일 vault 가정에서 surface 안 됨) |
| R16-M3 | rc API schema | rclone `vfs/refresh` 응답의 unknown key warn — schema 변경 detect forensic |
| R16-M4 | concurrency | ops-alert.py 의 `socket.setdefaulttimeout` race — long-running mode 전환 시 제거 |
| R16-L1 | logging | mount.py `error_snippet[:200]!r` 가독성 — `!s` + newline strip |
| R16-L4 | filesystem | `vault-fetch.py` 의 `fcntl.flock` NFS 미보장 — v0.2.x distributed 시 namespace |

### V<N> Phase 2 acceptance gate 미수행 항목

| 항목 | 내용 | 비고 |
|---|---|---|
| V18 fallback diagnostic 검증 (R14-CRIT-1) | last_failure.json **부재** 케이스에서 ops-alert 의 mount@ journalctl tail 첨부 분기 정합 | V<N> 검증 시 stale last_failure 잔존으로 미진입 — 별도 verification |

## update_mode 산출

### Should/MED 미수행분 — operational hardening

| ID | 영역 | 항목 |
|---|---|---|
| CR2-MED-1 | concurrency doc | rollback 도중 operator systemctl race — ADR-0030 Notes 에 운영 가이드 |
| CR2-MED-2 | helper | `_atomic_write_if_changed` 의 `.tmp` 잔존 정리 (process crash 시) |
| CR2-MED-3 | yaml | `os.path.expandvars` 추가 — `credentials_path: $HOME/...` 패턴 지원 |
| CR2-MED-5 | non-Ubuntu | ALLOW_NON_UBUNTU 호환성 — `find -executable`·`timeout` BSD fallback |
| CR2-MED-6 | security | `agent_binary` allowlist (v0.2.x) |
| CR2-MED-7 | dead code | `_step3_venv` 의 `venv_was_recreated` 변수 정리 |
| CR2-MED-8 | systemd | timer `Persistent=true` catch-up flood — `RandomizedDelaySec` |
| CR1-MED-1 | spec drift | §6.1 substitution key 목록 (helper key set 정합) |
| CR1-MED-2 | spec drift | VM 테스트 fix 4건 analysis_and_design back-port 명시화 |

### LOW 12건

`features/archive/20260517_update_mode/code_review_1.md` + `code_review_2.md` LOW 항목 참조.

### V<N> 미수행 (운영 surface 또는 v0.2.x)

V3 (--force-fresh confirm), V4 (vault@ mid-sync grace), V5a/b (downgrade), V6 (log rotation), V7 (req diff), V8 (network fail), V9 (tag pin), V10 (template fixture), V12 (disk full).

## install_scope_reduction 산출

### code review follow-up — v0.2.x deferred

| ID | 영역 | 항목 | 해결 방향 |
|---|---|---|---|
| ISR-1 | supply-chain | `scripts/requirements.txt` 의 `--require-hashes` 미적용 + ruamel.yaml SHA256 hash 미기재 — ADR-0028 의 uv·rclone·gws hash verify 패턴과 일관성 미달 | `uv pip compile --generate-hashes` 출력 lock + install.sh Step 3 `uv pip install --require-hashes -r` 전환 |
| ISR-2 | tests | `tests/test_config.py` 에 `mount_path != local_path` soft warn regression test 부재 — C10 (config.py:109-120) 가 코드 들어갔지만 test 미보유 | pytest fixture + `caplog` 활용 |
| ISR-3 | yaml_writer thread-safety | `scripts/lib/yaml_writer.py` 의 `_yaml_rt` module-level singleton — v0.2.x multi-thread/multi-process 호출 시 race | function-local instance + 또는 lock |
| ISR-4 | yaml_writer simplicity | `atomic_yaml_write(round_trip=False)` 분기 미사용 dead code (Karpathy §2) | 본 분기 삭제 또는 별도 helper 분리 |
| ISR-5 | yaml_writer hardening | `_cleanup_stale_tmp` 의 directory entry guard 부재 — `entry.is_file()` 추가 | 1줄 patch |
| ISR-6 | bash helper consistency | `_write_installed_versions_sidecar` 를 Python 으로 마이그레이션 — yaml_writer 와 동일 atomic invariant 공유 | v0.2.x Step 0 의 entry script 와 통합 |

### code review LOW 3건 (Step 4 follow-up commit 후 잔여)

- LOW-CR2-1: ADR-0031 §Decision B 의 `os.path.expanduser` 비교 정합 명시 (V6 false-positive 회피)
- LOW-CR2-2: setup.md "실패 처리" 표에 schema version mismatch (exit 2) 행 추가
- LOW-CR2-3: ADR-0023 Note 의 LICENSE 표현 추가 약화 ("install ≠ redistribution")
- LOW-CR1-9, LOW-CR1-10: stylistic / logging handler 검증

## 다음 feature 제안 (v0.2.x path)

| feat_id | 목적 | 의존 |
|---|---|---|
| `lint_authoring` (F2 잔여) | wiki 의 정합성 검증 자동화 (lint.service) | F2 spec |
| `wiki_query` (F6) | 메인테이너/사용자가 wiki 검색 / 그래프 탐색 (`wh-query`) | F5 (hermes_adapter) |

## oauth_unify_rclone_only 산출 — v0.2.x 검토 트리거

ADR-0035 §Consequences 의 재검토 조건:

- rclone 기본 OAuth client 의 GCP Console publishing status 가 Testing 회귀 시
- rclone 이 `rclone backend changes` 명령 추가 시 (cursor 모델 회귀 가능성)
- vault 규모 N >> 10k 도달 — lsjson 응답 latency p95 > sync_interval_sec/3
- Google native 파일이 vault 에 추가 — mtime 안정성 측정 verification 필요
- rclone v2.x major upgrade 시 lsjson schema breaking change

## branch_strategy_formalize 산출 — design/code review 범위 외

| ID | 영역 | 항목 | 출처 | 우선순위 |
|---|---|---|---|---|
| BL-1 | scripts | `scripts/promote_canary.sh` / `release.sh` 헬퍼 — Step 5 5 액션 누락 방지 (메인테이너 단일 명령 wrap) | design_review_2 L5 | low (수동 절차로 충분) |
| BL-2 | GitHub repo settings | Tag protection rule 정립 — `v*.*.*` 보호, `latest`/`canary` 는 protect 금지 (force-update 필요) | design_review_2 M2 | medium (v0.1.8 release 직전 확인 권장) |
| BL-3 | 버전 정책 | patch 자릿수 도입 결정 (v0.X.Y.Z 토폴로지) — hotfix 빈도 증가 시 검토 | plan.md Q2 default 보류 | low (현재 미발생) |
| BL-4 | 메소드론 | squash commit 안에 다중 feat_id 가 합쳐지는 경우의 conventional commit naming 컨벤션 | design_review_2 범위 외 5 | low (현재 1 feat = 1 squash 정합) |
| BL-5 | 메소드론 | AGENTS.md ↔ docs/agent_dev_guide.md 정본 분리 모델 재검토 — 중복 표 (Step 5 5 액션, Tag 운영, mermaid) 를 한쪽으로 통일하고 다른 쪽은 참조 축약 | code_review_2 O2 | medium (정본 동기화 결함 재발 방지) |
| BL-6 | 메소드론 | `git push --force-with-lease` 첫 push 동작 (lease 부재 시) — 사실상 `--force` 와 동등, race-safe 미보장. push 직전 `git fetch origin v0.X.Y` 선행 권고 메소드론 보강 | code_review_2 O3 | low (단일 maintainer 모델에서 발생 빈도 낮음) |
| BL-7 | 버전 정책 + 거버넌스 | production OCI critical bug 시 hotfix 시나리오 — BL-3 (patch 자릿수 도입) 와 결합. v0.2.x 진입 전 결정 필수 | code_review_2 O4 + R1-H5 | medium (production 사고 시 행동 불가 위험) |

---

## wikihub_monitor 산출 (2026-05-25 진행, v0.1.8 묶음)

본 feature 의 design review 에서 surfacing 된 범위 외 항목.

| ID | 영역 | 항목 | 출처 | 우선순위 |
|---|---|---|---|---|
| ~~BL-N1~~ | ~~scripts~~ | ~~Telegram message 4000 chars cap 초과 시 multi-message 분할~~ — **closed by ADR-0040 (2026-05-26)**: wikihub_monitor 폐기로 본 항목 자연 무효 (ops-alert fatal alert 는 페이로드 짧음). | ~~design_review_1 H1 + design_review_2 M5~~ | closed |
| ~~BL-N2~~ | ~~retention~~ | ~~`$WIKIHUB_HOME/vault/<vid>/<subpath>/YYYYMMDD__HH_mm.md` 누적~~ — **closed by ADR-0040**: monitor 보고서 파일 자체가 사라짐. | ~~사용자 §2.3 권고~~ | closed |
| ~~BL-N3~~ | ~~parse~~ | ~~lint.service 가 running 중일 때 monitor fire 시 진행 중 entries 처리~~ — **closed by ADR-0040**: monitor 자체 폐기. | ~~design_review_2 O5~~ | closed |
| ~~BL-N4~~ | ~~observability~~ | ~~monitor self-health surface~~ — **closed by ADR-0040**: monitor + pending-monitor 둘 다 폐기로 본 항목 자연 무효. | ~~code_review_2 L9~~ | closed |
| BL-N5 | systemd | timer enable catalog 정비 — `wh-lint.timer` / `wh-ingest@<vid>.timer` 가 install.sh 가 start 만, explicit enable 없음. reboot 후 자동 start 미보장. (2026-05-26 ADR-0040: pending-monitor.timer / monitor.timer 항목은 unit 자체 폐기로 자연 제거 — `wh-*` 만 잔존) | code_review_2 M1 | medium (reboot 후 silent break) |
| BL-N6 | security | subprocess env scrub — ops-alert.py 가 journalctl subprocess 호출 시 TELEGRAM_MONITOR_BOT_TOKEN 전파. `env={"PATH": ...}` explicit scrub 권장. (2026-05-26 ADR-0040: monitor.py 부분 폐기 — ops-alert.py 만 잔존) | code_review_2 M4 | low (single-user OCI 모델에선 race window 좁음) |

---

## lint_operations_improvements 산출 (2026-05-25 진행, v0.1.8 묶음)

| ID | 영역 | 항목 | 출처 | 우선순위 |
|---|---|---|---|---|
| BL-N7 | graphify | `--api-timeout` (600s) vs wrapper `graphify_timeout_sec` (900s) 의 운영 정합 검증 — backend 별 LLM latency 누적 실측 | design_review_1 M1 | low |
| BL-N8 | graphify | graphify_timeout_sec 의 backend 별 toggle (`operations.graphify_profile.<profile>.timeout_sec`) — ollama vs cloud 별도 적정값 | design_review_2 H3 | low |
| BL-N9 | data model | wiki link resolver 의 alias 인식 — `[[mini-max]]` 가 `MiniMax` page 로 자동 해석. 현행 sed 치환으로 link 정합. resolver layer 통합 시 별도 ADR | ADR-0039 §"재검토 트리거" | low |
| BL-N10 | lint | lint Step 4.5 의 alias 비교 알고리즘 deterministic Python helper 분리 — 현행 LLM 책임, daily token cost 누적. subprocess 로 token 0 화 | design_review_2 M4 | low |
| BL-N11 | lint | lint cycle 의 contradiction check (Step 6) LLM merge idempotency 가드 — concept 재등장 시 entity 본문 LLM merge 재호출 차단 (현행 lint.md Step 7 본문에 정책만, 구현 추후) | design_review_2 M5 | low |

> 이전 design 의 BL-N7 (lint-apply 결과 surface), BL-N8 (lint-apply race), BL-N10 (lint-apply yaml gate cost) 는 사용자 결정 (2026-05-25) 으로 `--apply` flag 폐기 + 별도 timer 미생성 → 무효화 / 흡수. lint.timer 단일 사이클이 매 cycle 진단 + 적용 default.

---

## update_path_fixes 산출 (2026-05-26 진행, v0.1.8 묶음)

| ID | 영역 | 항목 | 출처 | 우선순위 |
|---|---|---|---|---|
| BL-N12 | observability | wikihub-graphify.service bootstrap fail (exit 2) → ops-alert.service 가 last_failure.json 부재로 silent skip — wikihub_monitor 의 H2 와 같은 결함 inheritance. `scripts/wikihub_graphify.sh` 에 `_emit_bootstrap_alert` 패턴 (env token 직접 read + Telegram 발송) 또는 별도 last_failure.json write 추가 | code_review_2 C1 | medium |
| BL-N13 | observability | wikihub_monitor 보고서에 `wikihub-graphify.service` 결과 surface — 현행 monitor 가 lint + vault 만 수집. graphify chain 의 별도 systemd unit 결과도 가시화 (`wh-graphify`) | design v2 §3 Q2 | medium |
| BL-N14 | scripts | `scripts/wikihub_graphify.sh --rebuild` 가 systemd ExecStart 의 인자로 전달 불가 — `systemctl --user start wikihub-graphify.service --rebuild` 미지원. 운영자 manual 호출 시만 가능. helper alias 또는 별도 service `wikihub-graphify-rebuild.service` 검토 | code_review_1 M2 | low |
| BL-N15 | install | `_migrate_agent_schema` 의 detect / write Python heredoc 2개 분리 → race window + DRY 위반. 단일 heredoc 통합 검토 | code_review_1 M3 | low |
| BL-N16 | scripts | `wikihub_graphify.sh` 의 N/M partial failure 가드가 stderr warn 만, ops-alert trigger 안 함. 운영자 자동 인지 path 부재 | design v2 §3 Q3 | low |
| BL-N17 | install | `_install_graphify` 가 v0.1.0 → v0.1.8 update path 의 자동 trigger 검증 — v0.1.5 도입 후 venv 에 graphifyy 부재 운영자 base 의 자동 install | code_review_2 L | low |
