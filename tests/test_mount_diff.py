"""lib/mount_diff.py compute_diff 테스트 (ADR-0035)."""
from __future__ import annotations

import pytest

from lib.mount_diff import compute_diff


def _listing_item(
    *,
    id: str,
    path: str,
    mtime: str = "2026-05-19T00:00:00.000Z",
    mime: str = "text/markdown",
    size: int = 100,
    is_dir: bool = False,
) -> dict:
    return {
        "ID": id,
        "Path": path,
        "Name": path.split("/")[-1],
        "MimeType": mime,
        "ModTime": mtime,
        "Size": size,
        "IsDir": is_dir,
    }


def _file_map(files: dict[str, dict]) -> dict:
    return {"vault_id": "gdrive", "updated_at": None, "files": files}


# ---------------------------------------------------------------------------
# 분류 단위 테스트
# ---------------------------------------------------------------------------

def test_created_when_listing_id_absent_from_file_map() -> None:
    listing = [_listing_item(id="id_a", path="a.md")]
    file_map = _file_map({})

    diff = compute_diff(listing, file_map)

    assert len(diff.entries) == 1
    e = diff.entries[0]
    assert e.operation == "created"
    assert e.source_id == "id_a"
    assert e.source_relpath == "a.md"
    assert diff.listing_count == 1
    assert diff.file_map_count_before == 0


def test_modified_when_mtime_differs() -> None:
    listing = [_listing_item(id="id_a", path="a.md", mtime="2026-05-20T00:00:00Z")]
    file_map = _file_map({
        "id_a": {
            "source_relpath": "a.md",
            "source_mtime": "2026-05-19T00:00:00Z",
            "wiki_path": "wiki/sources/gdrive/a.md",
            "bytes": 100,
            "last_synced_at": "2026-05-19T00:00:00Z",
        }
    })

    diff = compute_diff(listing, file_map)

    assert len(diff.entries) == 1
    e = diff.entries[0]
    assert e.operation == "modified"
    assert e.source_id == "id_a"


def test_renamed_when_path_differs_same_id() -> None:
    listing = [_listing_item(id="id_a", path="renamed.md")]
    file_map = _file_map({
        "id_a": {
            "source_relpath": "original.md",
            "source_mtime": "2026-05-19T00:00:00.000Z",
            "wiki_path": "wiki/sources/gdrive/original.md",
            "bytes": 100,
            "last_synced_at": "2026-05-19T00:00:00Z",
        }
    })

    diff = compute_diff(listing, file_map)

    assert len(diff.entries) == 1
    e = diff.entries[0]
    assert e.operation == "renamed"
    assert e.source_id == "id_a"
    assert e.source_relpath == "renamed.md"
    assert e.prev_source_relpath == "original.md"


def test_deleted_when_file_map_id_absent_from_listing() -> None:
    listing: list[dict] = []
    file_map = _file_map({
        "id_a": {
            "source_relpath": "gone.md",
            "source_mtime": "2026-05-19T00:00:00Z",
            "wiki_path": "wiki/sources/gdrive/gone.md",
            "bytes": 100,
            "last_synced_at": "2026-05-19T00:00:00Z",
        }
    })

    diff = compute_diff(listing, file_map)

    assert len(diff.entries) == 1
    e = diff.entries[0]
    assert e.operation == "deleted"
    assert e.source_id == "id_a"
    assert e.prev_source_relpath == "gone.md"
    assert diff.delete_ratio == 1.0


def test_unchanged_skipped() -> None:
    listing = [_listing_item(id="id_a", path="a.md", mtime="2026-05-19T00:00:00Z")]
    file_map = _file_map({
        "id_a": {
            "source_relpath": "a.md",
            "source_mtime": "2026-05-19T00:00:00Z",
            "wiki_path": "wiki/sources/gdrive/a.md",
            "bytes": 100,
            "last_synced_at": "2026-05-19T00:00:00Z",
        }
    })

    diff = compute_diff(listing, file_map)

    assert diff.entries == []


def test_directories_excluded_from_diff() -> None:
    listing = [
        _listing_item(id="dir_a", path="folder", is_dir=True, mime="inode/directory"),
        _listing_item(id="id_b", path="b.md"),
    ]
    file_map = _file_map({})

    diff = compute_diff(listing, file_map)

    assert len(diff.entries) == 1
    assert diff.entries[0].source_id == "id_b"


def test_null_id_excluded_from_diff() -> None:
    """rclone lsjson 의 일부 항목은 ID 가 비어있을 수 있음 — file_map 키로 부적합 → skip."""
    listing = [
        {"Path": "ghost.md", "Name": "ghost.md", "Size": 0, "MimeType": "text/markdown",
         "ModTime": "2026-05-19T00:00:00Z", "IsDir": False, "ID": ""},
        _listing_item(id="id_b", path="b.md"),
    ]
    file_map = _file_map({})

    diff = compute_diff(listing, file_map)

    assert len(diff.entries) == 1
    assert diff.entries[0].source_id == "id_b"


# ---------------------------------------------------------------------------
# delete_ratio 가드 테스트
# ---------------------------------------------------------------------------

def test_delete_ratio_zero_when_empty_file_map() -> None:
    listing: list[dict] = []
    file_map = _file_map({})
    diff = compute_diff(listing, file_map)
    assert diff.delete_ratio == 0.0


def test_delete_ratio_half() -> None:
    listing = [_listing_item(id="id_a", path="a.md")]
    file_map = _file_map({
        "id_a": {"source_relpath": "a.md", "source_mtime": "2026-05-19T00:00:00.000Z",
                 "wiki_path": "wiki/sources/gdrive/a.md", "bytes": 100,
                 "last_synced_at": "2026-05-19T00:00:00Z"},
        "id_b": {"source_relpath": "b.md", "source_mtime": "2026-05-19T00:00:00Z",
                 "wiki_path": "wiki/sources/gdrive/b.md", "bytes": 100,
                 "last_synced_at": "2026-05-19T00:00:00Z"},
    })
    diff = compute_diff(listing, file_map)
    assert diff.deleted_count == 1
    assert diff.delete_ratio == 0.5


# ---------------------------------------------------------------------------
# NAS vault 테스트 (ADR-0045)
# ---------------------------------------------------------------------------

def _nas_listing_item(
    *,
    path: str,
    mtime: str = "2026-06-07T00:00:00.000Z",
    mime: str = "text/plain",
    size: int = 100,
) -> dict:
    """NAS vault listing item (ID is empty, Path-based)."""
    return {
        "ID": "",  # NAS: ID is empty
        "Path": path,
        "Name": path.split("/")[-1],
        "MimeType": mime,
        "ModTime": mtime,
        "Size": size,
        "IsDir": False,
    }


def test_nas_created_uses_path_as_source_id() -> None:
    """NAS vault created entry: source_id == path (ADR-0045)."""
    listing = [_nas_listing_item(path="a.txt")]
    file_map = _file_map({})

    diff = compute_diff(listing, file_map, vault_type="nas")

    assert len(diff.entries) == 1
    e = diff.entries[0]
    assert e.operation == "created"
    assert e.source_id == "a.txt"  # source_id == path
    assert e.source_relpath == "a.txt"


def test_nas_multi_file_2_cycle_no_false_created() -> None:
    """NAS vault 3+ 파일 / 2 cycle 운영 시 2nd cycle diff.entries == [] (정상 unchanged).

    Issue #134 회귀 테스트: source_id="" 하드코딩 시 2nd cycle 에 a.txt, b.txt 가
    created 로 재분류되어 매 cycle 재처리되는 문제 검증.
    """
    # 1st cycle: file_map 비어있음, listing 3건
    listing = [
        _nas_listing_item(path="a.txt", mtime="2026-06-07T00:00:00Z", size=100),
        _nas_listing_item(path="b.txt", mtime="2026-06-07T00:00:00Z", size=200),
        _nas_listing_item(path="c.txt", mtime="2026-06-07T00:00:00Z", size=300),
    ]
    file_map = _file_map({})

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

    # file_map entry 수 == NAS 파일 수
    assert len(file_map["files"]) == 3

    # 2nd cycle: 소스 변경 없음
    result2 = compute_diff(listing, file_map, vault_type="nas")
    assert len(result2.entries) == 0  # 2nd cycle diff.entries == []


def test_nas_modified_when_mtime_differs() -> None:
    """NAS vault modified: path 동일, mtime 변경."""
    listing = [_nas_listing_item(path="a.txt", mtime="2026-06-08T00:00:00Z")]
    file_map = _file_map({
        "a.txt": {  # NAS: key == path
            "source_relpath": "a.txt",
            "source_mtime": "2026-06-07T00:00:00Z",
            "wiki_path": "wiki/a.txt.md",
            "bytes": 100,
            "last_synced_at": "2026-06-07T00:00:00Z",
        },
    })

    diff = compute_diff(listing, file_map, vault_type="nas")

    assert len(diff.entries) == 1
    e = diff.entries[0]
    assert e.operation == "modified"
    assert e.source_id == "a.txt"  # source_id == path
    assert e.source_relpath == "a.txt"


def test_nas_deleted_when_path_absent_from_listing() -> None:
    """NAS vault deleted: file_map의 path가 listing에 없음."""
    listing = []  # empty listing
    file_map = _file_map({
        "a.txt": {
            "source_relpath": "a.txt",
            "source_mtime": "2026-06-07T00:00:00Z",
            "wiki_path": "wiki/a.txt.md",
            "bytes": 100,
            "last_synced_at": "2026-06-07T00:00:00Z",
        },
    })

    diff = compute_diff(listing, file_map, vault_type="nas")

    assert len(diff.entries) == 1
    e = diff.entries[0]
    assert e.operation == "deleted"
    assert e.source_id == "a.txt"  # source_id == path
    assert e.source_relpath == "a.txt"


def test_nas_legacy_empty_source_id_entry(caplog: pytest.LogCaptureFixture) -> None:
    """NAS vault 레거시 source_id=\"\" entry 감지 시 경고 로그 출력 (ADR-0045).

    기존 file_map에 source_id=\"\"로 저장된 entry가 있으면:
    1. files_by_path 재구성은 source_relpath 기반으로 정상 동작
    2. 로그 경고 출력 (레거시 entry 감지)
    3. modified 시 source_id=\"\"가 유지됨 (기존 동작 보존)
    """
    import logging

    # 레거시 file_map: source_id=""로 저장된 entry
    listing = [_nas_listing_item(path="a.txt", mtime="2026-06-08T00:00:00Z")]
    file_map = _file_map({
        "": {  # 레거시: source_id=""
            "source_relpath": "a.txt",
            "source_mtime": "2026-06-07T00:00:00Z",
            "wiki_path": "wiki/a.txt.md",
            "bytes": 100,
            "last_synced_at": "2026-06-07T00:00:00Z",
        },
    })

    with caplog.at_level(logging.WARNING):
        diff = compute_diff(listing, file_map, vault_type="nas")

    # 경고 로그 확인
    assert any("legacy NAS file_map entry detected" in record.message for record in caplog.records)

    # modified entry: source_id="" 유지 (기존 동작)
    assert len(diff.entries) == 1
    e = diff.entries[0]
    assert e.operation == "modified"
    assert e.source_id == ""  # 레거시 source_id 유지
    assert e.source_relpath == "a.txt"


