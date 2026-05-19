# Plan — migration_prompt_simplify (v0.1.5)

- **작업 분류**: 운영 (install.sh 의 noninteractive 휴리스틱 cycle 종료)
- **적용 단계 선언**:
  - Step 1 (Plan): 본 문서
  - Step 2 (Analysis & Design): 본 디렉토리의 `context.md` + 2건 서브에이전트 design_review (병합 권장 → 옵션 (1))
  - Step 3 (Implementation): 수행 — install.sh 1곳 단순화 + info log + VERSION + HISTORY + ADR §Note
  - **Step 4 (Review): 생략** — Step 2 의 design review 2건이 이미 옵션 평가 충분.
  - Step 5 (Deployment): 수행 — v0.1.5 patch bump + tag + latest force-update.
- **예상 영향 범위**:
  - `install.sh:_migrate_agent_schema` (line 749-758) — prompt 분기 제거 + info log 1줄
  - `_system/VERSION` 0.1.4 → 0.1.5
  - `docs/adr/0032-hermes-skill-registration-policy.md` — §Note 1줄 (옵션 (1) 채택 사유)
  - `features/HISTORY.md` v0.1.5 entry
- **메소드론 적용 여부**: 적용. v0.1.3 → v0.1.4 → v0.1.5 의 동일 패턴 (`[[ -t 0 ]]` cycle) 종료.

## 결정

서브에이전트 2건 design review (Reviewer 1 architectural/safety, Reviewer 2 operational/UX) 결과:
- 공통: (1)/(2) 가 (3)/(4) 보다 우월. (3)/(4) 는 stdin-shape 휴리스틱 cycle 잔존.
- 분기: Reviewer 1 → (2) [escape hatch 도입], Reviewer 2 → (1) [미래 비용 unknown 시점 over-engineering 회피].
- 운영자 의사결정: **미래 비용 (v0.2.x 외부 운영자) 불확정 — 가설에 대비한 escape hatch 미도입**. 옵션 (1) 채택.

배경 (한 문장): v0.1.3 → v0.1.4 의 동일 root cause (Hermes PTY 가 `[[ -t 0 ]]` 거짓 양성 만듦) 가 재발하지 않도록 prompt 분기 자체를 제거. backup (`.wikihub-bak.<utc_iso>`) 가 의도 override safety net 으로 유지.
