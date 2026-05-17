# Backlog — v0.2.x 후속 작업

본 문서는 v0.1.0 의 각 feature 작업 도중 surface 한 항목 중 **v0.2.x 이후로 deferred** 결정된 것들의 인덱스. feature 단위 작업이 본 backlog 의 항목을 picking 해서 새 feature_id 로 시작한다.

## F4 install_runtime 산출 (2026-05-17 종료)

### 결함 surface — v0.1.0 범위 밖

| ID | 영역 | 항목 | 해결 방향 (제안) |
|---|---|---|---|
| #12 | agent integration | Hermes 의 `-z` 가 LLM prompt 직접 전달 — wikihub spec 의 `wh:<skill>` slash-command 자동 매핑 안 함. ADR-0002·0011·0012 의 hermes invocation 가정과 실 Hermes 동작 mismatch | F5 (hermes_adapter) — Hermes skill 정의 (SKILL.md) 또는 ADR-0012 옵션 β (wrapper script dispatcher) 채택. v0.1.0 운영 시작의 blocker |
| ~~#A~~ | ~~install update~~ | ~~`BRANCH default=latest` 가 GitHub 부재~~ | ✅ **closed** by `update_mode` (2026-05-17) — ADR-0030 ref chain (`--version > BRANCH > latest tag > local cache > main`) |
| ~~#B~~ | ~~install update~~ | ~~Step 2 `rm -rf $WIKIHUB_HOME` destructive~~ | ✅ **closed** by `update_mode` — `_step2_update` git fetch + reset, fresh path 는 `--force-fresh` 명시 동의로 한정 |
| ~~#C~~ | ~~install update~~ | ~~update 중 vault@ timer race~~ | ✅ **closed** by `update_mode` — `_systemd_stop_before_update` 15min in-flight grace + reset-failed + daemon-reload |
| ~~#D~~ | ~~install update~~ | ~~update 후 service template 자동 redeploy~~ | ✅ **closed** by `update_mode` — `_step8_systemd_render` (install.sh 가 직접 render, hermes 독립) |
| #E | install scope | `_step2_clone` 가 repo 전체를 clone — `docs/`·`features/`·`tests/`·`AGENTS.md` 등 메인테이너 내부 산출물 (~1.5 MiB) 이 운영 타깃에 노출. AGENTS.md §1 의 Dev/Ops Zone 분리 invariant 위반 | `install_scope_reduction` feature — `git clone --filter=blob:none --sparse-checkout` 으로 `_system`·`scripts`·`install.sh`·`wikihub.yaml.example`·`README.md` 만 fetch. ADR-0023 본문에 "clone scope" 항목 보강 (supersede 아님). **의존: `update_mode` 완료 후 진입** (install.sh 동시 편집 회피) |
| #F | yaml provisioning | install.sh Step 5 `cp wikihub.yaml.example → wikihub.yaml` 가 raw template 그대로 복사 — 운영용 값 (instance.root override, vault paths, gws_min_version 등) 메인테이너 수동 편집 의존. yaml writer 책임이 install.sh + /wh:setup 두 곳 분산 (race·이중 정본 위험) | `install_scope_reduction` feature 와 묶음 — install.sh 의 yaml 개입 **0건** 으로 축소 (Step 5 cp 삭제). `/wh:setup` 에 Step 0 신규 — `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml` 부재 시 repo 의 `wikihub.yaml.example` 을 template 으로 read → derived 값 patching → atomic write. .example 은 repo 의 read-only template 으로 영구 거주, instance 에는 `wikihub.yaml` 만 — 위치 분리로 운영자 혼동 차단. setup.md "install.sh와의 관계" 표 갱신 + 신규 ADR-0031 후보 (template materialization 정책 + idempotent drift fix). **의존: `update_mode` 완료 후 #E 와 동시 진행** |

### R15·R16 Could 8건 (Step 4 code review)

`features/archive/20260514_install_runtime/code_review_3.md` (R15 internal consistency) + `code_review_4.md` (R16 SRE reliability) 의 backlog 항목.

| ID | 영역 | 항목 |
|---|---|---|
| R15-M4 | regex evidence | `_RCLONE_AUTH_PATTERNS` 의 SA key rotation·GCP project disabled·IAM revoke 패턴 미커버 — 운영 evidence 누적 후 surgical 추가 |
| R15-L4 | parsing | install.sh `rclone version` 의 `awk '{print $2}'` future-proof — 형식 변경 대비 |
| R15-L5 | yaml validation | yaml 내 `rclone_rc_port` 중복 검증 — config.py 의 `_parse_vault` 갱신 (v0.1.0 단일 vault 가정에서 surface 안 됨) |
| R16-M3 | rc API schema | rclone `vfs/refresh` 응답의 unknown key warn — schema 변경 detect forensic |
| R16-M4 | concurrency | ops-alert.py 의 `socket.setdefaulttimeout` race — long-running mode 전환 시 제거 |
| R16-L1 | logging | mount.py `error_snippet[:200]!r` 가독성 — `!s` + newline strip |
| ~~R16-L2~~ | ~~log rotation~~ | ~~install.log 의 rotation 없음~~ | ✅ **closed** by `update_mode` — `_rotate_install_log` (tee 시작 전, 7일/10MB, PID suffix, 7개 보관) |
| R16-L4 | filesystem | `vault-fetch.py` 의 `fcntl.flock` NFS 미보장 — v0.2.x distributed 시 namespace |

### V<N> Phase 2 acceptance gate 미수행 항목

| 항목 | 내용 | 비고 |
|---|---|---|
| V18 fallback diagnostic 검증 (R14-CRIT-1) | last_failure.json **부재** 케이스에서 ops-alert 의 mount@ journalctl tail 첨부 분기 정합 | V<N> 검증 시 stale last_failure 잔존으로 미진입 — 별도 verification |

## update_mode 산출 (2026-05-17 종료)

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

## 다음 feature 제안 (v0.1.0 완성 path)

| feat_id | 목적 | 의존 |
|---|---|---|
| `hermes_adapter` (F5) | wikihub 의 `wh:*` skill 을 Hermes skill 시스템에 정합화. ADR-0011·0012 spec 보강 또는 wrapper dispatcher 채택. 결함 #12 lock | F4 archive |
| ~~`update_mode`~~ | ✅ archive (2026-05-17) — ADR-0030 신설 | — |
| `install_scope_reduction` | 결함 #E + #F — install.sh clone scope 한정 (sparse-checkout, ADR-0023 보강) + yaml provisioning 책임을 `/wh:setup` Step 0 으로 이전 (install.sh yaml 개입 0건, .example 위치 분리, ADR-0031 후보) | `update_mode` archive 후 진행 가능 |
| `lint_authoring` (F2 잔여) | wiki 의 정합성 검증 자동화 (lint.service) | F2 spec |
| `wiki_query` (F6) | 메인테이너/사용자가 wiki 검색 / 그래프 탐색 (`wh:query`) | F5 (hermes_adapter) |

v0.1.0 acceptance = F4 (✅) + F5 + (선택) update_mode (✅). v0.2.x 는 lint_authoring·wiki_query·multi-vault·install_scope_reduction 등.
