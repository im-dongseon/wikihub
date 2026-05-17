# ADR-0007: state 저장 방식 — all JSON 통일

- **Status**: Accepted
- **Date**: 2026-05-13
- **Feature**: features/20260513_wikihub_schema_v1
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

F1 (`20260513_v030_initial_architecture`)의 §4.4가 `_state/{vault}/` 영속 파일 구조를 정의했다. 대부분(`cursor.json`·`file_map.json`·`last_sync.json`)은 JSON이고 retry queue(`retry.db`)만 SQLite (WAL 모드). F1의 SQLite 선택 근거(§4.4.4)는 "row-level 갱신 + 조건 쿼리 + 동시성 안전".

F2 Step 2에서 단일 파일 모델 + Unified orchestration (ADR-0006) 채택 + `pending_ingest.json` 도입을 거치며 state 파일이 5종으로 늘어남(cursor, file_map, last_sync, retry, pending). 5종 중 1종만 SQLite, 나머지는 JSON인 혼합 방식의 일관성·디버깅·의존성 부담을 재검토.

**v0.1.0 규모 검증**:

- Personal scale: Drive 파일 수 ~수천 (10K 미만 추정)
- 동시 쓰기: 없음 (vault sync는 systemd Type=oneshot)
- retry queue 크기: 보통 0~10 행, 많아도 수십

이 규모에서 SQLite의 "row-level 갱신·조건 쿼리·동시성"의 이점은 실현되지 않는다.

## Considered Options

- **(α) 혼합 유지 (F1 §4.4 그대로)**: JSON 4종 + SQLite 1종 (retry.db)
- **(β) all JSON 통일**: 5종 모두 JSON, atomic write (tmpfile + os.replace)
- **(γ) all SQLite 통일**: 단일 `state.db`에 tables. cursor·file_map·retry·pending 모두 row 형식

옵션 비교 표는 [features/20260513_wikihub_schema_v1/analysis_and_design.md](../../features/20260513_wikihub_schema_v1/analysis_and_design.md) state 저장 방식 검토 절 참조.

## Decision

**채택**: (β) all JSON 통일

5종 state 파일의 형식과 갱신 패턴:

| 파일 | 형식 | 패턴 |
|---|---|---|
| `cursor.json` | JSON object | 통째 read·write |
| `file_map.json` | JSON object (files: dict) | 통째 read → 일부 수정 → atomic write |
| `last_sync.json` | JSON object | 통째 덮어쓰기 (사이클별 스냅샷) |
| `pending_ingest.json` | JSON object | 통째 read·write (작성·삭제) |
| `retry.json` (was retry.db) | JSON object (queue: list of dicts) | 통째 read → 필터·갱신 → atomic write |

모든 파일은 `tmpfile + os.replace` 패턴으로 atomic 영속화.

**`retry.json` 스키마**:
```json
{
  "vault_id": "gdrive",
  "next_id": 42,
  "queue": [
    {
      "id": 41,
      "source_relpath": "notes/idea.md",
      "source_id": "1A2B3C...",
      "operation": "modified",
      "failure_reason": "429 rate limit",
      "attempts": 1,
      "next_retry_at": "2026-05-13T10:35:00+00:00",
      "first_failed_at": "2026-05-13T10:30:00+00:00",
      "last_failed_at": "2026-05-13T10:30:00+00:00"
    }
  ]
}
```

**이유**:
- **v0.1.0 규모에 충분**: retry queue 수십 행, file_map 수천 행 — JSON read-modify-write 비용 무시 가능
- **단일 writer 보장**: vault별 sync는 Type=oneshot → 동시 쓰기 없음 → SQLite WAL의 동시성 보호 불필요
- **디버깅 친화**: `cat retry.json`로 즉시 확인. `sqlite3 ... .dump`보다 단순
- **백업·복구 단순**: rsync·git·일반 파일 도구로 통일 처리
- **의존성 감소**: SQLite 자체는 stdlib이지만 WAL 모드 / corrupt 처리 / `.db-wal`+`.db-shm` 보조 파일 관리 복잡성 제거
- **일관성**: 5종 파일이 동일 형식·동일 atomic 패턴 → spec·구현·운영 모두 단일 멘탈 모델

**(α) 기각**: 혼합의 정당화가 약함. v0.1.0 규모에서 SQLite의 이점이 실현되지 않으므로 일관성을 위해 통일.
**(γ) 기각**: cursor 같은 단일 값에 DB 과잉. binary file 디버깅 비용. 5종을 1개 DB에 합치면 atomic 이점은 있으나 file_map 같은 큰 객체와 cursor 같은 작은 객체가 동일 DB에 공존하는 어색함.

## Consequences

- **긍정**:
  - F3 구현 단순화 — 모든 state read/write가 동일 helper 패턴 (`load_json_atomic`, `write_json_atomic`)
  - 운영 진단 통일 — 모든 state는 텍스트 파일
  - sync 스크립트의 SQLite 의존 제거
  - F1 §4.4.5 상태 파일 일관성 표가 단일 형식으로 통일 — `PRAGMA integrity_check` 같은 SQLite 전용 절차 제거

- **부정/제약**:
  - **read-modify-write 비용**: retry queue가 수백 행 이상이면 매 사이클 통째 read·write 비용 발생 (v0.1.0 규모에서는 무시 가능)
  - **부분 쓰기 위험 X**: atomic write로 보호되나 매 갱신마다 전체 직렬화 — file_map이 큰 경우(>10MB) 갱신 비용 증가
  - **scale ceiling**: file_map > 100K 행 또는 retry > 1K 행 도달 시 본 결정 재검토 필요

- **후속 영향**:
  - **F1 archive 영향**: F1 §4.4.4의 SQLite 결정 retracted. F1 archive 문서는 영속 기록이므로 수정 안 함. 본 ADR이 새 정본
  - **F1 §4.4.5 상태 파일 일관성 표**: "SQLite는 WAL 모드" 줄 무효화. 본 ADR이 우선
  - **F2(wikihub_schema_v1)**: wiki-schema나 commands에는 영향 없음 (state 형식은 F3 구현 책임). 단 `_system/commands/ingest.md`가 pending_ingest.json 참조 시 JSON 형식 가정
  - **F3(vault_gdrive_api)**: SQLite 코드·의존성 제거. retry queue는 JSON list of dicts로 구현. `_atomic_write_json(path, obj)` helper 1개
  - **F4(systemd_orchestrator)**: SQLite 관련 backup·rotate 정책 무관. 모든 state 파일 통일 처리
  - **재검토 트리거**: file_map > 100K 행 또는 retry queue > 1K 행 또는 read-modify-write latency > 1초 도달 시 SQLite 마이그레이션 ADR 발의
