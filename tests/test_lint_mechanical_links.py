"""lint_mechanical Step 2 링크 가드 · Step 4.5 인터프리터 (issue #223)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HELPER = REPO / "scripts" / "_helpers" / "lint_mechanical.py"


def _load():
    spec = importlib.util.spec_from_file_location("lint_mechanical_223", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_link_not_a_path_skips_only_unusable() -> None:
    mod = _load()
    assert mod._link_not_a_path("") is True
    assert mod._link_not_a_path("x" * 201) is True
    assert mod._link_not_a_path("entities/skills`") is True
    assert mod._link_not_a_path("a\nb") is True
    assert mod._link_not_a_path("a\rb") is True
    assert mod._link_not_a_path("AI Gateway") is False
    assert mod._link_not_a_path("nas/lecture/LLM MultiAgent.pdf") is False
    assert mod._link_not_a_path("가" * 86) is True
    assert mod._link_not_a_path("가" * 85) is False


def test_space_links_are_still_checked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """공백 포함 정상 링크는 스킵되지 않고 exists() 까지 간다."""
    mod = _load()
    wiki = tmp_path / "wiki"
    (wiki / "entities").mkdir(parents=True)
    (wiki / "note.md").write_text(
        "[[AI Gateway]]\n[[nas/lecture/LLM MultiAgent.pdf]]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "WIKIHUB_HOME", tmp_path)
    monkeypatch.setattr(mod, "WIKI_ROOT", wiki)
    monkeypatch.setattr(Path, "exists", lambda self: False)

    violations = mod.step2_links({}, ["nas"])

    assert any("AI Gateway" in item["link"] for item in violations["dangling_short_entity"])
    assert any("LLM MultiAgent.pdf" in item["link"] for item in violations["dangling_full_path"])


def test_step2_oserror_skips_without_abort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """exists() 가 OSError 를 내도 예외로 죽지 않고, 그 링크를 위반으로 보고하지 않는다."""
    mod = _load()
    wiki = tmp_path / "wiki"
    (wiki / "entities").mkdir(parents=True)
    long_link = "n" * 201
    (wiki / "note.md").write_text(
        "[[AI Gateway]]\n"
        "[[nas/lecture/LLM MultiAgent.pdf]]\n"
        f"[[{long_link}]]\n"
        "[[has`tick]]\n",
        encoding="utf-8",
    )
    seen: list[str] = []

    def boom(self: Path) -> bool:
        seen.append(str(self))
        raise OSError("ENAMETOOLONG")

    monkeypatch.setattr(mod, "WIKIHUB_HOME", tmp_path)
    monkeypatch.setattr(mod, "WIKI_ROOT", wiki)
    monkeypatch.setattr(Path, "exists", boom)

    violations = mod.step2_links({}, ["nas"])

    assert violations["dangling_short_entity"] == []
    assert violations["dangling_full_path"] == []
    assert len(seen) >= 2
    assert all(long_link not in item for item in seen)
    assert all("has`tick" not in item for item in seen)


def test_step45_uses_sys_executable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    helper = tmp_path / "scripts" / "_helpers" / "detect_alias_duplicates.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("print('{}')\n", encoding="utf-8")
    captured: dict[str, list[str]] = {}

    def fake_run(args, **kwargs):
        captured["args"] = list(args)

        class Result:
            returncode = 0
            stdout = "{}"
            stderr = ""

        return Result()

    monkeypatch.setattr(mod, "SRC_DIR", tmp_path)
    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    assert mod.step45_duplicates() == {}
    assert captured["args"][0] == sys.executable
    assert captured["args"][1] == str(helper)
