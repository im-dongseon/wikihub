"""lib/sync.py orchestration 테스트 (ADR-0035 — rclone lsjson + mount_diff 기반).

rclone subprocess 는 monkeypatch 로 mock — 실제 호출 없음.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lib import sync
from lib.config import VaultConfig
from lib.exceptions import VaultSyncRetryable
from lib.sync import (
    SyncResult,
    _compute_wiki_path,
    _sanitize_relpath,
    result_to_stdout_json,
)


# ---------------------------------------------------------------------------
# _compute_wiki_path
# ---------------------------------------------------------------------------

def test_compute_wiki_path_binary() -> None:
    assert _compute_wiki_path(
        "gdrive", "meetings/Q1.pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ) == "wiki/sources/gdrive/meetings/Q1.pptx.md"


def test_compute_wiki_path_md_no_double() -> None:
    assert _compute_wiki_path("gdrive", "notes/idea.md", "text/markdown") \
        == "wiki/sources/gdrive/notes/idea.md"


def test_compute_wiki_path_txt_keeps_ext() -> None:
    assert _compute_wiki_path("gdrive", "notes/readme.txt", "text/plain") \
        == "wiki/sources/gdrive/notes/readme.txt.md"


def test_compute_wiki_path_google_doc() -> None:
    assert _compute_wiki_path(
        "gdrive", "policies/onboarding",
        "application/vnd.google-apps.document",
    ) == "wiki/sources/gdrive/policies/onboarding.gdoc.md"


# ---------------------------------------------------------------------------
# _sanitize_relpath
# ---------------------------------------------------------------------------

def test_sanitize_relpath_empty_returns_none() -> None:
    assert _sanitize_relpath("") is None
    assert _sanitize_relpath("   ") is None


def test_sanitize_relpath_traversal_blocked() -> None:
    assert _sanitize_relpath("../etc/passwd") is None
    assert _sanitize_relpath("a/../b") is None
    assert _sanitize_relpath(".") is None
    assert _sanitize_relpath("./") is None


def test_sanitize_relpath_control_char_blocked() -> None:
    assert _sanitize_relpath("a\x00b.md") is None
    assert _sanitize_relpath("a\\b.md") is None


def test_sanitize_relpath_valid() -> None:
    assert _sanitize_relpath("notes/idea.md") == "notes/idea.md"
    assert _sanitize_relpath("/notes/idea.md") == "notes/idea.md"  # lstrip("/")


# ---------------------------------------------------------------------------
# result_to_stdout_json
# ---------------------------------------------------------------------------

def test_result_to_stdout_json_no_changes() -> None:
    result = SyncResult(vault_id="gdrive", has_changes=False, duration_ms=12)
    payload = json.loads(result_to_stdout_json(result))
    assert payload["vault_id"] == "gdrive"
    assert payload["has_changes"] is False
    assert payload["changed"] == []
    assert payload["deleted"] == []
    assert payload["duration_ms"] == 12


# ---------------------------------------------------------------------------
# sync orchestration — false-deleted 가드
# ---------------------------------------------------------------------------

def _vault_cfg(**options: Any) -> VaultConfig:
    return VaultConfig(
        id="gdrive",
        type="gdrive_api",
        enabled=True,
        sync_interval_sec=600,
        local_path=Path("/tmp/wikihub-test/vault/gdrive"),
        options={"rclone_remote_name": "gdrive", **options},
    )


def test_sync_listing_zero_with_existing_file_map_raises_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0035 §ζ2 — listing 0건 + file_map 비어있지 않음 → Retryable."""
    # file_map 사전 채움
    state_dir = tmp_path / "_state" / "gdrive"
    state_dir.mkdir(parents=True)
    (state_dir / "file_map.json").write_text(json.dumps({
        "vault_id": "gdrive",
        "updated_at": None,
        "files": {"id_a": {"source_relpath": "a.md", "source_mtime": "x",
                           "wiki_path": "wiki/sources/gdrive/a.md", "bytes": 1,
                           "last_synced_at": "x"}},
    }))

    # rclone lsjson 을 0건 반환으로 mock
    monkeypatch.setattr(sync, "lsjson", lambda *a, **kw: [])

    with pytest.raises(VaultSyncRetryable) as exc:
        sync.sync(
            vault_cfg=_vault_cfg(),
            instance_root=tmp_path,
            state_dir=state_dir,
        )
    assert "listing 0건" in exc.value.reason


def test_sync_delete_ratio_exceeds_threshold_raises_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0035 §ζ2 — delete_ratio > threshold → Retryable."""
    state_dir = tmp_path / "_state" / "gdrive"
    state_dir.mkdir(parents=True)
    # file_map 3건 — listing 에 1건만 → delete_ratio = 2/3 > 0.3
    (state_dir / "file_map.json").write_text(json.dumps({
        "vault_id": "gdrive",
        "updated_at": None,
        "files": {
            f"id_{x}": {"source_relpath": f"{x}.md", "source_mtime": "x",
                        "wiki_path": f"wiki/sources/gdrive/{x}.md", "bytes": 1,
                        "last_synced_at": "x"}
            for x in ("a", "b", "c")
        },
    }))

    monkeypatch.setattr(sync, "lsjson", lambda *a, **kw: [
        {"ID": "id_a", "Path": "a.md", "Name": "a.md", "Size": 1,
         "MimeType": "text/markdown", "ModTime": "x", "IsDir": False},
    ])

    with pytest.raises(VaultSyncRetryable) as exc:
        sync.sync(
            vault_cfg=_vault_cfg(false_delete_threshold=0.3),
            instance_root=tmp_path,
            state_dir=state_dir,
        )
    assert "삭제 비율" in exc.value.reason


def test_sync_delete_ratio_at_exact_threshold_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M5 경계 케이스 — delete_ratio == threshold 일 때 가드 통과 (>이지 >= 아님)."""
    state_dir = tmp_path / "_state" / "gdrive"
    state_dir.mkdir(parents=True)
    vault_local = tmp_path / "vault" / "gdrive"
    vault_local.mkdir(parents=True)
    # file_map 4건, listing 에 3건 → delete_ratio = 1/4 = 0.25
    (state_dir / "file_map.json").write_text(json.dumps({
        "vault_id": "gdrive",
        "updated_at": None,
        "files": {
            f"id_{x}": {"source_relpath": f"{x}.md", "source_mtime": "x",
                        "wiki_path": f"wiki/sources/gdrive/{x}.md", "bytes": 1,
                        "last_synced_at": "x"}
            for x in ("a", "b", "c", "d")
        },
    }))
    # mount FS 에 3건 (a/b/c) 배치
    for name in ("a.md", "b.md", "c.md"):
        (vault_local / name).write_text("hello")

    monkeypatch.setattr(sync, "lsjson", lambda *a, **kw: [
        {"ID": f"id_{x}", "Path": f"{x}.md", "Name": f"{x}.md", "Size": 5,
         "MimeType": "text/markdown", "ModTime": "x", "IsDir": False}
        for x in ("a", "b", "c")
    ])

    # threshold = 0.25 → delete_ratio == threshold → 통과 (> 만 abort)
    vault_cfg = VaultConfig(
        id="gdrive", type="gdrive_api", enabled=True, sync_interval_sec=600,
        local_path=vault_local,
        options={"rclone_remote_name": "gdrive", "false_delete_threshold": 0.25},
    )
    result = sync.sync(vault_cfg=vault_cfg, instance_root=tmp_path, state_dir=state_dir)
    # 정상 통과 — deleted 1건 (id_d) 분류
    assert len(result.deleted) == 1


def test_sync_rename_updates_file_map_and_wiki(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M7 — rename 처리: 같은 fileId 의 새 path 가 lsjson 에 있을 때
    file_map 갱신 + 새 wiki page 생성 + old wiki page unlink."""
    state_dir = tmp_path / "_state" / "gdrive"
    state_dir.mkdir(parents=True)
    vault_local = tmp_path / "vault" / "gdrive"
    vault_local.mkdir(parents=True)
    # mount FS 의 새 path 에만 파일 배치 (rename 후 상태)
    (vault_local / "renamed.md").write_text("hello new")
    # 기존 wiki page 사전 배치
    old_wiki = tmp_path / "wiki" / "sources" / "gdrive" / "original.md"
    old_wiki.parent.mkdir(parents=True)
    old_wiki.write_text("old content")
    # file_map 에 id_a → original.md 등록
    (state_dir / "file_map.json").write_text(json.dumps({
        "vault_id": "gdrive",
        "updated_at": None,
        "files": {
            "id_a": {"source_relpath": "original.md", "source_mtime": "2026-05-19T00:00:00Z",
                     "wiki_path": "wiki/sources/gdrive/original.md", "bytes": 100,
                     "last_synced_at": "2026-05-19T00:00:00Z"},
        },
    }))

    monkeypatch.setattr(sync, "lsjson", lambda *a, **kw: [
        {"ID": "id_a", "Path": "renamed.md", "Name": "renamed.md", "Size": 9,
         "MimeType": "text/markdown", "ModTime": "2026-05-19T00:00:00Z", "IsDir": False},
    ])

    vault_cfg = VaultConfig(
        id="gdrive", type="gdrive_api", enabled=True, sync_interval_sec=600,
        local_path=vault_local,
        options={"rclone_remote_name": "gdrive"},
    )
    result = sync.sync(vault_cfg=vault_cfg, instance_root=tmp_path, state_dir=state_dir)

    assert result.has_changes is True
    assert len(result.changed) == 1
    assert result.changed[0].operation == "renamed"
    # file_map source_relpath 갱신
    fm = json.loads((state_dir / "file_map.json").read_text())
    assert fm["files"]["id_a"]["source_relpath"] == "renamed.md"
    assert fm["files"]["id_a"]["wiki_path"] == "wiki/sources/gdrive/renamed.md"
    # 새 wiki page 생성
    new_wiki = tmp_path / "wiki" / "sources" / "gdrive" / "renamed.md"
    assert new_wiki.exists()
    # old wiki page unlink
    assert not old_wiki.exists()


def test_sync_first_run_all_listing_treated_as_created(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0035 — file_map 비어있는 first-run 은 모든 listing 이 created 분류 (자연 bootstrap)."""
    state_dir = tmp_path / "_state" / "gdrive"
    state_dir.mkdir(parents=True)
    vault_local = tmp_path / "vault" / "gdrive"
    vault_local.mkdir(parents=True)
    # mount FS 에 파일 실제 배치 (sync 의 read 경로)
    (vault_local / "a.md").write_text("hello")

    monkeypatch.setattr(sync, "lsjson", lambda *a, **kw: [
        {"ID": "id_a", "Path": "a.md", "Name": "a.md", "Size": 5,
         "MimeType": "text/markdown", "ModTime": "2026-05-19T00:00:00Z", "IsDir": False},
    ])

    vault_cfg = VaultConfig(
        id="gdrive", type="gdrive_api", enabled=True, sync_interval_sec=600,
        local_path=vault_local,
        options={"rclone_remote_name": "gdrive"},
    )
    result = sync.sync(vault_cfg=vault_cfg, instance_root=tmp_path, state_dir=state_dir)

    assert result.has_changes is True
    assert len(result.changed) == 1
    assert result.changed[0].operation == "created"
    assert result.changed[0].source_id == "id_a"
    # file_map 영속화 — source_id 키
    fm = json.loads((state_dir / "file_map.json").read_text())
    assert "id_a" in fm["files"]


def test_sync_passes_rclone_remote_path_to_lsjson(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0035 §Note 2026-05-19 — yaml.options.rclone_remote_path 가 lsjson 의 path 인자로 전달."""
    state_dir = tmp_path / "_state" / "gdrive"
    state_dir.mkdir(parents=True)
    vault_local = tmp_path / "vault" / "gdrive"
    vault_local.mkdir(parents=True)

    captured: dict[str, Any] = {}

    def _spy_lsjson(remote: str, *, path: str = "", **kw: Any) -> list[dict[str, Any]]:
        captured["remote"] = remote
        captured["path"] = path
        return []

    monkeypatch.setattr(sync, "lsjson", _spy_lsjson)

    vault_cfg = VaultConfig(
        id="gdrive", type="gdrive_api", enabled=True, sync_interval_sec=600,
        local_path=vault_local,
        options={"rclone_remote_name": "gdrive", "rclone_remote_path": "wikihub"},
    )
    result = sync.sync(vault_cfg=vault_cfg, instance_root=tmp_path, state_dir=state_dir)
    assert captured == {"remote": "gdrive", "path": "wikihub"}
    assert result.has_changes is False
