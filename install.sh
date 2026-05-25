#!/usr/bin/env bash
# WikiHub install.sh — curl-pipe + clean install pattern (ADR-0023).
#
# 운영자 한 줄 명령:
#   curl -fsSL --proto '=https' --tlsv1.2 \
#     https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh | bash
#
# 또는 로컬 호출 (개발/사전 inspection 후):
#   ./install.sh [--skip-confirm] [--branch <ref>] [--version <tag>] [--force-fresh]
#
# ADR-0035 (2026-05-19): gws CLI 폐기 — rclone 단독화. --gws-version 옵션 제거.
#
# detect signal: $WIKIHUB_SRC/_system/VERSION + $WIKIHUB_SRC/.git 둘 다 존재 → update mode
#   (ADR-0010 + ADR-0030). 둘 다 없으면 fresh install. 한쪽만 있으면 partial state fatal.
# --version <tag>     : 특정 tag pin (rollback 포함). 인자 강제 소비.
# --force-fresh       : 명시적 destructive 재설치. detect 무시 + 5초 confirm.
#
# Spec: features/20260514_install_runtime/analysis_and_design.md §4.1 (v5 정본 — fresh path)
#     + features/20260517_update_mode/analysis_and_design.md v3 (update path · ADR-0030).
set -euo pipefail

# ─── 색상 (TTY 일 때만) ────────────────────────────────────────────────
if [ -t 1 ]; then
    C_INFO=$'\033[1;34m'; C_OK=$'\033[1;32m'; C_WARN=$'\033[1;33m'; C_ERR=$'\033[1;31m'; C_RST=$'\033[0m'
else
    C_INFO=''; C_OK=''; C_WARN=''; C_ERR=''; C_RST=''
fi
# R10 NIT-1: timestamp prefix — rclone 다운로드 등 분 단위 step 의 hang vs 정상 구분
_ts() { date +%H:%M:%S; }
info()  { echo "${C_INFO}INFO${C_RST}  [$(_ts)] $*"; }
ok()    { echo "${C_OK}OK${C_RST}    [$(_ts)] $*"; }
warn()  { echo "${C_WARN}WARN${C_RST}  [$(_ts)] $*" >&2; }
err()   { echo "${C_ERR}ERROR${C_RST} [$(_ts)] $*" >&2; }

# ─── 기본값 + env override (ADR-0034 v0.2.0 — data-first layout) ──────
# WIKIHUB_HOME 의미 swap (v0.2.0): 운영 자산 dir (이전 repo dir 의미는 WIKIHUB_SRC 로 이전).
# WIKIHUB_INSTANCE_ROOT 폐기 — _step0_env_semantic_check 가 detect 시 fail-fast.
export WIKIHUB_HOME="${WIKIHUB_HOME:-$HOME/wikihub}"                            # 운영 자산 dir
export WIKIHUB_SRC="${WIKIHUB_SRC:-$HOME/.local/share/wikihub/src}"             # 시스템 코드 dir (XDG, ADR-0020 venv 와 동일 root)
WIKIHUB_REPO_URL="${WIKIHUB_REPO_URL:-https://github.com/im-dongseon/wikihub.git}"
# BRANCH default empty (ADR-0030) — `_resolve_ref` 가 우선순위 chain 으로 결정.
# 명시 export 또는 `--branch <name>` 시에만 path 2 (branch direct) 진입.
BRANCH="${BRANCH:-}"
# update_mode 신규 flag
EXPLICIT_VERSION="${EXPLICIT_VERSION:-}"   # --version <tag> 명시 시 set
EXPLICIT_VERSION_FLAG="${EXPLICIT_VERSION_FLAG:-}"
FORCE_FRESH="${FORCE_FRESH:-}"             # --force-fresh 명시 시 set
INSTALL_MODE=""                            # update | fresh — _detect_mode 가 set
PRE_UPDATE_REF=""                          # _step2_update 가 capture
# ADR-0035: gws CLI 폐기. GWS_VERSION 변수 제거. GWS_BIN_DIR → LOCAL_BIN_DIR (uv binary 위치만 유지).
SKIP_CONFIRM="${SKIP_CONFIRM:-${WIKIHUB_NONINTERACTIVE:-}}"
VENV_PATH="${VENV_PATH:-$HOME/.local/share/wikihub/venv}"
LOCAL_BIN_DIR="${LOCAL_BIN_DIR:-$HOME/.local/bin}"
ALLOW_NON_UBUNTU="${ALLOW_NON_UBUNTU:-}"      # R10 MED-4: 메인테이너 macOS dev box 실수 호출 차단
# ADR-0028: uv 기반 Python runtime 관리
UV_VERSION="${UV_VERSION:-0.11.14}"           # uv binary pinned (GitHub Releases + SHA256, rclone 패턴 일관)
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"      # uv 가 자체 install (apt python3 의존 없음)

# R9 MED-1 + R10 MED-5: 절대경로 normalize — 상대경로(./wikihub) + quoted tilde literal
# ("~/wikihub") 둘 다 차단. cd "$(dirname …)" && pwd 로 resolve. parent 부재 시 ensure.
_abs_path() {
    local _p="$1"
    # tilde expansion — env override 시 quoted "~/..." literal 처리
    case "$_p" in
        "~") _p="$HOME" ;;
        "~/"*) _p="$HOME/${_p#\~/}" ;;
    esac
    case "$_p" in
        /*) printf '%s\n' "$_p" ;;
        *)
            local _parent
            _parent="$(dirname "$_p")"
            mkdir -p "$_parent"
            printf '%s/%s\n' "$(cd "$_parent" && pwd)" "$(basename "$_p")"
            ;;
    esac
}
WIKIHUB_HOME="$(_abs_path "$WIKIHUB_HOME")"
WIKIHUB_SRC="$(_abs_path "$WIKIHUB_SRC")"

# R10 HIGH-7: install.sh stdout/stderr 의 log mirror — curl-pipe 모드 fail 시 사후 분석.
# v0.2.0 layout: install.log 는 운영 자산 dir 에 위치 (이전 INSTANCE_ROOT)
INSTALL_LOG="${WIKIHUB_HOME}/install.log"
mkdir -p "$WIKIHUB_HOME"

# ─── Step 0a — env semantic check (ADR-0034 §sub-2 — v0.1.0 release 전 architectural refactor) ──
# WIKIHUB_INSTANCE_ROOT env detect: ADR-0034 로 폐기. WIKIHUB_HOME 으로 통일.
if [[ -n "${WIKIHUB_INSTANCE_ROOT:-}" ]]; then
    err "WIKIHUB_INSTANCE_ROOT env 는 ADR-0034 로 폐기됨. WIKIHUB_HOME 으로 통일."
    err "  마이그레이션:"
    err "    unset WIKIHUB_INSTANCE_ROOT"
    err "    export WIKIHUB_HOME=<이전 INSTANCE_ROOT 값>"
    err "    export WIKIHUB_SRC=<시스템 코드 dir, 기본: \$HOME/.local/share/wikihub/src>"
    err "  ※ WIKIHUB_HOME 의 의미가 ADR-0034 로 변경 — 운영 자산 dir (이전 repo dir 의미는 WIKIHUB_SRC 로 이전)"
    err "  detail: docs/adr/0034-data-first-layout.md"
    exit 1
fi
# R16-L2 + R2-HIGH-6 (update_mode v3): log rotation — tee fd 보존 race 회피 위해 tee 시작 전 호출.
# 7일 또는 10MB 초과 시 rename, 7개 보관 (`tail -n +8` 의 8 = 보관수+1).
_rotate_install_log() {
    local log="$INSTALL_LOG"
    [[ -f "$log" ]] || return 0
    local age_days size_mb
    if [[ "$(uname -s)" == "Darwin" ]]; then
        age_days=$(( ($(date +%s) - $(stat -f %m "$log")) / 86400 ))
        size_mb=$(( $(stat -f %z "$log") / 1024 / 1024 ))
    else
        age_days=$(( ($(date +%s) - $(stat -c %Y "$log")) / 86400 ))
        size_mb=$(( $(stat -c %s "$log") / 1024 / 1024 ))
    fi
    if (( age_days >= 7 || size_mb >= 10 )); then
        # PID suffix 로 1초 안 중복 호출 collision 회피
        mv "$log" "${log}.$(date +%Y%m%d_%H%M%S)_$$"
        ls -1t "${log}".*_* 2>/dev/null | tail -n +8 | xargs -r rm -f
    fi
}
_rotate_install_log

# tee 로 log file 도 동시 write — 단 fd 1·2 모두 (stdout/stderr 둘 다 로깅).
exec > >(tee -a "$INSTALL_LOG") 2>&1
echo "─── install.sh start: $(date -u +%Y-%m-%dT%H:%M:%SZ) ───"

# R9 HIGH-2 fix: CLI 파싱 전 원본 args 보존 — bootstrap_clone_then_exec 가 self-replace 시 전달
ORIGINAL_ARGS=("$@")

# ─── CLI 파싱 ─────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --skip-confirm) SKIP_CONFIRM=1; shift ;;
        --branch) BRANCH="$2"; shift 2 ;;
        # ADR-0030 / HIGH-N3: --version 인자 강제 소비. no-arg 분기 없음.
        # version 조회는 `cat $WIKIHUB_SRC/_system/VERSION` 사용.
        --version)
            if [[ -z "${2:-}" || "${2:0:2}" == "--" ]]; then
                err "--version 인자 필요 (예: --version v0.1.0). version 조회는 \`cat \$WIKIHUB_SRC/_system/VERSION\`."
                exit 1
            fi
            EXPLICIT_VERSION="$2"
            EXPLICIT_VERSION_FLAG=1
            shift 2
            ;;
        --force-fresh) FORCE_FRESH=1; shift ;;
        --allow-non-ubuntu) ALLOW_NON_UBUNTU=1; shift ;;
        -h|--help)
            sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) err "Unknown option: $1"; exit 1 ;;
    esac
done

# ──────────────────────────────────────────────────────────────────────
# Step 0. 실행 컨텍스트 감지 + bootstrap (ADR-0023 [H1])
# ──────────────────────────────────────────────────────────────────────
# $BASH_SOURCE[0] 단독 감지 — env variable 의존 안 함 → exec 후 자연 분기 미진입.

bootstrap_clone_then_exec() {
    # ADR-0030 (C1 + HIGH-N4): mode-aware bootstrap.
    # _detect_mode 가 이미 INSTALL_MODE set. update mode 면 clone 없이 in-place exec.
    # fd 200 (install.lock) 명시 close — 새 process 가 fresh lock 잡도록 (HIGH-N4 fd inheritance 차단).
    exec 200>&- 2>/dev/null || true

    if [[ "$INSTALL_MODE" == "update" ]]; then
        info "curl-pipe + update mode — 기존 $WIKIHUB_SRC/install.sh 로 self-replace (clone 없이)"
        if [ ! -f "$WIKIHUB_SRC/install.sh" ]; then
            err "$WIKIHUB_SRC/install.sh 부재 — partial state 의심. --force-fresh 권장."
            exit 2
        fi
        exec bash "$WIKIHUB_SRC/install.sh" "${ORIGINAL_ARGS[@]}"
    fi
    # fresh path — repo clone (기존 동작)
    info "curl-pipe + fresh mode — repo 부트스트랩 진행"
    _step2_clone
    if [ ! -f "$WIKIHUB_SRC/install.sh" ]; then
        err "clone 후 $WIKIHUB_SRC/install.sh 가 없음 — repo 구조 결함 의심"
        exit 2
    fi
    info "→ $WIKIHUB_SRC/install.sh 로 self-replace (args: ${ORIGINAL_ARGS[*]:-(none)})"
    # R9 HIGH-2 fix: ORIGINAL_ARGS 보존 — CLI 파싱 후 $@ 가 비어 있어도 운영자 원본 args 전달
    exec bash "$WIKIHUB_SRC/install.sh" "${ORIGINAL_ARGS[@]}"
}

# Step 0 의 감지 — curl-pipe 모드 판별
_pipe_mode_detect() {
    # $BASH_SOURCE[0] 가 빈 문자열이거나 file system 에 없으면 curl-pipe.
    [ -z "${BASH_SOURCE[0]:-}" ] || [ ! -f "${BASH_SOURCE[0]}" ]
}

if _pipe_mode_detect; then
    if [ ! -c /dev/tty ]; then
        export WIKIHUB_NONINTERACTIVE=1
        SKIP_CONFIRM=1
        info "/dev/tty 부재 → 비대화 모드 자동 활성화"
    fi
    # bootstrap 은 _detect_mode 후 main() 안에서 호출 — 본 if 블록은 NONINTERACTIVE 설정만.
fi

# ──────────────────────────────────────────────────────────────────────
# Step 1. 환경 검증 (fail-fast — R5 §2.2 EUID assert + sudo pre-check)
# ──────────────────────────────────────────────────────────────────────

_step1_env_check() {
    # EUID assert — 메인테이너가 `sudo ./install.sh` 호출하면 즉시 exit 1
    if [ "$EUID" -eq 0 ]; then
        err "install.sh 는 일반 user 로 실행하세요. (현재 user: root)"
        err "       sudo 는 install.sh 내부에서 필요 시점에만 호출합니다."
        exit 1
    fi

    # sudo pre-check — 비대화 모드에서 silent hang 회피
    if ! sudo -n true 2>/dev/null; then
        if [ -n "$SKIP_CONFIRM" ]; then
            err "--skip-confirm 모드인데 sudo 비대화 호출 실패. NOPASSWD 설정 필요 (loginctl enable-linger Step 7)."
            exit 1
        fi
        info "sudo 권한이 필요합니다 (linger 활성화 Step 7 에서 1회). password prompt 가 나타날 수 있습니다."
    fi

    # OS 확인 (R10 MED-4: non-Ubuntu fail-fast — macOS dev box 의 wikihub repo wipe 위험 차단)
    local os_id="${ID:-unknown}"
    if [ -f /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        os_id="${ID:-unknown}"
    elif [ "$(uname -s)" = "Darwin" ]; then
        os_id="darwin"
    fi
    if [ "$os_id" != "ubuntu" ]; then
        if [ -n "$ALLOW_NON_UBUNTU" ]; then
            warn "v0.1.0 의 운영 타깃은 Ubuntu 22.04/24.04. 현재: $os_id ${VERSION_ID:-} (--allow-non-ubuntu 로 진행)"
        else
            err "v0.1.0 의 운영 타깃은 Ubuntu 22.04/24.04. 현재: $os_id ${VERSION_ID:-}"
            err "       메인테이너의 macOS dev box 에서 실수 호출 시 \$HOME/wikihub wipe 위험."
            err "       의도적인 비-Ubuntu 환경 설치는 ALLOW_NON_UBUNTU=1 env 또는 --allow-non-ubuntu flag."
            exit 1
        fi
    fi

    # arch 확인
    local arch
    arch="$(uname -m)"
    if [ "$arch" != "aarch64" ] && [ "$arch" != "arm64" ]; then
        warn "v0.1.0 의 운영 타깃은 ARM64. 현재 arch: $arch"
    fi

    # systemd user manager 확인 (이미 활성화돼 있어야 함)
    if ! systemctl --user status >/dev/null 2>&1; then
        warn "systemctl --user 응답 없음 — systemd user manager 미활성. linger 활성화 후 정상화 예상"
    fi

    # Python — system python3 검증 제거 (ADR-0028: uv 가 자체 Python $PYTHON_VERSION install).
    # unzip 검증 — Step 4.5 rclone zip 해제용 (V8 결함 #5 fix).
    if ! command -v unzip >/dev/null 2>&1; then
        info "unzip 미설치 → sudo apt-get install -y unzip"
        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y unzip >/dev/null
    fi

    ok "Step 1 환경 검증 완료"
}

# ──────────────────────────────────────────────────────────────────────
# Step 2. wikihub repo clean install (ADR-0023 — fresh / --force-fresh 한정)
# update path 는 _step2_update (ADR-0030).
# ──────────────────────────────────────────────────────────────────────

# H4: safety guard — fresh / --force-fresh 양쪽에서 재사용.
# ADR-0023 §Decision 갱신 (ADR-0034 정합):
#   1. system path 차단
#   2. .git 존재 검증
#   3. origin = im-dongseon/wikihub 검증
#   4. (신규) WIKIHUB_SRC 의 prefix 가 $HOME/.local/share/wikihub/ 외이면
#      NONINTERACTIVE 거부 + 명시 confirm — XDG path 외 wipe 는 운영자 의도 명시 요구
_validate_wipe_target() {
    case "$WIKIHUB_SRC" in
        ""|"/"|"/usr"|"/usr/local"|"/etc"|"/opt"|"/home"|"$HOME"|"$HOME/")
            err "WIKIHUB_SRC=$WIKIHUB_SRC 는 wipe 대상으로 안전하지 않음"
            err "       WIKIHUB_SRC env 로 다른 위치 지정 (default: ~/.local/share/wikihub/src)"
            exit 1
            ;;
    esac
    # safety guard 4번째 (ADR-0034) — XDG path 외 wipe 명시 confirm
    local xdg_prefix="$HOME/.local/share/wikihub"
    case "$WIKIHUB_SRC" in
        "$xdg_prefix"/*) ;;   # XDG path — 정상
        *)
            warn "WIKIHUB_SRC=$WIKIHUB_SRC 가 XDG path ($xdg_prefix/) 외부"
            if [[ -n "${SKIP_CONFIRM:-}" ]]; then
                err "  NONINTERACTIVE 모드는 XDG path 외 wipe 거부 — 운영자 명시 confirm 요구"
                err "  수동 호출: WIKIHUB_SRC=... ./install.sh (NONINTERACTIVE 해제)"
                exit 1
            fi
            printf "       continue? [y/N] " >&2
            local ans; read -r ans
            [[ "${ans,,}" == "y" || "${ans,,}" == "yes" ]] \
                || { err "wipe 거부"; exit 1; }
            ;;
    esac
    [ -e "$WIKIHUB_SRC" ] || return 0   # 신규 install 은 검증 대상 없음
    if [ ! -d "$WIKIHUB_SRC/.git" ]; then
        err "$WIKIHUB_SRC 가 존재하지만 git repo 가 아님 — wipe 거부."
        err "       wikihub 설치 위치가 아닐 가능성. 수동 확인 후 재시도."
        exit 1
    fi
    local existing_origin
    existing_origin="$(cd "$WIKIHUB_SRC" && git config --get remote.origin.url 2>/dev/null || true)"
    case "$existing_origin" in
        *im-dongseon/wikihub*|*wikihub.git*) ;;
        *)
            err "$WIKIHUB_SRC 의 origin=$existing_origin — wikihub repo 가 아님. wipe 거부."
            exit 1 ;;
    esac
    case "$(pwd)" in
        "$WIKIHUB_SRC"|"$WIKIHUB_SRC"/*) cd "$HOME" ;;
    esac
}

# --force-fresh path 의 5초 confirm + safety guard
_confirm_force_fresh_wipe() {
    _validate_wipe_target
    [ -n "${WIKIHUB_NONINTERACTIVE:-}${SKIP_CONFIRM:-}" ] && return 0
    info "[--force-fresh confirmed target: $WIKIHUB_SRC]"
    info "  Ctrl+C within 5s to abort. wipe 실행."
    sleep 5
}

# Sparse-checkout fetch list (ADR-0023 §"Clone scope" 정본).
# 운영 타깃에는 운영 필수 path 만 거주 — AGENTS.md §1 Dev/Ops Zone 분리 invariant 정합.
# 제외: docs/·features/·tests/·AGENTS.md·CLAUDE.md·GEMINI.md·.gitignore 등 governance·dev 파일.
WIKIHUB_SPARSE_PATHS=(_system scripts install.sh wikihub.yaml.example README.md LICENSE)

# Idempotent sparse-checkout state 적용 — _step2_clone + _step2_update + _rollback_if_failed
# 셋 다 호출 (ADR-0023 §"Clone scope" + ADR-0030 §부정/제약 sparse-checkout 영속화).
# git >=2.27 필요 (Ubuntu 22.04 의 2.34 OK, OCI custom image 가 2.20 이하면 fail-fast).
_apply_sparse_checkout() {
    git -C "$WIKIHUB_SRC" sparse-checkout init --no-cone >/dev/null 2>&1 \
        || { err "sparse-checkout init 실패 — git >=2.27 필요. 현재: $(git --version 2>/dev/null || echo 'git 미설치')"; return 2; }
    git -C "$WIKIHUB_SRC" sparse-checkout set "${WIKIHUB_SPARSE_PATHS[@]}" >/dev/null \
        || { err "sparse-checkout set 실패 — paths: ${WIKIHUB_SPARSE_PATHS[*]}"; return 2; }
}

_step2_clone() {
    _validate_wipe_target
    if [ -e "$WIKIHUB_SRC" ]; then
        info "기존 wikihub repo 발견 → clean re-install 진행"
        rm -rf "$WIKIHUB_SRC"
    fi

    # ref 결정 — fresh path 도 _resolve_ref chain 사용 (ADR-0030).
    local clone_ref
    clone_ref="$(_resolve_ref)"
    info "git clone --branch $clone_ref --depth 1 $WIKIHUB_REPO_URL → $WIKIHUB_SRC (sparse)"
    # _resolve_ref 가 `refs/tags/<tag>` 또는 branch name 또는 `origin/main` 반환 — git clone
    # 의 `--branch` 는 tag 또는 branch 둘 다 받음. `origin/main` 같은 prefixed ref 는 fallback.
    if [[ "$clone_ref" == refs/tags/* ]]; then
        clone_ref="${clone_ref#refs/tags/}"
    elif [[ "$clone_ref" == origin/* ]]; then
        clone_ref="${clone_ref#origin/}"
    fi
    # ADR-0023 §"Clone scope": --no-checkout 후 sparse-checkout init + set + checkout.
    # blob filter 미사용 (HIGH-S2 design review — partial clone + --unshallow 호환 위험 회피).
    git clone --no-checkout --depth 1 --branch "$clone_ref" \
        "$WIKIHUB_REPO_URL" "$WIKIHUB_SRC"
    _apply_sparse_checkout
    git -C "$WIKIHUB_SRC" checkout
    ok "Step 2 repo clone 완료 (ref=$clone_ref, scope=sparse: ${WIKIHUB_SPARSE_PATHS[*]})"
}

# ──────────────────────────────────────────────────────────────────────
# Step 3. venv 생성 (idempotent, ADR-0028 — uv 기반 Python runtime)
# ──────────────────────────────────────────────────────────────────────

# uv binary install — GitHub Releases binary + SHA256 verify (rclone 패턴 일관, ADR-0028)
_install_uv() {
    if command -v uv >/dev/null 2>&1 && uv --version 2>/dev/null | grep -q "$UV_VERSION"; then
        ok "uv $UV_VERSION 기존 설치 사용"
        return 0
    fi
    local triple url asset tmpdir uv_bin
    case "$(uname -m)" in
        aarch64|arm64) triple="aarch64-unknown-linux-gnu" ;;
        x86_64|amd64)  triple="x86_64-unknown-linux-gnu" ;;
        *) err "지원하지 않는 arch: $(uname -m)"; exit 2 ;;
    esac
    asset="uv-${triple}.tar.gz"
    url="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${asset}"
    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' RETURN
    info "uv $UV_VERSION 다운로드: $url"
    _curl_with_retry "$url" "$tmpdir/$asset"
    # R16-M2 (V<N> R16 SRE 리뷰): ADR-0028 §Decision (β2) 가 "astral-sh/uv 가 GitHub Releases
    # 에 SHA256 sidecar 제공" 을 spec 보장으로 명시 — 부재 시 fatal exit. TLS-only fallback
    # 은 supply chain 위협 surface (HIGH-2 와 짝).
    if ! _curl_with_retry "${url}.sha256" "$tmpdir/${asset}.sha256" 2>/dev/null; then
        err "uv sha256 sidecar 부재 — ADR-0028 spec 위반. release 형식 변경 의심: ${url}.sha256"
        exit 2
    fi
    ( cd "$tmpdir" && sha256sum -c "${asset}.sha256" )
    tar -C "$tmpdir" -xzf "$tmpdir/$asset"
    # uv tar 구조 가설: 최상위 또는 한 단계 깊이의 디렉토리 안에 `uv` binary
    uv_bin="$(find "$tmpdir" -maxdepth 3 -name uv -type f -executable | head -1)"
    if [ -z "$uv_bin" ]; then
        err "uv binary 가 tar 내에 없음 — V8 hand-check 필요 (asset 구조 가설 실패)"
        find "$tmpdir" -maxdepth 3 -not -name "$asset" -not -name "${asset}.sha256" -printf '  %P\n' >&2
        exit 2
    fi
    mkdir -p "$LOCAL_BIN_DIR"
    install -m 0755 "$uv_bin" "$LOCAL_BIN_DIR/uv"
    rm -rf "$tmpdir"
    trap - RETURN
    # PATH — 현 셸 + .profile 양쪽 (V8 결함 #4b 회귀 방지: self-replace 후에도 즉시 가용)
    if ! echo "$PATH" | tr ':' '\n' | grep -qx "$LOCAL_BIN_DIR"; then
        if ! grep -q "$LOCAL_BIN_DIR" "$HOME/.profile" 2>/dev/null; then
            echo "export PATH=\"$LOCAL_BIN_DIR:\$PATH\"" >> "$HOME/.profile"
            info "$HOME/.profile 에 PATH 추가 — 새 shell 부터 적용"
        fi
        export PATH="$LOCAL_BIN_DIR:$PATH"
    fi
    ok "uv $UV_VERSION 설치 완료 ($LOCAL_BIN_DIR/uv)"
}

_step3_venv() {
    _install_uv

    info "Python $PYTHON_VERSION install (uv 자체 관리, apt 의존 없음)"
    uv python install "$PYTHON_VERSION"

    # venv 검증 — 정상 venv (bin/python + 버전 일치) = skip, 무효/부분 생성 = wipe + 재생성
    # (V8 결함 #2·#6 fix — `uv venv` 자체는 기존 venv 존재 시 error, 검증 분기 + 명시적 wipe 필요)
    mkdir -p "$(dirname "$VENV_PATH")"
    local venv_was_recreated=0
    if [ -x "$VENV_PATH/bin/python" ] \
        && "$VENV_PATH/bin/python" --version 2>/dev/null | grep -q "Python $PYTHON_VERSION"; then
        info "venv 기존 사용: $VENV_PATH ($($VENV_PATH/bin/python --version))"
    else
        if [ -e "$VENV_PATH" ]; then
            info "venv 무효 (bin/python 부재 또는 버전 불일치) — wipe + 재생성: $VENV_PATH"
            rm -rf "$VENV_PATH"
        fi
        info "venv 생성: $VENV_PATH (Python $PYTHON_VERSION)"
        uv venv "$VENV_PATH" --python "$PYTHON_VERSION" --seed
        venv_was_recreated=1
    fi

    # R10 MED-7: scripts/requirements.txt (운영 deps) 가 정본 — repo root requirements.txt 미존재.
    # uv pip install 은 already-installed 시 fast no-op (idempotent) — skip 최적화 제거.
    # 이전 MED-N3 의 PRE_UPDATE_REF diff 기반 skip 은 venv 가 partial install state 일 때 결함
    # (V1 VM 테스트 surface: previous install 이 Step 3 후 fail → venv 존재하지만 deps 미설치).
    local req_file="$WIKIHUB_SRC/scripts/requirements.txt"
    if [ -f "$req_file" ]; then
        info "deps 설치/갱신: scripts/requirements.txt (uv pip — idempotent)"
        uv pip install --python "$VENV_PATH/bin/python" -r "$req_file"
    else
        warn "scripts/requirements.txt 없음 — venv 생성만 (의존성 미설치)"
    fi

    # 사이드카 — /wh:setup 의 substitution 시 read
    echo "$VENV_PATH" > "$WIKIHUB_SRC/.venv_path"
    ok "Step 3 venv ($PYTHON_VERSION) + .venv_path 기록 완료"
}

# ──────────────────────────────────────────────────────────────────────
# Step 4. (폐기, ADR-0035) — gws CLI 설치 단계 제거. 변경 감지는 rclone lsjson 으로 일원화.
# ──────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────
# Step 4.5. rclone 설치 + chmod 0600 + rc port pre-check (v9, ADR-0025·0026·0035)
# ──────────────────────────────────────────────────────────────────────

# v9 R14-HIGH-1: GitHub Releases 가용성 회귀 대응 — 3회 retry @ 5min interval.
_curl_with_retry() {
    local url="$1" out="$2" attempts=3 wait_sec=300 i
    for ((i=1; i<=attempts; i++)); do
        if curl -fsSL --proto '=https' --tlsv1.2 --max-time 60 -o "$out" "$url"; then
            return 0
        fi
        warn "curl 실패 ($url) — ${i}/${attempts} 시도. ${wait_sec}s 후 재시도"
        sleep "$wait_sec"
    done
    err "curl ${attempts}회 실패 ($url) — GitHub 가용성 또는 네트워크 점검. status.github.com 확인 후 재실행"
    exit 2
}

# v9 R13-CRIT-2: install.sh §10.4.2 Step 5.5c spec 의 helper.
# yaml.vaults[*].options.rclone_rc_port 를 줄바꿈 단위로 출력. PyYAML 은 venv 에서만 활용 가능
# (Step 3 venv 생성 후). 빈 출력 = 모든 vault 가 rclone_rc_port 미설정.
_yaml_get_vault_rc_ports() {
    local yaml_file="$1"
    "$VENV_PATH/bin/python3" - "$yaml_file" <<'PYEOF'
import sys, yaml
try:
    cfg = yaml.safe_load(open(sys.argv[1])) or {}
except Exception as e:
    print(f"yaml 파싱 실패: {e}", file=sys.stderr)
    sys.exit(2)
for v in cfg.get("vaults", []):
    port = (v.get("options") or {}).get("rclone_rc_port")
    if port is not None:
        print(port)
PYEOF
}

# v9 R14-HIGH-2 보강: ss + lsof cross-check + EUID 경고.
_check_rc_port_available() {
    local port="$1"
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
        warn "install.sh 가 root 로 실행 중 — ss port check 가 user namespace mismatch 가능. 운영자 의도 확인 권장."
    fi
    if ss -tlnH "( sport = :${port} )" 2>/dev/null | grep -q ":${port}"; then
        err "rclone rc port ${port} 이미 사용 중 (ss) — wikihub.yaml.vaults[*].options.rclone_rc_port 변경 후 재실행"
        exit 2
    fi
    if command -v lsof >/dev/null 2>&1; then
        if lsof -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null | grep -q .; then
            err "rclone rc port ${port} 이미 사용 중 (lsof) — wikihub.yaml.vaults[*].options.rclone_rc_port 변경 후 재실행"
            exit 2
        fi
    fi
}

_install_rclone() {
    local pinned="${RCLONE_PINNED_VERSION:-1.69.1}"
    # R16-H1 (V<N> Phase 2 R16 SRE 리뷰, 2026-05-17): RCLONE_MIN_VERSION local 변수
    # 제거. v0.1.0 은 pinned 단일 enforce 만 사용. min/max range enforce 는 v0.2.x deferred
    # (config.py 의 rclone_min/max_version 필드는 spec 정의만, 활성 enforce 없음).

    if command -v rclone >/dev/null 2>&1; then
        local current
        current="$(rclone version 2>/dev/null | head -1 | awk '{print $2}' | sed 's/^v//')"
        # 단순 string compare 로 충분 (v0.1.0 — semantic compare 는 v0.2.x)
        if [[ -n "$current" && "$current" == "$pinned" ]]; then
            ok "rclone $current 이미 설치됨 (pinned 일치) — skip"
            return 0
        fi
        info "rclone $current 설치되어 있으나 pinned=$pinned 와 다름 — 재설치"
    fi

    local arch archive base tmpdir
    case "$(uname -m)" in
        aarch64|arm64) arch="arm64" ;;
        x86_64|amd64)  arch="amd64" ;;
        *) err "지원하지 않는 arch: $(uname -m)"; exit 2 ;;
    esac
    archive="rclone-v${pinned}-linux-${arch}.zip"
    base="https://github.com/rclone/rclone/releases/download/v${pinned}"
    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' RETURN
    info "rclone v${pinned} 설치 (GitHub Releases + SHA256SUMS verify + curl retry)"
    _curl_with_retry "${base}/${archive}"  "${tmpdir}/${archive}"
    _curl_with_retry "${base}/SHA256SUMS"  "${tmpdir}/SHA256SUMS"
    ( cd "$tmpdir" && grep -E "  ${archive}\$" SHA256SUMS | sha256sum -c - ) \
        || { err "rclone SHA256 verify 실패 — supply chain 위협 가능, 설치 중단"; exit 2; }
    unzip -q -o "${tmpdir}/${archive}" -d "${tmpdir}/rclone-extract"
    sudo install -m 0755 "${tmpdir}/rclone-extract/rclone-v${pinned}-linux-${arch}/rclone" /usr/local/bin/rclone
    rm -rf "$tmpdir"
    trap - RETURN
    command -v rclone >/dev/null 2>&1 || { err "rclone 설치 실패"; exit 2; }
    ok "rclone v${pinned} 설치 완료 (/usr/local/bin/rclone)"
}

_install_graphify() {
    # ADR-0036 — graphify CLI (PyPI graphifyy) PyPI 설치 + version 검증.
    # rclone 의 binary 설치 (_install_rclone) 와 달리 PyPI 패키지 — pip 의 hash-based install 의존.
    # supply chain hash pin enforce 는 v0.2.x 검토 트리거.
    local pin_spec="${GRAPHIFY_PIN_SPEC:-graphifyy>=0.8.0,<1.0.0}"

    if command -v graphify >/dev/null 2>&1; then
        local current
        current="$(graphify --version 2>/dev/null | awk '{print $NF}' || true)"
        if [[ -n "$current" ]]; then
            info "graphify $current 이미 설치됨 — pip install 로 pin 재확인"
        fi
    fi

    info "graphify (PyPI: $pin_spec) 설치 — $VENV_PATH/bin/pip install"
    "$VENV_PATH/bin/pip" install --quiet "$pin_spec" \
        || { err "graphify 설치 실패 — PyPI 접근 또는 pip cache 확인"; exit 2; }

    # venv 의 bin/ 이 PATH 에 우선해야 systemd unit 의 PATH={venv_path}/bin:... 이 graphify 호출.
    command -v graphify >/dev/null 2>&1 \
        || { err "graphify 설치됐으나 PATH 에서 찾을 수 없음 — $VENV_PATH/bin 확인"; exit 2; }

    local installed
    installed="$(graphify --version 2>/dev/null | awk '{print $NF}' || true)"
    ok "graphify ${installed:-?} 설치 완료 ($pin_spec)"
}

_install_yq() {
    # mikefarah/yq (go version) — `_system/commands/lint.md` + `graphify.md` 의 `yq '.x // default'`
    # 문법 정합. Ubuntu apt 의 `yq` 는 다른 도구 (Python wrapper) — 문법 호환 안 됨.
    # GitHub Releases 의 single-binary direct download — supply chain: HTTPS + GitHub host trust.
    # SHA256 verify 는 v0.2.x 검토 트리거 — mikefarah/yq 의 multi-hash `checksums` 형식
    # (BLAKE-384/SHA-256/MD5 columnar) 추출 보강 필요 (rclone 의 SHA256SUMS 단순 형식과 다름).
    local pinned="${YQ_PINNED_VERSION:-4.44.3}"

    if command -v yq >/dev/null 2>&1; then
        local current
        current="$(yq --version 2>/dev/null | awk '{print $NF}' | sed 's/^v//')"
        if [[ -n "$current" && "$current" == "$pinned" ]]; then
            ok "yq $current 이미 설치됨 (pinned 일치) — skip"
            return 0
        fi
        info "yq ${current:-?} 설치되어 있으나 pinned=$pinned 와 다름 — 재설치"
    fi

    local arch base tmpdir
    case "$(uname -m)" in
        aarch64|arm64) arch="arm64" ;;
        x86_64|amd64)  arch="amd64" ;;
        *) err "지원하지 않는 arch: $(uname -m)"; exit 2 ;;
    esac
    base="https://github.com/mikefarah/yq/releases/download/v${pinned}"
    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' RETURN
    info "yq v${pinned} 설치 (GitHub Releases + curl retry)"
    _curl_with_retry "${base}/yq_linux_${arch}" "${tmpdir}/yq" \
        || { err "yq 다운로드 실패 ($base/yq_linux_${arch})"; exit 2; }
    chmod +x "${tmpdir}/yq"
    # quick smoke test (binary execution) — corrupt download 차단
    "${tmpdir}/yq" --version >/dev/null 2>&1 \
        || { err "yq binary 실행 검증 실패 — 다운로드 손상 의심"; exit 2; }
    sudo install -m 0755 "${tmpdir}/yq" /usr/local/bin/yq
    rm -rf "$tmpdir"
    trap - RETURN
    command -v yq >/dev/null 2>&1 || { err "yq 설치 실패"; exit 2; }
    local installed
    installed="$(yq --version 2>/dev/null | awk '{print $NF}' | sed 's/^v//')"
    ok "yq v${installed} 설치 완료 (/usr/local/bin/yq)"
}

_enforce_rclone_conf_perms() {
    local conf="${RCLONE_CONFIG:-${HOME}/.config/rclone/rclone.conf}"
    if [[ -f "$conf" ]]; then
        chmod 0600 "$conf"
        info "rclone.conf 권한 0600 enforce: $conf"
    else
        warn "rclone.conf 미존재 — /wh:setup Step 5.5 (rclone OAuth) 안내 대상"
    fi
}

# ADR-0031 §Decision B (MED-S2 design review): install-time version fact 를 sidecar 에 기록.
# ADR-0035: gws 키 제거. `/wh:setup` Step 0 의 gws_min_version 비교도 폐기.
# stdout 파싱 brittleness 회피 (rclone --version 형식 변경 시 fallback 으로만 사용).
#
# atomic write (CR1-HIGH-3 review 반영): tmpfile + sync + mv. same-directory + PID suffix +
# cleanup trap (errexit 또는 중단 시 orphan tmp 회수) + stale tmp 5분 이상 자동 정리.
_write_installed_versions_sidecar() {
    local target="$WIKIHUB_SRC/_system/INSTALLED_VERSIONS.json"
    local target_dir; target_dir="$(dirname "$target")"
    local target_base; target_base="$(basename "$target")"
    mkdir -p "$target_dir"
    # Stale .tmp.* 5분 이상 자동 cleanup (이전 process 의 SIGTERM/errexit 흔적).
    find "$target_dir" -maxdepth 1 -name "${target_base}.tmp.*" -mmin +5 -delete 2>/dev/null || true

    local rclone_v graphify_v yq_v
    rclone_v="$(rclone version 2>/dev/null | awk '/^rclone v/{print $2; exit}' | sed 's/^v//' || true)"
    # ADR-0036 — graphify 도 INSTALLED_VERSIONS.json 의 fact 로 기록. graphify --version 형식 미보장 → 단순 last-field 추출.
    graphify_v="$(graphify --version 2>/dev/null | awk '{print $NF; exit}' || true)"
    # yq (mikefarah/yq go version) — `yq --version` 출력 last-field "v4.44.3" → v prefix strip.
    yq_v="$(yq --version 2>/dev/null | awk '{print $NF; exit}' | sed 's/^v//' || true)"

    local tmp="${target}.tmp.$$"
    # 본 함수 ERR/RETURN 시 tmp 자동 회수 — set -e 환경에서 cat/sync fail 시 orphan 차단.
    trap "rm -f '$tmp' 2>/dev/null || true" RETURN ERR
    cat > "$tmp" <<EOF
{
  "schema_version": 1,
  "rclone": "${rclone_v:-}",
  "graphify": "${graphify_v:-}",
  "yq": "${yq_v:-}",
  "uv": "${UV_VERSION}",
  "wikihub": "$(cat "$WIKIHUB_SRC/_system/VERSION" 2>/dev/null || echo unknown)",
  "written_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
    # Ubuntu 22.04+ coreutils 8.32 의 `sync -f <file>` 는 해당 파일 의 FS data 만 flush.
    # 실패 시 fallback 으로 global sync (cost 증가하나 정합 유지).
    sync -f "$tmp" 2>/dev/null || sync || true
    mv "$tmp" "$target"
    info "Step 4.5 INSTALLED_VERSIONS.json 작성: $target"
}

_step45_rclone() {
    _install_rclone
    _enforce_rclone_conf_perms
    _install_graphify
    _install_yq    # lint.md/graphify.md 의 runtime yq 호출 의존
    _write_installed_versions_sidecar
    # rc port pre-check — yaml 이 이미 Step 5 에서 복사된 상태 가정. 첫 실행 (yaml 미복사) 시 skip.
    if [[ -f "$WIKIHUB_HOME/wikihub.yaml" ]]; then
        local ports
        ports="$(_yaml_get_vault_rc_ports "$WIKIHUB_HOME/wikihub.yaml" 2>/dev/null || true)"
        if [[ -n "$ports" ]]; then
            while IFS= read -r port; do
                [[ -z "$port" ]] && continue
                _check_rc_port_available "$port"
            done <<<"$ports"
            ok "rclone rc port 가용성 확인 완료"
        fi
    else
        info "wikihub.yaml 미존재 (첫 실행) — rc port pre-check 는 다음 install.sh 호출 시 수행"
    fi
    ok "Step 4.5 rclone 설치 + 권한 + port check 완료"
}

# ──────────────────────────────────────────────────────────────────────
# Step 5. instance dir 보장 (ADR-0031 이후 — yaml 미관여, ADR-0035 — credentials dir 폐기)
# ──────────────────────────────────────────────────────────────────────
# 본 함수는 yaml 한 글자도 안 만짐 (ADR-0031 §Decision A 정합).
# wikihub.yaml 의 시작·끝 책임은 `/wh:setup` Step 0 단독.
# 메인테이너가 install.sh 직후 `/wh:setup` 호출 시 .example → operational yaml materialize.
#
# ADR-0035: ~/.credentials/wikihub/ 폐기 — rclone.conf 단일 인증 자료.
# rclone.conf 권한 검증은 _step45_rclone 의 _enforce_rclone_conf_perms 가 책임.

_step5_instance_dirs() {
    mkdir -p "$WIKIHUB_HOME"
    # ADR-0036 + ADR-0038 (v0.1.7 follow-up) — graphify subprocess 의 env namespace 격리.
    # systemd unit (`wikihub-lint.service`) 의 `EnvironmentFile=-%h/.config/wikihub/env` 가 본 파일을 lenient 로 읽음.
    # default 3 키 (WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_<ENDPOINT|API_KEY|MODEL>) prefill — 운영자가 ollama_gemma 외 profile 사용 시만 편집 (cookbook 참조).
    local wh_config_dir="$HOME/.config/wikihub"
    local wh_env_file="$wh_config_dir/env"
    mkdir -p "$wh_config_dir"
    chmod 700 "$wh_config_dir"
    if [[ ! -f "$wh_env_file" ]]; then
        cat > "$wh_env_file" <<'EOF'
# wikihub 운영 자료 — systemd unit 의 EnvironmentFile= 가 lenient 로 읽음 (ADR-0036 + ADR-0038).
# 본 파일의 자료는 graphify subprocess 호출 시점에 namespace 격리되어 explicit 주입 (Hermes parent leak 차단).
# 추가 profile (openrouter / openai / claude / gemini / deepseek / kimi) cookbook:
#   → docs/graphify-backend-test-reference.md §6 (Alternative profile examples)
#
# 명명 컨벤션: WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL>
# yaml `operations.graphify_profile` 값 (lowercase) 과 1:1 매칭.

# === default active: ollama_gemma (Ollama daemon + gemma4:31b-cloud) ===
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_ENDPOINT=http://127.0.0.1:11434
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_API_KEY=local-daemon
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_MODEL=gemma4:31b-cloud

# === Alert channel — Telegram bot (ADR-0037 §D1) ===
# wikihub-ops-alert.service 가 fatal alert 발화 시 Telegram bot 으로 메시지 발송.
# bot 생성: @BotFather 에서 /newbot → token 받음 + chat_id 는 @userinfobot 활용.
#    TELEGRAM_ALERT_BOT_TOKEN=123456:ABC...
#    TELEGRAM_ALERT_CHAT_ID=-100123456
EOF
    fi
    chmod 600 "$wh_env_file"
    ok "Step 5 instance dir + ~/.config/wikihub/env 확인 ($WIKIHUB_HOME)"
}

# ──────────────────────────────────────────────────────────────────────
# Step 6. agent skill 초기 등록
# ──────────────────────────────────────────────────────────────────────

# ─── F5 ADR-0032·0033 — Hermes skill registration ────────────────────
# WIKIHUB_SKILLS 정본 list. ADR-0032 §sub-2 (install-time materialized)
WIKIHUB_SKILLS=(wh-ingest wh-lint wh-query wh-graphify wh-setup)

# Hermes config path. operator override: $HERMES_CONFIG_HOME (테스트 용도)
_hermes_config_path() {
    echo "${HERMES_CONFIG_HOME:-$HOME/.hermes}/config.yaml"
}

# operational yaml 의 schema 보강 — v0.1.5+ 신설 field 자동 추가 (부재 시만).
# PTY-safe — prompt 0, idempotent. 운영자 값 보존 (ADR-0031 §Note value-mutation 회피).
# Group B (자동 추가) + A4 (W_graphify_profile_invalid warn — 운영자 yaml 편집 mistake fail-fast surface).
_migrate_agent_schema() {
    local yaml="$WIKIHUB_HOME/wikihub.yaml"
    [[ -f "$yaml" ]] || return 0

    # drift detect — Python single-shot 으로 모든 3-group 검사 + flag 반환.
    # 단순 grep 으로 안전한 비교가 어려운 nested key (예: vaults[].options.bootstrap_allowed)
    # 가 있어서 yaml load + dict navigation 으로 detect.
    local drift_flags
    drift_flags="$("$VENV_PATH/bin/python3" - "$yaml" <<'PYEOF'
import sys, yaml as _yaml
path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as f:
        data = _yaml.safe_load(f) or {}
except Exception:
    print("")
    sys.exit(0)

agent = data.get("agent") or {}
operations = data.get("operations") or {}
vaults = data.get("vaults") or []

flags = []

# Group B — v0.1.5+ 신설 field 부재 (자동 추가 — 안전 default)
if "timeout_sec" not in agent:
    flags.append("B_agent_timeout_sec")
if "models" not in agent:
    flags.append("B_agent_models")
if "pending_alert_age_sec" not in operations:
    flags.append("B_pending_alert_age_sec")
if "lint_contradiction_check" not in operations:
    flags.append("B_lint_contradiction_check")
if "graphify_enabled" not in operations:
    flags.append("B_graphify_enabled")
if "graphify_backend" not in operations:
    flags.append("B_graphify_backend")
if "graphify_min_version" not in operations:
    flags.append("B_graphify_min_version")
if "graphify_max_version" not in operations:
    flags.append("B_graphify_max_version")
if "graphify_profile" not in operations:
    flags.append("B_graphify_profile")
if "lint_interval_hours" not in operations:
    flags.append("B_lint_interval_hours")

# Group B per-vault — sync_interval_sec 부재 vault 자동 추가 (yaml.example v0.1.6 default 1h)
for idx, v in enumerate(vaults):
    if isinstance(v, dict) and "sync_interval_sec" not in v:
        vid = v.get("id", f"idx{idx}")
        flags.append(f"B_vault_sync_interval_sec:{vid}")

# A4 (ADR-0038) — 기존 graphify_profile 값의 정규식 fail-fast (install-time, non-fatal warn).
# 운영자가 yaml 편집해 invalid profile 명 (대문자/특수문자/공백) 박은 경우 install 시점 surface.
# 값 mutation 안 함 (ADR-0031 §Note 정합) — warn 만, 운영자가 직접 수정.
import re as _re
_profile = operations.get("graphify_profile")
if _profile and not _re.match(r"^[a-z][a-z0-9_]*$", str(_profile)):
    flags.append(f"W_graphify_profile_invalid:{_profile}")

print("\n".join(flags))   # newline separator — profile 값에 `,` 박힌 경우 robust (code review 1 §M1)
PYEOF
)"

    [[ -z "$drift_flags" ]] && return 0

    # info log 출력 — 운영자가 어떤 drift 가 감지됐는지 surface
    info "schema drift detected — auto migration (PTY-safe, idempotent):"
    local f
    # newline-separated flags — profile 값에 `,` 박힌 경우 안전 (code review 1 §M1)
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        case "$f" in
            B_agent_timeout_sec)        info "  - [v0.1.5] agent.timeout_sec 부재 → 1200 추가 (DeepSeek/MiniMax latency 대응)" ;;
            B_agent_models)             info "  - [v0.1.5] agent.models 블록 부재 → {wh-lint, wh-ingest} 추가 (per-skill --model lock)" ;;
            B_pending_alert_age_sec)    info "  - [ADR-0037] operations.pending_alert_age_sec 부재 → 3600 추가" ;;
            B_lint_contradiction_check) info "  - [v0.1.5] operations.lint_contradiction_check 부재 → true 추가" ;;
            B_graphify_enabled)         info "  - [v0.1.5] operations.graphify_enabled 부재 → true 추가" ;;
            B_graphify_backend)         info "  - [ADR-0036] operations.graphify_backend 부재 → \"\" 추가 (auto-detect)" ;;
            B_graphify_min_version)     info "  - [ADR-0036] operations.graphify_min_version 부재 → \"0.8.0\" 추가" ;;
            B_graphify_max_version)     info "  - [ADR-0036] operations.graphify_max_version 부재 → \"0.99.99\" 추가" ;;
            B_graphify_profile)         info "  - [ADR-0038] operations.graphify_profile 부재 → \"ollama_gemma\" 추가" ;;
            B_lint_interval_hours)      info "  - [v0.1.6] operations.lint_interval_hours 부재 → 3 추가 (default 3h)" ;;
            B_vault_sync_interval_sec:*) info "  - [v0.1.6] vaults[${f#B_vault_sync_interval_sec:}].sync_interval_sec 부재 → 3600 추가 (default 1h)" ;;
            W_graphify_profile_invalid:*) warn "  - [ADR-0038] operations.graphify_profile=\"${f#W_graphify_profile_invalid:}\" 가 정규식 (^[a-z][a-z0-9_]*$) fail — 운영자 yaml 수정 권장 (자동 변경 안 함)" ;;
        esac
    done <<< "$drift_flags"

    # backup — 변경 발생 시만 (위 early return 통과한 경우)
    local backup="$yaml.wikihub-bak.$(date -u +%Y%m%dT%H%M%SZ)"
    cp -p "$yaml" "$backup"
    info "backup: $backup"

    # ADR-0032 §Note (v0.1.5, 2026-05-20) — prompt 분기 제거. `[[ -t 0 ]]` 가 Hermes PTY
    # 환경에서 거짓 양성 (subprocess 에 pty slave 할당 → stdin terminal-like) 으로 v0.1.3 →
    # v0.1.4 cycle 의 root cause. backup (.wikihub-bak.<utc_iso>) 가 의도 override safety
    # net — 운영자가 의도와 다르면 cp 1회로 즉시 복원. **값 변경은 자동 회피** — 운영자 의도
    # (또는 schema drift) 구분 불가 → 보수적으로 운영 값 보호 (예: vaults[].sync_interval_sec,
    # operations.lint_interval_hours).

    "$VENV_PATH/bin/python3" - "$yaml" <<'PYEOF'
import sys, ruamel.yaml
path = sys.argv[1]
yaml = ruamel.yaml.YAML(typ="rt")
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)
with open(path, encoding="utf-8") as f:
    data = yaml.load(f)

agent = data.setdefault("agent", {})

# Group B — v0.1.5+ 신설 field 자동 추가 (안전 default, 부재 시만)
if "timeout_sec" not in agent:
    agent["timeout_sec"] = 1200
if "models" not in agent:
    # ruamel CommentedMap 으로 추가 — 다른 field 의 주석 보존
    from ruamel.yaml.comments import CommentedMap
    models = CommentedMap()
    models["wh-lint"] = "deepseek-v4-flash"
    models["wh-ingest"] = "deepseek-v4-pro"
    agent["models"] = models

operations = data.setdefault("operations", {})
_op_defaults = {
    "pending_alert_age_sec": 3600,
    "lint_contradiction_check": True,
    "graphify_enabled": True,
    "graphify_backend": "",
    "graphify_min_version": "0.8.0",
    "graphify_max_version": "0.99.99",
    "graphify_profile": "ollama_gemma",
    "lint_interval_hours": 3,           # v0.1.6 default 3h (v0.1.5 era 24h 에서 변경)
}
for k, v in _op_defaults.items():
    if k not in operations:
        operations[k] = v

# Group B per-vault — sync_interval_sec 부재 vault 자동 추가 (yaml.example v0.1.6 default 1h)
vaults = data.get("vaults") or []
for v in vaults:
    if isinstance(v, dict) and "sync_interval_sec" not in v:
        v["sync_interval_sec"] = 3600

tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    yaml.dump(data, f)
import os
os.replace(tmp, path)
PYEOF

    ok "schema migration 완료 (backup: $backup)"
    info "  운영자 의도 영향 field (sync_interval_sec, lint_interval_hours 등) 의 새 default 적용은"
    info "  wikihub.yaml.example 참조 후 manual edit + install.sh 재실행 권장."
}

# `_system/skills/_generated/wh-<cmd>/SKILL.md` 5건 materialized.
# frontmatter source + _system/commands/<cmd>.md 본문 결합 (ADR-0032 §sub-2 β).
_materialize_skills() {
    local generated="$WIKIHUB_SRC/_system/skills/_generated"
    mkdir -p "$generated"

    # stale cleanup (R3-CR3-2 B-MED-5) — 5건 외 entries 제거
    if [[ -d "$generated" ]]; then
        for entry in "$generated"/*/; do
            [[ -d "$entry" ]] || continue
            local name="$(basename "$entry")"
            local found=0
            for skill in "${WIKIHUB_SKILLS[@]}"; do
                [[ "$name" == "$skill" ]] && { found=1; break; }
            done
            if [[ "$found" == 0 ]]; then
                info "stale skill 정리: $entry"
                rm -rf "$entry"
            fi
        done
    fi

    local count=0
    for skill in "${WIKIHUB_SKILLS[@]}"; do
        local cmd="${skill#wh-}"   # wh-ingest → ingest
        local frontmatter="$WIKIHUB_SRC/_system/skills/$skill.frontmatter.yaml"
        local commands_md="$WIKIHUB_SRC/_system/commands/$cmd.md"
        local target_dir="$generated/$skill"
        local target="$target_dir/SKILL.md"

        if [[ ! -f "$frontmatter" ]]; then
            err "frontmatter source 부재: $frontmatter"
            return 2
        fi
        if [[ ! -f "$commands_md" ]]; then
            err "commands playbook 부재: $commands_md"
            return 2
        fi

        mkdir -p "$target_dir"
        {
            echo "---"
            cat "$frontmatter"
            echo "---"
            echo ""
            cat "$commands_md"
        } > "$target.tmp"
        mv -f "$target.tmp" "$target"
        count=$((count + 1))
    done
    ok "skill materialized: $count 건 → $generated/"
}

# Hermes ~/.hermes/config.yaml 의 skills.external_dirs 패치 (ADR-0032 §sub-3·4).
# flock + backup + sha256 + realpath 비교 + marker comment.
_patch_hermes_external_dirs() {
    local hermes_config; hermes_config="$(_hermes_config_path)"
    local hermes_dir; hermes_dir="$(dirname "$hermes_config")"
    local lock_path="$hermes_config.lock"
    local wikihub_skill_dir
    wikihub_skill_dir="$("$VENV_PATH/bin/python3" -c \
        "import os; print(os.path.realpath('$WIKIHUB_SRC/_system/skills/_generated'))")"

    mkdir -p "$hermes_dir"

    # flock advisory — 5초 retry × 12회 (총 60s)
    exec 200>"$lock_path"
    local retries=0
    while ! flock -nx 200; do
        retries=$((retries + 1))
        if (( retries >= 12 )); then
            err "Hermes config lock 획득 실패 (60s timeout) — 다른 Hermes/wikihub 인스턴스가 mutate 중"
            exec 200>&-
            return 2
        fi
        sleep 5
    done

    # PRE_HASH + backup
    local pre_hash=""
    local backup=""
    if [[ -f "$hermes_config" ]]; then
        pre_hash="$(sha256sum "$hermes_config" | awk '{print $1}')"
        backup="$hermes_config.wikihub-bak.$(date -u +%Y%m%dT%H%M%SZ)"
        cp -p "$hermes_config" "$backup"
    fi

    # ruamel atomic write + idempotent check (Python helper)
    local result
    result="$("$VENV_PATH/bin/python3" - "$hermes_config" "$wikihub_skill_dir" <<'PYEOF'
import os, sys
import ruamel.yaml
from ruamel.yaml.comments import CommentedSeq

path = sys.argv[1]
wikihub_dir = sys.argv[2]
MARKER = "managed by wikihub install.sh — remove to disable auto-discovery"

yaml = ruamel.yaml.YAML(typ="rt")
yaml.preserve_quotes = True

if os.path.exists(path):
    with open(path, encoding="utf-8") as f:
        data = yaml.load(f) or {}
else:
    data = {}

skills = data.setdefault("skills", {})
ext = skills.get("external_dirs")
if ext is None:
    ext = CommentedSeq()
    skills["external_dirs"] = ext

# realpath 정규화 비교
existing_real = []
for p in ext:
    try:
        existing_real.append(os.path.realpath(os.path.expanduser(str(p))))
    except Exception:
        existing_real.append(str(p))

if wikihub_dir in existing_real:
    print("noop", end="")
    sys.exit(0)

ext.append(wikihub_dir)
# marker comment — ruamel 의 yaml_add_eol_comment (index = len(ext)-1)
try:
    ext.yaml_add_eol_comment(MARKER, len(ext) - 1, column=60)
except Exception:
    pass  # comment 부착 실패해도 entry 자체는 유지

tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    yaml.dump(data, f)
os.replace(tmp, path)
print("patched", end="")
PYEOF
)"

    # POST_HASH
    local post_hash=""
    [[ -f "$hermes_config" ]] && post_hash="$(sha256sum "$hermes_config" | awk '{print $1}')"

    flock -u 200
    exec 200>&-

    if [[ "$result" == "patched" ]]; then
        info "Hermes config 패치 — $hermes_config (backup: ${backup:-신규생성})"
        info "  pre_sha256:  ${pre_hash:-empty}"
        info "  post_sha256: $post_hash"
    elif [[ "$result" == "noop" ]]; then
        info "Hermes config 이미 wikihub skill path 포함 — 변경 없음"
        # backup 도 불필요 — cleanup
        [[ -n "$backup" && -f "$backup" ]] && rm -f "$backup"
    else
        err "Hermes config 패치 결과 비예상: $result"
        return 2
    fi

    # 7일 초과 backup cleanup
    find "$hermes_dir" -maxdepth 1 -name 'config.yaml.wikihub-bak.*' -mtime +7 -delete 2>/dev/null || true
}

# 등록 후 검증 (ADR-0032 §sub-3 검증 단계)
_verify_hermes_skill_registration() {
    local agent_binary="$1"
    info "Hermes skill 인식 검증 — $agent_binary skills list"
    local list_output
    if ! list_output="$("$agent_binary" skills list 2>&1)"; then
        warn "hermes skills list 실패 — 검증 skip"
        return 0
    fi
    local missing=()
    for skill in "${WIKIHUB_SKILLS[@]}"; do
        echo "$list_output" | grep -qE "(^|[[:space:]])$skill([[:space:]]|$)" \
            || missing+=("$skill")
    done
    if (( ${#missing[@]} == 0 )); then
        ok "Hermes skill 5건 인식 확인"
        return 0
    fi
    info "미인식 skill: ${missing[*]} — \`hermes skills audit\` 1회 호출 후 재검증"
    if "$agent_binary" skills audit >/dev/null 2>&1; then
        list_output="$("$agent_binary" skills list 2>&1 || true)"
        local still_missing=()
        for skill in "${missing[@]}"; do
            echo "$list_output" | grep -qE "(^|[[:space:]])$skill([[:space:]]|$)" \
                || still_missing+=("$skill")
        done
        if (( ${#still_missing[@]} == 0 )); then
            ok "audit 후 5건 인식 확인"
            return 0
        fi
        warn "audit 후에도 미인식: ${still_missing[*]} — Hermes 재시작 또는 운영자 수동 검증 필요"
    fi
}

_step6_agent_skill() {
    info "agent skill 등록 (ADR-0032·0033 F5)"

    # 1. Hermes 존재 검사 (ADR-0032 §sub-1·sub-2 의 Hermes detect gate, CR2-CRIT-1)
    local agent_binary="${HERMES_BIN:-}"
    if [[ -z "$agent_binary" ]]; then
        local yaml="$WIKIHUB_HOME/wikihub.yaml"
        if [[ -f "$yaml" ]]; then
            agent_binary="$("$VENV_PATH/bin/python3" -c \
                "import yaml,sys; print(yaml.safe_load(open(sys.argv[1])).get('agent',{}).get('binary',''))" \
                "$yaml" 2>/dev/null || true)"
        fi
        [[ -z "$agent_binary" ]] && agent_binary="$(command -v hermes 2>/dev/null || true)"
    fi

    if [[ -z "$agent_binary" || ! -x "$agent_binary" ]]; then
        warn "Hermes binary 미설치 또는 미실행 — systemd render/enable skip"
        warn "  Hermes 설치 후 install.sh 재호출 권장 (또는 wikihub.yaml.agent.binary 명시 후 재호출)"
        SKIP_SYSTEMD_RENDER=1
        export SKIP_SYSTEMD_RENDER
        ok "Step 6 — Hermes 부재 detect, 후속 systemd 단계 skip"
        return 0
    fi

    # 2. 운영자 yaml schema 보강 (Group B v0.1.5+ field auto-add + A4 W_graphify_profile_invalid warn — ADR-0031 §Note schema-only mutation)
    _migrate_agent_schema || return 2

    # 3. SKILL.md materialize (ADR-0032 §sub-2 β)
    _materialize_skills || return 2

    # 4. ~/.hermes/config.yaml 의 external_dirs 패치 (ADR-0032 §sub-3·sub-4)
    _patch_hermes_external_dirs || return 2

    # 5. 등록 후 검증
    _verify_hermes_skill_registration "$agent_binary"

    ok "Step 6 agent skill 등록 완료 (5건 materialized + external_dirs 패치)"
}

# ──────────────────────────────────────────────────────────────────────
# Step 7. linger 활성화 (ADR-0021 D1)
# ──────────────────────────────────────────────────────────────────────

_step7_linger() {
    # idempotent skip
    if loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=yes"; then
        ok "Step 7 linger 기존 활성화 (skip)"
        return 0
    fi
    info "linger 활성화 (sudo 필요): loginctl enable-linger $USER"

    # R10 HIGH-6 fix: linger 실패 회복 — fatal exit 대신 명시 안내 + 운영자 수동 fallback 경로
    # R10 MED-1 fix: SKIP_CONFIRM 비교를 `-n` 로 통일 (L122 와 정합 — 임의 truthy 값 허용)
    # V8 결함 #8 fix (2026-05-17): NOPASSWD pre-check 를 최우선 분기로 — multipass exec 등
    # non-tty 환경에서 `[ -c /dev/tty ]` 가 true 여도 실제 open 은 fail 하는 케이스 회피
    local linger_ok=0
    if sudo -n true 2>/dev/null; then
        # NOPASSWD 가용 — TTY 무관 (multipass·OCI ubuntu 사용자 default)
        if sudo -n loginctl enable-linger "$USER"; then
            linger_ok=1
        fi
    elif [ -n "$SKIP_CONFIRM" ]; then
        # SKIP_CONFIRM 명시인데 NOPASSWD 부재 — sudoers 사전 설정 필요
        err "SKIP_CONFIRM 모드인데 NOPASSWD 부재 — loginctl enable-linger 비대화 호출 불가"
    elif [ -c /dev/tty ] && (: >/dev/tty) 2>/dev/null; then
        # ADR-0023: curl-pipe 모드여도 /dev/tty 로 password prompt. open 가능 여부도 검증.
        if sudo loginctl enable-linger "$USER" < /dev/tty; then
            linger_ok=1
        fi
    else
        # /dev/tty open 불가 + NOPASSWD 부재 — R10 HIGH-6 fail-soft 로 흘러감
        warn "비대화 환경 + NOPASSWD 부재 — linger 자동 활성화 불가, 운영자 수동 fallback 안내"
    fi

    if [ "$linger_ok" = "1" ]; then
        # 검증 — 실제로 활성화됐는지 (polkit 정책 미설정 등으로 silent skip 가능성)
        if loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=yes"; then
            ok "Step 7 linger 활성화 완료 (검증)"
            return 0
        fi
        warn "linger 명령은 성공했으나 활성화 검증 실패 (polkit 정책 의심)"
    fi

    # 실패 — V12 acceptance invariant 깨질 위험 명시
    err "linger 활성화 실패 — V12 (reboot resilience) 가 작동 안 함"
    err "      운영자 수동 fallback 옵션:"
    err "        1. 별도 sudo 권한자가: sudo loginctl enable-linger $USER"
    err "        2. 또는 ADR-0021 의 D2 fallback (system-level unit) 절차 — analysis_and_design.md §3.4 참조"
    err "      install.sh 의 다른 Step 은 이미 완료 — linger 만 사후 수정해도 V12 정합 가능"
    # exit 1 대신 명시 warning + 0 으로 종료 — 운영자가 다른 단계 산출물 활용 가능
    return 0
}

# ──────────────────────────────────────────────────────────────────────
# Step 8. 안내 (ADR-0022 E3 — 실제 trigger 는 /wh:setup)
# ──────────────────────────────────────────────────────────────────────

_step8_guide() {
    cat <<EOF

${C_OK}=== WikiHub 설치 완료 ===${C_RST}

[경로 구조]
  $WIKIHUB_HOME/                          # ★ 운영 자산 (ADR-0034 — data-first, 메인테이너 편집 대상)
      ├── wikihub.yaml                    # 운영 정본 — **/wh-setup 첫 호출이 .example 으로부터 생성 (ADR-0031)**
      ├── _state/<vault_id>/              # file_map·retry·last_sync·last_failure (자동, ADR-0035: cursor 폐기)
      ├── vault/<vault_id>/               # vault local mirror — rclone mount (자동)
      └── wiki/                           # 통합 wiki (자동)
  $WIKIHUB_SRC/                           # 시스템 코드 (XDG, install.sh 가 git clone — sparse, ADR-0023·ADR-0034)
  ~/.config/rclone/                       # rclone.conf — OAuth token 단일 인증 자료 (ADR-0035)
  ~/.config/wikihub/env                   # graphify Pass 3 LLM API key (ADR-0036, chmod 600)
  $VENV_PATH/                             # Python venv (install.sh 관리, 메인테이너 미관여 — graphify 도 venv 내부)
  ~/.config/systemd/user/                 # systemd unit (install.sh _step8_systemd_render 관리)

${C_WARN}⚠ wikihub.yaml 은 아직 부재합니다 (ADR-0031 §Decision A — install.sh 는 yaml 미관여).${C_RST}
${C_WARN}  /wh:setup 호출 전에 systemd timer enable 또는 reboot 금지 — vault@.service 가 fail-loop.${C_RST}

다음 단계:
  1. /wh:setup 호출 — .example 으로부터 wikihub.yaml 자동 생성 (ADR-0031 Step 0):
       <agent_invocation> "/wh:setup"
     생성된 yaml 의 maintainer field (vault id, root_folder_id, fatal_webhook_url 등) 편집.
  2. rclone OAuth 발급 (ADR-0035 — gws SA 폐기, rclone.conf 단일 인증 자료):
       rclone config              # remote name 은 wikihub.yaml.vaults[*].options.rclone_remote_name 정합
       chmod 0600 ~/.config/rclone/rclone.conf
  3. graphify LLM 자료 — default (ollama_gemma + local Ollama daemon) 미사용 시 (ADR-0038):
       \$EDITOR ~/.config/wikihub/env
       # 명명: WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL>
       # 추가 profile cookbook → docs/graphify-backend-test-reference.md §6
       # yaml \`operations.graphify_profile\` 값 변경도 함께 (default ollama_gemma).
       # 미입력 상태에서도 systemd start 자체는 성공 — graphify subprocess 만 fail.
  4. /wh:setup --enable 호출 — drift 동기화 + systemd unit + 첫 ingest prompt:
       <agent_invocation> "/wh:setup --enable"

[운영 비용 환기 — graphify Pass 3 (ADR-0036)]
  wh-lint timer (default 3h, v0.1.5) 가 graphify chain 호출. wiki page 별 Claude/OpenAI subagent 호출
  발생 — 운영자 API 비용 모델 인지 필요. 호출 빈도 통제: operations.lint_interval_hours 조정.

[Hermes config.yaml 권장 (wikihub 정본 영역 외 — 운영자 책임)]
  ~/.hermes/config.yaml 의 다음 필드 권장 설정:
    delegation.model: minimax-m2.5         # wh-lint Step 6 등 subagent — non-reasoning 안정성 + 한자→한글 정합
  wh-ingest·wh-lint 메인 모델은 wikihub agent.models 가 systemd \`--model\` 으로 lock — hermes
  model.default 와 무관. Telegram 대화·미명시 skill (wh-query·wh-graphify·wh-setup) 의
  model.default 는 운영자 일반 선호로 결정.

업데이트는 같은 명령 한 번 더 (ADR-0010 + ADR-0030):
  curl -fsSL https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh | bash

[install/update 동작 — dual-mode (ADR-0030)]
  detect: $WIKIHUB_SRC/_system/VERSION + .git AND → update path / 미만족 → fresh path.
  update path: unstaged guard → systemd stop (15min grace) → git fetch + reset → render →
               daemon-reload → systemd start → verify. 실패 시 자동 rollback (직전 ref 복귀).
  fresh path: clean wipe + clone (ADR-0023 보존). user 파일 (instance.root) 미터치.
  명시적 재설치: install.sh --force-fresh (5초 confirm + 3중 safety guard).
  특정 버전 pin: install.sh --version v0.1.0 (rollback 포함).

[운영 진단 명령 — R10 HIGH-2 + R16-M6·L3]
  vault sync 로그:    journalctl --user -t wikihub-vault-<vault_id> --since '24h ago'
  lint 로그:          journalctl --user -t wikihub-lint --since '24h ago'
  fatal alert 로그:   journalctl --user -t wikihub-ops-alert --since '24h ago'
                       (alert 발송 실패는 "webhook 발송 실패" warn 로 기록)
  mount 로그:         journalctl --user -t wikihub-mount-<vault_id> --since '24h ago'
  timer 상태:         systemctl --user list-timers '*wikihub*' 'lint*' '*-ingest*'
  pending monitor:    systemctl --user status wikihub-pending-monitor.timer  /  journalctl --user -t wikihub-pending-monitor
  alert 발화 (test):  systemctl --user start wikihub-ops-alert.service  (Telegram bot / webhook 검증)
  install 로그:       cat $WIKIHUB_HOME/install.log
  last_failure 요약:  for s in $WIKIHUB_HOME/_state/*/last_failure.json; do
                        [ -f "\$s" ] && echo "─ \$s" && cat "\$s"; done
                       (scope=vault: sync layer, scope=mount: rclone OAuth/SA — V<N> 결함 #7)

[rclone 디버그 (R16-L3) — token 노출 주의]
  일시 DEBUG:         systemctl --user edit --runtime wikihub-mount@<vault_id>.service
                       (Service 섹션에 Environment=RCLONE_LOG_LEVEL=DEBUG 추가)
  사용 후 즉시 복원:  systemctl --user revert wikihub-mount@<vault_id>.service
                       (DEBUG 는 OAuth/SA token URL 노출 위험 — ADR-0025 R12-MED-3)

EOF
}

# ══════════════════════════════════════════════════════════════════════
# update_mode (ADR-0030) — dual-mode lifecycle 신규 함수 일괄
# ══════════════════════════════════════════════════════════════════════

# ─── lock ────────────────────────────────────────────────────────────
# R2-HIGH-4: 동시 install.sh 호출 차단. fd 200 = flock target.
# HIGH-N4 정합: bootstrap_clone_then_exec 진입 시 명시 close 후 exec.
_acquire_install_lock() {
    local lock="$WIKIHUB_HOME/install.lock"
    exec 200>"$lock"
    if ! flock -n 200; then
        err "다른 install.sh 가 진행 중 (lock: $lock)"
        err "  진단: lsof $lock  /  ps -ef | grep install.sh"
        exit 1
    fi
}

# ─── mode detect ─────────────────────────────────────────────────────
# C1 + #B: $WIKIHUB_SRC/_system/VERSION + .git AND → update mode.
_detect_mode() {
    if [[ -f "$WIKIHUB_SRC/_system/VERSION" ]] && [[ -d "$WIKIHUB_SRC/.git" ]]; then
        INSTALL_MODE="update"
        _verify_version_tag_integrity
    elif [[ -f "$WIKIHUB_SRC/_system/VERSION" ]] || [[ -d "$WIKIHUB_SRC/.git" ]]; then
        err "WIKIHUB_SRC ($WIKIHUB_SRC) 가 partial state — _system/VERSION 또는 .git 한쪽만 존재."
        err "  진단: ls -la $WIKIHUB_SRC"
        err "  복구: 의도적으로 wipe 하려면 --force-fresh, 이전 backup 복구는 수동."
        exit 1
    else
        INSTALL_MODE="fresh"
    fi
    # --force-fresh override (HIGH-N2 + H4: _confirm_force_fresh_wipe 가 _validate_wipe_target 호출)
    if [[ -n "$FORCE_FRESH" ]]; then
        INSTALL_MODE="fresh"
        _confirm_force_fresh_wipe
    fi
    export INSTALL_MODE
}

# HIGH-N2: VERSION 파일 값 vs git tag (exact-match) 비교 — warn only (dev branch 정합).
_verify_version_tag_integrity() {
    local version_str tag_exact
    IFS= read -r version_str < "$WIKIHUB_SRC/_system/VERSION" 2>/dev/null || version_str=""
    tag_exact="$(git -C "$WIKIHUB_SRC" describe --tags --exact-match HEAD 2>/dev/null || true)"
    if [[ -n "$version_str" && -n "$tag_exact" ]]; then
        if [[ "${tag_exact#v}" != "$version_str" ]]; then
            warn "_system/VERSION ($version_str) 과 git tag ($tag_exact) mismatch — VERSION 위조 의심 또는 dev branch."
            warn "  의도적이면 무시. 아니면 \`--force-fresh\` 로 재설치."
        fi
    fi
}

# ─── ref resolution (#A closure + C5 + HIGH-N3) ──────────────────────
# 우선순위: --version > BRANCH env > tag latest > local cache (semver max) > origin/main
_resolve_ref() {
    # 1. --version 명시
    if [[ -n "$EXPLICIT_VERSION" ]]; then
        # update mode 에서만 local check — fresh path 의 _step2_clone 은 git clone --branch 가 검증.
        if [[ "$INSTALL_MODE" == "update" ]]; then
            if ! git -C "$WIKIHUB_SRC" rev-parse "refs/tags/${EXPLICIT_VERSION}" >/dev/null 2>&1; then
                err "--version ${EXPLICIT_VERSION}: tag 부재."
                err "  fetch 후 tag 목록 확인: git -C $WIKIHUB_SRC tag --list"
                exit 1
            fi
        fi
        printf 'refs/tags/%s\n' "$EXPLICIT_VERSION"
        return 0
    fi
    # 2. BRANCH env / --branch 명시
    if [[ -n "$BRANCH" ]]; then
        # local branch 부재 일반적 (fresh clone shallow 또는 update remote-only) — origin/ prefix
        # 가 git reset --hard 의 remote tracking ref. _step2_clone 의 git clone --branch 는
        # `origin/` prefix 를 strip 후 호출 (이미 처리).
        case "$BRANCH" in
            origin/*) printf '%s\n' "$BRANCH" ;;
            refs/*)   printf '%s\n' "$BRANCH" ;;
            *)        printf 'origin/%s\n' "$BRANCH" ;;
        esac
        return 0
    fi
    # CR2-HIGH-2: fetch 가 실패했으면 path 3 의 local cache `latest` 는 stale 일 수 있음 — skip.
    # FETCH_FAILED env 가 set 이면 path 4 (semver local cache) 또는 path 5 (main) 로.
    if [[ -z "${FETCH_FAILED:-}" ]]; then
        # 3. tag `latest` (ADR-0010 정본)
        # CR2-HIGH-1: fresh path 에선 $WIKIHUB_SRC 부재 → local rev-parse 항상 fail → 무조건 path 5.
        # ls-remote 로 remote 의 `latest` 존재 여부 probe (네트워크 1회 추가).
        if [[ "$INSTALL_MODE" == "update" ]] \
            && git -C "$WIKIHUB_SRC" rev-parse refs/tags/latest >/dev/null 2>&1; then
            printf 'refs/tags/latest\n'
            return 0
        fi
        if [[ "$INSTALL_MODE" == "fresh" ]] \
            && git ls-remote --tags "$WIKIHUB_REPO_URL" refs/tags/latest 2>/dev/null | grep -q latest; then
            printf 'refs/tags/latest\n'
            return 0
        fi
    else
        warn "[fetch 실패 — stale 'latest' 신뢰 안 함. semver local cache 로 fallback]"
    fi
    # 4. local cache fallback — semver max tag (R2-HIGH-3 + MED-N2)
    local local_semver
    local_semver="$(git -C "$WIKIHUB_SRC" for-each-ref --sort=-v:refname --format='%(refname)' 'refs/tags/v*.*.*' 2>/dev/null | head -1 || true)"
    if [[ -n "$local_semver" ]]; then
        warn "[network offline — using local semver max tag (not 'latest'): $local_semver]"
        printf '%s\n' "$local_semver"
        return 0
    fi
    # 5. bootstrap fallback — origin/main
    warn "[no 'latest' tag — using origin/main HEAD]"
    printf 'origin/main\n'
}

# semver greater-than (a > b returns 0, else 1)
_semver_gt() {
    local a="${1#v}" b="${2#v}"
    [[ "$a" == "$b" ]] && return 1
    local sorted
    sorted="$(printf '%s\n%s\n' "$a" "$b" | sort -V | head -1)"
    [[ "$sorted" == "$b" ]]   # b 가 작으면 a > b
}

# ─── update path (#B + C3 + LOW-N3) ──────────────────────────────────
_step2_update() {
    # LOW-N3: trap 등록을 함수 진입 즉시 — VERSION read 실패 silent exit 회피
    PRE_UPDATE_REF="$(git -C "$WIKIHUB_SRC" rev-parse HEAD)"
    export PRE_UPDATE_REF
    # CR2-HIGH-3: TERM·HUP 추가 — ssh disconnect / systemd shutdown / OOM kill 시 rollback 보장
    trap '_rollback_if_failed' ERR EXIT INT TERM HUP

    info "[detected wikihub at $WIKIHUB_SRC]"
    local current_version=""
    IFS= read -r current_version < "$WIKIHUB_SRC/_system/VERSION" || current_version=""
    if [[ -z "$current_version" ]]; then
        err "_system/VERSION empty — 파일 손상 의심. \`--force-fresh\` 로 재설치 또는 수동 복구."
        exit 1
    fi
    info "  current version: v${current_version} (HEAD ${PRE_UPDATE_REF:0:7})"
    info "[update mode — Ctrl+C within 5s to abort]"
    [[ -z "${WIKIHUB_NONINTERACTIVE:-}${SKIP_CONFIRM:-}" ]] && sleep 5

    # 2a. unstaged guard (R2-HIGH-2 + index.lock 보강)
    if [[ -f "$WIKIHUB_SRC/.git/index.lock" ]]; then
        err ".git/index.lock 잔존 — 직전 git 명령이 비정상 종료된 흔적."
        err "  대처: 다른 git process 부재 확인 후 \`rm $WIKIHUB_SRC/.git/index.lock\` 후 재호출."
        exit 1
    fi
    if [[ -n "$(cd "$WIKIHUB_SRC" && git status --porcelain)" ]]; then
        err "WIKIHUB_SRC 에 unstaged 변경 있음."
        err "  대처: \`git -C ${WIKIHUB_SRC} stash\` 또는 \`--force-fresh\` 로 재설치"
        exit 1
    fi

    # 2c. systemd stop sequence (C4 + CRIT-N2)
    _systemd_stop_before_update

    # 2d. fetch + ref resolve + reset
    # F4 install.sh 의 `git clone --branch X --depth 1` 가 refspec 을 single-branch 로 제한.
    # update path 에서 다른 ref 를 fetch 하려면 refspec 을 default 로 normalize 필요 (운영
    # 첫 F4→update_mode 전환 시 critical).
    git -C "$WIKIHUB_SRC" config --replace-all remote.origin.fetch \
        '+refs/heads/*:refs/remotes/origin/*' 2>/dev/null || true
    # shallow clone 도 unshallow — arbitrary ref fetch 가능하도록 (idempotent).
    git -C "$WIKIHUB_SRC" fetch --unshallow 2>/dev/null || true

    # CR2-MED-4: stderr 분리 (2>&1 제거) + CR2-HIGH-2: FETCH_FAILED export → _resolve_ref 가 path 3 skip
    # branch_strategy_formalize (F8): canary lightweight tag force-update 수신 필수 → --force 추가 (git 2.20+ 부터 tag fetch 가 force 없이는 clobber 거부)
    if ! git -C "$WIKIHUB_SRC" fetch origin --tags --force; then
        warn "git fetch 실패 — local cache fallback 시도 (stale 'latest' 신뢰 안 함)"
        export FETCH_FAILED=1
    fi
    local target_ref
    target_ref="$(_resolve_ref)"
    info "git reset --hard ${target_ref}"
    git -C "$WIKIHUB_SRC" reset --hard "$target_ref"
    # ADR-0023 §"Clone scope" + ADR-0030 §부정/제약 (HIGH-S1 design review):
    # _apply_sparse_checkout 호출 위치는 reset --hard **이후** — working tree mutation 의
    # origin = target_ref 채택 후. pre-feature 풀-clone 운영 서버가 본 update 에서 sparse
    # 로 자동 전환 + 이후 update 는 idempotent.
    _apply_sparse_checkout
    # post-condition (R2-HIGH-5)
    if ! git -C "$WIKIHUB_SRC" diff --quiet HEAD --; then
        err "git reset --hard 후 working tree 여전히 dirty — disk full / 디스크 오류 의심"
        err "  진단: df -h $WIKIHUB_SRC; git -C $WIKIHUB_SRC status"
        exit 2   # trap 이 rollback
    fi

    # 2e. VERSION 비교 + downgrade 분기 (R2-MED-2)
    local new_version=""
    IFS= read -r new_version < "$WIKIHUB_SRC/_system/VERSION" || new_version=""
    if [[ "$current_version" == "$new_version" ]]; then
        info "already at v${new_version} — proceeding to systemd reorchestrate (idempotent)"
    elif _semver_gt "$current_version" "$new_version"; then
        if [[ -n "$EXPLICIT_VERSION_FLAG" ]]; then
            warn "intentional downgrade: v${current_version} → v${new_version} (via --version)"
        else
            err "unexpected downgrade detected: v${current_version} → v${new_version}"
            err "  의도적이면 --version v${new_version} 명시 호출"
            exit 1
        fi
    else
        ok "version transition: v${current_version} → v${new_version}"
    fi

    export INSTALL_MODE_TARGET_REF="$target_ref"
    export INSTALL_NEW_VERSION="$new_version"
    export INSTALL_OLD_VERSION="$current_version"
}

# CRIT-N1 fix: rollback 이 systemd unit 재render + start.
_rollback_if_failed() {
    local exit_code=$?
    trap - ERR EXIT INT TERM HUP
    [[ $exit_code -eq 0 ]] && return 0

    # MED-N4: SIGINT (130) — stop 중간 abort 분기
    if [[ $exit_code -eq 130 ]]; then
        err "사용자 abort (Ctrl+C) — 직전 systemd state 복구 시도"
        local current_ref
        current_ref="$(git -C "$WIKIHUB_SRC" rev-parse HEAD 2>/dev/null || echo unknown)"
        if [[ "$current_ref" == "${PRE_UPDATE_REF:-}" ]]; then
            warn "git tree 미변경. stop sequence 중간 abort 의심 — systemd 재기동 시도."
            _systemd_start_after_update 2>/dev/null \
                || warn "systemd 재기동 실패. 수동 복구: systemctl --user list-units 'wikihub-*'"
        fi
        exit 130
    fi

    [[ -z "${PRE_UPDATE_REF:-}" ]] && return 0
    local current_ref
    current_ref="$(git -C "$WIKIHUB_SRC" rev-parse HEAD 2>/dev/null || echo unknown)"
    if [[ "$current_ref" == "$PRE_UPDATE_REF" ]]; then
        err "update 실패 (exit ${exit_code}) — git reset 전 단계. systemd 재기동 시도."
        _systemd_start_after_update 2>/dev/null || warn "systemd 재기동 실패 — 수동 복구"
        exit $exit_code
    fi

    err "update 실패 (exit ${exit_code}) — 직전 ref ${PRE_UPDATE_REF:0:7} 로 자동 rollback"
    git -C "$WIKIHUB_SRC" reset --hard "$PRE_UPDATE_REF" \
        || { warn "rollback reset 실패 — 수동 복구"; exit $exit_code; }
    # ADR-0030 §부정/제약 (HIGH-S1): sparse-checkout 정책은 .git/info/sparse-checkout 에
    # 영속이라 PRE_UPDATE_REF (sparse 이전 ref) 의 install.sh 가 sparse 를 몰라도 working
    # tree 는 sparse subset 만 복원됨. governance 파일 (docs/·features/·tests/·AGENTS.md)
    # 은 rollback 후에도 미복구 — 의도. journal 로그에 명시.
    info "sparse re-apply (intended — governance 파일은 rollback 후 미복구, ADR-0030 §부정/제약)"
    _apply_sparse_checkout \
        || warn "rollback 후 sparse re-apply fail — working tree 일관성 확인 필요"
    # CRIT-N1: 직전 ref 의 template 으로 systemd unit 재render → daemon-reload → start
    _step8_systemd_render \
        || warn "rollback systemd render 실패 — 수동 (systemctl daemon-reload 직접 호출)"
    _systemd_start_after_update \
        || warn "rollback systemd 재기동 실패 — 수동 복구"
    exit $exit_code
}

# ─── systemd orchestration (C4 + R2-CRIT-2 + CRIT-N2 + MED-N7) ──────
_enabled_vaults_yaml() {
    local yaml="$WIKIHUB_HOME/wikihub.yaml"
    [[ -f "$yaml" ]] || return 0
    if [[ -x "$VENV_PATH/bin/python3" ]] \
        && [[ -f "$WIKIHUB_SRC/scripts/_helpers/render_systemd_units.py" ]]; then
        "$VENV_PATH/bin/python3" \
            "$WIKIHUB_SRC/scripts/_helpers/render_systemd_units.py" \
            --yaml "$yaml" --list-enabled 2>/dev/null
        return $?
    fi
    # MED-N1: venv 부재 시 bash fallback (best-effort yaml parse)
    warn "venv helper 미가용 — yaml bash fallback parse (기능 제한)"
    awk '
        /^vaults:/ {in_vaults=1; next}
        in_vaults && /^[^[:space:]]/ {in_vaults=0}
        in_vaults && /^[[:space:]]*-[[:space:]]*id:/ {
            gsub(/^[[:space:]]*-[[:space:]]*id:[[:space:]]*/, "")
            gsub(/[[:space:]]*#.*/, "")
            print
        }
    ' "$yaml"
}

_systemd_stop_before_update() {
    # CR2-HIGH-5: desired state (yaml.enabled) + 실제 loaded (failed/inactive 포함) union.
    # `list-units --all --no-legend` 가 inactive 까지 enumerate.
    local desired_vaults loaded_vaults all_vaults
    desired_vaults="$(_enabled_vaults_yaml)"
    loaded_vaults="$(systemctl --user list-units --all --no-legend 'wikihub-mount@*.service' 2>/dev/null \
        | awk '{print $1}' | sed 's/wikihub-mount@\(.*\)\.service/\1/' | grep -v '^$' || true)"
    all_vaults="$(printf '%s\n%s\n' "$desired_vaults" "$loaded_vaults" | sort -u | grep -v '^$' || true)"
    # timer 정지 — 새 fire 차단
    for v in $all_vaults; do
        systemctl --user stop "wikihub-vault@${v}.timer" 2>/dev/null || true
    done
    systemctl --user stop wikihub-lint.timer 2>/dev/null || true
    systemctl --user stop wikihub-pending-monitor.timer 2>/dev/null || true
    systemctl --user stop wikihub-pending-monitor.service 2>/dev/null || true
    # vault@.service mid-sync 대기 — 15min grace (TimeoutStartSec=15min 정합)
    # MED-N4: progress info — 운영자 visual 안심
    for v in $all_vaults; do
        info "  stopping vault@${v} (max 15min grace for mid-sync)"
        timeout 900 systemctl --user stop "wikihub-vault@${v}.service" 2>/dev/null \
            || warn "vault@${v} stop timeout — 강제 abort"
    done
    systemctl --user stop wikihub-lint.service 2>/dev/null || true
    # mount@ 마지막
    for v in $all_vaults; do
        systemctl --user stop "wikihub-mount@${v}.service" 2>/dev/null || true
    done
    # R2-CRIT-2: StartLimitBurst 카운터 초기화
    systemctl --user reset-failed 'wikihub-mount@*.service' \
        'wikihub-vault@*.service' 'wikihub-vault@*.timer' \
        'wikihub-lint.service' 'wikihub-lint.timer' \
        'wikihub-pending-monitor.service' 'wikihub-pending-monitor.timer' 2>/dev/null || true
    # CRIT-N2: stop 직후 daemon-reload — Step 8 render 이전 race window 차단.
    systemctl --user daemon-reload 2>/dev/null || true
    ok "systemd stop sequence 완료"
}

_systemd_start_after_update() {
    if [[ -n "${SKIP_SYSTEMD_RENDER:-}" ]]; then
        info "SKIP_SYSTEMD_RENDER 세팅됨 (Hermes 부재) — systemd start skip"
        return 0
    fi
    local desired_vaults
    desired_vaults="$(_enabled_vaults_yaml)"
    if [[ -z "$desired_vaults" ]]; then
        warn "enabled vault 없음 — systemd start skip"
        return 0
    fi
    # mount 선행
    for v in $desired_vaults; do
        info "  starting mount@${v}"
        systemctl --user start "wikihub-mount@${v}.service" 2>/dev/null \
            || { err "mount@${v} start 실패"; return 2; }
    done
    # FUSE-ready stat wait (MED-N1·N5: helper 단일화)
    for v in $desired_vaults; do
        _wait_mount_ready "$v" 120 || { err "mount@${v} not ready in 120s"; return 2; }
    done
    for v in $desired_vaults; do
        systemctl --user start "wikihub-vault@${v}.timer" 2>/dev/null \
            || warn "vault@${v}.timer start 실패"
    done
    systemctl --user start wikihub-lint.timer 2>/dev/null || warn "lint.timer start 실패"
    # ADR-0037 §D2 (v0.1.5) — pending_ingest age monitor
    systemctl --user start wikihub-pending-monitor.timer 2>/dev/null || warn "pending-monitor.timer start 실패"
    ok "systemd start sequence 완료"
}

_wait_mount_ready() {
    local v="$1" timeout="$2" elapsed=0 mount_path
    mount_path="$("$VENV_PATH/bin/python3" \
        "$WIKIHUB_SRC/scripts/_helpers/render_systemd_units.py" \
        --yaml "$WIKIHUB_HOME/wikihub.yaml" \
        --get-mount-path "$v" 2>/dev/null || true)"
    [[ -z "$mount_path" ]] && return 1
    mount_path="${mount_path/#\~/$HOME}"
    while (( elapsed < timeout )); do
        if systemctl --user is-active "wikihub-mount@${v}.service" >/dev/null 2>&1 \
           && timeout 5 stat "$mount_path" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2; elapsed=$((elapsed + 2))
    done
    return 1
}

# ─── Step 8 — install.sh 가 systemd render 직접 (C2 + #D) ────────────
_step8_systemd_render() {
    if [[ -n "${SKIP_SYSTEMD_RENDER:-}" ]]; then
        info "SKIP_SYSTEMD_RENDER 세팅됨 (Hermes 부재) — systemd render skip"
        return 0
    fi
    local yaml="$WIKIHUB_HOME/wikihub.yaml"
    if [[ ! -f "$yaml" ]]; then
        warn "wikihub.yaml 부재 — systemd render skip (yaml 편집 후 install.sh 재호출)"
        return 0
    fi
    info "systemd unit render → ~/.config/systemd/user/"
    mkdir -p "$HOME/.config/systemd/user"
    "$VENV_PATH/bin/python3" \
        "$WIKIHUB_SRC/scripts/_helpers/render_systemd_units.py" \
        --yaml "$yaml" \
        --render --out "$HOME/.config/systemd/user/" \
        || { err "render_systemd_units.py 실패"; return 2; }
    systemctl --user daemon-reload
    # ADR-0030 §Note (v0.1.4, 2026-05-20) — daemon-reload 는 active unit 의 "active since" 미갱신.
    # fresh / --force-fresh 경로에서 이미 enable+start 상태인 timer 의 새 template (OnActiveSec 등)
    # 이 무력화되는 결함 closure. `try-restart` 는 inactive unit 에 no-op — update path 의
    # stop/start 순서와 충돌 없음.
    systemctl --user try-restart 'wikihub-mount@*.service' \
        'wikihub-vault@*.timer' wikihub-lint.timer wikihub-pending-monitor.timer 2>/dev/null || true
    ok "Step 8 systemd render + daemon-reload + try-restart 완료"
}

# best-effort hermes /wh-setup — F5 정합 (chat --skills --quiet --query) + update path 만
_step8_wh_setup_skill_meta() {
    if [[ -n "${SKIP_SYSTEMD_RENDER:-}" ]]; then
        info "SKIP_SYSTEMD_RENDER 세팅됨 — /wh-setup skill 메타 갱신 skip"
        return 0
    fi
    [[ "$INSTALL_MODE" != "update" ]] && return 0
    local yaml="$WIKIHUB_HOME/wikihub.yaml"
    [[ -f "$yaml" ]] || return 0
    local agent_binary timeout_sec
    agent_binary="$("$VENV_PATH/bin/python3" -c \
        "import yaml,sys; print(yaml.safe_load(open(sys.argv[1])).get('agent',{}).get('binary',''))" \
        "$yaml" 2>/dev/null || true)"
    timeout_sec="$("$VENV_PATH/bin/python3" -c \
        "import yaml,sys; print(yaml.safe_load(open(sys.argv[1])).get('agent',{}).get('timeout_sec',600))" \
        "$yaml" 2>/dev/null || echo 600)"
    if [[ -z "$agent_binary" || ! -x "$agent_binary" ]]; then
        info "agent.binary ($agent_binary) 미설치 — /wh-setup skill 메타 갱신 skip"
        return 0
    fi
    info "agent skill 메타 갱신 (best-effort) — $agent_binary chat --skills wh-setup --quiet --yolo --query \"/wh-setup\" (timeout=${timeout_sec}s)"
    WIKIHUB_NONINTERACTIVE=1 timeout "$timeout_sec" "$agent_binary" \
        chat --skills wh-setup --quiet --yolo --query "/wh-setup" \
        || warn "/wh-setup 호출 실패 — Hermes skill 미인식 또는 LLM transient (systemd render 는 install.sh 가 이미 수행)"
}

# ─── Step 10 — verify ───────────────────────────────────────────────
_step10_verify() {
    local linger_state
    linger_state="$(loginctl show-user --property=Linger --value "$USER" 2>/dev/null || echo no)"
    if [[ "$linger_state" != "yes" ]]; then
        warn "linger 미활성 — systemd --user 가 ssh 종료 후 stop. verify skip."
        return 0
    fi
    local desired_vaults
    desired_vaults="$(_enabled_vaults_yaml)"
    [[ -z "$desired_vaults" ]] && { ok "enabled vault 없음 — verify skip"; return 0; }
    # CR2-HIGH-4: verify 실패는 warn-only — git rollback 분리.
    # 이유: verify 가 mount@ is-active 만 검사 → transient slow-start 도 fail 처리됐었음.
    # rollback 가 새 vault@ 가 이미 state 손댄 상태에서 fire 하면 invariant #1 위배 (state divergence).
    # 본 분기는 alert 만 — 운영자가 journalctl 로 진단 + 필요 시 수동 --version <prev> rollback.
    local verify_failed=0
    for v in $desired_vaults; do
        local unit="wikihub-mount@${v}.service"
        if ! systemctl --user is-active "$unit" >/dev/null 2>&1; then
            warn "$unit not active — 진단 필요 (transient slow-start 가능성)"
            warn "  journalctl --user -u $unit -n 50"
            warn "  필요 시 수동 rollback: install.sh --version <prev-tag>"
            verify_failed=1
        fi
    done
    if (( verify_failed )); then
        warn "Step 10 verify: 일부 mount@ inactive — install.sh 는 정상 종료 (git rollback 안 함)"
    else
        ok "Step 10 systemd verify ok"
    fi
    return 0   # 항상 success — auto rollback 회피
}

# ─── Step 11 — banner ────────────────────────────────────────────────
_step11_banner() {
    local mode_label="${INSTALL_MODE:-unknown}"
    local ref_label="${INSTALL_MODE_TARGET_REF:-N/A}"
    echo ""
    echo "=== wikihub install complete ==="
    echo "  mode: ${mode_label}"
    if [[ "$mode_label" == "update" ]]; then
        echo "  transition: v${INSTALL_OLD_VERSION:-?} → v${INSTALL_NEW_VERSION:-?}"
        echo "  ref:  ${ref_label}"
        # ADR-0031 (HIGH-S3): update path 에서도 yaml 부재 시 warn — update 도중 instance dir
        # wipe 또는 신규 vault 추가 시나리오 mitigation. _step8_guide 는 fresh 만 호출되므로
        # update path 전용 안내가 별도 필요.
        if [[ ! -f "$WIKIHUB_HOME/wikihub.yaml" ]]; then
            echo "  ${C_WARN}⚠ wikihub.yaml 부재 — /wh:setup 호출 전에는 systemd timer enable 금지 (ADR-0031).${C_RST}"
        fi
    fi
    echo "  status: systemctl --user list-timers wikihub-*"
    echo "================================="
}

# ══════════════════════════════════════════════════════════════════════
# main flow (v3 ADR-0030 — dual-mode)
# ══════════════════════════════════════════════════════════════════════

main() {
    _acquire_install_lock        # H7: 동시 호출 차단

    # Step 0: bootstrap dispatch
    if _pipe_mode_detect; then
        # detect 가 bootstrap 보다 먼저 — mode 별 분기.
        _detect_mode
        bootstrap_clone_then_exec "$@"
        # exec 호출 — 새 process 가 _detect_mode 재호출.
    fi

    # 직접 실행 경로 (또는 bootstrap exec 후의 새 process)
    _detect_mode

    _step1_env_check

    if [[ "$INSTALL_MODE" == "update" ]]; then
        _step2_update            # trap rollback 등록
    else
        _step2_clone             # _validate_wipe_target 내부 호출
    fi

    _step3_venv
    # ADR-0035: _step4_gws 폐기 (gws CLI 단독 폐기)
    _step45_rclone
    _step5_instance_dirs    # ADR-0031: yaml 미관여 (이름 변경 + cp 삭제)
    _step6_agent_skill

    [[ "$INSTALL_MODE" == "fresh" ]] && _step7_linger

    _step8_systemd_render        # install.sh 가 직접 render (C2)
    _step8_wh_setup_skill_meta   # best-effort (F5 미완 fallback)

    if [[ "$INSTALL_MODE" == "update" ]]; then
        _systemd_start_after_update
        _step10_verify
        trap - ERR EXIT INT TERM HUP      # rollback trap 해제 (성공 종료)
    fi

    # CR1-MED-3: fresh mode 에서만 운영자 안내 (update 는 banner 만 충분)
    [[ "$INSTALL_MODE" == "fresh" ]] && _step8_guide
    _step11_banner
}

# main guard — `source install.sh` 또는 `. install.sh` 시 main path 가 자동 실행되어
# Step 2 의 `rm -rf $WIKIHUB_SRC` 가 의도치 않게 trigger 되는 결함 차단
# (V<N> Phase 2 결함 #10, 2026-05-17 incident).
#
# 표준 실행 패턴은 직접 실행 (`bash install.sh`) 또는 curl-pipe (`curl ... | bash`).
# 둘 다 BASH_SOURCE[0] == ${0} 정합 (curl-pipe 시 BASH_SOURCE 가 빈 문자열인 경우도
# 같음 — 직접 process). source 패턴은 ${0} 가 호출 shell 의 이름 (bash, zsh) 이라
# 정확히 mismatch → main 실행 안 함.
if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]] || [[ -z "${BASH_SOURCE[0]:-}" ]]; then
    main "$@"
fi
