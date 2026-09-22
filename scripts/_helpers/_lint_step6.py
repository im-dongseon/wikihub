"""Step 6 모순 후보 검출 + report 한자 인용 살균 (issue #214 · #213).

## #214 — 진짜 원인은 "헤딩"이 아니라 **코드 펜스 내부 스캔**

구 버전(운영 로컬 `_scripts/_lint_step6.py`)은 source 본문의 `^# ` **헤딩** 중 대응 페이지가
없는 것을 후보로 삼았다. 이슈는 "헤딩을 근거로 삼은 것이 정의 착오" 라고 진단했으나,
**실측 결과 더 정확한 원인은 따로 있다**:

    2026-09-22 실측 — 후보 13건의 펜스 내부 여부
      또는                펜스내 3 / 펜스밖 0
      저장소 클론           펜스내 2 / 펜스밖 0
      웹 아티클 정리         펜스내 2 / 펜스밖 0
      Clone repository   펜스내 2 / 펜스밖 0
      Process web article 펜스내 2 / 펜스밖 0
      http://localhost:7000 펜스내 2 / 펜스밖 0
      Cargo              펜스내 2 / 펜스밖 0
      CSV → Markdown 테이블 펜스내 2 / 펜스밖 0
      wikihub.yaml       펜스내 2 / 펜스밖 0
      wikihub-lint.service 펜스내 2 / 펜스밖 0
      수정 후              펜스내 2 / 펜스밖 0
      Superpowers        펜스내 0 / 펜스밖 2   ← 예외
      설치 및 실행          펜스내 1 / 펜스밖 1   ← 예외

**13건 중 11건이 코드 펜스(```) 내부**에 있었다. 펜스 안의 `# 설치 및 실행` 은 문서 구조가
아니라 **예시로 제시된 코드/출력**이므로, 애초에 헤딩으로 파싱되어선 안 된다.

따라서 처방은 두 겹이다:

  1. **코드 펜스 내부를 스캔 대상에서 제외** (주 처방 — 11건 해소)
  2. **헤딩 근거를 유지하되 문서 구조 헤딩만** 취한다 (부 처방 — `skip_common` 확장)

### 왜 "실제 `[[...]]` 링크" 로 바꾸지 않았는가

이슈 §5(b) 는 판정 근거를 `[[...]]` 링크로 한정하라고 제안했으나, **실측 결과 이 데이터에서
동작하지 않는다**:

    전체 [[...]] 출현 537건 분류
      plain     305   '경로' · '링크' · '-'          ← 플레이스홀더·문법 예시
      path      148   'nas/article/....md'           ← log.md 의 경로 표기
      template   41   'gdrive/...' · 'analyses/...'   ← 템플릿
      shell      32   '-z $KUBECTL_COMPLETE'         ← **bash [[ ]] 테스트 연산자**
      url        11   'http://localhost:7000'

`[[` 는 마크다운 위키링크 문법이지만 **bash 의 조건 테스트 연산자이기도 하다**. 실제
source 에서는 셸 코드가 32건 있어 문자열만으로 구분할 수 없다 — #215 의 동형명사 문제와
같은 구조다. 링크 기반으로 바꾸면 후보가 **13 → 26건으로 늘어난다** (실측).

**그래서 링크 전환을 채택하지 않고, 펜스 제외 + 헤딩 유지를 택한다.** 이 결정의 근거를
여기 남긴다.

## #213 — report 한자 인용 살균

lint 가 한자 결함을 **보고하면서 그 한자를 그대로 인용**해, report 자신이 다음 회차의
검출 대상이 됐다. 실측: report 1건의 한자 20자 중 **20자가 lint 자기 산출**이었다
(47자 중). report 는 `sources/nas/project/wikihub/report/` 로 발행되어 다음 회차
`sources/` 스캔에 다시 들어가므로 **자기 재생산 경로**가 성립한다.

`sanitize_hanja()` 는 한자를 `U+XXXX` 표기로 바꿔 인용하면서 결함을 만들지 않게 하고,
`summarize_hanja()` 는 문자 자체 없이 개수만 요약한다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml

# ── 한자 범위 (CJK 통합 한자 + 확장 A) ─────────────────────────────────────
# 가나(U+3040-U+30FF)·한글(U+AC00-U+D7A3)은 **제외**한다 — 살균 대상은 한자다.
_HANJA_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_HANJA_RUN_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]+")

# 후보 제외 — URL · 확장자 · 순수 숫자 · 셸/템플릿 신호
_URLISH_RE = re.compile(r"://|^localhost\b|^www\.", re.IGNORECASE)
_EXT_RE = re.compile(r"\.(md|yaml|yml|json|py|sh|txt|service|timer)$", re.IGNORECASE)
_NUM_RE = re.compile(r"^\d+$")
_SHELL_SIG_RE = re.compile(r"[$]|==|!=|=~|&&|\|\|")
_TEMPLATE_RE = re.compile(r"<[^>]+>|\.\.\.|/")

# 문서 구조 산출물 — 페이지가 될 필요가 없는 헤딩 (구 버전에서 계승 + 확장)
SKIP_COMMON = {
    "introduction", "overview", "setup", "installation", "usage", "conclusion",
    "reference", "목차", "참고", "개요", "prerequisites", "requirements",
    "getting started", "저장소 클론", "설치 및 실행", "웹 아티클 정리", "수정 후",
}


def sanitize_hanja(text: str) -> str:
    """한자를 ``U+XXXX`` 표기로 치환 — report 가 한자를 인용하지 않게 한다 (issue #213).

    가나·한글·ASCII 는 **그대로** 둔다 (살균 대상은 한자뿐).
    """
    return _HANJA_RE.sub(lambda m: f"U+{ord(m.group(0)):04X}", text)


def summarize_hanja(text: str) -> tuple[int, str]:
    """``(한자 수, 한자 없는 요약)`` 반환 (issue #213).

    요약 형식: ``"7자 1건 · 4자 1건 · 2자 2건"`` — 길이별 건수를 내림차순.
    """
    counts: dict[int, int] = {}
    total = 0
    for m in _HANJA_RUN_RE.finditer(text):
        length = len(m.group(0))
        counts[length] = counts.get(length, 0) + 1
        total += length
    if not counts:
        return 0, "0자"
    parts = [f"{length}자 {n}건" for length, n in sorted(counts.items(), reverse=True)]
    return total, " · ".join(parts)


def _strip_frontmatter(text: str) -> str:
    """선두 YAML frontmatter(`---` 블록) 제거 — 본문만 남긴다.

    frontmatter 안의 YAML 주석(`# ...`)이 헤딩으로 오인되는 것을 막는다.
    `---` 로 시작하지 않으면 **원문을 그대로** 둔다 (수평선 `---` 로 시작하는
    frontmatter 없는 문서에서 본문이 통째로 잘리는 것을 막는다).
    """
    m = re.match(r"^---[ \t]*\n(.*?\n)?---[ \t]*(\n|$)", text, re.S)
    if not m:
        return text
    # 첫 `---` 쌍 사이가 YAML 매핑/시퀀스로 파싱될 때만 frontmatter 로 인정한다.
    try:
        fm = yaml.safe_load(m.group(1) or "")
    except Exception:
        return text
    if not isinstance(fm, (dict, list)):
        return text
    return text[m.end():]


# 닫는 펜스: 여는 펜스와 같은 문자·같은 길이 이상 + 뒤에 공백/탭만 (CommonMark).
# `\`\`\`bash` 는 **여는** 펜스이지 닫는 펜스가 아니다 — 이 구분이 없으면
# info string 이 붙은 줄이 펜스를 닫아 안쪽 헤딩이 누출한다 (PR #217 리뷰 [mid]).
_FENCE_CLOSE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
# 여는 펜스는 info string 을 가질 수 있다 (백틱 펜스의 info string 에는 백틱 금지).
_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def _fence_match(line: str, in_fence: bool, fence_char: str, fence_len: int):
    """``(is_fence_line, closes)`` — CommonMark 펜스 판정.

    닫는 펜스는 **같은 문자 + 길이 이상 + 뒤에 공백/탭만** 이어야 한다.
    info string 이 붙은 줄(```bash)은 닫는 펜스가 아니다.
    """
    if in_fence:
        m = _FENCE_CLOSE_RE.match(line)
        if m and m.group(1)[0] == fence_char and len(m.group(1)) >= fence_len:
            return True, True
        # 같은 문자로 시작하지만 닫힘 조건을 못 채운 줄도 펜스 '줄' 로 취급해
        # 헤딩 파싱에서 제외한다 (안쪽 내용이므로 어차피 제외된다).
        return bool(re.match(r"^ {0,3}(`{3,}|~{3,})", line)), False
    m = _FENCE_OPEN_RE.match(line)
    if not m:
        return False, False
    marker = m.group(1)
    # 백틱 여는 펜스의 info string 에는 백틱이 올 수 없다 (CommonMark).
    if marker[0] == "`" and "`" in m.group(2):
        return False, False
    return True, False


def iter_body_headings(text: str):
    """**코드 펜스 밖** 본문 헤딩만 yield (issue #214 주 처방).

    ```` ``` ```` / `~~~` 펜스 내부의 `# ...` 는 예시 코드이지 문서 구조가 아니므로 제외한다.
    실측: 후보 13건 중 11건이 펜스 내부였다.

    CommonMark 정합:
    - 닫는 펜스는 여는 펜스와 **같은 문자**이고 **길이가 같거나 길어야** 닫힌다.
      길이를 보지 않으면 4-backtick 펜스 안의 3-backtick 줄이 닫힘으로 오인되어
      안쪽 헤딩이 누출한다 (중첩 펜스 예시가 있는 source 에서 실제 발생).
    - 닫는 펜스 뒤에는 **공백/탭만** 올 수 있다 — ```` ```bash ```` 는 여는 펜스다.
      이 규칙이 없으면 info string 줄이 펜스를 닫아 안쪽 헤딩이 누출한다.
    - ATX 헤딩은 **최대 3칸** 들여쓰기까지 허용한다 (탭은 4칸이므로 헤딩이 아니다).
    - frontmatter 의 YAML 주석은 본문이 아니므로 먼저 제거한다.
    """
    body = _strip_frontmatter(text)
    in_fence = False
    fence_char = ""
    fence_len = 0
    for line in body.split("\n"):
        is_fence, closes = _fence_match(line, in_fence, fence_char, fence_len)
        if is_fence:
            if closes:
                in_fence, fence_char, fence_len = False, "", 0
            elif not in_fence:
                m = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
                in_fence, fence_char, fence_len = True, m.group(1)[0], len(m.group(1))
            continue
        if in_fence:
            continue
        h = re.match(r"^ {0,3}#[ \t]+(.+?)[ \t]*#*[ \t]*$", line)
        if h:
            yield h.group(1).strip()


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


def _load_existing_names(wiki: Path) -> set[str]:
    """entities/concepts 페이지 stem + aliases (lowercase)."""
    names: set[str] = set()
    for cat in ("entities", "concepts"):
        for f in (wiki / cat).glob("*.md"):
            names.add(f.stem.lower())
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        fm = yaml.safe_load(parts[1])
                        if isinstance(fm, dict):
                            for a in fm.get("aliases") or []:
                                if isinstance(a, str):
                                    names.add(a.strip().lower())
            except Exception:
                pass
    return names


def _is_excluded_heading(name: str) -> bool:
    """헤딩이 후보가 될 수 없는 형태인가 (URL · 확장자 · 셸/템플릿 · 숫자 · 구조 헤딩)."""
    if not name:
        return True
    if len(name) < 2 or len(name) > 80:
        return True
    if _URLISH_RE.search(name):
        return True
    if _EXT_RE.search(name):
        return True
    if _NUM_RE.match(name):
        return True
    if _SHELL_SIG_RE.search(name):
        return True
    if _TEMPLATE_RE.search(name):
        return True
    if name.lower() in SKIP_COMMON:
        return True
    return False


def find_candidates(wiki_home: Path, min_count: int = 2) -> tuple[dict, int]:
    """source **본문 헤딩(코드 펜스 밖)** 중 대응 페이지가 없는 것을 후보로 모은다.

    반환: ``(candidates, scanned_source_count)``
    """
    wiki = wiki_home / "wiki"
    sources_root = wiki / "sources"
    source_files = [
        f for f in sources_root.rglob("*.md") if ".archived" not in str(f)
    ]
    existing = _load_existing_names(wiki)

    # 후보 키는 **소문자로 통일**한다 — existing 매칭이 lowercase 이므로
    # 집계 키도 같은 기준이어야 한다. 원본 케이스로 키잉하면 `CaseVar`/`casevar`
    # 가 각각 count 1 이 되어 min_count 에 미달, 후보가 통째로 사라진다
    # (PR #217 리뷰 [mid]).
    candidates: dict[str, dict] = {}
    display: dict[str, str] = {}  # lowercase → 최초 관측 원본 표기

    for f in source_files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        try:
            rel = str(f.relative_to(sources_root))
        except ValueError:
            rel = str(f)
        for name in iter_body_headings(text):
            if _is_excluded_heading(name):
                continue
            key = name.lower()
            if key in existing:
                continue
            if key not in candidates:
                candidates[key] = {"count": 0, "sources": 0, "refs": [], "variants": []}
                display[key] = name
            entry = candidates[key]
            entry["count"] += 1
            if rel not in entry["refs"]:
                entry["sources"] += 1  # 출현 파일 수 — count(출현 횟수)와 구분한다
            if len(entry["refs"]) < 3 and rel not in entry["refs"]:
                entry["refs"].append(rel)
            # 표기 변형을 기록한다 — 같은 후보로 합산됐음을 보고서에서 확인 가능.
            if name not in entry["variants"]:
                entry["variants"].append(name)

    strong = {
        display[k]: v
        for k, v in sorted(candidates.items(), key=lambda x: -x[1]["count"])
        if v["count"] >= min_count
    }
    return strong, len(source_files)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Step 6 모순 후보 검출 — 본문 헤딩(코드 펜스 밖) 기준 (issue #214)"
    )
    ap.add_argument("--wiki-home", default=None, help="WIKIHUB_HOME (ADR-0034 default: ~/wikihub)")
    ap.add_argument("--min-count", type=int, default=2, help="후보 최소 출현 (default 2)")
    ap.add_argument("--json", default=None, help="후보 JSON 출력 경로 (기본: wiki/_lint/_step6_candidates.json)")
    ap.add_argument(
        "--summarize-hanja",
        default=None,
        help="주어진 파일의 한자를 요약만 한다 (살균 확인용, issue #213)",
    )
    args = ap.parse_args()

    if args.summarize_hanja:
        try:
            text = Path(args.summarize_hanja).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        count, summary = summarize_hanja(text)
        print(f"hanja={count} summary={summary}")
        return 0

    wiki_home = _resolve_wiki_home(args.wiki_home)
    if not (wiki_home / "wiki").is_dir():
        print(f"error: wiki 디렉토리 부재: {wiki_home}/wiki", file=sys.stderr)
        return 2

    strong, scanned = find_candidates(wiki_home, min_count=args.min_count)

    print(f"Scanned {scanned} source files")
    print("Missing entity/concept candidates (body headings outside code fences):")
    for name, info in list(strong.items())[:30]:
        # count = 출현 횟수, sources = 출현 파일 수. 같지 않을 수 있다 —
        # 한 파일 안에서 여러 번 나온 헤딩이 그 예 (PR #217 리뷰 [low]).
        detail = f"{info['count']} occ"
        if info.get("sources") and info["sources"] != info["count"]:
            detail += f" / {info['sources']} sources"
        var = info.get("variants") or []
        if len(var) > 1:
            detail += f" / variants: {', '.join(var[:3])}"
        print(f"  [[{name}]] — {detail} (e.g. {info['refs'][0]})")
    print(f"\nTotal candidates: {len(strong)}")

    out = Path(args.json) if args.json else (wiki_home / "wiki" / "_lint" / "_step6_candidates.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"strong": dict(list(strong.items())[:50])}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"written: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
