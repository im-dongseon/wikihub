---
approved: 2026-05-20
---

# Plan — agent_model_per_skill (v0.1.5 amend)

- **작업 분류**: 기능 보강 (yaml schema 신설 — per-skill model override + lint 출력 언어 정책)
- **적용 단계 선언**:
  - Step 1 (Plan/AD): 본 문서 (병합)
  - Step 3 (Implementation): yaml + render helper + lint.md + ADR §Note + setup.md catalog
  - **Step 4 (Review): 생략** — Hermes OCI 진단 자체가 review 의 실 데이터 layer + 외부 인터페이스 변경 최소 (yaml 1 field map)
  - Step 5 (Deployment): v0.1.5 amend (force-push 4번째 — user 명시 "0.1.5 유지")
- **영향 범위**:
  - `wikihub.yaml.example` — `agent.models` map (default 빈 dict, 예시 `wh-lint: minimax-m2.5`)
  - `scripts/_helpers/render_systemd_units.py:_per_skill_invocation` — yaml.agent.models[<skill>] → `--model <id>` inject
  - `_system/commands/lint.md` — "출력 언어 정책" section (한자 → 한글 변환 지시, LLM 호출 step 들 공통 적용)
  - `docs/adr/0032-hermes-skill-registration-policy.md` §Note — per-skill model override + 출력 언어 정책 결정 정본
  - `_system/commands/setup.md` maintainer catalog
- **메소드론 적용**: 적용 (yaml schema + ADR §Note + playbook 정책).

## 결정

### D1. per-skill model override

OCI 운영자가 wh-lint 만 `minimax-m2.5` 쓰고 hermes Telegram 대화는 다른 model 쓰고 싶을 때 가능하게. yaml `agent.models[<skill>]` map. render_systemd_units 가 `--model <id>` 명시 inject. backward-compat (빈 dict default → hermes config default).

### D2. lint 출력 언어 정책 (한자 → 한글)

MiniMax M2.5 등이 한국어 응답에 한자 섞어 출력 결함. `_system/commands/lint.md` 상단에 "출력 언어 정책" 1 section — 한자 감지 시 한글 변환. 고유명사 예외. 영어 약어 그대로.

### D3. version 유지

v0.1.5 amend (user 명시) — force-push 4번째. v0.1.5 immutability 약화 vs release window 응집성. 다른 wave 의 v0.1.5 변경 (migration_prompt_simplify + lint_fallback_toggles + minimax 갱신) 과 같은 release window 안. v0.1.6 별도 발행 하지 않음.

## 검증

- pytest 57 pass 회귀 확인
- render dry-run — lint.service 만 `--model minimax-m2.5` inject, 다른 wh-* unit 영향 없음 ✓ (이미 확인됨)

## 미결 사항

없음 — Hermes 실증 데이터로 모델 선택 + 정책 모두 lock.
