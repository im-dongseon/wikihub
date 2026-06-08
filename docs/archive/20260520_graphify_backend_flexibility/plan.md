# Plan — graphify_backend_flexibility (v0.1.4)

- **작업 분류**: 기능 보강 (ADR-0036 §D2 의 backend lock 해제)
- **적용 단계 선언**:
  - Step 1 (Plan): 본 문서
  - Step 2 (Analysis & Design): 수행 (간소)
  - Step 3 (Implementation): 수행
  - **Step 4 (Review): 생략** — 단일 의도 (graphify backend 선택 + lint Step 9 timeout), schema 1 field 추가 + ADR §Note. v0.1.4 wave 안 단순 cleanup.
  - Step 5 (Deployment): 수행 — install_robustness 와 동일 v0.1.4 wave 의 별도 commit.
- **예상 영향 범위**:
  - `wikihub.yaml.example` — `graphify_api_key_env_name` 제거 + `graphify_backend` 신설
  - `install.sh` `_step5_instance_dirs` — env 파일 template 의 backend 예시 (Anthropic / OpenAI / OpenCode-go / claude-cli / ollama local)
  - `_system/commands/lint.md` Step 9 — yaml `graphify_backend` 읽어 `--backend` 인자 + `timeout` wrapper 추가
  - `_system/commands/setup.md` Step 1 — env file 검증의 `graphify_api_key_env_name` 의존 제거 + Hermes `terminal.env_passthrough` 안내 1줄
  - `docs/adr/0036-graphify-cli-integration.md` — §Note (backend flexibility + OpenCode-go example)
  - `features/HISTORY.md` — v0.1.4 wave 의 두 번째 entry
- **메소드론 적용 여부**: 적용. yaml schema 변경 (1 field 교체) + ADR §Note + playbook 변경.

## 배경 (한 문장)

ADR-0036 §D2 의 default backend = Anthropic Claude (API key 필요) 가정이 운영자 비용/구독 모델에 misaligned (OCI 운영자가 별도 ANTHROPIC_API_KEY 발급 의사 없음). graphify CLI 의 source (`graphifyy 0.8.13/llm.py:64-71`) 검증 결과 `ollama` backend 가 실제로는 "OpenAI-compatible endpoint generic client" 임을 확인 — `OLLAMA_BASE_URL`/`OLLAMA_API_KEY`/`OLLAMA_MODEL` 조합으로 OpenCode-go (`https://opencode.ai/zen/go/v1` + `deepseek-v4-pro`) 등 사용 가능.
