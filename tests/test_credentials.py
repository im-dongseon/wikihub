"""lib/credentials.py rclone.conf 검증 테스트 (ADR-0035)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from lib.credentials import assert_rclone_config
from lib.exceptions import VaultSyncFatal


def _write_conf(path: Path, content: str, mode: int = 0o600) -> None:
    path.write_text(content)
    os.chmod(path, mode)


def test_missing_rclone_conf_fatal(tmp_path: Path) -> None:
    with pytest.raises(VaultSyncFatal) as exc:
        assert_rclone_config("gdrive", "gdrive", config_path=tmp_path / "absent.conf")
    assert "rclone.conf 없음" in exc.value.reason


def test_wrong_perm_fatal(tmp_path: Path) -> None:
    p = tmp_path / "rclone.conf"
    _write_conf(p, "[gdrive]\ntype = drive\ntoken = {}\n", mode=0o644)
    with pytest.raises(VaultSyncFatal) as exc:
        assert_rclone_config("gdrive", "gdrive", config_path=p)
    assert "권한 위반" in exc.value.reason


def test_missing_remote_section_fatal(tmp_path: Path) -> None:
    p = tmp_path / "rclone.conf"
    _write_conf(p, "[other_remote]\ntype = drive\ntoken = {}\n")
    with pytest.raises(VaultSyncFatal) as exc:
        assert_rclone_config("gdrive", "gdrive", config_path=p)
    assert "미등록" in exc.value.reason


def test_valid_rclone_conf_ok(tmp_path: Path) -> None:
    p = tmp_path / "rclone.conf"
    _write_conf(p, "[gdrive]\ntype = drive\ntoken = {\"access_token\":\"x\"}\n")
    # 예외 없이 통과
    assert_rclone_config("gdrive", "gdrive", config_path=p)


def test_rclone_conf_default_path_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``RCLONE_CONFIG`` env 가 없으면 ``~/.config/rclone/rclone.conf`` default 사용."""
    p = tmp_path / "rclone.conf"
    _write_conf(p, "[gdrive]\ntype = drive\ntoken = {}\n")
    monkeypatch.setenv("RCLONE_CONFIG", str(p))
    # config_path=None — env 사용
    assert_rclone_config("gdrive", "gdrive", config_path=None)
