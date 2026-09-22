#!/usr/bin/env bash
# tests/test_wikihub_src_profile_guard.sh — issue #184 회귀 테스트
#
# (b) fail-fast: 프로필 환경에서 WIKIHUB_SRC 미명시 시 오대상 트리 갱신을 차단
# (c) advisory:  렌더 결과가 이번 install 의 트리/venv 를 가리키지 않으면 경고 (실패 아님)
#
# 실행: bash tests/test_wikihub_src_profile_guard.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
RENDER="$REPO_ROOT/scripts/_helpers/render_systemd_units.py"
PY="$(command -v python3)"

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

# install.sh 의 helper 함수만 추출 (전체 source 는 main 을 실행함)
FNS="$WORK/fns.sh"
for fn in _hermes_root _hermes_agent_profile _verify_wikihub_src_explicit_in_profile; do
    sed -n "/^${fn}()/,/^}/p" "$INSTALL_SH" >> "$FNS"
    echo >> "$FNS"
done
printf 'err(){ echo "[err] $*" >&2; }\n' >> "$FNS"

setup_fixture() {
    local h="$1"
    mkdir -p "$h/wikihub" "$h/.hermes/profiles/tp/home/.local/share/wikihub/src"
    cat > "$h/wikihub/wikihub.yaml" <<'YAML'
graphify:
  graphify_profile: ollama_gemma
  graphify_profiles:
    local:
      timeout_sec: 1800
agent:
  profile: tp
YAML
}

# 판정 함수 호출 — rc 를 stdout 으로 돌려준다 (exit 1 이 subshell 을 종료하므로)
run_guard() {
    local h="$1" src="$2" explicit="$3"
    (
        export HOME="$h" HERMES_HOME="$h/.hermes/profiles/tp"
        export WIKIHUB_HOME="$h/wikihub" VENV_PATH="$h/nonexistent-venv"
        export WIKIHUB_SRC="$src" WIKIHUB_SRC_EXPLICIT_FLAG="$explicit"
        unset HERMES_PROFILE 2>/dev/null || true
        # shellcheck disable=SC1090
        source "$FNS"
        _verify_wikihub_src_explicit_in_profile 2>/dev/null
    ) >/dev/null 2>&1 && echo 0 || echo 1
}

echo "=== (b) fail-fast — 프로필 환경 ==="

H1="$WORK/h1"; setup_fixture "$H1"
# 미명시 + 기본값(프로필 밖) → 4조건 성립 → exit 1
assert_eq "미명시 + 프로필 + 도출경로 존재 → exit 1" \
    "$(run_guard "$H1" "$H1/.local/share/wikihub/src" "")" "1"

# 명시 → 통과 (프로필이 있어도)
assert_eq "명시 실행 → 통과" \
    "$(run_guard "$H1" "$H1/custom/src" "1")" "0"

# 미명시지만 기본값이 도출 경로와 일치 → 통과
assert_eq "미명시 + 기본값==도출경로 → 통과" \
    "$(run_guard "$H1" "$H1/.hermes/profiles/tp/home/.local/share/wikihub/src" "")" "0"

# 도출 경로 부재 → 통과 (하위 호환)
H2="$WORK/h2"; setup_fixture "$H2"
rm -rf "$H2/.hermes/profiles/tp/home/.local/share/wikihub/src"
assert_eq "도출 경로 부재 → 통과" \
    "$(run_guard "$H2" "$H2/.local/share/wikihub/src" "")" "0"

# agent.profile 부재 → 통과 (비프로필 운영)
H3="$WORK/h3"; setup_fixture "$H3"
sed -i 's/^  profile: tp$/  xprofile: tp/' "$H3/wikihub/wikihub.yaml"
assert_eq "agent.profile 부재 → 통과" \
    "$(run_guard "$H3" "$H3/.local/share/wikihub/src" "")" "0"

echo
echo "=== _hermes_agent_profile decoy 회피 ==="

read_profile() {
    local h="$1" venv="$2"
    (
        export HOME="$h" HERMES_HOME="$h/.hermes/profiles/tp"
        export WIKIHUB_HOME="$h/wikihub" VENV_PATH="$venv"
        unset HERMES_PROFILE 2>/dev/null || true
        # shellcheck disable=SC1090
        source "$FNS"
        _hermes_agent_profile
    ) 2>/dev/null
}

# venv 부재 → bash fallback. graphify_profile(ollama_gemma) 을 집으면 안 된다.
assert_eq "fallback: agent.profile=tp (decoy 회피)" \
    "$(read_profile "$H1" "$H1/nonexistent-venv")" "tp"

echo "=== (b) bootstrap self-replace 상속 검증 (issue #184) ==="

# install.sh 가 curl-pipe 로 self-replace 할 때 defaulted WIKIHUB_SRC 를 상속하면
# child 가 "명시됨"으로 오판해 가드가 무력화된다. _self_replace_exec 가 이를 차단하는지 확인.
SRW="$WORK/sr"; mkdir -p "$SRW/fh/.local/share/wikihub/src" "$SRW/fh/explicit/src"
printf '#!/usr/bin/env bash\necho "SRC=${WIKIHUB_SRC:-<unset>} FLAG=${WIKIHUB_SRC_EXPLICIT_FLAG:-<unset>}"\n' > "$SRW/ci.sh"
cp "$SRW/ci.sh" "$SRW/fh/.local/share/wikihub/src/install.sh"
cp "$SRW/ci.sh" "$SRW/fh/explicit/src/install.sh"
sed -n '/^_self_replace_exec()/,/^}/p' "$INSTALL_SH" > "$SRW/fh/sr.sh"
cat > "$SRW/fh/parent.sh" <<'EOF'
export WIKIHUB_SRC_EXPLICIT_FLAG="${WIKIHUB_SRC_EXPLICIT_FLAG:-}"
[[ -n "${WIKIHUB_SRC:-}" ]] && WIKIHUB_SRC_EXPLICIT_FLAG=1
export WIKIHUB_SRC="${WIKIHUB_SRC:-$HOME/.local/share/wikihub/src}"
ORIGINAL_ARGS=(); source "$HOME/sr.sh"; _self_replace_exec
EOF

sr_child() { env -u WIKIHUB_SRC_EXPLICIT_FLAG "$@" HOME="$SRW/fh" bash "$SRW/fh/parent.sh" 2>/dev/null | tr -d '\n'; }

assert_eq "self-replace: 미명시 → SRC 미상속 (가드 유지)" \
    "$(sr_child env -u WIKIHUB_SRC)" "SRC=<unset> FLAG=<unset>"
assert_eq "self-replace: 명시 → SRC 상속 (의도 보존)" \
    "$(sr_child env WIKIHUB_SRC="$SRW/fh/explicit/src")" \
    "SRC=$SRW/fh/explicit/src FLAG=1"

echo
echo "=== (c) --verify-paths advisory ==="

W="$WORK/vp"; VB="/opt/example/venv/bin"
mkdir -p "$W/good" "$W/bad" "$W/nopath" "$W/empty"
printf '[Service]\nEnvironment=PATH=%s:/usr/bin:/bin\nEnvironment=WIKIHUB_SRC=/opt/example/src\n' "$VB" \
    > "$W/good/wikihub-lint.service"
printf '[Service]\nEnvironment=PATH=/tmp/other-venv/bin:/usr/bin:/bin\n' \
    > "$W/bad/wikihub-lint.service"
printf '[Service]\nExecStart=/bin/true\n' > "$W/nopath/ops-alert.service"

vp() { "$PY" "$RENDER" --verify-paths /opt/example/venv /opt/example/src --out "$1" 2>&1 || true; }

assert_eq "정합 unit → 경고 0" "$(vp "$W/good" | grep -c 'WARN:' || true)" "0"
assert_eq "불일치 unit → 경고 발생" "$(vp "$W/bad" | grep -c 'WARN:' || true)" "1"
assert_eq "PATH 없는 unit → 경고 0" "$(vp "$W/nopath" | grep -c 'WARN:' || true)" "0"
assert_eq "빈 디렉토리 → 출력 0" "$(vp "$W/empty" | wc -l | tr -d ' ')" "0"
# advisory — 항상 exit 0
vp "$W/bad" >/dev/null 2>&1; assert_eq "불일치여도 exit 0 (advisory)" "$?" "0"

# WIKIHUB_SRC 다른 트리 참조 검출
mkdir -p "$W/othersrc"
printf '[Service]\nEnvironment=PATH=%s:/usr/bin\nEnvironment=WIKIHUB_SRC=/other/tree/src\n' "$VB" \
    > "$W/othersrc/wikihub-graphify.service"
assert_eq "다른 트리 src 참조 → 경고 발생" "$(vp "$W/othersrc" | grep -c 'WARN:' || true)" "1"

echo
echo "=== 기존 모드 회귀 ==="
Y="$WORK/w.yaml"
cat > "$Y" <<'YAML'
instance:
  root: /tmp/wh
vaults:
  - id: nas
    enabled: true
    mount_path: ~/vault/nas
YAML
assert_eq "--list-enabled 정상 동작" \
    "$("$PY" "$RENDER" --yaml "$Y" --list-enabled 2>/dev/null)" "nas"
assert_eq "--help 에 --verify-paths 노출" \
    "$("$PY" "$RENDER" --help 2>&1 | grep -c -- '--verify-paths' | awk '{print ($1>0)?1:0}')" "1"

echo
printf 'RESULT: %d passed, %d failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
