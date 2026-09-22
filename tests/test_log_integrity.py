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


# ══ 2차 리뷰 [mid]·[low] 회귀 — 실측 재현된 결함 ═════════════════════════════
def test_mixed_clock_formats_same_instant_not_backwards(tmp_path):
    """[mid] 초 표기가 섞여도 **같은 시각**이면 역행이 아니다.

    리뷰가 지적한 케이스는 `10:00:00` → `10:00` (둘 다 10:00:00) 이다.
    문자열 비교는 `'10:00' > '10:00:00'` 이 참이라 Δ-1m 오탐을 낸다.
    """
    p = _mklog(tmp_path, _hdr("2026-03-15 10:00:00") + _hdr("2026-03-15 10:00"))
    r = L.scan_log(p)
    assert r["backwards"] == [], f"오탐: {r['backwards']}"


def test_seconds_backwards_detected_with_mixed_format(tmp_path):
    """[mid] 반대편 — 초 단위 역행은 실제로 잡아야 한다 (초 표기 혼재).

    `10:00:30` → `10:00` 은 30초 역행이므로 **정탐**이 맞다. 정수 튜플 비교가
    이 케이스를 놓치지 않는지 고정한다 (문자열 비교도 우연히 잡지만 근거가 다르다).
    """
    p = _mklog(tmp_path, _hdr("2026-03-15 10:00:30") + _hdr("2026-03-15 10:00"))
    r = L.scan_log(p)
    assert len(r["backwards"]) == 1
    assert r["backwards"][0]["delta_min"] == -1


def test_clock_key_orders_correctly():
    """[mid] `_clock_key` 가 실제 시각 순서를 만든다."""
    assert L._clock_key("10:00") == L._clock_key("10:00:00")
    assert L._clock_key("10:00") < L._clock_key("10:00:30")
    assert L._clock_key("09:59:59") < L._clock_key("10:00")
    assert L._clock_key("10:00:30") < L._clock_key("10:01")


def test_trigger_substring_does_not_mask_missing(tmp_path):
    """[low] 필드명이 `Trigger source` 같은 다른 필드는 Trigger 로 인정하지 않는다."""
    body = "## 2026-09-01 10:00:00 KST\n\n- **Trigger source**: x\n- **Triggered-by**: y\n"
    p = _mklog(tmp_path, body)
    r = L.scan_log(p)
    assert len(r["missing_trigger"]) == 1, "substring 오판"


def test_exact_trigger_field_is_accepted(tmp_path):
    """[low] 반대편 — 정확한 `Trigger` 필드는 인정한다."""
    body = "## 2026-09-01 10:00:00 KST\n\n- **Trigger**: systemd timer\n"
    p = _mklog(tmp_path, body)
    r = L.scan_log(p)
    assert r["missing_trigger"] == []


def test_sortkey_is_json_serializable(tmp_path):
    """sortkey 가 튜플이 되어도 JSON 직렬화는 유지돼야 한다."""
    p = _mklog(tmp_path, _hdr("2026-09-01 10:00:00"))
    r = L.scan_log(p)
    # 내부 sortkey 는 headers 가 아니라 backwards 에만 노출된다.
    json.dumps(r)

