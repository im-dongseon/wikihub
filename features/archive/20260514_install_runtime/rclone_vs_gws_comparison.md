# rclone vs gws — Drive 접근 메커니즘 비교 검토

- **작성일**: 2026-05-15
- **목적**: F4 install_runtime Step 2 복귀 결정에 따라, ADR-0014 (gws 채택) supersede 여부 판단 자료
- **범위**: F3·F4 산출물의 **Drive 접근 메커니즘만**. 그 외 architecture (systemd 구조, ingest contract, ADR-0006 unified orchestration 등) 은 변경 없음 전제
- **상태**: draft — 사용자 검토 후 결정. 결정 후 본 문서는 archive 보존 (영속 의사결정 자료)

## 1. 두 방식의 기본 모델

### gws (현재 정본 — ADR-0014)

- `gws drive changes list --params '{"pageToken": cursor}'` → 증분 변경 목록
- `gws drive files get --params '{"fileId": fid, "alt": "media"}'` → 바이너리 다운로드
- `gws drive files export --params '{"fileId": fid, "mimeType": "text/markdown"}'` → Google native export
- 모두 subprocess 호출 + JSON I/O. **stateless** — 호출 종료 시 메모리 해제
- 환경변수 `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` 로 OAuth credentials 주입

### rclone (사용자 제안)

- **Track A** `rclone mount gdrive: /home/ubuntu/google_drive --vfs-cache-mode full` → FUSE 마운트, 백그라운드 상시
- **Track B** `rclone lsf gdrive: --max-age 10m --recursive --files-only` → 시각 기반 변경 리스트
- 다운로드: mount FS 통한 read 또는 `rclone copy <remote> <local>`
- Google native: `rclone --drive-export-formats markdown copy ...` 또는 mount의 자동 export
- 인증: `rclone config` interactive (내장 OAuth flow)

## 2. 차원별 비교 매트릭스

| 차원 | gws (현재) | rclone (검토) | 차이 영향도 |
|---|---|---|---|
| Drive 접근 모델 | API subprocess (stateless 호출) | FUSE mount (stateful daemon) + lsf | **HIGH** — 운영 모델 자체가 다름 |
| 변경 감지 | `changes.list` cursor 기반 증분, 정확 | `lsf --max-age` 시각 기반, 윈도우 drift 위험 | **HIGH** — F3 cursor state 의미 변경 |
| 삭제 감지 | `changes.list` 가 `trashed`/`removed` 명시 | lsf 가 명시 안 함 (사라진 파일은 list 에서 빠질 뿐) | **HIGH** — F3 `deleted[]` 생성 로직 재설계 |
| 인증 | env var + `scripts/auth_gdrive.py` (수동 OAuth) | `rclone config` interactive (내장 OAuth) | MED — auth_gdrive.py 폐기, rclone config 절차 신설 |
| 에러 분류 | exit code 0~5 + stderr regex (ADR-0017) | exit code 0~9 (https://rclone.org/docs/#exit-code) | MED — `errors.py` 재작성, ADR-0017 supersede |
| 파일 다운로드 | `gws files get alt=media` → stdout bytes | mount FS read 또는 `rclone copy` | MED — sync.py 다운로드 헬퍼 변경 |
| Google native export | `gws files export mimeType=...` | rclone mount + `--drive-export-formats` (mime별 자동) | MED — extraction.py 매핑 검토 |
| 메타데이터 | gws JSON (mimeType, modifiedTime, md5Checksum, parents) | `rclone lsjson` (ModTime, Size, MimeType, ID) | LOW — 필드 매핑만 |
| Pagination | gws `nextPageToken` (호출자 책임) | rclone 내부 처리 (사용자 비노출) | LOW — 단순화 효과 |
| 운영 복잡도 (인프라) | binary 1개 + venv | mount daemon (FUSE 의존) + cache 관리 + 추가 unit | **HIGH** — `wikihub-mount.service` 신규 |
| 캐시 관리 | 없음 (호출마다 다운로드, vault local copy 만 누적) | `--vfs-cache-mode full` + `--vfs-cache-max-size` | MED — 디스크 용량 정책 신규 |
| reboot resilience (V12) | systemd timer 만 fire 보장 (stateless) | mount.service 자동 재기동 + timer fire 2-unit 협조 | MED — V12 검증 케이스 1건 추가 |
| F3 산출물 재사용도 | 100% | ~60% (gws.py·errors.py·credentials.py 교체, sync.py 부분 수정) | — |
| 성숙도 | alpha (v0.x — breaking change 가능) | stable (v1.x — 장기 운영 실적) | **HIGH** — ADR-0014 알파 우려 정면 해소 |
| version pinning | `operations.gws_min_version` (ADR-0015) | rclone apt/binary pin (동등 방식 가능) | LOW |
| Workspace 확장 (Sheets·Chat 등) | gws 가 모두 cover | rclone 은 Drive 전용 | MED — F4 이후 확장 제약 |
| Google 공식성 | Workspace 조직 산하 (비공식) | 서드파티 (다중 클라우드 추상화) | 동등 |

## 3. 핵심 쟁점

### (1) 변경 감지 모델 — cursor vs --max-age

gws `changes.list` 는 cursor 기반 — **마지막 동기화 이후 모든 변경**을 정확히 가져온다. 사이클 1회 누락돼도 다음 사이클이 누락분 catch up. F3 `sync.py` 가 이 모델을 전제로 짜여 있다.

rclone `lsf --max-age 10m` 은 **상대 시각** — 현재 시점 기준 10분 이내 modified 파일만. timer 주기와 --max-age 가 정확히 정합되지 않으면:
- timer 주기 < --max-age: 중복 처리 (file_map 으로 idempotency 보장 가능)
- timer 주기 > --max-age: **변경 누락** (위험)
- timer 미 fire (reboot 중): catch up 안 됨 (--max-age 윈도우가 reboot 기간을 cover 못 함)

**대안**: rclone 에 `rclone changes <remote>` 가 있을 가능성 — Drive native changes API 노출 여부 검증 필요. 있다면 gws 와 동등 모델. 없다면 시각 윈도우 + file_map full diff 로 보완.

### (2) 삭제 감지 — architectural mismatch

gws `changes.list` 는 `trashed: true` 또는 `removed: true` 를 명시. F3 `sync.py` 가 이걸로 `deleted[]` 리스트 생성, vault local copy + wiki page 삭제.

rclone lsf 는 **현재 존재하는 파일만** 반환. 삭제 이벤트가 명시 없음. 대응 옵션:

| 옵션 | 방법 | 비용 |
|---|---|---|
| (a) 매 사이클 전체 lsjson + file_map diff | full list 가져와 비교 | bootstrap 비용 (수만 파일 시 부담) |
| (b) mount FS 를 inotify 감시 | mount 의존, FUSE inotify 신뢰성 확인 필요 | mount 의존성 강제 + 별도 메커니즘 |
| (c) `rclone changes` (있다면) | gws 와 동등 | rclone 의 changes 명령 노출 검증 필요 |
| (d) 삭제 감지 포기 (v0.1.0) | wiki 에 stale page 잔존 허용 | UX 결함, 후속 ADR 필요 |

(c) 가능성이 가장 안전. 검증 전에는 **HIGH 위험**.

### (3) mount 의 stateful 특성과 reboot resilience

gws 는 호출마다 새 subprocess → 완전 stateless. systemd timer 가 fire 하면 그만.

rclone mount 는 **상시 살아있어야** Track A 동작:
- `wikihub-mount.service` (Type=simple, Restart=always) 신규 필요
- mount 가 죽으면 mount-dependent 명령 (cat, ls 등) 도 같이 죽음
- reboot 후 mount.service → timer 순서 보장 필요 (`After=wikihub-mount.service` 의존)
- **V12 검증 시나리오 1건 추가**: reboot 후 mount 재기동 → vault 폴더 접근 → timer fire 의 end-to-end 검증

다만 **Track B 의 lsf 는 remote 직접 호출** (`gdrive:` 가리킴) 이라 mount 와 무관. **자동화만 본다면 mount 불필요** — 사용자가 mount 를 도입하려는 이유는 **SSH 접속 시 ls/cat 편의** 로 추정됨 (사용자 메시지 §1 "Track A: 실시간 사용 (Mount 방식)").

### (4) F3 산출물 재사용도

| F3 파일 | rclone 전환 시 영향 | 재사용률 |
|---|---|---|
| `scripts/lib/gws.py` | **교체** → `rclone.py` (subprocess wrapper) | 0% |
| `scripts/lib/errors.py` | **재작성** (exit code 0~9 매핑) | 0% |
| `scripts/lib/sync.py` | **부분 수정** — changes.list 호출부, deleted 생성 로직, 다운로드 헬퍼 (~30%) | 70% |
| `scripts/lib/state.py` | 유지 (cursor 의미만 변경 — token → 시각 또는 rclone changes token) | 95% |
| `scripts/lib/extraction.py` | 유지 (mime 매핑은 동일) | 100% |
| `scripts/lib/credentials.py` | **교체** — env var → rclone config 경로 검증 | 30% |
| `scripts/lib/config.py` | yaml 옵션 일부 추가/제거 | 90% |
| `scripts/vault-fetch.py` | import 교체 + 일부 호출 변경 | 85% |
| `tests/test_*` | gws·errors·sync 관련 ~30% 재작성 | 70% |

전체 평균 ~60% 재사용. **~40% 재작성 비용**.

### (5) ADR cascade

| ADR | rclone 전환 시 영향 |
|---|---|
| **ADR-0014** (gws CLI 채택) | **Superseded** — 신규 ADR (rclone 채택) |
| **ADR-0015** (gws version pinning) | **Superseded** — 신규 ADR (rclone version pin) |
| **ADR-0017** (gws stderr 패턴) | **Superseded** — 신규 ADR (rclone exit code 매핑) |
| **ADR-0003** (headless OAuth) | **부분 supersede** — rclone config 절차로 변경 |
| ADR-0004 (Direct Drive API, 이미 superseded by 0014) | 영향 없음 |
| ADR-0006 (unified orchestration) | 영향 없음 (subprocess 패턴 유지) |
| ADR-0021 (reboot resilience) | 영향 작음 (mount.service 추가 시 보완) |
| ADR-0022 (first ingest entry point) | 영향 없음 |
| ADR-0023 (curl-pipe install 모델) | 영향 작음 (install.sh 내용만 변경) |
| ADR-0024 (fatal alert contract) | 영향 없음 |
| **신규 ADR** | rclone 채택, version pin, exit code 매핑, mount unit 여부, 변경/삭제 감지 메커니즘 → **5~6건** |

**3~4건 supersede + 5~6건 신규** = 메소드론 §7 cascade 비용.

## 4. 차원별 잠정 평가

| 차원 | gws | rclone | 우위 |
|---|---|---|---|
| 변경 감지 정확성 | cursor 기반 정확 | --max-age 윈도우, drift 위험 | **gws** |
| 삭제 감지 | changes.list 명시 | 별도 메커니즘 필요 | **gws** |
| 운영 안정성 (성숙도) | alpha (운영 부담) | stable (v1.x, 광범위 사용) | **rclone** |
| 운영 복잡도 (인프라) | binary 1개 + venv | mount daemon + cache + 추가 unit | **gws** |
| 인증 UX | 수동 OAuth (auth_gdrive.py) | rclone config interactive | **rclone** |
| 디스크 사용 | vault local copy 만 | + vfs cache 누적 | **gws** |
| F3 산출물 재사용 | 100% | ~60% | **gws** |
| ADR supersede 비용 | 0건 | 3~4건 supersede + 5~6건 신규 | **gws** |
| 운영자 SSH UX | 없음 (file_map JSON 만) | mount 폴더로 ls/cat 가능 | **rclone** |
| Workspace 확장성 (Sheets·Chat 등) | gws 단일 도구 | Drive 전용 | **gws** |
| Google 공식성 | Workspace 조직 산하 | 서드파티 | 동등 |

## 5. 세 갈래 권고

### Path A — gws 유지 (현 정본 직진)

**조건**: F3 검증 단계 (V4 stderr 패턴 · V6 version pin · V8 deps) 가 큰 결함 없이 통과 가능.

- F4 분량 추가 없음, ADR cascade 없음, Step 5 직진
- alpha 우려는 ADR-0014 에서 인지 + version pin 으로 격리
- 운영자 SSH UX 는 별도 보강 (예: `scripts/vault-browse.sh` 등) 가능

### Path B — rclone 전체 전환 (사용자 초안)

**조건**: gws alpha 부담을 운영 시작 전 회피하고자 함 + rclone 의 다목적성 (mount UX + 자동화) 둘 다 활용.

- ADR 3~4건 supersede + 5~6건 신규
- F3 코드 ~40% 재작성
- **변경 감지·삭제 감지의 architectural mismatch 해소 방안 (rclone changes 노출 여부) 검증 필수**
- mount + lsf 둘 다 운영, wikihub-mount.service 추가

### Path C — 하이브리드 (자동화 = gws, UX = rclone mount)

**조건**: 사용자가 rclone 을 도입하려는 주된 동기가 **운영자 SSH 편의 (ls/cat)** 이고, 자동화 정확성은 그대로 유지하고 싶을 때.

- 자동화 (sync, ingest) 는 gws 유지 → 변경/삭제 감지·F3 재사용도·ADR 모두 보존
- mount 는 **운영자 편의 only** → `wikihub-mount.service` (Type=simple, Restart=always) 만 추가
- F4 변경 분량: install.sh 에 rclone install + mount.service unit 1개 신설
- ADR cascade: rclone-mount 채택 (1건 신규) 만, 기존 ADR supersede 없음

**잠정 평가**:
- 사용자 메시지 §1 "투 트랙 운영 구조" 의 가치는 (a) 실시간 mount UX + (b) lsf 의 빠른 변경 추출
- (b) 의 빠른 변경 추출은 **gws changes.list 도 동등** 한 속도 (둘 다 API 직접) — Track B 만으로는 rclone 채택 동기가 약함
- (a) 만이 rclone 의 차별적 가치 → **Path C 가 trade-off 최적**

## 6. 결정 후 후속 작업

### Path A 선택 시
F4 Step 5 직진 — 본 비교 검토는 archive 보존.

### Path B 선택 시
1. `analysis_and_design.md` v7 — rclone 기반 전면 개정
2. 신규 ADR 5~6건 발의 (rclone 채택, version pin, exit code 매핑, mount unit, 변경/삭제 감지)
3. ADR-0014/0015/0017/0003 supersede 처리
4. Step 3 재구현 (gws.py·errors.py·credentials.py 교체, sync.py·credentials.py 수정, tests 재작성)
5. Step 4 재리뷰, Step 5 배포
6. **선행 검증**: `rclone changes` 노출 여부 + 삭제 감지 메커니즘 PoC

### Path C 선택 시
1. `analysis_and_design.md` v7 — minor revision (mount unit 추가, install.sh 에 rclone install 보강)
2. 신규 ADR 1~2건 (rclone-mount 채택, UX/자동화 책임 분리)
3. Step 3 보강 (install.sh + `wikihub-mount.service` 신규)
4. Step 4 신규 부분만 review
5. Step 5 배포

## 7. 미결 — 사용자 결정 항목

| 질문 | 선택지 |
|---|---|
| Q1. rclone 도입 동기 | (a) 운영자 SSH UX, (b) gws alpha 회피, (c) 둘 다 |
| Q2. Path 결정 | A / B / C |
| Q3. (Path B/C 선택 시) mount unit 책임 — vault 별 instantiated vs 단일 | 단일 (`wikihub-mount.service`) 권고 — vault 별이 늘면 mount point 폭증 |
| Q4. (Path B 선택 시) 변경 감지 메커니즘 — `rclone changes` PoC 선행 여부 | PoC 우선 / 시각 윈도우 + diff 로 시작 |
