"""rclone mount lifecycle helpers (ADR-0024 v9 · 0025 · 0026 · 0027 정본).

본 모듈은 vault-fetch.py 사이클 시작 시 mount liveness check + vfs cache invalidation
을 수행. mount permanently failed / OAuth revoke 등 fatal case 는 ADR-0024 v9 의
last_failure (scope="mount") writer 책임을 직접 수행.

사이클 흐름 (vault-fetch.py 에서 호출, R15-L2 module prefix 정리):

    assert_mount_alive(vault_id, mount_path, state_dir)
    vfs_refresh(vault_id, rc_addr, state_dir, recursive=True)
    # ... gws drive changes list → _resolve_mount_path → _read_from_mount → ...

실패 분류:
- `VaultSyncRetryable` (exit 75) — 호출자가 사이클 abort. mount.service Restart=always 가 daemon 자체 복구.
- `VaultSyncFatal` (exit 2, scope="mount") — last_failure.json 영속화 + ops-alert 발화.
  - `assert_mount_alive` Retryable 가 ``MOUNT_RETRYABLE_FATAL_THRESHOLD`` 회 누적 시 escalate
  - `vfs_refresh` 의 rclone stderr 에서 OAuth error 패턴 매칭 시
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .exceptions import VaultSyncFatal, VaultSyncRetryable
from .state import read_last_failure, save_last_failure, utc_now_iso


# v9 R13-CRIT-1 — rclone OAuth/SA error 패턴. V18 (2026-05-17) 후 SA 패턴 추가.
#
# OAuth 시대 (ADR-0003, Superseded):
#   - "Token expired" — access token 만료 (refresh token revoke 케이스 분리 불가지만 동일 fatal)
#   - "invalid_grant" — refresh token 거부 (revoke / 회전 / 만료)
#   - "401 Unauthorized" — generic 401
#   - "oauth2.*invalid" / "unauthorized_client" / "access_denied" — OAuth flow 다양한 fail
#
# SA 시대 (ADR-0029, V18 결함 #6 fix):
#   - "private key should be a PEM" — SA JSON 의 private_key 가 PEM 형식 위반 / corrupt
#   - "asn1: structure error" — private_key DER decode fail
#   - "service account.*disabled" / "key.*disabled" — Cloud Console SA 또는 key disable
#   - "invalid_credentials" — credentials 일반
#   - "no such file or directory.*\.credentials/sa_" — credentials_path 파일 사라짐 (R15-M5
#     V<N> R15 리뷰 — 이전 `sa_` literal 은 Drive 폴더의 정상 파일명 `sa_report.docx` 에도
#     매칭하는 false positive 위험. `.credentials/sa_` 으로 narrow)
_RCLONE_AUTH_PATTERNS = re.compile(
    r"("
    r"Token expired|invalid_grant|401 Unauthorized|oauth2.*invalid|"
    r"unauthorized_client|access_denied|"
    r"private key should be|asn1: structure error|"
    r"service account.*disabled|key.*disabled|"
    r"invalid_credentials|no such file or directory.*\.credentials/sa_"
    r")",
    re.IGNORECASE,
)

# v9 R14-HIGH-4 — Retryable 누적 escalation 임계. 약 1시간 @ 10min cycle.
MOUNT_RETRYABLE_FATAL_THRESHOLD = 6


def assert_mount_alive(
    vault_id: str,
    mount_path: Path,
    state_dir: Path | None = None,
    timeout_sec: int = 5,
) -> None:
    """mount path 가 FUSE 응답 가능 상태인지 timeout 보장된 subprocess 로 검증.

    v9 R13-HIGH-2 + R14-HIGH-3: `ls -la` 의 stdout 이 대용량 vault 에서 메모리 폭발 (~10MB/50k 파일).
    `stat <path>` 로 교체 — directory 자체의 stat syscall 만 발행, stdout ~200B 고정.

    v9 R14-HIGH-4 (Retryable 누적 escalation):
    - state_dir 제공 시 직전 last_failure 의 failed_count >= THRESHOLD 면 Fatal escalate.
    - state_dir=None: v8 동작 (Retryable only) — 호출자가 state_dir 없이 호출하는 path 호환성.

    Args:
        vault_id: state_dir 식별. last_failure.json 의 vault_id 필드 정합.
        mount_path: rclone mount point (`<instance_root>/vault/<vault_id>/`).
        state_dir: vault state 디렉토리 (`<instance_root>/_state/<vault_id>/`). None 이면 escalation 안 함.
        timeout_sec: stat 호출의 timeout (default 5s).

    Raises:
        VaultSyncRetryable: hung FUSE (timeout) 또는 dead mount (exit non-zero). 누적 < THRESHOLD.
        VaultSyncFatal: 누적 >= THRESHOLD. last_failure.json (scope="mount") 도 함께 저장.
    """
    try:
        result = subprocess.run(
            ["stat", str(mount_path)],
            capture_output=True, text=True, timeout=timeout_sec, check=False,
        )
        if result.returncode != 0:
            reason = (
                f"mount path stat 실패 (rc={result.returncode}) — mount.service 미준비/dead: "
                f"{mount_path}, stderr={result.stderr[:200]!r}"
            )
            _raise_mount_failure(vault_id, state_dir, reason)
    except subprocess.TimeoutExpired:
        reason = f"mount path stat timeout ({timeout_sec}s) — hung FUSE 가능: {mount_path}"
        _raise_mount_failure(vault_id, state_dir, reason)


def _raise_mount_failure(vault_id: str, state_dir: Path | None, reason: str) -> None:
    """Retryable vs Fatal 판단 + last_failure writer.

    누적 카운트 결정:
    - state_dir 부재 → Retryable (escalation 없음)
    - state_dir 의 last_failure.json 부재 → Retryable (첫 fail)
    - last_failure.json 있으나 scope != "mount" → Retryable (다른 fault 경로의 잔재)
    - last_failure.json 의 failed_count + 1 < THRESHOLD → Retryable
    - last_failure.json 의 failed_count + 1 >= THRESHOLD → Fatal escalate
    """
    if state_dir is not None:
        prev = read_last_failure(state_dir)
        if prev is not None and prev.get("scope") == "mount":
            prev_count = int(prev.get("failed_count", 0))
            if prev_count + 1 >= MOUNT_RETRYABLE_FATAL_THRESHOLD:
                save_last_failure(state_dir, {
                    "vault_id": vault_id,
                    "exit_code": 2,
                    "severity": "fatal",
                    "scope": "mount",
                    "reason": f"mount Retryable {prev_count + 1}회 연속 누적 — escalate: {reason}",
                    "remediation": (
                        f"systemctl --user status wikihub-mount@{vault_id}.service && "
                        f"systemctl --user reset-failed wikihub-mount@{vault_id}.service && "
                        f"systemctl --user restart wikihub-mount@{vault_id}.service"
                    ),
                    "source_id": None,
                    "first_failed_at": prev.get("first_failed_at") or utc_now_iso(),
                    "last_failed_at": utc_now_iso(),
                    "failed_count": prev_count + 1,
                    "alerted_at": None,
                })
                raise VaultSyncFatal(
                    vault_id=vault_id,
                    reason=f"mount permanently failed ({prev_count + 1}회 누적): {reason}",
                    remediation=(
                        f"systemctl --user restart wikihub-mount@{vault_id}.service"
                    ),
                    scope="mount",   # V<N> Phase 2 결함 #7 fix
                )

    # 첫 fail 또는 임계 미달 → Retryable + last_failure 누적 (mount scope)
    if state_dir is not None:
        now = utc_now_iso()
        save_last_failure(state_dir, {
            "vault_id": vault_id,
            "exit_code": 75,
            "severity": "retryable",
            "scope": "mount",
            "reason": reason,
            "remediation": (
                f"mount.service Restart=always 자가 복구 대기 또는 "
                f"systemctl --user status wikihub-mount@{vault_id}.service"
            ),
            "source_id": None,
            "first_failed_at": now,
            "last_failed_at": now,
            "failed_count": 1,
            "alerted_at": None,
        })

    raise VaultSyncRetryable(
        vault_id=vault_id,
        retry_after_sec=120,    # 진단 메타 — vault-fetch.py 미사용. 실 retry 주기는 systemd OnUnitInactiveSec.
        reason=reason,
    )


def vfs_refresh(
    vault_id: str,
    rc_addr: str,
    state_dir: Path | None = None,
    recursive: bool = True,
    timeout_sec: int = 120,
) -> None:
    """rclone rc vfs/refresh — 사이클 시작 시 1회 호출 (ADR-0026 K1).

    race window 차단 — gws changes 알린 변경분이 mount read 시점에 fresh content 보장.

    v9 R13-CRIT-1 (Q6 alert 체인 정합):
    - rclone stderr 에 OAuth error 패턴 매칭 시 VaultSyncFatal (scope="mount") + last_failure writer.
    - 그 외 실패 → VaultSyncRetryable (race window 차단 실패 시 stale read 금지).

    Args:
        vault_id: state_dir 식별 + last_failure.json 의 vault_id.
        rc_addr: ``127.0.0.1:<port>`` — yaml `vaults[*].options.rclone_rc_port` 정합.
        state_dir: OAuth Fatal 시 last_failure 영속화 책임. None 이면 영속화 skip.
        recursive: vfs/refresh 의 recursive 옵션. True (K1 채택).
        timeout_sec: rclone rc 호출 timeout.

    Raises:
        VaultSyncRetryable: 일반 실패 — 호출자가 사이클 abort.
        VaultSyncFatal: OAuth revoke — last_failure (scope="mount") + ops-alert.
    """
    payload = "true" if recursive else "false"
    # `--url http://<addr>` 사용 — rclone 의 클라이언트 측 표준 connect 옵션.
    # `--rc-addr` 는 server side (rcd/mount) flag 라 RCLONE_RC_ADDR env 와 동시 지정 시
    # rclone CLI 가 두 값을 comma-join 하여 `addr,addr` 으로 잘못 lookup (V<N> Phase 2 surface).
    # vault@.service 가 RCLONE_RC_ADDR 주입하므로 client 호출은 `--url` 분리 필수.
    result = subprocess.run(
        ["rclone", "rc", "--url", f"http://{rc_addr}", "vfs/refresh", f"recursive={payload}"],
        capture_output=True, text=True, timeout=timeout_sec, check=False,
    )

    # V18 결함 #6 fix (2026-05-17):
    # rc API call 이 성공해도 (exit 0) mount daemon 의 backend 호출이 fail 한 경우,
    # 응답 JSON `result.""` 필드에 backend error string 이 포함됨. 예:
    #   {"result": {"": "couldn't list directory: ... private key should be a PEM ..."}}
    #   {"result": {"": "OK", "subdir/file.docx": "couldn't list ..."}}  ← recursive=true 의
    #     sub-path error (R15-M3 V<N> Phase 2 R15 internal consistency 리뷰, 2026-05-17)
    # rc API 자체의 fail (exit != 0) 은 mount daemon 미응답 / port unreachable.
    rc_error_msg = ""
    if result.returncode == 0:
        try:
            rc_response = json.loads(result.stdout) if result.stdout else {}
        except json.JSONDecodeError:
            rc_response = {}
        # R15-M2: result_val 이 dict 가 아닌 경우 (`result: []` · `result: null` 같은 future
        # schema) AttributeError 회피 — isinstance check.
        result_val = rc_response.get("result")
        if isinstance(result_val, dict):
            # R15-M3: root path 만 검사하면 sub-path OAuth/SA error 가 silent pass.
            # dict 의 모든 value 를 join 후 regex 매칭 — `OK` 만 가진 정상 응답은 빈 error
            # 으로 추출되어 return path 진입.
            joined = " ".join(str(v) for v in result_val.values() if v and v != "OK")
            if joined:
                rc_error_msg = joined
        elif result_val is not None:
            # dict 도 None 도 아닌 경우 (`result: "..."` 같은 unexpected schema) — 전체를 error
            # 로 분류해서 regex 매칭에 위임. 운영자에게 surface.
            rc_error_msg = str(result_val)
        if not rc_error_msg:
            return  # 정상

    # rc API fail (exit != 0) 또는 backend error in JSON — 패턴 매칭
    # error_full 은 regex 검색용 (Drive API URL fields 파라미터가 250+ char 라 [:500]
    # truncate 시 `private key should be` 등 핵심 키워드 잘려나가 매칭 fail — V18 검증).
    # R16-H3 (V<N> R16 SRE 리뷰, 2026-05-17): 단 무제한은 ReDoS 우려 — stderr 가 수MB 인
    # 비정상 케이스 (rclone bug 등) 시 regex.search 가 100ms+ 지연. 100KB cap 으로
    # 정상 케이스 (stderr ~1~10KB) 전부 커버하면서 비정상 케이스 latency 보호.
    _ERROR_REGEX_SIZE_CAP = 100 * 1024  # 100KB
    raw_full = result.stderr or rc_error_msg
    error_full = raw_full[-_ERROR_REGEX_SIZE_CAP:] if len(raw_full) > _ERROR_REGEX_SIZE_CAP else raw_full
    error_snippet = error_full[:500]
    if _RCLONE_AUTH_PATTERNS.search(error_full):
        if state_dir is not None:
            now = utc_now_iso()
            save_last_failure(state_dir, {
                "vault_id": vault_id,
                "exit_code": 2,
                "severity": "fatal",
                "scope": "mount",
                "reason": f"rclone OAuth/SA revoked/corrupt: {error_snippet[:200]!r}",
                "remediation": (
                    f"SA JSON 갱신 (~/wikihub-instance/.credentials/sa_{vault_id}.json) "
                    f"+ chmod 0600 + systemctl --user restart wikihub-mount@{vault_id}.service"
                ),
                "source_id": None,
                "first_failed_at": now,
                "last_failed_at": now,
                "failed_count": 1,
                "alerted_at": None,
            })
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=f"rclone OAuth/SA error (pattern matched): {error_snippet[:200]!r}",
            remediation=f"SA JSON 갱신 + systemctl --user restart wikihub-mount@{vault_id}.service",
            scope="mount",   # V<N> Phase 2 결함 #7 fix — scope 정합
        )

    # 그 외 → Retryable (race window 차단 실패, 사이클 abort)
    raise VaultSyncRetryable(
        vault_id=vault_id,
        retry_after_sec=120,    # 진단 메타
        reason=f"rclone rc vfs/refresh failed: rc={result.returncode}, "
               f"error={error_snippet[:200]!r}",
    )


__all__ = [
    "assert_mount_alive",
    "vfs_refresh",
    "MOUNT_RETRYABLE_FATAL_THRESHOLD",
]
