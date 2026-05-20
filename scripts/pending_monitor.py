#!/usr/bin/env python3
"""ADR-0037 §D2 — age-based alert trigger.

`wikihub-pending-monitor.timer` (30분 주기) 가 호출:
1. 각 enabled vault 의 ``$WIKIHUB_HOME/_state/<vault_id>/pending_ingest.json`` mtime age 검사
2. age > ``operations.pending_alert_age_sec`` (default 3600s = 1h) → 해당 vault 의
   ``last_failure.json`` 갱신 (scope="ingest_pending") + ops-alert.service 호출
3. ops-alert.py 의 dedup mechanism (alerted_failed_count + 24h reminder) 이 자연 적용

exit code 항상 0 — ops-alert 호출 실패 등 internal error 가 OnFailure 발화하면 본 monitor
가 자기 자신을 trigger 하는 loop 위험 회피 (ADR-0024 패턴 정합).
"""
from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

# scripts/ 디렉토리를 sys.path 에 추가
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.config import load_wikihub_yaml  # noqa: E402
from lib.state import (  # noqa: E402
    read_last_failure,
    save_last_failure,
    utc_now_iso,
)


log = logging.getLogger("pending-monitor")


def _setup_logging() -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def _check_vault_pending(
    state_dir: Path, vault_id: str, threshold_sec: int, now_ts: float
) -> bool:
    """vault 의 pending_ingest.json age 검사. threshold 위반 시 last_failure.json 갱신.

    Returns: alert trigger 했으면 True (ops-alert.service 호출 신호).
    """
    pending_file = state_dir / "pending_ingest.json"
    if not pending_file.exists():
        return False
    try:
        mtime = pending_file.stat().st_mtime
    except OSError as e:
        log.warning("pending_ingest stat 실패: %s — %s", pending_file, e)
        return False
    age_sec = int(now_ts - mtime)
    if age_sec <= threshold_sec:
        return False

    # last_failure.json 의 dedup mechanism 활용 — alerted_failed_count 가 없거나
    # 24h 경과 시 ops-alert 가 자연 재발송.
    existing = read_last_failure(state_dir)
    failed_count = (existing or {}).get("failed_count", 0) + 1 if existing else 1
    payload = {
        "vault_id": vault_id,
        "scope": "ingest_pending",
        "severity": "fatal",
        "reason": f"pending_ingest.json {age_sec}s old (threshold {threshold_sec}s) — ingest cycle 가 progress 안 함",
        "remediation": "journalctl --user -u wikihub-vault@%s.service --since '1h ago' 확인 + scripts/vault-fetch.py 수동 호출 진단" % vault_id,
        "first_failed_at": (existing or {}).get("first_failed_at") or utc_now_iso(),
        "last_failed_at": utc_now_iso(),
        "failed_count": failed_count,
    }
    save_last_failure(state_dir, payload)
    log.warning(
        "vault=%s pending age %ds > threshold %ds — last_failure.json 작성 (failed_count=%d)",
        vault_id, age_sec, threshold_sec, failed_count,
    )
    return True


def _trigger_ops_alert() -> None:
    """ops-alert.service 를 systemctl --user start 로 호출 (oneshot)."""
    try:
        subprocess.run(
            ["systemctl", "--user", "start", "ops-alert.service"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        log.info("ops-alert.service start 호출 완료")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        log.warning("ops-alert.service start 호출 실패: %s", e)


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    try:
        cfg = load_wikihub_yaml()
    except Exception as e:  # noqa: BLE001
        log.error("config load 실패: %s", e)
        return 0

    threshold_sec = cfg.operations.pending_alert_age_sec
    now_ts = time.time()
    triggered = False

    for vault_id, vault_cfg in cfg.vaults.items():
        if not vault_cfg.enabled:
            continue
        state_dir = cfg.instance_root / "_state" / vault_id
        if not state_dir.exists():
            continue
        if _check_vault_pending(state_dir, vault_id, threshold_sec, now_ts):
            triggered = True

    if triggered:
        _trigger_ops_alert()
    else:
        log.info("no pending age threshold violation (threshold=%ds)", threshold_sec)

    return 0  # exit 0 always — OnFailure recursion 회피


if __name__ == "__main__":
    raise SystemExit(main())
