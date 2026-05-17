"""lib/errors.py classification 테스트 (F3 §2.3 B5).

CRIT-R4-3 fix 이후 classify_gws_error 는 4-tuple (exit_c, severity, reason, scope) 반환.
"""
from __future__ import annotations

from lib.errors import classify_gws_error


def test_returncode_0_success() -> None:
    exit_c, sev, reason, scope = classify_gws_error(0, "")
    assert exit_c == 0
    assert sev == "success"
    assert reason == ""
    assert scope == "vault"


def test_403_quota_retryable() -> None:
    stderr = "API error: 403 userRateLimitExceeded — quota exceeded for user"
    exit_c, sev, reason, scope = classify_gws_error(1, stderr)
    assert exit_c == 75
    assert sev == "retryable"
    assert "userRateLimitExceeded" in reason
    assert scope == "vault"  # quota 는 vault 전체 영향


def test_403_forbidden_file_scope_fatal() -> None:
    """CRIT-R4-3: 403 insufficientPermissions 는 scope=file — vault stuck 회피."""
    stderr = "API error: 403 insufficientPermissions"
    exit_c, sev, _, scope = classify_gws_error(1, stderr)
    assert exit_c == 2
    assert sev == "fatal"
    assert scope == "file"


def test_401_vault_scope_fatal() -> None:
    stderr = "API error: 401 Unauthorized"
    exit_c, sev, _, scope = classify_gws_error(1, stderr)
    assert exit_c == 2
    assert sev == "fatal"
    assert scope == "vault"


def test_5xx_retryable() -> None:
    stderr = "API error: 503 Service Unavailable"
    exit_c, sev, _, scope = classify_gws_error(1, stderr)
    assert exit_c == 75
    assert sev == "retryable"
    assert scope == "vault"


def test_network_timeout_retryable() -> None:
    stderr = "connection timeout to googleapis.com"
    exit_c, sev, _, scope = classify_gws_error(1, stderr)
    assert exit_c == 75
    assert sev == "retryable"
    assert scope == "vault"


def test_unrecognized_stderr_fatal_with_raw() -> None:
    # M1 정합 — 미매치 시 Fatal + vault scope (안전 default) + raw stderr 보존
    stderr = "something completely new and unrecognized 1234 xyz"
    exit_c, sev, reason, scope = classify_gws_error(1, stderr)
    assert exit_c == 2
    assert sev == "fatal"
    assert "completely new" in reason
    assert scope == "vault"


def test_returncode_2_fatal() -> None:
    exit_c, sev, _, scope = classify_gws_error(2, "auth failed")
    assert (exit_c, sev, scope) == (2, "fatal", "vault")


def test_returncode_3_fatal() -> None:
    exit_c, sev, _, scope = classify_gws_error(3, "validation error")
    assert (exit_c, sev, scope) == (2, "fatal", "vault")


def test_returncode_unknown_fatal() -> None:
    exit_c, sev, _, scope = classify_gws_error(99, "weird")
    assert (exit_c, sev, scope) == (2, "fatal", "vault")


def test_stderr_truncated_to_500() -> None:
    stderr = "X" * 1000
    _, _, reason, _ = classify_gws_error(1, stderr)
    # raw stderr 첫 500자 보존 + prefix 부분 합쳐 약 500~ 미만
    assert len(reason) <= 600
