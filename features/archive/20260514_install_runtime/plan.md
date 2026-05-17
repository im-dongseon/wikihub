# Feature Plan — F4 install_runtime

- **feat_id**: `install_runtime`
- **시작일 (KST)**: 2026-05-14 (v1) / 2026-05-15 (v2 재plan)
- **버전**: v2
- **선행 feature**: F3 `vault_gdrive_api` (archive 완료, `00fd0aa·39db90d`)
- **목적**: F3 산출물을 OCI ARM Ubuntu 서버에 **실제로 돌리기 위한 설치·기동 인프라**를 만든다. v2 부터는 **rclone mount (vault 자체)** + **gws drive changes API (변경 감지 정본)** 의 역할 분리 design (Path C+) 으로 전환. install.sh (gws+rclone 설치·venv·pinned 버전) + systemd unit (mount.service + vault@.service + vault@.timer + ops-alert.service) + `wikihub.yaml.example` 한 묶음.

> **핵심 운영 invariant**: OS reboot 후 **사람 개입 없이** sync 사이클 자동 재기동 + rclone mount 자동 복구. v0.1.0 acceptance criteria — 모든 결정이 이 한 줄을 지키도록 정렬.

## Revision Log

| Version | Date | 변경 요지 |
|---|---|---|
| v1 | 2026-05-14 | 초안. install.sh + systemd unit + `wikihub.yaml.example` + `auth_gdrive.py` 한 묶음. **gws CLI 단독** 으로 Drive 접근 — `sync.py` 가 `gws drive changes list` (변경 감지) + `gws drive files get/export` (다운로드/export) 양쪽 호출. Step 2 design review R1~R4 + Step 4 code review R9·R10 통과, Step 5 직전까지 진행 |
| v2 | 2026-05-15 | **rclone mount 도입 + Path C+ 역할 분리** 결정 반영. 결정 근거: `rclone_vs_gws_comparison.md` (동일 디렉토리). 핵심 변경: (1) **rclone mount = vault 자체에 마운트** (`<instance_root>/vault/<vault_id>/`) — 사용자 입력 채널 + 다운로드 패스 (vfs cache 활용) + 실시간 mount UX. (2) **gws drive changes list = 변경 감지 정본** (cursor 기반, ADR-0014 유지). 근거: rclone 은 Drive Changes API 를 사용자에게 노출하지 않음 (backend command 부재). lsf --max-age 윈도우 모델은 삭제/권한/catch-up 손실. (3) **사이클 시작 시 `rclone rc vfs/refresh` 1회** — gws 가 변경 알린 후 mount vfs stale race window 차단. (4) F3 `sync.py` 핵심 로직 **~90% 재사용** — 다운로드 헬퍼만 mount path `open()` 으로 교체. ADR-0014/0015/0017 supersede 없음. 신규 ADR 3건 (rclone-mount 채택, vfs refresh 정책, 책임 분리 정본화) |

---

## 작업 분류

**기능** (운영 인프라 신규 + v1 산출물의 surgical 보강).

---

## 적용 단계 선언

v1 의 단계 선언은 v2 에서도 유지. 다만 **Step 2 복귀** 가 트리거된 상태 — v1 의 Step 4 code review 통과 (R9·R10) 이후 사용자가 architectural 변경 (rclone 도입) 을 결정. 메소드론 §3 의 Step 4 → Step 2 복귀 흐름 따름.

| 단계 | v1 상태 | v2 진행 | 사유 |
|---|---|---|---|
| Step 1 Plan | ✅ v1 승인 완료 | v2 재plan — 본 문서 | rclone 도입 결정 lock 필요 |
| Step 2 Analysis & Design | ✅ v6 approved (Step 4 fix 반영) | **v7 신규** — Path C+ design lock | mount unit·vfs refresh·책임 분리·sync.py 다운로드 헬퍼 교체 spec |
| Step 2 Design Review | ✅ R1~R4 통과 | v7 신규 부분만 R5·R6 (멀티모델) | mount/refresh/책임 분리는 신규 architectural 결정 — 정합성 결함 운영에서 surface |
| Step 3 Implementation | ✅ v1 산출물 완료 (7 신규 + 5 수정) | v7 변경 부분만 surgical 구현 | install.sh rclone 추가, mount.service.template, sync.py 다운로드 헬퍼 교체 |
| Step 4 Code Review | ✅ R9·R10 통과 (29건 처리) | ✅ v9 R15·R16 (멀티모델, 2026-05-17) — CRIT 1·HIGH 9 모두 fix + Must·Should 묶음 적용. CRIT·HIGH 0건 DoD lock | 외부 인터페이스 (mount path · vfs refresh hook · SA 인증) 신규 |
| Step 5 Deployment | ⏸ **deferred** (2026-05-17 사용자 결정) | v0.1.0 의 다른 feature 가 미완성 상태라 본 feature 단독 배포 보류 — v0.1.0 전체 feature 완성 후 일괄 deploy | F4 만 단독 배포 시 hermes integration 미완 (결함 #12) + 운영 시작 의미 약함 |
| Feature 종료 처리 | ✅ 수행 (2026-05-17) | Step 5 deferred 결정 후 archive 이동 — ADR 9건 + 11+1건 결함 fix + V<N> Phase 2 acceptance gate 11건 통과 | ADR-0014·0015·0021·0022·0023·0024·0025·0026·0027·0028·0029 모두 Accepted 상태 |

생략 조건 비매핑: v2 신규 부분도 Step 2~5 모두 수행. 사유 — rclone mount + race window 차단이 신규 architectural 결정이므로 멀티모델 검토·실수행 verification 모두 필수.

---

## 예상 영향 범위 (v2 변경)

### 신규 (v2 추가)

- `_system/systemd/wikihub-mount@.service.template` — rclone mount daemon (Type=simple, Restart=always, `After=network-online.target`). vault 별 instantiated (vault_id) — Step 2 에서 단일 vs instantiated 재검토
- `scripts/lib/mount.py` (또는 `sync.py` 내 helper) — 사이클 시작 시 `rclone rc vfs/refresh` 호출. race window 차단 책임. mount stat 검증 (마운트 실패 시 fail-fast)
- `wikihub.yaml.example` — `vaults[*].mount_path` 추가 (mount FS path 명시, default `<instance_root>/vault/<vault_id>/`), `operations.rclone_min_version` 추가, `operations.vfs_refresh_mode` 추가 (`recursive` / `per-file` / `dir-cache-time`)
- `docs/adr/0025-rclone-mount-adoption.md` — rclone mount 채택, vfs cache 정책
- `docs/adr/0026-vfs-refresh-policy.md` — race window 차단 메커니즘 (recursive vs per-file)
- `docs/adr/0027-rclone-gws-responsibility-split.md` — Path C+ 정본화 (책임 경계 + 장애 격리 정책)

### v1 산출물 surgical 수정 (Step 3 보강만)

- `install.sh` — rclone 설치 단계 추가 (apt 또는 binary, Step 2 결정), `rclone config` 절차 안내 (`/dev/tty` 분기), mount.service 활성화
- `scripts/lib/sync.py` — **다운로드 헬퍼** (`_download_to_vault` 또는 동등) 를 `gws files get/export` 호출 → **mount path `open()`** 으로 교체. **변경 감지 (`gws drive changes list`) 는 그대로 유지**
- `scripts/lib/config.py` — `vault.mount_path` 옵션 파싱
- `scripts/lib/credentials.py` — rclone credentials (`~/.config/rclone/rclone.conf`) 존재 검증 helper 추가 (gws credentials 검증은 그대로)
- `_system/commands/setup.md` — rclone config 절차 1-step 추가 + mount path 디렉토리 ensure
- `_system/systemd/wikihub-vault@.service.template` — `After=wikihub-mount@%i.service` + `Requires=wikihub-mount@%i.service` 의존 추가
- `README.md` — install 절차에 rclone OAuth 1회성 절차 + mount 개념 도식 추가
- `tests/test_sync.py` — mount path open 패턴 테스트 (mock filesystem). `gws files get/export` 호출 테스트 제거

### v1 산출물 유지 (변경 없음)

- `scripts/lib/gws.py` — `gws drive changes list` subprocess wrapper 그대로
- `scripts/lib/errors.py` — gws exit code/stderr 매핑 그대로 (ADR-0017 유지)
- `scripts/auth_gdrive.py` — gws OAuth 발급 그대로
- `scripts/lib/extraction.py` — mime 매핑·extraction 로직 그대로 (mount path 가 input 만 바뀜)
- `scripts/lib/state.py` — cursor + file_map + last_sync 그대로
- `scripts/ops-alert.py` — fatal alert 흐름 그대로
- 기존 systemd unit (`wikihub-vault@.service/.timer`, `ops-alert.service`) — service 본문은 그대로, 의존성만 추가

### F3 후속과의 경계 (v1 유지)

F3 의 R3·R4 잔류 MED 8건 (next_retry_at backoff, error_count/skipped_count stdout, operation 분기, root_folder_id 다중 hop 등) 은 **본 feature 범위 밖**. v2 에서도 별도 light feature 로 분리.

---

## 메소드론 적용 여부

- **적용**: Step 1~5 + Feature 종료 처리 (모두 수행)
- **사유**: v2 의 rclone 도입 + race window 차단은 신규 architectural 결정. 단일 실수가 운영 사이클 정합성 직격 (stale read → wiki page 오염). 메소드론 풀 적용 + ADR 추출.

---

## V<N> verification

v1 의 V4·V6·V8·V10·V11·V12 모두 유지 (v2 에서 일부 갱신). v2 추가:

| ID | 항목 | 방법 | 영향 |
|---|---|---|---|
| V4 | gws stderr 실패 패턴 | dev box/OCI 에서 의도적 403/401/5xx trigger → `lib/errors.py` regex refine + ADR-0017 정본화 | F3 잠정 매핑 확정 (v1 유지) |
| V6 | gws version pinning | `gws --version` + changelog → install.sh pinned + ADR-0015 발의 | install.sh 안정성 (v1 유지) |
| V8 | 의존성 — Python venv + gws + **rclone** + Python libs (pdfminer.six·python-pptx·…) | clean ARM Ubuntu 에서 install.sh 실수행 → 모든 import + rclone binary import-time 성공 | F3 dispatch 정합 (v2 — rclone 추가) |
| V10 | systemd unit 동작 — Type=oneshot · exit 75 의 timer Restart trigger · `SuccessExitStatus=0 75` | OCI 에서 timer fire + 실 vault-fetch 1 사이클 | F3 exit code 매핑 정합 (v1 유지) |
| V11 | install.sh idempotency — 두 번 호출해도 안전 (gws+rclone 재설치 안 함, venv·systemd 중복 enable 안 함) | install.sh 두 번 호출 후 state 비교 | OCI 운영 절차 안전성 (v1 유지) |
| **V12** | **reboot resilience — mount.service + vault@.service 양쪽 자동 진입** + timer `Persistent=true` catch up | OCI 인스턴스 강제 reboot 후 5분 내 mount + timer fire + last_sync.json 진행 | **v0.1.0 acceptance** (v2 — mount 의존 추가) |
| **V13** | rclone mount 가 `<instance_root>/vault/<vault_id>/` 에 정상 마운트 + SSH 에서 ls/cat 가능 | OCI 에서 `systemctl start wikihub-mount@<vid>` 후 `ls`/`cat` | 사용자 입력 채널·실시간 UX 충족 (v2 신규) |
| **V14** | mount.service Restart=always — daemon 죽었을 때 자동 재기동 | 의도적 `kill <rclone pid>` 후 30s 내 재기동 + vault 폴더 접근 복구 관찰 | 장애 격리 (v2 신규) |
| **V15** | **race window 차단 — gws changes 의 modifiedTime ↔ mount stat mtime 정합** | Drive 에서 파일 수정 직후 5s 내 `gws drive changes list` + `rclone rc vfs/refresh` + mount read → content 정합 확인 (수정 전후 두 사이클 모두) | 정합성 정본 — v2 핵심 (v2 신규) |
| **V16** | rclone version pinning + 채널 (apt vs binary) 선택 | `rclone version` + 채널별 비교 → ADR-0025 정본화 | install.sh 안정성 (v2 신규) |

V4·V6 결과로 ADR-0015·ADR-0017 정본 status (`Accepted`) 전환 (v1 그대로). V13~V16 결과로 ADR-0025·0026·0027 정본 status 전환 (v2 신규). V15 fail 시 race window 차단 design 재설계 — 옵션: per-file `vfs/refresh file=X` 우회 또는 `--dir-cache-time` 단축 fallback. Step 2 도중 surface 가능성 명시.

---

## 운영 환경 가정

v1 의 전제 모두 유지. v2 추가:

- OCI ARM Ubuntu 22.04 또는 24.04 (LTS)
- systemd 사용 가능 — user unit + linger 또는 system-level unit 중 Step 2 결정 (ADR-0021)
- Python 3.11 또는 3.12 apt 설치 가능
- gws · rclone 둘 다 ARM Ubuntu 에서 동작 (V6·V16 확인)
- 외부 네트워크 (Google API, PyPI, rclone download) 도달 가능
- **FUSE 사용 가능** — Ubuntu 22.04/24.04 기본 포함. systemd 권한으로 `/dev/fuse` 접근 가능 (v2 신규)
- mount path (`<instance_root>/vault/<vault_id>/`) 가 다른 프로세스에 의해 사용 중이지 않음 — install.sh 가 pre-check (v2 신규)
- Google Drive OAuth 2회 발급 — gws · rclone 각각 1개씩 (같은 Google 계정이라도 token 분리, setup.md 가 절차 명시) (v2 신규)

---

## 생성 예정 ADR

v1 의 ADR 모두 유지 (supersede 없음). v2 추가 3건:

| ID | Title | 발의 트리거 | v1/v2 |
|---|---|---|---|
| ADR-0015 | gws version pinning 값 | V6 verification 후 | v1 — Accepted |
| ADR-0017 | gws stderr 패턴 매칭 표 | V4 verification 후 | v1 — Accepted |
| ADR-0021 | reboot resilience 전략 — user-level + linger vs system-level + (v2 갱신) mount.service 의존 | v1 plan 발의 + v2 본문 갱신 | v1 — Accepted (v2 본문 갱신만, supersede 아님) |
| ADR-0022 | 첫 ingest 실행 진입점 — install.sh vs `wh:setup` | v1 plan 발의 | v1 — Accepted |
| ADR-0023 | install.sh 배포 모델 — curl-pipe one-liner | v1 Step 2 v3 발의 | v1 — Accepted |
| ADR-0024 | fatal alert contract — last_failure.json + Hermes 이중 경로 | v1 Step 2 v5 발의 | v1 — Accepted |
| **ADR-0025** | **rclone mount 채택 — vault 자체 마운트 + vfs cache 정책** | **v2 plan 발의 확정** | v2 신규 |
| **ADR-0026** | **vfs refresh 정책 — 사이클 시작 시 1회 refresh + race window 차단** | **v2 plan 발의 확정** (Step 2 에서 recursive vs per-file 결정) | v2 신규 |
| **ADR-0027** | **rclone vs gws 책임 분리 — Path C+ 정본화** | **v2 plan 발의 확정** | v2 신규 |

ADR-0014 (gws CLI 채택) 는 supersede 없음 — v2 에서도 변경 감지의 정본은 gws.

---

## 입력 자료

v1 의 입력 자료 모두 유지. v2 추가:

- `features/20260514_install_runtime/rclone_vs_gws_comparison.md` — Path C+ 결정 근거 (2026-05-15, 동일 디렉토리)
- rclone Drive backend docs — https://rclone.org/drive/ (backend command 목록 — `changes` 명령 부재 근거)
- rclone lsf docs — https://rclone.org/commands/rclone_lsf/ (--max-age 동작)
- Google Drive API changes overview — https://developers.google.com/workspace/drive/api/guides/change-overview (changeType · removed · trashed 정본)
- googleworkspace/cli — https://github.com/googleworkspace/cli/tree/main/skills/gws-drive (Drive Changes resource 명시)

v1 입력 (참조 유지):
- F3 archive `analysis_and_design.md` §2.2~§2.4 / §4
- F3 `scripts/vault-fetch.py` · `scripts/lib/*`
- F2 `_system/commands/setup.md`
- ADR-0003 · 0014 · 0006 · 0012

---

## 사전 조건 / 운영 가정

v1 유지:

- 메인테이너 dev box (macOS) 에서 install.sh draft 작성·검증
- 별도 PC 또는 OCI ARM Ubuntu test instance 에서 V4·V6·V8·V10·V11·V12·V13·V14·V15·V16 실수행
- Test Workspace + `wikihub-test/` 폴더 (F3 L2 fixture) 재사용

---

## Definition of Done (Step 1 단계 기준)

본 plan.md v2 의 적용 단계 선언 + 영향 범위 + V<N> 목록 + 생성 예정 ADR 표를 사용자가 승인하면 Step 1 v2 종료. Step 2 (`analysis_and_design.md` v7) 진입.

## Definition of Done (feature 전체 — Step 5 완료 기준, v2 갱신)

v1 의 DoD 항목 모두 유지. v2 추가:

v1 항목 (유지):
- [ ] install.sh 가 clean ARM Ubuntu instance 에서 1회 실행으로 wikihub 가 sync 사이클까지 자동 진입 (V8 + V10)
- [ ] install.sh idempotent — 두 번째 호출이 state 손상 없음 (V11)
- [ ] **OS reboot 후 사람 개입 없이 timer fire + 첫 사이클 완료 + last_sync.json 진행** (V12 — v0.1.0 acceptance)
- [ ] install/setup 흐름 마지막에 "첫 ingest 실행 여부" prompt (대화형 default `Y` + 비대화형 flag)
- [ ] exit 75 systemd timer Restart, exit 2 재시도 안 함 (V10)
- [ ] ADR-0015·0017·0021·0022·0023·0024 Status=`Accepted`
- [ ] Step 4 멀티모델 code review 결함 모두 처리 — CRIT·HIGH 0건
- [ ] HISTORY.md 항목 추가 + ADR 참조 + archive 이동

v2 추가:
- [ ] **rclone mount 가 `<instance_root>/vault/<vault_id>/` 에 정상 마운트** + SSH 에서 ls/cat 가능 (V13)
- [ ] **mount.service Restart=always — daemon 자동 복구** (V14)
- [ ] **race window 차단 검증 — gws changes 의 modifiedTime ↔ mount stat mtime 정합** (V15 — v2 핵심)
- [ ] **rclone version pinning + 채택 채널 (apt vs binary) lock** — ADR-0025 Accepted (V16)
- [ ] **mount.service + vault@.service 의 reboot 후 자동 진입** (V12 갱신)
- [ ] **ADR-0025 (rclone-mount), ADR-0026 (vfs refresh 정책), ADR-0027 (책임 분리) Status=`Accepted`**
- [ ] Step 4 v2 멀티모델 code review (R11·R12) 결함 처리 — CRIT·HIGH 0건
