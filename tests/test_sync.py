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
from lib.exceptions import VaultSyncFatal, VaultSyncFileFatal, VaultSyncRetryable
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


# ---------------------------------------------------------------------------
# issue #133 — file_map end-of-cycle batch commit (fsync 1회)
# ---------------------------------------------------------------------------


def test_sync_file_map_save_called_once_per_cycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """issue #133: 사이클 내 N건 변경 → save_file_map 호출은 정확히 1회.

    변경 0건 cycle 의 fsync 0회 동작은 test_sync_no_changes_does_not_save_file_map
    (line 379) 에서 별도 검증. 본 테스트는 has_changes=True 케이스의 단일 호출만 다룬다.
    """
    state_dir = tmp_path / "_state" / "gdrive"
    state_dir.mkdir(parents=True)
    vault_local = tmp_path / "vault" / "gdrive"
    vault_local.mkdir(parents=True)
    # mount FS 에 3건 배치 (sync 가 read 할 수 있도록)
    for name in ("a.md", "b.md", "c.md"):
        (vault_local / name).write_text(f"content {name}")

    monkeypatch.setattr(sync, "lsjson", lambda *a, **kw: [
        {"ID": f"id_{x}", "Path": f"{x}.md", "Name": f"{x}.md", "Size": 9,
         "MimeType": "text/markdown", "ModTime": "2026-05-19T00:00:00Z", "IsDir": False}
        for x in ("a", "b", "c")
    ])

    # save_file_map 호출 횟수 카운트 — module-level spy
    call_count = {"n": 0}
    real_save = sync.save_file_map

    def _spy_save_file_map(state_dir_arg: Path, file_map_arg: dict[str, Any]) -> None:
        call_count["n"] += 1
        real_save(state_dir_arg, file_map_arg)

    monkeypatch.setattr(sync, "save_file_map", _spy_save_file_map)

    vault_cfg = VaultConfig(
        id="gdrive", type="gdrive_api", enabled=True, sync_interval_sec=600,
        local_path=vault_local,
        options={"rclone_remote_name": "gdrive"},
    )
    result = sync.sync(vault_cfg=vault_cfg, instance_root=tmp_path, state_dir=state_dir)

    assert len(result.changed) == 3
    # 핵심 assertion: 3건 변경 → fsync 1회
    assert call_count["n"] == 1, (
        f"save_file_map should be called exactly once per cycle "
        f"(end-of-cycle batch), got {call_count['n']}"
    )
    # file_map.json 도 1회만 disk write 됨 — 최종 상태는 영속화됨
    fm = json.loads((state_dir / "file_map.json").read_text())
    assert set(fm["files"].keys()) == {"id_a", "id_b", "id_c"}


def test_sync_no_changes_does_not_save_file_map(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """issue #133: 변경 0건 cycle 은 file_map.json disk write 생략 (fsync 0회).

    기존 file_map 이 비어있지 않은 상태에서 listing 이 동일 → diff 0건.
    has_changes=False 이면 file_map 자체가 동일하므로 save_file_map 호출 불필요.
    """
    state_dir = tmp_path / "_state" / "gdrive"
    state_dir.mkdir(parents=True)
    vault_local = tmp_path / "vault" / "gdrive"
    vault_local.mkdir(parents=True)
    (vault_local / "a.md").write_text("hello")
    # 기존 file_map 과 listing 이 일치 (변경 0건)
    (state_dir / "file_map.json").write_text(json.dumps({
        "vault_id": "gdrive",
        "updated_at": "2026-05-19T00:00:00+00:00",
        "files": {"id_a": {"source_relpath": "a.md", "source_mtime": "2026-05-19T00:00:00Z",
                           "wiki_path": "wiki/sources/gdrive/a.md", "bytes": 5,
                           "last_synced_at": "2026-05-19T00:00:00Z"}},
    }))

    monkeypatch.setattr(sync, "lsjson", lambda *a, **kw: [
        {"ID": "id_a", "Path": "a.md", "Name": "a.md", "Size": 5,
         "MimeType": "text/markdown", "ModTime": "2026-05-19T00:00:00Z", "IsDir": False},
    ])

    call_count = {"n": 0}
    real_save = sync.save_file_map

    def _spy_save_file_map(state_dir_arg: Path, file_map_arg: dict[str, Any]) -> None:
        call_count["n"] += 1
        real_save(state_dir_arg, file_map_arg)

    monkeypatch.setattr(sync, "save_file_map", _spy_save_file_map)

    vault_cfg = VaultConfig(
        id="gdrive", type="gdrive_api", enabled=True, sync_interval_sec=600,
        local_path=vault_local,
        options={"rclone_remote_name": "gdrive"},
    )
    result = sync.sync(vault_cfg=vault_cfg, instance_root=tmp_path, state_dir=state_dir)

    assert result.has_changes is False
    # 변경 0건 → save_file_map 0회 (file_map 불변, fsync 무의미)
    assert call_count["n"] == 0, (
        f"save_file_map should NOT be called when has_changes=False, "
        f"got {call_count['n']}"
    )
    # updated_at 도 변경되지 않음
    fm = json.loads((state_dir / "file_map.json").read_text())
    assert fm["updated_at"] == "2026-05-19T00:00:00+00:00"


def test_sync_mixed_operations_saves_file_map_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S3 (review 2) — created + deleted + renamed 혼합 cycle 에서도 fsync 1회.

    회귀 가드: `if changed or deleted:` condition 이 혼합 ops 에서도 단일 save 만
    트리거하는지 검증. (3건 create / 0건 change 단일 케이스만 있던 기존 테스트 보강.)
    """
    state_dir = tmp_path / "_state" / "gdrive"
    state_dir.mkdir(parents=True)
    vault_local = tmp_path / "vault" / "gdrive"
    vault_local.mkdir(parents=True)

    # mount FS 에 created+renamed 대상 배치
    (vault_local / "new.md").write_text("new file")
    (vault_local / "renamed.md").write_text("renamed target")
    # noop entry 들도 mount FS 에 배치 (diff 가 noop 으로 분류)
    for name in ("noop_a.md", "noop_b.md", "noop_c.md"):
        (vault_local / name).write_text("noop content")

    # 기존 file_map: id_keep, id_rename, id_delete + 3개 noop (총 6개) — delete_ratio = 1/6 ≈ 17%
    # (기본 false_delete_threshold 0.3 통과)
    (state_dir / "file_map.json").write_text(json.dumps({
        "vault_id": "gdrive",
        "updated_at": "2026-05-19T00:00:00+00:00",
        "files": {
            "id_keep": {"source_relpath": "keep.md", "source_mtime": "2026-05-19T00:00:00Z",
                        "wiki_path": "wiki/sources/gdrive/keep.md", "bytes": 1,
                        "last_synced_at": "2026-05-19T00:00:00Z"},
            "id_rename": {"source_relpath": "original.md", "source_mtime": "2026-05-19T00:00:00Z",
                          "wiki_path": "wiki/sources/gdrive/original.md", "bytes": 1,
                          "last_synced_at": "2026-05-19T00:00:00Z"},
            "id_delete": {"source_relpath": "doomed.md", "source_mtime": "2026-05-19T00:00:00Z",
                          "wiki_path": "wiki/sources/gdrive/doomed.md", "bytes": 1,
                          "last_synced_at": "2026-05-19T00:00:00Z"},
            "id_noop_a": {"source_relpath": "noop_a.md", "source_mtime": "2026-05-19T00:00:00Z",
                          "wiki_path": "wiki/sources/gdrive/noop_a.md", "bytes": 1,
                          "last_synced_at": "2026-05-19T00:00:00Z"},
            "id_noop_b": {"source_relpath": "noop_b.md", "source_mtime": "2026-05-19T00:00:00Z",
                          "wiki_path": "wiki/sources/gdrive/noop_b.md", "bytes": 1,
                          "last_synced_at": "2026-05-19T00:00:00Z"},
            "id_noop_c": {"source_relpath": "noop_c.md", "source_mtime": "2026-05-19T00:00:00Z",
                          "wiki_path": "wiki/sources/gdrive/noop_c.md", "bytes": 1,
                          "last_synced_at": "2026-05-19T00:00:00Z"},
        },
    }))
    # delete 대상 wiki page 사전 배치
    doomed_wiki = tmp_path / "wiki" / "sources" / "gdrive" / "doomed.md"
    doomed_wiki.parent.mkdir(parents=True)
    doomed_wiki.write_text("doomed")

    # listing: id_new (created) + id_rename (renamed → renamed.md) + id_keep + 3 noop
    # — id_delete 는 listing 에 없음 → deleted
    monkeypatch.setattr(sync, "lsjson", lambda *a, **kw: [
        {"ID": "id_new", "Path": "new.md", "Name": "new.md", "Size": 7,
         "MimeType": "text/markdown", "ModTime": "2026-05-19T00:00:00Z", "IsDir": False},
        {"ID": "id_rename", "Path": "renamed.md", "Name": "renamed.md", "Size": 14,
         "MimeType": "text/markdown", "ModTime": "2026-05-19T00:00:00Z", "IsDir": False},
        {"ID": "id_keep", "Path": "keep.md", "Name": "keep.md", "Size": 0,
         "MimeType": "text/markdown", "ModTime": "2026-05-19T00:00:00Z", "IsDir": False},
        {"ID": "id_noop_a", "Path": "noop_a.md", "Name": "noop_a.md", "Size": 0,
         "MimeType": "text/markdown", "ModTime": "2026-05-19T00:00:00Z", "IsDir": False},
        {"ID": "id_noop_b", "Path": "noop_b.md", "Name": "noop_b.md", "Size": 0,
         "MimeType": "text/markdown", "ModTime": "2026-05-19T00:00:00Z", "IsDir": False},
        {"ID": "id_noop_c", "Path": "noop_c.md", "Name": "noop_c.md", "Size": 0,
         "MimeType": "text/markdown", "ModTime": "2026-05-19T00:00:00Z", "IsDir": False},
    ])

    call_count: dict[str, int] = {"n": 0}
    real_save = sync.save_file_map

    def _spy_save_file_map(state_dir_arg: Path, file_map_arg: dict[str, Any]) -> None:
        call_count["n"] += 1
        real_save(state_dir_arg, file_map_arg)

    monkeypatch.setattr(sync, "save_file_map", _spy_save_file_map)

    # 기본 false_delete_threshold 0.3 사용 — file_map 6개 중 1개 delete → 17% < 30% 가드 통과
    vault_cfg = VaultConfig(
        id="gdrive", type="gdrive_api", enabled=True, sync_interval_sec=600,
        local_path=vault_local,
        options={"rclone_remote_name": "gdrive"},
    )
    result = sync.sync(vault_cfg=vault_cfg, instance_root=tmp_path, state_dir=state_dir)

    # changed: created 1 + renamed 1, deleted: 1, noop 3 (분류만, save 영향 없음)
    assert len(result.changed) == 2
    assert len(result.deleted) == 1
    # 핵심: 혼합 ops 에서도 save_file_map 1회
    assert call_count["n"] == 1, (
        f"save_file_map should be called once for mixed ops cycle, got {call_count['n']}"
    )
    # 최종 file_map: id_delete 제거, id_rename source_relpath 갱신, id_new 추가, 3 noop 유지
    fm = json.loads((state_dir / "file_map.json").read_text())
    assert set(fm["files"].keys()) == {"id_keep", "id_rename", "id_new", "id_noop_a", "id_noop_b", "id_noop_c"}
    assert fm["files"]["id_rename"]["source_relpath"] == "renamed.md"
    assert fm["files"]["id_new"]["source_relpath"] == "new.md"


def test_sync_all_fails_does_not_save_file_map(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S2 (review 1) — 모든 entry 가 handler 에서 raise 시 file_map.json save 0회.

    시나리오: N건의 diff.entries 가 모두 VaultSyncFileFatal → error_count == N →
    changed/deleted 모두 빈 상태 → end-of-cycle save_file_map skipped.
    """
    state_dir = tmp_path / "_state" / "gdrive"
    state_dir.mkdir(parents=True)
    vault_local = tmp_path / "vault" / "gdrive"
    vault_local.mkdir(parents=True)
    (vault_local / "a.md").write_text("hello")

    monkeypatch.setattr(sync, "lsjson", lambda *a, **kw: [
        {"ID": f"id_{x}", "Path": f"{x}.md", "Name": f"{x}.md", "Size": 5,
         "MimeType": "text/markdown", "ModTime": "2026-05-19T00:00:00Z", "IsDir": False}
        for x in ("a", "b")
    ])

    # 모든 handler 가 VaultSyncFileFatal raise — per-entry fatal (sync 가 catch 후 continue)
    def _always_fail(*a: Any, **kw: Any) -> None:
        raise VaultSyncFileFatal(vault_id="gdrive", source_id="x", reason="all-fail simulation")

    monkeypatch.setattr(sync, "_handle_create_or_modify", _always_fail)

    call_count: dict[str, int] = {"n": 0}
    real_save = sync.save_file_map

    def _spy_save_file_map(state_dir_arg: Path, file_map_arg: dict[str, Any]) -> None:
        call_count["n"] += 1
        real_save(state_dir_arg, file_map_arg)

    monkeypatch.setattr(sync, "save_file_map", _spy_save_file_map)

    vault_cfg = VaultConfig(
        id="gdrive", type="gdrive_api", enabled=True, sync_interval_sec=600,
        local_path=vault_local,
        options={"rclone_remote_name": "gdrive"},
    )
    result = sync.sync(vault_cfg=vault_cfg, instance_root=tmp_path, state_dir=state_dir)

    # 모든 entry 가 file-fatal → changed/deleted 모두 비어있음
    assert len(result.changed) == 0
    assert len(result.deleted) == 0
    # → end-of-cycle save_file_map skip (changed or deleted == False)
    assert call_count["n"] == 0, (
        f"save_file_map should NOT be called when all entries fail with FileFatal, "
        f"got {call_count['n']}"
    )


def test_sync_vaultsyncfatal_midcycle_aborts_batch_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S5 (review 2) — VaultSyncFatal mid-cycle 시 batch save 미도달.

    시나리오: 1건 성공 → 2건째 handler 에서 VaultSyncFatal (auth/structural fatal,
    사람 개입 필요) → sync 함수가 즉시 re-raise (sync.py:565-566) → batch save 라인
    도달 못함 → file_map.json 미저장. crash safety 주장은 다음 cycle 의 idempotent
    re-detect 로 보완 (in-memory mutation 만 유실).
    """
    state_dir = tmp_path / "_state" / "gdrive"
    state_dir.mkdir(parents=True)
    vault_local = tmp_path / "vault" / "gdrive"
    vault_local.mkdir(parents=True)
    (vault_local / "a.md").write_text("a ok")
    (vault_local / "b.md").write_text("b ok")

    monkeypatch.setattr(sync, "lsjson", lambda *a, **kw: [
        {"ID": "id_a", "Path": "a.md", "Name": "a.md", "Size": 4,
         "MimeType": "text/markdown", "ModTime": "2026-05-19T00:00:00Z", "IsDir": False},
        {"ID": "id_b", "Path": "b.md", "Name": "b.md", "Size": 4,
         "MimeType": "text/markdown", "ModTime": "2026-05-19T00:00:00Z", "IsDir": False},
    ])

    real_handler = sync._handle_create_or_modify
    call_index: dict[str, int] = {"i": 0}

    def _maybe_fail(*a: Any, **kw: Any) -> None:
        call_index["i"] += 1
        if call_index["i"] == 1:
            # 첫 번째 entry (id_a) — 성공
            real_handler(*a, **kw)
        else:
            # 두 번째 entry (id_b) — vault-level fatal (auth/structural)
            raise VaultSyncFatal(
                vault_id="gdrive",
                reason="midcycle-fatal simulation",
                remediation="re-authenticate",
            )

    monkeypatch.setattr(sync, "_handle_create_or_modify", _maybe_fail)

    call_count: dict[str, int] = {"n": 0}
    real_save = sync.save_file_map

    def _spy_save_file_map(state_dir_arg: Path, file_map_arg: dict[str, Any]) -> None:
        call_count["n"] += 1
        real_save(state_dir_arg, file_map_arg)

    monkeypatch.setattr(sync, "save_file_map", _spy_save_file_map)

    vault_cfg = VaultConfig(
        id="gdrive", type="gdrive_api", enabled=True, sync_interval_sec=600,
        local_path=vault_local,
        options={"rclone_remote_name": "gdrive"},
    )
    with pytest.raises(VaultSyncFatal):
        sync.sync(vault_cfg=vault_cfg, instance_root=tmp_path, state_dir=state_dir)

    # batch save 미도달 — VaultSyncFatal propagate 시 end-of-cycle 라인 도달 못함
    assert call_count["n"] == 0, (
        f"save_file_map should NOT be called when VaultSyncFatal mid-cycle, "
        f"got {call_count['n']}"
    )
    # file_map.json 도 미저장 (in-memory mutation 만 있고, batch save skip)
    # → pre-existing file_map.json 없었으므로 파일 자체가 없어야 함
    assert not (state_dir / "file_map.json").exists()


# ---------------------------------------------------------------------------
# NAS vault 테스트 (ADR-0045)
# ---------------------------------------------------------------------------

def test_handle_create_or_modify_nas_path_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """NAS vault _handle_create_or_modify: file_map key == path (source_id == path).

    Issue #134 회귀 테스트: source_id="" 하드코딩 시 모든 NAS 파일이 같은 키로 덮어써지는 문제 검증.
    """
    from lib.mount_diff import DiffEntry

    # setup
    instance_root = tmp_path / "instance"
    instance_root.mkdir()
    wiki_root = instance_root / "wiki"
    wiki_root.mkdir(parents=True)
    vault_local = tmp_path / "vault" / "nas1"
    vault_local.mkdir(parents=True)
    (vault_local / "a.txt").write_text("hello")

    file_map: dict[str, Any] = {"files": {}}
    changed_out: list = []

    entry = DiffEntry(
        operation="created",
        source_id="a.txt",  # NAS: source_id == path (ADR-0045)
        source_relpath="a.txt",
        mime_type="text/plain",
        mtime="2026-06-07T00:00:00Z",
        size=5,
    )

    # execute
    sync._handle_create_or_modify(
        entry,
        vault_id="nas1",
        vault_local_path=vault_local,
        instance_root=instance_root,
        file_map=file_map,
        started_iso="2026-06-07T00:00:00Z",
        max_file_size_mb=None,
        changed_out=changed_out,
    )

    # verify: file_map key == path
    assert "a.txt" in file_map["files"], f"Expected 'a.txt' in file_map, got {list(file_map['files'].keys())}"
    assert file_map["files"]["a.txt"]["source_relpath"] == "a.txt"
    assert file_map["files"]["a.txt"]["source_mtime"] == "2026-06-07T00:00:00Z"


def test_handle_create_or_modify_nas_multi_file_no_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """NAS vault multi-file: 각 파일이 고유한 key로 file_map에 저장 (덮어쓰기 없음).

    Issue #134 회귀 테스트: source_id="" 하드코딩 시 3개 파일 처리 후 file_map에 1개만 남는 문제 검증.
    """
    from lib.mount_diff import DiffEntry

    # setup
    instance_root = tmp_path / "instance"
    instance_root.mkdir()
    wiki_root = instance_root / "wiki"
    wiki_root.mkdir(parents=True)
    vault_local = tmp_path / "vault" / "nas1"
    vault_local.mkdir(parents=True)
    (vault_local / "a.txt").write_text("aaa")
    (vault_local / "b.txt").write_text("bbb")
    (vault_local / "c.txt").write_text("ccc")

    file_map: dict[str, Any] = {"files": {}}
    changed_out: list = []

    entries = [
        DiffEntry(
            operation="created",
            source_id="a.txt",  # NAS: source_id == path
            source_relpath="a.txt",
            mime_type="text/plain",
            mtime="2026-06-07T00:00:00Z",
            size=3,
        ),
        DiffEntry(
            operation="created",
            source_id="b.txt",
            source_relpath="b.txt",
            mime_type="text/plain",
            mtime="2026-06-07T00:00:00Z",
            size=3,
        ),
        DiffEntry(
            operation="created",
            source_id="c.txt",
            source_relpath="c.txt",
            mime_type="text/plain",
            mtime="2026-06-07T00:00:00Z",
            size=3,
        ),
    ]

    # execute: 3개 파일 처리
    for entry in entries:
        sync._handle_create_or_modify(
            entry,
            vault_id="nas1",
            vault_local_path=vault_local,
            instance_root=instance_root,
            file_map=file_map,
            started_iso="2026-06-07T00:00:00Z",
            max_file_size_mb=None,
            changed_out=changed_out,
        )

    # verify: file_map에 3개 entry 모두 존재 (덮어쓰기 없음)
    assert len(file_map["files"]) == 3, f"Expected 3 entries, got {len(file_map['files'])}: {list(file_map['files'].keys())}"
    assert "a.txt" in file_map["files"]
    assert "b.txt" in file_map["files"]
    assert "c.txt" in file_map["files"]

