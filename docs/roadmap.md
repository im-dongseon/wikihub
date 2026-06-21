# Roadmap

WikiHub 의 향후 계획. 시점·내용은 변경 가능 — release 확정은 [`docs/changelog.md`](changelog.md) 의 해당 version entry 가 정본.

---

## 현재 진행

| 항목 | 상태 |
|---|---|

---

## Phase 2 검토 항목 (post-v0.1.10, 별도 ADR 필요)

| 항목 | 트리거 |
|---|---|
| **MCP SSE/HTTP transport** (현 stdio + SSH 의 외부 확장) | 회사 망 outbound SSH 불가 환경 / 다중 client 다양화 |
| **MCP write tool** (lint trigger / vault refresh 등 mutation) | 운영 수요 surface 시 — 별도 ADR + 인증 강화 (Bearer token + audit log) 필수 |
| **Cloudflare Tunnel** integration | outbound-only reverse tunnel — 회사 망 친화. SSH 자체 불가 시 fallback |
| **alias index 공통 helper 추출** (`scripts/lib/alias.py`) | lint.md playbook (markdown) ↔ wikihub_mcp.py (Python) 정본 중복이 maintenance 부담 surface 시 |

---

## v0.2.x — 미래 feature 후보

| Feature | 범위 | 상태 |
|---|---|---|
| **F6: `vault_directory`** | NAS / 로컬 디렉토리 vault type, inotifywait 통합 (Drive 외부 source 확장) | 후속 |
| 추가 vault backend (Notion / Slack archive 등) | source 다양화 | 검토 (v0.2.x+) |
| Multi-instance | 여러 wikihub 인스턴스 federation | 검토 (v0.3.x+) |

---

## v0.1.x 누적 완료 (최근 순)

자세한 변경 사항은 [`docs/changelog.md`](changelog.md) 참조.

| 그룹 | feature_id | 결과 |
|---|---|---|
| v0.1.14 | `index_md_lightweight`(#156) · `lint_file_permission_644`(#157) · opencode review model 변경 | ✅ release (2026-06-21) |
| v0.1.12 | `branch_policy_cleanup`(PR #136) · `file_map_batch_commit`(PR #135) · `nas_file_map_key`(PR #137) · `wq_alias`(PR #139) · OpenCode agent 정규화(ADR-0046) · feature directory retire(ADR-0047) | ✅ release (2026-06-08) |
| v0.1.11 | NAS vault type (ADR-0044) · install.sh SFTP remote · systemd mount 분기 · release document preflight (#114) · sync file_map batch (#133) · refspec push fix (#112) | ✅ release (2026-06-05) |
| v0.1.10 | MCP Phase 1(ADR-0043) · alias resolver(ADR-0042) · install/update hardening · deployment helpers · sidecar fixes(#108/#109) | ✅ release (2026-05-30) |
| v0.1.9 | `sync_passthrough_fix` | ✅ release |
| v0.1.8 | `entity_concept_alias_frontmatter`, `monitor_services_remove`, `systemd_prefix_realign`, `branch_strategy_formalize`, `lint_operations_improvements`, `update_path_fixes`, `install_update_hardening`, `legacy_migration_cleanup`, `graphify_path_absolute` | ✅ release |
| v0.1.7 | `yaml_schema_drift_auto_migration`, `graphify_env_namespace_isolation` | ✅ release |
| v0.1.6 | `operations_default_align` | ✅ release |
| v0.1.5 | `per_skill_model_override` | ✅ release |
| v0.1.4 | `alert_pipeline_overhaul` (later superseded by ADR-0040) | ✅ release |
| v0.1.3 | `graphify_cli_integration` | ✅ release |
| v0.1.2 | `rclone_only_unified_oauth` | ✅ release |
| v0.1.1 | `install_scope_reduction` follow-up | ✅ release |
| v0.1.0 | `v030_initial_architecture` (F1), `wikihub_schema_v1` (F2), `vault_gdrive_api` (F3), `install_runtime` (F4), `update_mode`, `install_scope_reduction`, `hermes_adapter` (F5), `dir_layout_refactor` | ✅ acceptance 달성 (2026-05-18) |

---

## 정본 / 의사결정 trace

- 결정의 정본: [`docs/adr/`](adr/) (ADR-NNNN)
- 진행 중 feature workspace: `features/<feat_id>/` (active → archive 라이프사이클, AGENTS.md §3)
- 배포 이력: `docs/release-history.md` (release 시 append)
- 누적 changelog: [`docs/changelog.md`](changelog.md)

본 roadmap 은 "**아직 결정 안 된 후보**" 수준의 진행 trace. 확정된 결정은 ADR 작성 + feature workspace 진행 시점에 정본 이동.
