# Backlog — v0.2.x 후속 작업

본 문서는 v0.1.0 의 각 feature 작업 도중 surface 한 항목 중 **v0.2.x 이후로 deferred** 결정된 것들의 인덱스. feature 단위 작업이 본 backlog 의 항목을 picking 해서 새 feature_id 로 시작한다.

## F4 install_runtime 산출 (2026-05-17 종료)

### 결함 surface — v0.1.0 범위 밖

| ID | 영역 | 항목 | 해결 방향 (제안) |
|---|---|---|---|
| ~~#12~~ | ~~agent integration~~ | ~~Hermes 의 `-z` 가 LLM prompt 직접 전달 — wikihub spec 의 `wh:<skill>` slash-command 자동 매핑 안 함~~ | ✅ **closed** by `hermes_adapter` (2026-05-18) — ADR-0032 (registration policy, external_dirs + install-time materialized SKILL.md) + ADR-0033 (`wh-` prefix lock, supersedes ADR-0011). systemd ExecStart `hermes chat --skills <name> --quiet --query "/<name> ..."`. VM `wikihub-fresh` 에서 V1·V2·V5a·V6·V7·V8·V9 + V3 end-to-end (vault@gdrive.service → hermes wh-ingest → vault-fetch.py → wiki/sources/gdrive/) PASS |
| #G | rclone mount | `_system/systemd/wikihub-mount@.service.template` 의 ExecStart 가 yaml `vaults[*].options.root_folder_id` 를 `--drive-root-folder-id` flag 로 전파 안 함 — SA 가 본인 home (empty) 만 mount → 운영자 rclone.conf 직접 편집 필요. F5 V3 검증 시 surface | F6 (또는 별도 micro feature) — `render_systemd_units.py` 의 `_cross_vault_subs` 에 `root_folder_id_for_{vid}` 추가 + mount template ExecStart 에 `--drive-root-folder-id={root_folder_id_for_%i}` substitution. yaml 의 빈 root_folder_id 케이스 fail-fast 또는 omit flag |
| ~~#A~~ | ~~install update~~ | ~~`BRANCH default=latest` 가 GitHub 부재~~ | ✅ **closed** by `update_mode` (2026-05-17) — ADR-0030 ref chain (`--version > BRANCH > latest tag > local cache > main`) |
| ~~#B~~ | ~~install update~~ | ~~Step 2 `rm -rf $WIKIHUB_HOME` destructive~~ | ✅ **closed** by `update_mode` — `_step2_update` git fetch + reset, fresh path 는 `--force-fresh` 명시 동의로 한정 |
| ~~#C~~ | ~~install update~~ | ~~update 중 vault@ timer race~~ | ✅ **closed** by `update_mode` — `_systemd_stop_before_update` 15min in-flight grace + reset-failed + daemon-reload |
| ~~#D~~ | ~~install update~~ | ~~update 후 service template 자동 redeploy~~ | ✅ **closed** by `update_mode` — `_step8_systemd_render` (install.sh 가 직접 render, hermes 독립) |
| ~~#E~~ | ~~install scope~~ | ~~`_step2_clone` 가 repo 전체를 clone — 메인테이너 내부 산출물 (~1.5 MiB) 운영 노출, AGENTS.md §1 invariant 위반~~ | ✅ **closed** by `install_scope_reduction` (2026-05-18) — ADR-0023 §"Clone scope" Note + `WIKIHUB_SPARSE_PATHS` 6필드 lock (`_system scripts install.sh wikihub.yaml.example README.md LICENSE`) |
| ~~#F~~ | ~~yaml provisioning~~ | ~~install.sh Step 5 raw cp + yaml writer 책임 분산~~ | ✅ **closed** by `install_scope_reduction` (2026-05-18) — ADR-0031 신설 + install.sh `_step5_yaml` 삭제 + `/wh:setup` Step 0 신규 (4필드 patching catalog · drift fix · 단일 helper `yaml_writer.py`) |

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

## install_scope_reduction 산출 (2026-05-18 Step 4 종결)

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

## 다음 feature 제안 (v0.1.0 완성 path)

| feat_id | 목적 | 의존 |
|---|---|---|
| ~~`hermes_adapter` (F5)~~ | ✅ archive (2026-05-18) — ADR-0032·ADR-0033 신설. wh- prefix lock + external_dirs + install-time materialized SKILL.md + Hermes detect gate (SKIP_SYSTEMD_RENDER) + flock·backup·sha256. V3 end-to-end PASS | — |
| ~~`update_mode`~~ | ✅ archive (2026-05-17) — ADR-0030 신설 | — |
| ~~`install_scope_reduction`~~ | ✅ archive (2026-05-18) — ADR-0031 신설 | — |
| ~~`dir_layout_refactor`~~ | ✅ archive (2026-05-19) — ADR-0034 신설 + 7 ADR Note. data-first layout invert (WIKIHUB_HOME=운영, WIKIHUB_SRC=시스템 XDG) + scripts/migrate_layout.sh (9-phase) + hermes_config_migrate.py. V1·V2·V3 e2e PASS | — |
| `lint_authoring` (F2 잔여) | wiki 의 정합성 검증 자동화 (lint.service) | F2 spec |
| `wiki_query` (F6) | 메인테이너/사용자가 wiki 검색 / 그래프 탐색 (`wh-query`) | F5 (hermes_adapter) |

v0.1.0 acceptance = F4 (✅) + update_mode (✅) + install_scope_reduction (✅) + F5 (✅) + dir_layout_refactor (✅, 2026-05-19). **달성**. v0.2.x 는 lint_authoring·wiki_query·multi-vault·#G (mount@ root_folder_id 전파)·dir_layout_refactor 의 잔존 R3 surface 항목 등.

---

## oauth_unify_rclone_only 산출 (2026-05-19 종료)

### v0.1.0 진입 직전 OCI 결함 surface (closed by ADR-0035)

| ID | 영역 | 항목 |
|---|---|---|
| §D | drive auth | SA write 시 `403 storageQuotaExceeded` (Personal Drive SA quota 미할당). ADR-0029 §Decision L50 (Editor 공유) + §부정/제약 L79 ("polling/mount 시나리오는 OK") 가정 깨짐. w2a 등 쓰기 흐름 surface 시점에 모델 자체 무효 |
| §I | changes feed | w2a → rclone mount(OAuth) 업로드가 vault-fetch (SA gws `changes.list`) 사이클 2회 후에도 `Status: skipped` (0건 감지). 인증 주체 비대칭으로 user-scoped changes feed 단절 |

두 항목 모두 `features/20260519_oauth_unify_rclone_only` (ADR-0035) 로 closed — rclone OAuth 단일 인증 + gws 폐기 + lsjson full snapshot diff. 상세 운영 진단은 사용자 노트 backlog (`Google Drive/wikihub/backlog/260518-backlog.md`) §D·§I·§E·§F 참조.

### v0.2.x 검토 트리거 (ADR-0035 §Consequences)

- rclone 기본 OAuth client 의 GCP Console publishing status 가 Testing 회귀 시
- rclone 이 `rclone backend changes` 명령 추가 시 (cursor 모델 회귀 가능성)
- vault 규모 N >> 10k 도달 — lsjson 응답 latency p95 > sync_interval_sec/3
- Google native 파일이 vault 에 추가 — mtime 안정성 측정 verification 필요
- rclone v2.x major upgrade 시 lsjson schema breaking change

---

## graphify_profile_namespace 산출 (2026-05-24 종료, v0.1.7 follow-up)

### v0.1.8 cleanup 묶음 — 1회성 migration 코드 일괄 삭제 (별도 feature)

운영자 base 가 v0.1.7 정착 → v0.1.0~v0.1.6 era 의 1회성 migration 코드가 영구 no-op state. 단일 feature `legacy_migration_cleanup` (가칭) 으로 일괄 정리.

| ID | 영역 | 항목 (라인 수) | 도입 시점 | 안전 마진 | 결정 |
|---|---|---|---|---|---|
| #M | install.sh `_migrate_graphify_env` | 함수 전체 (약 110줄, line ~911-1035) + main flow 호출 (line ~1917) + 머리 코멘트 + ADR-0036 §Note 의 §Decision 7 일부 | v0.1.7 follow-up (2026-05-24) | (v0.1.7→v0.1.8 = 1 minor) | **v0.1.8 삭제** — namespace 정착 후 drift 0 영구 no-op. 보존: `_step5_instance_dirs` env template (fresh install 영구 필요) + `_migrate_agent_schema` 의 `graphify_profile` 자동 추가·W_invalid warn (운영자 mistake 대응으로 영구 가치) |
| #N | install.sh `_migrate_agent_schema` **Group A** | drift detect (line ~778-786) + migration 블록 (line ~866-883) + info log case 3개 (line ~828-830). 약 30줄 | ADR-0033 (v0.1.1~v0.1.2) + ADR-0032 (v0.1.0 + v0.1.3 §Note) | 4 minor (v0.1.3→v0.1.7) | **v0.1.8 삭제** — `A_skill_prefix` (wh:→wh-) + `A_oneshot_legacy` (F5 schema lift) + `A_yolo_missing` (in-place 삽입). 운영자 base 가 v0.1.4+ 이후 install 했으면 영구 no-op |
| #O | install.sh `_migrate_agent_schema` **Group C** | drift detect (line ~807-814) + migration 블록 (line ~912-922) + info log case `C_*` (line ~831). 약 20줄 | ADR-0035 (v0.1.4/v0.1.5) | 2-3 minor (v0.1.5→v0.1.7) | **v0.1.8 삭제** — `vaults[].options.{bootstrap_allowed, credentials_path, root_folder_id, cursor_path}` legacy field cleanup. gws SA + cursor 모델 폐기 후 운영자 yaml 의 잔존 field 자동 삭제 — base 정착 후 영구 no-op. 단 #G (mount@ root_folder_id 전파, F4 backlog) 와의 의미적 충돌 0 — #G 는 신규 field 도입이고 #O 는 폐기 field cleanup |
| #P | install.sh `WIKIHUB_HOME` silent bug detect | line 98-108 (10줄) + `err` 안내 + 폐기된 `migrate_layout.sh` 참조 | ADR-0034 (pre-v0.1.0, data-first layout transition) | 7+ minor (v0.0.x→v0.1.7) | **v0.1.8 삭제** — pre-v0.1.0 운영자 base 0건 가정 정합. ADR-0034 §sub-3 의 "release 전 마지막 architectural fix" 표현이 이미 본 detect 의 영구 무용 명시 |
| #Q | `scripts/migrate_layout.sh` | 220줄 파일 전체 | ADR-0034 (pre-v0.1.0) | 7+ minor | **v0.1.8 삭제** — pre-v0.1.0 → v0.1.0 transition 1회성 helper. v0.1.0 이후 install 모든 운영자에게 영구 무의미. install.sh `WIKIHUB_SPARSE_PATHS` 의 `scripts` 도 그대로 (다른 active script 만 남음) |

### 삭제 전 확인 사항 (v0.1.8 진입 직전)

운영자 base 의 마이그레이션 정착 검증:

```bash
# #M — env namespace 정착
grep '^WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_' ~/.config/wikihub/env   # 3 키 반환 기대
grep -E '^(OLLAMA_|ANTHROPIC_API_KEY|OPENAI_API_KEY|GEMINI_)' ~/.config/wikihub/env   # 빈 결과 기대

# #N — agent schema 정착 (Group A)
yq '.agent.skill_prefix' ~/wikihub/wikihub.yaml                # "wh-" 기대 (wh: 아님)
yq '.agent.oneshot_args' ~/wikihub/wikihub.yaml                # {skill} placeholder + --yolo 포함 기대

# #O — vaults options cleanup 정착 (Group C)
yq '.vaults[].options | keys' ~/wikihub/wikihub.yaml           # legacy 4 키 (bootstrap_allowed 등) 부재 기대

# #P — WIKIHUB_HOME 의미 정착
[[ -d "$HOME/wikihub/.git" ]] && echo "WARN: legacy repo state 잔존" || echo "OK: data-first layout 정착"

# #Q — backup retention 만료 (선택)
find ~/.config/wikihub -name '*.wikihub-bak.*' -mtime +30      # 30일 만료 backup 자동 정리 확인
```

모두 통과하면 v0.1.8 cleanup feature 진입 가능.

### v0.1.8 cleanup feature 의 시작 안내

- 분류: **리팩토링** (1회성 migration 코드 일괄 삭제)
- 분석 대상 파일: `install.sh` + `scripts/migrate_layout.sh` + ADR-0034·0036 §Note (cross-reference 정리)
- 영향: install.sh ~170줄 감소 + scripts/migrate_layout.sh 220줄 삭제 = 약 390줄 감소
- ADR 작업:
  - ADR-0034 §"후속 영향" 에 "v0.1.8 의 `migrate_layout.sh` 삭제 — pre-v0.1.0 transition 완료 정합" 1줄
  - ADR-0036 §Note 2026-05-24 의 §Decision 7 (마이그레이션 절차) 정리 — `_migrate_graphify_env` 부분 삭제 + Rollback procedure 의 `<utc_iso>` placeholder 안내만 보존
  - ADR-0038 §"후속 영향" 에 "v0.1.8 _migrate_graphify_env 삭제 — 운영자 base 정착 정합" 1줄
