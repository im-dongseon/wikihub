"""vault sync orchestration — F3 §2.5/2.6 정본.

흐름:
1. cursor 존재 여부 → bootstrap 가드 (F1 §4.4.6 lift, B2 정합)
2. bootstrap: gws drive files list (pagination) → 전체 스캔
   incremental: gws drive changes list(pageToken=cursor)
3. 각 file: gws drive files get/export → vault_local_path 에 저장
4. extraction → wiki page write (frontmatter + body, ADR-0001 정합)
5. file_map 즉시 갱신 (CRIT-4 — 사이클 중단 시 N-1 commit 보존)
6. 사이클 끝: last_sync.json 저장 후 cursor 저장 (I3 — partial-failure window 차단)
7. stdout JSON emit (F2 ingest.md §Step 2 contract)

Step 3 verification 미실증 부분은 ``# V<N>`` 주석으로 표시.

Code review (Step 4) 수정 반영:
- CRIT-1: 바이너리 다운로드 binary_output=True (gws.py)
- CRIT-2: _atomic_write_wiki_page tempfile 패턴 통일
- CRIT-3: _sanitize_relpath traversal 차단
- CRIT-4: 파일별 file_map 즉시 commit
- CRIT/SIG-6: incremental 에서도 root_folder_id post-filter
- I1: dead-code ternary 수정 (failed 시 tool=None)
- I3: cursor save 를 last_sync 뒤로 이동
- SIG-1: last_sync.json schema 명시적 dict
- SIG-2: removed 시 vault binary 도 삭제
- SIG-3: max_file_size_mb 적용
- SIG-5: per-file 에러 시 enqueue_retry + 사이클 계속
- Obs: log.info 사이클 가시화
- Q4: _download_to_vault 반환값 정리 (saved_path 제거)
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import VaultConfig
from .credentials import ensure_env_var
from .errors import classify_gws_error
from .exceptions import VaultSyncFatal, VaultSyncFileFatal, VaultSyncRetryable
from .extraction import GWS_EXPORT_MIME, ExtractionResult, extract, extract_text
from .frontmatter import build_source_frontmatter, emit_page
from .gws import GwsBinaryMissing, GwsResult, run_gws
from .state import (
    enqueue_retry,
    has_cursor,
    load_cursor,
    load_file_map,
    load_retry,
    save_cursor,
    save_file_map,
    save_last_sync,
    save_retry,
    utc_now_iso,
)

log = logging.getLogger("vault-fetch.sync")

# CRIT-3: 파일명에 허용 안 되는 char (control + 슬래시 + 백슬래시)
_INVALID_NAME_CHARS = re.compile(r"[\x00-\x1f\\]")


@dataclass
class ChangedFile:
    source_relpath: str
    wiki_path: str
    operation: str  # 'created' | 'modified'
    source_id: str | None
    source_mtime: str
    bytes_written: int


@dataclass
class SyncResult:
    vault_id: str
    has_changes: bool
    changed: list[ChangedFile] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    cursor_before: str = ""
    cursor_after: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# gws 호출 helpers
# ---------------------------------------------------------------------------

def _run(vault_id: str, args: list[str], params: dict | None, *,
         env_extra: dict[str, str], timeout_sec: int = 300,
         binary_output: bool = False, source_id: str | None = None) -> GwsResult:
    """gws subprocess 실행 + wikihub 예외 변환.

    Args:
        source_id: per-file 호출이면 fileId — VaultSyncFileFatal 의 진단 메타.
            None 이면 vault-level 호출(changes.list 등).

    Raises:
        VaultSyncRetryable: timeout / 5xx / quota / 네트워크 일시 장애.
        VaultSyncFileFatal: scope=file 결함 (예: 한 파일의 403 insufficientPermissions).
        VaultSyncFatal: scope=vault 결함 (예: 401, gws auth/discovery error).
    """
    try:
        result = run_gws(args, params=params, timeout_sec=timeout_sec,
                         env_extra=env_extra, binary_output=binary_output)
    except GwsBinaryMissing as e:
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=str(e),
            remediation="install.sh 재실행 또는 gws binary 설치.",
        ) from e
    except subprocess.TimeoutExpired as e:
        # CRIT-R4-2: timeout 은 transient — Retryable 로 매핑.
        # gws docstring 의 약속 이행 + ADR-0014 fallback policy 정합.
        raise VaultSyncRetryable(
            vault_id=vault_id,
            retry_after_sec=60,
            reason=f"gws timeout after {e.timeout}s: args={args[:3]}",
        ) from e
    if result.returncode != 0:
        wh_exit, severity, reason, scope = classify_gws_error(result.returncode, result.stderr)
        if severity == "retryable":
            raise VaultSyncRetryable(vault_id=vault_id, retry_after_sec=60, reason=reason)
        # CRIT-R4-3: scope 따라 분기 — vault stuck 회피.
        if scope == "file":
            raise VaultSyncFileFatal(vault_id=vault_id, source_id=source_id, reason=reason)
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=reason,
            remediation="ADR-0014 fallback (Workspace 권한·token 점검) 또는 ADR-0017 stderr 매핑 갱신.",
        )
    return result


def _gws_json(result: GwsResult, vault_id: str) -> Any:
    """stdout 을 JSON 으로 파싱. binary_output=False 일 때만 사용."""
    try:
        return json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError as e:
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=f"gws stdout JSON 파싱 실패: {e}; stdout 첫 500자: {result.stdout[:500]!r}",
            remediation="V1·V2 verification 후 stdout 형식 spec refine.",
        ) from e


# ---------------------------------------------------------------------------
# Bootstrap & incremental
# ---------------------------------------------------------------------------

def _bootstrap_token(vault_id: str, env_extra: dict[str, str]) -> str:
    """gws drive changes getStartPageToken — 첫 sync 시 cursor 발급.

    gws v0.22.5 의 정본 subcommand 는 camelCase `getStartPageToken`
    (V<N> Phase 2 결함 #8, 2026-05-17). 이전 hyphenated `get-start-page-token`
    은 unrecognized subcommand 로 reject.
    """
    result = _run(vault_id, ["drive", "changes", "getStartPageToken"], None, env_extra=env_extra)
    data = _gws_json(result, vault_id)
    token = data.get("startPageToken") if isinstance(data, dict) else None
    if not token:
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=f"start-page-token 응답 형식 미상: {result.stdout[:500]!r}",
            remediation="V1 verification — gws schema drive.changes 확인.",
        )
    return str(token)


def _files_list_iter(vault_id: str, env_extra: dict[str, str], *,
                     root_folder_id: str | None, exclude_shared_with_me: bool) -> list[dict]:
    """bootstrap 시 vault 내 모든 파일 enumeration. files.list pagination (V9)."""
    q_parts: list[str] = []
    if exclude_shared_with_me:
        q_parts.append("sharedWithMe=false")
    if root_folder_id:
        q_parts.append(f"'{root_folder_id}' in parents")
    q = " and ".join(q_parts) if q_parts else None
    page_token = ""
    all_files: list[dict] = []
    while True:
        params: dict[str, Any] = {
            "pageSize": 100,
            "fields": "files(id,name,mimeType,modifiedTime,parents,shared,ownedByMe,size),nextPageToken",
        }
        if q:
            params["q"] = q
        if page_token:
            params["pageToken"] = page_token
        result = _run(vault_id, ["drive", "files", "list"], params, env_extra=env_extra)
        data = _gws_json(result, vault_id)
        files = data.get("files") if isinstance(data, dict) else []
        all_files.extend(files or [])
        page_token = data.get("nextPageToken") if isinstance(data, dict) else None
        if not page_token:
            break
    log.info("files.list pagination 완료: %d files", len(all_files))
    return all_files


def _changes_list_iter(vault_id: str, env_extra: dict[str, str], *,
                       page_token: str) -> tuple[list[dict], str]:
    """incremental — pageToken 부터 changes 수집. 새 newStartPageToken 반환.

    Returns: (changes, new_start_page_token).
    """
    changes: list[dict] = []
    new_start = page_token
    cur = page_token
    while True:
        params: dict[str, Any] = {
            "pageToken": cur,
            "pageSize": 100,
            "includeRemoved": True,
            "fields": "changes(removed,fileId,file(id,name,mimeType,modifiedTime,parents,shared,ownedByMe,size)),nextPageToken,newStartPageToken",
        }
        result = _run(vault_id, ["drive", "changes", "list"], params, env_extra=env_extra)
        data = _gws_json(result, vault_id)
        page_changes = data.get("changes", []) if isinstance(data, dict) else []
        changes.extend(page_changes or [])
        next_tok = data.get("nextPageToken") if isinstance(data, dict) else None
        new_start_in_resp = data.get("newStartPageToken") if isinstance(data, dict) else None
        if new_start_in_resp:
            new_start = str(new_start_in_resp)
        if next_tok:
            cur = str(next_tok)
            continue
        break
    log.info("changes.list 사이클 완료: %d changes (new start_token=%s)",
             len(changes), new_start[:16] + "..." if len(new_start) > 16 else new_start)
    return changes, new_start


# ---------------------------------------------------------------------------
# Filtering & path computation
# ---------------------------------------------------------------------------

def _passes_trust_boundary(file_meta: dict, *, exclude_shared_with_me: bool,
                           root_folder_id: str | None) -> bool:
    """Q3·SIG-6 정합 — sharedWithMe + root_folder_id 둘 다 post-filter (changes API)."""
    if exclude_shared_with_me and file_meta.get("shared") and not file_meta.get("ownedByMe", False):
        return False
    if root_folder_id:
        parents = file_meta.get("parents", []) or []
        # parents 에 root_folder_id 가 직접 포함되어야 함 (다중 hop 추적은 v0.2.x)
        if root_folder_id not in parents:
            return False
    return True


def _sanitize_relpath(raw: str) -> str | None:
    """CRIT-3 — traversal · invalid char 차단. 부적합 시 None.

    Drive name 은 사용자 제어 입력 — '../', 절대경로, control char 차단 후 vault 경계 안에만 저장.

    HIGH-R3-2 fix: lstrip("/") 이후 startswith("/") 는 dead code 였음 — 제거.
    LOW-R3-1 fix: "." / "./" 처럼 normalize 후 빈 path 가 되는 입력도 차단.
        (Python 3.10 의 ``Path(".").parts == ()``, ``Path("./").parts == ()``)
    """
    if not raw:
        return None
    candidate = raw.lstrip("/").strip()
    if not candidate:
        return None
    # control char 또는 backslash 차단
    if _INVALID_NAME_CHARS.search(candidate):
        return None
    # path 분해 — normalize 후 빈 path 거부 ("." / "./")
    parts = Path(candidate).parts
    if not parts:
        return None
    # .. / . / 빈 segment — traversal · 자기참조 차단
    if any(p in ("..", ".", "") for p in parts):
        return None
    # defense-in-depth: 어떤 이유로든 absolute path 가 만들어졌다면 거부
    if Path(candidate).is_absolute():
        return None
    return candidate


# Google native mimeType → rclone mount 의 export 확장자 매핑.
# ADR-0025 service template `--drive-export-formats docx,xlsx,pptx,md` 우선순위 정합.
# `_download_to_vault` 의 mount lookup 시점에서만 사용 — source_relpath 자체에는 prepend 안 함.
# **운영자 주의 (R15-M1)**: 본 dict 의 mimeType→ext 매핑은 mount template 의 export-formats
# 첫 매치 우선순위에 silent coupled. mount template 의 export-formats 변경 (예:
# `md,docx,xlsx,pptx` 순) 시 본 dict 도 동기 갱신 필수 — 안 그러면 mount 의 export 확장자
# 와 sync.py 의 mount lookup 확장자 mismatch → `mount path 미존재` warning.
_NATIVE_MIME_TO_EXT: dict[str, str] = {
    "application/vnd.google-apps.document": ".docx",
    "application/vnd.google-apps.spreadsheet": ".xlsx",
    "application/vnd.google-apps.presentation": ".pptx",
}


def _source_relpath(file_meta: dict) -> str | None:
    """vault 내 상대 경로 — CRIT-3 sanitized.

    v0.1.0 은 Drive 'name' 만 flat 사용. 디렉토리 구조 보존은 v0.2.x (parents traversal).

    raw name 그대로 (Google native 도 mimeType 확장자 prepend 안 함). file_map
    primary key 안정성 보장 — Drive rename 시 동일 fileId 의 source_relpath 가
    그대로 유지되어 file_map "modified" 분류 정합.

    Google native 의 mount path lookup 은 `_download_to_vault` 에서 mimeType→ext
    suffix 적용 (V<N> Phase 2 결함 #9 fix R15-CRIT-1 + R16-H4 후속, 2026-05-17).
    """
    return _sanitize_relpath(str(file_meta.get("name", "")))


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
        # `endswith(virt)` 분기는 defensive — Drive 운영자가 파일 이름을 `note.gdoc` 같이
        # virtual ext 와 동일한 suffix 로 지정한 edge case 에서 이중 추가 (`note.gdoc.gdoc.md`)
        # 차단. 결함 #11 fix 후 source_relpath 는 raw Drive name 이라 일반 케이스에선 False.
        # R15-M6 정리: dead 가 아닌 defensive guard 로 의도 명시 (2026-05-17 R15 리뷰 응답).
        if virt and not source_relpath.endswith(virt):
            return f"wiki/sources/{vault_id}/{source_relpath}{virt}.md"
        return f"wiki/sources/{vault_id}/{source_relpath}.md"
    # .md 중복 회피
    if source_relpath.endswith(".md"):
        return f"wiki/sources/{vault_id}/{source_relpath}"
    return f"wiki/sources/{vault_id}/{source_relpath}.md"


# ---------------------------------------------------------------------------
# Download & extraction
# ---------------------------------------------------------------------------

def _download_to_vault(vault_id: str, env_extra: dict[str, str],
                       file_meta: dict, vault_local_path: Path,
                       *, source_relpath: str,
                       max_file_size_mb: int | None) -> tuple[ExtractionResult, int]:
    """파일을 mount FS 에서 read + extraction 수행 (v9 ADR-0025 — Path C+ mount path open).

    v6 (gws 단독): ``gws drive files get/export`` subprocess 로 binary 다운로드 + vault 에 write.
    v9 (Path C+): vault_local_path 가 rclone mount point. 파일은 이미 mount FS 에 존재
    (rclone vfs cache 가 자동 fetch). 본 함수는 mount path open + extraction 만 수행.

    Args:
        source_relpath: caller 가 ``_sanitize_relpath`` 로 정제한 vault 내 상대경로.
            CRIT-R4-1·R3-CRIT-1 fix — 함수 내부에서는 raw ``file_meta["name"]`` 사용 금지.

    Returns:
        (extraction_result, bytes_written).
        Q4 정합 — saved_path 제거 (호출자 미사용).

    SIG-3: max_file_size_mb 초과 시 read skip + failed ExtractionResult.
    v9 (R11-CRIT-3 정합): mount FS 위 atomic_write 폐기 — read 만 수행, vault binary 는
    rclone 이 관리. ``_handle_removed`` 도 unlink 제거 (Drive 원본 보호).

    Google native export (ADR-0027 Q1 lock, V<N> Phase 2 결함 #9 fix, 2026-05-17):
    - rclone mount `--drive-export-formats docx,xlsx,pptx,md` 우선순위로 binary export.
    - source_relpath 는 raw Drive name 유지 (file_map primary key 안정성).
    - mount lookup 시점에 `_NATIVE_MIME_TO_EXT` 의 mimeType→ext suffix 적용 → `saved` 경로
      가 `.docx`·`.xlsx`·`.pptx` 포함.
    - `extract(saved, mime)` 가 LOCAL_EXTRACTION_DISPATCH 의 Google native mime → extract_docx/
      xlsx/pptx 매핑으로 binary 변환.
    """
    fid = file_meta["id"]
    mime = file_meta.get("mimeType", "")
    env_extra = env_extra  # unused in v9 — gws files get 폐기. 호환성을 위해 시그니처 유지.

    # invariant: source_relpath 는 caller 측 sanitize 통과한 값이어야 함
    if not source_relpath or Path(source_relpath).is_absolute():
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=f"_download_to_vault invariant 위반: source_relpath={source_relpath!r}",
            remediation="caller(_sync_loop) 가 sanitize 후 전달해야 함 — 코드 변경 회귀.",
        )

    # SIG-3: pre-read size 가드 (mount FS stat 으로 확인)
    size_bytes = int(file_meta.get("size", 0) or 0)
    size_cap_bytes = max_file_size_mb * 1024 * 1024 if max_file_size_mb else None
    if size_cap_bytes and size_bytes and size_bytes > size_cap_bytes:
        log.warning("skip oversized file (pre-check): id=%s size=%dB max=%dMB",
                    fid, size_bytes, max_file_size_mb)
        return ExtractionResult(
            body_text=f"[extraction failed: file size {size_bytes}B exceeds limit {max_file_size_mb}MB]",
            tool="size-check",
            tool_version="n/a",
            extraction_status="failed",
            reason=f"oversize: {size_bytes}B > {max_file_size_mb}MB",
        ), 0

    # V<N> Phase 2 결함 #9 fix R15-CRIT-1 후속 (2026-05-17):
    # Google native 의 mount path 는 rclone 의 `--drive-export-formats` 우선순위로
    # `.docx`·`.xlsx`·`.pptx` 자동 추가. source_relpath 자체는 raw name 유지
    # (file_map primary key 안정성) 후 mount lookup 시점에만 ext suffix 적용.
    mount_relpath = source_relpath
    if mime in _NATIVE_MIME_TO_EXT:
        ext = _NATIVE_MIME_TO_EXT[mime]
        if not mount_relpath.endswith(ext):
            mount_relpath = mount_relpath + ext
    saved = vault_local_path / mount_relpath
    # defense-in-depth: vault_local_path 경계 escape 차단 (CRIT-R4-1 권장 3)
    # v9: vault_local_path 가 mount point. mount FS 내 traversal 도 동일하게 차단 필요.
    vault_resolved = vault_local_path.resolve()
    try:
        saved.resolve().relative_to(vault_resolved)
    except ValueError as e:
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=f"vault_local_path escape detected: saved={saved}",
            remediation="caller sanitize 결함 — _sanitize_relpath 추가 검토.",
        ) from e

    # v9 (ADR-0025·0027 Path C+) — mount FS 에 파일이 이미 존재 (rclone vfs cache 가 자동 fetch).
    # Google native 파일은 rclone `--drive-export-formats markdown` 설정 시 mount 에 .md 로 보임 (Q1 잠정).
    # 단 mount path 가 stale 또는 vfs cache miss 일 수 있음 — 사이클 시작 시 vfs_refresh 호출이 정합 보장 (ADR-0026 K1).
    if not saved.exists():
        log.warning("mount path 미존재 (vfs cache miss 가능): vault=%s id=%s path=%s",
                    vault_id, fid, saved)
        return ExtractionResult(
            body_text=f"[extraction failed: mount path 미존재 — vfs_refresh 누락 또는 mount stale: {saved}]",
            tool="mount-read",
            tool_version="n/a",
            extraction_status="failed",
            reason="mount-path-missing",
        ), 0

    # mount FS 의 파일 read — text/binary mime 분기로 extract helper 결정
    is_text_mime = mime.startswith("text/") or mime in ("application/json",)
    is_native = mime in GWS_EXPORT_MIME

    try:
        if is_text_mime:
            content = saved.read_text(encoding="utf-8")
            bytes_written = len(content.encode("utf-8"))
            er = extract_text(saved)
        elif is_native:
            # V<N> Phase 2 결함 #9 fix (2026-05-17 — ADR-0027 Q1 lock):
            # rclone mount 가 `--drive-export-formats docx,xlsx,pptx,md` 우선순위로
            # Google native 를 binary 로 자동 export → mount path 는 `.docx`·`.xlsx`·`.pptx`
            # 확장자 포함 (caller 의 `_source_relpath` 가 mimeType 기반 매핑 완료).
            # binary read + extraction.extract dispatch (LOCAL_EXTRACTION_DISPATCH 가 Google
            # native mimeType → extract_docx/xlsx/pptx 매핑).
            data = saved.read_bytes()
            bytes_written = len(data)
            if bytes_written == 0:
                log.warning("mount native export empty: vault=%s id=%s mime=%s path=%s",
                            vault_id, fid, mime, saved)
                return ExtractionResult(
                    body_text=f"[extraction failed: native export empty for {mime} at {saved}]",
                    tool="mount-native-export",
                    tool_version="n/a",
                    extraction_status="failed",
                    reason="empty native export",
                ), 0
            er = extract(saved, mime)
        else:
            # binary — extraction 은 saved path 를 직접 받음 (mount FS read-through)
            data = saved.read_bytes()
            bytes_written = len(data)
            # HIGH-R4-4: post-read size 가드 (v9 — pre-check 가 size_bytes=0 인 경우 보강)
            if size_cap_bytes and bytes_written > size_cap_bytes:
                log.warning("skip oversized file (post-check): id=%s read=%dB max=%dMB",
                            fid, bytes_written, max_file_size_mb)
                return ExtractionResult(
                    body_text=f"[extraction failed: read {bytes_written}B exceeds limit {max_file_size_mb}MB]",
                    tool="size-check",
                    tool_version="n/a",
                    extraction_status="failed",
                    reason=f"oversize-post: {bytes_written}B > {max_file_size_mb}MB",
                ), 0
            er = extract(saved, mime)
    except OSError as e:
        # FUSE read 실패 — mount stale 또는 OAuth revoke (rclone 이 read 시점에 fail)
        log.error("mount read OSError: vault=%s id=%s path=%s err=%s", vault_id, fid, saved, e)
        return ExtractionResult(
            body_text=f"[extraction failed: mount FS read OSError errno={e.errno}: {saved}]",
            tool="mount-read",
            tool_version="n/a",
            extraction_status="failed",
            reason=f"mount-read-oserror: errno={e.errno}",
        ), 0

    return er, bytes_written


# ---------------------------------------------------------------------------
# wiki page atomic write (CRIT-2)
# ---------------------------------------------------------------------------

def _atomic_write_wiki_page(full_path: Path, content: str) -> None:
    """CRIT-2 — state._atomic_write_json 패턴과 통일.

    tempfile.mkstemp 로 random suffix tmpfile + fsync + os.replace.
    실패 시 tmpfile 정리.

    HIGH-R4-1: fsync 추가 — OCI ARM unexpected reboot 시 zero-length 파일 회피.
    """
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
# Removed change 처리 (SIG-2)
# ---------------------------------------------------------------------------

def _handle_removed(*, vault_id: str, file_id: str, file_map: dict,
                    instance_root: Path,
                    deleted_out: list[str]) -> None:
    """SIG-2: removed change 시 wiki source 만 삭제 (v9 R11-CRIT-3 — mount FS unlink 제거).

    v9 (ADR-0025 Path C+): `vault_local_path` 가 rclone mount point 가 됨. mount 위 unlink 는
    `--vfs-cache-mode full` 의 write-through 로 Drive 원본 파일까지 삭제할 위험 (데이터 손실).
    v6 의 `(vault_local_path / entry).unlink()` 라인 제거 — mount FS 의 vault binary 는
    Drive 에서 삭제 시 vfs/refresh 후 자동으로 mount listing 에서 사라짐. 별도 unlink 불필요.

    유지: wiki page 삭제 + file_map 갱신 + deleted_out append.
    """
    entry = next((p for p, v in file_map["files"].items() if v.get("source_id") == file_id), None)
    if not entry:
        log.info("removed (untracked): file_id=%s", file_id)
        return
    deleted_out.append(entry)
    info = file_map["files"][entry]
    wp = info.get("wiki_path")
    if wp:
        (instance_root / wp).unlink(missing_ok=True)
    # v9 R11-CRIT-3: vault_local_path 는 mount point — unlink 시 Drive 원본 삭제 위험. 제거됨.
    # 미러 일관성은 rclone vfs/refresh 가 자동 보장 (사이클 시작 시 호출 — ADR-0026 K1).
    del file_map["files"][entry]
    log.info("removed: %s (wiki page 삭제, mount FS unlink 미수행 — Drive 원본 보호)", entry)


# ---------------------------------------------------------------------------
# 종합 흐름
# ---------------------------------------------------------------------------

def sync(
    *,
    vault_cfg: VaultConfig,
    instance_root: Path,
    state_dir: Path,
    credentials_path: Path,
    bootstrap_flag: bool,
) -> SyncResult:
    """vault sync orchestration — main entry from vault-fetch.py.

    **Invariant (R16-L5, V<N> R16 SRE 리뷰)**: 본 함수는 vault-fetch.py 의 control flow 에서
    `credentials.assert_credentials(credentials_path)` 호출 **이후**에만 호출된다는 전제.
    즉 credentials_path 의 JSON 형식 + type 필드 검증이 선행된 상태. 본 함수의 SA override
    분기 (sharedWithMe=false → True 회피) 는 credentials_path 의 raw JSON 을 `json.load`
    로 재읽기 — 이때 OSError / JSONDecodeError 발생 시 silent skip (assert_credentials 가
    이미 catch). 직접 sync() 단위 테스트 호출 시엔 SA override 가 silent fail 가능 — 운영
    경로는 vault-fetch.py 의 호출 순서 보장.
    """
    started = time.monotonic()
    started_iso = utc_now_iso()
    env_extra = ensure_env_var(credentials_path)
    vault_id = vault_cfg.id
    options = dict(vault_cfg.options)
    root_folder_id = options.get("root_folder_id")
    exclude_swm = bool(options.get("exclude_shared_with_me", True))
    # ADR-0029 SA 정합 (V4 본격 + 결함 #2 fix, 2026-05-17):
    # SA 의 경우 own 파일 자체가 없으므로 `sharedWithMe=false` query 가 Drive API 에서
    # `400 Invalid Value` 로 reject. SA 채택 시 무조건 false override (yaml 설정 무시).
    # credentials JSON 의 `type` 필드 확인 (credentials.py 의 assert_credentials 가 이미
    # `service_account` 검증 완료 — vault-fetch.py 의 호출 순서 정합).
    try:
        with open(credentials_path) as f:
            creds_type = json.load(f).get("type", "")
        if creds_type == "service_account" and exclude_swm:
            log.info("SA 채택 — exclude_shared_with_me=false override (sharedWithMe query 가 SA 에서 Invalid Value)")
            exclude_swm = False
    except (OSError, json.JSONDecodeError):
        pass  # credentials.py 가 이미 검증 — 여기서 fail 무시
    max_file_size_mb = options.get("max_file_size_mb")

    log.info("sync start: vault=%s bootstrap=%s root_folder_id=%s",
             vault_id, bootstrap_flag, root_folder_id)

    cursor_obj = load_cursor(state_dir)
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

    cursor_before = cursor_obj.get("cursor", "")

    if not has_cursor(cursor_obj):
        # Bootstrap 가드 (F1 §4.4.6 lift, B2)
        if not options.get("bootstrap_allowed", False):
            raise VaultSyncFatal(
                vault_id=vault_id,
                reason="cursor 없음 + bootstrap 비활성",
                remediation=(
                    f"wikihub.yaml.vaults[{vault_id}].options.bootstrap_allowed=true 설정 "
                    "+ --bootstrap 플래그로 실행 후 다시 false 환원."
                ),
            )
        if not bootstrap_flag:
            raise VaultSyncFatal(
                vault_id=vault_id,
                reason="bootstrap 허용됐으나 --bootstrap 플래그 누락",
                remediation=f"명시 의도 확인 후 vault-fetch.py --vault {vault_id} --bootstrap",
            )
        log.info("bootstrap mode: 전체 스캔 시작")
        files_meta = _files_list_iter(
            vault_id, env_extra,
            root_folder_id=root_folder_id,
            exclude_shared_with_me=exclude_swm,
        )
        new_cursor = _bootstrap_token(vault_id, env_extra)
        changes_synthetic: list[dict] = [
            {"removed": False, "fileId": fm["id"], "file": fm}
            for fm in files_meta
        ]
    else:
        log.info("incremental mode: cursor_before=%s...",
                 cursor_before[:16] if cursor_before else "")
        changes_synthetic, new_cursor = _changes_list_iter(
            vault_id, env_extra, page_token=cursor_before)

    changed: list[ChangedFile] = []
    deleted: list[str] = []
    skipped_count = 0
    error_count = 0

    for ch in changes_synthetic:
        try:
            if ch.get("removed"):
                fid = ch.get("fileId")
                if fid:
                    _handle_removed(
                        vault_id=vault_id, file_id=fid, file_map=file_map,
                        instance_root=instance_root,
                        deleted_out=deleted,
                    )
                    # CRIT-4: file_map 즉시 commit
                    save_file_map(state_dir, file_map)
                continue
            file_meta = ch.get("file") or {}
            if not file_meta:
                skipped_count += 1
                continue
            if not _passes_trust_boundary(
                file_meta,
                exclude_shared_with_me=exclude_swm,
                root_folder_id=root_folder_id,
            ):
                log.info("skip (trust boundary): id=%s name=%s",
                         file_meta.get("id"), file_meta.get("name"))
                skipped_count += 1
                continue
            source_relpath = _source_relpath(file_meta)
            if not source_relpath:
                log.warning("skip (invalid name): id=%s raw_name=%r",
                            file_meta.get("id"), file_meta.get("name"))
                skipped_count += 1
                continue
            mime = file_meta.get("mimeType", "")
            wiki_path_rel = _compute_wiki_path(vault_id, source_relpath, mime)
            operation = "modified" if source_relpath in file_map["files"] else "created"

            log.info("process %s: id=%s mime=%s op=%s",
                     source_relpath, file_meta.get("id"), mime, operation)

            er, bytes_written = _download_to_vault(
                vault_id, env_extra, file_meta, vault_cfg.local_path,
                source_relpath=source_relpath,
                max_file_size_mb=max_file_size_mb,
            )
            source_mtime = str(file_meta.get("modifiedTime", utc_now_iso()))
            title = file_meta.get("name", source_relpath)
            # I1 + HIGH-R4-5 fix: failed 시 tool/tool_version 모두 None.
            extraction_ok = er.extraction_status == "success"
            fm_dict = build_source_frontmatter(
                title=title,
                vault_id=vault_id,
                relpath=source_relpath,
                source_id=file_meta.get("id"),
                source_mtime=source_mtime,
                last_synced_at=utc_now_iso(),
                extraction_tool=er.tool if extraction_ok else None,
                extraction_tool_version=er.tool_version if extraction_ok else None,
                extracted_at=utc_now_iso(),
                created=started_iso.split("T")[0],
                updated=started_iso.split("T")[0],
            )
            page_text = emit_page(fm_dict, er.body_text)
            _atomic_write_wiki_page(instance_root / wiki_path_rel, page_text)

            file_map["files"][source_relpath] = {
                "source_id": file_meta.get("id"),
                "source_mtime": source_mtime,
                "wiki_path": wiki_path_rel,
                "bytes": bytes_written,
                "last_synced_at": utc_now_iso(),
            }
            changed.append(ChangedFile(
                source_relpath=source_relpath,
                wiki_path=wiki_path_rel,
                operation=operation,
                source_id=file_meta.get("id"),
                source_mtime=source_mtime,
                bytes_written=bytes_written,
            ))
            # CRIT-4: file_map 즉시 commit
            save_file_map(state_dir, file_map)

        except VaultSyncRetryable as e:
            # SIG-5: per-file retryable 은 retry queue 등록 + 사이클 계속
            log.warning("per-file retryable: %s", e)
            fm = ch.get("file") or {}
            sr = _source_relpath(fm) or fm.get("id", "unknown")
            enqueue_retry(
                retry_obj,
                source_relpath=sr,
                source_id=fm.get("id"),
                operation="modified",
                failure_reason=str(e),
                next_retry_at=utc_now_iso(),
            )
            save_retry(state_dir, retry_obj)
            error_count += 1
            continue
        except VaultSyncFileFatal as e:
            # CRIT-R4-3: per-file fatal 은 retry queue 등록 + 사이클 계속.
            # vault 전체 stuck 회피 — 운영자가 retry.json 으로 가시화.
            log.error("per-file fatal: %s", e)
            fm = ch.get("file") or {}
            sr = _source_relpath(fm) or fm.get("id", "unknown")
            enqueue_retry(
                retry_obj,
                source_relpath=sr,
                source_id=fm.get("id"),
                operation="modified",
                failure_reason=f"file-fatal: {e.reason}",
                next_retry_at=utc_now_iso(),
            )
            save_retry(state_dir, retry_obj)
            error_count += 1
            continue
        except VaultSyncFatal:
            # vault-wide fatal — 사이클 중단. file_map 은 지금까지 처리분 보존됨 (CRIT-4)
            raise
        except Exception as e:  # noqa: BLE001
            # unknown exception per-file — log + skip
            log.exception("per-file unexpected error: %s", e)
            error_count += 1
            continue

    duration_ms = int((time.monotonic() - started) * 1000)
    finished_iso = utc_now_iso()
    result = SyncResult(
        vault_id=vault_id,
        has_changes=bool(changed or deleted),
        changed=changed,
        deleted=deleted,
        cursor_before=cursor_before,
        cursor_after=new_cursor,
        started_at=started_iso,
        finished_at=finished_iso,
        duration_ms=duration_ms,
    )

    # SIG-1: last_sync.json 명시적 schema
    save_last_sync(state_dir, _result_to_last_sync_dict(result))
    # I3: cursor save 를 last_sync 뒤로 — partial-failure window 차단
    save_cursor(state_dir, new_cursor, vault_id=vault_id, vault_type=vault_cfg.type)

    log.info(
        "sync ok: vault=%s changed=%d deleted=%d skipped=%d errors=%d duration_ms=%d",
        vault_id, len(changed), len(deleted), skipped_count, error_count, duration_ms,
    )
    return result


def _result_to_last_sync_dict(result: SyncResult) -> dict:
    """SIG-1: last_sync.json 정본 schema (asdict 대신 명시적)."""
    return {
        "vault_id": result.vault_id,
        "has_changes": result.has_changes,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "duration_ms": result.duration_ms,
        "cursor_before": result.cursor_before,
        "cursor_after": result.cursor_after,
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
