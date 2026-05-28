#!/usr/bin/env bash
# promote_canary.sh — Actions 1-3 of Step 5 deployment workflow
#   Squash merge feature → version branch, push + canary tag, cleanup
#
# Usage: promote_canary.sh [--dry-run] <version_branch> <feature_id> [commit_message]
#
#   <version_branch>  Target version branch (e.g., v0.1.10)
#   <feature_id>      Feature directory ID (e.g., 20260525_my_feature)
#   [commit_message]  Optional. If omitted, prompted from defaults
#
# Example: promote_canary.sh v0.1.10 20260525_my_feature
#
# AGENTS.md §3 Step 5 actions 1-3

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
DRY_RUN=false

usage() {
    sed -n '3,13p' "$0" | sed 's/^#//'
    exit 0
}

die() {
    echo "[ERROR] $*" >&2
    exit 1
}

info() {
    echo "[INFO] $*"
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
        *) break ;;
    esac
done

[[ $# -lt 2 ]] && die "Usage: $0 [--dry-run] <version_branch> <feature_id> [commit_message]"
VERSION_BRANCH="$1"
FEATURE_ID="$2"
shift 2
COMMIT_MSG="${1:-}"

# --- Pre-flight checks ---
command -v git >/dev/null 2>&1 || die "git is required"

# Validate version branch format
if [[ ! "$VERSION_BRANCH" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    die "Invalid version branch: '$VERSION_BRANCH'. Expected format: vX.Y.Z"
fi

# Ensure we're inside a git repo
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "Not inside a git repository"
echo "[INFO] Repository root: $GIT_ROOT"

# Check for dirty state
if ! "$DRY_RUN" && [[ -n "$(git status --porcelain 2>/dev/null | grep -v '^?? \.hermes/')" ]]; then
    die "Working tree has modified tracked files. Clean or stash before promote."
fi

# --- Action 1: Squash merge feature into version branch ---
info "=== Action 1: Squash merge feature/$FEATURE_ID -> $VERSION_BRANCH ==="

run_or_dry git fetch origin "$VERSION_BRANCH"
run_or_dry git checkout "$VERSION_BRANCH"

# Check if feature branch exists
FEATURE_BRANCH="feature/$FEATURE_ID"
if git rev-parse --verify "$FEATURE_BRANCH" 2>/dev/null; then
    echo "[INFO] Feature branch '$FEATURE_BRANCH' found locally"
elif git rev-parse --verify "origin/$FEATURE_BRANCH" 2>/dev/null; then
    echo "[INFO] Feature branch 'origin/$FEATURE_BRANCH' found, creating local tracking"
    run_or_dry git checkout -B "$FEATURE_BRANCH" "origin/$FEATURE_BRANCH"
    run_or_dry git checkout "$VERSION_BRANCH"
else
    die "Feature branch '$FEATURE_BRANCH' not found locally or remotely"
fi

# Detect previous squash commit message from branch if not provided
if [[ -z "$COMMIT_MSG" ]]; then
    # Try to extract from the feature branch's commits
    BRANCH_FIRST_COMMIT="$(git log --oneline "origin/$VERSION_BRANCH..$FEATURE_BRANCH" 2>/dev/null | tail -1 || true)"
    if [[ -n "$BRANCH_FIRST_COMMIT" ]]; then
        COMMIT_MSG="${BRANCH_FIRST_COMMIT#* }"
        echo "[INFO] Using first branch commit as message: $COMMIT_MSG"
    else
        COMMIT_MSG="chore($FEATURE_ID): automated promote ($VERSION_BRANCH)"
        echo "[INFO] Using default message: $COMMIT_MSG"
    fi
fi

run_or_dry git merge --squash "$FEATURE_BRANCH"
run_or_dry git commit --no-edit -m "$COMMIT_MSG" 2>/dev/null || {
    # If --no-edit fails (no changes), check if squash was empty
    if git diff --cached --quiet 2>/dev/null; then
        echo "[INFO] Squash produced no new changes (already up to date). Continuing."
        # Reset if we have staged nothing
        git reset --hard HEAD 2>/dev/null || true
    else
        run_or_dry git commit -m "$COMMIT_MSG"
    fi
}

SQUASH_SHA="$(git rev-parse HEAD)"
echo "[INFO] Squash commit: $SQUASH_SHA"

# --- Action 2: Push + canary tag ---
info "=== Action 2: Push version branch + canary tag force-update ==="

run_or_dry git push origin "$VERSION_BRANCH" --force-with-lease 2>/dev/null || \
    die "Force-push of '$VERSION_BRANCH' failed. Check lease or GitHub protection rules."

run_or_dry git tag -f canary
run_or_dry git push origin canary --force 2>/dev/null || \
    echo "[WARN] Canary tag push failed. Check GitHub tag protection rules."

# --- Action 3: Cleanup feature branch and worktree ---
info "=== Action 3: Feature branch/worktree cleanup ==="

# Check for worktree
WORKTREE_PATH="../wikihub-feat/$FEATURE_ID"
if [[ -d "$WORKTREE_PATH" ]]; then
    echo "[INFO] Found worktree at $WORKTREE_PATH"
    # Check worktree status
    WT_STATUS="$(git -C "$WORKTREE_PATH" status --porcelain 2>/dev/null || true)"
    if [[ -n "$WT_STATUS" ]]; then
        echo "[WARN] Worktree has uncommitted changes:"
        echo "$WT_STATUS"
        echo "[WARN] Skipping worktree removal. Handle manually."
    else
        run_or_dry git worktree remove "$WORKTREE_PATH"
        echo "[INFO] Worktree removed: $WORKTREE_PATH"
    fi
else
    echo "[INFO] No worktree at $WORKTREE_PATH"
fi

# Delete local feature branch
if git rev-parse --verify "$FEATURE_BRANCH" 2>/dev/null; then
    run_or_dry git branch -D "$FEATURE_BRANCH"
    echo "[INFO] Local branch '$FEATURE_BRANCH' deleted"
else
    echo "[INFO] Local branch '$FEATURE_BRANCH' not found (already clean)"
fi

# Delete remote feature branch
if git rev-parse --verify "origin/$FEATURE_BRANCH" 2>/dev/null; then
    run_or_dry git push origin --delete "$FEATURE_BRANCH" 2>/dev/null || \
        echo "[INFO] Remote branch '$FEATURE_BRANCH' not deleted (may not exist or permission)"
fi

info "=== promote_canary.sh complete ==="
echo ""
echo "Actions completed:"
echo "  1. Squash merged feature/$FEATURE_ID -> $VERSION_BRANCH ($SQUASH_SHA)"
echo "  2. Pushed $VERSION_BRANCH + canary tag force-updated"
echo "  3. Feature branch/worktree cleanup"
echo ""
echo "Next step: Run './scripts/release.sh $VERSION_BRANCH' when OCI canary is verified."
