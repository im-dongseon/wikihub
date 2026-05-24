# Analysis & Design — graphify profile namespace + CLI v8 정합 (v0.1.7 follow-up)

approved: 2026-05-24

> 본 문서의 결정은 ADR-0036 §Note (2026-05-24, CLI v8 sync) + 신규 ADR-0038 (namespace isolation, U1 결정) 로 분리 추출. plan.md 의 Q1~Q6 결정 (모두 확정) 정합.

## 변경 이력

- **v1** (2026-05-24): 초안 작성. plan.md Q1~Q6 결정 반영.
- **v2** (2026-05-24): Step 2 design review (`design_review_1.md` + `design_review_2.md`) 반영
  - C1: endpoint pattern hostname-anchored (substring → URL prefix)
  - C2: claude_direct 등 ENDPOINT-less backend 의 `set -u` 안전화 (`${!var:-}` + backend guard)
  - C3: lint.md Step 9 의 v7 패턴 설명 block 정리 (1줄 reference)
  - A4: install-time profile 정규식 validation (`_migrate_agent_schema` warn)
  - A5: Step 3 결과 검증에 partial graph.json 보호 (jq keys fail → delete + exit 1)
  - A6: backup 파일 `-mtime +30 -delete` rotation
  - A7: 운영자 코멘트 drop info surface
  - D8: Gap window 분석 절 신설
  - D9: Rollback procedure 절 신설
  - D10: Hermes trust 가정 명시
  - U1 (b): ADR 분리 — namespace isolation 만 신규 ADR-0038, CLI v8 sync 는 ADR-0036 §Note

---

## 분석

### 1. 배경 및 목적

OCI 운영 (2026-05-22 ~ 2026-05-24) 에서 두 가지 문제 surface:

1. **Hermes env bleed**: `~/.config/wikihub/env` 의 `OLLAMA_BASE_URL/API_KEY/MODEL` 이 systemd `EnvironmentFile=` 경유로 Hermes parent process 에 주입 → Hermes 가 자기 LLM backend 로 인식 → `model.default` 오버라이드. graphify subprocess 만 받아야 할 자료가 leak.
2. **graphify v8 CLI drift**: graphify.md Step 2 의 호출 패턴 (`graphify <wiki> [--update] $backend_flag`) 이 v8 의 실제 CLI (`graphify extract <wiki> --backend X --model Y --max-concurrency N --out DIR`) 와 어긋남. `docs/graphify-backend-test-reference.md` (2026-05-23 검증) 이 ground truth 제공.

부차적 운영 요구: opencode / openrouter / local Ollama 등 **여러 backend·endpoint·model 묶음을 동시 보유**하고 yaml 한 줄로 swap 하는 시나리오 (model 비교 테스트 + provider fail 시 대체).

### 2. 현행 진단 (결함 목록 및 근거)

| ID | 결함 | 근거 |
|---|---|---|
| **D1** | `OLLAMA_*` namespace 가 Hermes 도 인식하는 표준 컨벤션 | OCI 운영 관측: `model.default` (deepseek-v4-flash) 가 ollama 로 fallback. install.sh:683 `EnvironmentFile=` 가 unscoped env 주입 |
| **D2** | graphify.md Step 2 가 v8 CLI 와 불일치 | `graphify --help`: `extract` subcommand 필수, `--out DIR` 명시, `--model` flag, `--max-concurrency`. 현 graphify.md:55-66 의 `graphify <wiki> --update` 는 v8 미존재 |
| **D3** | profile 다중 보유 불가능 | 현 env: 단일 `OLLAMA_*` 키 세트. 운영자가 OpenCode → OpenRouter swap 시 env 파일 편집 + service restart |
| **D4** | JSON 검증이 잘못된 key 가정 | `docs/graphify-backend-test-reference.md` §1: edges 는 `.links` (NetworkX node-link format). 현 graphify.md:104 는 "edges 수" 만 언급 |
| **D5** | local Ollama daemon 에서 graphify 가 `OLLAMA_API_KEY` unset warning | test reference §3: "any non-empty value" 로 회피. 운영자가 dummy 매번 채우는 burden |
| **D6** | endpoint 형식이 native vs OpenAI-compat 두 종 — 단일 env 키로 양분 어려움 | test reference §5: `OLLAMA_HOST=http://127.0.0.1:11434` (native) ↔ install.sh 코멘트 `OLLAMA_BASE_URL=https://opencode.ai/zen/go/v1` (compat) |
| **D7** | `--max-concurrency` 권장값 backend 별 다름 | graphify --help: "default 4; set 1 for local LLMs". 현 graphify.md 미명시 |

### 3. 사실 근거 (검증된 ground truth)

| 출처 | 사실 |
|---|---|
| `docs/graphify-backend-test-reference.md` §1 | NetworkX node-link, edges 는 `.links` 위치 |
| 동 §3 | local Ollama 의 `OLLAMA_API_KEY` warning — non-empty 값 (dummy `local-daemon` 등) 으로 회피 |
| 동 §5 | `graphify extract <wiki> --backend ollama --model gemma4:31b-cloud --max-concurrency 1 --out <dir>` 패턴 검증 |
| graphify v8 `--help` | backends: `gemini|kimi|claude|openai|deepseek|ollama` (6종). `--out DIR` 가 `DIR/graphify-out/` 생성 |
| 동 | `update <wiki>` 는 AST-only (code 전용, no LLM) — markdown wiki 부적합 |
| 동 | `check-update <wiki>` "cron-safe" 라고 표현 |
| OCI 검증 (2026-05-24) | `check-update` 가 3 시나리오 (graph.json 미존재 / extract 직후 / wiki 수정 후) 모두 `exit=0` + stdout 무음 — gate 활용 불가 |

---

## 설계

### 1. 개정 범위

| 파일 | 변경 성격 | 주요 변경 |
|---|---|---|
| `install.sh` `_step5_instance_dirs` | env template 전면 단순화 (fresh install 만) | 기존 6 backend 예시 block 제거 → 단일 `WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_*` 활성 default + 코멘트로 docs reference 안내 |
| `install.sh` `_migrate_graphify_env` | **신규** — 기존 env 파일 자동 migration | legacy 키 삭제 + Telegram 보존 + ollama_gemma default inject. PTY-safe, idempotent, backup |
| `install.sh` `_migrate_agent_schema` | `_op_defaults` 1 항목 추가 | `operations.graphify_profile: "ollama_gemma"` 자동 추가 |
| `wikihub.yaml.example` | `operations` 섹션 필드 1개 신설 + 코멘트 갱신 | `graphify_profile: ollama_gemma`. `graphify_backend` 코멘트 — "protocol" 의미 명확화 |
| `_system/commands/graphify.md` | Step 2 전면 재작성 + Step 3 .links 정합 | profile resolve + endpoint/concurrency 자동 분기 + backend case + 2-mode (rebuild / extract) |
| `_system/commands/setup.md` | Step 1 Hermes terminal.env_passthrough 안내 정리 | `OLLAMA_*` 언급 제거 — namespace 격리 후 더 이상 필요 없음 |
| `_system/commands/lint.md` | Step 9 의 v7 패턴 설명 block 정리 (C3) | line 183-196 의 backend dispatch 의사코드 → 1줄 reference "graphify.md Step 2 단일 책임" |
| `docs/adr/0036-graphify-cli-integration.md` | §Note 2026-05-24 신설 | CLI v8 sync + concurrency 휴리스틱 + check-update deferred + Rollback procedure (D9) |
| **`docs/adr/0038-graphify-env-namespace-isolation.md`** (신규) | 신규 ADR (U1=b) | namespace 격리 결정의 정본 — Hermes bleed 차단 + multi-profile + Hermes trust 가정 (D10) + ADR-0036 §D2 partial supersede |
| `docs/graphify-backend-test-reference.md` | "Alternative profile examples" 섹션 추가 | 운영자가 추가 profile 등록 시 cookbook |

### 2. env namespace 설계

#### 2.1 명명 규칙

```
WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<KEY>
```

- `<PROFILE_UPPER>`: `operations.graphify_profile` (yaml) 의 uppercase. 정규식 `^[a-z][a-z0-9_]*$` (lowercase alphanum + `_`, 첫 자 letter).
- `<KEY>`: `ENDPOINT` / `API_KEY` / `MODEL` 의 셋. 셋이 한 profile 의 full bundle.

#### 2.2 profile 명 컨벤션 (운영자 권장, 강제 X)

```
<provider>_<model_hint>
```

예시: `ollama_gemma`, `opencode_minimax`, `openrouter_claude`, `claude_direct`, `local_qwen`.

#### 2.3 활성 default

```bash
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_ENDPOINT=http://127.0.0.1:11434
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_API_KEY=local-daemon     # warning 회피용 dummy
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_MODEL=gemma4:31b-cloud   # cloud-proxied via local Ollama daemon
```

yaml 정합:
```yaml
operations:
  graphify_backend: ollama
  graphify_profile: ollama_gemma
```

#### 2.4 backend → env 변수 mapping

| backend | API key env (runtime) | endpoint env (runtime) | 비고 |
|---|---|---|---|
| `ollama` | `OLLAMA_API_KEY` (없으면 dummy `local-daemon`) | `OLLAMA_HOST` 또는 `OLLAMA_BASE_URL` — endpoint pattern 으로 분기 | 양분 |
| `openai` | `OPENAI_API_KEY` | (없음) | API key only |
| `claude` | `ANTHROPIC_API_KEY` | (없음) | API key only |
| `gemini` | `GEMINI_API_KEY` | (없음) | API key only |
| `deepseek` | `DEEPSEEK_API_KEY` | (없음) | API key only |
| `kimi` | `MOONSHOT_API_KEY` (Kimi = Moonshot) | (없음) | API key only |

#### 2.5 endpoint pattern → ollama env 분기 (Q2 결정 + C1 hostname-anchored)

**v2 (C1)**: 기존 substring `*:11434*` 가 외부 URL (`api.example.com:11434/v1`) 도 우발 match → hostname-anchored prefix 로 좁힘.

```
endpoint 가 다음 prefix 중 하나로 시작:
  http://localhost:*  |  http://127.0.0.1:*  |  http://[::1]:*    → OLLAMA_HOST (native API)
그 외                                                              → OLLAMA_BASE_URL (OpenAI-compat)
```

**Edge case 처리 후 검토 결과**:
- LAN Ollama (`http://192.168.1.10:11434`) → OpenAI-compat 분기 (잘못 — 의도는 native). v0.2.x 에서 `WIKIHUB_GRAPHIFY_<P>_OLLAMA_MODE=native|compat` env override 추가 (U2=b deferred). 본 patch 에서는 localhost/loopback 만 cover, LAN 케이스는 운영자가 `WIKIHUB_GRAPHIFY_<P>_ENDPOINT=http://localhost:11434` 로 ssh tunneling 또는 OpenAI-compat 호환 wrapper 사용 권장.
- ngrok / reverse proxy → `http://` 가 아니라 `https://` 로 시작 — OpenAI-compat 분기 (대부분의 reverse proxy 가 OpenAI-compat 노출이라 정합)

#### 2.6 `--max-concurrency` 휴리스틱 (Q1 deferred — 휴리스틱만)

```
model 명에 "cloud" 부분일치                                                       → 4 (cloud-proxied, network-bound)
그 외 + endpoint 가 http://localhost:* / http://127.0.0.1:* / http://[::1]:*  → 1 (진짜 local LLM, resource-bound)
그 외 (외부 cloud endpoint)                                                       → 4 (cloud, network-bound)
```

v2 (C1): 분기 패턴이 §2.5 와 동일 hostname-anchored — coherence 유지.

### 3. graphify.md Step 2 호출 패턴 (전면 재작성, v2: C1+C2 반영)

```bash
# ─── Profile resolve ─────────────────────────────────────────────────
profile="$(yq '.operations.graphify_profile // ""' "$WIKIHUB_HOME/wikihub.yaml")"
backend="$(yq '.operations.graphify_backend // "ollama"' "$WIKIHUB_HOME/wikihub.yaml")"

# Q4 — profile 명 정규식 런타임 검증 (silent fail 회피)
if [[ ! "$profile" =~ ^[a-z][a-z0-9_]*$ ]]; then
    echo "ERROR: graphify_profile '$profile' invalid — must match ^[a-z][a-z0-9_]*$" >&2
    exit 2   # Fatal, ops-alert trigger
fi

profile_upper="$(echo "$profile" | tr '[:lower:]' '[:upper:]')"
endpoint_var="WIKIHUB_GRAPHIFY_${profile_upper}_ENDPOINT"
api_key_var="WIKIHUB_GRAPHIFY_${profile_upper}_API_KEY"
model_var="WIKIHUB_GRAPHIFY_${profile_upper}_MODEL"

# C2 — set -u 안전 indirection (ENDPOINT-less profile, 예: claude_direct)
endpoint="${!endpoint_var:-}"
api_key="${!api_key_var:-}"
model="${!model_var:-}"

# model 부재 시 fatal (env 미설정 = 운영자 실수)
if [[ -z "$model" ]]; then
    echo "ERROR: $model_var unset — env 의 profile bundle 확인" >&2
    exit 2
fi

# ─── Ollama env name 분기 — backend=ollama 일 때만 (C1+C2) ───────────
ollama_env_name=""
if [[ "$backend" == "ollama" ]]; then
    case "$endpoint" in
        http://localhost:*|http://127.0.0.1:*|http://[::1]:*) ollama_env_name="OLLAMA_HOST" ;;
        *)                                                     ollama_env_name="OLLAMA_BASE_URL" ;;
    esac
fi

# ─── concurrency 휴리스틱 (Q1 deferred, C1 hostname-anchored) ────────
case "$model" in
    *cloud*) concurrency=4 ;;
    *)
        case "$endpoint" in
            http://localhost:*|http://127.0.0.1:*|http://[::1]:*) concurrency=1 ;;
            *)                                                     concurrency=4 ;;
        esac
        ;;
esac

# ─── Mode dispatch ──────────────────────────────────────────────────
# 수동 --rebuild → graph.json 삭제 → extract (force full)
# 그 외 → extract (graphify internal cache 가 자동 incremental, timer/수동 공통)
if [[ "$1" == "--rebuild" ]]; then
    rm -f "$WIKIHUB_HOME/graphify-out/graph.json"
fi

# ─── Backend dispatch ───────────────────────────────────────────────
case "$backend" in
    ollama)
        timeout 720 env \
            "$ollama_env_name=$endpoint" \
            OLLAMA_API_KEY="${api_key:-local-daemon}" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend ollama --model "$model" \
                --max-concurrency "$concurrency" --out "$WIKIHUB_HOME"
        ;;
    openai)
        timeout 720 env OPENAI_API_KEY="$api_key" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend openai --model "$model" \
                --max-concurrency 4 --out "$WIKIHUB_HOME"
        ;;
    claude)
        timeout 720 env ANTHROPIC_API_KEY="$api_key" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend claude --model "$model" \
                --max-concurrency 4 --out "$WIKIHUB_HOME"
        ;;
    gemini)
        timeout 720 env GEMINI_API_KEY="$api_key" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend gemini --model "$model" \
                --max-concurrency 4 --out "$WIKIHUB_HOME"
        ;;
    deepseek)
        timeout 720 env DEEPSEEK_API_KEY="$api_key" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend deepseek --model "$model" \
                --max-concurrency 4 --out "$WIKIHUB_HOME"
        ;;
    kimi)
        timeout 720 env MOONSHOT_API_KEY="$api_key" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend kimi --model "$model" \
                --max-concurrency 4 --out "$WIKIHUB_HOME"
        ;;
    *)
        echo "ERROR: unknown graphify_backend '$backend' (expected: gemini|kimi|claude|openai|deepseek|ollama)" >&2
        exit 2
        ;;
esac
```

**timeout 720**: graphify `--api-timeout` default 600s + LLM 호출 N건 → 720s 가 wrapper 보호 마진. wiki 규모 증가 시 yaml expose 검토 (v0.2.x).

### 4. graphify.md Step 3 검증 갱신 (v2: A5 partial 보호)

```bash
# 결과 검증
[[ -f "$WIKIHUB_HOME/graphify-out/graph.json" ]] || { echo "graph.json 미생성" >&2; exit 1; }

# A5 — NetworkX node-link 정합 확인 + partial graph.json 보호
# jq 'keys' fail 시 graph.json 이 invalid JSON 또는 partial write — 삭제 + exit 1 (force clean)
keys="$(jq -r 'keys | join(",")' "$WIKIHUB_HOME/graphify-out/graph.json" 2>/dev/null)" || {
    echo "ERROR: graph.json invalid JSON (timeout 도중 partial write 의심) — 삭제 후 exit" >&2
    rm -f "$WIKIHUB_HOME/graphify-out/graph.json"
    exit 1
}
echo "graph.json keys: $keys"   # 예: directed,graph,hyperedges,links,multigraph,nodes

# 노드/엣지 수 (edges 는 .links 위치 — graphify 출력 메시지의 "edges" 와 JSON 위치 불일치)
nodes="$(jq -r '.nodes | length' "$WIKIHUB_HOME/graphify-out/graph.json")"
links="$(jq -r '.links | length' "$WIKIHUB_HOME/graphify-out/graph.json")"
echo "nodes=$nodes links=$links"
```

### 5a. install.sh `_migrate_graphify_env` (신규 함수)

기존 env 파일 자동 migration. legacy 키 (Hermes bleed 원인) 삭제 + Telegram 값 보존 + ollama_gemma default inject. `_migrate_agent_schema` 와 동일 정책 (PTY-safe, idempotent, backup).

#### 호출 위치

`_step5_instance_dirs` 직후. fresh install (env 파일 미존재) 은 `_step5_instance_dirs` 가 처리, 본 함수는 존재 시 migration 만.

#### Drift 정의

다음 중 하나라도 참이면 drift:
- legacy 키 잔존: `OLLAMA_BASE_URL` / `OLLAMA_API_KEY` / `OLLAMA_MODEL` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` / `GEMINI_BASE_URL` / `GEMINI_MODEL` 중 1개 이상
- `WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_ENDPOINT` / `_API_KEY` / `_MODEL` 중 1개라도 부재

#### Migration 정책

| 데이터 | 처리 |
|---|---|
| **legacy 키** (위 8 종) | **삭제** (Hermes bleed 차단 핵심) |
| **`TELEGRAM_ALERT_*`** | **값 보존** (운영자 데이터) |
| **운영자 등록 추가 profile** (`WIKIHUB_GRAPHIFY_<X>_*`, ollama_gemma 외) | **값 보존** (operator custom) |
| **`WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_*` 기존 값** | **값 보존** (ADR-0031 §Note value mutation 회피) |
| **`WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_*` 부재 키** | **default inject** (ENDPOINT=http://127.0.0.1:11434, API_KEY=local-daemon, MODEL=gemma4:31b-cloud) |
| **코멘트** | canonical template 으로 교체 (운영자 코멘트 없다고 가정 — 운영 env 는 KEY=VAL 자료만) |

#### 구현 의사코드 (bash + awk/grep, python 미사용)

```bash
_migrate_graphify_env() {
    local wh_env_file="$HOME/.config/wikihub/env"
    [[ -f "$wh_env_file" ]] || return 0   # 부재 시 _step5_instance_dirs 가 fresh template 처리

    # drift detect — legacy 잔존 OR ollama_gemma 3-키 중 1개라도 부재
    local has_legacy=0 has_endpoint=0 has_api_key=0 has_model=0
    while IFS= read -r line; do
        case "$line" in
            \#*|"") continue ;;
            OLLAMA_BASE_URL=*|OLLAMA_API_KEY=*|OLLAMA_MODEL=*) has_legacy=1 ;;
            ANTHROPIC_API_KEY=*|OPENAI_API_KEY=*)              has_legacy=1 ;;
            GEMINI_API_KEY=*|GEMINI_BASE_URL=*|GEMINI_MODEL=*) has_legacy=1 ;;
            WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_ENDPOINT=*) has_endpoint=1 ;;
            WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_API_KEY=*)  has_api_key=1 ;;
            WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_MODEL=*)    has_model=1 ;;
        esac
    done < "$wh_env_file"

    if [[ "$has_legacy" == 0 && "$has_endpoint" == 1 && "$has_api_key" == 1 && "$has_model" == 1 ]]; then
        return 0   # 이미 migrated — no-op
    fi

    info "env file drift detected — auto migration (PTY-safe, idempotent):"
    [[ "$has_legacy" == 1 ]]  && info "  - legacy graphify keys (OLLAMA_* / ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_*) → 삭제"
    [[ "$has_endpoint" == 0 ]] && info "  - WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_ENDPOINT 부재 → default inject"
    [[ "$has_api_key" == 0 ]]  && info "  - WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_API_KEY 부재 → 'local-daemon' inject"
    [[ "$has_model" == 0 ]]    && info "  - WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_MODEL 부재 → 'gemma4:31b-cloud' inject"
    info "  - 운영자 코멘트 라인은 backup 파일에서만 참조 가능 (canonical template 으로 교체)"   # A7

    # backup
    local backup="$wh_env_file.wikihub-bak.$(date -u +%Y%m%dT%H%M%SZ)"
    cp -p "$wh_env_file" "$backup"
    info "backup: $backup"

    # 보존 대상 추출 — bash assoc array 로 KEY=VAL 수집
    local tg_lines=""
    local custom_lines=""
    local og_endpoint="" og_api_key="" og_model=""
    while IFS= read -r line; do
        case "$line" in
            \#*|"") continue ;;
            TELEGRAM_ALERT_BOT_TOKEN=*|TELEGRAM_ALERT_CHAT_ID=*)
                tg_lines+="${line}"$'\n' ;;
            WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_ENDPOINT=*)
                og_endpoint="${line#WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_ENDPOINT=}" ;;
            WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_API_KEY=*)
                og_api_key="${line#WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_API_KEY=}" ;;
            WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_MODEL=*)
                og_model="${line#WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_MODEL=}" ;;
            WIKIHUB_GRAPHIFY_*=*)
                custom_lines+="${line}"$'\n' ;;
            # 그 외 legacy 키는 drop
        esac
    done < "$wh_env_file"

    # default fill (부재 시만 — 기존 값 보존)
    : "${og_endpoint:=http://127.0.0.1:11434}"
    : "${og_api_key:=local-daemon}"
    : "${og_model:=gemma4:31b-cloud}"

    # atomic write — tmp → rename
    local tmp="$wh_env_file.tmp"
    {
        cat <<EOF
# wikihub 운영 자료 — systemd unit 의 EnvironmentFile= 가 lenient 로 읽음.
# 본 파일의 자료는 graphify subprocess 호출 시 namespace 격리되어 전달 (Hermes parent leak 차단).
# 추가 profile (openrouter / openai / claude / gemini / deepseek / kimi) cookbook:
#   → docs/graphify-backend-test-reference.md §6
#
# 명명: WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL>
# yaml 의 \`operations.graphify_profile\` 와 매칭.

# === default active: ollama_gemma (Ollama daemon + gemma4:31b-cloud) ===
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_ENDPOINT=${og_endpoint}
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_API_KEY=${og_api_key}
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_MODEL=${og_model}
EOF
        if [[ -n "$custom_lines" ]]; then
            printf '\n'
            echo "# === 운영자 등록 추가 profile (operator custom — 자동 보존) ==="
            printf '%s' "$custom_lines"
        fi
        printf '\n'
        cat <<'EOF'
# === Alert channel — Telegram bot (ADR-0037 §D1) ===
# wikihub-ops-alert.service 가 fatal alert 발화 시 Telegram bot 으로 메시지 발송.
# bot 생성: @BotFather 에서 /newbot → token, chat_id 는 @userinfobot.
EOF
        if [[ -n "$tg_lines" ]]; then
            printf '%s' "$tg_lines"
        else
            cat <<'EOF'
#    TELEGRAM_ALERT_BOT_TOKEN=123456:ABC...
#    TELEGRAM_ALERT_CHAT_ID=-100123456
EOF
        fi
    } > "$tmp"
    mv "$tmp" "$wh_env_file"
    chmod 600 "$wh_env_file"

    # A6 — backup 파일 rotation (30일 이상 누적 backup 정리, install.sh `_patch_hermes_external_dirs` 패턴 추종)
    find "$wh_config_dir" -maxdepth 1 -name 'env.wikihub-bak.*' -mtime +30 -delete 2>/dev/null || true

    ok "env migration 완료 (backup: $backup)"
}
```

#### 호출 흐름

```bash
# install.sh main flow
_step5_instance_dirs       # fresh install: 새 env 파일 + chmod 600
_migrate_graphify_env      # 기존 env 파일: legacy 삭제 + Telegram 보존 + default inject
# ... 후속 step
```

`_step5_instance_dirs` 가 새 env 파일 만든 직후 호출되면 `_migrate_graphify_env` 가 drift 0 → no-op return. 멱등성 정합.

### 5b. install.sh `_migrate_agent_schema` 확장

기존 `_op_defaults` dict 에 1 항목 추가, drift detection 에 1 flag 추가, A4 — profile 명 정규식 install-time validation (non-fatal warn):

```python
# Group B detection (line ~803 부근)
if "graphify_profile" not in operations:
    flags.append("B_graphify_profile")

# A4 — 기존 graphify_profile 값의 정규식 fail-fast (install-time, non-fatal warn)
# 운영자가 yaml 편집해 invalid profile 명 (대문자/특수문자/공백) 박은 경우 install 시점 surface.
# 값 mutation 안 함 (ADR-0031 §Note 정합) — warn 만, 운영자가 직접 수정.
import re as _re
_profile = operations.get("graphify_profile")
if _profile and not _re.match(r"^[a-z][a-z0-9_]*$", str(_profile)):
    flags.append(f"W_graphify_profile_invalid:{_profile}")   # W_ prefix — Warning, non-migration
```

```python
# Group B migration (line ~897 부근)
_op_defaults = {
    "pending_alert_age_sec": 3600,
    "lint_contradiction_check": True,
    "graphify_enabled": True,
    "graphify_backend": "",
    "graphify_min_version": "0.8.0",
    "graphify_max_version": "0.99.99",
    "graphify_profile": "ollama_gemma",    # ★ 신설
}
```

```bash
# info log case 추가 (line ~836 부근)
B_graphify_profile)         info "  - [ADR-0038] operations.graphify_profile 부재 → \"ollama_gemma\" 추가" ;;
W_graphify_profile_invalid:*) warn "  - [ADR-0038] operations.graphify_profile=\"${f#W_graphify_profile_invalid:}\" 가 정규식 (^[a-z][a-z0-9_]*$) fail — 운영자 yaml 수정 권장 (자동 변경 안 함)" ;;
```

A4 의 warn 는 fail-fast (install-time surface) 이나 fatal 아님 — ADR-0031 §Note "value mutation = operator trust" 정합. 운영자가 의도적으로 invalid 값을 박은 경우 (test 상황 등) install.sh 가 자동으로 mutate 하지 않음.

`graphify_backend` default 의 변경 (`""` → `"ollama"`) 는 본 patch scope **밖**. 운영자가 명시 안 한 운영 yaml 의 backend 값 변경은 ADR-0031 §Note "value mutation = operator trust" 위반. yaml.example 의 default 만 갱신 (신규 install 대상).

### 6. install.sh env template — fresh install 만 (Q3: 단일 profile + 문서 참조)

`_step5_instance_dirs` 의 env template 전면 단순화:

```bash
cat > "$wh_env_file" <<'EOF'
# wikihub 운영 자료 — systemd unit 의 EnvironmentFile= 가 lenient 로 읽음.
# 본 파일의 자료는 graphify subprocess 호출 시 namespace 격리되어 전달 (Hermes parent leak 차단).
# 추가 profile (openrouter / openai / claude / gemini / deepseek / kimi) 예시:
#   → docs/graphify-backend-test-reference.md "Alternative profile examples" 참조
#
# 명명 컨벤션: WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL>
# yaml 의 `operations.graphify_profile` 와 매칭.

# === default active: ollama_gemma (Ollama daemon + gemma4:31b-cloud) ===
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_ENDPOINT=http://127.0.0.1:11434
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_API_KEY=local-daemon
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_MODEL=gemma4:31b-cloud

# === Alert channel — Telegram bot (ADR-0037 §D1) ===
# wikihub-ops-alert.service 가 fatal alert 발화 시 Telegram bot 으로 메시지 발송.
# bot 생성: @BotFather 에서 /newbot → token, chat_id 는 @userinfobot.
#    TELEGRAM_ALERT_BOT_TOKEN=123456:ABC...
#    TELEGRAM_ALERT_CHAT_ID=-100123456
EOF
```

### 7. wikihub.yaml.example 갱신

`operations:` 섹션 (line 34~57) 에서:

```yaml
operations:
  # ... 기존 필드 그대로 ...
  graphify_backend: ollama              # protocol — graphify CLI 의 backend (gemini|kimi|claude|openai|deepseek|ollama)
  graphify_profile: ollama_gemma        # env namespace key — env 의 WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL> 와 매칭. v0.1.7 follow-up.
  # ... 기존 필드 그대로 ...
```

기존 `graphify_backend: ""` 코멘트의 "auto-detect" 안내 제거 — 이제 명시 default 가 `ollama`. profile 신설로 endpoint/key/model 분기 책임이 env 로 이동.

### 8. setup.md Step 1 정리

기존:
> Hermes terminal.env_passthrough 안내 (ADR-0036 §Note 2026-05-20): wh-lint Step 9 의 graphify 는 hermes 의 terminal tool 로 spawn 됨. Hermes 의 tirith 가 default 로 secret env 를 subprocess 에서 strip — `~/.hermes/config.yaml` 의 `terminal.env_passthrough` 에 backend env (예: `OLLAMA_API_KEY`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`) 추가 필요.

변경:
> Hermes terminal.env_passthrough — **본 정합은 v0.1.7 follow-up 으로 불필요**. wikihub 가 `WIKIHUB_GRAPHIFY_*` namespace 로 env 를 보유 후 graphify 호출 시점에 `env <K=V> graphify ...` 로 explicit 주입 → Hermes parent 가 backend env 를 보지 않고, tirith strip 도 우회. 운영자 `terminal.env_passthrough` 편집 불필요.

### 9a. ADR-0036 §Note 2026-05-24 — CLI v8 sync + 휴리스틱 (U1 결정 후 축소)

ADR-0036 (graphify-cli-integration) 의 follow-up §Note. 본가 결정을 refine — graphify CLI v8 의 실제 동작에 wikihub 정합:

- **결정 A**: v8 CLI 정합 — `graphify extract <wiki> ...` 패턴으로 graphify.md Step 2 전면 재작성. `--update` flag (v7 era) 사용 안 함 — v8 의 `update <wiki>` 는 AST-only (code 전용) 이라 markdown wiki 부적합.
- **결정 B**: endpoint pattern 자동 분기 — `http://localhost:*` / `http://127.0.0.1:*` / `http://[::1]:*` → `OLLAMA_HOST` (native API), 그 외 → `OLLAMA_BASE_URL` (OpenAI-compat). hostname-anchored prefix 로 substring 우발 match 차단 (C1, design_review_1/2 합의).
- **결정 C**: `--max-concurrency` 휴리스틱 — `*cloud*` model 부분일치 또는 외부 endpoint → 4, 진짜 local LLM → 1. v8 --help 권장 ("default 4; set 1 for local LLMs") 정합.
- **결정 D**: graphify internal cache 가 incremental 자동 보유 → wikihub 측 추가 incremental 로직 불필요. 2-mode dispatch (수동 `--rebuild` 시 graph.json 삭제, 그 외 extract 직접).
- **결정 E**: `check-update` deferred — OCI 검증 (2026-05-24) 결과 3 시나리오 (graph.json 미존재 / extract 직후 / wiki 수정 후) 모두 `exit=0` + stdout 무음 → gate 활용 불가. graphify 본가의 notification 채널 미명세. v0.2.x 재방문.
- **결정 F**: Step 3 결과 검증에 partial graph.json 보호 — `jq 'keys'` fail 시 graph.json 삭제 + exit 1 (A5).
- **Rollback procedure** (D9): 본 §Note 끝 절 — `cp <backup> <original>` 1줄로 env + yaml 복원, systemctl restart 또는 다음 timer fire 자동 적용.

> **결정 1 (env namespace 격리)** + 결정 7 (마이그레이션) 은 **신규 ADR-0038 로 분리** (§9b) — namespace 격리는 ADR-0036 §D2 (secret layer) 의 schema-level mutation 으로 별도 decision-record weight.

### 9b. 신규 ADR-0038 — graphify-env-namespace-isolation (U1=b 결정)

`docs/adr/0038-graphify-env-namespace-isolation.md` 신설.

#### Title

`ADR-0038 — graphify env namespace isolation (WIKIHUB_GRAPHIFY_<PROFILE>_*)`

#### Status

`Accepted`. Partially supersedes ADR-0036 §D2 (single env file as secret layer).

#### Context

`~/.config/wikihub/env` 의 `OLLAMA_*` 등 표준 컨벤션 명명이 systemd `EnvironmentFile=` 경유로 Hermes parent process 에 주입 → Hermes 가 자기 LLM backend 로 인식 → `model.default` 오버라이드 (OCI 운영 2026-05-22~24 관측). graphify subprocess 만 받아야 할 자료가 leak.

#### Decision

1. **Namespace 격리**: env 파일이 `WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL>` 의 wikihub-private 키만 사용. graphify subprocess 호출 시점 (graphify.md Step 2) 에서 `env <BACKEND_ENV>=<value>` 로 explicit 주입 — Hermes parent 는 backend env (OLLAMA_*, ANTHROPIC_API_KEY 등) 를 안 봄.
2. **Profile bundle 모델**: `operations.graphify_profile: <name>` yaml 1 필드가 env 의 어떤 키 세트를 활용할지 선택. 다중 profile 동시 보유 (yaml 한 줄 swap 으로 backend 교체).
3. **Auto-migration**: 기존 env 파일의 legacy 키 (OLLAMA_*, ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_*) 는 `_migrate_graphify_env` 가 자동 삭제. Telegram 값 + 운영자 custom profile 보존. ollama_gemma default inject. `_migrate_agent_schema` 가 yaml `graphify_profile` 자동 추가.
4. **Hermes trust 가정** (D10): Hermes 는 자기 표준 env (`OLLAMA_*`, `ANTHROPIC_*`, `OPENAI_*`, `GEMINI_*`) 만 react. `WIKIHUB_GRAPHIFY_*` 는 Hermes 가 무시 (interpret 안 함, load 만 됨). 검증 방법 — `hermes` process env 에 `WIKIHUB_GRAPHIFY_*` 가 보이되 `model.default` 의 override 영향 없음을 확인.
5. **PTY-safe + idempotent + backup** (ADR-0031 §Note 정합): 모든 마이그레이션은 운영자 값 mutate 안 함. legacy 키 삭제 = schema mutation (env 변수명 자체가 schema), 운영자 값/Telegram/custom profile = value mutation 회피로 보존. backup 파일 30일 retention (A6).

#### Consequences

**Positive**:
- Hermes bleed 차단 (운영 정확성 복원)
- Multi-profile 운영 (model 비교 테스트 용이)
- ADR-0031 §Note "schema vs value mutation" 정합 — install.sh 가 schema 만 mutate, value 는 보존
- ADR-0036 §D2 의 secret layer 가 wikihub-private namespace 로 evolve — 표준 컨벤션 충돌 해소

**Negative / Trade-off**:
- 운영자 코멘트 drop (canonical template 으로 교체 — backup 에서 참조 가능)
- LAN Ollama / Docker network endpoint 분기 fragility (v0.2.x 의 `WIKIHUB_GRAPHIFY_<P>_OLLAMA_MODE` escape hatch 로 해결 deferred — U2)
- backend/profile prefix mismatch 의 silent misconfig 가능 (warn 추가 안 함 — U3, advanced 운영자의 mixed case 존중)

#### Supersedes / Partially supersedes

- ADR-0036 §D2 (API key 저장 layer) — secret layer 가 단일 file 에서 namespace bundle 로 evolve. 본질적 decision: "어디에 어떻게 저장" 의 schema 변경.

#### Related

- ADR-0031 (yaml-template-materialization) §Note: schema vs value mutation 정책
- ADR-0036 (graphify-cli-integration) §Note 2026-05-24 (CLI v8 sync)
- ADR-0037 (alert-pipeline) — Telegram env 영역 영향 없음

### 10. docs/graphify-backend-test-reference.md 보강

`§6 Alternative profile examples` 섹션 신설 (기존 §5 뒤 append):

```markdown
## 6. Alternative profile examples

본 섹션은 install.sh env template 의 default (ollama_gemma) 외 추가 profile 등록 시 cookbook.
명명 컨벤션: `WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL>`

### 6.1 OpenCode-go (OpenAI-compatible)
WIKIHUB_GRAPHIFY_OPENCODE_MINIMAX_ENDPOINT=https://opencode.ai/zen/go/v1
WIKIHUB_GRAPHIFY_OPENCODE_MINIMAX_API_KEY=sk-...
WIKIHUB_GRAPHIFY_OPENCODE_MINIMAX_MODEL=minimax-m2.5
yaml: graphify_backend: ollama / graphify_profile: opencode_minimax

### 6.2 OpenRouter
WIKIHUB_GRAPHIFY_OPENROUTER_CLAUDE_ENDPOINT=https://openrouter.ai/api/v1
WIKIHUB_GRAPHIFY_OPENROUTER_CLAUDE_API_KEY=sk-or-...
WIKIHUB_GRAPHIFY_OPENROUTER_CLAUDE_MODEL=anthropic/claude-3.5-sonnet
yaml: graphify_backend: ollama / graphify_profile: openrouter_claude

### 6.3 Anthropic 직접 (claude backend, endpoint 없음)
WIKIHUB_GRAPHIFY_CLAUDE_DIRECT_API_KEY=sk-ant-...
WIKIHUB_GRAPHIFY_CLAUDE_DIRECT_MODEL=claude-3-5-sonnet-20241022
(ENDPOINT 키 생략 — claude backend 는 표준 API endpoint hardcoded)
yaml: graphify_backend: claude / graphify_profile: claude_direct

### 6.4 OpenAI 직접
WIKIHUB_GRAPHIFY_OPENAI_GPT4_API_KEY=sk-...
WIKIHUB_GRAPHIFY_OPENAI_GPT4_MODEL=gpt-4o
yaml: graphify_backend: openai / graphify_profile: openai_gpt4

### 6.5 Gemini 직접
WIKIHUB_GRAPHIFY_GEMINI_FLASH_API_KEY=...
WIKIHUB_GRAPHIFY_GEMINI_FLASH_MODEL=gemini-2.5-flash-lite
yaml: graphify_backend: gemini / graphify_profile: gemini_flash

### 6.6 DeepSeek / Kimi 직접
WIKIHUB_GRAPHIFY_DEEPSEEK_V4_API_KEY=sk-...
WIKIHUB_GRAPHIFY_DEEPSEEK_V4_MODEL=deepseek-chat
(yaml: graphify_backend: deepseek / graphify_profile: deepseek_v4)

WIKIHUB_GRAPHIFY_KIMI_K2_API_KEY=sk-...
WIKIHUB_GRAPHIFY_KIMI_K2_MODEL=moonshot-v1-128k
(yaml: graphify_backend: kimi / graphify_profile: kimi_k2)
```

(코드블록 표현은 markdown 파일 작성 시 적절히)

---

## 개정 전/후 비교

### `~/.config/wikihub/env`

**Before** (install.sh:691~731 의 6 backend example block):
```bash
# 1. Anthropic Claude (`--backend claude`):
#    ANTHROPIC_API_KEY=sk-ant-...
# 2. OpenAI (`--backend openai`):
#    OPENAI_API_KEY=sk-...
# 3. OpenCode-go / OpenRouter / LM Studio 등 OpenAI-compatible (`--backend ollama`):
#    OLLAMA_BASE_URL=https://opencode.ai/zen/go/v1
#    OLLAMA_API_KEY=<provider key>
#    OLLAMA_MODEL=minimax-m2.5
# 4. 진짜 Ollama 로컬 (`--backend ollama`, API 비용 0):
#    OLLAMA_BASE_URL=http://localhost:11434/v1
#    OLLAMA_MODEL=qwen2.5-coder:7b
# 5. Claude Code 구독 활용 (`--backend claude-cli`, API key 불필요): ...
# 6. Google Gemini (`--backend gemini`): GEMINI_API_KEY=... GEMINI_BASE_URL=... GEMINI_MODEL=...
# === Telegram === (그대로)
```

**After**:
```bash
# wikihub 운영 자료 — namespace 격리 (Hermes leak 차단).
# 추가 profile cookbook → docs/graphify-backend-test-reference.md §6
# 명명: WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL>
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_ENDPOINT=http://127.0.0.1:11434
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_API_KEY=local-daemon
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_MODEL=gemma4:31b-cloud
# === Telegram === (그대로)
```

### `wikihub.yaml.example` operations 섹션

**Before**:
```yaml
graphify_backend: ""        # auto-detect (claude → kimi → openai → gemini → claude-cli → ollama)
```

**After**:
```yaml
graphify_backend: ollama              # protocol (gemini|kimi|claude|openai|deepseek|ollama)
graphify_profile: ollama_gemma        # env namespace key (WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_*)
```

### `_system/commands/graphify.md` Step 2

**Before** (현 35줄 분기):
```bash
backend="$(yq '.operations.graphify_backend // ""' "$WIKIHUB_HOME/wikihub.yaml")"
backend_flag=""
[[ -n "$backend" ]] && backend_flag="--backend $backend"

# 3-mode 분기
# rebuild:     timeout 300 graphify "$WIKIHUB_HOME/wiki" $backend_flag
# incremental: timeout 300 graphify "$WIKIHUB_HOME/wiki" --update $backend_flag
# first:       timeout 300 graphify "$WIKIHUB_HOME/wiki" $backend_flag
```

**After**: §3 의 의사코드 (profile resolve + endpoint/concurrency 분기 + backend case + 2-mode dispatch)

### `_system/commands/graphify.md` Step 3 결과 검증

**Before**: 노드/엣지 수 "stdout 출력" 만 명시

**After**: `jq 'keys'` + `jq '.nodes | length'` + `jq '.links | length'` 명시 (NetworkX node-link 정합)

### `_system/commands/setup.md` Step 1

**Before**: `terminal.env_passthrough` 에 `OLLAMA_API_KEY`/`OLLAMA_BASE_URL`/`OLLAMA_MODEL` 추가 안내

**After**: namespace 격리 후 불필요 — explicit `env <K=V> graphify` 주입이 tirith strip 우회

### `_system/commands/lint.md` Step 9 (v2: C3)

**Before** (line 183-196):
```markdown
**graphify 호출 형태 (ADR-0036 §Note 2026-05-20 — backend flexibility)**:

`/wh-graphify` playbook 이 yaml `operations.graphify_backend` 를 읽어 다음 형태로 graphify CLI subprocess 호출:

backend="$(yq '.operations.graphify_backend // ""' "$WIKIHUB_HOME/wikihub.yaml")"
backend_flag=""
[[ -n "$backend" ]] && backend_flag="--backend $backend"
timeout 300 graphify "$WIKIHUB_HOME/wiki" --update $backend_flag

- `--backend $backend`: yaml override (빈 문자열이면 flag 생략 → graphify auto-detect).
- `timeout 300`: graphify 가 어떤 사유로든 hang 하면 SIGTERM (exit 124). lint 본체 보호.
- exit 124 시 report 에 `graph rebuild timeout (300s, backend=$backend)` 기록 + lint 계속 (ADR-0036 §D6 정합).
```

**After**:
```markdown
**graphify 호출 형태**: graphify.md Step 2 가 단일 책임 (ADR-0006 + ADR-0038). lint.md 는 `<agent_invocation> "/wh-graphify"` 만 호출 — backend/timeout/profile dispatch 의 detail 은 graphify.md 참조.
```

Self-check (line 198-207) 는 변경 없음 — graphify-out 파일 read 기반 ratio 검증, lint-side 자료.

### `install.sh _migrate_agent_schema`

**Before**: `_op_defaults` 6 항목 (pending_alert_age_sec / lint_contradiction_check / graphify_enabled / graphify_backend / graphify_min_version / graphify_max_version)

**After**: + `graphify_profile: "ollama_gemma"` (7 항목)

---

## 연계 룰/스킬 정합성 검토

| 대상 | 영향 | 결과 |
|---|---|---|
| **ADR-0031** (yaml-template-materialization) | `_migrate_agent_schema` 가 `graphify_profile` 자동 추가 — schema mutation. 값 mutation 안 함 (default 만, 기존 값 보존) | 정합 — §Note 2026-05-22 의 "schema mutation = install.sh 책임" 원칙 정합 |
| **ADR-0032** (hermes-skill-registration) | systemd unit 의 `EnvironmentFile=` 그대로 — env 변수명만 변경. Hermes config.yaml 변경 없음 | 정합 |
| **ADR-0036** (graphify-cli-integration) | 본 patch 의 정본 변경 대상 — §Note 2026-05-24 로 결정 추출 | 정합 — Original decision 의 evolution |
| **ADR-0037** (alert-pipeline-architecture) | Telegram env 영역 변경 없음 (`TELEGRAM_ALERT_*` 유지) | 정합 |
| `_system/commands/lint.md` Step 9 | **C3 — line 183-196 의 v7 패턴 설명 block (`backend_flag` + `timeout 300` + `--update`) 을 1줄 reference 로 축소** | 본 patch 흡수 — graphify.md Step 2 단일 source 정합 (ADR-0006). 실제 호출 `<agent_invocation> "/wh-graphify"` 는 그대로 (line 176). |
| `_system/commands/setup.md` Step 1 | terminal.env_passthrough 안내 정리 | 본 patch 가 수정 |
| `_system/systemd/lint.service.template` | `EnvironmentFile=-%h/.config/wikihub/env` 그대로 — env 파일 위치 + lenient prefix 유지 | 정합 (env 내부 변수명만 변경) |
| `_system/systemd/ops-alert.service` | Telegram 환경 유지 — 변경 없음 | 정합 |
| `_system/systemd/wikihub-vault@.service.template` | EnvironmentFile= 미참조 — wh-ingest 가 graphify 호출 안 함. 영향 없음 | 정합 |

---

## 배포 Gap window 분석 (v2: D8)

`install.sh --update` 가 일으키는 상태 변경:

1. `_migrate_agent_schema` 가 yaml 의 `graphify_profile` 자동 추가 (또는 invalid value warn)
2. `_migrate_graphify_env` 가 env 파일 rewrite (legacy 삭제 + namespace inject)
3. `_materialize_skills` 가 `~/.hermes/skills/wh-graphify/SKILL.md` 갱신 (새 Step 2 코드 반영)
4. systemd unit 정의 변경 없음 → `daemon-reload` 불필요

### gap window 의미

- **install.sh 가 env 파일 rewrite 하는 동안 service 가 graphify 호출 중**: race window 거의 0. systemd `EnvironmentFile=-%h/.config/wikihub/env` semantics 는 **service start 시점 1회 read** — running service 는 이미 env 를 받았음. install.sh 가 file 을 rewrite 해도 running service 는 영향 없음.
- **install.sh 후 다음 timer fire**: 새 oneshot service instance start → `EnvironmentFile=` 가 새 env 파일 read → 새 namespace 적용. 동시에 새 SKILL.md (Step 2 코드) 가 Hermes 로 load 됨. 정합.
- **수동 호출 (`/wh-graphify`)**: install.sh 후 즉시 새 코드 + 새 env 동시 적용.

### 명시적 race window = 0

systemd EnvironmentFile= 의 service-start-time semantics + atomic file rewrite (`mv tmp file`) 으로 race window 0. 운영자가 `install.sh --update` 도중 graphify 가 호출되는 시나리오에서도:
- 호출 시점 ≤ install.sh start: graphify 이미 old env 받음. install.sh 가 file rewrite 해도 그 호출은 old 상태로 완료. **Safe**.
- 호출 시점 > install.sh end: new env 로 동작. **Safe**.
- install.sh 시간 동안: graphify subprocess 이미 받은 env 로 진행, file 의 inode 가 new file 로 swap 되는 mv 는 in-memory env 에 영향 없음. **Safe**.

### 권장 운영 (실 race window 0 이나 즉시 검증 원하는 경우)

```bash
sudo -u <wikihub_user> systemctl --user restart wikihub-lint.service
# 또는 다음 timer fire 자동 적용 — 최대 lint_interval_hours (default 3h) 대기
```

---

## Rollback Procedure (v2: D9)

`install.sh --update` 후 문제 발생 시 운영자가 즉시 되돌리는 절차. ADR-0036 §Note 2026-05-24 + ADR-0038 양쪽에서 cross-link.

### 단계

```bash
# 1. backup 위치 확인
ls -la ~/.config/wikihub/env.wikihub-bak.*
ls -la ~/wikihub/wikihub.yaml.wikihub-bak.*

# 2. env 복원 (legacy 키 + 기존 운영자 코멘트 복원)
cp ~/.config/wikihub/env.wikihub-bak.<utc_iso> ~/.config/wikihub/env
chmod 600 ~/.config/wikihub/env   # 권한 보장

# 3. yaml 복원 (graphify_profile 제거)
cp ~/wikihub/wikihub.yaml.wikihub-bak.<utc_iso> ~/wikihub/wikihub.yaml

# 4. (선택) 즉시 적용 — 다음 timer fire 도 자동 적용
sudo -u <wikihub_user> systemctl --user restart wikihub-lint.service

# 5. install.sh 재실행 금지 — drift detect 가 다시 migration 시도
#    (재실행 필요 시 위 backup 파일 절대 경로 보존 + 미리 cp 백업)
```

### 주의

- backup 파일은 `.wikihub-bak.<utc_iso>` 형식 (`A6` rotation: 30일 이상 누적 자동 삭제). 30일 이내 복원 필요.
- yaml 의 `graphify_profile` 복원은 새 schema 와 호환 안 됨 — graphify.md Step 2 가 profile 부재 시 fatal (정규식 fail). rollback 시 graphify 호출 자체가 fail — 운영자가 yaml 도 함께 복원 필수.
- service restart 가 즉시 적용 — 다음 timer fire 까지 대기해도 자동.

---

## 미결 사항

**없음** — plan.md 의 Q1~Q6 + review 의 U1/U2/U3 모두 확정 (v2).

---

## Definition of Done

### 코드 정합

- [ ] `~/.config/wikihub/env` template (fresh install) 이 `WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_*` + Telegram 만 포함.
- [ ] `_migrate_graphify_env` 가 기존 OCI env 파일에서 legacy 키 삭제 + Telegram 값 보존 + ollama_gemma default inject. backup 생성 (`.wikihub-bak.<utc>`). 두번째 호출 시 no-op (idempotent). **A6 — 30일 이상 누적 backup 자동 삭제**. **A7 — 코멘트 drop info 메시지**.
- [ ] `install.sh _migrate_agent_schema` 의 Group B detection + migration + info log 에 `graphify_profile` 추가. 기존 운영 yaml 의 `graphify_profile` 부재 → `"ollama_gemma"` 자동 추가 + idempotent. **A4 — invalid profile 값 install-time warn (non-fatal)**.
- [ ] `wikihub.yaml.example` 의 `operations.graphify_backend` default = `"ollama"`, `graphify_profile` = `"ollama_gemma"` 신설. 코멘트가 "protocol" vs "endpoint+key+model bundle" 의미 분리 명시.
- [ ] `_system/commands/graphify.md` Step 2 가 §3 의사코드와 정합 — profile 검증 (Q4) + **C1 hostname-anchored endpoint 분기 + C2 set -u 안전 indirection + backend=ollama guard** + concurrency 휴리스틱 + backend case (6 종) + 2-mode dispatch.
- [ ] `_system/commands/graphify.md` Step 3 가 `.links` 검증 + `jq 'keys'` 명시 + **A5 partial graph.json 보호 (jq fail → delete + exit 1)**.
- [ ] `_system/commands/setup.md` Step 1 에서 `OLLAMA_*` terminal.env_passthrough 안내 제거 — namespace 격리 후 불필요 명시.
- [ ] **C3 — `_system/commands/lint.md` Step 9 의 line 183-196 v7 패턴 설명 block 정리 — 1줄 reference "graphify.md Step 2 단일 책임" 으로 축소**. 실제 호출 line 176 `<agent_invocation> "/wh-graphify"` 유지.
- [ ] `docs/adr/0036-graphify-cli-integration.md` §Note 2026-05-24 (결정 A~F + Rollback procedure) 신설.
- [ ] **`docs/adr/0038-graphify-env-namespace-isolation.md` 신설** — namespace 격리 + multi-profile + auto-migration + Hermes trust 가정 (D10) + ADR-0036 §D2 partial supersede.
- [ ] `docs/graphify-backend-test-reference.md` §6 Alternative profile examples 추가 (6 profile cookbook).
- [ ] **analysis_and_design.md 의 Gap window 분석 (D8) + Rollback procedure (D9) 절이 ADR-0036 §Note 및 ADR-0038 에 cross-link 됨**.

### 운영 검증 (OCI 배포 후)

- [ ] OCI 운영 env 파일이 `install.sh --update` 1회로 자동 migration — legacy 키 0건 + Telegram 값 유지 + ollama_gemma 3 키 박힘.
- [ ] Hermes parent process 가 `OLLAMA_*` / `ANTHROPIC_API_KEY` 등 raw env 를 안 봄 (`hermes` ENV 검사 또는 logging).
- [ ] `wh-graphify --rebuild` 호출 시 graph.json 삭제 + extract 정상 동작 (gemma4:31b-cloud, max-concurrency=4 자동 적용).
- [ ] `wh-lint` Step 9 의 자동 graphify 호출 정상 (extract 만, gate 없음).
- [ ] `graph.json` 의 `.links` 위치에 edges 존재 + `jq 'keys'` 가 NetworkX node-link key set 반환.
- [ ] alternative profile (opencode_minimax 등) 수동 등록 후 yaml `graphify_profile` 한 줄 swap → 정상 동작.

### 거버넌스

- [ ] v0.1.7 commit 누적 (VERSION 미변경, tag 재발급 X).
- [ ] HISTORY.md 항목 추가 — Step 5 (Deployment) 완료 시.
- [ ] feature 종료 처리 — Step 5 후 `features/archive/20260524_graphify_profile_namespace/` 로 이동.
