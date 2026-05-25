#!/usr/bin/env python3
"""WikiHub Monitor — 12hr 윈도우 운영 보고서 발송.

``wikihub-monitor.timer`` (매일 09:00, 21:00 KST) 가 호출:
1. 지난 12hr journal (`wikihub-vault@<vid>.service` per vault + `wikihub-lint.service`) 수집
2. 정적 보고서 생성 (LLM 없음, 결정적 포맷)
3. 보고서 파일 저장 — ``$WIKIHUB_HOME/vault/<vault_id>/<subpath>/YYYYMMDD__HH_mm.md``
4. Telegram 발송 — ``TELEGRAM_MONITOR_BOT_TOKEN`` + ``TELEGRAM_MONITOR_CHAT_ID`` 재사용 (ADR-0037)

exit code:
- 0 — 정상 (보고서 발송 + 파일 저장 성공)
- 2 — bootstrap fail (config load 실패 등) → OnFailure=ops-alert 발화
- 75 — runtime fail (telegram 발송 fail 등) → SuccessExitStatus 정합, 12hr 후 자연 재시도
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

# scripts/ 디렉토리를 sys.path 에 추가 (pending_monitor.py / ops-alert.py 패턴 정합)
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.config import Config, load_wikihub_yaml  # noqa: E402
from lib.telegram import send_telegram  # noqa: E402

log = logging.getLogger("wikihub-monitor")

KST = timezone(timedelta(hours=9))

# systemd unit 종료 entry 식별 — `_SYSTEMD_UNIT_RESULT` / `EXIT_STATUS` 가 1차 자료원.
# MESSAGE_ID 는 보조 (보존하나 우선순위 낮음 — 정확한 unit-stopped MESSAGE_ID 는 systemd 버전마다 변동).
_MESSAGE_ID_UNIT_STOPPED = "9d1aaa27d60140bd96365438aad20286"  # SD_MESSAGE_UNIT_STOPPED

# Telegram bot message size limit (4096 chars) — cap 보수적으로 4000
_TELEGRAM_MAX_CHARS = 4000
_TRUNCATE_MARKER = "\n\n[보고서 cap — journalctl --user -u wikihub-monitor 로 전체 확인]"

# Journal entry collect cap (메모리 폭증 가드)
_JOURNAL_LINES_CAP = 10000

# subprocess timeout (journalctl 호출)
_SUBPROCESS_TIMEOUT_SEC = 30

# 실패 reason 추출 cap
_REASON_CAP_CHARS = 100


@dataclass
class ServiceRun:
    """Service unit 의 한 fire 결과."""

    timestamp: datetime  # service 종료 시각 (없으면 시작 시각)
    success: bool        # exit 0 또는 75 = True
    exit_code: int | None = None
    reason: str | None = None
    # lint 전용 (chain 의 별도 단계 — 시각은 lint.service run 과 공유)
    graphify_status: Literal["success", "skipped", "timeout", "partial", "failed", "unknown"] | None = None
    graphify_detail: str | None = None  # success: "N=... M=...", partial: ratio, failed: reason 등


def _setup_logging() -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def collect_journal(unit: str, since_epoch: int) -> list[dict[str, Any]]:
    """journalctl --user -u <unit> -o json 출력을 파싱해 entry list 반환.

    H1: TZ 무관 ``@<epoch>`` 형식.
    H2: ``--no-pager`` 명시.
    H3: ``timeout=30`` subprocess.
    H4: ``--lines=10000`` hard cap (메모리 폭증 가드).
    """
    cmd = [
        "journalctl",
        "--user",
        "-u",
        unit,
        "-o",
        "json",
        "--no-pager",
        f"--lines={_JOURNAL_LINES_CAP}",
        "--since",
        f"@{since_epoch}",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_SEC,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log.warning("journalctl timeout unit=%s", unit)
        return []

    if result.returncode != 0:
        log.warning(
            "journalctl 실패 unit=%s exit=%d stderr=%s",
            unit,
            result.returncode,
            result.stderr[:200],
        )
        return []

    entries: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as e:
            log.debug("journal entry parse 실패: %s — skip", e)
    return entries


def _ts_from_journal(entry: dict[str, Any]) -> datetime:
    """journal entry 의 __REALTIME_TIMESTAMP (μs epoch) → datetime KST."""
    raw = entry.get("__REALTIME_TIMESTAMP", "0")
    try:
        usec = int(raw)
    except (TypeError, ValueError):
        usec = 0
    return datetime.fromtimestamp(usec / 1_000_000, tz=KST)


def parse_runs(entries: list[dict[str, Any]]) -> list[ServiceRun]:
    """journal entries → ServiceRun list.

    종료 entry 안정 식별 = MESSAGE_ID. EXIT_STATUS / _SYSTEMD_UNIT_RESULT 가 종료 entry 에만 emit.
    종료 entry 가 없는 trailing 묶음 = 진행 중 또는 unknown — skip.
    """
    runs: list[ServiceRun] = []
    current_run_entries: list[dict[str, Any]] = []

    for entry in entries:
        current_run_entries.append(entry)
        msg_id = entry.get("MESSAGE_ID", "")
        unit_result = entry.get("_SYSTEMD_UNIT_RESULT")
        exit_status_raw = entry.get("EXIT_STATUS")

        is_terminal = bool(
            msg_id == _MESSAGE_ID_UNIT_STOPPED
            or unit_result is not None
            or exit_status_raw is not None
        )
        if not is_terminal:
            continue

        try:
            exit_code = int(exit_status_raw) if exit_status_raw is not None else None
        except (TypeError, ValueError):
            exit_code = None

        # success = exit 0 or 75 (SuccessExitStatus 정합)
        success = exit_code in (0, 75) or unit_result == "success"
        reason = None
        if not success:
            reason = extract_failure_reason(current_run_entries)

        runs.append(
            ServiceRun(
                timestamp=_ts_from_journal(entry),
                success=success,
                exit_code=exit_code,
                reason=reason,
            )
        )
        current_run_entries = []

    return runs


def extract_failure_reason(run_entries: list[dict[str, Any]]) -> str:
    """실패 run 의 마지막 ERROR/WARNING MESSAGE 5줄 + 100 chars cap.

    PRIORITY 3 = error, 4 = warning (RFC 5424).
    """
    candidates: list[str] = []
    for entry in reversed(run_entries):
        prio = entry.get("PRIORITY")
        try:
            prio_int = int(prio) if prio is not None else 6
        except (TypeError, ValueError):
            prio_int = 6
        if prio_int <= 4:  # err or warn
            msg = str(entry.get("MESSAGE", "")).strip()
            if msg:
                candidates.append(msg)
        if len(candidates) >= 5:
            break

    if not candidates:
        # fallback — 마지막 MESSAGE 1줄
        for entry in reversed(run_entries):
            msg = str(entry.get("MESSAGE", "")).strip()
            if msg:
                candidates.append(msg)
                break

    reason = " | ".join(reversed(candidates))
    return reason[:_REASON_CAP_CHARS]


def extract_graphify_status(
    lint_run: ServiceRun,
    cfg: Config,
    report_path: Path,
) -> tuple[Literal["success", "skipped", "timeout", "partial", "unknown"], str | None]:
    """lint run 의 graphify chain 상태를 ``wiki/_lint/report.md`` 정본에서 추출.

    1차: ``$WIKIHUB_HOME/wiki/_lint/report.md`` tail 마지막 50줄 grep
    2차 (fallback): journal MESSAGE pattern matching — 본 함수에서는 1차만 (caller 가 보강).

    ※ ``_lint/report.md`` 는 lint cycle 별 overwrite (lint.md §"산출물" 정책). 12hr 윈도우
       안 lint 가 N회 실행돼도 report.md 는 가장 최근 1회의 결과만 보존 — caller 가 마지막
       lint_run 에만 본 함수 호출하고 나머지 run 의 graphify_status 는 "unknown (overwrite)"
       으로 surface 권장 (Step 4 code_review_2 H1 흡수).
    """
    if not report_path.exists():
        return ("unknown", "report.md 부재")

    try:
        # tail 마지막 50줄
        text = report_path.read_text(encoding="utf-8", errors="replace")
        tail = "\n".join(text.splitlines()[-50:])
    except OSError as e:
        return ("unknown", f"report.md read 실패: {e}")

    # 1차 키워드 grep (정본 마커 — lint.md Step 9 정합):
    # - 성공: `graph rebuilt: N nodes, M edges`
    # - 실패: `graph rebuild failed: <reason>` / `graph rebuild timeout`
    # - skip: `graphify chain skipped (yaml toggle)`
    # - partial: `graphify partial failure 의심: N=<N>, M=<M>, ratio=<r>`
    if "graphify chain skipped (yaml toggle)" in tail:
        return ("skipped", "yaml toggle")
    if "graph rebuild timeout" in tail:
        return ("timeout", None)
    m_partial = re.search(
        r"graphify partial failure 의심: N=(\d+), M=(\d+), ratio=([0-9.]+)",
        tail,
    )
    if m_partial:
        return ("partial", f"N={m_partial.group(1)} M={m_partial.group(2)} ratio={m_partial.group(3)}")
    m_failed = re.search(r"graph rebuild failed:\s*([^\n]+)", tail)
    if m_failed:
        reason = m_failed.group(1).strip()[:80]
        return ("failed", reason)
    m_ok = re.search(r"graph rebuilt:\s*(\d+)\s*nodes?,\s*(\d+)\s*edges?", tail)
    if m_ok:
        return ("success", f"N={m_ok.group(1)} M={m_ok.group(2)}")

    return ("success", None)


def _resolve_wikihub_home(cfg: Config) -> Path:
    """WIKIHUB_HOME 경로 결정 우선순위 (Step 4 code_review_1 H3 / code_review_2 M3 흡수):

    1. ``WIKIHUB_HOME`` env (systemd service template `Environment=WIKIHUB_HOME=...`)
    2. ``cfg.instance_root`` (yaml 정본)
    3. ``WIKIHUB_YAML`` env 의 parent
    4. ``~/wikihub`` (fallback)
    """
    env_home = os.environ.get("WIKIHUB_HOME", "").strip()
    if env_home:
        return Path(env_home).expanduser()
    if cfg.instance_root:
        return Path(str(cfg.instance_root)).expanduser()
    yaml_env = os.environ.get("WIKIHUB_YAML", "").strip()
    if yaml_env:
        return Path(yaml_env).expanduser().parent
    return Path.home() / "wikihub"


def _resolve_report_path(cfg: Config, window_end: datetime) -> Path:
    """보고서 파일 저장 경로 — ``$WIKIHUB_HOME/vault/<vid>/<subpath>/YYYYMMDD__HH_mm.md``.

    ``operations.monitor_report_vault`` 명시 시 그 vault, None 이면 첫 enabled vault.
    """
    wikihub_home = _resolve_wikihub_home(cfg)

    enabled_vaults = [vid for vid, v in cfg.vaults.items() if v.enabled]
    target_vid = cfg.operations.monitor_report_vault or (enabled_vaults[0] if enabled_vaults else None)
    if target_vid is None:
        raise ValueError("monitor_report_vault 미지정 + 활성 vault 없음")

    subpath = cfg.operations.monitor_report_subpath.strip("/")
    fname = window_end.strftime("%Y%m%d__%H_%M.md")
    return wikihub_home / "vault" / target_vid / subpath / fname


def format_report(
    ingest_results: dict[str, list[ServiceRun]],
    lint_results: list[ServiceRun],
    window_start: datetime,
    window_end: datetime,
) -> str:
    """정적 보고서 생성 — 사용자 제시 라인 단위 포맷."""
    lines: list[str] = []
    lines.append(
        f"🔭 WikiHub Monitor — {window_end.strftime('%Y-%m-%d %H:%M')} (KST)"
    )
    lines.append(
        f"윈도우: {window_start.strftime('%Y-%m-%d %H:%M')} ~ {window_end.strftime('%Y-%m-%d %H:%M')} (12hr)"
    )
    lines.append("")

    # wh-ingest 섹션 (vault 별)
    if not ingest_results:
        lines.append("wh-ingest")
        lines.append("  (활성 vault 없음)")
        lines.append("")
    else:
        for vid, runs in ingest_results.items():
            lines.append(f"wh-ingest [vault: {vid}]")
            if not runs:
                lines.append("  (12hr 동안 실행 없음)")
            else:
                success_n = sum(1 for r in runs if r.success)
                fail_n = len(runs) - success_n
                for r in runs:
                    ts = r.timestamp.strftime("%Y-%m-%d %H:%M")
                    if r.success:
                        lines.append(f"  {ts} : 성공")
                    else:
                        reason = r.reason or "unknown"
                        ec = r.exit_code if r.exit_code is not None else "?"
                        lines.append(f"  {ts} : 실패 (exit {ec}, {reason})")
                lines.append(
                    f"  (윈도우 내 {len(runs)}회 — 성공 {success_n} / 실패 {fail_n})"
                )
            lines.append("")

    # wh-lint 섹션 — lint + graphify chain 각 단계 분리 표시.
    # 시각: lint.service journal 의 단일 terminal entry 기반 (chain 두 단계가 같은 service run).
    lines.append("wh-lint (lint + graphify chain)")
    if not lint_results:
        lines.append("  (12hr 동안 실행 없음)")
    else:
        lint_success_n = sum(1 for r in lint_results if r.success)
        graphify_success_n = sum(1 for r in lint_results if r.graphify_status == "success")
        graphify_skipped_n = sum(1 for r in lint_results if r.graphify_status == "skipped")
        graphify_timeout_n = sum(1 for r in lint_results if r.graphify_status == "timeout")
        graphify_partial_n = sum(1 for r in lint_results if r.graphify_status == "partial")
        graphify_failed_n = sum(1 for r in lint_results if r.graphify_status == "failed")

        for r in lint_results:
            ts = r.timestamp.strftime("%Y-%m-%d %H:%M")
            # lint 라인
            if r.success:
                lint_line = f"  {ts} (lint) : 성공"
            else:
                ec = r.exit_code if r.exit_code is not None else "?"
                lint_line = f"  {ts} (lint) : 실패 (exit {ec}, {r.reason or 'unknown'})"
            lines.append(lint_line)

            # graphify 라인
            gstatus = r.graphify_status or "unknown"
            gdetail = r.graphify_detail
            if gstatus == "success":
                graphify_line = f"  {ts} (graphify) : 성공" + (f" ({gdetail})" if gdetail else "")
            elif gstatus == "skipped":
                graphify_line = f"  {ts} (graphify) : skipped" + (f" ({gdetail})" if gdetail else "")
            elif gstatus == "timeout":
                graphify_line = f"  {ts} (graphify) : 실패 (timeout)"
            elif gstatus == "partial":
                graphify_line = f"  {ts} (graphify) : partial failure" + (f" ({gdetail})" if gdetail else "")
            elif gstatus == "failed":
                graphify_line = f"  {ts} (graphify) : 실패" + (f" ({gdetail})" if gdetail else "")
            else:  # unknown
                graphify_line = f"  {ts} (graphify) : ?" + (f" ({gdetail})" if gdetail else "")
            lines.append(graphify_line)

        lines.append(
            f"  (윈도우 내 {len(lint_results)}회 — "
            f"lint 성공 {lint_success_n} / "
            f"graphify 성공 {graphify_success_n} · skipped {graphify_skipped_n} · "
            f"timeout {graphify_timeout_n} · partial {graphify_partial_n} · "
            f"failed {graphify_failed_n})"
        )

    return "\n".join(lines)


def write_report_file(report: str, window_end: datetime, cfg: Config) -> Path:
    """보고서 파일 저장 — atomic (.tmp → rename)."""
    path = _resolve_report_path(cfg, window_end)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    body = f"# WikiHub Monitor — {window_end.strftime('%Y-%m-%d %H:%M')} (KST)\n\n```\n{report}\n```\n"
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)
    return path


def send_report(bot_token: str, chat_id: str, text: str) -> bool:
    """Telegram 발송 — plain text (parse_mode=None), 4000 char cap + truncate marker."""
    if len(text) > _TELEGRAM_MAX_CHARS:
        cap = _TELEGRAM_MAX_CHARS - len(_TRUNCATE_MARKER)
        text = text[:cap] + _TRUNCATE_MARKER
    return send_telegram(bot_token, chat_id, text, parse_mode=None, timeout_sec=10)


def _emit_bootstrap_alert(reason: str) -> None:
    """bootstrap fail 시 OnFailure=ops-alert 가 last_failure.json 부재로 silent — monitor 가
    자체적으로 telegram alert 발송 (Step 4 code_review_2 H2 흡수).

    env token 미설정 시 silent (journal log.error 만 surface).
    """
    bot_token = os.environ.get("TELEGRAM_MONITOR_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_MONITOR_CHAT_ID", "").strip()
    if not (bot_token and chat_id):
        log.error("bootstrap fail + Telegram env 미설정 — journal log 만")
        return
    try:
        send_telegram(
            bot_token,
            chat_id,
            f"🚨 wikihub-monitor BOOTSTRAP FAIL\n\n{reason}",
            parse_mode=None,
            timeout_sec=10,
        )
    except Exception as e:
        log.error("bootstrap alert send 실패: %s", e)


def main(argv: list[str] | None = None) -> int:
    _setup_logging()

    # 1. config load — bootstrap fail = exit 2.
    # ops-alert.service 의 OnFailure 가 last_failure.json 부재로 silent → monitor 가
    # 자체 telegram alert 발송 후 exit 2 (code_review_2 H2 흡수).
    try:
        cfg = load_wikihub_yaml()
    except Exception as e:
        log.error("config load 실패: %s — bootstrap fail (exit 2)", e)
        _emit_bootstrap_alert(f"config load 실패: {e}")
        return 2

    if not cfg.operations.monitor_enabled:
        log.info("operations.monitor_enabled = false — skip")
        return 0

    bot_token = os.environ.get("TELEGRAM_MONITOR_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_MONITOR_CHAT_ID", "").strip()
    if not (bot_token and chat_id):
        log.warning(
            "TELEGRAM_MONITOR_BOT_TOKEN/CHAT_ID 미설정 — monitor skip "
            "(~/.config/wikihub/env 에 설정 권장)"
        )
        return 0

    # 2. 윈도우 — TZ 무관 @epoch 형식
    window_end = datetime.now(tz=KST)
    window_start = window_end - timedelta(hours=12)
    since_epoch = int(window_start.timestamp())

    # 3. vault_ids — Config.vaults 가 dict[str, VaultConfig]
    vault_ids = [vid for vid, v in cfg.vaults.items() if v.enabled]

    # 4. journal collect
    ingest_entries_per_vault = {
        vid: collect_journal(f"wikihub-vault@{vid}.service", since_epoch)
        for vid in vault_ids
    }
    lint_entries = collect_journal("wikihub-lint.service", since_epoch)

    # 5. parse runs
    ingest_results = {
        vid: parse_runs(entries) for vid, entries in ingest_entries_per_vault.items()
    }
    lint_results = parse_runs(lint_entries)

    # 6. graphify 상태 — wiki/_lint/report.md 정본 1차.
    # ※ report.md 는 lint cycle 별 overwrite — 가장 최근 lint_run 1개에만 정확. 나머지 run 은
    #   "unknown (overwrite)" surface (Step 4 code_review_2 H1 흡수).
    wikihub_home = _resolve_wikihub_home(cfg)
    report_path = wikihub_home / "wiki" / "_lint" / "report.md"
    if lint_results:
        status, detail = extract_graphify_status(lint_results[-1], cfg, report_path)
        lint_results[-1].graphify_status = status
        lint_results[-1].graphify_detail = detail
        for older_run in lint_results[:-1]:
            older_run.graphify_status = "unknown"
            older_run.graphify_detail = "overwrite (report.md per-cycle)"

    # 7. format + write + send
    report = format_report(ingest_results, lint_results, window_start, window_end)

    try:
        saved_path = write_report_file(report, window_end, cfg)
        log.info("보고서 파일 저장: %s", saved_path)
    except Exception as e:
        log.warning("보고서 파일 write 실패: %s — telegram 발송 계속", e)

    ok = send_report(bot_token, chat_id, report)
    if not ok:
        log.warning(
            "telegram 발송 실패 — 12hr 후 자연 재시도 (exit 75, SuccessExitStatus 정합)"
        )
        return 75

    log.info("monitor 정상 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
