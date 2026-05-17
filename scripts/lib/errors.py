"""gws exit code + stderr → wikihub exit code 분류 (F3 §2.3 B5 정본).

분류 결과:
- ``0``  = success
- ``75`` = Retryable (EX_TEMPFAIL — systemd Restart=on-failure 호환)
- ``2``  = Fatal

severity 와 별도로 ``scope`` 컬럼이 있다 (CRIT-R4-3 fix).
- ``vault``: vault 전체 영향 (예: 401, gws auth error) → ``VaultSyncFatal`` → 사이클 중단.
- ``file``: 단일 파일 (예: 403 insufficientPermissions) → ``VaultSyncFileFatal`` → 사이클 계속.

v0.1.0 starting regex 는 F3 §2.3 표 lift.
Step 3 V4 verification 에서 실제 gws stderr 샘플 관측 후 매핑 갱신 → ADR-0017 정본화.

미매치 패턴은 **Fatal + vault scope + raw stderr (첫 500자) 보존** (M1 정합 — 안전 default).
"""
from __future__ import annotations

import re
from typing import Literal


Severity = Literal["success", "retryable", "fatal"]
Scope = Literal["vault", "file"]

# F3 §2.3 default 매핑 — Step 3 V4 결과 따라 refine.
# (regex, severity, wikihub_exit, scope)
GWS_API_ERROR_PATTERNS: list[tuple[re.Pattern, Severity, int, Scope]] = [
    (
        re.compile(
            r"\b403\b.*(userRateLimitExceeded|rateLimitExceeded|quotaExceeded)",
            re.IGNORECASE | re.DOTALL,
        ),
        "retryable",
        75,
        "vault",  # quota 는 vault 전체 영향
    ),
    (
        re.compile(
            r"\b403\b.*(insufficientPermissions|forbidden)",
            re.IGNORECASE | re.DOTALL,
        ),
        "fatal",
        2,
        "file",  # 단일 파일 권한 — vault 전체 stuck 회피
    ),
    (re.compile(r"\b401\b"), "fatal", 2, "vault"),  # auth invalid
    (re.compile(r"\b5\d{2}\b"), "retryable", 75, "vault"),
    (re.compile(r"(timeout|connection|network|refused)", re.IGNORECASE), "retryable", 75, "vault"),
]


def classify_gws_error(returncode: int, stderr: str) -> tuple[int, Severity, str, Scope]:
    """gws subprocess 결과 → (wikihub_exit, severity, reason, scope).

    Args:
        returncode: gws exit code (0/1/2/3/4/5).
        stderr: gws stderr raw 문자열.

    Returns:
        ``(wikihub_exit_code, severity, reason, scope)``.
        - ``wikihub_exit_code``: 0 | 75 | 2.
        - ``severity``: 'success' | 'retryable' | 'fatal'.
        - ``reason``: 진단 메시지 (stderr 첫 500자 포함).
        - ``scope``: 'vault' | 'file' (호출자가 raise 분기에 사용).
    """
    if returncode == 0:
        return (0, "success", "", "vault")

    stderr_trim = (stderr or "").strip()
    stderr_500 = stderr_trim[:500]

    if returncode == 1:
        # API 에러 — stderr 패턴 매칭
        for pat, sev, exit_c, scope in GWS_API_ERROR_PATTERNS:
            if pat.search(stderr_trim):
                return (exit_c, sev, stderr_500, scope)
        # 미매치 → Fatal + vault scope (안전 default)
        return (2, "fatal", f"gws unrecognized stderr: {stderr_500}", "vault")

    # gws exit 2~5 — 모두 Fatal vault scope (subprocess 자체 결함)
    if returncode == 2:
        return (2, "fatal", f"gws auth error: {stderr_500}", "vault")
    if returncode == 3:
        return (2, "fatal", f"gws validation error (caller bug): {stderr_500}", "vault")
    if returncode == 4:
        return (2, "fatal", f"gws discovery error: {stderr_500}", "vault")
    if returncode == 5:
        return (2, "fatal", f"gws internal error: {stderr_500}", "vault")
    return (2, "fatal", f"gws unknown exit {returncode}: {stderr_500}", "vault")


__all__ = ["classify_gws_error", "GWS_API_ERROR_PATTERNS", "Severity", "Scope"]
