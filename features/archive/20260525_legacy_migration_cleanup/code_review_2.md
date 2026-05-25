# Code Review 2 — Integration & Design Alignment

- Reviewer: Claude subagent (Opus 4.7)
- Date: 2026-05-25
- Scope: v0.1.8 `legacy_migration_cleanup` Step 3 산출물 (분석 대상 8 파일, 752줄 diff)
- Method: design-to-impl alignment + ADR cross-link 정합 + 보존 항목 동작 검증 + 잔존 stale reference grep

---

## Critical 결함

**없음.**

cleanup 대상 5 항목 (#M~#Q) 모두 명세 boundary 대로 삭제됐고, `bash -n install.sh` syntax pass, 보존 항목 (Group B + A4 + env template) 본문 그대로. 운영 정본 동작 정합.

---

## High 결함

### H1. `scripts/_helpers/hermes_config_migrate.py` orphan — 호출 site 0

- **파일**: `scripts/_helpers/hermes_config_migrate.py:5`
- **문제**: 본 helper 의 module docstring 이 `"ADR-0034 layout refactor 의 §sub-3 helper — scripts/migrate_layout.sh 의 Step 5 가 호출."` 명시. 본 cleanup 으로 `scripts/migrate_layout.sh` 가 삭제됐는데, 그 유일 caller 인 본 helper 는 그대로 남음. `grep -rn hermes_config_migrate install.sh _system/commands/*.md` 결과 호출 site 0 (위 active code 의 모든 검색 결과는 docstring + design/archive/ADR 본문 reference 만).
- **근거**: analysis_and_design.md §"보존 명확화" 의 4 항목에 본 helper 미언급 — 즉 보존 의도도 명시 안 됨. `scripts/migrate_layout.sh` 삭제 boundary (§2 #Q) 안에 본 helper 의 처분 결정 부재. ADR-0032 §sub-3 line 99 (`scripts/migrate_layout.sh` 의 Step 5 가 `scripts/_helpers/hermes_config_migrate.py` 호출) 가 본 cleanup 의 referent (`scripts/migrate_layout.sh`) 부재로 사실상 dead link.
- **제안**: 둘 중 하나 명시 결정 + 적용 —
  (a) **동반 삭제**: `git rm scripts/_helpers/hermes_config_migrate.py`. ADR-0032 §sub-3 + ADR-0034 §"추가" line 95 (`helper 별도 (scripts/_helpers/hermes_config_migrate.py)`) 의 reference 도 cleanup. 본 feature scope 안에 포함 (atomic — #Q 의 진정한 cleanup boundary).
  (b) **보존 + 명시**: docstring 의 caller reference 갱신 (예: "운영자가 수동 호출 시 hermes external_dirs 정합" 등) + analysis_and_design.md §"보존 명확화" 에 항목 추가 + HISTORY entry 의 "보존" 절에 명시. 단 v0.1.0+ install 운영자는 호출 site 0 → 사실상 dead code 보존 → Karpathy §2 Simplicity First 위배. **(a) 권장.**

### H2. `install.sh:1143` 주석 stale — Group A 삭제 후 referent 부재

- **파일**: `install.sh:1143`
- **문제**: `# 2. 운영자 yaml schema 1회성 lift (ADR-0033 — wh:/-z 잔존 detect + patch)` 주석이 그대로. 본 cleanup 으로 Group A (`wh:`→`wh-`) 가 삭제됐으므로 `wh:/-z 잔존 detect + patch` 는 referent 부재. 함수 자체는 Group B + A4 보강 책임으로 의미 전환됨.
- **근거**: analysis_and_design.md §2 #N "함수 머리 코멘트 marker" 정리는 명시 (line 781) 됐고 line 760-762 의 함수 정의 주석은 정확하게 갱신됨. 그러나 `_step6_agent_skill` 내부 호출 지점의 주석 (line 1143) 은 명세 boundary 밖이라 누락. install.sh 안의 grep 결과 `wh:/-z` 잔존 reference 1개.
- **제안**: 갱신 — `# 2. 운영자 yaml schema 보강 (Group B v0.1.5+ field auto-add + A4 W_graphify_profile_invalid warn)` 또는 단순화 `# 2. 운영자 yaml schema 자동 보강 (ADR-0031 §Note schema-only mutation)`. 1줄 수정.

---

## Medium 결함

### M1. `scripts/migrate_layout.sh` 줄 수 불일치 — 220 vs 313

- **파일**: `features/HISTORY.md:215, 220` / `features/backlog.md:133` / `features/20260525_legacy_migration_cleanup/analysis_and_design.md:25, 47, 56, 200, 332, 360` (다수)
- **문제**: 모든 문서가 `scripts/migrate_layout.sh` 를 **220줄** 로 명시. 실제 diff 의 `@@ -1,313 +0,0 @@` 헤더가 보여주는 삭제 본문은 **313줄**. HISTORY 의 "약 390줄 감소" 결론도 (170 install.sh + 220) = 390 가정인데 실제로는 (170 + 313) = ~480줄 감소가 맞음.
- **근거**: `wc -l` 검증으로는 파일 부재라 직접 확인 불가하지만 diff hunk 헤더 `@@ -1,313 +0,0 @@` 는 git 의 정확한 line count. design 도 backlog 의 잘못된 표 기재 (220) 를 그대로 carry over.
- **영향**: 의사결정 영향 없음 (모두 영구 cleanup 의도). 단 HISTORY 의 결론 수치 정확성 + 후속 메인테이너의 추적성 측면에서 정정 권장.
- **제안**: HISTORY 의 "결론" line 220줄 → 313줄로 정정 + "약 390줄 감소" → "약 480줄 감소" 또는 "약 480줄 (install.sh ~170 + scripts/migrate_layout.sh 313) 감소" 로 갱신. design 본문은 archive 후 historical 정합 — 갱신 선택. backlog `~~#Q~~` row 의 "220줄 파일 전체" 는 strikethrough 안에 있어 history record 보존 의미상 그대로 두는 것도 정합 (strikethrough = 옛 정보).

### M2. ADR-0034 §"추가" line 95 의 `hermes_config_migrate.py` reference 미정리

- **파일**: `docs/adr/0034-data-first-layout.md:95`
- **문제**: `helper 별도 (scripts/_helpers/hermes_config_migrate.py)` reference 가 그대로. 본 cleanup 에서 ADR-0034 §"후속 영향" 에 cleanup bullet 1줄을 추가했지만 §"추가" 본문의 helper reference 는 손대지 않음.
- **근거**: H1 와 연동. helper 의 실 호출 chain 이 본 cleanup 으로 끊겼는데 ADR 본문은 helper 존재 가정으로 기재된 상태.
- **제안**: H1 의 결정 (a) 또는 (b) 와 paired —
  - H1=(a) 채택: line 95 의 helper reference 도 cleanup bullet 안에 명시 ("§"후속 영향" 의 cleanup bullet 에 helper 동반 삭제 명시").
  - H1=(b) 채택: 본 ADR §"후속 영향" 추가 줄에 "helper 는 운영자 수동 호출용으로 보존" 명시.

### M3. ADR-0032 §sub-3 line 99 dead reference

- **파일**: `docs/adr/0032-hermes-skill-registration-policy.md:99-102`
- **문제**: `scripts/migrate_layout.sh 의 Step 5 가 scripts/_helpers/hermes_config_migrate.py 호출:` + `--remove-stale`/`--add-new` 인자 명시 절 4줄. 본 cleanup 으로 caller 부재.
- **근거**: design §"연계 룰/스킬 정합성 검토" 표에 "ADR-0032 본문 변경 0 — history record 보존" 명시. 그러나 본 절은 design 의 §"연계 룰" 정합성 검토 시 빠진 부분 — Group A 삭제 (ADR-0033 + ADR-0032 §Note oneshot) 와 별개로, ADR-0032 §sub-3 의 migration helper 절은 ADR-0034 referent 라 본 cleanup 으로 dead. design 의 "ADR 본문 변경 0" 원칙은 v0.1.0 era 결정 본문 (Decision 자체) 보존 의미였는데, helper reference 절 (운영 절차 안내 — Decision 아님) 까지 보존 가정이 design 에 surface 안 됨.
- **제안**: 둘 중 하나 —
  (a) ADR-0032 §sub-3 line 97-103 의 "migration 자동화 (ADR-0034 §sub-3 정합)" 절 전체 삭제 + ADR-0034 §"후속 영향" 의 cleanup bullet 에 "ADR-0032 §sub-3 migration 자동화 절 동반 삭제" 명시. (atomic — H1=(a) 와 paired 권장.)
  (b) §sub-3 line 99 의 caller 명시만 갱신 ("`scripts/migrate_layout.sh` (v0.1.8 cleanup 으로 삭제) 의 Step 5 가 …" 등 historical phrasing). dead link 명시. — H1=(b) 와 paired.

---

## Low / 권장 개선

### L1. `_migrate_agent_schema` 함수 머리 코멘트 의 `_op_defaults` 미언급

- **파일**: `install.sh:760-762`
- **관찰**: 본 cleanup 후 함수 머리 코멘트가 `Group B (자동 추가) + A4 (W_graphify_profile_invalid warn)` 까지 갱신됐고 PTY-safe / idempotent 도 명시. 그러나 design DoD 의 `_op_defaults` dict 동작 검증 명시 항목 (`features/.../analysis_and_design.md` line 405) 의 dict 확장 패턴 — 향후 새 field 도입 시 본 dict 확장만으로 영구 보강 — 가 코멘트에 surface 안 됨. 코드는 ruamel.yaml 의 setdefault 패턴이라 명확하지만 후속 메인테이너 onboarding 측면에서 1줄 추가 권장.
- **제안**: 함수 머리 코멘트 끝에 "신 field 추가 시 본 함수 의 Group B detect + migration 두 블록에 1쌍 추가 (yaml.example 동기 갱신)." 1줄 — 선택.

### L2. canary tag 운영 정합 — `docs/agent_dev_guide.md` 5-step 절차 cross-link

- **파일**: `features/HISTORY.md:220` ("canary tag 검증 cycle" 절)
- **관찰**: HISTORY 결론에 "canary tag 검증 cycle (`docs/agent_dev_guide.md §Step 5 "배포 채널 — canary tag 활용"`) 의 첫 dogfooding" 명시 — 정합. 단 canary tag 부여 명령 (`git tag -f canary <commit> && git push origin canary --force`) 과 OCI 검증 → latest promote 흐름이 plan.md §3 의 Q2=(a) 결정과 HISTORY 의 진술 사이에 매끄럽게 정합 — design DoD §"거버넌스 / canary 검증" 도 정합. 추가 결함 없음.
- **권장**: canary push 시 `--force` 사용은 의도된 mutable channel 정합 — agent_dev_guide.md 의 안내와 일치. OCI batch 검증 완료 후 latest promote 시 별도 follow-up commit 으로 처리 (atomic). 본 review 시점에서 actionable item 없음.

### L3. `_step5_instance_dirs` env template 직접 verify

- **파일**: `install.sh:692-714` (design line 35 reference)
- **관찰**: design §"보존 명확화" 의 첫 항목 — `_step5_instance_dirs` env template (default `WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_*` 3 키 + Telegram placeholder + chmod 600). 본 cleanup 의 diff 에는 본 함수 변경 0 (preserve). `_migrate_graphify_env` 삭제 후에도 fresh install 시 env 자동 생성 동작은 _step5_instance_dirs 책임으로 그대로. 정합.
- **권장**: design DoD 의 "fresh install fixture 통과" 항목은 OCI batch 검증에 deferred — plan.md §7 "OCI 검증 timing" 결정 정합. 본 review 단계에서는 코드 변경 0 + bash syntax pass 로 충분.

---

## 정합 확인 (no issue)

다음 항목들은 design 명세대로 정확하게 반영됨, 결함 없음:

1. **#M (`_migrate_graphify_env` 삭제)**: 함수 본체 + 머리 코멘트 + main flow 호출 1줄 모두 삭제 (install.sh 의 grep 결과 0 hit). ADR-0036 §Note 의 §Rollback procedure + §배포 Gap window 분석 두 절 전체 삭제 — diff line 51-86 정확. ADR-0036 §결정 A~F (CLI v8 sync 본체) 본문 변경 0 — 보존.
2. **#N (Group A 삭제)**: detect (807-816) + migration (917-936) + info case (877-879) + 함수 머리 코멘트 marker (781) 모두 삭제. `agent.setdefault("agent", {})` 만 남고 Group A 의 skill_prefix/oneshot_args mutation 부재. `wh:` reference 가 install.sh active 코드에서 0 hit (남은 `/wh:setup` 은 skill 호출 명령, 별개).
3. **#O (Group C 삭제)**: detect (854-862) + migration (970-981, `_legacy_vault_opts` tuple 2 위치) + info case `C_*` (892) 모두 삭제. install.sh 의 `_legacy_vault_opts` grep 0 hit.
4. **#P (`WIKIHUB_HOME` silent bug detect 삭제)**: line 98-109 의 12줄 block 삭제 — diff line 155-170 정확. `WIKIHUB_INSTANCE_ROOT` env detect (84-96) 는 보존 — 정합.
5. **#Q (`scripts/migrate_layout.sh` 파일 삭제)**: `git rm` 완료 (status `D scripts/migrate_layout.sh`). 다른 active code 의 호출 site 0 (단 H1 의 helper docstring 이 stale).
6. **ADR-0031 §Note 정합**: Group A·C 삭제 = schema mutation 코드 제거, 운영자 yaml 값 영향 0. `_migrate_graphify_env` 삭제 = env 값 영향 0. value-mutation policy (warn-only) 정합 — A4 W_graphify_profile_invalid 가 그대로 보존되며 자동 변경 안 함.
7. **ADR-0033 / ADR-0032 §Note (oneshot) / ADR-0035 본문**: 변경 0 — history record 보존 정합.
8. **ADR-0034 §"후속 영향" 추가 bullet**: diff line 42 정확 (`- **v0.1.8 cleanup** … pre-v0.1.0 → v0.1.0 transition 의 1회성 helper …`).
9. **ADR-0036 §Cross-references 갱신 끝 bullet**: diff line 92 정확. §"결정 A~F" + §"본 §Note 의 분석 정본" 보존.
10. **ADR-0038 §"후속 영향" 3 변경**: (1) cleanup bullet 1줄 추가 (diff line 107-108) ✓ (2) line 74 `Rollback procedure` bullet 삭제 (dead link) ✓ (3) line 73 TELEGRAM_ALERT_* parenthetical 갱신 (`_migrate_graphify_env 가 값 보존` → `v0.1.7 follow-up 의 마이그레이션 + v0.1.8 cleanup 후에도 영역 영향 없음`) ✓. supersede 아님 — Decision 1·2·4·5 영구 유효 명시.
11. **HISTORY entry 6 항목**: 목적 / 로직 / 생성 ADR (없음 명시) / 트레이드오프 / 결론 / 참조 — 모두 명시. canary tag 첫 dogfooding 명시. 보존 명확화 (Group B + A4 + env template) 명시. (M1 의 줄 수 표기만 정정 권장.)
12. **backlog #M~#Q 컨벤션 정합**: 5 row 모두 strikethrough on 앞 3 컬럼 + 결정 컬럼에 `✅ **closed** by `legacy_migration_cleanup` (2026-05-25)` prefix. F4 산출의 closed 컨벤션 (`~~#12~~ ... ✅ **closed** by ...`) 동일. 정합.
13. **README badge + 개발 상태**: v0.1.7 → v0.1.8 (Title + Status + Version badge 3 위치). 개발 상태 1줄에 v0.1.8 cleanup 누적 명시 + `scripts/migrate_layout.sh` 삭제 + 약 390줄 감소 (M1 의 줄 수 표기 정정 적용 여부에 따라 ~480 로 조정 가능). v0.1.7 follow-up 의 bold 가 v0.1.8 cleanup 으로 이동 — 직전 release 강조 컨벤션 정합.
14. **`_system/VERSION`**: `0.1.7` → `0.1.8` 1줄 변경. atomic VERSION bump 결정 (plan.md Q3=(a)) 정합.
15. **WIKIHUB_SPARSE_PATHS**: install.sh:329 의 `(_system scripts install.sh wikihub.yaml.example README.md LICENSE)` 그대로. `scripts/` 안에 다른 active script (`ops-alert.py`, `vault-fetch.py`, `pending_monitor.py`, `_helpers/`, `lib/`, `requirements*.txt`) 잔존으로 sparse-checkout 정합.
16. **Q1 별개 feature framing**: v0.1.8 branch 의 기존 commit (`4f5f206 _install_yq` + `4b90fc0 interval default` + `79b7a4e canary_channel`) 은 본 cleanup feature 와 별개 — 본 diff 에 미포함 정합 (책임 영역 외).
17. **`bash -n install.sh`**: syntax pass. 함수 정의 + main flow + heredoc 정합.

---

## 결론

- **Critical**: 없음.
- **High 2건**: H1 (`hermes_config_migrate.py` orphan), H2 (install.sh:1143 stale 주석) — 둘 다 design 의 §2 명세 boundary 가 좁게 잡혀 빠진 항목. H1 은 H2/M2/M3 와 연동 결정 필요 (helper 동반 삭제 vs 운영자 수동 호출용 보존).
- **Medium 3건**: M1 (220 vs 313 줄 수치 정정), M2 (ADR-0034 line 95 helper reference), M3 (ADR-0032 §sub-3 migration 자동화 절). 모두 H1 결정과 paired.
- **Low 3건**: L1 (코멘트 보강), L2 (canary 절차 정합 확인), L3 (env template 보존 확인) — actionable item 없음.

**권장 follow-up**: H1=(a) (helper 동반 삭제) 채택 시 M2 + M3 자동 cleanup 가능. atomic — 본 feature scope 안에 포함 결정. H2 + M1 은 1줄 수정으로 즉시 흡수 가능 (Step 3 복귀). 결정 후 Step 4 재검토 또는 즉시 Step 5 진입.

본 cleanup 의 핵심 의도 (1회성 migration 코드 일괄 삭제, 가독성·유지보수성 개선) 는 정확하게 달성. critical 결함 없음 + DoD 핵심 항목 모두 정합.
