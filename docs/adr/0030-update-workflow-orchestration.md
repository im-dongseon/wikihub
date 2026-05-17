# ADR-0030: install.sh update workflow orchestration

- **Status**: Accepted
- **Date**: 2026-05-17
- **Feature**: features/20260517_update_mode
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

ADR-0010 이 `install.sh` 단일 entrypoint + `_system/VERSION` detect 기반 dual-mode lifecycle (install + update) 큰 골조는 lock 했으나, F4 (`install_runtime`) 가 update path 를 구현하지 못한 채 archive 됐다. 결과:

- F4 install.sh 는 detect 후 무조건 `rm -rf + clone` (ADR-0023 의 clean wipe). 운영자의 unstaged 작업이 silent 손실 + vault@ timer fire 와 race 위험.
- ADR-0010 은 운영 안전 영역 (systemd stop/start sequence, rollback, unstaged 보호, 동시 호출 차단) 을 명시하지 않음 — 본 ADR 이 그 gap 을 정본화.

F4 backlog 의 결함 #C·#D + R16-L2 + design review 3 round (R1·R2·R3) 의 CRIT·HIGH 가 모두 본 영역 결정 부재의 증상. update_mode feature 가 본 ADR 을 따라 구현.

## Considered Options

본 ADR 은 단일 architectural 결정이 아니라 **update workflow safety 정합** 의 4 sub-decision 묶음. 동일 관심사라 1 ADR 로 묶음 (CLAUDE.md §3 Step 2 ADR 추출 원칙의 "결정 = 1 ADR" 은 unrelated decisions 분리 의도; 동일 관심사 내 sub-decision 은 묶음 허용).

### sub-decision 1 — systemd stop/start sequence

- **(α) mount 먼저 stop**: rclone mount 가 가장 먼저 사라지면 vault@.service 의 ExecStart 가 mount path stat fail → 즉시 abort. 부분 file_map 저장 위험.
- **(β) mount 마지막 stop, timer 먼저 stop**: 새 timer fire 차단 → 진행 중 vault@.service 의 mid-sync 가 15min grace 안에 자연 종료 → mount 정지. file_map 보호.
- **(γ) systemctl 호출 없이 SIGTERM 직접**: 비결정적, systemd 의 state machine 외 처리.

### sub-decision 2 — unstaged 작업 보호

- **(α) abort default + `--force-fresh` 로만 destructive**: 운영자 mental model 명시 — clean tree 가 update path 진입 조건.
- **(β) warn + 자동 stash**: 메인테이너가 의도 안 한 stash 가 누적 → 다음 trace 어려움.
- **(γ) warn only, 그대로 reset**: 직전 incident (`rm -rf $WIKIHUB_HOME` silent 손실) 의 root cause 재발.

### sub-decision 3 — 실패 시 rollback

- **(α) `trap ERR EXIT INT` 자동 rollback + systemd unit 재render**: PRE_UPDATE_REF 캡처 → 실패 시 `git reset --hard $PRE_UPDATE_REF` + render 재호출 + daemon-reload + start.
- **(β) 운영자 수동**: 실패 후 install.sh 종료, 운영자가 `--version <prev>` 로 재호출. 운영 부담.
- **(γ) git revert auto-commit**: 다른 git workflow 와 충돌.

### sub-decision 4 — ref resolution chain

- **(α) `--version` > BRANCH env > tag `latest` > local cache (semver max) > main HEAD**: ADR-0010 의 `latest` (이동 태그) 정본 유지 + network fallback + bootstrap fallback.
- **(β) semver tag sort 만 (mutable latest 비사용)**: ADR-0010 의 release 절차 (`git tag -f latest`) 와 충돌. 메인테이너의 promote semantics 깨짐.
- **(γ) `main` HEAD 만 (tag 무관)**: rollback 불가능.

## Decision

**채택**: 모든 sub-decision (α).

- **sub-1**: stop sequence = `vault@.timer → vault@.service (15min grace) → lint.* → mount@`. start sequence = `daemon-reload → mount@ → FUSE-ready stat wait (120s) → vault@.timer → lint.timer`. stop 직후 `daemon-reload` 호출 (stale unit 캐시 race 차단). `reset-failed` 호출로 `StartLimitBurst` 카운터 초기화.
- **sub-2**: `git status --porcelain` empty 가 update path 진입 조건. `.git/index.lock` 잔존 시 명시 abort + 안내. `--force-fresh` 로만 destructive 재설치.
- **sub-3**: `_step2_update` 진입 즉시 `trap '_rollback_if_failed' ERR EXIT INT` 등록 + `PRE_UPDATE_REF="$(git rev-parse HEAD)"` 캡처. 실패 분기:
  - `current_ref == PRE_UPDATE_REF` (git reset 전 실패) → systemd 재기동 만.
  - `current_ref != PRE_UPDATE_REF` (git reset 후 실패) → `git reset --hard $PRE_UPDATE_REF` + `_step8_systemd_render` 재호출 + `_systemd_start_after_update`.
  - SIGINT (exit 130) → 명시 안내 + 재기동.
- **sub-4**: `_resolve_ref()` 우선순위 정본 — `--version <tag>` (인자 강제 소비, no-arg 분기 없음) > `BRANCH` env / `--branch` > `refs/tags/latest` > local cache (`git for-each-ref --sort=-v:refname 'refs/tags/v*' | head -1`, mutable `latest` stale 비사용) > `origin/main` HEAD. BRANCH default empty 로 변경.

**이유**:
- (sub-1 β): vault@.service 의 `TimeoutStartSec=15min` 과 grace 정합. mount last-stop 이 file_map atomic 보호.
- (sub-2 α): destructive 동작은 운영자의 명시 동의로만. ADR-0023 의 clean wipe 도 본 결정 후 fresh / `--force-fresh` 에만 한정.
- (sub-3 α): 운영 invariant "재호출 = 정합 동기화" 가 실패 시에도 보장. 운영자 mental load 최소.
- (sub-4 α): ADR-0010 의 release 절차 (`git tag -f latest`) 정합 + network fallback. semver derive (v2 초안) 는 ADR-0010 spec 변경이라 기각.

## Consequences

- **긍정**:
  - 결함 #B·#C·#D + R16-L2 closure.
  - 운영자 mental model 명시 — update 는 정합 동기화, fresh 는 명시 동의.
  - 동시 호출·dirty tree·partial state 시나리오 explicit error.
  - rollback 자동 — 실패 후 손으로 복구 불필요.
  - ADR-0010 의 `latest` 정본 회복 — 메인테이너 release 절차와 install.sh 의 ref resolution 정합.

- **부정/제약**:
  - install.sh 가 systemd unit render 책임을 가져감 (C2 fix) — F4 의 `/wh:setup` 위임 모델 변경. `/wh:setup` 의 책임은 skill 메타 + yaml validate + first ingest prompt 로 축소.
  - 새 helper `scripts/_helpers/render_systemd_units.py` 신설 — yaml + template 접근 단일화. setup.md §Step 2 의 2-pass substitution 이 본 helper 로 이관 (§6.1 contract 정본).
  - bash trap 의 의사코드 복잡도 증가 — ERR/EXIT/INT 3-signal handling + PRE_UPDATE_REF state machine.
  - `--force-fresh` flag 신규 — ADR-0010 의 single-curl-line 정합은 유지 (no-flag default 가 update, flag 로만 destructive).
  - `--version` flag 의 인자 강제 소비 — GNU CLI 관례 (`--version` no-arg) 와 충돌. version 조회는 `cat $WIKIHUB_HOME/_system/VERSION` 으로 안내.

- **후속 영향**:
  - **ADR-0010** conformance 회복 — supersede 아님. ADR-0010 §Decision 의 `latest` 절차 + `_system/VERSION` detect 가 본 ADR 의 implementation spec.
  - **ADR-0023** Note 추가 — clean wipe (`rm -rf + clone`) 은 fresh install / `--force-fresh` 명시 호출에만 한정. update path 는 본 ADR 의 fetch + reset.
  - **F5 hermes_adapter** 와 독립 — install.sh 가 systemd render 직접 수행이므로 hermes 부재·`/wh:setup` skill 미등록 상태에서도 update path full functional. `/wh:setup` 호출은 best-effort skill 메타 갱신.
  - **재검토 트리거**: rclone mount 외 vault type 도입 (F6 `vault_directory`) 시 stop/start sequence 가 vault type-aware 분기 필요할 수 있음.

## Notes

- `--version` GNU 관례 충돌 인지. 운영자에게 명시 안내 — README 의 install snippet + `install.sh -h` 출력.
- 본 ADR 의 4 sub-decision 분할 검토 (R3 Notes): "ref resolution chain (sub-4) 만 별도 ADR-0031 로 분리 가능" 제안. v0.1.0 에서는 1 ADR 유지 (동일 관심사 — update workflow safety). v0.2.x release engineering 확장 시 (e.g. tag signature verification) ADR-0031 신설 검토.
