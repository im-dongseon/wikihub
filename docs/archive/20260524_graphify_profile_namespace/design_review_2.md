# Design Review 2 — Implementation Feasibility & Operational Safety

- **Reviewer**: Claude subagent (Opus 4.7, 1M context)
- **Date**: 2026-05-24
- **Scope**: `features/20260524_graphify_profile_namespace/analysis_and_design.md` §3 (graphify.md Step 2 의사코드), §5a (`_migrate_graphify_env`), §5b (`_migrate_agent_schema` 확장). Focus = 구현 가능성 + 운영 안전성 (배포 gap window, rollback, idempotency edge cases).
- **방법**: install.sh 670-940 + lint.service.template + graphify.md 현행 + docs/graphify-backend-test-reference.md cross-check.

---

## Critical 결함

**없음.** 설계의 모든 결함은 운영 권고 또는 boundary-case 강화 수준. 정본 기능은 안전.

---

## High 결함

### H1. graphify.md Step 2 의 endpoint substring 분기 — `:11434` 가 외부 endpoint 와 우발 match

**위치**: §3 line 147-150, plan.md line 84-87 (이미 §3 에서 보강하긴 함).

**문제**: `case "$endpoint" in *localhost*|*127.0.0.1*|*:11434*)` 패턴은 `https://api.example.com:11434/v1` (운영자가 외부 reverse-proxy 를 11434 port 로 띄운 시나리오) 를 `OLLAMA_HOST` (native API) 로 잘못 분기. native API 와 OpenAI-compat 는 path schema 가 다름 (`/api/chat` vs `/v1/chat/completions`) → 호출 자체 실패.

**근거**: bash glob `*:11434*` 는 substring match 라 hostname 부에 11434 가 포함된 임의 endpoint 도 match. test reference §5 의 검증된 native endpoint 는 `http://127.0.0.1:11434` (host=127.0.0.1) 라 host 부 검사가 본질적 신호.

**제안**: `:11434*` 대신 hostname-anchored 패턴으로 좁힘. 즉
```bash
case "$endpoint" in
    http://localhost:*|http://127.0.0.1:*|http://[::1]:*) ollama_env_name="OLLAMA_HOST" ;;
    *)                                                    ollama_env_name="OLLAMA_BASE_URL" ;;
esac
```
이렇게 하면 `:11434` substring 의 우발 match 가 사라지고 IPv6 loopback 도 cover. 또한 §2.5 의 결정 (D6 — endpoint pattern 양분) 의 핵심은 "localhost vs cloud" 이므로 hostname-anchored 가 의도 정합.

### H2. `WIKIHUB_GRAPHIFY_<P>_ENDPOINT` 부재 backend (claude/openai/gemini/deepseek/kimi) — `set -u` 환경에서 unbound variable

**위치**: §3 line 136 `endpoint="${!endpoint_var}"`, §6.3 cookbook line 491 `(ENDPOINT 키 생략 — claude backend 는 표준 API endpoint hardcoded)`.

**문제**: graphify.md Step 2 가 Hermes terminal 의 bash subprocess 에서 실행됨. Hermes 가 `set -u` 활성 여부 불명확하나, **install.sh** 는 `set -euo pipefail` 활성 (install.sh:20). graphify.md 의 의사코드 자체는 `set -u` 가정이 없어 보이나, indirection `${!var}` 는 `var` 가 unset 일 때 `set -u` 하에 `unbound variable` 로 fatal. claude_direct profile 처럼 ENDPOINT 키가 의도적으로 부재인 경우 Step 2 가 die.

**근거**: §6.3 의 명시적 cookbook 이 ENDPOINT 키를 생략하라고 권장. backend=claude 분기 (§3 line 187-191) 는 endpoint 를 안 쓰지만, Step 2 의 앞단 (line 136-150) 은 endpoint 를 강제 evaluate.

**제안**: indirection 전에 안전한 default 부여 + backend 가 ollama 일 때만 endpoint 분기 실행.
```bash
endpoint="${!endpoint_var:-}"   # set -u 안전
api_key="${!api_key_var:-}"
model="${!model_var:-}"
# ...
if [[ "$backend" == "ollama" ]]; then
    case "$endpoint" in
        http://localhost:*|http://127.0.0.1:*|http://[::1]:*) ollama_env_name="OLLAMA_HOST" ;;
        *) ollama_env_name="OLLAMA_BASE_URL" ;;
    esac
fi
```
또는 §6.3 의 cookbook 에서 dummy ENDPOINT 라도 명시하라고 안내 (less clean).

### H3. `_migrate_graphify_env` — 호출 위치 정합성: `info`/`ok` 함수 가용 보장

**위치**: §5a line 285-289, 294, 362.

**문제**: pseudocode 가 `info "..."` / `ok "..."` 를 호출. install.sh 앞쪽에서 정의된 helper 함수인데, `_migrate_graphify_env` 가 `_step5_instance_dirs` 직후 호출되도록 §5a 가 명시하므로 정의 순서상 OK. 다만 의사코드만 보면 함수 정의가 안 보여서 implementer 가 단독 함수로 발췌하면 ReferenceError.

**근거**: install.sh:823 의 기존 `_migrate_agent_schema` 도 동일 helper 사용. 패턴 동일.

**제안**: 구현 시 `_migrate_agent_schema` 와 동일 위치 (line 754 직전 또는 직후) 에 정의. analysis_and_design.md §5a 의 "호출 위치" 절이 `_step5_instance_dirs` 직후라고 명시했는데, install.sh 의 main flow 에서 `_migrate_agent_schema` 가 `_step5_instance_dirs` 보다 뒤에 호출되는 시점을 함께 명시 (구체 line number) → implementer guidance 강화.

---

## Medium 결함

### M1. `exit 2` 와 systemd `SuccessExitStatus=0 75` 의 정합 — ops-alert 발화 정상

**위치**: §3 line 128-129, 142-143, 212. lint.service.template:19 `SuccessExitStatus=0 75`.

**확인**: exit 2 는 SuccessExitStatus 목록 (0, 75) 에 없음 → systemd 는 fail 로 인식 → `OnFailure=ops-alert.service` (line 5) 가 trigger. **정합 (no issue)**. 단, graphify.md Step 2 는 **lint** subprocess 가 아니라 Hermes 가 spawn 한 terminal subprocess 내부에서 실행됨. exit 2 가 Hermes terminal 까지 bubble up 하는지가 핵심. Hermes 가 subprocess exit code 를 자기 exit code 로 forward 하지 않으면 ops-alert 미발화. 본 영향은 graphify.md Step 1 (line 33) 의 기존 `exit 2` 와 동일 — 기존 동작에 의존하므로 본 patch 의 추가 risk 0.

**제안**: 없음 (기존 패턴 추종).

### M2. `timeout 720` vs graphify 의 `--api-timeout 600` — wrapper kill 시 partial graph.json 위험

**위치**: §3 line 173-208 (모든 backend case). §3 line 217 의 설명.

**문제**: graphify v8 의 `--api-timeout` default 가 600s 이고 LLM 호출 N건 시 누적 시간은 N×600s 까지 가능. `timeout 720` 은 first LLM call 끝나기 전에 kill 할 수도 있음 (wiki 가 50+ docs 면). 반대로 첫 call 이 짧고 후속 call 다수 누적 시 720 초과로 kill — graph.json partial write 가능.

**근거**: test reference §5 의 3 docs subset 은 짧은 시간 내 완료지만, OCI 운영 wiki 가 클 때 timeout 도달 위험 실재. 현 graphify.md (line 53) 의 `timeout 300` 도 동일 문제 있었으나 v0.1.6 적용 후 OCI 운영 실측 데이터 부재.

**제안**: (a) `timeout 720` 을 yaml `operations.graphify_timeout_sec` 로 expose (v0.2.x 로 deferred 한다고 §3 line 217 이 명시 — 정합). (b) **본 patch 범위에서**: backend별 timeout 차등 (cloud-only = 1800, local = 720) 으로 조정 검토. (c) partial graph.json 보호 — Step 3 검증 (§4) 에서 `jq 'keys' graph.json` 가 fail 하면 graph.json 삭제 → exit 1 로 force clean.

### M3. `_migrate_graphify_env` 가 코멘트·blank 라인 통째 drop — 운영자 manual 코멘트 손실

**위치**: §5a line 271, 314 (`\#*|"") continue`).

**문제**: pseudocode 가 코멘트 line 을 모두 drop 하고 canonical template 으로 교체. 운영자가 env 파일에 적어둔 customization 메모 (예: `# REVIEW: 2026-06 에 openrouter 로 swap`) 가 소실. 자동 migration 의 매력 ↔ 운영자 데이터 보존 의 trade-off — §5a 의 표 (line 258) 가 명시적으로 "canonical template 으로 교체 (운영자 코멘트 없다고 가정)" 라고 선언하므로 의도된 동작이긴 함.

**근거**: ADR-0031 §Note "value mutation = operator trust" 의 정신 — value 는 보존하나 코멘트는 보존 대상에서 제외하는 결정의 명시적 trade-off.

**제안**: (a) 운영자 코멘트 drop 사실을 backup 파일과 함께 info 로 surface — `info "  - 운영자 코멘트 라인은 backup 에서만 참조 가능 ($backup)"`. (b) HISTORY.md 항목에도 명시. (c) 더 안전한 옵션 — `WIKIHUB_GRAPHIFY_*` 가 아닌 KEY=VAL 라인 (예: `# Custom note: ...`) 을 `custom_lines` 에 흡수하는 로직 추가. 권장은 (a)+(b) — 단순성 우선.

### M4. backup file 누적 — disk fill 장기 risk

**위치**: §5a line 292-294.

**문제**: 매 `install.sh --update` 가 drift 감지 시 신규 backup `.wikihub-bak.<utc>` 생성. rotation 없음. 운영 1년 누적 시 ~365개 파일 (각 < 4KB) — 실 disk fill 위험 minor 이나 정책상 누적 자체가 의도와 다를 수 있음.

**근거**: `_migrate_agent_schema` 도 동일 패턴 (`$yaml.wikihub-bak.<utc>`). install.sh:1095 의 `_patch_hermes_external_dirs` 는 7일 retention (`-mtime +7 -delete`) 적용 — 정책 inconsistency 도 surface.

**제안**: `_migrate_graphify_env` 끝에 `_patch_hermes_external_dirs` 동일 패턴 추가.
```bash
find "$wh_config_dir" -maxdepth 1 -name 'env.wikihub-bak.*' -mtime +30 -delete 2>/dev/null || true
```
또는 별도 ADR 으로 backup 정책 통일 (`_migrate_agent_schema` + Hermes config + env 의 retention 일관화). 본 patch 에서 atomic 수정은 후자.

### M5. systemd 서비스 자동 재시작 부재 — 배포 gap window 정의

**위치**: 설계 전반. analysis_and_design.md 의 "rollback path" 또는 "deploy 절차" 섹션 부재.

**문제**: `install.sh --update` 후 (a) yaml 에 `graphify_profile` 추가됨 (b) env 가 namespace 로 rewrite 됨 (c) systemd service 는 마지막 start 시점의 env (legacy `OLLAMA_*`) 로 동작 중. 다음 timer fire 시 `EnvironmentFile=` 가 재read 되어 새 env 가 적용. timer interval 이 24h 이므로 gap window = 0~24h. 그 사이:
- wh-lint timer 가 graphify.md Step 2 의 **새 코드** (materialize 된 SKILL.md) 를 run → 새 코드는 `WIKIHUB_GRAPHIFY_*` env 를 기대 → systemd unit env 는 아직 미 reload 인데 `EnvironmentFile=` 는 service start 시 read 이므로 **현 timer 사이클은 이미 새 env 가 file 에 있어 OK**. 즉 next timer fire 시 정상 동작.
- 위의 미묘한 점: `EnvironmentFile=-%h/.config/wikihub/env` 는 service start 시점에 read. install.sh 가 service running 중에 env 를 rewrite 해도 running service 는 영향 없음. timer 가 다시 fire → 새 oneshot service 인스턴스 start → 새 env read. **gap window 의 worst case = 현 timer 사이클이 graphify 호출 중일 때 install.sh 가 env 를 rewrite** — race window 거의 0 (graphify subprocess 이미 env 받았음).

**근거**: lint.service.template:8 `Type=oneshot`. systemd EnvironmentFile semantics (start 시 1회 read).

**제안**: 실 risk 없음. 단 설계 문서에 명시 누락 — analysis_and_design.md 에 "배포 gap window 분석" 1 절 추가 권장 (review check item). 또한 운영자가 immediate 검증하고 싶을 때를 위해 install.sh 끝에 `systemctl --user start wikihub-lint.service` 또는 안내 message 추가 (옵션).

### M6. rollback 절차 미문서화

**위치**: §5a 의 backup 생성은 명시되나 rollback steps 가 design 어디에도 없음.

**문제**: 운영자가 migration 후 문제 발생 시 어떻게 되돌릴지 분명한 가이드 부재. backup 파일은 있으나 (env + yaml 둘 다 backup), 적용 순서 (env 먼저? yaml 먼저?) 와 service restart 필요 여부 안내 없음.

**제안**: ADR-0036 §Note 2026-05-24 에 "Rollback procedure" 절 추가:
```
1. cp ~/.config/wikihub/env.wikihub-bak.<utc> ~/.config/wikihub/env
2. cp ~/.wikihub/wikihub.yaml.wikihub-bak.<utc> ~/.wikihub/wikihub.yaml
3. systemctl --user restart wikihub-lint.service (optional, next timer fire 도 자동 적용)
4. install.sh 재실행 금지 — drift detect 가 다시 migration 시도
```

---

## Low / 권장 개선

### L1. §5a 의 `\#*|"")` glob — leading whitespace 코멘트 처리

`case "$line" in \#*|"")` 는 `^#` 만 match. 운영자가 `  # comment` (앞 공백) 로 적었으면 그 라인은 drop 되지 않고 default branch 로 흘러 — `WIKIHUB_GRAPHIFY_*=*` 등 다른 패턴도 안 맞으므로 결국 silently 무시 (output 안 됨). **결과는 동일** (drop) 이라 functional impact 0. 단 implementer 가 향후 default branch 에 warning 추가 시 헷갈릴 수 있음.

**제안**: 코멘트 패턴을 `[[:space:]]*\#*|"")` 로 확장 — 단 bash glob 은 character class 미지원이라 `case` 가 아닌 `[[ "$line" =~ ^[[:space:]]*# ]]` 가 필요. 단순성 우선이면 현 패턴 유지 (실 위험 0).

### L2. §3 line 175 `OLLAMA_API_KEY="${api_key:-local-daemon}"` — 명시적 empty assign 처리

bash `${VAR:-default}` 는 unset OR empty 시 default 사용. 운영자가 `WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_API_KEY=` (explicit empty) 로 적어둔 경우 `api_key=""` 가 되고 fallback `local-daemon` 적용. test reference §3 ("any non-empty value") 와 정합 — **의도 정합 (no issue)**. 단 다른 backend (openai 등) 는 fallback 없음 — `env OPENAI_API_KEY=""` 가 graphify 에 전달되어 graphify 가 fail. 의도된 동작이긴 함 (env 미설정 = 운영자 실수).

**제안**: §3 line 142-143 의 model check 옆에 api_key check 추가 — backend != ollama 일 때 api_key 빈값 검출 + fatal.
```bash
if [[ "$backend" != "ollama" && -z "$api_key" ]]; then
    echo "ERROR: $api_key_var unset for non-ollama backend" >&2; exit 2
fi
```

### L3. §5a 의 `og_endpoint=""` 초기화 + `: "${og_endpoint:=http://127.0.0.1:11434}"` — set -u 보호

install.sh 가 `set -u` 활성. line 299 의 `local og_endpoint="" og_api_key="" og_model=""` 가 선제 초기화 → `:=` 가 안전하게 동작. **정합 (no issue)**. 다만 implementer 가 초기화 라인을 누락하면 set -u 하에서 fatal — 의사코드를 코드로 옮길 때 주의 필요.

### L4. `_migrate_agent_schema` 의 graphify_profile 추가 — info log case label 정합

§5b line 402 의 info log case label = `B_graphify_profile` 이며 메시지는 `"[v0.1.7 follow-up] operations.graphify_profile 부재 → \"ollama_gemma\" 추가"`. 기존 line 836 의 `B_graphify_backend` 메시지는 `"[ADR-0036] ..."` prefix. 일관성을 위해 `B_graphify_profile` 도 `"[ADR-0036 §Note v0.1.7]"` prefix 권장 — ADR 식별자가 정본이라는 §7 ADR 원칙 정합.

### L5. Hermes session restart 명시

`_materialize_skills` 가 매 install 실행. 새 graphify.md (Step 2 rewrite) 가 `~/.hermes/skills/wh-graphify/SKILL.md` 에 반영. Hermes 가 매 invocation 시 SKILL.md 를 read 하면 자동 적용. 캐시 메커니즘 시 session restart 필요. 본 patch 가 Hermes 의 SKILL.md cache 정책에 영향 받음 — design 에 명시 부재.

**제안**: ADR-0036 §Note 2026-05-24 에 "Hermes SKILL.md cache 확인 — Hermes 가 매 chat 시 read 면 자동, file watcher 기반이면 자동, in-memory cache 면 `hermes restart` 또는 운영자 안내" 1 줄. 실측 필요 사항이라 design 단계에서 결정 보류 가능.

---

## 정합 확인 (no issue)

- **§3 의 `endpoint="${!endpoint_var}"` indirection**: bash 4+ 표준. Hermes 의 terminal tool 이 `/bin/sh` 가 아닌 `bash` invoke 하는지가 결정적. OCI Ubuntu 24.04 의 `/bin/sh` 는 dash → indirection 미지원. **그러나** graphify.md 의 다른 곳 (현 line 44 `backend="$(yq ...)"` 의 `$()` 도 POSIX OK 이긴 함) 에서 이미 bash-ism 사용. 따라서 Hermes terminal 이 bash 호출이라는 가정이 본 design 의 기반. plan.md `q` Q1~Q6 결정 단계에서 이미 검증된 전제로 추정.
- **§5a atomic write `mv "$tmp" "$wh_env_file"`**: tmp 가 `$wh_env_file.tmp` 라 동일 디렉토리 → 동일 filesystem → atomic OK.
- **§5a `chmod 600`**: cp -p 가 source mode 보존 → backup 도 600. mv 후 chmod 600 명시 → tmp 의 default umask (0644 등) 영향 차단.
- **§5a idempotency 정의**: 3-key 모두 present + legacy 0 → no-op return. 정확.
- **§5a empty env file (0 bytes)**: while loop 0회 → has_legacy=0, has_endpoint/key/model=0 → drift 감지 → migration → fresh canonical. **정합 (의도 정확)**.
- **§5a 운영자 custom profile (e.g. `WIKIHUB_GRAPHIFY_OPENCODE_MINIMAX_*`)**: line 311-312 `WIKIHUB_GRAPHIFY_*=*) custom_lines+=...` 가 ollama_gemma 외 namespace 를 보존 — 정합. 단 ollama_gemma 의 3 키 중 1개만 missing 인 부분 케이스에서도 custom profile 은 보존됨 (case branch 순서 정합).
- **§5a legacy AND new keys both present**: case 분기에서 legacy 는 drop, new 는 `og_*` 변수로 capture → 후속 atomic write 에 new 만 반영. 정합.
- **§5b `_migrate_agent_schema` 확장**: 기존 Group B 패턴 1 항목 추가 — schema mutation only, value mutation 안 함 (ADR-0031 §Note 정합). drift detect Python block + _op_defaults dict 1 줄씩 추가 → 위험 0.
- **`_step5_instance_dirs` fresh install template (§6)**: 새 namespace + Telegram comments 만. install.sh:690-732 의 단순화 — line 수 감소가 maintainability 개선. lint.service.template 의 EnvironmentFile= path 변경 없음.

---

## 종합 의견

**Critical/High 결함은 H1, H2 만**. H1 (`:11434` substring match) 은 운영자가 외부 reverse-proxy 를 11434 로 띄울 가능성이 낮으나 future-proofing 차원에서 hostname-anchored 로 좁히기 권장. H2 (claude_direct 등 ENDPOINT-less profile 의 `set -u` 충돌) 는 §6.3 cookbook 의 명시적 권장과 충돌 — 반드시 `${!endpoint_var:-}` 형식 + backend=ollama 가드 추가 필요.

Medium 결함 중 **M5/M6 (gap window 분석 + rollback 문서)** 가 운영 안전성 측면에서 가장 가치 있음 — install.sh 코드 변경은 minimal, ADR/HISTORY 1 절 추가로 cover 가능.

설계의 핵심 (env namespace 격리 + v8 CLI sync + migration) 은 ADR-0031 §Note "schema mutation = install.sh 책임" 정합. ADR-0037 (alert pipeline), ADR-0036 (graphify integration) 와 충돌 없음. Karpathy §2 "Simplicity First" 와 §3 "Surgical Changes" 정합 — 본 patch scope (yaml schema 1 field + env namespace + graphify.md Step 2) 가 최소 변경으로 두 가지 문제 (Hermes bleed + v8 CLI drift) 해결.

**권장 진행**: H1, H2 반영 후 Step 3 진입. M5, M6 은 ADR-0036 §Note 의 동일 commit 으로 통합.
