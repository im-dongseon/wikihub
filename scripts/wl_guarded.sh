#!/usr/bin/env bash
# wl_guarded.sh — lint 상호배제 가드를 세션 전체 수명 동안 유지하는 wrapper.
#
# ── 왜 필요한가 ────────────────────────────────────────────────────────────
# 이전 2차 가드(flock)는 이 실행 모델에서 **무력**했다. `flock(2)` 는 열린 fd 에
# lock 을 걸고, fd 는 프로세스 수명과 함께 사라진다. Hermes agent 는 terminal 명령을
# 매번 별도 subprocess 로 실행하므로 lock 을 잡은 명령이 끝나는 순간 커널이 해제한다.
#   실측(2026-09-22):
#     C: exec 200>lock; flock -n 200; exit   → 획득 후 프로세스 종료 → 해제
#     D: exec 201>lock; flock -n 201         → 획득됨 (가드 무력)
#
# ── 왜 이 방식은 유효한가 ──────────────────────────────────────────────────
# `exec` 는 shell 프로세스 이미지를 **교체**하므로 fd 가 살아남고, lock 은 그
# 프로세스(= LLM 세션)가 끝날 때까지 유지된다.
#   실측(2026-09-22):
#     A: exec 200>lock; flock -n 200; exec sleep N → lock 유지
#     B: exec 201>lock; flock -n 201               → A 생존 중 차단됨 ✅
#
# ⚠️ `flock -o`(--close) 를 쓰지 않는다 — 명령 실행 전에 fd 를 닫아 정확히 우리가
#    필요한 성질을 깨뜨린다. `flock -n <fd> <cmd>` subshell 형도 쓰지 않는다 —
#    fd 가 lock 보유 프로세스에서 상속되지 않는다. 반드시 `exec N>file` + `flock -n N`
#    + `exec "$@"` 3단으로 쓴다.
#
# ── 경합 시 동작: 조용한 skip (설계 결정) ──────────────────────────────────
# 이미 lint 가 돌고 있으면 **exit 0** 으로 조용히 건너뛴다. stderr 1줄 + logger 로
# 흔적만 남긴다. `OnFailure=ops-alert.service` 가 benign skip 에 발화하면 안 되므로
# 비영(非零) exit·알림은 하지 않는다.
#
# 사용:
#   wl_guarded.sh --probe              # lock 상태만 확인 (LOCK=HELD|FREE)
#   wl_guarded.sh <cmd> [args...]      # lock 잡고 cmd 를 exec (세션 수명 동안 유지)

set -euo pipefail

# ── lock 경로 해석 ─────────────────────────────────────────────────────────
# systemd unit 은 WIKIHUB_HOME 을 직접 주입하지 않고 WIKIHUB_YAML 만 주입한다
# (실측: Environment=WIKIHUB_YAML=... / WIKIHUB_HOME 없음). 따라서 2순위인
# "WIKIHUB_YAML 부모" 가 systemd 경유 시의 실제 경로이며, 이는 인스턴스별로
# 분리된 디렉토리라 공유되지 않는다.
# 3순위($HOME/wikihub)는 두 env 가 모두 없는 ad-hoc 호출 전용 fallback 이다 —
# 같은 $HOME 아래 다중 인스턴스를 돌리는 경우에만 충돌 가능하다(단일 운영자 환경
# 에서는 무해). render_systemd_units.py 의 경로 복원 순서와 정합한다.
_resolve_lock() {
    if [[ -n "${WIKIHUB_HOME:-}" ]]; then
        printf '%s' "${WIKIHUB_HOME}/.wl.lock"
        return
    fi
    if [[ -n "${WIKIHUB_YAML:-}" ]]; then
        printf '%s' "$(dirname "$WIKIHUB_YAML")/.wl.lock"
        return
    fi
    printf '%s' "${HOME:-/tmp}/wikihub/.wl.lock"
}

LOCK="$(_resolve_lock)"

if [[ "${1:-}" == "--probe" ]]; then
    mkdir -p "$(dirname "$LOCK")"
    exec 200>"$LOCK"
    if flock -n 200; then
        echo "LOCK=FREE"
    else
        echo "LOCK=HELD"
    fi
    exit 0
fi

if [[ $# -eq 0 ]]; then
    echo "usage: $0 --probe | <command> [args...]" >&2
    exit 2
fi

mkdir -p "$(dirname "$LOCK")"

# fd 200 을 열고 non-blocking 으로 lock 시도.
# -o 를 쓰지 않는다 (fd 를 닫으면 exec 후에도 유지되지 않는다).
exec 200>"$LOCK"
if ! flock -n 200; then
    # silent skip — 이미 lint 세션이 돌고 있다. OnFailure 를 발화시키지 않는다.
    echo "[wl_guarded] lint 세션이 이미 진행 중 — skip (exit 0)" >&2
    logger -t wl_guarded "lint session already running — skip (exit 0)" 2>/dev/null || true
    exit 0
fi

# lock 을 보유한 채 명령으로 프로세스 이미지를 교체한다.
# 이 시점부터 lock 은 세션 프로세스가 끝날 때까지 유지된다.
exec "$@"
