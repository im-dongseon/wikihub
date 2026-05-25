# ADR-0038: graphify env namespace isolation (WIKIHUB_GRAPHIFY_<PROFILE>_*)

- **Status**: Accepted
- **Date**: 2026-05-24
- **Feature**: features/20260524_graphify_profile_namespace
- **Supersedes**: 없음 (ADR-0036 §D2 partially superseded — secret layer schema 재정의)
- **Superseded by**: 없음

## Context

`~/.config/wikihub/env` 의 `OLLAMA_BASE_URL`/`OLLAMA_API_KEY`/`OLLAMA_MODEL` 등 graphify backend env 가 systemd `EnvironmentFile=` 경유로 Hermes parent process 에 주입 → Hermes 가 자기 LLM backend 로 인식 → `model.default` 오버라이드. OCI 운영 2026-05-22~24 관측. graphify subprocess 만 받아야 할 자료가 leak.

부차적으로, opencode / openrouter / local Ollama 등 **여러 backend·endpoint·model 묶음을 동시 보유**하고 yaml 한 줄로 swap 하는 운영 요구 (model 비교 테스트 + provider fail 대체).

기존 ADR-0036 §D2 는 "API key 저장 layer" 를 `~/.config/wikihub/env` 단일 파일로 정의했으나, 표준 env 컨벤션 (OLLAMA_*, ANTHROPIC_API_KEY 등) 을 그대로 사용 → Hermes parent 의 인식 영역과 충돌.

## Considered Options

- **(α) 단일 active + 주석 alternative**: 같은 OLLAMA_* 키 유지, 주석 처리로 swap. yaml 변경 0, 단 다중 profile 불가, secret 주석 처리 휴먼에러.
- **(β) 단일 env 키 + yaml model 별도**: profile 은 endpoint+key 만, model 은 yaml 별도 필드. 2-필드로 3-secret 어드레싱 → 추적 분산.
- **(γ) profile-bundle full namespace**: env 가 `WIKIHUB_GRAPHIFY_<PROFILE>_<ENDPOINT|API_KEY|MODEL>` 의 wikihub-private 키 보유. yaml `graphify_profile` 1 필드가 selector. 다중 profile 동시 보유 + 1:1 direct mapping.
- **(δ) env 파일 분리**: graphify.env 와 alerts.env 분리, systemd 가 graphify.env 미참조. 파일 단위 isolation, 단 install.sh perm 책임 확장.

> 옵션 상세 비교는 [features/20260524_graphify_profile_namespace/plan.md](../../features/20260524_graphify_profile_namespace/plan.md) Q3 + [analysis_and_design.md](../../features/20260524_graphify_profile_namespace/analysis_and_design.md) §2 참조.

## Decision

**채택**: (γ) profile-bundle full namespace.

### 채택 사항

1. **Namespace 격리**: env 파일이 `WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL>` 의 wikihub-private 키만 사용. graphify subprocess 호출 시점 (`_system/commands/graphify.md` Step 2) 에서 `env <BACKEND_ENV>=<value>` 로 explicit 주입 — Hermes parent 는 backend env (`OLLAMA_*`, `ANTHROPIC_API_KEY` 등) 를 보지 않음.

2. **Profile bundle 모델**: `operations.graphify_profile: <name>` yaml 1 필드가 env 의 어떤 키 세트를 활성으로 쓸지 선택. 다중 profile 동시 보유 (yaml 한 줄 swap 으로 backend 교체). profile 명 컨벤션: `<provider>_<model_hint>` 권장, regex `^[a-z][a-z0-9_]*$` 강제 (런타임 검증 + install-time non-fatal warn).

3. **Auto-migration**: 기존 env 파일의 legacy 키 (`OLLAMA_*`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_*`) 는 `install.sh _migrate_graphify_env` 가 자동 삭제. Telegram 값 + 운영자 custom profile 보존. `ollama_gemma` default inject. `_migrate_agent_schema` 가 yaml `graphify_profile` 자동 추가. 모두 PTY-safe + idempotent + backup (`.wikihub-bak.<utc_iso>`, 30일 retention).

4. **Hermes trust 가정**: Hermes 는 자기 표준 env (`OLLAMA_*`, `ANTHROPIC_*`, `OPENAI_*`, `GEMINI_*`) 만 react. `WIKIHUB_GRAPHIFY_*` 는 Hermes 가 load 하되 interpret 안 함 (unknown prefix 무시). 검증 방법 — `systemctl --user show-environment` 또는 hermes process env 에 `WIKIHUB_GRAPHIFY_*` 가 보이되 `model.default` override 영향 없음을 확인. 추가 가정: **Hermes terminal tool 이 `bash` invoke** (dash 미지원) — graphify.md Step 2 의 `${!var:-}` indirection 이 bash 4+ 의존이며 POSIX `/bin/sh` (dash) 환경에서는 미동작. OCI Ubuntu 24.04 default Hermes terminal = bash 가 본 ADR 의 기반.

5. **Schema vs Value mutation 정합**: 본 ADR 의 auto-migration 은 ADR-0031 §Note (v0.1.7) 의 boundary 정합. **legacy 키 삭제 = schema mutation** (env 변수명 자체가 schema). **Telegram 값 + 운영자 custom profile + 기존 ollama_gemma 값 = value mutation 회피로 보존**. install.sh 가 값 자체를 변경하지 않음.

### 기각 이유

- **(α)**: 다중 profile 동시 보유 불가 — model 비교 테스트 friction. secret 주석 처리는 휴먼에러 risk (실수로 활성화).
- **(β)**: 2-필드 (graphify_profile + graphify_model) 로 3-secret 어드레싱 → "bundle-with-override" 어색한 모델. 활성 model 추적이 두 곳 검증 분산.
- **(δ)**: 파일 단위 isolation 강점 있으나 install.sh perm 책임 확장 + `EnvironmentFile=` 패턴 이탈. 운영 부담 대비 (γ) 와 동등한 isolation 효과 미달.

## Consequences

### 긍정

- **Hermes bleed 차단** — `model.default` 오버라이드 surface 0. 운영 정확성 복원.
- **Multi-profile 운영** — `opencode_minimax` / `openrouter_claude` / `claude_direct` 등 cookbook 의 6 profile 보유 가능. yaml `graphify_profile` 1줄 swap 으로 전환.
- **ADR-0036 §D2 evolution** — secret layer 가 단일 file 의 표준 컨벤션에서 wikihub-private namespace bundle 로 진화. 표준 컨벤션 충돌 해소.
- **ADR-0031 §Note 정합** — auto-migration 이 schema 만 mutate, 운영자 value 는 보존. backup + idempotent + PTY-safe.

### 부정 / 제약

- **운영자 코멘트 drop** — `_migrate_graphify_env` 가 env 파일을 canonical template 으로 rewrite → 운영자가 적어둔 inline 메모 소실 (backup 에서만 참조 가능). install.sh info 메시지로 surface.
- **endpoint pattern 분기 fragility** — LAN Ollama (`http://192.168.x.x:11434`) / Docker network (`http://ollama:11434`) / reverse-proxy 의 native API 노출 시 silent misroute 가능. v0.2.x 에서 `WIKIHUB_GRAPHIFY_<P>_OLLAMA_MODE=native|compat` env override 도입 deferred.
- **backend/profile prefix mismatch silent misconfig 가능** — `backend: claude` + `profile: ollama_gemma` 같은 mixed configuration 시 graphify.md Step 2 가 ANTHROPIC_API_KEY 로 dispatch 하면서 ollama_gemma 의 ENDPOINT 무시. consistency warn 추가 안 함 (advanced 운영자 mixed case legitimate, U3 결정).

### 후속 영향

- **재검토 트리거**:
  - LAN Ollama / Docker network endpoint 운영 시나리오 surface → v0.2.x 의 `OLLAMA_MODE` env override 검토
  - graphify 본가의 `check-update` notification 채널 spec 명확화 → cron-safe gate 도입 재검토 (현 deferred — ADR-0036 §Note 2026-05-24 결정 E)
  - graphify v9+ backend 추가 (예: AWS Bedrock) → 본 ADR 의 backend case 확장
- **관련 ADR**:
  - ADR-0031 §Note (v0.1.7) — schema vs value mutation 정책의 본 ADR 적용
  - ADR-0036 §Note 2026-05-24 — CLI v8 sync (extract subcommand + endpoint/concurrency 휴리스틱)
  - ADR-0036 §D2 partially superseded — secret layer schema 재정의
  - ADR-0037 — TELEGRAM_ALERT_* env 영역 영향 없음 (v0.1.7 follow-up 의 마이그레이션 + v0.1.8 cleanup 후에도 영역 영향 없음)
- **v0.1.8 cleanup** (2026-05-25, feature `legacy_migration_cleanup`) — `_migrate_graphify_env` 함수 삭제 (운영자 base 정착 후 영구 no-op). §Decision 3 (auto-migration) 의 1회성 본체 polish 완료. §Decision 1·2·4·5 (namespace 격리 자체 + Hermes trust 가정) 은 영구 유효 — supersede 아님.
