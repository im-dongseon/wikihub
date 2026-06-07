# ADR-0045: NAS vault file_map primary key = path

**Status**: Accepted
**작성일**: 2026-06-07 (KST)
**작성**: Hermes-A
**Issue**: #134

## Context

v0.1.11 NAS vault 지원 (#117) 도입 시 rclone SFTP backend 의 lsjson 이 stable fileId 를 노출하지 않는 문제가 확인되었다. Drive vault 와의 공존을 위해 `_compute_diff_path_based` (path 기반 diff) 가 `mount_diff.py:172-252` 에 추가되었으나, file_map 자체는 여전히 source_id key dict (ADR-0035 정합) 로 남았다.

당시 NAS created entry 의 `source_id` 를 `""` 로 하드코딩한 (`mount_diff.py:211`) 결과, file_map 키 충돌이라는 회귀가 발생했다:

- NAS 파일 N개 모두 키 `""` 로 덮어써져 file_map 에 마지막 1개만 남음
- 2nd cycle 부터 나머지 파일이 created 로 재분류되어 매 cycle 재처리
- multi-file NAS vault 가 실제로 운영되기 시작하면 즉시 노출되는 회귀

## Decision

NAS vault 의 file_map primary key 를 **path** 로 전환한다. 구체적으로:

- NAS vault 의 `file_map["files"]` 는 path 를 key 로 사용 (`source_id == path`)
- Drive vault 는 기존 ID 기반 유지 (ADR-0035 정합)
- file_map schema 는 변경 없음 (`source_id` 필드는 유지, 값만 path)

### 구현

- `mount_diff.py:210` — created entry 의 `source_id=""` 를 `source_id=path` 로 변경
- `sync.py:337, 421` — file_map key 사용처는 변경 없음 (key 만 path 가 됨)
- `_compute_diff_path_based` 의 `files_by_path` 재구성 (line 188-193) 은 기존 로직 유지 (source_relpath 를 path 로 사용)

## Consequences

### Positive

- NAS vault multi-file / multi-cycle 운영 정상화
- file_map 비결정적 동작 제거 (처리 순서 무관)
- Drive vault 회귀 0 (변경 면적 최소)

### Negative

- ADR-0035 와 불일치 (Drive: ID, NAS: path) — 하지만 ADR-0035 를 "Drive 한정" 으로 명시하면 정합 유지
- 기존 NAS file_map 에 `source_id=""` 로 저장된 entry 가 있다면 마이그레이션 필요 (현재 운영 evidence 없음)

## References

- ADR-0035: file_map primary key = source_id (Drive 한정 정합)
- Issue #134: NAS vault 의 file_map source_id 충돌 — 매 cycle 동일 파일 재처리
- Code: `scripts/lib/mount_diff.py:172-252` (_compute_diff_path_based)
- Code: `scripts/lib/sync.py:337, 421` (file_map key 사용)
