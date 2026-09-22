"""log_integrity — log.md append 무결성 검출 테스트 (issue #211)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_HELPERS = Path(__file__).resolve().parent.parent / "scripts" / "_helpers"
sys.path.insert(0, str(_HELPERS))

_spec = importlib.util.spec_from_file_location("log_integrity", _HELPERS / "log_integrity.py")
L = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(L)


def _mklog(tmp_path: Path, body: str, vault: str = "nas") -> Path:
    p = tmp_path / "wiki" / "sources" / vault / "log.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _hdr(ts: str) -> str:
    return f"## {ts} KST\n\n- **Trigger**: systemd timer\n- **Status**: success\n\n"


# ── 기본 파싱 ────────────────────────────────────────────────────────────────
def test_header_and_field_parsing(tmp_path):
    p = _mklog(tmp_path, _hdr("2026-09-01 10:00:00") + _hdr("2026-09-01 11:00:00"))
    r = L.scan_log(p)
    assert r["headers"] == 2
    assert r["backwards"] == []
    assert r["bad_prefix"] == []
    assert r["field_names"].get("Trigger") == 2


def test_clock_without_seconds_is_valid(tmp_path):
    """초 생략 표기도 유효한 헤더다 (실측: 초 단위와 혼재)."""
    p = _mklog(tmp_path, _hdr("2026-09-01 10:00") + _hdr("2026-09-01 11:00"))
    r = L.scan_log(p)
    assert r["headers"] == 2
    assert r["malformed_headers"] == []


# ── (a) 헤더 시각 역행 ───────────────────────────────────────────────────────
def test_backwards_detected(tmp_path):
    """역행 1건 — 이슈 #211 의 실측 패턴 (직전보다 이른 시각)."""
    p = _mklog(tmp_path, _hdr("2026-08-22 07:01:49") + _hdr("2026-08-22 06:00:08"))
    r = L.scan_log(p)
    assert len(r["backwards"]) == 1
    b = r["backwards"][0]
    assert b["cur"].startswith("## 2026-08-22 06:00:08")
    assert b["delta_min"] == -62  # 실측 Δ 와 일치


def test_backwards_detects_second_level(tmp_path):
    """초 단위 역행도 잡는다 — 분만 보면 놓치는 케이스."""
    p = _mklog(tmp_path, _hdr("2026-09-01 10:00:30") + _hdr("2026-09-01 10:00:10"))
    r = L.scan_log(p)
    assert len(r["backwards"]) == 1


def test_monotonic_increasing_no_false_positive(tmp_path):
    """정상 증가는 오탐하지 않는다 (반대편 검증)."""
    p = _mklog(tmp_path, _hdr("2026-09-01 10:00:00") + _hdr("2026-09-01 11:00:00")
               + _hdr("2026-09-02 09:00:00"))
    r = L.scan_log(p)
    assert r["backwards"] == []


def test_timezone_mix_flagged_separately(tmp_path):
    """KST/UTC 혼재는 역행이 아니라 별도 신호로 잡는다."""
    p = _mklog(tmp_path, _hdr("2026-09-01 10:00:00")
               + "## 2026-09-01 02:00:00 UTC\n\n- **Trigger**: manual\n")
    r = L.scan_log(p)
    assert r["tz_mixed"] is True
    assert r["backwards"] == []  # 다른 tz 는 역행 비교에서 제외


# ── (b) 비정상 접두 ──────────────────────────────────────────────────────────
def test_bad_pipe_prefix_detected(tmp_path):
    """`|` 접두 — markdown 표로 오인한 흔적 (실측 860행)."""
    body = _hdr("2026-09-01 10:00:00") + "|- **Status**: skipped\n|-\n"
    p = _mklog(tmp_path, body)
    r = L.scan_log(p)
    assert len(r["bad_prefix"]) == 2
    assert r["bad_prefix"][0]["text"].startswith("|")


def test_normal_lines_not_flagged_as_prefix(tmp_path):
    p = _mklog(tmp_path, _hdr("2026-09-01 10:00:00"))
    r = L.scan_log(p)
    assert r["bad_prefix"] == []


# ── (c) 헤더 형식 / Trigger ─────────────────────────────────────────────────
def test_malformed_header_detected(tmp_path):
    body = "## 2026-09-01\n\n- **Trigger**: manual\n"
    p = _mklog(tmp_path, body)
    r = L.scan_log(p)
    assert len(r["malformed_headers"]) == 1
    assert r["headers"] == 0


def test_missing_trigger_detected(tmp_path):
    body = "## 2026-09-01 10:00:00 KST\n\n- **Status**: success\n"
    p = _mklog(tmp_path, body)
    r = L.scan_log(p)
    assert len(r["missing_trigger"]) == 1


def test_trigger_present_no_false_positive(tmp_path):
    p = _mklog(tmp_path, _hdr("2026-09-01 10:00:00"))
    r = L.scan_log(p)
    assert r["missing_trigger"] == []


# ── 스캔 범위 / 결정성 ──────────────────────────────────────────────────────
def test_archived_log_skipped(tmp_path):
    p = tmp_path / "wiki" / "sources" / ".archived" / "nas" / "log.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_hdr("2026-09-01 10:00:00"), encoding="utf-8")
    assert L.find_log_files(tmp_path) == []


def test_multiple_vaults_scanned(tmp_path):
    _mklog(tmp_path, _hdr("2026-09-01 10:00:00"), vault="nas")
    _mklog(tmp_path, _hdr("2026-09-01 10:00:00"), vault="gdrive")
    files = L.find_log_files(tmp_path)
    assert len(files) == 2
    assert files == sorted(files, key=str)  # 결정적 순서


def test_scan_result_json_serializable(tmp_path):
    p = _mklog(tmp_path, _hdr("2026-09-01 10:00:00") + "|bad\n")
    r = L.scan_log(p)
    json.dumps(r)  # 예외 없이 통과해야 한다


def test_no_log_files_returns_empty(tmp_path):
    (tmp_path / "wiki").mkdir()
    assert L.scan_all(tmp_path) == []


# ── 실측 패턴 회귀 (이슈 #211 실데이터) ─────────────────────────────────────
def test_issue_211_real_pattern(tmp_path):
    """이슈 본문의 실측 패턴: 역행 직후 정상 복귀 (단발).

    L2380 정상 → L2389 역행 → 이후 정상. 연쇄 오염이 아님을 고정한다.
    """
    body = (
        _hdr("2026-08-05 22:00:00")
        + _hdr("2026-08-06 06:20:45")
        + _hdr("2026-08-05 17:09:53")   # 역행 1건
        + _hdr("2026-08-06 07:00:00")   # 정상 복귀
    )
    p = _mklog(tmp_path, body)
    r = L.scan_log(p)
    assert len(r["backwards"]) == 1
    assert r["backwards"][0]["delta_min"] == -791  # 실측 Δ 와 일치
