"""lib/mount_diff.py compute_diff 테스트 (ADR-0035)."""
from __future__ import annotations

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
