# ADR-0046: Issue-first workflow transition + OpenCode canonical agent

- **Status**: Accepted
- **Date**: 2026-06-07 (KST)
- **Feature**: governance transition (ADR-0046 itself)
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

WikiHub의 5-step workflow (AGENTS.md §3·§4, agent_dev_guide.md)는 `features/[YYYYMMDD]_[feat_id]/` 디렉토리와 `feature/[기능개발주제명]` 브랜치 명명의 feature-based 패턴을 정본으로 규정해왔다. 그러나 실무에서는 이미 `feature/issue-<N>` 브랜치 + `YYYYMMDD_issue<N>_<slug>/` 디렉토리가 사용되고 있으며, Hermes `github-dev-flow` 스킬이 이 명명 규칙에 기반한 issue-first 워크플로우를 정의. 정본과 실무 사이에 정합성 갭이 존재하며, ADR Feature 필드에 `features/YYYYMMDD_slug/`, `issue #N`, 혼합형이 혼재.

동시에 에이전트 생태계 변화:
- **OpenCode**를 유일한 code agent로 채택 (구현·리뷰·배포)
- **Claude Code** deprecated 예정 (기존 `.claude/` 설정 유지하되 신규 세션 사용 금지)
- **Hermes**는 외부 오케스트레이션 레이어로 전환 (운영 환경에서만 호출, 개발 repo와 분리)

이에 따라 `.opencode/`를 git 추적 대상으로 전환하고, 모든 워크플로우 명명 규칙을 issue-first로 통일할 필요가 있음.

## Considered Options

- **(α) Issue-first 단일 워크플로우**: 모든 작업은 GitHub issue 선행 생성 필수. 브랜치·디렉토리·커밋 명명이 issue 번호에 기반.
- **(β) 이중 패턴 유지 (Issue + Issueless)**: issue-linked는 `feature/issue-<N>`, self-driven(인프라·리팩터링 등)은 종래 `feature/[slug]` 유지.
- **(γ) 현행 유지**: AGENTS.md 정본을 feature-based로 두고 실무의 issue-based 패턴을 비공식 허용.

## Decision

**채택**: (α) Issue-first 단일 워크플로우 + OpenCode 단독 정본

**이유**:
- 트래서빌리티: 작업↔issue↔PR↔ADR 추적이 단일 체인으로 보장
- 정합성: 정본과 실무의 불일치 해소 (ADR-0046이 AGENTS.md §3·§4 관례를 대체)
- 단순성: 이중 패턴(β)은 선택의 부담과 혼란만 증가
- 에이전트 단순화: OpenCode만 추적하므로 설정 파일이 `.opencode/`에 집중
- 외부 오케스트레이션(Hermes)이 OpenCode를 호출할 때도 동일한 issue 기반 컨벤션 적용

**기각된 옵션의 단점**:
- (β): "이슈가 없는 작업"의 판단 기준이 모호해지고, 인프라 작업도 결국 issue를 만들어야 한다는 오버헤드만 피할 수 있음. 그러나 추적 가능성의 가치가 이 오버헤드를 상회.
- (γ): 정본과 실무의 불일치가 계속 확대되어 신규 contributor의 혼란과 ADR 참조 불일치 악화.

### 세부 결정

#### 1. 명명 규칙 전환 (feature-based → issue-first)

| 항목 | 기존 (feature-based) | 새로운 (issue-first) |
|---|---|---|
| 브랜치명 | `feature/[기능개발주제명]` | `feature/issue-<N>` |
| 디렉토리명 | `features/[YYYYMMDD]_[feat_id]/` | `features/[YYYYMMDD]_issue<N>_<slug>/` |
| 워크트리 | `../[repo]-feat/[YYYYMMDD]_[기능개발주제명]` | `../wikihub-issue<N>` |
| 커밋 타이틀 | `<type>: <요약>` (예: `fix:`, `docs:`) | `<type>(issue-<N>): <요약>` (예: `fix(issue-42):`) |
| PR head | `feature/[slug]` | `feature/issue-<N>` |
| PR milestone | `<vX.Y.Z>` | `<vX.Y.Z>` (변경 없음) |
| ADR Feature 필드 | `features/[YYYYMMDD]_[feat_id]/` | `issue #N` |
| HISTORY.md 항목 | `feat_id` 중심 | `issue #N` 중심 |

#### 2. GitHub issue 선행 강제

모든 작업은 GitHub issue 먼저 생성. 자발적 개선·인프라 작업도 issue 작성 후 진행. issue 없는 작업은 exception이 아닌 규칙 위반.

#### 3. OpenCode 정본화

- **`.opencode/`**: `.gitignore`에서 제거 → repo 추적 대상으로 전환
  - `opencode.json`: 에이전트 model mapping
  - `agent/*.md`: 서브에이전트(리뷰·계획 등) 프롬프트 정의
- **`.claude/`**: `.gitignore`에 유지 (deprecated). 기존 파일은 보존하되 신규 세션에서는 사용 금지
- **`.hermes/`**: `.gitignore`에 유지 (외부 오케스트레이션). 개발 repo에서 Hermes 스킬은 추적하지 않음
- **`CLAUDE.md`**: deprecated 주석 추가. AGENTS.md §0 Quick map에서 링크 유지하되 deprecation 표기
- **스킬 마이그레이션**: 미실행. OpenCode는 oneshot 도구 역할만 수행하므로 자체 스킬 불필요. 전체 issue workflow는 Hermes `github-dev-flow` 스킬이 주도.

#### 4. 기존 산출물 보존

기존 `features/` 및 `features/archive/` 내 디렉토리명은 변경하지 않음. archive된 feature는 기존 명명 그대로 보존하며, 새로운 issue-based 명명은 이후 작업부터 적용.

## Consequences

### Positive

- 모든 작업의 GitHub issue ↔ PR ↔ ADR 단일 추적 체인 확보
- 정본-실무 정합성 확보 (AGENTS.md, agent_dev_guide.md, 스킬 파일 동기화)
- `.opencode/` repo 추적으로 에이전트 설정 버전 관리 가능
- 단일 에이전트(OpenCode) 집중으로 설정 단순화 및 크로스 에이전트 불일치 제거
- 외부 오케스트레이션 레이어(Hermes)가 OpenCode를 호출할 때도 동일한 issue 컨벤션 적용

### Negative / Constraints

- 사소한 변경(오타 수정 등)도 GitHub issue 생성 오버헤드 발생 — 하지만 추적 가능성 보장의 대가
- 기존 문서(archive, HISTORY.md 등)의 feature 기반 명명은 영구 보존됨 → 읽을 때 혼란 가능
- `.hermes/` 스킬(github-dev-flow 등)은 여전히 비추적 — 외부 오케스트레이션 레이어의 문서가 repo 밖에 존재할 수 있음
- 마이그레이션 과도기(ADR-0046 반영 전까지 작성된 문서)와의 불일치

### Follow-up Impact

- AGENTS.md §3·§4·§8 업데이트 필요
- agent_dev_guide.md Step 1~5 명명 규칙 업데이트 필요
- `docs/adr/README.md` 인덱스 포맷: Feature 필드 `issue #N` 패턴 표준화
- `features/HISTORY.md` 포맷: 향후 항목부터 `issue #N` 기반으로 전환
- `agent/*.md`에 `write: true` 설정 추가하여 review 에이전트의 artifact 영속화 지원

## References

- AGENTS.md §3 (5-step feature workflow): 기존 feature-based 정본
- `docs/agent_dev_guide.md`: 기존 feature-based 실무 how-to
- Hermes `github-dev-flow` 스킬 (`.hermes/`, gitignored): 전체 issue workflow 오케스트레이션
- AGENTS.md §7 (외부 client entry points): Hermes ↔ OpenCode 레이어 분리
