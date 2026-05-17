"""lib/frontmatter.py YAML emit 테스트 (F2 wiki-schema.md §A1)."""
from __future__ import annotations

from lib.frontmatter import build_source_frontmatter, emit_page


def test_build_source_frontmatter_basic() -> None:
    fm = build_source_frontmatter(
        title="Q1 회의",
        vault_id="gdrive",
        relpath="meetings/Q1.pptx",
        source_id="DRIVE_ID_123",
        source_mtime="2026-05-13T01:55:12+00:00",
        last_synced_at="2026-05-13T02:00:00+00:00",
        extraction_tool="python-pptx",
        extraction_tool_version="0.6.21",
        extracted_at="2026-05-13T02:00:00+00:00",
        created="2026-05-13",
        updated="2026-05-13",
    )
    assert fm["title"] == "Q1 회의"
    assert fm["source"]["vault"] == "gdrive"
    assert fm["source"]["source_id"] == "DRIVE_ID_123"
    assert fm["source"]["extraction"]["tool"] == "python-pptx"
    assert fm["tags"] == []


def test_emit_page_string_dates() -> None:
    """YAML 1.2 native datetime 금지 — created 는 string 으로 emit 되어야."""
    fm = {
        "title": "T",
        "source": {"vault": "gdrive", "relpath": "x.md", "source_id": None,
                   "source_mtime": "2026-05-13T01:55:12+00:00",
                   "last_synced_at": "2026-05-13T02:00:00+00:00"},
        "created": "2026-05-13",
        "updated": "2026-05-13",
        "tags": [],
    }
    text = emit_page(fm, body="hello world\n")
    assert text.startswith("---\n")
    assert "---\n\nhello world\n" in text
    # YAML 에서 created 값이 string quoted 또는 plain string (datetime 으로 파싱되면 안 됨)
    # 검증: PyYAML 로 다시 load 했을 때 created 가 str 인지
    import yaml
    body_start = text.index("---\n", 4)
    yaml_section = text[4:body_start]
    parsed = yaml.safe_load(yaml_section)
    assert isinstance(parsed["created"], str), f"created 는 string 이어야: {type(parsed['created'])}"


def test_emit_page_no_extraction_block() -> None:
    """extraction 정보 없으면 frontmatter 에 extraction 키 미포함."""
    fm = build_source_frontmatter(
        title="md doc",
        vault_id="gdrive",
        relpath="x.md",
        source_id="ID1",
        source_mtime="2026-05-13T01:00:00+00:00",
        last_synced_at="2026-05-13T01:00:00+00:00",
        created="2026-05-13",
        updated="2026-05-13",
    )
    assert "extraction" not in fm["source"]


def test_emit_page_unicode_preserved() -> None:
    fm = build_source_frontmatter(
        title="회의록 (Q1)",
        vault_id="gdrive",
        relpath="meetings/Q1.md",
        source_id=None,
        source_mtime="2026-05-13T01:00:00+00:00",
        last_synced_at="2026-05-13T01:00:00+00:00",
        created="2026-05-13",
        updated="2026-05-13",
    )
    text = emit_page(fm, body="본문")
    assert "회의록" in text
    assert "본문" in text
