#!/usr/bin/env python3
"""wl 사이클 보조 검증 — graph node source_file 실부재 검사

WikiHub 정본 helper (#201 ⑥ 정본화 + ⑧ 검출기 교정, ADR-0034 data-first layout 정합).

경로 복원 체계 (fail-safe 순서):
  1. `--wiki-home` / `--src` CLI arg
  2. `WIKIHUB_HOME` / `WIKIHUB_SRC` env
  3. `WIKIHUB_YAML` env 의 부모 디렉토리  (lint/graphify/ingest systemd unit 이 주입)
  4. `~/wikihub` / `~/.local/share/wikihub/src`  (ADR-0034 default)

원 운영 로컬 버전(`$WIKIHUB_HOME/_scripts/`)은 `/home/ubuntu/wikihub` 을
하드코딩했으나, 본 정본은 이식 가능하게 정규화했다.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _resolve_wiki_home(explicit=None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("WIKIHUB_HOME")
    if env:
        return Path(env).expanduser().resolve()
    yaml_env = os.environ.get("WIKIHUB_YAML")
    if yaml_env:
        return Path(yaml_env).expanduser().resolve().parent
    return Path("~/wikihub").expanduser().resolve()


def _resolve_src(explicit=None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("WIKIHUB_SRC")
    if env:
        return Path(env).expanduser().resolve()
    return Path("~/.local/share/wikihub/src").expanduser().resolve()


def _parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="wl 사이클 보조 검증 — graph node source_file 실부재 검사")
    parser.add_argument("--wiki-home", default=None,
                        help="WIKIHUB_HOME (default: $WIKIHUB_HOME > $WIKIHUB_YAML 부모 > ~/wikihub)")
    parser.add_argument("--src", default=None,
                        help="WIKIHUB_SRC (default: $WIKIHUB_SRC > ~/.local/share/wikihub/src)")
    args, _unknown = parser.parse_known_args()
    return args


_ARGS = _parse_cli()
WIKIHUB_HOME: Path = _resolve_wiki_home(_ARGS.wiki_home)
WIKIHUB_SRC: Path = _resolve_src(_ARGS.src)


import json, unicodedata
from pathlib import Path

wiki = WIKIHUB_HOME / "wiki"
g = json.load(open(WIKIHUB_HOME / "graphify-out" / "graph.json"))
nodes = g.get("nodes", [])
links = g.get("links", g.get("edges", []))
print(f"graph: {len(nodes)} nodes, {len(links)} links")

disk_files = set()
for cat in ("entities", "concepts", "sources", "analyses"):
    base = wiki / cat
    if base.exists():
        for f in base.rglob("*.md"):
            disk_files.add(f"{cat}/{f.relative_to(base)}")

def norm(s):
    return unicodedata.normalize("NFC", s)

disk_norm = {norm(x) for x in disk_files}
missing_on_disk = []
for n in nodes:
    src = n.get("source_file") or ""
    if not src or src.startswith(".archived"):
        continue
    for cat in ("entities", "concepts", "sources", "analyses"):
        if src.startswith(f"{cat}/"):
            p = src
            break
    else:
        continue
    # 구 버전은 concepts/ 를 무조건 통과시켜 실부재를 은닉했다 (#201 ⑧).
    # 제외를 제거해 categories 실부재를 정본대로 계상한다.
    if norm(p) not in disk_norm:
        missing_on_disk.append(p)

uniq = sorted(set(missing_on_disk))
print(f"missing on disk (unique): {len(uniq)}")
for m in uniq[:15]:
    print(" ", m)
