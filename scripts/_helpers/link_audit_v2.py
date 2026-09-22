#!/usr/bin/env python3
"""Step 2 — ADR-0001 link 규약 검증 (v2)

WikiHub 정본 helper (#201 ⑥ 정본화, ADR-0034 data-first layout 정합).

경로 복원 체계 (fail-safe 순서):
  1. `--wiki-home` / `--src` CLI arg
  2. `WIKIHUB_HOME` / `WIKIHUB_SRC` env
  3. `WIKIHUB_YAML` env 의 부모 디렉토리  (lint/graphify/ingest systemd unit 이 주입)
  4. `~/wikihub` / `~/.local/share/wikihub/src`  (ADR-0034 default)

원 운영 로컬 버전(`$WIKIHUB_HOME/_scripts/`)은 `/home/ubuntu/wikihub` 을
하드코딩했으나, 본 정본은 이식 가능하게 정규화했다. **판정 로직은 무변경.**
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _resolve_wiki_home(explicit: "str | None" = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("WIKIHUB_HOME")
    if env:
        return Path(env).expanduser().resolve()
    yaml_env = os.environ.get("WIKIHUB_YAML")
    if yaml_env:
        return Path(yaml_env).expanduser().resolve().parent
    return Path("~/wikihub").expanduser().resolve()


def _resolve_src(explicit: "str | None" = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("WIKIHUB_SRC")
    if env:
        return Path(env).expanduser().resolve()
    return Path("~/.local/share/wikihub/src").expanduser().resolve()


def _parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Step 2 — ADR-0001 link 규약 검증 (v2)")
    parser.add_argument("--wiki-home", default=None,
                        help="WIKIHUB_HOME (default: $WIKIHUB_HOME > $WIKIHUB_YAML 부모 > ~/wikihub)")
    parser.add_argument("--src", default=None,
                        help="WIKIHUB_SRC (default: $WIKIHUB_SRC > ~/.local/share/wikihub/src)")
    args, _unknown = parser.parse_known_args()
    return args


_ARGS = _parse_cli()
WIKIHUB_HOME: Path = _resolve_wiki_home(_ARGS.wiki_home)
WIKIHUB_SRC: Path = _resolve_src(_ARGS.src)


import json, os, re

WIKI = str(WIKIHUB_HOME / "wiki")
VAULTS = {"nas"}  # from wikihub.yaml

with open(WIKIHUB_HOME / "wiki" / "_lint" / "alias_index.json") as f:
    alias_index = json.load(f)

OUT_DIR = str(WIKIHUB_HOME / "wiki" / "_lint")

violations = {
    "shortcut_in_sources": [],
    "unknown_vault_prefix": [],
    "dangling_vault_path": [],
    "dangling_entity_concept": []
}

# Patterns that indicate the [[...]] is NOT a wiki link (code, math, etc.)
NON_LINK_RE = re.compile(r'^[\s\-–—$@#%^&*+=<>\[\]{}|\\/;:~`!]+$|^\d+$|^[\._\-]+$|^[-\d\s]+$')

def is_likely_wiki_link(link_text):
    """Filter out non-wiki-link patterns like [[-]], [[$var]], etc."""
    stripped = link_text.strip()
    # Too short
    if len(stripped) <= 1:
        return False
    # Purely special characters
    if NON_LINK_RE.match(stripped):
        return False
    # Shell variables
    if '$' in stripped:
        return False
    # Pure numbers
    if stripped.isdigit():
        return False
    return True

def resolve_entity_concept(name):
    """Resolve [[name]] in entities/concepts context."""
    key = name.strip().lower()
    # Check exact match in entities first
    if os.path.isfile(os.path.join(WIKI, "entities", f"{name}.md")):
        return "entities", name
    # Check exact match in concepts
    if os.path.isfile(os.path.join(WIKI, "concepts", f"{name}.md")):
        return "concepts", name
    # Check alias index
    canonical = alias_index.get(key)
    if canonical:
        # Determine which category the canonical belongs to
        if os.path.isfile(os.path.join(WIKI, "entities", f"{canonical}.md")):
            return "entities", canonical
        if os.path.isfile(os.path.join(WIKI, "concepts", f"{canonical}.md")):
            return "concepts", canonical
    return None

page_count = 0
link_count = 0
real_link_count = 0
link_pattern = re.compile(r'\[\[([^\]]+)\]\]')

for root, dirs, files in os.walk(WIKI):
    skip_dirs = {"_lint", "_state", ".archived", ".git", "__pycache__"}
    dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
    
    for fname in files:
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(root, fname)
        try:
            with open(fpath, 'r') as f:
                content = f.read()
        except:
            continue
        
        rel_path = os.path.relpath(fpath, WIKI)
        path_parts = rel_path.split(os.sep)
        category = path_parts[0] if len(path_parts) >= 1 else ""
        
        page_count += 1
        
        for match in link_pattern.finditer(content):
            link = match.group(1).strip()
            link_count += 1
            if not is_likely_wiki_link(link):
                continue
            real_link_count += 1
            
            if "/" in link:
                prefix, rest = link.split("/", 1)
                if prefix in VAULTS:
                    # wiki 저장 관례는 '<원본파일명>.<ext>.md' — 링크가 '.md' 로 끝나면 그대로 쓴다.
                    # 재부착하면 '.md.md' 가 되어 실존 항목을 dangling 으로 오탐한다.
                    _rest_md = rest if rest.endswith(".md") else f"{rest}.md"
                    target_path = os.path.join(WIKI, "sources", prefix, _rest_md)
                    if not os.path.isfile(target_path) and not os.path.isdir(os.path.join(WIKI, "sources", prefix, rest)):
                        violations["dangling_vault_path"].append({
                            "link": link, "source": rel_path,
                            "expected": f"sources/{prefix}/{_rest_md}"
                        })
                elif prefix in ("entities", "concepts"):
                    _rest_md = rest if rest.endswith(".md") else f"{rest}.md"
                    target_path = os.path.join(WIKI, prefix, _rest_md)
                    if not os.path.isfile(target_path):
                        violations["dangling_entity_concept"].append({
                            "link": link, "source": rel_path,
                            "expected": f"{prefix}/{_rest_md}", "type": "prefixed"
                        })
                else:
                    violations["unknown_vault_prefix"].append({
                        "link": link, "source": rel_path, "unknown_prefix": prefix
                    })
            else:
                if category == "sources" or "sources" in path_parts:
                    violations["shortcut_in_sources"].append({
                        "link": link, "source": rel_path
                    })
                elif category in ("entities", "concepts"):
                    resolved = resolve_entity_concept(link)
                    if not resolved:
                        violations["dangling_entity_concept"].append({
                            "link": link, "source": rel_path,
                            "expected": f"{category}/{link}.md", "type": "shortcut"
                        })

for key, data in violations.items():
    out_path = os.path.join(OUT_DIR, f"_{key}.json")
    with open(out_path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Pages: {page_count}, Total links: {link_count}, Real links: {real_link_count}")
print(f"\nShortcut in sources: {len(violations['shortcut_in_sources'])}")
print(f"Unknown vault prefix: {len(violations['unknown_vault_prefix'])}")
print(f"Dangling vault path: {len(violations['dangling_vault_path'])}")
print(f"Dangling entity/concept: {len(violations['dangling_entity_concept'])}")

for key, data in violations.items():
    if data:
        print(f"\n--- {key} ---")
        for item in data[:10]:
            print(f"  [[{item['link']}]] in {item['source']}")
