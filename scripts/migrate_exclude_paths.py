#!/usr/bin/env python3
"""exclude_paths 1회성 마이그레이션 (issue #221).

sync 가 exclude_paths 를 listing/file_map filtering 에 적용하지만, 이미 wiki 로
ingest 된 source 페이지·file_map 엔트리·referenced_by 참조는 그대로 남는다.
본 스크립트는 vault 의 exclude_paths prefix 하위를 wiki·file_map·참조
그래프에서 정리한다. 기본은 dry-run (쓰기 0) — `--apply` 있을 때만 변경한다.

호출:
    python3 scripts/migrate_exclude_paths.py --vault <id> [--config PATH] \\
        [--home PATH] [--apply] [--strip-refs] [--json OUT]

종료 코드: 0 정상 / 2 설정·인자 오류 / 3 lock 실패 / 4 부분 실패
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

# scripts/ 디렉토리를 sys.path 에 추가 (vault-fetch.py 와 동일 패턴)
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.config import load_wikihub_yaml  # noqa: E402
from lib.exceptions import VaultSyncFatal  # noqa: E402
from lib.path_exclude import normalize_prefixes, prune_file_map  # noqa: E402
from lib.state import load_file_map, save_file_map, utc_now_iso  # noqa: E402


def _fail(msg: str) -> None:
    print(f"[migrate_exclude_paths] 오류: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# --strip-refs — referenced_by 라인 수술
# ---------------------------------------------------------------------------

def _strip_refs_from_page(
    page: Path,
    *,
    vault_id: str,
    prefixes: list[str],
    apply: bool,
    result: dict[str, Any],
) -> None:
    """frontmatter 의 ``referenced_by:`` 목록에서 ``sources/<vault_id>/<prefix>``
    로 시작하는 항목만 라인 수술로 제거한다.

    파일 전체 재직렬화 금지 — frontmatter 라인 단위 편집만 수행한다.
    제거 후 목록이 비면 ``referenced_by: []`` 단일 라인으로 기록한다.
    ``referenced_by`` 키가 없는 페이지는 건드리지 않는다.
    """
    targets = tuple(f"sources/{vault_id}/{p}" for p in prefixes)
    lines = page.read_text(encoding="utf-8").splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return
    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            end_idx = i
            break
    if end_idx < 0:
        return

    fm_lines = lines[: end_idx + 1]
    rest = lines[end_idx + 1:]
    out: list[str] = []
    stripped = 0
    emptied = False
    i = 0
    while i < len(fm_lines):
        line = fm_lines[i]
        key_match = re.match(r"^(\s*)([A-Za-z0-9_-]+):", line)
        if not (key_match and key_match.group(2) == "referenced_by"):
            out.append(line)
            i += 1
            continue

        indent = key_match.group(1)
        content = line.split(":", 1)[1].strip()
        if content.startswith("["):
            # inline flow style — 대괄호 내 항목만 수술
            inner = content.strip("[]").strip()
            items = [x.strip() for x in inner.split(",") if x.strip()] if inner else []
            kept = [
                x for x in items
                if not any(x.strip("'\"").startswith(t) for t in targets)
            ]
            stripped += len(items) - len(kept)
            if kept:
                out.append(f"{indent}referenced_by: [{', '.join(kept)}]\n")
            else:
                out.append(f"{indent}referenced_by: []\n")
                emptied = True
            i += 1
            continue

        # block style — 이후 `- item` 라인들을 수집 (목록 중간의 빈 줄은 목록 내부로 간주)
        j = i + 1
        item_idx: list[int] = []
        while j < len(fm_lines):
            raw = fm_lines[j]
            if re.match(r"^\s*-\s+", raw):
                item_idx.append(j)
                j += 1
                continue
            if raw.strip() == "":
                k = j + 1
                while k < len(fm_lines) and fm_lines[k].strip() == "":
                    k += 1
                if k < len(fm_lines) and re.match(r"^\s*-\s+", fm_lines[k]):
                    j = k  # 목록 내부 빈 줄 — 버리고 계속 수집
                    continue
            break
        if not item_idx:
            # 빈 블록 (항목 없음) — 그대로 보존
            out.append(line)
            i += 1
            continue
        kept_idx: list[int] = []
        for k in item_idx:
            value = re.match(r"^\s*-\s+(.*)$", fm_lines[k]).group(1).strip().strip("'\"")
            if any(value.startswith(t) for t in targets):
                stripped += 1
            else:
                kept_idx.append(k)
        if kept_idx:
            out.append(line)
            out.extend(fm_lines[k] for k in kept_idx)
        else:
            out.append(f"{indent}referenced_by: []\n")
            emptied = True
        i = j

    if stripped == 0:
        return
    result["stripped_ref_items"] += stripped
    if emptied:
        result["empty_ref_pages"] += 1
    if apply:
        page.write_text("".join(out) + "".join(rest), encoding="utf-8")


# ---------------------------------------------------------------------------
# 마이그레이션 순서
# ---------------------------------------------------------------------------

def _migrate_file_map(state_dir: Path, prefixes: list[str], *, apply: bool,
                      result: dict[str, Any]) -> None:
    """1. file_map backup (apply 시) → 2. prune + 저장 (apply 시)."""
    fm_path = state_dir / "file_map.json"
    file_map = load_file_map(state_dir)
    if apply and fm_path.exists():
        backup = state_dir / f"file_map.json.bak-{utc_now_iso().replace(':', '')}"
        try:
            shutil.copy2(fm_path, backup)
        except OSError as e:
            result["errors"].append(f"file_map backup 실패: {e}")
    pruned, removed = prune_file_map(file_map, prefixes)
    result["removed_file_map_entries"] = len(removed)
    if apply and removed:
        try:
            save_file_map(state_dir, pruned)
        except OSError as e:
            result["errors"].append(f"file_map 저장 실패: {e}")


def _migrate_wiki_sources(instance_root: Path, vault_id: str, prefixes: list[str],
                          *, apply: bool, result: dict[str, Any]) -> None:
    """3. wiki/sources/<vault_id>/<prefix> 하위 *.md unlink + 빈 디렉터리 제거."""
    sources_root = instance_root / "wiki" / "sources" / vault_id
    if not sources_root.exists():
        return
    sources_real = sources_root.resolve()
    for prefix in prefixes:
        target_real = (sources_root / prefix).resolve()
        # realpath 가 wiki/sources/<vault_id>/ 하위인지 검사 — 밖이면 abort
        try:
            target_real.relative_to(sources_real)
        except ValueError:
            result["errors"].append(
                f"prefix '{prefix}' 가 wiki sources 경계 밖 (realpath: {target_real}) — abort"
            )
            continue
        if not target_real.exists():
            continue
        for md in sorted(target_real.rglob("*.md")):
            if not md.is_file():
                continue
            if not apply:
                result["unlinked_pages"] += 1
                continue
            try:
                md.unlink()
                result["unlinked_pages"] += 1
            except OSError as e:
                result["errors"].append(f"unlink 실패: {md}: {e}")
        if not apply:
            continue
        # 빈 디렉터리 제거 — 하위부터 bottom-up, 비어있지 않으면 유지
        for d in sorted((p for p in target_real.rglob("*") if p.is_dir()),
                        reverse=True):
            try:
                d.rmdir()
            except OSError:
                pass
        try:
            target_real.rmdir()
        except OSError:
            pass


def _migrate_refs(instance_root: Path, vault_id: str, prefixes: list[str],
                  *, apply: bool, result: dict[str, Any]) -> None:
    """4. --strip-refs — entities/concepts/analyses 페이지 referenced_by 수술."""
    for section in ("entities", "concepts", "analyses"):
        root = instance_root / "wiki" / section
        if not root.exists():
            continue
        for page in sorted(root.rglob("*.md")):
            if not page.is_file():
                continue
            try:
                _strip_refs_from_page(
                    page, vault_id=vault_id, prefixes=prefixes, apply=apply,
                    result=result,
                )
            except OSError as e:
                result["errors"].append(f"referenced_by 수술 실패 ({page}): {e}")


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="exclude_paths 1회성 마이그레이션 (issue #221) — 기본 dry-run",
    )
    parser.add_argument("--vault", required=True, help="wikihub.yaml.vaults[*].id")
    parser.add_argument("--config", help="wikihub.yaml 경로 (기본: --home/wikihub.yaml)")
    parser.add_argument("--home", help="wikihub home (기본: $WIKIHUB_HOME 또는 ~/wikihub)")
    parser.add_argument("--apply", action="store_true",
                        help="실제 변경 수행 (기본 dry-run)")
    parser.add_argument("--strip-refs", action="store_true", dest="strip_refs",
                        help="entities/concepts/analyses referenced_by 정리")
    parser.add_argument("--json", dest="json_out", metavar="OUT",
                        help="결과 JSON 파일 저장 경로")
    args = parser.parse_args(argv)

    # home / config 결정
    if args.home:
        home = Path(args.home).expanduser()
    else:
        home_env = os.environ.get("WIKIHUB_HOME")
        home = Path(home_env).expanduser() if home_env else Path("~/wikihub").expanduser()
    config_path = Path(args.config).expanduser() if args.config else home / "wikihub.yaml"

    # 설정 로드 + vault 조회
    try:
        cfg = load_wikihub_yaml(config_path)
    except VaultSyncFatal as e:
        _fail(str(e))
        return 2
    if args.vault not in cfg.vaults:
        _fail(f"vault '{args.vault}' 가 wikihub.yaml 에 정의되어 있지 않다")
        return 2
    vault_cfg = cfg.vaults[args.vault]

    # exclude_paths 정규화 — 없거나 비면 종료
    try:
        prefixes = normalize_prefixes(vault_cfg.options.get("exclude_paths") or [])
    except VaultSyncFatal as e:
        _fail(str(e))
        return 2
    if not prefixes:
        _fail(
            f"vault '{args.vault}' 에 exclude_paths 설정이 없거나 비어 있다 — "
            f"wikihub.yaml vaults.{args.vault}.options.exclude_paths 확인"
        )
        return 2

    instance_root = cfg.instance_root
    state_dir = instance_root / "_state" / args.vault
    state_dir.mkdir(parents=True, exist_ok=True)

    # lock — vault-fetch 와 동일 패턴 (LOCK_EX | LOCK_NB)
    lock_path = state_dir / ".lock"
    lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError) as e:
        _fail(f"다른 sync 가 실행 중 (lock 획득 실패: {lock_path}) — 잠시 후 재시도")
        lock_fd.close()
        return 3

    try:
        result: dict[str, Any] = {
            "vault_id": args.vault,
            "apply": args.apply,
            "prefixes": prefixes,
            "removed_file_map_entries": 0,
            "unlinked_pages": 0,
            "stripped_ref_items": 0,
            "empty_ref_pages": 0,
            "errors": [],
        }
        _migrate_file_map(state_dir, prefixes, apply=args.apply, result=result)
        _migrate_wiki_sources(instance_root, args.vault, prefixes,
                              apply=args.apply, result=result)
        if args.strip_refs:
            _migrate_refs(instance_root, args.vault, prefixes,
                          apply=args.apply, result=result)

        payload = json.dumps(result, ensure_ascii=False)
        sys.stdout.write(payload + "\n")
        sys.stdout.flush()
        if args.json_out:
            out_path = Path(args.json_out).expanduser()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(payload + "\n", encoding="utf-8")

        if result["errors"]:
            return 4
        return 0
    finally:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()


if __name__ == "__main__":
    raise SystemExit(main())
