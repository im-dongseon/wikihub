#!/usr/bin/env bash
# tests/test_session_env.sh — issue #186 회귀 테스트
#
# `_ensure_session_env_file()` / `_patch_hermes_shell_init_files()` 의 계약 검증.
# 이 로직이 검증 없이 ship 되면 세션 env 주입이 조용히 깨지고(파일 미생성·미등록)
# extraction deps 부재가 재발한다.
#
# 실행: bash tests/test_session_env.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"

VENV="/home/ubuntu/.hermes/profiles/jisaseo/home/.local/share/wikihub/venv"
[[ -x "$VENV/bin/python3" ]] || { echo "SKIP: 운영 venv python 없음 ($VENV)"; exit 0; }

PASS=0; FAIL=0
assert_eq() {
    local label="$1" actual="$2" expected="$3"
    if [[ "$actual" == "$expected" ]]; then
        PASS=$((PASS + 1)); printf '  ok   %s\n' "$label"
    else
        FAIL=$((FAIL + 1)); printf '  FAIL %s\n         expected: %s\n         actual:   %s\n' "$label" "$expected" "$actual"
    fi
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FNS="$WORK/fns.sh"
for fn in _hermes_agent_profile _hermes_root _hermes_config_path \
          _ensure_session_env_file _patch_hermes_shell_init_files; do
    sed -n "/^${fn}()/,/^}/p" "$INSTALL_SH" >> "$FNS"
    echo >> "$FNS"
done
printf 'info(){ :; }\nerr(){ :; }\nwarn(){ :; }\nok(){ :; }\n' >> "$FNS"

setup_home() {
    # $1 = HOME 로 쓸 경로, $2 = 기존 shell_init_files 항목 (선택)
    local h="$1" pre="${2:-}"
    mkdir -p "$h/.hermes/profiles/tp" "$h/wikihub" "$h/src"
    {
        printf 'skills:\n  external_dirs:\n    - %s\n' "$h/wh-skill"
        printf 'terminal:\n  shell_init_files:\n'
        [[ -n "$pre" ]] && printf '    - %s\n' "$pre"
        printf '  auto_source_bashrc: true\n'
    } > "$h/.hermes/profiles/tp/config.yaml"
}

invoke() {
    # $1 = HOME, $2 = 함수명  → stdout 캡처
    (
        export HOME="$1" HERMES_HOME="$1/.hermes/profiles/tp"
        export WIKIHUB_HOME="$1/wikihub" WIKIHUB_SRC="$1/src" VENV_PATH="$VENV"
        unset HERMES_CONFIG_HOME HERMES_PROFILE 2>/dev/null || true
        # shellcheck disable=SC1090
        source "$FNS"
        "$2"
    )
}

echo "=== issue #186 — session env 파일 ==="

H1="$WORK/h1"; setup_home "$H1"
invoke "$H1" _ensure_session_env_file >/dev/null
ENVF="$H1/.config/wikihub/session-env.sh"

assert_eq "session-env.sh 생성됨" "$([[ -f "$ENVF" ]] && echo yes || echo no)" "yes"
assert_eq "파일 mode 644" "$(stat -c '%a' "$ENVF")" "644"
assert_eq "디렉토리 mode 700" "$(stat -c '%a' "$H1/.config/wikihub")" "700"
# 비밀값 가드 — 이 파일은 Hermes 세션에 source 되므로 API key/token 이 들어가면 유출
assert_eq "비밀값(TOKEN/API_KEY) 0건" "$(grep -cE 'TOKEN|API_KEY' "$ENVF" || true)" "0"
# 4개 export + WIKIHUB_SRC 가 실제 값이어야 함 (빈 값 확장 회귀 가드)
assert_eq "WIKIHUB_HOME export" "$(grep -c "^export WIKIHUB_HOME=\"$H1/wikihub\"$" "$ENVF" || true)" "1"
assert_eq "WIKIHUB_SRC export" "$(grep -c "^export WIKIHUB_SRC=\"$H1/src\"$" "$ENVF" || true)" "1"
assert_eq "WIKIHUB_VENV export" "$(grep -c "^export WIKIHUB_VENV=\"$VENV\"$" "$ENVF" || true)" "1"
# PATH guard 는 source-time 에 \$WIKIHUB_VENV 를 평가해야 한다 (install-time bake 회귀 가드)
assert_eq "PATH guard 가 source-time 변수 사용" "$(grep -c 'WIKIHUB_VENV/bin' "$ENVF" || true)" "2"

echo
echo "=== source 동작 ==="
# 비밀 파일과 분리되어 있고, source 하면 venv python 이 PATH 우선이 되어야 한다
OUT="$(bash -c "source '$ENVF'; python3 -c 'import sys;print(sys.executable)'")"
assert_eq "source 후 python3 = venv" "$OUT" "$VENV/bin/python3"
OUT2="$(bash -c "source '$ENVF'; test -n \"\$WIKIHUB_SRC\" && echo set")"
assert_eq "source 후 WIKIHUB_SRC 설정" "$OUT2" "set"
# 멱등: 두 번 source 해도 PATH 중복 없음
OUT3="$(bash -c "source '$ENVF'; source '$ENVF'; python3 -c 'import sys;print(sys.executable)'")"
assert_eq "두 번 source 해도 venv python 유지" "$OUT3" "$VENV/bin/python3"

echo
echo "=== terminal.shell_init_files 등록 ==="

H2="$WORK/h2"; setup_home "$H2" "/home/ubuntu/.config/mise/path.sh"
CFG="$H2/.hermes/profiles/tp/config.yaml"
invoke "$H2" _ensure_session_env_file >/dev/null
invoke "$H2" _patch_hermes_shell_init_files >/dev/null

assert_eq "session-env.sh 가 등록됨" "$(grep -c 'session-env.sh' "$CFG" || true)" "1"
# append-only — 기존 entry 를 절대 잃으면 안 된다
assert_eq "기존 mise/path.sh 보존됨" "$(grep -c 'mise/path.sh' "$CFG" || true)" "1"
assert_eq "기존 skills.external_dirs 보존됨" "$(grep -c 'wh-skill' "$CFG" || true)" "1"
assert_eq "marker comment 부착" "$(grep -c 'managed by wikihub install.sh' "$CFG" || true)" "1"

# 멱등성 — 2회차는 변경 없음
PRE_HASH="$(sha256sum "$CFG" | awk '{print $1}')"
invoke "$H2" _patch_hermes_shell_init_files >/dev/null
assert_eq "2회차 멱등 (파일 미변경)" "$(sha256sum "$CFG" | awk '{print $1}')" "$PRE_HASH"
# 중복 entry 없음
assert_eq "session-env.sh 중복 없음" "$(grep -c 'session-env.sh' "$CFG" || true)" "1"

echo
echo "=== 실패 경로 ==="

# 비밀 파일(~/.config/wikihub/env)은 건드리지 않는다
H3="$WORK/h3"; setup_home "$H3"
mkdir -p "$H3/.config/wikihub"
printf 'TELEGRAM_ALERT_BOT_TOKEN=secret-value\n' > "$H3/.config/wikihub/env"
cp "$H3/.config/wikihub/env" "$WORK/env.before"
invoke "$H3" _ensure_session_env_file >/dev/null
assert_eq "기존 env 파일 무변경" "$(cmp -s "$WORK/env.before" "$H3/.config/wikihub/env" && echo same || echo diff)" "same"
assert_eq "env 파일에 비밀이 새지 않음" "$(grep -c 'secret-value' "$H3/.config/wikihub/session-env.sh" || true)" "0"

# HOME 에 single quote 가 있어도 경로 도출이 깨지지 않는다 (argv 방식 회귀 가드)
H4="$WORK/it's"; setup_home "$H4" "/home/ubuntu/.config/mise/path.sh"
invoke "$H4" _ensure_session_env_file >/dev/null
invoke "$H4" _patch_hermes_shell_init_files >/dev/null
assert_eq "HOME quote 시에도 등록 성공" "$(grep -c 'session-env.sh' "$H4/.hermes/profiles/tp/config.yaml" || true)" "1"

# 생성 자체가 불가한 경로 → return 1 (caller 가 graceful skip 할 수 있어야 함).
# chmod 555 는 소유자가 chmod 로 되돌릴 수 있어 실패를 유발하지 않는다 — 경로 자리에 파일을
# 두어 mkdir -p 를 실패시킨다.
H5="$WORK/h5"; setup_home "$H5"
mkdir -p "$H5/.config"
printf 'not-a-dir\n' > "$H5/.config/wikihub"
RC=0
invoke "$H5" _ensure_session_env_file >/dev/null 2>&1 || RC=$?
assert_eq "생성 불가 시 return 1" "$RC" "1"

echo
printf 'RESULT: %d passed, %d failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
