# Plan — graphifyignore_migration

**Date:** 2026-05-27
**Feat ID:** graphifyignore_migration
**Trigger:** graphify_path_absolute (v0.1.9 squash) 의 multipass canary 검증에서 surface

approved: 2026-05-27 (retroactive — 본 변경은 trivial fix 로 직접 commit. 본 plan.md 는 HISTORY 참조 정합 위한 retroactive 문서화)

---

## 작업 분류

버그 fix (defense-in-depth layer 회복). 운영자 `~/wikihub/wiki/.graphifyignore` 가 update 시 자동 갱신 안 됨 — `cp -n` (template 배치) 가 fresh install 만 효과 → 기존 instance 의 `.graphifyignore` 가 `graphify-out/` line 미보유 → graphify_path_absolute 의 defense-in-depth layer 3 미적용.

## 타겟 버전 브랜치

`v0.1.9` — graphify_path_absolute (`5862847`) 의 follow-up. 같은 release window 흡수.

## 적용 단계

| Step | 수행 | 사유 |
|---|---|---|
| Step 1 (Plan) | ✅ (retroactive) | 본 문서 |
| Step 2 (Analysis & Design) | ❌ 생략 | trivial fix (install.sh 1 함수 + setup.md 1 bullet + ADR-0036 §Note 1줄). 메소드론 §3 Step 1 의 "trivial 변경 절차 자체를 생략 가능" 정합. |
| Step 3 (Implementation) | ✅ commit `f22e665` | install.sh `_migrate_graphifyignore` fn 신규 + `_step5_instance_dirs` hook + setup.md catalog 갱신 + ADR-0036 §"후속 영향" 1줄. |
| Step 4 (Code Review) | ❌ 생략 | trivial fix + multipass 검증 통과. |
| Step 5 (Deploy) | ✅ | v0.1.9 squash (commit `40c5154` HISTORY 포함) + main release (commit `32396bd`) 같은 release window 흡수. |

## 변경

**install.sh:**
- `_migrate_graphifyignore` fn 신규 (~30 line) — wiki/.graphifyignore 가 존재하면 `^graphify-out/?$` regex 부재 시만 idempotent append. 운영자 customization 보존 (다른 형태 `/graphify-out`, `**/graphify-out/` 미touch).
- `_step5_instance_dirs` 끝에 `_migrate_graphifyignore` 호출 hook — 매 install (update + fresh) 시점 작동.

**`_system/commands/setup.md`:**
- Step 1 §wiki/.graphifyignore catalog 갱신 — default 4 항목 (`_lint/`, `_state/`, `**/log.md`, `graphify-out/`) + line-level idempotent migration 메커니즘 설명 1 bullet 추가.

**`docs/adr/0036-graphify-cli-integration.md`:**
- §"후속 영향" cross-ref 1줄 add — graphifyignore_migration 결정 trail.

## 검증

multipass `wikihub-test` (Ubuntu 24.04 ARM):
- 첫 실행: `wiki/.graphifyignore migration: graphify-out/ append (graphify_path_absolute layer 3 회복)` 출력 + 운영자 파일에 line 추가됨
- 재실행 (idempotent): message 미출력 + 파일 변경 0 — `^graphify-out/?$` regex 매칭 1건 = 정합

## 4-Layer 회귀 차단 (graphify_path_absolute + 본 fix 통합)

| Layer | Source code | Effective on existing instance? |
|---|---|---|
| 1. wh-lint playbook absolute path | `_system/commands/lint.md` 5 위치 | ✅ install.sh update 가 source code 갱신 |
| 2. wh-lint Step 7 stale cleanup | `_system/commands/lint.md` Step 7 | ✅ install.sh update 가 source code 갱신 |
| 3. `.graphifyignore` `graphify-out/` ignore | `_system/templates/wiki/.graphifyignore` + **본 feature 의 `_migrate_graphifyignore`** | ✅ 본 fix 으로 기존 instance 자동 보강 |
| 4. 운영자 진단 가이드 | `docs/references/graph-path-resolution.md` | ✅ source 신본 보유 |

본 fix 가 layer 3 의 effective gap 을 닫음.

## 참조

- 트리거: features/archive/20260526_graphify_path_absolute/ (preceding feature)
- 결정 trail: docs/adr/0036-graphify-cli-integration.md §"후속 영향" 2026-05-27 entry
- commit: f22e665
