# Plan — OAuth 통일 + gws 폐기 (rclone 단독 인증·변경 감지)

- **Feature ID**: 20260519_oauth_unify_rclone_only
- **시작일**: 2026-05-19 (KST)
- **계기**: `features/backlog.md` §I — w2a → rclone(OAuth) 업로드가 gws(SA) `changes.list` 에 미감지. 인증 주체 비대칭이 근본 원인.

## 배경 요지

ADR-0029 (SA 채택) 가 "Workspace 마이그레이션 의존 제거" 목적으로 도입됐으나, **Personal Drive 에서 SA 는 storage quota 미할당 — write 불가** (`403 storageQuotaExceeded`, 2026-05-19 실증). 양방향 동기화(w2a 등 쓰기 흐름) 가 등장한 시점에 SA 모델 자체가 깨짐. Personal Google 운영 환경에서는 **OAuth 가 유일 선택**.

추가로 §검토 결과 (대화 전사 참조):
- rclone 의 OAuth client (기본값) 는 이미 Production 검증 통과 → 7일 refresh 문제 자체 부재
- `rclone lsjson` 출력에 `ID` (Drive fileId) + `MimeType` 노출 확인 (2026-05-19 OCI 실증) → **gws `changes.list` 의 정보를 lsjson + file_map(source_id 키) diff 로 등가 대체 가능**
- `rclone backend changes` 명령 부재는 v1.69.1 에서도 그대로 — full lsjson + diff 가 정본 메커니즘

→ ADR-0014 (gws CLI 채택) · ADR-0027 (rclone vs gws 책임 분리) · ADR-0029 (SA) 의 cascade 를 **rclone 단독 + OAuth 단독 + lsjson diff** 로 단순화.

## 작업 분류

**복합**: 큰 refactor (코드 ~수백 줄 변경) + ADR cascade (5건 supersede + 1건 신규) + 인프라 갱신 (install.sh / systemd / yaml.example).

## 적용 단계 선언

| Step | 수행 여부 | 사유 |
|---|---|---|
| Step 1 Plan | ✅ 수행 | 본 문서 |
| Step 2 Analysis & Design | ✅ 수행 | 큰 refactor + ADR cascade → 설계 정본 필수 |
| Step 3 Implementation | ✅ 수행 | 코드 변경 본체 |
| Step 4 Review | ✅ **수행** | 변경 크기·외부 인터페이스 영향 (credentials_path 의미 변경, install.sh, systemd unit) 모두 검토 기준 위반 → 멀티 리뷰어 필수 |
| Step 5 Deployment | ✅ **수행** | `_system/` + `scripts/` + `install.sh` + systemd unit 모두 변경 → 운영 반영 필수. HISTORY.md 항목 추가 + archive 이동 포함 |

## 예상 영향 범위

### 코드 (active)
- `scripts/lib/sync.py` — 재작성 (gws subprocess → rclone lsjson diff)
- `scripts/lib/gws.py` — **삭제**
- `scripts/lib/errors.py` — **삭제** (gws exit code 매핑)
- `scripts/lib/credentials.py` — 재구성 (SA JSON 검증 → rclone.conf 검증으로 일원화)
- `scripts/lib/mount_diff.py` — **신규** (lsjson 호출 + file_map diff)
- `scripts/vault-fetch.py` — 호출 흐름 갱신 (assert_credentials → assert_rclone_config 일원화)

### 정본 문서
- `_system/wiki-schema.md` — Google native export 표 (gws → rclone export-formats)
- `_system/commands/setup.md` — Step 1 gws 단계 폐기, gws_min_version 항목 폐기
- `_system/commands/ingest.md` — Step 2 흐름 갱신 (lsjson 기반)
- `_system/systemd/wikihub-vault@.service` — `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` Env 제거

### 인프라·설정
- `install.sh` — gws 다운로드/설치 단계 (`_step5_gws_install` 등) 제거. ADR-0015/0017 정합 폐기
- `wikihub.yaml.example` — `credentials_path` 키 의미 변경 또는 폐기. `gws_min_version` 폐기

### 테스트
- `tests/test_gws.py` — **삭제**
- `tests/test_sync.py` — 재작성 (mount_diff 기반)
- `tests/test_credentials.py` — rclone.conf 검증 테스트로 전환
- `tests/test_mount_diff.py` — **신규**

### ADR cascade
| ADR | 변경 |
|---|---|
| ADR-0014 (gws CLI 채택) | `Accepted` → `Superseded by ADR-0035` |
| ADR-0015 (gws pinned version) | `Accepted` → `Superseded by ADR-0035` |
| ADR-0017 (gws stderr 매핑) | `Accepted` → `Superseded by ADR-0035` |
| ADR-0027 (rclone vs gws 책임 분리) | `Accepted` → `Superseded by ADR-0035` |
| ADR-0029 (SA 인증) | `Accepted` → `Superseded by ADR-0035` |
| ADR-0035 (rclone-only unified OAuth) | **신규** Accepted |

## 메소드론 적용

- **적용**. trivial 변경 아님 (5건 ADR supersede + 코드 ~수백 줄).
- §3 Step 1~5 전부 수행. Step 4 의 멀티 리뷰어는 서브에이전트 2건 (설계 정합 1건 + 코드 정합 1건).
- Karpathy §2 Simplicity First 정합: 본 feature 자체가 두 도구 → 한 도구 단순화. 신규 abstraction 도입 없음 — 기존 `_run` (gws subprocess) 자리에 `_lsjson` 한 함수 교체.

## 비-목표 (Out of scope)

- Google native (`.gdoc`/`.gsheet`/`.gslides`) 본격 검증 — OCI vault 에 실제로 없음 (2026-05-19 실증). `_NATIVE_MIME_TO_EXT` 매핑은 유지하되 실증/테스트는 v0.2.x deferred
- Workspace 전환 또는 OAuth Production 검증 신청 — rclone 기본 client 가 이미 Production. 본 feature 의 전제로 둠 (재검토 트리거: rclone 기본 client 의 정책 변경)
- file_map schema migration tooling — v0.1.0 미배포 시점이라 운영자 base 영향 0. 빅뱅 후 first-run 이 모든 파일 created 로 처리

## DoD 미리보기 (Step 2 에서 확정)

- [ ] rclone lsjson `gdrive:` 호출 + `--recursive` + ID·MimeType·ModTime 파싱
- [ ] file_map primary key 가 source_id (fileId) 로 재설계 — rename 정확 추적
- [ ] false-deleted 가드 — listing 0건 또는 삭제율 > 임계치 시 abort
- [ ] cursor 모델 폐기 — `state.py` 의 `load_cursor`/`save_cursor` 제거, `bootstrap_allowed` yaml key 폐기
- [ ] systemd unit 의 gws env 제거 + install.sh 의 gws 단계 제거
- [ ] ADR-0035 신규 + 5건 Status Superseded 갱신
- [ ] OCI 실배포 검증: w2a → article/ 업로드 → 다음 vault-fetch 사이클에서 정상 감지 (이슈 I 자체 해소 실증)
