"""vault sync orchestration — ADR-0035 정본 (gws 폐기 + rclone lsjson + mount_diff).

흐름:
1. rclone lsjson <remote>: --recursive  → 현재 vault listing
2. load_file_map(state_dir)              → 이전 사이클 결과 (After schema, source_id 키)
3. compute_diff(listing, file_map)       → DiffResult (created/modified/renamed/deleted)
4. false-deleted 가드 — listing 0건 또는 delete_ratio > threshold 면 Retryable
5. for each entry:
     - created/modified: mount FS open + extraction → wiki page atomic write
     - renamed: wiki page mv + file_map source_relpath 갱신
     - deleted: wiki page unlink + file_map entry 제거
6. file_map 즉시 commit (per-entry) — 사이클 중단 시 N-1 commit 보존
7. last_sync.json 저장
8. stdout JSON emit (F2 ingest.md §Step 2 contract)
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import VaultConfig
from .exceptions import VaultSyncFatal, VaultSyncFileFatal, VaultSyncRetryable
from .extraction import GWS_EXPORT_MIME, ExtractionResult, extract, extract_text
from .frontmatter import build_source_frontmatter, emit_page
from .mount_diff import DiffEntry, DiffResult, compute_diff
from .rclone import lsjson
from .state import (
    enqueue_retry,
    load_file_map,
    load_retry,
    save_file_map,
    save_last_sync,
    save_retry,
    utc_now_iso,
)

log = logging.getLogger("vault-fetch.sync")

# 파일명 안전성 — control char + 백슬래시 차단
_INVALID_NAME_CHARS = re.compile(r"[\x00-\x1f\\]")

# Google native mimeType → mount 의 export-formats 우선순위 매핑 (ADR-0025 §β2 정합).
# mount template `--drive-export-formats docx,xlsx,pptx,md` 의 첫 매치 우선순위.
_NATIVE_MIME_TO_EXT: dict[str, str] = {
    "application/vnd.google-apps.document": ".docx",
    "application/vnd.google-apps.spreadsheet": ".xlsx",
    "application/vnd.google-apps.presentation": ".pptx",
}


@dataclass
class ChangedFile:
    source_relpath: str
    wiki_path: str
    operation: str  # 'created' | 'modified' | 'renamed'
    source_id: str | None
    source_mtime: str
    bytes_written: int


@dataclass
class SyncResult:
    vault_id: str
    has_changes: bool
    changed: list[ChangedFile] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    file_map_count_before: int = 0
    listing_count: int = 0
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Filtering & path computation
# ---------------------------------------------------------------------------

def _sanitize_relpath(raw: str) -> str | None:
    """traversal · invalid char 차단. 부적합 시 None.

    rclone lsjson 의 ``Path`` 는 mount 의 relative path — Drive 운영자 제어 입력.
    ``../`` 절대경로, control char 차단 후 vault 경계 안에만 저장.
    """
    if not raw:
        return None
    candidate = raw.lstrip("/").strip()
    if not candidate:
        return None
    if _INVALID_NAME_CHARS.search(candidate):
        return None
    parts = Path(candidate).parts
    if not parts:
        return None
    if any(p in ("..", ".", "") for p in parts):
        return None
    if Path(candidate).is_absolute():
        return None
    return candidate


def _virtual_ext_for_native(mime: str) -> str:
    return {
        "application/vnd.google-apps.document": ".gdoc",
        "application/vnd.google-apps.spreadsheet": ".gsheet",
        "application/vnd.google-apps.presentation": ".gslides",
    }.get(mime, "")


def _compute_wiki_path(vault_id: str, source_relpath: str, mime_type: str) -> str:
    """wiki-schema.md §A2 파일명 규약.

    - binary (.pptx 등): <relpath>.<ext>.md
    - text .md: <relpath>.md (중복 회피)
    - Google native: <relpath>.<virtual_ext>.md
    - 기타 (.txt 포함): <relpath>.<ext>.md
    """
    if mime_type in GWS_EXPORT_MIME:
        virt = _virtual_ext_for_native(mime_type)
        if virt and not source_relpath.endswith(virt):
            return f"wiki/sources/{vault_id}/{source_relpath}{virt}.md"
        return f"wiki/sources/{vault_id}/{source_relpath}.md"
    if source_relpath.endswith(".md"):
        return f"wiki/sources/{vault_id}/{source_relpath}"
    return f"wiki/sources/{vault_id}/{source_relpath}.md"


# ---------------------------------------------------------------------------
# Mount FS read & extraction
# ---------------------------------------------------------------------------

def _read_from_mount(
    vault_id: str,
    source_id: str,
    source_relpath: str,
    mime: str,
    vault_local_path: Path,
    *,
    max_file_size_mb: int | None,
) -> tuple[ExtractionResult, int]:
    """mount FS 의 파일 read + extraction (ADR-0025 Path C+ 의 read 경로 유지).

    Google native 의 mount path lookup 은 ``_NATIVE_MIME_TO_EXT`` 매핑으로 suffix 적용
    (mount 의 ``--drive-export-formats`` 우선순위 정합).

    Returns:
        (extraction_result, bytes_written). 실패 시 ExtractionResult 의 status="failed".
    """
    mount_relpath = source_relpath
    if mime in _NATIVE_MIME_TO_EXT:
        ext = _NATIVE_MIME_TO_EXT[mime]
        if not mount_relpath.endswith(ext):
            mount_relpath = mount_relpath + ext
    saved = vault_local_path / mount_relpath

    # defense-in-depth: vault_local_path 경계 escape 차단
    vault_resolved = vault_local_path.resolve()
    try:
        saved.resolve().relative_to(vault_resolved)
    except ValueError as e:
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=f"vault_local_path escape detected: saved={saved}",
            remediation="caller sanitize 결함 — _sanitize_relpath 추가 검토.",
        ) from e

    if not saved.exists():
        log.warning("mount path 미존재 (vfs cache miss 가능): vault=%s id=%s path=%s",
                    vault_id, source_id, saved)
        return ExtractionResult(
            body_text=f"[extraction failed: mount path 미존재 — vfs_refresh 누락 또는 mount stale: {saved}]",
            tool="mount-read",
            tool_version="n/a",
            extraction_status="failed",
            reason="mount-path-missing",
        ), 0

    size_cap_bytes = max_file_size_mb * 1024 * 1024 if max_file_size_mb else None
    is_text_mime = mime.startswith("text/") or mime in ("application/json",)
    is_native = mime in GWS_EXPORT_MIME

    try:
        if is_text_mime:
            content = saved.read_text(encoding="utf-8")
            bytes_written = len(content.encode("utf-8"))
            if size_cap_bytes and bytes_written > size_cap_bytes:
                return ExtractionResult(
                    body_text=f"[extraction failed: read {bytes_written}B exceeds limit {max_file_size_mb}MB]",
                    tool="size-check",
                    tool_version="n/a",
                    extraction_status="failed",
                    reason=f"oversize: {bytes_written}B > {max_file_size_mb}MB",
                ), 0
            er = extract_text(saved)
        elif is_native:
            data = saved.read_bytes()
            bytes_written = len(data)
            if bytes_written == 0:
                log.warning("mount native export empty: vault=%s id=%s mime=%s path=%s",
                            vault_id, source_id, mime, saved)
                return ExtractionResult(
                    body_text=f"[extraction failed: native export empty for {mime} at {saved}]",
                    tool="mount-native-export",
                    tool_version="n/a",
                    extraction_status="failed",
                    reason="empty native export",
                ), 0
            er = extract(saved, mime)
        else:
            data = saved.read_bytes()
            bytes_written = len(data)
            if size_cap_bytes and bytes_written > size_cap_bytes:
                return ExtractionResult(
                    body_text=f"[extraction failed: read {bytes_written}B exceeds limit {max_file_size_mb}MB]",
                    tool="size-check",
                    tool_version="n/a",
                    extraction_status="failed",
                    reason=f"oversize: {bytes_written}B > {max_file_size_mb}MB",
                ), 0
            er = extract(saved, mime)
    except OSError as e:
        log.error("mount read OSError: vault=%s id=%s path=%s err=%s",
                  vault_id, source_id, saved, e)
        return ExtractionResult(
            body_text=f"[extraction failed: mount FS read OSError errno={e.errno}: {saved}]",
            tool="mount-read",
            tool_version="n/a",
            extraction_status="failed",
            reason=f"mount-read-oserror: errno={e.errno}",
        ), 0

    return er, bytes_written


# ---------------------------------------------------------------------------
# wiki page atomic write
# ---------------------------------------------------------------------------

def _atomic_write_wiki_page(full_path: Path, content: str) -> None:
    """tempfile + fsync + os.replace 패턴 (state._atomic_write_json 과 통일)."""
    full_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=f".{full_path.name}.",
        suffix=".tmp",
        dir=str(full_path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, full_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Per-entry handlers
# ---------------------------------------------------------------------------

def _handle_create_or_modify(
    entry: DiffEntry,
    *,
    vault_id: str,
    vault_local_path: Path,
    instance_root: Path,
    file_map: dict,
    state_dir: Path,
    started_iso: str,
    max_file_size_mb: int | None,
    changed_out: list[ChangedFile],
) -> None:
    source_relpath = _sanitize_relpath(entry.source_relpath)
    if not source_relpath:
        log.warning("skip (invalid relpath): id=%s raw=%r", entry.source_id, entry.source_relpath)
        return
    wiki_path_rel = _compute_wiki_path(vault_id, source_relpath, entry.mime_type)
    log.info("process %s: id=%s mime=%s op=%s",
             source_relpath, entry.source_id, entry.mime_type, entry.operation)

    er, bytes_written = _read_from_mount(
        vault_id=vault_id,
        source_id=entry.source_id,
        source_relpath=source_relpath,
        mime=entry.mime_type,
        vault_local_path=vault_local_path,
        max_file_size_mb=max_file_size_mb,
    )
    extraction_ok = er.extraction_status == "success"
    title = source_relpath
    fm_dict = build_source_frontmatter(
        title=title,
        vault_id=vault_id,
        relpath=source_relpath,
        source_id=entry.source_id,
        source_mtime=entry.mtime,
        last_synced_at=utc_now_iso(),
        extraction_tool=er.tool if extraction_ok else None,
        extraction_tool_version=er.tool_version if extraction_ok else None,
        extracted_at=utc_now_iso(),
        created=started_iso.split("T")[0],
        updated=started_iso.split("T")[0],
    )
    page_text = emit_page(fm_dict, er.body_text)
    _atomic_write_wiki_page(instance_root / wiki_path_rel, page_text)

    file_map["files"][entry.source_id] = {
        "source_relpath": source_relpath,
        "source_mtime": entry.mtime,
        "wiki_path": wiki_path_rel,
        "bytes": bytes_written,
        "last_synced_at": utc_now_iso(),
    }
    changed_out.append(ChangedFile(
        source_relpath=source_relpath,
        wiki_path=wiki_path_rel,
        operation=entry.operation,
        source_id=entry.source_id,
        source_mtime=entry.mtime,
        bytes_written=bytes_written,
    ))
    save_file_map(state_dir, file_map)


def _handle_rename(
    entry: DiffEntry,
    *,
    vault_id: str,
    vault_local_path: Path,
    instance_root: Path,
    file_map: dict,
    state_dir: Path,
    started_iso: str,
    max_file_size_mb: int | None,
    changed_out: list[ChangedFile],
) -> None:
    """rename — 새 path 로 write 성공 후에만 old wiki unlink (atomicity 가드).

    Drive 의 fileId 는 stable, name 만 변경. 순서:
      1. 새 path 로 read + extraction + atomic write (raise 시 old wiki 그대로 보존)
      2. file_map[source_id] 갱신 (_handle_create_or_modify 내부)
      3. old wiki path 가 새 path 와 다르면 unlink

    이전 구현은 1번 이전에 unlink 했지만, _read_from_mount 가 raise 시
    old·new 모두 부재 윈도우 → 사이클 종료 시 wiki partial state. M4 fix.
    """
    new_relpath = _sanitize_relpath(entry.source_relpath)
    if not new_relpath:
        log.warning("rename skip (invalid new relpath): id=%s raw=%r",
                    entry.source_id, entry.source_relpath)
        return
    prev_entry = file_map["files"].get(entry.source_id)
    prev_wiki_path = str(prev_entry.get("wiki_path", "")) if prev_entry else ""

    # 1~2. 새 path 로 write + file_map 갱신 (실패 시 old wiki 그대로 보존)
    _handle_create_or_modify(
        entry,
        vault_id=vault_id,
        vault_local_path=vault_local_path,
        instance_root=instance_root,
        file_map=file_map,
        state_dir=state_dir,
        started_iso=started_iso,
        max_file_size_mb=max_file_size_mb,
        changed_out=changed_out,
    )

    # 3. old wiki unlink (새 path 와 다른 경우만 — 동일 경로면 이미 overwrite 됨)
    new_entry = file_map["files"].get(entry.source_id)
    new_wiki_path = str(new_entry.get("wiki_path", "")) if new_entry else ""
    if prev_wiki_path and prev_wiki_path != new_wiki_path:
        old_wiki = instance_root / prev_wiki_path
        old_wiki.unlink(missing_ok=True)
        log.info("rename: unlink old wiki %s (new=%s)", old_wiki, new_wiki_path)


def _handle_delete(
    entry: DiffEntry,
    *,
    file_map: dict,
    instance_root: Path,
    state_dir: Path,
    deleted_out: list[str],
) -> None:
    """deleted — wiki page unlink + file_map entry 제거.

    mount FS 의 vault binary 는 rclone vfs 가 자동 정리 — unlink 하지 않음 (Drive 원본 보호).
    """
    prev = file_map["files"].get(entry.source_id)
    if not prev:
        log.info("delete (untracked): id=%s", entry.source_id)
        return
    wiki_rel = str(prev.get("wiki_path", ""))
    if wiki_rel:
        (instance_root / wiki_rel).unlink(missing_ok=True)
    deleted_out.append(str(prev.get("source_relpath", entry.source_id)))
    del file_map["files"][entry.source_id]
    save_file_map(state_dir, file_map)
    log.info("delete: id=%s wiki=%s", entry.source_id, wiki_rel)


# ---------------------------------------------------------------------------
# 종합 흐름
# ---------------------------------------------------------------------------

def sync(
    *,
    vault_cfg: VaultConfig,
    instance_root: Path,
    state_dir: Path,
) -> SyncResult:
    """vault sync orchestration — vault-fetch.py 에서 진입.

    ADR-0035: gws 폐기 + rclone lsjson + mount_diff. cursor 모델 폐기.
    """
    started = time.monotonic()
    started_iso = utc_now_iso()
    vault_id = vault_cfg.id
    options = dict(vault_cfg.options)
    remote = str(options.get("rclone_remote_name") or vault_id)
    remote_path = str(options.get("rclone_remote_path") or "")
    exclude_swm = bool(options.get("exclude_shared_with_me", True))
    max_file_size_mb = options.get("max_file_size_mb")
    false_delete_threshold = float(options.get("false_delete_threshold", 0.3))

    log.info("sync start: vault=%s remote=%s path=%s exclude_swm=%s",
             vault_id, remote, remote_path or "", exclude_swm)

    # 1. lsjson 호출 — mount source 와 동일 scope (ADR-0035 §Note 2026-05-19).
    listing = lsjson(remote, path=remote_path, recursive=True, vault_id=vault_id)

    # 2. file_map 로드 + retry 로드
    file_map = load_file_map(state_dir)
    if "files" not in file_map:
        file_map["files"] = {}
    if not file_map.get("vault_id"):
        file_map["vault_id"] = vault_id
    retry_obj = load_retry(state_dir)
    if not retry_obj.get("vault_id"):
        retry_obj["vault_id"] = vault_id
        retry_obj.setdefault("next_id", 1)
        retry_obj.setdefault("queue", [])

    # 3. diff 계산
    diff = compute_diff(
        listing,
        file_map,
        exclude_shared_with_me=exclude_swm,
    )

    # 4. false-deleted 가드 (ADR-0035 §ζ2)
    if diff.listing_count == 0 and diff.file_map_count_before > 0:
        raise VaultSyncRetryable(
            vault_id=vault_id,
            retry_after_sec=300,
            reason=(
                f"rclone lsjson listing 0건 (file_map_before={diff.file_map_count_before}) — "
                "mount/auth 부분 장애 의심"
            ),
        )
    if diff.file_map_count_before > 0 and diff.delete_ratio > false_delete_threshold:
        raise VaultSyncRetryable(
            vault_id=vault_id,
            retry_after_sec=300,
            reason=(
                f"삭제 비율 {diff.delete_ratio:.0%} > 임계 {false_delete_threshold:.0%} "
                f"(deleted={diff.deleted_count}, file_map_before={diff.file_map_count_before}) — "
                "listing partial 의심"
            ),
        )

    # 5. per-entry 처리
    changed: list[ChangedFile] = []
    deleted: list[str] = []
    error_count = 0

    for entry in diff.entries:
        try:
            if entry.operation == "deleted":
                _handle_delete(
                    entry,
                    file_map=file_map,
                    instance_root=instance_root,
                    state_dir=state_dir,
                    deleted_out=deleted,
                )
            elif entry.operation == "renamed":
                _handle_rename(
                    entry,
                    vault_id=vault_id,
                    vault_local_path=vault_cfg.local_path,
                    instance_root=instance_root,
                    file_map=file_map,
                    state_dir=state_dir,
                    started_iso=started_iso,
                    max_file_size_mb=max_file_size_mb,
                    changed_out=changed,
                )
            else:  # created | modified
                _handle_create_or_modify(
                    entry,
                    vault_id=vault_id,
                    vault_local_path=vault_cfg.local_path,
                    instance_root=instance_root,
                    file_map=file_map,
                    state_dir=state_dir,
                    started_iso=started_iso,
                    max_file_size_mb=max_file_size_mb,
                    changed_out=changed,
                )
        except VaultSyncRetryable as e:
            log.warning("per-entry retryable: %s", e)
            enqueue_retry(
                retry_obj,
                source_relpath=entry.source_relpath or entry.source_id,
                source_id=entry.source_id,
                operation=entry.operation,
                failure_reason=str(e),
                next_retry_at=utc_now_iso(),
            )
            save_retry(state_dir, retry_obj)
            error_count += 1
            continue
        except VaultSyncFileFatal as e:
            log.error("per-entry file fatal: %s", e)
            enqueue_retry(
                retry_obj,
                source_relpath=entry.source_relpath or entry.source_id,
                source_id=entry.source_id,
                operation=entry.operation,
                failure_reason=f"file-fatal: {e.reason}",
                next_retry_at=utc_now_iso(),
            )
            save_retry(state_dir, retry_obj)
            error_count += 1
            continue
        except VaultSyncFatal:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("per-entry unexpected error: %s", e)
            error_count += 1
            continue

    duration_ms = int((time.monotonic() - started) * 1000)
    finished_iso = utc_now_iso()
    result = SyncResult(
        vault_id=vault_id,
        has_changes=bool(changed or deleted),
        changed=changed,
        deleted=deleted,
        file_map_count_before=diff.file_map_count_before,
        listing_count=diff.listing_count,
        started_at=started_iso,
        finished_at=finished_iso,
        duration_ms=duration_ms,
    )

    save_last_sync(state_dir, _result_to_last_sync_dict(result))

    log.info(
        "sync ok: vault=%s changed=%d deleted=%d errors=%d duration_ms=%d",
        vault_id, len(changed), len(deleted), error_count, duration_ms,
    )
    return result


def _result_to_last_sync_dict(result: SyncResult) -> dict:
    return {
        "vault_id": result.vault_id,
        "has_changes": result.has_changes,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "duration_ms": result.duration_ms,
        "file_map_count_before": result.file_map_count_before,
        "listing_count": result.listing_count,
        "changed": [asdict(c) for c in result.changed],
        "deleted": list(result.deleted),
    }


def result_to_stdout_json(result: SyncResult) -> str:
    """F2 ingest.md §Step 2 contract emit (stdout JSON)."""
    return json.dumps(
        {
            "vault_id": result.vault_id,
            "has_changes": result.has_changes,
            "changed": [asdict(c) for c in result.changed],
            "deleted": result.deleted,
            "duration_ms": result.duration_ms,
        },
        ensure_ascii=False,
    )


__all__ = ["ChangedFile", "SyncResult", "sync", "result_to_stdout_json"]
