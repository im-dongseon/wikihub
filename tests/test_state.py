"""lib/state.py atomic JSON I/O 테스트."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib import state


def test_atomic_write_creates_dir(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "cursor.json"
    state._atomic_write_json(target, {"vault_id": "gdrive", "cursor": "abc"})
    assert target.exists()
    assert json.loads(target.read_text()) == {"vault_id": "gdrive", "cursor": "abc"}


def test_atomic_write_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "x.json"
    state._atomic_write_json(target, {"v": 1})
    state._atomic_write_json(target, {"v": 2})
    assert json.loads(target.read_text()) == {"v": 2}


def test_atomic_write_cleans_tmp_on_failure(tmp_path: Path) -> None:
    # 객체에 직렬화 불가능한 set 포함 → TypeError 시 tmpfile 정리됨
    target = tmp_path / "broken.json"
    with pytest.raises(TypeError):
        state._atomic_write_json(target, {"bad": {1, 2, 3}})
    assert not target.exists()
    # tmp file 도 남지 않아야
    tmps = list(tmp_path.glob(".*.tmp"))
    assert tmps == []


# ADR-0035: cursor 함수 (initial_cursor/load_cursor/save_cursor/has_cursor) 폐기 — 관련 테스트 제거.


def test_file_map_roundtrip(tmp_path: Path) -> None:
    """ADR-0035: file_map primary key 가 source_id (Drive fileId)."""
    fm = state.initial_file_map("gdrive")
    fm["files"]["id1"] = {
        "source_relpath": "a.md",
        "source_mtime": "2026-05-19T00:00:00Z",
        "wiki_path": "wiki/sources/gdrive/a.md",
        "bytes": 100,
        "last_synced_at": "2026-05-19T00:00:00Z",
    }
    state.save_file_map(tmp_path, fm)
    loaded = state.load_file_map(tmp_path)
    assert loaded["files"]["id1"]["source_relpath"] == "a.md"
    assert loaded["updated_at"] is not None


def test_retry_enqueue(tmp_path: Path) -> None:
    rq = state.initial_retry("gdrive")
    state.enqueue_retry(
        rq,
        source_relpath="a.md",
        source_id="id1",
        operation="modified",
        failure_reason="403",
        next_retry_at="2026-05-13T01:00:00+00:00",
    )
    assert rq["next_id"] == 2
    assert rq["queue"][0]["attempts"] == 1
    state.save_retry(tmp_path, rq)
    loaded = state.load_retry(tmp_path)
    assert len(loaded["queue"]) == 1


def test_last_sync_overwrite(tmp_path: Path) -> None:
    state.save_last_sync(tmp_path, {"vault_id": "gdrive", "has_changes": True})
    state.save_last_sync(tmp_path, {"vault_id": "gdrive", "has_changes": False})
    loaded = json.loads((tmp_path / "last_sync.json").read_text())
    assert loaded["has_changes"] is False


def test_utc_now_iso_format() -> None:
    val = state.utc_now_iso()
    assert "T" in val and val.endswith("+00:00")


# ---------------------------------------------------------------------------
# ADR-0024 — save_last_failure / clear_last_failure
# ---------------------------------------------------------------------------

def _make_failure_payload() -> dict:
    return {
        "vault_id": "gdrive",
        "exit_code": 2,
        "severity": "fatal",
        "scope": "vault",
        "reason": "401 invalid_grant",
        "remediation": "auth_gdrive.py 재실행",
        "source_id": None,
        "first_failed_at": "2026-05-14T01:00:00+00:00",
        "last_failed_at": "2026-05-14T01:00:00+00:00",
        "failed_count": 1,
        "alerted_at": None,
    }


def test_save_last_failure_first_fatal(tmp_path: Path) -> None:
    """첫 fatal — 그대로 영속화."""
    state.save_last_failure(tmp_path, _make_failure_payload())
    loaded = json.loads((tmp_path / "last_failure.json").read_text())
    assert loaded["vault_id"] == "gdrive"
    assert loaded["failed_count"] == 1
    assert loaded["first_failed_at"] == "2026-05-14T01:00:00+00:00"


def test_save_last_failure_consecutive_increments_count(tmp_path: Path) -> None:
    """연속 fatal — failed_count +1, first_failed_at 보존."""
    p1 = _make_failure_payload()
    state.save_last_failure(tmp_path, p1)

    p2 = _make_failure_payload()
    p2["last_failed_at"] = "2026-05-14T02:00:00+00:00"
    state.save_last_failure(tmp_path, p2)

    loaded = json.loads((tmp_path / "last_failure.json").read_text())
    assert loaded["failed_count"] == 2
    assert loaded["first_failed_at"] == "2026-05-14T01:00:00+00:00"  # 보존
    assert loaded["last_failed_at"] == "2026-05-14T02:00:00+00:00"  # 갱신
    assert loaded["alerted_at"] is None


def test_save_last_failure_preserves_alerted_at(tmp_path: Path) -> None:
    """ops-alert.py 의 dedup 메타데이터 (alerted_at + alerted_failed_count) 보존 검증.

    연속 fatal 시 두 필드가 보존되지 않으면 needs_alert 가 매 사이클 True 로 평가 →
    매 timer cycle 마다 webhook 발송 → ADR-0024 dedup 정책 무력화.
    """
    p1 = _make_failure_payload()
    state.save_last_failure(tmp_path, p1)

    # ops-alert.py 가 webhook 발송 성공 → alerted_at + alerted_failed_count 갱신 (직접 write)
    path = tmp_path / "last_failure.json"
    existing = json.loads(path.read_text())
    existing["alerted_at"] = "2026-05-14T01:05:00+00:00"
    existing["alerted_failed_count"] = 1
    state._atomic_write_json(path, existing)

    # 다음 fatal — 두 필드 모두 보존되어야 dedup 정책 적용 가능
    p2 = _make_failure_payload()
    p2["last_failed_at"] = "2026-05-14T02:00:00+00:00"
    state.save_last_failure(tmp_path, p2)

    loaded = json.loads(path.read_text())
    assert loaded["alerted_at"] == "2026-05-14T01:05:00+00:00"
    assert loaded["alerted_failed_count"] == 1
    assert loaded["failed_count"] == 2


def test_clear_last_failure_removes_file(tmp_path: Path) -> None:
    """success 시 — 연속 fatal 카운트 리셋."""
    state.save_last_failure(tmp_path, _make_failure_payload())
    assert (tmp_path / "last_failure.json").exists()

    state.clear_last_failure(tmp_path)
    assert not (tmp_path / "last_failure.json").exists()


def test_clear_last_failure_idempotent(tmp_path: Path) -> None:
    """파일 없을 때도 안전."""
    state.clear_last_failure(tmp_path)
    state.clear_last_failure(tmp_path)
    assert not (tmp_path / "last_failure.json").exists()
