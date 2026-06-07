# Analysis & Design: NAS vault file_map source_id 충돌 해결

**Issue**: #134
**작성일**: 2026-06-07 (KST)
**작성자**: Hermes-A
**Status**: Draft

## 1. 문제 분석

### 1.1. 현재 동작

`_compute_diff_path_based` (mount_diff.py:172-252):

```python
# line 185: listing을 Path 키 dict로 변환
listing_by_path: dict[str, dict[str, Any]] = {item["Path"]: item for item in listing_filtered}

# line 188-193: file_map을 path 키 dict로 재구성
files_by_path: dict[str, dict[str, Any]] = {}
for source_id, file_data in files.items():
    path = str(file_data.get("source_relpath", ""))
    if path:
        files_by_path[path] = {**file_data, "_source_id": source_id}

# line 207-215: created entry
if prev is None:
    result.entries.append(DiffEntry(
        operation="created",
        source_id="",  # ← 문제: 모든 NAS 파일이 같은 키
        source_relpath=path,
        ...
    ))
```

`sync.py:337`:
```python
file_map["files"][entry.source_id] = {
    "source_relpath": source_relpath,
    "source_mtime": entry.mtime,
    ...
}
```

### 1.2. 문제 시나리오

NAS vault에 `a.txt`, `b.txt`, `c.txt` 3개 파일이 있다고 가정:

**1st cycle** (file_map 비어있음):
1. diff 3건 created (source_id=""로 각각 생성)
2. sync.py가 3개 파일 처리:
   - `file_map["files"][""] = {a.txt 메타데이터}`
   - `file_map["files"][""] = {b.txt 메타데이터}` (덮어쓰기)
   - `file_map["files"][""] = {c.txt 메타데이터}` (덮어쓰기)
3. 결과: file_map에 1개 entry만 남음 (c.txt)

**2nd cycle** (소스 변경 없음):
1. file_map[""] = c.txt 메타데이터
2. `_compute_diff_path_based`:
   - `files_by_path` = {c.txt path: c.txt 메타데이터}
   - listing_by_path = {a.txt: ..., b.txt: ..., c.txt: ...}
   - a.txt: prev=None → created
   - b.txt: prev=None → created
   - c.txt: prev=c.txt 메타데이터, mtime 동일 → unchanged
3. diff 2건 created (a.txt, b.txt)
4. sync.py가 2개 파일 재처리 → wiki 페이지 재기록

**3rd cycle 이후**: a.txt, b.txt는 영구적으로 매 cycle 재처리

### 1.3. 근본 원인

- rclone SFTP backend의 lsjson은 `ID` 필드가 공백
- `_compute_diff_path_based`는 path 기반으로 diff를 수행하지만, created entry의 `source_id`를 `""`로 하드코딩
- `sync.py`는 `source_id`를 file_map의 key로 사용 → 모든 NAS 파일이 같은 키로 덮어써짐

## 2. 해결 방향

### 2.1. 선택지 분석

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| (α) source_id를 path로 치환 | NAS만 `file_map["files"][path] = { ... source_id: path, ... }` | 변경 최소, Drive 회귀 0 | ADR-0035와 불일치 (ADR 갱신 필요) |
| (β) NAS만 별도 file_map 섹션 | `file_map["files"]` (Drive) + `file_map["files_by_path"]` (NAS) 분리 | 명확한 분리 | schema 확장, 더 invasive |
| (γ) source_id를 NAS에서 unique key로 합성 | `f"nas:{path}"` 같은 prefix 부여 | ADR-0035 정합 유지 | 불필요한 prefix |

### 2.2. 결정: (α) source_id를 path로 치환

**근거**:
- 변경 면적 최소 (mount_diff.py:210만 수정)
- Drive vault 회귀 0 (Drive는 기존 ID 기반 유지)
- ADR-0035를 "Drive 한정"으로 명시하면 정합 유지

## 3. 설계

### 3.1. 코드 변경

#### 3.1.1. mount_diff.py:210 — created entry의 source_id를 path로 설정

**변경 전**:
```python
if prev is None:
    result.entries.append(DiffEntry(
        operation="created",
        source_id="",  # NAS vault는 ID 부재
        source_relpath=path,
        ...
    ))
```

**변경 후**:
```python
if prev is None:
    result.entries.append(DiffEntry(
        operation="created",
        source_id=path,  # NAS vault는 path를 source_id로 사용
        source_relpath=path,
        ...
    ))
```

#### 3.1.2. mount_diff.py:188-193 — files_by_path 재구성 로직 단순화

**변경 전**:
```python
files_by_path: dict[str, dict[str, Any]] = {}
for source_id, file_data in files.items():
    path = str(file_data.get("source_relpath", ""))
    if path:
        files_by_path[path] = {**file_data, "_source_id": source_id}
```

**변경 후**:
NAS vault의 file_map은 이미 path-key dict이므로 단순화 가능:
```python
# NAS vault: file_map 자체가 path-key dict (source_id == path)
files_by_path: dict[str, dict[str, Any]] = {
    source_id: {**file_data, "_source_id": source_id}
    for source_id, file_data in files.items()
    if source_id  # path가 있는 경우만
}
```

하지만 이 변경은 필수는 아님. 기존 로직도 올바르게 동작함 (source_relpath를 path로 사용).

**결정**: 단순화는 생략 (기존 로직 유지). source_id="" 하드코딩만 수정.

#### 3.1.3. mount_diff.py:221, 235 — modified/deleted entry의 source_id

**변경 전**:
```python
# modified (line 221)
source_id=prev.get("_source_id", ""),

# deleted (line 235)
source_id=prev.get("_source_id", ""),
```

**변경 후**:
변경 없음. `_source_id`는 file_map의 key를 보존한 것이므로, file_map의 key가 path가 되면 `_source_id`도 path가 됨.

### 3.2. ADR 작성

`docs/adr/0045-nas-file-map-key.md` 신설:

- **Title**: NAS vault file_map primary key = path
- **Status**: Accepted
- **Context**: rclone SFTP backend는 stable fileId를 노출하지 않음
- **Decision**: NAS vault의 file_map primary key는 path (source_id == path)
- **Consequences**:
  - Drive vault: 기존 ID 기반 유지 (ADR-0035 정합)
  - NAS vault: path 기반 (본 ADR)
  - file_map schema 변경 없음 (source_id 필드는 유지, 값만 path)

### 3.3. 테스트 추가

#### 3.3.1. test_mount_diff.py — NAS 3+ 파일 / 2 cycle 회귀 테스트

```python
def test_nas_multi_file_2_cycle_no_false_created(tmp_path):
    """NAS vault 3+ 파일 / 2 cycle 운영 시 2nd cycle diff.entries == [] (정상 unchanged)."""
    # 1st cycle: file_map 비어있음, listing 3건
    listing = [
        {"Path": "a.txt", "ModTime": "2026-06-07T00:00:00Z", "Size": 100, "MimeType": "text/plain"},
        {"Path": "b.txt", "ModTime": "2026-06-07T00:00:00Z", "Size": 200, "MimeType": "text/plain"},
        {"Path": "c.txt", "ModTime": "2026-06-07T00:00:00Z", "Size": 300, "MimeType": "text/plain"},
    ]
    file_map = {"files": {}}
    
    result1 = compute_diff(listing, file_map, vault_type="nas")
    assert len(result1.entries) == 3
    assert all(e.operation == "created" for e in result1.entries)
    assert all(e.source_id == e.source_relpath for e in result1.entries)  # source_id == path
    
    # 1st cycle 이후 file_map 시뮬레이션 (sync.py가 저장한 결과)
    for entry in result1.entries:
        file_map["files"][entry.source_id] = {
            "source_relpath": entry.source_relpath,
            "source_mtime": entry.mtime,
            "wiki_path": f"wiki/{entry.source_relpath}.md",
            "bytes": entry.size,
            "last_synced_at": "2026-06-07T00:00:00Z",
        }
    
    # 2nd cycle: 소스 변경 없음
    result2 = compute_diff(listing, file_map, vault_type="nas")
    assert len(result2.entries) == 0  # 2nd cycle diff.entries == []
    assert len(file_map["files"]) == 3  # file_map entry 수 == NAS 파일 수
```

#### 3.3.2. test_sync.py — _handle_create_or_modify NAS 입력 단위 테스트

```python
def test_handle_create_or_modify_nas_path_key(tmp_path):
    """NAS vault _handle_create_or_modify: file_map key == path."""
    # setup
    instance_root = tmp_path
    wiki_root = instance_root / "wiki"
    wiki_root.mkdir()
    vault_root = instance_root / "vault" / "nas1"
    vault_root.mkdir(parents=True)
    (vault_root / "a.txt").write_text("hello")
    
    file_map = {"files": {}}
    entry = DiffEntry(
        operation="created",
        source_id="a.txt",  # NAS: source_id == path
        source_relpath="a.txt",
        mime_type="text/plain",
        mtime="2026-06-07T00:00:00Z",
        size=5,
    )
    
    # execute
    _handle_create_or_modify(entry, file_map, instance_root, vault_root, ...)
    
    # verify
    assert "a.txt" in file_map["files"]  # key == path
    assert file_map["files"]["a.txt"]["source_relpath"] == "a.txt"
```

## 4. 영향 분석

### 4.1. Drive vault 회귀

- Drive vault는 `_compute_diff_id_based` 사용 (line 92-169)
- 본 변경은 `_compute_diff_path_based`만 수정
- Drive vault 회귀 0

### 4.2. 기존 NAS file_map 마이그레이션

- 이슈의 "영향 / 리스크" 섹션: "v0.1.11 부터 도입된 회귀로 운영 evidence 는 없으나"
- 아직 운영에서 노출되지 않았으므로 마이그레이션 불필요
- 하지만 혹시 모르니 로그로 경고 추가 가능 (선택)

### 4.3. file_map schema

- schema 변경 없음 (source_id 필드는 유지, 값만 path)
- `file_map["files"][path] = { source_relpath, source_mtime, wiki_path, bytes, last_synced_at }`

## 5. 검증 계획

1. 기존 `tests/test_mount_diff.py` 전체 pass (Drive vault 회귀 없음)
2. 신규 테스트: NAS 3+ 파일 / 2 cycle 회귀 테스트 pass
3. 신규 테스트: `_handle_create_or_modify` NAS 입력 단위 테스트 pass
4. 수동 검증: NAS vault 3+ 파일 / 2 cycle 운영 시 2nd cycle diff.entries == []

## 6. 미결 사항

없음.

---

**approved**: 2026-06-07 (사용자 승인 대기)
