"""lib/config.py wikihub.yaml load + 스키마 검증 테스트."""
from __future__ import annotations

from pathlib import Path

import pytest

from lib.config import load_wikihub_yaml
from lib.exceptions import VaultSyncFatal


def _write(p: Path, text: str) -> Path:
    p.write_text(text, encoding="utf-8")
    return p


def _minimum_yaml() -> str:
    return """
version: 1
instance:
  root: /opt/wikihub
  timezone: Asia/Seoul
vaults:
  - id: gdrive
    type: gdrive_api
    enabled: true
    sync_interval_sec: 600
    local_path: /opt/vault-gdrive
    options:
      credentials_path: /opt/wikihub/.credentials/token_gdrive.json
agent:
  type: hermes
  binary: /usr/local/bin/hermes
  oneshot_args: ["-z"]
operations:
  lint_interval_hours: 3
""".strip()


def test_load_ok(tmp_path: Path) -> None:
    yp = _write(tmp_path / "wikihub.yaml", _minimum_yaml())
    cfg = load_wikihub_yaml(yp)
    assert cfg.instance_root == Path("/opt/wikihub")
    assert "gdrive" in cfg.vaults
    assert cfg.vaults["gdrive"].sync_interval_sec == 600
    assert cfg.agent.binary == "/usr/local/bin/hermes"
    assert cfg.agent.skill_prefix == "wh:"
    assert cfg.operations.lint_interval_hours == 3


def test_missing_file_fatal(tmp_path: Path) -> None:
    with pytest.raises(VaultSyncFatal) as e:
        load_wikihub_yaml(tmp_path / "absent.yaml")
    assert "없음" in e.value.reason


def test_bad_version_fatal(tmp_path: Path) -> None:
    yp = _write(tmp_path / "wikihub.yaml", _minimum_yaml().replace("version: 1", "version: 2"))
    with pytest.raises(VaultSyncFatal) as e:
        load_wikihub_yaml(yp)
    assert "version" in e.value.reason


def test_bad_vault_id_fatal(tmp_path: Path) -> None:
    yp = _write(tmp_path / "wikihub.yaml", _minimum_yaml().replace("id: gdrive", "id: GDrive"))
    with pytest.raises(VaultSyncFatal) as e:
        load_wikihub_yaml(yp)
    assert "vault id" in e.value.reason


def test_unsupported_type_fatal(tmp_path: Path) -> None:
    yp = _write(tmp_path / "wikihub.yaml", _minimum_yaml().replace("type: gdrive_api", "type: dropbox"))
    with pytest.raises(VaultSyncFatal) as e:
        load_wikihub_yaml(yp)
    assert "vault type" in e.value.reason


def test_low_interval_fatal(tmp_path: Path) -> None:
    yp = _write(
        tmp_path / "wikihub.yaml",
        _minimum_yaml().replace("sync_interval_sec: 600", "sync_interval_sec: 30"),
    )
    with pytest.raises(VaultSyncFatal) as e:
        load_wikihub_yaml(yp)
    assert "60" in e.value.reason


def test_mount_path_warn_on_mismatch(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """mount_path != local_path 시 WARNING 로그 발화 + VaultSyncFatal 미발생."""
    yp = _write(
        tmp_path / "wikihub.yaml",
        _minimum_yaml().replace(
            "    options:",
            "    options:\n      mount_path: /custom/mount",
        ),
    )
    cfg = load_wikihub_yaml(yp)
    assert "gdrive" in cfg.vaults
    assert any("mount_path" in record.message for record in caplog.records)
    assert any(record.levelname == "WARNING" for record in caplog.records)


def test_mount_path_no_warn_on_default(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """mount_path 미설정 시 WARNING 로그 미발화."""
    yp = _write(tmp_path / "wikihub.yaml", _minimum_yaml())
    cfg = load_wikihub_yaml(yp)
    assert "gdrive" in cfg.vaults
    mount_warnings = [
        r for r in caplog.records if "mount_path" in r.message and r.levelname == "WARNING"
    ]
    assert len(mount_warnings) == 0


def test_mount_path_no_warn_on_equal(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """mount_path == local_path 시 WARNING 로그 미발화."""
    yp = _write(
        tmp_path / "wikihub.yaml",
        _minimum_yaml().replace(
            "    options:",
            "    options:\n      mount_path: /opt/vault-gdrive",
        ),
    )
    cfg = load_wikihub_yaml(yp)
    assert "gdrive" in cfg.vaults
    mount_warnings = [
        r for r in caplog.records if "mount_path" in r.message and r.levelname == "WARNING"
    ]
    assert len(mount_warnings) == 0


def test_duplicate_vault_id_fatal(tmp_path: Path) -> None:
    text = """
version: 1
instance:
  root: /opt/wikihub
vaults:
  - id: gdrive
    type: gdrive_api
    enabled: true
    sync_interval_sec: 600
    local_path: /opt/vault-gdrive
  - id: gdrive
    type: gdrive_api
    enabled: true
    sync_interval_sec: 600
    local_path: /opt/vault-gdrive-dup
agent:
  type: hermes
  binary: /usr/local/bin/hermes
""".strip()
    yp = _write(tmp_path / "wikihub.yaml", text)
    with pytest.raises(VaultSyncFatal) as e:
        load_wikihub_yaml(yp)
    assert "중복" in e.value.reason
