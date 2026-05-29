#!/usr/bin/env python3
"""vault sync 진입점 (ADR-0035 rclone 단독 + OAuth 단일 인증).

호출: agent (Hermes·codex·gemini 등) 가 systemd unit ExecStart 의 subprocess 로 실행.

입출력:
- stdout: F2 ingest.md §Step 2 JSON contract (1줄 JSON)
- stderr: 진단/로그 (Python logging)
- exit code: 0 (성공) / 75 (Retryable) / 2 (Fatal)
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import sys
from pathlib import Path

# scripts/ 디렉토리를 sys.path 에 추가
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.config import load_wikihub_yaml  # noqa: E402
from lib.credentials import assert_rclone_config  # noqa: E402
from lib.exceptions import VaultSyncFatal, VaultSyncRetryable  # noqa: E402
from lib.mount import assert_mount_alive, vfs_refresh  # noqa: E402  # ADR-0025·0026
from lib.notify import notify_via_hermes  # noqa: E402
from lib.state import clear_last_failure, save_last_failure, utc_now_iso  # noqa: E402
from lib.sync import result_to_stdout_json, sync  # noqa: E402


log = logging.getLogger("vault-fetch")


def _setup_logging() -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def _emit_noop_stdout(vault_id: str) -> None:
    """disabled 또는 early-exit 시 F2 stdout contract emit."""
    sys.stdout.write(json.dumps({
        "vault_id": vault_id,
        "has_changes": False,
        "changed": [],
        "deleted": [],
        "duration_ms": 0,
    }, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(
        description="WikiHub vault sync (rclone lsjson + mount_diff, ADR-0035)",
    )
    parser.add_argument("--vault", required=True, help="wikihub.yaml.vaults[*].id")
    args = parser.parse_args(argv)

    # ADR-0024 writer 책임 — state_dir 생성 후의 fatal 만 last_failure.json 영속화
    state_dir: Path | None = None
    notify_on_fatal: bool = False

    try:
        cfg = load_wikihub_yaml()
        notify_on_fatal = cfg.agent.notify_on_fatal
        if args.vault not in cfg.vaults:
            raise VaultSyncFatal(
                vault_id=args.vault,
                reason=f"wikihub.yaml.vaults 에 '{args.vault}' 정의 없음",
                remediation="vault id 오타 확인 또는 wikihub.yaml 수정 후 /wh:setup 재호출.",
            )
        vault_cfg = cfg.vaults[args.vault]
        if not vault_cfg.enabled:
            log.info("vault %s disabled — no-op", args.vault)
            _emit_noop_stdout(args.vault)
            return 0

        # ADR-0035: rclone.conf 단일 인증 자료. credentials_path 검증 폐기.
        rclone_remote_name = vault_cfg.options.get("rclone_remote_name", args.vault)
        assert_rclone_config(args.vault, rclone_remote_name)

        state_dir = cfg.instance_root / "_state" / args.vault
        state_dir.mkdir(parents=True, exist_ok=True)

        # ADR-0025·0026 — mount liveness check + vfs refresh
        # mount_path 는 yaml.vaults[*].options.mount_path 가 정본. 폴백으로 vault_cfg.local_path.
        mount_path_raw = vault_cfg.options.get("mount_path") or str(vault_cfg.local_path)
        mount_path = Path(mount_path_raw).expanduser()
        rc_addr = os.environ.get("RCLONE_RC_ADDR")
        if not rc_addr:
            # vault@.service 가 RCLONE_RC_ADDR 주입. dev box 수동 실행 시 yaml 에서 산출.
            rc_port = vault_cfg.options.get("rclone_rc_port", 5572)
            rc_addr = f"127.0.0.1:{rc_port}"

        assert_mount_alive(args.vault, mount_path, state_dir=state_dir)
        if cfg.operations.vfs_refresh_mode == "recursive":
            vfs_refresh(args.vault, rc_addr, state_dir=state_dir, recursive=True)
        elif cfg.operations.vfs_refresh_mode == "per-file":
            # K2 (per-file) — v0.2.x deferred. v0.1.0 fallback 으로 recursive.
            log.warning("vfs_refresh_mode=per-file 은 v0.2.x deferred. recursive 로 폴백.")
            vfs_refresh(args.vault, rc_addr, state_dir=state_dir, recursive=True)
        # vfs_refresh_mode=none — refresh skip (운영자가 명시적으로 off, 위험 인지)

        # 동시 invocation 방지 — state_dir/.lock 에 LOCK_EX|LOCK_NB.
        # 경고: fcntl.flock(2) 는 NFS 등 네트워크 파일시스템에서 동작이 보장되지 않음.
        # v0.1.0 단일 서버(OCI ARM 로컬 디스크) 모델에서는 문제없으나,
        # 분산 배포(여러 인스턴스가 동일 NFS state_dir 공유) 시 race 가능.
        # 분산 배포 전환 시 server-id prefix 로 state_dir 격리 또는 외부 lock 으로 대체 필요.
        lock_path = state_dir / ".lock"
        with open(lock_path, "w") as lock_fd:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as e:
                raise VaultSyncRetryable(
                    vault_id=args.vault,
                    retry_after_sec=120,
                    reason=f"concurrent vault-fetch in progress (lock: {lock_path})",
                ) from e

            result = sync(
                vault_cfg=vault_cfg,
                instance_root=cfg.instance_root,
                state_dir=state_dir,
            )
            sys.stdout.write(result_to_stdout_json(result) + "\n")
            sys.stdout.flush()
            log.info(
                "sync ok: vault=%s changed=%d deleted=%d duration_ms=%d",
                result.vault_id, len(result.changed), len(result.deleted), result.duration_ms,
            )
            # ADR-0024: success 시 연속 fatal 카운트 리셋
            clear_last_failure(state_dir)
            return 0

    except VaultSyncRetryable as e:
        log.warning("retryable: %s", e)
        return 75
    except VaultSyncFatal as e:
        log.error("fatal: %s", e)
        if state_dir is not None:
            if notify_on_fatal:
                notify_via_hermes(e.vault_id, e.reason)
            now = utc_now_iso()
            save_last_failure(state_dir, {
                "vault_id": e.vault_id,
                "exit_code": 2,
                "severity": "fatal",
                "scope": getattr(e, "scope", "vault"),
                "reason": e.reason,
                "remediation": e.remediation,
                "source_id": None,
                "first_failed_at": now,
                "last_failed_at": now,
                "failed_count": 1,
                "alerted_at": None,
            })
        return 2
    except Exception as e:  # noqa: BLE001
        log.exception("unexpected error: %s", e)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
