"""rclone.conf 파일 검증 — ADR-0035 정본 (gws SA 검증 폐기, rclone OAuth 단독).

ADR-0035: rclone.conf 가 단일 인증 자료. SA JSON · OAuth credentials 별도 검증 폐기.
install.sh `_enforce_rclone_conf_perms` 가 자동 chmod 0600 — 본 모듈은 vault-fetch.py
가 사이클 시작 시 추가 검증 (운영자가 setup.md 미수행한 경우 fail-fast).
"""
from __future__ import annotations

import os
from pathlib import Path

from .exceptions import VaultSyncFatal


def assert_rclone_config(
    vault_id: str,
    remote_name: str,
    config_path: Path | None = None,
) -> None:
    """rclone.conf 파일 존재 + 권한 (0600) + remote_name 등록 검증.

    Args:
        vault_id: VaultSyncFatal 의 vault_id 필드.
        remote_name: ``wikihub.yaml.vaults[*].options.rclone_remote_name`` 값.
            rclone.conf 의 ``[<remote_name>]`` 섹션 등록 여부 확인.
        config_path: rclone.conf 경로. None 이면 환경변수 ``RCLONE_CONFIG`` 또는
            ``~/.config/rclone/rclone.conf`` default.

    Raises:
        VaultSyncFatal: 파일 부재 / 권한 위반 / remote_name 미등록.
    """
    if config_path is None:
        env = os.environ.get("RCLONE_CONFIG")
        config_path = Path(env) if env else Path("~/.config/rclone/rclone.conf").expanduser()
    if not config_path.exists():
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=f"rclone.conf 없음: {config_path}",
            remediation="setup.md §Step 5.5 (rclone OAuth 발급) 수행 후 install.sh 재실행",
        )
    mode = config_path.stat().st_mode & 0o777
    if mode != 0o600:
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=f"rclone.conf 권한 위반: {oct(mode)} (요구: 0o600 — token 평문 저장)",
            remediation=f"chmod 0600 {config_path}",
        )
    content = config_path.read_text(encoding="utf-8")
    if f"[{remote_name}]" not in content:
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=f"rclone.conf 에 remote '{remote_name}' 미등록 — yaml.vaults[*].options.rclone_remote_name 정합",
            remediation=f"`rclone config` 실행 + remote name='{remote_name}' 등록 (setup.md Step 5.5 참조)",
        )


__all__ = ["assert_rclone_config"]
