# Analysis & Design — update_mode

- **approved**: 2026-05-17 (v3)
- **feat_id**: `update_mode`
- **시작일 (KST)**: 2026-05-17
- **선행 ADR**: ADR-0010 (Accepted) — 본 feature 가 conformance 회복.
- **신규 ADR 후보**: ADR-0030 — update workflow orchestration (CRIT/HIGH lock 후 Step 3 진입 직전 작성).

## Revision Log

| Version | Date | 변경 요지 |
|---|---|---|
| v1 | 2026-05-17 | 초안. ADR-0010 conformance + F4 결함 #A·#B·#C·#D + R16-L2. design_review_1·2 회부. |
| v2 | 2026-05-17 | R1·R2 리뷰 (CRIT 5 + HIGH 9) 반영. ADR-0010 의 `latest` 정본 유지 (semver derive 제거), curl-pipe bootstrap mode-aware, install.sh 가 systemd render 직접 수행 (hermes 독립), rollback trap, 15min stop grace + reset-failed, force-fresh safety guard 추출. |
| v3 | 2026-05-17 | R3 리뷰 (CRIT-N 2 + HIGH-N 4 + PARTIAL 5건 + MED/LOW 8건) 반영. rollback 에 systemd re-render 추가 (CRIT-N1), stop 직후 daemon-reload (CRIT-N2), `render_systemd_units.py` 정본 contract §6.1 신설 (HIGH-N1), `_detect_mode` 후 tag integrity check + 단일 wipe (HIGH-N2 + LOW-N1), `--version` no-arg 분기 제거 (HIGH-N3), bootstrap exec 전 fd close (HIGH-N4), SIGINT 분기 + progress output (MED-N4), helper 단일화 (MED-N5). |

---

## 1. 배경 및 목적

F4 install_runtime 이 OCI ARM Ubuntu 신규 설치 path 만 완성. ADR-0010 이 lock 한 **dual-mode lifecycle** (install + update 동일 entrypoint, `_system/VERSION` detect 자동 분기, tag `latest` default) 의 update path 가 implementation 단계에서 누락. F4 surface 결함 #A·#B·#C·#D 가 모두 본 누락의 증상.

**목적**: ADR-0010 spec 을 install.sh 에 완전 반영하고, ADR-0010 미명시 운영 안전 영역 (systemd orchestration · unstaged 작업 보호 · rollback · log rotation · 동시 호출 차단) 을 ADR-0030 로 신규 정본화.

### 핵심 invariant (acceptance criteria 원천)

1. **재호출 = 정합 동기화**, 재설치 아님. user 파일 (`wikihub.yaml`·`.credentials/`·`_state/`·`vault/`·`wiki/`) 절대 미터치. WIKIHUB_HOME 내부의 .gitignored 파일도 reset --hard 가 보존.
2. **vault@ timer fire 와 update race 차단**: systemd stop sequence 의 15min in-flight grace (`TimeoutStartSec` 정합) + reset-failed.
3. **unstaged 작업 silent 손실 0**: dirty tree → abort. `.git/index.lock` 잔존 → abort + 안내. `--force-fresh` 로만 명시 동의.
4. **idempotent + 자동 rollback**: 동일 ref 재호출은 no-op. 다른 ref 재호출은 깨끗하게 transition. Step 2~Step 10 어디서 실패해도 직전 ref + 직전 systemd spec 로 자동 복귀.
5. **동시 invocation 차단**: install.sh 자체에 `flock` 락 — 두 인스턴스 동시 호출 시 둘째 즉시 fatal exit.

---

## 2. 현행 진단

### 2.1 F4 install.sh 상태 (main `27966bc` 기준)

| 항목 | 현행 | ADR-0010 spec | gap |
|---|---|---|---|
| Entrypoint | `install.sh` 단일 (curl-pipe + 직접 실행) | 동일 | 정합 |
| Repo URL | env `WIKIHUB_REPO_URL`, default GitHub HTTPS | 동일 | 정합 |
| Default ref | `BRANCH="${BRANCH:-latest}"` — branch name 로 `git clone --branch latest` | tag `latest` (이동 태그, 메인테이너가 release 시 force-push) | **#A**: tag 미존재 → fail |
| curl-pipe bootstrap | `bootstrap_clone_then_exec` 가 mode 무관 무조건 `_step2_clone` (rm -rf) | detect 후 분기 | **#B** |
| `--version` flag | 부재 | `--version v0.1.0` 명시 (ADR-0010 §Decision L66) | **#A 보강** |
| Detect 시그널 | `[ -e $WIKIHUB_HOME ]` + origin 검증 → wipe | `_system/VERSION` 존재 → update mode | **#B** |
| Update path | 부재 (모두 wipe+clone) | git fetch + checkout target, user 파일 보존 | **#B** |
| systemd stop/start | install Step 6 stub, restart 미수행 | (ADR-0010 미명시 — 본 feature 가 ADR-0030 신규) | **#C** + **#D** |
| install.log rotation | 부재 | (미명시 — 본 feature 신규) | **R16-L2** |
| unstaged guard | 부재 | (미명시 — 본 feature 신규) | **신규 safety gap** |
| Rollback | 부재 | (미명시 — 본 feature 신규) | **신규 safety gap** |
| 동시 호출 차단 | 부재 | (미명시 — 본 feature 신규) | **신규 safety gap** |

### 2.2 F4 결함·R16-L2 매핑

| 결함 ID | 본 feature step 매핑 |
|---|---|
| #A | §4 ref resolution + §3 Step 0 BRANCH default 변경 + Step 6 `--version` flag |
| #B | §3 Step 0·2·2a·2d update path (`git fetch` + `reset --hard`) + curl-pipe mode-aware bootstrap |
| #C | §3 Step 2c stop sequence (15min grace) + §3 Step 9 start sequence + reset-failed (ADR-0030) |
| #D | §3 Step 8 install.sh 가 systemd unit template 직접 render + restart (hermes 독립). `/wh:setup` 은 best-effort skill 메타 갱신 |
| R16-L2 | §3 Step -1 log rotation (tee 시작 직전) |

### 2.3 ADR-0010 conformance 회복 항목

- `_system/VERSION` AND `.git` 존재 detect → update path (§3 Step 0).
- "v0.1.0 → v0.1.1" 형식 transition 보고 (§3 Step 2e).
- `--version v0.1.0` flag (§4 우선순위 1).
- tag `latest` (이동 태그) 정본 유지 — semver derive 제거 (v1 의 path 3 회수). v0.1.0 spec 완성 시점에 메인테이너가 `git tag -f latest <commit> && git push -f origin latest` 부여.

---

## 3. Update Workflow 정본 (Step 단위 spec)

### 진입점 (사용자 시점)

```bash
# 표준 — install/update 동일 명령 (ADR-0010 정합)
curl -fsSL https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh | bash

# 옵션
curl ... | bash -s -- --version v0.1.0       # 특정 tag pin (install·rollback)
curl ... | bash -s -- --force-fresh           # 명시적 destructive 재설치
```

> **C5 lock**: ADR-0010 의 `latest` (이동 태그) 정본 유지. 본 feature ship + v0.1.0 spec 완성 후 메인테이너가 `latest` tag 부여. tag 부재 시 (현 시점) curl URL `/latest/install.sh` 가 404 — 메인테이너는 본 feature ship 직후 `latest` tag 를 main HEAD 로 1회 push 후 정상 운영. README/ADR-0010 에 release 절차 명시 (이미 ADR-0010 L84-86 정의됨).

### Step -1 (신규) — log rotation (tee 시작 전, **R16-L2 + R2-HIGH-6 closure**)

main flow 의 가장 첫 호출. install.log tee 가 fd 잡기 전에 수행 → tee fd race 회피.

```bash
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
        # 7개 보관 — tail -n +8 의 8 = 보관수 + 1 (LOW-N2)
        ls -1t "${log}".*_* 2>/dev/null | tail -n +8 | xargs -r rm -f
    fi
}
```

호출 순서: `_rotate_install_log` → `mkdir -p $WIKIHUB_INSTANCE_ROOT` → `exec > >(tee -a $INSTALL_LOG) 2>&1`.

### Step 0 — Mode Detect (신규, **C1 + #B closure**)

curl-pipe bootstrap **이전** 에 detect → mode-aware 분기.

```bash
_detect_mode() {
    if [[ -f "$WIKIHUB_HOME/_system/VERSION" ]] && [[ -d "$WIKIHUB_HOME/.git" ]]; then
        INSTALL_MODE="update"
        # HIGH-N2: VERSION 파일과 git tag 정합 검증 (위조 시나리오 namespace)
        _verify_version_tag_integrity   # warn-only (dev branch / detached HEAD 정합)
    elif [[ -f "$WIKIHUB_HOME/_system/VERSION" ]] || [[ -d "$WIKIHUB_HOME/.git" ]]; then
        err "WIKIHUB_HOME ($WIKIHUB_HOME) 가 partial state — _system/VERSION 또는 .git 한쪽만 존재."
        err "  진단: ls -la $WIKIHUB_HOME"
        err "  복구: 의도적으로 wipe 하려면 --force-fresh, 이전 backup 복구는 수동."
        exit 1
    else
        INSTALL_MODE="fresh"
    fi
    # --force-fresh override
    if [[ -n "${FORCE_FRESH:-}" ]]; then
        INSTALL_MODE="fresh"
        _confirm_force_fresh_wipe   # 5초 confirm (interactive only) — Step 2 의 wipe 진입 직전
    fi
    export INSTALL_MODE
}

_verify_version_tag_integrity() {
    # VERSION 파일 값 vs 현 HEAD 의 git tag (exact-match) 비교.
    # mismatch 는 fatal 아닌 warn — 운영자가 main HEAD 또는 dev branch 위에 있는 정합 케이스 포함.
    local version_str tag_exact
    IFS= read -r version_str < "$WIKIHUB_HOME/_system/VERSION" 2>/dev/null || version_str=""
    tag_exact="$(git -C "$WIKIHUB_HOME" describe --tags --exact-match HEAD 2>/dev/null || true)"
    if [[ -n "$version_str" && -n "$tag_exact" ]]; then
        # tag 가 v-prefix, VERSION 은 prefix 없음 — strip 후 비교
        if [[ "${tag_exact#v}" != "$version_str" ]]; then
            warn "_system/VERSION ($version_str) 과 git tag ($tag_exact) mismatch — VERSION 위조 의심 또는 dev branch."
            warn "  의도적이면 무시. 아니면 \`--force-fresh\` 로 재설치."
        fi
    fi
}
```

**bootstrap_clone_then_exec mode-aware 갱신** (C1 fix):

```bash
bootstrap_clone_then_exec() {
    # detect 가 이미 끝났음. update mode 면 clone 없이 in-place exec.
    # HIGH-N4: fd 200 (install.lock) 명시 close 후 exec — 새 process 가 fresh lock 잡도록.
    exec 200>&- 2>/dev/null || true
    if [[ "$INSTALL_MODE" == "update" ]]; then
        info "curl-pipe + update mode — 기존 $WIKIHUB_HOME/install.sh 로 self-replace (clone 없이)"
        exec bash "$WIKIHUB_HOME/install.sh" "${ORIGINAL_ARGS[@]}"
    fi
    # fresh path 만 clone (기존 동작)
    info "curl-pipe + fresh mode — repo 부트스트랩"
    _step2_clone
    exec bash "$WIKIHUB_HOME/install.sh" "${ORIGINAL_ARGS[@]}"
}
```

> **C1 PARTIAL closure note**: curl-pipe + update mode 에서 새 process 는 **disk 의 직전 ref install.sh** 를 실행. 즉 curl 로 받은 새 install.sh 의 신규 guard·rollback trap 등은 적용 안 됨. 이는 ADR-0010 정합 — "update 는 정본 동기화" 의미상 직전 install.sh 가 가져다 둔 working tree (현재 main 의 F4 baseline + update_mode 본 feature 의 self-bootstrap) 가 충분한 baseline 임을 가정. 단 첫 update (F4 → update_mode) 는 F4 install.sh 의 destructive `rm -rf` 가 동작하므로 본 feature 의 첫 deploy 는 운영자가 명시적으로 fresh path 로 진행 (`--force-fresh` 또는 install 없는 환경) → 다음 호출부터 update path 자동.

main 의 흐름: `_rotate_install_log` → tee setup → CLI parse → `_pipe_mode_detect` → `_detect_mode` → `bootstrap_clone_then_exec` (mode-aware) 또는 직접 진행.

### Step 1 — Env Check (기존 유지)

`_step1_env_check` — EUID·OS·systemd·unzip. update mode 도 동일.

### Step 2 — `_step2_update` (신규, **#B closure** + **C3 rollback trap**)

```bash
_step2_update() {
    # LOW-N3: trap 등록을 함수 진입 즉시 (read 보다 먼저) — silent exit 회피
    export PRE_UPDATE_REF
    PRE_UPDATE_REF="$(git -C "$WIKIHUB_HOME" rev-parse HEAD)"
    trap '_rollback_if_failed' ERR EXIT INT

    info "[detected wikihub at ${WIKIHUB_HOME}]"
    local current_version
    IFS= read -r current_version < "$WIKIHUB_HOME/_system/VERSION" || current_version=""
    if [[ -z "$current_version" ]]; then
        err "_system/VERSION empty — 파일 손상 의심. \`--force-fresh\` 로 재설치 또는 수동 복구."
        exit 1
    fi
    info "  current version: v${current_version}"
    info "[update mode — Ctrl+C within 5s to abort]"
    [[ -z "${WIKIHUB_NONINTERACTIVE:-}" ]] && sleep 5

    # 2a. unstaged guard (R2-HIGH-2 + index.lock 보강)
    if [[ -f "$WIKIHUB_HOME/.git/index.lock" ]]; then
        err ".git/index.lock 잔존 — 직전 git 명령이 비정상 종료된 흔적."
        err "  대처: 다른 git process 부재 확인 후 \`rm $WIKIHUB_HOME/.git/index.lock\` 후 재호출."
        exit 1
    fi
    if [[ -n "$(cd "$WIKIHUB_HOME" && git status --porcelain)" ]]; then
        err "WIKIHUB_HOME 에 unstaged 변경 있음."
        err "  대처: \`git -C ${WIKIHUB_HOME} stash\` 또는 \`--force-fresh\` 로 재설치"
        exit 1
    fi

    # 2b. (PRE_UPDATE_REF 캡처 + trap 은 함수 진입 시 이미 등록 — LOW-N3 fix)

    # 2c. systemd stop sequence (C4 — 15min grace + reset-failed + CRIT-N2 daemon-reload)
    _systemd_stop_before_update

    # 2d. fetch + ref resolve + reset
    git -C "$WIKIHUB_HOME" fetch origin --tags || {
        warn "git fetch 실패 — local cache fallback"
    }
    local target_ref
    target_ref="$(_resolve_ref)"
    info "git reset --hard ${target_ref}"
    git -C "$WIKIHUB_HOME" reset --hard "$target_ref"
    # post-condition (R2-HIGH-5 disk full 등 partial state)
    if ! git -C "$WIKIHUB_HOME" diff --quiet HEAD --; then
        err "git reset --hard 후 working tree 여전히 dirty — disk full / 디스크 오류 의심"
        err "  진단: df -h $WIKIHUB_HOME; git -C $WIKIHUB_HOME status"
        exit 2   # trap 이 rollback 수행
    fi

    # 2e. VERSION 비교·보고 + downgrade 분기 (R2-MED-2)
    local new_version
    IFS= read -r new_version < "$WIKIHUB_HOME/_system/VERSION"
    if [[ "$current_version" == "$new_version" ]]; then
        info "already at v${new_version} — proceeding to systemd reorchestrate (idempotent)"
    elif _semver_gt "$current_version" "$new_version"; then
        if [[ -n "${EXPLICIT_VERSION_FLAG:-}" ]]; then
            warn "intentional downgrade: v${current_version} → v${new_version} (via --version)"
        else
            err "unexpected downgrade detected: v${current_version} → v${new_version}"
            err "  의도적이면 --version v${new_version} 명시 호출"
            exit 1   # trap rollback
        fi
    else
        ok "version transition: v${current_version} → v${new_version}"
    fi

    export INSTALL_MODE_TARGET_REF="$target_ref"
}

_rollback_if_failed() {
    local exit_code=$?
    trap - ERR EXIT INT
    [[ $exit_code -eq 0 ]] && return 0

    # MED-N4: SIGINT (exit 130) — stop sequence 중간 abort 분기
    if [[ $exit_code -eq 130 ]]; then
        err "사용자 abort (Ctrl+C) — 직전 systemd state 복구 시도"
        # PRE_UPDATE_REF 와 current ref 가 같다 = git reset 전. systemd 만 직전 state 로.
        local current_ref
        current_ref="$(git -C "$WIKIHUB_HOME" rev-parse HEAD)"
        if [[ "$current_ref" == "${PRE_UPDATE_REF:-}" ]]; then
            warn "git tree 미변경. stop sequence 중간 abort 의심 — systemd 재기동 시도."
            _systemd_start_after_update 2>/dev/null || warn "systemd 재기동 실패. 수동 복구: systemctl --user list-units 'wikihub-*'"
        fi
        exit 130
    fi

    [[ -z "${PRE_UPDATE_REF:-}" ]] && return 0
    local current_ref
    current_ref="$(git -C "$WIKIHUB_HOME" rev-parse HEAD)"
    [[ "$current_ref" == "$PRE_UPDATE_REF" ]] && {
        # git tree 미변경 — systemd 가 stop 됐다면 직전 spec 으로 재기동
        err "update 실패 (exit ${exit_code}) — git reset 전 단계. systemd 재기동 시도."
        _systemd_start_after_update 2>/dev/null || warn "systemd 재기동 실패 — 수동 복구"
        exit $exit_code
    }

    err "update 실패 (exit ${exit_code}) — 직전 ref ${PRE_UPDATE_REF:0:7} 로 자동 rollback"
    # CRIT-N1: git reset 후 직전 ref 의 template 으로 systemd unit 재render → daemon-reload → start
    git -C "$WIKIHUB_HOME" reset --hard "$PRE_UPDATE_REF" || { warn "rollback reset 실패 — 수동 복구"; exit $exit_code; }
    _step8_systemd_render || warn "rollback systemd render 실패 — 수동 복구 (systemctl daemon-reload 직접 호출)"
    _systemd_start_after_update || warn "rollback systemd 재기동 실패 — 수동 복구"
    exit $exit_code
}
```

### Step 2 (fresh path) — `_step2_clone` (기존 + H4)

기존 `_step2_clone` 의 3 safety guard 를 `_validate_wipe_target()` 으로 추출:

```bash
_validate_wipe_target() {
    case "$WIKIHUB_HOME" in
        ""|"/"|"/usr"|"/usr/local"|"/etc"|"/opt"|"/home"|"$HOME"|"$HOME/")
            err "WIKIHUB_HOME=$WIKIHUB_HOME — wipe 대상으로 안전하지 않음"
            exit 1 ;;
    esac
    [[ -e "$WIKIHUB_HOME" ]] || return 0   # 신규 install 은 검증 대상 없음
    if [[ ! -d "$WIKIHUB_HOME/.git" ]]; then
        err "$WIKIHUB_HOME 가 존재하지만 git repo 아님 — wipe 거부."
        exit 1
    fi
    local origin
    origin="$(cd "$WIKIHUB_HOME" && git config --get remote.origin.url 2>/dev/null || true)"
    case "$origin" in
        *im-dongseon/wikihub*|*wikihub.git*) ;;
        *) err "origin=$origin — wikihub repo 아님. wipe 거부."; exit 1 ;;
    esac
    case "$(pwd)" in
        "$WIKIHUB_HOME"|"$WIKIHUB_HOME"/*) cd "$HOME" ;;
    esac
}

_confirm_force_fresh_wipe() {
    _validate_wipe_target
    [[ -n "${WIKIHUB_NONINTERACTIVE:-}" ]] && return 0
    info "[--force-fresh confirmed target: $WIKIHUB_HOME]"
    info "  Ctrl+C within 5s to abort. wipe 실행."
    sleep 5
}
```

`_step2_clone` 진입 시 `_validate_wipe_target` 호출 후 `rm -rf` (기존 동작).

### Step 3 — venv deps sync (기존 + R2-MED-5 PRE_UPDATE_REF)

update mode 에서 diff 비교:

```bash
_step3_venv() {
    # uv + Python 설치 (idempotent, 기존)
    ...
    # MED-N3: update mode 면 PRE_UPDATE_REF 가 _step2_update 진입 시 항상 capture.
    # 부재 시 fatal assertion (외부 단독 호출 방어).
    if [[ "$INSTALL_MODE" == "update" ]]; then
        [[ -n "${PRE_UPDATE_REF:-}" ]] || { err "_step3_venv invariant 위배: PRE_UPDATE_REF 미설정"; exit 2; }
        if git -C "$WIKIHUB_HOME" diff --quiet "$PRE_UPDATE_REF" HEAD -- scripts/requirements.txt; then
            info "requirements.txt 변경 없음 — pip install skip"
            return 0
        fi
    fi
    # 변경 또는 fresh — uv pip install
    "$VENV_PATH/bin/uv" pip install -r "$WIKIHUB_HOME/scripts/requirements.txt"
}
```

### Step 4·4.5 — gws · rclone (기존 유지)

`GWS_VERSION` / `RCLONE_VERSION` 비교 후 변경 시만 재설치. idempotent.

### Step 5 — yaml (기존 유지)

`_step5_yaml` 가 이미 idempotent (`wikihub.yaml.example` → `wikihub.yaml` 없을 때만).

### Step 6 — agent skill 등록 (기존, **C2 분리**)

기존 `_step6_agent_skill` 는 skill 메타 등록 stub 만 (변경 없음). systemd unit render 책임은 **Step 8 로 이동**.

### Step 7 — linger (update 에서 skip)

`loginctl show-user --property=Linger` 가 `yes` 면 skip. fresh 시점에 활성화.

### Step 8 (변경) — systemd unit render + reorchestrate (**C2 + #D closure**)

install.sh 가 unit template render 를 **직접 수행**. hermes/`wh:setup` 가용성과 독립.

```bash
_step8_systemd_render() {
    # yaml parse 는 venv python 사용 (Step 3 후라 이미 가용)
    local yaml="$WIKIHUB_INSTANCE_ROOT/wikihub.yaml"
    [[ -f "$yaml" ]] || { warn "wikihub.yaml 부재 — systemd render skip (yaml 편집 후 install.sh 재호출)"; return 0; }
    "$VENV_PATH/bin/python3" "$WIKIHUB_HOME/scripts/_helpers/render_systemd_units.py" \
        --yaml "$yaml" --out "$HOME/.config/systemd/user/"
    systemctl --user daemon-reload
}

# best-effort skill 메타 갱신 (F5 미완성 시에도 fail-safe)
_step8_wh_setup_skill_meta() {
    [[ "$INSTALL_MODE" != "update" ]] && return 0
    local agent_binary
    agent_binary="$("$VENV_PATH/bin/python3" -c \
        "import yaml,sys; print(yaml.safe_load(open(sys.argv[1])).get('agent',{}).get('binary',''))" \
        "$WIKIHUB_INSTANCE_ROOT/wikihub.yaml" 2>/dev/null)"
    [[ -x "$agent_binary" ]] || { info "agent.binary 미설치 — skill 메타 갱신 skip"; return 0; }
    info "agent skill 메타 갱신 (best-effort)"
    WIKIHUB_NONINTERACTIVE=1 timeout 300 "$agent_binary" -z "/wh:setup" \
        || warn "/wh:setup 호출 실패 — F5 미완 또는 skill 미등록 (systemd render 는 이미 install.sh 가 수행)"
}
```

**신규 helper**: `scripts/_helpers/render_systemd_units.py` — yaml 의 `vaults[*]` + `agent.*` 읽어 `_system/systemd/*.template` 의 `{placeholder}` substitution 후 `~/.config/systemd/user/wikihub-*` 에 write. 본 helper 는 venv 의존이지만 Step 3 venv 가 install 단계라 항상 가용. (idempotent: byte-equal 시 mtime 보존 → daemon-reload 도 no-op)

> **`/wh:setup` 의 책임 재정의 (C2 fix 의 결과)**: install.sh 가 unit render + daemon-reload 책임을 가져갔으므로, `/wh:setup` 의 책임은 **skill 메타 갱신 + yaml validate + (선택) first ingest prompt** 로 축소. Step 3 구현 시 setup.md 갱신.

### Step 9 — systemd start sequence (**C4 + R2-MED-7 reset-failed**)

```bash
_systemd_stop_before_update() {
    # _enabled_vaults_running = systemctl 에서 active 한 mount instance
    local running_vaults
    running_vaults="$(systemctl --user list-units --no-legend 'wikihub-mount@*.service' \
        | awk '{print $1}' | sed 's/wikihub-mount@\(.*\)\.service/\1/')"
    # timer 정지 — 새 fire 차단
    for v in $running_vaults; do
        systemctl --user stop "wikihub-vault@${v}.timer" 2>/dev/null || true
    done
    systemctl --user stop wikihub-lint.timer 2>/dev/null || true
    # vault@.service mid-sync 대기 — 15min grace (TimeoutStartSec=15min 정합)
    # MED-N4: progress output 으로 운영자 visual 안심 (timeout 명령 wrapper 가 nohup 처럼 동작)
    for v in $running_vaults; do
        info "  stopping vault@${v} (max 15min grace for mid-sync)"
        timeout 900 systemctl --user stop "wikihub-vault@${v}.service" \
            || warn "vault@${v} stop timeout — 강제 abort"
    done
    systemctl --user stop wikihub-lint.service 2>/dev/null || true
    # mount@ 마지막
    for v in $running_vaults; do
        systemctl --user stop "wikihub-mount@${v}.service" 2>/dev/null || true
    done
    # StartLimitBurst 카운터 초기화 (R2-CRIT-2)
    systemctl --user reset-failed 'wikihub-mount@*.service' \
        'wikihub-vault@*.service' 'wikihub-vault@*.timer' \
        'wikihub-lint.service' 'wikihub-lint.timer' 2>/dev/null || true
    # CRIT-N2: stop sequence 직후 daemon-reload — Step 8 render 직전까지 외부 systemctl 호출
    # 시 stale unit 캐시 사용 race 차단. unit 파일 변경 전이라 시 무영향 idempotent.
    systemctl --user daemon-reload
}

_systemd_start_after_update() {
    # _enabled_vaults_yaml = yaml 의 enabled vault (Step 8 render 후의 desired state)
    local desired_vaults
    desired_vaults="$(_enabled_vaults_yaml)"
    # mount 선행
    for v in $desired_vaults; do
        systemctl --user start "wikihub-mount@${v}.service"
    done
    # mount FUSE 안정화 대기 (assert_mount_alive 패턴 재사용)
    for v in $desired_vaults; do
        _wait_mount_ready "$v" 120 || { err "mount@${v} not ready in 120s"; exit 2; }
    done
    for v in $desired_vaults; do
        systemctl --user start "wikihub-vault@${v}.timer"
    done
    systemctl --user start wikihub-lint.timer
}

_wait_mount_ready() {
    local v="$1" timeout="$2" elapsed=0 mount_path
    # MED-N5: helper 단일화 — inline python 제거. render_systemd_units.py 가 yaml 접근 일원화.
    mount_path="$("$VENV_PATH/bin/python3" \
        "$WIKIHUB_HOME/scripts/_helpers/render_systemd_units.py" \
        --yaml "$WIKIHUB_INSTANCE_ROOT/wikihub.yaml" \
        --get-mount-path "$v")"
    mount_path="${mount_path/#\~/$HOME}"
    while (( elapsed < timeout )); do
        if systemctl --user is-active "wikihub-mount@${v}.service" >/dev/null \
           && timeout 5 stat "$mount_path" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2; elapsed=$((elapsed + 2))
    done
    return 1
}

# MED-N1: helper 단일화 + bash fallback (venv 부재 / partial 상태 방어).
_enabled_vaults_yaml() {
    local yaml="$WIKIHUB_INSTANCE_ROOT/wikihub.yaml"
    [[ -f "$yaml" ]] || return 0
    if [[ -x "$VENV_PATH/bin/python3" ]] && \
       [[ -f "$WIKIHUB_HOME/scripts/_helpers/render_systemd_units.py" ]]; then
        "$VENV_PATH/bin/python3" \
            "$WIKIHUB_HOME/scripts/_helpers/render_systemd_units.py" \
            --yaml "$yaml" --list-enabled
        return $?
    fi
    # bash fallback — venv 미가용 시 (rollback 도중 partial 상태 등).
    # 한계: enabled: false 필터링은 best-effort (yaml indent 의존).
    warn "venv helper 미가용 — yaml bash fallback parse (기능 제한)"
    awk '
        /^vaults:/ {in_vaults=1; next}
        in_vaults && /^[^[:space:]]/ {in_vaults=0}
        in_vaults && /^[[:space:]]*-\s*id:/ {gsub(/^[[:space:]]*-\s*id:[[:space:]]*/, ""); print}
    ' "$yaml"
}
```

> `_enabled_vaults_yaml` 는 `_step8_systemd_render` 가 사용하는 동일 helper 가 재사용 (`render_systemd_units.py` 에 `--list-enabled` mode 추가).

### Step 10 — verify (**R2-LOW-4 linger 검사 + H2 unit 존재 검증**)

```bash
_step10_verify() {
    if [[ "$(loginctl show-user --property=Linger --value $USER)" != "yes" ]]; then
        warn "linger 미활성 — systemd --user 명령이 ssh 종료 후 stop. verify skip."
        return 0
    fi
    local desired_vaults; desired_vaults="$(_enabled_vaults_yaml)"
    for v in $desired_vaults; do
        local unit="wikihub-mount@${v}.service"
        if ! systemctl --user is-active "$unit" >/dev/null; then
            err "$unit not active"
            err "  진단: journalctl --user -u $unit -n 50"
            exit 2
        fi
    done
    ok "systemd verify ok"
}
```

### Step 11 — banner (단일 출력, **R1-LOW-3 중복 제거**)

```
=== wikihub install complete ===
  mode: update  (v0.1.0 → v0.1.1)
  ref:  v0.1.1  (target_ref=refs/tags/v0.1.1)
  next sync: ~10m (vault@ timer)
  status: systemctl --user list-timers wikihub-*
=================================
```

Step 2e 의 transition `ok` 출력은 제거 — banner 가 단일 source.

### Step 12 — install.sh lock (**R2-HIGH-4**)

main 진입 직후 (rotate · tee setup 후 즉시):

```bash
_acquire_install_lock() {
    local lock="$WIKIHUB_INSTANCE_ROOT/install.lock"
    exec 200>"$lock"
    if ! flock -n 200; then
        err "다른 install.sh 가 진행 중 (lock: $lock). PID 확인: lsof $lock"
        exit 1
    fi
    # process exit 시 fd 200 자동 close → lock release
}
```

### main flow (v2)

```bash
main() {
    _rotate_install_log            # tee 시작 전 (R16-L2 + R2-HIGH-6)
    mkdir -p "$WIKIHUB_INSTANCE_ROOT"
    exec > >(tee -a "$INSTALL_LOG") 2>&1
    echo "─── install.sh start: $(date -u +%Y-%m-%dT%H:%M:%SZ) ───"

    _parse_cli "$@"                # CLI (--version, --force-fresh, --branch, --skip-confirm 등)
    _acquire_install_lock          # 동시 호출 차단 (R2-HIGH-4)
    _detect_mode                   # update vs fresh (C1, #B)

    if _pipe_mode_detect; then
        bootstrap_clone_then_exec "$@"   # mode-aware (C1 fix)
    fi

    _step1_env_check

    if [[ "$INSTALL_MODE" == "update" ]]; then
        _step2_update              # trap rollback 등록
    else
        # LOW-N1: wipe 단일화 — _step2_clone 이 _validate_wipe_target + rm -rf + clone 일괄 책임
        _step2_clone
    fi

    _step3_venv
    _step4_gws
    _step45_rclone
    _step5_yaml
    _step6_agent_skill

    [[ "$INSTALL_MODE" == "fresh" ]] && _step7_linger

    _step8_systemd_render          # install.sh 가 직접 render (C2)
    _step8_wh_setup_skill_meta     # best-effort skill 메타 (F5 독립)

    if [[ "$INSTALL_MODE" == "update" ]]; then
        _systemd_start_after_update
        _step10_verify
        trap - ERR EXIT             # rollback trap 해제 (성공 종료)
    fi

    _step11_banner
}
```

---

## 4. ref resolution 정책 (#A closure, **C5 ADR-0010 정합 + R2-HIGH-3 network fallback**)

### `_resolve_ref()` 우선순위

1. `--version <tag>` flag 명시 + tag 존재 → `refs/tags/<tag>`. tag 부재 시 fatal exit. `EXPLICIT_VERSION_FLAG=1` set. (HIGH-N3: 인자 강제 소비, no-arg 분기 없음 — 다음 토큰 부재 또는 `--` 시작 시 fatal)
2. `BRANCH` env / `--branch <name>` 명시 + branch 존재 → branch name. fallback 안 함 (의도 명시).
3. (default) tag `latest` 존재 → `refs/tags/latest`. ADR-0010 정본 — 메인테이너 release 시 `git tag -f latest <commit> && git push -f origin latest`.
4. (network fallback) `git ls-remote` fail 시 local cache: `git for-each-ref --sort=-v:refname 'refs/tags/v*' | head -1` — **semver `v*` tag 의 max 값만** 사용. mutable `latest` 의 stale cache 는 비사용 (의미 불안정). banner 에 "[network offline — using local semver max tag (not 'latest')]". 운영자가 `latest` 의 직전 값을 원하면 `--version <tag>` 명시.
5. (bootstrap fallback) tag `latest` 부재 (v0.1.0 spec 완성 전) → `origin/main` HEAD. banner 에 "[no `latest` tag — using main HEAD]".

### BRANCH env default 변경 (R1-MED-1)

- Before: `BRANCH="${BRANCH:-latest}"` → path 2 가 `latest` 를 branch name 로 해석 → fail.
- After: `BRANCH=""` (env 미설정 시 빈 문자열). path 2 는 명시 export 시에만 진입. path 3·4·5 가 자동 fallback chain.

### `--version` flag naming (R1-HIGH-4 + HIGH-N3 v3 lock)

ADR-0010 §Decision L66 그대로 `--version <tag>` — **인자 강제 소비** (no-arg 분기 없음). GNU `--version` (no arg) 관례와 충돌 인지하나 parser 모호성 (인자 순서 swap silent print-exit) 회피 위해 단순화. 운영자 version inspection 은 `cat $WIKIHUB_HOME/_system/VERSION` 사용. ADR-0030 §Notes 에 GNU 관례 분기 명시.

bash parser:
```bash
case "$1" in
    --version)
        if [[ -z "${2:-}" || "${2:0:2}" == "--" ]]; then
            err "--version 인자 필요 (예: --version v0.1.0). version 조회는 \`cat $WIKIHUB_HOME/_system/VERSION\`."
            exit 1
        fi
        EXPLICIT_VERSION="$2"; EXPLICIT_VERSION_FLAG=1
        shift 2
        ;;
```

### tag overwrite 방어 (R2-MED-4 backlog)

`git config remote.origin.pruneTags false` (default) 유지. tag signature verification 은 v0.2.x backlog (자체 본 feature 스코프 외).

---

## 5. 개정 전·후 비교 (Before → After)

### 5.1 install.sh 진입 동작

| 시나리오 | Before (F4) | After (update_mode v2) |
|---|---|---|
| 신규 호출 (`$WIKIHUB_HOME` 없음) | clone | clone + 신규 systemd render |
| 재호출 — clean | rm -rf + clone (user 파일은 instance.root 라 무영향이지만 .git/venv 매번 재생성) | detect → update path → `git fetch + reset --hard` + venv keep + systemd reorchestrate |
| 재호출 — dirty | `rm -rf` (unstaged 손실) | abort + `--force-fresh` 안내 |
| 재호출 — index.lock 잔존 | crash 또는 rm | abort + 안내 |
| `--version v0.1.0` | 미지원 | tag resolve, fresh/update 양쪽 지원 |
| `--force-fresh` | 미지원 | 5초 confirm → wipe (interactive only, NONINTERACTIVE 자동) |
| BRANCH default | `latest` (branch) → fail | empty → tag `latest` 또는 main fallback |
| systemd | render 미수행 + restart 미수행 | install.sh 가 render + daemon-reload + restart |
| install.log | 무제한 append | 7일/10MB → rotate, 7개 보관 |
| 동시 호출 | 보호 없음 | flock 즉시 fatal |
| failure 시 | broken state | trap rollback (직전 ref + 직전 systemd spec) |

### 5.2 운영 mental model

| 행위 | Before | After |
|---|---|---|
| 신규 설치 | `curl ... \| bash` | 동일 |
| 정본 업데이트 | `curl ... \| bash` (race·destructive) | 동일 명령, idempotent + race 차단 |
| 특정 버전 rollback | 수단 없음 | `--version v0.1.0` |
| 완전 재설치 | 의도 불분명 (default 가 destructive) | `--force-fresh` 명시 |

---

## 6. 연계 정본 영향

| 정본 | 영향 | 조치 |
|---|---|---|
| `install.sh` | **전면 갱신** — Step -1·0·2·8 신규, Step 2·9 의사코드 신규, lock·rollback 추가 | §3 모든 변경 |
| `scripts/_helpers/render_systemd_units.py` | **신규** — yaml + template → unit file write + helper modes (`--list-enabled`, `--get-mount-path`) | C2 의 install.sh 직접 render 책임. 정본 contract: §6.1 |
| `_system/commands/setup.md` | 책임 축소 — unit render 가 install.sh 로 이동. skill 메타 + yaml validate + first ingest prompt 만 | Step 3 구현 시 setup.md slim 갱신 |
| `wikihub.yaml.example` | 무영향 | — |
| `_system/wiki-schema.md` · `commands/ingest.md` | 무영향 | — |
| `_system/systemd/*.template` | 무영향 (template 자체 unchanged) | — |
| `_system/VERSION` | 무영향 (`0.1.0` 유지) | v0.1.0 spec 완성 시점에 메인테이너가 tag `v0.1.0` + tag `latest` push |
| `README.md` | install snippet + roadmap 갱신 | Step 3 마지막 |
| `docs/adr/0010-…md` | **conformance 회복** — supersede 아님 | ADR-0030 가 ADR-0010 의 detail 보강 |
| `docs/adr/0023-clean-install-pattern.md` | **scope 분할 명시** — fresh / `--force-fresh` 에만 한정. update path 는 ADR-0030 | Step 3 lock 시점에 ADR-0023 에 Note 추가 |
| `docs/adr/0030-update-workflow-orchestration.md` | **신규 Proposed** | Step 3 lock 직전 작성. Decision 4건 (stop/start sequence · rollback trap · unstaged guard · lock) — ADR 1건 1결정 원칙 위배 가능성은 §8 에서 분할 검토 |

---

## 6.1 `scripts/_helpers/render_systemd_units.py` Contract (v3 신설 — HIGH-N1 closure)

본 helper 는 install.sh 의 yaml 접근·systemd unit render 책임을 단일화하는 정본. setup.md §Step 2 의 2-pass substitution 책임이 본 helper 로 이관.

### CLI 인터페이스

```
render_systemd_units.py [--yaml PATH] <MODE>

modes (mutually exclusive):
  --render --out DIR         : yaml + _system/systemd/*.template → DIR 에 render. idempotent.
  --list-enabled             : enabled vault id 목록 (1줄 1개) stdout. exit 0.
  --get-mount-path VAULT_ID  : 해당 vault 의 options.mount_path 출력. 미발견 exit 1.
  --validate                 : yaml schema validate only — render 없음. exit 0/1.

options:
  --yaml PATH    yaml 경로. default `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml`.
```

### `--render` 동작

1. `--yaml` 로드. malformed 시 exit 2 (fatal, stderr 에 line·col).
2. `_system/systemd/` 의 모든 `*.template` 자동 발견 (glob).
3. template type 분류:
   - `wikihub-mount@.service.template` / `wikihub-vault@.service.template` / `wikihub-vault@.timer.template` — **per-vault instantiated**. enabled vault 마다 1회 render → `wikihub-<type>@<vault_id>.service` 또는 `.timer`.
   - 그 외 (`wikihub-lint.timer.template` · `ops-alert.service` 등) — **singleton**. 1회 render → 동일 stem.
4. **Multi-group substitution** (4 groups — `_current_vault_subs` · `_cross_vault_subs` · `_instance_wide_subs`):
   - **current-vault scalar** (`_current_vault_subs`): `{sync_interval_sec}` — 각 vault 의 현재 instance render 에만 적용. `{credentials_path}` 는 ADR-0035 로 폐기됨.
   - **cross-vault** (`_cross_vault_subs`): `{remote_name_for_<vid>}`, `{remote_path_for_<vid>}`, `{rc_port_for_<vid>}` — `%i → vault_id` 변환 후 lookup. template 에 `{remote_name_for_%i}` 형태로 사용.
   - **instance-wide** (`_instance_wide_subs`): `{wikihub_home}`, `{wikihub_src}`, `{instance_root}`, `{venv_path}`, `{rclone_config_path}`, `{rclone_bin}`, `{vfs_cache_max_size}`, `{lint_interval_hours}`, `{agent_invocation}`, `{skill_prefix}`, `{timeout_start_sec}`, `{agent_invocation_for_<skill>}`.
   - **systemd-native** (`%i`): `{vault_id}`, `{mount_path}` — helper 미산출. template 의 systemd `%i` instantiation 으로 직접 처리. vault_id 는 `WikihubMount@.service` · `WikihubVault@.service` 의 unit instance 식별자로 사용되며, mount_path 는 `--get-mount-path` CLI 로 조회.
   - 모든 key group 이 **disjoint** 여야 함 (`render_systemd_units.py` 가 동일 key 명 중복 시 fatal). 총 4개 그룹의 합집합이 template 접근 가능한 전체 key space.
5. **idempotency**: 기존 output file 이 존재하고 byte-equal 이면 **rewrite skip** (mtime preserve). 다르면 atomic write — `<output>.tmp` 작성 후 `os.rename` (POSIX rename atomic).
6. enabled=false vault 의 직전 render 가 disk 에 있으면 — **`enabled: false` 진입 시 명시 삭제** (file_map 의 desired state 정합). 단 user 데이터인 mount point 디렉토리 자체는 보존.

### exit code

| code | 의미 |
|---|---|
| 0 | success — 1회 이상 file changed 또는 byte-equal 으로 skip 정상 |
| 1 | 의미적 결함 (vault id 미발견, `--get-mount-path` lookup fail, validation fail 등) |
| 2 | 운영 결함 (yaml malformed, template 미존재, write permission deny, disk full) |

### error handling

- yaml malformed → exit 2 + stderr 에 PyYAML 의 `YAMLError` 위치 출력.
- template 미존재 → exit 2 + 어느 template 인지 명시.
- duplicate substitution key (pass 1·2 충돌) → exit 2 + 충돌 key 출력.
- write permission deny / disk full → exit 2 + 어느 output path 인지 명시 + cleanup (`<output>.tmp` 잔존 시 best-effort 삭제).

### `--list-enabled` 동작

`vaults[*]` 중 `enabled: true` 인 vault 의 `id` 만 stdout 에 1줄씩 출력. yaml 부재 또는 vaults empty 시 stdout 비어있음 + exit 0.

### `--get-mount-path` 동작

`vaults[*]` 에서 id 가 매칭되는 첫 entry 의 `options.mount_path` 출력 (path 그대로 — `~` expansion 은 호출자 책임). 미발견 시 exit 1 + stderr 명시.

---

## 7. 미결 사항

| ID | 항목 | Lock 결정 |
|---|---|---|
| O1 | `/wh:setup` 의 update mode 책임 — flag 도입 vs idempotent 자체 | **lock**: flag 없음. install.sh 가 systemd render 직접 책임 (C2). `/wh:setup` 은 skill 메타 + yaml validate 만 |
| O2 | `_enabled_vaults_*` 구현 — bash vs python helper | **lock**: python helper `render_systemd_units.py` 가 `--list-enabled` mode 도 제공. yq dep 없음 |
| O3 | ADR-0030 의 Decision 분할 (1 ADR 1 decision 원칙) | **lock**: 1 ADR 유지 — 4 decision 이 모두 "update workflow safety" 라는 한 관심사. CLAUDE.md §3 의 원칙은 unrelated decisions 분리 강조라 동일 관심사면 OK |

미결 사항 **없음** (Step 2 종료 조건 만족).

backlog 후보 (본 feature 스코프 밖):
- R2-MED-4 tag signature verification (gpg/sigstore) — v0.2.x.
- R1-LOW-4 install.sh 의 plan.md L43 trace 명시 (의도적 책임 분할).

---

## 8. ADR 추출 계획

### ADR-0030 (update workflow orchestration) — 신규 Proposed (Step 3 lock 직전)

- **Status**: Proposed → Step 3 완료 후 Accepted.
- **Context**: ADR-0010 dual-mode lifecycle 의 update path 운영 안전 (race · rollback · unstaged · 동시 호출) 미명시. F4 결함 #C·#D 가 증상.
- **Decision** (4건, 동일 관심사 — update workflow safety 정합):
  1. systemd stop/start sequence (mount 마지막 stop, 첫 start; 15min in-flight grace; reset-failed; FUSE-ready stat wait).
  2. unstaged 작업 abort default + index.lock 보호 + `--force-fresh` 로만 destructive.
  3. trap ERR EXIT 기반 자동 rollback (PRE_UPDATE_REF 캡처 → 실패 시 reset + systemd 재기동).
  4. ref resolution chain (`--version` > BRANCH env > tag `latest` > local cache > main HEAD). BRANCH default empty 로 변경.
- **Consequences**: install.sh 가 dual-mode + systemd render 책임. ADR-0023 의 clean wipe 는 fresh / `--force-fresh` 명시 호출에만 한정.

### ADR-0023 갱신 (Status `Accepted` + Note)

- **Note (2026-05-17)**: update_mode feature 에서 update path 는 ADR-0030 의 fetch + reset 으로 분리. ADR-0023 의 `rm -rf + clone` 은 fresh install 과 `--force-fresh` 명시 호출에만 한정. Status 변경 없음 (의미론 일관, 스코프만 명시).

### ADR-0010 무변경

- conformance 회복이지 supersede 아님. ADR-0010 L84-86 의 release 절차 (`git tag -f latest`) 가 정본 — 본 feature 가 install.sh 측 conformance 만 회복.

---

## 9. Definition of Done

### 9.1 implementation

- [ ] install.sh 가 `_system/VERSION` + `.git` AND detect 분기. partial state explicit error.
- [ ] curl-pipe bootstrap mode-aware — update mode 시 clone 우회.
- [ ] `--version <tag>` flag (tag 부재 fatal). `--version` no-arg → VERSION print.
- [ ] `--force-fresh` flag — `_validate_wipe_target` 통과 후 5초 confirm.
- [ ] BRANCH default empty.
- [ ] update path: lock → mode → unstaged·index.lock guard → systemd stop → fetch + reset → post-condition diff check → VERSION transition 보고 → venv deps diff sync → systemd render → wh:setup skill 메타 (best-effort) → systemd start → verify.
- [ ] ref resolution: --version > BRANCH > tag latest > local cache > main HEAD. banner 에 reasoning 노출.
- [ ] systemd stop sequence: vault@.timer → vault@.service (15min grace) → lint.* → mount@. reset-failed after.
- [ ] systemd start sequence: mount@ → FUSE-ready wait (120s) → vault@.timer → lint.timer.
- [ ] trap ERR EXIT 기반 rollback (PRE_UPDATE_REF).
- [ ] install.sh `flock` lock.
- [ ] log rotation tee 시작 전 + PID suffix.
- [ ] `scripts/_helpers/render_systemd_units.py` 신규 — yaml + template → unit file write + `--list-enabled` mode.
- [ ] `_system/commands/setup.md` 갱신 — render 책임 install.sh 이관, slim spec.
- [ ] `docs/adr/0030-update-workflow-orchestration.md` 신규 Accepted.
- [ ] `docs/adr/0023-…md` Note 추가.
- [ ] `README.md` install snippet + roadmap 갱신.

### 9.2 verification (Step 3 자가 검증, V1~V13)

| ID | 시나리오 | 기대 |
|---|---|---|
| V1 | fresh install → 재호출 동일 ref | update path, no-op exit |
| V2a | dirty tree (modified) → 재호출 | abort + git stash 안내 |
| V2b | `.git/index.lock` 잔존 → 재호출 | abort + 명시 안내 (lock 제거 후 재시도 가능 명시) |
| V3 | `--force-fresh` (interactive) → 5초 confirm → wipe + clean install. Ctrl+C → exit 0 | guard 통과 후 confirm |
| V3a | `WIKIHUB_HOME=/ --force-fresh` | guard fatal exit (confirm 도달 안 함) |
| V4 | vault@.service mid-sync 중 update | 15min in-flight grace, fetch 도중 timer fire 0건 |
| V5a | `--version <older>` (의도 rollback) | warn + 진행 |
| V5b | `_system/VERSION` 위조 후 update (no --version) | fatal exit |
| V6 | install.log > 10MB 호출 | rotation + 새 file. 8번째 prune |
| V7 | requirements.txt 변경된 ref | venv keep, pip install 재실행. 미변경 → skip |
| V8 | tag latest 부재 + ls-remote 정상 → main HEAD fallback. ls-remote fail → local cache | banner 에 명시 |
| V9a | `--version <존재 tag>` → checkout. `--version <부재 tag>` → fatal |  |
| V10 | template fixture commit (e.g. mount@ 의 placeholder 한 줄 추가) → update → active service 의 `systemctl show` 에 반영 | render_systemd_units.py 가 정합 |
| V11 | `uv pip install` 강제 실패 (PyPI 401 또는 invalid requirement) → trap rollback | PRE_UPDATE_REF 복귀 + render 재호출 + systemd 재기동. **rollback 후 active unit content 가 직전 ref render 결과와 byte-equal** (CRIT-N1 검증) |
| V12 | `git reset --hard` 중 disk full (`fallocate` 시뮬) → fatal + 진단 | trap rollback (PRE_UPDATE_REF 미변경 분기) |
| V13 | 동시 두 install.sh 호출 | 둘째 즉시 fatal (lock). curl-pipe + update 호출 시 bootstrap exec 후 새 process 가 fresh lock 잡음 (HIGH-N4 검증) |
| V14 | `render_systemd_units.py` contract — yaml malformed (`--render` exit 2), `--list-enabled` (enabled vault stdout), `--get-mount-path` (미발견 exit 1), idempotent (동일 yaml 재호출 시 byte-equal skip — `stat -c %Y` mtime 보존) | HIGH-N1 contract 정합 |
| V15 | stop sequence 중간 Ctrl+C (SIGINT) | rollback trap 의 SIGINT 분기 진입 + systemd 재기동 자동 (MED-N4 검증) |

### 9.3 review (Step 4)

- [ ] CRIT 0 · HIGH 0.
- [ ] R≥2 멀티모델 (Claude + Gemini/Codex 또는 서브에이전트).
- [ ] backlog.md 의 #A·#B·#C·#D + R16-L2 모두 closed mark.
- [ ] R1·R2 (design review) 의 CRIT 5 + HIGH 9 closure trace (본 v2 내 mapping 표).

---

## v2 closure trace — review finding → 본 문서 반영 위치

| ID | 출처 | 본 v2 위치 |
|---|---|---|
| C1 | R1-CRIT-1 | §3 Step 0 (bootstrap_clone_then_exec mode-aware) |
| C2 | R1-CRIT-2 + R2-CRIT-3 | §3 Step 8 (install.sh 직접 render + best-effort skill 메타) |
| C3 | R2-CRIT-1 | §3 Step 2b (trap + PRE_UPDATE_REF) + §3 `_rollback_if_failed` |
| C4 | R2-CRIT-2 | §3 Step 9 (15min grace + reset-failed + FUSE-ready wait) |
| C5 | R1-HIGH-1 | §4 ref resolution (semver derive 제거, ADR-0010 정본 유지) + §1 invariant |
| H1 | R1-HIGH-2 | §9.2 V10 (template fixture commit 명시) |
| H2 | R1-HIGH-3 | §3 Step 8 의 install.sh 직접 render — unit 존재 precondition 무관 |
| H3 | R1-HIGH-4 | §4 `--version` no-arg → print, with-arg → ref pin |
| H4 | R2-HIGH-1 | §3 `_validate_wipe_target` 추출 + force-fresh 도 호출 |
| H5 | R2-HIGH-2 | §3 Step 2a `.git/index.lock` 명시 abort |
| H6 | R2-HIGH-3 | §4 path 4 local cache fallback |
| H7 | R2-HIGH-4 | §3 Step 12 `_acquire_install_lock` (flock) |
| H8 | R2-HIGH-5 | §3 Step 2d post-condition `git diff --quiet HEAD --` |
| H9 | R2-HIGH-6 | §3 Step -1 (tee 시작 전 rotation + PID suffix) |

MED·LOW 처리:
- R1-MED-1: §4 BRANCH default empty 명시 — 반영.
- R1-MED-2: §7 미결 표 lock 표기 (plan.md U lock + design 단계 O lock 둘 다 reconcile).
- R1-MED-3: §3 Step 8 의 render_systemd_units.py 가 venv 의존 — Step 3 후 호출이라 invariant 정합.
- R1-MED-4: §6 impact 표에 install.sh 행 + setup.md slim 갱신 명시.
- R1-MED-5: §8 ADR-0023 Note 명시 — Step 2 종료 시점 결정 lock.
- R1-LOW-1: §3 Step 2 `IFS= read -r` 로 newline strip.
- R1-LOW-2: §3 Step -1 BSD/GNU stat 양쪽 처리.
- R1-LOW-3: §3 Step 11 banner 가 단일 transition 출력 — Step 2e 의 ok 제거.
- R1-LOW-4: Step 3 진입 시 install.sh trace comment.
- R2-MED-1: §3 Step 9 `_wait_mount_ready` 120s + stat 둘 다.
- R2-MED-2: §3 Step 2e semver_gt + EXPLICIT_VERSION_FLAG.
- R2-MED-3: §3 Step 8 `WIKIHUB_NONINTERACTIVE=1` propagation + 300s timeout.
- R2-MED-4: §4 backlog 후보 명시.
- R2-MED-5: §3 Step 3 `PRE_UPDATE_REF` 사용.
- R2-MED-6: §7 O2 lock (helper script `--list-enabled`).
- R2-MED-7: §3 Step 9 reset-failed.
- R2-LOW-1: §3 Step 2f `export INSTALL_MODE_TARGET_REF`.
- R2-LOW-2: §3 Step 0 NONINTERACTIVE 시 confirm skip.
- R2-LOW-3: §3 Step 2d `git fetch origin --tags` (prune 제거).
- R2-LOW-4: §3 Step 10 linger 검사.

---

## 다음 단계

본 v3 을 사용자에게 승인 요청 → `approved: 2026-05-17` 마커 추가 시 Step 3 진입.

---

## v3 closure trace — R3 finding → 본 문서 반영 위치

| ID | 출처 | 본 v3 위치 |
|---|---|---|
| CRIT-N1 | R3 신규 | §3 `_rollback_if_failed` — git reset 후 `_step8_systemd_render` + `_systemd_start_after_update`. V11 fixture 에 unit byte-equal 검증 |
| CRIT-N2 | R3 신규 | §3 `_systemd_stop_before_update` 끝에 `daemon-reload` 명시 호출 |
| HIGH-N1 | R3 신규 | **§6.1 신설** — `render_systemd_units.py` Contract (CLI · modes · 2-pass substitution · idempotency · exit codes · error handling) |
| HIGH-N2 | R3 신규 | §3 Step 0 `_verify_version_tag_integrity` (warn-only) + main flow 의 단일 wipe (LOW-N1 합치) |
| HIGH-N3 | R3 신규 | §4 `_resolve_ref` 우선순위 1 — 인자 강제 소비. no-arg 분기 제거 |
| HIGH-N4 | R3 신규 | §3 `bootstrap_clone_then_exec` 진입 시 `exec 200>&-` |
| C1 PARTIAL | R3 closure | §3 bootstrap 직후 inline note — "update 의미상 직전 ref install.sh 실행 정합" |
| C3 PARTIAL | R3 closure | CRIT-N1 fix 가 동시 closure |
| H3 PARTIAL | R3 closure | HIGH-N3 fix 가 동시 closure |
| H6 PARTIAL | R3 closure | §4 path 4 banner 명시 "[network offline — using local semver max tag (not 'latest')]" |
| H7 PARTIAL | R3 closure | HIGH-N4 fix 가 동시 closure |
| MED-N1 | R3 신규 | §3 `_enabled_vaults_yaml` — helper + bash fallback (venv 부재 방어) |
| MED-N2 | R3 신규 | §4 path 4 의미 명시 (semver-only, 'latest' stale 비사용) |
| MED-N3 | R3 신규 | §3 `_step3_venv` guard 단순화 + PRE_UPDATE_REF empty assertion |
| MED-N4 | R3 신규 | §3 `_rollback_if_failed` SIGINT 분기 + stop sequence progress output. V15 추가 |
| MED-N5 | R3 신규 | §3 `_wait_mount_ready` — helper `--get-mount-path` 사용, inline python 제거 |
| LOW-N1 | R3 신규 | §3 main flow 단일 wipe — `_step2_clone` 이 wipe 책임 단일화 |
| LOW-N2 | R3 신규 | §3 Step -1 prune 카운트 8 의 의미 주석 |
| LOW-N3 | R3 신규 | §3 `_step2_update` 진입 즉시 trap 등록 + VERSION empty 검증 |
