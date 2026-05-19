# ADR-0017: gws stderr → wikihub exit code 매핑 표

- **Status**: Superseded
- **Date**: 2026-05-14 (Proposed) / 2026-05-19 (Superseded by ADR-0035 — Accepted 도달 전 무효화)
- **Feature**: features/20260514_install_runtime
- **Supersedes**: 없음
- **Superseded by**: ADR-0035 (gws CLI 폐기로 stderr 매핑 자체 불필요)

## Note (2026-05-19, ADR-0035 supersede)

본 ADR 은 V4 verification 통과로 Accepted 도달 예정이었으나, ADR-0035 로 gws CLI 자체가 폐기되어 stderr 매핑 표가 불필요해짐. `scripts/lib/errors.py` 삭제. 본문은 역사적 맥락 보존을 위해 유지.

## Context

ADR-0014 가 gws CLI 를 채택한 후, 운영 중 gws 의 stderr 출력을 wikihub 의 exit code 시맨틱 (0 / 75 / 2) 으로 분류하는 매핑 표 필요. F3 의 `scripts/lib/errors.py` 가 starting regex 를 가지고 있지만 V4 verification (실 gws 에러 트리거 후 stderr 캡처) 전까지 추정.

추가로 R4 (F3 archive code review) 의 CRIT-R4-3 결과 — fatal 의 scope (vault 전체 vs file 단위) 분리 필요. v0.1.0 의 stderr 매핑 표에 scope 컬럼 포함.

## Considered Options

- **(α) G1**: F3 archive 의 `lib/errors.py` 의 `GWS_API_ERROR_PATTERNS` regex 그대로 starting. V4 후 refine.
- **(β) G2**: 모든 에러를 fatal 로 분류하는 단순 starting. V4 후 한 번에 정밀 매핑.

> 옵션 상세는 [features/20260514_install_runtime/analysis_and_design.md §3.7](../../features/20260514_install_runtime/analysis_and_design.md) 참조.

## Decision

**채택**: (α) G1 — F3 archive 의 starting regex.

**v0.1.0 starting 매핑** (`scripts/lib/errors.py` 의 `GWS_API_ERROR_PATTERNS`):

| regex | severity | wikihub_exit | scope |
|---|---|---|---|
| `\b403\b.*(userRateLimitExceeded\|rateLimitExceeded\|quotaExceeded)` | retryable | 75 | vault |
| `\b403\b.*(insufficientPermissions\|forbidden)` | fatal | 2 | **file** |
| `\b401\b` | fatal | 2 | vault |
| `\b5\d{2}\b` | retryable | 75 | vault |
| `(timeout\|connection\|network\|refused)` | retryable | 75 | vault |
| (미매치) | fatal | 2 | vault (안전 default) |

**scope 컬럼 의미**:
- `vault`: vault 전체 사이클 중단 → `VaultSyncFatal` (cursor advance 안 함).
- `file`: 단일 파일만 영향 → `VaultSyncFileFatal` (retry queue 등록 + cursor advance — vault 전체 stuck 회피).

**이유**:
- F3 archive 의 regex 는 추정이지만 v0.1.0 의 safety 보장 (5xx·timeout retryable, 4xx fatal 분류).
- G2 (모두 fatal) 은 운영에서 quota exceeded 같은 일시 결함도 fatal 로 분류 → vault 영원히 stuck.
- scope 컬럼은 R4 CRIT-R4-3 결과 — 한 파일의 403 insufficientPermissions 가 vault 전체를 stuck 시키지 않기 위해 file 분류 필수.

## Consequences

- **긍정**: 첫 사이클부터 정밀하지는 않아도 safe-by-default. quota / 일시 결함은 자동 재시도, 권한 결함은 운영자 통지.
- **부정/제약**: regex 가 추정이라 실제 gws stderr 형식과 차이 가능 — 미매치 시 fatal-vault 로 분류되어 cursor 멈춤. V4 후 refine 필수.
- **후속 영향**:
  - V4 verification (의도적 403/401/5xx trigger) 결과로 본 매핑 표 정본화 → Status → Accepted.
  - 신규 패턴 추가 시 본 ADR 본문 갱신 (supersede 아닌 표 보강).
