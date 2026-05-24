# /wh-graphify

`graphify` CLI로 wiki 지식 그래프를 빌드한다. `graphify-out/graph.json` + `GRAPH_REPORT.md` 생성. `/wh-query`·`/wh-lint`의 1차 검색·진단 자원.

## 호출

```
<agent_invocation> "/wh-graphify"          # 증분 빌드 (graph.json 있으면 update, 없으면 최초 빌드)
<agent_invocation> "/wh-graphify --rebuild" # 강제 전체 재빌드
```

- **트리거 (주, 자동)**: `/wh-lint` 종료 시 자동 호출 (lint playbook의 마지막 Step) — 하루 1회 자연 갱신
- **트리거 (보조, 수동)**: 메인테이너가 graph 즉시 갱신 필요 시 직접 호출
- **vault-agnostic**: wiki/ 전체를 입력으로 받음

## 사전 조건

- `graphify` CLI 실행 가능 — install.sh `_install_graphify` 가 `$VENV_PATH/bin/pip install "graphifyy>=0.8.0,<1.0.0"` 으로 venv 에 설치 (PyPI 패키지 `graphifyy`, 2 y; ADR-0036)
- `wiki/` 디렉토리 존재 (페이지 0개여도 OK — 빈 그래프 생성)
- `instance.root`/`graphify-out/` 쓰기 권한
- `~/.config/wikihub/env` 의 active profile bundle 채워짐 (ADR-0038 v0.1.7 follow-up — namespace 격리). yaml `operations.graphify_profile` 이 가리키는 env keyset (`WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL>`) 가 graphify subprocess 호출 시점에 backend-native env (OLLAMA_HOST/ANTHROPIC_API_KEY 등) 로 explicit 변환 주입 → Hermes parent leak 차단. Hermes `terminal.env_passthrough` 정합 불필요 (explicit `env <K=V> graphify` 가 tirith strip 우회). 추가 profile cookbook → `docs/graphify-backend-test-reference.md` §6.

## 절차

### Step 1. graphify CLI 사전 확인

```bash
command -v graphify >/dev/null
```

- 없음 → "graphify 미설치 — install.sh 재실행 안내" + exit 2 (Fatal, ops-alert)
  - PyPI 패키지: `graphifyy` (2 y; ADR-0036). CLI 명령: `graphify`. install.sh `_install_graphify` 가 venv 에 설치.
- 있음 → 버전 확인:
  ```bash
  graphify --version
  ```
  버전이 `operations.graphify_min_version` (default `0.8.0`, ADR-0036; v0.1.0 documentation only — 실 enforce 는 v0.2.x) 미만: stderr 경고 + 진행. GRAPH_REPORT.md 없으면 wiki/index.md 폴백 (ADR-0005)

### Step 2. Profile resolve + backend dispatch (v0.1.7 follow-up — ADR-0038 + ADR-0036 §Note 2026-05-24)

**Profile resolve (env namespace 격리)**:

```bash
profile="$(yq '.operations.graphify_profile // ""' "$WIKIHUB_HOME/wikihub.yaml")"
backend="$(yq '.operations.graphify_backend // "ollama"' "$WIKIHUB_HOME/wikihub.yaml")"

# profile 명 정규식 런타임 검증 (silent fail 회피, ADR-0038 §Decision 2)
if [[ ! "$profile" =~ ^[a-z][a-z0-9_]*$ ]]; then
    echo "ERROR: graphify_profile '$profile' invalid — must match ^[a-z][a-z0-9_]*$" >&2
    exit 2   # Fatal, ops-alert trigger
fi

# env 의 profile bundle 해소 (set -u 안전)
profile_upper="$(echo "$profile" | tr '[:lower:]' '[:upper:]')"
endpoint_var="WIKIHUB_GRAPHIFY_${profile_upper}_ENDPOINT"
api_key_var="WIKIHUB_GRAPHIFY_${profile_upper}_API_KEY"
model_var="WIKIHUB_GRAPHIFY_${profile_upper}_MODEL"
endpoint="${!endpoint_var:-}"   # ENDPOINT-less profile (claude_direct 등) 안전
api_key="${!api_key_var:-}"
model="${!model_var:-}"

[[ -z "$model" ]] && { echo "ERROR: $model_var unset — env 의 profile bundle 확인" >&2; exit 2; }
```

**endpoint pattern → Ollama env 분기** (backend=ollama 일 때만):

```bash
ollama_env_name=""
if [[ "$backend" == "ollama" ]]; then
    # bash case: [::1] 은 POSIX character class 로 parse → \[::1\] escape 필수 (code review 1 §C1)
    case "$endpoint" in
        http://localhost:*|http://127.0.0.1:*|http://\[::1\]:*) ollama_env_name="OLLAMA_HOST" ;;   # native API
        *)                                                       ollama_env_name="OLLAMA_BASE_URL" ;;   # OpenAI-compat
    esac
fi
```

- loopback hostname (localhost/127.0.0.1/[::1]) → `OLLAMA_HOST` (Ollama native API)
- 그 외 (OpenCode/OpenRouter/LM Studio 등) → `OLLAMA_BASE_URL` (OpenAI-compat client)
- LAN Ollama (`http://192.168.x.x:11434`) 같은 edge case 는 v0.2.x 의 override env 로 deferred (ADR-0038 §부정/제약)

**`--max-concurrency` 휴리스틱** (v8 `--help` 권장: "default 4; set 1 for local LLMs"):

```bash
case "$model" in
    *cloud*) concurrency=4 ;;                           # cloud-proxied (network-bound)
    *)
        case "$endpoint" in
            http://localhost:*|http://127.0.0.1:*|http://\[::1\]:*) concurrency=1 ;;   # 진짜 local LLM (C1 escape)
            *)                                                       concurrency=4 ;;
        esac
        ;;
esac
```

**Mode dispatch** (v8 의 internal cache 가 자동 incremental — ADR-0036 §Note 2026-05-24 결정 D):

```bash
# 수동 --rebuild → graph.json 삭제 후 extract (force full)
# 그 외 (timer + 수동 일반) → extract 그대로 (graphify cache 가 자동 incremental)
# ${1:-} — 인자 없는 호출 시 set -u 안전 (code review 1 §C2)
if [[ "${1:-}" == "--rebuild" ]]; then
    rm -f "$WIKIHUB_HOME/graphify-out/graph.json"
fi
```

**Backend dispatch** (`env <BACKEND_ENV>=<value>` 로 explicit 주입 — Hermes parent leak 차단):

```bash
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

- `timeout 720`: graphify 의 `--api-timeout` default 600s + LLM 호출 누적 대비 wrapper 보호 margin. yaml expose 는 v0.2.x deferred.
- `${api_key:-local-daemon}`: local Ollama 의 `OLLAMA_API_KEY` warning 회피 dummy (test reference §3 검증).
- `--out "$WIKIHUB_HOME"` → graphify 가 `$WIKIHUB_HOME/graphify-out/` 에 graph.json + GRAPH_REPORT.md 생성.

> wiki/ 경로는 `instance.root`/wiki 기준 (`$WIKIHUB_HOME/wiki`, ADR-0034). 메타 디렉토리 제외는 `wiki/.graphifyignore` 파일이 책임 (gitignore 문법; ADR-0036 §D3) — install.sh 또는 wh-setup 가 default template 배치 (`_lint/`, `_state/` 제외). 운영자가 vault 별 추가 패턴 직접 편집 가능.

### Step 3. 결과 검증 (v0.1.7 follow-up — A5 partial 보호)

```bash
[[ -f "$WIKIHUB_HOME/graphify-out/graph.json" ]] || { echo "graph.json 미생성" >&2; exit 1; }

# NetworkX node-link 정합 확인 + partial graph.json 보호 (test reference §1)
# jq 'keys' fail 시 invalid JSON / partial write (timeout kill 등) → 삭제 + exit 1 (force clean)
keys="$(jq -r 'keys | join(",")' "$WIKIHUB_HOME/graphify-out/graph.json" 2>/dev/null)" || {
    echo "ERROR: graph.json invalid JSON (timeout 도중 partial write 의심) — 삭제 후 exit" >&2
    rm -f "$WIKIHUB_HOME/graphify-out/graph.json"
    exit 1
}
echo "graph.json keys: $keys"   # 예: directed,graph,hyperedges,links,multigraph,nodes

# 노드 수 + edges 수 (edges 는 .links 위치 — graphify 출력 메시지의 "edges" 와 JSON 위치 불일치, test reference §1)
nodes="$(jq -r '.nodes | length' "$WIKIHUB_HOME/graphify-out/graph.json")"
links="$(jq -r '.links | length' "$WIKIHUB_HOME/graphify-out/graph.json")"
echo "nodes=$nodes links=$links"
```

- `graphify-out/graph.json` 존재 + 유효 JSON (jq parse OK)
- `graphify-out/GRAPH_REPORT.md` 존재 (없으면 graphify 버전 노후 경고)
- 노드 수·엣지 수 stdout 출력 (edges = `.links` field)

### Step 4. (트리거가 /wh-lint인 경우) lint report에 통합

- lint playbook이 본 명령을 호출한 경우, graphify 결과를 lint report에 추가 — lint.md Step 8 참조
- 수동 호출 시 lint report 만지지 않음

## 출력 산출물

| 대상 | 조건 |
|---|---|
| `graphify-out/graph.json` | 매 호출 (증분 또는 재빌드) |
| `graphify-out/GRAPH_REPORT.md` | graphify 최신 버전 사용 시 |
| `wiki/` | 본 명령은 wiki 자체 만지지 않음 (read-only) |
| systemd journal | 빌드 사이클 (agent runtime) |

## 실패 처리

| 실패 시점 | 동작 |
|---|---|
| graphify 미설치 | exit 2 (Fatal) + ops-alert |
| graphify 빌드 자체 실패 (wiki/ 권한 등) | exit 1 + stderr 상세 |
| graphify-out/ 쓰기 실패 (disk full) | exit 1 + ops-alert |
| 증분 빌드 실패 → fallback | stderr 경고 + `--rebuild` 전체 재시도 1회 (이것도 실패 시 exit 1) |

## 멱등성

- 같은 wiki 상태에 대해 N회 빌드 → graph.json **structural** 동등.
  - Pass 1 (Tree-sitter code analysis) deterministic — 같은 입력 → 같은 syntax tree.
  - Pass 3 (LLM semantic extraction) **non-deterministic** (temperature / sampling, ADR-0036 §D4). graphify 내부 cache (graph.json 보존) 가 증분 단계에서 unchanged 노드는 보존 → cycle 간 churn 부분 완화. 노드 메타데이터의 minor drift 는 operational normal (panic 아님).
- 증분 빌드는 stale graph.json도 안전히 갱신.
- `--rebuild`는 항상 전체 재계산 = always 정합 (Pass 3 churn 포함).

## 자동 호출 흐름 (lint와 통합)

```
/wh-lint (timer, 하루 1회)
   ├─ Step 1~7: wiki 점검·정비
   ├─ Step 8: lint report 작성
   └─ Step 9 (추가): subprocess → /wh-graphify 자동 호출
            ├─ 성공 → lint report에 "graph rebuilt: N nodes, M edges" 추가
            └─ 실패 → lint report에 "graph rebuild failed" + ops-alert
```

본 통합은 lint.md Step 9에 명시 (lint playbook 갱신 필요 — F2 작성 중 reflection).

## 관련 ADR

- ADR-0005 wiki/index.md vs graphify 관계 (graphify는 1차, index는 폴백)
- ADR-0006 unified orchestration (본 명령도 lint 사이클의 일부로 자동 호출)
- ADR-0008 lint 권한 — graphify는 비파괴 (graphify-out만 만지므로 자동 OK)
- ADR-0036 graphify CLI 통합 — PyPI 패키지 `graphifyy` + Pass 3 non-deterministic 가정 + `.graphifyignore` 정책 + 운영 비용 모델
- ADR-0036 §Note 2026-05-24 — v8 CLI sync (extract subcommand + endpoint pattern + concurrency 휴리스틱 + check-update deferred + Rollback procedure)
- **ADR-0038** graphify env namespace isolation — `WIKIHUB_GRAPHIFY_<PROFILE>_*` + multi-profile bundle + auto-migration (`install.sh _migrate_graphify_env`) + Hermes trust 가정
