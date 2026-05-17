# Design Review #3 — update_mode v2 (closure verification + new defect surface)

- **Reviewer**: Claude Sonnet 4.6 (subagent, R3 narrow-scope)
- **Date**: 2026-05-17
- **Target**: features/20260517_update_mode/analysis_and_design.md v2 (closure trace § + new code)
- **Prior reviews**: design_review_1.md (R1 spec), design_review_2.md (R2 SRE)

## Summary

v2 가 R1/R2 의 CRIT 5 + HIGH 9 중 11건은 SOUND 하게 closure 했으나 **3건이 PARTIAL** (C1, H3, H7) — 모두 main flow 의 호출 순서 결함과 fd/lock semantics 관련. 또한 v2 신규 코드에서 **CRIT 2 / HIGH 4 / MED 5 / LOW 3** 의 신규 결함을 발견. 가장 critical 한 신규 결함은 (1) `_detect_mode` 가 curl-pipe bootstrap 직후 빈 `$WIKIHUB_HOME` 상태에서 호출되어 첫 update 호출이 반드시 fresh mode 로 오분기, (2) rollback trap 이 새 ref 의 systemd template render 후 직전 ref 의 unit 으로 복귀 안 됨 (rollback 이 broken state 만 생성).

## Closure Verification

| ID | Original Finding (1-line) | v2 Fix Location | Status |
|---|---|---|---|
| C1 | curl-pipe bypasses update | §3 Step 0 mode-aware bootstrap | **PARTIAL** |
| C2 | hermes detect / F5 gap | §3 Step 8 direct render | **CLOSED** |
| C3 | rollback missing | §3 Step 2b trap | **PARTIAL** (rollback semantics 미완 — 신규 CRIT-N1 참조) |
| C4 | systemd race / grace | §3 Step 9 15min grace | **CLOSED** |
| C5 | ADR-0010 latest semantics | §4 ref priority | **CLOSED** |
| H1 | V10 unverifiable | §9.2 V10 fixture | **CLOSED** |
| H2 | Step 9 precondition | §3 Step 8 direct render | **CLOSED** |
| H3 | --version naming | §4 --version no-arg | **PARTIAL** (parser 모호성 미해소 — 신규 HIGH-N3) |
| H4 | force-fresh guards | §3 _validate_wipe_target | **CLOSED** |
| H5 | index.lock | §3 Step 2a pre-check | **CLOSED** |
| H6 | network fallback | §4 path 4 local cache | **PARTIAL** (local `latest` ref staleness 미명시 — 신규 MED-N2) |
| H7 | concurrent install.sh | §3 _acquire_install_lock | **PARTIAL** (lock 호출 위치가 _detect_mode 보다 뒤 — 신규 HIGH-N4) |
| H8 | partial reset state | §3 Step 2d post-cond | **CLOSED** |
| H9 | log rotation race | §3 Step -1 + PID suffix | **CLOSED** |

### C1 PARTIAL — `_detect_mode` ordering vs curl-pipe

v2 main flow (§3 L463-507) 는 `_acquire_install_lock → _detect_mode → bootstrap_clone_then_exec` 순서다. curl-pipe + fresh 케이스에서 `_detect_mode` 가 호출되는 시점에 `$WIKIHUB_HOME/_system/VERSION` 이 부재해서 `INSTALL_MODE=fresh` 로 정합. **그러나 curl-pipe + update 케이스에서** 도 새 install.sh 스크립트가 `/dev/stdin` 으로 들어와 처음 process 가 시작될 때 `bootstrap_clone_then_exec` 의사코드는 `$WIKIHUB_HOME` 이 이미 존재하므로 (`_system/VERSION + .git` 둘 다) update 분기 → `exec bash "$WIKIHUB_HOME/install.sh" "${ORIGINAL_ARGS[@]}"`. exec 후 새 process 에서 다시 `_detect_mode` 가 호출되고 정합. 의도된 동작은 SOUND 함.

문제는 (1) exec 후의 새 install.sh 가 **disk 의 직전 ref install.sh** 라는 점 — 즉 curl 로 받은 새 install.sh 의 로직 (e.g. 새 unstaged guard, 새 rollback trap) 은 적용 안 됨. 이건 ADR-0010 의 mental model 상 의도된 trade-off ("update 는 정본 동기화") 일 수 있지만 v2 어디에도 명시 안 됨 — 만약 직전 ref install.sh 에 unstaged guard 가 없으면 update path 가 guard 없이 진행. (이는 본 feature 의 첫 update 가 항상 직전 = F4 install.sh 인 점에서 critical.)

### C3 PARTIAL — rollback semantics

`_rollback_if_failed` (§3 L225-237) 가 `git reset --hard $PRE_UPDATE_REF` + `_systemd_start_after_update` 호출. 그러나:
- `_systemd_start_after_update` 가 desired vault 를 `_enabled_vaults_yaml` 로 산출하는데 yaml 자체는 `$WIKIHUB_INSTANCE_ROOT` 에 있어 git reset 영향 외이므로 정합.
- **그러나 systemd unit 파일 자체** (`~/.config/systemd/user/wikihub-*`) 는 `_step8_systemd_render` 가 새 ref 의 template 으로 render 한 상태. rollback 후 systemd 가 본 unit 파일을 그대로 사용 → 새 template content 가 active 한 채 git tree 만 직전 ref. systemd-active spec 과 정본 tree mismatch. (예: 새 template 이 `--vfs-cache-mode full` 인데 직전 git tree 의 코드는 minimal 가정 → mount 거동 불일치).
- 신규 CRIT-N1 참조.

### H3 PARTIAL — `--version` no-arg parser 모호성

v2 §4 L527-531 가 `--version` no-arg → VERSION print, with-arg → ref pin 분기를 명시. 그러나 §3 main flow 의 `_parse_cli` 의사코드 자체는 미정의 (§3 L470 단순 호출). bash 의 표준 인자 파싱 (`case "$1" in --version) ... shift 2 ;;`) 패턴에서 다음 인자를 항상 소비하는데, 어떻게 no-arg 분기를 구현할지 미명시. `install.sh --version --skip-confirm` 같은 호출에서 `--version` 의 다음 토큰 `--skip-confirm` 이 tag 인지 다음 flag 인지 결정 불가. 신규 HIGH-N3 참조.

### H6 PARTIAL — local cache staleness for `latest` tag

v2 §4 path 4 L518: `git for-each-ref --sort=-v:refname 'refs/tags/v*' | head -1`. 이 명시는 **semver `v*` tag 만 fallback** 으로 명확. 그러나 §4 path 3 의 default 는 `refs/tags/latest` (mutable). path 4 가 path 3 의 stale local cache 인지 (e.g. weeks 전 fetch 했던 `latest` 가 local 에 있고 ls-remote fail) 또는 semver fallback 전용인지 모호. v2 가 의도한 건 후자(semver-only) 같지만 path 4 L518 의 banner 명시가 `[network offline — using local cache]` 라서 path 3 의 fallback 으로 오해 가능. 신규 MED-N2 참조.

### H7 PARTIAL — lock acquire 위치

v2 §3 L471 `_acquire_install_lock` 가 `_detect_mode` 보다 먼저. 그러나 `_acquire_install_lock` 의 lock 경로는 `$WIKIHUB_INSTANCE_ROOT/install.lock` 인데 main flow L466 `mkdir -p "$WIKIHUB_INSTANCE_ROOT"` 가 `_acquire_install_lock` 보다 앞에 있어 정합. **그러나 curl-pipe + update mode 에서 `bootstrap_clone_then_exec` 가 `exec bash` 로 새 process 시작 시, 첫 process 는 lock 잡고 exec 직전에 fd 200 닫음 (exec 가 bash 를 self-replace → bash man page: "fd 가 close-on-exec flag 없으면 보존"). bash 가 fd 200 을 close-on-exec 로 표시 안 함 → lock 이 새 process 에 inherit. 새 process 에서 다시 `_acquire_install_lock` 호출 → `exec 200>"$lock"` 이 inherited fd 위에 새로 open → 즉 같은 lock 을 새로 잡는 셈 (이미 first process 가 잡고 있는 같은 fd 를 새로 open 한 새 fd reference 라 lock check 정합). 위험은 약하지만 의도된 동작인지 v2 미명시.** 신규 HIGH-N4 참조.

## New Defects (v2-introduced)

### CRIT-N1: rollback 이 systemd unit 파일 spec mismatch 야기

**Section**: §3 `_rollback_if_failed` (L225-237), `_step8_systemd_render` (L318-325)

**Issue**: rollback 흐름은 다음과 같다.
1. `_step2_update` 성공 → git tree 가 new ref.
2. `_step3_venv` 또는 `_step8_systemd_render` 성공 → `~/.config/systemd/user/wikihub-*` 가 new ref template + new yaml 로 render.
3. `_systemd_start_after_update` 실패 (예: mount@ ready timeout, V12 시나리오).
4. trap fire → `_rollback_if_failed` 호출 → `git reset --hard $PRE_UPDATE_REF` → `_systemd_start_after_update` 재호출.

문제: step 4 의 `_systemd_start_after_update` 는 **여전히 new template render 된 unit 파일** 로 start 시도. systemd `daemon-reload` 가 호출 안 됐어도 systemd 가 기존 unit 캐시를 사용한다 — new template 의 content 가 그대로 active. 운영 invariant ("직전 ref + 직전 systemd spec 로 자동 복귀", §1 invariant 4) 위배.

**Evidence**:
- §3 L235 `_systemd_start_after_update || warn "rollback systemd 재기동 실패 — 수동 복구"` — 시작만 시도, **re-render 없음**.
- `_step8_systemd_render` 는 idempotent (byte-equal mtime preserve) 라 했지만 idempotency 는 yaml + template 동일 가정. rollback 시점에 git tree 는 직전 ref 인데 unit 파일은 new ref render 상태 — re-render 호출 안 하면 stale.
- §1 invariant 4 "Step 2~Step 10 어디서 실패해도 직전 ref + **직전 systemd spec** 로 자동 복귀" — 자체 spec 과 의사코드 mismatch.

**Suggested fix**:
- `_rollback_if_failed` 가 `git reset --hard` 직후 **`_step8_systemd_render` 재호출** (직전 ref 의 template 으로 다시 render) + `daemon-reload` + `_systemd_start_after_update`.
- 추가로 `_step8_systemd_render` 실행 직전에 unit 파일 snapshot (cp ~/.config/systemd/user/wikihub-*.service → /tmp/wikihub-rollback-units/) 보관 — render 자체가 disk full 등 fail 한 후 rollback 시도 시 fallback.
- V11/V12 fixture 에 "rollback 후 systemd show 가 직전 spec 과 byte-equal" verification 추가.

### CRIT-N2: `_step8_systemd_render` 의 `daemon-reload` 가 idempotent 보장 깨질 때 race window

**Section**: §3 L323-324, §3 L341 "byte-equal 시 mtime preserve → daemon-reload 도 no-op"

**Issue**: v2 는 `_step8_systemd_render` 가 idempotent 라고 약속 — 모든 unit 파일이 byte-equal 이면 mtime 보존 → daemon-reload no-op. 그러나 의사코드 L323-324 는 **render 후 무조건 `systemctl --user daemon-reload`** 호출. daemon-reload 자체는 byte-equal 여부에 무관하게 호출됨 → idempotent 약속이 깨지진 않지만, daemon-reload 가 항상 호출되면서 동시에 `_systemd_stop_before_update` 에서 stop 후 reset-failed 한 후 daemon-reload 가 안 일어남 (stop 은 Step 2c, daemon-reload 는 Step 8 — 사이에 git reset + venv install).

window 분석:
- Step 2c stop sequence 완료 → unit 파일은 직전 ref content 그대로 (active state 만 stopped).
- Step 2d git reset → `_system/systemd/*.template` 자체는 직전 → new 로 변경. 그러나 `~/.config/systemd/user/wikihub-*` 은 아직 직전 render 상태.
- Step 3 venv install (수분).
- Step 8 render → new template 으로 unit 파일 write + daemon-reload.

**문제**: Step 2c 와 Step 8 사이 (수분~수십분 동안) systemd 의 unit 캐시는 직전 render content 를 가리킨다. **이 window 동안 `systemctl --user list-units` 가 호출되거나 timer 가 (다른 wikihub unrelated) fire 되면 systemd 가 캐시된 unit 으로 동작**. 일반 운영에선 vault@.timer 가 stop 됐으므로 race 없지만, **외부 (예: 운영자 ssh 로 `systemctl --user start wikihub-mount@gdrive.service` 수동 호출)** 시 직전 unit 내용으로 start. 이건 SRE incident 시나리오 — 위험 낮으나 namespace.

**Evidence**:
- §3 L323-324 — daemon-reload 가 render 끝에 호출, Step 2c stop 직후 호출 안 됨.
- §3 L368-371 `reset-failed` 가 stop 후 호출되지만 daemon-reload 는 없음.

**Suggested fix**:
- Step 2c stop sequence 종료 직전에도 `systemctl --user daemon-reload` 1회 (정합성은 안 영향 — stop 후 reload 는 안전). 또는 명시적으로 "Step 2c 와 Step 8 사이 운영자 수동 systemctl 호출 금지" 를 §3 invariant 로 명시.
- DoD 에 "Step 2c stop 후 unit 파일 변경 없음 (직전 render) — Step 8 render 가 차이를 만든 후 daemon-reload" 명시.

### HIGH-N1: `render_systemd_units.py` 의 spec 이 Step 3 구현 불가능할 정도로 모호

**Section**: §3 L318-325, §3 L341, §3 L409, §6 L572

**Issue**: v2 가 `scripts/_helpers/render_systemd_units.py` 신규 helper 를 **신설**하면서도 의사코드 + 인자 + 동작이 한 줄 wrapper (§3 L322-323) + 한 문장 description (§3 L341) + L409 의 `--list-enabled` mode 언급만으로 명세화. Step 3 구현 진입 시 다음이 미정의:
- **yaml read path**: `--yaml` 인자가 매번 명시 vs default `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml`?
- **template read path**: `_system/systemd/*.template` glob 자동 detect vs 명시? mount@/vault@.service.template 외 신규 template (lint.service.template 등) 자동 발견?
- **output path**: `--out` 가 directory (`~/.config/systemd/user/`) 가정. 그 안에 어떤 filename pattern 으로 write (wikihub-mount@<vid>.service, vs wikihub-mount@.service)?
- **idempotency**: v2 가 "byte-equal 시 mtime preserve" 약속 — 비교 단위는 file 단위? content 단위? mtime preserve 가 atomic 인지 (write to .tmp + rename, 또는 read-compare-no-write)?
- **error handling**: yaml malformed → exit 1? exit 2? template missing → fatal vs skip? write permission deny → fatal vs warn?
- **`--list-enabled` 모드 contract**: stdout 으로 vault id 1줄당 1개 print? exit code 정책? `enabled: false` vault 의 처리 (제외)?
- **2-pass substitution** (setup.md L72-81): mount@/vault@ template 의 `%i` 전치환 + `{rc_port_for_<vault_id>}` 같은 per-vault key — v2 가 이 spec 을 helper 가 흡수한다고 가정하나 명시 없음.

Step 3 구현자가 위 모두를 재유추해야 함 → §3 step 3 진입 직전 lock 필요.

**Evidence**:
- §3 L322-323 — wrapper 만.
- setup.md L46-86 (특히 L72-81) — 직전 책임자였던 /wh:setup 이 가지고 있던 2-pass substitution spec 이 helper 로 이관되어야 하는데 v2 어디에도 언급 없음.

**Suggested fix**:
- §3 §6 에 `render_systemd_units.py` 의 contract 별도 sub-section 추가. 최소: 인자 list (`--yaml <path>`, `--out <dir>`, `--list-enabled`), exit code 표, idempotency 알고리즘 (read existing → byte-compare → skip-write if equal → atomic write else), 2-pass substitution 책임 명시.
- 또는 helper 의 contract 를 ADR-0030 의 Decision 5번째로 추출 (정본화).

### HIGH-N2: `_detect_mode` 가 첫 fresh install 직후 curl-pipe 재호출 시 race

**Section**: §3 Step 0 (L117-134), main flow L472-475

**Issue**: 시나리오 — 운영자가 dev 환경에서 wikihub 디렉토리를 일부 파일만 가지고 있다 (예: 직전 `rm -rf $WIKIHUB_HOME` 가 disk full 로 partial fail → `.git/` 은 지워졌으나 `_system/VERSION` 만 남음). `_detect_mode` 의 partial state branch (§3 L120-124) 가 fatal exit 명시 — 정합.

문제는 다음 케이스: 운영자가 의도적으로 dev 환경에서 `$WIKIHUB_HOME` 에 fresh clone 후 `_system/VERSION` 파일을 수정해 보내려 한 상태. `_detect_mode` 가 update mode 로 판단 → `bootstrap_clone_then_exec` 가 curl-pipe 시 `exec bash "$WIKIHUB_HOME/install.sh"` 호출 → 새 install.sh 가 다시 `_detect_mode` → still update mode → `_step2_update` → unstaged guard 통과 (clean tree) → fetch + reset. **운영자의 _system/VERSION 위조가 silent 통과**. R2-MED-2 의 "VERSION 위조 후 update" 시나리오를 §3 Step 2e 의 semver_gt 분기로 처리하지만, **위조가 downgrade 가 아닌 동일 version 이면 검출 안 됨**.

추가로 fresh path L484 가 `_validate_wipe_target` + `[[ -e "$WIKIHUB_HOME" ]] && rm -rf "$WIKIHUB_HOME"` 인데 `_step2_clone` 자체도 (기존 코드) `_step2_clone` 내부에 동일 wipe 가 있다 — **double wipe 시도** (의도된 노이즈, 큰 위험은 아니지만 v2 가 의도적으로 _step2_clone 의 wipe 를 외부로 추출했는지 안에 남겼는지 § 어디에도 명시 안 됨). install.sh:222 의 기존 `rm -rf` 가 그대로 유지된다고 가정하면 fresh path L484 의 `rm -rf` 가 redundant.

**Evidence**:
- §3 L283: `_step2_clone` 의 기존 wipe (install.sh:222) 미변경 가정.
- §3 L484: main flow 의 `[[ -e ... ]] && rm -rf` 가 추가 호출.

**Suggested fix**:
- `_step2_clone` 의 함수 정의 자체에서 wipe 책임을 제거, main flow 에서만 wipe → `_step2_clone` 은 clone-only.
- VERSION 위조 시나리오 검출: `_system/VERSION` 의 값 + tag name 정합 확인 — `git describe --tags --exact-match HEAD` 와 비교 (mismatch → warn).

### HIGH-N3: `--version` no-arg vs with-arg parser 구현 모호

**Section**: §4 L527-531, §3 L470 `_parse_cli`

**Issue**: H3 PARTIAL closure 의 상세. v2 §4 L527-531 의 약속:
- `install.sh --version` → VERSION print
- `install.sh --version <tag>` → ref pin

bash 표준 case-based 파싱:
```bash
case "$1" in
    --version)
        if [[ -z "${2:-}" || "${2:0:2}" == "--" ]]; then
            cat _system/VERSION; exit 0
        else
            EXPLICIT_VERSION="$2"; shift 2
        fi
        ;;
```

이 패턴이 의도. 그러나 `install.sh --version --skip-confirm` 호출 시 `--skip-confirm` 이 tag 인지 다음 flag 인지 → 위 코드는 next-flag 로 처리 → no-arg branch. 정합. **그러나 운영자가 의도적으로 tag name 이 `--` 로 시작하는 (e.g. `--rollback-test`) tag 를 만들 가능성** — 거의 0 이지만 v2 미명시. 더 critical: `install.sh --version v0.1.0 --skip-confirm` 의 인자 순서가 swap 되면 (`install.sh --skip-confirm --version`) → bash 파서가 v0.1.0 을 못 봄 → no-arg branch → print + exit 0. **운영자의 의도 (update + skip-confirm) 가 silent print-and-exit 으로 변형**. confusion 위험.

**Evidence**:
- §4 L527-531 — 분기 spec 만, 파서 구현 미명시.
- §3 L470 `_parse_cli` — 의사코드 미정의.

**Suggested fix**:
- `--version` 의 의미를 자체적으로 다음 인자 강제 소비로 변경: no-arg → fatal. version 출력은 별도 flag (`-V` 또는 `--show-version`).
- 또는 ADR-0010 의 `--version v0.1.0` 형식만 유지 + no-arg 는 새 분기 안 만듦. README 에 `cat ~/wikihub/_system/VERSION` 으로 안내.

### HIGH-N4: `_acquire_install_lock` 의 fd inheritance + curl-pipe self-replace 흐름

**Section**: §3 Step 12 L450-459, main flow L471

**Issue**: H7 PARTIAL closure 의 상세. v2 가 main flow 에서 `_acquire_install_lock` 을 `_detect_mode` 보다 먼저, `bootstrap_clone_then_exec` 보다도 먼저 (L471) 호출. update mode + curl-pipe 의 흐름:

1. 첫 process (curl-pipe) → `_acquire_install_lock` → fd 200 open, flock 잡힘.
2. `_detect_mode` → update.
3. `bootstrap_clone_then_exec` → update branch → `exec bash "$WIKIHUB_HOME/install.sh"`.
4. exec 가 process image replace — bash 의 default 로 fd 200 은 close-on-exec flag 없음 → 새 process 에 inherit. **그러나 새 install.sh 의 main 이 다시 `_acquire_install_lock` 호출 → `exec 200>"$lock"` 가 fd 200 을 다시 open** (이미 open 된 fd 를 새로 open 하면 기존 fd 가 close 되고 새 fd 가 그 자리 할당; bash 의 `exec NN>file` semantic). 새 file descriptor 는 새로 open 한 file 의 reference. `flock -n 200` 호출 시 **새 fd 가 기존 lock 을 모르고 새 lock 잡으려 시도**. flock 은 file 단위 advisory lock — 같은 inode 에 대해 동일 process 가 두 번 lock 요청 시 보통 success (재진입 가능 lock; Linux flock(2) man "Locks created by flock() are associated with an open file description"). 

즉 새 process 가 새 fd 로 open → 새 OFD (open file description) → 다른 OFD → flock 재요청 → block 또는 다른 process 인식. Linux flock 의 정확한 semantic: 같은 process 가 다른 fd 로 open 후 flock 시도 → 이건 다른 OFD 라 lock contention 가능 (man flock(2): "If a process uses open(2) (or similar) to obtain more than one file descriptor for the same file, these file descriptors are treated independently by flock()"). **즉 새 install.sh 가 flock -n 200 호출 시 fail 가능** — 첫 process (이미 exec 로 사라진) 의 lock 이 fd 200 inherit 로 살아있을 수 있어 race.

v2 의사코드 L457 `# process exit 시 fd 200 자동 close → lock release` 가 exec semantic 을 가정 안 함. exec 는 process exit 가 아닌 image replace — fd 가 새 process 로 inherit. close 안 됨.

**Evidence**:
- §3 L450-459 — flock 구현.
- main flow L471 — lock 이 bootstrap 보다 먼저.
- bash man (exec): inherited fds 명시.

**Suggested fix**:
- 옵션 A: `bootstrap_clone_then_exec` 진입 시 `exec 200>&-` 로 fd 명시 close 후 `exec bash`. 새 process 가 fresh lock 잡음.
- 옵션 B: `_acquire_install_lock` 을 `bootstrap_clone_then_exec` 이후로 옮김 — main flow L471 을 L477 (env_check 이후) 로 이동. 단 두 동시 curl-pipe 호출이 bootstrap (clone) 단계에서 race 가능 (CRIT-1 의 sub-case). bootstrap 단계는 clone 만 하므로 race window 가 짧지만 git index.lock 충돌 가능.
- 옵션 C: lock 파일 fd inheritance 회피 — `flock` 의 `-o` flag (lock 후 fd 즉시 close) 또는 `flock` 명령 wrapping (`flock -n /path/to/lock bash -c '...'`) 으로 lock lifecycle 을 별도 wrapper subshell 로 한정.

권장: 옵션 A — 명시적이고 race window 도 최소화.

### MED-N1: `_systemd_start_after_update` 의 `desired_vaults` 가 venv 부재 시 silent fail

**Section**: §3 L375-378, `_enabled_vaults_yaml` (정의는 미명시 — §3 L409 만 언급)

**Issue**: `_systemd_start_after_update` 의 첫 줄 `desired_vaults="$(_enabled_vaults_yaml)"`. `_enabled_vaults_yaml` 정의는 v2 어디에도 안 보이고 §3 L409 가 "`render_systemd_units.py` 가 `--list-enabled` mode 도 제공" 으로 helper 책임 위임. helper 는 venv python 의존. **rollback 흐름에서 `_step3_venv` 가 실패해서 trap 으로 진입한 경우 venv 가 partial 상태** — `_enabled_vaults_yaml` 가 silent fail or empty string return. 그 경우 `_systemd_start_after_update` 의 `for v in $desired_vaults` 가 empty loop → start 안 됨 → rollback 이 "systemd 재기동 실패" warn 만 띄우고 끝남.

운영자 mental: rollback 성공 메시지 보고 안심 → 실제로는 vault@ timer 도 mount@ 도 모두 stopped 상태.

**Evidence**:
- §3 L375-378 — helper 호출, fallback 없음.
- §3 L235 — rollback 중 `_systemd_start_after_update` warn-only.

**Suggested fix**:
- `_enabled_vaults_yaml` 에 bash fallback (e.g. `grep -E '^\s*-\s*id:' $WIKIHUB_INSTANCE_ROOT/wikihub.yaml | awk ...`). venv 부재 시 fallback 사용.
- 또는 `_systemd_start_after_update` 가 empty desired_vaults 시 warn → 명시적 fatal 또는 운영자 안내.

### MED-N2: `_resolve_ref` path 4 의 `latest` ref staleness

**Section**: §4 L518 (path 4 local cache fallback)

**Issue**: H6 PARTIAL closure 의 상세. path 4 는 "git ls-remote fail 시 local cache: `git for-each-ref --sort=-v:refname 'refs/tags/v*' | head -1`". `v*` glob 만 매치 — `refs/tags/latest` 는 매치 안 됨. 즉 path 3 (tag `latest`) 가 network fail 로 unreachable 인 경우, **path 4 는 `latest` 의 stale local cache 가 아니라 semver tag 의 local cache 로 fallback**.

운영 시나리오: 운영자가 직전 `git fetch origin --tags` 로 local `refs/tags/latest` 를 받음 (e.g. commit abc123 가리킴). 다음 update 시점에 network 불가 → ls-remote fail → path 4 진입. v2 의도가 다음 중 어느 것?
- (A) 직전 fetch 의 `latest` 를 신뢰해서 abc123 사용 (대부분 운영자 mental model).
- (B) `latest` 의 의미는 mutable이라 network 없이는 신뢰 불가, 따라서 semver tag (e.g. v0.1.0) 로 안전 fallback.

v2 path 4 는 (B) 선택. 그러나 banner L518 "[network offline — using local cache]" 가 (A) 로 오해 가능. 더 critical: v0.1.0 spec 완성 직후에는 local 에 semver tag 가 1개 (v0.1.0) — 이는 path 3 의 `latest` 와 의미 동등 (latest = v0.1.0). 그러나 v0.1.1 release 후 운영자가 fetch 없이 update 호출하면 path 3 의 `latest` (캐시 = v0.1.0) vs path 4 의 semver 최신 (= v0.1.0) 일치. v0.1.2 도착 후 메인테이너가 local 에 fetch — local cache 에 v0.1.0, v0.1.1, v0.1.2 + latest=v0.1.2. 이제 network down → path 4 → v0.1.2 (semver 최신). 그러나 `latest` 의 의미가 "stable release pointer" 라면 메인테이너가 v0.1.2 를 stable 로 promote 했다는 보장 없음 (latest 가 아직 v0.1.1 가리킬 수 있음).

**Evidence**:
- §4 L517-518 — path 3 vs path 4 의미 차이 미명시.
- §1 invariant — "이동 태그" 강조.

**Suggested fix**:
- path 3 와 path 4 의 의미 차이를 §4 에 명시: "path 4 는 network 부재 시 가장 안전한 stable release (semver max) 사용. mutable `latest` 의 stale cache 는 비사용. 운영자가 latest 의 직전 값을 원하면 `--version <tag>` 명시."
- banner 문구를 "[network offline — using local semver max tag]" 로 명확화.

### MED-N3: `_step3_venv` 의 diff 판정이 PRE_UPDATE_REF 없을 때 처리 누락

**Section**: §3 L283-294

**Issue**: `_step3_venv` 의 update mode 분기 (L286-291) 는 `PRE_UPDATE_REF` 가 set 됐을 때 diff 비교. **fresh path** 에선 PRE_UPDATE_REF 자체가 없음 → `[[ "$INSTALL_MODE" == "update" && -n "${PRE_UPDATE_REF:-}" ]]` 조건 false → 분기 안 들어감 → `uv pip install` 무조건 실행. 정합.

문제는 update mode + first update 케이스 — `PRE_UPDATE_REF` 는 `_step2_update` 진입 시 항상 capture (§3 L184). 즉 update mode 면 PRE_UPDATE_REF 부재 시나리오 없음. 그럼 `&& -n "${PRE_UPDATE_REF:-}"` guard 자체가 redundant. 더 우려스러운 건 **rollback trap 도중에 _step3_venv 가 다시 호출되는 경우는 없지만, 만약 운영자가 의도적으로 `_step3_venv` 를 단독 호출** (개발 디버깅) → PRE_UPDATE_REF 없음 → silent fallback 으로 force install. v2 의도된 안전망인지 명시 안 됨.

**Evidence**:
- §3 L286-291 — guard.
- §3 L184 — capture 시점.

**Suggested fix**:
- guard 단순화: `if [[ "$INSTALL_MODE" == "update" ]]; then` 만. PRE_UPDATE_REF empty 면 fatal (assertion).

### MED-N4: 15min stop grace 중 Ctrl+C 처리

**Section**: §3 L360 `timeout 900 systemctl --user stop ...`

**Issue**: `timeout 900` 명령은 grace 가 15분 길어서 운영자가 hung 으로 오인하고 Ctrl+C 가능. SIGINT 가 install.sh main process 로 전달 → `trap '_rollback_if_failed' ERR EXIT` 가 EXIT 에서 fire. 그러나 이 시점에 `PRE_UPDATE_REF` capture 후 git reset 도 안 함 — `_rollback_if_failed` 의 `current_ref == PRE_UPDATE_REF` check (§3 L232) 가 true → return 0. silent exit.

운영자는 Ctrl+C 후 "어디까지 진행됐는지" 모름. 특히 stop sequence 중간이면 일부 vault@/timer 가 stopped 상태로 남음. install.sh 가 silent exit 하면 다음 timer fire 까지 sync 정지.

**Evidence**:
- §3 L360 — timeout 900.
- §3 L228-232 — rollback 의 early return.

**Suggested fix**:
- `_rollback_if_failed` 가 SIGINT (exit code 130) 명시 분기: stop sequence 중간 abort 시 명시적 안내 + `systemctl --user start wikihub-mount@*.service wikihub-vault@*.timer` 자동 복구 (직전 state 유지가 목적).
- timeout 900 은 너무 길다 — 메시지 1분 단위로 progress 출력 (`info "  vault@${v} stop 진행 중 (Nm 경과 / max 15m)"`) → 운영자 visual 안심.

### MED-N5: `_wait_mount_ready` 의 yaml read 가 helper 미사용 + Python inline

**Section**: §3 L392-406

**Issue**: `_wait_mount_ready` 가 yaml 의 mount_path 를 inline Python (L394-396) 으로 read. v2 §7 O2 가 "`render_systemd_units.py` 가 `--list-enabled` mode 도 제공" 으로 helper 단일화 약속했는데 `_wait_mount_ready` 는 별도 inline — helper 단일화 spec 깨짐. 또 inline python 의 `y['vaults']` access 는 yaml 형식 정합 가정 — yaml malformed 시 silent KeyError → bash subshell capture 부재.

**Evidence**:
- §3 L394-396 — inline python.
- §7 O2 — helper 단일화 약속.

**Suggested fix**:
- `render_systemd_units.py --get-mount-path <vault_id>` mode 추가 또는 `_yaml_get_vault_field` 같은 generic helper. inline python 제거.

### LOW-N1: fresh path 의 `_validate_wipe_target` 중복 호출

**Section**: §3 main flow L483 + `_step2_clone` 함수 내부

**Issue**: fresh path 에서 main flow L483 가 `_validate_wipe_target` 호출, 그 후 L484 `[[ -e "$WIKIHUB_HOME" ]] && rm -rf "$WIKIHUB_HOME"` 가 wipe, L485 `_step2_clone` 호출. **그런데 v2 §3 L276 가 "`_step2_clone` 진입 시 `_validate_wipe_target` 호출 후 `rm -rf` (기존 동작)"** 라고 명시 → 즉 `_step2_clone` 안에서도 다시 validate + rm. **이중 wipe 시도** (이미 main flow 가 rm 했으므로 두 번째 rm 은 no-op, 정합) + **이중 validate** (성능 미세, 정합).

이건 minor 정합 결함이지만 v2 가 추출/inline 의 어느 방향으로 가는지 결정 미흡.

**Suggested fix**:
- `_step2_clone` 의 함수 body 에서 `_validate_wipe_target` + `rm -rf` 제거 — main flow 의 책임으로 단일화. 또는 main flow 의 L483-484 제거 — `_step2_clone` 의 책임으로 단일화.

### LOW-N2: `_rotate_install_log` 의 prune 카운트 8

**Section**: §3 L105 `tail -n +8`

**Issue**: rotation 후 prune 시 `ls -1t ... | tail -n +8 | xargs -r rm` — 7개 보관 (8번째부터 prune) 정합. 단 8 의 magic number 가 §3 어디에도 명시 안 됨. plan.md U5 "7개 보관" 과 정합하지만 design 본문에서는 sentinel 없음.

**Suggested fix**:
- §3 Step -1 도입부에 "7개 보관 — `tail -n +8` 의 8 = 보관수+1" 주석.

### LOW-N3: `IFS= read -r ... < file` 의 empty file 처리

**Section**: §3 L165, L207

**Issue**: `IFS= read -r current_version < "$WIKIHUB_HOME/_system/VERSION"` — 정합한 trailing newline strip pattern. **그러나 VERSION 파일이 empty (0 bytes)** 인 경우 read 가 exit 1 → set -e 로 install.sh 즉시 종료. trap fire → rollback 시도. 그러나 PRE_UPDATE_REF capture (L184) 보다 current_version read (L165) 가 앞 → trap 등록 전 → silent exit.

운영자 mental: "그냥 죽음".

**Evidence**:
- §3 L165 — read 위치.
- §3 L184 — trap 등록.

**Suggested fix**:
- read 후 검증: `[[ -n "$current_version" ]] || { err "VERSION empty — 파일 손상 의심"; exit 1; }`.
- 또는 trap 등록을 _step2_update 첫줄로 이동.

## Verdict

**fix CRIT/HIGH before lock**. CRIT-N1 (rollback systemd unit mismatch) 가 §1 invariant 4 (자동 rollback) 의 의미 자체를 깨므로 ADR-0030 Decision 3 의 정합도 깨짐 — lock 전 반드시 해소. CRIT-N2 (race window) 는 운영 안전 우려가 약간 약하지만 §1 invariant 2 의 race 차단 정신과 충돌. HIGH-N1 (helper spec) 은 Step 3 구현 진입 자체를 막음. HIGH-N2~N4 는 silent failure modes — 운영 incident 의 source.

C1 / C3 / H3 / H6 / H7 의 PARTIAL closure 도 v3 round 에서 명시적으로 해소되어야 함. MED·LOW 는 v3 내 in-line fix 가능.

**전체 verdict**: v2 가 v1 대비 큰 진전 (특히 hermes 독립 + ref resolution + 15min grace + trap rollback 등 구조 정합) 이지만, **rollback 의사코드의 핵심 결함 (CRIT-N1) + helper spec 모호성 (HIGH-N1) + lock fd inheritance (HIGH-N4)** 가 모두 lock 전 v3 fix 필요. v3 round 에서 CRIT-N1·HIGH-N1·HIGH-N4 + PARTIAL 5건 closure 후 Step 3 진입.

## Notes

- v2 의 ADR-0010 conformance 회복 결정 (semver derive 제거, mutable `latest` 정본 유지) 은 SOUND. 메인테이너 release 절차 (ADR-0010 L84-86) 와 정합. README + 운영자 안내 갱신 필요.
- §7 O3 lock ("1 ADR 4 decisions") 는 CLAUDE.md §3 Step 2 ADR 추출 원칙 ("결정 = 1 ADR") 과의 정합이 약간 약하지만 v2 §7 의 해석 ("동일 관심사") 합리적. 단 ADR-0030 의 Decision 4건 중 "ref resolution chain" (Decision 4) 은 §1 invariant 와 약간 결이 다른 영역 (resolution policy vs safety) — 분할 검토 권장 (ADR-0030 → update workflow safety + ADR-0031 → ref resolution policy).
- v2 V1~V13 verification 이 happy path + failure injection (V11~V13) 모두 cover. 단 V11 의 "uv pip install 강제 실패" 가 CRIT-N1 의 rollback systemd unit mismatch 시나리오를 검증 — V11 fixture spec 에 "rollback 후 active unit content 가 직전 ref 와 byte-equal" 검증 항목 추가 권장.
- `_step8_wh_setup_skill_meta` 의 timeout 300 + best-effort 패턴 (§3 L335-338) — F5 미완 fallback 으로 CLOSED. 단 systemd render 가 install.sh 책임으로 이관되면서 `/wh:setup` 의 shrink 가 setup.md 갱신 (Step 3) 단계에서 quantitative spec 필요 — §6 표의 "slim 갱신" 표기로 부족, 어떤 책임이 제거되는지 명시 (Step 2 의 systemd unit substitution 본체 — setup.md L46-86 — 가 helper 로 이관됨).
