"""lib/credentials.py file-level 검증 테스트."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from lib.credentials import assert_credentials, ensure_env_var
from lib.exceptions import VaultSyncFatal


def _write_token(path: Path, content: str, mode: int = 0o600) -> None:
    path.write_text(content)
    os.chmod(path, mode)


def test_missing_file_fatal(tmp_path: Path) -> None:
    with pytest.raises(VaultSyncFatal) as exc:
        assert_credentials("gdrive", tmp_path / "absent.json")
    assert "credentials file 없음" in exc.value.reason


def test_wrong_perm_fatal(tmp_path: Path) -> None:
    p = tmp_path / "t.json"
    _write_token(p, '{"type":"authorized_user","client_id":"a","client_secret":"b","refresh_token":"c"}',
                 mode=0o644)
    with pytest.raises(VaultSyncFatal) as exc:
        assert_credentials("gdrive", p)
    assert "권한 위반" in exc.value.reason


def test_bad_json_fatal(tmp_path: Path) -> None:
    p = tmp_path / "t.json"
    _write_token(p, "{not json}")
    with pytest.raises(VaultSyncFatal) as exc:
        assert_credentials("gdrive", p)
    assert "JSON 파싱 실패" in exc.value.reason


def test_wrong_type_fatal(tmp_path: Path) -> None:
    p = tmp_path / "t.json"
    _write_token(p, '{"type":"service_account"}')
    with pytest.raises(VaultSyncFatal) as exc:
        assert_credentials("gdrive", p)
    assert "authorized_user" in exc.value.reason


def test_missing_refresh_token_fatal(tmp_path: Path) -> None:
    p = tmp_path / "t.json"
    _write_token(p, '{"type":"authorized_user","client_id":"a","client_secret":"b"}')
    with pytest.raises(VaultSyncFatal) as exc:
        assert_credentials("gdrive", p)
    assert "필수 필드 누락" in exc.value.reason


def test_valid_credentials_ok(tmp_path: Path) -> None:
    p = tmp_path / "t.json"
    _write_token(
        p,
        '{"type":"authorized_user","client_id":"a","client_secret":"b","refresh_token":"c"}',
    )
    # 예외 없이 통과
    assert_credentials("gdrive", p)


def test_ensure_env_var_returns_dict(tmp_path: Path) -> None:
    p = tmp_path / "t.json"
    env = ensure_env_var(p)
    assert env["GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE"] == str(p)
