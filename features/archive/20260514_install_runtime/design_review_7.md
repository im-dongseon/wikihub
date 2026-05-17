# F4 design review R13 (feature-dev:code-reviewer — Step 2 v8)

리뷰어: feature-dev:code-reviewer
대상: v7 → v8 transition (§10 v8 patch 마커 31건) — fix-induced regression + internal consistency
정본: analysis_and_design.md v8 (§10) + design_review_5.md (R11) + design_review_6.md (R12)
독립성 선언: R11 (design_review_5.md) · R12 (design_review_6.md) 의 finding 답습 회피. v8 patch 적용 결과 자체의 결함 — fix-induced regression, spec 내부 정합 누락 — 에만 집중. v6 §1~§9 자체의 결함은 본 라운드 범위 밖.

## 결함 요약

| 분류 | 건수 | v9 surgical patch 필요 |
|---|---|---|
| CRIT | 2 | 필수 |
| HIGH | 2 | 필수 |
| MED | 3 | 권장 |
| NIT | 1 | 선택 |

총 8건.

---

## CRIT

### CRIT-R13-1: Q6 잠정 결정 ("vfs_refresh → VaultSyncFatal") 이 §10.4.6 vfs_refresh spec 코드와 내부 불일치 — OAuth revoke 시 ops-alert 미발화

**위치**: §10.5 Q6 (line 1575) vs §10.4.6 `vfs_refresh` spec 코드 (lines 1503–1509) vs §10.6 V18 (line 1599)

**현행**:

§10.5 Q6 잠정 결정:
"`vfs_refresh` 또는 mount.service log 의 OAuth error (rclone exit 인증 관련 패턴: "Token expired", "invalid_grant", "401") 감지 시 `VaultSyncFatal` → ADR-0024 last_failure writer 가 발화"

§10.6 V18: "다음 사이클의 `vfs_refresh` 호출 → rclone stderr 에 인증 관련 패턴 출현 → vault-fetch.py 가 `VaultSyncFatal` raise → ops-alert 발화"

§10.4.6 `vfs_refresh` spec 코드:
```python
if result.returncode != 0:
    raise VaultSyncRetryable(
        vault_id=vault_id,
        retry_after_sec=120,
        reason=f"rclone rc vfs/refresh failed: rc={result.returncode}, "
               f"stderr={result.stderr[:200]!r}",
    )
```

**문제**: `vfs_refresh` 함수는 non-zero rc 에 대해 stderr 내 OAuth error 패턴 여부와 무관하게 `VaultSyncRetryable` 만 raise 한다. `VaultSyncFatal` 경로가 없다. Q6 와 V18 이 약속한 "OAuth error → VaultSyncFatal → ops-alert" 체인이 현재 §10.4.6 spec 코드로는 성립하지 않는다.

추가 문제: `rclone rc vfs/refresh` 는 로컬 daemon 에 HTTP 명령을 보내는 RC 호출이다. OAuth token 유효성을 직접 검증하지 않으며, token revoke 시 `vfs/refresh` RC endpoint 자체는 정상 응답할 수 있다 (cache invalidation 명령만 처리). 인증 실패는 mount daemon 이 Drive API 를 실제 호출할 때 발생하므로 `vfs_refresh` 호출 시점에 "rclone stderr 에 인증 관련 패턴 출현" 이 보장되는지 검증 전이다. V18 이 이를 확인해야 하는데, Q6/V18 의 연결 고리가 spec 코드 수준에서 이미 끊어져 있다.

**제안**: 다음 중 하나를 §10.4.6 에 명시해야 한다.

옵션 (a) — `vfs_refresh` 에 OAuth error 패턴 검사 추가:
```python
if result.returncode != 0:
    stderr_snippet = result.stderr[:500]
    auth_patterns = ("Token expired", "invalid_grant", "401 Unauthorized")
    if any(p in stderr_snippet for p in auth_patterns):
        raise VaultSyncFatal(
            vault_id=vault_id,
            reason=f"rclone OAuth revoked or expired (pattern matched): {stderr_snippet[:200]!r}",
            remediation="rclone config reconnect <remote_name>",
        )
    raise VaultSyncRetryable(vault_id=vault_id, retry_after_sec=120,
                             reason=f"vfs/refresh failed: rc={result.returncode}")
```
단, `rclone rc vfs/refresh` 가 OAuth error 를 stderr 에 노출하는지 V18 에서 먼저 검증. PoC 실패 시 옵션 (b) 로 fall-back.

옵션 (b) — Q6 잠정 결정을 "v0.1.0 Retryable-only, 별도 `assert_rclone_auth_alive` helper 는 v0.2.x" 로 변경하고, §10.4.6 `vfs_refresh` 를 현행 Retryable-only 로 유지하면서 spec 코드에 TODO 코멘트 추가: `# Q6 v0.1.0: OAuth error 감지 미구현 — V18 결과 후 결정`.

어느 경로든 Q6 문장 ↔ §10.4.6 spec 코드 중 하나를 정합시켜야 한다.

**근거**: §10.4.6 `vfs_refresh` spec (lines 1503–1509) 는 `VaultSyncRetryable` 만 raise. vault-fetch.py (line 132–134) 는 `VaultSyncRetryable` catch 후 exit 75 만 반환. `SuccessExitStatus=0 75` 로 systemd 가 success 분류 → `OnFailure=ops-alert.service` 미발화. ADR-0024 last_failure writer 는 `VaultSyncFatal` catch 경로에서만 동작.

---

### CRIT-R13-2: `_yaml_get_vault_rc_ports` helper 구현 spec 부재 — Step 5.5c 호출 블로커

**위치**: §10.4.2 Step 5.5c (line 1294)

**현행**:
```bash
for port in $(_yaml_get_vault_rc_ports "${WIKIHUB_YAML}"); do
  _check_rc_port_available "${port}"
done
```

**문제**: `_yaml_get_vault_rc_ports` 가 §10 전체 어디에도 구현 spec 이 없다. v6 scripts/ 에도 동등 bash helper 가 존재하지 않는다. Step 3 구현자가 이 함수를 새로 작성해야 하는데 다음이 모두 미정이다:

- 파싱 도구: `yq` / `python3 -c` / `awk` / `grep+sed` 중 무엇을 사용하는가 (install.sh 기존 yaml 파싱 패턴과 정합 필요)
- 출력 형식: 멀티 vault 시 port 를 공백·개행 중 어떻게 구분하는가
- `rclone_rc_port` 미설정 vault 처리: default port (5572) 를 자동 산출하는가, 항목을 skip 하는가
- 실패 처리: yaml 파싱 오류 시 `_die` 호출 vs 빈 출력 vs 무시

R12-MED-1 (rc port pre-check) 은 이 함수에 전적으로 의존한다. 함수 spec 이 없으면 Step 5.5c 전체가 동작하지 않고 R12-MED-1 fix 가 무효화된다.

**제안**: §10.4.2 Step 5.5c 에 `_yaml_get_vault_rc_ports` 구현 spec 을 추가한다. install.sh 의 기존 Python inline 파싱 패턴과 정합하는 예시:

```bash
_yaml_get_vault_rc_ports() {
  local yaml_file="$1"
  python3 - "$yaml_file" <<'EOF'
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1]))
for v in cfg.get("vaults", []):
    port = v.get("options", {}).get("rclone_rc_port")
    if port is not None:
        print(port)
EOF
}
```

또는 yaml 파싱 도구 결정 (python3 with PyYAML 가 venv 이미 있으므로 적합) 을 명시하고 간결한 1-liner 형식으로 spec 추가.

**근거**: §10.4.2 Step 5.5c (line 1294) — `_yaml_get_vault_rc_ports` 호출. 검색 결과 §10 전체 (`analysis_and_design.md` line 1081–1627) 및 `scripts/` 내 기존 파일 어디에도 이 함수의 정의 없음.

---

## HIGH

### HIGH-R13-1: §10.7 ADR-0025 Title 이 v8 install channel 변경 후 미갱신 — ADR 파일 작성 시 결정 오기 위험

**위치**: §10.7 ADR 발의 목록 (line 1607)

**현행**:
> ADR-0025 | rclone mount 채택 — vault 자체에 마운트 + `--vfs-cache-mode full` + `--rc` 활성화 + **설치 채널 (rclone.org install.sh)** | Accepted (본 v7) | V13·V16 회귀 방지

**문제**: v8 patch (R12-HIGH-3) 가 install channel 을 `rclone.org/install.sh | sudo bash` 에서 GitHub Releases binary + SHA256SUMS verify 로 변경했다. §10.4.2 채널 결정 (line 1299–1302), Q2 lock (line 1571), V16 (line 1597) 은 모두 GitHub Releases 를 정본으로 명시한다. 그러나 ADR-0025 Title 은 여전히 "(rclone.org install.sh)" 를 포함한다.

"설치 채널" 결정은 ADR-0025 의 핵심 scope 중 하나이며 v8 에서 변경된 사항이다. ADR-0025 Title 을 그대로 사용해서 `docs/adr/0025-*.md` 를 작성하면 결정 사항이 오기된 ADR 이 생성된다.

**제안**: §10.7 ADR-0025 Title 갱신:

> ADR-0025 | rclone mount 채택 — vault 자체에 마운트 + `--vfs-cache-mode full` + `--rc` 활성화 + 설치 채널 (GitHub Releases binary + SHA256SUMS verify, v8 R12-HIGH-3)

**근거**: §10.4.2 채널 결정 (line 1300) — "GitHub Releases binary + SHA256SUMS verify — `rclone.org/install.sh` 폐기". Q2 lock (line 1571) — "v8 lock (R12-HIGH-3) — GitHub Releases binary + SHA256SUMS verify (rclone.org/install.sh 폐기)". ADR-0025 Title (line 1607) 의 "(rclone.org install.sh)" 는 v7 이전 draft 잔재로 v8 에서 미갱신.

---

### HIGH-R13-2: `assert_mount_alive` 의 `ls -la` + `capture_output=True` — flat vault 대용량 stdout 메모리 버퍼링

**위치**: §10.4.6 `assert_mount_alive` spec 코드 (lines 1472–1474)

**현행**:
```python
result = subprocess.run(
    ["ls", "-la", str(mount_path)],
    capture_output=True, text=True, timeout=timeout_sec, check=False,
)
```

**문제**: `ls -la <mount_path>` 는 mount root 의 모든 파일 목록 (이름·크기·권한·타임스탬프) 을 stdout 으로 출력한다. `capture_output=True` 로 이 출력이 Python 프로세스 메모리에 버퍼링된다.

vault 가 flat 구조 (Drive root 에 파일 직접 저장) 이고 수만 파일이 있으면, `ls -la` 한 줄 ~200B × 50,000건 ≈ 10MB 가 메모리에 적재된다. ADR-0026 K1 의 V15-cost 가 "10k 파일" 을 측정 대상으로 명시 — 이 규모는 v0.1.0 가정 운영 범위 내다.

`assert_mount_alive` 의 목적은 FUSE 가 응답 가능한지 liveness check 뿐이다. 파일 목록 내용은 불필요하다.

**제안**: spec 코드를 다음으로 교체:

```python
result = subprocess.run(
    ["stat", str(mount_path)],
    capture_output=True, text=True, timeout=timeout_sec, check=False,
)
```

`stat <mount_path>` 는 디렉토리 자체의 stat syscall 만 발행 — stdout ~200B 고정. hung mount 에서는 동일하게 timeout 으로 catch. dead mount 에서는 동일하게 exit non-zero. liveness check intent 를 충족하면서 메모리 압박 없음.

**근거**: §10.4.6 docstring (line 1459) — "mount path 가 FUSE 응답 가능 상태인지 timeout 보장된 subprocess 로 검증". liveness check 에 파일 목록 내용 불필요. R12-CRIT-2 가 `stat -f` 를 권고했고 v8 이 `ls -la` 를 채택했지만 대용량 stdout 버퍼링 부작용은 v8 patch 에서 언급되지 않음.

---

## MED

### MED-R13-1: `VaultSyncRetryable(retry_after_sec=120)` 의 의미 미명시 — vault-fetch.py 는 이 값을 사용하지 않음

**위치**: §10.4.6 `assert_mount_alive` (line 1479) · `vfs_refresh` (line 1506)

**현행**: 두 함수 모두 `retry_after_sec=120` 을 전달한다. `vault-fetch.py` (lines 132–134):
```python
except VaultSyncRetryable as e:
    log.warning("retryable: %s", e)
    return 75
```

**문제**: `retry_after_sec=120` 은 `exceptions.py` 의 `VaultSyncRetryable.__init__` 에 저장되지만 vault-fetch.py 가 이 값을 읽어 scheduling 에 반영하는 로직이 없다. 실제 다음 fire 시점은 systemd `OnUnitInactiveSec=600s` (10분) 가 결정한다. `retry_after_sec=120` (2분) 은 진단 메타로만 존재한다.

spec 에 이 사실이 명시되지 않으면 Step 3 구현자가 "retry_after_sec 를 기반으로 timer reschedule 또는 sleep 로직을 추가해야 하는가" 를 오해할 수 있다. 또한 §10.4.7 의 "다음 timer 사이클 (10min 후) 에 mount@ 가 FUSE 준비 완료 → 정상 진입" 설명과 `retry_after_sec=120` (2분) 이 표면적으로 충돌한다.

**제안**: §10.4.6 `assert_mount_alive` + `vfs_refresh` 의 `VaultSyncRetryable` raise 부분에 주석 추가:

```python
raise VaultSyncRetryable(
    vault_id=vault_id,
    retry_after_sec=120,   # 진단 메타 — vault-fetch.py 가 사용하지 않음.
                           # 실제 retry 타이밍은 systemd OnUnitInactiveSec=600s 가 결정.
                           # v0.2.x: 이 값 기반 reschedule 검토 가능.
    reason=...,
)
```

**근거**: vault-fetch.py lines 132–134 — `VaultSyncRetryable` catch 후 exit 75 반환, `retry_after_sec` 미사용. `exceptions.py` — `VaultSyncRetryable.__init__` 에 `self.retry_after_sec = retry_after_sec` 저장되나 호출자 미사용. vault@.service `OnUnitInactiveSec=600s` 가 실제 retry 주기.

---

### MED-R13-2: `{rc_port_for_%i}` / `{remote_name_for_%i}` template key 의 Python substitution 순서 미명시

**위치**: §10.4.1 mount@.service.template (lines 1206, 1212) + §10.4.4 치환변수 binding (lines 1409–1410)

**현행**:

mount@.service.template (Python brace syntax):
```
ExecStart={rclone_bin} mount {remote_name_for_%i}: {instance_root}/vault/%i \
  ...
  --rc-addr 127.0.0.1:{rc_port_for_%i}
```

§10.4.4 binding 표:
- "`{rc_port_for_<vault_id>}` (v8 명시) — ... 예: vault_id=`gdrive` → ... 치환변수 key `{rc_port_for_gdrive}` = `5572`. mount@.service 의 `--rc-addr 127.0.0.1:{rc_port_for_%i}` 는 systemd `%i` 가 vault_id 와 동일 substitution"

**문제**: template 파일의 Python brace key 는 `rc_port_for_%i` (literal `%i` 포함) 이지만, binding 표의 key 이름은 `rc_port_for_gdrive` (vault_id 로 치환된 형태) 로 다르다. 두 표기가 불일치한다.

Python `.format_map()` 으로 이를 처리하려면 두 가지 방식 중 하나가 필요하다:

- 방식 A: dict 에 key `rc_port_for_%i` (literal) 를 등록하고 단일 pass 치환. binding 표의 "key `rc_port_for_gdrive`" 설명이 오기가 된다.
- 방식 B: Python helper 가 vault_id 별로 instantiate 시 template 의 `%i` 를 먼저 vault_id 로 치환 (2-pass), 이후 brace 치환. 이 경우 2-pass 로직이 ADR-0019 에 없으며 Step 3 에서 구현해야 함.

어느 방식인지 명시 없이는 Step 3 의 substitution helper 구현이 ambiguous 하다. `{remote_name_for_%i}` 도 동일 문제다.

**제안**: §10.4.4 치환변수 binding 에 다음을 추가:

> Python substitution helper 는 vault_id 별로 template instantiate 시 **2-pass** 처리: (1) template 내 `%i` 를 vault_id 로 전치환 (`{rc_port_for_%i}` → `{rc_port_for_gdrive}`), (2) `.format_map(substitution_dict)` 로 brace 치환. ADR-0019 의 단일 pass 패턴을 per-vault 키 prefix 방식으로 확장.

또는 방식 A (dict key 를 literal `rc_port_for_%i` 로 등록) 로 결정하고 binding 표의 key 이름 표기를 template 과 일치시킨다.

**근거**: §10.4.1 (lines 1206, 1212) — template 에 `{remote_name_for_%i}:` 와 `{rc_port_for_%i}`. §10.4.4 (line 1409) — binding 표에 `{rc_port_for_gdrive}` 로 상이한 key 표기. ADR-0019 — per-vault Python substitution 정의. 두 표기의 불일치.

---

### MED-R13-3: §10.8 DoD Feature 전체에 V15-cost 와 V18 누락 — v8 신규 acceptance gate 미포함

**위치**: §10.8 DoD Feature 전체 v7 (line 1623)

**현행**:
```
- [ ] V13·V14·V15·V16·V17 모두 통과 + V12 갱신 통과
```

**문제**: v8 신규 verification 2건이 누락됐다:

- **V15-cost (v8 신규, line 1595)**: `vfs/refresh recursive=true` 의 vault 규모별 latency 측정 (R12-HIGH-2 처리 결과). 10k 파일에서 60s 초과 시 ADR-0026 K1→K2 마이그레이션 결정의 정량적 gate. DoD 에 없으면 K1 채택 정당성 확인 없이 Step 5 배포 가능.
- **V18 (v8 신규, line 1599)**: rclone OAuth revoke 감지 검증 (R12-HIGH-4 처리 결과). Q6 lock 의 verification. CRIT-R13-1 과 연결 — `vfs_refresh` 가 OAuth error 를 stderr 에 노출하는지 V18 이 확인해야 Q6 alert 체인의 정합 여부가 결정됨. DoD 에 없으면 Q6 미lock 상태로 배포 위험.

V15a 는 기존 DoD (line 1624) 의 "V15a 결과로 Q1 lock" 으로 별도 커버됨. 이 finding 은 V15-cost · V18 만 해당.

**제안**: §10.8 Feature 전체 DoD 를 갱신:

```markdown
- [ ] V13·V14·V15·V15-cost·V16·V17·V18 모두 통과 + V12 갱신 통과
```

**근거**: §10.6.2 V15-cost (line 1595) — "v8 신규". §10.6.2 V18 (line 1599) — "v8 신규". §10.8 DoD (line 1623) 에 미포함.

---

## NIT

### NIT-R13-1: `mount.py` spec 코드의 `import os` — os.statvfs 교체 후 orphan import

**위치**: §10.4.6 `mount.py` spec 코드 (line 1451)

**현행**:
```python
import os
import subprocess
```

**문제**: v8 patch 가 `os.statvfs` 를 `subprocess.run(['ls', ...])` 로 교체했다. spec 코드 전체 (lines 1447–1509) 에서 `os.` prefix 사용이 없다. Step 3 에서 spec 을 그대로 구현하면 flake8/ruff F401 (unused import) 경고가 발생한다.

**제안**: `import os` 제거.

**근거**: §10.4.6 mount.py spec 코드 전체 내 `os.` 사용 없음. v7 이전 `os.statvfs` 가 있던 자리의 잔재.

---

## 결론

### v8 approval 가능 여부

**현 상태에서 approval 불가.**

**CRIT-R13-1** — Q6 alert 체인이 spec 내부에서 self-contradicting 하다. `vfs_refresh` spec 코드는 `VaultSyncRetryable` 만 raise 하지만 Q6/V18 은 `VaultSyncFatal` → ops-alert 를 전제한다. V18 수행 전에도 최소한 spec 코드와 Q6 문장 중 하나를 정합시켜야 한다.

**CRIT-R13-2** — install.sh Step 5.5c 에서 호출하는 `_yaml_get_vault_rc_ports` 의 구현 spec 이 전혀 없다. Step 3 진입 즉시 구현 블로커가 된다. R12-MED-1 fix 전체가 이 함수에 의존한다.

### v9 surgical patch 권고 항목

| 우선순위 | 항목 | 처리 방법 |
|---|---|---|
| 1 | CRIT-R13-1 | §10.4.6 `vfs_refresh` 에 OAuth error 패턴 검사 추가 (VaultSyncFatal 경로) 또는 Q6 잠정 결정 수정 (Retryable-only 명시 + spec 코드에 TODO 추가) |
| 2 | CRIT-R13-2 | §10.4.2 Step 5.5c 에 `_yaml_get_vault_rc_ports` 구현 spec 추가 |
| 3 | HIGH-R13-1 | §10.7 ADR-0025 Title — "(rclone.org install.sh)" → "(GitHub Releases binary + SHA256SUMS verify, v8)" |
| 4 | HIGH-R13-2 | §10.4.6 `ls -la` → `stat` 교체 |
| 5 | MED-R13-1 | §10.4.6 docstring/주석에 `retry_after_sec` 가 passive metadata 임을 명시 |
| 6 | MED-R13-2 | §10.4.4 치환변수 binding 에 `{rc_port_for_%i}` Python substitution 순서 명시 (2-pass vs literal key) |
| 7 | MED-R13-3 | §10.8 DoD 에 V15-cost · V18 추가 |
| 8 | NIT-R13-1 | §10.4.6 `import os` 제거 |

CRIT-R13-1 · R13-2 + HIGH-R13-1 · R13-2 처리 후 v9 approved 마커 + Step 3 진입 가능. MED · NIT 는 Step 3 진입 전 또는 Step 3 초반 처리 권장.

---

관련 파일:
- `/Users/1004790/workspace/wikihub/features/20260514_install_runtime/analysis_and_design.md`
- `/Users/1004790/workspace/wikihub/features/20260514_install_runtime/design_review_5.md`
- `/Users/1004790/workspace/wikihub/features/20260514_install_runtime/design_review_6.md`
- `/Users/1004790/workspace/wikihub/scripts/lib/exceptions.py`
- `/Users/1004790/workspace/wikihub/scripts/vault-fetch.py`
- `/Users/1004790/workspace/wikihub/scripts/lib/sync.py`
