"""lib/gws.py subprocess wrapper 테스트 — 외부 mock binary 사용."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from lib.gws import GwsBinaryMissing, run_gws


def _make_mock_binary(tmp_path: Path, *, exit_code: int = 0, stdout: str = "",
                      stderr: str = "") -> Path:
    """python script 가 stdout/stderr/exit_code 를 emit 하도록 mock binary 생성."""
    b = tmp_path / "mock-gws"
    b.write_text(
        f"""#!{sys.executable}
import sys
sys.stdout.write({stdout!r})
sys.stderr.write({stderr!r})
sys.exit({exit_code})
""",
        encoding="utf-8",
    )
    b.chmod(0o755)
    return b


def test_run_gws_success(tmp_path: Path) -> None:
    binary = _make_mock_binary(tmp_path, exit_code=0, stdout='{"ok":true}')
    result = run_gws(["drive", "about", "get"], None, binary=str(binary))
    assert result.returncode == 0
    assert "ok" in result.stdout
    assert result.duration_ms >= 0


def test_run_gws_with_params(tmp_path: Path) -> None:
    binary = _make_mock_binary(tmp_path, exit_code=0, stdout="x")
    result = run_gws(["drive", "files", "list"], {"pageSize": 10}, binary=str(binary))
    assert result.returncode == 0


def test_run_gws_nonzero(tmp_path: Path) -> None:
    binary = _make_mock_binary(tmp_path, exit_code=1, stderr="API error")
    result = run_gws(["drive", "files", "list"], None, binary=str(binary))
    assert result.returncode == 1
    assert "API error" in result.stderr


def test_run_gws_missing_binary() -> None:
    with pytest.raises(GwsBinaryMissing):
        run_gws(["drive", "files", "list"], None, binary="/nonexistent/gws-binary-xyz")


def test_run_gws_env_extra(tmp_path: Path) -> None:
    # env_extra 가 subprocess 환경에 들어가는지 — emit 으로 확인
    b = tmp_path / "mock-env"
    b.write_text(
        f"""#!{sys.executable}
import os, sys
sys.stdout.write(os.environ.get('WH_TEST', 'absent'))
sys.exit(0)
""",
        encoding="utf-8",
    )
    b.chmod(0o755)
    result = run_gws(["x"], None, binary=str(b), env_extra={"WH_TEST": "present"})
    assert result.stdout == "present"
