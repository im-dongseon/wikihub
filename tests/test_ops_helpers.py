"""scripts/_helpers/ 정본 helper 회귀 테스트 (#201 ⑥⑧).

회귀 방지 대상:
  ⑥ 정본화 — 경로 복원 체계가 arg > env > WIKIHUB_YAML 부모 > default 순으로 동작한다.
     하드코딩 `/home/ubuntu/wikihub` 이 남아 있으면 실패한다 (이식성 회귀).
  ⑧ 검출기 결손 — (a) aliases block 형 인식  (b) `.md` 이중 부착  (c) concepts 은닉
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HELPERS = REPO / "scripts" / "_helpers"

CANON_HELPERS = [
    "lint_mechanical.py",
    "analyze_graph_v3.py",
    "rebuild_index.py",
    "step7_apply.py",
    "apply_fixes.py",
    "_wl_step2_spec.py",
    "_wl_check_missing_cycle.py",
]


def _load(name: str):
    path = HELPERS / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── ⑥ 정본화: 하드코딩 제거 ──────────────────────────────────────────


@pytest.mark.parametrize("name", CANON_HELPERS)
def test_no_hardcoded_wikihub_path(name):
    """정본 helper 에 `/home/ubuntu/wikihub` 하드코딩이 남아 있으면 안 된다."""
    text = (HELPERS / name).read_text(encoding="utf-8")
    # docstring/주석의 역사 설명은 허용 — 코드 라인만 검사
    code_lines = [
        ln for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    offenders = [
        ln for ln in code_lines
        if "/home/ubuntu/wikihub" in ln
        and "하드코딩" not in ln and "원 운영" not in ln
    ]
    assert not offenders, f"{name}: 하드코딩 경로 잔존 → {offenders[:3]}"


@pytest.mark.parametrize("name", CANON_HELPERS)
def test_resolve_functions_present(name):
    """경로 복원 함수가 정의돼 있어야 한다."""
    text = (HELPERS / name).read_text(encoding="utf-8")
    assert "_resolve_wiki_home" in text, f"{name}: _resolve_wiki_home 부재"
    assert "argparse" in text, f"{name}: argparse 부재"


def _resolve_wiki_home_standalone(name: str):
    """모듈 import 없이 _resolve_wiki_home 함수만 떼어낸다.

    정본 helper 들은 모듈 최상위에서 실제 파일을 읽고 쓰므로
    import 만으로 부작용이 난다. 테스트는 함수 정의만 추출해 검증한다.
    """
    text = (HELPERS / name).read_text(encoding="utf-8")
    m = re.search(r"def _resolve_wiki_home.*?(?=\ndef |\n_ARGS)", text, re.S)
    assert m, f"{name}: _resolve_wiki_home 정의를 찾지 못함"
    ns: dict = {"os": os, "Path": Path}
    exec(m.group(0), ns)  # noqa: S102 — 테스트 전용, 저장소 내 신뢰 파일
    return ns["_resolve_wiki_home"]


@pytest.mark.parametrize("name", CANON_HELPERS)
def test_wiki_home_arg_precedence(tmp_path, monkeypatch, name):
    """arg > env > WIKIHUB_YAML 부모 > default 순서 (helper 전건)."""
    monkeypatch.setenv("WIKIHUB_HOME", str(tmp_path / "from_env"))
    monkeypatch.setenv("WIKIHUB_YAML", str(tmp_path / "yaml_dir" / "wikihub.yaml"))
    fn = _resolve_wiki_home_standalone(name)

    assert fn(str(tmp_path / "from_arg")) == (tmp_path / "from_arg").resolve()
    assert fn(None) == (tmp_path / "from_env").resolve()

    monkeypatch.delenv("WIKIHUB_HOME")
    assert fn(None) == (tmp_path / "yaml_dir").resolve()

    monkeypatch.delenv("WIKIHUB_YAML")
    assert fn(None) == Path("~/wikihub").expanduser().resolve()


def test_helpers_are_executable_with_wiki_home(tmp_path):
    """정본 helper 가 --wiki-home 을 받고 실제로 실행돼야 한다 (이식성 실증).

    빈 wiki 트리를 만들어 rebuild_index 를 돌린다 — 하드코딩이 남아 있으면
    /home/ubuntu/wikihub 을 건드리거나 실패한다.
    """
    (tmp_path / "wiki").mkdir()
    for cat in ("entities", "concepts", "analyses", "sources", "_lint"):
        (tmp_path / "wiki" / cat).mkdir()

    r = subprocess.run(
        [sys.executable, str(HELPERS / "rebuild_index.py"), "--wiki-home", str(tmp_path)],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, f"rc={r.returncode} stderr={r.stderr[:300]}"
    assert (tmp_path / "wiki" / "index.md").is_file(), "index.md 미생성"
    # 하드코딩 경로를 건드리지 않았는지
    assert "Index" in r.stdout or "Total pages" in r.stdout, r.stdout[:200]


# ── ⑧(a) alias 파서: inline + block ─────────────────────────────────


def test_aliases_parser_reads_both_styles(tmp_path):
    """inline `[a, b]` 과 block `- c` 를 모두 인식해야 한다."""
    mod = _load("_wl_step2_spec.py")
    page = tmp_path / "P.md"
    page.write_text(
        "---\n"
        "type: entity\n"
        "aliases: [inline-a, inline-b]\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    got = mod.aliases_of(page)
    assert {"inline-a", "inline-b"} <= got, got

    page2 = tmp_path / "Q.md"
    page2.write_text(
        "---\n"
        "type: entity\n"
        "aliases:\n"
        "  - block-a\n"
        "  - block-b\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    got2 = mod.aliases_of(page2)
    assert {"block-a", "block-b"} <= got2, got2


def test_aliases_parser_block_does_not_swallow_next_key(tmp_path):
    """block aliases 뒤의 다른 top-level 키를 alias 로 먹으면 안 된다."""
    mod = _load("_wl_step2_spec.py")
    page = tmp_path / "R.md"
    page.write_text(
        "---\n"
        "aliases:\n"
        "  - only-a\n"
        "referenced_by:\n"
        "  - sources/x.md\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    got = mod.aliases_of(page)
    assert "only-a" in got
    assert "sources/x.md" not in got, got
    assert "referenced_by:" not in got, got


# ── ⑧(b) `.md` 이중 부착 ────────────────────────────────────────────


def test_md_suffix_not_doubled():
    """링크가 이미 `.md` 로 끝나면 재부착하지 않아야 한다."""
    text = (HELPERS / "_wl_step2_spec.py").read_text(encoding="utf-8")
    assert 'sub if sub.endswith(".md")' in text, "`.md` 조건부 재부착 부재"
    assert 'f"{sub}.md"' not in text or "_sub_md" in text, "무조건 재부착 잔존"


# ── ⑧(c) concepts 은닉 제거 ─────────────────────────────────────────


def test_no_concepts_blind_exclusion():
    """`_wl_check_missing_cycle.py` 가 concepts/ 를 무조건 통과시키면 안 된다."""
    text = (HELPERS / "_wl_check_missing_cycle.py").read_text(encoding="utf-8")
    offenders = [
        ln for ln in text.splitlines()
        if 'not p.startswith("concepts/")' in ln and not ln.strip().startswith("#")
    ]
    assert not offenders, f"concepts/ 무조건 제외 잔존 → {offenders}"


# ── ⑧ 셸 파편 필터 ──────────────────────────────────────────────────


def test_non_link_filter_present():
    """셸 파편·placeholder 를 위반으로 계상하지 않아야 한다."""
    text = (HELPERS / "_wl_step2_spec.py").read_text(encoding="utf-8")
    assert "NON_LINK_RE" in text, "NON_LINK_RE 필터 부재"


def test_short_link_resolution_present():
    """단축형을 판정 없이 전부 위반 1 로 넣으면 안 된다."""
    text = (HELPERS / "_wl_step2_spec.py").read_text(encoding="utf-8")
    assert 'resolve(link, "entities", idx)' in text, "단축형 해소 판정 부재"


def test_aliases_parser_reads_column_zero_block(tmp_path):
    r"""block aliases 가 **들여쓰기 없이** column 0 에 있어도 읽어야 한다 (#208).

    실측 분포: column 0 2,020 / 들여쓰기 272.
    구 정규식 `^\s+-\s+` 는 column-0 을 전량 놓쳐 alias 558건이 누락됐다.
    """
    mod = _load("_wl_step2_spec.py")
    page = tmp_path / "P.md"
    page.write_text(
        "---\n"
        "type: entity\n"
        "aliases:\n"
        "- ADR\n"
        "- ADR-0028\n"
        "- American Depositary Receipt\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    got = mod.aliases_of(page)
    assert {"adr", "adr-0028", "american depositary receipt"} <= got, got


def test_aliases_parser_column_zero_does_not_swallow_next_key(tmp_path):
    """column-0 block aliases 뒤의 top-level 키를 alias 로 삼키면 안 된다 (#208)."""
    mod = _load("_wl_step2_spec.py")
    page = tmp_path / "Q.md"
    page.write_text(
        "---\n"
        "aliases:\n"
        "- only-a\n"
        "merged_from:\n"
        "- concepts/Other\n"
        "referenced_by:\n"
        "- sources/x.md\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    got = mod.aliases_of(page)
    assert got == {"only-a"} or got == {"only-a", "q"}, got
    assert "concepts/other" not in got, got
    assert "sources/x.md" not in got, got


def test_aliases_parser_mixed_indent(tmp_path):
    """같은 페이지에 column-0 과 들여쓰기가 섞여도 전량 읽어야 한다 (#208)."""
    mod = _load("_wl_step2_spec.py")
    page = tmp_path / "R.md"
    page.write_text(
        "---\n"
        "aliases:\n"
        "- col0-a\n"
        "  - indented-b\n"
        "- col0-c\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    got = mod.aliases_of(page)
    assert {"col0-a", "indented-b", "col0-c"} <= got, got
