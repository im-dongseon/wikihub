# ADR-0035: rclone 단독 + OAuth 단일 인증 — gws CLI 폐기 + SA 폐기

- **Status**: Accepted
- **Date**: 2026-05-19
- **Feature**: features/20260519_oauth_unify_rclone_only
- **Supersedes**: ADR-0014, ADR-0015, ADR-0017, ADR-0027, ADR-0029
- **Superseded by**: 없음

## Context

ADR-0014 (gws CLI 채택) · ADR-0027 (rclone vs gws 책임 분리, Path C+) · ADR-0029 (Service Account 인증) 의 cascade 가 v0.1.0 운영 진입 직전(2026-05-19) OCI 검증에서 두 결함 surface (`features/backlog.md` §D·§I):

### 결함 1 — Personal Drive 에서 SA write 불가

ADR-0029 §Decision L50 이 "SA 이메일을 vault 폴더에 Editor 공유 (rclone mount 의 write 가정 위한)" 명시하고 §부정/제약 L79 가 "SA 가 ownedBy 가 될 수 없음 — read/write 는 가능하나 Storage 는 항상 메인테이너 계정 quota. v0.1.0 의 vault polling/mount 시나리오는 OK" 로 둘 다 적었지만, **실증 결과 Personal Drive 에서 SA 는 storage quota 미할당 → 모든 write 가 `403 storageQuotaExceeded`** (백로그 §D 근본 원인).

ADR-0029 채택 시점엔 polling/read 만 가정. w2a (write-to-article) 같은 쓰기 흐름이 surface 한 시점에 모델 자체가 깨짐.

### 결함 2 — 인증 주체 비대칭으로 changes feed 단절

백로그 §D 대처로 rclone 을 긴급히 OAuth 로 전환 (rclone.conf 의 `service_account_file` → `token` 교체). 결과 시스템 인증 주체:

- rclone: OAuth user (`dngsn.im@gmail.com`)
- gws: SA (`oci-hermes-sa@…`)

Drive `changes.list` 는 **user-scoped feed** — 호출 주체의 changes 만 반환. SA 가 자신의 cursor 로 호출하면 OAuth user 의 변경은 별도 feed 라 미포함. 결과 (백로그 §I): w2a 가 rclone mount(OAuth) 로 업로드한 5건이 vault-fetch (SA gws) 사이클 2회 후에도 `changes.list` 반환 0건 → wiki ingest 실패.

### 결함 3 — gws alpha 의존성의 누적 부담

ADR-0014 §부정/제약 가 식별한 부담이 v0.1.0 운영 진입 시점에 누적 surface:

- alpha 의존성 (백로그 §I 와 별개로 V<N> Phase 2 결함 #8 — `get-start-page-token` → `getStartPageToken` subcommand 명명 변동)
- ADR-0017 의 stderr 매핑 표가 gws 버전마다 갱신 필요 — v0.1.0 정합 표를 만들지 못한 채 Proposed 상태로 동결
- Discovery 동적 빌드 latency 의 first-call 부담

### 실증 (2026-05-19 OCI)

rclone v1.69.1 의 `rclone lsjson gdrive:` 출력이 다음 두 필드를 노출:

- `ID` (Drive fileId) — file_map primary key 로 rename 추적 가능
- `MimeType` (Drive 원본 mimeType) — Google native 분기 가능

→ **gws `drive changes list` 의 정보 중 wikihub 가 사용하는 부분은 lsjson 전체 listing + file_map(source_id 키) diff 로 등가 대체 가능**.

`rclone backend help drive` 의 명령 목록 (get/set/shortcut/drives/untrash/copyid/exportformats/importformats/query/rescue) 에 `changes` 부재 — ADR-0027 §Context 의 v9 진단이 v1.69.1 에서도 그대로 유효 → cursor 기반 증분이 아닌 **lsjson full snapshot diff** 가 정본 메커니즘.

## Considered Options

### (α) 도구 구성

- (α1) ADR-0027 Path C+ 유지 + SA → OAuth 만 전환 (gws/rclone 둘 다 OAuth)
- **(α2) gws 폐기 + rclone 단독화** — 본 ADR 채택
- (α3) Workspace 전환 후 ADR-0029 유지 + ADR-0027 유지

### (β) 변경 감지 메커니즘

- (β1) mount FS walk (`os.walk(vault_local_path)`) — fileId 노출 안 됨 → rename 추적 불가, false-deleted 위험 큼
- **(β2) `rclone lsjson <remote>: --recursive`** — Drive API files.list backend 호출. ID/MimeType 노출 — 본 ADR 채택
- (β3) `rclone backend changes` — 부재 (v1.69.1)
- (β4) `rclone lsf --max-age 1d` — 시각 윈도우, 삭제·reboot catch-up 부정확

### (γ) state schema

- (γ1) file_map primary key 를 `source_relpath` 유지 (현행)
- **(γ2) primary key 를 `source_id` (Drive fileId) 로 재설계** — 본 ADR 채택

### (δ) cursor 모델

- (δ1) cursor.json 유지 — 매 사이클의 lsjson 호출에 cursor 의미 부재. dead field
- **(δ2) cursor 모델 폐기** — `state.py` 의 cursor 함수 4개 및 yaml 의 `bootstrap_allowed` 키 폐기

### (ε) 인증 자료

- (ε1) SA JSON + rclone.conf 병존 (현행)
- **(ε2) rclone.conf 단독** — `credentials_path` yaml key 폐기, gws env 폐기

### (ζ) false-deleted 가드

- (ζ1) 가드 없음 — mount/auth 부분 장애 시 wiki 대량 삭제 위험
- **(ζ2) 삭제 비율 임계치 + listing 0건 가드** — 본 ADR 채택. default 0.3 (30%), yaml override 가능

> 옵션 상세 비교는 [features/20260519_oauth_unify_rclone_only/analysis_and_design.md](../../features/20260519_oauth_unify_rclone_only/analysis_and_design.md) §2~§5 참조.

## Decision

**채택**: (α2) + (β2) + (γ2) + (δ2) + (ε2) + (ζ2).

### ADR-0027 §Considered Options L1 기각 사유 재평가

ADR-0027 이 (L1) rclone 단독을 4가지 사유로 기각했으나, lsjson 의 ID·MimeType 노출이 입증된 시점에 모두 무력화 또는 등가 대체 가능:

| ADR-0027 기각 사유 | 재평가 | 본 ADR 의 대체 메커니즘 |
|---|---|---|
| 삭제 이벤트 미감지 | 무력화 | listing 의 ID 가 file_map 에 없으면 deleted. false-delete 가드 추가 |
| 권한 변경 미감지 | 무력화 | vault 폴더 trust boundary 외 권한 변경은 관심사 아님. 폴더 내 unshare 는 mount/listing 에서 사라짐 → deleted 로 처리 |
| reboot 기간 catch-up 불가 | 오히려 단순화 | full snapshot 은 항상 현재 상태 정확 — cursor catch-up 자체가 불요 |
| cursor 기반 정확성 부재 | 등가 | "현재 listing vs file_map" diff 도 동등 정확성. 메커니즘만 다름 |

### 책임 매트릭스 (After)

| 영역 | rclone |
|---|---|
| Drive ↔ 로컬 실시간 sync | mount daemon (`wikihub-mount@.service`) — ADR-0025 그대로 |
| 변경 감지 (메타데이터) | `rclone lsjson <remote>: --recursive` (Drive API files.list backend 호출) |
| 파일 read (다운로드) | mount FS `open()` (vfs cache) — ADR-0025 Path C+ 의 다운로드 영역 그대로 |
| Google native export | mount template `--drive-export-formats docx,xlsx,pptx,md` — ADR-0025 그대로 |
| 인증 | rclone.conf 단일 (OAuth token) |
| systemd unit | `wikihub-mount@.service` (Type=simple) + `wikihub-vault@.service` (Type=oneshot, timer) — ADR-0025/0019 그대로 |

### state schema 갱신

- `file_map.json` primary key 가 `source_id` (Drive fileId). value: `{source_relpath, source_mtime, wiki_path, bytes, last_synced_at}`
- `cursor.json` 폐기 — `state.py` 의 `initial_cursor`/`load_cursor`/`save_cursor`/`has_cursor` 4개 함수 제거
- `last_sync.json` 의 `cursor_before`/`cursor_after` 필드 제거 (또는 `listing_count_before`/`listing_count_after` 로 대체)
- `retry.json`, `last_failure.json`, `pending_ingest.json` 그대로 (ADR-0024 정합)

### false-deleted 가드

- yaml `vault.options.false_delete_threshold` (default 0.3)
- 한 사이클의 `delete_ratio = deleted_count / file_map_count_before` 이 threshold 초과 시 → `VaultSyncRetryable` (exit 75, retry_after=300s)
- listing 0건 + file_map 비어있지 않음 → 동일하게 Retryable
- 연속 retry 발화 시 ADR-0024 last_failure writer 가 escalate (기존 흐름 그대로)

### 인증 자료 단일화

- `wikihub.yaml.vaults[*].options.credentials_path` 키 폐기 — rclone.conf 가 단일 자료
- systemd unit 의 `Environment=GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=...` 제거
- `Environment=RCLONE_CONFIG=...` 만 유지 (install.sh 가 주입)
- `scripts/lib/credentials.py` 의 `assert_credentials` 폐기, `assert_rclone_config` 유지
- `scripts/lib/credentials.py:ensure_env_var` 폐기 (gws env 주입 책임)

### install.sh 단순화

- Step 5.2 `_step5_gws_install` 폐기 (gws binary 다운로드 + SHA verify + version pin)
- `INSTALLED_VERSIONS.json` 의 `gws` 키 폐기
- Step 5.3 `_step5_instance_dirs` 의 `~/.credentials/wikihub/` 생성 폐기 (rclone.conf 만 필요 — `~/.config/rclone/`)
- `operations.gws_min_version` yaml key 폐기

### 운영 자산 영향

기존 OCI 운영 자산 (cursor.json + Before schema file_map.json) 은 first-run 시 운영자가 수동 rm (`rm ~/wikihub/_state/<vault>/{cursor,file_map}.json`). 모든 파일이 created 로 분류되어 wiki/sources/ 가 재생성되는 정상 흐름. 자동 migration script 는 코드 표면적만 늘려 제공하지 않음 (운영자 base = 메인테이너 1명, v0.1.0 미배포 시점). 상세 절차는 §Operational Note 참조.

### rclone lsjson 에러 매핑 표 (ADR-0017 정본 자리)

ADR-0017 이 정의한 gws stderr 5-bucket 매핑 표가 ADR-0035 supersede 후 의미 부재. 본 ADR 이 등가 자리로 lsjson 에러 매핑을 정본화. `scripts/lib/rclone.py:classify_rclone_error` 가 본 표를 구현.

| rclone exit | stderr pattern (case-insensitive) | severity | wikihub_exit | scope |
|---|---|---|---|---|
| 1 | `oauth2.*invalid` · `invalid_grant` · `401 Unauthorized` · `unauthorized_client` · `access_denied` · `Token expired` · `invalid_credentials` | fatal | 2 | vault |
| 1 | `userRateLimitExceeded` · `rateLimitExceeded` · `quotaExceeded` · `403 Forbidden: userRateLimit` | retryable | 75 | vault |
| 1 | `connection refused` · `no such host` · `timeout awaiting` · `i/o timeout` · `TLS handshake timeout` | retryable | 75 | vault |
| 1 | 그 외 미매치 | fatal (안전 default) | 2 | vault |
| 2+ | argv·subcommand 오류 (caller bug) | fatal | 2 | vault |
| 137·143 (SIGKILL/SIGTERM) | — | retryable | 75 | vault |
| `RcloneBinaryMissing` | — | fatal | 2 | vault |

lsjson 은 full snapshot 호출이므로 **file scope 가 없음** (ADR-0017 의 file vs vault 분리 무력). 모든 fatal 은 vault scope — ADR-0024 의 vault-level fatal alert writer 가 책임. mount scope (rclone mount daemon 의 OAuth revoke) 는 `scripts/lib/mount.py:_RCLONE_AUTH_PATTERNS` + ADR-0024 v9 mount scope writer 가 별도 처리 — lsjson 과 인증 자료 (rclone.conf) 는 공유하나 호출 경로·scope 가 분리.

### (위 §운영 자산 영향 단락 참조 — §Operational Note 와 cross-reference)

**이유**:

- (α2) gws 폐기: alpha 의존성·stderr 매핑 부담·인증 비대칭 위험 모두 한 결정으로 해소. ADR-0014·0015·0017 cascade 자체가 사라짐
- (β2) lsjson: ADR-0027 L1 기각 사유 4개를 ID 노출 + file_map diff + 가드로 모두 등가 대체. rclone backend `changes` 부재라는 v9 진단을 v1.69.1 실증으로 재확인
- (γ2) source_id 키: rename 추적이 정확. Drive `name` 은 user-mutable, `id` 는 stable — primary key 로서 자연
- (δ2) cursor 폐기: lsjson full snapshot 에 cursor 의미 부재
- (ε2) rclone.conf 단독: 인증 자료 1개 → 운영 부담·실수 표면 감소
- (ζ2) false-delete 가드: mount/auth 부분 장애 시 wiki 데이터 손실 차단. yaml override 로 운영자 의도된 대량 삭제 시 임계 완화 가능

**기각 사유**:

- (α1) Path C+ 유지 + OAuth 통일: gws alpha 부담 + ADR-0017 stderr 매핑의 깨지기 쉬움 + 두 도구 관리 부담 잔존. gws 로 얻는 cursor 효율 (증분만 보는 cost) 이 v0.1.0 vault 규모 (N~수천) 에서 미미
- (α3) Workspace 전환 + ADR-0029 유지: 사용자 비용 + 데이터 이관 부담. rclone OAuth (기본 client Production) 가 이미 동작 — Workspace 강제 필요 없음
- (β1) mount FS walk: fileId 미노출 → rename = (delete + create) 오분류 → wiki fragmentation
- (β4) `lsf --max-age`: 삭제·권한 변경·reboot catch-up 부정확 (ADR-0027 §Context 원본 진단)
- (γ1) source_relpath 키 유지: rename 시 (delete + create) 오분류
- (δ1) cursor 유지: lsjson full snapshot 모델에 의미 부재 — dead field
- (ε1) credentials_path 유지: 두 자료 (SA JSON + rclone.conf) 운영 부담 + 인증 비대칭 회귀 위험
- (ζ1) 가드 없음: 백로그 §I 와 정반대 방향 결함 (대량 삭제) 가능 — 실수 비용 큼

## Consequences

### 긍정

- **인증 비대칭 해소** (백로그 §I 자체) — 변경 감지·다운로드 모두 동일 OAuth user 컨텍스트
- **도구 단일화** — rclone v1.x stable 만 운영. gws alpha 부담 제거
- **ADR cascade 단순화** — 5건 supersede 로 Drive 접근 모델 정본 1건으로 압축
- **상태 단순화** — cursor.json 폐기, file_map 키 모델 정합 (source_id stable)
- **install.sh 단순화** — Step 5.2 통째 제거, `~/.credentials/wikihub/` 폐기
- **인증 자료 1개** — rclone.conf 만. 운영 부담·실수 표면 감소
- **supply chain 위협 surface 1개 감소** — gws GitHub Releases artifact (ADR-0015 §γ3) 폐기. rclone 만 ADR-0025 §γ3 흐름 유지

### 부정/제약

- **lsjson cost** — 매 사이클 full snapshot. v0.1.0 vault 규모 (N~수천) 에선 무영향 가정. 큰 vault (N >> 10k) 에서는 latency 증가 가능 — 재검토 트리거
- **첫 사이클 부담** — file_map 비어있는 first-run 이 모든 파일 created → extraction + wiki write 일시 부하 (단 사이클은 lock 으로 다음 timer 흡수)
- **rclone OAuth client 의존** — rclone 기본 client 의 publishing status 정책 변경 시 영향. 재검토 트리거
- **Google native mtime 안정성 미실증** — vault 에 native 파일 없어 검증 불가. native 파일 도입 시 mount export-formats 의 mtime 거동 확인 필수 (Consequences 재검토 트리거)
- **운영자 수동 state migration** — first-run 전 `rm cursor.json file_map.json` 수동. 자동화 미제공 (v0.1.0 미배포 시점 가정)
- **state migration 후 wiki/sources/ overwrite** — 기존 페이지의 frontmatter 가 갱신됨. extraction 결과가 deterministic 이라 내용 동일성은 보존되나, file mtime/last_synced_at 갱신은 발생

### 후속 영향

- `scripts/lib/sync.py` 재작성, `scripts/lib/{gws,errors}.py` 삭제, `scripts/lib/{rclone,mount_diff}.py` 신규
- `scripts/lib/credentials.py` 재구성, `scripts/lib/state.py` cursor 함수 제거
- `_system/wiki-schema.md` Google native export 표 갱신 (gws → rclone)
- `_system/commands/setup.md` Step 0/Step 1 gws 단계 폐기
- `_system/commands/ingest.md` Step 2 흐름 갱신
- `_system/systemd/wikihub-vault@.service.template` 의 gws env 제거
- `install.sh` Step 5.2 폐기 + INSTALLED_VERSIONS.json 의 gws 키 폐기
- `wikihub.yaml.example` credentials_path/bootstrap_allowed/gws_min_version 제거, false_delete_threshold 추가
- `tests/test_gws.py` 삭제, `tests/test_{sync,credentials}.py` 재작성, `tests/test_mount_diff.py` 신규
- ADR-0014/0015/0017/0027/0029 Status `Superseded by ADR-0035` 갱신 + §Note 추가
- `docs/adr/README.md` 인덱스 갱신
- **재검토 트리거**:
  - rclone 기본 client 의 OAuth consent screen publishing status 가 Testing 으로 회귀
  - rclone 이 `rclone backend changes` 명령 추가 (cursor 모델 회귀 가능성)
  - vault 규모 N >> 10k 도달 — lsjson latency 가 sync_interval_sec 의 의미 있는 비율을 차지
  - Google native 파일이 vault 에 추가 → mtime 안정성 실증 필요
  - rclone v2.x major upgrade 시 lsjson schema breaking change

## Operational Note

본 ADR cascade 후 운영자가 따라야 할 절차의 정본.

### state migration (Before → After file_map schema)

v0.1.0 미배포 시점이라 자동 migration tool 미제공. 운영자는 deploy 직후 다음 1회 수행:

```bash
# 1. systemd timer 정지 (사이클 race 방지)
systemctl --user stop wikihub-vault@gdrive.timer

# 2. cursor + Before schema file_map 제거
rm -f ~/wikihub/_state/gdrive/cursor.json
rm -f ~/wikihub/_state/gdrive/file_map.json

# 3. timer 재시작 — first cycle 이 file_map 비어있어 모든 lsjson 항목을 created 분류
systemctl --user start wikihub-vault@gdrive.timer

# 4. 24h 관찰 — fatal 0건 + delete_ratio < false_delete_threshold (default 0.3)
journalctl --user -u wikihub-vault@gdrive.service -f
```

### 가드 default 값

- `vault.options.false_delete_threshold` default = **0.3** (30%). yaml override 가능.
- `vault.options.exclude_shared_with_me` default = **true**. v0.1.0 hook only (rclone lsjson default 동작이 sharedWithMe 제외 — `--drive-shared-with-me` 미지정 시).

### first-run 거동

- file_map 비어있는 사이클 (first-run 또는 운영자 rm 후) 은 모든 lsjson 항목을 `created` 분류 → wiki/sources/ 일괄 생성.
- 단일 사이클 동안 vault-fetch.py 의 동시 invocation 은 `_state/<vault>/.lock` flock 으로 차단 — timer + 운영자 수동 호출 race 무영향.
- first-run sync 의 사이클 duration 이 클 수 있음 (vault N건 = lsjson + N회 mount FS read + N회 atomic wiki write). `TimeoutStartSec` 충분히 설정 권장.

### OAuth client 출처

- rclone 기본 client (`rclone config` 시 client_id 빈칸 선택) — rclone 프로젝트 소유, 이미 Production 검증 통과. 7일 refresh 만료 없음.
- 운영자 본인 GCP 프로젝트의 OAuth client 사용은 v0.2.x 검토 사항 (quota 격리 + supply chain 분리 효과). v0.1.0 운영 안정성은 rclone 기본 client 로 충분.

### last_synced_at 의미

`file_map.json` 의 각 entry 의 `last_synced_at` = 해당 source_id 의 wiki page 가 마지막으로 atomic write 된 시각 (UTC ISO 8601). `modified`/`renamed`/`created` 분류 시 갱신, `unchanged` 분류 시 보존.

## Cross-references

- **Supersedes**: ADR-0014, ADR-0015, ADR-0017, ADR-0027, ADR-0029
- **무관·정합 유지**: ADR-0001 (source collision), ADR-0006 (unified orchestration), ADR-0007 (state JSON), ADR-0025 (rclone mount), ADR-0034 (data-first layout)
- **부분 갱신** (Status `Accepted` 유지, 본문 또는 §Note minor):
  - ADR-0024 (fatal alert) — v9 §Context 의 ADR-0027 인용을 historical 로 명시 (ADR-0027 supersede 후). mount scope writer 책임 자체는 정합 유지.
  - ADR-0026 (vfs refresh) — §Note 추가 (cycle 순서 step 3 gws → lsjson 으로 갱신, step 5 cursor → file_map 으로 갱신, race window 정의 lsjson context 로 재서술). K1 정책 자체는 정합 유지.
  - ADR-0029 (SA 인증) — §"Note (2026-05-19, dir_layout_refactor)" 의 credentials_path default 갱신이 ADR-0035 supersede 로 무효화 명시.
- **본 ADR 의 분석 정본**: [features/20260519_oauth_unify_rclone_only/analysis_and_design.md](../../features/20260519_oauth_unify_rclone_only/analysis_and_design.md)
- **계기 백로그**: [features/backlog.md](../../features/backlog.md) §D·§I
- **2026-05-19 OCI 실증 결과**: 동 backlog.md 의 §D 근본 원인 (SA storageQuotaExceeded) + 본 feature 의 analysis_and_design.md §2.4 (lsjson ID/MimeType 노출)
