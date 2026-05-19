"""atomic JSON I/O for 4 state files (ADR-0007 all JSON, ADR-0035 cursor 폐기).

state 파일 종류:
- file_map.json (ADR-0035: primary key 가 source_id, Drive fileId)
- last_sync.json
- retry.json
- last_failure.json (ADR-0024)
- pending_ingest.json (F3 미작성 — F5/agent 책임)

ADR-0035: cursor.json 폐기. lsjson full snapshot diff 모델에서 cursor 의미 부재.

모든 쓰기는 tmpfile + os.replace 패턴 (atomic).
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _atomic_write_json(path: Path, obj: Any) -> None:
    """tmpfile + fsync + os.replace 패턴 (HIGH-R4-1).

    fsync 가 없으면 OCI 의 unexpected reboot 시 zero-length state 파일 발생 가능.
    `os.replace` 는 rename 만 atomic — tmpfile 내용 자체의 disk durability 는 fsync 가 보장.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def utc_now_iso() -> str:
    """현 시각 UTC ISO 8601 (F2 wiki-schema.md §시간·timezone 정책)."""
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# file_map.json (ADR-0035: primary key 가 source_id, Drive fileId)
# ---------------------------------------------------------------------------

def initial_file_map(vault_id: str) -> dict[str, Any]:
    return {"vault_id": vault_id, "updated_at": None, "files": {}}


def load_file_map(state_dir: Path) -> dict[str, Any]:
    path = state_dir / "file_map.json"
    if not path.exists():
        return {"vault_id": "", "updated_at": None, "files": {}}
    return _read_json(path)


def save_file_map(state_dir: Path, file_map: dict[str, Any]) -> None:
    file_map = dict(file_map)
    file_map["updated_at"] = utc_now_iso()
    _atomic_write_json(state_dir / "file_map.json", file_map)


# ---------------------------------------------------------------------------
# last_sync.json (F3 §2.5 Q2 정합 — vault-fetch.py 가 매 사이클 overwrite)
# ---------------------------------------------------------------------------

def save_last_sync(state_dir: Path, payload: dict[str, Any]) -> None:
    _atomic_write_json(state_dir / "last_sync.json", payload)


# ---------------------------------------------------------------------------
# retry.json (ADR-0007 정합)
# ---------------------------------------------------------------------------

def initial_retry(vault_id: str) -> dict[str, Any]:
    return {"vault_id": vault_id, "next_id": 1, "queue": []}


def load_retry(state_dir: Path) -> dict[str, Any]:
    path = state_dir / "retry.json"
    if not path.exists():
        return {"vault_id": "", "next_id": 1, "queue": []}
    return _read_json(path)


def save_retry(state_dir: Path, retry_obj: dict[str, Any]) -> None:
    _atomic_write_json(state_dir / "retry.json", retry_obj)


def enqueue_retry(retry_obj: dict[str, Any], *, source_relpath: str, source_id: str | None,
                  operation: str, failure_reason: str, next_retry_at: str) -> None:
    """retry queue 에 item 추가 + next_id 갱신 (단일 writer 가정으로 lock 불필요)."""
    item = {
        "id": retry_obj["next_id"],
        "source_relpath": source_relpath,
        "source_id": source_id,
        "operation": operation,
        "failure_reason": failure_reason,
        "attempts": 1,
        "next_retry_at": next_retry_at,
        "first_failed_at": utc_now_iso(),
        "last_failed_at": utc_now_iso(),
    }
    retry_obj["queue"].append(item)
    retry_obj["next_id"] = retry_obj["next_id"] + 1


# ---------------------------------------------------------------------------
# last_failure.json (ADR-0024 — fatal 알림 contract writer)
# ---------------------------------------------------------------------------

class _LastFailureLock:
    """``.last_failure.lock`` flock context manager — save_last_failure / mark_last_failure_alerted
    가 공유하는 단일 lock. R10 HIGH-3: vault-fetch 의 fatal write 와 ops-alert 의 alerted_at 갱신
    사이 lost-update race 차단.
    """

    def __init__(self, state_dir: Path) -> None:
        self._lock_path = state_dir / ".last_failure.lock"
        self._lock_fd = None

    def __enter__(self) -> "_LastFailureLock":
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_fd = open(self._lock_path, "w")
        fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self._lock_fd is not None:
                fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
        finally:
            if self._lock_fd is not None:
                self._lock_fd.close()
                self._lock_fd = None


def save_last_failure(state_dir: Path, payload: dict[str, Any]) -> None:
    """vault-level fatal 발생 시 영속화. ops-alert.service 의 input.

    연속 fatal 시:
    - ``first_failed_at`` 는 기존 값 보존 (최초 fatal 시각).
    - ``failed_count`` 는 +1.
    - ``alerted_at`` / ``alerted_failed_count`` 는 기존 값 보존
      (dedup 기준 — ops-alert.py 가 webhook 발송 시 갱신).

    R10 HIGH-3: ``.last_failure.lock`` 안에서 read-modify-write — ops-alert 의
    mark_last_failure_alerted 와 동일 lock 공유 → lost-update race 차단.

    Args:
        state_dir: vault state 디렉토리 (``_state/<vault_id>/``).
        payload: ADR-0024 schema 의 dict — vault_id/exit_code/severity/scope/reason/
            remediation/source_id/first_failed_at/last_failed_at/failed_count/alerted_at.
    """
    path = state_dir / "last_failure.json"
    with _LastFailureLock(state_dir):
        if path.exists():
            existing = _read_json(path)
            payload = dict(payload)  # mutate copy
            payload["first_failed_at"] = existing.get("first_failed_at", payload.get("first_failed_at"))
            payload["failed_count"] = int(existing.get("failed_count", 0)) + 1
            payload["alerted_at"] = existing.get("alerted_at")
            payload["alerted_failed_count"] = existing.get("alerted_failed_count")
        _atomic_write_json(path, payload)


def clear_last_failure(state_dir: Path) -> None:
    """success 1회 시 호출 — 연속 fatal 카운트 리셋. 다음 fatal 은 first 로 인식."""
    path = state_dir / "last_failure.json"
    path.unlink(missing_ok=True)


def read_last_failure(state_dir: Path) -> dict[str, Any] | None:
    """``last_failure.json`` 읽어 dict 반환. 파일 부재 시 ``None``.

    raises: OSError / json.JSONDecodeError — 호출자가 분류 (ops-alert 는 warn 후 skip).
    """
    path = state_dir / "last_failure.json"
    if not path.exists():
        return None
    return _read_json(path)


def mark_last_failure_alerted(state_dir: Path, alerted_at: str) -> None:
    """ops-alert.py 가 webhook 발송 성공 후 호출 — ``alerted_at`` + ``alerted_failed_count`` 갱신.

    R10 HIGH-3 lock: ``save_last_failure`` 와 동일 ``.last_failure.lock`` 공유로 lost-update 차단.
    R9 HIGH-4: ``alerted_failed_count`` 도 함께 기록 → 다음 fatal 의 needs_alert dedup 기준.
    """
    path = state_dir / "last_failure.json"
    if not path.exists():
        return
    with _LastFailureLock(state_dir):
        # lock 획득 후 다시 read — 그 사이 vault-fetch 가 갱신했을 수 있음
        if not path.exists():
            return
        payload = _read_json(path)
        payload["alerted_at"] = alerted_at
        payload["alerted_failed_count"] = int(payload.get("failed_count", 1))
        _atomic_write_json(path, payload)
