# install_update_hardening — analysis_and_design.md

## 배경 및 목적

v0.1.8 canary (`a9f971e`) 의 multipass `wikihub-test` 검증 중 `install.sh --version canary` 실행이 **3회 fail** 후 회피로 통과. 3 결함 모두 운영 OCI 첫 update / fresh install 시점에 동일 surface 가능. v0.1.8 release 전에 흡수해서 운영 영향 차단.

## 현행 진단

### 결함 1 — `_system/INSTALLED_VERSIONS.json` `.gitignore` 누락

| 항목 | 현행 |
|---|---|
| 파일 | install.sh 가 install/update 매번 만드는 runtime artifact (Step 4.5) |
| host repo | `.gitignore` 등록 없음. git tracked 도 아님. |
| install.sh L1439 | `git status --porcelain` 가 untracked 의 `??` prefix 도 detect → exit 1 |
| 운영 OCI 첫 update | install.sh 가 자기 자신이 만든 artifact 로 인해 update guard 차단 |

근거: host repo `git ls-files _system/INSTALLED_VERSIONS.json` 비어 있음 + `.gitignore` grep 매치 없음.

### 결함 2 — install.sh self-update anti-pattern

| 항목 | 현행 |
|---|---|
| 위치 | install.sh update flow 내 `git reset --hard refs/tags/<ref>` step (대략 L1450s 근처) |
| bash 동작 | disk 의 install.sh 자체가 reset 으로 갈리지만 bash 는 이미 read 한 array (`WIKIHUB_SKILLS=`) 와 함수 body 를 유지 |
| 결과 | reset 이전 source 의 array (예: 5 skill) vs reset 이후 disk source 의 정합 file (4 skill) → file lookup mismatch → rollback |
| 영향 release | `WIKIHUB_SKILLS=` 또는 다른 module-level array/var 변경 동반 release |

근거: multipass 에서 `2c4b42d` 시점 install.sh = 5 skill, reset 후 `a9f971e` disk = 4 skill. bash 는 5 skill 유지 → `wh-graphify.frontmatter.yaml` lookup fail.

### 결함 3 — `_install_graphify` PATH prepend 책임 누락

| 항목 | 현행 |
|---|---|
| install.sh L578 comment | "venv 의 bin/ 이 PATH 에 우선해야" 명시 |
| 실제 동작 | L413 의 `LOCAL_BIN_DIR` (`~/.local/bin`) 만 prepend. `$VENV_PATH/bin` 은 prepend 안 함. |
| `_install_graphify` L579 | `command -v graphify` check — PATH 미포함 시 fail → exit 2 |
| 영향 OCI | 운영자 shell PATH 에 venv/bin 자연 없음 → fresh install + update 양쪽 fail |

근거: install.sh 본문 grep — `PATH=.*venv` prepend step 부재.

## 개정 범위

| 파일 | 변경 |
|---|---|
| `.gitignore` | `_system/INSTALLED_VERSIONS.json` 1줄 추가 |
| `install.sh` `_install_graphify` 진입 직후 | `export PATH="$VENV_PATH/bin:$PATH"` 1줄 추가 (L568 즈음) |
| `install.sh` update flow `git reset` 직후 | `exec "$0" "$@"` self-restart + 무한 루프 guard 환경변수 (`WIKIHUB_INSTALL_SELF_RESTARTED`) |

총 변경 ~10 줄.

## 개정 전/후 비교

### 결함 1 — `.gitignore`

```diff
 _system/skills/_generated/
+_system/INSTALLED_VERSIONS.json
```

### 결함 2 — install.sh update flow self-restart

Before (L1450s 근처, git reset block 직후 — 정확 line 은 구현 시 확정):

```bash
info "git reset --hard refs/tags/$ref"
(cd "$WIKIHUB_SRC" && git reset --hard "refs/tags/$ref")
# (이후 sparse re-apply + _step3_venv + _install_rclone + _install_graphify ...)
```

After:

```bash
info "git reset --hard refs/tags/$ref"
(cd "$WIKIHUB_SRC" && git reset --hard "refs/tags/$ref")

# self-restart with fresh source (bash mid-read array/function 정합화)
# WIKIHUB_INSTALL_SELF_RESTARTED guard — 한 번만 exec, 무한 루프 차단.
if [[ -z "${WIKIHUB_INSTALL_SELF_RESTARTED:-}" ]]; then
    info "install.sh self-restart with refreshed source (post-reset)"
    export WIKIHUB_INSTALL_SELF_RESTARTED=1
    exec "$WIKIHUB_SRC/install.sh" "$@"
fi
# (이후 sparse re-apply + _step3_venv + _install_rclone + _install_graphify ...)
```

핵심:
- `exec` — 현재 bash process 를 새 install.sh 로 대체. 자식 process 안 만듦. PID 유지.
- `"$@"` — 원래 호출 인자 그대로 (`--skip-confirm --version canary` 등).
- guard env — 새 process 가 같은 line 도달 시 skip → 정확히 한 번만 self-restart.
- guard 가 set 되어 있으면 (= 이미 restart 된 process) 그냥 진행 → idempotent.

### 결함 3 — `_install_graphify` PATH prepend

Before (L562 근처):

```bash
_install_graphify() {
    local pin_spec="${GRAPHIFY_PIN_SPEC:-graphifyy>=0.8.0,<1.0.0}"

    if command -v graphify >/dev/null 2>&1; then
        ...
```

After:

```bash
_install_graphify() {
    local pin_spec="${GRAPHIFY_PIN_SPEC:-graphifyy>=0.8.0,<1.0.0}"

    # venv 의 bin/ 이 install-time PATH 에 우선해야 `command -v graphify` 동작 정합.
    # systemd unit 의 PATH=$VENV_PATH/bin:... 과 일관성.
    export PATH="$VENV_PATH/bin:$PATH"

    if command -v graphify >/dev/null 2>&1; then
        ...
```

핵심:
- `_install_graphify` scope 시작 직후 1회 prepend. install.sh process 전체에 effect (이후 다른 함수에서도 graphify 호출 시 정합).
- shell init (`~/.bashrc` 등) 수정 없음 — install.sh process 한정.

## 연계 룰/스킬 정합성 검토

| 영역 | 검토 |
|---|---|
| `_system/commands/` | 변경 없음. graphify CLI 의 호출 path 는 systemd unit + scripts/wikihub_graphify.sh 가 책임 (별도 PATH set). |
| `scripts/wikihub_graphify.sh` | 변경 없음. systemd unit `Environment=PATH=...venv/bin:...` 가 정합. |
| `.gitignore` | `_system/skills/_generated/` 옆에 추가 — install.sh runtime artifact 카테고리 일관. |
| systemd unit template | 영향 없음. |
| ADR-0030 (update path) | self-restart 추가는 update path 의 일부 — ADR-0030 §부정/제약 의 "rollback 시 governance 파일 미복구" 와 무관 (self-restart 는 git reset 직후 1회). |

## 미결 사항

### 결정 1 — self-restart 정책이 ADR 발의 대상인가?

| 옵션 | 장점 | 단점 |
|---|---|---|
| A — ADR 발의 (예: `ADR-0040 install.sh self-update self-restart`) | 정책 영구 기록. 향후 install.sh 의 다른 self-update 시점에도 정합. | install.sh 한정 detail — 다른 영역 영향 없음. ADR 발의 임계점 초과. |
| **B — ADR 미발의** | 본 fix 의 commit message + analysis_and_design 에서 기록. install.sh 한정 implementation detail. | 향후 install.sh 외 self-update 자료 (예: scripts/* self-update) 등장 시 별도 결정. |

**결정**: **B** (ADR 미발의). 결함 자체가 install.sh 한정 + bash mid-read source 안티패턴 fix — 향후 영향 범위 좁음. commit message 와 본 design doc 에 기록.

### 결정 2 — `_install_graphify` 의 PATH prepend 가 install.sh process 전역에 영향 (이후 함수에서 graphify 호출 시 정합) — 안전한가?

| 점검 | 결과 |
|---|---|
| install.sh 가 PATH 에 의존하는 다른 binary | `rclone`, `yq`, `hermes` — 모두 system PATH (`/usr/local/bin`, `~/.local/bin`) 의존. venv/bin prepend 가 충돌하지 않음 (venv/bin 에 동명 binary 없음). |
| systemd unit 의 PATH | install.sh 가 PATH set 해도 systemd unit 은 자체 `Environment=PATH=...` 으로 isolation. 영향 없음. |
| sub-process 영향 | install.sh 가 spawn 하는 자식 (예: `hermes chat ...`) 의 PATH 도 inherit — venv/bin 우선이지만 wikihub binary 외 영향 거의 없음. |

**결정**: 안전. install.sh process 전역 prepend 진행.

## Definition of Done

- [ ] `.gitignore` 에 `_system/INSTALLED_VERSIONS.json` 추가
- [ ] `install.sh` `_install_graphify` 진입 직후 `export PATH="$VENV_PATH/bin:$PATH"` 추가
- [ ] `install.sh` update flow `git reset --hard refs/tags/$ref` 직후 `exec "$0" "$@"` self-restart + guard 추가
- [ ] multipass `wikihub-test` 에서 fresh re-update — 3 결함 회피 없이 직접 통과 (`PATH=` prepend 회피 + 수동 git reset 회피 + INSTALLED_VERSIONS.json `rm` 회피 모두 불필요)
- [ ] v0.1.8 squash merge + canary force-update
- [ ] features/HISTORY.md 항목 추가 (Step 5 수행 + release 시점에 일괄)

## v1

initial draft — 2026-05-26.

approved: 2026-05-26 (사용자: "지금 수정 진행하자" — Step 1 plan.md 통과 후 즉시 Step 2 진입 의사 명시)
