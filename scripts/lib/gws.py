"""gws CLI subprocess wrapper (ADR-0014, F3 §2.2 B4 signature 정본).

gws 는 v0.1.0 alpha 의존성 — install.sh 가 pinned 버전 보장.
본 모듈은 subprocess 호출의 표준 진입점.

사용 예::

    # 텍스트 응답 (default)
    result = run_gws(['drive', 'changes', 'list'], params={'pageToken': cursor})

    # 바이너리 응답 (files.get alt=media)
    result = run_gws(['drive', 'files', 'get'], params={'fileId': fid, 'alt': 'media'},
                    binary_output=True)
    saved.write_bytes(result.stdout_bytes)

stdout 은 호출자가 처리:
- ``binary_output=False`` (default): ``stdout: str`` 채워짐, ``stdout_bytes: b""``
- ``binary_output=True``: ``stdout_bytes: bytes`` 채워짐, ``stdout: ""``
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field


@dataclass
class GwsResult:
    """gws 호출 결과 — raw stdout/stderr + 메타."""

    returncode: int
    stdout: str
    stderr: str
    duration_ms: int
    stdout_bytes: bytes = field(default=b"")


class GwsBinaryMissing(Exception):
    """gws CLI 미설치 — install.sh 재실행 안내."""


def run_gws(
    args: list[str],
    params: dict | None = None,
    *,
    timeout_sec: int = 300,
    env_extra: dict[str, str] | None = None,
    binary: str = "gws",
    binary_output: bool = False,
) -> GwsResult:
    """gws subprocess 호출.

    Args:
        args: gws 서브명령 list (예: ``['drive', 'changes', 'list']``).
        params: Drive API 파라미터 dict. ``--params '<json>'`` 으로 전달.
        timeout_sec: subprocess timeout. 초과 시 ``subprocess.TimeoutExpired`` raise.
        env_extra: 추가/덮어쓰기 환경변수. install.sh 가 systemd unit 으로 주입한 게 정본 경로.
        binary: gws 실행 파일명/경로. 테스트 시 mock binary 경로 사용.
        binary_output: True 면 stdout 을 bytes 로 캡처(``stdout_bytes``). False 면 UTF-8 decode 후 ``stdout`` 에 저장.
            바이너리 파일(``files.get alt=media``) 다운로드 시 반드시 True (CRIT-1 — F3 §V3 정합).

    Returns:
        GwsResult — returncode + raw stdout/stderr + duration_ms.
        binary_output=True 시 ``stdout_bytes`` 에 raw bytes, ``stdout`` 은 빈 문자열.

    Raises:
        GwsBinaryMissing: gws 가 PATH 에 없음.
        subprocess.TimeoutExpired: timeout 초과 (호출자가 catch → VaultSyncRetryable 매핑).
    """
    cmd = [binary, *args]
    if params is not None:
        cmd += ["--params", json.dumps(params)]

    env: dict[str, str] | None = None
    if env_extra:
        env = os.environ.copy()
        env.update(env_extra)

    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=not binary_output,
            timeout=timeout_sec,
            env=env,
            check=False,
            start_new_session=True,
        )
    except FileNotFoundError as e:
        raise GwsBinaryMissing(
            f"gws binary 미설치 ({binary}) — install.sh 재실행 필요."
        ) from e
    duration_ms = int((time.monotonic() - started) * 1000)

    if binary_output:
        # text=False 모드 — stdout/stderr 가 bytes
        stderr_text = proc.stderr.decode("utf-8", errors="replace") if isinstance(proc.stderr, bytes) else proc.stderr
        return GwsResult(
            returncode=proc.returncode,
            stdout="",
            stdout_bytes=proc.stdout if isinstance(proc.stdout, bytes) else proc.stdout.encode("utf-8"),
            stderr=stderr_text,
            duration_ms=duration_ms,
        )
    return GwsResult(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        duration_ms=duration_ms,
    )


__all__ = ["GwsResult", "GwsBinaryMissing", "run_gws"]
