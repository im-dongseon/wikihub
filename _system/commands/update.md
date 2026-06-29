# /wh-update

wikihub 운영 환경을 latest (또는 지정 ref) 로 동기화. install.sh update mode 의 thin wrapper — `_system/commands/wu.md` 가 단축 alias.

## 호출

```
<agent_invocation> "/wh-update [--version vX.Y.Z] [--branch canary] [--skip-drift-check] [--non-interactive]"
```

## 사전 조건

- wikihub 가 이미 한 번 설치된 상태 (`$WIKIHUB_SRC/_system/VERSION` + `.git` 존재)
- Linger 활성화 (ssh 종료 후 systemd --user 유지)
- 사용자 wikihub 환경 = `$WIKIHUB_HOME/wikihub.yaml` 존재

## 절차

### Step 1. scripts/update.sh preflight

1. `WIKIHUB_SRC` 경로에 `install.sh` 존재 확인
2. `_detect_drift()` 실행 — 설정 drift 사전 점검 (read-only, update 차단 안 함)
   - `wikihub.yaml` 존재 여부
   - `rclone.conf` 권한 (600/400)
   - systemd unit override 존재 시 경고
   - `install.lock` stale 여부
3. `_snapshot_active_units()` 실행 — 현재 활성화된 wikihub systemd unit 목록 스냅샷

### Step 2. install.sh update mode (위임)

```bash
bash "$WIKIHUB_SRC/install.sh" [--skip-confirm] [--version <tag>] [--branch <ref>]
```

install.sh 가 다음을 처리:
- `git fetch origin --tags --force` + `git reset --hard <target_ref>`
- `_systemd_stop_before_update` (mount/ingest/lint/graphify 중지)
- `_step8_systemd_render` (systemd unit 재렌더링)
- `_systemd_start_after_update` (mount → wait → ingest timer → lint timer 재시작)
- `_rollback_if_failed` (실패 시 git reset + systemd 복원)

### Step 3. 사후 확인

1. `_selective_restart_report()` — 변경된 unit 파일과 재시작된 서비스 목록 출력
2. `systemctl --user status wikihub-*` 로 각 서비스 상태 확인
3. `journalctl --user -u wikihub-* -n 20 --no-pager` 로 에러 로그 확인

## 출력 산출물

| 변경 대상 | 주체 | 설명 |
|---|---|---|
| `$WIKIHUB_SRC/` | install.sh | git pull + reset |
| `~/.config/systemd/user/wikihub-*` | install.sh | systemd unit 재렌더링 |
| `_system/skills/_generated/wh-update/SKILL.md` | install.sh | Hermes skill 자동 생성 |
| `$WIKIHUB_HOME/.update-snapshot.units` | update.sh | transient, post-exec 삭제 |

## 실패 처리

install.sh 의 `_rollback_if_failed` 가 모든 권한 보유. update.sh 자체는 pre-drift 만 warn.

| 실패 시점 | 동작 |
|---|---|
| preflight (install.sh 미존재) | die — install.sh 경로 안내 |
| drift 감지 (yaml 미존재) | warn + continue (install.sh 가 update mode 감지) |
| install.sh exit non-zero | trap rollback 실행 후 exit code 전파 |
| network failure | install.sh 가 local cache fallback |

## 멱등성 보장

- 동일 ref 에서 재실행 시 git reset --hard 가 no-op (변경 없음)
- systemd render 는 동일 template → 동일 unit file → restart no-op
- drift 감지는 read-only, side effect 없음

## 동시성

install.sh 의 `_acquire_install_lock` (flock on `$WIKIHUB_HOME/install.lock`) 이 중복 실행 차단. update.sh 는 별도 lock 미획득.

## 관련 ADR

- ADR-0032 Hermes skill registration (materialize 패턴)
- ADR-0033 install-time materialized skills
