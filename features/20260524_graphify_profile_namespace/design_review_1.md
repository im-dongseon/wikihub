# Design Review 1 — Architecture & ADR Consistency

- **Reviewer**: Claude subagent (Opus 4.7, 1M context, 컨텍스트 초기화)
- **Date**: 2026-05-24
- **Scope**: analysis_and_design.md + plan.md (Q1~Q6) 의 architectural soundness + ADR-0031/0032/0036/0037 정합
- **Cap**: ~1000 words

---

## Critical 결함

**없음** — namespace 격리 + v8 CLI 정합 + `_migrate_*` 분리는 핵심 architecture 가 ADR-0031 §Note (value vs schema mutation) 정합으로 안전. 다만 아래 High 1건은 운영 안전성에 직결되어 Critical 인접.

---

## High 결함

### H1. lint.md Step 9 의 backend dispatch 잔존 — graphify.md 와 dual source

**위치**: `_system/commands/lint.md:183-196` (Step 9 backend dispatch 본문)
**문제**: lint.md Step 9 가 `backend="$(yq '.operations.graphify_backend // ""' …)"` + `--backend $backend` + `timeout 300 graphify "$WIKIHUB_HOME/wiki" --update $backend_flag` 로 v7 CLI 패턴 + `--update` flag 를 **직접** 호출. graphify.md Step 2 의 정본화 로직 (profile resolve + endpoint 분기 + `extract` subcommand + `--out`) 을 lint.md 가 우회하면 namespace 격리 자체가 무효 (env 가 OLLAMA_* 로 명시 변환 안 됨).
**근거**: 본 patch 의 §1 개정 범위 표에 `lint.md` 미포함. §"연계 룰/스킬 정합성 검토" 표는 "lint.md 본문 변경 없음 — 정합" 으로 표시. 그러나 lint.md:188-191 의 backend dispatch 코드 자체가 graphify CLI 를 직접 호출하는 dual source — graphify.md Step 2 와 분기 로직 중복.
**제안**: lint.md Step 9 의 backend dispatch 본문 (line 183-196) 을 **agent_invocation 호출 1줄** 로 축소 — `<agent_invocation> "/wh-graphify"` 만 남기고 backend/timeout/dispatch 는 graphify.md Step 2 단일 책임 (ADR-0006 single-source 정합). 본 patch 의 개정 범위에 `lint.md Step 9 정리` 추가. (v0.1.6 graphify.md backend fix 의 직전 commit eb766ef·b09c564 가 lint.md ↔ graphify.md 정합을 한 번 fix 한 흐름과도 정합.)

---

## Medium 결함

### M1. endpoint 분기의 IPv6/Docker network/LAN edge case

**위치**: §2.5 + graphify.md Step 2 case 분기 (line 147-150)
**문제**: pattern `*localhost*|*127.0.0.1*|*:11434*` 는 다음 case 가 misclassify —
- **IPv6 loopback** (`http://[::1]:11434`) — `:11434` substring 으로 OLLAMA_HOST 분기 OK (정합).
- **LAN Ollama** (`http://192.168.1.10:11434`) — `:11434` substring match → **OLLAMA_HOST native API**. 그러나 Ollama 본가 native API endpoint 와 OpenAI-compat endpoint 는 *별도 path* (native=`/api/chat`, compat=`/v1/chat/completions`). substring 으로 native 보장 안 됨.
- **Docker network** (`http://ollama:11434`) — service name. `:11434` substring match OK.
- **ngrok / reverse proxy** (`https://abc.ngrok.io`) — port 명시 X, localhost X → OLLAMA_BASE_URL (compat). 운영자가 native 노출했어도 compat 분기 → fail.
- **non-standard port local** (`http://127.0.0.1:8080`) — `127.0.0.1` substring match → OLLAMA_HOST, OK.

**근거**: plan.md Q2 옵션 (c) `graphify_ollama_mode: native|compat` yaml hint 가 cleanest. 현 채택 (b) 는 *대다수* OK 지만 LAN/reverse-proxy edge case 에 silent misroute.
**제안**: §2.5 에 fallback override 명시 — `WIKIHUB_GRAPHIFY_<PROFILE>_OLLAMA_MODE=native|compat` env (optional, 빈 값이면 substring 휴리스틱) 1 키 추가. graphify.md Step 2 의 case 분기 전에 env override check. Q2 결정의 spirit (단순 휴리스틱) 보존하면서 edge case escape hatch 제공.

### M2. `:11434` substring 이 path/query string 에 우연 match 가능

**위치**: graphify.md Step 2 case glob `*:11434*` (line 148)
**문제**: bash glob 은 부분 match — `https://api.example.com/x?port=11434` 같은 URL 도 OLLAMA_HOST 분기. realistic 빈도는 낮으나 silent misroute.
**제안**: regex `^[^:]+://[^/]*:11434(/|$)` 처럼 host:port 위치 한정. 또는 M1 의 env override 가 결정적 escape — Q2 (b) 의 substring 휴리스틱 fragility 인지 명시.

### M3. profile 명 regex 검증이 graphify.md runtime 만 — install-time validation 부재

**위치**: §5b `_migrate_agent_schema` + Q4 결정 (d) (graphify.md runtime)
**문제**: `_migrate_agent_schema` 가 `operations.graphify_profile: "ollama_gemma"` 자동 추가만, 운영자가 yaml 편집해 `graphify_profile: "OLLAMA-Gemma!"` (regex fail) 로 변조 시 install.sh 가 detect 안 함. runtime (`/wh-graphify` 호출) 에서 처음 fail → ops-alert. *fail-fast* 측면 약함.
**근거**: ADR-0031 §Decision E (schema version 검증) 패턴 — fail-fast 가 install-time / setup-time 에 surface. profile 명도 schema 정합 자료. plan.md Q4 (d) 가 "silent fail 회피" 명분이라 install-time validation 이 자연 follow-up.
**제안**: `_migrate_agent_schema` 의 detect 단계에 `profile_invalid` flag 추가 — `re.match(r"^[a-z][a-z0-9_]*$", profile)` 검증 + fail 시 info log + 운영자 fix 안내 + non-fatal warn (값 변경 자동 회피 정책 정합 — `_migrate_agent_schema` 가 운영자 값 mutate 안 함, 단 surface).

### M4. `graphify_backend` + `graphify_profile` 의 redundancy/mismatch 운영 burden

**위치**: §7 yaml 갱신 + §6 test-reference cookbook
**문제**: 두 필드가 **orthogonal 이라 명시되어 있지만 운영자 mental model 에서는 강결합**. cookbook §6.1~6.6 의 모든 row 가 `backend: X / profile: X_modelhint` 패턴 — backend 가 profile 의 prefix 와 1:1. 운영자가 backend 만 바꾸고 profile 안 바꾸면 silent misconfig (예: `backend: claude / profile: ollama_gemma` → graphify.md case 가 ANTHROPIC_API_KEY 로 dispatch 하면서 ollama_gemma 의 ENDPOINT 값을 무시 → 운영자 의도와 다른 model 호출).
**근거**: cookbook 자체가 두 필드의 1:1 매핑을 증명. 명목상 orthogonal 한 이유 = "ollama backend + opencode profile" 같은 mixed case 가 가능해서지만, 실제 호출 시 backend 가 case dispatch + profile 이 env 키만 결정 → backend 와 profile 의 provider 부분이 매칭 안 되면 운영자 의도 깨짐.
**제안**: graphify.md Step 2 에 **consistency check** 추가 — `case "$backend" in claude) [[ "$profile" =~ ^claude_ ]] || warn "profile prefix mismatch backend";; …`. fail 아닌 warn 으로 충분 (advanced 운영자 의도 case 예: ollama backend + opencode_minimax profile 은 legitimate). Q4 결정 (d) 의 silent-fail-회피 spirit 와 정합.

### M5. ADR-0036 §Note 의 7 결정 — 별도 ADR 분리 검토

**위치**: §9 ADR-0036 §Note 신설
**문제**: ADR-0036 본문은 v0.1.0 의 graphify 통합 정본, §Note 가 이미 4 건 (2026-05-20 backend flexibility / lint default 변경 / lint_fallback_toggles / v016_operational_default_align). 본 patch 가 §Note 5번째 추가 + 7 결정 항목 동시 — §Note 가 ADR 본문보다 길어질 위험. Decision 1 (namespace 격리) 은 ADR-0036 §D2 본문의 "API key 저장 layer" 를 **근본적으로 mutate** (single env file → namespaced bundle). value mutation 이 아니라 schema-of-secret-layer mutation.
**근거**: ADR convention §"결정 1건 = 파일 1개" (CLAUDE.md §7). 본 patch 의 결정 1 (namespace) + 결정 2 (v8 CLI sync) + 결정 5 (check-update deferred) 는 각각 별도 ADR 가능한 weight.
**제안**: namespace 격리 (결정 1+7) 만 **신규 ADR-0038** (graphify-env-namespace-isolation), 나머지 (결정 2~6) 는 ADR-0036 §Note 로 남김. ADR-0038 이 ADR-0036 §D2 를 `Partially supersedes` 로 명시. ADR convention 정합 + 향후 namespace 재변경 시 history trace 명확.

---

## Low / 권장 개선

### L1. lint.service.template `EnvironmentFile=` 가 Hermes parent 에 namespace env 까지 로드

**위치**: `_system/systemd/lint.service.template:17`
**문제**: `EnvironmentFile=-%h/.config/wikihub/env` 가 *lint.service* (= Hermes parent invocation) 에 *전체 파일* 로드 → `WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_*` 도 Hermes parent env 에 주입. Hermes 가 unknown prefix env 를 무시한다는 *implicit* 가정. ADR-0032/0036 의 `terminal.env_passthrough` 메커니즘이 Hermes child (graphify subprocess) 의 env strip 정책 — parent 의 env 인식은 별개. **본 patch 의 namespace 격리는 "Hermes 가 OLLAMA_* / ANTHROPIC_API_KEY 같은 표준 이름만 인식한다" 가정에 의존**. namespace prefix `WIKIHUB_GRAPHIFY_*` 는 Hermes 가 인식할 표준 컨벤션 아니라 safe — 그러나 가정의 명시화 부재.
**제안**: ADR-0036 §Note 또는 신규 ADR-0038 에 trust 가정 명시 — "Hermes 는 자기 인식 env namespace (OLLAMA_*, ANTHROPIC_*, OPENAI_*, GEMINI_*) 만 react. `WIKIHUB_GRAPHIFY_*` 는 Hermes 가 무시 (verified: 2026-05-24 OCI 또는 hermes source line ref)." DoD 의 운영 검증 항목에 `hermes process env grep "WIKIHUB_GRAPHIFY_"` 결과 = "loaded but not interpreted" 명시.

### L2. `check-update` deferred 의 alternative path 미탐색

**위치**: §3 의 fact table + plan.md Q5 (c)
**문제**: OCI 검증이 exit=0 + stdout 무음 1건만 시도. journalctl scan / marker file detection / strace 등 alternative path 탐색 trace 부재. v0.2.x 재방문 시점 운영자/메인테이너가 "왜 deferred" 만 알고 "alternative 가 다 시도됐는가" 불확실.
**제안**: §3 의 fact table 에 1줄 — "alternative: journalctl `wikihub-lint.service` graphify subprocess output scan 검토 (정합 grep pattern 없음, graphify 자체 verbose logging 부재). marker file (graph.json mtime vs wiki/ newest mtime 비교) 는 graphify 의 internal cache 와 unsynced — false positive 위험. v0.2.x 검토."

### L3. concurrency 휴리스틱의 `*cloud*` substring match — model 명 wild

**위치**: §2.6 + graphify.md Step 2 (line 153-161)
**문제**: `gemma4:31b-cloud` 처럼 `cloud` suffix 패턴은 Ollama daemon 의 cloud-proxied tag 컨벤션이지만 일반 모델 명에 `cloud` substring 출현 가능 (예: `cloudburst-llm`, `accloud-model`). silent misclassify → concurrency 4 (cloud) vs 1 (local) 분기 잘못.
**제안**: 정규식 `:[^:]*cloud$` 또는 `[-:]cloud(\.|$|[-:])` 으로 token boundary 명시. 또는 endpoint 가 `127.0.0.1` + model 이 `:cloud` suffix 결합 시만 cloud-proxied 로 classify (운영 실증 패턴).

---

## 정합 확인 (no issue)

- **ADR-0031 §Note (v0.1.7) — schema vs value mutation**: `_migrate_graphify_env` 가 legacy 키 (OLLAMA_*/ANTHROPIC_API_KEY/OPENAI_API_KEY/GEMINI_*) **삭제** = schema mutation. Telegram 값 보존 + ollama_gemma 기존 값 보존 = value mutation 회피. ADR-0031 §Note 의 boundary 정합. (분석: 환경변수 *이름 자체가 schema* — legacy 이름의 키 삭제는 schema namespace cleanup. 단 운영자가 의도적으로 OLLAMA_* 를 유지하고 싶은 case 는 backup 파일로 복원 가능 — ADR-0031 §Note 의 backup safety net 정합.)
- **ADR-0032 (hermes-skill-registration)**: 본 patch 가 Hermes config.yaml 한 글자도 안 만짐. setup.md Step 1 안내문 변경 (terminal.env_passthrough 안내 제거) 은 운영자 *guidance* 변경, ADR-0032 §sub-4 의 mutate 책임 범위 변동 없음.
- **ADR-0037 (alert-pipeline)**: `TELEGRAM_ALERT_BOT_TOKEN` + `TELEGRAM_ALERT_CHAT_ID` 가 `_migrate_graphify_env` 의 **값 보존** 대상 명시 (§5a 의 Migration 정책 표). ops-alert.service 의 `EnvironmentFile=-%h/.config/wikihub/env` 영향 0. ADR-0037 §D1 (Telegram env 채널) 정합.
- **2-mode dispatch (--rebuild vs default)**: graphify v8 의 internal cache 가 incremental 자동 보장 (test reference §1) → wikihub 측 추가 mode 불필요. v7 era 의 `--update` flag 폐기 정합. `check-update` gate 가 Q5 (c) 로 deferred 된 후 missing mode 없음.
- **graphify v8 CLI 정합**: `extract <wiki> --backend X --model Y --max-concurrency N --out DIR` 패턴이 test reference §5 검증된 ground truth — graphify.md Step 2 의 6 backend case dispatch (line 171-214) 정합.

---

## 우선순위 정리

| 우선순위 | finding | 조치 timing |
|---|---|---|
| **High** | H1 lint.md Step 9 dual source | **본 patch 에 흡수** — graphify.md 와 lint.md 정합 단일 사이클 |
| Medium | M1 endpoint env override / M3 install-time profile 검증 / M4 backend-profile consistency warn | 본 patch 에 흡수 권장 (graphify.md Step 2 / install.sh 최소 추가) |
| Medium | M2 substring fragility (regex tighten) / M5 ADR 분리 | 본 patch 흡수 또는 v0.1.7 followup commit 분리 |
| Low | L1 trust 가정 명시 / L2 check-update alternative trace / L3 cloud regex tighten | §Note 1~2 줄 보강 |

**결론**: 핵심 architecture (namespace + v8 CLI + auto-migration) 는 sound. **H1 (lint.md dual source) 1건만 본 patch 흡수 권장** — 그 외는 운영 안전성·trace·long-term ADR 정합 측면의 보강. 본 design 을 Step 3 (Implementation) 진입 가능 — H1 흡수 후.
