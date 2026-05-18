#!/usr/bin/env python3
"""scripts/_helpers/hermes_config_migrate.py

Hermes ~/.hermes/config.yaml 의 skills.external_dirs 의 migration helper.
ADR-0034 layout refactor 의 §sub-3 helper — scripts/migrate_layout.sh 의 Step 5 가 호출.

기능:
    --remove-stale <path>   : stale entry 제거 (wikihub-managed marker 검증).
                              운영자 직접 등록 (marker 부재) entry 는 보존.
    --add-new <path>        : 신규 entry 추가 (realpath 정규화 + idempotent).

ADR-0032 §sub-3·sub-4 정합:
- flock advisory lock (외부 자산 mutate)
- backup (~/.hermes/config.yaml.wikihub-bak.<utc_iso>)
- PRE/POST sha256 record
- ruamel.yaml round-trip (comment 보존)
- marker comment ("managed by wikihub install.sh — remove to disable auto-discovery")

exit code:
    0 — success (변경됨 또는 no-op)
    1 — semantic (config 부재, marker 불일치, etc.)
    2 — operational (write fail, flock fail)
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import ruamel.yaml
    from ruamel.yaml.comments import CommentedSeq
except ImportError:
    sys.stderr.write("ERROR: ruamel.yaml 미설치. venv 활성화 후 재시도.\n")
    sys.exit(2)


MARKER = "managed by wikihub install.sh — remove to disable auto-discovery"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _realpath_or(value: str) -> str:
    try:
        return os.path.realpath(os.path.expanduser(value))
    except Exception:
        return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hermes config external_dirs migration helper (ADR-0034)")
    parser.add_argument("--config", type=Path, required=True, help="~/.hermes/config.yaml path")
    parser.add_argument("--remove-stale", action="append", default=[], help="stale entry path (multiple OK)")
    parser.add_argument("--add-new", action="append", default=[], help="신규 entry path (multiple OK)")
    args = parser.parse_args(argv)

    config_path = args.config
    if not config_path.is_file():
        sys.stderr.write(f"ERROR: config 부재: {config_path}\n")
        return 1

    # flock advisory (parent dir 의 lock file)
    lock_path = config_path.with_suffix(config_path.suffix + ".lock")
    lock_fp = open(lock_path, "w")
    try:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.stderr.write(f"ERROR: lock contention: {lock_path} (Hermes 또는 다른 install.sh 가 mutate 중)\n")
        return 2

    try:
        pre_hash = _sha256(config_path)

        # backup
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = Path(str(config_path) + f".wikihub-bak.{ts}")
        backup.write_bytes(config_path.read_bytes())

        # load
        yaml = ruamel.yaml.YAML(typ="rt")
        yaml.preserve_quotes = True
        yaml.width = 4096
        with open(config_path, encoding="utf-8") as f:
            data = yaml.load(f) or {}

        skills = data.setdefault("skills", {})
        ext = skills.get("external_dirs")
        if ext is None or not isinstance(ext, CommentedSeq):
            new_seq = CommentedSeq()
            if isinstance(ext, list):
                new_seq.extend(ext)
            skills["external_dirs"] = new_seq
            ext = new_seq

        stale_paths = {_realpath_or(p) for p in args.remove_stale}
        add_paths = [_realpath_or(p) for p in args.add_new]

        existing_real = [_realpath_or(str(p)) for p in ext]

        # 1) remove stale (marker 검증 — wikihub-managed entry 만)
        removed = []
        kept_with_no_marker = []
        new_ext: CommentedSeq = CommentedSeq()
        for idx, entry in enumerate(ext):
            entry_real = _realpath_or(str(entry))
            if entry_real in stale_paths:
                # marker 검증 — ruamel 의 eol comment 가 wikihub MARKER 포함이면 제거 OK
                eol_comment = ""
                try:
                    # CommentedSeq 의 item comment 는 ca.items[idx] 가 [None, [comments], ...] 형태
                    item_ca = ext.ca.items.get(idx)
                    if item_ca and len(item_ca) > 0 and item_ca[0]:
                        eol_comment = str(item_ca[0].value if hasattr(item_ca[0], "value") else item_ca[0])
                except Exception:
                    pass
                if MARKER in eol_comment or (
                    # fallback: marker 부재여도 stale path 가 wikihub 의 _generated 패턴이면 제거
                    "_system/skills/_generated" in entry_real
                ):
                    removed.append(str(entry))
                    continue
                else:
                    # marker 부재 + non-wikihub path — 운영자 의도 보존
                    kept_with_no_marker.append(str(entry))
            new_ext.append(entry)

        # 2) add new (idempotent — realpath 비교)
        new_existing_real = [_realpath_or(str(p)) for p in new_ext]
        added = []
        for new_path in add_paths:
            if new_path not in new_existing_real:
                new_ext.append(new_path)
                added.append(new_path)
                # marker eol comment 부착
                try:
                    new_ext.yaml_add_eol_comment(MARKER, len(new_ext) - 1, column=60)
                except Exception:
                    pass

        skills["external_dirs"] = new_ext

        # save (atomic)
        tmp = Path(str(config_path) + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
        os.replace(tmp, config_path)

        post_hash = _sha256(config_path)

        if pre_hash == post_hash:
            sys.stderr.write(f"INFO: no change (config 이미 정합) — backup {backup} 삭제\n")
            backup.unlink(missing_ok=True)
        else:
            sys.stderr.write(f"OK: config patched\n")
            sys.stderr.write(f"  backup: {backup}\n")
            sys.stderr.write(f"  pre  sha256: {pre_hash}\n")
            sys.stderr.write(f"  post sha256: {post_hash}\n")
            if removed:
                sys.stderr.write(f"  removed stale entries: {removed}\n")
            if added:
                sys.stderr.write(f"  added new entries:     {added}\n")
            if kept_with_no_marker:
                sys.stderr.write(
                    f"  WARN: marker 부재로 stale 후보 entry 보존 (운영자 의도 존중): {kept_with_no_marker}\n"
                )

        # 7일 초과 backup cleanup
        try:
            for f in config_path.parent.glob(f"{config_path.name}.wikihub-bak.*"):
                age = (datetime.now(timezone.utc).timestamp() - f.stat().st_mtime) / 86400
                if age > 7:
                    f.unlink()
        except Exception:
            pass

        return 0
    finally:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)
        lock_fp.close()


if __name__ == "__main__":
    sys.exit(main())
