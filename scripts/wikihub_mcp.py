#!/usr/bin/env python3
"""WikiHub MCP server — read-only wiki query (ADR-0043).

호출: stdio mode. 외부 MCP-호환 client (Claude Desktop / Cline / IDE plugin 등) 가
SSH 로 wikihub VM 에 원격 spawn (`ssh wikihub-oci 'python wikihub_mcp.py'`).
daemon 없음 — per-session subprocess.

Scope: **read-only**. wiki/ + frontmatter 만. write 0. OAuth credential 접근 0.

Resources (4 base + 1 dynamic):
- wikihub://entities          — entities 목록
- wikihub://concepts          — concepts 목록
- wikihub://analyses          — analyses 목록
- wikihub://sources/<vid>     — vault 별 source 목록 (dynamic, vault_id ∈ wikihub.yaml.vaults[*].id)
- wikihub://page/<cat>/<name> — 단일 page (entities/concepts/analyses/sources). ADR-0042 resolver 적용

Tools (5):
- list_entities(filter?)
- list_concepts(filter?)
- read_page(category, name)
- grep_wiki(pattern, category?)
- search_by_alias(name)

본문 LLM 호출 0 — semantic synthesis 는 client 측 LLM 책임 (ADR-0043 §Hermes layer 분리).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import yaml
from mcp import types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server


# ─── paths (ADR-0034 data-first layout) ──────────────────────────────────
WIKIHUB_HOME = Path(
    os.environ.get("WIKIHUB_HOME", str(Path.home() / "wikihub"))
).expanduser().resolve()
WIKI_ROOT = WIKIHUB_HOME / "wiki"
YAML_PATH = WIKIHUB_HOME / "wikihub.yaml"

# entities/concepts 만 alias resolver 적용. analyses 는 slug 식, sources 는 vault-prefix 필수.
_ALIAS_CATEGORIES = ("entities", "concepts")


# ─── frontmatter parse (O5: pyyaml.safe_load — read-only, 의존성 최소) ───
_FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _read_frontmatter(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    m = _FM_RE.match(text)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _split_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    """returns (frontmatter_dict, body_text)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}, ""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    return (fm if isinstance(fm, dict) else {}), text[m.end():]


# ─── alias index — ADR-0042 정합, per-process lazy cache ─────────────────
_alias_index_cache: dict[str, str] | None = None


def _build_alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for category in _ALIAS_CATEGORIES:
        cat_dir = WIKI_ROOT / category
        if not cat_dir.is_dir():
            continue
        for page in sorted(cat_dir.glob("*.md")):
            canonical = page.stem
            fm = _read_frontmatter(page)
            aliases = fm.get("aliases") or [canonical]
            if not isinstance(aliases, list):
                aliases = [canonical]
            for alias in aliases:
                if not isinstance(alias, str):
                    continue
                key = alias.strip().lower()
                if not key:
                    continue
                if key in index and index[key] != canonical:
                    # 충돌 — lint Step 4.5 duplicate detection 책임. resolver 는 첫 등록 유지.
                    continue
                index[key] = canonical
    return index


def _get_alias_index() -> dict[str, str]:
    """per-session lifetime cache. session 종료 시 reset — 다음 spawn 시 fresh build.
    lint 가 alias 변경해도 현 session 안에서는 stale. per-session spawn 모델상 실운영 영향 미미."""
    global _alias_index_cache
    if _alias_index_cache is None:
        _alias_index_cache = _build_alias_index()
    return _alias_index_cache


# ─── vault_id (ADR-0019 + O4 validation) ──────────────────────────────────
_vault_ids_cache: list[str] | None = None


def _list_vault_ids() -> list[str]:
    global _vault_ids_cache
    if _vault_ids_cache is not None:
        return _vault_ids_cache
    if not YAML_PATH.is_file():
        _vault_ids_cache = []
        return _vault_ids_cache
    try:
        cfg = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        _vault_ids_cache = []
        return _vault_ids_cache
    vaults = cfg.get("vaults") or []
    _vault_ids_cache = [
        v.get("id") for v in vaults
        if isinstance(v, dict) and isinstance(v.get("id"), str)
    ]
    return _vault_ids_cache


# ─── path traversal guard — wiki/ scope 외 read 차단 (M2) ────────────────
def _safe_under(target: Path, base: Path) -> bool:
    """target 이 base 하위인지 정규화 비교. symlink 포함 resolve."""
    try:
        return target.resolve().is_relative_to(base.resolve())
    except (OSError, ValueError):
        return False


# ─── ADR-0042 resolver (entities/concepts 한정) ─────────────────────────
def _resolve_page(category: str, name: str) -> tuple[Path | None, str]:
    """returns (resolved_path or None, via). via in {"exact", "alias", "missing"}."""
    cat_root = WIKI_ROOT / category
    target = cat_root / f"{name}.md"
    if target.is_file() and _safe_under(target, cat_root):
        return target, "exact"
    if category in _ALIAS_CATEGORIES:
        canonical = _get_alias_index().get(name.strip().lower())
        if canonical:
            via_target = cat_root / f"{canonical}.md"
            if via_target.is_file() and _safe_under(via_target, cat_root):
                return via_target, "alias"
    return None, "missing"


# ─── tool implementations (read-only) ────────────────────────────────────
def _list_pages(category: str, filter_substr: str = "") -> list[dict[str, Any]]:
    """entities/concepts/analyses 단순 enumeration."""
    cat_dir = WIKI_ROOT / category
    if not cat_dir.is_dir():
        return []
    results: list[dict[str, Any]] = []
    flt = filter_substr.strip().lower()
    for page in sorted(cat_dir.glob("*.md")):
        canonical = page.stem
        fm = _read_frontmatter(page)
        raw_aliases = fm.get("aliases") or [canonical]
        aliases = [a for a in raw_aliases if isinstance(a, str)] if isinstance(raw_aliases, list) else [canonical]
        if flt:
            haystack = " ".join([canonical, *aliases]).lower()
            if flt not in haystack:
                continue
        summary = fm.get("summary", "")
        results.append({
            "name": canonical,
            "aliases": aliases,
            "summary": summary[:200] if isinstance(summary, str) else "",
        })
    return results


def _list_sources(vault_id: str) -> list[dict[str, Any]]:
    """O4: vault_id 미존재 시 ValueError raise (ToolError 변환)."""
    available = _list_vault_ids()
    if vault_id not in available:
        raise ValueError(f"vault_id '{vault_id}' 미존재. 가용 vault: {available}")
    src_dir = WIKI_ROOT / "sources" / vault_id
    if not src_dir.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(src_dir.rglob("*.md")):
        try:
            stat = path.stat()
        except OSError:
            continue
        results.append({
            "relpath": str(path.relative_to(src_dir)),
            "size_bytes": stat.st_size,
            "mtime": stat.st_mtime,
        })
    return results


def _read_page_tool(category: str, name: str) -> dict[str, Any]:
    if category == "sources":
        # name = "<vault_id>/<path>" 형식. multi-slash URI 그대로
        if "/" not in name:
            raise ValueError("sources 는 name 이 '<vault_id>/<path>' 형식 필요 (예: 'gdrive/meetings/Q1.pptx')")
        vault_id, _, rel = name.partition("/")
        available = _list_vault_ids()
        if vault_id not in available:
            raise ValueError(f"vault_id '{vault_id}' 미존재. 가용: {available}")
        src_root = WIKI_ROOT / "sources" / vault_id
        target = src_root / f"{rel}.md"
        # M2: path traversal 차단 — `<vault_id>/../../secret` 같은 입력으로 wiki/ 바깥 read 회피
        if not target.is_file() or not _safe_under(target, src_root):
            raise ValueError(f"sources/{vault_id}/{rel}.md 미존재 또는 scope 외 path")
        fm, body = _split_frontmatter(target)
        return {
            "canonical_name": rel,
            "category": "sources",
            "vault_id": vault_id,
            "frontmatter": fm,
            "body": body,
            "resolved_via": "exact",
        }
    if category not in (*_ALIAS_CATEGORIES, "analyses"):
        raise ValueError(f"category must be one of entities, concepts, analyses, sources — got '{category}'")
    resolved, via = _resolve_page(category, name)
    if resolved is None:
        if category in _ALIAS_CATEGORIES:
            raise ValueError(f"{category}/{name} (또는 alias 매핑) 미존재")
        raise ValueError(f"{category}/{name} 미존재")
    fm, body = _split_frontmatter(resolved)
    return {
        "canonical_name": resolved.stem,
        "category": category,
        "frontmatter": fm,
        "body": body,
        "resolved_via": via,
    }


def _grep_wiki(pattern: str, category: str = "", max_results: int = 200) -> list[dict[str, Any]]:
    try:
        regex = re.compile(pattern)
    except re.error as e:
        raise ValueError(f"invalid regex: {e}")
    # Skip: wiki/.archived/, wiki/_lint/. 검색 범위: 본문 + frontmatter (full text)
    skip_prefixes = (".archived/", "_lint/")
    if category:
        targets = [WIKI_ROOT / category]
    else:
        targets = [WIKI_ROOT / c for c in ("entities", "concepts", "analyses")]
        for vid in _list_vault_ids():
            targets.append(WIKI_ROOT / "sources" / vid)
    results: list[dict[str, Any]] = []
    for cat_dir in targets:
        if not cat_dir.is_dir():
            continue
        for path in cat_dir.rglob("*.md"):
            rel = path.relative_to(WIKI_ROOT)
            rel_str = str(rel)
            if any(rel_str.startswith(p) for p in skip_prefixes):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(lines):
                if regex.search(line):
                    ctx_start = max(0, i - 2)
                    ctx_end = min(len(lines), i + 3)
                    snippet = "\n".join(lines[ctx_start:ctx_end])
                    results.append({
                        "path": f"wiki/{rel_str}",
                        "line": i + 1,
                        "snippet": snippet,
                    })
                    if len(results) >= max_results:
                        return results
    return results


def _search_by_alias(name: str) -> list[dict[str, Any]]:
    key = name.strip().lower()
    if not key:
        return []
    out: list[dict[str, Any]] = []
    for category in _ALIAS_CATEGORIES:
        cat_dir = WIKI_ROOT / category
        if not cat_dir.is_dir():
            continue
        for page in sorted(cat_dir.glob("*.md")):
            canonical = page.stem
            fm = _read_frontmatter(page)
            raw_aliases = fm.get("aliases") or [canonical]
            aliases = [a for a in raw_aliases if isinstance(a, str)] if isinstance(raw_aliases, list) else [canonical]
            for alias in aliases:
                if alias.strip().lower() == key:
                    out.append({
                        "category": category,
                        "canonical_name": canonical,
                        "matched_alias": alias,
                    })
                    break
    return out


# ─── MCP server bindings ──────────────────────────────────────────────────
server: Server = Server("wikihub-mcp")


@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    resources: list[types.Resource] = [
        types.Resource(
            uri="wikihub://entities",
            name="Wiki entities",
            description="entities/ 디렉토리 page 목록 (canonical name + aliases + summary)",
            mimeType="application/json",
        ),
        types.Resource(
            uri="wikihub://concepts",
            name="Wiki concepts",
            description="concepts/ 디렉토리 page 목록",
            mimeType="application/json",
        ),
        types.Resource(
            uri="wikihub://analyses",
            name="Wiki analyses",
            description="analyses/ 디렉토리 page 목록 (/wh-query 가 자동 저장)",
            mimeType="application/json",
        ),
    ]
    for vid in _list_vault_ids():
        resources.append(types.Resource(
            uri=f"wikihub://sources/{vid}",
            name=f"Wiki sources ({vid})",
            description=f"vault '{vid}' 의 source page 목록 (relpath + size + mtime)",
            mimeType="application/json",
        ))
    return resources


@server.read_resource()
async def handle_read_resource(uri: Any) -> str:
    parsed = urlparse(str(uri))
    if parsed.scheme != "wikihub":
        raise ValueError(f"unsupported scheme: {parsed.scheme!r}")
    netloc = unquote(parsed.netloc)
    # URI segment 별 percent-decode. spec-compliant client (Claude Desktop 등) 가 공백·한글
    # 을 `%20` / `%XX` 로 encode 해서 보낼 때 alias index 키와 정합 매칭 (ADR-0042 정합).
    parts = [unquote(p) for p in parsed.path.split("/") if p]
    if netloc in ("entities", "concepts", "analyses") and not parts:
        return json.dumps(_list_pages(netloc), ensure_ascii=False, indent=2)
    if netloc == "sources":
        if not parts:
            raise ValueError("wikihub://sources URI 는 vault_id 필요 (예: wikihub://sources/gdrive)")
        return json.dumps(
            _list_sources(parts[0]),
            ensure_ascii=False, indent=2, default=str,
        )
    if netloc == "page":
        if len(parts) < 2:
            raise ValueError("wikihub://page URI 는 '<category>/<name>' 형식 (예: wikihub://page/entities/MiniMax)")
        category = parts[0]
        name = "/".join(parts[1:])
        return json.dumps(
            _read_page_tool(category, name),
            ensure_ascii=False, indent=2, default=str,
        )
    raise ValueError(f"unknown wikihub resource: {uri!r}")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_entities",
            description="wiki/entities/ page 목록. filter (substring) 가 비어있지 않으면 name + aliases 에 포함된 page 만.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {"type": "string", "description": "substring filter (case-insensitive). 빈 문자열이면 전체."},
                },
            },
        ),
        types.Tool(
            name="list_concepts",
            description="wiki/concepts/ page 목록. filter 동일.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="read_page",
            description=(
                "단일 page 의 frontmatter + body read. entities/concepts 는 ADR-0042 resolver 적용 — "
                "alias form (예: 'mini-max') 입력해도 canonical page ('MiniMax') 로 resolve. "
                "sources 는 name 이 '<vault_id>/<path>' 형식 필요."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": ["entities", "concepts", "analyses", "sources"]},
                    "name": {"type": "string"},
                },
                "required": ["category", "name"],
            },
        ),
        types.Tool(
            name="grep_wiki",
            description=(
                "wiki/ 전체 또는 특정 category 의 .md 파일에서 regex 검색. "
                "Skip: wiki/.archived/, wiki/_lint/. 검색 범위: 본문 + frontmatter (full text). "
                "최대 200건 (cost gate)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Python regex"},
                    "category": {"type": "string", "description": "선택 — entities/concepts/analyses/sources/<vid>"},
                },
                "required": ["pattern"],
            },
        ),
        types.Tool(
            name="search_by_alias",
            description=(
                "ADR-0042 alias index lookup. entities/concepts 중 frontmatter `aliases` 에 "
                "(lowercase) name 매칭되는 page 모두 반환. 매칭 0건 빈 list."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                },
                "required": ["name"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    try:
        if name == "list_entities":
            data: Any = _list_pages("entities", arguments.get("filter", ""))
        elif name == "list_concepts":
            data = _list_pages("concepts", arguments.get("filter", ""))
        elif name == "read_page":
            data = _read_page_tool(arguments["category"], arguments["name"])
        elif name == "grep_wiki":
            data = _grep_wiki(arguments["pattern"], arguments.get("category", ""))
        elif name == "search_by_alias":
            data = _search_by_alias(arguments["name"])
        else:
            raise ValueError(f"unknown tool: {name!r}")
    except (ValueError, KeyError) as e:
        return [types.TextContent(type="text", text=f"error: {e}")]
    return [types.TextContent(
        type="text",
        text=json.dumps(data, ensure_ascii=False, indent=2, default=str),
    )]


async def _amain() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="wikihub-mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
