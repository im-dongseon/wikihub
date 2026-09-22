#!/usr/bin/env python3
"""Step 5 — wiki/index.md 재구성 (ADR-0001 링크 형식)

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
    parser = argparse.ArgumentParser(description="Step 5 — wiki/index.md 재구성 (ADR-0001 링크 형식)")
    parser.add_argument("--wiki-home", default=None,
                        help="WIKIHUB_HOME (default: $WIKIHUB_HOME > $WIKIHUB_YAML 부모 > ~/wikihub)")
    parser.add_argument("--src", default=None,
                        help="WIKIHUB_SRC (default: $WIKIHUB_SRC > ~/.local/share/wikihub/src)")
    args, _unknown = parser.parse_known_args()
    return args


_ARGS = _parse_cli()
WIKIHUB_HOME: Path = _resolve_wiki_home(_ARGS.wiki_home)
WIKIHUB_SRC: Path = _resolve_src(_ARGS.src)


import os

WIKI = str(WIKIHUB_HOME / "wiki")
INDEX = os.path.join(WIKI, "index.md")

def list_md_recursive(directory, prefix=""):
    """List .md files recursively, returning (display_path, full_path)."""
    results = []
    if not os.path.isdir(directory):
        return results
    for entry in sorted(os.listdir(directory)):
        fpath = os.path.join(directory, entry)
        if os.path.isdir(fpath):
            results.extend(list_md_recursive(fpath, f"{prefix}/{entry}" if prefix else entry))
        elif entry.endswith(".md") and os.path.isfile(fpath):
            display = f"{prefix}/{entry[:-3]}" if prefix else entry[:-3]
            results.append((display, fpath))
    return results

lines = ["# WikiHub", ""]

# Sources section
lines.append("## Sources")
sources_dir = os.path.join(WIKI, "sources")
if os.path.isdir(sources_dir):
    for vault in sorted(os.listdir(sources_dir)):
        vault_path = os.path.join(sources_dir, vault)
        if not os.path.isdir(vault_path):
            continue
        lines.append(f"### {vault}")
        src_files = list_md_recursive(vault_path)
        # vault 변경 로그(log.md)는 카탈로그 제외 — ADR-0005 index 는 사람 가시 진입점 (log 는 ingest append 로그)
        src_files = [x for x in src_files if os.path.basename(x[1]) != "log.md"]
        count = 0
        for display, _ in src_files:
            lines.append(f"- [[{vault}/{display}]]")
            count += 1
        if count == 0:
            lines.append("  *(empty)*")
        lines.append("")

# Entities section
lines.append("## Entities")
entities_dir = os.path.join(WIKI, "entities")
if os.path.isdir(entities_dir):
    for fname in sorted(os.listdir(entities_dir)):
        if fname.endswith(".md") and os.path.isfile(os.path.join(entities_dir, fname)):
            lines.append(f"- [[entities/{fname[:-3]}]]")
lines.append("")

# Concepts section
lines.append("## Concepts")
concepts_dir = os.path.join(WIKI, "concepts")
if os.path.isdir(concepts_dir):
    for fname in sorted(os.listdir(concepts_dir)):
        if fname.endswith(".md") and os.path.isfile(os.path.join(concepts_dir, fname)):
            lines.append(f"- [[concepts/{fname[:-3]}]]")
lines.append("")

# Analyses section
lines.append("## Analyses")
analyses_dir = os.path.join(WIKI, "analyses")
analysis_count = 0
if os.path.isdir(analyses_dir):
    for fname in sorted(os.listdir(analyses_dir)):
        if fname.endswith(".md") and os.path.isfile(os.path.join(analyses_dir, fname)):
            lines.append(f"- [[analyses/{fname[:-3]}]]")
            analysis_count += 1

content = "\n".join(lines) + "\n"

# Count stats
src_total = sum(1 for l in lines if l.startswith("- [[") and not l.startswith("- [[entities/") and not l.startswith("- [[concepts/") and not l.startswith("- [[analyses/"))
entity_total = sum(1 for l in lines if l.startswith("- [[entities/"))
concept_total = sum(1 for l in lines if l.startswith("- [[concepts/"))

with open(INDEX, 'w') as f:
    f.write(content)

# Set permissions
os.chmod(INDEX, 0o644)

print(f"Sources: {src_total}")
print(f"Entities: {entity_total}")
print(f"Concepts: {concept_total}")
print(f"Analyses: {analysis_count}")
print(f"Total pages: {src_total + entity_total + concept_total + analysis_count}")
print(f"\nindex.md rebuilt with correct ADR-0001 format ([[vault/...]]).")
