#!/usr/bin/env bash
# tests/test_wl_guarded.sh — (f) flock wrapper 검증 (issue #201, 2026-09-22)
#
# 검증 대상: scripts/wl_guarded.sh
#  1. --probe  : lock free 일 때 LOCK=FREE / 점유 중일 때 LOCK=HELD
#  2. 인자 없음 : exit 2 + usage
#  3. silent skip : 점유 중이면 명령을 실행하지 않고 exit 0 (OnFailure 미발화)
#  4. exec 후 lock 유지 : wrapper 가 세션 수명 동안 lock 을 보유 (핵심 성질)
#  5. template 이 wrapper 경로를 ExecStart 에 포함
#
# 모든 검증은 temp dir 를 쓰고 live wiki 를 건드리지 않는다.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUARD="$REPO/scripts/wl_guarded.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"; [[ -n "${HOLDER_PID:-}" ]] && kill "$HOLDER_PID" 2>/dev/null || true' EXIT

export WIKIHUB_HOME="$TMP/wh"
mkdir -p "$WIKIHUB_HOME"

PASS=0; FAIL=0
ok()   { printf '  ✓ %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  ✗ %s\n' "$1"; FAIL=$((FAIL+1)); }
check() { if [[ "$2" == "$3" ]]; then ok "$1"; else bad "$1 (기대 '$3', 실제 '$2')"; fi; }

echo "[test_wl_guarded] repo=$REPO"

# ── 1. 문법
if bash -n "$GUARD" 2>/dev/null; then ok "bash -n"; else bad "bash -n"; fi

# ── 2. 인자 없음 → exit 2 + usage
out="$("$GUARD" 2>&1)"; rc=$?
check "인자 없음 exit 2" "$rc" "2"
if [[ "$out" == *usage* ]]; then ok "usage 메시지"; else bad "usage 메시지"; fi

# ── 3. --probe (free)
out="$("$GUARD" --probe 2>/dev/null)"; rc=$?
check "--probe free exit 0" "$rc" "0"
check "--probe free 출력" "$out" "LOCK=FREE"

# ── 4. --probe (held) — 별도 프로세스가 lock 을 잡고 있는 동안
#    holder 는 fd 를 열어둔 채 대기해야 한다 (exec 로 교체해 fd 를 유지).
bash -c "exec 200>\"$WIKIHUB_HOME/.wl.lock\"; flock -n 200; exec sleep 30" &
HOLDER_PID=$!
sleep 1

out="$("$GUARD" --probe 2>/dev/null)"; rc=$?
check "--probe held exit 0" "$rc" "0"
check "--probe held 출력" "$out" "LOCK=HELD"

# ── 5. silent skip — 점유 중이면 명령을 실행하지 않는다
MARKER="$TMP/marker"
"$GUARD" touch "$MARKER" >/dev/null 2>&1; rc=$?
check "silent skip exit 0" "$rc" "0"
if [[ -f "$MARKER" ]]; then bad "silent skip 이 명령을 실행함"; else ok "silent skip 이 명령을 실행하지 않음"; fi

# ── 6. holder 종료 후 lock 해제 → 정상 실행
kill "$HOLDER_PID" 2>/dev/null || true
wait "$HOLDER_PID" 2>/dev/null || true
HOLDER_PID=""
sleep 1
out="$("$GUARD" --probe 2>/dev/null)"
check "holder 종료 후 FREE" "$out" "LOCK=FREE"

"$GUARD" touch "$MARKER" >/dev/null 2>&1; rc=$?
check "정상 실행 exit 0" "$rc" "0"
if [[ -f "$MARKER" ]]; then ok "lock 해제 후 명령 실행됨"; else bad "lock 해제 후에도 명령 미실행"; fi

# ── 7. exec 후 lock 유지 (핵심 성질) — wrapper 가 세션을 소유하는 동안 유지되는가
#    systemd 는 wrapper 를 **직접 exec** 하므로(bash 경유 아님) 그 방식을 재현한다.
#    wrapper 에 shebang + 755 mode 가 있어야 직접 실행이 성립한다.
if [[ ! -x "$GUARD" ]]; then bad "wrapper 에 실행 권한 없음 (systemd 직접 exec 불가)"; fi
head -1 "$GUARD" | grep -q '^#!/usr/bin/env bash' && ok "wrapper shebang" || bad "wrapper shebang 없음"
"$GUARD" sleep 8 &
GUARD_PID=$!
sleep 2
out="$("$GUARD" --probe 2>/dev/null)"
check "세션 보유 중 HELD (exec 후 유지)" "$out" "LOCK=HELD"
kill "$GUARD_PID" 2>/dev/null || true
wait "$GUARD_PID" 2>/dev/null || true

# ── 8. template 이 wrapper 경로를 ExecStart 에 포함
TPL="$REPO/_system/systemd/wikihub-lint.service.template"
if grep -qE '^ExecStart=\{wl_guarded_path\} \{agent_invocation_for_wl\}' "$TPL"; then
    ok "template ExecStart 에 wrapper 포함"
else
    bad "template ExecStart 에 wrapper 미포함"
fi

# ── 9. renderer 가 wl_guarded_path subs 를 노출
if grep -q '"wl_guarded_path"' "$REPO/scripts/_helpers/render_systemd_units.py"; then
    ok "renderer 에 wl_guarded_path subs"
else
    bad "renderer 에 wl_guarded_path subs 없음"
fi

echo
printf '[test_wl_guarded] PASS=%s FAIL=%s\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
