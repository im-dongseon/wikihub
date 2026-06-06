# WikiHub Maintainer Guide (AI Agent 공통) v0.1.0

WikiHub 시스템 설계·개발·배포를 위한 최상위 거버넌스. Claude Code · OpenCode · Gemini · Codex · Hermes 등 모든 에이전트가 본 파일을 정본으로 참조. 운영 환경(live wikihub instance)에서 위키를 다루는 agent는 [`_system/wiki-schema.md`](_system/wiki-schema.md) (Operator Guide)로 전환.

> 본 문서는 **얕은 지도**. 5단계 워크플로우 실무 how-to / git 액션 5단계 명령 / 리뷰 규칙 등은 [docs/agent_dev_guide.md](docs/agent_dev_guide.md) 에 위임.

## 0. Quick map

| 영역 | 정본 |
|---|---|
| [docs/agent_dev_guide.md](docs/agent_dev_guide.md) | 5단계 Step 1~5 실무 how-to (깊음) |
| [docs/karpathy-guidelines.md](docs/karpathy-guidelines.md) | 코딩 행동 4원칙 |
| [docs/adr/NNNN-*.md](docs/adr/) | 아키텍처 결정의 정본 |
| [docs/issue-authoring-guide.md](docs/issue-authoring-guide.md) | GitHub 이슈 8섹션 템플릿 |
| [docs/changelog.md](docs/changelog.md) + `_system/VERSION` | 릴리스 누적 변경 |
| [docs/roadmap.md](docs/roadmap.md) | 향후 계획 (시점 확정 아님) |
| [features/HISTORY.md](features/HISTORY.md) | 운영 history (release 시 append) |
| [docs/mcp-setup.md](docs/mcp-setup.md) | 외부 MCP client 셋업 (회사 망 fallback 포함) |
| [CLAUDE.md](CLAUDE.md) | Claude Code 특화 (도구 선택, Agent tool) |

## 1. Architecture zones — 절대 규칙

| Zone | 위치 | 역할 | 누가 건드리는가 |
|---|---|---|---|
| **Development** | 루트 (`features/`, `docs/`, `install.sh`, `scripts/`, `AGENTS.md`) | 시스템을 만드는 공장 | 메인테이너(agent) |
| **Operations** | `_system/` | 시스템이 돌아가는 엔진 — 정본 룰 + 명령어 playbook | `install.sh` 가 fetch·갱신. **agent는 운영 인스턴스(OCI)일 때만 read** |

- **에이전트가 Development Zone 에서 작업할 때 `_system/` 을 직접 수정하지 말 것.** 변경은 §3 의 Step 1~5 를 거쳐 git workflow + `install.sh` 로만 운영에 주입.
- **Vault 외부화**: 원본 데이터(Drive / NAS 파일 등)는 `wikihub/` 외부. `wikihub/` 자체는 `_system/`(정본) + `wiki/`(통합 위키)만 보유 (ADR-0034 data-first layout).
- **에이전트가 운영 인스턴스에서 일할 때**(`ssh wikihub-oci` 류) — `_system/wiki-schema.md` 가 정본.

## 2. 코딩 행동 원칙 (한 줄 요약)

자세: [docs/karpathy-guidelines.md](docs/karpathy-guidelines.md). 충돌 시 본 §3 메소드론이 우선.

1. **Think Before Coding** — 가정을 명시, 모호하면 멈추고 묻는다.
2. **Simplicity First** — 요청 외 기능·추상화 금지.
3. **Surgical Changes** — "설계서에 없는 추가 변경은 하지 말 것."
4. **Goal-Driven Execution** — DoD 가 있는 작업만 받아들인다.

## 3. 5-step feature workflow

**플로우**: Plan → Analysis & Design → Implementation → (Review) → (Deploy) → archive. Step 4·5 는 조건부 생략 가능 (생략 결정은 Step 1 plan.md 에 사전 선언). 분기 base = **`origin/<현재 버전 브랜치>`** (예: `origin/v0.1.12`) — main 직접 분기·commit 금지. 버전 브랜치는 release 시 `release.sh`가 cleanup 하므로, 다음 사이클 시작은 첫 feature PR 시 `github-dev-flow` Step 4 가 `scripts/bootstrap_version.sh` 를 자동 호출한다. **메서드론 정본은 본 §3**, 실무 how-to / git 액션 5단계 / 리뷰 규칙 / HISTORY.md 형식은 [agent_dev_guide §3](docs/agent_dev_guide.md#5단계-feature-based-workflow) 참조.

| Step | 산출물 | 진입 조건 | 종료 |
|---|---|---|---|
| 1 Plan | `features/[YYYYMMDD]_[feat_id]/plan.md` | — | 사용자 확정 |
| 2 AD | `analysis_and_design.md` (optional `design_review_N.md`) | — | `approved: YYYY-MM-DD` 마커 (사용자 명시 승인 필수) |
| 3 Impl | `_system/commands/*.md`, `_system/wiki-schema.md`, `scripts/*`, `install.sh` 등 | Step 2 승인 | 설계서 모든 항목 반영 |
| 4 Review | `code_review_N.md` (생략 가능) | Step 3 완료 | 결함 없음 |
| 5 Deploy | squash → v0.X.Y, canary force-update, (release 시) main merge + tag | 사용자 `"배포 진행해줘"` | 운영 반영 + archive 이동 |

- **ADR 추출**: Step 2 의 미결 사항이 결정되면 `docs/adr/NNNN-{slug}.md` 1개 (결정 N개 = ADR N개). ADR이 정본 — `analysis_and_design.md` 의 미결 표는 옵션 탐색 과정만 보존.
- **Feature 종료**: 완료 시 `git mv features/[id] features/archive/[id]` (archive 위치 자체가 종료 마커). feature 브랜치·worktree 강제 정리.

## 4. 버전 관리 — Atomic Change

- **버전 명명**: 문서·tag = `v{X.Y.Z}`, 배포 도구 인자 = `{X_Y_Z}`. WikiHub 시작 = v0.1.0.
- **Atomic Change**: 한 feature = 한 목적. 부수 이슈는 새 feature ID 발급.
- **feature 디렉토리**: `features/[YYYYMMDD]_[feat_id]/` (KST 날짜, 소문자+언더스코어).
- **features/ 라이프사이클**: 루트 = 진행 중, `features/archive/` = 완료.

## 5. Tag 운영 의미 — main 직접 commit 금지

| Tag | 성격 | 가리키는 commit | 운영 의미 |
|---|---|---|---|
| `vX.Y.Z` | annotated, **immutable** | main 의 merge commit (M) | release 영구 record, rollback target. force-push 금지 (GitHub Ruleset) |
| `latest` | lightweight, force-move | 가장 최근 release commit | production default |
| `canary` | lightweight, force-update | 현재 버전 브랜치 HEAD | pre-production 검증 trace. `install.sh --branch canary`. **fetch 시 `--force` 필요** (git 2.20+) |

Release 직후: `release.sh` 가 cleanup 만 자동 수행.
- `refs/heads/v0.X.Y` (version branch) + `refs/tags/canary` **삭제**
- `main HEAD = vX.Y.Z = latest` 3 ref 동일 commit (immutable record)
- **새 버전 브랜치/canary 자동 생성 X** — bootstrap 은 on-demand

**다음 사이클 시작** (release 직후 첫 feature 작업 시):
- `github-dev-flow` Step 4 가 `origin/{base_branch}` 부재를 감지 → `scripts/bootstrap_version.sh` 자동 호출
- 수동 호출: `bash scripts/bootstrap_version.sh` (release 후 바로 다음 사이클 시작 시)

**hotfix 필요 시**: `refs/tags/vX.Y.Z` (annotated, main HEAD) 에서 임시 hotfix 브랜치 분기. 5-액션 git workflow 전체: [agent_dev_guide §Step 5](docs/agent_dev_guide.md#step-5-deployment-배포--조건부-생략-가능).

## 6. Release 시 동시 갱신 문서 (issue #114, `scripts/release.sh` preflight)

| 문서 | 갱신 | preflight |
|---|---|---|
| `_system/VERSION` | `= X.Y.Z` | **HARD** (release tag 일치) |
| `docs/changelog.md` | `## [vX.Y.Z]` `(canary)`→`(released)` + 날짜 | **HARD** |
| `README.md` 배지 | Status/Version canary→vX.Y.Z released | **HARD** |
| `docs/roadmap.md` | "현재 진행"→"누적 완료(release)" | WARN |
| `features/HISTORY.md` | 항목 append | WARN |

HARD 3종 미충족 시 `release.sh` 가 비가역 merge 전에 `die` (escape hatch: `--skip-doc-check`).

## 7. 외부 client entry points (v0.1.10+, ADR-0043)

| Entry | 책임 | mutation 권한 |
|---|---|---|
| **Hermes CLI skill** (`/wh-ingest`, `/wh-lint`, `/wh-query`, `/wh-setup`) | LLM-mediated playbook — 의미 검색 + cross-ref 추론 + `analyses` 자동 저장 | `wiki/`, `_state/`, OAuth credential 모두 mutation 가능 |
| **MCP server** (`scripts/wikihub_mcp.py`) | deterministic primitive (LLM 호출 0) — 외부 client (Claude Desktop / Cline) 가 SSH 로 spawn | **`wiki/` read 전용**. mutation은 Hermes skill 전유 |

**레이어 분리 invariant**: `wikihub_mcp.py` 안에서 LLM 호출 0 (recursive LLM 회피). semantic synthesis 는 MCP client 측 LLM 책임.

## 8. Git Worktree

병렬 작업(서브에이전트 / cmux 패널) 시 필수. feature 분기 base = `origin/<현재 버전 브랜치>`. 패턴 + 명령: [agent_dev_guide §Worktree](docs/agent_dev_guide.md#git-worktree-활용).

## 9. GitHub 이슈 작성

에이전트 작성 이슈는 **제목 `[<AGENT-ID>] <한글 요약>`** + 라벨 `agent` + `priority: high|medium|low` + 8섹션 본문(메타/배경/현행·문제/영향·리스크/제안/영향 범위/DoD/참조). 정본: [docs/issue-authoring-guide.md](docs/issue-authoring-guide.md). 추측 금지 — 소스·코드 read 후 작성.

## 10. ADR

`docs/adr/NNNN-{kebab-case-slug}.md`, Status `Accepted` / `Superseded` / `Deprecated`. 결정 변경 시 supersede (삭제 금지). 컨벤션 + 인덱스: [docs/adr/README.md](docs/adr/README.md).

---

## OpenCode 세션 메모

- **Config**: `.opencode/opencode.json` (현재 `plugin: ["list"]`). OpenCode plugin API: <https://opencode.ai>.
- **Gitignored (절대 commit 금지)**: `.opencode/`, `.claude/`, `.agents/`, `.hermes/`, `skills-lock.json`, `.env`, `wikihub.yaml`, `.credentials/`, `*token_*.json` — 로컬 세션 산출물·자격증명.
- **사용 가능한 skills** (project-local, OpenCode 가 자동 detect):
  - `brainstorming`, `writing-plans`, `subagent-driven-development` — [obra/superpowers](https://github.com/obra/superpowers) (해시는 `skills-lock.json`, gitignored)
  - `fix-wikihub-issue` — GitHub 이슈 → PR/canary close 풀 워크플로우 (이슈 번호 언급 시 자동 트리거)
  - `karpathy-guidelines` — 코딩 행동 원칙 (4원칙)
- **세션 시작 권장**: "AGENTS.md 를 읽고 현재 작업 컨텍스트에 맞춰 적용해줘" + 관련 docs/adr 명시. Issue 작업이면 `fix-wikihub-issue` 스킬을 명시 호출.
- **CLAUDE.md 와 동등한 OpenCode 전용 노트가 필요하면** `OPENCODE.md` 를 추가하고 본 §0 Quick map 에서 링크.
