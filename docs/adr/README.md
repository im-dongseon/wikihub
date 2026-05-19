# Architecture Decision Records (ADR)

WikiHub의 모든 아키텍처/설계 결정을 영구 기록합니다. 결정의 **정본(source of truth)** 은 이 디렉토리의 개별 ADR 파일이며, `features/` 산출물과 `features/HISTORY.md`는 ADR을 참조만 합니다.

## 작명 규칙

```
NNNN-{kebab-case-title}.md
```

- `NNNN`: 4자리 0-padded 시퀀스 (`0001`, `0002`, …). 1부터 시작.
- `kebab-case-title`: 소문자 + 하이픈. 결정 주제를 간결히 표현 (예: `source-collision-policy`).

## Status

| Status | 의미 |
|---|---|
| **Proposed** | 제안됨. 아직 미결정 (사용 빈도 낮음 — 보통 결정 후에 ADR 작성) |
| **Accepted** | 채택됨. 활성 결정 |
| **Deprecated** | 더 이상 권장되지 않음 (대안 ADR이 명시되지 않은 경우) |
| **Superseded** | 다른 ADR로 대체됨. `Superseded by: ADR-NNNN` 필드로 연결 |

## 결정 변경 정책

결정을 뒤집을 때:

1. 새 ADR 생성. `Status: Accepted`, `Supersedes: ADR-NNNN` 명시
2. 기존 ADR Status를 `Superseded`로 변경. `Superseded by: ADR-MMMM` 추가
3. 기존 ADR은 **삭제하지 않는다** — 과거 결정 맥락을 보존해야 supersede 이유가 추적됨

## 참조 형식

다른 문서에서 ADR을 참조할 때는 식별자만 사용:

```markdown
… ADR-0001 채택에 따라 …
```

링크가 필요하면:

```markdown
[ADR-0001](../../docs/adr/0001-source-collision-policy.md)
```

## 신규 ADR 작성

`template.md`를 복사해 다음 시퀀스 번호로 이름을 짓는다.

```bash
cp docs/adr/template.md docs/adr/NNNN-{slug}.md
```

작성 시점은 메소드론 Step 2(분석및설계) 중 미결 사항을 결정하는 시점.

## 인덱스

| ID | Title | Status | Date | Feature |
|---|---|---|---|---|
| [ADR-0001](0001-source-collision-policy.md) | Source collision policy (α: vault namespace) | Accepted | 2026-05-13 | `20260513_v030_initial_architecture` |
| [ADR-0002](0002-hermes-invocation-interface.md) | Hermes invocation interface (CLI subprocess) | Accepted | 2026-05-13 | `20260513_v030_initial_architecture` |
| [ADR-0003](0003-headless-oauth-strategy.md) | Headless OAuth strategy (Workspace + token-scp) — **Superseded by ADR-0029** | Superseded | 2026-05-13 | `20260513_v030_initial_architecture` |
| [ADR-0004](0004-drive-access-mechanism.md) | Drive access mechanism (Direct API, not gws CLI) | **Superseded** by ADR-0014 | 2026-05-13 | `20260513_v030_initial_architecture` |
| [ADR-0005](0005-index-and-log-locality.md) | wiki/index.md·log.md 위치성 (index 단일+lint 갱신 / log vault별) | Accepted | 2026-05-13 | `20260513_wikihub_schema_v1` |
| [ADR-0006](0006-ingest-orchestration-model.md) | Ingest orchestration (agent as orchestrator, unified) | Accepted | 2026-05-13 | `20260513_wikihub_schema_v1` |
| [ADR-0007](0007-state-storage-format.md) | State storage format (all JSON, drop SQLite) | Accepted | 2026-05-13 | `20260513_wikihub_schema_v1` |
| [ADR-0008](0008-lint-permission-model.md) | /lint 권한 분류 (비파괴 자동 / 파괴 --apply) | Accepted | 2026-05-13 | `20260513_wikihub_schema_v1` |
| [ADR-0009](0009-setup-responsibility.md) | /setup의 책임 (wikihub.yaml→systemd 동기화 + 환경 검증) | Accepted | 2026-05-13 | `20260513_wikihub_schema_v1` |
| [ADR-0010](0010-operational-tooling-split.md) | 운영 도구 책임 분할 (install.sh + /wh:setup, deploy.sh 폐기) | Accepted | 2026-05-13 | `20260513_wikihub_schema_v1` |
| [ADR-0011](0011-skill-namespace-prefix.md) | Agent skill namespace prefix (wh:) — **Superseded by ADR-0033** | Superseded | 2026-05-13 | `20260513_wikihub_schema_v1` |
| [ADR-0012](0012-agent-invocation-abstraction.md) | Agent invocation 추상화 (yaml.agent.invocation + install.sh 매핑) | Accepted | 2026-05-13 | `20260513_wikihub_schema_v1` |
| [ADR-0013](0013-entity-concept-extraction-policy.md) | entity·concept 추출 정책 (분류·임계·신뢰 경계) | Accepted | 2026-05-13 | `20260513_wikihub_schema_v1` |
| [ADR-0014](0014-drive-access-mechanism-revisited.md) | Drive 접근 — gws CLI 채택 (ADR-0004 supersede) — **Superseded by ADR-0035** | Superseded | 2026-05-13 | `20260513_wikihub_schema_v1` |
| [ADR-0015](0015-gws-pinned-version-and-install-channel.md) | gws pinned version + 설치 채널 — `0.22.5` lock, Rust target triple asset 이름, GitHub Releases binary + SHA256 (V8 결함 #3·#4a fix) — **Superseded by ADR-0035** | Superseded | 2026-05-14 / 2026-05-17 (V8 hand-check) | `20260514_install_runtime` |
| [ADR-0017](0017-gws-stderr-error-mapping.md) | gws stderr → wikihub exit code 매핑 (scope 컬럼 — file vs vault) — **Superseded by ADR-0035** (Accepted 도달 전 무효화) | Superseded | 2026-05-14 | `20260514_install_runtime` |
| [ADR-0018](0018-install-script-single-model.md) | install.sh 단일 모델 (deploy.sh 미존재) | Accepted | 2026-05-14 | `20260514_install_runtime` |
| [ADR-0019](0019-per-vault-systemd-unit-substitution.md) | per-vault systemd unit (file substitution + Python helper) | Accepted | 2026-05-14 | `20260514_install_runtime` |
| [ADR-0020](0020-python-venv-location.md) | Python venv 위치 — `~/.local/share/wikihub/venv` (XDG) | Accepted | 2026-05-14 | `20260514_install_runtime` |
| [ADR-0021](0021-reboot-resilience-user-systemd-linger.md) | reboot resilience — user-level systemd + linger + V12 fallback | Accepted | 2026-05-14 | `20260514_install_runtime` |
| [ADR-0022](0022-first-ingest-entry-point.md) | 첫 ingest 진입점 + timer enable 게이트 (E3 + 흐름 역전) | Accepted | 2026-05-14 | `20260514_install_runtime` |
| [ADR-0023](0023-install-script-distribution-curl-pipe.md) | install.sh 배포 — curl-pipe + tag `latest` + clean install + safety guard 3개 | Accepted | 2026-05-14 | `20260514_install_runtime` |
| [ADR-0024](0024-fatal-alert-contract.md) | fatal 알림 contract — last_failure.json + dedup + Hermes 이중 경로 (v9 본문 minor: `scope="mount"` 추가) | Accepted | 2026-05-14 / 2026-05-15 (v9 minor) | `20260514_install_runtime` |
| [ADR-0025](0025-rclone-mount-adoption.md) | rclone mount 채택 — vault 자체 mount + vfs-cache full + GitHub Releases binary + SHA256SUMS verify + curl retry | Accepted | 2026-05-15 | `20260514_install_runtime` |
| [ADR-0026](0026-vfs-refresh-policy.md) | vfs refresh 정책 — 사이클 시작 시 `vfs/refresh recursive=true` 1회 (K1) | Accepted | 2026-05-15 | `20260514_install_runtime` |
| [ADR-0027](0027-rclone-gws-responsibility-split.md) | rclone vs gws 책임 분리 — Path C+ 정본화 (rclone = mount/다운로드/UX, gws = changes API). ADR-0014·0006 supersede 없음 — **Superseded by ADR-0035** | Superseded | 2026-05-15 | `20260514_install_runtime` |
| [ADR-0028](0028-uv-python-runtime.md) | uv 기반 Python runtime — GitHub Releases binary + SHA256, Python 3.12 pinned, `python3-venv` apt 의존 제거 (V8 결함 #1·#2·#5·#6 fix) | Accepted | 2026-05-17 | `20260514_install_runtime` |
| [ADR-0029](0029-service-account-auth.md) | Service Account 기반 Drive 인증 (gws + rclone 둘 다 SA JSON key, Personal Google OK, vault 폴더 명시 공유) — **Superseded by ADR-0035** (Personal Drive SA write 불가 실증) | Superseded | 2026-05-17 | `20260514_install_runtime` |
| [ADR-0030](0030-update-workflow-orchestration.md) | install.sh dual-mode lifecycle (`_step2_update` git fetch + reset, `--force-fresh`/`--version` flag, systemd stop/start orchestration + rollback trap, log rotation) | Accepted | 2026-05-17 | `20260517_update_mode` |
| [ADR-0031](0031-yaml-template-materialization.md) | wikihub.yaml template materialization — `/wh:setup` Step 0 단독 writer + 4-필드 patching + confirm drift fix + ruamel.yaml round-trip + Step 6 helper 통합 + §E schema version 정책 | Accepted | 2026-05-17 / 2026-05-18 (v2 + Step 4 통과) | `20260517_install_scope_reduction` |
| [ADR-0032](0032-hermes-skill-registration-policy.md) | Hermes skill 등록 정책 — `external_dirs` + install-time materialized SKILL.md + marker comment + flock·backup·sha256 safety (4 sub-decision) | Accepted | 2026-05-18 | `20260518_hermes_adapter` |
| [ADR-0033](0033-skill-prefix-hyphen-lock.md) | Skill namespace prefix lock — `wh-` (hyphen) — **Supersedes ADR-0011** | Accepted | 2026-05-18 | `20260518_hermes_adapter` |
| [ADR-0034](0034-data-first-layout.md) | Data-first layout — `~/wikihub/` = 운영 자산 + `~/.local/share/wikihub/src/` = 시스템 코드 (XDG). env swap (WIKIHUB_HOME 의미 변경 + WIKIHUB_SRC 신규 + WIKIHUB_INSTANCE_ROOT 폐기) + migration helper + mv-only backup (4 sub-decision) | Accepted | 2026-05-19 | `20260519_dir_layout_refactor` |
| [ADR-0035](0035-rclone-only-unified-oauth.md) | rclone 단독 + OAuth 단일 인증 — gws CLI 폐기 + SA 폐기. lsjson full snapshot + file_map(source_id 키) diff + false-delete 가드. **Supersedes ADR-0014/0015/0017/0027/0029** | Accepted | 2026-05-19 | `20260519_oauth_unify_rclone_only` |

> ADR-0016 은 F3 plan 의 잠정 후보 (Python 모듈 구조) 였으나 spec 명시로 충분 — 발의 안 함 결정 (`features/archive/20260513_vault_gdrive_api/analysis_and_design.md` §5).
> 신규 ADR을 추가할 때마다 이 표에 1행씩 append.
