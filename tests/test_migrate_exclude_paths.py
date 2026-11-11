"""scripts/migrate_exclude_paths.py 테스트 (issue #221 — 1회성 마이그레이션).

tmp_path 로 가짜 wikihub home 을 구성해 검증한다. dry-run 이 기본 (쓰기 0).
"""
from __future__ import annotations

import fcntl
import json
from pathlib import Path

import pytest

import migrate_exclude_paths as m


def _write_yaml(home: Path) -> None:
    """가짜 wikihub.yaml — vault gdrive, exclude_paths: [report/]."""
    (home / "wikihub.yaml").write_text(f"""
version: 1
instance:
  root: {home}
  timezone: Asia/Seoul
vaults:
  - id: gdrive
    type: directory
    enabled: true
    sync_interval_sec: 600
    local_path: {home}/vault
    options:
      exclude_paths:
        - report/
agent:
  type: hermes
  binary: /usr/local/bin/hermes
  oneshot_args: []
""", encoding="utf-8")


def _setup(tmp_path: Path) -> Path:
    """가짜 home 구성 — wikihub.yaml + wiki source 페이지 + file_map. state_dir 반환."""
    home = tmp_path
    _write_yaml(home)
    state_dir = home / "_state" / "gdrive"
    state_dir.mkdir(parents=True)

    # file_map: keep 1건 + report/ 2건 (중첩 sub 포함)
    (state_dir / "file_map.json").write_text(json.dumps({
        "vault_id": "gdrive",
        "updated_at": "2026-05-19T00:00:00+00:00",
        "files": {
            "id_keep": {"source_relpath": "keep.md", "source_mtime": "x",
                        "wiki_path": "wiki/sources/gdrive/keep.md", "bytes": 1,
                        "last_synced_at": "x"},
            "id_r1": {"source_relpath": "report/r1.md", "source_mtime": "x",
                      "wiki_path": "wiki/sources/gdrive/report/r1.md", "bytes": 1,
                      "last_synced_at": "x"},
            "id_r2": {"source_relpath": "report/sub/r2.md", "source_mtime": "x",
                      "wiki_path": "wiki/sources/gdrive/report/sub/r2.md", "bytes": 1,
                      "last_synced_at": "x"},
        },
    }), encoding="utf-8")

    # wiki source 페이지 — prefix 내 2건 + prefix 밖 2건
    src = home / "wiki" / "sources" / "gdrive"
    src.mkdir(parents=True)
    (src / "keep.md").write_text("keep page", encoding="utf-8")
    (src / "report_final.md").write_text("prefix 밖 (report/ 아님)", encoding="utf-8")
    (src / "report").mkdir()
    (src / "report" / "r1.md").write_text("report r1", encoding="utf-8")
    (src / "report" / "sub").mkdir()
    (src / "report" / "sub" / "r2.md").write_text("report r2", encoding="utf-8")
    return state_dir


# ---------------------------------------------------------------------------
# 1. dry-run (기본) — 쓰기 0
# ---------------------------------------------------------------------------

def test_dry_run_changes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """dry-run 기본 — wiki 파일·file_map 모두 변경되지 않는다."""
    state_dir = _setup(tmp_path)
    src = tmp_path / "wiki" / "sources" / "gdrive"

    rc = m.main(["--vault", "gdrive", "--home", str(tmp_path)])
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out["apply"] is False
    assert out["removed_file_map_entries"] == 2
    assert out["unlinked_pages"] == 2
    assert out["errors"] == []

    # wiki 페이지 모두 보존
    assert (src / "keep.md").exists()
    assert (src / "report" / "r1.md").exists()
    assert (src / "report" / "sub" / "r2.md").exists()
    # file_map 불변
    fm = json.loads((state_dir / "file_map.json").read_text())
    assert set(fm["files"].keys()) == {"id_keep", "id_r1", "id_r2"}
    assert fm["updated_at"] == "2026-05-19T00:00:00+00:00"
    # 백업 파일 미생성
    assert not list(state_dir.glob("file_map.json.bak-*"))


# ---------------------------------------------------------------------------
# 2. --apply — wiki unlink + file_map 프루닝 + 백업
# ---------------------------------------------------------------------------

def test_apply_unlinks_prefix_pages_and_prunes_file_map(
    tmp_path: Path, capsys: pytest.CaptureFixture,
) -> None:
    """--apply — prefix 하위 *.md 만 삭제, 밖은 보존, file_map 제거, 백업 생성."""
    state_dir = _setup(tmp_path)
    src = tmp_path / "wiki" / "sources" / "gdrive"

    rc = m.main(["--vault", "gdrive", "--home", str(tmp_path), "--apply"])
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out["apply"] is True
    assert out["removed_file_map_entries"] == 2
    assert out["unlinked_pages"] == 2
    assert out["errors"] == []

    # prefix 하위 *.md 만 삭제 + 빈 디렉터리 제거
    assert not (src / "report" / "r1.md").exists()
    assert not (src / "report" / "sub" / "r2.md").exists()
    assert not (src / "report").exists()
    # prefix 밖 파일 보존 ('report_final.md' 는 'report/' prefix 아님)
    assert (src / "keep.md").exists()
    assert (src / "report_final.md").exists()

    # file_map 엔트리 제거
    fm = json.loads((state_dir / "file_map.json").read_text())
    assert set(fm["files"].keys()) == {"id_keep"}

    # 백업 파일 생성 — 프루닝 전 상태 보존
    backups = list(state_dir.glob("file_map.json.bak-*"))
    assert len(backups) == 1
    backup_fm = json.loads(backups[0].read_text())
    assert set(backup_fm["files"].keys()) == {"id_keep", "id_r1", "id_r2"}


# ---------------------------------------------------------------------------
# 3. --strip-refs --apply — referenced_by 라인 수술
# ---------------------------------------------------------------------------

def test_apply_strip_refs(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """--strip-refs — sources/<vault>/<prefix> 항목만 제거, 빈 목록은 [] 단일 라인."""
    state_dir = _setup(tmp_path)
    ents = tmp_path / "wiki" / "entities"
    ents.mkdir(parents=True)

    # (1) 부분 제외 — 남은 항목은 보존
    (ents / "e_partial.md").write_text(
        "---\n"
        "title: 부분 제외\n"
        "referenced_by:\n"
        "  - sources/gdrive/report/r1.md\n"
        "  - sources/gdrive/other/o1.md\n"
        "---\n\n본문 부분\n",
        encoding="utf-8",
    )
    # (2) 전부 제외 — referenced_by: [] 단일 라인
    (ents / "e_empty.md").write_text(
        "---\n"
        "title: 전부 제외\n"
        "referenced_by:\n"
        "  - sources/gdrive/report/r1.md\n"
        "  - sources/gdrive/report/sub/r2.md\n"
        "---\n\n본문 전부\n",
        encoding="utf-8",
    )
    # (3) referenced_by 키 없음 — 건드리지 않음
    nokey_text = (
        "---\n"
        "title: 키 없음\n"
        "tags: []\n"
        "---\n\n본문 키없음\n"
    )
    (ents / "e_nokey.md").write_text(nokey_text, encoding="utf-8")

    rc = m.main(["--vault", "gdrive", "--home", str(tmp_path), "--apply", "--strip-refs"])
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out["stripped_ref_items"] == 3
    assert out["empty_ref_pages"] == 1
    assert out["errors"] == []

    # (1) — 제외 대상만 제거, 비제외 항목·본문 보존
    partial = (ents / "e_partial.md").read_text(encoding="utf-8")
    assert "sources/gdrive/report/r1.md" not in partial
    assert "referenced_by:\n  - sources/gdrive/other/o1.md\n" in partial
    assert "본문 부분" in partial

    # (2) — 빈 목록은 referenced_by: [] 단일 라인
    empty = (ents / "e_empty.md").read_text(encoding="utf-8")
    assert "referenced_by: []\n" in empty
    assert "sources/gdrive/report/" not in empty
    assert "본문 전부" in empty

    # (3) — 키 없는 페이지는 바이트 단위로 그대로
    assert (ents / "e_nokey.md").read_text(encoding="utf-8") == nokey_text


# ---------------------------------------------------------------------------
# 4. lock 점유 시 exit 3
# ---------------------------------------------------------------------------

def test_lock_held_returns_exit_3(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """다른 프로세스(=다른 fd)가 state_dir/.lock 을 flock 보유 중이면 exit 3."""
    _setup(tmp_path)
    lock_path = tmp_path / "_state" / "gdrive" / ".lock"
    lock_fd = open(lock_path, "w")
    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        rc = m.main(["--vault", "gdrive", "--home", str(tmp_path)])
    finally:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()
    capsys.readouterr()
    assert rc == 3


# ---------------------------------------------------------------------------
# 5. 목록 중간 빈 줄 — 현장 데이터 회귀 (WikiHub/Hermes 페이지 실측)
# ---------------------------------------------------------------------------

def test_apply_strip_refs_with_blank_line_inside_list(
    tmp_path: Path, capsys: pytest.CaptureFixture,
) -> None:
    """referenced_by 목록 중간에 빈 줄이 있어도 목록으로 인식해 참조를 전부 제거한다."""
    _setup(tmp_path)
    ents = tmp_path / "wiki" / "entities"
    ents.mkdir(parents=True)
    (ents / "e_blank.md").write_text(
        "---\n"
        "title: 빈 줄 포함\n"
        "referenced_by:\n"
        "  - sources/gdrive/report/r1.md\n"
        "\n"
        "  - sources/gdrive/report/sub/r2.md\n"
        "  - sources/gdrive/other/o1.md\n"
        "---\n\n본문 빈줄\n",
        encoding="utf-8",
    )

    rc = m.main(["--vault", "gdrive", "--home", str(tmp_path), "--apply", "--strip-refs"])
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out["stripped_ref_items"] == 2
    text = (ents / "e_blank.md").read_text(encoding="utf-8")
    assert "sources/gdrive/report/" not in text
    assert "sources/gdrive/other/o1.md" in text
    assert "본문 빈줄" in text


# ---------------------------------------------------------------------------
# 6. symlink escape 가드 — 실패 시 unlink 0건
# ---------------------------------------------------------------------------

def test_symlinked_vault_dir_aborts_without_unlink(
    tmp_path: Path, capsys: pytest.CaptureFixture,
) -> None:
    """wiki/sources/<vault> 가 symlink 면 실패로 기록하고 아무것도 삭제하지 않는다."""
    _setup(tmp_path)
    src = tmp_path / "wiki" / "sources" / "gdrive"
    # 실제 디렉터리를 외부로 옮기고 symlink 로 대체
    outside = tmp_path / "outside"
    src.rename(outside)
    src.symlink_to(outside)
    victim = outside / "report" / "r1.md"

    rc = m.main(["--vault", "gdrive", "--home", str(tmp_path), "--apply"])
    out = json.loads(capsys.readouterr().out)

    assert rc == 4
    assert out["errors"]
    assert out["unlinked_pages"] == 0
    assert victim.exists()

