# Plan — graphify profile namespace + CLI v8 정합 (v0.1.7 follow-up)

> v0.1.7 유지 — VERSION 파일 미변경. 이전 graphify.md backend fix 가 v0.1.6 유지한 패턴 정합 (CLAUDE.md §8 Atomic Change).

## 1. 배경

- **bug**: `~/.config/wikihub/env` 의 `OLLAMA_*` 가 systemd `EnvironmentFile=` 로 Hermes parent process 에도 주입 → Hermes 가 자기 LLM backend 로 인식 → `model.default` 오버라이드. graphify subprocess 만 받아야 할 env 가 leak.
- **drift**: graphify v8 의 실제 CLI (`graphify extract <wiki> --backend X --model Y --max-concurrency N --out DIR`) 와 graphify.md Step 2 의 호출 패턴 (`graphify <wiki> [--update] $backend_flag`) 어긋남. `docs/graphify-backend-test-reference.md` (2026-05-23 검증) 가 ground truth.
- **profile 다중 보유 요구**: opencode / openrouter / local Ollama 등 여러 backend·endpoint·model 묶음을 동시 보유하고 yaml 한 줄로 swap 하는 운영 시나리오.

## 2. 작업 분류

- 분류: **운영 정합 + 버그 fix** (Hermes env bleed + graphify CLI v8 sync)
- 버전: **v0.1.7 유지** (VERSION 파일 미변경, follow-up commit 누적)
- Feature ID: `graphify_profile_namespace`
- 디렉토리: `features/20260524_graphify_profile_namespace/`

## 3. 적용 단계 선언

| Step | 수행 여부 | 사유 |
|---|---|---|
| Step 1 Plan | 본 파일 | 가벼움 |
| Step 2 Analysis & Design | 수행 | 다중 backend × profile namespace × endpoint pattern 자동 분기 → 설계 명세 필수 |
| Step 4 Review | **수행** | install.sh + graphify.md + ADR + 신규 docs 동시 변경 (다파일 + 외부 인터페이스 변경 = env var 이름) |
| Step 5 Deployment | **수행** | `_system/` 변경 + install.sh 변경 → 운영 동기화 필요 |

메소드론 적용: 예 (trivial 미수준 — env 컨벤션 break + CLI 패턴 갱신).

## 4. 예상 영향 범위

| 파일 | 변경 성격 |
|---|---|
| `install.sh` `_step5_instance_dirs` | env template 전면 갱신 (`WIKIHUB_GRAPHIFY_*_*` namespace, 6~7 profile 예시) |
| `install.sh` `_migrate_agent_schema` | `operations.graphify_profile` 자동 추가 (default `ollama_gemma`) |
| `wikihub.yaml.example` | `operations.graphify_profile` 필드 신설 + 코멘트, 기존 `graphify_backend` 코멘트 갱신 |
| `_system/commands/graphify.md` | Step 2 전면 재작성 (v8 `extract` subcommand + profile resolve + endpoint pattern 분기 + concurrency 휴리스틱), Step 3 결과 검증 절차 갱신 (`.links`), 증분 빌드 절차 폐기 |
| `_system/commands/setup.md` | Step 1 Hermes terminal.env_passthrough 안내에서 `OLLAMA_*` 언급 제거 (이제 wikihub 가 namespace 격리) |
| `docs/adr/0036-graphify-cli-integration.md` | §Note 2026-05-24 신설 — namespace 격리 + v8 CLI 정합 + endpoint/model pattern 분기 |
| `docs/graphify-backend-test-reference.md` | 이미 이동 완료 (Downloads → docs), graphify.md cross-link 만 추가 |

## 5. 핵심 설계 요지 (analysis_and_design.md 로 확장)

### env namespace

```bash
# ~/.config/wikihub/env
# 기본 active
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_ENDPOINT=http://127.0.0.1:11434
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_API_KEY=local-daemon       # dummy (warning suppression)
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_MODEL=gemma4:31b-cloud

# 사전 등록 alternative profile (yaml 한 줄로 swap)
WIKIHUB_GRAPHIFY_OPENCODE_MINIMAX_ENDPOINT=https://opencode.ai/zen/go/v1
WIKIHUB_GRAPHIFY_OPENCODE_MINIMAX_API_KEY=sk-...
WIKIHUB_GRAPHIFY_OPENCODE_MINIMAX_MODEL=minimax-m2.5

WIKIHUB_GRAPHIFY_OPENROUTER_CLAUDE_ENDPOINT=https://openrouter.ai/api/v1
WIKIHUB_GRAPHIFY_OPENROUTER_CLAUDE_API_KEY=sk-or-...
WIKIHUB_GRAPHIFY_OPENROUTER_CLAUDE_MODEL=anthropic/claude-3.5-sonnet

# Telegram alert (unchanged — bleed 없음)
TELEGRAM_ALERT_BOT_TOKEN=...
TELEGRAM_ALERT_CHAT_ID=...
```

### yaml schema

```yaml
operations:
  graphify_backend: ollama              # v8 backends: gemini|kimi|claude|openai|deepseek|ollama
  graphify_profile: ollama_gemma        # ★ 신설 — env namespace key
```

### graphify.md Step 2 핵심 분기

```bash
profile="$(yq '.operations.graphify_profile' "$yaml")"
profile_upper="$(echo "$profile" | tr '[:lower:]' '[:upper:]')"
endpoint="$(eval echo \$WIKIHUB_GRAPHIFY_${profile_upper}_ENDPOINT)"
api_key="$(eval echo \$WIKIHUB_GRAPHIFY_${profile_upper}_API_KEY)"
model="$(eval echo \$WIKIHUB_GRAPHIFY_${profile_upper}_MODEL)"

# env var 분기 — daemon 위치 (endpoint)
case "$endpoint" in
  *localhost*|*127.0.0.1*) ollama_env_name="OLLAMA_HOST" ;;
  *)                       ollama_env_name="OLLAMA_BASE_URL" ;;
esac

# concurrency 분기 — 실 model 위치 (suffix)
case "$model" in
  *cloud*)
    concurrency=4 ;;                              # cloud-proxied
  *)
    case "$endpoint" in
      *localhost*|*127.0.0.1*) concurrency=1 ;;   # 진짜 local LLM
      *)                       concurrency=4 ;;   # 외부 cloud
    esac
    ;;
esac

case "$backend" in
  ollama)
    env "$ollama_env_name=$endpoint" OLLAMA_API_KEY="${api_key:-local-daemon}" \
      timeout 720 graphify extract "$WIKIHUB_HOME/wiki" \
        --backend ollama --model "$model" \
        --max-concurrency "$concurrency" --out "$WIKIHUB_HOME" ;;
  openai)
    env OPENAI_API_KEY="$api_key" \
      timeout 720 graphify extract "$WIKIHUB_HOME/wiki" \
        --backend openai --model "$model" \
        --max-concurrency 4 --out "$WIKIHUB_HOME" ;;
  claude)
    env ANTHROPIC_API_KEY="$api_key" \
      timeout 720 graphify extract "$WIKIHUB_HOME/wiki" \
        --backend claude --model "$model" \
        --max-concurrency 4 --out "$WIKIHUB_HOME" ;;
  gemini)
    env GEMINI_API_KEY="$api_key" \
      timeout 720 graphify extract "$WIKIHUB_HOME/wiki" \
        --backend gemini --model "$model" \
        --max-concurrency 4 --out "$WIKIHUB_HOME" ;;
  deepseek)
    env DEEPSEEK_API_KEY="$api_key" \
      timeout 720 graphify extract "$WIKIHUB_HOME/wiki" \
        --backend deepseek --model "$model" \
        --max-concurrency 4 --out "$WIKIHUB_HOME" ;;
  kimi)
    env MOONSHOT_API_KEY="$api_key" \
      timeout 720 graphify extract "$WIKIHUB_HOME/wiki" \
        --backend kimi --model "$model" \
        --max-concurrency 4 --out "$WIKIHUB_HOME" ;;
esac
```

### 증분 빌드 — v8 메커니즘으로 재매핑 (폐기 아님)

graphify v8 의 incremental 능력은 `extract` 자체에 internal cache 로 내장. 외부 `--update` flag 불필요.

- **수동 `--rebuild`**: `graphify-out/graph.json` 삭제 후 `extract` (force full)
- **수동 일반 호출 + timer 호출 공통**: `extract` 그대로 (graphify 가 graph.json 있으면 자동 incremental — unchanged 노드 보존, LLM cost 0)

`update <wiki>` subcommand 는 AST-only (code 전용) → markdown wiki 부적합 → 사용 안 함.

`check-update <wiki>` gate 는 본 patch 에서 **활용 불가** (OCI 검증 2026-05-24: 3 시나리오 모두 exit=0 + stdout 무음 → 본가의 notification 채널 미명세). v0.2.x 에서 graphify 본가 spec 명확해지면 재방문.

### 마이그레이션

- 기존 OLLAMA_*= 운영자가 직접 삭제 (D9(b) — 자동 변환 안 함)
- `_migrate_agent_schema` 는 yaml 의 `graphify_profile` 만 자동 추가 (default `ollama_gemma`)
- 운영자 책임 안내: `setup.md` Step 1 에서 env template 비교 + 수동 채우기 권장

## 6. 미결 사항 (Step 2 에서 결정)

| ID | 항목 | 옵션 |
|---|---|---|
| Q1 | `graphify_concurrency` yaml expose 시점 | (a) v0.1.7 deferred ★ (b) 본 patch 에 포함 |
| Q2 | endpoint pattern 분기 robust 보강 | (a) localhost/127 substring 만 (b) `:11434` port 도 추가 (c) yaml `graphify_ollama_mode: native\|compat` 명시 hint |
| Q3 | install.sh env template 의 profile 예시 개수 | (a) 4개 (ollama_gemma + opencode_minimax + openrouter_claude + claude_direct) ★ (b) 6개 (위 + openai_gpt4 + deepseek_v4) (c) 1개만 + README 안내 |
| Q4 | profile 명 컨벤션 enforce | (a) 자유 ★ (b) `<provider>_<model_hint>` regex |
| Q5 | `check-update` gate 활성화 시점 | **(c) v0.1.7 deferred** — OCI 검증 결과 (2026-05-24) check-update 가 모든 상태 exit=0 + 무음 → gate 불가. graphify internal cache 가 incremental 자동 보유로 동등 효과 |
| Q6 | `check-update` 출력 파싱 정밀도 | **무효** — Q5 deferred 결정으로 본 patch scope 제거 |

## 7. Definition of Done

- [ ] `WIKIHUB_GRAPHIFY_<PROFILE>_*` namespace 채택, `OLLAMA_*` / `ANTHROPIC_API_KEY` 등 raw env 가 systemd EnvironmentFile= 경유로는 더 이상 안 나감
- [ ] graphify.md Step 2 가 v8 `extract` 패턴 + `--out $WIKIHUB_HOME` + `--max-concurrency` 자동 분기 정합
- [ ] graphify.md Step 2 가 incremental 2-mode 분기 정합: 수동 `--rebuild` (graph.json 삭제 → extract), 그 외 (extract — graphify internal cache 가 자동 incremental, timer/수동 동일 경로)
- [ ] graphify.md Step 3 검증 명령이 `.links` 사용 (NetworkX node-link 정합)
- [ ] `install.sh _migrate_agent_schema` 가 기존 yaml 에 `operations.graphify_profile: ollama_gemma` 자동 추가 + idempotent
- [ ] install.sh env template 이 새 namespace + dummy api_key 가이드 포함
- [ ] ADR-0036 §Note 2026-05-24 신설 (namespace 격리 + v8 CLI sync + endpoint/model pattern 분기 결정 근거)
- [ ] `docs/graphify-backend-test-reference.md` 가 graphify.md 와 cross-link
- [ ] OCI 운영 환경에서 (a) Hermes 가 OLLAMA_* 안 봄 (b) graphify extract 가 새 패턴으로 동작 (c) `.links` 출력 검증
- [ ] v0.1.7 commit 누적 (tag 재발급 X)
