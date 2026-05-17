"""Service Account credentials file 검증 (file 존재 + 권한 600).

ADR-0029 (ADR-0003 supersede) 정본: credentials 는 SA JSON key file.
gws 는 ``GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`` env 로, rclone 은 rclone.conf 의
``service_account_file`` 로 동일 SA JSON 참조. 본 모듈은 file-level 검증만.

setup.md §Step 1 의 SA light call(``gws drive about get``)은 본 모듈 범위 밖
— ``/wh:setup`` 구현(F4) 책임 (F3 §2.4 M3 정합).
"""
from __future__ import annotations

import json
from pathlib import Path

from .exceptions import VaultSyncFatal


def assert_credentials(vault_id: str, path: Path) -> None:
    """credentials JSON 의 file-level 정합성만 검증.

    검증 항목:
    - 존재 여부
    - 권한 600 (umask 0o077 — owner-only read/write)
    - JSON 파싱 가능 + ``type: service_account`` 형식 확인 (ADR-0029)
    - 필수 필드: ``private_key``, ``client_email`` (Google Cloud SA JSON 표준)
    """
    if not path.exists():
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=f"credentials file 없음: {path}",
            remediation="Google Cloud Console 에서 SA JSON key 발급 + scp 로 서버 배치 (ADR-0029).",
        )
    mode = path.stat().st_mode & 0o777
    if mode != 0o600:
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=f"credentials file 권한 위반: {oct(mode)} (요구: 0o600)",
            remediation=f"chmod 600 {path}",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=f"credentials JSON 파싱 실패: {e}",
            remediation="SA JSON key 재발급 후 scp 재전송 (Cloud Console IAM > Service Accounts).",
        ) from e
    if not isinstance(data, dict) or data.get("type") != "service_account":
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason="credentials JSON 의 type 이 'service_account' 가 아님 (ADR-0029)",
            remediation="Google Cloud Console 에서 SA JSON key 재발급 (OAuth user JSON 은 ADR-0003 supersede 로 미지원).",
        )
    required = ("private_key", "client_email")
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=f"SA credentials JSON 필수 필드 누락: {missing}",
            remediation="SA JSON key 재발급 — Cloud Console 의 raw download 형식 확인.",
        )


def ensure_env_var(path: Path) -> dict[str, str]:
    """gws 가 사용할 환경변수 dict 반환.

    install.sh 가 systemd unit 의 Environment 로 주입하는 게 정본 경로지만,
    dev box 수동 호출 또는 명시적 override 시 본 함수로 dict 구성 후 ``lib/gws.py:run_gws`` 의 ``env_extra`` 로 전달.
    """
    return {"GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE": str(path)}


def assert_rclone_config(vault_id: str, remote_name: str, config_path: Path | None = None) -> None:
    """rclone.conf 파일 존재 + 권한 (0600) + remote_name 등록 검증 (v9 ADR-0025).

    install.sh `_enforce_rclone_conf_perms` 가 자동 chmod 0600 — 본 함수는 vault-fetch.py
    가 사이클 시작 시 추가 검증 (운영자가 setup.md 미수행한 경우 fail-fast).

    Args:
        vault_id: VaultSyncFatal 의 vault_id 필드.
        remote_name: ``wikihub.yaml.vaults[*].options.rclone_remote_name`` 값.
            rclone.conf 의 `[<remote_name>]` 섹션 등록 여부 확인.
        config_path: rclone.conf 경로. None 이면 환경변수 ``RCLONE_CONFIG`` 또는
            ``~/.config/rclone/rclone.conf`` default.

    Raises:
        VaultSyncFatal: 파일 부재 / 권한 위반 / remote_name 미등록.
    """
    import os
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
    # remote_name 섹션 등록 확인 — `[<remote_name>]` literal grep
    content = config_path.read_text(encoding="utf-8")
    if f"[{remote_name}]" not in content:
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=f"rclone.conf 에 remote '{remote_name}' 미등록 — yaml.vaults[*].options.rclone_remote_name 정합",
            remediation=f"`rclone config` 실행 + remote name='{remote_name}' 등록 (setup.md Step 5.5 참조)",
        )


__all__ = ["assert_credentials", "ensure_env_var", "assert_rclone_config"]
