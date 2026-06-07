# Plan: NAS vault file_map source_id 충돌 해결

**Issue**: #134 — NAS vault 의 file_map source_id 충돌 — 매 cycle 동일 파일 재처리
**작성일**: 2026-06-07 (KST)
**작성자**: Hermes-A

## 문제 요약

v0.1.11 NAS vault 지원 도입 시 rclone SFTP backend 의 lsjson 이 stable fileId 를 노출하지 않는 문제로 `_compute_diff_path_based` 가 추가되었으나, created entry 의 `source_id` 를 `""` 로 하드코딩한 결과 file_map 키 충돌이 발생했다.

**재현 시나리오** (NAS vault, 3 파일):
1. 1st cycle: file_map 비어있음 → diff 3건 created → 3 wiki 페이지 write → file_map `[""]` 에 마지막 처리된 파일만 남음 (나머지는 덮어써져 손실)
2. 2nd cycle: file_map `[""]` = 마지막 파일의 데이터 → 나머지 파일은 created 로 재분류 → 매 cycle 재기록
3. 3rd cycle 이후: 영구적으로 매 cycle 재처리

## 해결 방향

**(α) source_id 를 path 로 강제 치환** — NAS 만 `file_map["files"][path] = { ... source_id: path, ... }`

- ADR-0035 의 "primary key = source_id" 를 "source_id 는 Drive 한정, NAS 는 path" 로 명시 분기
- 변경 최소, Drive vault 회귀 0

## 작업 범위

### Step 1: 코드 수정

1. `scripts/lib/mount_diff.py:210` — created entry 의 `source_id=""` 를 `source_id=path` 로 변경
2. `scripts/lib/mount_diff.py:188-193` — `files_by_path` 재구성 로직 단순화 (file_map 자체가 path-key dict 이므로 직접 사용 가능)
3. `scripts/lib/sync.py:337, 421` — file_map key 사용처는 변경 없음 (key 만 path 가 됨)

### Step 2: ADR 작성

- `docs/adr/0045-nas-file-map-key.md` 신설
- NAS vault 의 file_map primary key 정책 명시
- ADR-0035 와의 관계 명시 (Drive 한정, NAS 는 path)

### Step 3: 테스트 추가

- `tests/test_mount_diff.py` — NAS 3+ 파일 / 2 cycle 회귀 테스트 추가
  - assert: 2nd cycle diff.entries == [] (정상 unchanged)
  - assert: file_map["files"] 의 entry 수가 NAS 파일 수와 일치
- `tests/test_sync.py` — `_handle_create_or_modify` 의 NAS 입력 단위 테스트 보강

### Step 4: 검증

- 기존 `tests/test_mount_diff.py` 전체 pass (Drive vault 회귀 없음)
- NAS vault 3+ 파일 / 2 cycle 운영 시 2nd cycle 의 `diff.entries == []`
- `file_map["files"]` 의 entry 수가 NAS 파일 수와 일치

## 수용 기준 (DoD)

- [ ] NAS vault 3+ 파일 / 2 cycle 운영 시 2nd cycle 의 `diff.entries == []` (정상 unchanged)
- [ ] `file_map["files"]` 의 entry 수가 NAS 파일 수와 일치 (회귀 시 1)
- [ ] Drive vault 회귀 없음 (기존 `tests/test_mount_diff.py` 전체 pass)
- [ ] ADR-0045 에 NAS vault file_map key 정책 명시
- [ ] wiki page 는 동일 path·mtime 일 때 재기록되지 않음 (idempotency)

## 영향 파일

- `scripts/lib/mount_diff.py:172-252` — `_compute_diff_path_based` (NAS path-key 정합)
- `scripts/lib/mount_diff.py:210-211` — `source_id=""` 하드코딩 제거
- `scripts/lib/mount_diff.py:188-193` — `files_by_path` 재구성 로직 단순화
- `docs/adr/0045-nas-file-map-key.md` — NAS vault file_map key 정책 정본화
- `tests/test_mount_diff.py:130-156` — NAS 3+ 파일 / multi-cycle 회귀 테스트 추가
- `tests/test_sync.py` — `_handle_create_or_modify` 의 NAS 입력 단위 테스트 보강

## 참고

- 코드: `scripts/lib/mount_diff.py:172-252` (NAS path-based diff)
- 코드: `scripts/lib/mount_diff.py:210-211` (`source_id=""` 회귀 지점)
- 코드: `scripts/lib/sync.py:337` (file_map key 사용)
- ADR: ADR-0035 (file_map primary key = source_id, Drive 한정 정합)
