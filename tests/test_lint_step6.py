"""_lint_step6 — 후보 검출(#214) + 한자 살균(#213) 테스트."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_HELPERS = Path(__file__).resolve().parent.parent / "scripts" / "_helpers"
sys.path.insert(0, str(_HELPERS))

import _lint_step6 as S  # noqa: E402

_HANJA = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


# ══ #213 — sanitize_hanja ══════════════════════════════════════════════════
def test_sanitize_replaces_hanja_with_codepoint():
    assert S.sanitize_hanja("汉") == "U+6C49"


def test_sanitize_leaves_non_hanja_untouched():
    """한글·ASCII·가나는 살균 대상이 아니다."""
    src = "abc 漢字 한글テスト !@#"
    out = S.sanitize_hanja(src)
    assert "한글" in out          # 한글 보존
    assert "テスト" in out         # 가나 보존
    assert "abc" in out           # ASCII 보존
    assert "!@#" in out
    assert "漢字" not in out       # 한자는 치환됨


def test_sanitize_output_has_zero_hanja():
    src = "复度思杂源笔记 · 千義通问 · 界面 · 场景 · 多 · 下面"
    out = S.sanitize_hanja(src)
    assert _HANJA.findall(out) == []
    assert "U+590D" in out


def test_sanitize_is_idempotent_on_clean_text():
    clean = "no hanja here 한글만"
    assert S.sanitize_hanja(clean) == clean


# ══ #213 — summarize_hanja ═════════════════════════════════════════════════
def test_summarize_counts_and_is_hanja_free():
    total, summary = S.summarize_hanja("复度思杂源笔记")
    assert total == 7
    assert _HANJA.findall(summary) == []
    assert "7자 1건" in summary


def test_summarize_multiple_runs():
    # 2자 run 1개 + 1자 run 2개
    total, summary = S.summarize_hanja("界面 그리고 多 그리고 的")
    assert total == 4
    assert _HANJA.findall(summary) == []
    assert "2자 1건" in summary
    assert "1자 2건" in summary


def test_summarize_no_hanja():
    total, summary = S.summarize_hanja("한글만 있고 한자 없음")
    assert total == 0
    assert "0자" in summary


# ══ #214 — 코드 펜스 밖 헤딩만 추출 ════════════════════════════════════════
def test_code_fence_headings_excluded():
    """펜스 내부 `# ...` 는 문서 구조가 아니라 예시 코드다 (후보 13건 중 11건이 이 경우)."""
    doc = (
        "# 실제 헤딩1\n"
        "본문\n"
        "```bash\n"
        "# 설치 및 실행\n"
        "[[ 또는 ]]\n"
        "```\n"
        "# 실제 헤딩2\n"
        "```\n"
        "# 펜스 내부 2\n"
        "```\n"
        "# 실제 헤딩3\n"
    )
    assert list(S.iter_body_headings(doc)) == ["실제 헤딩1", "실제 헤딩2", "실제 헤딩3"]


def test_tilde_fence_also_excluded():
    doc = "# 밖\n~~~\n# 안\n~~~\n# 밖2\n"
    assert list(S.iter_body_headings(doc)) == ["밖", "밖2"]


def test_unclosed_fence_hides_rest():
    """닫히지 않은 펜스 뒤는 코드로 본다 (문서 파손 시 안전측)."""
    doc = "# 밖\n```\n# 안1\n# 안2\n"
    assert list(S.iter_body_headings(doc)) == ["밖"]


def test_nested_fence_shorter_marker_does_not_close():
    """리뷰 [mid] 회귀 — 4-backtick 펜스 안의 3-backtick 줄은 닫힘으로 성립하지 않는다.

    CommonMark: 닫는 펜스는 같은 문자 + **길이 이상**이어야 한다.
    길이를 보지 않으면 안쪽 헤딩이 누출한다.
    """
    doc = "````\n# outer\n```\n# inner (펜스 안)\n````\n# real\n"
    assert list(S.iter_body_headings(doc)) == ["real"]


def test_nested_fence_longer_marker_closes():
    """3-backtick 을 4-backtick 으로 닫는 것은 허용 (길이 이상)."""
    doc = "```\n# in\n````\n# out\n"
    assert list(S.iter_body_headings(doc)) == ["out"]


def test_frontmatter_yaml_comment_not_heading():
    """리뷰 [low] 회귀 — frontmatter 안 YAML 주석(`# ...`)은 본문 헤딩이 아니다."""
    doc = "---\ntitle: x\n# yaml comment\n---\n\n# 실제 헤딩\n"
    assert list(S.iter_body_headings(doc)) == ["실제 헤딩"]


def test_indented_atx_heading_up_to_3_spaces():
    """리뷰 [low] 회귀 — ATX 헤딩은 최대 3칸 들여쓰기 허용, 4칸 이상은 코드 블록."""
    doc = "   # 들여쓴\n# 정상\n     # 5칸(초과)\n"
    assert list(S.iter_body_headings(doc)) == ["들여쓴", "정상"]


# ══ #214 — 후보 제외 규칙 ═════════════════════════════════════════════════
@pytest.mark.parametrize(
    "name,excluded",
    [
        ("https://x.com", True),
        ("http://localhost:7000", True),
        ("wikihub.yaml", True),
        ("a.md", True),
        ("wikihub-lint.service", True),
        ("123", True),
        ("x", True),                      # 길이 < 2
        ("설치 및 실행", True),             # SKIP_COMMON
        ("저장소 클론", True),
        ("수정 후", True),
        ('-z $KUBECTL_COMPLETE', True),   # 셸 신호
        ('"$sandbox" == "1"', True),
        ("<name>", True),                 # 템플릿
        ("analyses/...", True),
        ("nas/article/x.md", True),       # 확장자 + 경로
        ("Superpowers", False),           # 진성 — 이름 자체로는 노이즈가 아니다
        ("에이전트-워커-모델", False),
    ],
)
def test_excluded_heading_rules(name, excluded):
    assert S._is_excluded_heading(name) is excluded


# ══ #214 — find_candidates (fixture 기반) ═════════════════════════════════
def _mk(tmp_path: Path, rel: str, content: str) -> None:
    p = tmp_path / "wiki" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_heading_in_code_fence_not_candidate(tmp_path):
    """#214 핵심 회귀 — 펜스 내부 헤딩은 후보가 되지 않는다."""
    _mk(tmp_path, "entities/Exists.md", "---\naliases:\n- Exists\n---\n")
    _mk(
        tmp_path,
        "sources/x/a.md",
        "```bash\n# 설치 및 실행\n```\n```\n# 설치 및 실행\n```\n",
    )
    strong, _ = S.find_candidates(tmp_path)
    assert "설치 및 실행" not in strong


def test_real_heading_without_page_is_candidate(tmp_path):
    _mk(tmp_path, "entities/Exists.md", "---\naliases:\n- Exists\n---\n")
    _mk(tmp_path, "sources/x/a.md", "# 없는페이지\n# 없는페이지\n")
    strong, _ = S.find_candidates(tmp_path)
    assert strong.get("없는페이지", {}).get("count") == 2


def test_existing_page_heading_not_candidate(tmp_path):
    _mk(tmp_path, "entities/Exists.md", "---\naliases:\n- Exists\n---\n")
    _mk(tmp_path, "sources/x/a.md", "# Exists\n# Exists\n")
    strong, _ = S.find_candidates(tmp_path)
    assert "Exists" not in strong


def test_single_occurrence_not_candidate(tmp_path):
    _mk(tmp_path, "sources/x/a.md", "# 한번만\n")
    strong, _ = S.find_candidates(tmp_path)
    assert "한번만" not in strong


def test_alias_of_existing_page_not_candidate(tmp_path):
    _mk(tmp_path, "concepts/MiniMax.md", "---\naliases:\n- MiniMax\n- mini-max\n---\n")
    _mk(tmp_path, "sources/x/a.md", "# mini-max\n# mini-max\n")
    strong, _ = S.find_candidates(tmp_path)
    assert "mini-max" not in strong


def test_archived_sources_skipped(tmp_path):
    _mk(tmp_path, "sources/.archived/a.md", "# 없는페이지\n# 없는페이지\n")
    strong, _ = S.find_candidates(tmp_path)
    assert "없는페이지" not in strong


# ══ PR #217 2차 리뷰 [mid]·[low] 회귀 — 실측 재현된 결함 ═══════════════════
def test_closing_fence_info_string_is_open_fence():
    """[mid] ```` ```bash ```` 는 여는 펜스다 — 닫는 펜스가 아니다."""
    doc = "```\n```bash\n# leak\n```\n# real\n"
    assert list(S.iter_body_headings(doc)) == ["real"]


def test_sources_count_independent_of_refs_cap(tmp_path):
    """[mid] sources 는 refs 캡(3)과 무관하게 세야 한다.

    refs 로 중복을 판정하면 4번째 파일부터 캡에 걸려 sources 가 출현 횟수처럼
    부풀려진다. 별도 seen 집합으로 세야 한다.
    """
    for name in "ABCDE":
        body = "# Dup\n# Dup\n" if name == "D" else "# Dup\n"
        _mk(tmp_path, f"sources/{name}/f.md", body)
    strong, _ = S.find_candidates(tmp_path, min_count=2)
    e = strong["Dup"]
    assert e["count"] == 6, f"출현 횟수 오류: {e}"      # A,B,C,E 1회 + D 2회
    assert e["sources"] == 5, f"파일 수 오류: {e}"       # A~E 5개 파일
    assert len(e["refs"]) == 3, f"refs 캡 위반: {e}"     # refs 는 3으로 캡


@pytest.mark.parametrize(
    "heading,expected",
    [
        ("# C#", "C#"),            # CommonMark: 앞 공백 없는 `#` 는 텍스트의 일부
        ("# F# language", "F# language"),
        ("# foo #", "foo"),        # 앞 공백 있는 닫는 시퀀스는 제거된다
        ("# foo bar##", "foo bar##"),
        ("# 제목#", "제목#"),        # `# 제목` 과 합쳐지면 count 가 부풀려진다
    ],
)
def test_trailing_hash_only_stripped_after_space(heading, expected):
    """[mid] 닫는 `#` 시퀀스는 앞에 공백/탭이 있을 때만 제거한다."""
    assert list(S.iter_body_headings(heading)) == [expected]


@pytest.mark.parametrize(
    "doc,should_strip",
    [
        ("---\ntitle: x\nsource:\n  vault: nas\n---\n# H\n", True),   # 중첩 mapping
        ("---\ntitle: x\naliases:\n- A\n---\n# H\n", True),           # 리스트 포함
        ("---\n# just a comment\n---\n# Body\n", False),              # 주석만 → 비-mapping
        ("---\n- item one\n- item two\n---\n# Body\n", False),        # YAML 리스트
        ("---\n# 첫 헤딩\n---\n# 둘째 헤딩\n", False),                    # 수평선 시작
        ("---\n---\n# Body\n", False),                                # 빈 블록
        ("# frontmatter 없음\n", False),
    ],
)
def test_frontmatter_detection(doc, should_strip):
    """[low] 실제 frontmatter 는 YAML **매핑**일 때만 제거한다."""
    assert (S._strip_frontmatter(doc) != doc) is should_strip


def test_frontmatterless_body_not_swallowed():
    """[low] 수평선으로 시작하는 문서에서 본문이 잘리지 않는다.

    ⚠️ 이 테스트는 **기존 코드에서도 통과했다**(vacuous). 그래서 판정 기준을
    'YAML 매핑일 때만' 으로 강화하고 위 parametrized 테스트로 케이스를 넓혔다.
    """
    doc = "---\n# 첫 헤딩\n---\n# 둘째 헤딩\n"
    assert "둘째 헤딩" in list(S.iter_body_headings(doc))


def test_candidates_json_serializable(tmp_path):
    """후보 dict 는 JSON 직렬화 가능해야 한다.

    내부 중복 판정용 set 을 후보 dict 에 넣으면 `--json` 출력이
    `TypeError: Object of type set is not JSON serializable` 로 죽는다 —
    테스트가 아니라 **실행 경로에서만** 드러나므로 별도로 고정한다.
    """
    import json

    _mk(tmp_path, "sources/A/f.md", "# 직렬화\n# 직렬화\n")
    strong, _ = S.find_candidates(tmp_path)
    json.dumps({"strong": strong})  # 예외 없이 통과해야 한다



