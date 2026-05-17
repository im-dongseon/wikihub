# Feature Plan — update_mode

- **feat_id**: `update_mode`
- **시작일 (KST)**: 2026-05-17
- **버전**: v1
- **선행 feature**: F4 `install_runtime` (archive 완료, squash `27966bc`)
- **목적**: 운영 중 wikihub 정본을 **재설치 없이 안전하게 갱신**하는 경로 정본화. ADR-0010 이 이미 lock 한 dual-mode lifecycle (install + update via `_system/VERSION` detect + tag `latest` ref) 을 F4 install.sh 가 부분만 구현했고 destructive `rm -rf` 로 남아있는 gap 을 닫는다. F4 surface 결함 #A·#B·#C·#D + R16-L2 일괄 fix + systemd orchestration·unstaged 작업 보호·log rotation 신규 spec.

> **핵심 운영 invariant**: 운영 중 vault@ timer fire 와 update 가 겹쳐도 **데이터 정합성·idempotency 깨지지 않음**. 메인테이너의 unstaged 작업은 명시적 동의 없이 손실되지 않음. 재실행은 "재설치" 가 아닌 "정합 동기화".

---

## 작업 분류

**기능** + **버그 수정 묶음** (install.sh 라이프사이클 결함 4건 + 로그 회전 1건).

---

## 적용 단계 선언

| 단계 | 수행 | 상태 | 비고 |
|---|---|---|---|
| Step 1 Plan | ✅ 본 문서 | 완료 | U1~U5 lock (사용자 confirm, 2026-05-17) |
| Step 2 Analysis & Design | ✅ v3 | 완료 (`approved: 2026-05-17`) | v1 → v2 (R1·R2 CRIT 5+HIGH 9) → v3 (R3 CRIT-N 2+HIGH-N 4+PARTIAL 5) |
| Step 2 Design Review | ✅ R1·R2·R3 | 완료 | spec consistency · SRE safety · v2 closure verification |
| Step 3 Implementation | ✅ | 완료 (HEAD `8601406`) | install.sh dual-mode + render_systemd_units.py + setup.md slim + README |
| Step 4 Code Review | ✅ R1·R2 | 완료 (CRIT 0 · HIGH 0) | Must 7건 fix (CR2-CRIT-1·HIGH 1-5 + CR1-MED-3) + V1·V11·V15 회귀 PASS |
| Step 5 Deployment | ⏸ **deferred** | v0.1.0 다른 feature (F5 hermes_adapter) 미완성. F4 와 동일 정책 — v0.1.0 일괄 deploy 시점에 진행 | |
| Feature 종료 처리 | ✅ | 2026-05-17 archive 이동 | ADR-0030 Accepted + ADR-0023 Note |

## V<N> Phase 2 acceptance gate (VM 검증)

| ID | 시나리오 | 결과 |
|---|---|---|
| V1 | fresh F4 → update path 첫 호출 + 멱등 재호출 | ✅ PASS |
| V2a | dirty tracked file | ✅ PASS (abort + stash 안내) |
| V2b | `.git/index.lock` 잔존 | ✅ PASS (abort + 명시 안내) |
| V13 | 동시 install.sh 호출 | ✅ PASS (둘째 fatal exit 1) |
| V14 | render idempotency | ✅ PASS (mtime 보존, written=0/skipped=3) |
| V11-ish | `--version v9.9.9` (tag 부재) → trap rollback path | ✅ PASS (pre-reset 분기) |
| V15-ish | trap signal registration (TERM·HUP 포함) | ✅ PASS |
| V3·V4·V5·V6·V7·V8·V9·V10·V12 | (시간/환경 한계) | deferred (v0.2.x 후속 또는 운영 surface 시) |

## VM 테스트 도중 surface fix (5건)

1. `.gitignore .venv_path` 추가 — runtime sidecar untracked → unstaged guard 오발화 차단
2. install.sh refspec normalize + unshallow — F4 single-branch clone 잔재 회수
3. `_resolve_ref` path 2 `origin/` prefix — local branch 부재 시 git reset fail 해소
4. venv 재생성 후 pip skip 결함 — pip skip 최적화 자체 제거
5. (Step 4 fix 7건) — 위 표

메소드론 적용: **전체 적용** — trivial 변경 아님. install.sh 의 라이프사이클 정본 변경이라 spec 영향 큼.

---

## 예상 영향 범위

### 신규

- `_system/logrotate/wikihub.conf` (or in-script rotation) — install.log 일별 회전, 7일 보관. R16-L2 처리.
- (잠재) `_system/commands/wh-update.md` — `/wh:update` skill 정본. Step 2 에서 install.sh 직접 호출 vs skill wrapper 결정.

### 수정

- `install.sh` — `--update` flag 추가, Step 2 `rm -rf` 제거, `git fetch + reset --hard origin/$BRANCH` idempotent path, Step 6 systemd unit auto-redeploy + mount stop/start orchestration, BRANCH default 정책 정리 (결함 #A).
- `_system/commands/setup.md` — `/wh:setup` 의 첫 시도 vs 재실행 동작 명시 (update mode 와 의미 경계 lock).
- `docs/adr/NNNN-update-mode-policy.md` (신규 ADR 1건) — `--update` 의 idempotency 모델 + BRANCH/tag 정책 + unstaged 작업 보호 (warn vs abort) 결정.

### 비영향 (의도적 제외)

- `_system/wiki-schema.md` — 지식 모델 무변경.
- `_system/commands/ingest.md` — vault sync 의미론 무변경.
- `scripts/lib/*` — Python 런타임 무변경.
- F5 hermes_adapter — 별도 feature.

---

## 미결 사항 (사용자 confirm 으로 lock 완료 — 2026-05-17)

| ID | 항목 | Lock 결정 |
|---|---|---|
| U1 | 정본 entrypoint | **ADR-0010 정합 그대로** — `install.sh` 단일. `_system/VERSION` 존재 여부로 update vs fresh 자동 분기. `--force-fresh` 로 명시 파괴 재설치 |
| U2 | 버전 정본·ref 정책 | **ADR-0010 정합 그대로** — `_system/VERSION` (이미 `0.1.0`) + tag `latest` default + `--version v0.1.0` 명시 pin. tag 부재 시 `main` HEAD fallback (v0.1.0 spec 완성 후 tag cut) |
| U3 | unstaged 작업 보호 | **abort default + `--force-fresh` 안내** (destructive 명시 동의). 신규 ADR-0030 후보 항목 |
| U4 | systemd orchestration sequence | **stop**: `vault@*.timer` → `vault@*.service` → `lint.timer/service` → `mount@*.service`. **start**: `mount@*.service` → `vault@*.timer` → `lint.timer`. reorchestrate trigger = install.sh 가 `/wh:setup` 자동 호출. 신규 ADR-0030 후보 항목 |
| U5 | log rotation 위치 | **in-script** (`install.log` 가 user-mode 환경 정합). 7일 또는 10MB 시 `install.log.YYYYMMDD` rename, 7개 보관 후 prune |

신규 ADR 후보: **ADR-0030 (update workflow orchestration)** — U3·U4 의 운영 정책을 1건으로 묶음. update path 의 stop/start sequence + unstaged guard + rollback automation 을 정본화. ADR-0010 의 후속 (supersede 아님, 보강).

---

## DoD 미리보기 (Step 2 에서 정밀화)

- `install.sh --update` 가 unstaged 작업 abort + git reset + systemd orchestration + mount stop/start 까지 idempotent 하게 동작.
- 두 번째 실행이 첫 실행 결과를 깨지 않음 (재호출 안전).
- vault@ timer fire 와 update 가 겹쳐도 sync 정합성 손상 없음.
- install.log 가 7일 보관 후 회전.
- 결함 #A·#B·#C·#D + R16-L2 모두 closed.

---

## 다음 단계

사용자 확정 후 `features/20260517_update_mode/analysis_and_design.md` 작성 진입. 진입 시점에서 미결 U1~U5 surface 우선.
