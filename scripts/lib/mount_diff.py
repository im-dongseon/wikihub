"""rclone lsjson listing 과 file_map 의 diff — 변경 감지 (ADR-0035).

ADR-0027 의 cursor 기반 changes API 자리를 lsjson full snapshot diff 가 대체.
file_map primary key 는 ``source_id`` (Drive fileId, ADR-0035 §state schema 갱신).

diff 4 분류:
- ``created``  — listing 의 ID 가 file_map 에 없음
- ``modified`` — ID 동일, ModTime 변경
- ``renamed``  — ID 동일, Path 변경 (ModTime 비교 무관 — 별도 modified 사이클에서 처리)
- ``deleted``  — file_map 의 ID 가 listing 에 없음

trust boundary filter:
- mount source path 자체가 boundary (ADR-0035 §Note 2026-05-19) — yaml.options.rclone_remote_path
  로 좁힘. lsjson 호출이 ``<remote>:<path>`` 단위로 같은 scope 조회.
- v0.1.0 추가 filter: ``exclude_shared_with_me`` 만 적용. (SA 시절 root_folder_id 는 폐기.)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("vault-fetch.mount_diff")


@dataclass
class DiffEntry:
    operation: str  # 'created' | 'modified' | 'renamed' | 'deleted'
    source_id: str
    source_relpath: str
    prev_source_relpath: str | None = None
    mime_type: str = ""
    mtime: str = ""
    size: int = 0
    is_dir: bool = False


@dataclass
class DiffResult:
    entries: list[DiffEntry] = field(default_factory=list)
    listing_count: int = 0
    file_map_count_before: int = 0

    @property
    def deleted_count(self) -> int:
        return sum(1 for e in self.entries if e.operation == "deleted")

    @property
    def delete_ratio(self) -> float:
        if self.file_map_count_before == 0:
            return 0.0
        return self.deleted_count / self.file_map_count_before


def _is_indexable(item: dict[str, Any], vault_type: str = "gdrive_api") -> bool:
    """디렉토리·null ID 항목은 file_map 대상이 아님.
    
    NAS vault는 ID가 공백이므로 Path 기반으로 판단.
    """
    if item.get("IsDir"):
        return False
    if vault_type == "nas":
        # NAS vault: Path 기반 (ID 부재)
        return bool(item.get("Path"))
    else:
        # Drive vault: ID 기반
        return bool(item.get("ID"))


def compute_diff(
    listing: list[dict[str, Any]],
    file_map: dict[str, Any],
    *,
    vault_type: str = "gdrive_api",
    exclude_shared_with_me: bool = True,
) -> DiffResult:
    """rclone lsjson 결과 + file_map → DiffResult.

    Args:
        listing: rclone.lsjson() 의 반환값 (list[dict]).
        file_map: state.load_file_map() 의 반환값. After schema — files 는 source_id 키.
        vault_type: vault 유형 ("gdrive_api" 또는 "nas"). NAS는 path 기반 diff.
        exclude_shared_with_me: ADR-0035 — rclone lsjson default 가 sharedWithMe 제외 동작과
            정합 (`--drive-shared-with-me` 미지정 시). 본 인자는 향후 옵션 변경 시 hook —
            v0.1.0 은 lsjson default 에 위임.
    """
    _ = exclude_shared_with_me  # ADR-0035 — lsjson default 에 위임 (위 docstring 참조)
    
    if vault_type == "nas":
        return _compute_diff_path_based(listing, file_map)
    
    # Drive vault: ID 기반 diff (기존 로직)
    listing_filtered = [item for item in listing if _is_indexable(item, vault_type)]
    listing_by_id: dict[str, dict[str, Any]] = {item["ID"]: item for item in listing_filtered}

    files = file_map.get("files", {})
    file_map_count_before = len(files)

    result = DiffResult(
        listing_count=len(listing_filtered),
        file_map_count_before=file_map_count_before,
    )

    # created / modified / renamed
    for source_id, item in listing_by_id.items():
        path = str(item.get("Path", ""))
        mime = str(item.get("MimeType", ""))
        mtime = str(item.get("ModTime", ""))
        size = int(item.get("Size", 0) or 0)
        prev = files.get(source_id)
        if prev is None:
            result.entries.append(DiffEntry(
                operation="created",
                source_id=source_id,
                source_relpath=path,
                mime_type=mime,
                mtime=mtime,
                size=size,
            ))
            continue
        prev_relpath = str(prev.get("source_relpath", ""))
        prev_mtime = str(prev.get("source_mtime", ""))
        if prev_relpath != path:
            result.entries.append(DiffEntry(
                operation="renamed",
                source_id=source_id,
                source_relpath=path,
                prev_source_relpath=prev_relpath,
                mime_type=mime,
                mtime=mtime,
                size=size,
            ))
            continue
        if prev_mtime != mtime:
            result.entries.append(DiffEntry(
                operation="modified",
                source_id=source_id,
                source_relpath=path,
                mime_type=mime,
                mtime=mtime,
                size=size,
            ))
            continue
        # unchanged — diff 에 포함 안 함

    # deleted — file_map 에 있으나 listing 에 없음
    for source_id, prev in files.items():
        if source_id in listing_by_id:
            continue
        result.entries.append(DiffEntry(
            operation="deleted",
            source_id=source_id,
            source_relpath=str(prev.get("source_relpath", "")),
            prev_source_relpath=str(prev.get("source_relpath", "")),
        ))

    log.info(
        "mount_diff: listing=%d file_map_before=%d entries=%d "
        "(created=%d modified=%d renamed=%d deleted=%d) delete_ratio=%.2f",
        result.listing_count,
        result.file_map_count_before,
        len(result.entries),
        sum(1 for e in result.entries if e.operation == "created"),
        sum(1 for e in result.entries if e.operation == "modified"),
        sum(1 for e in result.entries if e.operation == "renamed"),
        result.deleted_count,
        result.delete_ratio,
    )
    return result


def _compute_diff_path_based(
    listing: list[dict[str, Any]],
    file_map: dict[str, Any],
) -> DiffResult:
    """NAS vault용 path 기반 diff.

    SFTP backend는 ID가 공백이므로 Path를 기준으로 diff 수행.
    - created: Path가 file_map에 없음
    - modified: Path 동일, ModTime 변경
    - renamed: 생성 안 함 (old path deleted + new path created로 분해)
    - deleted: file_map의 Path가 listing에 없음
    """
    listing_filtered = [item for item in listing if _is_indexable(item, "nas")]
    listing_by_path: dict[str, dict[str, Any]] = {item["Path"]: item for item in listing_filtered}

    files = file_map.get("files", {})
    # file_map을 path 기반으로 변환 (source_relpath를 key로 사용)
    files_by_path: dict[str, dict[str, Any]] = {}
    for source_id, file_data in files.items():
        path = str(file_data.get("source_relpath", ""))
        if path:
            # ADR-0045: 레거시 source_id="" entry 감지 시 경고
            if source_id == "":
                log.warning(
                    "legacy NAS file_map entry detected: source_id=\"\" path=%s. "
                    "This entry will be migrated to source_id=path on next write (ADR-0045).",
                    path,
                )
            files_by_path[path] = {**file_data, "_source_id": source_id}

    file_map_count_before = len(files)
    result = DiffResult(
        listing_count=len(listing_filtered),
        file_map_count_before=file_map_count_before,
    )

    # created / modified (renamed 없음 — path 기반)
    for path, item in listing_by_path.items():
        mime = str(item.get("MimeType", ""))
        mtime = str(item.get("ModTime", ""))
        size = int(item.get("Size", 0) or 0)
        prev = files_by_path.get(path)
        if prev is None:
            result.entries.append(DiffEntry(
                operation="created",
                source_id=path,  # NAS vault는 path를 source_id로 사용 (ADR-0045)
                source_relpath=path,
                mime_type=mime,
                mtime=mtime,
                size=size,
            ))
            continue
        prev_mtime = str(prev.get("source_mtime", ""))
        if prev_mtime != mtime:
            result.entries.append(DiffEntry(
                operation="modified",
                source_id=prev.get("_source_id", ""),
                source_relpath=path,
                mime_type=mime,
                mtime=mtime,
                size=size,
            ))
        # unchanged — diff 에 포함 안 함

    # deleted — file_map 에 있으나 listing 에 없음
    for path, prev in files_by_path.items():
        if path in listing_by_path:
            continue
        result.entries.append(DiffEntry(
            operation="deleted",
            source_id=prev.get("_source_id", ""),
            source_relpath=path,
            prev_source_relpath=path,
        ))

    log.info(
        "mount_diff (path-based): listing=%d file_map_before=%d entries=%d "
        "(created=%d modified=%d renamed=%d deleted=%d) delete_ratio=%.2f",
        result.listing_count,
        result.file_map_count_before,
        len(result.entries),
        sum(1 for e in result.entries if e.operation == "created"),
        sum(1 for e in result.entries if e.operation == "modified"),
        sum(1 for e in result.entries if e.operation == "renamed"),
        result.deleted_count,
        result.delete_ratio,
    )
    return result


__all__ = ["DiffEntry", "DiffResult", "compute_diff"]
