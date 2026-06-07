# ADR-0047: Retire feature directory — GitHub issue as workflow single source

- **Status**: Accepted
- **Date**: 2026-06-08 (KST)
- **Feature**: governance transition (issue #N/A — ADR-0046 follow-up)
- **Supersedes**: 없음 (ADR-0046 §세부결정-4 "기존 산출물 보존"을 구체화)
- **Superseded by**: 없음

## Context

ADR-0046(issue-first workflow)에서 모든 작업을 GitHub issue 기반으로 전환했으나, workflow 산출물 디렉토리(`features/[YYYYMMDD]_issue<N>_<slug>/`)는 여전히 실무에서 사용 중이다. 실제로:

- Step 1 `plan.md`, Step 2 `analysis_and_design.md` 모두 GitHub issue body/comment로 대체 가능
- Step 4 `code_review_N.md`는 이미 `docs/reviews/issue-N/` 경로로 artifact화 (review agent 자동 기록)
- archive 이동 + `git mv` 오버헤드가 지속 발생
- `docs/release-history.md`는 release history append 전용으로 유지 가치 있음 (디렉토리 구조와 무관)

## Considered Options

- **(α) feature directory 폐기**: 신규 작업에서 `features/` 디렉토리 생성 금지. 산출물을 GitHub issue(plan, AD) + `docs/reviews/` (code review)로 분산 수용. `features/archive/`는 기존 기록 보존만 — 신규 항목 추가 금지.
- **(β) 현행 유지**: `features/issue<N>/` 디렉토리 계속 생성. 장점은 로컬 파일로 모든 산출물이 모여 있음.
- **(γ) 축소형 유지**: plan.md만 `features/`에 두고 AD/review는 issue/reviews로 이동. 디렉토리 구조는 유지하되 최소화.

## Decision

**채택**: (α) feature directory 폐기

**이유**:
- GitHub issue body가 plan.md 역할을 충분히 대체 (8섹션 템플릿에 모든 정보 포함)
- `analysis_and_design.md`는 issue comment로 작성 → PR 시 review link로도 활용 가능
- `docs/reviews/`는 이미 review agent가 자동 기록 — 중복 디렉토리 불필요
- `git mv features/... features/archive/...` 커맨드와 archive 라이프사이클 관리 오버헤드 제거
- workflow 단순화: feature 완료 = PR merge + issue close (추가 액션 없음)

**기각된 옵션의 단점**:
- (β): 새 정합성 갭 발생 — issue-first 정책과 feature dir 생성 사이 모순
- (γ): 반쪽짜리 단순화 — 디렉토리 생성/archive 이동 오버헤드가 여전히 존재

## Consequences

### Positive

- **issue = single source**: plan/AD/review trail이 issue 하나로 추적 가능
- **오버헤드 제거**: `mkdir -p features/...`, `git mv ... features/archive/...`, archive lifecycle 관리 불필요
- **review artifact 단일화**: `docs/reviews/issue-N/`만 유지 (feature dir vs reviews dir 이중화 해소)
- **원격 작업 friendly**: GitHub 웹 UI만으로 모든 workflow 산출물 작성 가능

### Negative / Constraints

- 로컬에 산출물 파일이 남지 않음 → 오프라인 접근 시 불편
- `features/archive/`는 기존 35개 항목에 대해 read-only 보존 — 혼동 가능
- `docs/release-history.md`는 유지하되, 신규 항목부터는 `issue #N` 기반 참조로 전환 (변경 없음 — ADR-0046에서 이미 전환 완료)

### Changes Required

- AGENTS.md §3 Step 테이블: plan.md → GitHub issue body, review dir 변경, archive 이동 제거
- AGENTS.md §4: `features/` 디렉토리 참조 제거
- AGENTS.md §6: `docs/release-history.md` WARN preflight — HISTORY.md는 유지되므로 preflight 그대로
- `docs/agent_dev_guide.md`: 전면 재작성 (Step 1~5 산출물 위치, archive 종료 처리, features 구조 섹션)
- `docs/adr/README.md`: template Feature 필드 기본값을 `issue #N`로 수정
- `docs/adr/template.md`: Feature 필드 기본 포맷 변경
