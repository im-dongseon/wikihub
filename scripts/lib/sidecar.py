"""Atomic JSON sidecar writer for INSTALLED_VERSIONS.json (ADR-0031 §Decision B).

Migrated from bash ``_write_installed_versions_sidecar`` in install.sh (issue-19).
Uses same atomic invariant as ``state.py._atomic_write_json``:
tmpfile (same-directory) + fsync + os.replace + stale cleanup.

CLI entry point::

    WIKIHUB_SRC=/path/to/wikihub uv run python -m scripts.lib.sidecar
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _get_rclone_version() -> str:
    """Extract rclone version from ``rclone version`` output.

    Matches bash::
        rclone version 2>/dev/null | awk '/^rclone v/{print $2; exit}' | sed 's/^v//'
    """
    try:
        result = subprocess.run(
            ["rclone", "version"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return ""
        for line in result.stdout.splitlines():
            if line.startswith("rclone v"):
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1].lstrip("v")
        return ""
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def _get_graphify_version() -> str:
    """Extract graphify version from ``graphify --version`` output.

    Matches bash::
        graphify --version 2>/dev/null | awk '{print $NF; exit}'
    """
    try:
        result = subprocess.run(
            ["graphify", "--version"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip().split()[-1] if result.stdout.strip() else ""
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def _get_yq_version() -> str:
    """Extract yq version from ``yq --version`` output.

    Matches bash::
        yq --version 2>/dev/null | awk '{print $NF; exit}' | sed 's/^v//'
    """
    try:
        result = subprocess.run(
            ["yq", "--version"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return ""
        last_field = result.stdout.strip().split()[-1] if result.stdout.strip() else ""
        return last_field.lstrip("v")
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def _read_wikihub_version(src_dir: Path) -> str:
    """Read wikihub version from ``_system/VERSION`` file.

    Matches bash::
        cat "$WIKIHUB_SRC/_system/VERSION" 2>/dev/null || echo unknown
    """
    version_file = src_dir / "_system" / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return "unknown"


def write_installed_versions(target_path: Path) -> None:
    """Collect version info and atomically write INSTALLED_VERSIONS.json.

    Matches the schema from the original bash implementation:

    - **rclone**: parsed from ``rclone version`` output
    - **graphify**: parsed from ``graphify --version`` output
    - **yq**: parsed from ``yq --version`` output
    - **uv**: ``UV_VERSION`` environment variable
    - **wikihub**: ``_system/VERSION`` file content
    - **written_at**: current UTC timestamp
    """
    src_dir = Path(os.environ.get("WIKIHUB_SRC", str(target_path.parent.parent)))

    data: dict[str, Any] = {
        "schema_version": 1,
        "rclone": _get_rclone_version(),
        "graphify": _get_graphify_version(),
        "yq": _get_yq_version(),
        "uv": os.environ.get("UV_VERSION", ""),
        "wikihub": _read_wikihub_version(src_dir),
        "written_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    _atomic_write_json(target_path, data)


def _atomic_write_json(path: Path, obj: Any) -> None:
    """tmpfile + fsync + os.replace pattern (same invariant as ``state.py``).

    Uses same-directory tmpfile with ``tempfile.mkstemp`` for atomic durability.
    On exception the tmpfile is unlinked and the exception is re-raised.
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


def main() -> None:
    """CLI entry point: write INSTALLED_VERSIONS.json.

    Target path: ``$WIKIHUB_SRC/_system/INSTALLED_VERSIONS.json``
    """
    src = os.environ.get("WIKIHUB_SRC")
    if not src:
        print("ERROR: WIKIHUB_SRC environment variable is not set", file=sys.stderr)
        sys.exit(1)
    target = Path(src) / "_system" / "INSTALLED_VERSIONS.json"
    write_installed_versions(target)


if __name__ == "__main__":
    main()
