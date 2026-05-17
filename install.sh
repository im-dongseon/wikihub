#!/usr/bin/env bash
# WikiHub install.sh — curl-pipe + clean install pattern (ADR-0023).
#
# 운영자 한 줄 명령:
#   curl -fsSL --proto '=https' --tlsv1.2 \
#     https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh | bash
#
# 또는 로컬 호출 (개발/사전 inspection 후):
#   ./install.sh [--gws-version <ver>] [--skip-confirm] [--branch <ref>]
#
# Spec: features/20260514_install_runtime/analysis_and_design.md §4.1 (v5 정본).
set -euo pipefail

# ─── 색상 (TTY 일 때만) ────────────────────────────────────────────────
if [ -t 1 ]; then
    C_INFO=$'\033[1;34m'; C_OK=$'\033[1;32m'; C_WARN=$'\033[1;33m'; C_ERR=$'\033[1;31m'; C_RST=$'\033[0m'
else
    C_INFO=''; C_OK=''; C_WARN=''; C_ERR=''; C_RST=''
fi
# R10 NIT-1: timestamp prefix — gws 다운로드 등 분 단위 step 의 hang vs 정상 구분
_ts() { date +%H:%M:%S; }
info()  { echo "${C_INFO}INFO${C_RST}  [$(_ts)] $*"; }
ok()    { echo "${C_OK}OK${C_RST}    [$(_ts)] $*"; }
warn()  { echo "${C_WARN}WARN${C_RST}  [$(_ts)] $*" >&2; }
err()   { echo "${C_ERR}ERROR${C_RST} [$(_ts)] $*" >&2; }

# ─── 기본값 + env override ─────────────────────────────────────────────
export WIKIHUB_HOME="${WIKIHUB_HOME:-$HOME/wikihub}"
export WIKIHUB_INSTANCE_ROOT="${WIKIHUB_INSTANCE_ROOT:-$HOME/wikihub-instance}"
WIKIHUB_REPO_URL="${WIKIHUB_REPO_URL:-https://github.com/im-dongseon/wikihub.git}"
BRANCH="${BRANCH:-latest}"
GWS_VERSION="${GWS_VERSION:-0.22.5}"   # V8 통과 시점 pinned (ADR-0015 Accepted). `latest` env override 시 GitHub API 호출 분기 유지
SKIP_CONFIRM="${SKIP_CONFIRM:-${WIKIHUB_NONINTERACTIVE:-}}"
VENV_PATH="${VENV_PATH:-$HOME/.local/share/wikihub/venv}"
GWS_BIN_DIR="${GWS_BIN_DIR:-$HOME/.local/bin}"
ALLOW_NON_UBUNTU="${ALLOW_NON_UBUNTU:-}"      # R10 MED-4: 메인테이너 macOS dev box 실수 호출 차단
# ADR-0028: uv 기반 Python runtime 관리
UV_VERSION="${UV_VERSION:-0.11.14}"           # uv binary pinned (GitHub Releases + SHA256, gws·rclone 패턴 일관)
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
WIKIHUB_INSTANCE_ROOT="$(_abs_path "$WIKIHUB_INSTANCE_ROOT")"

# R10 HIGH-7: install.sh stdout/stderr 의 log mirror — curl-pipe 모드 fail 시 사후 분석.
INSTALL_LOG="${WIKIHUB_INSTANCE_ROOT}/install.log"
mkdir -p "$WIKIHUB_INSTANCE_ROOT"
# tee 로 log file 도 동시 write — 단 fd 1·2 모두 (stdout/stderr 둘 다 로깅).
exec > >(tee -a "$INSTALL_LOG") 2>&1
echo "─── install.sh start: $(date -u +%Y-%m-%dT%H:%M:%SZ) ───"

# R9 HIGH-2 fix: CLI 파싱 전 원본 args 보존 — bootstrap_clone_then_exec 가 self-replace 시 전달
ORIGINAL_ARGS=("$@")

# ─── CLI 파싱 ─────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --gws-version) GWS_VERSION="$2"; shift 2 ;;
        --skip-confirm) SKIP_CONFIRM=1; shift ;;
        --branch) BRANCH="$2"; shift 2 ;;
        --allow-non-ubuntu) ALLOW_NON_UBUNTU=1; shift ;;
        -h|--help)
            sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
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
    info "curl-pipe mode 감지 → repo 부트스트랩 진행"
    _step2_clone   # Step 2 함수 정의는 아래
    if [ ! -f "$WIKIHUB_HOME/install.sh" ]; then
        err "clone 후 $WIKIHUB_HOME/install.sh 가 없음 — repo 구조 결함 의심"
        exit 2
    fi
    info "→ $WIKIHUB_HOME/install.sh 로 self-replace (args: ${ORIGINAL_ARGS[*]:-(none)})"
    # R9 HIGH-2 fix: ORIGINAL_ARGS 보존 — CLI 파싱 후 $@ 가 비어 있어도 운영자 원본 args 전달
    exec bash "$WIKIHUB_HOME/install.sh" "${ORIGINAL_ARGS[@]}"
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
    # Step 2 의 clone 을 먼저 수행 → 새 install.sh 로 self-replace.
    # bootstrap_clone_then_exec 가 exec 호출 — 본 함수 이후 코드는 새 process 에서 실행.
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
# Step 2. wikihub repo clean install (ADR-0023 — clean wipe + clone)
# ──────────────────────────────────────────────────────────────────────

_step2_clone() {
    # safety guard 1: 시스템 path 차단
    case "$WIKIHUB_HOME" in
        ""|"/"|"/usr"|"/usr/local"|"/etc"|"/opt"|"/home"|"$HOME"|"$HOME/")
            err "WIKIHUB_HOME=$WIKIHUB_HOME 는 wipe 대상으로 안전하지 않음"
            err "       WIKIHUB_HOME env 로 다른 위치 지정 (default: ~/wikihub)"
            exit 1
            ;;
    esac

    # 기존 디렉토리 검증 후 wipe
    if [ -e "$WIKIHUB_HOME" ]; then
        if [ ! -d "$WIKIHUB_HOME/.git" ]; then
            err "$WIKIHUB_HOME 가 존재하지만 git repo 가 아님."
            err "       wikihub 설치 위치가 아닐 가능성 — 수동 확인 후 재시도."
            exit 1
        fi
        # safety guard 2: origin remote 검증
        local existing_origin
        existing_origin="$(cd "$WIKIHUB_HOME" && git config --get remote.origin.url 2>/dev/null || true)"
        case "$existing_origin" in
            *im-dongseon/wikihub*|*wikihub.git*)
                info "기존 wikihub repo 발견 → clean re-install 진행"
                ;;
            *)
                err "$WIKIHUB_HOME 의 origin=$existing_origin — wikihub repo 가 아님."
                err "       dev box 작업 디렉토리를 잘못 지정했을 가능성. WIKIHUB_HOME 재확인."
                exit 1
                ;;
        esac
        # safety guard 3: cwd 가 WIKIHUB_HOME 안이면 밖으로 이동
        case "$(pwd)" in
            "$WIKIHUB_HOME"|"$WIKIHUB_HOME"/*) cd "$HOME" ;;
        esac
        rm -rf "$WIKIHUB_HOME"
    fi

    info "git clone --branch $BRANCH --depth 1 $WIKIHUB_REPO_URL → $WIKIHUB_HOME"
    git clone --branch "$BRANCH" --depth 1 "$WIKIHUB_REPO_URL" "$WIKIHUB_HOME"
    ok "Step 2 repo clone 완료"
}

# ──────────────────────────────────────────────────────────────────────
# Step 3. venv 생성 (idempotent, ADR-0028 — uv 기반 Python runtime)
# ──────────────────────────────────────────────────────────────────────

# uv binary install — GitHub Releases binary + SHA256 verify (gws·rclone 패턴 일관, ADR-0028)
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
    mkdir -p "$GWS_BIN_DIR"
    install -m 0755 "$uv_bin" "$GWS_BIN_DIR/uv"
    rm -rf "$tmpdir"
    trap - RETURN
    # PATH — 현 셸 + .profile 양쪽 (V8 결함 #4b 회귀 방지: self-replace 후에도 즉시 가용)
    if ! echo "$PATH" | tr ':' '\n' | grep -qx "$GWS_BIN_DIR"; then
        if ! grep -q "$GWS_BIN_DIR" "$HOME/.profile" 2>/dev/null; then
            echo "export PATH=\"$GWS_BIN_DIR:\$PATH\"" >> "$HOME/.profile"
            info "$HOME/.profile 에 PATH 추가 — 새 shell 부터 적용"
        fi
        export PATH="$GWS_BIN_DIR:$PATH"
    fi
    ok "uv $UV_VERSION 설치 완료 ($GWS_BIN_DIR/uv)"
}

_step3_venv() {
    _install_uv

    info "Python $PYTHON_VERSION install (uv 자체 관리, apt 의존 없음)"
    uv python install "$PYTHON_VERSION"

    # venv 검증 — 정상 venv (bin/python + 버전 일치) = skip, 무효/부분 생성 = wipe + 재생성
    # (V8 결함 #2·#6 fix — `uv venv` 자체는 기존 venv 존재 시 error, 검증 분기 + 명시적 wipe 필요)
    mkdir -p "$(dirname "$VENV_PATH")"
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
    fi

    # R10 MED-7: scripts/requirements.txt (운영 deps) 가 정본 — repo root requirements.txt 미존재.
    local req_file="$WIKIHUB_HOME/scripts/requirements.txt"
    if [ -f "$req_file" ]; then
        info "deps 설치/갱신: scripts/requirements.txt (uv pip)"
        # R16-M7 (V<N> R16 SRE 리뷰): `--quiet` 제거 — supply chain visibility 보존.
        # install.log 에 의존성 install trace (패키지 + 버전) 가 남아 추후 incident 시 forensic.
        uv pip install --python "$VENV_PATH/bin/python" -r "$req_file"
    else
        warn "scripts/requirements.txt 없음 — venv 생성만 (의존성 미설치)"
    fi

    # 사이드카 — /wh:setup 의 substitution 시 read
    echo "$VENV_PATH" > "$WIKIHUB_HOME/.venv_path"
    ok "Step 3 venv ($PYTHON_VERSION) + .venv_path 기록 완료"
}

# ──────────────────────────────────────────────────────────────────────
# Step 4. gws 설치 (ADR-0015 — GitHub Releases binary + shasum)
# ──────────────────────────────────────────────────────────────────────

_step4_gws() {
    # 버전 결정
    if [ "$GWS_VERSION" = "latest" ]; then
        info "GitHub Releases 의 latest tag 조회"
        # R9 CRIT-1 fix: set -euo pipefail + 파이프 체인 — grep 미발견 / API rate limit 시 pipefail
        # 로 스크립트 즉시 종료 방지. 빈 결과는 아래 check 에서 명시적 안내.
        GWS_VERSION="$(curl -fsSL --proto '=https' --tlsv1.2 \
            https://api.github.com/repos/googleworkspace/cli/releases/latest \
            | grep '"tag_name"' | head -1 | sed -E 's/.*"v?([^"]+)".*/\1/' || true)"
        if [ -z "$GWS_VERSION" ]; then
            err "gws latest 버전 조회 실패 (API rate limit / 네트워크 결함 의심) — --gws-version <ver> 명시 후 재시도"
            exit 2
        fi
    fi
    info "gws version: $GWS_VERSION"

    # 이미 설치된 버전이면 skip
    if command -v gws >/dev/null 2>&1 && gws --version 2>/dev/null | grep -q "$GWS_VERSION"; then
        ok "gws $GWS_VERSION 기존 설치 사용"
        return 0
    fi

    # 다운로드 + verify + 배치
    # V8 hand-check (2026-05-17) lock — Rust target triple 명명 (ADR-0015 Accepted)
    local triple asset url tmpdir
    case "$(uname -m)" in
        aarch64|arm64) triple="aarch64-unknown-linux-gnu" ;;
        x86_64|amd64)  triple="x86_64-unknown-linux-gnu" ;;
        *) err "지원하지 않는 arch: $(uname -m)"; exit 2 ;;
    esac
    asset="google-workspace-cli-${triple}.tar.gz"
    url="https://github.com/googleworkspace/cli/releases/download/v${GWS_VERSION}/${asset}"

    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' EXIT
    info "gws binary 다운로드: $url"
    if ! curl -fsSL --proto '=https' --tlsv1.2 "$url" -o "$tmpdir/$asset"; then
        err "gws binary 다운로드 실패: $url"
        exit 2
    fi
    # sha256 검증 — R10 MED-2: sha256sum (coreutils 표준) 사용. Ubuntu minimal image 의 perl
    # 미포함 시 shasum 부재 위험 회피.
    # R16-M2 (V<N> R16 SRE 리뷰): TLS-only fallback 제거 — sidecar 부재 시 fatal exit.
    # googleworkspace/cli 의 v0.22.5 release 가 SHA256 sidecar 제공 (ADR-0015 정합).
    if ! curl -fsSL --proto '=https' --tlsv1.2 "${url}.sha256" -o "$tmpdir/${asset}.sha256" 2>/dev/null; then
        err "gws sha256 sidecar 부재 — ADR-0015 spec 위반. release 형식 변경 의심: ${url}.sha256"
        exit 2
    fi
    ( cd "$tmpdir" && sha256sum -c "${asset}.sha256" )
    tar -C "$tmpdir" -xzf "$tmpdir/$asset"
    mkdir -p "$GWS_BIN_DIR"
    # R9 MED-3: tar 구조 가설(`gws` 가 최상위 binary) 어긋날 시 진단 정보 출력 후 fatal
    if [ ! -f "$tmpdir/gws" ]; then
        err "gws binary 가 tar 최상위에 없음 — V8 hand-check 필요 (asset 구조 가설 실패)"
        err "tar 내용물:"
        find "$tmpdir" -maxdepth 3 -not -name "$asset" -not -name "${asset}.sha256" -printf '  %P\n' 2>/dev/null \
            || ls -laR "$tmpdir" >&2
        exit 2
    fi
    install -m 0755 "$tmpdir/gws" "$GWS_BIN_DIR/gws"
    rm -rf "$tmpdir"
    trap - EXIT

    # PATH 확인
    if ! echo "$PATH" | tr ':' '\n' | grep -qx "$GWS_BIN_DIR"; then
        if ! grep -q "$GWS_BIN_DIR" "$HOME/.profile" 2>/dev/null; then
            echo "export PATH=\"$GWS_BIN_DIR:\$PATH\"" >> "$HOME/.profile"
            info "$HOME/.profile 에 PATH 추가 — 새 shell 부터 적용"
        fi
    fi

    ok "Step 4 gws $GWS_VERSION 설치 완료 ($GWS_BIN_DIR/gws)"
}

# ──────────────────────────────────────────────────────────────────────
# Step 4.5. rclone 설치 + chmod 0600 + rc port pre-check (v9, ADR-0025·0026·0027)
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

_enforce_rclone_conf_perms() {
    local conf="${RCLONE_CONFIG:-${HOME}/.config/rclone/rclone.conf}"
    if [[ -f "$conf" ]]; then
        chmod 0600 "$conf"
        info "rclone.conf 권한 0600 enforce: $conf"
    else
        warn "rclone.conf 미존재 — /wh:setup Step 5.5 (rclone OAuth) 안내 대상"
    fi
}

_step45_rclone() {
    _install_rclone
    _enforce_rclone_conf_perms
    # rc port pre-check — yaml 이 이미 Step 5 에서 복사된 상태 가정. 첫 실행 (yaml 미복사) 시 skip.
    if [[ -f "$WIKIHUB_INSTANCE_ROOT/wikihub.yaml" ]]; then
        local ports
        ports="$(_yaml_get_vault_rc_ports "$WIKIHUB_INSTANCE_ROOT/wikihub.yaml" 2>/dev/null || true)"
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
# Step 5. wikihub.yaml.example → wikihub.yaml (없을 때만)
# ──────────────────────────────────────────────────────────────────────

_step5_yaml() {
    mkdir -p "$WIKIHUB_INSTANCE_ROOT"
    mkdir -p "$WIKIHUB_INSTANCE_ROOT/.credentials"
    chmod 700 "$WIKIHUB_INSTANCE_ROOT/.credentials"

    local target="$WIKIHUB_INSTANCE_ROOT/wikihub.yaml"
    if [ -f "$target" ]; then
        ok "Step 5 wikihub.yaml 기존 보존: $target"
    else
        cp "$WIKIHUB_HOME/wikihub.yaml.example" "$target"
        ok "Step 5 wikihub.yaml.example → $target (메인테이너 편집 대상)"
    fi

    # R10 HIGH-5 fix: credentials 파일 chmod 600 enforce — 이미 배치된 파일 검증.
    # install.sh 가 credentials 자체를 만들지 않지만, 메인테이너 scp 후 권한 미설정 케이스 회피.
    local cred_count=0
    local bad_perm_count=0
    for cred in "$WIKIHUB_INSTANCE_ROOT/.credentials"/*.json; do
        [ -f "$cred" ] || continue
        cred_count=$((cred_count + 1))
        local mode
        mode=$(stat -c '%a' "$cred" 2>/dev/null || stat -f '%Lp' "$cred" 2>/dev/null)
        if [ "$mode" != "600" ]; then
            warn "credentials 권한 위반: $cred (mode=$mode, 요구=600) — chmod 600 적용"
            chmod 600 "$cred"
            bad_perm_count=$((bad_perm_count + 1))
        fi
    done
    if [ "$cred_count" -gt 0 ]; then
        ok "Step 5 credentials 검증 ($cred_count 건, $bad_perm_count 건 권한 fix)"
    fi
}

# ──────────────────────────────────────────────────────────────────────
# Step 6. agent skill 초기 등록
# ──────────────────────────────────────────────────────────────────────

_step6_agent_skill() {
    # v0.1.0 minimal — Hermes / codex / gemini 별 메커니즘은 ADR-0012 + F5 에서 정본화.
    # 본 Step 은 placeholder — 추후 agent 별 register helper 추가.
    info "agent skill 초기 등록 — v0.1.0 stub (F5 에서 정본화)"
    ok "Step 6 agent skill 메타 (placeholder)"
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
  $WIKIHUB_HOME/                          # repo (install.sh 가 git clone --branch $BRANCH)
  $VENV_PATH/                             # Python venv (install.sh 관리, 메인테이너 미관여)
  $GWS_BIN_DIR/gws                        # gws binary (install.sh 관리)
  $WIKIHUB_INSTANCE_ROOT/                 # 운영 state (instance.root) — 메인테이너 편집 대상
      ├── wikihub.yaml                    # 운영 정본 (편집 필수)
      ├── .credentials/                   # OAuth tokens (scp 배치 + chmod 600)
      ├── _state/<vault_id>/              # cursor·file_map·retry·last_sync (자동)
      ├── vault-<vault_id>/               # vault local mirror (자동)
      └── wiki/                           # 통합 wiki (자동)
  ~/.config/systemd/user/                 # systemd unit (/wh:setup 관리)

다음 단계:
  1. $WIKIHUB_INSTANCE_ROOT/wikihub.yaml 편집 — vault 정의 + 옵션 채우기
  2. credentials 배치 — dev box (macOS) 에서 scripts/auth_gdrive.py 실행 후 scp:
       scp ~/wikihub-credentials/token_gdrive.json user@$(hostname):$WIKIHUB_INSTANCE_ROOT/.credentials/
       ssh user@$(hostname) 'chmod 600 $WIKIHUB_INSTANCE_ROOT/.credentials/token_*.json'
  3. /wh:setup 호출 — wikihub.yaml 검증 + systemd unit + 첫 ingest prompt
       <agent_invocation> "/wh:setup --enable"

업데이트는 같은 명령 한 번 더:
  curl -fsSL https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh | bash

[update 동작 — clean install pattern (ADR-0023)]
  매 install 호출은 $WIKIHUB_HOME 디렉토리를 wipe 후 latest tag 로 다시 clone.
  $WIKIHUB_INSTANCE_ROOT (운영 state) · $VENV_PATH (venv) · systemd unit 은 영향 없음.
  $WIKIHUB_HOME 안의 메인테이너 수동 편집은 손실됨 — repo 는 read-only 정책.

[운영 진단 명령 — R10 HIGH-2 + R16-M6·L3]
  vault sync 로그:    journalctl --user -t wikihub-vault-<vault_id> --since '24h ago'
  lint 로그:          journalctl --user -t wikihub-lint --since '24h ago'
  fatal alert 로그:   journalctl --user -t wikihub-ops-alert --since '24h ago'
                       (alert 발송 실패는 "webhook 발송 실패" warn 로 기록)
  mount 로그:         journalctl --user -t wikihub-mount-<vault_id> --since '24h ago'
  timer 상태:         systemctl --user list-timers '*wikihub*' 'lint*' '*-ingest*'
  install 로그:       cat $WIKIHUB_INSTANCE_ROOT/install.log
  last_failure 요약:  for s in \$WIKIHUB_INSTANCE_ROOT/_state/*/last_failure.json; do
                        [ -f "\$s" ] && echo "─ \$s" && cat "\$s"; done
                       (scope=vault: sync layer, scope=mount: rclone OAuth/SA — V<N> 결함 #7)

[rclone 디버그 (R16-L3) — token 노출 주의]
  일시 DEBUG:         systemctl --user edit --runtime wikihub-mount@<vault_id>.service
                       (Service 섹션에 Environment=RCLONE_LOG_LEVEL=DEBUG 추가)
  사용 후 즉시 복원:  systemctl --user revert wikihub-mount@<vault_id>.service
                       (DEBUG 는 OAuth/SA token URL 노출 위험 — ADR-0025 R12-MED-3)

EOF
}

# ──────────────────────────────────────────────────────────────────────
# main flow
# ──────────────────────────────────────────────────────────────────────

main() {
    # Step 0 의 bootstrap — pipe mode 면 clone 후 exec, 아니면 그대로 진행
    if _pipe_mode_detect; then
        bootstrap_clone_then_exec "$@"
        # exec 가 호출돼서 여기 도달 안 함
    fi

    _step1_env_check
    _step2_clone
    _step3_venv
    _step4_gws
    _step45_rclone          # v9 (ADR-0025·0026·0027) — rclone install + chmod 0600 + rc port pre-check
    _step5_yaml
    _step6_agent_skill
    _step7_linger
    _step8_guide
}

# main guard — `source install.sh` 또는 `. install.sh` 시 main path 가 자동 실행되어
# Step 2 의 `rm -rf $WIKIHUB_HOME` 가 의도치 않게 trigger 되는 결함 차단
# (V<N> Phase 2 결함 #10, 2026-05-17 incident).
#
# 표준 실행 패턴은 직접 실행 (`bash install.sh`) 또는 curl-pipe (`curl ... | bash`).
# 둘 다 BASH_SOURCE[0] == ${0} 정합 (curl-pipe 시 BASH_SOURCE 가 빈 문자열인 경우도
# 같음 — 직접 process). source 패턴은 ${0} 가 호출 shell 의 이름 (bash, zsh) 이라
# 정확히 mismatch → main 실행 안 함.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]] || [[ -z "${BASH_SOURCE[0]:-}" ]]; then
    main "$@"
fi
