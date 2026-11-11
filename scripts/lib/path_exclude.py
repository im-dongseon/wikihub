"""vault 경로 제외 — `options.exclude_paths` 판정 유틸 (issue #221).

prefix 는 '디렉터리 prefix' 만 지원한다. 반드시 '/' 로 끝나는 형태로 정규화하며,
경계 비교는 NFC 정규화 후 prefix 매칭으로 수행한다('report/' 는 'report2/' 를 매치하지 않는다).
"""
from __future__ import annotations

import unicodedata
from typing import Any, Sequence

from .exceptions import VaultSyncFatal

_REMEDIATION = "예: project/wikihub/report/"


def normalize_prefixes(raw: Sequence[str] | None) -> list[str]:
    """원본 prefix 목록을 vault 상대 디렉터리 prefix 로 정규화한다."""
    if not raw:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            raise VaultSyncFatal(
                vault_id="__config__",
                reason=f"exclude_paths 항목이 문자열이 아니다 (원본: {item!r}). 각 항목은 문자열이어야 한다",
                remediation=_REMEDIATION,
            )

        value = item.strip()
        if value.startswith("./"):
            value = value[2:]
        if value.startswith("/"):
            value = value[1:]
        value = unicodedata.normalize("NFC", value)
        if not value.endswith("/"):
            value += "/"

        if value in ("", "/"):
            raise VaultSyncFatal(
                vault_id="__config__",
                reason=(
                    f"exclude_paths 항목 정규화 결과가 비어 있다 (원본: {item!r}). "
                    "vault 상대 디렉터리 prefix 이며 '/' 로 끝나야 한다"
                ),
                remediation=_REMEDIATION,
            )

        if value not in seen:
            seen.add(value)
            normalized.append(value)

    return normalized


def is_excluded(relpath: str, prefixes: Sequence[str]) -> bool:
    """vault 상대 경로가 제외 prefix 에 속하는지 판정한다."""
    if not prefixes or not relpath:
        return False

    normalized = unicodedata.normalize("NFC", relpath)
    return any(normalized.startswith(prefix) for prefix in prefixes)


def filter_listing(
    listing: list[dict[str, Any]], prefixes: Sequence[str]
) -> tuple[list[dict[str, Any]], int]:
    """listing 에서 제외 prefix 에 속한 항목을 제거한다."""
    kept: list[dict[str, Any]] = []
    excluded = 0
    for item in listing:
        path = item.get("Path", "")
        if path is None:
            kept.append(item)
            continue
        if is_excluded(path, prefixes):
            excluded += 1
        else:
            kept.append(item)
    return kept, excluded


def prune_file_map(
    file_map: dict[str, Any], prefixes: Sequence[str]
) -> tuple[dict[str, Any], list[str]]:
    """file_map 의 files 엔트리 중 제외 대상 경로를 프루닝한다."""
    if "files" not in file_map:
        return {**file_map, "files": {}}, []

    files = file_map["files"] or {}
    kept: dict[str, Any] = {}
    removed: list[str] = []
    for source_id, entry in files.items():
        relpath = entry.get("source_relpath", "")
        if is_excluded(relpath, prefixes):
            removed.append(relpath)
        else:
            kept[source_id] = entry

    return {**file_map, "files": kept}, sorted(removed)
