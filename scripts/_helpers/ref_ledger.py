#!/usr/bin/env python3
"""referenced_by 등록 근거 ledger (issue #215).

`referenced_by` 항목마다 **왜 유효한지**(매칭된 이름·분기·위치)를 기록한다. 이 기록이
있으면 오등록이 즉시 감사 가능하고, 사후에 판정 기준을 세우는 사이클이 재발하지 않는다.

사용:
    ref_ledger.py --wiki-home DIR [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

import ref_match as R  # noqa: E402

_CATS = ("entities", "concepts")
_FM = re.compile(r"^---\s*\n(.*?)\n---", re.S)


# ── 경로 복원 (ADR-0034 data-first layout 정합 — 타 helper 와 동일 순서) ──────
def _resolve_wiki_home(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("WIKIHUB_HOME")
    if env:
        return Path(env).expanduser().resolve()
    yaml_env = os.environ.get("WIKIHUB_YAML")
    if yaml_env:
        return Path(yaml_env).expanduser().resolve().parent
    return Path("~/wikihub").expanduser().resolve()


def build_ledger(wiki_home: Path) -> tuple[list[dict], dict[str, int]]:
    wiki = wiki_home / "wiki"
    entries: list[dict] = []
    counts = {"total": 0, "OK": 0, "P1": 0, "P2": 0, "P3": 0, "missing_file": 0}

    for cat in _CATS:
        cat_dir = wiki / cat
        if not cat_dir.is_dir():
            continue
        for page in sorted(cat_dir.rglob("*.md")):
            raw = page.read_text(encoding="utf-8", errors="replace")
            m = _FM.match(raw)
            if not m:
                continue
            try:
                fm = yaml.safe_load(m.group(1)) or {}
            except Exception:
                continue
            names = {str(a) for a in (fm.get("aliases") or []) if a} | {page.stem}

            for src in fm.get("referenced_by") or []:
                if not isinstance(src, str):
                    continue
                counts["total"] += 1
                sp = wiki / src
                if not sp.exists():
                    counts["missing_file"] += 1
                    entries.append(
                        {
                            "page": f"{cat}/{page.name}",
                            "source": src,
                            "name_matched": None,
                            "branch": None,
                            "verdict": "missing_file",
                            "line": None,
                        }
                    )
                    continue

                text = sp.read_text(encoding="utf-8", errors="replace")
                v, name, line = R.verdict(names, text)
                counts[v] += 1
                entries.append(
                    {
                        "page": f"{cat}/{page.name}",
                        "source": src,
                        "name_matched": name,
                        "branch": R.classify(name) if name else None,
                        "verdict": v,
                        "line": line or None,
                    }
                )

    return entries, counts


def main() -> int:
    ap = argparse.ArgumentParser(description="referenced_by 등록 근거 ledger (#215)")
    ap.add_argument("--wiki-home", default=None, help="WIKIHUB_HOME (ADR-0034 default: ~/wikihub)")
    ap.add_argument("--json", default=None, help="ledger JSON 출력 경로 (기본: stdout)")
    args = ap.parse_args()

    wiki_home = _resolve_wiki_home(args.wiki_home)
    if not (wiki_home / "wiki").is_dir():
        print(f"error: wiki 디렉토리 부재: {wiki_home}/wiki", file=sys.stderr)
        return 2

    entries, counts = build_ledger(wiki_home)
    payload = {"wiki_home": str(wiki_home), "counts": counts, "entries": entries}

    if args.json:
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        out = {"wiki_home": str(wiki_home), "counts": counts}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    print(
        f"ledger: total {counts['total']} | OK {counts['OK']} | "
        f"P1 {counts['P1']} | P2 {counts['P2']} | P3 {counts['P3']} | "
        f"missing {counts['missing_file']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
