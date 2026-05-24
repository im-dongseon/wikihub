#!/usr/bin/env bash
# scripts/migrate_layout.sh
# wikihub layout migration helper (ADR-0034) — pre-ADR-0034 layout → v0.1.0 data-first.
#
# !!! v0.1.8 cleanup 예정 #Q (features/backlog.md "graphify_profile_namespace 산출 §v0.1.8 cleanup 묶음") — pre-v0.1.0 transition 1회성 helper, 운영자 base 정착 후 영구 무용. 본 파일 전체 삭제 예정 !!!
#
# pre-layout: ~/wikihub (repo) + ~/wikihub-instance (운영 자산)
# new layout: ~/wikihub (운영 자산, WIKIHUB_HOME) + ~/.local/share/wikihub/src (시스템 코드, WIKIHUB_SRC)
#
# 특징 (ADR-0034 §sub-3 + §sub-4):
#   - 9-phase state machine (resume on partial failure)
#   - mv-only (cp 없음 — ENOSPC 회피)
#   - rollback trap (ADR-0030 패턴 — phase-aware reverse-mv)
#   - rclone FUSE unmount retry + lazy fallback (busy 처리)
#   - flock advisory lock (단독 실행 race 차단)
#   - systemd in-flight grace (15min, ADR-0030 §sub-1)
#
# 호출:
#   bash <(curl ...)/scripts/migrate_layout.sh
#   또는 install.sh _step0_legacy_detect 가 자동 호출 (NONINTERACTIVE=1)
# ============================================================================

set -euo pipefail

# ─── 변수 (env override 가능) ──────────────────────────────────────────
LEGACY_REPO="${LEGACY_WIKIHUB_REPO:-$HOME/wikihub}"
LEGACY_INSTANCE="${LEGACY_WIKIHUB_INSTANCE:-$HOME/wikihub-instance}"
NEW_HOME="${WIKIHUB_HOME:-$HOME/wikihub}"
NEW_SRC="${WIKIHUB_SRC:-$HOME/.local/share/wikihub/src}"
STATE_DIR="${WIKIHUB_STATE_DIR:-$HOME/.local/state/wikihub}"
PHASE_FILE="$STATE_DIR/migrate_layout.phase"
LOCK_FILE="$STATE_DIR/migrate_layout.lock"

mkdir -p "$STATE_DIR"

# ─── ANSI ──────────────────────────────────────────────────────────────
if [ -t 1 ] && [ -n "${TERM:-}" ] && [ "${TERM:-}" != "dumb" ]; then
    C_OK=$'\033[1;32m'; C_INFO=$'\033[1;34m'; C_WARN=$'\033[1;33m'; C_ERR=$'\033[1;31m'; C_RST=$'\033[0m'
else
    C_OK=''; C_INFO=''; C_WARN=''; C_ERR=''; C_RST=''
fi
_ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
info() { echo "${C_INFO}INFO${C_RST}  [$(_ts)] $*"; }
ok()   { echo "${C_OK}OK${C_RST}    [$(_ts)] $*"; }
warn() { echo "${C_WARN}WARN${C_RST}  [$(_ts)] $*" >&2; }
err()  { echo "${C_ERR}ERROR${C_RST} [$(_ts)] $*" >&2; }

# ─── flock advisory ────────────────────────────────────────────────────
exec 200>"$LOCK_FILE"
if ! flock -nx 200; then
    err "다른 migration 인스턴스 실행 중 (lock: $LOCK_FILE)"
    exit 2
fi

# ─── phase marker ──────────────────────────────────────────────────────
# values: pre-stop | stopped | unmounted | mv-src-done | mv-home-done |
#         hermes-patched | render-done | start-done | DONE
get_phase() { [[ -f "$PHASE_FILE" ]] && cat "$PHASE_FILE" || echo "pre-stop"; }
set_phase() { echo "$1" > "$PHASE_FILE"; }

_validate_phase() {
    local p
    p=$(get_phase)
    case "$p" in
        pre-stop|stopped|unmounted|mv-src-done|mv-home-done|hermes-patched|render-done|start-done|DONE) ;;
        *)
            err "invalid phase value: $p (PHASE_FILE: $PHASE_FILE)"
            err "  운영자 직접 편집 또는 typo — 수동 정합 후 재시도"
            exit 2
            ;;
    esac
}

# ─── rollback trap (ADR-0030 패턴, phase-aware reverse-mv) ─────────────
_systemd_start_legacy() {
    # 운영자 backup 상태 — legacy paths 가 다시 존재한다는 가정
    if [[ -d "$LEGACY_INSTANCE/wikihub.yaml" || -f "$LEGACY_INSTANCE/wikihub.yaml" ]]; then
        info "  rollback: systemd 재기동 (legacy paths)"
        systemctl --user daemon-reload 2>/dev/null || true
        systemctl --user start 'wikihub-mount@*.service' 2>/dev/null || true
        sleep 3
        systemctl --user start 'wikihub-vault@*.timer' 2>/dev/null || true
        systemctl --user start 'wikihub-lint.timer' 2>/dev/null || true
    fi
}

_rollback_if_failed() {
    local exit_code=$?
    [[ $exit_code -eq 0 ]] && return 0
    local current
    current=$(get_phase)
    err "migration failed at phase: $current"
    case "$current" in
        pre-stop|stopped|unmounted)
            warn "  mv 전 단계 — systemd 재기동 만"
            _systemd_start_legacy
            ;;
        mv-src-done)
            warn "  src mv 후 home mv 전 — src 만 reverse"
            if [[ -d "$NEW_SRC/.git" ]] && [[ ! -d "$LEGACY_REPO/.git" ]]; then
                mv "$NEW_SRC" "$LEGACY_REPO"
            fi
            _systemd_start_legacy
            ;;
        mv-home-done)
            warn "  양쪽 mv 후 hermes 갱신 전 — 양쪽 reverse"
            if [[ -e "$NEW_HOME" ]] && [[ ! -e "$LEGACY_INSTANCE" ]]; then
                mv "$NEW_HOME" "$LEGACY_INSTANCE"
            fi
            if [[ -d "$NEW_SRC/.git" ]] && [[ ! -d "$LEGACY_REPO/.git" ]]; then
                mv "$NEW_SRC" "$LEGACY_REPO"
            fi
            _systemd_start_legacy
            ;;
        hermes-patched|render-done)
            err "  migration 후반 단계 실패 — 운영자 수동 검토 필요"
            err "  - ~/.hermes/config.yaml.wikihub-bak.* backup 검토"
            err "  - phase: $current (PHASE_FILE: $PHASE_FILE 보존)"
            ;;
    esac
    exit "$exit_code"
}
trap '_rollback_if_failed' ERR EXIT INT TERM HUP

# ─── Step 1. systemd stop (ADR-0030 §sub-1 — in-flight grace) ─────────
_systemd_stop_legacy() {
    local p; p=$(get_phase)
    [[ "$p" != "pre-stop" ]] && return 0   # idempotent resume
    info "Step 1: systemd stop sequence (15min in-flight grace)"
    # timer 먼저 stop (새 fire 차단)
    systemctl --user stop 'wikihub-vault@*.timer' 2>/dev/null || true
    systemctl --user stop 'wikihub-lint.timer' 2>/dev/null || true
    # vault@*.service grace (mid-sync 자연 종료 대기, max 15min)
    timeout 900 systemctl --user stop 'wikihub-vault@*.service' 2>/dev/null || true
    systemctl --user stop 'wikihub-lint.service' 2>/dev/null || true
    # mount@ 마지막 (file_map 보호)
    systemctl --user stop 'wikihub-mount@*.service' 2>/dev/null || true
    systemctl --user reset-failed 'wikihub-*' 2>/dev/null || true
    set_phase "stopped"
    ok "Step 1 systemd stop 완료"
}

# ─── Step 2. rclone FUSE unmount (busy retry + lazy fallback) ─────────
_unmount_vaults() {
    local p; p=$(get_phase)
    [[ "$p" != "stopped" ]] && return 0
    info "Step 2: rclone FUSE unmount"
    [[ -d "$LEGACY_INSTANCE/vault" ]] || { set_phase "unmounted"; return 0; }
    for mp in "$LEGACY_INSTANCE"/vault/*/; do
        [[ -d "$mp" ]] || continue
        local mpr="${mp%/}"
        # FUSE mount 인지 확인
        if mount | grep -qF " on $mpr type fuse"; then
            local i=0
            while (( i < 6 )); do
                if fusermount3 -u "$mpr" 2>/dev/null; then
                    info "  unmounted: $mpr"
                    break
                fi
                sleep 10
                i=$((i+1))
            done
            if (( i == 6 )); then
                warn "  busy retry 60s 초과 — lazy unmount fallback: $mpr"
                fusermount3 -uz "$mpr" 2>/dev/null || true
            fi
        fi
    done
    set_phase "unmounted"
    ok "Step 2 unmount 완료"
}

# ─── Step 3. mv src (LEGACY_REPO → NEW_SRC, mv-only) ──────────────────
_mv_src() {
    local p; p=$(get_phase)
    [[ "$p" != "unmounted" ]] && return 0
    info "Step 3: mv $LEGACY_REPO → $NEW_SRC"
    if [[ ! -d "$LEGACY_REPO/.git" ]]; then
        err "  $LEGACY_REPO 가 git repo 아님 — migration 대상 아님"
        return 1
    fi
    mkdir -p "$(dirname "$NEW_SRC")"
    if [[ -e "$NEW_SRC" ]]; then
        err "  $NEW_SRC 가 이미 존재 — 수동 정합 필요"
        return 1
    fi
    mv "$LEGACY_REPO" "$NEW_SRC"
    set_phase "mv-src-done"
    ok "Step 3 src mv 완료"
}

# ─── Step 4. mv home (LEGACY_INSTANCE → NEW_HOME) ─────────────────────
_mv_home() {
    local p; p=$(get_phase)
    [[ "$p" != "mv-src-done" ]] && return 0
    info "Step 4: mv $LEGACY_INSTANCE → $NEW_HOME"
    if [[ ! -d "$LEGACY_INSTANCE" ]]; then
        warn "  $LEGACY_INSTANCE 부재 — 신규 install 시나리오 (skip)"
        set_phase "mv-home-done"
        return 0
    fi
    if [[ -e "$NEW_HOME" ]]; then
        err "  $NEW_HOME 가 이미 존재 — 수동 정합 필요"
        return 1
    fi
    mv "$LEGACY_INSTANCE" "$NEW_HOME"
    set_phase "mv-home-done"
    ok "Step 4 home mv 완료"
}

# ─── Step 5. Hermes external_dirs 갱신 ─────────────────────────────────
_patch_hermes_external_dirs_migration() {
    local p; p=$(get_phase)
    [[ "$p" != "mv-home-done" ]] && return 0
    info "Step 5: ~/.hermes/config.yaml external_dirs 갱신"
    local hermes_config="${HERMES_CONFIG_HOME:-$HOME/.hermes}/config.yaml"
    if [[ ! -f "$hermes_config" ]]; then
        warn "  $hermes_config 부재 — Hermes 미설치 추정, skip"
        set_phase "hermes-patched"
        return 0
    fi
    # venv 위치 (ADR-0020 그대로)
    local venv_python="$HOME/.local/share/wikihub/venv/bin/python3"
    if [[ ! -x "$venv_python" ]]; then
        warn "  venv python 부재 ($venv_python) — install.sh _step3_venv 진행 후 재시도 권장"
        set_phase "hermes-patched"
        return 0
    fi
    local stale="$LEGACY_REPO/_system/skills/_generated"
    local new_path="$NEW_SRC/_system/skills/_generated"
    "$venv_python" "$NEW_SRC/scripts/_helpers/hermes_config_migrate.py" \
        --config "$hermes_config" \
        --remove-stale "$stale" \
        --add-new "$new_path" \
        || warn "  hermes_config_migrate.py 실패 — 운영자 수동 정합 필요"
    set_phase "hermes-patched"
    ok "Step 5 Hermes config 갱신 완료"
}

# ─── Step 6. systemd unit render (신 path) ─────────────────────────────
_render_systemd_new() {
    local p; p=$(get_phase)
    [[ "$p" != "hermes-patched" ]] && return 0
    info "Step 6: systemd unit render (신 path)"
    export WIKIHUB_HOME="$NEW_HOME"
    export WIKIHUB_SRC="$NEW_SRC"
    local venv_python="$HOME/.local/share/wikihub/venv/bin/python3"
    if [[ ! -x "$venv_python" ]]; then
        warn "  venv python 부재 — install.sh 재호출 권장 (render 자동 수행)"
        set_phase "render-done"
        return 0
    fi
    "$venv_python" "$NEW_SRC/scripts/_helpers/render_systemd_units.py" \
        --yaml "$NEW_HOME/wikihub.yaml" \
        --render --out "$HOME/.config/systemd/user/" \
        || { err "render_systemd_units.py 실패"; return 2; }
    systemctl --user daemon-reload
    set_phase "render-done"
    ok "Step 6 render 완료"
}

# ─── Step 7. systemd start ─────────────────────────────────────────────
_systemd_start_new() {
    local p; p=$(get_phase)
    [[ "$p" != "render-done" ]] && return 0
    info "Step 7: systemd start (신 path)"
    systemctl --user start 'wikihub-mount@*.service' 2>/dev/null || true
    sleep 5
    systemctl --user start 'wikihub-vault@*.timer' 2>/dev/null || true
    systemctl --user start 'wikihub-lint.timer' 2>/dev/null || true
    set_phase "start-done"
    ok "Step 7 start 완료"
}

# ─── detect ─────────────────────────────────────────────────────────────
detect_legacy() {
    [[ -d "$LEGACY_REPO/.git" && -d "$LEGACY_INSTANCE" ]] \
        && (cd "$LEGACY_REPO" 2>/dev/null && git config --get remote.origin.url 2>/dev/null | grep -q "im-dongseon/wikihub")
}

# ─── main ───────────────────────────────────────────────────────────────
main() {
    _validate_phase
    local current
    current=$(get_phase)
    info "wikihub layout migration helper (ADR-0034)"
    info "  phase resume from: $current"
    if [[ "$current" == "DONE" ]]; then
        ok "이미 migration 완료 (phase: DONE). PHASE_FILE 삭제 후 재실행 시 처음부터:"
        ok "  rm $PHASE_FILE && bash $0"
        return 0
    fi
    if [[ "$current" == "pre-stop" ]] && ! detect_legacy; then
        info "legacy layout (~/wikihub repo + ~/wikihub-instance) 미detect — migration 불필요"
        set_phase "DONE"
        trap - ERR EXIT INT TERM HUP
        return 0
    fi
    _systemd_stop_legacy
    _unmount_vaults
    _mv_src
    _mv_home
    _patch_hermes_external_dirs_migration
    _render_systemd_new
    _systemd_start_new
    set_phase "DONE"
    trap - ERR EXIT INT TERM HUP   # 명시 해제 (success)
    ok "migration 완료 — phase: DONE"
    ok "  운영 자산: $NEW_HOME"
    ok "  시스템 코드: $NEW_SRC"
}

main "$@"
