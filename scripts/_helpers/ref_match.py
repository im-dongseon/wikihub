"""referenced_by 매칭 규정 — 3중 분기 (issue #215).

`referenced_by` 등록 판정이 단순 부분문자열 매칭이라 `os` 가 `most`·`cost`·`host` 안에서,
`agents` 가 `agents.md` 안에서 매칭되는 오등록이 발생했다 (실측 3,928건 / 315페이지).

이 모듈은 판정 로직의 **단일 정본**이며, `ref_ledger.py`(근거 기록)와
`ref_audit.py`(lint 검출기)가 함께 import 한다.

분기:
  ① ext   — 확장자 포함 이름(`AGENTS.md`)      → 완전 일치 (대소문자 무시)
  ② ascii — ASCII 이름(`AST`·`OS`·`Go`)        → 토큰 경계 (구분자 허용, 양쪽 비영숫자)
  ③ cjk   — 한글·CJK 이름(`에이닷`·`마이크론`) → 표기변형 정규화 후 **같은 줄** substring

⚠️ ②는 ``re.IGNORECASE`` 필수 — 이름과 본문 표기가 대소문자로 다르다(`Go` vs `go`).
   누락 시 대문자 이름이 전부 미매칭되어 오등록이 3,928 → 7,383 으로 과대계상된다.
⚠️ 표기 정규화를 ②에 적용하지 않는다 — `AST` → `ast` 로 낮추면 `Fast`·`last`·`taste`
   에 걸린다. ③에만 적용한다.
⚠️ 전역 정규화 금지 — ``re.sub(r'[-_\\s]+','',whole_body)`` 는 개행까지 지워 인접 단어를
   이어붙여 오탐을 위조한다. ③은 반드시 줄 단위로만 적용한다.
"""

from __future__ import annotations

import re

BRANCH_EXT = "ext"
BRANCH_ASCII = "ascii"
BRANCH_CJK = "cjk"

# 구분자 — hyphen / underscore / whitespace / 괄호 / 대괄호 / slash
_SEP = r"[-_\s()\[\]/]"
_SEP_RUN = re.compile(_SEP + r"+")

# 확장자 포함 이름 판정
_EXT_RE = re.compile(r"\.(md|yaml|yml|json|py|sh|txt)$", re.IGNORECASE)

# 한글 / CJK / 가나
_CJK_RE = re.compile(r"[\uac00-\ud7a3\u4e00-\u9fff\u3040-\u30ff]")

# ⚠️ 동형명사(homograph) — 일반명사·영어 단어와 충돌해 **문자열 매칭으로 진성/오염을
# 구분할 수 없는** 이름. 이 페이지들은 P3(판정 불가)로 분류되어 **자동 제거 대상이
# 아니며 목록 보고만** 한다.
#
# 근거 실측 (`Go`): 언어 문맥 14건 / 일반 동사 문맥 54건 — 같은 단어가 문맥에 따라
# 언어이기도 동사이기도 하다 ("have a go at", "ready to go", "Go language").
# `OS` ⊂ most·cost·host, `AST` ⊂ Fast·last·taste, `PR` ⊂ process·project 도 동일 계열.
HOMOGRAPH_NAMES: frozenset[str] = frozenset(
    {
        # 짧은 ASCII 약어 — 영어 단어·부분문자열과 충돌
        "ast", "sst", "pr", "pi", "os", "ip", "per", "omp", "ci", "ai",
        "ide", "orm", "ui", "go", "ram", "git", "amp", "tab", "owl", "uri",
        "web", "zed", "zen", "neo", "cd", "ml", "db", "io", "vm",
        # 프로토콜·형식 약어 — 일반명사와 겹침
        "api", "http", "url", "tls", "dns", "sql", "csv", "json", "xml", "yaml",
    }
)


def classify(name: str) -> str:
    """이름 유형 판정 — ``ext`` | ``ascii`` | ``cjk``."""
    if _EXT_RE.search(name):
        return BRANCH_EXT
    if _CJK_RE.search(name):
        return BRANCH_CJK
    return BRANCH_ASCII


def normalize_kr(s: str) -> str:
    """③ 전용 정규화 — lowercase 후 구분자 run 제거.

    ``구글_지식_그래프`` → ``구글지식그래프`` (본문 ``구글 지식 그래프`` 와 동일).
    개행은 제거 대상이 아니며(``\\s`` 에 포함되나 호출 측이 줄 단위로 자름), 호출 측은
    반드시 **한 줄**을 넘겨야 한다.
    """
    return _SEP_RUN.sub("", s.lower())


def ascii_pattern(name: str) -> str | None:
    """② 전용 — 토큰 경계 정규식. 토큰이 없으면 None.

    ``GitHub CLI`` → ``(?<![a-z0-9])github[^a-z0-9]{0,3}cli(?![a-z0-9])``
    (구분자가 hyphen·공백·괄호 등으로 달라도 허용)

    ⚠️ 반환 패턴은 반드시 ``re.IGNORECASE`` 와 함께 쓴다 (``matches`` 참조).
    """
    toks = [t for t in _SEP_RUN.split(name.lower()) if t]
    if not toks:
        return None
    joined = r"[^a-z0-9]{0,3}".join(re.escape(t) for t in toks)
    return r"(?<![a-z0-9])" + joined + r"(?![a-z0-9])"


def matches(name: str, body: str) -> bool:
    """3중 분기 매칭 — ``body`` 는 source 의 **본문**(frontmatter 제외)이어야 한다."""
    branch = classify(name)

    if branch == BRANCH_EXT:
        # ① 확장자 포함 — 완전 일치. `agents` ≠ `agents.md`
        return name.lower() in body.lower()

    if branch == BRANCH_ASCII:
        # ② 토큰 경계 — re.I 필수
        pat = ascii_pattern(name)
        return bool(pat and re.search(pat, body, re.IGNORECASE))

    # ③ 한글·CJK — 줄 단위 정규화 substring (전역 정규화 금지)
    needle = normalize_kr(name)
    if not needle:
        return False
    return any(needle in normalize_kr(line) for line in body.split("\n"))


def _split_frontmatter(text: str) -> tuple[str, str]:
    """``(frontmatter, body)`` 분리. frontmatter 없으면 ``("", text)``."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if m:
        return m.group(1), text[m.end():]
    return "", text


def _match_line(name: str, body: str) -> int:
    """매칭된 줄 번호(1-based, **body 기준**). 없으면 0.

    ``matches()`` 와 동일한 패턴을 쓰되 위치를 얻기 위해 별도로 ``search`` 한다.
    패턴 생성은 :func:`ascii_pattern` 단일 정본을 공유하므로 분기 로직이 갈라지지 않는다.
    (파일 절대 줄 번호가 필요하면 frontmatter 줄 수를 더해야 한다 — ledger 는 body 기준을 쓴다.)
    """
    branch = classify(name)
    if branch == BRANCH_CJK:
        needle = normalize_kr(name)
        if not needle:
            return 0
        for i, line in enumerate(body.split("\n"), 1):
            if needle in normalize_kr(line):
                return i
        return 0

    if branch == BRANCH_EXT:
        pattern = re.escape(name)
    else:
        pattern = ascii_pattern(name)
        if not pattern:
            return 0

    m = re.search(pattern, body, re.IGNORECASE)   # ⚠️ re.I 필수 (matches 와 동일)
    if not m:
        return 0
    return body[: m.start()].count("\n") + 1


def verdict(names: set[str], full_text: str) -> tuple[str, str | None, int]:
    """판정 — ``(verdict, matched_name, line_no)``.

    verdict:
      ``OK``  매칭됨 (matched_name·line_no 채움)
      ``P1``  이름·alias 가 source **어디에도** 없음 (완전부재 — 제거 대상)
      ``P2``  source **frontmatter 에만** 있고 본문엔 없음 (제거 대상)
      ``P3``  동형명사 페이지 — **판정 불가, 자동 제거 금지** (목록 보고만)

    ⚠️ **P3 가 P1/P2 보다 우선한다.** 동형명사 페이지는 개별 ref 가 P1/P2 처럼 보여도
    항상 P3 로 보고한다 — 문자열 매칭으로 그 페이지의 진성/오염을 결정할 수 없다는 것이
    요점이다.
    """
    cand = sorted(n for n in names if n)
    if not cand:
        return "P1", None, 0

    # P3 우선 — 동형명사 이름을 하나라도 가진 페이지
    lowered = {n.lower() for n in cand}
    if lowered & HOMOGRAPH_NAMES:
        return "P3", None, 0

    front, body = _split_frontmatter(full_text)

    for name in cand:
        if matches(name, body):
            return "OK", name, _match_line(name, body)

    # 본문 미매칭 — frontmatter 에만 있는지 구분
    for name in cand:
        if matches(name, front):
            return "P2", None, 0

    return "P1", None, 0
