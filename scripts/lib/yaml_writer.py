"""atomic yaml round-trip writer (ADR-0031 §Decision D 정본).

`/wh:setup` Step 0 (template materialization) + Step 6 (`bootstrap_allowed: true → false`) 의
**단일 helper** — yaml writer 책임이 두 곳에 분산되지 않도록 `atomic_yaml_write` 1 함수로 통합
(CRIT-A2 design review 반영).

ruamel.yaml 의 round-trip 모드 (`YAML(typ='rt')`) 가 주석·key 순서·indent 를 보존 → `.example`
의 풍부한 주석이 operational yaml 에 살아남음 (메인테이너 편집 UX).

atomic write 패턴은 `scripts/lib/state.py` 의 `_atomic_write_json` 와 정합 — tmpfile 은
target 의 same-directory + PID suffix, fsync 후 os.replace.

**Thread-safety**: `_yaml_rt` 는 module-level singleton (`YAML(typ="rt")` 인스턴스) 으로,
ruamel.yaml 공식 문서 기준 thread-safe 하지 않음. 본 helper 는 single-threaded 호출을 가정한다.
v0.2.x multi-thread 도입 시 function-local instance 또는 `threading.Lock` 보호 필요
(ADR-0031 §Decision A single-writer invariant 범위 확장 검토).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

_yaml_rt = YAML(typ="rt")
_yaml_rt.preserve_quotes = True
_yaml_rt.indent(mapping=2, sequence=4, offset=2)


def atomic_yaml_write(path: Path, data: Any) -> None:
    """yaml 을 atomic 으로 write (ADR-0031 §Decision A · D 정합).

    - **tmpfile 위치**: `path.parent / f".{path.name}.tmp.{os.getpid()}"` — same-directory
      (`os.replace` 의 `EXDEV` cross-FS 회피) + PID suffix (concurrent 호출 시 stale 식별 가능).
    - **fsync + os.replace**: POSIX atomic rename 보장. fsync 가 없으면 unexpected reboot 시
      zero-length 파일 발생 가능.
    - **실패 모드 cleanup**: `ENOSPC` / write 실패 시 tmpfile unlink + exception 재throw.
    - **stale .tmp cleanup**: 본 helper 진입 시 자신의 PID 와 다른 `.<name>.tmp.*` 발견 시
      unlink (SIGTERM mid-write 후 다음 호출에서 cleanup). 단 same PID 의 tmpfile (동시 호출)
      은 보호.
    - **round-trip only**: ruamel YAML(typ='rt') 로 dump — 주석·key 순서·indent 보존.
      `round_trip=False` 분기는 v0.1.0 기준 호출처 없어 제거됨 (issue-13).

    Args:
        path: 최종 yaml 파일 경로.
        data: ruamel.yaml round-trip load 결과.

    Raises:
        OSError: tmpfile write 또는 rename 실패.
        Exception: data dump 실패 (예: ruamel API 변경).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_tmp(path)

    tmp = path.parent / f".{path.name}.tmp.{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            _yaml_rt.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def load_yaml_rt(path: Path) -> Any:
    """ruamel round-trip load — 주석 보존 상태로 read.

    `/wh:setup` Step 0 의 template materialization 에서 `.example` 또는 기존 operational yaml
    을 load 할 때 사용. 반환값을 그대로 `atomic_yaml_write(round_trip=True)` 로 dump 하면
    원본 주석·key 순서·indent 유지.
    """
    with open(path, encoding="utf-8") as f:
        return _yaml_rt.load(f)


def _cleanup_stale_tmp(path: Path) -> None:
    """SIGTERM mid-write 등으로 잔존한 `.<name>.tmp.<pid>` 정리 — 자신의 PID 는 제외."""
    own_pid = os.getpid()
    prefix = f".{path.name}.tmp."
    try:
        for entry in path.parent.iterdir():
            if not entry.name.startswith(prefix):
                continue
            if not entry.is_file():
                continue
            try:
                stale_pid = int(entry.name[len(prefix):])
            except ValueError:
                continue
            if stale_pid == own_pid:
                continue
            try:
                entry.unlink()
            except OSError:
                pass
    except FileNotFoundError:
        return
