#!/usr/bin/env python3
"""Step 3 — 그래프 기반 점검 (v3)

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
    parser = argparse.ArgumentParser(description="Step 3 — 그래프 기반 점검 (v3)")
    parser.add_argument("--wiki-home", default=None,
                        help="WIKIHUB_HOME (default: $WIKIHUB_HOME > $WIKIHUB_YAML 부모 > ~/wikihub)")
    parser.add_argument("--src", default=None,
                        help="WIKIHUB_SRC (default: $WIKIHUB_SRC > ~/.local/share/wikihub/src)")
    args, _unknown = parser.parse_known_args()
    return args


_ARGS = _parse_cli()
WIKIHUB_HOME: Path = _resolve_wiki_home(_ARGS.wiki_home)
WIKIHUB_SRC: Path = _resolve_src(_ARGS.src)


import json, os, re, yaml
from collections import defaultdict

WIKI = str(WIKIHUB_HOME / "wiki")
GRAPH = str(WIKIHUB_HOME / "graphify-out" / "graph.json")
OUT_DIR = str(WIKIHUB_HOME / "wiki" / "_lint")

with open(GRAPH) as f:
    g = json.load(f)

nodes = g.get("nodes", [])
edges = g.get("links", g.get("edges", []))

print(f"Graph: {len(nodes)} nodes, {len(edges)} edges")

node_map = {n.get("id"): n for n in nodes}

# Build inbound
inbound = defaultdict(int)
for e in edges:
    tgt = e.get("target") or e.get("to")
    if tgt:
        inbound[tgt] += 1

# Categorize nodes
categories = defaultdict(list)
for n in nodes:
    sf = n.get("source_file") or ""
    if sf.startswith(("sources/", "wiki/sources/")) or n.get("file_type") == "source":
        cat = "sources"
    elif sf.startswith(("entities/", "wiki/entities/")) or n.get("file_type") == "entity":
        cat = "entities"
    elif sf.startswith(("concepts/", "wiki/concepts/")) or n.get("file_type") == "concept":
        cat = "concepts"
    elif sf.startswith(("analyses/", "wiki/analyses/")):
        cat = "analyses"
    else:
        cat = "other"
    categories[cat].append(n)

print(f"\nCategories: {', '.join(f'{k}={len(v)}' for k, v in sorted(categories.items()))}")

# Graph orphans
orphan_sources = [n for n in categories["sources"] if inbound.get(n["id"], 0) == 0]
orphan_entities = [n for n in categories["entities"] if inbound.get(n["id"], 0) == 0]
orphan_concepts = [n for n in categories["concepts"] if inbound.get(n["id"], 0) == 0]

print(f"\n=== Graph orphans (0 inbound edges) ===")
print(f"  sources: {len(orphan_sources)}")
print(f"  entities: {len(orphan_entities)}")
print(f"  concepts: {len(orphan_concepts)}")

# === Cross-check with actual frontmatter referenced_by ===
print(f"\n=== Cross-check: Orphans by frontmatter referenced_by ===")

def get_referenced_by(filepath):
    """Read frontmatter from a markdown file and return referenced_by list."""
    try:
        with open(filepath) as f:
            content = f.read()
    except:
        return None, None
    
    if not content.startswith("---"):
        return None, None
    
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, None
    
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except:
        return None, None
    
    return fm.get("referenced_by"), fm.get("aliases")

# Check entities
print("\n  Entities with referenced_by=0 or missing:")
fm_orphan_entities = 0
entity_dir = os.path.join(WIKI, "entities")
for fname in sorted(os.listdir(entity_dir)):
    if not fname.endswith(".md"):
        continue
    refs, _ = get_referenced_by(os.path.join(entity_dir, fname))
    if refs is None or len(refs) == 0:
        fm_orphan_entities += 1
        if fm_orphan_entities <= 10:
            print(f"    {fname[:-3]}")

print(f"  Total frontmatter-orphan entities: {fm_orphan_entities}")

# Check concepts
print("\n  Concepts with referenced_by=0 or missing:")
fm_orphan_concepts = 0
concept_dir = os.path.join(WIKI, "concepts")
for fname in sorted(os.listdir(concept_dir)):
    if not fname.endswith(".md"):
        continue
    refs, _ = get_referenced_by(os.path.join(concept_dir, fname))
    if refs is None or len(refs) == 0:
        fm_orphan_concepts += 1
        if fm_orphan_concepts <= 10:
            print(f"    {fname[:-3]}")

print(f"  Total frontmatter-orphan concepts: {fm_orphan_concepts}")

# === Dangling edges ===
dangling = []
for e in edges:
    tgt = e.get("target") or e.get("to")
    if tgt and tgt not in node_map:
        dangling.append(e)

print(f"\n=== Dangling edges: {len(dangling)} ===")

# === Top referenced ===
top_in = sorted(inbound.items(), key=lambda x: -x[1])
wiki_inbound = [(nid, cnt) for nid, cnt in top_in 
                if ((node_map.get(nid, {}).get("source_file") or "") 
                    .startswith(("sources/", "entities/", "concepts/", "analyses/")))]
print("\n=== Top inbound (wiki pages) ===")
for nid, cnt in wiki_inbound[:10]:
    n = node_map.get(nid, {})
    print(f"  {n.get('source_file', '?')}: {cnt}")

# === Missing on disk ===
missing = 0
for n in nodes:
    sf = n.get("source_file") or ""
    if not sf:
        continue
    rel = sf.replace("wiki/", "", 1) if sf.startswith("wiki/") else sf
    if not os.path.isfile(os.path.join(WIKI, rel)):
        missing += 1
print(f"\n=== Missing on disk: {missing} ===")

# === Archived ===
archived = sum(1 for n in nodes if ".archived/" in (n.get("source_file") or ""))
print(f"=== Archived nodes: {archived} ===")

# Save
summary = {
    "orphan_sources_graph": len(orphan_sources),
    "orphan_entities_graph": len(orphan_entities),
    "orphan_concepts_graph": len(orphan_concepts),
    "orphan_entities_frontmatter": fm_orphan_entities,
    "orphan_concepts_frontmatter": fm_orphan_concepts,
    "dangling_edges": len(dangling),
    "missing_on_disk": missing,
    "archived_nodes": archived,
    "top_inbound": [(n.get("source_file","?"),cnt) for nid,cnt in wiki_inbound[:10] if (n:=node_map.get(nid,{}))]
}
with open(os.path.join(OUT_DIR, "_graph_analysis.json"), 'w') as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

print("\nStep 3 complete.")
