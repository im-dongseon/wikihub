"""ref_match 판정 규정 테스트 (issue #215).

핵심 회귀: **re.IGNORECASE 누락**. 이 플래그가 없으면 `Go`·`AST` 같은 대문자 이름이
본문 소문자 표기와 매칭되지 않아 오등록이 3,928 → 7,383 으로 과대계상된다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_HELPERS = Path(__file__).resolve().parent.parent / "scripts" / "_helpers"
sys.path.insert(0, str(_HELPERS))

import ref_match as R  # noqa: E402


# ── 1. classify
@pytest.mark.parametrize(
    "name,expected",
    [
        ("AGENTS.md", "ext"),
        ("wikihub.yaml", "ext"),
        ("_lint_step6.py", "ext"),
        ("AST", "ascii"),
        ("Go", "ascii"),
        ("GitHub CLI", "ascii"),
        ("에이닷", "cjk"),
        ("마이크론", "cjk"),
        ("한자", "cjk"),
    ],
)
def test_classify(name, expected):
    assert R.classify(name) == expected


# ── 2. ASCII 토큰 경계 — 짧은 이름이 긴 단어 안에서 매칭되지 않는다
@pytest.mark.parametrize("name,body", [("OS", "most"), ("OS", "cost"), ("OS", "host")])
def test_os_not_inside_longer_words(name, body):
    assert R.matches(name, body) is False


@pytest.mark.parametrize("name,body", [("AST", "Fast"), ("AST", "last"), ("AST", "taste")])
def test_ast_not_inside_longer_words(name, body):
    assert R.matches(name, body) is False


@pytest.mark.parametrize("name,body", [("OS", "OS 운영체제"), ("AST", "AST 기반"), ("Pi", "Pi 서버")])
def test_short_name_matches_standalone(name, body):
    assert R.matches(name, body) is True


# ── 3. ⚠️ re.I 회귀 — 이 테스트가 실패하면 플래그가 빠진 것이다
def test_case_insensitive_uppercase_name_vs_lowercase_body():
    """`Go`(페이지) vs `go`(본문 소문자).

    ⚠️ 이 단언은 **vacuous 하다** — `ascii_pattern()` 이 이름을 소문자로 낮춰
    `(?<![a-z0-9])go(?![a-z0-9])` 를 만들므로 re.I 없이도 통과한다.
    비-vacuous 회귀 검출은 아래 `test_re_i_regression_non_vacuous` 가 담당한다.
    (역사적 이유로 남겨둔다 — 초기 스펙의 단언이었다.)
    """
    assert R.matches("Go", "go") is True


@pytest.mark.parametrize(
    "name,body",
    [
        ("Go", "GO"),                      # 본문이 대문자
        ("Go", "Go"),                      # 본문이 원형
        ("AST", "AST"),                    # 약어 원형
        ("GitHub CLI", "GITHUB CLI"),      # 다중 토큰 대문자
        ("GitHub CLI", "GitHub CLI"),      # 다중 토큰 원형
        ("Pi", "PI"),
    ],
)
def test_re_i_regression_non_vacuous(name, body):
    """⚠️ **re.I 를 제거하면 반드시 실패해야 한다.**

    `ascii_pattern()` 은 이름을 소문자로 낮추므로, 본문이 소문자가 아닌 경우
    (대문자·원형)에는 re.I 없이 매칭되지 않는다. 이 케이스들이 실질 회귀 검출이다 —
    re.I 누락 시 대문자 이름이 전부 미매칭되어 오등록이 3,928 → 7,383 으로 과대계상된다.
    """
    assert R.matches(name, body) is True


def test_re_i_absence_is_detectable():
    """re.I 없이 돌리면 위 케이스가 False 가 됨을 직접 확인 (회귀 검출력 실증)."""
    pat = R.ascii_pattern("Go")
    assert pat is not None
    assert re.search(pat, "GO", re.IGNORECASE) is not None
    assert re.search(pat, "GO") is None      # ← re.I 없으면 미매칭 (회귀가 검출됨)



def test_case_insensitive_mixed_case():
    assert R.matches("Go", "Go language") is True
    assert R.matches("AST", "ast") is True
    assert R.matches("GitHub CLI", "GITHUB CLI 사용") is True


def test_ascii_pattern_includes_case_handling_documented():
    """패턴 자체는 소문자 토큰을 만들고, 호출 측이 re.I 를 붙인다."""
    pat = R.ascii_pattern("GitHub CLI")
    assert pat is not None
    assert "github" in pat and "cli" in pat
    # 구분자 허용 (hyphen·공백·괄호)
    assert R.matches("GitHub CLI", "GitHub-CLI") is True
    assert R.matches("GitHub CLI", "GitHub_CLI") is True


# ── 4. ext 분기 — 확장자 포함 이름은 완전 일치
def test_ext_branch_requires_full_match():
    """`AGENTS.md` 페이지는 bare `agents` 에 매칭되지 않는다."""
    assert R.matches("AGENTS.md", "agents are useful") is False
    assert R.matches("AGENTS.md", "AGENTS.md 파일") is True
    assert R.matches("AGENTS.md", "agents.md") is True


# ── 5. cjk 분기 — 표기변형 정규화
def test_cjk_normalization():
    assert R.matches("구글_지식_그래프", "구글 지식 그래프") is True
    assert R.matches("밀리의_서재", "밀리의 서재") is True
    assert R.matches("Context Graph (CGs)", "Context Graph(CGs)") is True


def test_cjk_does_not_match_when_absent():
    assert R.matches("에이닷", "전혀 무관한 내용") is False


# ── 6. 전역 정규화 금지 — 줄을 넘나드는 매칭 차단
def test_cjk_normalization_is_line_scoped():
    """전역 정규화면 `구글 지식\\n그래프` 가 붙어 오탐이 된다."""
    body = "구글 지식\n그래프"
    assert R.matches("구글_지식_그래프", body) is False
    assert R.matches("구글_지식", body) is True


def test_normalize_kr_removes_separators():
    assert R.normalize_kr("구글_지식-그래프") == "구글지식그래프"
    assert R.normalize_kr("Context Graph (CGs)") == "contextgraphcgs"


# ── 7. verdict — P3 우선순위
def test_p3_takes_precedence_over_p1():
    """동형명사 페이지는 개별 ref 가 완전부재처럼 보여도 P3 로 보고한다."""
    v, name, _ = R.verdict({"Go"}, "---\naliases:\n- Go\n---\n\n아무 내용")
    assert v == "P3"
    assert name is None


def test_p3_takes_precedence_over_ok():
    v, _name, _ = R.verdict({"Go"}, "---\naliases:\n- Go\n---\n\nGo language")
    assert v == "P3"


def test_verdict_p1_for_non_homograph():
    # P1 = 이름·alias 가 source **어디에도** 없음 → 픽스처에 fm·본문 모두 이름 부재
    v, name, _ = R.verdict({"Zebra"}, "---\ntags: [other]\n---\n\n무관 내용")
    assert v == "P1"
    assert name is None


def test_verdict_p2_frontmatter_only():
    text = "---\ntags: [Zebra]\n---\n\n본문에 이름 없음"
    v, _name, _ = R.verdict({"Zebra"}, text)
    assert v == "P2"


def test_verdict_ok_returns_name_and_line():
    text = "---\naliases:\n- Zebra\n---\n\n첫 줄\nZebra 등장"
    v, name, line = R.verdict({"Zebra"}, text)
    assert v == "OK"
    assert name == "Zebra"
    # body = "첫 줄\nZebra 등장" (frontmatter 이후 개행은 split 이 소비) → 'Zebra' 는 2번째 줄
    assert line == 2


# ── 8. homograph 목록이 실제로 채워져 있다
def test_homograph_allowlist_populated():
    for n in ("go", "os", "pr", "ast", "sst", "pi", "ip", "ci", "ai"):
        assert n in R.HOMOGRAPH_NAMES


def test_non_homograph_page_not_p3():
    assert "zebra" not in R.HOMOGRAPH_NAMES
