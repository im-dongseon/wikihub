"""F1 §4.2.3 lift — vault sync 예외 클래스.

raise 사이트는 모두 vault_id를 keyword 인자로 전달해야 함 (F1 §4.6.6 notify 경로).
"""
from __future__ import annotations


class VaultSyncRetryable(Exception):
    """일시적 실패. 다음 sync 사이클에서 자동 재시도 가능."""

    def __init__(self, *, vault_id: str, retry_after_sec: int, reason: str) -> None:
        self.vault_id = vault_id
        self.retry_after_sec = retry_after_sec
        self.reason = reason
        super().__init__(f"[{vault_id}] retryable (retry_after={retry_after_sec}s): {reason}")


class VaultSyncFatal(Exception):
    """vault 전체 비복구 실패. 사람 개입 전까지 재시도 무의미.

    예: rclone OAuth 401 invalid_grant, rclone.conf 파손/누락 (ADR-0035).
    raise 시 sync 사이클은 *즉시 중단* — file_map 갱신 안 됨.

    ``scope`` 필드 (ADR-0024):
    - "vault" (default) — sync.py · vault-fetch.py 의 일반 vault-level fatal.
    - "mount" — mount.py 의 OAuth error · mount permanently failed.
    last_failure.json 의 ``scope`` 필드를 통해 ops-alert 가 fallback diagnostic
    경로 (mount 시 journalctl tail) 를 결정하므로 raise 사이트의 scope 정합 필수.
    """

    def __init__(self, *, vault_id: str, reason: str, remediation: str,
                 scope: str = "vault") -> None:
        self.vault_id = vault_id
        self.reason = reason
        self.remediation = remediation
        self.scope = scope
        super().__init__(f"[{vault_id}] fatal: {reason} | remediation: {remediation}")


class VaultSyncFileFatal(Exception):
    """단일 파일의 비복구 실패 — vault 전체는 계속 진행 (CRIT-R4-3).

    예: 한 파일의 403 insufficientPermissions, 파일별 corrupt content.
    sync 루프가 catch → retry queue 등록 + log + continue.
    vault 전체 stuck 회피.
    """

    def __init__(self, *, vault_id: str, source_id: str | None, reason: str) -> None:
        self.vault_id = vault_id
        self.source_id = source_id
        self.reason = reason
        super().__init__(f"[{vault_id}] file-fatal (source_id={source_id}): {reason}")
