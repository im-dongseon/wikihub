"""fatal 통지 — Hermes 채널 stub (ADR-0024 의 v0.2.x 마이그레이션 경로).

v0.1.0 은 ``log.info`` 만 — Hermes 채널 활성화는 F5 (hermes_adapter) 의 책임.
ADR-0024 본문이 본 모듈의 stub 책임을 lock — 함수 시그니처는 v0.1.0 부터 고정.

운영 시점의 fatal 알림 정본은 ``ops-alert.service`` → ``ops-alert.py`` (Hermes-독립 webhook).
본 모듈은 그 외 fatal 인지 채널 (Hermes Telegram 등) 의 hook 지점.
"""
from __future__ import annotations

import logging

log = logging.getLogger("vault-fetch.notify")


def notify_via_hermes(vault_id: str, reason: str) -> None:
    """v0.1.0 stub — Hermes Telegram 통지를 모방 (실 활성화는 v0.2.x).

    Args:
        vault_id: 통지 대상 vault.
        reason: fatal 분류 (errors.py 의 classification 결과).
    """
    log.info("[STUB] notify_via_hermes: vault=%s reason=%s (v0.2.x activation pending)",
             vault_id, reason)


__all__ = ["notify_via_hermes"]
