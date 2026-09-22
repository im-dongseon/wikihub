#!/usr/bin/env python3
"""referenced_by 실재성 전수 감사 — lint 검출기 (issue #215).

현행 lint Step 4 는 **단일 페이지**만 보고한다 (`entities/AGENTS.md` 중복 2건 등).
본 검출기는 **전수 스캔**해 오등록을 계층별로 분류한다.

⚠️ **자동 제거하지 않는다 — 보고만.** P1·P2 는 제거 대상이지만 데이터 변경은 운영
소관이고, P3(동형명사)는 문자열 매칭으로 진성/오염을 구분할 수 없어 제거하면 진성분을
잃는다 (`Go` 실측: 언어 문맥 14 / 동사 문맥 54).

사용:
    ref_audit.py --wiki-home DIR [--json OUT]
"""
from __future__ import annotations

import argparse
import collections
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


def audit(wiki_home: Path) -> dict:
    wiki = wiki_home / "wiki"
    counts = collections.Counter()
    by_verdict: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    per_page: collections.Counter = collections.Counter()

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
                    by_verdict["missing_file"][src] += 1
                    continue
                v, name, _line = R.verdict(names, sp.read_text(encoding="utf-8", errors="replace"))
                counts[v.lower()] += 1
                if v != "OK":
                    by_verdict[v][f"{cat}/{page.name}"] += 1
                    per_page[f"{cat}/{page.name}"] += 1

    top = [
        {"page": p, "count": c} for p, c in per_page.most_common(30)
    ]
    return {
        "wiki_home": str(wiki_home),
        "total": counts["total"],
        "ok": counts["ok"],
        "p1": counts["p1"],
        "p2": counts["p2"],
        "p3": counts["p3"],
        "missing_file": counts["missing_file"],
        "contaminated": counts["p1"] + counts["p2"] + counts["p3"],
        "contaminated_pages": len(per_page),
        "top_pages": top,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="referenced_by 실재성 전수 감사 (#215)")
    ap.add_argument("--wiki-home", default=None, help="WIKIHUB_HOME (ADR-0034 default: ~/wikihub)")
    ap.add_argument("--json", default=None, help="결과 JSON 출력 경로 (기본: stdout)")
    args = ap.parse_args()

    wiki_home = _resolve_wiki_home(args.wiki_home)
    if not (wiki_home / "wiki").is_dir():
        print(f"error: wiki 디렉토리 부재: {wiki_home}/wiki", file=sys.stderr)
        return 2

    res = audit(wiki_home)
    text = json.dumps(res, ensure_ascii=False, indent=2)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
        print(json.dumps({k: v for k, v in res.items() if k != "top_pages"}, ensure_ascii=False, indent=2))
    else:
        print(text)

    print(
        f"ref_audit: total {res['total']} | OK {res['ok']} | "
        f"P1 {res['p1']} | P2 {res['p2']} | P3 {res['p3']} | "
        f"missing {res['missing_file']} | 오염 {res['contaminated']}건 / {res['contaminated_pages']}페이지",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
