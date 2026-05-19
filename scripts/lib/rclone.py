"""rclone CLI subprocess wrapper (ADR-0035).

rclone 은 ADR-0025 의 mount + ADR-0035 의 변경 감지(lsjson) 둘 다 책임.
본 모듈은 lsjson 호출의 표준 진입점 — mount 는 systemd unit 이 별도 daemon 으로 운영.

사용 예::

    listing = lsjson("gdrive", recursive=True)
    # listing: list[dict] — 각 항목에 Path/Name/Size/MimeType/ModTime/IsDir/ID
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Any

from .exceptions import VaultSyncFatal, VaultSyncRetryable

log = logging.getLogger("rclone")


@dataclass
class RcloneResult:
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int


class RcloneBinaryMissing(Exception):
    """rclone CLI 미설치 — install.sh 재실행 안내."""


# stderr 패턴 매칭 — OAuth revoke / quota / network 분류.
# v0.1.0 시작 매핑. 운영 중 추가 패턴 surface 시 보강.
_RCLONE_AUTH_PATTERNS = (
    "oauth2: token expired",
    "invalid_grant",
    "invalid_credentials",
    "couldn't fetch token",
    "401 Unauthorized",
)
_RCLONE_QUOTA_PATTERNS = (
    "userRateLimitExceeded",
    "rateLimitExceeded",
    "quotaExceeded",
    "403 Forbidden: userRateLimit",
)
_RCLONE_NETWORK_PATTERNS = (
    "connection refused",
    "no such host",
    "timeout awaiting",
    "i/o timeout",
    "TLS handshake timeout",
)


def run_rclone(
    args: list[str],
    *,
    timeout_sec: int = 300,
    env_extra: dict[str, str] | None = None,
    binary: str = "rclone",
) -> RcloneResult:
    """rclone subprocess 호출.

    Args:
        args: rclone 서브명령 list (예: ``['lsjson', 'gdrive:', '--recursive']``).
        timeout_sec: subprocess timeout. 초과 시 ``subprocess.TimeoutExpired`` raise.
        env_extra: 추가/덮어쓰기 환경변수. systemd unit 의 ``RCLONE_CONFIG`` 가 정본.
        binary: rclone 실행 파일명/경로.

    Raises:
        RcloneBinaryMissing: rclone PATH 부재.
        subprocess.TimeoutExpired: timeout (호출자가 catch → VaultSyncRetryable 매핑).
    """
    cmd = [binary, *args]
    env: dict[str, str] | None = None
    if env_extra:
        env = os.environ.copy()
        env.update(env_extra)

    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=env,
            check=False,
            start_new_session=True,
        )
    except FileNotFoundError as e:
        raise RcloneBinaryMissing(
            f"rclone binary 미설치 ({binary}) — install.sh 재실행 필요."
        ) from e
    duration_ms = int((time.monotonic() - started) * 1000)
    return RcloneResult(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        duration_ms=duration_ms,
    )


def classify_rclone_error(returncode: int, stderr: str, *, vault_id: str) -> Exception:
    """rclone 호출 실패 → wikihub 예외로 분류.

    매핑:
    - OAuth revoke / 401 → VaultSyncFatal (vault scope)
    - quota / rate limit → VaultSyncRetryable
    - network / timeout → VaultSyncRetryable
    - 그 외 → VaultSyncFatal (vault scope, 안전 default)
    """
    stderr_trim = (stderr or "").strip()
    stderr_500 = stderr_trim[:500]
    lower = stderr_trim.lower()

    if any(p.lower() in lower for p in _RCLONE_AUTH_PATTERNS):
        return VaultSyncFatal(
            vault_id=vault_id,
            reason=f"rclone OAuth invalid/expired: {stderr_500}",
            remediation="setup.md §Step 5.5 — `rclone authorize drive` 재발급 + rclone.conf 갱신.",
        )
    if any(p.lower() in lower for p in _RCLONE_QUOTA_PATTERNS):
        return VaultSyncRetryable(
            vault_id=vault_id,
            retry_after_sec=120,
            reason=f"rclone quota: {stderr_500}",
        )
    if any(p.lower() in lower for p in _RCLONE_NETWORK_PATTERNS):
        return VaultSyncRetryable(
            vault_id=vault_id,
            retry_after_sec=60,
            reason=f"rclone network: {stderr_500}",
        )
    return VaultSyncFatal(
        vault_id=vault_id,
        reason=f"rclone exit {returncode}: {stderr_500}",
        remediation="rclone stderr 확인 후 setup.md §Step 5.5 또는 install.sh 재실행.",
    )


def lsjson(
    remote: str,
    *,
    path: str = "",
    recursive: bool = True,
    timeout_sec: int = 300,
    vault_id: str | None = None,
    binary: str = "rclone",
    env_extra: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """``rclone lsjson <remote>:<path>`` 호출 → listing list 반환.

    각 항목 schema (rclone v1.69.1 기준):
        ``{Path, Name, Size, MimeType, ModTime, IsDir, ID}``

    Args:
        remote: rclone remote 이름 (예: ``"gdrive"``). 함수가 ``:`` 자동 부착.
        path: remote 내 sub-path (예: ``"wikihub"``). 빈 문자열이면 remote 루트 (``<remote>:``).
            mount source path 와 동일해야 mount/lsjson scope 정합 (ADR-0035 §Note 2026-05-19).
        recursive: ``--recursive`` 플래그 (default True).
        timeout_sec: subprocess timeout.
        vault_id: 에러 매핑 시 VaultSync* 예외에 채울 vault_id. None 이면 ``remote`` 사용.
        binary: rclone 실행 파일명/경로.
        env_extra: 추가 환경변수 (예: 테스트의 ``RCLONE_CONFIG`` override).

    Raises:
        VaultSyncFatal · VaultSyncRetryable · RcloneBinaryMissing.
    """
    vid = vault_id or remote
    spec = f"{remote}:{path}" if path else f"{remote}:"
    args = ["lsjson", spec]
    if recursive:
        args.append("--recursive")

    try:
        result = run_rclone(args, timeout_sec=timeout_sec, binary=binary, env_extra=env_extra)
    except subprocess.TimeoutExpired as e:
        raise VaultSyncRetryable(
            vault_id=vid,
            retry_after_sec=60,
            reason=f"rclone lsjson timeout after {e.timeout}s: remote={remote}",
        ) from e
    except RcloneBinaryMissing as e:
        raise VaultSyncFatal(
            vault_id=vid,
            reason=str(e),
            remediation="install.sh 재실행 또는 rclone binary 설치.",
        ) from e

    if result.returncode != 0:
        raise classify_rclone_error(result.returncode, result.stderr, vault_id=vid)

    try:
        data = json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError as e:
        raise VaultSyncFatal(
            vault_id=vid,
            reason=f"rclone lsjson stdout JSON 파싱 실패: {e}; stdout 첫 500자: {result.stdout[:500]!r}",
            remediation="rclone --version 확인 후 install.sh 재실행 — rclone v1.65+ 권장.",
        ) from e
    if not isinstance(data, list):
        raise VaultSyncFatal(
            vault_id=vid,
            reason=f"rclone lsjson 출력이 list 아님: type={type(data).__name__}",
            remediation="rclone v1.65+ 권장 — schema 호환성 확인.",
        )
    log.info("rclone lsjson: remote=%s path=%s items=%d duration_ms=%d",
             remote, path or "", len(data), result.duration_ms)
    return data


__all__ = [
    "RcloneResult",
    "RcloneBinaryMissing",
    "run_rclone",
    "classify_rclone_error",
    "lsjson",
]
