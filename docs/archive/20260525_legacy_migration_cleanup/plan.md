# Plan — legacy_migration_cleanup (v0.1.8)

## 1. 배경

- `features/backlog.md` "graphify_profile_namespace 산출 §v0.1.8 cleanup 묶음" 의 5 항목 (#M~#Q) — v0.1.0~v0.1.6 era 의 1회성 migration 코드.
- 운영자 base 가 v0.1.7 정착 → 5 항목 모두 영구 no-op state. install.sh re-run 시 drift 0 → migration 본체 진입 안 함, 단 코드는 그대로 잔존.
- 단일 OCI server 환경 (메인테이너 자신) → safety margin 충분 (마이그레이션 거친 base 정착 확인 가능).
- 본 cleanup 자체가 v0.1.8 의 "리팩토링" 분류 feature. v0.1.0~v0.1.6 의 누적 migration 코드 일괄 정리 → install.sh 가독성·유지보수성 개선.

## 2. 작업 분류

- **리팩토링** (1회성 migration 코드 일괄 삭제) — Karpathy §2 "Simplicity First" 정합.
- Feature ID: `legacy_migration_cleanup`
- 디렉토리: `features/20260525_legacy_migration_cleanup/`
- 버전: **v0.1.8** (VERSION 0.1.7 → 0.1.8 bump)

## 3. 적용 단계 선언

| Step | 수행 여부 | 사유 |
|---|---|---|
| Step 1 Plan | 본 파일 | 가벼움 |
| Step 2 Analysis & Design | **수행** | 5 항목 (#M~#Q) 의 각 삭제 boundary + ADR cross-link 정리 + 진입 전 검증 procedure 명세 필요 + 보존 항목 (`_migrate_agent_schema` Group B + A4 W_invalid warn + `_step5_instance_dirs` env template) 명확화 |
| Step 4 Review | **수행** | install.sh 약 170줄 + scripts 220줄 삭제 = 외부 의존성 깨질 위험 surface 검증 필요. 멀티 reviewer (Claude + Gemini/Codex 또는 서브에이전트) 권장 |
| Step 5 Deployment | **수행** | `_system/` (사실상 변경 없음, VERSION 만) + install.sh + scripts 변경 → OCI 동기화 필수. canary tag 검증 cycle 활용 (방금 신설된 canary 채널의 첫 실 사용 — `docs/agent_dev_guide.md §Step 5 "배포 채널 — canary tag 활용"` 정합) |

## 4. 예상 영향 범위

### 삭제 대상

| ID | 파일 | 변경 | 줄 수 |
|---|---|---|---|
| #M | `install.sh` `_migrate_graphify_env` 함수 + main flow 호출 + 머리 코멘트 | 전체 삭제 | ~110 |
| #M | `docs/adr/0036-graphify-cli-integration.md` §Note 2026-05-24 의 §Decision 7 (마이그레이션 절차) 의 `_migrate_graphify_env` 명시 부분 | 부분 정리 | ~5 |
| #N | `install.sh` `_migrate_agent_schema` Group A (detect + migration + info log case `A_*` × 3) | 부분 삭제 | ~30 |
| #O | `install.sh` `_migrate_agent_schema` Group C (detect + migration + info log case `C_*` + `_legacy_vault_opts` tuple) | 부분 삭제 | ~20 |
| #P | `install.sh` `WIKIHUB_HOME` silent bug detect block (line ~98-108) | 전체 삭제 | ~10 |
| #Q | `scripts/migrate_layout.sh` | 파일 전체 삭제 | 220 |
| #Q | `install.sh:103` 의 `scripts/migrate_layout.sh` 참조 안내 (#P 와 동시 삭제) | 동반 정리 | (#P 에 포함) |

### 갱신 대상 (cross-link 정리 + release artifact)

| 파일 | 변경 |
|---|---|
| `docs/adr/0034-data-first-layout.md` | §"후속 영향" 에 "v0.1.8 cleanup — `migrate_layout.sh` + WIKIHUB_HOME bug detect 삭제, pre-v0.1.0 transition 정합 완료" 1줄 |
| `docs/adr/0036-graphify-cli-integration.md` | §Note 2026-05-24 의 §Decision 7 정리 (`_migrate_graphify_env` 부분 삭제, Rollback procedure 의 `<utc_iso>` placeholder 안내만 보존) |
| `docs/adr/0038-graphify-env-namespace-isolation.md` | §"후속 영향" 에 "v0.1.8 cleanup — `_migrate_graphify_env` 삭제, 운영자 base 정착 정합 완료" 1줄 |
| `features/backlog.md` | "graphify_profile_namespace 산출 §v0.1.8 cleanup 묶음" 항목 #M~#Q 를 `✅ closed by legacy_migration_cleanup (2026-05-25)` 로 갱신 |
| `_system/VERSION` | `0.1.7` → `0.1.8` |
| `README.md` | "개발 상태" 1줄 갱신 — v0.1.8 cleanup 누적 명시 + Status/Version badge 갱신 |
| `features/HISTORY.md` | `[2026-MM-DD] legacy_migration_cleanup (v0.1.8)` entry 추가 |

### 보존 (삭제 후보 아님, design 에서 명확화)

| 항목 | 보존 사유 |
|---|---|
| `_migrate_agent_schema` Group B (v0.1.5+ field auto-add 8 항목) | yaml.example schema 와의 single source of truth 보장 — 새 field 추가 시 운영자 yaml 자동 보강. 영구 가치 |
| `_migrate_agent_schema` A4 W_graphify_profile_invalid warn | 운영자 yaml 편집 mistake (대문자/특수문자/공백) 의 install-time fail-fast surface — 영구 가치 |
| `_step5_instance_dirs` env template (default `WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_*` 3 키 + Telegram) | fresh install 시 영구 필요 (운영자 chmod 600 보장 + namespace 안내) |
| `_migrate_agent_schema` 함수 자체 (Group B + A4 만 유지) | 영구 schema 보강 책임 |

**총 영향**: install.sh ~170줄 감소 + `scripts/migrate_layout.sh` 220줄 삭제 = **약 390줄 감소** + ADR/HISTORY/VERSION/README/backlog 약 50줄 추가 = 순감 ~340줄.

## 5. 메소드론 적용 여부

**적용** — trivial 미수준. 이유:
- 코드 5건 삭제 + ADR 3건 갱신 + release artifact 5건 = 운영자 visible 변경
- 단일 파일·1줄 수정 아님 (총 8개 파일 영향)
- 운영 server 의 `install.sh --update` 동작에 직접 영향 — 검증 필수

## 6. 진입 전 검증 (backlog 명시 — Step 3 시작 전 OCI 에서 수동 확인)

운영자가 v0.1.8 cleanup 시작 전 OCI 운영 server 에서 다음 명령 모두 통과 확인:

```bash
# #M — env namespace 정착 (v0.1.7 follow-up 후)
grep '^WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_' ~/.config/wikihub/env | wc -l   # = 3 기대
grep -E '^(OLLAMA_|ANTHROPIC_API_KEY|OPENAI_API_KEY|GEMINI_)' ~/.config/wikihub/env | wc -l   # = 0 기대

# #N — agent schema 정착 (Group A)
yq '.agent.skill_prefix' ~/wikihub/wikihub.yaml   # = "wh-" 기대
yq '.agent.oneshot_args' ~/wikihub/wikihub.yaml | grep -q '{skill}' && echo OK   # OK 기대

# #O — vaults options cleanup 정착 (Group C)
yq '.vaults[].options | keys' ~/wikihub/wikihub.yaml | grep -E 'bootstrap_allowed|credentials_path|root_folder_id|cursor_path' | wc -l   # = 0 기대

# #P — WIKIHUB_HOME 의미 정착 (data-first layout)
[[ -d "$HOME/wikihub/.git" ]] && echo "WARN: legacy repo state 잔존" || echo "OK"

# #Q — pre-v0.1.0 layout 흔적 부재
[[ -d "$HOME/wikihub-instance" ]] && echo "WARN: pre-v0.1.0 instance dir 잔존" || echo "OK"
```

모두 통과 → Step 2 (Analysis & Design) 진입 가능.

## 7. 결정 (2026-05-25 확정)

### Q1 = (a) — 별개 feature 로 분리

v0.1.8 branch 의 기존 commit 2건 (`4f5f206` _install_yq + `4b90fc0` interval default) 은 본 cleanup feature 와 무관한 별개 의도. 본 feature 의 scope 에서 제외. 현 v0.1.8 branch 에는 그대로 보존 — 본 cleanup 과 무관한 별개 feature 들의 lifecycle 은 독립적으로 진행 (v0.1.8 = multi-feature merge 결과, 각 feature 는 자기 plan/design/impl/review/deploy/archive 책임).

### Q2 = (a) — canary 검증 cycle 활용

본 cleanup 의 Step 5 (Deployment) 가 canary tag 의 첫 dogfooding. canary tag 부여 + OCI 검증 → 통과 시 latest promote. `docs/agent_dev_guide.md §Step 5 "배포 채널 — canary tag 활용"` 5-step 절차 정합 운영.

### Q3 = (a) — atomic VERSION bump

`_system/VERSION` 0.1.7 → 0.1.8 을 본 cleanup feature 의 핵심 commit 안에 포함. release artifact 정합.

### 추가 결정 — OCI 검증 timing

운영자가 "OCI 검증은 나중에 한번에 진행" 의도. **§6 의 진입 전 검증 명령은 plan 명시 보존, Step 3 진입 전 강제 통과는 요구 안 함**. canary tag 부여 후 OCI 에서 batch 검증 시 한 번에 모든 #M~#Q 정착 + cleanup 적용 + 후속 정상 동작 확인.

## 8. Definition of Done (preview — Step 2 에서 확장)

- install.sh 5 항목 (#M·#N·#O·#P + #Q reference) 삭제 완료. `bash -n install.sh` pass.
- `scripts/migrate_layout.sh` 파일 부재
- 보존 항목 (Group B + A4 + env template) 그대로 동작 — `_migrate_agent_schema` Group B 검증 fixture 통과
- ADR cross-link 3건 정리 — 0034 + 0036 + 0038 §"후속 영향" 갱신
- `features/backlog.md` #M~#Q closed 표기
- `_system/VERSION` = `0.1.8`
- README "개발 상태" 1줄 + Status/Version badge
- HISTORY.md entry
- canary tag 검증 cycle 통과 (Q2 결정 시 (a) 경로)

---

진행 방향:
- 본 plan 승인 → Step 2 (analysis_and_design.md) 작성 진입
- 미결 사항 Q1·Q2·Q3 결정도 함께
