#!/usr/bin/env python3
"""ADR-0024 reader — Hermes-독립 fatal 알림 dispatcher.

systemd ``OnFailure=ops-alert.service`` 가 trigger 한 시점에:
1. 모든 vault 의 ``_state/<vault_id>/last_failure.json`` 수집
2. dedup 정책 적용 (alerted_failed_count + 24h reminder)
3. ``operations.fatal_webhook_url`` POST (미설정 시 no-op + journal 로그만)
4. 발송 성공 시 ``alerted_at`` + ``alerted_failed_count`` 갱신 (file lock 보호)

exit code 항상 ``0`` — ops-alert 자체 실패는 silent (무한 OnFailure recursion 회피).
"""
from __future__ import annotations

import json
import logging
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

# scripts/ 디렉토리를 sys.path 에 추가
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.config import load_wikihub_yaml  # noqa: E402
from lib.state import (  # noqa: E402
    mark_last_failure_alerted,
    read_last_failure,
    utc_now_iso,
)


log = logging.getLogger("ops-alert")


def _setup_logging() -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def needs_alert(failure: dict[str, Any]) -> bool:
    """ADR-0024 dedup 정책 — alerted_failed_count + 24h reminder 기준 (R9 HIGH-4 fix).

    - alerted_at 없음 → first fatal 또는 발송 미완료 → 발송 시도
    - failed_count > alerted_failed_count → resurfacing → 발송
    - failed_count == alerted_failed_count → dedup hit (단 24h 경과 시 reminder)
    """
    alerted_at = _parse_iso(failure.get("alerted_at"))
    if alerted_at is None:
        return True

    alerted_count = failure.get("alerted_failed_count")
    current_count = int(failure.get("failed_count", 1))

    # alerted_failed_count 미설정 (구버전 schema) — 안전하게 발송
    if alerted_count is None:
        return True

    if current_count > int(alerted_count):
        # resurfacing — 운영자가 진단 안 한 상태에서 새 fatal 누적
        return True

    # dedup hit — 단 24h 경과 시 reminder
    last_failed_at = _parse_iso(failure.get("last_failed_at"))
    if last_failed_at is None:
        return False
    # clock skew 방어 — 음수면 dedup
    seconds_since_alert = (last_failed_at - alerted_at).total_seconds()
    if seconds_since_alert > 24 * 3600:
        return True
    return False


def collect_mount_fallback_failures(vault_ids: list[str]) -> list[dict[str, Any]]:
    """v9 (ADR-0024 minor) — mount@.service OnFailure 직접 trigger case 의 fallback diagnostic.

    case: mount@.service 가 StartLimitBurst=5/300s 초과로 permanently failed → OnFailure=ops-alert
    가 직접 trigger. 그러나 vault@.service 가 `Requires=` cancel 로 미실행이라 mount.py 도
    호출 안 됨 → last_failure.json (scope="mount") 가 비어있음. 본 함수가 mount@ 상태 query +
    journalctl tail 을 fallback_diagnostic 으로 수집.

    Args:
        vault_ids: yaml.vaults 의 vault_id list.

    Returns:
        mount@ 가 failed 상태인 vault 의 fallback payload list. failed 아니면 빈 list.
    """
    out: list[dict[str, Any]] = []
    for vault_id in vault_ids:
        is_failed = subprocess.run(
            ["systemctl", "--user", "is-failed", f"wikihub-mount@{vault_id}.service"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        # is-failed: failed 면 exit 0 + stdout "failed". active/inactive 등은 exit 1.
        if is_failed.returncode == 0 and "failed" in is_failed.stdout.strip():
            log_tail = subprocess.run(
                ["journalctl", "--user", "-u", f"wikihub-mount@{vault_id}.service",
                 "--since", "30min ago", "--no-pager", "-n", "100"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            diag = (
                log_tail.stdout[:5000] if log_tail.returncode == 0
                else f"journalctl 실패: {log_tail.stderr[:200]}"
            )
            out.append({
                "vault_id": vault_id,
                "severity": "fatal",
                "scope": "mount",
                "reason": f"mount@{vault_id}.service permanently failed (last_failure.json 부재 — fallback)",
                "remediation": (
                    f"systemctl --user reset-failed wikihub-mount@{vault_id}.service && "
                    f"systemctl --user restart wikihub-mount@{vault_id}.service"
                ),
                "first_failed_at": None,
                "last_failed_at": None,
                "failed_count": None,
                "fallback_diagnostic": diag,
            })
    return out


def collect_last_failures(instance_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    """``_state/<vault_id>/last_failure.json`` glob 수집.

    Returns: ``[(state_dir, failure_payload), ...]``.
    """
    state_root = instance_root / "_state"
    if not state_root.exists():
        return []
    out: list[tuple[Path, dict[str, Any]]] = []
    for state_dir in state_root.iterdir():
        if not state_dir.is_dir():
            continue
        try:
            payload = read_last_failure(state_dir)
        except (OSError, json.JSONDecodeError) as e:
            log.warning("last_failure 파싱 실패: %s — %s", state_dir, e)
            continue
        if payload is not None:
            out.append((state_dir, payload))
    return out


def post_webhook(url: str, payload: dict[str, Any], timeout_sec: int) -> bool:
    """webhook POST. 성공 시 True. 실패는 silent — exit 0 유지.

    R10 HIGH-1 fix: connect + read timeout 분리 — socket-level default 도 설정.
    """
    # connect timeout 도 함께 적용되도록 socket default 도 짧게 설정
    socket.setdefaulttimeout(timeout_sec)
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        log.warning("webhook POST 실패: %s — %s", url, e)
        return False
    finally:
        socket.setdefaulttimeout(None)


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    try:
        cfg = load_wikihub_yaml()
    except Exception as e:  # noqa: BLE001
        log.error("config load 실패: %s", e)
        return 0

    failures = collect_last_failures(cfg.instance_root)

    # v9 (ADR-0024 minor) — mount@.service OnFailure 직접 trigger case 의 fallback diagnostic
    mount_fallbacks: list[dict[str, Any]] = []
    if not failures:
        # last_failure.json 부재인데 ops-alert 가 trigger 됐다 → mount@ OnFailure 가능성
        mount_fallbacks = collect_mount_fallback_failures(list(cfg.vaults.keys()))

    if not failures and not mount_fallbacks:
        log.info("no last_failure to alert (mount@ status 도 normal)")
        return 0

    to_send = [(state_dir, f) for state_dir, f in failures if needs_alert(f)]
    if not to_send and not mount_fallbacks:
        log.info("dedup hit — %d failure(s) skipped", len(failures))
        return 0

    webhook_url = cfg.operations.fatal_webhook_url
    total_pending = len(to_send) + len(mount_fallbacks)
    if not webhook_url:
        # R10 HIGH-2: 운영자 visibility — webhook 미설정 + pending alert 가 있는 상태
        log.warning(
            "fatal_webhook_url 미설정 — %d 건의 fatal 알림이 journal 에만 기록됩니다 "
            "(운영자가 wikihub.yaml.operations.fatal_webhook_url 설정 권장)",
            total_pending,
        )
        for _, f in to_send:
            log.warning(
                "  vault=%s severity=%s reason=%s",
                f.get("vault_id"), f.get("severity"), f.get("reason"),
            )
        for f in mount_fallbacks:
            log.warning(
                "  [fallback] vault=%s scope=mount reason=%s",
                f.get("vault_id"), f.get("reason"),
            )
        return 0

    # R10 MED-3: instance_label 미설정 시 hostname fallback. webhook payload 가 외부 SaaS 면
    # OCI 의 internal hostname 노출 방지 — 운영자가 명시 alias 권장.
    instance_identifier = cfg.operations.instance_label or socket.gethostname()
    alerts: list[dict[str, Any]] = []
    for _, f in to_send:
        alerts.append({
            "vault_id": f.get("vault_id"),
            "severity": f.get("severity"),
            "scope": f.get("scope"),
            "reason": f.get("reason"),
            "remediation": f.get("remediation"),
            "first_failed_at": f.get("first_failed_at"),
            "last_failed_at": f.get("last_failed_at"),
            "failed_count": f.get("failed_count"),
        })
    # v9 (ADR-0024 minor) — mount@ OnFailure fallback case 도 같은 payload schema 에 첨부
    for f in mount_fallbacks:
        alerts.append({
            "vault_id": f.get("vault_id"),
            "severity": f.get("severity"),
            "scope": f.get("scope"),
            "reason": f.get("reason"),
            "remediation": f.get("remediation"),
            "first_failed_at": f.get("first_failed_at"),
            "last_failed_at": f.get("last_failed_at"),
            "failed_count": f.get("failed_count"),
            "fallback_diagnostic": f.get("fallback_diagnostic"),
        })
    payload = {
        "wikihub_instance": instance_identifier,
        "alerts": alerts,
    }
    ok = post_webhook(webhook_url, payload, cfg.operations.fatal_webhook_timeout_sec)
    if ok:
        now = utc_now_iso()
        for state_dir, _ in to_send:
            mark_last_failure_alerted(state_dir, now)
        log.info("webhook 발송 완료: %d failure(s)", len(to_send))
    else:
        # R10 HIGH-2: 발송 실패 visibility — stderr 에 명시 (systemd journal 로 운영자 보임)
        log.error(
            "webhook 발송 실패 — alerted_at 갱신 안 함 (다음 사이클 재시도). "
            "운영자 점검: webhook URL=%s, timeout=%ds",
            webhook_url, cfg.operations.fatal_webhook_timeout_sec,
        )

    return 0  # exit 0 always — OnFailure recursion 회피 (ADR-0024)


if __name__ == "__main__":
    raise SystemExit(main())
