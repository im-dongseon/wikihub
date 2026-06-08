---
approved: 2026-05-20
---

# Analysis & Design — graphify_backend_flexibility (v0.1.4)

## 1. 배경 및 목적

ADR-0036 §D2 (2026-05-19) 가 graphify Pass 3 의 LLM backend 를 default `ANTHROPIC_API_KEY` 로 lock. OCI 운영자가 별도 Anthropic API key 발급 의사 없음 + Hermes 측에 OpenCode-go (`https://opencode.ai/zen/go/v1`) 의 deepseek-v4-pro API key 가 이미 설정돼 있음을 보고 — backend 선택 layer 의 schema 보강 필요.

graphify CLI source (`graphifyy 0.8.13/llm.py:64-71`) 검증:

```python
"ollama": {
    "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    "default_model": os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"),
    "env_key": "OLLAMA_API_KEY",
    ...
}
```

그리고 `llm.py:287` 의 client init: `client = OpenAI(api_key=api_key, base_url=base_url, ...)` — **`ollama` backend = "OpenAI-compatible generic client"**. 이름이 misleading. OpenCode-go / OpenRouter / LM Studio / Together / Fireworks 등 OpenAI-compatible endpoint 모두 호환.

## 2. 결정 (간단)

### D1. yaml schema 보강

- 신설: `operations.graphify_backend` (string, default `""` = graphify auto-detect)
- 폐기: `operations.graphify_api_key_env_name` (현재 default `ANTHROPIC_API_KEY`) — backend 별 env 가 다양해 단일 필드 미적합
- backend 값 catalog: `""` | `claude` | `claude-cli` | `openai` | `gemini` | `kimi` | `deepseek` | `ollama` | `bedrock`

### D2. lint Step 9 의 graphify 호출 갱신

- yaml `operations.graphify_backend` 읽어 `--backend $value` 명시 전달 (비어있으면 flag 생략 → graphify auto-detect)
- `timeout 300 graphify ...` wrapper — exit 124 (timeout) 시 report 에 기록 + lint 본체 계속 (ADR-0036 §D6 정합: graphify 보조 자원)

### D3. 운영자 env 자료 전달 layer 변경 — ~/.config/wikihub/env vs Hermes 의 terminal.env_passthrough

ADR-0036 §D2 는 `~/.config/wikihub/env` + systemd `EnvironmentFile=-%h/.config/wikihub/env` 패턴. 이는 systemd 가 unit 의 환경에 KEY=VALUE 주입.

그러나 wh-lint 실행 흐름: `lint.service` ExecStart=hermes chat → hermes 가 wh-lint skill 실행 → Step 9 의 graphify 호출은 **hermes 의 terminal tool 을 통한 subprocess**. Hermes 의 tirith 보안 layer 가 secret env 를 subprocess 에서 strip — `~/.hermes/hermes-agent/tools/env_passthrough.py` 의 `_HERMES_PROVIDER_ENV_BLOCKLIST` 와 allowlist 메커니즘.

→ `~/.config/wikihub/env` 의 OLLAMA_API_KEY 가 systemd 차원에선 unit env 에 있지만 hermes 가 spawn 한 graphify subprocess 에선 strip 가능.

해결 옵션:
- (α) skill frontmatter `required_environment_variables` 로 OLLAMA_* 선언 — Hermes 자동 allowlist. 단 macOS dev env 에서 prompt 트리거 위험 (이전 `wh_skills_env_cleanup` 의 학습 — wh-* skill 의 frontmatter 정리 의도 와 충돌).
- (β) **운영자가 `~/.hermes/config.yaml` 의 `terminal.env_passthrough` 에 backend env 추가** — wikihub setup.md 가 안내 1줄. wikihub spec 차원 무영향.
- (γ) Hermes 의 env 가 이미 OLLAMA_* 보유 가정 (운영자 보고 — "api 키는 이미 hermes 에 설정") + setup.md 가 운영자 확인 책임 위임.

**채택**: (β) + (γ) — operator-side Hermes config 가 정본. wikihub 의 `~/.config/wikihub/env` 는 fallback 용 (Hermes 외 직접 graphify CLI 호출 시 사용). setup.md 가 양쪽 안내.

### D4. ADR-0036 §D2 §Note 갱신

본 변경의 결정 정본 기록. backend 가 단일 default 가 아닌 catalog + 운영자 선택. OpenCode-go (deepseek-v4-pro) 예시 명시.

## 3. 개정 범위

| 파일 | 변경 |
|---|---|
| `wikihub.yaml.example` | `graphify_api_key_env_name` 제거 + `graphify_backend` 신설 + 주석에 backend catalog |
| `install.sh:_step5_instance_dirs` env template | backend 별 예시 5종 (Anthropic / OpenAI / OpenCode-go via ollama / 진짜 Ollama 로컬 / claude-cli) |
| `_system/commands/lint.md` Step 9 | yaml `graphify_backend` 읽어 `--backend` 전달 + `timeout 300` wrapper |
| `_system/commands/setup.md` Step 1 | env file 검증 단순화 + Hermes `terminal.env_passthrough` 안내 1줄 |
| `docs/adr/0036-graphify-cli-integration.md` | §Note (backend flexibility + OpenCode-go) |
| `features/HISTORY.md` | v0.1.4 wave 두 번째 entry |

## 4. 미결 사항

없음.

## 5. Definition of Done

- [ ] `wikihub.yaml.example` 의 `graphify_api_key_env_name` 제거 + `graphify_backend` 추가
- [ ] `install.sh` env template 의 backend 예시 5종 보강
- [ ] `lint.md` Step 9 의 graphify 호출에 `--backend` + `timeout 300` 추가 + exit 124 처리
- [ ] `setup.md` Step 1 env file 검증 단순화 + Hermes config 안내
- [ ] ADR-0036 §Note 추가
- [ ] pytest 회귀 57 pass 유지
- [ ] feature dir archive 이동
