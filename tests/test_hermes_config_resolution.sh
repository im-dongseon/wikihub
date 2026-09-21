#!/usr/bin/env bash
# tests/test_hermes_config_resolution.sh — install.sh 의 Hermes config 경로 해석 검증
#
# issue #190: `_hermes_config_path()` 가 HERMES_HOME 을 인지하지 못해 실환경에서
# default 프로필 정본을 대상으로 삼던 결함 + stray 정리 fail-closed 가드 검증.
#
# 실행: bash tests/test_hermes_config_resolution.sh
#
# NOTE: 검토된 리뷰 finding — 본 로직이 #182 회차에 테스트 없이 ship 되어
# 실환경 무효 결함이 통과했다. 그 재발을 막기 위한 회귀 테스트다.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"

PASS=0
FAIL=0

assert_eq() {
    local label="$1" actual="$2" expected="$3"
    if [[ "$actual" == "$expected" ]]; then
        PASS=$((PASS + 1))
        printf '  ok   %s\n' "$label"
    else
        FAIL=$((FAIL + 1))
        printf '  FAIL %s\n         expected: %s\n         actual:   %s\n' "$label" "$expected" "$actual"
    fi
}

# install.sh 에서 검증 대상 함수만 추출 (install.sh 자체는 실행하지 않음)
FNS="$(mktemp)"
trap 'rm -f "$FNS"; [[ -n "${FAKE_ROOT:-}" ]] && rm -rf "$FAKE_ROOT"' EXIT
for fn in _hermes_agent_profile _hermes_root _hermes_config_path _hermes_stray_candidates; do
    sed -n "/^${fn}()/,/^}/p" "$INSTALL_SH" >> "$FNS"
    echo >> "$FNS"
done

# 테스트용 가짜 wikihub.yaml (agent.profile 지정)
FAKE_ROOT="$(mktemp -d)"
mkdir -p "$FAKE_ROOT/wikihub"
printf 'agent:\n  type: hermes\n  profile: testp\n' > "$FAKE_ROOT/wikihub/wikihub.yaml"
# 프로필 디렉토리 (step 3 의 -d 검사 통과용)
mkdir -p "$FAKE_ROOT/hermes/profiles/testp"

# 가짜 venv python3 — _hermes_agent_profile 이 yaml 을 파싱하므로 실제 python 필요
VENV_PY="/home/ubuntu/.hermes/profiles/jisaseo/home/.local/share/wikihub/venv/bin/python3"
[[ -x "$VENV_PY" ]] || VENV_PY="$(command -v python3)"

run_case() {
    # $1 = HOME, $2 = HERMES_HOME(빈 문자열 가능), $3 = HERMES_CONFIG_HOME(빈 문자열 가능)
    local home="$1" hh="$2" hch="$3"
    (
        export HOME="$home"
        export WIKIHUB_HOME="$FAKE_ROOT/wikihub"
        export VENV_PATH="$(dirname "$VENV_PY")/.."
        [[ -n "$hh" ]] && export HERMES_HOME="$hh" || unset HERMES_HOME
        [[ -n "$hch" ]] && export HERMES_CONFIG_HOME="$hch" || unset HERMES_CONFIG_HOME
        unset HERMES_PROFILE 2>/dev/null || true
        # shellcheck disable=SC1090
        source "$FNS"
        printf '%s\n' "$(_hermes_config_path)"
    )
}

echo "=== issue #190 — Hermes config 경로 해석 ==="

# 1. 실환경: HOME=OS home, HERMES_HOME=프로필 → 정본
assert_eq "실환경 (HERMES_HOME=프로필) → 정본" \
    "$(run_case "/home/ubuntu" "$FAKE_ROOT/hermes/profiles/testp" "")" \
    "$FAKE_ROOT/hermes/profiles/testp/config.yaml"

# 2. HERMES_HOME trailing slash 정규화 (finding: 이중 슬래시 회귀 가드)
assert_eq "HERMES_HOME trailing slash 정규화" \
    "$(run_case "/home/ubuntu" "$FAKE_ROOT/hermes/profiles/testp/" "")" \
    "$FAKE_ROOT/hermes/profiles/testp/config.yaml"

# 3. HERMES_CONFIG_HOME 우선 (테스트용 override) + trailing slash
assert_eq "HERMES_CONFIG_HOME 우선" \
    "$(run_case "/home/ubuntu" "$FAKE_ROOT/hermes/profiles/testp" "$FAKE_ROOT/override")" \
    "$FAKE_ROOT/override/config.yaml"
assert_eq "HERMES_CONFIG_HOME trailing slash" \
    "$(run_case "/home/ubuntu" "" "$FAKE_ROOT/override/")" \
    "$FAKE_ROOT/override/config.yaml"

# 4. HERMES_HOME 미지정 (SSH) → agent.profile + 프로필 dir 로 정본 도달
#    HOME 을 fake root 로 두어 _hermes_root = <fake>/.hermes 가 되게 한다.
#    그러면 <fake>/.hermes/profiles/testp 가 step 3 의 -d 검사 대상이 된다.
mkdir -p "$FAKE_ROOT/fakehome/.hermes/profiles/testp"
assert_eq "HERMES_HOME 미설정 → agent.profile 경로 도출" \
    "$(run_case "$FAKE_ROOT/fakehome" "" "")" \
    "$FAKE_ROOT/fakehome/.hermes/profiles/testp/config.yaml"

echo
echo "=== stray candidates — fail-closed 가드 ==="

# 후보가 default 정본(<root>/config.yaml)을 절대 포함하지 않아야 한다
CAND_RESULT="$(
    (   export HOME=/home/ubuntu
        export HERMES_HOME="$FAKE_ROOT/hermes/profiles/testp"
        export WIKIHUB_HOME="$FAKE_ROOT/wikihub"
        export VENV_PATH="$(dirname "$VENV_PY")/.."
        unset HERMES_CONFIG_HOME HERMES_PROFILE 2>/dev/null || true
        source "$FNS"
        _hermes_stray_candidates
    )
)"

assert_eq "candidates 에 정본(config.yaml 직접) 미포함" \
    "$(printf '%s\n' "$CAND_RESULT" | grep -c "profiles/testp/config.yaml$" || true)" \
    "0"
assert_eq "candidates 에 profile home 잔재 포함" \
    "$(printf '%s\n' "$CAND_RESULT" | grep -c "profiles/testp/home/.hermes/config.yaml$" || true)" \
    "1"

echo
printf 'RESULT: %d passed, %d failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
