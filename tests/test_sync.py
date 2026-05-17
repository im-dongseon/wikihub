"""lib/sync.py orchestration 테스트.

gws 호출은 monkeypatch 로 mock — 실제 subprocess 호출 없음.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lib import sync
from lib.config import VaultConfig
from lib.exceptions import VaultSyncFatal, VaultSyncFileFatal, VaultSyncRetryable
from lib.gws import GwsResult
from lib.sync import (
    ChangedFile,
    SyncResult,
    _compute_wiki_path,
    _passes_trust_boundary,
    _sanitize_relpath,
    result_to_stdout_json,
)


# ---------------------------------------------------------------------------
# _compute_wiki_path — 모든 branch 커버
# ---------------------------------------------------------------------------

def test_compute_wiki_path_binary() -> None:
    assert _compute_wiki_path("gdrive", "meetings/Q1.pptx",
                              "application/vnd.openxmlformats-officedocument.presentationml.presentation") \
        == "wiki/sources/gdrive/meetings/Q1.pptx.md"


def test_compute_wiki_path_md_no_double() -> None:
    assert _compute_wiki_path("gdrive", "notes/idea.md", "text/markdown") \
        == "wiki/sources/gdrive/notes/idea.md"


def test_compute_wiki_path_txt_keeps_ext() -> None:
    # I2 정합 — .txt 는 그대로 .txt.md (binary 패턴), spec A2 ambiguity 명시 lock
    assert _compute_wiki_path("gdrive", "notes/readme.txt", "text/plain") \
        == "wiki/sources/gdrive/notes/readme.txt.md"


def test_compute_wiki_path_google_doc() -> None:
    assert _compute_wiki_path("gdrive", "policies/onboarding",
                              "application/vnd.google-apps.document") \
        == "wiki/sources/gdrive/policies/onboarding.gdoc.md"


def test_compute_wiki_path_google_sheet() -> None:
    assert _compute_wiki_path("gdrive", "data/Q1",
                              "application/vnd.google-apps.spreadsheet") \
        == "wiki/sources/gdrive/data/Q1.gsheet.md"


def test_compute_wiki_path_google_slides_already_suffixed() -> None:
    # 이미 .gslides 가 있는 경우 중복 추가 안 함
    assert _compute_wiki_path("gdrive", "decks/deck.gslides",
                              "application/vnd.google-apps.presentation") \
        == "wiki/sources/gdrive/decks/deck.gslides.md"


def test_compute_wiki_path_other_binary_ext() -> None:
    assert _compute_wiki_path("gdrive", "raw/data.csv", "text/csv") \
        == "wiki/sources/gdrive/raw/data.csv.md"


# ---------------------------------------------------------------------------
# _sanitize_relpath — CRIT-3 traversal 차단
# ---------------------------------------------------------------------------

def test_sanitize_relpath_ok() -> None:
    assert _sanitize_relpath("meetings/Q1.pptx") == "meetings/Q1.pptx"
    assert _sanitize_relpath("Q1.pptx") == "Q1.pptx"
    assert _sanitize_relpath("회의록 (Q1).md") == "회의록 (Q1).md"


def test_sanitize_relpath_strips_leading_slash() -> None:
    assert _sanitize_relpath("/leading.md") == "leading.md"


def test_sanitize_relpath_blocks_traversal() -> None:
    assert _sanitize_relpath("../etc/passwd") is None
    assert _sanitize_relpath("foo/../../bar") is None
    assert _sanitize_relpath("..") is None


def test_sanitize_relpath_blocks_control_chars() -> None:
    assert _sanitize_relpath("file\x00name") is None
    assert _sanitize_relpath("file\nname") is None


def test_sanitize_relpath_blocks_backslash() -> None:
    assert _sanitize_relpath("foo\\bar") is None


def test_sanitize_relpath_empty() -> None:
    assert _sanitize_relpath("") is None
    assert _sanitize_relpath("   ") is None


def test_sanitize_relpath_dot_only() -> None:
    # LOW-R3-1: '.' / './' 차단 — vault_local_path / '.' = vault_local_path 자체 write 회피.
    # Python 3.10 의 Path 는 둘 다 parts = () 로 normalize 함.
    assert _sanitize_relpath(".") is None
    assert _sanitize_relpath("./") is None


def test_sanitize_relpath_normalizes_safely() -> None:
    # Path 가 './' 같은 prefix 를 normalize 한 결과가 안전한 path 면 통과.
    # vault_local_path / "./foo" 와 vault_local_path / "foo" 는 동일 — 보안 무해.
    assert _sanitize_relpath("./foo") == "./foo"
    assert _sanitize_relpath("foo/bar") == "foo/bar"


# ---------------------------------------------------------------------------
# _passes_trust_boundary — SIG-6 incremental post-filter
# ---------------------------------------------------------------------------

def test_trust_boundary_my_file_allowed() -> None:
    fm = {"id": "x", "shared": False, "ownedByMe": True, "parents": ["root"]}
    assert _passes_trust_boundary(fm, exclude_shared_with_me=True, root_folder_id=None) is True


def test_trust_boundary_shared_blocked() -> None:
    fm = {"id": "x", "shared": True, "ownedByMe": False, "parents": ["root"]}
    assert _passes_trust_boundary(fm, exclude_shared_with_me=True, root_folder_id=None) is False


def test_trust_boundary_shared_but_owned_allowed() -> None:
    # 내가 만든 파일을 남에게 공유한 경우 — shared=True 이지만 ownedByMe=True
    fm = {"id": "x", "shared": True, "ownedByMe": True, "parents": ["root"]}
    assert _passes_trust_boundary(fm, exclude_shared_with_me=True, root_folder_id=None) is True


def test_trust_boundary_root_folder_match() -> None:
    fm = {"id": "x", "parents": ["folder123"]}
    assert _passes_trust_boundary(fm, exclude_shared_with_me=False, root_folder_id="folder123") is True


def test_trust_boundary_root_folder_no_match() -> None:
    # SIG-6: incremental 에서도 root_folder_id post-filter 적용
    fm = {"id": "x", "parents": ["other"]}
    assert _passes_trust_boundary(fm, exclude_shared_with_me=False, root_folder_id="folder123") is False


def test_trust_boundary_no_parents() -> None:
    fm = {"id": "x"}
    assert _passes_trust_boundary(fm, exclude_shared_with_me=False, root_folder_id="folder123") is False


# ---------------------------------------------------------------------------
# result_to_stdout_json — F2 contract field 검증 (R1 H2 회귀 방지)
# ---------------------------------------------------------------------------

def test_result_to_stdout_json_minimum() -> None:
    r = SyncResult(vault_id="gdrive", has_changes=False, duration_ms=42)
    parsed = json.loads(result_to_stdout_json(r))
    assert parsed == {
        "vault_id": "gdrive",
        "has_changes": False,
        "changed": [],
        "deleted": [],
        "duration_ms": 42,
    }


def test_result_to_stdout_json_with_changes() -> None:
    r = SyncResult(
        vault_id="gdrive",
        has_changes=True,
        changed=[
            ChangedFile(
                source_relpath="meetings/Q1.pptx",
                wiki_path="wiki/sources/gdrive/meetings/Q1.pptx.md",
                operation="created",
                source_id="DRIVE_ID",
                source_mtime="2026-05-13T01:55:12+00:00",
                bytes_written=12453,
            )
        ],
        deleted=["old/archive.md"],
        duration_ms=12345,
    )
    parsed = json.loads(result_to_stdout_json(r))
    assert parsed["vault_id"] == "gdrive"
    assert parsed["has_changes"] is True
    assert len(parsed["changed"]) == 1
    c = parsed["changed"][0]
    # F2 ingest.md §Step 2 contract 8개 필드 모두 검증
    assert c["source_relpath"] == "meetings/Q1.pptx"
    assert c["wiki_path"] == "wiki/sources/gdrive/meetings/Q1.pptx.md"
    assert c["operation"] == "created"
    assert c["source_id"] == "DRIVE_ID"
    assert c["source_mtime"] == "2026-05-13T01:55:12+00:00"
    assert c["bytes_written"] == 12453
    assert parsed["deleted"] == ["old/archive.md"]


def test_result_to_stdout_json_unicode() -> None:
    r = SyncResult(vault_id="gdrive", has_changes=True,
                   changed=[ChangedFile(
                       source_relpath="회의록 (Q1).pptx",
                       wiki_path="wiki/sources/gdrive/회의록 (Q1).pptx.md",
                       operation="modified",
                       source_id="X",
                       source_mtime="2026-05-13T00:00:00+00:00",
                       bytes_written=100,
                   )],
                   duration_ms=0)
    out = result_to_stdout_json(r)
    # ensure_ascii=False 로 unicode 보존
    assert "회의록" in out


# ---------------------------------------------------------------------------
# Bootstrap 가드 — F1 §4.4.6 lift, B2 정합
# ---------------------------------------------------------------------------

def _make_vault_cfg(*, options: dict | None = None) -> VaultConfig:
    return VaultConfig(
        id="gdrive",
        type="gdrive_api",
        enabled=True,
        sync_interval_sec=600,
        local_path=Path("/tmp/vault-gdrive"),
        options=options or {},
    )


def test_bootstrap_guard_no_cursor_no_flag_no_allowed(tmp_path: Path) -> None:
    vault = _make_vault_cfg()
    cred = tmp_path / "cred.json"
    cred.write_text("{}")
    with pytest.raises(VaultSyncFatal) as exc:
        sync.sync(
            vault_cfg=vault,
            instance_root=tmp_path,
            state_dir=tmp_path / "_state",
            credentials_path=cred,
            bootstrap_flag=False,
        )
    assert "bootstrap 비활성" in exc.value.reason


def test_bootstrap_guard_allowed_but_no_flag(tmp_path: Path) -> None:
    vault = _make_vault_cfg(options={"bootstrap_allowed": True})
    cred = tmp_path / "cred.json"
    cred.write_text("{}")
    with pytest.raises(VaultSyncFatal) as exc:
        sync.sync(
            vault_cfg=vault,
            instance_root=tmp_path,
            state_dir=tmp_path / "_state",
            credentials_path=cred,
            bootstrap_flag=False,
        )
    assert "플래그 누락" in exc.value.reason


# ---------------------------------------------------------------------------
# sync end-to-end with mocked gws (incremental)
# ---------------------------------------------------------------------------

def test_sync_incremental_no_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """기존 cursor 가 있는데 changes 0건 → has_changes=False, 정상 종료."""
    vault = _make_vault_cfg(options={"credentials_path": str(tmp_path / "cred.json")})
    cred = tmp_path / "cred.json"
    cred.write_text("{}")
    state_dir = tmp_path / "_state"
    state_dir.mkdir()
    # cursor 미리 작성
    (state_dir / "cursor.json").write_text(json.dumps({
        "vault_id": "gdrive", "vault_type": "gdrive_api",
        "cursor": "TOKEN_PREV", "cursor_updated_at": "2026-05-13T00:00:00+00:00",
    }))

    # monkeypatch run_gws — changes.list 에 빈 응답
    def fake_run_gws(args, params=None, *, timeout_sec=300, env_extra=None, binary="gws",
                     binary_output=False):
        if args[:3] == ["drive", "changes", "list"]:
            return GwsResult(
                returncode=0,
                stdout=json.dumps({"changes": [], "newStartPageToken": "TOKEN_NEW"}),
                stderr="",
                duration_ms=10,
            )
        raise AssertionError(f"unexpected gws call: {args}")

    monkeypatch.setattr("lib.gws.run_gws", fake_run_gws)
    monkeypatch.setattr("lib.sync.run_gws", fake_run_gws)

    result = sync.sync(
        vault_cfg=vault,
        instance_root=tmp_path,
        state_dir=state_dir,
        credentials_path=cred,
        bootstrap_flag=False,
    )
    assert result.has_changes is False
    assert result.cursor_before == "TOKEN_PREV"
    assert result.cursor_after == "TOKEN_NEW"
    # last_sync.json 작성됐는지
    ls = json.loads((state_dir / "last_sync.json").read_text())
    assert ls["vault_id"] == "gdrive"
    assert ls["has_changes"] is False
    assert ls["cursor_after"] == "TOKEN_NEW"
    # cursor 업데이트됐는지 (I3 정합 — last_sync 다음에)
    cur = json.loads((state_dir / "cursor.json").read_text())
    assert cur["cursor"] == "TOKEN_NEW"


def test_sync_incremental_with_text_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """text/markdown 파일 1개 변경 → wiki page 작성 + file_map 갱신."""
    vault_local = tmp_path / "vault-gdrive"
    vault_local.mkdir()
    vault = VaultConfig(
        id="gdrive", type="gdrive_api", enabled=True, sync_interval_sec=600,
        local_path=vault_local,
        options={"credentials_path": str(tmp_path / "cred.json")},
    )
    cred = tmp_path / "cred.json"
    cred.write_text("{}")
    state_dir = tmp_path / "_state"
    state_dir.mkdir()
    (state_dir / "cursor.json").write_text(json.dumps({
        "vault_id": "gdrive", "vault_type": "gdrive_api",
        "cursor": "T_PREV", "cursor_updated_at": "2026-05-13T00:00:00+00:00",
    }))

    file_meta = {
        "id": "FILE_ABC", "name": "notes/idea.md", "mimeType": "text/markdown",
        "modifiedTime": "2026-05-13T01:00:00+00:00", "size": 50,
        "shared": False, "ownedByMe": True, "parents": ["root"],
    }

    def fake_run_gws(args, params=None, *, timeout_sec=300, env_extra=None, binary="gws",
                     binary_output=False):
        if args[:3] == ["drive", "changes", "list"]:
            return GwsResult(
                returncode=0,
                stdout=json.dumps({
                    "changes": [{"removed": False, "fileId": "FILE_ABC", "file": file_meta}],
                    "newStartPageToken": "T_NEW",
                }),
                stderr="",
                duration_ms=10,
            )
        if args[:3] == ["drive", "files", "get"]:
            return GwsResult(returncode=0, stdout="# hello\n\nbody\n", stderr="", duration_ms=5)
        raise AssertionError(f"unexpected gws call: {args}")

    monkeypatch.setattr("lib.gws.run_gws", fake_run_gws)
    monkeypatch.setattr("lib.sync.run_gws", fake_run_gws)

    result = sync.sync(
        vault_cfg=vault,
        instance_root=tmp_path,
        state_dir=state_dir,
        credentials_path=cred,
        bootstrap_flag=False,
    )
    assert result.has_changes is True
    assert len(result.changed) == 1
    cf = result.changed[0]
    assert cf.source_relpath == "notes/idea.md"
    assert cf.wiki_path == "wiki/sources/gdrive/notes/idea.md"
    assert cf.operation == "created"
    # wiki 페이지 실제 작성됐는지
    wiki_page = tmp_path / "wiki/sources/gdrive/notes/idea.md"
    assert wiki_page.exists()
    text = wiki_page.read_text()
    assert "hello" in text
    assert "title:" in text  # frontmatter
    # vault local 에도 다운로드됐는지
    assert (vault_local / "notes/idea.md").exists()
    # file_map 갱신 (CRIT-4: 즉시 commit)
    fm = json.loads((state_dir / "file_map.json").read_text())
    assert "notes/idea.md" in fm["files"]


def test_sync_removed_change_deletes_wiki_and_vault(tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """SIG-2: removed change 시 wiki + vault binary 둘 다 삭제."""
    vault_local = tmp_path / "vault-gdrive"
    vault_local.mkdir()
    vault = VaultConfig(
        id="gdrive", type="gdrive_api", enabled=True, sync_interval_sec=600,
        local_path=vault_local,
        options={"credentials_path": str(tmp_path / "cred.json")},
    )
    cred = tmp_path / "cred.json"
    cred.write_text("{}")
    state_dir = tmp_path / "_state"
    state_dir.mkdir()
    (state_dir / "cursor.json").write_text(json.dumps({
        "vault_id": "gdrive", "vault_type": "gdrive_api",
        "cursor": "T_PREV", "cursor_updated_at": "2026-05-13T00:00:00+00:00",
    }))
    # file_map 에 기존 파일 등록
    (state_dir / "file_map.json").write_text(json.dumps({
        "vault_id": "gdrive", "updated_at": "2026-05-13T00:00:00+00:00",
        "files": {
            "old.md": {"source_id": "OLD_ID", "source_mtime": "...",
                       "wiki_path": "wiki/sources/gdrive/old.md", "bytes": 10,
                       "last_synced_at": "2026-05-13T00:00:00+00:00"}
        },
    }))
    # 기존 wiki + vault binary 실재
    wiki_old = tmp_path / "wiki/sources/gdrive/old.md"
    wiki_old.parent.mkdir(parents=True, exist_ok=True)
    wiki_old.write_text("# old")
    (vault_local / "old.md").write_text("vault local old")

    def fake_run_gws(args, params=None, *, timeout_sec=300, env_extra=None, binary="gws",
                     binary_output=False):
        if args[:3] == ["drive", "changes", "list"]:
            return GwsResult(
                returncode=0,
                stdout=json.dumps({
                    "changes": [{"removed": True, "fileId": "OLD_ID"}],
                    "newStartPageToken": "T_NEW",
                }),
                stderr="", duration_ms=10,
            )
        raise AssertionError(f"unexpected gws call: {args}")

    monkeypatch.setattr("lib.gws.run_gws", fake_run_gws)
    monkeypatch.setattr("lib.sync.run_gws", fake_run_gws)

    result = sync.sync(
        vault_cfg=vault,
        instance_root=tmp_path,
        state_dir=state_dir,
        credentials_path=cred,
        bootstrap_flag=False,
    )
    assert result.deleted == ["old.md"]
    # wiki + vault local 둘 다 삭제됨
    assert not wiki_old.exists()
    assert not (vault_local / "old.md").exists()
    # file_map 에서도 제거
    fm = json.loads((state_dir / "file_map.json").read_text())
    assert "old.md" not in fm["files"]


# ---------------------------------------------------------------------------
# CRIT-R4-4: binary download bytes round-trip
# ---------------------------------------------------------------------------

def test_sync_incremental_binary_pptx_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CRIT-1·CRIT-R4-4 회귀 방지 — binary 파일은 binary_output=True 경로로
    bytes 손상 없이 vault 에 저장되어야 한다.
    """
    vault_local = tmp_path / "vault-gdrive"
    vault_local.mkdir()
    vault = VaultConfig(
        id="gdrive", type="gdrive_api", enabled=True, sync_interval_sec=600,
        local_path=vault_local,
        options={"credentials_path": str(tmp_path / "cred.json")},
    )
    cred = tmp_path / "cred.json"
    cred.write_text("{}")
    state_dir = tmp_path / "_state"
    state_dir.mkdir()
    (state_dir / "cursor.json").write_text(json.dumps({
        "vault_id": "gdrive", "vault_type": "gdrive_api",
        "cursor": "T_PREV", "cursor_updated_at": "2026-05-13T00:00:00+00:00",
    }))

    # ZIP 헤더 + non-UTF8 byte sequence — text mode 였으면 UTF-8 decode 실패하거나 손상
    pptx_bytes = b"PK\x03\x04" + bytes(range(256)) + b"\xff\xfe\x80\x81"

    file_meta = {
        "id": "FILE_PPTX",
        "name": "decks/Q1.pptx",
        "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "modifiedTime": "2026-05-13T01:00:00+00:00", "size": len(pptx_bytes),
        "shared": False, "ownedByMe": True, "parents": ["root"],
    }

    binary_call_seen = {"flag": False}

    def fake_run_gws(args, params=None, *, timeout_sec=300, env_extra=None,
                     binary="gws", binary_output=False):
        if args[:3] == ["drive", "changes", "list"]:
            return GwsResult(
                returncode=0,
                stdout=json.dumps({
                    "changes": [{"removed": False, "fileId": "FILE_PPTX", "file": file_meta}],
                    "newStartPageToken": "T_NEW",
                }),
                stderr="", duration_ms=10,
            )
        if args[:3] == ["drive", "files", "get"]:
            # CRIT-R4-4: binary 다운로드는 반드시 binary_output=True 로 와야 함
            assert binary_output is True, (
                "binary MIME 다운로드 시 binary_output=True 필수 (CRIT-1 회귀)"
            )
            binary_call_seen["flag"] = True
            return GwsResult(
                returncode=0, stdout="", stderr="",
                duration_ms=5, stdout_bytes=pptx_bytes,
            )
        raise AssertionError(f"unexpected gws call: {args}")

    monkeypatch.setattr("lib.gws.run_gws", fake_run_gws)
    monkeypatch.setattr("lib.sync.run_gws", fake_run_gws)

    sync.sync(
        vault_cfg=vault, instance_root=tmp_path, state_dir=state_dir,
        credentials_path=cred, bootstrap_flag=False,
    )

    assert binary_call_seen["flag"], "binary path 가 실제 호출되지 않음"
    # bytes 가 손상 없이 그대로 disk 에 떨어졌는지 — round-trip 검증
    saved = vault_local / "decks/Q1.pptx"
    assert saved.exists()
    assert saved.read_bytes() == pptx_bytes


# ---------------------------------------------------------------------------
# CRIT-R4-2: subprocess.TimeoutExpired → VaultSyncRetryable
# ---------------------------------------------------------------------------

def test_run_gws_timeout_maps_to_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CRIT-R4-2: gws subprocess timeout 은 VaultSyncRetryable 로 변환되어야 한다."""
    vault = _make_vault_cfg(options={"credentials_path": str(tmp_path / "cred.json")})
    cred = tmp_path / "cred.json"
    cred.write_text("{}")
    state_dir = tmp_path / "_state"
    state_dir.mkdir()
    (state_dir / "cursor.json").write_text(json.dumps({
        "vault_id": "gdrive", "vault_type": "gdrive_api",
        "cursor": "T_PREV", "cursor_updated_at": "2026-05-13T00:00:00+00:00",
    }))

    def fake_run_gws(args, params=None, *, timeout_sec=300, env_extra=None,
                     binary="gws", binary_output=False):
        raise subprocess.TimeoutExpired(cmd=["gws", *args], timeout=timeout_sec)

    monkeypatch.setattr("lib.gws.run_gws", fake_run_gws)
    monkeypatch.setattr("lib.sync.run_gws", fake_run_gws)

    with pytest.raises(VaultSyncRetryable) as exc:
        sync.sync(
            vault_cfg=vault, instance_root=tmp_path, state_dir=state_dir,
            credentials_path=cred, bootstrap_flag=False,
        )
    assert "timeout" in exc.value.reason.lower()


# ---------------------------------------------------------------------------
# CRIT-R4-3: per-file VaultSyncFileFatal → retry queue + 사이클 계속
# ---------------------------------------------------------------------------

def test_sync_per_file_fatal_enqueues_retry_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CRIT-R4-3: 한 파일의 403 insufficientPermissions 가 vault 전체를 stuck 시키면 안 됨.

    시나리오: 2개 changes 중 1번째 파일이 403 fatal → retry queue 등록 + continue.
    2번째 파일은 정상 처리 → file_map 등록 + cursor advance.
    """
    vault_local = tmp_path / "vault-gdrive"
    vault_local.mkdir()
    vault = VaultConfig(
        id="gdrive", type="gdrive_api", enabled=True, sync_interval_sec=600,
        local_path=vault_local,
        options={"credentials_path": str(tmp_path / "cred.json")},
    )
    cred = tmp_path / "cred.json"
    cred.write_text("{}")
    state_dir = tmp_path / "_state"
    state_dir.mkdir()
    (state_dir / "cursor.json").write_text(json.dumps({
        "vault_id": "gdrive", "vault_type": "gdrive_api",
        "cursor": "T_PREV", "cursor_updated_at": "2026-05-13T00:00:00+00:00",
    }))

    forbidden_meta = {
        "id": "FILE_FORBIDDEN", "name": "restricted.md", "mimeType": "text/markdown",
        "modifiedTime": "2026-05-13T01:00:00+00:00", "size": 50,
        "shared": False, "ownedByMe": True, "parents": ["root"],
    }
    ok_meta = {
        "id": "FILE_OK", "name": "notes/ok.md", "mimeType": "text/markdown",
        "modifiedTime": "2026-05-13T01:01:00+00:00", "size": 20,
        "shared": False, "ownedByMe": True, "parents": ["root"],
    }

    def fake_run_gws(args, params=None, *, timeout_sec=300, env_extra=None,
                     binary="gws", binary_output=False):
        if args[:3] == ["drive", "changes", "list"]:
            return GwsResult(
                returncode=0,
                stdout=json.dumps({
                    "changes": [
                        {"removed": False, "fileId": "FILE_FORBIDDEN", "file": forbidden_meta},
                        {"removed": False, "fileId": "FILE_OK", "file": ok_meta},
                    ],
                    "newStartPageToken": "T_NEW",
                }),
                stderr="", duration_ms=10,
            )
        if args[:3] == ["drive", "files", "get"]:
            assert params is not None
            if params.get("fileId") == "FILE_FORBIDDEN":
                # 403 insufficientPermissions → errors.py 가 scope=file fatal 로 분류
                return GwsResult(
                    returncode=1, stdout="",
                    stderr='HttpError 403: insufficientPermissions for fileId',
                    duration_ms=5,
                )
            if params.get("fileId") == "FILE_OK":
                return GwsResult(returncode=0, stdout="# ok\n", stderr="", duration_ms=5)
        raise AssertionError(f"unexpected gws call: {args} params={params}")

    monkeypatch.setattr("lib.gws.run_gws", fake_run_gws)
    monkeypatch.setattr("lib.sync.run_gws", fake_run_gws)

    result = sync.sync(
        vault_cfg=vault, instance_root=tmp_path, state_dir=state_dir,
        credentials_path=cred, bootstrap_flag=False,
    )
    # vault 사이클 자체는 성공해야 함 (per-file fatal 이 vault stuck 안 시킴)
    assert result.cursor_after == "T_NEW"
    # 정상 파일은 처리됨
    assert len(result.changed) == 1
    assert result.changed[0].source_relpath == "notes/ok.md"

    # cursor advance 확인 — 다음 사이클에 같은 차단을 또 만나지 않음
    cur = json.loads((state_dir / "cursor.json").read_text())
    assert cur["cursor"] == "T_NEW"

    # 차단된 파일은 retry queue 에 등록
    retry = json.loads((state_dir / "retry.json").read_text())
    assert len(retry["queue"]) == 1
    item = retry["queue"][0]
    assert item["source_relpath"] == "restricted.md"
    assert item["source_id"] == "FILE_FORBIDDEN"
    assert "file-fatal" in item["failure_reason"]


# ---------------------------------------------------------------------------
# CRIT-R4-1: _download_to_vault invariant — sanitized source_relpath 만 받음
# ---------------------------------------------------------------------------

def test_download_to_vault_rejects_absolute_source_relpath(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CRIT-R4-1 defense-in-depth — invariant 위반 시 VaultSyncFatal.

    실제 운영 시에는 caller(_sync_loop) 가 _sanitize_relpath 통과한 값만 전달하지만,
    내부 buggy refactor 시 즉시 fail-loud 하도록.
    """
    from lib.sync import _download_to_vault

    vault_local = tmp_path / "vault-gdrive"
    vault_local.mkdir()

    def fake_run_gws(*a, **kw):
        raise AssertionError("must not reach gws — invariant 검사가 먼저")

    monkeypatch.setattr("lib.sync.run_gws", fake_run_gws)

    with pytest.raises(VaultSyncFatal) as exc:
        _download_to_vault(
            "gdrive", {"GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE": "/tmp/x"},
            {"id": "X", "name": "/abs/escape", "mimeType": "text/markdown"},
            vault_local,
            source_relpath="/abs/escape",  # invariant 위반 — absolute
            max_file_size_mb=None,
        )
    assert "invariant" in exc.value.reason


# ---------------------------------------------------------------------------
# vault-fetch.py 의 file lock 호출 invariant — HIGH-R4-2
#
# 동시 invocation 의 e2e 검증은 wikihub.yaml 전체 schema + assert_credentials 통과가
# 필요해서 무겁다. fcntl.flock(LOCK_EX|LOCK_NB) 자체는 표준 POSIX 동작 — 통합 검증은
# v0.2.x 의 V8 시점(systemd timer 와 함께)으로 미루고, 여기서는 source 에 lock 호출이
# 실제 들어있는지 정적으로 보장.
# ---------------------------------------------------------------------------

def test_vault_fetch_uses_fcntl_flock_for_concurrency_lock() -> None:
    """HIGH-R4-2 회귀 방지 — vault-fetch.py 에서 fcntl.flock 호출이 제거되지 않도록."""
    src = (Path(__file__).parent.parent / "scripts" / "vault-fetch.py").read_text()
    assert "import fcntl" in src
    assert "fcntl.flock" in src
    assert "LOCK_EX" in src
    assert "LOCK_NB" in src
