"""source 페이지 frontmatter 작성 (F2 wiki-schema.md §A1 정합).

invariant:
- YAML 1.2 native date·datetime 사용 금지 → string 통일 (sync·agent·grep 디버깅 일관)
- 빈 list 는 ``[]`` flow style
"""
from __future__ import annotations

from typing import Any

import yaml


class _StringDumper(yaml.SafeDumper):
    """본 wikihub 전용 YAML SafeDumper subclass.

    str representer 를 명시적으로 등록해 ISO 8601 같은 date-string 도 plain str 로 emit.
    representer 등록은 본 subclass 에 한정 (PyYAML 의 다른 Dumper·SafeDumper 영향 없음).
    sort_keys 는 emit 호출 시 ``sort_keys=False`` 인자로 처리 (Dumper 자체 설정 아님).
    """


def _str_representer(dumper: yaml.Dumper, data: str):
    # multi-line 은 literal block 으로
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_StringDumper.add_representer(str, _str_representer)


def build_source_frontmatter(
    *,
    title: str,
    vault_id: str,
    relpath: str,
    source_id: str | None,
    source_mtime: str,
    last_synced_at: str,
    extraction_tool: str | None = None,
    extraction_tool_version: str | None = None,
    extracted_at: str | None = None,
    created: str,
    updated: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """source 페이지 frontmatter dict 구성 (wiki-schema.md §A1 자료형 표 정합).

    날짜/시각은 모두 string (YYYY-MM-DD 또는 UTC ISO 8601).
    """
    source: dict[str, Any] = {
        "vault": vault_id,
        "relpath": relpath,
        "source_id": source_id,
        "source_mtime": source_mtime,
        "last_synced_at": last_synced_at,
    }
    if extraction_tool:
        source["extraction"] = {
            "tool": extraction_tool,
            "tool_version": extraction_tool_version or "unknown",
            "extracted_at": extracted_at or last_synced_at,
        }
    return {
        "title": title,
        "source": source,
        "created": created,
        "updated": updated,
        "tags": list(tags or []),
    }


def emit_page(frontmatter: dict[str, Any], body: str) -> str:
    """frontmatter dict + body → 완성된 markdown 페이지 문자열.

    YAML 은 string-only emit (native datetime 회피).
    """
    yaml_text = yaml.dump(
        frontmatter,
        Dumper=_StringDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    ).rstrip()
    body = body.rstrip()
    return f"---\n{yaml_text}\n---\n\n{body}\n"


__all__ = ["build_source_frontmatter", "emit_page"]
