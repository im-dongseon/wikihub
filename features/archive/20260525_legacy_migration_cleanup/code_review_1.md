# Code Review 1 — Correctness & Deletion Completeness

- reviewer: Claude subagent (Opus 4.7)
- date: 2026-05-25
- scope: v0.1.8 legacy_migration_cleanup (#M~#Q) 의 삭제 안전성·완전성 검증
- diff: 752 lines, 553 deletions / 33 insertions across 9 files

---

## Critical 결함

없음.

- `bash -n install.sh` pass 확인.
- 4 개 Python heredoc (`<<'PYEOF'`) 모두 `ast.parse` 통과 (10/52/47/47 lines).
- `_migrate_agent_schema` 본체: Group B 11개 flag + per-vault sync_interval_sec + A4 `W_graphify_profile_invalid` 만 남음 — orphan `A_*`/`C_*` reference 0건 (info case bash, line 838-851).
- `_migrate_graphify_env` 함수/호출/머리 코멘트 marker 모두 삭제 — 잔존 grep 0건.
- `WIKIHUB_HOME silent bug detect` block (line 98-109 in old, "WIKIHUB_HOME=$WIKIHUB_HOME 가 이전 semantic" + `im-dongseon/wikihub` repo dir 비교) 깨끗하게 제거. main flow 호출 site (`_step5_instance_dirs` 직후 1줄) 도 부재.
- `scripts/migrate_layout.sh` 파일 부재 (git status: `deleted:    scripts/migrate_layout.sh`).
- `install.sh` 의 `WIKIHUB_SPARSE_PATHS` (line 329) 는 그대로 `scripts` dir 포함 — 다른 active script (`ops-alert.py`, `vault-fetch.py`, `pending_monitor.py`, `_helpers/`, `lib/`) 정합.
- ADR-0036 §결정 A~F (line 261-295, CLI v8 sync 본체 결정 6건) 모두 보존 + cleanup 1줄 line 307 에 추가.
- ADR-0038 §"후속 영향" 3 변경 모두 적용: (1) line 73 TELEGRAM parenthetical 갱신 (stale `_migrate_graphify_env 가 값 보존` → `v0.1.7 follow-up 의 마이그레이션 + v0.1.8 cleanup 후에도 영역 영향 없음`), (2) old Rollback procedure bullet 삭제, (3) line 74 cleanup bullet 추가.
- ADR-0034 line 122 cleanup 1줄 추가 확인.
- `_system/VERSION` = `0.1.8`, README badge `v0.1.8` × 3 위치 + 개발 상태 1줄 누적 명시 + HISTORY entry 6 항목 (목적/로직/생성 ADR/트레이드오프/결론/참조) 모두 확인.
- backlog.md #M~#Q 5 row 모두 strikethrough on 앞 3 컬럼 + `✅ **closed** by \`legacy_migration_cleanup\` (2026-05-25)` prefix 적용 (line 129-133).

---

## High 결함

### H1. `README.md:161-163` §Migration 절 — `_step0_legacy_detect` + `scripts/migrate_layout.sh` 호출 prompt 안내 잔존 (dead reference)

**파일**: `README.md` line 161-163
```
### Migration (pre-ADR-0034 layout 운영자 — v0.1.0 미배포 시점은 영향 0)

이전 layout (`~/wikihub` = repo + `~/wikihub-instance` = 운영 데이터) 운영자는 install.sh `_step0_legacy_detect` 가 자동 detect → `scripts/migrate_layout.sh` 호출 prompt. 9-phase state machine + 부분 실패 시 resume.
```

**문제**: §Migration 절이 (a) install.sh 의 `_step0_legacy_detect` 함수 (부재 — `grep -n "_step0_legacy_detect" install.sh` = 0건), (b) `scripts/migrate_layout.sh` 파일 (본 cleanup 으로 삭제) — 둘 다 dead reference 를 안내. 본 절은 README 가 운영자에게 보여주는 운영 가이드 — 실재 없는 helper 를 호출하라고 안내.

**근거**: 본 cleanup 의 D-P/D-Q (`WIKIHUB_HOME silent bug detect` + `migrate_layout.sh`) 삭제 정합. design 의 §4 release artifact 갱신 (README 항목) 은 badge + 개발 상태 1줄만 명세하고 §Migration 절은 누락.

**제안**: §Migration 절 (line 161-165 — 165 까지 ADR cross-link 도 포함) 삭제하거나, "pre-v0.1.0 layout (= `_step0_legacy_detect` + `migrate_layout.sh`) 운영자 base 0건 정합 — v0.1.8 cleanup (`legacy_migration_cleanup`, 2026-05-25) 으로 transition helper 삭제" 의 historical note 로 단순화. 후자 권장 — ADR-0034 cross-link 의 의미 보존.

---

## Medium 결함

### M1. `_system/wiki-schema.md:61` — directory tree 에 `migrate_layout.sh` 잔존

**파일**: `_system/wiki-schema.md` line 61
```
├── scripts/                          # 인프라 스크립트
│   ├── vault-fetch.py
│   ├── ops-alert.py
│   ├── migrate_layout.sh             #   ADR-0034 layout migration helper
│   └── _helpers/{render_systemd_units,hermes_config_migrate}.py
```

**문제**: `_system/wiki-schema.md` 는 v0.1.8 운영자가 install 후 read 하는 정본 schema 문서 — 부재 file 을 directory tree 에 표시.

**근거**: file 삭제됐으나 schema 문서 갱신 누락. 또한 `_helpers/` 안 `pending_monitor` (or `ops-alert` 의 `_helpers` 변형) 의 현 구조와도 비교 필요 (별개 — 본 cleanup scope 외).

**제안**: line 61 `migrate_layout.sh` row 삭제. (선택) `pending_monitor.py` 가 빠진 부분도 별개 trivial PR 로 정리.

### M2. `install.sh:1143` `_migrate_agent_schema` caller 코멘트 — stale ADR-0033 reference

**파일**: `install.sh` line 1143
```bash
# 2. 운영자 yaml schema 1회성 lift (ADR-0033 — wh:/-z 잔존 detect + patch)
_migrate_agent_schema || return 2
```

**문제**: 함수가 Group A (ADR-0033 `wh:`→`wh-` + ADR-0032 oneshot) 삭제 후 더 이상 "wh:" detect 안 함. caller-side 코멘트가 함수 의미를 stale 하게 묘사. 함수 자체의 머리 코멘트 (line 763-765) 는 정확하게 "Group B (자동 추가) + A4 (W_graphify_profile_invalid warn)" 로 갱신됐는데 caller 코멘트만 누락.

**근거**: design §4 §"개정 전/후 비교" 에 caller-side 코멘트 갱신 명세 부재.

**제안**: `# 2. 운영자 yaml schema 보강 — v0.1.5+ field 자동 추가 + graphify_profile 정규식 warn (`_migrate_agent_schema` 머리 코멘트 참조)` 로 1줄 갱신.

---

## Low / 권장 개선

### L1. `_system/commands/graphify.md:237` — `install.sh _migrate_graphify_env` reference 잔존

**파일**: `_system/commands/graphify.md` line 237
```
- **ADR-0038** graphify env namespace isolation — `WIKIHUB_GRAPHIFY_<PROFILE>_*` + multi-profile bundle + auto-migration (`install.sh _migrate_graphify_env`) + Hermes trust 가정
```

**문제**: 함수 부재 후에도 ADR-0038 sub-bullet 에 호출 가능한 helper 인 양 표기.

**근거**: 본 file 은 운영 command 문서 — `wh-graphify` skill 의 정본. ADR-0038 의 Decision 본문 (line 36, 59) 은 design 의도상 history 보존이라 그대로 두는 것이 맞지만, graphify.md 의 운영 cross-reference 는 현재 동작 기준이 되어야 함.

**제안**: `auto-migration (`install.sh _migrate_graphify_env`)` → `auto-migration (v0.1.7 follow-up 의 1회성 본체 — v0.1.8 cleanup 으로 함수 삭제, namespace 정합 정착)` 로 1줄 갱신. 또는 단순히 `+ auto-migration (v0.1.7 era 1회성, cleanup 완료)` 로 축약.

### L2. backlog.md "§v0.1.8 cleanup feature 의 시작 안내" 절 — closed 표기 누락

**파일**: `features/backlog.md` line 125+ (시작 안내 절 본문 시작 line ~125)

**문제**: design §4 backlog 절 끝에 "§v0.1.8 cleanup feature 의 시작 안내" 절 (line 160~) 에 "✅ closed" marker 1줄 추가가 *선택* 으로 명세됐는데, 본 patch 에서는 적용 안 됨. 위 5 row 의 `closed` marker 만 적용.

**근거**: design 명세 "선택" — strict 결함 아님. 운영자가 backlog 의 시작 안내 절 read 시 "이 묶음은 이미 닫혔다" 의 명시적 marker 부재.

**제안**: line 124~125 시작 부근에 `> ✅ **closed** by feature \`legacy_migration_cleanup\` (2026-05-25). 본 절은 historical 정합으로 보존.` 1줄 추가 (선택).

### L3. `features/HISTORY.md:215` "로직" bullet — `scripts/migrate_layout.sh` 인용 미세 차이

**파일**: `features/HISTORY.md` line 215

**문제**: 본 cleanup 의 (e) 항목 description "220줄 9-phase state machine" — design analysis 에서는 단순 "220줄". 미세 — design 정합. 그러나 본 line 215 와 line 207 (v0.1.7 follow-up HISTORY) 가 모두 줄 수 표기 — 운영자 read 시 정합. 결함 아님.

---

## 정합 확인 (no issue)

| 항목 | 결과 |
|---|---|
| `bash -n install.sh` | pass |
| 4 PYEOF Python heredoc ast.parse | 4/4 pass (10/52/47/47 lines) |
| `_migrate_agent_schema` Group B+A4 only | detect/migration/info case 모두 정합 — orphan `A_*`/`C_*` reference 0건 |
| `_migrate_graphify_env` 완전 제거 | grep 0건 (install.sh 내), main flow 호출 0건, 머리 코멘트 marker 0건 |
| `WIKIHUB_HOME silent bug detect` 완전 제거 | `이전 semantic` text + `migrate_layout` reference (install.sh 내) 모두 0건 |
| `scripts/migrate_layout.sh` 파일 부재 | `git status: deleted` 확인 |
| `WIKIHUB_SPARSE_PATHS` 의 `scripts` 항목 | 그대로 — 다른 active script 정합 (`vault-fetch.py`, `ops-alert.py`, `pending_monitor.py`, `_helpers/`, `lib/`) |
| ADR-0036 §결정 A~F 보존 | line 261-295 6 결정 모두 그대로 + line 307 cleanup 1줄 추가 |
| ADR-0038 §"후속 영향" 3 변경 | (1) line 73 TELEGRAM 갱신 ✓ (2) Rollback bullet 삭제 ✓ (3) line 74 cleanup 추가 ✓ |
| ADR-0034 §"후속 영향" 1줄 추가 | line 122 cleanup 1줄 확인 |
| backlog.md #M~#Q closed marker | 5 row strikethrough + `✅ **closed** by \`legacy_migration_cleanup\`` prefix 모두 적용 |
| README badge + 개발 상태 | title v0.1.8 + Status badge v0.1.8 + Version badge 0.1.8 + 개발 상태 1줄 cleanup 명시 |
| `_system/VERSION` = `0.1.8` | 확인 |
| install.sh `wh:`→`wh-` migration 자취 | grep 0건 (드러난 `wh:` 매치는 모두 documentation/UX prefix — Group A 자취 아님) |
| `_step8_guide` migrate_layout.sh 안내 | 0건 (`_step8_guide` 본체 line 1216-1280 깨끗) |
| `_step0_legacy_detect` 함수 | install.sh 내 0건 (정합 — 본 cleanup 으로 동반 부재) |
| HISTORY entry 6 항목 + analysis 일관성 | 목적/로직/생성 ADR (없음 + 3 ADR cross-link 갱신 명시)/트레이드오프 (2건)/결론 (390줄 감소 + canary 첫 dogfooding)/참조 (archive path) 모두 정합 |
| Step 1 plan Q1=a / Q2=a / Q3=a 일관성 | branch v0.1.8 별개 feature 분리 (Q1) + canary 검증 cycle (Q2) + atomic VERSION bump (Q3) 모두 본 patch 안에 정합 |

---

## 요약

- **Critical/Blocking 결함**: 0건. install.sh + ADR + backlog + release artifact 의 핵심 cleanup boundary 는 정확.
- **High 결함**: 1건 (H1: README §Migration 절 dead reference) — 운영자 visible documentation 결함이라 Step 5 (canary push) 전 fix 권장.
- **Medium 결함**: 2건 (M1: wiki-schema.md tree, M2: install.sh:1143 stale 코멘트) — surgical 1줄 fix.
- **Low**: 3건 (graphify.md cross-ref + backlog 시작 안내 marker + HISTORY 줄 수 표기) — 선택.

**Step 3 복귀 권장 항목**: H1 + M1 + M2 fix (3 file, 약 5줄 변경) 후 Step 4 종결 → Step 5 canary push 진입 가능.
