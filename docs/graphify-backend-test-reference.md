# 260523 graphify Backend Test Reference

> **Purpose**: graphify backend 시험에서 검증된 사실 기록 — 다른 backend (deepseek/gemini/claude 등) 적용 시 재사용
> **Validated**: 2026-05-23, OCI VM Ubuntu 24.04 ARM
> **Tool**: graphify v8 (`~/.local/share/wikihub/venv/bin/graphify`)

---

## 1. JSON 응답 구조 — Markdown fence 처리

### 검증 사실

**graphify 가 markdown fence 를 자체 처리함**. LLM 응답이 ``` 로 감싸져 있어도 `graph.json` 에는 깨끗한 JSON 으로 저장.

### 시험 데이터

LLM raw 응답 (단발 API 호출):
```json
{
  "content": "```json\n{\"entities\": [...]}\n```"
}
```

graphify 거친 후 `graph.json`:
```bash
jq 'keys' graph.json
# ["directed", "graph", "hyperedges", "links", "multigraph", "nodes"]
```

NetworkX node-link format. Edge 는 `.edges` 가 아니라 **`.links`** 에 저장됨 (graphify 출력 메시지는 "edges" 라고 표현해도 JSON 표준 위치는 `.links`).

### 적용 시 확인 사항

다른 backend 로 swap 시:
- `jq 'keys' graph.json` 으로 구조 유지 확인
- `jq '.links | length'` 로 edge 개수 확인 (graphify 출력 메시지의 edges count 와 일치해야 함)
- `graphify path <A> <B> --graph graph.json` 로 traversal 동작 확인

---

## 2. Thinking Mode

### 검증 사실 (gemma4:31b-cloud)

| 호출 방식 | Default 동작 | 의미 |
|---|---|---|
| `ollama run <model> "..."` (CLI) | thinking **enabled** | "Thinking..." trace 출력됨 |
| API + `"think": false` | thinking **disabled** | trace 없음, `content` 만 |
| API + `"think": true` 또는 생략 | thinking **enabled** | trace 가 `thinking` field 에 |

### 정량 비교 (같은 짧은 prompt)

| Mode | Total duration | Eval tokens | 비고 |
|---|---|---|---|
| Enabled | 669ms | 40 (trace 포함) | trace 가 응답 길이 차지 |
| Disabled | 491ms | 2 (답변만) | 짧음, 빠름 |

→ Extraction task 같은 structured output 에 thinking disabled 권장 (DeepSeek 공식 가이드 일치).

### Backend 별 thinking control 형식

확인된 것:
- **Ollama (모델 무관)**: API 의 `think: true/false` boolean parameter
- **Gemma 4 내부**: `<|think|>` system prompt token (Ollama 가 자동 wrapping)

미확인 (적용 시 검증 필요):
- DeepSeek native API: `extra_body={"thinking": {"type": "disabled"}}` (검색 결과 기반, 미시험)
- Gemini: thinking budget parameter 별도 (Gemini 2.5 의 thinking control)
- Claude: extended thinking 별도 parameter

### 적용 시 확인 명령

```bash
# CLI level
ollama run <model>:cloud --think=false "Reply with: ok"

# API level
curl http://localhost:11434/api/chat -d '{
  "model": "<model>:cloud",
  "messages": [{"role": "user", "content": "..."}],
  "think": false,
  "stream": false
}'
```

응답에 `thinking` field 비어있거나 부재면 disabled 동작 확정.

---

## 3. Warning 회피

### 검증된 Warning

graphify ollama backend 호출 시:

```
WARNING: ollama backend selected with no OLLAMA_API_KEY set; 
sending corpus to http://localhost:11434/v1. 
Set OLLAMA_API_KEY (any non-empty value) to suppress this warning.
```

### 원인

- Ollama daemon 자체는 API key 검증 안 함 (localhost)
- graphify 의 ollama backend wrapper 가 `OLLAMA_API_KEY` unset 을 보고 보안 warning 출력
- "any non-empty value" 면 warning 사라짐

### 회피 방법

graphify 호출 시 환경변수:
```bash
OLLAMA_API_KEY=<any-non-empty-string>
```

값은 무엇이든 무관 (Ollama daemon 이 무시). 의미적으로 명확한 dummy 권장:
- `OLLAMA_API_KEY=local-daemon` 
- `OLLAMA_API_KEY=graphify-dummy`
- `OLLAMA_API_KEY=not-required` 

### 다른 backend 의 동등 warning

미검증이나 패턴 유사할 가능성:
- `--backend deepseek` + DEEPSEEK_API_KEY unset → warning 또는 error
- `--backend gemini` + GEMINI_API_KEY unset → 동일
- `--backend openai` + OPENAI_API_KEY unset → 동일

각 backend 적용 시 처음 호출에서 warning 메시지 확인하고 동등 회피.

---

## 4. JSON 입력 (Ollama API 호출 패턴)

### 검증된 호출 형식

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "gemma4:31b-cloud",
  "messages": [
    {"role": "system", "content": "You are a JSON-only API. Never use markdown formatting. Never wrap responses in code blocks. Output raw JSON starting with { and ending with }."},
    {"role": "user", "content": "<task with explicit format spec>"}
  ],
  "think": false,
  "format": "json",
  "stream": false
}'
```

### 발견 — Markdown fence 회피 조건

- ❌ `format: "json"` 만 → fence 끼어듦 (Ollama Issue #15595, Gemma 4 알려진 버그)
- ❌ system prompt 만 + 빈 user content → fence 없으나 task 안 함
- ✅ **system prompt + format + 명확한 user task** → fence 없는 깨끗한 JSON

이건 **단발 API 호출** 검증. graphify 가 자체적으로 system prompt 를 어떻게 구성하는지는 graphify 내부 로직.

### 적용 시 확인

graphify 가 다른 backend (deepseek/gemini 등) 사용 시 markdown fence 발생 여부:
- 실제 시험 후 `graph.json` 구조 검증 (`jq 'keys'`)
- 응답에 fence 가 끼면 graphify 의 backend wrapper 가 후처리 하는지 확인 필요

---

## 5. 검증된 시험 환경 (재현용)

### 명령

```bash
env -i \
  HOME="$HOME" \
  PATH="$PATH" \
  USER="$USER" \
  TERM="$TERM" \
  OLLAMA_HOST="http://127.0.0.1:11434" \
  OLLAMA_API_KEY="local-daemon" \
  ~/.local/share/wikihub/venv/bin/graphify extract <wiki-path> \
    --backend ollama \
    --model gemma4:31b-cloud \
    --max-concurrency 1 \
    --out <output-dir>
```

### 결과 (3 docs subset)

- 6 nodes, 4 edges (links), 2 communities
- 716 input tokens, 1110 output tokens
- 비용 $0.00 (Free tier)
- 실행 fail 없음, JSON 유효

### 정리

```bash
rm -rf <output-dir>
```

env -i 격리라 production 영향 0. 시험 디렉토리 삭제로 완전 정리.

---

## 6. Alternative profile examples (v0.1.7 follow-up — namespace 격리, ADR-0038)

본 섹션은 install.sh env template 의 default (`ollama_gemma`) 외 추가 profile 등록 시 cookbook.

**명명 컨벤션**: `WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL>`
**Profile 명 규칙**: `^[a-z][a-z0-9_]*$` (lowercase alphanum + `_`, 첫 자 letter). 권장 패턴 `<provider>_<model_hint>`.
**yaml 매칭**: `operations.graphify_profile` 값이 env prefix (lowercase) 와 1:1.

### 6.1 OpenCode-go (OpenAI-compat)

env:
```
WIKIHUB_GRAPHIFY_OPENCODE_MINIMAX_ENDPOINT=https://opencode.ai/zen/go/v1
WIKIHUB_GRAPHIFY_OPENCODE_MINIMAX_API_KEY=sk-...
WIKIHUB_GRAPHIFY_OPENCODE_MINIMAX_MODEL=minimax-m2.5
```
yaml:
```yaml
operations:
  graphify_backend: ollama
  graphify_profile: opencode_minimax
```
endpoint 패턴 (`*.opencode.ai/v1`) → `OLLAMA_BASE_URL` 분기 (OpenAI-compat). concurrency 4 (외부 cloud).

### 6.2 OpenRouter

env:
```
WIKIHUB_GRAPHIFY_OPENROUTER_CLAUDE_ENDPOINT=https://openrouter.ai/api/v1
WIKIHUB_GRAPHIFY_OPENROUTER_CLAUDE_API_KEY=sk-or-...
WIKIHUB_GRAPHIFY_OPENROUTER_CLAUDE_MODEL=anthropic/claude-3.5-sonnet
```
yaml:
```yaml
operations:
  graphify_backend: ollama
  graphify_profile: openrouter_claude
```

### 6.3 Anthropic 직접 (claude backend, endpoint 없음)

env (ENDPOINT 키 생략 — claude backend 는 표준 API endpoint hardcoded):
```
WIKIHUB_GRAPHIFY_CLAUDE_DIRECT_API_KEY=sk-ant-...
WIKIHUB_GRAPHIFY_CLAUDE_DIRECT_MODEL=claude-3-5-sonnet-20241022
```
yaml:
```yaml
operations:
  graphify_backend: claude
  graphify_profile: claude_direct
```
graphify.md Step 2 가 `backend=ollama` 가 아닐 때 endpoint 분기 skip → ENDPOINT 키 부재 OK.

### 6.4 OpenAI 직접

env:
```
WIKIHUB_GRAPHIFY_OPENAI_GPT4_API_KEY=sk-...
WIKIHUB_GRAPHIFY_OPENAI_GPT4_MODEL=gpt-4o
```
yaml:
```yaml
operations:
  graphify_backend: openai
  graphify_profile: openai_gpt4
```

### 6.5 Gemini 직접

env (graphify Pass 3 의 content 필드 직접 파싱 → non-reasoning flash-lite 계열 필수):
```
WIKIHUB_GRAPHIFY_GEMINI_FLASH_API_KEY=...
WIKIHUB_GRAPHIFY_GEMINI_FLASH_MODEL=gemini-2.5-flash-lite
```
yaml:
```yaml
operations:
  graphify_backend: gemini
  graphify_profile: gemini_flash
```

### 6.6 DeepSeek / Kimi 직접

env (DeepSeek):
```
WIKIHUB_GRAPHIFY_DEEPSEEK_V4_API_KEY=sk-...
WIKIHUB_GRAPHIFY_DEEPSEEK_V4_MODEL=deepseek-chat
```
yaml:
```yaml
operations:
  graphify_backend: deepseek
  graphify_profile: deepseek_v4
```

env (Kimi = Moonshot):
```
WIKIHUB_GRAPHIFY_KIMI_K2_API_KEY=sk-...
WIKIHUB_GRAPHIFY_KIMI_K2_MODEL=moonshot-v1-128k
```
yaml:
```yaml
operations:
  graphify_backend: kimi
  graphify_profile: kimi_k2
```

### 6.7 운영자 추가 시 절차

1. env 파일에 `WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_*` 3 키 (또는 API key only backend 의 경우 2 키) 추가
2. yaml `operations.graphify_profile` 을 신규 profile 명으로 변경 + `graphify_backend` 도 정합
3. `systemctl --user restart wikihub-lint.service` 또는 다음 timer fire 자동 적용
4. `journalctl --user -u wikihub-lint.service` 로 호출 검증

