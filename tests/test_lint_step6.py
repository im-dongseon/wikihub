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


# ══ PR #217 리뷰 [mid] 회귀 — 실측 재현된 결함 2건 ═══════════════════════════
def test_closing_fence_with_info_string_does_not_close():
    """[mid 1] ```` ```bash ```` 는 여는 펜스다 — 닫는 펜스가 아니다 (CommonMark).

    뒤에 공백/탭 외 문자가 오면 닫는 펜스가 아니다. 이 규칙이 없으면 info string
    줄이 펜스를 닫아 안쪽 헤딩이 누출한다.
    """
    doc = "```\n```bash\n# leak\n```\n# real\n"
    assert list(S.iter_body_headings(doc)) == ["real"]


def test_closing_fence_with_trailing_spaces_closes():
    """닫는 펜스 뒤 공백/탭은 허용된다 (위 규칙의 반대편 — 누락 방지)."""
    doc = "```\n# in\n```   \n# out\n"
    assert list(S.iter_body_headings(doc)) == ["out"]


def test_roundtrip_case_variants_are_merged(tmp_path):
    """[mid 2] 표기 변형은 같은 후보로 합산된다 — 분리 집계 시 후보가 사라진다."""
    _mk(tmp_path, "sources/A/f.md", "# CaseVar\n")
    _mk(tmp_path, "sources/B/f.md", "# casevar\n")
    strong, _ = S.find_candidates(tmp_path)
    assert list(strong) == ["CaseVar"], f"분리 집계됨: {strong}"
    assert strong["CaseVar"]["count"] == 2
    assert sorted(strong["CaseVar"]["variants"]) == ["CaseVar", "casevar"]


def test_case_variant_meets_min_count(tmp_path):
    """분리 집계 시 각 count=1 이 되어 min_count 미달로 전량 소실된다."""
    _mk(tmp_path, "sources/A/f.md", "# GoLang\n")
    _mk(tmp_path, "sources/B/f.md", "# golang\n")
    strong, _ = S.find_candidates(tmp_path, min_count=2)
    assert len(strong) == 1, f"후보 소실: {strong}"


def test_occurrence_count_vs_source_count(tmp_path):
    """[low] 출현 횟수와 출현 파일 수는 다를 수 있다 — 라벨 오표기 방지."""
    _mk(tmp_path, "sources/A/f.md", "# Twice\n# Twice\n")
    strong, _ = S.find_candidates(tmp_path)
    assert strong["Twice"]["count"] == 2      # 출현 횟수
    assert strong["Twice"]["sources"] == 1    # 출현 파일 수


def test_frontmatterless_horizontal_rule_keeps_body():
    """수평선 `---` 로 시작하는 문서에서 본문이 잘리지 않는다."""
    doc = "---\n# 첫 헤딩\n---\n# 둘째 헤딩\n"
    got = list(S.iter_body_headings(doc))
    assert "둘째 헤딩" in got, f"본문 소실: {got}"

