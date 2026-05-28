#!/usr/bin/env python3
"""wiki/entities/ + wiki/concepts/ frontmatter alias duplicate detection.

Step 4.5 subprocess helper — replaces LLM-based alias comparison with
deterministic Python to eliminate per-cycle token cost (ADR-0039).

Scan all pages under wiki/entities/ and wiki/concepts/, parse frontmatter
``aliases`` field, and detect:

- **case-variant duplicates**: same lowercase alias shared by 2+ pages in
  the same category (entity-entity or concept-concept).
- **cross-category duplicates**: same lowercase alias shared by an entity
  and a concept page.

Usage::

    python3 scripts/_helpers/detect_alias_duplicates.py \\
        [--wiki-home WIKIHUB_HOME]

Defaults to ``$WIKIHUB_HOME`` env var, then ``~/wikihub``.

Output: JSON to stdout.

Exit codes:
    0 — success (may have duplicates or not; check JSON content)
    1 — operational error (directory missing, frontmatter parse fail, etc.)

Spec: ADR-0039 §Decision 세부 §1 (alias frontmatter),
      ADR-0039 §Decision 세부 §2 (lint Step 4.5 duplicate detection)
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


def _resolve_wiki_home(cli_arg: str | None) -> Path:
    if cli_arg:
        return Path(cli_arg).resolve()
    env = os.environ.get("WIKIHUB_HOME")
    if env:
        return Path(env).resolve()
    return Path.home() / "wikihub"


def _parse_frontmatter(path: Path) -> dict:
    """Parse YAML frontmatter (--- ... ---) from a markdown file.

    Returns the parsed dict, or raises ValueError on malformed content.
    """
    text = path.read_text(encoding="utf-8")
    # Match leading frontmatter block: ---\n...\n---\n
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        raise ValueError(f"Missing or malformed frontmatter: {path}")
    import yaml  # lazy import — only needed on this path

    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        raise ValueError(f"YAML parse error in {path}: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"Frontmatter is not a dict in {path}")
    return data


def _collect_aliases(wiki_home: Path) -> dict[str, list[dict]]:
    """Scan wiki/entities/ and wiki/concepts/ and build alias index.

    Returns a dict mapping normalized_lowercase_alias → list of page info dicts.
    """
    alias_map: dict[str, list[dict]] = {}
    categories = {
        "entities": "entity",
        "concepts": "concept",
    }

    for cat_dir, cat_label in categories.items():
        cat_path = wiki_home / "wiki" / cat_dir
        if not cat_path.is_dir():
            continue
        for md_path in sorted(cat_path.glob("*.md")):
            try:
                fm = _parse_frontmatter(md_path)
            except (ValueError, OSError) as e:
                print(f"WARNING: {e}", file=sys.stderr)
                continue

            raw_aliases: list[str] = fm.get("aliases") or []
            if not raw_aliases:
                # Page missing aliases entirely — use filename stem as canonical
                raw_aliases = [md_path.stem]

            for form in raw_aliases:
                norm = form.lower().strip()
                page_info = {
                    "path": str(md_path.relative_to(wiki_home)),
                    "original": form,
                    "category": cat_label,
                    "category_dir": cat_dir,
                }
                alias_map.setdefault(norm, []).append(page_info)

    return alias_map


def _detect_duplicates(alias_map: dict[str, list[dict]]) -> dict:
    """From alias map, extract case-variant and cross-category duplicates.

    Returns ``{"case_variant": [...], "cross_category": [...]}``.
    """
    case_variant: list[dict] = []
    cross_category: list[dict] = []

    for norm, pages in alias_map.items():
        if len(pages) < 2:
            continue

        # Count distinct categories
        cats: set[str] = {p["category"] for p in pages}
        if len(cats) == 1:
            # Same category (entity/entity or concept/concept) → case-variant
            cat = next(iter(cats))
            case_variant.append({
                "alias": norm,
                "category": cat,
                "category_dir": pages[0]["category_dir"],
                "pages": [
                    {"path": p["path"], "original": p["original"]}
                    for p in sorted(pages, key=lambda x: x["path"])
                ],
            })
        else:
            # Cross-category (entity + concept)
            entry: dict = {"alias": norm, "pages": []}
            for cat_type in ("entity", "concept"):
                for p in pages:
                    if p["category"] == cat_type:
                        entry["pages"].append({
                            "path": p["path"],
                            "original": p["original"],
                            "category": cat_type,
                        })
            cross_category.append(entry)

    return {"case_variant": case_variant, "cross_category": cross_category}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Detect alias duplicates in wiki/entities/ and wiki/concepts/",
    )
    parser.add_argument(
        "--wiki-home",
        default=None,
        help="WIKIHUB_HOME path (default: $WIKIHUB_HOME or ~/wikihub)",
    )
    args = parser.parse_args()

    wiki_home = _resolve_wiki_home(args.wiki_home)
    if not wiki_home.is_dir():
        print(f"FATAL: wiki home not found: {wiki_home}", file=sys.stderr)
        sys.exit(1)

    alias_map = _collect_aliases(wiki_home)
    result = _detect_duplicates(alias_map)
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
