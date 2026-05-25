"""Telegram bot 발송 공용 helper — ADR-0037 §D1.

env: ``TELEGRAM_MONITOR_BOT_TOKEN`` + ``TELEGRAM_MONITOR_CHAT_ID``

caller:
- ``ops-alert.py`` — ``parse_mode="HTML"`` (fatal alert, HTML 태그 사용)
- ``wikihub_monitor.py`` — ``parse_mode=None`` (정적 보고서, plain text)

ADR-0037 §"후속 영향" 2026-05-25: ``wikihub_monitor`` (v0.1.8) 추가 → ops-alert.py 의
``send_telegram`` / ``format_telegram_alert_message`` 함수를 본 모듈로 추출 +
``parse_mode`` 옵션화.
"""
from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger("lib.telegram")


def send_telegram(
    bot_token: str,
    chat_id: str,
    text: str,
    parse_mode: str | None = None,
    timeout_sec: int = 10,
) -> bool:
    """Telegram bot 으로 message 전송. 성공 시 True.

    parse_mode=None  → plain text (Telegram 이 escape 처리 없이 그대로 표시)
    parse_mode="HTML" → caller 가 ``<`` ``>`` ``&`` escape 책임
    parse_mode="MarkdownV2" → caller 가 special chars escape 책임
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    data = json.dumps(payload).encode("utf-8")
    socket.setdefaulttimeout(timeout_sec)
    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        log.warning("telegram 전송 실패: %s", e)
        return False
    finally:
        socket.setdefaulttimeout(None)


def format_telegram_alert_message(instance: str, alerts: list[dict[str, Any]]) -> str:
    """ops-alert 의 fatal alert 목록을 Telegram HTML 메시지로 변환 (ADR-0037 §D1).

    caller 는 ``parse_mode="HTML"`` 로 send_telegram 호출.
    """
    lines = ["🚨 <b>Wikihub Alert</b>", f"Instance: {instance}", ""]
    for a in alerts:
        lines.append(f"• <b>{a.get('vault_id', 'unknown')}</b>")
        lines.append(f"  Scope: {a.get('scope', 'unknown')}")
        lines.append(f"  Severity: {a.get('severity', 'unknown')}")
        reason = str(a.get("reason", "unknown"))
        lines.append(f"  Reason: {reason[:200]}")
        if a.get("failed_count"):
            lines.append(f"  Failed count: {a['failed_count']}")
        lines.append("")
    return "\n".join(lines)
