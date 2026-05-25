# ADR-0036: graphify CLI 통합 — PyPI 의존성 + API key 자료 layer + non-deterministic Pass 3 가정

- **Status**: Accepted
- **Date**: 2026-05-19
- **Feature**: features/archive/20260519_graphify_integration
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

`_system/commands/graphify.md` (F2 시점 작성) 은 `graphify` 라는 CLI 가 wikihub 의 wiki 지식 그래프를 빌드한다고 가정 + L31/L36/L50/L83 의 4항목을 "F4 install.sh 구현 시점에 확정" 으로 잠정 표시. 2026-05-19 검토 — graphify.net 의 graphify CLI (PyPI `graphifyy`) 가 정확히 이 가정과 매칭 (출력 디렉토리 `graphify-out/`, 파일 `graph.json` + `GRAPH_REPORT.md` + `graph.html`, CLI `graphify <path>` build / `graphify <path> --update` incremental).

격차 — install.sh 가 실제로 graphify CLI 를 설치하는 plumbing 부재. wh-lint Step 9 의 chain 호출 (`<agent_invocation> "/wh-graphify"`) 가 `command -v graphify` false → exit 2 Fatal → ops-alert 매 사이클 발화 결함. v0.1.0 미배포라 surface 안 됐을 뿐.

추가 — graphify 3-pass 의 Pass 3 (Claude/OpenAI subagent semantic extraction) 가 LLM 호출 → API key 자료 + 비용 모델 + non-deterministic output 이라는 3가지 새 운영 제약 surface.

## Considered Options

### O1. PyPI 패키지 선택

- **(α1) `graphifyy` (graphify.net 공식)**: 2 y 패키지명. MIT. NetworkX + Tree-sitter 의존.
- (β1) self-host 대안 (`graphify-dotnet` 등 .NET port): wikihub 의 Python venv 구조와 정합 약함.
- (γ1) wikihub 자체 graph builder 구현: cost 과대, 본 ADR 의 목적 벗어남.

### O2. API key 자료 layer

- **(α2) `~/.config/wikihub/env` + systemd `EnvironmentFile=`** : 새 파일, KEY=VALUE 형식.
- (β2) 운영자 shell rc (`.bashrc` export) + systemd `PassEnvironment=` : systemd --user manager env 가 운영자 shell env 와 분리돼 미작동 가능.
- (γ2) 별도 credentials 파일 (rclone.conf 패턴): rclone 의 OAuth token 과 LLM API key 는 의미 다름. 별도 layer 가 정합.

### O3. graphify install (Claude Code hook) 통합

- (α3) install.sh 가 `graphify install` 도 호출 → wikihub agent (Hermes) 가 보유 안 한 PreToolUse hook 충돌 가능.
- **(β3) hook 통합 skip — PyPI 설치만 수행**: hermes 가 graphify 를 subprocess 로 호출 — hook 의존 0.

### O4. .graphifyignore 정책

- **(α4) wiki root 단일 `.graphifyignore`** : graphify 의 표준 — repo root 1개로 subfolder 호출 시에도 정합.
- (β4) wikihub 의 메타 디렉토리 (`_lint/`, `_state/`) underscore-prefix 자동 제외 — graphify 가 보장 안 함. 명시 ignore 가 안전.

### O5. non-deterministic Pass 3 의 멱등성 해석

- (α5) graphify deterministic 으로 가정 — graphify.md L83 의 기존 표현. **부정확** (Pass 3 LLM).
- **(β5) Tree-sitter Pass 1 만 deterministic, Pass 3 churn 가능성 인지** — graphify 내부 cache (graph.json 보존) 가 증분 단계에서 변경되지 않은 노드는 보존하므로 cycle 간 churn 부분 완화 — operational 으로 acceptable.

### O6. 운영 비용 모델

- (α6) wikihub 가 token-budget 제어 — `operations.graphify.token_budget` 등 schema 추가.
- **(β6) graphify CLI default + wh-lint timer 주기 통제** : `operations.lint_interval_hours` (default 24h) 가 자연 cost upper bound. v0.1.0 minimum viable. 후속 schema 확장은 v0.2.x 검토 트리거.

## Decision

**채택**: (α1) `graphifyy` PyPI + (α2) `~/.config/wikihub/env` EnvironmentFile + (β3) hook skip + (α4) wiki root `.graphifyignore` + (β5) Pass 3 churn 인지 + (β6) timer 주기 통제.

### 구체적 결정

#### D1. PyPI 패키지 + 버전 pinning

- 패키지: `graphifyy` (PyPI), CLI: `graphify`. install.sh `_install_graphify` 함수가 `$VENV_PATH/bin/pip install "graphifyy>=0.8.0,<1.0.0"` 수행.
- `wikihub.yaml.operations.graphify_min_version` / `graphify_max_version` schema 추가 — v0.1.0 은 documentation only (rclone min/max 와 동일 — 실제 enforce 는 v0.2.x).
- `INSTALLED_VERSIONS.json` 에 graphify key 추가 — `_write_installed_versions_sidecar` 의 출력 schema 갱신.

#### D2. API key 저장 — `~/.config/wikihub/env` (EnvironmentFile)

- 새 파일: `~/.config/wikihub/env` — systemd `EnvironmentFile=` 호환 형식 (KEY=VALUE per line, no quoting).
- install.sh `_step5_instance_dirs` 가 `~/.config/wikihub/` 디렉토리 (chmod 700) + `env` 파일 (chmod 600, 미존재 시 빈 template) ensure.
- 운영자가 1회 수동으로 `ANTHROPIC_API_KEY=sk-ant-...` 채움. wikihub 시스템은 자동 입력 안 함 (secret material).
- systemd `_system/systemd/lint.service.template` 에 `EnvironmentFile=-%h/.config/wikihub/env` (lenient `-` prefix — 부재 시 unit start fail 안 함).
- hermes 가 호출하는 graphify subprocess 는 자연스럽게 lint.service env 상속.
- default env var name: `ANTHROPIC_API_KEY` (wikihub agent = Hermes/Claude 정합).
- yaml `operations.graphify_api_key_env_name` 으로 override (e.g. `OPENAI_API_KEY` — graphify CLI 가 다중 backend 수용).

#### D3. `.graphifyignore` 정책 — wiki root 배치

- `wiki/.graphifyignore` 파일을 install.sh `_step5_instance_dirs` 또는 wh-setup playbook 의 wiki/ ensure 단계가 배치 (template literal 또는 separate file).
- default 제외:
  ```
  # wikihub 메타 디렉토리 — graphify 분석 대상 아님 (ADR-0036)
  _lint/
  _state/
  ```
- `sources/` 는 vault mirror — graphify 가 vault content 와 wiki page 를 함께 분석 정합 → 제외 안 함. 운영자가 vault 별 ignore 패턴 필요 시 본 파일에 직접 추가.

#### D4. Pass 3 non-deterministic 가정

- `commands/graphify.md` L83 의 "graphify deterministic 가정" 표현 §Note 보강 — Pass 1 (Tree-sitter) deterministic, Pass 3 (LLM) non-deterministic.
- graphify 내부 cache (graph.json) 가 증분 단계에서 unchanged 노드 보존 → cycle 간 churn 부분 완화.
- wh-lint Step 9 의 보고 (`graph rebuilt: N nodes, M edges`) 가 cycle 간 drift 시 panic 아님 — operational normal.
- 멱등성 spec 갱신: 같은 wiki 상태 N회 호출 시 graph.json **structural** 동등 (LLM-driven 노드 메타데이터 minor drift 허용).

#### D5. graphify install (Claude Code hook) skip

- install.sh `_install_graphify` 는 PyPI 설치 + version check 만. `graphify install` 호출 안 함.
- 사유: wikihub agent (Hermes) 가 graphify 를 subprocess 로 호출 — hook 의존 0. Claude Code 용 PreToolUse hook 은 wikihub 컨텍스트 무관.

#### D6. 운영 비용 — wh-lint timer 주기 + 운영자 자체 cost 인지

- v0.1.0 default: graphify CLI default backend (Anthropic) + 기본 token-budget.
- wikihub 의 호출 빈도 통제: `operations.lint_interval_hours` (default 24h) — wh-lint timer fire 시점만 graphify chain. 24h 1회 호출이 default cost upper bound.
- install.sh `_step8_guide` + setup.md 에 cost 환기 메시지 추가.
- graphify-side token-budget / backend 제어 schema (`operations.graphify.token_budget`, `operations.graphify.backend`) 는 v0.2.x 검토 트리거.

## Consequences

### 긍정

- wh-lint Step 9 chain 의 graphify Fatal 결함 해소 — `command -v graphify` true.
- API key 자료 위치 명확화 + chmod 600 + EnvironmentFile lenient prefix 로 운영자 미입력 상태에서도 lint unit start 자체는 성공 (graphify 호출만 fail).
- `_system/commands/graphify.md` 의 잠정 4항목 모두 확정.
- graphify 의 3-pass 아키텍처 + .graphifyignore + Pass 3 churn 인지가 wikihub 의 명시 spec 으로 lift.

### 부정 / 제약

- PyPI 의존성 추가 (`graphifyy`) — install.sh 의 supply chain surface 확장. rclone 의 SHA256 검증 vs PyPI 의 hash-based pip install (pip 자체의 PEP 658 + hashes 의존). install.sh 가 추가로 hash pin 옵션 검토는 v0.2.x.
- API key 자료 신규 layer (`~/.config/wikihub/env`) — ADR-0035 가 폐기한 `~/.credentials/wikihub/` (SA JSON) 와 별도 경로. 보안 자료 layer 가 2개로 분리 (rclone.conf 의 OAuth + 본 env 파일의 LLM key) — 단일 layer 통합 검토는 v0.2.x.
- graphify Pass 3 가 운영자 별도 API 비용 발생 — 운영자 인지 책임. token-budget / backend 통제 schema 부재 (v0.1.0).
- wh-lint timer 가 graphify Fatal 을 cycle 단위로 surface 가능 — 운영자가 ops-alert 받고 API key 채우는 흐름. setup.md / install.sh `_step8_guide` 안내.

### 후속 영향

- `_system/commands/graphify.md` 의 잠정 4항목 확정 — L18/L31, L36, L44/L47, L50, L83.
- `_system/commands/setup.md` Step 0 entry condition 에 `~/.config/wikihub/env` 존재 (API key 채워졌는지 *확인 안 함* — 운영자 책임) 안내.
- `wikihub.yaml.example` 의 `operations.*` 에 graphify 관련 3 필드 추가.
- `_system/systemd/lint.service.template` 의 `EnvironmentFile=` 추가.
- install.sh INSTALLED_VERSIONS.json schema 갱신 (graphify key).
- v0.1.0 의 graphify Pass 3 churn 운영 데이터 surface 시 D4 의 cycle 간 drift 허용 범위 재검토 트리거.
- v0.2.x 검토 트리거: graphify-side token-budget / backend 통제 schema (`operations.graphify.*`), PyPI hash pin 옵션, secret material layer 통합.
- 2026-05-25: `lint_operations_improvements` (v0.1.8) 가 graphify timeout wrapper 의 yaml expose 작업 완료. `graphify.md` Step 2 의 6 위치 hard-coded `timeout 720` 가 `timeout "$timeout_sec"` 로 변경 (yaml `operations.graphify_timeout_sec` 정본, default 900s = 15분). 운영자 backend 별 조정 가능. graphify.md:156 의 "yaml expose 는 v0.2.x deferred" 코멘트 폐기 처리.

### 재검토 트리거

- graphify Pass 3 cycle 간 graph.json drift 가 wh-lint 보고에서 운영적 불편 surface 시 → D4 churn 허용 범위 또는 token-budget schema 도입.
- LLM cost 가 운영자 base 의 부담으로 surface 시 → backend=ollama 등 local LLM 옵션 yaml schema 격상.
- graphifyy 의 hash / supply chain 사고 발생 시 → install.sh hash pin enforce (rclone SHA256 패턴 차용).

## Cross-references

- **연계 정합**: ADR-0005 (wiki/index.md fallback) — graphify primary 본문 그대로, §Note 추가 (도구 정해짐). ADR-0023 (install.sh distribution) — graphify install.sh 책임 §Note 추가. ADR-0024 (fatal alert) — graphify 실패 → ops-alert 경로 동일. ADR-0032 (agent invocation) — hermes invocation 본문 무관.
- **비교 / 분리**: ADR-0035 (rclone OAuth) — `~/.config/rclone/rclone.conf` 가 OAuth credentials, 본 ADR 의 `~/.config/wikihub/env` 가 LLM API key — 경로/책임 모두 별개.
- **본 ADR 의 분석 정본**: [features/archive/20260519_graphify_integration/analysis_and_design.md](../../features/archive/20260519_graphify_integration/analysis_and_design.md)
- **2026-05-19 검토 자료**: graphify.net / GitHub safishamsi/graphify (MIT) — pypi.org/project/graphifyy

## Note (2026-05-20, feature `graphify_backend_flexibility`) — §D2 backend lock 해제

### 발견

§D2 가 default backend = Anthropic Claude (`ANTHROPIC_API_KEY`) 로 lock. OCI 운영자가 별도 Anthropic key 발급 의사 없음 + Hermes 측에 OpenCode-go (`https://opencode.ai/zen/go/v1`) API key 가 이미 설정 — backend 선택 layer 보강 필요. (운영 모델 = `minimax-m2.5` — reasoning 모델 아닌 fast-response 모델 채택, 2026-05-20 갱신. 초기 검토 시점 `deepseek-v4-pro` 였으나 reasoning lock.acquire() hang 결함으로 변경.)

graphify CLI source 검증 (`graphifyy 0.8.13/llm.py:64-71, 287`):
- `ollama` backend 의 base_url 은 `os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")` — runtime env 로 override.
- client init: `OpenAI(api_key=api_key, base_url=base_url, ...)` — 표준 OpenAI Python SDK.
- 즉 `ollama` backend = **"OpenAI-compatible endpoint generic client"** (이름은 misleading).

→ OpenCode-go / OpenRouter / LM Studio / Together / Fireworks / Anyscale 등 OpenAI-compatible 한 모든 endpoint 가 `--backend ollama` 로 사용 가능. `OLLAMA_BASE_URL` + `OLLAMA_API_KEY` + `OLLAMA_MODEL` 조합.

### §D2 갱신

**Before** (§D2 본문): API key 저장 — `~/.config/wikihub/env` (EnvironmentFile), default env var name `ANTHROPIC_API_KEY`, yaml `operations.graphify_api_key_env_name` 로 override.

**After**:

- yaml schema 변경: `graphify_api_key_env_name` 폐기 (backend 별 env 가 다양해 단일 필드 미적합). 신설: `operations.graphify_backend` (catalog: `""` auto-detect | `claude` | `claude-cli` | `openai` | `gemini` | `kimi` | `deepseek` | `ollama` | `bedrock`).
- `~/.config/wikihub/env` 는 그대로 (systemd `EnvironmentFile=-` 패턴 유지). 내용은 backend 별 자유 — install.sh 가 template 으로 5종 예시 (Anthropic / OpenAI / OpenCode-go via ollama / Ollama local / claude-cli) 표기.
- lint Step 9 의 graphify 호출이 yaml `graphify_backend` 읽어 `--backend $value` 명시 전달. 빈 값이면 flag 생략 → graphify auto-detect (claude → kimi → openai → gemini → claude-cli → ollama 순).

### Hermes env_passthrough 정합 (operational)

wh-lint Step 9 의 graphify 는 **hermes 의 terminal tool 로 spawn** — Hermes 의 tirith 가 default 로 secret env 를 subprocess 에서 strip. `~/.hermes/hermes-agent/tools/env_passthrough.py` 의 allowlist 메커니즘 정합:

- skill frontmatter `required_environment_variables` 선언 → Hermes 자동 allowlist.
- 또는 `~/.hermes/config.yaml` 의 `terminal.env_passthrough` 에 명시.

본 ADR 은 후자 (operator-side Hermes config) 를 정본 — wikihub skill 의 frontmatter 는 path 상수 / API key 둘 다 비워 wh_skills_env_cleanup (2026-05-19) 의 정합 유지. wikihub setup.md Step 1 이 Hermes config 안내 1줄로 운영자에게 책임 위임.

### OpenCode-go 사례 (operator 운영 예시)

```yaml
# wikihub.yaml
operations:
  graphify_backend: ollama
```

```
# ~/.config/wikihub/env (또는 Hermes config 의 env)
OLLAMA_BASE_URL=https://opencode.ai/zen/go/v1
OLLAMA_API_KEY=<provider key>
OLLAMA_MODEL=minimax-m2.5
```

```yaml
# ~/.hermes/config.yaml
terminal:
  env_passthrough: [OLLAMA_BASE_URL, OLLAMA_API_KEY, OLLAMA_MODEL]
```

### 추가 보강 — lint Step 9 의 timeout wrapper

graphify subprocess 가 hang (API key 부재 / endpoint 응답 없음 / etc.) 시 lint 전체가 TimeoutStartSec 으로 SIGINT 받음. lint.md Step 9 에 `timeout 300 graphify ...` wrapper 추가 — exit 124 시 report 에 `graph rebuild timeout` + lint 계속 (ADR-0036 §D6 정합 보강).

### Cross-references 갱신

- §D2 본문 ↔ 본 §Note 정합. 본문 미수정 — 역사적 맥락 보존, schema 정본은 본 §Note + 본 feature 의 analysis_and_design.md.
- 본 feature 의 분석 정본: [features/archive/20260520_graphify_backend_flexibility/analysis_and_design.md](../../features/archive/20260520_graphify_backend_flexibility/analysis_and_design.md)
- 2026-05-20 검토 자료: `graphifyy 0.8.13/llm.py` (BACKENDS dict, line 47-118; client init line 287).

## Note (2026-05-20, lint default 변경) — §D6 cost 모델 보강

v0.1.5 wave 의 default `operations.lint_interval_hours: 24 → 3` 변경. §D6 "wh-lint timer 주기로만 cost 통제" 가정 그대로 — 단 cost upper bound 가 24h 1회 → 3h 1회 (8배). 운영자가 부담 시 `operations.graphify_enabled: false` toggle 로 chain 자체 skip.

§D6 본문 미수정 — default 값 변경만 운영적 사실로 명시.

## Note (2026-05-20, feature `lint_fallback_toggles` v0.1.5) — graphify chain skip toggle + v0.1.6 분리 트리거

### 발견

OCI 운영 중 lint timeout 결함 surface — 운영자(Hermes) 가 수동 SIGINT (`systemctl --user stop`). 진짜 root cause = `_interruptible_streaming_api_call` 의 `lock.acquire()` 5분 대기 = **DeepSeek API 응답 느림** (네트워크 대기, CPU 10.6초). lint Step 9 의 graphify chain 이 cost 비대칭 — 운영자가 chain 자체 skip 원할 때 toggle 부재.

### Quick fix (본 §Note)

yaml schema 토글 신설 — lint chain 안에서 graphify 호출 skip 가능:

- `operations.graphify_enabled: true` (default; false 시 lint Step 9 skip)
- `operations.lint_contradiction_check: true` (default; false 시 lint Step 6 skip — 가장 무거운 LLM 호출)
- `agent.timeout_sec: 600 → 1200` (default 증설 — DeepSeek 등 느린 backend 대비)

§D6 의 "wh-lint timer 주기로만 cost 통제" 가정 보강 — 운영자가 chain 분리 통제도 가능.

### v0.1.6 분리 트리거 (재검토 트리거)

본 quick fix 는 lint chain **안에서** toggle. 더 architectural 한 fix = `wikihub-graphify.service` + `.timer` 신설 (lint 와 분리). lint chain 의 Step 9 제거 → lint 본체만 단일 systemd unit, graphify 가 자기 timer 로 별도 trigger.

분리 이점:
- lint timeout 영향 격리 (graphify hang 이 lint 와 무관)
- 주기 별도 통제 (`operations.graphify_interval_hours`)
- failure isolation (각자 OnFailure ops-alert)

분리 시 ADR-0006 (unified orchestration) §Note 검토 필요 — "각 skill 이 자기 unified 경로" 의 재해석. graphify 분리는 v0.1.6 별도 feature 로 추출.

### 본 §Note 의 분석 정본

[features/archive/20260520_lint_fallback_toggles/](../../features/archive/20260520_lint_fallback_toggles/)

---

## Note (2026-05-24, feature `graphify_profile_namespace` v0.1.7 follow-up) — CLI v8 sync

> namespace 격리 결정은 본 §Note 에서 제외 — **ADR-0038** 로 분리 (Partially supersedes §D2). 본 §Note 는 graphify v8 의 실제 CLI 동작에 wikihub 정합하는 결정만 보유.

### 발견

graphify v8 (`graphifyy>=0.8.0`) 의 `--help` 와 OCI 운영 검증 (2026-05-22~24) 으로 graphify.md Step 2 가 v8 과 어긋남 확인:

- v8 는 `extract <wiki>` subcommand 필수 (`graphify <wiki>` 단독 명령 없음). 기존 graphify.md 는 v7 패턴 (`graphify <wiki>` + `--update` flag) 사용 — 동작 불가.
- `--out DIR` 명시 → `DIR/graphify-out/` 생성. 기존 graphify.md 는 묵시적 cwd `graphify-out/` 가정.
- `--max-concurrency N` (default 4; "set 1 for local LLMs" 권장).
- `--api-timeout S` (default 600s) per-request timeout — wrapper `timeout 300` (기존) 보다 더 큼.
- v8 의 `update <wiki>` subcommand 는 AST-only (code 전용, no LLM) — markdown wiki 부적합.
- v8 의 `check-update <wiki>` 는 "cron-safe" 표현 — OCI 검증 (3 시나리오 모두 exit=0 + stdout 무음) → 활용 불가.

`docs/graphify-backend-test-reference.md` (2026-05-23) 가 ground truth.

### 결정 A. CLI v8 sync

graphify.md Step 2 전면 재작성 — `extract <wiki>` subcommand + `--out $WIKIHUB_HOME` + `--max-concurrency N` + `--model M` flag. v7 era 의 `--update` flag 사용 안 함 (v8 미존재).

### 결정 B. endpoint pattern → ollama env 분기

`--backend ollama` 호출 시 endpoint URL 형태로 두 env 컨벤션 중 분기:

- `http://localhost:*` / `http://127.0.0.1:*` / `http://[::1]:*` (loopback hostname-anchored) → `OLLAMA_HOST` (native Ollama API)
- 그 외 (`https://opencode.ai/zen/go/v1` 등) → `OLLAMA_BASE_URL` (OpenAI-compat client)

substring (`*:11434*`) 대신 prefix-anchored — 외부 URL 의 `:11434` 우발 match 차단 (design review 합의).

### 결정 C. `--max-concurrency` 휴리스틱

- model 명에 `cloud` 부분일치 (예: `gemma4:31b-cloud`) → 4 (cloud-proxied, network-bound)
- 그 외 + endpoint 가 loopback hostname → 1 (진짜 local LLM, resource-bound)
- 그 외 (외부 cloud endpoint) → 4 (cloud, network-bound)

v8 `--help` 의 "default 4; set 1 for local LLMs" 권장 정합.

### 결정 D. 증분 빌드 — graphify internal cache 위임

graphify v8 의 `extract` 가 graph.json 보존 시 internal cache 로 unchanged 노드 자동 보존. 외부 `--update` flag 불필요. 2-mode dispatch:

- 수동 `--rebuild` flag → graph.json 삭제 후 `extract` (force full)
- 그 외 (timer + 수동 일반) → `extract` 그대로 (graphify cache 가 자동 incremental)

v7 era 의 rebuild/incremental/first 3-분기 폐기.

### 결정 E. `check-update` gate deferred

OCI 검증 (2026-05-24) 결과 — 3 시나리오 (graph.json 미존재 / extract 직후 up-to-date / wiki 수정 후 pending) 모두 `exit=0` + stdout 무음. graphify 본가의 notification 채널 미명세. gate 활용 불가 → 본 patch 에서 미사용. **재검토 트리거**: graphify 본가의 spec 명확화 (`--json` flag 도입 또는 exit code semantics 문서화) 시 v0.2.x 에서 재방문.

### 결정 F. Step 3 결과 검증 — partial graph.json 보호

`extract` 호출 후 graph.json 검증:

- `jq 'keys' graph.json` fail → graph.json 이 invalid JSON 또는 partial write (timeout 도중 kill) → **삭제 + exit 1** (force clean). 다음 호출이 fresh state 로 시작.
- pass → `jq '.nodes | length'` + `jq '.links | length'` 로 node/edge 수 출력. **edges 는 `.links` 위치** — NetworkX node-link format 정합 (`docs/graphify-backend-test-reference.md` §1 검증).

### Cross-references 갱신

- ADR-0006 unified orchestration: 본 patch 의 lint.md Step 9 단순화 (`<agent_invocation> "/wh-graphify"` 1줄) 정합 — "각 skill 이 자기 unified 경로" 의 strict 해석. backend dispatch 의 single source 가 graphify.md.
- ADR-0031 §Note (v0.1.7): `_migrate_*` 함수의 schema vs value mutation boundary — 본 §Note 의 모든 마이그레이션 (env legacy 키 삭제, yaml graphify_profile 자동 추가, profile 값 invalid warn-but-no-mutate) 이 정합.
- ADR-0038 (신규): namespace 격리 — 본 §Note 의 §D2 partial supersede.
- **v0.1.8 cleanup** (2026-05-25, feature `legacy_migration_cleanup`) — 본 §Note 의 §Rollback procedure + §배포 Gap window 분석 두 절은 `_migrate_graphify_env` referent 였음. cleanup 으로 함수 삭제 → 두 절도 동시 삭제 (dead text). §결정 A~F (CLI v8 sync 본체) 는 실 code 정본이므로 그대로 유지.

### 본 §Note 의 분석 정본

[features/20260524_graphify_profile_namespace/](../../features/20260524_graphify_profile_namespace/) (active, archive 이동 예정)
