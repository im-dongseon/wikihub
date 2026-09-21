"""detect_alias_duplicates.py — Step 4.5 alias 중복 탐지 테스트 (ADR-0039).

회귀 방지 대상 (issue #176):
  - 한 페이지의 aliases 가 정규화 후 같은 form 으로 겹칠 때, 그 페이지를
    자기 자신과 중복으로 보고하지 않는다 (오탐).
  - 서로 다른 페이지가 같은 alias 를 쓸 때는 계속 탐지한다 (회귀 없음).
  - 출력 ``pages`` 에 같은 경로가 2회 이상 나오지 않는다 (dedupe).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_HELPER = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "_helpers"
    / "detect_alias_duplicates.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("detect_alias_duplicates", _HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_mod = _load_module()


def _write_page(root: Path, category: str, name: str, aliases: list[str]) -> None:
    cat_dir = root / "wiki" / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"- {a}" for a in aliases)
    (cat_dir / f"{name}.md").write_text(
        f"---\naliases:\n{body}\n---\n# {name}\n", encoding="utf-8"
    )


def _detect(root: Path) -> dict:
    return _mod._detect_duplicates(_mod._collect_aliases(root))


def test_single_page_alias_variant_is_not_duplicate(tmp_path: Path) -> None:
    """한 페이지 안의 대소문자 변형 alias 는 중복이 아니다 (오탐 방지)."""
    _write_page(tmp_path, "entities", "xguru", ["xguru", "Xguru"])

    result = _detect(tmp_path)

    assert result["case_variant"] == []
    assert result["cross_category"] == []


def test_korean_alias_variant_within_one_page(tmp_path: Path) -> None:
    """운영 실측 케이스 — 한 페이지에 4개 표기 변형이 공존해도 오탐 아님."""
    _write_page(
        tmp_path,
        "concepts",
        "프롬프트 엔지니어링",
        ["프롬프트 엔지니어링", "Prompt Engineering", "프롬프팅", "prompt engineering"],
    )

    result = _detect(tmp_path)

    assert result["case_variant"] == []
    assert result["cross_category"] == []


def test_two_distinct_pages_same_alias_still_detected(tmp_path: Path) -> None:
    """서로 다른 페이지가 같은 alias 를 쓰면 계속 탐지한다 (회귀 없음)."""
    _write_page(tmp_path, "entities", "pagea", ["sharedalias"])
    _write_page(tmp_path, "entities", "pageb", ["sharedalias"])

    result = _detect(tmp_path)

    assert len(result["case_variant"]) == 1
    entry = result["case_variant"][0]
    assert entry["alias"] == "sharedalias"
    assert [p["path"] for p in entry["pages"]] == [
        "wiki/entities/pagea.md",
        "wiki/entities/pageb.md",
    ]


def test_cross_category_duplicate_still_detected(tmp_path: Path) -> None:
    """entity + concept 이 같은 alias 를 쓰면 cross_category 로 탐지한다."""
    _write_page(tmp_path, "entities", "dupa", ["sharedalias"])
    _write_page(tmp_path, "concepts", "dupc", ["sharedalias"])

    result = _detect(tmp_path)

    assert result["case_variant"] == []
    assert len(result["cross_category"]) == 1
    assert [p["path"] for p in result["cross_category"][0]["pages"]] == [
        "wiki/entities/dupa.md",
        "wiki/concepts/dupc.md",
    ]


def test_output_pages_deduped_by_path(tmp_path: Path) -> None:
    """한 페이지가 변형 alias 를 가진 채 타 페이지와 alias 를 공유해도 각 페이지 1회만 보고."""
    _write_page(tmp_path, "entities", "pagea", ["Shared", "shared"])
    _write_page(tmp_path, "entities", "pageb", ["shared"])

    result = _detect(tmp_path)

    assert len(result["case_variant"]) == 1
    paths = [p["path"] for p in result["case_variant"][0]["pages"]]
    assert paths == ["wiki/entities/pagea.md", "wiki/entities/pageb.md"]
    assert len(paths) == len(set(paths))


@pytest.mark.parametrize("category", ["entities", "concepts"])
def test_aliases_missing_uses_stem_only(tmp_path: Path, category: str) -> None:
    """aliases 부재 페이지는 파일 stem 하나만 canonical 로 잡혀 오탐이 없다."""
    _write_page(tmp_path, category, "onlystem", [])

    result = _detect(tmp_path)

    assert result["case_variant"] == []
    assert result["cross_category"] == []
