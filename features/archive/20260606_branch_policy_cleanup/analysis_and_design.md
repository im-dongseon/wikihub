approved: 2026-06-06

# Analysis & Design: 브랜치 정책 cleanup/bootstrap 분리

## 분석

### 현행 진단

`fc99d8b` (v0.1.12) 의 `scripts/release.sh` 는 release 완료 후 자동으로 다음 버전 브랜치 + canary tag 를 생성한다 (라인 185~244). 이 정책은 두 가지 문제를 가진다:

1. **고아 브랜치 (orphan branch)**: release 직후 후속 이슈/feature 가 0개여도 `refs/heads/v0.1.13` 가 생성된다. v0.1.13 에 squash 할 feature 가 없으면 branch 는 빈 채로 남는다.
2. **canary tag 의 trace 가치 손실**: canary tag 는 main HEAD(= v0.1.12 release commit) 의 patch+1 인 v0.1.13 HEAD 에 즉시 고정된다. v0.1.13 에 squash 가 일어나기 전까지 canary 는 release commit 을 가리키는 별 의미 없는 ref 다.

또한 release.sh 의 책임이 두 가지(cleanup + bootstrap) 로 섞여 있어 단위 테스트와 dry-run 이 어렵다. 두 동작은 트리거 시점(release vs. next-feature) 도 다르다.

### 영향 범위 (수정 대상)

| 파일 | 현 상태 | 변경 |
|---|---|---|
| `scripts/release.sh` | cleanup + bootstrap 통합 (246 lines) | cleanup 만 유지 (대략 200 lines 로 축소) |
| `scripts/bootstrap_version.sh` | 부재 | **신규** — release.sh post-release 부분 + 문서 갱신 통합 |
| `AGENTS.md` | §3 Step 5 의 "release.sh 자동 cleanup/bootstrap" 설명 | cleanup 만으로 축소, bootstrap 별도 안내 |
| `docs/agent_dev_guide.md` | post-release ref 상태 + hotfix 흐름 | post-release ref 상태 (cleanup 만) + 새 "Bootstrap 절차" 절 추가 |
| `.hermes/skills/github/github-dev-flow/SKILL.md` | Step 4 worktree 생성 | `origin/{base_branch}` 부재 감지 → `bootstrap_version.sh` 자동 호출 |
| `docs/changelog.md` | v0.1.12 (canary/released) 만 | v0.1.13 (canary) entry 추가 (bootstrap 시점에 doc 갱신 가능) |

## 설계

### 책임 분리

```
release.sh v0.1.12
  ├─ preflight (HARD 3종)
  ├─ Action 4: merge v0.1.12 → main --no-ff
  ├─ Action 5: tag v0.1.12 (annotated) + latest --force
  ├─ Cleanup:
  │   ├─ refs/heads/v0.1.12 삭제 (local + remote)
  │   └─ refs/tags/canary 삭제 (local + remote)
  └─ DONE — main HEAD = v0.1.12 = latest
```

```
bootstrap_version.sh
  ├─ LATEST_TAG=v0.1.12 (방금 released) → NEXT=v0.1.13 (patch+1)
  ├─ git checkout main && git pull --ff-only
  ├─ Doc 갱신:
  │   ├─ _system/VERSION: 0.1.12 → 0.1.13
  │   ├─ docs/changelog.md: ## [v0.1.13] (canary) entry
  │   ├─ README.md: Status 배지 v0.1.13 (canary)
  │   └─ docs/roadmap.md: "현재 진행" v0.1.13
  ├─ git add + commit "chore(bootstrap): v0.1.13 시작"
  ├─ git branch v0.1.13 (main HEAD) + push
  ├─ git tag -f canary v0.1.13 + force-push
  └─ checkout v0.1.13
```

### 트리거

`bootstrap_version.sh` 는 두 가지 방법으로 호출 가능:

1. **수동**: 사용자가 release 후 명시적으로 호출
2. **자동**: `github-dev-flow` Step 4 (worktree 생성) 진입 시 `origin/{base_branch}` 가 부재하면 자동 호출

```bash
# github-dev-flow Step 4 진입부
git fetch origin {base_branch} 2>/dev/null
if ! git rev-parse --verify "origin/{base_branch}" 2>/dev/null; then
  echo "[bootstrap] {base_branch} not found on remote — release 후 첫 feature."
  bash scripts/bootstrap_version.sh
fi
gh issue develop <N> -n feature/issue-<N> --base {base_branch}
```

### Hotfix

변경 없음. `refs/tags/vX.Y.Z` (annotated, main HEAD) 에서 임시 hotfix 브랜치 분기.

### Before → After

#### release.sh

| Before (fc99d8b) | After (이 PR) |
|---|---|
| `cleanup` + `bootstrap` (60 lines) | `cleanup` only (~20 lines) |
| `NEXT_VERSION` 계산 (line 206-210) | 제거 |
| 새 branch 생성 (line 216-220) | 제거 |
| canary tag 재생성 (line 221) | 제거 |
| `checkout $NEXT_VERSION` (line 230) | 제거 |
| 표시 메시지 (line 232-245) | cleanup 결과만 표시 |

#### docs/agent_dev_guide.md

**Before** (line 202-206):
```
- `main HEAD = refs/tags/vX.Y.Z = refs/tags/latest` (= 동일 merge commit M)
- `refs/heads/v0.X.Y` + `refs/tags/canary` **삭제**
- `main HEAD` 에서 최신 tag patch+1 로 **새 버전 브랜치 + canary tag 생성**
```

**After**:
```
- `main HEAD = refs/tags/vX.Y.Z = refs/tags/latest` (= 동일 merge commit M)
- `refs/heads/v0.X.Y` + `refs/tags/canary` **삭제** (cleanup only)
- 다음 버전 시작은 `scripts/bootstrap_version.sh` 수동 호출 또는
  `github-dev-flow` Step 4 진입 시 자동 호출
```

#### github-dev-flow Step 4

**Before** (line 80-85):
```bash
git fetch origin {base_branch}
gh issue develop <number> -n feature/issue-<number> --base {base_branch}
git worktree add ../{repo_name}-feat-<number> -b feature/issue-<number> origin/feature/issue-<number>
cd ../{repo_name}-feat-<number>}
```

**After**:
```bash
git fetch origin {base_branch}
# Bootstrap if {base_branch} doesn't exist on remote (post-release first feature)
if ! git rev-parse --verify "origin/{base_branch}" 2>/dev/null; then
  echo "[bootstrap] {base_branch} 부재 — scripts/bootstrap_version.sh 자동 호출"
  bash scripts/bootstrap_version.sh
fi
gh issue develop <number> -n feature/issue-<number> --base {base_branch}
git worktree add ../{repo_name}-feat-<number> -b feature/issue-<number> origin/feature/issue-<number}
cd ../{repo_name}-feat-<number>}
```

## 미결 사항

없음. 모든 결정은 user 와 합의 완료.

## Definition of Done

- [ ] `release.sh` post-release 6, 7 단계 제거 (cleanup only)
- [ ] `scripts/bootstrap_version.sh` 신규 — doc 갱신 + 새 branch + canary 자동
- [ ] `AGENTS.md` §3 Step 5 / §8 Tag 운영 표 갱신
- [ ] `docs/agent_dev_guide.md` post-release ref + bootstrap 절차 갱신
- [ ] `github-dev-flow` Step 4 auto-trigger 추가
- [ ] `changelog.md` v0.1.13 (canary) entry (bootstrap 시 사용)
- [ ] dry-run 검증: `release.sh --dry-run v0.1.12` 정상 종료
- [ ] Review 1/2 (background) 통과
- [ ] PR 생성
