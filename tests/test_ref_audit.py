"""ref_audit 의 referenced_by 중복 전수 검사 테스트 (issue #210 DoD 3·4).

현행 lint 는 단일 페이지만 보고해 전수를 놓쳤다 (실측: lint `entities/AGENTS.md` 2건 vs
실제 362페이지 823건). `ref_audit.py` 가 전수 스캔으로 중복을 검출하는지 검증한다.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_HELPERS = Path(__file__).resolve().parent.parent / "scripts" / "_helpers"
sys.path.insert(0, str(_HELPERS))

import ref_audit as A  # noqa: E402


def _mkpage(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _make_wiki(tmp_path: Path, pages: dict[str, str], sources: dict[str, str] | None = None):
    """pages: {relative path under wiki/: content}, sources: {rel path under wiki/: content}"""
    wiki = tmp_path / "wiki"
    for rel, content in pages.items():
        _mkpage(wiki / rel, content)
    for rel, content in (sources or {}).items():
        _mkpage(wiki / rel, content)
    return tmp_path


# ── 1. 중복 검출 — 같은 source 가 3회 → 초과분 2건
def test_detects_duplicate_refs(tmp_path):
    root = _make_wiki(
        tmp_path,
        {
            "entities/Zebra.md": (
                "---\naliases:\n- Zebra\nreferenced_by:\n"
                "- sources/x/a.md\n- sources/x/b.md\n- sources/x/a.md\n- sources/x/a.md\n---\n"
            ),
            "sources/x/a.md": "Zebra\n",
            "sources/x/b.md": "Zebra\n",
        },
    )
    res = A.audit(root)
    assert res["duplicate_refs"] == 2      # a.md 3회 → 초과분 2
    assert res["duplicate_pages"] == 1
    assert res["duplicate_top"][0]["page"] == "entities/Zebra.md"
    assert res["duplicate_top"][0]["count"] == 2


# ── 2. 중복 없으면 0
def test_no_duplicates_reports_zero(tmp_path):
    root = _make_wiki(
        tmp_path,
        {
            "entities/Zebra.md": (
                "---\naliases:\n- Zebra\nreferenced_by:\n- sources/x/a.md\n- sources/x/b.md\n---\n"
            ),
            "sources/x/a.md": "Zebra\n",
            "sources/x/b.md": "Zebra\n",
        },
    )
    res = A.audit(root)
    assert res["duplicate_refs"] == 0
    assert res["duplicate_pages"] == 0


# ── 3. 전수 스캔 — 여러 페이지의 중복을 모두 합산 (단일 페이지 보고가 아님)
def test_full_scan_aggregates_across_pages(tmp_path):
    root = _make_wiki(
        tmp_path,
        {
            "entities/A.md": (
                "---\naliases:\n- A\nreferenced_by:\n- sources/x/a.md\n- sources/x/a.md\n---\n"
            ),
            "concepts/B.md": (
                "---\naliases:\n- B\nreferenced_by:\n"
                "- sources/x/a.md\n- sources/x/a.md\n- sources/x/a.md\n---\n"
            ),
            "sources/x/a.md": "A B\n",
        },
    )
    res = A.audit(root)
    assert res["duplicate_pages"] == 2     # 두 페이지 모두 검출
    assert res["duplicate_refs"] == 3      # A:1 + B:2


# ── 4. 중복 검사가 기존 verdict 집계를 깨지 않는다
def test_duplicate_scan_does_not_break_other_counts(tmp_path):
    root = _make_wiki(
        tmp_path,
        {
            "entities/Zebra.md": (
                "---\naliases:\n- Zebra\nreferenced_by:\n- sources/x/a.md\n- sources/x/a.md\n---\n"
            ),
            "sources/x/a.md": "Zebra\n",
        },
    )
    res = A.audit(root)
    assert res["duplicate_refs"] == 1
    assert res["total"] == 2               # 중복이어도 total 은 항목 수 그대로
    assert res["ok"] == 2                  # 둘 다 매칭됨


# ── 5. referenced_by 가 없거나 비어도 안전
def test_no_referenced_by_is_safe(tmp_path):
    root = _make_wiki(
        tmp_path,
        {"entities/Empty.md": "---\naliases:\n- Empty\n---\n"},
    )
    res = A.audit(root)
    assert res["duplicate_refs"] == 0
    assert res["total"] == 0


# ── 6. frontmatter 가 dict 가 아니어도 crash 하지 않는다
def test_non_dict_frontmatter_is_safe(tmp_path):
    root = _make_wiki(
        tmp_path,
        {"entities/Weird.md": "---\n- just\n- a\n- list\n---\n"},
    )
    res = A.audit(root)          # 예외 없이 통과해야 함
    assert res["duplicate_refs"] == 0


# ── 7. 비문자열 항목은 중복 집계에서 제외
def test_non_string_refs_ignored(tmp_path):
    root = _make_wiki(
        tmp_path,
        {
            "entities/Zebra.md": (
                "---\naliases:\n- Zebra\nreferenced_by:\n"
                "- sources/x/a.md\n- sources/x/a.md\n- 123\n- null\n---\n"
            ),
            "sources/x/a.md": "Zebra\n",
        },
    )
    res = A.audit(root)
    assert res["duplicate_refs"] == 1      # a.md 2회만 계상, 123/null 무시
