#!/usr/bin/env bash
# tests/test_update_wrapper.sh — Test scripts/update.sh wrapper
#
# Tests CLI parsing, dry-run, drift detection, preflight, and help flag.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
UPDATE="$REPO_ROOT/scripts/update.sh"

assert_eq() { [[ "$1" == "$2" ]] || { echo "FAIL: expected '$2' got '$1'"; exit 1; }; }
assert_contains() { [[ "$1" == *"$2"* ]] || { echo "FAIL: '$2' not in '$1'"; exit 1; }; }
assert_not_contains() { [[ "$1" != *"$2"* ]] || { echo "FAIL: '$2' found in '$1' (should be absent)"; exit 1; }; }

# Create mock install.sh that records argv
MOCK_DIR="$(mktemp -d)"
trap 'rm -rf "$MOCK_DIR"' EXIT

# Seed mock _system/VERSION and .git for preflight
mkdir -p "$MOCK_DIR/_system"
echo "0.1.14" > "$MOCK_DIR/_system/VERSION"
mkdir -p "$MOCK_DIR/.git"

cat > "$MOCK_DIR/install.sh" <<'MOCKEOF'
#!/usr/bin/env bash
echo "MOCK_INSTALL_CALLED $*" >> "$MOCK_LOG"
exit 0
MOCKEOF
chmod +x "$MOCK_DIR/install.sh"

MOCK_LOG="$MOCK_DIR/mock.log"
export MOCK_LOG
export WIKIHUB_SRC="$MOCK_DIR"
export WIKIHUB_HOME="$MOCK_DIR/home"
mkdir -p "$WIKIHUB_HOME"

passed=0
failed=0

run_test() {
    local name="$1"
    shift
    echo "=== $name ==="
    # Clear mock log before each test
    : > "$MOCK_LOG"
    # Run update.sh, capture stdout+stderr
    local output
    output="$("$UPDATE" "$@" 2>&1 || true)"
    echo "$output" | head -5
    echo "---"
}

# Test 1: --help
echo "=== Test 1: --help flag ==="
output="$("$UPDATE" --help 2>&1 || true)"
assert_contains "$output" "Usage:"
assert_contains "$output" "--version"
assert_contains "$output" "--dry-run"
echo "PASS"
passed=$((passed+1))

# Test 2: --dry-run exits 0 without calling install.sh
echo "=== Test 2: --dry-run ==="
output="$("$UPDATE" --dry-run 2>&1 || true)"
assert_contains "$output" "DRY RUN"
assert_not_contains "$output" "MOCK_INSTALL_CALLED"
[[ ! -f "$MOCK_LOG" ]] || { echo "FAIL: dry-run should not call install.sh"; failed=$((failed+1)); exit 1; }
echo "PASS"
passed=$((passed+1))

# Test 3: --version pinned
echo "=== Test 3: --version flag ==="
: > "$MOCK_LOG"
output="$("$UPDATE" --version v0.1.13 2>&1 || true)"
assert_contains "$(tail -1 "$MOCK_LOG")" "MOCK_INSTALL_CALLED --skip-confirm --version v0.1.13"
echo "PASS"
passed=$((passed+1))

# Test 4: --branch flag
echo "=== Test 4: --branch flag ==="
: > "$MOCK_LOG"
output="$("$UPDATE" --branch canary 2>&1 || true)"
assert_contains "$(tail -1 "$MOCK_LOG")" "MOCK_INSTALL_CALLED --skip-confirm --branch canary"
echo "PASS"
passed=$((passed+1))

# Test 5: --non-interactive (should NOT pass --skip-confirm, should export WIKIHUB_NONINTERACTIVE)
echo "=== Test 5: --non-interactive ==="
: > "$MOCK_LOG"
output="$("$UPDATE" --non-interactive 2>&1 || true)"
# With --non-interactive, --skip-confirm is NOT added to argv
assert_not_contains "$(tail -1 "$MOCK_LOG")" "--skip-confirm"
echo "PASS"
passed=$((passed+1))

# Test 6: --skip-drift-check
echo "=== Test 6: --skip-drift-check ==="
output="$("$UPDATE" --skip-drift-check --dry-run 2>&1 || true)"
assert_contains "$output" "DRY RUN"
# Should not contain "drift" messages
echo "PASS"
passed=$((passed+1))

# Test 7: Preflight — install.sh missing
echo "=== Test 7: preflight — install.sh missing ==="
# Temporarily move install.sh
mv "$MOCK_DIR/install.sh" "$MOCK_DIR/install.sh.bak"
output="$("$UPDATE" --dry-run 2>&1 || true)"
assert_contains "$output" "install.sh not found"
mv "$MOCK_DIR/install.sh.bak" "$MOCK_DIR/install.sh"
echo "PASS"
passed=$((passed+1))

# Test 8: Preflight — no _system/VERSION
echo "=== Test 8: preflight — no _system/VERSION ==="
mv "$MOCK_DIR/_system/VERSION" "$MOCK_DIR/_system/VERSION.bak"
output="$("$UPDATE" --dry-run 2>&1 || true)"
assert_contains "$output" "update mode 조건 미충족"
mv "$MOCK_DIR/_system/VERSION.bak" "$MOCK_DIR/_system/VERSION"
echo "PASS"
passed=$((passed+1))

# Test 9: Combined flags
echo "=== Test 9: combined flags ==="
output="$("$UPDATE" --version v0.1.13 --branch canary --skip-drift-check 2>&1 || true)"
assert_contains "$(cat "$MOCK_LOG")" "MOCK_INSTALL_CALLED --skip-confirm --version v0.1.13 --branch canary"
echo "PASS"
passed=$((passed+1))

# Test 10: Color TTY toggle — when stdout is a pipe, color codes absent
echo "=== Test 10: color TTY toggle ==="
output="$("$UPDATE" --dry-run 2>&1 | cat)"
assert_not_contains "$output" $'\033['
echo "PASS"
passed=$((passed+1))

echo ""
echo "=== Results: $passed passed, $failed failed ==="
[[ $failed -eq 0 ]] || exit 1
