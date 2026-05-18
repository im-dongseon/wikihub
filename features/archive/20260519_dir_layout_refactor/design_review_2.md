# Design Review 2 — dir_layout_refactor (CR2: SRE)

- **리뷰 대상**: analysis_and_design.md v1 (2026-05-19, 618줄)
- **리뷰어**: CR2 (운영 신뢰성 / SRE / 시스템 통합 / race / failure mode)
- **리뷰 일자**: 2026-05-19
- **종합 판단**: **Reject (revisions required)** — migration helper §5.3.1 의 7-step pseudo-code 이 in-flight race·rclone mount·partial-failure idempotency·rollback trap 미정의. v2 에서 helper 의 step-별 정합 / failure mode / 검증 매트릭스 보강 후 재제출 필요.

---

## CRIT — 진입 차단 (Step 2 v2 lock 전 필수 해결)

### CR2-CRIT-1 — rclone FUSE mount 의 mv 전 unmount 미정의 (§5.3.1)

**위치**: §5.3.1 helper pseudo-code step 4 (`mv $LEGACY_INSTANCE → $NEW_HOME`)

**결함**: `~/wikihub-instance/vault/<vault>/` 는 rclone FUSE mount point. 본 디렉토리를 `mv` 시 두 가지 시나리오 모두 destructive:
- (a) mount 활성 상태에서 `mv` — kernel EBUSY 또는 (cross-fs 시) FUSE 통신 단절 + 운영자 자산 ENOENT
- (b) mount 가 parent dir 의 `mv` 후 stale path 가리킴 → vault-fetch.py 의 다음 fire 시 path 불일치 fatal

helper pseudo-code 의 어떤 step 에도 `fusermount3 -u <mount_path>` (또는 vault@<id>.service stop 으로 mount@.service 의 의존성 cascade) 호출 없음.

**권장 해결책**:
- step 1 (systemd stop) 의 정확한 시퀀스 명시:
  ```
  1.1 systemctl --user disable --now wikihub-vault@<id>.timer
  1.2 systemctl --user stop wikihub-vault@<id>.service  # active 시 15min in-flight grace
  1.3 systemctl --user stop wikihub-mount@<id>.service  # Requires= cascade
  1.4 fusermount3 -u $LEGACY_INSTANCE/vault/<id> 2>/dev/null || true
  1.5 systemctl --user reset-failed wikihub-{vault,mount}@<id>.{service,timer}
  ```
- mount 가 EBUSY 시 retry loop (max 3회, 5초 간격) + 실패 시 helper 전체 abort (mv 단계 미진입)
- Step 2 v2 에 systemd unit dependency graph 명시 (Requires= / BindsTo= / PartOf= 정합)
- V3 PASS 기준에 "fusermount3 -u 성공" + "mount path 가 mv 전 unmounted state" 측정 추가

---

### CR2-CRIT-2 — backup cp 의 ENOSPC 위험 (§5.3.1 step 2)

**위치**: §5.3.1 step 2 (`cp -r $LEGACY_INSTANCE ${LEGACY_INSTANCE}.pre-migration.<ts>`)

**결함**: 운영자의 `~/wikihub-instance/` 는 wiki/ + vault/ cache + _state/ 전체 — multi-vault 운영 시 GB 단위. OCI ARM 의 boot volume 통상 50GB. 운영자가 50% 이상 사용 중이면 cp 실패. 더 심각한 경우:
- cp 가 부분 성공 후 ENOSPC → backup partial + 디스크 full → 후속 mv 도 실패 → 운영자 디스크 wedged
- cp 가 rclone mount path (`vault/<id>/`) 까지 재귀 진입 시 (mount 활성 시) FUSE 통신으로 wall time 폭발 + 디스크 사용량 폭증 (mount content 전체 local copy)

**권장 해결책**:
- backup 전략을 cp 가 아닌 **reverse-mv-able 설계** 로 전환:
  - mv 자체가 atomic (같은 fs 내) → 실패 시 reverse mv 로 rollback. cp 불필요.
  - cp 가 정말 필요한 자산은 `wikihub.yaml` + `_state/<vault>/*.json` 등 작은 파일만 (KB 단위)
- helper 에 pre-check 추가:
  ```
  required_kb=$(du -sk $LEGACY_INSTANCE | cut -f1)
  available_kb=$(df -k $HOME | tail -1 | awk '{print $4}')
  [[ $available_kb -ge $required_kb ]] || abort "disk insufficient"
  ```
  단 본 check 가 BLOCKING 이면 운영자 onboarding 마찰 증가 — pre-check 결과를 명시 표시 후 confirm 받는 패턴 권장
- cp 가 vault mount path 진입 안 하도록 `--exclude vault/` 또는 mount 가 unmounted 인 상태에서만 backup
- Step 2 v2 에 backup 전략 재설계 — "cp 전체" 가 아니라 "small files only + mv-based atomic" 명시

---

### CR2-CRIT-3 — partial mv 실패 시 idempotent 재진입 부재 (§5.3.1)

**위치**: §5.3.1 step 3·4 (`mv $LEGACY_REPO → $NEW_SRC` + `mv $LEGACY_INSTANCE → $NEW_HOME`)

**결함**: helper 가 step 3 성공 + step 4 실패 시 (예: cross-fs mv 의 SIGINT, ENOSPC, kernel race) 운영자 상태:
- `~/wikihub/` 가 존재하지 않음 (mv 완료)
- `~/.local/share/wikihub/src/` 에 repo 이전 완료
- `~/wikihub-instance/` 여전히 존재 (mv 실패)

이 상태에서 운영자가 helper 재호출 시:
- `detect_legacy()` 가 `$LEGACY_REPO/.git` 존재 검증 — `~/wikihub/.git` 없음 → false
- helper 가 "legacy detect 안됨" 으로 종료. 운영자 wedged.

또는 install.sh `_step0_legacy_detect` 의 동일 검증도 fail — install.sh 도 진입 거부.

**권장 해결책**:
- helper 에 **stage-aware resume** 로직 추가:
  ```
  if [[ -d $NEW_SRC/.git ]] && [[ ! -d $LEGACY_REPO/.git ]] && [[ -d $LEGACY_INSTANCE ]]; then
      info "resume: step 3 완료, step 4 부터 재개"
      goto step 4
  fi
  if [[ -d $NEW_SRC/.git ]] && [[ -d $NEW_HOME/wikihub.yaml ]] && [[ ! -d $LEGACY_INSTANCE ]]; then
      info "migration 이미 완료. systemd render 만 재실행"
      goto step 6
  fi
  ```
- 또는 lock file 패턴 (`$HOME/.cache/wikihub/migration.state`) — JSON 으로 진행 단계 기록 → 재호출 시 last_stage 부터 resume
- V3 PASS 기준에 "step 3 직후 SIGTERM → 재호출 → step 4 자동 진입 + 최종 PASS" 시뮬레이션 추가

---

### CR2-CRIT-4 — `_step2_update` 의 v0.1.x detect 분기 부재 (§5.2.4)

**위치**: §5.2.4 (`_step2_update: cd "$WIKIHUB_SRC" && git fetch ... && git reset --hard ...`)

**결함**: v0.2.0 release 후 v0.1.x 운영자가 update path 호출 시 (`curl ... | bash` 또는 `bash ~/wikihub/install.sh`):
- §5.2.4 의 `_step2_update` 가 `cd $WIKIHUB_SRC` (= `~/.local/share/wikihub/src`) 시도 → 디렉토리 없음 → fail
- 또는 fresh path 진입 시 `git clone ... $WIKIHUB_SRC` 호출 → `~/wikihub/` (v0.1.x 의 repo) 그대로 두고 신규 src dir 에 clone → **두 repo 공존** → 운영자 confusion + INSTALLED_VERSIONS.json 정합 깨짐

§5.3.2 의 `_step0_legacy_detect` 분기가 fresh path 진입 **전** 에 호출돼야 하는데, 본 의도가 설계서에 명시되지 않음. install.sh 의 step 순서 (Step 0 legacy detect → Step 1 fresh|update 분기 → Step 2 clone|update) 명시 필요.

**권장 해결책**:
- §5.2 또는 §5.3.2 에 install.sh 의 step 순서 정본 명시:
  ```
  install.sh entry:
    Step 0a: WIKIHUB_INSTANCE_ROOT env detect → fail-fast (§5.3.3)
    Step 0b: legacy layout detect → helper 호출 또는 exit (§5.3.2)
    Step 0c: NEW_SRC 존재 여부 detect → fresh vs update 분기
    Step 1+: 기존 flow
  ```
- Step 0b 에서 helper 호출 후 helper 가 exec 또는 self-replace 로 신 install.sh 호출 → recursion guard 명시 (`WIKIHUB_MIGRATION_DONE=1` env 등)
- V3 PASS 기준에 "v0.1.x layout 에서 curl-pipe 호출 → 자동 helper 호출 → 자동 install 완주" 의 정확한 step trace 추가

---

### CR2-CRIT-5 — systemd unit Environment= directive 의 path 갱신 누락 (§5.4)

**위치**: §5.4 (render_systemd_units.py + unit template substitution)

**결함**: 현 systemd unit (vault@.service, lint.service, mount@.service) 의 `Environment=` directive 에 path-bearing 변수 다수 — 예:
- `Environment=WIKIHUB_YAML=$INSTANCE_ROOT/wikihub.yaml`
- `Environment=WIKIHUB_STATE_DIR=$INSTANCE_ROOT/_state`
- `Environment=PYTHONPATH={wikihub_home}/scripts`
- `Environment=WIKIHUB_HOME={...}` (있다면)

§5.4 가 `{wikihub_src}` substitution key 신설을 명시하나, 각 unit 의 모든 `Environment=` directive 의 **before/after 매트릭스** 부재. 일부만 갱신 시 운영 중 ExecStart 가 stale env 로 fire → fatal alert 발동 (ADR-0024).

**권장 해결책**:
- §5.4 에 systemd unit 별 Environment= directive 영향 표 추가:
  | unit | directive | Before | After |
  |---|---|---|---|
  | vault@.service | WIKIHUB_YAML | `{instance_root}/wikihub.yaml` | `{wikihub_home}/wikihub.yaml` |
  | vault@.service | PYTHONPATH | `{wikihub_home}/scripts` | `{wikihub_src}/scripts` |
  | vault@.service | WIKIHUB_STATE_DIR | `{instance_root}/_state` | `{wikihub_home}/_state` |
  | lint.service | (동일) | … | … |
  | mount@.service | (동일) | … | … |
- WorkingDirectory= 도 영향 표 — 운영 자산 의미면 `{wikihub_home}`, src 의미면 `{wikihub_src}` 구분
- ExecStartPre 의 mkdir target 도 영향 표 — 운영 dir 자동 생성용 mkdir 은 `{wikihub_home}` 기준
- V1 PASS 기준에 "각 unit 의 Environment= directive grep → 변경 완료 검증" 추가

---

## HIGH — Step 2 v2 에서 반영 권장 (lock 전 명시 필요)

### CR2-HIGH-1 — migration helper 의 rollback trap 부재 (§5.3.1)

**위치**: §5.3.1 helper pseudo-code 의 `set -euo pipefail` 만 명시, trap 없음

**결함**: ADR-0030 (update_mode) 의 install.sh trap 패턴 (`trap _rollback ERR EXIT INT TERM HUP`) 이 migrate_layout.sh 에 미적용. helper 가 step 4 중간에 SIGTERM 받으면:
- mv partial 상태로 종료
- backup tag 존재하나 reverse-mv 없음
- 운영자가 trap 메시지 없이 silent fail → wedged

**권장 해결책**:
- helper 에도 trap 패턴 채택 (ADR-0030 의 update trap 함수 reuse 가능):
  ```bash
  _migrate_rollback() {
      [[ -d $NEW_SRC/.git && ! -d $LEGACY_REPO ]] && mv $NEW_SRC $LEGACY_REPO
      [[ -d $NEW_HOME/wikihub.yaml && ! -d $LEGACY_INSTANCE ]] && mv $NEW_HOME $LEGACY_INSTANCE
      systemctl --user start wikihub-*.timer 2>/dev/null || true
  }
  trap _migrate_rollback ERR INT TERM HUP
  ```
- rollback 이 step 별 partial state 인식 — CR2-CRIT-3 의 stage-aware resume 과 통합 권장
- exit 정상 시 trap 해제 (`trap - EXIT`) — 운영자 wedged 방지

### CR2-HIGH-2 — Hermes external_dirs 의 다른 도구 entry 보존 보장 부재 (§5.3.1 step 5)

**위치**: §5.3.1 step 5 + §7.2

**결함**: `_step6_agent_skill _patch_hermes_external_dirs` (ADR-0032) 는 marker comment (`# managed by wikihub: ...`) 와 realpath 비교로 wikihub-managed entry 만 변경. 그러나 §5.3.1 step 5 의 helper pseudo-code 가 본 패턴 reuse 한다는 명시 부재 — helper 가 단순 sed 로 path 치환 시 운영자의 codex/aider 등 entry 손상 위험.

**권장 해결책**:
- §5.3.1 step 5 명시:
  ```
  step 5: install.sh `_patch_hermes_external_dirs` 함수 reuse — marker comment 기반 wikihub entry 만 갱신
          (운영자의 다른 도구 entry 보존 보장. ADR-0032 §sub-4 정합)
  ```
- helper 가 install.sh 의 함수를 source 하거나, helper 자체에 동일 marker 패턴 + flock 적용
- V7 PASS 기준에 "~/.hermes/config.yaml 의 비-wikihub external_dirs entry (예: `~/.codex/skills/`) 가 migration 후 unchanged" 명시 추가

### CR2-HIGH-3 — flock 정합 부재 — helper 단독 실행 시 race (§5.3.1)

**위치**: §5.3.1 step 5 + ADR-0032 §sub-4

**결함**: install.sh `_patch_hermes_external_dirs` 는 flock (`flock -x $HOME/.hermes/.config.lock`) 적용. 그러나 helper 가 단독 실행되거나 install.sh 와 병행 시 (예: 운영자가 helper 호출 직후 다른 패널에서 install.sh 재호출) lock 경합 없으면 ~/.hermes/config.yaml double-write 가능.

**권장 해결책**:
- helper 도 동일 flock 적용 명시 (§5.3.1 step 5 에 명시)
- helper 와 install.sh 가 호출 chain 인 경우 helper 가 lock 보유 → install.sh exec 시 lock 자동 해제 또는 fd 전달 패턴 (`exec {lockfd}<>...`)
- 단순화 옵션: helper 가 ~/.hermes/config.yaml 갱신을 수행하지 않고, helper 종료 후 install.sh `_step6` 에 위임 — 책임 단일화

### CR2-HIGH-4 — `WIKIHUB_HOME=$HOME/wikihub` 명시 export 운영자의 silent bug (§5.3.3)

**위치**: §5.3.3 (WIKIHUB_INSTANCE_ROOT env detect 만 명시)

**결함**: v0.1.x 운영자가 `~/.bashrc` 또는 systemd `Environment=WIKIHUB_HOME=$HOME/wikihub` 같이 명시 사용 중이면:
- v0.2.0 의 의미 변경 후 silent — `WIKIHUB_HOME=$HOME/wikihub` 가 운영 dir 의미로 해석 → install.sh 가 운영 자산을 `~/wikihub/` (이전 repo 위치) 에 생성 시도 → repo content 와 충돌 (mv 안 됐다면) 또는 정합 안 되는 dir 사용
- WIKIHUB_INSTANCE_ROOT 만 fail-fast 지만 WIKIHUB_HOME 의 의미 변경은 silent

**권장 해결책**:
- §5.3.3 확장 — WIKIHUB_HOME env 명시 사용 detect 시 안내 메시지 (강제 fail 아니나 명시):
  ```
  if [[ -n "${WIKIHUB_HOME:-}" ]] && [[ -d "$WIKIHUB_HOME/.git" ]]; then
      warn "WIKIHUB_HOME=$WIKIHUB_HOME 이 git repo. v0.2.0 부터 WIKIHUB_HOME 의미가 운영 자산 dir 로 변경됨."
      warn "  현 env 가 repo dir 지칭이면 WIKIHUB_SRC 로 rename 권장. (이전 의미 = WIKIHUB_SRC, 신 의미 = 운영 자산)"
      _prompt_yn "그래도 진행? (현 dir 을 운영 자산으로 처리)" || exit 0
  fi
  ```
- README 의 v0.2.0 migration 안내 section 에 본 silent change 명시

### CR2-HIGH-5 — `WIKIHUB_SRC` per-instance 분리 정책 미결 (§5.4 / §4.4)

**위치**: §4.4 (multi-instance) + plan.md §핵심 미결 #4 ("WIKIHUB_SRC 는 default 공유 또는 per-instance — Step 2 결정")

**결함**: v1 §4.4 가 "src dir 도 운영자 명시 분리 가능" 만 명시. 그러나 default behavior 미결:
- (a) default `WIKIHUB_SRC=~/.local/share/wikihub/src` 공유 — 두 instance 가 동일 src 참조 → src 의 git fetch+reset 시 race (instance A 의 update 가 instance B 의 ExecStart 중 src 변경)
- (b) default `WIKIHUB_SRC=~/.local/share/wikihub/src-<instance_label>` per-instance — 안전하나 instance_label 식별 메커니즘 부재 (systemd %i 외)

plan.md §핵심 미결 #4 가 Step 2 결정 항목이라 명시했으나 v1 §4.4 가 lock 안 함.

**권장 해결책**:
- §4.4 또는 §5.4 에 default 정책 명시 — multi-instance 운영자는 `WIKIHUB_SRC` 도 명시 분리 필수 (default 공유, 운영자 책임으로 분리)
- 또는 v0.2.0 은 single-instance 만 지원 명시 (multi-instance 는 v0.2.x backlog) — Out of Scope §10 에 명시
- README 에 multi-instance 경고 명시 + 권장 패턴 (instance_label suffix)

### CR2-HIGH-6 — backup tag 의 retention 정책 부재 (§5.3.1 step 2)

**위치**: §5.3.1 step 2 (`cp -r ... ${LEGACY_INSTANCE}.pre-migration.<ts>`)

**결함**: backup 이 운영자 home 에 잔존. 운영자가 migration 성공 후 backup 삭제 명령 미인지 시 디스크 누적. 또한:
- 운영자가 v0.2.1 등 후속 update 시 backup 자체가 detect_legacy 의 false positive 유발 가능 (.git 없으니 false 일 거지만 명시 검증 필요)
- backup 위치 자체가 `~/wikihub-instance.pre-migration.*` — v0.2.0 후에는 `~/wikihub-instance` prefix 자체가 legacy 표식이라 운영자 혼란

**권장 해결책**:
- backup 위치를 `~/.cache/wikihub/migration-backup-<ts>/` 또는 `~/.local/share/wikihub/backup/<ts>/` 같이 영향 격리된 곳으로 이동
- helper 종료 시 backup 자동 삭제 명령 안내 출력 (단 자동 삭제는 위험 — 안내만)
- detect_legacy 가 `.git` 존재 외 `~/wikihub-instance.pre-migration.*` 류 path 도 무시 명시
- CR2-CRIT-2 의 mv-based atomic 권장과 통합 — backup 자체가 작아지면 retention 부담도 작아짐

### CR2-HIGH-7 — V3 검증의 step-별 측정 방법 부재 (§9.3)

**위치**: §9.3 V3 PASS 기준 (7 단계)

**결함**: V3 의 7 단계 PASS 기준이 outcome 만 명시 ("systemd stop", "backup", "mv", "render", "start", "fire 성공"). 각 step 의 측정 방법 부재:
- (1) systemd stop — `systemctl --user is-active` 가 inactive 반환? 또는 journalctl 의 STOP 이벤트?
- (2) backup — `du -sh` 결과? 파일 카운트? checksum?
- (3) mv — `ls -la` 결과? inode 비교?
- (5) external_dirs 갱신 — sha256 PRE/POST? marker comment 검증?
- (7) fire 성공 — journalctl 의 first ExecStart event + exit_code=0?

PASS 기준이 측정 가능하지 않으면 VM 검증이 epistemically 약함.

**권장 해결책**:
- §9.3 V3 의 PASS 기준을 측정 방법 표 형태로 재작성:
  | step | 측정 명령 | PASS 조건 |
  |---|---|---|
  | 1 systemd stop | `systemctl --user is-active wikihub-vault@gdrive.service` | "inactive" |
  | 2 backup | `du -sk ${LEGACY_INSTANCE}.pre-*` | original 의 ±5% |
  | 3 mv repo | `[[ ! -d $LEGACY_REPO && -d $NEW_SRC/.git ]]` | true |
  | 4 mv data | `[[ ! -d $LEGACY_INSTANCE && -f $NEW_HOME/wikihub.yaml ]]` | true |
  | 5 ext_dirs | `sha256sum ~/.hermes/config.yaml; grep "managed by wikihub"` | PRE != POST, marker 1개 |
  | 6 render | `systemctl --user cat wikihub-vault@gdrive.service \| grep WIKIHUB_YAML` | new path |
  | 7 fire | `journalctl --user -u wikihub-vault@gdrive.service -n 1 --no-pager` | exit_code=0 |
- V3 외 V8 신설 — "mv 직후 SIGTERM (CR2-HIGH-1 trap 검증)" + V9 "step 3 만 완료 상태에서 helper 재호출" (CR2-CRIT-3 resume 검증)

---

## MED — backlog 처리 가능 (구현 단계에서 명시)

### CR2-MED-1 — last_failure.json path migration 명시 (§7.1 ADR-0024 누락)

**위치**: §7.1 ADR 영향 매트릭스 — ADR-0024 (ops-alert) 행 부재

**결함**: ADR-0024 의 fatal alert path (`~/wikihub-instance/_state/<vault>/last_failure.json`) 가 layout 변경 영향. 매트릭스에 미포함 → 정합 검토 누락. ops-alert.py 의 path detection 도 영향.

**권장 해결책**:
- §7.1 에 ADR-0024 행 추가:
  | ADR-0024 | ops-alert detection path | `{instance_root}/_state/...` → `{wikihub_home}/_state/...` | path 갱신만 |
- ops-alert.py 의 path 표현이 env 기반인지 hardcoded 인지 확인 — env 기반이면 자연 정합, hardcoded 면 §5.x 에 변경 항목 추가
- ADR-0024 R10-MED-3 의 instance_label 은 별도 메타 — layout 변경 영향 없음 (별도 명시)

### CR2-MED-2 — helper 의 sha256 trace record 부재 (§5.3.1 step 5)

**위치**: §5.3.1 step 5 + ADR-0032 §sub-4

**결함**: install.sh `_patch_hermes_external_dirs` 가 PRE/POST sha256 logging. helper 도 동일 패턴 필요 — 운영자가 사후 audit 가능해야.

**권장 해결책**:
- helper step 5 에 명시: "config.yaml 변경 PRE/POST sha256 을 journalctl 에 기록 (운영자 trace 용)"
- 또는 helper log file (`~/.cache/wikihub/migration.log`) 에 기록

### CR2-MED-3 — `WIKIHUB_SRC` 의 운영 dir 경계 검증 (§5.2.5 safety guard 4번째)

**위치**: §5.2.5 (safety guard #4 — XDG path 외 사용 시 명시 confirm)

**결함**: §5.2.5 의 4번째 guard 가 "XDG path 외 사용 시 confirm" 명시하나 **`WIKIHUB_HOME` 과 `WIKIHUB_SRC` 가 동일 또는 nested path 인 경우** 미언급:
- `WIKIHUB_HOME=~/wikihub WIKIHUB_SRC=~/wikihub/src` → 운영 자산 안에 src nested → src wipe 시 운영 자산 영향
- `WIKIHUB_HOME=~/wikihub WIKIHUB_SRC=~/wikihub` → 두 dir 동일 → wipe = 운영 자산 wipe (catastrophic)

**권장 해결책**:
- safety guard #4 보강:
  ```
  4a. realpath($WIKIHUB_SRC) != realpath($WIKIHUB_HOME) — 동일 시 exit 1
  4b. realpath($WIKIHUB_SRC) 가 realpath($WIKIHUB_HOME) prefix 시작 시 exit 1 (nested 차단)
  4c. 역방향도 — realpath($WIKIHUB_HOME) 가 $WIKIHUB_SRC prefix 시작 시 exit 1
  ```
- V6 (multi-instance) PASS 기준에 본 negative test 추가

### CR2-MED-4 — `INSTALLED_VERSIONS.json` mv 가 migration helper 에 누락 (§5.2.7)

**위치**: §5.2.7 (`$WIKIHUB_SRC/_system/INSTALLED_VERSIONS.json` 정합 mv) + §5.3.1

**결함**: §5.2.7 가 신 INSTALLED_VERSIONS.json 위치 명시. 그러나 §5.3.1 helper 의 step 3 mv (`$LEGACY_REPO → $NEW_SRC`) 가 본 파일 포함 mv 한다는 명시 부재. mv 의 자연 결과로 포함되긴 하나, helper 가 mv 후 INSTALLED_VERSIONS.json 의 version field 를 v0.2.0 으로 갱신해야 하는지 미명시.

**권장 해결책**:
- §5.3.1 step 후속에 명시:
  ```
  step 6.5: INSTALLED_VERSIONS.json 의 wikihub.version 을 v0.2.0 으로 갱신
            (migration 자체가 v0.1.x → v0.2.0 의미, 후속 update_mode 가 본 file 기준 ref 판단)
  ```
- V3 PASS 기준에 "$NEW_SRC/_system/INSTALLED_VERSIONS.json 의 wikihub.version == v0.2.0" 추가

### CR2-MED-5 — VM 검증 V<N> 의 "migration 중단" 시나리오 부재 (§9.3)

**위치**: §9.3 (V1~V7)

**결함**: 모든 V<N> 가 happy path. partial failure 시나리오 없음:
- helper step 3 직후 SIGTERM (rollback trap 검증)
- step 2 의 cp 도중 ENOSPC (CR2-CRIT-2)
- step 4 의 mv 도중 fs 다른 device (cross-fs cp+rm fallback) 의 large file 시간 폭증
- step 5 의 hermes config 갱신 도중 다른 패널의 install.sh 동시 실행

**권장 해결책**:
- §9.3 에 V8~V11 신설:
  | V8 | step 3 직후 SIGTERM → 재호출 → 자동 resume → 최종 PASS (CR2-CRIT-3) |
  | V9 | step 2 의 cp 강제 ENOSPC (fallocate 로 disk full 시뮬레이션) → trap 발동 → rollback (CR2-CRIT-2, CR2-HIGH-1) |
  | V10 | cross-fs mv (LEGACY 가 / mount, NEW_SRC 가 /home mount 일 때) — 시간 + 정합 검증 |
  | V11 | hermes config 동시 write race — flock 정합 (CR2-HIGH-3) |

### CR2-MED-6 — update_mode 의 `_step2_update` 후 hermes external_dirs realpath drift (§7.2)

**위치**: §7.2 + ADR-0032

**결함**: v0.2.0 → v0.2.1 update 시 `$WIKIHUB_SRC` path 자체는 안 변해도 `_system/skills/_generated/` 디렉토리가 git reset 으로 재생성. 운영자의 hermes 가 inotify watcher 활성이면 file change 감지로 OK 인데, fork-exec 기반이면 다음 invocation 까지 stale. 본 동작은 본 feature 영향 아니나, layout 변경 후 path 가 더 깊어져 (`~/.local/share/wikihub/src/_system/skills/_generated/`) realpath 길이 의존 도구 (예: hermes 의 path normalize) 영향 검토 필요.

**권장 해결책**:
- 본 feature 범위 외지만 V1 PASS 기준에 "Hermes 가 신 external_dirs path 를 정상 인식 + skill invocation 가능" 명시 추가
- 별도 backlog issue 로 hermes path 길이 edge case 검증 — backlog 추가만

---

## LOW — 참고 (필수 아님)

### CR2-LOW-1 — README migration 안내의 운영자 menta-model 마찰 완화

**위치**: §5.8

**관찰**: README 의 v0.1.x → v0.2.x migration 안내가 "WIKIHUB_HOME 의미 변경" 만 명시 시 운영자가 "왜 의미가 변경됐는가" 의 배경 (data-first vs code-first) 을 모름. ADR-0034 (신설 시) 또는 §1.1 의 mental model 결함 인용 권장.

**권장**: README 의 migration section 1줄 추가 — "본 변경의 배경은 `docs/adr/0034-xdg-layout-decision.md` 참조" 또는 §1.1 가 ADR 이면 ADR 링크.

### CR2-LOW-2 — `--version` flag 의 v0.1.x ref 처리

**위치**: §7.1 ADR-0030 행

**관찰**: `--version v0.1.0` 같은 specific ref 호출 시 v0.1.x 의 install.sh 가 신 layout 인식 안 함. 본 동작 자체는 v0.1.x 의 의도된 behavior — 본 feature 영향 아니나 운영자 의도와 일치 안 할 가능성.

**권장**: §7.1 ADR-0030 Note 에 명시 — "v0.2.0 install.sh 가 `--version v0.1.x` 호출 시 v0.1.x 의 install.sh exec → v0.1.x layout 으로 install. 신·구 layout 혼재 가능". 또는 install.sh 가 신 layout 강제 (`--version` 무시) 옵션.

### CR2-LOW-3 — `_system/VERSION` v0.2.0 bump 시점

**위치**: §9.2 (`_system/VERSION` v0.1.0 → v0.2.0`)

**관찰**: helper 가 mv 한 src 의 `_system/VERSION` 은 v0.1.x 기존 값. helper 가 본 file 도 갱신해야 하는지 미명시 (CR2-MED-4 의 INSTALLED_VERSIONS.json 과 별개 file). 단 v0.2.0 release tag checkout 후라면 자연 갱신 — 본 lifecycle 명시 권장.

**권장**: §9.2 의 version bump 항목에 명시 — "_system/VERSION 갱신은 release branch 의 commit 으로 자연 적용. helper 가 별도 갱신하지 않음. 단, helper 호출 시 신 ref 의 checkout 이 자동 발생하는지 (= helper 가 git fetch 하는지) 명시 필요".

---

## 추가 관찰

### Obs-1 — helper 단독 실행 vs install.sh 호출 chain 의 책임 경계 모호

§5.3.1 helper 의 step 1~7 중 step 5 (hermes external_dirs) + step 6 (systemd render) 는 install.sh `_step6` / `_step3` 의 기능과 중복. helper 가 이를 직접 수행 vs install.sh 위임 결정 미명시 — 책임 단일화 측면에서 helper 는 mv + 운영 자산 안전성만 담당하고, hermes/systemd 는 install.sh `_step*` 에 위임 (helper 가 install.sh `_init_*` 함수 source) 권장.

### Obs-2 — `WIKIHUB_HOME` semantic 변경의 documentation impact

§5.8 (README 갱신) 외에 ADR-0023·0030·0031 의 본문 (Decision section) 도 `WIKIHUB_HOME` 의 의미 변경 영향. 각 ADR Note 만으로는 본 의미 변경의 cross-cutting 영향이 trace 안 됨 — §8.3 의 ADR-0034 신설 vs Note 분산 결정에서 (나) ADR-0034 신설 권장 (CR2 의견). ADR-0034 가 cross-cutting decision 의 정본을 한 곳에 두면 후속 ADR 가 `WIKIHUB_HOME` 의미 참조 시 본 ADR 만 cite — trace 단순화.

### Obs-3 — multipass VM 검증 환경의 v0.1.x snapshot 보존 필수

§9.3 V3 검증 (legacy migration) 이 가능하려면 VM-B 에 v0.1.x install 된 상태 snapshot 필요. F5 archive 후 (eb4b6ed) 의 multipass VM 이 v0.1.0 acceptance 상태인지 확인 필요. 본 snapshot 이 없으면 V3 검증 자체가 불가 — Step 3 진입 전 VM-B snapshot 확보 명시 (§9.3 의 진입 조건 추가).

### Obs-4 — backwards-incompat release 의 SemVer 정합

v0.2.0 의 SemVer 정합: `0.x.y` 의 minor bump 는 SemVer §4 에 따라 backwards-incompat 허용 (0.x.y 는 unstable). 단 운영자 perception 측면에서 v0.2.0 = major-level change 인식 — README 의 release note 가 "0.2.0 = layout breaking" 명시 권장. 단순 minor bump 표기로는 운영자 underestimate 위험.

### Obs-5 — `.credentials/` 위치 결정의 cross-platform 정합

§4.5 (B) 채택 — `~/.credentials/wikihub/` 외부 유지. Linux only 환경 (ADR-0020) 이라 본 위치는 자연. 단 `~/.credentials/` 자체가 XDG 표준 아닌 wikihub-specific convention — 운영자가 다른 도구 (예: ansible vault, gcloud SA) 와 같은 위치 사용 시 권한 모드 (0700) 정합 명시 권장. ADR-0029 본문에 mode/owner 명시 있으면 OK, 없으면 본 feature 가 보강.

---

## 최종 권고

본 v1 은 **layout invert 의 의도와 권장 옵션 (B/C/B) 은 sound** 하나, **migration helper 의 in-flight safety / partial failure / idempotent resume / rollback trap / systemd Environment 정합 / hermes config flock** 측면에서 SRE-grade 검증 부재. v0.2.0 release 의 architectural change 인 만큼 helper 실패 시 운영자 wedged 가능성이 가장 큰 운영 리스크.

**Step 2 v2 진입 전 필수 (CRIT 5건)**:
1. helper step 1 의 fusermount3 unmount 시퀀스 + systemd dependency cascade 명시 (CR2-CRIT-1)
2. backup 전략 재설계 — mv-based atomic + small-file cp (CR2-CRIT-2)
3. helper 의 stage-aware resume + lock file 또는 detect 강화 (CR2-CRIT-3)
4. install.sh entry step 순서 정본 명시 (Step 0a/0b/0c) + recursion guard (CR2-CRIT-4)
5. systemd unit Environment= directive 의 before/after 매트릭스 (CR2-CRIT-5)

**v2 권장 (HIGH 7건)**:
- helper rollback trap + 부분 실패 시 reverse-mv (HIGH-1)
- hermes external_dirs marker comment + flock + 다른 도구 entry 보존 (HIGH-2, HIGH-3)
- WIKIHUB_HOME silent semantic change 의 detect (HIGH-4)
- multi-instance 의 WIKIHUB_SRC default 정책 또는 v0.2.0 single-only 명시 (HIGH-5)
- backup retention 정책 + 위치 격리 (HIGH-6)
- V3 의 step-별 측정 방법 표 + V8~V11 partial failure 시나리오 (HIGH-7)

CRIT 5건 + HIGH 7건 = 12건 보강 후 Step 2 v2 재제출 → CR2 재리뷰 후 lock. v1 → v2 lead time 1~2 일 예상.
