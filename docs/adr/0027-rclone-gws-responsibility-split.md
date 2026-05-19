# ADR-0027: rclone vs gws 책임 분리 — Path C+ 정본화

- **Status**: Superseded
- **Date**: 2026-05-15 (Accepted) / 2026-05-19 (Superseded by ADR-0035)
- **Feature**: features/20260514_install_runtime (v9)
- **Supersedes**: 없음
- **Superseded by**: ADR-0035 (gws 폐기 + rclone 단독화 — 책임 분리 자체 폐기, rclone 이 mount + lsjson 변경 감지 둘 다 담당)

## Note (2026-05-19, ADR-0035 supersede)

본 ADR §Considered Options 의 (L1) rclone 단독 기각 사유 4개 (삭제·권한·catch-up·cursor 정확성) 를 ADR-0035 §재평가 표에서 해체. lsjson 의 `ID` 노출 + file_map(source_id 키) diff + false-delete 가드 조합으로 L1 의 모든 기각 사유가 등가 대체 또는 무력화됨을 2026-05-19 OCI 실증으로 확인. 본문은 v9 설계의 역사적 맥락 보존을 위해 유지.

## Context

ADR-0025 (rclone mount 채택) 도입 시점에 두 도구 (rclone + gws) 가 공존하게 됨. 책임 경계 lock 이 필요.

선행 분석 (`features/20260514_install_runtime/rclone_vs_gws_comparison.md`) 에서 surface 한 결정적 사실:

- **rclone 은 Drive Changes API 를 backend command 로 노출하지 않음** (`rclone backend changes` 부재 — https://rclone.org/drive/ 의 backend command 목록 검증)
- rclone 의 변경 감지 메커니즘은 `lsf --max-age` (시각 윈도우) 또는 디렉토리 walk + mtime diff — cursor 기반 정확성 부재
- 시각 윈도우 모델은 **삭제 이벤트·권한 변경 미감지** + reboot 기간 변경 catch-up 불가 — wikihub 의 정합성 invariants 와 충돌
- gws 는 Discovery Service 동적 빌드로 `gws drive changes list` (cursor 기반) + `changes.watch` 모두 노출

## Considered Options

- **(L1) rclone 단독** (mount FS walk + file_map diff): 단일 도구, F3 코드 ~40% 재작성. 삭제·권한·catch-up 손실 + source_id 노출 미보장
- **(L2) gws 단독 유지** (ADR-0014 그대로): 사용자 요구사항 (실시간 mount UX) 미충족
- **(L3) Path C 하이브리드** (mount = UX only, gws = 자동화 전부 — 변경 감지 + 다운로드): mount 가치 일부만 활용
- **(L4 = Path C+) rclone = mount/다운로드, gws = changes API**: 각 도구의 강점만 사용. F3 코드 ~90% 재사용 (다운로드 헬퍼만 교체)

> 옵션 상세 비교는 [features/20260514_install_runtime/rclone_vs_gws_comparison.md](../../features/20260514_install_runtime/rclone_vs_gws_comparison.md) §2~§5 참조.

## Decision

**채택**: (L4) Path C+

### 책임 분배 매트릭스

| 영역 | rclone | gws |
|---|---|---|
| Drive ↔ 로컬 sync (실시간) | ✅ mount daemon | ❌ |
| 변경 감지 (cursor 기반) | ❌ (Drive Changes API 미노출) | ✅ `drive changes list` |
| 삭제 · 권한 · rename 이벤트 | ❌ | ✅ `changeType` 명시 |
| 파일 read (다운로드) | ✅ mount FS `open()` (vfs cache) | ❌ (v7 에서 폐기) |
| Google native export | rclone `--drive-export-formats docx,xlsx,pptx,md` 우선 + sync.py 가 mimeType 기반 `source_relpath` 매핑 + extraction.py 의 `extract_docx/xlsx/pptx` dispatch (**Q1 lock, V18·V4 본격 후 V<N> Phase 2 결함 #9 fix**, 2026-05-17) | Q1 lock |
| OAuth | ✅ rclone config | ✅ `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` |
| systemd unit | `wikihub-mount@.service` (Type=simple, Restart=always) | `wikihub-vault@.service` (Type=oneshot, timer 기반) |

### 장애 격리

- **mount 죽음** → vault read 불가. `wikihub-vault@.service` 가 `assert_mount_alive()` 로 fail-fast (mount stat 실패 감지). `OnFailure=ops-alert.service` 발화 + (StartLimitBurst 초과 시) mount@ 의 직접 `OnFailure` 발화. 변경 감지 (gws) 호출 자체는 막힘 (사이클 abort)
- **gws 결함** → 변경 감지 끊김. mount 는 살아있어 운영자 SSH UX 유지. `wikihub-vault@.service` 가 fail-fast → ops-alert
- **rclone OAuth revoke** → `vfs_refresh` 가 stderr 패턴 매칭 → VaultSyncFatal (mount scope) → ADR-0024 last_failure writer → ops-alert
- **gws OAuth revoke** → `gws drive changes list` 가 exit 2 (auth error) → ADR-0017 vault scope fatal → ADR-0024 last_failure writer (기존)

### F3 코드 재사용도

| F3 모듈 | 변경 |
|---|---|
| `scripts/lib/gws.py` | 변경 없음 (subprocess wrapper 그대로) |
| `scripts/lib/errors.py` | 변경 없음 (gws exit code/stderr 매핑 그대로) |
| `scripts/lib/sync.py` | 다운로드 헬퍼 (`_download_to_vault`) → `_read_from_mount` 교체. `_handle_removed` unlink 라인 제거 (mount FS 위 unlink 가 Drive 원본 삭제 위험). `_resolve_mount_path` 신규 (v0.1.0 flat) |
| `scripts/lib/state.py` | `save_last_failure` schema enum 에 `"mount"` 추가 (ADR-0024 v9 minor) |
| `scripts/lib/credentials.py` | rclone config 존재 + 권한 검증 helper 추가 (gws credentials 검증은 그대로) |
| `scripts/lib/config.py` | `mount_path`, `rclone_remote_name`, `rclone_rc_port` 옵션 파싱 |
| `scripts/lib/extraction.py` | 변경 없음 (mime 매핑은 동일) |
| `scripts/vault-fetch.py` | `assert_mount_alive` + `vfs_refresh` 호출 추가, import 갱신 |

**전체 ~90% 재사용** (변경 감지·extraction·state·error 분류 모두 그대로).

### ADR cascade

- **ADR-0014 (gws CLI 채택) — supersede 없음**. 변경 감지의 정본은 gws 유지. ADR-0014 의 reversal 결정이 v9 에서도 유효
- **ADR-0006 (unified orchestration) — supersede 없음**. `vault-fetch.py` 외부 인터페이스 (ingest.md §Step 2 stdout JSON contract) 무변경. subprocess 패턴 확장 (gws + rclone rc)
- ADR-0024 (fatal alert contract) — v9 minor 갱신 (mount scope writer 추가, supersede 아님)
- ADR-0025·0026 — 신규 (본 ADR 의 architectural 결정을 산출물 spec 으로 분해)

**이유**:
- L1 (rclone 단독): 삭제·권한·catch-up 손실은 wikihub 의 정합성 invariants 와 충돌. ADR-0014 의 reversal 정신 (changes API 정확성 우선) 과 불일치
- L2 (gws 단독): 사용자 요구사항 미충족. 본 feature 의 v7 architectural revision 이 무의미해짐
- L3 (Path C, mount = UX only): mount 가 다운로드 패스로도 동작 (vfs cache 가 다운로드 캐시 흡수) — 가치 일부만 활용은 비효율
- L4 (Path C+): 각 도구의 강점만 사용 + F3 ~90% 재사용 + ADR cascade 최소 (supersede 0건, 신규 3건) + alpha 부담을 gws changes API 한 영역에만 격리

## Consequences

- **긍정**:
  - 각 도구의 강점 활용 (rclone v1.x stable mount + gws Discovery 정확성)
  - F3 sync.py 핵심 로직 ~90% 재사용 — Step 3 구현 분량 최소
  - ADR cascade 최소 (supersede 0건) — 결정 정합 단순
  - 장애 격리 명확 (mount 죽음 ↔ gws 결함이 독립)
  - 사용자 요구사항 (실시간 mount UX) + 정합성 (cursor·삭제·권한) 둘 다 충족

- **부정/제약**:
  - 두 도구 동시 운영 — install 분량 + version pin 부담 2배 (다만 v0.1.0 운영 가이드로 흡수 가능)
  - 두 OAuth token 발급 필요 (gws + rclone) — setup.md Step 5 + Step 5.5 분리
  - mount alert 채널의 정합성 (ADR-0024 mount scope writer) 추가 필요
  - race window (gws changes 알림 ↔ mount stale) — ADR-0026 K1 으로 차단

- **후속 영향**:
  - F3 의 R3·R4 잔류 MED 8건 (next_retry_at backoff, error_count/skipped_count stdout 등) 은 본 ADR 범위 밖 — 별도 light feature
  - 재검토 트리거:
    - rclone 이 `rclone backend changes` 추가 → 단일화 가능성 재검토 (rclone 으로 changes 도 흡수)
    - gws 가 v1.0 도달 + breaking change 부재 확인 → alpha 부담 해소 + Q11 (gws schema runtime assert) 무력화 가능

## Cross-references

- ADR-0006 (unified orchestration) — supersede 없음, 본 ADR 이 subprocess 패턴 확장 (gws + rclone rc)
- ADR-0014 (Drive 접근 — gws CLI 채택) — supersede 없음, 변경 감지의 정본 유지
- ADR-0024 v9 (fatal alert contract) — mount scope writer 추가
- ADR-0025 (rclone mount 채택) — 본 ADR 의 mount 영역 spec
- ADR-0026 (vfs refresh 정책) — 본 ADR 의 race window 차단 spec
- features/20260514_install_runtime/rclone_vs_gws_comparison.md — 결정 근거 (3 갈래 Path A·B·C+ 비교 + 차원별 평가)
- features/20260514_install_runtime/analysis_and_design.md §10.3.3 — 결정 [L] 본문
