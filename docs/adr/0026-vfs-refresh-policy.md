# ADR-0026: vfs refresh 정책 — 사이클 시작 시 recursive 1회 (K1)

- **Status**: Accepted
- **Date**: 2026-05-15
- **Feature**: features/20260514_install_runtime (v9)
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

ADR-0025 채택 후 발생하는 **race window**:

- gws `drive changes list` 가 "파일 X 변경됨" 알림 → vault-fetch.py 가 mount path 의 `open(X).read()` 호출
- 그 사이에 rclone vfs cache 가 stale 일 수 있음 — `--dir-cache-time 5m` 또는 vfs cache 자체의 latency 로 새 content 가 mount 에 아직 반영 안 됨
- 결과: stale read → wiki page 가 오래된 content 로 갱신 → **정합성 결함**

race window 차단 메커니즘 결정 필요.

## Considered Options

- **(K1) 사이클 시작 시 `rclone rc vfs/refresh recursive=true` 1회**: 모든 dir cache + vfs cache invalidate. 단순·보수적. 큰 vault 시 비용
- **(K2) per-file refresh**: gws changes 응답의 source_id 별로 `rclone rc vfs/refresh file=<path>` 호출. 정밀하지만 Drive ID → mount path 매핑 로직 신규
- **(K3) `--dir-cache-time` 단축 + `--vfs-read-wait`**: refresh 호출 없음, vfs 가 자동 invalidate. 사이클 (10min) 대비 fresh 보장 안 됨

> 옵션 상세는 [features/20260514_install_runtime/analysis_and_design.md §10.3.2](../../features/20260514_install_runtime/analysis_and_design.md) 참조.

## Decision

**채택**: (K1) 사이클 시작 시 `vfs/refresh recursive=true` 1회

### `mount.py` 의 `vfs_refresh` helper (v9 정본 + V<N> Phase 2 결함 #1·#6 fix)

```python
def vfs_refresh(vault_id, rc_addr, state_dir=None, recursive=True, timeout_sec=120):
    payload = "true" if recursive else "false"
    # `--url http://<addr>` 사용 (V<N> 결함 #1 fix, 2026-05-17) — `--rc-addr` 는 server side
    # flag 라 RCLONE_RC_ADDR env 와 동시 지정 시 rclone CLI 가 두 값을 comma-join 함.
    result = subprocess.run(
        ["rclone", "rc", "--url", f"http://{rc_addr}", "vfs/refresh", f"recursive={payload}"],
        capture_output=True, text=True, timeout=timeout_sec, check=False,
    )
    # V<N> 결함 #6 fix: rc API exit 0 이어도 mount daemon backend fail 가능 — JSON `result.""` 검사
    if result.returncode != 0 or _rc_backend_error(result.stdout):
        error_full = result.stderr or _extract_backend_msg(result.stdout)
        # v9 R13-CRIT-1 + V18 결함 #6 fix — OAuth/SA 패턴 → Fatal scope="mount" (Q6 정합)
        if _RCLONE_AUTH_PATTERNS.search(error_full):
            # save_last_failure(scope="mount") + raise VaultSyncFatal(scope="mount")
            ...
        # 그 외 → Retryable (race window 차단 실패, 사이클 abort)
        raise VaultSyncRetryable(vault_id=vault_id, retry_after_sec=120, reason=...)
```

### vault-fetch.py 사이클 순서 (v9)

1. `assert_mount_alive(vault_id, mount_path, state_dir)` — mount liveness check
2. **`vfs_refresh(vault_id, rc_addr, state_dir, recursive=True)`** — race window 차단
3. `gws drive changes list --params {pageToken: cursor}` — 변경 감지 (v6 유지)
4. 각 변경 file 별: `_resolve_mount_path()` → `_read_from_mount()` → extraction → wiki page write
5. cursor 저장, last_sync 갱신

vfs_refresh 실패 → exit 75 사이클 abort (R11-HIGH-3 정합 — stale read 허용 금지)

### 실패 분기 (v9 R13-CRIT-1 흡수)

| stderr 패턴 | 분기 |
|---|---|
| `Token expired` / `invalid_grant` / `401 Unauthorized` / `oauth2.*invalid` / `unauthorized_client` / `access_denied` | `VaultSyncFatal` (mount scope) + last_failure writer → ops-alert |
| 그 외 | `VaultSyncRetryable` (exit 75) — 다음 사이클 재시도. mount.service Restart=always 가 daemon 자체는 복구 |

**이유**:
- (K1) 채택:
  - v0.1.0 vault 규모 (수천 파일 추정) 에서 recursive refresh 비용 < 5s — acceptable (V15-cost 검증 대상)
  - per-file refresh (K2) 는 source_id → mount path 매핑 로직 신규 — Step 3 verification 부담 추가. K2 는 v0.2.x deferred
  - K3 (dir-cache-time 단축) 는 fresh 보장 안 됨 — race window 잔존
- 사이클 시작 시 1회 호출이 단순 + 보수적 (모든 변경을 fresh 로 보장)
- vfs_refresh 의 OAuth error 패턴 매칭 (R13-CRIT-1) 으로 ADR-0024 v9 mount scope writer 와 정합

## Consequences

- **긍정**:
  - race window 차단 — gws changes 가 알린 변경분이 mount read 시점에 fresh content 보장
  - 단일 호출로 모든 cache invalidate — 운영 복잡도 낮음
  - mount.py 의 fatal 분기 (OAuth error) 가 ADR-0024 writer 와 정합

- **부정/제약**:
  - 큰 vault (수만 파일) 에서 refresh 자체가 사이클 timeout (15min = TimeoutStartSec) 압박 가능 → V15-cost 측정. 10k 파일 60s 초과 시 K2 마이그레이션 검토 (Q13)
  - recursive refresh 실패 시 fallback 없음 → fail-fast (다음 사이클 재시도, mount.service Restart=always 가 mount 자체 복구)
  - mount permanently failed case 와의 정합: assert_mount_alive 가 먼저 fail 하므로 vfs_refresh 호출까지 안 감 (의도된 순서)

- **후속 영향**:
  - V15 (race window 차단 — vfs/refresh 응답 완료 후 mount read fresh) 가 본 ADR 정합성 회귀 방지
  - V15-cost (1k/5k/10k 파일 latency 측정) 가 K1 채택 정당성 lock
  - V18 (rclone OAuth revoke 감지) 가 `_RCLONE_AUTH_PATTERNS` regex refine
  - 재검토 트리거:
    - V15-cost 결과 10k 파일에서 60s 초과 → K2 (per-file refresh) 또는 K1+K2 hybrid 마이그레이션 ADR 신규 발의
    - rclone vfs 가 자동 invalidate 정확성 향상 (v2.x major) → K3 채택 가능성 재검토

## Cross-references

- ADR-0025 (rclone mount 채택) — `--rc --rc-addr` 활성화가 본 ADR 호출의 전제
- ADR-0024 v9 (fatal alert contract) — OAuth Fatal 분기의 writer 정본
- ADR-0027 (rclone vs gws 책임 분리) — mount.py 의 책임 분배
- features/20260514_install_runtime/analysis_and_design.md §10.3.2·§10.4.6 — spec 정본
- features/20260514_install_runtime/analysis_and_design.md §10.6 V15·V15-cost·V18 — verification
