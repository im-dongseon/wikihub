"""lib/extraction.py dispatch + passthrough 테스트.

binary extraction 은 실제 lib 의존성 필요 — install 안 됐을 때 skip.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lib.extraction import (
    GWS_EXPORT_MIME,
    LOCAL_EXTRACTION_DISPATCH,
    extract,
    extract_text,
)


def test_extract_text_md(tmp_path: Path) -> None:
    p = tmp_path / "a.md"
    p.write_text("# hello\n\nbody\n", encoding="utf-8")
    er = extract_text(p)
    assert er.extraction_status == "success"
    assert "hello" in er.body_text
    assert er.tool == "passthrough"


def test_extract_text_cp949_fallback(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_bytes("한국어 텍스트".encode("cp949"))
    er = extract_text(p)
    assert er.extraction_status == "success"
    assert "한국어" in er.body_text


def test_extract_unsupported_mime_failed(tmp_path: Path) -> None:
    p = tmp_path / "a.bin"
    p.write_bytes(b"\x00\x01\x02")
    er = extract(p, mime_type="application/octet-stream")
    assert er.extraction_status == "failed"
    assert "unsupported MIME" in er.reason


def test_extract_dispatch_keys_covered() -> None:
    # F2 wiki-schema.md §A3 정합 — 4 binary + 2 text 매핑
    for mime in [
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/pdf",
        "text/markdown",
        "text/plain",
    ]:
        assert mime in LOCAL_EXTRACTION_DISPATCH


def test_gws_export_mime_mapping() -> None:
    # Google native MIME → export MIME (L1 정합)
    assert GWS_EXPORT_MIME["application/vnd.google-apps.document"] == "text/markdown"
    assert GWS_EXPORT_MIME["application/vnd.google-apps.spreadsheet"] == "text/csv"
    assert GWS_EXPORT_MIME["application/vnd.google-apps.presentation"] == "text/plain"


@pytest.mark.skip(reason="python-pptx 등 binary extraction 은 실제 fixture + install 필요 — V8")
def test_extract_pptx_fixture(tmp_path: Path) -> None:
    pass
