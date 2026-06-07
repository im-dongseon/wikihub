#!/usr/bin/env bash
# release.sh — Actions 4-5 of Step 5 deployment workflow
#   Merge version branch → main, create annotated tag, push
#
# Usage: release.sh [--dry-run] [--skip-doc-check] <version_branch> [description]
#
#   <version_branch>  Version branch to release (e.g., v0.1.10)
#   [description]     Optional release description (e.g., "2026-05-28 batch")
#                     If omitted, uses current date.
#   --skip-doc-check  Bypass the release-doc preflight (issue #114). Escape hatch only.
#
# Example: release.sh v0.1.10 "2026-05-28 batch"
#
# AGENTS.md §3 Step 5 actions 4-5

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
DRY_RUN=false
SKIP_DOC_CHECK=false

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

# Release-doc preflight (issue #114) — verify the release-doc set is updated on the
# version branch BEFORE the irreversible merge/tag. Reads the branch tree via `git show`
# (no checkout). HARD-fails on deterministic signals (VERSION / changelog / README badge),
# WARNs on prose docs (roadmap / HISTORY). `--skip-doc-check` is the escape hatch.
# Checklist 정본: docs/agent_dev_guide.md §Step 5.
_preflight_release_docs() {
    if "$SKIP_DOC_CHECK"; then
        warn "Release-doc preflight 생략 (--skip-doc-check)."
        return 0
    fi
    info "=== Release-doc preflight (issue #114) ==="
    local ref="origin/$VERSION_BRANCH" ver="${VERSION_TAG#v}"
    local vfile changelog readme badge

    # HARD 1 — _system/VERSION == release tag
    vfile="$(git show "$ref:_system/VERSION" 2>/dev/null | head -1 | tr -d '[:space:]')"
    [[ "$vfile" == "$ver" ]] || die "preflight: _system/VERSION ('${vfile:-<empty>}') != $VERSION_TAG. VERSION 파일을 $ver 로 갱신 후 재시도 (또는 --skip-doc-check)."

    # HARD 2 — docs/changelog.md 에 released (non-canary) entry 존재
    changelog="$(git show "$ref:docs/changelog.md" 2>/dev/null || true)"
    local cl_line
    cl_line="$(printf '%s\n' "$changelog" | grep -m1 "^## \[$VERSION_TAG\]" || true)"
    [[ -n "$cl_line" ]] || die "preflight: docs/changelog.md 에 '## [$VERSION_TAG]' entry 부재 — changelog 갱신 후 재시도."
    printf '%s' "$cl_line" | grep -qi "canary" && die "preflight: docs/changelog.md '$VERSION_TAG' entry 가 아직 (canary) — (released) + 날짜로 갱신 후 재시도."

    # HARD 3 — README Status 배지가 이 버전을 released 로 반영
    readme="$(git show "$ref:README.md" 2>/dev/null || true)"
    badge="$(printf '%s\n' "$readme" | grep -i 'img.shields.io/badge/Status' | head -1 || true)"
    printf '%s' "$badge" | grep -q "$VERSION_TAG" || die "preflight: README.md Status 배지가 $VERSION_TAG 미반영 ('${badge:-<none>}') — 배지 갱신 후 재시도."
    printf '%s' "$badge" | grep -qi "canary" && die "preflight: README.md Status 배지가 아직 canary — released 로 갱신 후 재시도."

    # WARN — roadmap / HISTORY (prose, 기계 단정 어려움 — 존재 힌트만)
    printf '%s\n' "$(git show "$ref:docs/roadmap.md" 2>/dev/null || true)" | grep -q "$VERSION_TAG" \
        || warn "preflight: docs/roadmap.md 에 $VERSION_TAG 언급 없음 — 누적완료 이동 확인 권장."
    printf '%s\n' "$(git show "$ref:docs/release-history.md" 2>/dev/null || true)" | grep -q "$VERSION_TAG" \
        || warn "preflight: docs/release-history.md 에 $VERSION_TAG 항목 없음 — release 항목 append 확인 (AGENTS §3.5)."

    info "Release-doc preflight 통과 (HARD 3종 OK)."
}

# --- Argument parsing ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --skip-doc-check) SKIP_DOC_CHECK=true; shift ;;
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

# Release-doc preflight — BEFORE the irreversible merge (issue #114)
_preflight_release_docs

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

# Push main + tags — explicit refspecs (issue #112): the version branch
# (refs/heads/vX.Y.Z) and the annotated tag (refs/tags/vX.Y.Z) share a name, so a
# bare `git push origin vX.Y.Z` is ambiguous ("src refspec matches more than one").
run_or_dry git push origin main
run_or_dry git push origin "refs/tags/$VERSION_TAG"
run_or_dry git push origin "refs/tags/latest" --force 2>/dev/null || \
    warn "Latest tag force-push failed. Check GitHub tag protection rules."

# --- Post-release: cleanup version branch + canary (cleanup only) ---
# v0.1.13+ 정책 (AGENTS.md §3 Step 5): release.sh 는 cleanup 만 담당.
# 새 버전 브랜치 + canary tag 의 bootstrap 은 `scripts/bootstrap_version.sh` 가
# 별도로 처리 (수동 호출 또는 github-dev-flow Step 4 자동 호출).
info "=== Post-release: Cleanup version branch + canary (cleanup only) ==="

# Delete local version branch
run_or_dry git branch -D "$VERSION_BRANCH" 2>/dev/null || warn "Local branch '$VERSION_BRANCH' not found."

# Delete remote version branch
run_or_dry git push origin --delete "refs/heads/$VERSION_BRANCH" 2>/dev/null || \
    warn "Remote version branch 'refs/heads/$VERSION_BRANCH' not found (already deleted)."

# Delete remote canary tag
run_or_dry git push origin --delete "refs/tags/canary" 2>/dev/null || \
    warn "Remote canary tag not found (already deleted)."

# Delete local canary tag
run_or_dry git tag -d canary 2>/dev/null || true

# --- Post-release state display ---
info "=== release.sh complete ==="
echo ""
echo "Release $VERSION_TAG completed."
echo "  Merge commit : $MERGE_SHA"
echo "  Description  : $TAG_MESSAGE"
echo ""
echo "Ref state after release:"
echo "  main HEAD           = refs/tags/$VERSION_TAG = refs/tags/latest = $MERGE_SHA"
echo "  (deleted)           = refs/heads/$VERSION_BRANCH"
echo "  (deleted)           = refs/tags/canary"
echo ""
echo "다음 사이클 시작: scripts/bootstrap_version.sh 호출 (또는 github-dev-flow Step 4에서 자동 호출)"
echo ""
echo "Next step: Notify operators to run 'install.sh --branch latest'"
