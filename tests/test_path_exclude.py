"""`lib.path_exclude` 단위 테스트 (issue #221)."""
from __future__ import annotations

import unicodedata

import pytest

from lib.exceptions import VaultSyncFatal
from lib.path_exclude import (
    filter_listing,
    is_excluded,
    normalize_prefixes,
    prune_file_map,
)


def test_normalize_prefixes_strips_leading_markers() -> None:
    """선두 '/' 와 './' 를 제거한다."""
    assert normalize_prefixes(["/project/a", "./project/b"]) == [
        "project/a/",
        "project/b/",
    ]


def test_normalize_prefixes_appends_trailing_slash() -> None:
    """말미 '/' 가 없으면 자동으로 추가한다."""
    assert normalize_prefixes(["project/report"]) == ["project/report/"]


def test_normalize_prefixes_nfd_to_nfc() -> None:
    """NFD 입력을 NFC 로 정규화한다."""
    nfd = unicodedata.normalize("NFD", "프로젝트/보고서")
    result = normalize_prefixes([nfd])
    assert result == [unicodedata.normalize("NFC", nfd) + "/"]


def test_normalize_prefixes_deduplicates() -> None:
    """정규화 후 중복 항목을 제거한다."""
    assert normalize_prefixes(["a/", "/a", "./a"]) == ["a/"]


def test_normalize_prefixes_none_and_empty() -> None:
    """None 과 빈 시퀀스는 빈 리스트가 된다."""
    assert normalize_prefixes(None) == []
    assert normalize_prefixes([]) == []


def test_normalize_prefixes_rejects_empty_item() -> None:
    """빈 문자열 항목은 VaultSyncFatal 을 발생시킨다."""
    with pytest.raises(VaultSyncFatal):
        normalize_prefixes([""])


def test_normalize_prefixes_rejects_root_slash() -> None:
    """'/' 만 있는 항목은 VaultSyncFatal 을 발생시킨다."""
    with pytest.raises(VaultSyncFatal):
        normalize_prefixes(["/"])


def test_normalize_prefixes_rejects_non_string() -> None:
    """문자열이 아닌 항목은 VaultSyncFatal 을 발생시킨다."""
    with pytest.raises(VaultSyncFatal):
        normalize_prefixes([123])


def test_is_excluded_directory_boundary() -> None:
    """'report/' 는 'report/a.md' 를 매치하고 'report2/a.md' 는 매치하지 않는다."""
    prefixes = normalize_prefixes(["project/wikihub/report/"])
    assert is_excluded("project/wikihub/report/a.md", prefixes) is True
    assert is_excluded("project/wikihub/report2/a.md", prefixes) is False


def test_is_excluded_empty_prefixes() -> None:
    """prefixes 가 비면 항상 False 를 반환한다."""
    assert is_excluded("project/report/a.md", []) is False


def test_filter_listing_removes_matches_and_counts() -> None:
    """매치 항목만 제거하고 제외 건수를 반환한다."""
    listing = [
        {"Path": "project/report/a.md"},
        {"Path": "project/other/b.md"},
        {"Path": "project/report/c.md"},
    ]
    kept, excluded = filter_listing(listing, ["project/report/"])
    assert [item["Path"] for item in kept] == ["project/other/b.md"]
    assert excluded == 2


def test_filter_listing_does_not_mutate_input() -> None:
    """입력 리스트를 변형하지 않는다."""
    listing = [{"Path": "project/report/a.md"}, {"Path": "keep.md"}]
    original = [dict(item) for item in listing]
    filter_listing(listing, ["project/report/"])
    assert listing == original


def test_filter_listing_preserves_items_without_path() -> None:
    """Path 키가 없거나 None 인 항목은 보존한다."""
    listing = [{"Name": "a.md"}, {"Path": None}, {"Path": "project/report/b.md"}]
    kept, excluded = filter_listing(listing, ["project/report/"])
    assert kept == [{"Name": "a.md"}, {"Path": None}]
    assert excluded == 1


def test_prune_file_map_removes_matches() -> None:
    """매치 엔트리만 제거한다."""
    file_map = {
        "files": {
            "1": {"source_relpath": "project/report/a.md"},
            "2": {"source_relpath": "project/other/b.md"},
        }
    }
    pruned, removed = prune_file_map(file_map, ["project/report/"])
    assert list(pruned["files"]) == ["2"]
    assert removed == ["project/report/a.md"]


def test_prune_file_map_returns_sorted_removed() -> None:
    """제거된 source_relpath 를 정렬해 반환한다."""
    file_map = {
        "files": {
            "1": {"source_relpath": "project/report/z.md"},
            "2": {"source_relpath": "project/report/a.md"},
        }
    }
    _, removed = prune_file_map(file_map, ["project/report/"])
    assert removed == ["project/report/a.md", "project/report/z.md"]


def test_prune_file_map_does_not_mutate_input() -> None:
    """원본 file_map 을 변형하지 않는다."""
    file_map = {"version": 1, "files": {"1": {"source_relpath": "project/report/a.md"}}}
    prune_file_map(file_map, ["project/report/"])
    assert file_map == {"version": 1, "files": {"1": {"source_relpath": "project/report/a.md"}}}


def test_prune_file_map_without_files_key() -> None:
    """files 키가 없으면 빈 files 를 추가한 새 dict 를 반환한다."""
    pruned, removed = prune_file_map({"version": 1}, ["project/report/"])
    assert pruned == {"version": 1, "files": {}}
    assert removed == []
