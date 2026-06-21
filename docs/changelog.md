# Changelog

WikiHub 의 version 별 누적 변경 기록. [Keep a Changelog](https://keepachangelog.com) 스타일.

**정본**: 본 문서는 외부 visible 누적 changelog. 결정의 정본은 `docs/adr/NNNN-*.md`, 운영 history 의 정본은 `docs/release-history.md` (release 시 append, AGENTS.md §3 Step 5). 본 changelog 는 사용자 관점 요약.

---

## [v0.1.14] — 2026-06-21 (canary)

### 추가 (Added)

- (bootstrap — first feature commit 부터 entry 누적)

---

## [v0.1.13] — 2026-06-16 (released)

### 추가 (Added)

- **wi/wl 단축명 등록** — `wh-ingest` → `wi`, `wh-lint` → `wl` 로 Hermes skill 이름 단축. `wq` alias 패턴(ADR-0039)과 동일한 frontmatter + thin command wrapper 방식. frontmatter tags/description에 `wikihub ingest`, `wikihub lint` 유지하여 자연어 명령 매칭 보존 (#150, PR #151)
- **backward compat** — `render_systemd_units.py`가 `agent.models`에서 구 `wh-ingest`/`wh-lint` 키를 `wi`/`wl`의 fallback으로 lookup (기존 운영자 yaml 무변경 호환)
- **Hermes profile 지원 (optional)** — `wikihub.yaml` `agent.profile` 필드로 Hermes profile 지정 가능. 미지정 시 default profile 사용 (backward-compat). `render_systemd_units.py`가 `--profile <name>`을 oneshot_args에 inject (#153, PR #154)

---

## [v0.1.12] — 2026-06-08 (released)

### 추가 (Added)
- **wq alias 등록** — `wh-query`와 동일 playbook(`_system/commands/query.md`)을 공유하는 `wq` skill 신규 등록. `/wq <질문>` 으로 `/wh-query`와 동일 동작 (#138, PR #139)
- **브랜치 전략 단순화 (release.sh cleanup)** — `release.sh`가 post-release bootstrap 대신 cleanup만 담당. 새 사이클 시작은 `scripts/bootstrap_version.sh` 또는 dev-flow Step 4 lazy trigger (`v0.1.13+` 정책, PR #136)
- **file_map end-of-cycle batch commit** — vault sync 시 file_map을 매 entry마다 직렬화 대신 cycle 종료 시 batch write로 전환 (#133, PR #135)
- **OpenCode agent 정규화** — `.opencode/opencode.json` 정본화 + agent prompt를 `.opencode/agent/*.md`로 분리 (ADR-0046)
- **feature directory retire** — `features/` → `features/archive/` 라이프사이클 종료, GitHub Issue 기반 workflow로 전환 (ADR-0047)

### 수정 (Fixed)
- **NAS vault file_map source_id 충돌** — NAS vault vfs refresh 없이 cycle 중복 재처리. source_id를 path 기반으로 설정 (#134, PR #137)
- **mount_diff.py path 기반 diff** — NAS vault(path 기반)와 Drive vault(fileId 기반) 병행 (#120, #129)

### 변경 (Changed)
- `scripts/release.sh` — post-release 6,7 단계(bootstrap) 제거, cleanup 전용
- `scripts/bootstrap_version.sh` — 신규 (on-demand bootstrap)
- `_system/skills/wq.frontmatter.yaml` — 신규
- `_system/VERSION` — `0.1.11` → `0.1.12`

---

[v0.1.11] — 2026-06-05 (released)

### 추가 (Added)
- **NAS vault type 지원** (ADR-0044) — `SUPPORTED_VAULT_TYPES` 에 `nas` 추가, vault type별 필수 옵션 검증, rclone rc port skip. Google Drive 외 SFTP 기반 NAS vault 운영 가능 (#117, #125)
- **install.sh rclone SFTP remote 생성** — `install.sh setup` 시 rclone SFTP remote 자동 생성, NAS vault 사전 조건 충족 (#126)
- **mount_diff.py path 기반 diff** — NAS vault (path 기반 변경 감지)를 위한 `compute_path_diff` 추가. Drive vault (fileId 기반)와 공존 (#129)
- **NAS vault mount 템플릿 분기** — systemd `mount@.service` 템플릿이 vault type에 따라 rclone mount 옵션 분기. NAS vault는 `--sftp` + `--vfs-cache-mode full` (#130)
- **NAS vault 저장 계층 ADR** — NAS vault 데이터 저장 위치·권한·백업 구조를 ADR-0044로 정본화 (#123, #131)
- **릴리스 문서 preflight** — `release.sh` 가 merge 전 `_system/VERSION`·`docs/changelog.md`·`README.md` 배지를 검증(HARD), roadmap/HISTORY 경고(WARN). 릴리스 문서 체크리스트를 `docs/agent_dev_guide.md §Step 5` 에 정본화 (issue #114)

### 수정 (Fixed)
- **NAS vault vfs_refresh 및 OAuth 검사 건너뛰기** — NAS vault (SFTP)에서 불필요한 `vfs/refresh` 호출 및 OAuth token 검사 시  `rc` port 미사용으로 인한 오류 방지 (#119, #127)
- **release.sh push refspec** — 버전 브랜치(`refs/heads/vX.Y.Z`)와 annotated 태그(`refs/tags/vX.Y.Z`) 동일명으로 인한 `git push origin main vX.Y.Z` 모호성 → 명시적 refspec 분리 (issue #112)

### 변경 (Changed)
- `_system/VERSION` — `0.1.10` → `0.1.11`

---

## [v0.1.10] — 2026-05-30 (released)

### 추가 (Added)
- **MCP server** (ADR-0043) — 외부 MCP-호환 client (Claude Desktop / Cline / IDE plugin) 가 SSH 로 wikihub VM 에 원격 spawn → wiki 데이터 read-only query.
  - `scripts/wikihub_mcp.py` (4 resource + 5 tool — `list_entities`, `list_concepts`, `read_page`, `grep_wiki`, `search_by_alias`)
  - `docs/mcp-setup.md` — 외부 client 셋업 가이드 (OCI 측 포트 4 layer + 회사 망 4 케이스 분기)
  - Hermes CLI skill (LLM-mediated playbook) 과 layer 분리 — MCP = deterministic primitive (LLM 호출 0)
- **alias-aware link resolver** (ADR-0042) — `[[mini-max]]` 가 `aliases: [MiniMax, mini-max, minimax]` 보유한 `entities/MiniMax.md` 로 자동 resolve. lint Step 1.5 alias index build (per-cycle, in-memory).
- **deployment helpers** — `promote_canary.sh` + `release.sh` (AGENTS.md §3 Step 5 자동화).
- **acceptance gate 결과 기록** — update_mode V3·V4·V5a/b·V6·V7·V8·V9a·V10·V12 multipass VM 검증 + design.md §9.2.1.
- **웹 UI 도입 검토 가이드** — `docs/web-ui-setup.md` (hermes-webui + Cloudflare Tunnel, Telegram 대체 — issue #107). 외부 컴포넌트 셋업·보안·걷어내기 절차 + AionUi 비교.

### 수정 (Fixed)
- **curl-pipe 업데이트 sidecar fix** — `_write_installed_versions_sidecar` 가 cwd 미고정으로 `python3 -m scripts.lib.sidecar` 호출 → curl-pipe 업데이트(cwd=$HOME)에서 `ModuleNotFoundError` 로 Step 4.5 abort. `(cd "$WIKIHUB_SRC" && …)` 로 해소 (issue #108 — curl-pipe 업데이트 경로 blocking)
- **sidecar uv 버전 탐지** — `INSTALLED_VERSIONS.json` 의 uv 필드 빈 문자열 → rclone/yq 와 동일하게 `uv --version` 직접 파싱 (issue #109)
- **install hardening**:
  - `_step2_update` self-restart 후 `current_version` export 보존 (downgrade warn 미발화 silent fail fix, issue #86)
  - ingest Step 0 per-vault flock — Hermes 채팅 직접 호출 race 차단 (issue #61)
  - systemctl --user enable — reboot 후 timer 자동 시작 보장 (issue #34)
- **observability** — `mount@.service` permanently failed 시 ops-alert `collect_mount_fallback_failures` env scrub bug (`XDG_RUNTIME_DIR` 제거로 silent fail) + Telegram payload 에 `fallback_diagnostic` (journalctl tail) 첨부 누락 fix (issue #29 — high priority silent failure 해소)
- **spec 정합** — update_mode V5b "fatal exit" 표현을 `_verify_version_tag_integrity` 실 동작 (warn-only) 에 정합 (issue #87)
- 기타 install.sh / lint / graphify timeout / yaml schema migration 다수 (PR #62~#94, #100/#101)

### 변경 (Changed)
- **systemd TimeoutStartSec yaml-driven** — lint/ingest 각각 `lint_timeout_start_sec` / `ingest_timeout_start_sec` override + `agent.timeout_sec` fallback (issue #104)
- **문서 정리** — `docs/reviews/`·`docs/reports/` 의 v0.1.8/v018-fix 산출물을 `features/archive/` 로 이관 (docs/ 는 영속 문서만 잔존)
- `_system/VERSION` — `0.1.9` → `0.1.10`

---

## [v0.1.9] — 2026-05-25

### 수정 (Fixed)
- **sync passthrough fix** — binary MIME (`.md`, `.txt` 등) text 확장자 기반 UTF-8 passthrough + config 기본값 정합 + 문서 보강

---

## [v0.1.8] — 2026-05-18 ~ 2026-05-25

### 추가 (Added)
- **entity/concept alias frontmatter** (ADR-0039) — duplicate detection 정합 + LLM 재생성 무한 loop 방지
- **monitor services remove** (ADR-0040 — supersedes ADR-0037) — `wikihub-monitor` + `wikihub-pending-monitor` unit 폐기, `ops-alert` 단독 운영. Telegram channel 만 carry-over
- **systemd prefix realign** (ADR-0041) — systemd unit `wikihub-*` namespace 일관화 (Hermes skill `wh-*` lock 은 ADR-0033 그대로)
- **branch strategy formalize** — feature/version branch flow + canary/latest tag SOP
- **lint operations improvements** — Step 4.5 duplicate detection · Step 7 자동 적용 (--apply 폐기, 매 cycle 자동)
- **update path fixes** — update_mode follow-up
- **install_update_hardening**

### 제거 (Removed)
- **legacy migration cleanup** — install.sh 의 v0.1.0~v0.1.6 era 1회성 migration 코드 일괄 정리

### 변경 (Changed)
- **graphify path absolute** — wh-lint playbook 의 graph.json 절대 경로 정합 + stale `wiki/graphify-out/` 자동 cleanup (ADR-0036 §"후속 영향")

---

## [v0.1.7] — 2026-05-24

### 추가 (Added)
- **graphify env namespace isolation** (ADR-0038) — `WIKIHUB_GRAPHIFY_<PROFILE>_*` 명명규칙 + Hermes parent leak 차단 + multi-profile bundle + graphify v8 CLI sync + 기존 env 파일 자동 migration
- **yaml schema drift auto-migration** — install.sh 가 신설 field 자동 추가 + ADR-0035 폐기 field cleanup (PTY-safe + idempotent)

---

## [v0.1.6] — 2026-05-22

### 변경 (Changed)
- **운영 정본 default align** — wh-lint = deepseek-v4-flash · sync_interval = 1h · hermes `delegation.model` 권장

---

## [v0.1.5]~[v0.1.4] — 2026-05-19 ~ 2026-05-21

### 추가 (Added)
- **rclone unify** (ADR-0035 — supersedes ADR-0014/0015/0017/0027/0029) — gws CLI 폐기 + SA JSON 폐기. rclone 단독 + OAuth 단일 인증. lsjson full snapshot + file_map(source_id 키) diff + false-delete 가드
- **graphify CLI 통합** (ADR-0036) — PyPI 패키지 `graphifyy` install.sh 책임 + `~/.config/wikihub/env` API key + `wiki/.graphifyignore` 정책 + 운영 비용 모델
- **alert pipeline overhaul** (ADR-0037 — superseded by ADR-0040) — Telegram channel + (이후 폐기될) pending-monitor unit
- **per-skill model override** — yaml `agent.models` (skill 별 model 지정)

---

## [v0.1.0] — 2026-05-18 (acceptance 달성)

### 추가 (Added)
- **data-first layout** (ADR-0034) — `~/wikihub/` = 운영 자산 (WIKIHUB_HOME) + `~/.local/share/wikihub/src/` = 시스템 코드 (WIKIHUB_SRC, XDG)
- **F5 hermes_adapter** (ADR-0032 + ADR-0033) — Hermes skill 등록 정책 + skill prefix `wh-` lock
- **install_scope_reduction** (ADR-0031) — sparse-checkout 6 필드 lock + install.sh yaml 미관여 + `/wh-setup` Step 0 yaml writer 단독 책임
- **update_mode** (ADR-0030) — install.sh dual-mode (fresh / update) + `_system/VERSION` detect + tag `latest` ref + rollback trap + systemd orchestration + log rotation
- **F4 install_runtime** — install.sh + systemd unit (mount@/vault@/timer/ops-alert/lint) + rclone mount + vfs/refresh + Service Account 인증 (ADR-0029)
- **F3 vault_gdrive_api** — `scripts/sync.py` (이후 ADR-0035 에서 `scripts/vault-fetch.py` 로 rename) + Drive API + cursor/file_map 영속화
- **F2 wikihub_schema_v1** — `_system/wiki-schema.md` + `_system/commands/*` 구현
- **F1 v030_initial_architecture** — 메소드론 + 초기 architecture 정본화

acceptance gate 결과 (multipass VM Ubuntu 24.04 ARM + Hermes v0.14.0): V1·V2·V3·V5a·V6·V7·V8·V9 PASS.

---

## 참조

- 각 release 의 자세한 결정은 [`docs/adr/`](adr/) 참조 (ADR 번호로 cross-ref)
- 미래 로드맵: [`docs/roadmap.md`](roadmap.md)
- 운영 history (배포 시점 기준): [`docs/release-history.md`](../docs/release-history.md) (Step 5 actions 4-5 release 시 append, AGENTS.md §3)
