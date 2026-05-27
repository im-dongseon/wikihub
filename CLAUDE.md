# WikiHub Claude Code Guide (에이전트 특화 지침)

이 파일은 WikiHub 시스템에서 **Claude Code**가 사용하는 에이전트별 지침입니다.
공통 거버넌스와 워크플로우는 [AGENTS.md](AGENTS.md)를 따릅니다.

## 도구 선택

| 단계 | Claude Code 도구 |
|---|---|
| Step 2 (Analysis & Design) | Claude Code CLI 또는 Superpowers |
| Step 3 (Implementation) | Claude Code CLI |
| Step 4 (Code Review) | Claude CLI (새 터미널 탭에서 `claude` 실행) |

## Claude Agent Tool 활용

- **멀티에이전트 접근법**: Claude Agent tool로 병렬 리뷰 오케스트레이션 가능
  ```
  "두 에이전트가 병렬로 A는 성능, B는 보안 리뷰해줘"
  ```
- **worktree isolation**: 서브에이전트 검토/탐색 시 `isolation: "worktree"` 사용
  (Agent tool이 HEAD 기준 임시 worktree를 자동 생성·제거)

## GitHub 이슈 작성

- Agent ID: `CLAUDE-A`
- 기타 형식은 [AGENTS.md §9](AGENTS.md#9-github-이슈-작성-컨벤션-에이전트-공통) 및 [docs/issue-authoring-guide.md](docs/issue-authoring-guide.md) 참조
