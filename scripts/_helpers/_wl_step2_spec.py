#!/usr/bin/env python3
"""wl Step 2 — ADR-0001 link 규약 검증 (spec lint.md Step 2 정합)

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
    parser = argparse.ArgumentParser(description="wl Step 2 — ADR-0001 link 규약 검증 (spec lint.md Step 2 정합)")
    parser.add_argument("--wiki-home", default=None,
                        help="WIKIHUB_HOME (default: $WIKIHUB_HOME > $WIKIHUB_YAML 부모 > ~/wikihub)")
    parser.add_argument("--src", default=None,
                        help="WIKIHUB_SRC (default: $WIKIHUB_SRC > ~/.local/share/wikihub/src)")
    args, _unknown = parser.parse_known_args()
    return args


_ARGS = _parse_cli()
WIKIHUB_HOME: Path = _resolve_wiki_home(_ARGS.wiki_home)
WIKIHUB_SRC: Path = _resolve_src(_ARGS.src)


import json
import re
import sys
from pathlib import Path

WIKI = WIKIHUB_HOME / "wiki"
OUT = WIKI / "_lint" / "_wl_step2.json"
CATEGORIES = ("entities", "concepts", "analyses", "sources", "_lint")
VAULTS = {"nas"}
LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
FENCE_RE = re.compile(r"```.*?```", re.S)
INLINE_RE = re.compile(r"`[^`\n]*`")
FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)
# 셸 파편·placeholder 필터 — link_audit_v2.py 와 동일 기준 (#201 ⑧).
# `-` · `$var` · `[[경로]]` 같은 비링크를 위반 1 로 계상하지 않는다.
NON_LINK_RE = re.compile(
    r"^[\s\-–—$@#%^&*+=<>\[\]{}|\\/;:~`!]+$|^\d+$|^[\._\-]+$|^[-\d\s]+$"
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def aliases_of(path: Path):
    """frontmatter aliases 셋 (lowercase normalize). 파싱 실패 시 [stem].

    두 style 을 모두 지원한다 (2026-09-22 실측: inline 101 / block 1,603).
      inline: aliases: [a, b]
      block : aliases:\n  - a\n  - b
    구 버전은 inline 만 인식해 alias index 가 125건 누락되고
    위반 1 이 106건으로 부풀려졌다 (#201 ⑧).
    """
    m = FM_RE.match(read(path))
    stem = path.stem
    if not m:
        return {stem.lower()}
    fm = m.group(1)
    out: set[str] = set()
    # inline: aliases: [a, b]
    for k in re.findall(r"^aliases:\s*\[(.*?)\]\s*$", fm, re.M):
        out |= {a.strip().strip("'\"") for a in k.split(",") if a.strip()}
    # block: aliases: (빈 값) 다음 줄부터 "  - a"
    lines = fm.split("\n")
    for i, ln in enumerate(lines):
        if re.match(r"^aliases:\s*$", ln):
            for nxt in lines[i + 1:]:
                bm = re.match(r"^\s+-\s+(.*)$", nxt)
                if not bm:
                    break
                out.add(bm.group(1).strip().strip("'\""))
    return {a.lower() for a in out} or {stem.lower()}


def build_alias_index():
    idx = {}
    for cat in ("entities", "concepts"):
        for page in sorted((WIKI / cat).glob("*.md")):
            for a in aliases_of(page):
                idx.setdefault(a, page.stem)
    return idx


def resolve(name, category, idx):
    if (WIKI / category / f"{name}.md").is_file():
        return True
    return idx.get(name.strip().lower()) is not None


def main():
    idx = build_alias_index()
    v1, v2, v3, dang, ok = [], [], [], [], 0
    for page in sorted(WIKI.rglob("*.md")):
        rel = page.relative_to(WIKI).as_posix()
        if rel.startswith(".archived/") or rel.startswith("_lint/"):
            continue
        body = INLINE_RE.sub("", FENCE_RE.sub("", read(page)))
        for link in LINK_RE.findall(body):
            link = link.strip()
            head = link.split("/")[0]
            if head in CATEGORIES:
                if head in ("entities", "concepts"):
                    name = link.split("/", 1)[1]
                    if not resolve(name, head, idx):
                        dang.append({"link": link, "source": rel, "type": "explicit_dangling"})
                    else:
                        ok += 1
                else:
                    ok += 1
                continue
            if head in VAULTS:
                if NON_LINK_RE.match(link) or "$" in link:
                    continue
                parts = link.split("/", 1)
                sub = parts[1] if len(parts) > 1 else ""
                # 링크가 이미 .md 로 끝나면 그대로 쓴다 — 재부착하면 '.md.md' 가 되어
                # 실존 항목을 dangling 으로 오탐한다 (#201 ⑧: log.md 52건 전량 이 원인).
                _sub_md = sub if sub.endswith(".md") else f"{sub}.md"
                if (WIKI / "sources" / head / _sub_md).is_file():
                    ok += 1
                else:
                    v3.append({"link": link, "source": rel})
                continue
            if "/" in link:
                v2.append({"link": link, "source": rel})
            else:
                # 단축형 `[[name]]` — entities/concepts 실존 또는 alias 해소면 정상.
                # 구 버전은 판정 없이 전부 위반 1 로 넣어 106건으로 부풀렸다 (#201 ⑧).
                if NON_LINK_RE.match(link) or len(link) <= 1 or "$" in link:
                    continue   # 비링크 — 계상 대상 아님
                if resolve(link, "entities", idx) or resolve(link, "concepts", idx):
                    ok += 1
                else:
                    v1.append({"link": link, "source": rel})
    res = {
        "alias_index_entries": len(idx),
        "violation_1_no_prefix_sources": v1,
        "violation_2_unknown_prefix": v2,
        "violation_3_dangling_vault_path": v3,
        "dangling_entity_concept": dang,
        "ok": ok,
    }
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in res.items()},
                     ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
