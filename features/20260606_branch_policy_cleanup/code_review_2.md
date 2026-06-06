# Code Review 2 (manual) — PR #136

## Summary
모델 기반 리뷰(minimax-m3)는 분석 완료 단계까지 진행했으나 `code_review_2.md` 파일 작성은 실패. 직접 정적 검증 + 보안 검토 수행. **결함 없음 — 머지 가능.**

## 검증 절차

```bash
cd /Users/ds.im/workspace/wikihub-feat-130

# 1. Bash syntax
bash -n scripts/release.sh
bash -n scripts/bootstrap_version.sh
# → 둘 다 OK

# 2. Permission audit
stat -f '%Sp' scripts/release.sh scripts/bootstrap_version.sh
# → 755 755 (둘 다 rwxr-xr-x)
# bootstrap_version.sh 는 처음 commit 시 git index 가 100755 였으나
# working tree 가 711 이 되었던 현상 — chmod 755 로 정정 (git add -A 효과)

# 3. shellcheck
command -v shellcheck
# → not installed (skip)

# 4. VERSION / changelog / README 포맷
xxd _system/VERSION
# → 302e 312e 3131 0a  ("0.1.11\n" — 4 bytes, trailing newline)

grep -n 'img.shields.io/badge/Status' README.md
# → line 11: Status-v0.1.11%20released-green
```

## Findings

### 보안 (Security)

| 항목 | 평가 | 비고 |
|---|---|---|
| 실행 권한 | ✓ | 755 (rwxr-xr-x), 비-root 실행 가능 |
| force-push 보호 | ✓ | canary tag 만 force (lightweight, 정상) |
| Python heredoc eval 위험 | ✓ | `python3 -c "..."` 패턴, bash 변수 보간으로 전달되는 변수는 `'$VAR'` quoted — injection 방어 |
| 입력 검증 | ✓ | LATEST_TAG `v[0-9]+\.[0-9]+\.[0-9]+$` regex filter |
| 변수 injection | ✓ | `'$NEXT_VERSION'`, `'$TODAY'`, `'$DRY_RUN'`, `'$CHANGELOG_FILE'` 모두 single-quoted |

### 스키마 (Schema)

| 항목 | 포맷 | 일치? |
|---|---|---|
| VERSION | `x.y.z\n` (4 bytes) | ✓ |
| changelog entry | `## [vX.Y.Z] — YYYY-MM-DD (state)` | ✓ (canary 일관성) |
| README badge | `img.shields.io/badge/Status-vX.Y.Z%20<state>-<color>` | ✓ (%20 URL-encoding 정상) |
| branch/tag 명명 | `vX.Y.Z` semver | ✓ |

### Timeout / 에러 처리 (수동 검토)

| 시나리오 | 동작 | OK? |
|---|---|---|
| `git pull --ff-only` 실패 | `warn` (스크립트 계속, stale 일 수 있으나 안전) | ✓ |
| `git push` 실패 | `set -e` 로 즉시 `die` (commit 됐는데 push 실패 → partial state) | ⚠ MEDIUM |
| Python heredoc 실패 | `python3` exit code 비-0 → `set -e` 로 `die` | ✓ |
| VERSION 파일 부재 | `die` 명시 | ✓ |
| changelog 부재 | `die` 명시 | ✓ |
| README 부재 | `die` 명시 | ✓ |
| Status 배지 부재 | `die` 명시 | ✓ |
| `git diff --cached --quiet` (no staged changes) | `die` (doc update 모두 적용 검증) | ✓ |

#### [MEDIUM] Partial state — commit 됐는데 push 실패

`set -euo pipefail` 적용 + `git push` 직전 commit + 직후 push. push 실패 시:
- local main HEAD: bootstrap commit 존재
- origin main: 변경 없음
- local vX.Y.Z branch + canary tag: 생성됐지만 push 안 됨
- 스크립트 die → 사용자 개입 필요

**현재 동작**: 사용자가 push 실패 로그 보고 manual retry 가능. **개선 가능성**: `git push --atomic` 또는 push 실패 시 cleanup (reset) 옵션. 다만 release.sh 의 post-release 단계도 동일 패턴을 사용하므로 v0.1.12 release 전 정합성 개선 범위 밖 — 별도 ADR/이슈로 추출 권장.

**판단**: MEDIUM 이지만 머지 차단 사유는 아님 (현행 release.sh 와 동일 위험도).

### Code Quality (수동 검토)

| 항목 | 평가 | 비고 |
|---|---|---|
| 중복 코드 (release.sh / bootstrap_version.sh 의 helper) | ⚠ LOW | `die`, `info`, `warn`, `run_or_dry` 4개 함수 100% 중복. `scripts/_lib/release_helpers.sh` 추출 가능 |
| 명명 일관성 | ✓ | LATEST_TAG, NEXT_VERSION, NEXT_VERSION_PLAIN, NEXT_BRANCH 일관 |
| shellcheck warning 가능성 | ⚠ LOW | `local` 미사용 (top-level var), SC2155 (declare and assign) 가능. test 환경에 shellcheck 없어 미확인 |
| 한글/이모지 출력 terminal 호환성 | ✓ | UTF-8 출력, 한국어 status message |

#### [LOW] Helper 함수 중복

`scripts/_lib/release_helpers.sh` 추출 + `source` 패턴 도입 가능. 다만 이번 PR 의 핵심은 정책 분리고 refactor 범위 최소화 원칙. 별도 후속 작업.

**판단**: LOW, 머지 차단 사유 아님. follow-up 이슈로 분리 가능.

## 결론

**MEDIUM 1건** (push 실패 시 partial state) + **LOW 1건** (helper 중복). 둘 다 머지 차단 사유 아님. 사용자 확인 후 머지 진행.

### Follow-up 권장

1. **Partial state** (MEDIUM): `git push --atomic` 도입 또는 cleanup 패턴 — 별도 issue
2. **Helper 중복** (LOW): `scripts/_lib/release_helpers.sh` 추출 — 별도 issue
3. **shellcheck CI** 도입 (현 환경 미설치) — 별도 issue
