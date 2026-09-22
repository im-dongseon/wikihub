"""log.md append 무결성 검출기 (issue #211).

## 배경

`ingest.md` Step 5 가 `wiki/sources/<vault>/log.md` 에 항목을 append 하는데, LLM 이
작성하는 서식이 **검증 없이 누적**됐다. 운영 실측(2026-09-22)으로 두 결함이 확인됐다:

  (a) 헤더 시각 역행 8건 — 파일 순서는 append 순서인데 헤더 시각만 이른 값
  (b) `|` 접두 손상 860행 — 형식 전환기에 markdown 표로 취급한 흔적 (운영 복원 완료)

upstream 코드에 `|` 생성 로직은 0건이므로 둘 다 **LLM 서식 오류**다. 재발 방지
장치가 없어서 수개월 누적됐다 (#210 의 `referenced_by` 중복과 같은 패턴).

## 검출 항목

본 모듈은 **보고 전용**이다 (report-only). log.md 는 append-only 이력이라
자동 수정하면 이력이 왜곡된다 — 진단만 하고 `_lint/report.md` 에 기록한다.

  1. 헤더 시각 단조성 (비감소) — 초 단위 표기 포함
  2. 행 형식 — 선행 `|` 접두 등 비정상 접두
  3. 헤더 자체의 형식 정합 (`## YYYY-MM-DD HH:MM:SS KST`)
  4. 헤더에 대응하는 필드 블록의 최소 요건 (`- **Trigger**:` 존재)

## 판정 기준 (실측 근거)

- **시각 비교는 문자열로 하면 안 된다** — 초 생략 표기(`HH:MM`)가 섞이면
  `'10:00' > '10:00:30'` 이 참이 되어 같은 분의 순서를 역행으로 오탐한다
  (실측: Δ-1m 오탐). `(HH, MM, SS)` 정수 튜플로 비교한다. 날짜는 `YYYY-MM-DD`
  zero-padding 이라 문자열 비교가 곧 시간순이다.
- **역행은 단발로 나타난다** (연쇄 오염 아님 — 실측: 역행 직후 정상 복귀).
  따라서 "역행 발견 = 그 헤더의 시각이 스테일" 이지 "이후 전부 오염" 이 아니다.
- KST/UTC 혼재(−9h) 가설은 **기각됐다** (실측 Δ 가 −1h/−7h/−8h/−13h 로 불규칙).
- **Trigger 필드 판정은 필드명 정확 일치**로 한다 — substring 검사는
  `Trigger source` 같은 다른 필드를 통과시킨다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

# `## YYYY-MM-DD HH:MM(:SS)? KST` — 초는 생략 가능 (실측: 초 단위 694건 + 분 단위 혼재)
_HEADER_RE = re.compile(
    r"^## (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}(?::\d{2})?) (KST|UTC)\s*$"
)
# 헤더처럼 보이지만 형식이 어긋난 줄 — 오탐 방지를 위해 후보만 모은다.
_HEADER_LOOSE_RE = re.compile(r"^##\s+\d{4}-\d{2}-\d{2}")
# 정상 필드 줄: `- **Field**: value` (2칸 들여쓰기 하위 항목 허용)
_FIELD_RE = re.compile(r"^\s*- \*\*([^*]+)\*\*:")
# 비정상 접두 — 선행 `|` 등 (markdown 표로 오인한 흔적)
_BAD_PREFIX_RE = re.compile(r"^\|")


def _clock_key(clock: str) -> tuple[int, int, int]:
    """`HH:MM` / `HH:MM:SS` → 정렬 가능한 정수 튜플.

    **문자열 비교로는 부족하다** (2차 리뷰 [mid]): `'10:00' > '10:00:30'` 이 참이라
    같은 분의 `HH:MM:SS` → `HH:MM` 순서를 역행으로 오탐한다 (실측 Δ-1m 오탐).
    초 생략은 0 으로 채워 실제 시각 순서를 만든다.
    """
    parts = clock.split(":")
    hh, mm = int(parts[0]), int(parts[1])
    ss = int(parts[2]) if len(parts) > 2 else 0
    return hh, mm, ss


def _sortkey(date: str, clock: str) -> tuple[str, tuple[int, int, int]]:
    """(날짜 문자열, 시각 정수 튜플).

    날짜는 `YYYY-MM-DD` zero-padding 이라 문자열 비교가 곧 시간순이다.
    시각은 초 생략 표기가 섞이므로 **정수 비교**가 필요하다.
    """
    return date, _clock_key(clock)


def _resolve_wiki_home(explicit: str | None = None) -> Path:
    """WIKIHUB_HOME 해소 — 타 helper 와 동일 순서 (ADR-0034)."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("WIKIHUB_HOME")
    if env:
        return Path(env).expanduser().resolve()
    yaml_env = os.environ.get("WIKIHUB_YAML")
    if yaml_env:
        return Path(yaml_env).expanduser().resolve().parent
    return Path("~/wikihub").expanduser().resolve()


def find_log_files(wiki_home: Path) -> list[Path]:
    """vault 별 log.md 전량 (log.md 는 vault별 — ADR-0005)."""
    root = wiki_home / "wiki" / "sources"
    if not root.is_dir():
        return []
    return sorted(
        (p for p in root.rglob("log.md") if ".archived" not in str(p)),
        key=lambda p: str(p),
    )


def scan_log(path: Path) -> dict:
    """log.md 한 건을 스캔해 결함 내역을 반환한다 (수정하지 않음)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")

    headers: list[dict] = []      # (lineno, raw, sortkey)
    malformed: list[dict] = []    # `## 날짜` 인데 형식 불일치
    bad_prefix: list[dict] = []   # 비정상 접두 행
    missing_trigger: list[dict] = []
    field_names: Counter = Counter()

    for i, line in enumerate(lines, 1):
        if _BAD_PREFIX_RE.match(line):
            bad_prefix.append({"line": i, "text": line[:80]})

        m = _HEADER_RE.match(line)
        if m:
            date, clock, tz = m.groups()
            headers.append({
                "line": i,
                "date": date,
                "clock": clock,
                "tz": tz,
                "sortkey": _sortkey(date, clock),
                "raw": line.strip(),
            })
            continue

        if _HEADER_LOOSE_RE.match(line):
            malformed.append({"line": i, "text": line[:80]})
            continue

        fm = _FIELD_RE.match(line)
        if fm:
            field_names[fm.group(1).strip()] += 1

    # (a) 시각 역행 — 인접 헤더 쌍 비교 (같은 tz 기준)
    backwards: list[dict] = []
    for prev, cur in zip(headers, headers[1:]):
        if prev["tz"] != cur["tz"]:
            continue  # tz 혼재 자체는 별도 신호 (아래)
        if cur["sortkey"] < prev["sortkey"]:
            backwards.append({
                "prev": prev["raw"], "prev_line": prev["line"],
                "cur": cur["raw"], "cur_line": cur["line"],
                "delta_min": _delta_minutes(prev["sortkey"], cur["sortkey"]),
            })

    tz_mixed = len({h["tz"] for h in headers}) > 1

    # (c) Trigger 필드 부재 헤더 — 헤더~다음 헤더 사이에 `- **Trigger**` 가 없으면 결함
    for idx, h in enumerate(headers):
        start = h["line"]
        end = headers[idx + 1]["line"] if idx + 1 < len(headers) else len(lines) + 1
        block = lines[start:end - 1]
        # 필드명이 **정확히** `Trigger` 인 줄만 인정한다 — substring 검사는
        # `Trigger source` · `Triggered-by` 같은 다른 필드를 통과시킨다
        # (2차 리뷰 [low], 실측 확인).
        has_trigger = any(
            (fm := _FIELD_RE.match(b)) and fm.group(1).strip() == "Trigger"
            for b in block
        )
        if not has_trigger:
            missing_trigger.append({"line": h["line"], "header": h["raw"]})

    return {
        "path": str(path),
        "lines": len(lines),
        "headers": len(headers),
        "backwards": backwards,
        "malformed_headers": malformed,
        "bad_prefix": bad_prefix,
        "missing_trigger": missing_trigger,
        "tz_mixed": tz_mixed,
        "field_names": dict(field_names.most_common()),
    }


def _delta_minutes(prev: tuple[str, tuple[int, int, int]],
                   cur: tuple[str, tuple[int, int, int]]) -> int | None:
    """두 sortkey 의 분 차이 (cur - prev). 음수면 역행.

    sortkey 는 `(날짜, (HH, MM, SS))` 튜플이므로 문자열 파싱이 필요 없다 —
    초 생략 표기가 섞여도 실제 시각 차이를 정확히 계산한다.
    """
    import datetime as _dt

    try:
        a = _dt.datetime(*map(int, prev[0].split("-")), *prev[1])
        b = _dt.datetime(*map(int, cur[0].split("-")), *cur[1])
    except (ValueError, TypeError):
        return None
    return int((b - a).total_seconds() // 60)


def scan_all(wiki_home: Path) -> list[dict]:
    return [scan_log(p) for p in find_log_files(wiki_home)]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="log.md append 무결성 검출 (report-only, issue #211)"
    )
    ap.add_argument("--wiki-home", default=None, help="WIKIHUB_HOME (기본 ~/wikihub)")
    ap.add_argument("--json", default=None, help="결과 JSON 출력 경로")
    ap.add_argument("--quiet", action="store_true", help="요약만 출력")
    args = ap.parse_args()

    wiki_home = _resolve_wiki_home(args.wiki_home)
    if not (wiki_home / "wiki").is_dir():
        print(f"error: wiki 디렉토리 부재: {wiki_home}/wiki", file=sys.stderr)
        return 2

    results = scan_all(wiki_home)
    if not results:
        print("no log.md found", file=sys.stderr)
        return 0

    total_back = total_prefix = total_malformed = total_notrig = 0
    for r in results:
        total_back += len(r["backwards"])
        total_prefix += len(r["bad_prefix"])
        total_malformed += len(r["malformed_headers"])
        total_notrig += len(r["missing_trigger"])

        if not args.quiet:
            print(f"\n=== {r['path']} ===")
            print(f"  줄 {r['lines']}  헤더 {r['headers']}  tz혼재={r['tz_mixed']}")
            if r["backwards"]:
                print(f"  ⚠️ 시각 역행 {len(r['backwards'])}건:")
                for b in r["backwards"][:10]:
                    d = f"{b['delta_min']}m" if b["delta_min"] is not None else "?"
                    print(f"     L{b['cur_line']}: {b['cur']}  (직전 L{b['prev_line']}: {b['prev']}, Δ{d})")
            if r["bad_prefix"]:
                print(f"  ⚠️ 비정상 접두 {len(r['bad_prefix'])}행 (예: L{r['bad_prefix'][0]['line']})")
            if r["malformed_headers"]:
                print(f"  ⚠️ 형식 불일치 헤더 {len(r['malformed_headers'])}건")
            if r["missing_trigger"]:
                print(f"  ⚠️ Trigger 필드 부재 헤더 {len(r['missing_trigger'])}건")

    print(
        f"\n합계 — 역행 {total_back} / 접두손상 {total_prefix} / "
        f"헤더형식 {total_malformed} / Trigger부재 {total_notrig}"
    )

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"written: {out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
