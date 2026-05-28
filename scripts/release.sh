#!/usr/bin/env bash
# release.sh — Actions 4-5 of Step 5 deployment workflow
#   Merge version branch → main, create annotated tag, push
#
# Usage: release.sh [--dry-run] <version_branch> [description]
#
#   <version_branch>  Version branch to release (e.g., v0.1.10)
#   [description]     Optional release description (e.g., "2026-05-28 batch")
#                     If omitted, uses current date.
#
# Example: release.sh v0.1.10 "2026-05-28 batch"
#
# AGENTS.md §3 Step 5 actions 4-5

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
        *) break ;;
    esac
done

[[ $# -lt 1 ]] && die "Usage: $0 [--dry-run] <version_branch> [description]"
VERSION_BRANCH="$1"
shift
DESCRIPTION="${1:-}"

# --- Pre-flight checks ---
command -v git >/dev/null 2>&1 || die "git is required"

# Validate version branch format
if [[ ! "$VERSION_BRANCH" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    die "Invalid version branch: '$VERSION_BRANCH'. Expected format: vX.Y.Z"
fi

# Extract version tag from branch name (same string, but validate as semver)
VERSION_TAG="$VERSION_BRANCH"

# Ensure we're inside a git repo
GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "Not inside a git repository"
echo "[INFO] Repository root: $GIT_ROOT"

# Check for dirty state
if ! "$DRY_RUN" && [[ -n "$(git status --porcelain 2>/dev/null | grep -v '^?? \.hermes/')" ]]; then
    die "Working tree has modified tracked files. Clean or stash before release."
fi

# --- Action 4: Merge version branch into main ---
info "=== Action 4: Merge $VERSION_BRANCH -> main (--no-ff) ==="

run_or_dry git fetch origin "$VERSION_BRANCH" main
run_or_dry git checkout main

# Ensure main is up to date with origin/main
run_or_dry git pull --ff-only origin main 2>/dev/null || \
    warn "Could not fast-forward main. If first-time release, this may be expected."

# Check if version branch exists
if git rev-parse --verify "origin/$VERSION_BRANCH" 2>/dev/null; then
    echo "[INFO] Version branch 'origin/$VERSION_BRANCH' found"
elif git rev-parse --verify "$VERSION_BRANCH" 2>/dev/null; then
    echo "[INFO] Local branch '$VERSION_BRANCH' found (no remote)"
else
    die "Version branch '$VERSION_BRANCH' not found. Has promote_canary.sh been run?"
fi

# Perform merge --no-ff
run_or_dry git merge --no-ff "$VERSION_BRANCH" -m "Merge branch '$VERSION_BRANCH' into main"

MERGE_SHA="$(git rev-parse HEAD)"
echo "[INFO] Merge commit: $MERGE_SHA"

# --- Action 5: Annotated tag + latest tag + push ---
info "=== Action 5: Annotated tag + latest tag force-update + push ==="

# Build tag message
if [[ -z "$DESCRIPTION" ]]; then
    DESCRIPTION="Release $(date +%Y-%m-%d)"
fi
TAG_MESSAGE="$VERSION_TAG — $DESCRIPTION"

# Check if annotated tag already exists (immutable)
if git rev-parse --verify "refs/tags/$VERSION_TAG" 2>/dev/null; then
    EXISTING_SHA="$(git rev-parse "refs/tags/$VERSION_TAG")"
    if [[ "$EXISTING_SHA" != "$MERGE_SHA" ]]; then
        die "Annotated tag '$VERSION_TAG' already exists at $EXISTING_SHA (different from $MERGE_SHA). Tags are immutable — cannot overwrite. Did you already release this version?"
    else
        echo "[INFO] Tag '$VERSION_TAG' already exists at same commit — skipping creation."
    fi
else
    run_or_dry git tag -a "$VERSION_TAG" -m "$TAG_MESSAGE" "$MERGE_SHA"
    echo "[INFO] Annotated tag '$VERSION_TAG' created"
fi

# Update latest tag (force-update allowed)
run_or_dry git tag -f latest "$MERGE_SHA"

# Push main + tags
run_or_dry git push origin main "$VERSION_TAG"
run_or_dry git push origin latest --force 2>/dev/null || \
    warn "Latest tag force-push failed. Check GitHub tag protection rules."

# --- Post-release state display ---
info "=== release.sh complete ==="
echo ""
echo "Release $VERSION_TAG completed."
echo "  Merge commit : $MERGE_SHA"
echo "  Description  : $TAG_MESSAGE"
echo ""
echo "Ref state after release:"
echo "  main HEAD       = refs/tags/$VERSION_TAG = refs/tags/latest = $MERGE_SHA"
echo "  $VERSION_BRANCH = $(git rev-parse "$VERSION_BRANCH" 2>/dev/null || echo 'N/A') (previous HEAD, preserved)"
echo "  canary tag      = previous canary target (preserved until next squash)"
echo ""
echo "Next step: Notify operators to run 'install.sh --branch latest'"
