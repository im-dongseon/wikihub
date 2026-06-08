# Code Review 2 — Integration & Design Alignment

- **Reviewer**: Claude subagent (Opus 4.7, 1M context, 컨텍스트 초기화)
- **Date**: 2026-05-24
- **Scope**: `analysis_and_design.md` v2 (approved 2026-05-24) ↔ 본 patch 의 6 modified files + 2 new files 의 design-to-impl alignment + ADR coherence + Step 2 review (C1~C3, A4~A7, D8~D10) 해소 검증
- **방법**: design pseudocode walk-through ↔ 실 코드 line-by-line, ADR cross-link, cookbook ↔ graphify.md backend case 매핑, 전체 repo grep 으로 legacy reference drift

---

## Critical 결함

**없음.** 핵심 architecture (namespace + v8 CLI sync + auto-migration) 가 설계대로 충실히 반영됨. design review 의 C1~C3 (Critical 인접) 도 모두 적용 확인.

---

## High 결함

**없음.** 모든 High-priority 항목 (design_review_1 H1, design_review_2 H1·H2·H3) 이 본 patch 에 흡수됨 — 아래 정합 확인 절 참조.

---

## Medium 결함

### M1. `install.sh:1361` Step 9 final guide block 의 stale env 예시 — namespace 격리 정합 미달

**위치**: `install.sh:1359-1362` (`_step8_guide` 의 graphify API key 안내 줄)

**문제**:
```bash
3. graphify LLM API key 입력 (ADR-0036 — wh-lint Step 9 chain 의 Pass 3 가 요구):
     \$EDITOR ~/.config/wikihub/env
     # 예: ANTHROPIC_API_KEY=sk-ant-...  (또는 OPENAI_API_KEY=...)
```
이 안내는 fresh install 운영자에게 출력되며, **신규 namespace (`WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_*`)** 가 아닌 legacy 키를 적으라고 유도. `_step5_instance_dirs` template (line 691~) 의 default 가 이미 `WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_*` 3 키 + `local-daemon` API key prefill 임에도 가이드가 모순.

**근거**: analysis_and_design.md §"개정 범위" 표는 `install.sh _step5_instance_dirs` 의 template 만 다루나, `_step8_guide` 의 install banner 도 동일 env layer 안내. design DoD 의 "fresh install 운영자가 OLLAMA_GEMMA 3-키 박힌 env 를 발견" 가 정합되도록 안내도 일치 필요.

**제안**: 해당 안내 3줄을 다음으로 교체:
```
3. graphify LLM 자료 — default (ollama_gemma + local Ollama daemon) 미사용 시:
     \$EDITOR ~/.config/wikihub/env
     # WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL> 형식 (ADR-0038).
     # 추가 profile cookbook → docs/graphify-backend-test-reference.md §6
     # yaml `operations.graphify_profile` 값 변경도 함께.
```

### M2. `lint.service.template:16` 코멘트의 stale env 예시

**위치**: `_system/systemd/lint.service.template:14-16`

**문제**:
```
# ADR-0036 — graphify Pass 3 (LLM subagent) 의 API key. lenient `-` prefix:
#   파일 부재 또는 빈 값이어도 unit start 자체는 성공 — graphify subprocess 만 fail.
#   운영자가 ~/.config/wikihub/env 에 ANTHROPIC_API_KEY=... 채움 (chmod 600, install.sh 가 보장).
```
namespace 격리 후 `ANTHROPIC_API_KEY=...` 가 더 이상 env 파일에 위치하지 않음. 운영자가 lint.service 검사 시 잘못된 mental model 형성 risk.

**근거**: design_review_1 L1 의 "Hermes trust 가정 명시" + ADR-0038 §Decision 1 "wikihub-private 키만 사용" 정합.

**제안**: 코멘트를 `WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_*` 로 갱신 + ADR-0038 cross-link. systemd unit template 변경은 deploy 시 re-render 필요 — Step 5 의 `daemon-reload` 흐름 정합 확인.

### M3. `install.sh:684` `_step5_instance_dirs` 의 함수 머리 코멘트 — stale

**위치**: `install.sh:682-684`

**문제**:
```bash
# ADR-0036 — graphify Pass 3 (LLM API) 의 key 자료 layer.
# systemd unit (`wikihub-lint.service`) 의 `EnvironmentFile=-%h/.config/wikihub/env` 가 본 파일을 lenient 로 읽음.
# 운영자가 수동으로 `ANTHROPIC_API_KEY=...` 채움. install.sh 는 빈 template + 권한만 보장.
```
header 코멘트가 v0.1.7 follow-up 이전 정본을 그대로 유지 — 본 patch 가 template 내용은 모두 갱신했으나 함수 docstring 누락. "운영자 수동" 도 부정확 (default 3 키 prefill 후 사용 가능).

**제안**: 코멘트를 ADR-0038 정합으로 1~2 줄 갱신.

### M4. `_migrate_graphify_env` 호출 흐름 — `update` 모드에서만 의미, fresh 에서 redundant 호출

**위치**: `install.sh:1911-1912` (main flow)

**문제**: `_migrate_graphify_env` 가 `_step5_instance_dirs` 직후 무조건 호출. fresh install 의 경우 `_step5_instance_dirs` 가 방금 namespace template 으로 작성 → `_migrate_graphify_env` 가 즉시 `has_legacy=0, has_endpoint=1, has_api_key=1, has_model=1` → no-op return. 정합 (의도 정확).

다만 design §5a "호출 흐름" 절은 두 함수 모두 항상 호출되는 일관 흐름을 의도. 코드도 정합. **이는 결함 아님** — 의사코드와 실 코드 정합 확인 → 정합 확인 절로 이동 (아래).

**조치**: 본 항목은 confirm only — Medium 라벨 회수.

### M5. `graphify.md` Step 2 의 endpoint 분기 — Step 2 본문 절차에 명시적 `set -u` 가정 부재

**위치**: `_system/commands/graphify.md:43-63`

**문제**: design_review_2 H2 가 `${!var:-}` + backend guard 로 해소됐고 graphify.md 도 정합. 다만 의사코드 머리 코멘트가 "set -u 안전 indirection" 만 언급 — Hermes terminal subprocess 가 `bash` 인지 `sh` (dash) 인지 가정 명시 부재. dash 는 `${!var}` indirection 미지원.

**근거**: design_review_2 §"정합 확인" 의 indirection 정합 분석 (line 178~179) — Hermes terminal = bash 가 본 design 의 기반. design 본문에는 명시 안 됨.

**제안**: graphify.md Step 2 앞단 또는 ADR-0038 §Decision 4 (Hermes trust 가정) 에 1줄 — "Hermes terminal tool 이 `bash` invoke (dash 미지원) — `${!var:-}` indirection 의존". 본 patch 흡수 또는 ADR-0036 §Note 후속 추가.

---

## Low / 권장 개선

### L1. ADR-0038 §Decision 2 의 "런타임 검증 + install-time non-fatal warn" — graphify.md 가 fatal exit 2 사용

**위치**: ADR-0038 line 34 vs `graphify.md:48-51`

graphify.md Step 2 는 invalid profile → `exit 2` (fatal, ops-alert). ADR-0038 §Decision 2 의 표현 "런타임 검증 + install-time non-fatal warn" 은 install-time 만 non-fatal 임을 명시했으나 미세하게 ambiguous — runtime 도 non-fatal 로 오독 risk. 이 부분은 **현재 install.sh + graphify.md 동작이 정합** (runtime=fatal, install-time=warn) 이며 design_review_1 M3 가 install-time 추가를 요청한 것 자체에 정합 — 다만 ADR 표현 1줄 명확화 권장.

**제안**: ADR-0038 line 34 의 표현을 "런타임 fatal + install-time non-fatal warn" 으로 명확화.

### L2. design_review_1 M4 (backend/profile prefix consistency warn) — implementation 미적용 + ADR 에 결정 trace 명시

**위치**: `_system/commands/graphify.md` Step 2 + ADR-0038 §Consequences (line 61)

**문제**: design_review_1 의 M4 는 `case "$backend" in claude) [[ "$profile" =~ ^claude_ ]] || warn ...` 추가 권장. ADR-0038 §부정/제약 (line 61) 이 "U3 결정 — advanced 운영자 mixed case legitimate" 으로 명시적 reject — 정합. 단 graphify.md 본문에 결정 trace 없음 — operator 가 mixed config 박았다가 silent misroute 시 root cause 추적 시간 늘어남.

**제안**: graphify.md Step 2 의 backend case dispatch 끝에 1줄 코멘트 — "backend/profile prefix mismatch warn 미추가 (ADR-0038 U3 결정 — advanced mixed case 존중)". 또는 cookbook §6.7 운영자 절차에 "yaml `graphify_backend` 와 `graphify_profile` 의 prefix 정합 권장" 1 줄.

### L3. `_migrate_graphify_env` 의 코멘트 `\#*|""` 패턴 — leading whitespace 코멘트 처리 (design_review_2 L1)

**위치**: `install.sh:939, 971`

**문제**: design_review_2 L1 의 지적 — `case "$line" in \#*|"")` 는 앞 공백 코멘트 (`  # note`) 를 default branch 로 흘려보냄. 본 patch 의 default branch 가 silent drop 이라 functional impact 0이고 design_review_2 도 "functional impact 0" 으로 분류 — 정합. 향후 default 에 warn 추가 시 재방문 필요.

**제안**: 본 patch 범위에서는 조치 불필요. 메소드론 §2 Surgical Changes 정합.

### L4. cookbook §6.2 OpenRouter — `graphify_backend: ollama` + claude 계열 model — concurrency 휴리스틱 검증

**위치**: `docs/graphify-backend-test-reference.md:233-237` + graphify.md:84-92

**문제**: §6.2 의 model `anthropic/claude-3.5-sonnet` 가 endpoint `https://openrouter.ai/api/v1` (외부) 와 결합 → graphify.md `case "$model"` 의 `*cloud*` substring 미일치 → endpoint 분기로 진입 → 외부 endpoint → concurrency=4. 의도 정합. **결함 아님**, 단 cookbook 에 명시적 concurrency 예상값 1줄 추가하면 운영자 검증 편이.

**제안**: §6.2 끝에 1줄 — "endpoint 외부 + model `*cloud*` 미일치 → concurrency=4 적용 (외부 cloud)".

### L5. cookbook §6.5 Gemini — non-reasoning flash-lite 권장의 출처 정합

**위치**: `docs/graphify-backend-test-reference.md:268-280`

**문제**: §6.5 가 `gemini-2.5-flash-lite` 권장 사유 "graphify Pass 3 의 content 필드 직접 파싱 → non-reasoning flash-lite 필수" 보유 — install.sh 의 이전 (legacy) env template 의 동일 안내 (`260521 §F 실증`) 가 본 patch 로 cookbook 으로만 이전됨. install.sh 코멘트에서 해당 안내 깔끔히 제거된 것 확인 (정합).

**조치**: 본 항목은 confirm only — 정합 확인 절로 이동.

---

## 정합 확인 (no issue)

### Design Step 2 review findings 해소

| ID | 항목 | 확인 위치 | 결과 |
|---|---|---|---|
| **C1** | hostname-anchored endpoint | graphify.md:71, 88 | `http://localhost:*\|http://127.0.0.1:*\|http://[::1]:*` 정합 (Ollama env 분기 + concurrency 휴리스틱 양쪽) |
| **C2** | `${!var:-}` + backend guard | graphify.md:58-60, 69 | `endpoint="${!endpoint_var:-}"` + `if [[ "$backend" == "ollama" ]]` 정합 (ENDPOINT-less profile 안전) |
| **C3** | lint.md Step 9 1줄 reference | lint.md:183 | v7 block 완전 제거 + 1줄 "graphify.md Step 2 단일 책임 (ADR-0006 + ADR-0038)" |
| **A4** | install-time profile regex warn | install.sh:785-791, 827 | `W_graphify_profile_invalid:` flag + non-fatal warn 정합. 값 mutation 없음 — ADR-0031 §Note 정합 |
| **A5** | partial graph.json 보호 | graphify.md:167-171 | `jq 'keys'` fail → `rm -f graph.json` + `exit 1` 정합 |
| **A6** | backup rotation 30일 | install.sh:1031-1032 | `find ... -mtime +30 -delete` — `_patch_hermes_external_dirs` 패턴 추종 |
| **A7** | 코멘트 drop info | install.sh:958 | `info "  - 운영자 코멘트 라인은 backup 파일에서만 참조 가능 ..."` |
| **D8** | Gap window 분석 | analysis_and_design.md §"배포 Gap window" + ADR-0036 §Note 끝 절 | service-start-time semantics + atomic mv → race window 0 명시 |
| **D9** | Rollback procedure | analysis_and_design.md §"Rollback Procedure" + ADR-0036 §Note 끝 절 | 5-step 절차 (backup ls → env 복원 → yaml 복원 → restart → 재실행 금지) 정합 |
| **D10** | Hermes trust 가정 | ADR-0038 §Decision 4 | 명시 + 검증 방법 (`systemctl --user show-environment` + `model.default` override 확인) |

### ADR coherence

- **ADR-0038 신설** (line 1~75): Status/Date/Feature/Supersedes/Context/Considered Options/Decision/Consequences/Cross-references 모두 보유 — `docs/adr/template.md` 정합 확인 (별도 read 생략 — 본 ADR 구조가 다른 ADR 와 일치).
- **ADR-0036 §Note 2026-05-24** (line 244~339): 분리 결정 explicit — "namespace 격리는 ADR-0038 로 분리 (Partially supersedes §D2)" + Cross-references 의 "ADR-0038 (신규): namespace 격리 — 본 §Note 의 §D2 partial supersede" 양방향 cross-link.
- **graphify.md 관련 ADR 절** (line 228~235): ADR-0036 + ADR-0036 §Note 2026-05-24 + ADR-0038 3건 모두 명시.
- **ADR-0031 §Note 정합**: `_migrate_graphify_env` 의 legacy 키 삭제 = schema mutation, Telegram/custom profile/기존 ollama_gemma 값 보존 = value mutation 회피. ADR-0038 §Decision 5 가 명시. `_migrate_agent_schema` 의 `graphify_profile` 자동 추가도 schema mutation only — `_op_defaults` 가 `"graphify_backend": ""` 유지 (value 변경 없음, install.sh:890) 확인.
- **ADR-0037 정합**: `_migrate_graphify_env` 의 `TELEGRAM_ALERT_BOT_TOKEN=*|TELEGRAM_ALERT_CHAT_ID=*` 분기로 값 보존 (install.sh:972-973). 빈 env file 의 경우 placeholder 코멘트 유지 (install.sh:1022-1025).

### Cookbook ↔ code alignment

- §6.1 OpenCode (ollama backend + 외부 endpoint): graphify.md ollama case (line 109-116) 의 endpoint 분기 → OLLAMA_BASE_URL 정합 (cookbook line 222 명시).
- §6.2 OpenRouter (ollama backend + claude model): 동일 패턴, concurrency 4 (외부 endpoint).
- §6.3 claude_direct (claude backend, ENDPOINT 키 부재): graphify.md `${!endpoint_var:-}` (line 58) + backend!=ollama 시 endpoint 분기 skip (line 69) — set -u 안전 정합. cookbook line 252 명시.
- §6.4~6.6: 각 backend case 의 env var (`OPENAI_API_KEY` / `GEMINI_API_KEY` / `DEEPSEEK_API_KEY` / `MOONSHOT_API_KEY`) 가 graphify.md backend case (line 117-146) 와 1:1 매칭.

### 운영 흐름 정합

- **호출 순서**: `_step5_instance_dirs` (1911) → `_migrate_graphify_env` (1912) → `_step6_agent_skill` (1913, 내부에서 `_migrate_agent_schema` 호출 1260) → `_step8_systemd_render` (1917). env namespace 정착 → yaml `graphify_profile` 자동 추가 → unit template render. 운영자 다음 invocation 시 모든 자료가 준비된 상태로 동작.
- **fresh install**: `_step5_instance_dirs` 가 namespace template 작성 → `_migrate_graphify_env` 가 drift 0 detect → no-op return. 정합 (의사코드 §5a 의 "fresh install 직후 호출 시 drift 0 → no-op return" line 1929 코멘트 정합).
- **update install** (OCI legacy env): `_step5_instance_dirs` 가 기존 env 보존 (조건 `[[ ! -f "$wh_env_file" ]]`) → `_migrate_graphify_env` 가 drift detect → backup + atomic rewrite.
- **bash syntax**: `bash -n install.sh` pass 확인.

### Documentation drift

- **HISTORY.md / README.md** 미변경 — 정합 (Step 5 영역).
- **lint.md Step 9 self-check** (line 185-194): graphify-out file read 기반 ratio 검증, lint-side 자료 — 변경 없음 (설계 의도).
- **setup.md Step 1**: active profile 3-키 검증 + Hermes terminal.env_passthrough 안내 제거 (line 109-110) — 설계 §8 정합.
- **graphify.md "사전 조건"** (line 21): ADR-0038 + namespace 격리 정합 갱신 확인.

---

## 우선순위 정리

| 우선순위 | finding | 조치 timing |
|---|---|---|
| Medium | M1 install.sh:1361 final guide stale / M2 lint.service.template:16 코멘트 / M3 install.sh:684 함수 머리 코멘트 | **본 patch 흡수 권장** — 운영자 mental model 정합 (drift 3건은 모두 sed 1줄 수준) |
| Medium | M5 Hermes terminal bash 가정 명시 | ADR-0038 §Decision 4 또는 graphify.md 1줄 |
| Low | L1 ADR-0038 §Decision 2 표현 / L2 backend/profile mismatch trace / L4 cookbook concurrency 명시 / L5 gemini flash-lite 안내 (confirm only) | 본 patch 흡수 또는 v0.1.7 followup commit |

---

## 결론

설계 (analysis_and_design.md v2) 의 모든 핵심 항목 (C1~C3, A4~A7, D8~D10) 이 본 patch 에 충실히 반영. ADR-0038 신설 + ADR-0036 §Note 2026-05-24 분리 + 양방향 cross-link 모두 정합. ADR-0031 §Note 의 schema vs value mutation boundary 준수 (legacy 키 삭제 = schema, 운영자 값 보존 = value-mutation 회피). ADR-0037 의 TELEGRAM_ALERT_* 영역 보존 검증 OK. bash syntax 정합.

**Medium 결함 3건 (M1, M2, M3)** 은 운영자 mental model 정합 측면의 stale 코멘트 — 본 patch 흡수 권장 (sed 1줄 수준의 surgical change). 흡수 후 Step 4 DoD 충족 가능. Critical / High 결함 없음 — 본 implementation 은 Step 4 (Review) 통과 권고.
