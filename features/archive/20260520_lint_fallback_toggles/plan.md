# Plan — lint_fallback_toggles (v0.1.5)

- **작업 분류**: 운영 (yaml schema 토글 + default 변경)
- **적용 단계 선언**:
  - Step 1 (Plan): 본 문서
  - Step 2 (Analysis & Design): 간소 (아래 §결정)
  - Step 3 (Implementation): yaml + lint.md + setup.md + HISTORY + ADR §Note
  - **Step 4 (Review): 생략** — 단일 의도 (운영자 cost/시간 통제 토글), 외부 인터페이스 변경은 yaml 3 field
  - Step 5 (Deployment): v0.1.5 wave 2번째 commit (push 보류 — 152d751 와 함께 일괄 push 예정)
- **예상 영향 범위**:
  - `wikihub.yaml.example` — `agent.timeout_sec` default 600 → 1200 + `operations.graphify_enabled` + `operations.lint_contradiction_check`
  - `_system/commands/lint.md` Step 6 / Step 9 진입 분기
  - `_system/commands/setup.md` maintainer catalog
  - `docs/adr/0036-graphify-cli-integration.md` §Note (graphify_enabled toggle + v0.1.6 분리 트리거)
  - `features/HISTORY.md` entry
- **메소드론 적용 여부**: 적용. yaml schema 추가 (2 toggle) + default 변경.

## 결정

서브에이전트 review (이전 wave) + Hermes 진단 (lint timeout 의 root cause = DeepSeek API 느림 + lint 본체 LLM 호출) 기반:

- **timeout 증설**: `agent.timeout_sec` default 600 → 1200. Hermes 가 이미 manual patch (TimeoutStartSec=1200) 실증.
- **graphify chain skip 토글**: `operations.graphify_enabled` (default true). false 시 lint Step 9 graphify 호출 skip. 운영자 cost / API key 부재 대응.
- **모순 점검 skip 토글**: `operations.lint_contradiction_check` (default true). false 시 lint Step 6 (가장 무거운 LLM 호출) skip.

graphify 분리 (별도 systemd unit + .timer) 는 별도 v0.1.6 feature — architectural refactor + ADR-0006 정합 검토 필요. 본 wave 에서는 ADR-0036 §Note 에 트리거만 명시.
