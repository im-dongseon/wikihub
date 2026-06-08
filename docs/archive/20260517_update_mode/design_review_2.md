# Design Review #2 — update_mode (SRE operational safety)

- **Reviewer**: Claude Sonnet 4.6 (subagent, SRE angle)
- **Date**: 2026-05-17
- **Target**: features/20260517_update_mode/analysis_and_design.md v1

## Summary

CRIT 3 / HIGH 6 / MED 7 / LOW 4. 가장 큰 결함은 (a) update path 의 **rollback 메커니즘 부재** — design §3 와 §8 가 "자동 rollback" 을 약속하지만 `_step2_update` 의사코드에 trap/try 가 없고 reset 이후 systemd-start 실패 시 broken 상태로 종료, (b) systemd stop/start 가 mount@.service 의 `Restart=always` 와 race 가능 — `systemctl stop` 만으로 정합 보장 안 됨, (c) `_step8_wh_setup` 이 `command -v hermes` 로 binary 탐지하면서 정작 systemd unit 은 yaml `agent.binary` 절대경로 ({agent_invocation}) 를 substitution — F5 미완 상태에서도 detect 분기가 엇갈리고 `--reorchestrate` flag spec 도 setup.md 에 부재.

## Findings

### CRIT-1: update path 실패 시 rollback 메커니즘 미정의 — broken 상태 silent 종료
**File/section**: analysis_and_design.md §3 Step 2d / §8 ADR-0030 Decision / §9.1 DoD
**Issue**: §8 ADR-0030 Decision 3행은 "Step 6 (fetch + reset) 실패 시 자동 rollback (직전 ref reset + systemd 재기동)" 을 명시하지만 §3 `_step2_update()` 의사코드 어디에도 `trap`/`try` 없음. 다음 흐름이 모두 silent broken 상태로 끝남:

1. `_step2_update` 가 `git reset --hard $target_ref` 성공 후 종료.
2. `_step3_venv` 의 `uv pip install -r requirements.txt` 실패 (e.g. PyPI 504, disk full, requirements 호환성 결함) → 새 deps 부분 설치된 venv. 운영자 대응: 직전 ref 로 복귀해서 호환 deps 사용 — 그러나 working tree 는 이미 new ref. `--force-fresh` 외 복구 명령 없음.
3. `_systemd_start_after_update` 실패 (e.g. `wikihub-mount@<vid>.service` 의 ExecStart 가 새 template 의 syntax error 로 즉시 fail) → install.sh 가 exit 2. 운영자는 다음 vault@ timer fire 전까지 sync 정지 + 새 template 적용 안 됨을 모름.
4. `_step10_verify` 가 60s timeout 으로 fail → 동일.

**Evidence**:
- `_step2_update` (analysis_and_design.md L98-135) — `bash -e` 의 자연 exit 만 의존, 직전 ref 보존 안 함.
- §9.1 의 DoD checklist 에 "auto rollback" 항목 부재 — V1~V10 verification 어디에도 rollback 시나리오 없음.
- 현행 F4 install.sh (L687-) `main()` 도 `set -euo pipefail` 만, trap EXIT 부재.

**Suggested fix**:
- `_step2_update` 진입 시점에 `PRE_UPDATE_REF="$(git -C "$WIKIHUB_HOME" rev-parse HEAD)"` 캡처.
- `trap '_rollback_if_failed' ERR EXIT` 등록. `_rollback_if_failed()` 는 (a) exit code 비-0 + (b) 현재 ref ≠ `PRE_UPDATE_REF` 인 경우만 `git reset --hard "$PRE_UPDATE_REF"` + `_systemd_start_after_update` (직전 spec 로) 호출.
- DoD V11 추가: "uv pip install 실패 시 직전 ref 복귀 + systemd 직전 spec 로 재기동."
- design §3 Step 2d 의사코드에 `PRE_UPDATE_REF` 캡처 1줄과 trap 등록 1줄을 명시. 빠지면 ADR-0030 §Decision 3행이 implementation gap.

---

### CRIT-2: systemd mount@ stop 이 `Restart=always` 와 race — stop sequence 부정합
**File/section**: analysis_and_design.md §3 Step 9 `_systemd_start_after_update` (역방향 stop 도 동일)
**Issue**: `wikihub-mount@.service.template` L25-26 은 `Restart=always` + `RestartSec=10s`. systemd 의 `systemctl stop` 은 unit 을 "inactive" 로 만들고 `Restart=` 가 더 이상 자동 fire 안 하지만, **stop 명령 직전에 ExecStart 가 이미 crash 했고 RestartSec=10s wait 중이라면 stop 이 wait state 를 cancel** — 다음 `start` 가 fresh 한 ExecStart 를 실행. 이는 정상.

문제는 다음: design §3 Step 2c 가 호출하는 `_systemd_stop_before_update` (의사코드 미명시 — §6 표 "stop: vault@.timer → vault@.service → lint.* → mount@" 만) 가 `systemctl --user stop wikihub-mount@${vault}.service` 를 마지막에 호출하는데, 그 시점에 `vault@.service` 가 oneshot 진행 중이면 mount@ 가 `Requires=` 관계로 묶여 있어 dependency stop 이 cascade — vault@ 가 mid-sync 중에 강제 abort → 부분 file_map 저장 위험. design §3 Step 2c 의 30s grace 가 vault@ 의 mid-rclone-export (50MB Google native 파일은 backend export 단계에서 30s 초과 가능) 를 cover 못함.

추가로 §3 Step 2c 에 stop sequence 의사코드가 아예 없음 — §6 의 표만 spec.

**Evidence**:
- wikihub-mount@.service.template L4: `StartLimitIntervalSec=300 / StartLimitBurst=5` — stop+start 5회 이상 시 permanently failed → vault@ 의 `Requires=` cancel.
- wikihub-vault@.service.template L21: `TimeoutStartSec=15min` — sync 가 최대 15분 진행 가능. 30s grace 는 0.3% 만 cover.
- vault-fetch.py L130-138: `LOCK_EX|LOCK_NB` 잡고 sync 진행 중 → SIGTERM 시 try-finally 없음. file_map atomic write 가 lib.state 책임이지만 mid-write SIGKILL 시 broken state.

**Suggested fix**:
- §3 Step 2c 에 `_systemd_stop_before_update` 의사코드 명시:
  ```bash
  systemctl --user stop wikihub-vault@*.timer    # 첫째 — 새 fire 차단
  systemctl --user stop wikihub-lint.timer
  # vault@.service mid-sync 대기 — 최대 15min (TimeoutStartSec 정합)
  for vault in $(_enabled_vaults); do
      timeout 900 systemctl --user stop "wikihub-vault@${vault}.service" || \
          warn "vault@${vault} stop timeout — 강제 abort"
  done
  systemctl --user stop wikihub-lint.service 2>/dev/null || true
  # mount@ 마지막. fusermount3 -uz 가 vault-fetch.py 의 fd 강제 detach.
  for vault in $(_enabled_vaults); do
      systemctl --user stop "wikihub-mount@${vault}.service" || true
  done
  # mount@ 가 RestartSec=10s wait 잔존하지 않도록 reset-failed.
  systemctl --user reset-failed 'wikihub-mount@*.service' 2>/dev/null || true
  ```
- 30s grace → 15min (`TimeoutStartSec` 정합) 명시. DoD V4 갱신: "vault@ sync 가 30s 가 아닌 15min 까지 in-flight grace 보장."
- `reset-failed` 호출이 stop 직후 필수 — `StartLimitBurst` 카운터 초기화로 다음 start 가 fresh hit limit 회피.

---

### CRIT-3: `_step8_wh_setup` 의 hermes 탐지가 yaml `agent.binary` 와 mismatch — F5 미완 상태에서 silent skip
**File/section**: analysis_and_design.md §3 Step 8 `_step8_wh_setup`
**Issue**: §3 Step 8 의 의사코드는 `command -v hermes >/dev/null 2>&1` 로 분기. 그러나:
1. `wikihub.yaml.example` L52: `binary: /usr/local/bin/hermes` — absolute path 가 정본. 운영자가 `binary: /opt/hermes/bin/hermes-cli` 같이 yaml 편집한 경우 `command -v hermes` 는 false (PATH 에 없음) → silent warn 후 skip. 그러나 systemd unit template 의 {agent_invocation} 은 yaml absolute path 로 substitution 되므로 unit 자체는 정상 동작. design 의 detect 가 unit 의 substitution 과 엇갈림.
2. F5 미완성 (plan.md 적용 단계 선언 — Step 5 deferred + backlog #12 `/wh:setup` 매핑 미완) 상태에서 `hermes -z "/wh:setup --reorchestrate"` 는 hermes 측에 skill 등록 자체가 안 됐을 가능성. design §3 Step 8 의 `warn "hermes 미설치"` 분기는 미설치만 cover, **설치되어 있지만 `/wh:setup` skill 미등록 케이스** 미cover — hermes 가 exit 0 으로 silent ignore 가능.
3. 결과: install.sh 가 `daemon-reload` 수행 안 됨 → unit template 갱신 사항이 active service 에 미반영 — 결함 #D 가 재현 (본 feature 가 해결하려는 결함 본인).

**Evidence**:
- analysis_and_design.md L168-176: detect = `command -v hermes` 단독, exit code 검증 없음.
- wikihub.yaml.example L52 + setup.md L60: `{agent.binary}` 가 substitution source. install.sh 가 yaml parse 안 함.
- backlog/F4 surface #D: "template 변경 시 restart 누락" — 본 feature 의 해결 약속과 충돌.

**Suggested fix**:
- `_step8_wh_setup` 이 yaml.agent.binary 를 read 해서 직접 exec (Step 4.5 의 `_yaml_get_vault_rc_ports` 패턴 재사용):
  ```bash
  local agent_binary
  agent_binary="$("$VENV_PATH/bin/python3" -c "import yaml,sys; print(yaml.safe_load(open(sys.argv[1])).get('agent',{}).get('binary',''))" "$WIKIHUB_INSTANCE_ROOT/wikihub.yaml")"
  [[ -x "$agent_binary" ]] || { warn "agent.binary ($agent_binary) 미설치 — /wh:setup 수동 호출 안내"; return 0; }
  local rc
  "$agent_binary" -z "/wh:setup --reorchestrate"
  rc=$?
  if [[ $rc -ne 0 ]]; then
      warn "/wh:setup 호출 실패 (rc=$rc) — F5 미완 또는 skill 미등록. install.sh 가 systemctl daemon-reload 직접 수행."
      systemctl --user daemon-reload
  fi
  ```
- F5 미완 상태의 **fallback path** 를 design 에 명시 — daemon-reload + unit restart 를 install.sh 가 직접 수행. `/wh:setup` 호출은 best-effort.
- `_system/commands/setup.md` 에 `--reorchestrate` flag 의미 spec 추가 항목을 §9.1 DoD 에 명시 (현재 §9.1 9번째 bullet 만, flag 의미론 정의 미명시).

---

### HIGH-1: `--force-fresh` 가 fresh path safety guard 재사용 정책 불명확
**File/section**: analysis_and_design.md §3 Step 0 / §5.1 표 "--force-fresh" 행
**Issue**: 현행 F4 install.sh `_step2_clone` (L188-228) 는 3중 safety guard:
1. WIKIHUB_HOME 시스템 path 차단 (L191-195) — `/`, `/usr`, `$HOME` 등
2. .git 디렉토리 + origin URL 검증 (L200-217) — `im-dongseon/wikihub` 패턴 확인
3. cwd 가 WIKIHUB_HOME 안이면 밖으로 이동 (L219-221)

design §3 Step 0 의 `--force-fresh` 가 "5초 confirm → rm -rf + clean install" 만 명시. 위 3 guard 를 **재사용 보장 명시 없음**. 만약 운영자가 `WIKIHUB_HOME=/ --force-fresh` 호출 (정신 나간 시나리오지만 실제 incident 가능 — env override 실수) 시 5초 confirm 만 통과하면 rm -rf / 실행 가능성. 현행 F4 의 guard 가 `_step2_clone` 안에 있어 force-fresh path 가 별도 wipe 한다면 guard 미적용 위험.

**Evidence**:
- install.sh L188-221 — guard 가 `_step2_clone` 함수 내부 inline.
- analysis_and_design.md §3 Step 0: "INSTALL_MODE 강제 fresh + 5초 wipe confirm" 만 spec.

**Suggested fix**:
- design §3 Step 0 에 명시: "`--force-fresh` path 는 `_step2_clone` 의 3 safety guard (system path · git+origin · cwd) 전부 통과 후 rm -rf 진행. 5초 confirm 은 guard 통과 후 추가 layer."
- DoD V3 갱신: `WIKIHUB_HOME=/ --force-fresh` 시 guard fatal exit (5초 confirm 도달 안 함).
- `_step2_clone` 의 guard 를 `_validate_wipe_target()` 함수로 추출해서 force-fresh path 가 명시적으로 호출하는 구조.

---

### HIGH-2: `git status --porcelain` unstaged guard 가 .git/index.lock + untracked ignored 시나리오 미고려
**File/section**: analysis_and_design.md §3 Step 2a unstaged guard
**Issue**: 다음 케이스에서 의도치 않은 행동:
1. **index.lock 잔존**: 직전 git 명령이 SIGKILL 로 중단 (메인테이너 vim 으로 commit msg 편집 중 SSH timeout) → `.git/index.lock` 잔존. `git status --porcelain` 가 `fatal: Unable to create ... index.lock: File exists` 로 fail → install.sh 가 set -e 로 exit, 의사코드는 abort 안내도 없음. 운영자는 `--force-fresh` 로 가는 경향 → 직전 작업 손실 위험.
2. **.gitignore untracked**: design 은 `git status --porcelain` 만, `-uall` 안 씀 → ignored 파일 (e.g. install.sh 가 만든 `.venv_path` L316 — repo root 에 sidecar) 은 무시. 다행히 `.venv_path` 는 install.sh 가 매번 다시 만들므로 손실 영향 없음. 그러나 운영자가 디버깅 중 `WIKIHUB_HOME/_local_notes.md` (gitignored) 같은 파일 생성 시 reset --hard 이후도 보존됨. 단, design 의 "unstaged silent 손실 0" invariant 가 ignored 도 보존 의미인지 명시 안 됨.
3. **WIKIHUB_HOME 외부 instance.root (`.credentials/`)**: design §1 invariant 1행이 instance.root 미터치 약속 — 이는 instance.root 가 WIKIHUB_HOME 외부 (`$HOME/wikihub-instance`) 라 git 영향 0. OK.

**Evidence**:
- analysis_and_design.md L106-110: `git status --porcelain` 단독, error path 미정의.
- install.sh L29: `WIKIHUB_INSTANCE_ROOT="${WIKIHUB_INSTANCE_ROOT:-$HOME/wikihub-instance}"` — WIKIHUB_HOME 외부 확정.

**Suggested fix**:
- §3 Step 2a 에 index.lock pre-check 추가:
  ```bash
  if [[ -f "$WIKIHUB_HOME/.git/index.lock" ]]; then
      err ".git/index.lock 잔존 — 직전 git 명령이 비정상 종료된 흔적."
      err "  대처: 현재 다른 git process 가 안 도는지 확인 후 \`rm $WIKIHUB_HOME/.git/index.lock\`."
      exit 1
  fi
  ```
- DoD V2 갱신: "index.lock 잔존 시 명시 안내 후 abort."
- invariant 1 명시: "WIKIHUB_HOME 내부의 .gitignored 파일은 reset --hard 가 보존 — 운영자 디버그 메모는 손실 안 됨."

---

### HIGH-3: `_resolve_ref` 의 `git ls-remote` 가 네트워크 결함 시 fallback 부재
**File/section**: analysis_and_design.md §4 ref resolution `_resolve_ref()`
**Issue**: §4 우선순위 3행 `git ls-remote --tags origin | grep -E ... | sort -V | tail -1`. 운영 시점:
- OCI 인스턴스의 outbound HTTPS 가 일시 결함 (GitHub status incident, 운영자 firewall 변경 등) → `git ls-remote` fail → set -e 로 exit. 본 시점에 local 의 `git fetch --tags --prune` (Step 2b) 는 이미 성공해서 local refs/tags 에 캐시된 tag 가 있을 수도 (이전 install.sh 호출이 fetch 했던 tag). `git tag --list 'v*' | sort -V | tail -1` 로 local fallback 가능하지만 design 미명시.
- design §6 표는 ADR-0023 의 Status 갱신을 "Step 3 lock 시점에 결정" 으로 deferred — 정작 `_resolve_ref` 가 network-only 의존이라 위 시점에 install.sh 가 fully blocked.

**Evidence**:
- analysis_and_design.md §4 우선순위 3행 — local cache fallback 미명시.
- §3 Step 2b: `git fetch origin --tags --prune` 가 _resolve_ref 직전 호출 — 성공이 보장됨을 가정하나 fetch 도 동일 네트워크 의존.

**Suggested fix**:
- §4 우선순위에 3'행 추가: "3' (네트워크 fallback): `git ls-remote` 실패 시 `git -C $WIKIHUB_HOME for-each-ref --sort=-v:refname 'refs/tags/v*'` 로 local cache 최신 semver tag 사용. banner 에 '[network offline — using local tag cache]' 명시."
- §3 Step 2b 의 `git fetch` 도 `|| warn "fetch 실패 — local cache 로 진행"` fallback. 단 fetch 실패 시 update path 진행은 위험 (직전 호출 이후 신규 tag 못 받음) — 운영자에게 명시적 confirm 요구가 더 안전.
- DoD V8 갱신: "outbound HTTPS 결함 환경 → local tag cache fallback 동작."

---

### HIGH-4: 두 install.sh 인스턴스 동시 실행 차단 부재
**File/section**: analysis_and_design.md 전체
**Issue**: vault-fetch.py 는 `_state/<vault_id>/.lock` (LOCK_EX|LOCK_NB) — sync 단위 동시성 차단. **install.sh 자체는 락 없음**. 시나리오:
1. 운영자가 ssh 세션 A 에서 `curl ... | bash` 호출.
2. 동시에 ansible playbook 또는 deploy 자동화가 호출 (또는 운영자가 hang 으로 오인하고 새 세션에서 재호출).
3. 둘 다 `_step2_update` 진입 → 첫째 `git reset --hard` 중 둘째 `git fetch --tags` 호출 → race. 더 위험 — 첫째가 `_systemd_stop_before_update` 후 reset 중, 둘째가 `_systemd_start_after_update` 호출 → 첫째 reset 중에 vault@ timer fire.

추가로 `_rotate_install_log` (§3 Step 11) 도 race — 두 인스턴스가 동시에 mv → 둘째가 이미 rename 된 파일에 stat 시도해서 fail.

**Evidence**:
- vault-fetch.py L129-138 — sync 단위 lock 패턴 존재. install.sh 는 미적용.
- analysis_and_design.md §9.1 DoD 9 (V<N>) 어디에도 동시 호출 시나리오 없음.

**Suggested fix**:
- install.sh 진입 직후 (`_rotate_install_log` 직전) 락 획득:
  ```bash
  _acquire_install_lock() {
      local lock="$WIKIHUB_INSTANCE_ROOT/install.lock"
      exec 200>"$lock"
      if ! flock -n 200; then
          err "다른 install.sh 가 진행 중 (lock: $lock)"
          err "  진단: ps -ef | grep install.sh / lsof $lock"
          exit 1
      fi
      # process exit 시 자동 release (fd 200 닫힘)
  }
  ```
- DoD V11 추가: "동시 두 install.sh 인스턴스 호출 시 둘째가 즉시 fatal exit."

---

### HIGH-5: `git reset --hard` 중 disk full / SIGKILL 시 working tree partial — 자가 진단 부재
**File/section**: analysis_and_design.md §3 Step 2d
**Issue**: `git reset --hard $target_ref` 가 disk full / SIGKILL 로 중단된 경우:
- `.git/HEAD` 는 이미 새 ref 가리킴 (atomic 갱신, git plumbing 보장).
- working tree 는 partial — 일부 파일은 새 ref content, 일부는 직전. install.sh 가 그대로 종료 시 `_system/*` 정본이 inconsistent state.
- 재실행 시 design §3 Step 2a 의 `git status --porcelain` 가 modified 파일 list 출력 → unstaged guard 가 abort. 운영자가 `--force-fresh` 로 가야 복구.

**Evidence**:
- analysis_and_design.md §3 Step 2d: `git reset --hard "$target_ref"` 단일 호출, 실패 분기 없음.
- install.sh L67: `exec > >(tee -a "$INSTALL_LOG") 2>&1` — install.log 에 trace 는 남으나 진단 helper 부재.

**Suggested fix**:
- §3 Step 2d 후 post-condition 검증:
  ```bash
  if ! git -C "$WIKIHUB_HOME" diff --quiet HEAD --; then
      err "git reset --hard 후에도 working tree 가 dirty — disk full / 디스크 오류 의심"
      err "  진단: df -h $WIKIHUB_HOME; git -C $WIKIHUB_HOME status"
      err "  복구: --force-fresh 또는 git -C $WIKIHUB_HOME checkout -- ."
      exit 2
  fi
  ```
- DoD V12 추가: "disk full 시뮬레이션 (`fallocate -l <remaining> filler`) 후 update → fatal + 명시 진단."

---

### HIGH-6: log rotation 의 tee fd race + filename collision
**File/section**: analysis_and_design.md §3 Step 11 `_rotate_install_log`
**Issue**: install.sh L67 가 `exec > >(tee -a "$INSTALL_LOG") 2>&1` 로 tee 를 시작. main flow 진입 직후 (§3 main flow `_rotate_install_log`) 가 호출되는데:

1. **tee fd 보존 시나리오**: tee 가 이미 file open (fd로 referencing) — `mv` 는 inode 보존 + path 만 변경. tee 는 mv 이후에도 직전 inode 에 계속 write → **로테이션된 파일에 현 호출 로그가 계속 누적**. 새 `install.log` 는 비어 있음. 다음 호출 시까지 비어 있음. 효과: rotation 이 의미 없음 + 진단 시 분산.
2. **filename collision**: `mv "$log" "${log}.$(date +%Y%m%d_%H%M%S)"` — 동일 초 내 두 호출 (HIGH-4 race 잔존 시) 또는 1초 안 두 번 호출 시 같은 filename → mv 가 silently overwrite. 직전 회전된 로그 손실.
3. **prune race**: `ls -1t ... | tail -n +8 | xargs -r rm` — 동시 두 인스턴스가 prune 시 ENOENT 가능. set -e + pipefail 영향은 미한정 (`-r` 가 있으니 빈 인자엔 안전).

**Evidence**:
- install.sh L67 — tee 의 fd 가 main flow 전체 lifetime 유지.
- analysis_and_design.md L218-234 — rotate 가 main 진입 직후 1회 호출만, tee restart 안 함.

**Suggested fix**:
- 로테이션 순서를 **tee 시작 전** 으로 옮김:
  1. log rotation check + rename (`_rotate_install_log` 호출).
  2. 그 다음 `exec > >(tee -a "$INSTALL_LOG") 2>&1` — 새 install.log 가 명시적으로 open.
- 또는 tee fd 를 명시 close 후 재open:
  ```bash
  exec 1>&- 2>&-       # tee fd close (subshell SIGPIPE 로 tee 종료)
  mv "$log" "${log}.YYYYMMDD_HHMMSS"
  exec > >(tee -a "$INSTALL_LOG") 2>&1   # 새 fd
  ```
  (단 이 패턴은 직전 step 출력 일부 손실 위험 — 1번 옵션이 안전).
- filename collision 회피: 동일 초 안 두 호출 — `_$$` (PID) suffix 추가: `${log}.$(date +%Y%m%d_%H%M%S)_$$`.
- design §3 main flow 의사코드에 `_rotate_install_log` 호출 위치를 `exec > >(tee...)` 보다 위로 이동 명시.

---

### MED-1: `_step10_verify` 의 60s timeout 이 rclone VFS init 첫 호출 대비 부족 가능
**File/section**: analysis_and_design.md §3 Step 10 `_step10_verify`
**Issue**: §3 Step 9 의 mount start 후 5초 grace + Step 10 의 60s wait — total 65s. rclone mount 의 첫 init 은:
- network-online.target 대기 (After/Wants) — 변동성 큼 (cloud-init 후 1~30s)
- rclone VFS 초기 dir scan + drive credentials handshake — Google Drive API 첫 호출 latency 5~15s
- `_wait_active` 가 어떤 상태를 active 로 보는지 design 미명시 — `Type=simple` 이라 ExecStart 시작 즉시 active. 그러나 실제 FUSE 응답은 그보다 늦음 — assert_mount_alive 가 이걸 cover. 그러나 install.sh `_step10_verify` 는 `systemctl is-active` 만 보는지, stat 까지 보는지 명시 안 됨.

**Evidence**:
- mount@.service.template L34-36: `Type=simple` — process 시작 시점이 active, FUSE 준비 ≠.
- scripts/lib/mount.py L74-99: assert_mount_alive 는 5초 timeout 의 stat 호출 — install.sh 의 verify 도 이 패턴 재사용 권장.

**Suggested fix**:
- `_step10_verify` 가 systemd `is-active` + stat path 둘 다 확인 (assert_mount_alive 재사용):
  ```bash
  _wait_active() {
      local unit="$1" mount_path="$2" timeout="$3" elapsed=0
      while (( elapsed < timeout )); do
          if systemctl --user is-active "$unit" >/dev/null && \
             timeout 5 stat "$mount_path" >/dev/null 2>&1; then
              return 0
          fi
          sleep 2; elapsed=$((elapsed + 2))
      done
      return 1
  }
  ```
- timeout 을 60s → 120s 권장 (cloud-init + Drive handshake 마진).
- DoD V10 갱신: "verify 가 systemctl 상태 + stat path 둘 다 통과."

---

### MED-2: V5 downgrade 시나리오 — 의도적 rollback 과 위조 구분 안 됨
**File/section**: analysis_and_design.md §9.2 V5
**Issue**: V5 verification 은 "VERSION 위조 후 update → downgrade warn". 그러나 ADR-0010 의 `--version v0.0.9` 는 의도적 rollback path. 두 시나리오의 분기 정책 미정의:
- 의도적 (`--version v0.0.9`) → semver 비교 (current=0.1.0 > target=0.0.9) → 운영자가 명시 의도. warn 으로 충분.
- 비의도 (VERSION 파일 위조) → 운영자가 무엇을 했는지 모름. fatal 가능.

design 은 두 케이스를 같은 "downgrade warn" 으로 처리하는데, ADR-0030 의 idempotency invariant 와 충돌 가능 — 위조 후 update 는 idempotent 아님 (file system 외 의존).

**Evidence**:
- analysis_and_design.md L398: V5 단일 검증 항목.
- §3 Step 2e: VERSION 비교는 string equality 만 (`if [[ "$current_version" == "$new_version" ]]`) — semver 순서 비교 없음.

**Suggested fix**:
- §3 Step 2e 에 semver 비교 추가:
  ```bash
  if [[ -n "$EXPLICIT_VERSION_FLAG" ]]; then
      # --version 명시 — rollback intent 인정. warn only.
      [[ "$(_semver_cmp $current_version $new_version)" == ">" ]] && \
          warn "intentional downgrade: v$current_version → v$new_version"
  else
      # auto resolve (latest tag) 에서 downgrade — VERSION 파일 위조 또는 tag 회귀 의심
      [[ "$(_semver_cmp $current_version $new_version)" == ">" ]] && {
          err "unexpected downgrade detected — VERSION 위조 또는 tag 회귀 의심: v$current_version → v$new_version"
          err "  의도적 rollback 이면 --version v$new_version 명시 후 재호출"
          exit 1
      }
  fi
  ```
- V5 두 케이스로 split: V5a (명시 rollback 통과), V5b (위조 fatal exit).

---

### MED-3: `_step8_wh_setup` 가 `WIKIHUB_NONINTERACTIVE=1` 환경에서 `/wh:setup` 의 interactive prompt 가 hang 가능
**File/section**: analysis_and_design.md §3 Step 8
**Issue**: install.sh 가 `_step8_wh_setup` 에서 `hermes -z "/wh:setup --reorchestrate"` 호출. `/wh:setup` 의 setup.md (F1 정본) 는 첫 ingest prompt 등 interactive 분기 포함. install.sh 가 curl-pipe 모드인 경우 `WIKIHUB_NONINTERACTIVE=1` 자동 설정 (install.sh L113) 되어 있지만, 이 env 가 hermes subprocess 로 자동 inherits 되어 hermes 가 noninteractive 분기 타는지 보장 안 됨.

추가로 `--reorchestrate` flag 가 setup.md 에 미정의 — Step 3 lock 시점에 setup.md 갱신을 §6 표가 약속하지만 design §9.1 DoD 9 (setup.md 갱신) 만 있고 의미론 spec 부재. flag 의미가 다음 둘 중 어느 쪽?
- (a) 기존 `/wh:setup` 전체 흐름 (yaml validate + systemd unit + first ingest prompt) idempotent 재실행.
- (b) daemon-reload + unit restart 만 (interactive prompt skip).

design §7 O1 미결 사항으로 surface 했지만 "추천 (b)" 로 적었을 뿐 lock 안 됨.

**Evidence**:
- analysis_and_design.md L168-176, L350 (O1 미결).
- install.sh L113 — WIKIHUB_NONINTERACTIVE auto-set.

**Suggested fix**:
- O1 을 Step 3 lock 전에 결정. 권장 (b) — install.sh 의 update path 는 systemd reorchestrate 만 필요. interactive prompt 는 fresh install 의 첫 호출 책임 분리.
- §3 Step 8 의사코드에 env propagation 명시:
  ```bash
  WIKIHUB_NONINTERACTIVE=1 "$agent_binary" -z "/wh:setup --reorchestrate"
  ```
- timeout 추가:
  ```bash
  timeout 300 "$agent_binary" -z "/wh:setup --reorchestrate" || { warn "/wh:setup timeout — daemon-reload 직접 수행"; systemctl --user daemon-reload; }
  ```

---

### MED-4: `--version <tag>` 의 tag verification (signature / pgp) 부재
**File/section**: analysis_and_design.md §4 우선순위 1행
**Issue**: `--version v0.1.0` → `refs/tags/v0.1.0` resolve. tag 가 signed 인지 verification 없음. supply chain 위협:
- 운영자 또는 BOT 이 repo 의 GitHub 권한 탈취 → 새 tag (`v0.1.0` 동일 이름) force-push → `git fetch --tags` 가 local 의 tag overwrite. 운영자가 v0.1.0 으로 rollback 시도 → 악성 tag 받음.
- 일반 git default 는 `fetch.pruneTags = false` 이지만 design 의 `git fetch --tags --prune` 가 prune 활성화 — overwrite 시도가 자동 통과.

이건 v0.1.0 minimum scope 초과 가능 (운영자 보안 모델 토론), 그러나 design 어디에도 surface 안 됨 — backlog 후보로 명시 가치 있음.

**Evidence**:
- analysis_and_design.md §4 — tag verify 미명시.
- §6 표의 ADR-0023 supersede 표기는 wipe 의미론만 다룸.

**Suggested fix**:
- design §7 미결 항목 추가: "tag signature verification (gpg / sigstore) — v0.2.x backlog 후보. 운영자가 self-hosted git mirror 사용 시 더 critical."
- §4 에 1행: "tag overwrite 차단 — `git config fetch.fsckObjects true` 권장. install.sh 가 fresh 시점에 set."

---

### MED-5: `requirements.txt diff` 비교 시 `<prev_ref>` 추적 spec 불명확
**File/section**: analysis_and_design.md §3 Step 3 venv deps sync
**Issue**: §3 Step 3 의 "직전 ref 대비 변경됐는지 비교 (`git diff <prev_ref> HEAD -- scripts/requirements.txt`)". `<prev_ref>` 가 무엇? 의사코드 미명시.
- HIGH-1 의 `PRE_UPDATE_REF` 와 같은 값이어야 함. design 이 PRE_UPDATE_REF capture 자체를 안 한 상태에서 비교 정합 보장 불가.
- 또는 `_system/VERSION` 의 직전 값 + tag resolve 로 구한 직전 ref — 이 경우 운영자가 직전 install 후 `git checkout` 으로 commit ahead/behind 한 케이스 미반영.

**Evidence**:
- analysis_and_design.md L143-146.

**Suggested fix**:
- HIGH-1 의 `PRE_UPDATE_REF` 캡처 spec 과 묶어서 명시. `_step2_update` 가 `export PRE_UPDATE_REF="$(git rev-parse HEAD)"` → `_step3_venv` 가 `git diff $PRE_UPDATE_REF HEAD -- scripts/requirements.txt`.
- 단 PRE_UPDATE_REF 부재 (첫 update) 시 — `_system/VERSION` 직전 값으로 fallback resolve. 또는 unconditional `uv pip install -r requirements.txt` (idempotent).

---

### MED-6: `_enabled_vaults` 부재 — Step 9·10 의 핵심 helper 가 미정의
**File/section**: analysis_and_design.md §3 Step 9·10 / §7 O2
**Issue**: §3 Step 9·10 의사코드 모두 `for vault in $(_enabled_vaults)` 사용. 그러나 `_enabled_vaults` 정의 부재. §7 O2 가 "python helper (`scripts/_helpers/list_enabled_vaults.py`) 1개 추가 vs yq dependency" — 미결.

이 helper 가 어디서 yaml 을 read? `WIKIHUB_INSTANCE_ROOT/wikihub.yaml`? 운영자가 yaml 편집 직후 update 호출 → 직전 vault list 와 mismatch 가능. 의사코드:
- (a) yaml 가 정본 → 새 vault 추가/제거가 즉시 반영. 합리적.
- (b) 직전 systemd unit instance 가 정본 — `systemctl --user list-units 'wikihub-mount@*.service'` parse. 운영자가 yaml 에서 vault 제거해도 stale unit 정리 안 됨.

위 두 케이스 모두 부분적으로 옳음 — install.sh 가 둘 다 호출해서 reconcile 해야. design 미명시.

**Evidence**:
- analysis_and_design.md L188-196, L205-211, L350-351 (O2 미결).

**Suggested fix**:
- O2 Step 3 lock 전 결정. 권장:
  - `_enabled_vaults_yaml` = yaml `vaults[?(@.enabled)].id`.
  - `_enabled_vaults_running` = systemd 의 active mount instance.
  - stop sequence 는 `_enabled_vaults_running` (현재 도는 것 모두 정지).
  - start sequence 는 `_enabled_vaults_yaml` (yaml 의 desired state).
  - reconcile gap (yaml 에서 제거된 vault) — install.sh 가 `systemctl --user stop` + `disable` + ExecStop 의 fusermount 후 mount point 디렉토리는 보존 (사용자 데이터). design §3 Step 9 후 reconcile pass 추가.

---

### MED-7: in-flight vault@ timer fire vs `daemon-reload` race
**File/section**: analysis_and_design.md §3 Step 9
**Issue**: Step 9 의 `systemctl --user daemon-reload` 호출 시점에 vault@ timer 가 fire 가능 (Persistent=true + OnUnitInactiveSec). 정확한 race:
1. Step 2c stop sequence 가 `wikihub-vault@*.timer` stop.
2. `git reset --hard` 진행.
3. Step 9 시작 — `daemon-reload`.
4. daemon-reload 가 unit 캐시 갱신. 이 시점 직후, 그러나 `_systemd_start_after_update` 의 mount@ start 직전, systemd 가 timer 의 OnUnitInactiveSec 카운터를 evaluate 가능. 만약 직전 inactive 가 >> sync_interval_sec 이면 immediately fire 시도. 그러나 timer 가 inactive 상태라 안 fire — start 직전. OK 같지만:
5. `Persistent=true` 가 reboot 가 아닌 stop/start 도 catch up 하는지 — systemd doc 상 timer-inactive 동안 missed schedule 도 catch up. start 시점에 missed fire 즉시 발화 → mount@ 가 아직 starting 인데 (Type=simple grace 5s 진행 중) vault@ ExecStart 의 `Requires=wikihub-mount@%i.service` 로 cascading start → mount@ 첫 init 5초 안에 stat 호출 → assert_mount_alive Retryable.

이건 ADR-0024 가 Retryable 1회 → no-op 으로 처리 가능. 그러나 design 의 idempotent invariant 와 충돌 — 첫 update 가 항상 1회 Retryable 발화 부작용.

**Evidence**:
- wikihub-vault@.timer.template L12-13: `OnBootSec=2min`, `Persistent=true`.
- mount@.service.template L26: `RestartSec=10s` — first init 후 dead 면 10s wait.

**Suggested fix**:
- §3 Step 9 mount start → grace → timer start 사이에 명시 timer-state reset:
  ```bash
  systemctl --user reset-failed 'wikihub-vault@*.timer' 'wikihub-vault@*.service' \
      'wikihub-mount@*.service' 2>/dev/null || true
  ```
- DoD V4 갱신: "update 직후 첫 vault@ fire 가 mount@ ready 후에만 실행 — Retryable 0건."

---

### LOW-1: `INSTALL_MODE_TARGET_REF` 변수가 export 안 됨 — `_step3_venv` 등 다른 함수에서 access 불가
**File/section**: analysis_and_design.md §3 Step 2f
**Issue**: §3 Step 2f 마지막 줄 `INSTALL_MODE_TARGET_REF="$target_ref"` — local 변수 미선언 + export 안 됨. bash 의 자연 scope 으로 main 의 자식 함수에서 read 가능하지만, sourced subshell 또는 추후 helper 분리 시 깨질 위험.

**Suggested fix**:
- 명시 export: `export INSTALL_MODE_TARGET_REF="$target_ref"` 또는 `declare -g`.
- 또는 sidecar file: `echo "$target_ref" > "$WIKIHUB_HOME/.install_target_ref"` — 진단 가능.

---

### LOW-2: `sleep 5` confirm 의 Ctrl+C 외 입력 처리 미정의
**File/section**: analysis_and_design.md §3 Step 2 "Ctrl+C within 5s to abort"
**Issue**: 5초 sleep 중 운영자가 Enter / spacebar 등 입력 시 동작 미정의. design 은 "Ctrl+C" 만 명시. 운영자 mental model: "아무 키 누르면 abort" 가능 → 5초 wait 동안 그냥 진행. 약함 — confirmation 명시성 부족.

추가로 `WIKIHUB_NONINTERACTIVE=1` 인 경우 sleep 5 skip 명시 (§3 L103 주석) 인데, `--force-fresh` 5초 confirm 도 같은 동작 보장 여부 미명시.

**Suggested fix**:
- §3 Step 0 에 명시: "WIKIHUB_NONINTERACTIVE=1 환경에서 `--force-fresh` confirm 5초도 skip — 자동 진행. 운영자가 의도적 wipe 만 자동화 가능."
- 5초 sleep 대신 `read -t 5 -p "Continue in 5s [Ctrl+C to abort, Enter to skip wait]: "` — 명시적 Enter skip + Ctrl+C abort.

---

### LOW-3: `git fetch --tags --prune` 의 prune 가 운영자의 local 작업 tag 손실 가능
**File/section**: analysis_and_design.md §3 Step 2b
**Issue**: `git fetch --tags --prune` 는 origin 에서 삭제된 tag 를 local 에서도 prune. 운영자가 디버깅 중 local-only tag (`v0.1.0-dev-rc1` 같은) 생성한 경우 자동 prune 됨. unstaged guard 와 같은 보호 의도라면 tag 도 보호 대상이어야.

**Suggested fix**:
- `git fetch origin --tags` (prune 제외). 또는 `--prune-tags` 만 origin/* prefix 에 한정 — `git config remote.origin.pruneTags true` (refs/tags/* 가 아닌 refs/remotes/origin/tags/* prune).
- 영향 작아서 LOW — 단 design 미명시는 정합.

---

### LOW-4: `verify` 가 `--user` 컨텍스트 의존 — linger 미활성 시 진단 메시지 부족
**File/section**: analysis_and_design.md §3 Step 10 `_step10_verify`
**Issue**: linger 미활성 + 운영자 ssh 비-로그인 시 `systemctl --user` 명령이 D-Bus 에 연결 못 함. fresh path 의 `_step7_linger` 가 활성화하지만 update path 는 §3 main flow 가 `_step7_linger` skip. 운영자가 linger 비활성화 후 (e.g. ADR-0021 D2 fallback) update 호출 시 verify 가 fail. 명시 안내 부재.

**Suggested fix**:
- `_step10_verify` 진입 시 `loginctl show-user --property=Linger` 확인. `Linger=no` 면 명시 안내 + verify skip (안 fail).

---

## Verdict

**BLOCK** — CRIT-1·CRIT-2·CRIT-3 모두 design lock 전에 surface 필요. 특히 CRIT-1 (rollback) 은 ADR-0030 의 명시 약속과 design 의사코드 불일치라 ADR 작성 직전 반드시 해소. HIGH-1~HIGH-6 도 Step 3 진입 전에 design 에 반영 필요 (구현 단계의 surgical change 회피).

MED·LOW 는 Step 3 진입 후에도 fix 가능 (구현 시점에 의사결정해도 lock 손상 없음).

## Notes

- design §9.1 DoD 의 V1~V10 verification 이 happy path 만. CRIT-1·HIGH-5 의 failure-injection 시나리오 (disk full / SIGKILL / network drop) 부재 — V11~V13 추가 권장.
- design §6 표의 "ADR-0023 부분 supersede 여부 deferred" — Step 3 lock 시점에 결정 명시했지만 ADR-0023 도 supersede 일 가능성 더 강함 (clean wipe 의 default 가 force-fresh 명시 호출로 격리 — 의미론 변경). 본 리뷰 스코프 밖 (architectural decision) 이지만 surface.
- `_step6_agent_skill` 의 update 시 idempotency — design §3 Step 6 "변경 가능성 낮음, idempotent" 만, ADR-0011 prefix 변경 시 운영자 mental model 영향 surface 안 됨. 본 feature 스코프 외지만 backlog 후보.
- 본 리뷰는 design v1 (2026-05-17) 기준. v2 lock 시 본 review_2 의 finding ID 별 처리 결과 (§9 DoD 갱신 또는 ADR-0030 본문 반영) 를 design_review_2_response.md 같이 트레이싱.
