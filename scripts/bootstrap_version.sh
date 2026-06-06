#!/usr/bin/env bash
# bootstrap_version.sh — On-demand start of the next version cycle
#
#   AGENTS.md §3 Step 5: v0.1.13+ 정책. release.sh 는 cleanup 만 담당하고,
#   새 버전 브랜치 + canary tag 의 시작은 본 스크립트가 처리.
#
# Usage: bootstrap_version.sh [--dry-run]
#
#   --dry-run    Print intended actions without modifying repo state.
#
# Prerequisites (호출자 책임):
#   - main HEAD = last released version (refs/tags/<last> = refs/tags/latest = main HEAD)
#   - 작업 트리 clean (스크립트가 강제 검증)
#   - main 브랜치에 checkout 되어 있음 (스크립트가 강제 검증)
#
# What it does:
#   1. main HEAD 의 VERSION → patch+1 bump
#   2. docs/changelog.md 에 next (canary) entry 추가
#   3. README.md Status 배지 → next (canary) 로 갱신
#   4. 변경분을 main 에 commit "chore(bootstrap): v<next> 시작"
#   5. main HEAD 에서 v<next> 브랜치 생성 + push
#   6. canary tag → v<next> HEAD (force)
#   7. v<next> 브랜치로 checkout
#
# 자동 호출: github-dev-flow Step 4 가 `origin/<base_branch>` 부재 시 호출.
# 수동 호출: `bash scripts/bootstrap_version.sh` (release 후 다음 작업 시작 시).

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
DRY_RUN=false

usage() {
    sed -n '3,15p' "$0" | sed 's/^#//'
    exit 0
}

die() {
    echo "[ERROR] $*" >&2
    exit 1
}

info() {
    echo "[INFO] $*"
}

warn() {
    echo "[WARN] $*" >&2
}

run_or_dry() {
    if "$DRY_RUN"; then
        echo "[DRY-RUN] $*"
    else
        echo "[RUN] $*"
        "$@"
    fi
}

# --- Argument parsing ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help) usage ;;
        *) die "Unknown arg: $1 (try --help)" ;;
    esac
done

# --- Preflight: clean working tree on main ---
command -v git >/dev/null 2>&1 || die "git is required"

GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "Not inside a git repository"
cd "$GIT_ROOT"

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
if [[ "$CURRENT_BRANCH" != "main" ]]; then
    die "Must be on 'main' branch to bootstrap next version (현재: $CURRENT_BRANCH). 'git checkout main' 후 재시도."
fi

# Stale local guard — release.sh 가 cleanup 만 하므로 stale local ref 가 남을 수 있음
run_or_dry git fetch --tags origin main
run_or_dry git pull --ff-only origin main 2>/dev/null || \
    warn "Could not fast-forward main. 로컬 main 이 stale 일 수 있음 — 'git pull --rebase origin main' 후 재시도."

if ! "$DRY_RUN"; then
    if [[ -n "$(git status --porcelain 2>/dev/null | grep -v '^?? \.hermes/')" ]]; then
        die "Working tree has modified tracked files. Clean or stash before bootstrap."
    fi
fi

# --- Calculate next version (patch+1 from highest v* tag) ---
LATEST_TAG="$(git tag -l 'v*' --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -1)"
if [[ -z "$LATEST_TAG" ]]; then
    die "No version tag found to determine next version."
fi
NEXT_VERSION="$(echo "$LATEST_TAG" | awk -F. '{print $1"."$2"."($3+1)}')"
NEXT_BRANCH="$NEXT_VERSION"
NEXT_VERSION_PLAIN="${NEXT_VERSION#v}"

info "Latest released tag : $LATEST_TAG"
info "Next version       : $NEXT_VERSION (patch+1)"

# Check if next branch already exists (idempotency guard)
if git rev-parse --verify "refs/heads/$NEXT_BRANCH" 2>/dev/null; then
    die "Local branch '$NEXT_BRANCH' already exists — 이미 bootstrap 완료된 사이클. 다음 사이클을 시작하려면 추가 작업이 필요하지 않습니다."
fi
if git rev-parse --verify "origin/$NEXT_BRANCH" 2>/dev/null; then
    die "Remote branch 'origin/$NEXT_BRANCH' already exists — 이미 bootstrap 완료된 사이클. fetch 후 checkout 하세요: 'git checkout $NEXT_BRANCH'."
fi

# --- Step 1: Bump _system/VERSION ---
VERSION_FILE="_system/VERSION"
if [[ ! -f "$VERSION_FILE" ]]; then
    die "$VERSION_FILE not found at repo root."
fi
CUR_VER="$(tr -d '[:space:]' < "$VERSION_FILE")"
if [[ "$CUR_VER" != "${LATEST_TAG#v}" ]]; then
    die "VERSION file ($CUR_VER) != latest released tag ($LATEST_TAG). release.sh preflight 가 정상 완료된 상태에서만 bootstrap 가능."
fi
info "Bumping _system/VERSION: $CUR_VER → $NEXT_VERSION_PLAIN"
run_or_dry bash -c "echo '$NEXT_VERSION_PLAIN' > '$VERSION_FILE'"

# --- Step 2: docs/changelog.md — add (canary) entry for next version ---
# Use Python heredoc (more reliable for Unicode than inline sed/awk).
CHANGELOG_FILE="docs/changelog.md"
if [[ ! -f "$CHANGELOG_FILE" ]]; then
    die "$CHANGELOG_FILE not found at repo root."
fi
if grep -q "^## \[$NEXT_VERSION\]" "$CHANGELOG_FILE"; then
    die "$CHANGELOG_FILE 이미 '$NEXT_VERSION' entry 가 존재 — 수동 확인 후 정리 필요."
fi
info "Adding $NEXT_VERSION (canary) entry to docs/changelog.md"
TODAY="$(date +%Y-%m-%d)"
run_or_dry python3 -c "
import sys
path = '$CHANGELOG_FILE'
next_version = '$NEXT_VERSION'
today = '$TODAY'
dry_run = '$DRY_RUN' == 'true'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()
out = []
inserted = False
for line in lines:
    if not inserted and line.startswith('## [v') and ']' in line and '[v' in line:
        # Insert new entry BEFORE this existing one
        out.append('## [' + next_version + '] — ' + today + ' (canary)\n')
        out.append('\n')
        out.append('### \ucd94\uac00 (Added)\n')
        out.append('\n')
        out.append('- (bootstrap \u2014 first feature commit \ubd80\ud130 entry \ub204\uc801)\n')
        out.append('\n')
        out.append('---\n')
        out.append('\n')
        inserted = True
    out.append(line)
if not inserted:
    sys.exit('ERROR: no existing ## [vX.Y.Z] line found in changelog')
if not dry_run:
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(out)
else:
    print('[DRY-RUN] would insert before first existing vX.Y.Z entry')
"

# --- Step 3: README.md — Status badge update ---
README_FILE="README.md"
if [[ ! -f "$README_FILE" ]]; then
    die "$README_FILE not found at repo root."
fi
if ! grep -q 'img.shields.io/badge/Status' "$README_FILE"; then
    die "$README_FILE 에 Status 배지 (img.shields.io/badge/Status) 가 없음 — README 포맷 변경 필요."
fi
info "Updating $README_FILE Status badge → $NEXT_VERSION canary"
run_or_dry bash -c "sed -i.bak -E 's|img.shields.io/badge/Status-v[0-9]+\\.[0-9]+\\.[0-9]+%20[a-z-]+|img.shields.io/badge/Status-$NEXT_VERSION%20canary-orange|' '$README_FILE' && rm -f '$README_FILE.bak'"

# --- Step 4: docs/roadmap.md — manual update warning ---
ROADMAP_FILE="docs/roadmap.md"
if [[ -f "$ROADMAP_FILE" ]]; then
    if ! grep -q "$NEXT_VERSION" "$ROADMAP_FILE"; then
        warn "$ROADMAP_FILE 에 '$NEXT_VERSION' (현재 진행) entry 가 없음 — 수동으로 '현재 진행 ($NEXT_VERSION, 시작)' 섹션 추가 권장."
    fi
else
    warn "$ROADMAP_FILE not found at repo root. roadmap 갱신은 수동으로 처리."
fi

# --- Step 5: features/HISTORY.md — manual update warning ---
HISTORY_FILE="features/HISTORY.md"
if [[ -f "$HISTORY_FILE" ]]; then
    if ! grep -q "$NEXT_VERSION" "$HISTORY_FILE"; then
        warn "$HISTORY_FILE 에 '$NEXT_VERSION' 항목 없음 — release 시 append 되므로 지금은 무시 가능."
    fi
else
    warn "$HISTORY_FILE not found at repo root."
fi

# --- Step 6: Commit doc updates to main ---
info "Committing bootstrap changes to main"
run_or_dry git add "$VERSION_FILE" "$CHANGELOG_FILE" "$README_FILE"
if ! "$DRY_RUN"; then
    if git diff --cached --quiet; then
        die "No staged changes — bootstrap doc updates 가 모두 적용되지 않음."
    fi
fi
run_or_dry git commit -m "chore(bootstrap): $NEXT_VERSION 시작

- _system/VERSION: $CUR_VER → $NEXT_VERSION_PLAIN
- docs/changelog.md: $NEXT_VERSION (canary) entry
- README.md: Status 배지 → $NEXT_VERSION canary

release.sh post-release 정책 분리 (AGENTS.md §3 Step 5) 에 따라
수동 bootstrap. 다음 feature PR 부터 $NEXT_BRANCH 브랜치에 squash."

# --- Step 7: Create new version branch + canary tag ---
info "=== Bootstrap $NEXT_VERSION: create branch + canary tag ==="
run_or_dry git branch "$NEXT_BRANCH"
run_or_dry git tag -f canary "$NEXT_BRANCH"
run_or_dry git push origin "$NEXT_BRANCH"
run_or_dry git push origin refs/tags/canary --force

# --- Step 8: Switch to new version branch ---
run_or_dry git checkout "$NEXT_BRANCH"

# --- Final state display ---
info "=== bootstrap_version.sh complete ==="
echo ""
echo "Bootstrap $NEXT_VERSION 완료."
echo ""
echo "Ref state after bootstrap:"
echo "  main HEAD           = refs/tags/$LATEST_TAG (released)"
echo "  New version branch  = refs/heads/$NEXT_BRANCH (from main HEAD, +1 bootstrap commit)"
echo "  New canary tag      = refs/tags/canary → $NEXT_BRANCH HEAD"
echo ""
echo "다음 단계: github-dev-flow Step 4 (worktree + feature 작업) 시작."
echo ""
