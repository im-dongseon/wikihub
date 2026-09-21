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
    text = """\
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


def test_agent_profile_default_none(tmp_path: Path) -> None:
    """profile 미지정 시 None (backward-compat)."""
    yp = _write(tmp_path / "wikihub.yaml", _minimum_yaml())
    cfg = load_wikihub_yaml(yp)
    assert cfg.agent.profile is None


def test_agent_profile_set(tmp_path: Path) -> None:
    """profile 지정 시 값 반영."""
    text = _minimum_yaml().replace(
        "  oneshot_args: [\"-z\"]",
        "  profile: wikihub\n  oneshot_args: [\"-z\"]",
    )
    yp = _write(tmp_path / "wikihub.yaml", text)
    cfg = load_wikihub_yaml(yp)
    assert cfg.agent.profile == "wikihub"


# ─── issue #185 — path 미지정 시 resolution chain ────────────────────────────
# 기존 테스트는 모두 명시 path 를 넘기므로 fallback 분기(path=None)는 미커버였다.
# `/opt/wikihub` 하드코딩 제거가 회귀하지 않도록 env 기반으로 검증한다.


def test_default_resolution_prefers_wikihub_yaml_env(tmp_path: Path, monkeypatch) -> None:
    """1순위 — WIKIHUB_YAML 이 최우선."""
    explicit = _write(tmp_path / "explicit.yaml", _minimum_yaml())
    other_home = tmp_path / "other-home"
    other_home.mkdir()
    _write(other_home / "wikihub.yaml", _minimum_yaml())

    monkeypatch.setenv("WIKIHUB_YAML", str(explicit))
    monkeypatch.setenv("WIKIHUB_HOME", str(other_home))

    cfg = load_wikihub_yaml()
    assert cfg.instance_root == Path("/opt/wikihub")


def test_default_resolution_falls_back_to_wikihub_home(tmp_path: Path, monkeypatch) -> None:
    """2순위 — WIKIHUB_YAML 부재 시 $WIKIHUB_HOME/wikihub.yaml."""
    home = tmp_path / "wh-home"
    home.mkdir()
    _write(home / "wikihub.yaml", _minimum_yaml())

    monkeypatch.delenv("WIKIHUB_YAML", raising=False)
    monkeypatch.setenv("WIKIHUB_HOME", str(home))

    cfg = load_wikihub_yaml()
    assert cfg.instance_root == Path("/opt/wikihub")


def test_default_resolution_no_opt_wikihub(tmp_path: Path, monkeypatch) -> None:
    """3순위 — env 전무 시 ~/wikihub/wikihub.yaml 을 시도한다 (`/opt/wikihub` 아님).

    issue #185 회귀 가드: resolution 경로에 `/opt/wikihub` 이 등장하면 실패한다.
    """
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()

    monkeypatch.delenv("WIKIHUB_YAML", raising=False)
    monkeypatch.delenv("WIKIHUB_HOME", raising=False)
    monkeypatch.setenv("HOME", str(fake_home))

    with pytest.raises(VaultSyncFatal) as e:
        load_wikihub_yaml()

    # 시도한 경로가 ~/wikihub/wikihub.yaml 이어야 하며 /opt/wikihub 이면 안 된다
    assert str(fake_home / "wikihub" / "wikihub.yaml") in e.value.reason
    assert "/opt/wikihub" not in e.value.reason
