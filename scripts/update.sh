#!/usr/bin/env bash
# scripts/update.sh — thin wrapper for install.sh update mode (Issue #152)
#
# Usage: scripts/update.sh [--version <tag>] [--branch <ref>]
#                         [--skip-drift-check] [--non-interactive] [--dry-run]
#
#   --version <tag>       Pin to specific tag (rollback/promotion). Passed to install.sh.
#   --branch <ref>        Override latest resolution (e.g. canary). Passed to install.sh.
#   --skip-drift-check    Skip config drift detection (faster, no warnings).
#   --non-interactive     Suppress install.sh 5s confirm (sets WIKIHUB_NONINTERACTIVE=1).
#   --dry-run             Print plan + drift report, exit 0 without exec'ing install.sh.
#
# Design: thin wrapper — delegates git fetch/reset, systemd stop/start, rollback to
# install.sh. All hard guarantees (lock, trap rollback, systemd stop sequence, verify)
# come from install.sh untouched.

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
DRY_RUN=false
SKIP_DRIFT_CHECK=false
NON_INTERACTIVE=false
EXPLICIT_VERSION=""
BRANCH=""

# ─── Color (TTY only) ─────────────────────────────────────────────────
if [ -t 1 ]; then
    C_INFO=$'\033[1;34m'; C_OK=$'\033[1;32m'; C_WARN=$'\033[1;33m'; C_ERR=$'\033[1;31m'; C_RST=$'\033[0m'
else
    C_INFO=''; C_OK=''; C_WARN=''; C_ERR=''; C_RST=''
fi

_ts() { date +%H:%M:%S; }
info()  { echo "${C_INFO}INFO${C_RST}  [$(_ts)] $*"; }
ok()    { echo "${C_OK}OK${C_RST}    [$(_ts)] $*"; }
warn()  { echo "${C_WARN}WARN${C_RST}  [$(_ts)] $*" >&2; }
err()   { echo "${C_ERR}ERROR${C_RST} [$(_ts)] $*" >&2; }
die()   { err "$*"; exit 1; }

usage() {
    sed -n '3,14p' "$0" | sed 's/^#//'
    exit 0
}

# ─── Path resolution (mirrors install.sh lines 38-79) ──────────────────
_resolve_paths() {
    export WIKIHUB_HOME="${WIKIHUB_HOME:-$HOME/wikihub}"
    export WIKIHUB_SRC="${WIKIHUB_SRC:-$HOME/.local/share/wikihub/src}"

    # Normalize absolute paths (mirrors install.sh _abs_path)
    local _h _s
    case "$WIKIHUB_HOME" in
        "~") WIKIHUB_HOME="$HOME" ;;
        "~/"*) WIKIHUB_HOME="$HOME/${WIKIHUB_HOME#\~/}" ;;
    esac
    case "$WIKIHUB_SRC" in
        "~") WIKIHUB_SRC="$HOME" ;;
        "~/"*) WIKIHUB_SRC="$HOME/${WIKIHUB_SRC#\~/}" ;;
    esac
    _h="$(cd "$(dirname "$WIKIHUB_HOME")" 2>/dev/null && pwd)" && WIKIHUB_HOME="$_h/$(basename "$WIKIHUB_HOME")" || true
    _s="$(cd "$(dirname "$WIKIHUB_SRC")" 2>/dev/null && pwd)" && WIKIHUB_SRC="$_s/$(basename "$WIKIHUB_SRC")" || true
}

# ─── Pre-flight: ensure install.sh exists and is executable ────────────
_preflight() {
    local install_sh="$WIKIHUB_SRC/install.sh"
    if [[ ! -f "$install_sh" ]]; then
        die "install.sh not found at $install_sh — wikihub가 설치되지 않았거나 WIKIHUB_SRC 경로가 잘못됨."
    fi
    if [[ ! -x "$install_sh" ]]; then
        chmod +x "$install_sh" 2>/dev/null || die "install.sh at $install_sh 에 실행 권한이 없고 chmod 실패."
    fi
    # Verify update mode eligibility (mirrors install.sh _detect_mode)
    if [[ ! -f "$WIKIHUB_SRC/_system/VERSION" ]] || [[ ! -d "$WIKIHUB_SRC/.git" ]]; then
        die "WIKIHUB_SRC ($WIKIHUB_SRC) 가 update mode 조건 미충족 — _system/VERSION 또는 .git 부재. fresh install이 필요하면 install.sh를 직접 실행."
    fi
}

# ─── Config drift detection (read-only, never blocks update) ──────────
_detect_drift() {
    local drift_found=false

    # 1. wikihub.yaml existence
    if [[ ! -f "$WIKIHUB_HOME/wikihub.yaml" ]]; then
        warn "[drift] wikihub_yaml=missing — $WIKIHUB_HOME/wikihub.yaml not found. /wh:setup 으로 초기화 필요."
        drift_found=true
    fi

    # 2. rclone.conf existence and permissions
    local rclone_conf="$HOME/.config/rclone/rclone.conf"
    if [[ -f "$rclone_conf" ]]; then
        local rclone_mode
        rclone_mode="$(stat -c %a "$rclone_conf" 2>/dev/null || echo "unknown")"
        if [[ "$rclone_mode" != "600" ]] && [[ "$rclone_mode" != "400" ]]; then
            warn "[drift] rclone_conf=badmode ($rclone_mode) — $rclone_conf 권한이 600 또는 400이 아님. chmod 600 $rclone_conf 권장."
            drift_found=true
        fi
    else
        warn "[drift] rclone_conf=missing — $rclone_conf 없음. rclone 설정 필요."
        drift_found=true
    fi

    # 3. systemd unit overrides
    local override_dirs=()
    while IFS= read -r -d '' d; do
        override_dirs+=("$d")
    done < <(find "$HOME/.config/systemd/user/" -maxdepth 2 -type d -name '*.d' -print0 2>/dev/null || true)
    if [[ ${#override_dirs[@]} -gt 0 ]]; then
        for d in "${override_dirs[@]}"; do
            local unit_name
            unit_name="$(basename "$(dirname "$d")")"
            warn "[drift] unit_override=present — $d (unit: $unit_name). git pull 후 unit 갱신 시 override 손실 가능. 백업 권장."
        done
        drift_found=true
    fi

    # 4. install.lock stale check
    local lock="$WIKIHUB_HOME/install.lock"
    if [[ -f "$lock" ]]; then
        local lock_pid
        lock_pid="$(lsof -Fp "$lock" 2>/dev/null | head -1 | tr -d 'p' || true)"
        if [[ -n "$lock_pid" ]] && kill -0 "$lock_pid" 2>/dev/null; then
            warn "[drift] install_lock=held pid=$lock_pid — 다른 install.sh 가 진행 중. update.sh는 대기하지 않고 종료."
            die "install.lock 이 pid $lock_pid 에 의해 점유됨. 완료 후 재시도."
        elif [[ -n "$lock_pid" ]]; then
            warn "[drift] install_lock_stale pid=$lock_pid — lock holder PID가 존재하지 않음. kill -9 후 잔존 가능. 수동 확인: lsof $lock"
            drift_found=true
        fi
    fi

    # 5. env drift — compare against wikihub.yaml.example
    local example="$WIKIHUB_SRC/wikihub.yaml.example"
    if [[ -f "$example" ]] && command -v python3 &>/dev/null; then
        local env_keys
        env_keys="$(python3 -c "
import yaml, sys
with open('$example') as f:
    data = yaml.safe_load(f)
def find_env(d, path=''):
    if isinstance(d, dict):
        for k, v in d.items():
            if k == 'env_default':
                print(path)
            find_env(v, f'{path}.{k}' if path else k)
find_env(data)
" 2>/dev/null || true)"
        if [[ -n "$env_keys" ]]; then
            while IFS= read -r key; do
                [[ -z "$key" ]] && continue
                local env_var
                env_var="$(echo "$key" | tr '[:lower:]-' '[:upper:]_')"
                if [[ -z "$(eval echo "\${$env_var:-}")" ]]; then
                    warn "[drift] env=$env_var — wikihub.yaml.example 에 env_default 가 정의되었으나 $env_var 미설정."
                    drift_found=true
                fi
            done <<< "$env_keys"
        fi
    fi

    if ! "$drift_found"; then
        ok "설정 drift 없음."
    fi
}

# ─── Snapshot currently-active wikihub systemd units ──────────────────
_snapshot_active_units() {
    systemctl --user list-units --no-legend 'wikihub-*' 2>/dev/null \
        | awk '{print $1}' \
        | sort -u
}

# ─── Selective restart report (post-update) ──────────────────────────
_selective_restart_report() {
    local snapshot_file="$WIKIHUB_HOME/.update-snapshot.units"
    [[ -f "$snapshot_file" ]] || { info "스냅샷 파일 없음 — restart report 생략."; return 0; }

    local snapshot_ts
    snapshot_ts="$(stat -c %Y "$snapshot_file" 2>/dev/null || echo "0")"
    local changed_units=()
    local skipped_units=()

    while IFS= read -r unit; do
        [[ -z "$unit" ]] && continue
        local unit_file="$HOME/.config/systemd/user/$unit"
        if [[ -f "$unit_file" ]] && [[ "$(stat -c %Y "$unit_file" 2>/dev/null || echo "0")" -gt "$snapshot_ts" ]]; then
            changed_units+=("$unit")
        else
            skipped_units+=("$unit")
        fi
    done < "$snapshot_file"

    if [[ ${#changed_units[@]} -gt 0 ]]; then
        info "변경된 systemd unit (재시작됨):"
        for u in "${changed_units[@]}"; do
            echo "  [restart-needed] $u"
        done
    fi
    if [[ ${#skipped_units[@]} -gt 0 ]]; then
        info "변경 없는 unit (재시작 불필요):"
        for u in "${skipped_units[@]}"; do
            echo "  [restart-skip]   $u"
        done
    fi
    rm -f "$snapshot_file"
}

# ─── Argument parsing ─────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) shift; EXPLICIT_VERSION="$1"; shift ;;
        --branch)  shift; BRANCH="$1"; shift ;;
        --skip-drift-check) SKIP_DRIFT_CHECK=true; shift ;;
        --non-interactive)  NON_INTERACTIVE=true; shift ;;
        --dry-run)          DRY_RUN=true; shift ;;
        -h|--help) usage ;;
        *) die "Unknown option: $1. See --help for usage." ;;
    esac
done

# ─── Main ─────────────────────────────────────────────────────────────
main() {
    _resolve_paths

    info "=== wikihub update (scripts/update.sh) ==="
    info "WIKIHUB_SRC  = $WIKIHUB_SRC"
    info "WIKIHUB_HOME = $WIKIHUB_HOME"
    [[ -n "$EXPLICIT_VERSION" ]] && info "Version pin  = $EXPLICIT_VERSION"
    [[ -n "$BRANCH" ]] && info "Branch       = $BRANCH"

    _preflight

    # Drift detection (informational, never blocks)
    if ! "$SKIP_DRIFT_CHECK"; then
        info "=== 설정 drift 점검 ==="
        _detect_drift
    fi

    # Snapshot active units for selective restart report
    local snapshot_file="$WIKIHUB_HOME/.update-snapshot.units"
    _snapshot_active_units > "$snapshot_file"
    local unit_count
    unit_count="$(wc -l < "$snapshot_file")"
    info "활성 wikihub unit 스냅샷: ${unit_count}개"

    # Build install.sh argv
    local install_sh="$WIKIHUB_SRC/install.sh"
    local argv=()

    # --skip-confirm: suppress install.sh 5s confirm (unless --non-interactive)
    if ! "$NON_INTERACTIVE"; then
        argv+=( "--skip-confirm" )
    fi
    [[ -n "$EXPLICIT_VERSION" ]] && argv+=( "--version" "$EXPLICIT_VERSION" )
    [[ -n "$BRANCH" ]] && argv+=( "--branch" "$BRANCH" )

    if "$DRY_RUN"; then
        info "=== DRY RUN — install.sh 미호출 ==="
        echo ""
        echo "Planned command:"
        echo "  bash $install_sh ${argv[*]}"
        echo ""
        echo "Snapshot file: $snapshot_file (${unit_count} units)"
        echo "Exit 0 (dry-run)."
        rm -f "$snapshot_file"
        exit 0
    fi

    # Export NONINTERACTIVE if flag set
    if "$NON_INTERACTIVE"; then
        export WIKIHUB_NONINTERACTIVE=1
    fi

    # Delegate to install.sh
    info "=== install.sh update mode 호출 ==="
    bash "$install_sh" "${argv[@]}"
    local install_exit=$?

    if [[ $install_exit -eq 0 ]]; then
        ok "install.sh update 완료 (exit 0)."
        # Post-update: selective restart report
        _selective_restart_report
        info "=== wikihub update 완료 ==="
        echo ""
        echo "사후 확인:"
        echo "  systemctl --user status wikihub-*"
        echo "  journalctl --user -u wikihub-* -n 20 --no-pager"
    else
        err "install.sh update 실패 (exit $install_exit). install.sh 의 trap rollback 이 실행됨."
        err "로그 확인: journalctl --user -u wikihub-* -n 50 --no-pager"
        rm -f "$snapshot_file"
        exit $install_exit
    fi
}

main "$@"
