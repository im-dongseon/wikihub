#!/usr/bin/env bash
# wikihub_graphify.sh — graphify CLI 호출 정본 (ADR-0036 §D6 single-source)
#
# v0.1.8 update_path_fixes (D3=B): graphify hermes skill 폐기 → wikihub-graphify.service 격상.
# 본 script 가 graphify CLI 호출 + backend dispatch + 결과 검증 정본.
#
# 호출자:
# 1. wikihub-graphify.service ExecStart (lint Step 9 가 systemctl --user start trigger)
# 2. 메인테이너 manual: systemctl --user start wikihub-graphify.service
# 3. 직접 실행 (테스트 / debug): WIKIHUB_HOME=... WIKIHUB_YAML=... ./scripts/wikihub_graphify.sh [--rebuild]
#
# ADR-0036: graphify CLI integration (PyPI graphifyy)
# ADR-0038: env namespace isolation (WIKIHUB_GRAPHIFY_<PROFILE>_*)
set -euo pipefail

: "${WIKIHUB_HOME:?WIKIHUB_HOME unset}"
: "${WIKIHUB_YAML:?WIKIHUB_YAML unset}"

GRAPHIFY_STATE_DIR="${WIKIHUB_HOME}/_state/_graphify"

_write_graphify_failure() {
  local reason="$1"
  local remediation="${2:-}"
  mkdir -p "$GRAPHIFY_STATE_DIR"
  local now
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  (
    flock -w 5 200
    failed_count=1
    first_failed_at="$now"
    if [[ -f "$GRAPHIFY_STATE_DIR/last_failure.json" ]]; then
      failed_count=$(python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
print(d.get(\"failed_count\",0)+1)
" "$GRAPHIFY_STATE_DIR/last_failure.json" 2>/dev/null || echo 1)
      first_failed_at=$(python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
print(d.get(\"first_failed_at\", sys.argv[2]))
" "$GRAPHIFY_STATE_DIR/last_failure.json" "$now" 2>/dev/null || echo "$now")
    fi
    cat > "$GRAPHIFY_STATE_DIR/last_failure.json" <<EOF
{
  "vault_id": "_graphify",
  "severity": "fatal",
  "scope": "graphify",
  "reason": "${reason}",
  "remediation": "${remediation}",
  "exit_code": 2,
  "source_id": null,
  "first_failed_at": "${first_failed_at}",
  "last_failed_at": "${now}",
  "failed_count": ${failed_count},
  "alerted_at": null,
  "alerted_failed_count": null
}
EOF
  ) 200>"$GRAPHIFY_STATE_DIR/.last_failure.lock"
}

# Step 1. graphify CLI 존재 확인
if ! command -v graphify >/dev/null; then
    echo "ERROR: graphify CLI 미설치 — install.sh 재실행 또는 'pip install graphifyy>=0.8.0,<1.0.0'" >&2
    _write_graphify_failure "graphify CLI 미설치" "pip install graphify 또는 PATH 확인"
    exit 2
fi

# Step 2. yaml read + profile resolve (ADR-0038 namespace 격리)
profile="$(yq '.operations.graphify_profile // ""' "$WIKIHUB_YAML")"
backend="$(yq '.operations.graphify_backend // "ollama"' "$WIKIHUB_YAML")"
timeout_sec="$(yq '.operations.graphify_timeout_sec // 900' "$WIKIHUB_YAML")"

# profile 명 정규식 검증 (silent fail 회피, ADR-0038 §Decision 2)
if [[ ! "$profile" =~ ^[a-z][a-z0-9_]*$ ]]; then
    echo "ERROR: graphify_profile '$profile' invalid — must match ^[a-z][a-z0-9_]*\$" >&2
    _write_graphify_failure "graphify_profile 형식 불일치: ${profile}" "profile 이름은 ^[a-z][a-z0-9_]*$ 패턴이어야 함"
    exit 2
fi

# env profile bundle resolve (set -u 안전)
profile_upper="$(echo "$profile" | tr '[:lower:]' '[:upper:]')"
endpoint_var="WIKIHUB_GRAPHIFY_${profile_upper}_ENDPOINT"
api_key_var="WIKIHUB_GRAPHIFY_${profile_upper}_API_KEY"
model_var="WIKIHUB_GRAPHIFY_${profile_upper}_MODEL"
endpoint="${!endpoint_var:-}"
api_key="${!api_key_var:-}"
model="${!model_var:-}"

if [[ -z "$model" ]]; then
    echo "ERROR: $model_var unset — ~/.config/wikihub/env 의 profile bundle 확인" >&2
    _write_graphify_failure "환경변수 ${model_var} 미설정" "wikihub.yaml의 graphify.<profile>.model 확인"
    exit 2
fi

# ollama endpoint pattern → env name 분기 (loopback vs OpenAI-compat proxy)
ollama_env_name=""
if [[ "$backend" == "ollama" ]]; then
    # bash case 의 [::1] 은 POSIX char class 로 parse → \[::1\] escape (lint_operations C1)
    case "$endpoint" in
        http://localhost:*|http://127.0.0.1:*|http://\[::1\]:*) ollama_env_name="OLLAMA_HOST" ;;
        *)                                                       ollama_env_name="OLLAMA_BASE_URL" ;;
    esac
fi

# concurrency 휴리스틱 (v8 graphify --help: "default 4; set 1 for local LLMs")
concurrency=4
case "$model" in
    *cloud*) concurrency=4 ;;
    *)
        case "$endpoint" in
            http://localhost:*|http://127.0.0.1:*|http://\[::1\]:*) concurrency=1 ;;
            *)                                                       concurrency=4 ;;
        esac
        ;;
esac

# --rebuild 분기 (수동 force full rebuild — graphify cache 가 자동 incremental 아님 detect 시)
# ${1:-} — set -u 안전
if [[ "${1:-}" == "--rebuild" ]]; then
    rm -f "$WIKIHUB_HOME/graphify-out/graph.json"
fi

# Step 3. backend dispatch (graphify.md v0.1.7 spec 정합 — 6 case)
case "$backend" in
    ollama)
        timeout "$timeout_sec" env \
            "$ollama_env_name=$endpoint" \
            OLLAMA_API_KEY="${api_key:-local-daemon}" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend ollama --model "$model" \
                --max-concurrency "$concurrency" --out "$WIKIHUB_HOME"
        ;;
    openai)
        timeout "$timeout_sec" env OPENAI_API_KEY="$api_key" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend openai --model "$model" \
                --max-concurrency 4 --out "$WIKIHUB_HOME"
        ;;
    claude)
        timeout "$timeout_sec" env ANTHROPIC_API_KEY="$api_key" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend claude --model "$model" \
                --max-concurrency 4 --out "$WIKIHUB_HOME"
        ;;
    gemini)
        timeout "$timeout_sec" env GEMINI_API_KEY="$api_key" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend gemini --model "$model" \
                --max-concurrency 4 --out "$WIKIHUB_HOME"
        ;;
    deepseek)
        timeout "$timeout_sec" env DEEPSEEK_API_KEY="$api_key" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend deepseek --model "$model" \
                --max-concurrency 4 --out "$WIKIHUB_HOME"
        ;;
    kimi)
        timeout "$timeout_sec" env MOONSHOT_API_KEY="$api_key" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend kimi --model "$model" \
                --max-concurrency 4 --out "$WIKIHUB_HOME"
        ;;
    *)
        echo "ERROR: unknown graphify_backend '$backend' (expected: gemini|kimi|claude|openai|deepseek|ollama)" >&2
        _write_graphify_failure "알 수 없는 graphify_backend: ${backend}" "gemini|kimi|claude|openai|deepseek|ollama 중 하나여야 함"
        exit 2
        ;;
esac

# Step 4. 결과 검증 + partial failure 가드 (graphify.md v0.1.7 Step 3 정합)
if [[ ! -f "$WIKIHUB_HOME/graphify-out/graph.json" ]]; then
    echo "ERROR: graph.json 미생성" >&2
    exit 1
fi

# JSON validity check (timeout 도중 partial write 보호)
if ! keys="$(jq -r 'keys | join(",")' "$WIKIHUB_HOME/graphify-out/graph.json" 2>/dev/null)"; then
    echo "ERROR: graph.json invalid JSON (timeout 도중 partial write 의심) — 삭제 후 exit" >&2
    rm -f "$WIKIHUB_HOME/graphify-out/graph.json"
    exit 1
fi

# partial failure 가드 (ADR-0036 §재검토 트리거 — Pass 3 silent partial failure)
N="$(jq -r '.nodes | length' "$WIKIHUB_HOME/graphify-out/graph.json")"
M="$(find "$WIKIHUB_HOME/wiki" -name '*.md' -not -path '*/_lint/*' -not -path '*/_state/*' 2>/dev/null | wc -l)"
threshold="$(yq '.operations.graphify_partial_failure_threshold // 0.5' "$WIKIHUB_YAML")"

if [[ "$M" -gt 0 ]]; then
    if awk "BEGIN {exit !($N / $M < $threshold)}"; then
        echo "WARNING: graphify partial failure 의심: N=$N, M=$M, ratio=$(awk "BEGIN {print $N/$M}")" >&2
        # ops-alert trigger 는 BL 등록 (본 fix scope 외 — 단순 stderr warn 만)
    fi
fi

echo "graph rebuilt: $N nodes, $M docs" >&2

# Step 5. cache cleanup — 입력 경로 아래 graphify-out/cache side effect 제거 (lint→graphify 무한 루프 방지)
rm -rf "$WIKIHUB_HOME/wiki/graphify-out"
rm -f "$GRAPHIFY_STATE_DIR/last_failure.json"

exit 0
