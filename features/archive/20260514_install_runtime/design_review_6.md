# F4 design review R12 (general-purpose SRE — Step 2 v7)

- **리뷰어**: general-purpose SRE
- **대상**: `analysis_and_design.md` v7 §10 신규 (Path C+ — rclone mount + gws 책임 분리)
- **정본**: §10.1~§10.8 (line 1081~1483) + `rclone_vs_gws_comparison.md` + `plan.md` v2
- **검토 관점**: 24/7 운영 reliability · observability · supply chain · failure recovery · reboot resilience
- **독립성 선언**: R11 (`feature-dev:code-reviewer`) 의 internal consistency · yaml-template substitution 정합 · spec 정합 영역은 답습 회피. 본 라운드는 위 SRE 관점에서만 신규 finding 을 surface. v6 §1~§9 (이미 R6·R8·R10 통과) 자체에 대한 결함은 본 라운드 범위 밖.

## 결함 요약

| 분류 | 건수 | release blocking |
|---|---|---|
| CRIT | 2 | v0.1.0 blocking |
| HIGH | 5 | v0.1.0 blocking |
| MED | 4 | v0.2.x 적정 (운영 가이드/명시 필요) |
| LOW | 2 | v0.2.x 적정 |
| NIT | 1 | 권고 |

총 14건.

---

## CRIT

### CRIT-R12-1: mount.service `OnFailure` 미설정 — StartLimit 소진 후 fatal 알림 채널 침묵

**위치**: §10.4.1 (mount.service.template) · §10.3.3 (장애 격리 표) · §10.4.7 (vault@ Requires)

**운영 시나리오**: rclone mount 가 `Restart=always + RestartSec=10s + StartLimitBurst=5 / IntervalSec=300` 로 5회/5분 초과 후 stuck 상태 (`activating (auto-restart) → failed`) 진입. systemd 가 더 이상 재기동 안 함. 동일 시점에 `wikihub-vault@.timer` 가 fire 하면 `Requires=wikihub-mount@%i.service` 의 의미상 vault@ 가 활성화 시도 → mount@ 가 inactive failed 라 vault@ 도 `dependency` 사유로 fail (start condition 만족 안 함). 이 경우 vault@ 의 `ExecStart` 자체가 호출되지 않아 `OnFailure=ops-alert.service` 가 trigger 되지 않을 가능성 高.

**문제**:
- §10.3.3 본문이 "mount 죽음 → vault read 불가 → `wikihub-vault@.service` 가 `assert_mount_alive()` 로 fail-fast → `OnFailure=ops-alert.service` 발화" 라고 명시. 그러나 이 경로는 vault@ 의 `ExecStart` 가 실행돼야 성립.
- systemd 의 `Requires=` 의미: dependency 가 `failed` 상태면 unit 자체가 dependency error 로 fail. 이 경우 `OnFailure=` 가 trigger 되는지는 systemd 동작상 보장되지 않음 (`ExecStart` 미실행이라 `ExecMainPID` 도 없음 — `OnFailure` 는 service 가 `failed` state 로 enter 할 때 trigger 되나, dependency-only fail 의 propagation 동작이 systemd 버전 의존).
- 결과: mount 가 StartLimit 소진된 stuck 상태에서는 ops-alert 자체가 발화 안 함 → fatal 알림 0건 → 운영자 인지 늦어짐 → v0.1.0 acceptance invariant 위반 (`사람 개입 없이 자동 재기동` 의 fallback alert 까지 dead).
- mount.service 자체에 `OnFailure=ops-alert.service` 가 미설정. §10.4.1 본문 "OnFailure 미설정, 단 vault@ 측에서 fail-fast 하므로 ops-alert 는 vault@ 측에서 발화" — 위 propagation 가정이 검증되지 않은 상태.

**제안**:
- mount.service.template 에 `OnFailure=ops-alert.service` 추가. 단 ops-alert.py 가 `last_failure.json` 만 읽으므로 mount 가 last_failure 를 쓰는 책임도 명시 필요. 옵션:
  - (a) mount.service 의 `ExecStopPost=` 로 simple python helper 호출 — exit code 가 0 이 아니면 `_state/<vault_id>/last_failure.json` 에 `severity=fatal, scope=mount, reason="rclone mount StartLimit 소진"` 기록
  - (b) ops-alert.py 가 `systemctl --user show wikihub-mount@*.service` 의 `Result=` 를 인식하도록 보강 — mount 의 failed state 감지 + 임시 alert payload 생성
- (a) 가 ADR-0024 패턴 (last_failure.json producer/reader 분리) 과 정합. helper 는 `scripts/mount-fail-recorder.py` 신규 — Step 3 추가.
- Step 3 V14 검증 case 를 보강: "5회/5분 초과 후 mount@ stuck 상태에서 vault@.timer fire → ops-alert 가 발화하는지" 명시. 현재 V14 본문은 "30s 내 재기동 + 5회/5min 초과 시 fail 도 검증 (StartLimitBurst)" — fail 후 alert 도달 여부 verification 미명시.

**근거**: §10.4.1 본문 "OnFailure 미설정, 단 vault@ 측에서 fail-fast" + §10.3.3 "vault@.service 가 fail-fast → ops-alert" — 가정에 의존. systemd 의 `Requires=` propagation 동작은 ADR-0024 의 fatal-alert-contract 가 보증하는 last_failure.json producer/reader 경로 밖에 있음. ADR-0024 본문이 "producer = vault-fetch.py (ExecStart 내부)" 명시.

---

### CRIT-R12-2: Python `os.statvfs` 가 hung FUSE mount 에서 무한 block 가능 — 사이클 자체 hang

**위치**: §10.4.6 (`mount.py` `assert_mount_alive`)

**운영 시나리오**: rclone mount daemon 이 살아있으나 (`pid` 존재) FUSE 응답이 hung 상태 (예: Drive API 가 5xx 반환 후 vfs 가 retry 무한 루프, 또는 network partition 으로 outbound https 가 SYN timeout 만 반복). mount path 의 `stat()`/`statvfs()` 가 FUSE 응답을 기다리며 block. v6 R10 의 V12 (reboot resilience) 가 위와 같은 hung 시점에 fire 되면 `vault-fetch.py` 사이클 자체가 hang → `TimeoutStartSec=15min` 도달 후 systemd 가 SIGTERM → exit 으로 종료되지만 그 사이 사이클 누적 손실.

**문제**:
- `os.statvfs(str(mount_path))` 는 Python stdlib — timeout 인자 없음. FUSE 가 응답을 안 주면 syscall 이 indefinitely block.
- 일부 systemd-managed FUSE mount 는 `nonempty,allow_other` 옵션과 결합해 더 빠른 EIO 반환을 보장하지만 rclone mount 의 기본 동작은 그렇지 않음 (rclone 의 `--attr-timeout 1s` 등으로 cache-only stat 응답 가능하지만 §10.4.1 본문에 미설정).
- 결과:
  - `assert_mount_alive` 가 fail-fast 의도와 반대로 fail-block 으로 동작.
  - `TimeoutStartSec=15min` 까지 사이클 hang → systemd journal 만 SIGTERM 기록 + last_failure.json 미기록 (vault-fetch.py 의 `except` block 진입 못 함). → ops-alert.py 도 발화 안 함 (CRIT-1 과 동일 패턴).
- mount.service 가 살아있는 (Restart=always 가 트리거 안 함) hung 케이스가 가장 위험 — daemon pid 는 살아있으니 systemd 가 정상 인식, mount 만 응답 없음.

**제안**:
- `assert_mount_alive` 에 timeout 강제. Python stdlib 의 `os.statvfs` 가 timeout 미지원 — 대안:
  - (a) `subprocess.run(['stat', '-f', str(mount_path)], timeout=5)` — OS 의 `stat` 명령어가 syscall 발행. subprocess timeout 으로 hung 도 catch.
  - (b) `signal.SIGALRM` 으로 timeout 강제 (단일 thread 환경 한정 — vault-fetch.py 가 single-thread 면 가능).
  - (c) `rclone rc core/version` 응답 확인 — rclone 의 rc API 가 mount daemon 자체 health check. mount path 의 FUSE 응답과는 다르지만 daemon liveness + 응답 가능성 검증.
- 권고: (a) + (c) 결합. (a) 로 mount path FUSE 응답 검증, (c) 로 daemon 자체 health 검증 → 두 path 모두 fail-fast 보장.
- Step 3 V14 검증 case 보강: "rclone process 가 살아있지만 outbound network 단절 시 사이클 hang 여부" — `iptables` 로 outbound 차단 후 사이클 trigger.

**근거**: §10.4.6 의 `os.statvfs` 사용. Python 공식 docs 의 `os.statvfs` 가 timeout 미지원. FUSE 응답 hang 시 syscall block 은 Linux/POSIX 보편 동작. rclone 의 `--attr-timeout` 옵션 (§10.4.1 의 mount args 에 미존재) 도 default 가 1s 가 아니라 1s — but 본문에 명시되지 않아 회귀 위험.

---

## HIGH

### HIGH-R12-1: `vfs/refresh recursive=true` 비용 측정 절차 부재 — 큰 vault 에서 timeout 도달

**위치**: §10.3.2 (K1 결정) · §10.5 (Q4 미결) · §10.6.2 (V15)

**운영 시나리오**: v0.1.0 launch 후 vault 가 수천 파일 → 수만 파일 누적. 매 사이클 시작 시 `rclone rc vfs/refresh recursive=true` 호출이 점차 느려져 `TimeoutStartSec=15min` 의 일부를 잠식. 이후 ingest 단계 + extraction + write 가 압박 받음 → 사이클 자체 timeout → exit 75 (Retryable) 도 아닌 SIGTERM 으로 종료.

**문제**:
- §10.3.2 본문 "v0.1.0 vault 규모 (수천 파일 추정) 에서 recursive refresh 비용 < 5s — acceptable" 추정만. **측정 절차 부재**.
- §10.6.2 의 V15 본문: "Drive 에서 파일 X 의 content 수정 직후 5s 내 사이클 trigger → mount read content 가 새 content" — race window 차단 검증만. **refresh 자체의 latency 측정 항목 부재**.
- §10.4.6 의 `vfs_refresh` 가 `timeout_sec=120` 설정. 120s 가 사이클 timeout 의 13% (120/900) — 측정 없이 잠정.
- 큰 vault 에서 refresh 가 60s+ 걸리면 사이클 timeout 압박 + retry 시 cumulative delay.

**제안**:
- V15 검증 절차에 추가 항목:
  - **V15b (신규)**: 파일 개수 N = 1k, 10k, 50k 별 refresh latency 측정 (P50/P95/P99). Drive test workspace 에 fixture 생성 후 `time rclone rc vfs/refresh recursive=true` 반복.
  - 결과 기반으로 §10.5 Q4 (vfs_refresh 실패 시 fallback) lock + `wikihub.yaml.operations.vfs_refresh_mode` 의 default 결정 (recursive vs per-file).
- §10.4.4 의 `vfs_refresh_mode: recursive` default 를 Step 3 V15b 결과 후 확정 — Step 2 잠정 결정으로 명시.
- `vfs_refresh` 호출에 elapsed time 로그 추가 (info level — journal 에 timestamp 남도록):
  ```python
  start = time.monotonic()
  result = subprocess.run(...)
  elapsed = time.monotonic() - start
  log.info("vfs_refresh: elapsed=%.1fs recursive=%s", elapsed, recursive)
  ```
  → 운영자가 사이클별 refresh latency drift 를 journal 에서 추적 가능.

**근거**: §10.3.2 의 "비용 < 5s — acceptable" 추정만 명시. 측정 가설 검증 절차 부재. v6 §4.8 V<N> 패턴 (V4·V6·V8·V10·V11·V12 모두 OCI 실수행 verification) 와 정합 안 됨.

---

### HIGH-R12-2: vfs cache 디스크 압박 시 mount 동작 불명확 + OCI free tier 한도 가이드 부재

**위치**: §10.4.1 (mount.service args `--vfs-cache-max-size 10G`) · §10.4.4 (yaml `vfs_cache_max_size: 10G`)

**운영 시나리오**: OCI free tier ARM (Always Free) 의 boot volume 한도 = 47GB / 200GB block storage. wikihub 의 누적 disk 사용량 추정:
- `~/wikihub` (repo) — ~10MB
- `~/.local/share/wikihub/venv` — ~150~300MB (pdfminer, pptx, gws 등 deps)
- `~/wikihub-instance/` (instance_root) — vault local mirror + wiki + state + install.log
- vfs cache (`--vfs-cache-max-size 10G`) — 10GB
- gws binary + rclone binary — ~100MB
- journal log (rclone `--log-level INFO`) — 누적

추정 ceil = 11~12GB. OCI free tier 47GB 내 안전하지만 운영자가 `vfs_cache_max_size` 를 default 10G 로 두는 가정 + multi-vault 시 vault 당 10G → 2 vault 면 20G + 다른 항목으로 30G+ 가능.

**문제**:
- §10.4.1·§10.4.4 의 default 가 10G 일 뿐 OCI free tier 운영 가이드 부재. v0.1.0 acceptance 가 OCI 환경인데 디스크 fill 케이스의 행동 미명시.
- vfs cache 가 max-size 도달 후 동작: rclone 의 `--vfs-cache-max-size` 는 LRU eviction 기반이지만 eviction 도중 disk 가 fill 된 경우 (예: 다른 프로세스가 동시에 디스크 사용) write fail 시 mount 가 어떻게 응답하는지 불명확.
- v6 §4.6 (disk-watch) 의 v0.2.x deferred 결정과의 정합 부재. v6 §4.6 본문이 "disk 95% 도달 시 ops-alert" 를 v0.2.x 로 미뤘는데, v7 의 vfs cache 가 디스크 사용량 가속화시킴 → disk-watch 의 v0.2.x deferred 적정성 재평가 필요.

**제안**:
- §10.4.4 의 yaml 본문에 OCI free tier 환경 권장값 comment 추가:
  ```yaml
  vfs_cache_max_size: 10G   # OCI free tier (47GB boot) 권장 — multi-vault 시 vault 당 5G 권장
  ```
- §10.5 에 신규 미결 Q5 추가: "vfs cache fill 시 mount FS 의 write/read 응답 — Step 3 V18 검증 항목"
- v6 §4.6 의 disk-watch deferred 결정을 v7 본문에 cross-reference + 운영 환경 가이드 (`docs/operations/disk-budget.md` 신규 또는 README 한 섹션) 작성. v0.1.0 release 전 운영자가 디스크 한도 인지 보장.
- Step 3 신규 V18: clean ARM Ubuntu 47GB instance 에서 vfs cache 10G 누적 + vault local + venv 의 cumulative disk 측정.

**근거**: §10.4.1 `--vfs-cache-mode full --vfs-cache-max-size 10G` 의 운영 가시성 부재. v6 §4.6 deferred 결정 + plan.md v2 "운영 환경 가정" 의 "FUSE 사용 가능" 만 명시 (디스크 한도 미명시).

---

### HIGH-R12-3: `curl ... | sudo bash` 의 supply chain 위협 — ADR-0023 패턴보다 더 위험

**위치**: §10.4.2 (install.sh Step 5.5 — `curl -fsSL https://rclone.org/install.sh | sudo bash`)

**운영 시나리오**: 메인테이너가 OCI 서버에서 `curl https://raw.githubusercontent.com/.../install.sh | bash` (ADR-0023) 실행. 내부적으로 install.sh 가 Step 5.5 진입 → `curl https://rclone.org/install.sh | sudo bash` 실행. rclone.org TLS cert / GitHub raw TLS cert 둘 다 신뢰 가정. rclone.org 가 침해되거나 CDN cache poisoning 발생 시 OCI 서버에 root 권한 임의 코드 실행.

**문제**:
- ADR-0023 의 위협 매트릭스가 wikihub install.sh 자체에 대해서만 매핑. rclone.org/install.sh 는 wikihub 의 supply chain 의 일부지만 별도 위협 모델 미작성.
- wikihub install.sh 는 `sudo` 가 `loginctl enable-linger` 1회 (idempotent) 만 사용. **rclone install.sh 는 `| sudo bash` — 전체 스크립트가 root 권한**. 위험 surface 가 ADR-0023 보다 훨씬 큼.
- §10.4.2 본문 "supply chain: ADR-0023 (curl-pipe install.sh) 와 동일 위협 모델 적용 — install.sh 본문에 안내 코멘트 명시" — comment 만 명시. 실제 mitigation (sha256 verification, GPG signature, version pin enforce) 미명시.
- ADR-0015 (gws version pinning) 는 GitHub Releases 의 sha256 verify 까지 본 매트릭스에 명시 (ADR-0023 위협 매트릭스 마지막 행). rclone 은 동급 verify 명시 없음.

**제안**:
- §10.4.2 의 `_install_rclone()` 를 다음으로 강화:
  - (a) curl-pipe 대신 직접 binary 다운로드 + sha256 검증 (gws 의 Step 4 패턴 reuse):
    ```bash
    # rclone GitHub Releases binary 직접 다운로드 (gws Step 4 패턴)
    local rclone_url="https://downloads.rclone.org/v${RCLONE_MIN_VERSION}/rclone-v${RCLONE_MIN_VERSION}-linux-arm64.zip"
    local rclone_sha_url="${rclone_url}.sha256"
    curl -fsSL --proto '=https' --tlsv1.2 "$rclone_url" -o "$tmpdir/rclone.zip"
    curl -fsSL --proto '=https' --tlsv1.2 "$rclone_sha_url" -o "$tmpdir/rclone.zip.sha256"
    (cd "$tmpdir" && sha256sum -c rclone.zip.sha256)
    unzip "$tmpdir/rclone.zip" -d "$tmpdir/"
    sudo install -m 0755 "$tmpdir/rclone-v${RCLONE_MIN_VERSION}-linux-arm64/rclone" /usr/local/bin/rclone
    ```
  - (b) `rclone.org/install.sh` 채널 유지 시 최소 — install.sh 본문을 다운로드 → sha256 검증 → 실행:
    ```bash
    curl -fsSL "https://rclone.org/install.sh" -o "$tmpdir/rclone-install.sh"
    # rclone.org 가 install.sh 의 sha256 도 published — 검증 가능
    sudo bash "$tmpdir/rclone-install.sh"
    ```
- ADR-0023 위협 매트릭스에 신규 행 추가: "rclone install supply chain — curl-pipe + sudo" + mitigation 매핑.
- §10.5 의 Q2 (rclone install 채널) 본문에 "v0.1.0 sha256 verify 필수 / GPG 는 v0.2.x" 잠정 결정 추가.

**근거**: §10.4.2 본문 `curl -fsSL https://rclone.org/install.sh | sudo bash`. install.sh Step 4 (gws) 는 sha256 verify 있음 (line 305~311). rclone 은 동급 verify 미명시. ADR-0023 위협 매트릭스의 "TLS MITM mitigation = --proto/--tlsv1.2 + 시스템 CA" 가 install.sh 자체에는 적용되지만 install.sh **내부에서 호출하는** rclone install.sh 에는 미적용.

---

### HIGH-R12-4: rclone OAuth credentials 의 lifecycle alert 부재 — revoke 시 silent fail

**위치**: §10.3.3 (장애 격리 표) · §10.4.5 (setup.md Step 5.5) · §10.4.6 (mount.py)

**운영 시나리오**: 운영자가 Google 계정 보안 점검 차원에서 `myaccount.google.com` 의 "Third-party apps" 에서 rclone 의 OAuth access 를 **수동 revoke**. mount.service 의 rclone daemon 이 다음 Drive API 호출 시 401 invalid_grant. rclone 의 동작:
- mount path 의 `read()` 요청은 EIO 반환 (Linux FUSE)
- mount daemon 은 죽지 않음 (rclone 의 retry policy — refresh_token 시도 후 fail)
- `Restart=always` 가 trigger 안 함 (daemon 정상 살아있음)
- vault-fetch.py 의 `assert_mount_alive` 는 statvfs 만 검증 → pass (FUSE 응답 가능)
- vault-fetch.py 의 `vfs_refresh` 도 rclone rc 호출 → daemon 자체는 응답하므로 pass (refresh 명령은 cache invalidate 만 — auth 검증 안 함)
- 실제 `_read_from_mount(mount_path)` 의 `read_bytes()` 가 EIO → Python `OSError`
- `_read_from_mount` 의 raise 패턴이 `VaultSyncFileFatal` (§10.4.3 본문) — file 단위 retry. 모든 파일에 동일 EIO → 모든 파일이 retry.json 으로 영속화.
- last_failure.json 은 미기록 (VaultSyncFatal 이 아님). ops-alert 는 retry.json 만 기록되는 file fatal 는 read 안 함 (ADR-0024 본문: "VaultSyncFileFatal 은 retry.json 이 정본 — last_failure.json 에는 기록 안 함").

**문제**:
- 결과: rclone OAuth revoke 시 ops-alert 발화 안 함. 운영자가 vault sync 가 점진 줄어드는 (모든 파일 file fatal) 현상을 retry.json 으로만 인지. 인지 latency 24h+.
- gws OAuth revoke 는 ADR-0024 본문 + ADR-0017 stderr 매핑으로 `invalid_grant` 패턴 catch → exit 2 → ops-alert. **두 OAuth 의 lifecycle 알림 경로가 비대칭**.
- §10.3.3 의 장애 격리 표 "gws 결함 → ops-alert" 만 명시. **rclone OAuth 결함 → 알림 경로** 미명시.

**제안**:
- `scripts/lib/mount.py` 에 신규 helper `assert_rclone_auth_alive(rc_addr)`:
  ```python
  # rclone rc operations/about 호출 — auth 필요한 endpoint. 401 응답이면 즉시 raise VaultSyncFatal
  result = subprocess.run(["rclone", "rc", "--rc-addr", rc_addr,
                          "operations/about", f"fs={remote_name}:"],
                          capture_output=True, text=True, timeout=10)
  if result.returncode != 0:
      if "invalid_grant" in result.stderr or "401" in result.stderr:
          raise VaultSyncFatal(
              vault_id=vault_id,
              reason="rclone OAuth revoked or expired",
              remediation="rclone config reconnect <remote_name>",
          )
  ```
- 사이클 시작에 `assert_mount_alive` → `assert_rclone_auth_alive` → `vfs_refresh` 순으로 호출. auth fail 은 VaultSyncFatal (vault-scope) — last_failure.json 영속화 → ops-alert 발화.
- §10.5 의 미결 Q 표에 신규 행 추가: "Q5 (v7) — rclone OAuth lifecycle 검증 메커니즘 + setup.md 가이드" + Step 3 V19 검증.
- §10.3.3 장애 격리 표에 신규 행: `rclone OAuth revoke | mount daemon 살아있음 (`read()` EIO) | `assert_rclone_auth_alive` fail-fast → VaultSyncFatal → ops-alert`.

**근거**: §10.3.3 본문 "gws 결함 → 변경 감지 끊김 ... vault@.service 가 fail-fast → ops-alert" — gws 만 cover. ADR-0024 본문 "VaultSyncFileFatal 은 retry.json 이 정본 — last_failure.json 에는 기록 안 함" → 모든 file fatal 케이스가 vault-level alert 회피.

---

### HIGH-R12-5: `Requires=` + `Restart=always` 의 timer fire sequencing race — reboot 직후 Persistent catch up 시점

**위치**: §10.4.7 (vault@.service.template patch — `Requires=wikihub-mount@%i.service`) · §10.6.1 (V12 갱신)

**운영 시나리오**: OCI ARM 인스턴스 reboot. systemd 부팅 sequence:
1. `network-online.target` 도달
2. `wikihub-mount@gdrive.service` 시작 (Type=simple) — rclone daemon 이 mount path 생성 + Drive Initial sync (vfs cache warm-up)
3. mount@ 의 ExecStart 가 daemon 모드로 진입 — systemd 가 `active (running)` 분류 (rclone 이 fork 안 함 → Type=simple 의 표준 — exec 자체가 진행되면 active)
4. `wikihub-vault@gdrive.timer` 가 Persistent=true 로 OnBootSec=2min 후 fire
5. `wikihub-vault@gdrive.service` 가 trigger → Requires=mount@ 검증 → mount@ 가 active 이므로 통과
6. ExecStart 실행 → `assert_mount_alive` 호출

**문제**:
- 위 sequence 의 step 3 ↔ step 6 사이 race: rclone mount 가 systemd 에 active 분류된 시점과 실제로 FUSE 가 mount path 에 ready 상태인 시점이 **다르다**. rclone 의 mount 초기화는 `--vfs-cache-mode full` 시 daemon 시작 후 Drive 초기 listing + cache 워밍 동안 mount path 가 응답 안 할 수 있음.
- `Type=simple` 은 ExecStart fork 자체로 active 분류 — daemon ready 와 active 분류가 불일치. 이 race 가 발생하면 vault@.service 가 mount path 의 statvfs 에서 ENOTCONN 또는 ETIMEDOUT.
- §10.6.1 V12 갱신 본문 "wikihub-mount@<vid>.service 자동 진입 + mount path 정상 마운트" — "정상 마운트" 의 검증 시점이 step 3 의 systemd active 분류 후가 아니라 step 6 의 vault@.service 진입 시점까지 보장돼야 함. 명시 부재.

**제안**:
- mount.service.template 에 `ExecStartPost=` 추가 — mount path 가 실제 응답 가능 상태인지 ready check 후 0 반환:
  ```ini
  ExecStartPost=/bin/bash -c 'for i in $(seq 1 30); do stat -f {instance_root}/vault/%i >/dev/null 2>&1 && exit 0; sleep 1; done; exit 1'
  ```
  → mount 가 30s 내 응답 안 하면 ExecStartPost fail → systemd 가 mount.service 를 failed 분류 → Restart=always 가 재시도. vault@ 의 Requires 검증이 active 보장 후만 통과.
- 또는 `Type=notify` 로 전환 + rclone 의 `--rc-systemd-notify` 옵션 (rclone 1.65+) 활용 — daemon ready 시점에 systemd 에 notify. 단 rclone 의 systemd-notify 옵션 가용성 V13 에서 확인 필요.
- §10.6.1 V12 갱신 본문에 명시: "step 6 진입 시점에 `stat -f vault path` 가 5s 내 응답" 추가.

**근거**: §10.4.1 의 `Type=simple` + §10.4.7 의 `Requires=wikihub-mount@%i.service`. systemd 공식 docs — `Type=simple` 의 active 분류 = ExecStart fork 시점 (daemon ready 와 별개). rclone 의 daemon 모드 초기화는 vfs cache 워밍 시간 (size 의존).

---

## MED

### MED-R12-1: per-vault rc port 충돌 사전 점검 부재 + Q3 미결 상태로 release

**위치**: §10.4.1 (`--rc-addr 127.0.0.1:{rc_port_for_%i}`) · §10.4.4 (yaml `rclone_rc_port: 5572`) · §10.5 (Q3 미결)

**운영 시나리오**: 운영자 OCI 서버에 다른 서비스 (예: `prometheus-node-exporter`, `loki`, 자체 모니터링 daemon) 가 이미 port 5572 사용 중. install.sh 실행 → mount.service.template instantiation 후 `systemctl --user start wikihub-mount@gdrive.service` → rclone 의 `--rc-addr 127.0.0.1:5572` 가 bind fail → mount daemon 즉시 exit → `Restart=always` 가 무한 retry → StartLimitBurst 5회/5min 도달 후 stuck.

**문제**:
- install.sh 가 port 5572 의 가용성 pre-check 안 함 (§10.4.2 의 `_install_rclone()` 본문에 미명시).
- yaml default `rclone_rc_port: 5572` — 충돌 시 운영자가 yaml 수동 편집 + mount.service 재 instantiate 필요. 발생 시점이 install.sh 직후가 아니라 mount.service start 시점이라 운영자 인지 latency 증가.
- §10.5 Q3 본문 "잠정 — wikihub.yaml.vaults.<id>.options.rclone_rc_port 명시 (default 5572 + 순번). V17 — 2개 vault 동시 mount + rc 응답 충돌 case 검증" — **자체 vault 간 충돌만 검증**. 외부 서비스와의 충돌 검증 없음.

**제안**:
- install.sh Step 5.5 (`_install_rclone()`) 에 port pre-check helper 추가:
  ```bash
  _check_port_available() {
    local port="$1"
    if ss -tlnp 2>/dev/null | grep -q ":$port "; then
      warn "port $port 가 이미 사용 중 — wikihub.yaml 의 rclone_rc_port 수정 필요"
      return 1
    fi
  }
  ```
- 또는 mount.service.template 의 ExecStartPre 에 동일 check 후 fail-fast.
- §10.5 Q3 본문에 외부 서비스 충돌 케이스 명시 + V17 검증 항목에 "OCI free tier 의 default port 점유 상황 인벤토리 (5572 가 비표준 port 인지 확인)" 추가.

**근거**: §10.4.4 yaml default `rclone_rc_port: 5572`. install.sh §10.4.2 본문에 port pre-check 미명시. Q3 미결 상태 — V17 이 release 전 lock 책임이지만 V17 본문이 vault 간 충돌만 검증.

---

### MED-R12-2: `~/.config/rclone/rclone.conf` 의 chmod 0600 enforce 책임 미명시

**위치**: §10.4.5 (setup.md Step 5.5) · §10.4.1 (mount.service `Environment=RCLONE_CONFIG=`)

**운영 시나리오**: 운영자가 `rclone config` interactive 모드 실행 → OAuth 발급 → `~/.config/rclone/rclone.conf` 자동 생성. rclone 의 conf 파일 default permission 은 0600 이지만 일부 환경 (umask 0022 + 운영자 수동 편집 후 재저장) 에서 0644 가능. conf 파일에는 OAuth `refresh_token` + `client_id`/`client_secret` 평문 저장.

**문제**:
- gws credentials 는 install.sh Step 5 (line 354~371) 가 명시적으로 chmod 0600 검증 + 강제. rclone.conf 는 **install.sh / setup.md 양쪽에 chmod enforce 미명시**.
- §10.4.5 setup.md 본문 "완료 후 `~/.config/rclone/rclone.conf` 에 remote 등록 확인" — permission 검증 미언급.
- 멀티유저 OCI 인스턴스 (메인테이너 user + 다른 user 가 있는 경우) 에서 conf 가 0644 면 다른 user 의 refresh_token leak.

**제안**:
- install.sh Step 5.5 본문 (rclone install 후) 에 conf permission enforce 추가:
  ```bash
  if [ -f "$HOME/.config/rclone/rclone.conf" ]; then
    chmod 600 "$HOME/.config/rclone/rclone.conf"
  fi
  ```
- §10.4.5 setup.md Step 5.5 본문에 명시: "10. `chmod 0600 ~/.config/rclone/rclone.conf` 권한 확인 (rclone default 가 0600 이지만 idempotent 보장)".
- §10.5 미결 Q 표에 신규 행: "Q6 (v7) — rclone.conf 의 permission enforce 책임 (install.sh vs setup.md vs mount.service ExecStartPre)" + Step 3 V20 검증.

**근거**: install.sh line 354~371 의 gws credentials chmod 0600 패턴 — rclone 은 동등 패턴 미적용. §10.4.1 의 `Environment=RCLONE_CONFIG={rclone_config_path}` 가 conf 경로 주입만 명시.

---

### MED-R12-3: rclone `--log-level INFO` 의 OAuth token 노출 위험 + 운영자 yaml override 경로

**위치**: §10.4.1 (mount.service `--log-level INFO`)

**운영 시나리오**: 운영자가 mount sync 문제 진단 위해 `--log-level INFO` → `--log-level DEBUG` 변경 (mount.service.template 직접 편집). DEBUG 모드에서 rclone 이 HTTP request/response header 전체 dump → `Authorization: Bearer ya29...` access_token leak 가 journal 에 영속화. journalctl 권한 (메인테이너 user 의 journal) 으로 token 노출.

**문제**:
- §10.4.1 본문 default `--log-level INFO` — INFO 자체는 안전하지만 DEBUG 전환 경로 가이드 부재.
- mount.service.template 직접 편집 vs yaml override 의 책임 불명확. §10.4.4 yaml 본문에 `rclone_log_level` 옵션 미존재.
- DEBUG 운영 후 INFO 복귀 절차 미명시.

**제안**:
- §10.4.4 yaml 본문에 `rclone_log_level: INFO` 추가 + substitution variable `{rclone_log_level}` 로 mount.service.template 의 `--log-level` 치환:
  ```yaml
  operations:
    rclone_log_level: INFO   # INFO | DEBUG (DEBUG 시 token 노출 위험 — 진단 후 INFO 복귀 필수)
  ```
- §10.4.5 setup.md 또는 README 운영 진단 섹션에 "DEBUG 활성화 후 token redaction 절차 (`journalctl --user --vacuum-time=1d` 등)" 명시.
- §10.5 미결 Q 표에 추가 (Q7 — rclone DEBUG 로그 활성화 시 token redaction 정책).

**근거**: §10.4.1 본문의 `--log-level INFO` hardcoded. rclone 공식 docs 의 DEBUG 모드 log 가 HTTP body 노출 명시. ADR-0024 의 webhook payload 도 token redaction (`reason` 본문에 toekn 절단) 책임 — log path 도 동일 기준 필요.

---

### MED-R12-4: gws v0.x breaking change 시 부분 outage 시나리오 명시 부재

**위치**: §10.3.3 (장애 격리 표) · §10.5 (Q4 미결)

**운영 시나리오**: gws v0.7.0 → v0.8.0 minor 업데이트 후 `gws drive changes list` 의 응답 schema 변경 (alpha — breaking 가능). install.sh 가 `operations.gws_min_version` 만 검증 — schema 변경 catch 안 함. mount 는 살아있음 (rclone 의 `--vfs-cache-mode full` 로 read 자체는 동작). 그러나 변경 감지 끊김 → 사이클은 success 분류 (`gws drive changes list` 가 빈 응답 반환하면 "변경 없음" 으로 인식) → 점진적 stale.

**문제**:
- §10.3.3 본문 "gws 결함 → 변경 감지 끊김. mount 는 살아있어 운영자 SSH UX 유지" — gws "결함" 의 정의 모호. exit code fail 은 ADR-0017 매핑으로 catch 가능하지만 **success 분류 + 응답 schema 변경** 케이스 미명시.
- gws v0.x 의 breaking change 가 silent stale 로 surface → mount path 의 read 는 fresh (vfs cache 가 invalidate 됨) 인 것처럼 보이지만 gws 가 변경 감지 안 함 → wiki page 미갱신 → 운영자가 인지 매우 늦음.

**제안**:
- §10.5 미결 Q 표에 추가: "Q8 (v7) — gws response schema regression detection. 사이클 시작 시 changes.list 응답의 필수 필드 (kind, time, changeType 등) presence assertion".
- `scripts/lib/gws.py` 또는 `sync.py` 의 changes.list 호출 직후 schema assert:
  ```python
  required_keys = {"kind", "newStartPageToken"}
  if not required_keys.issubset(changes.keys()):
      raise VaultSyncFatal(
          reason=f"gws changes.list response missing keys: expected {required_keys}, got {set(changes.keys())}",
          remediation="gws downgrade 또는 schema 매핑 갱신 필요",
      )
  ```
- §10.3.3 본문 "장애 격리" 에 신규 행: "gws breaking change → schema mismatch → 사이클 시작 schema assert fail-fast → VaultSyncFatal → ops-alert".

**근거**: rclone_vs_gws_comparison.md §2 "성숙도: alpha (v0.x — breaking change 가능)". ADR-0014 본문 "gws alpha 부담을 운영 시작 전 회피하고자 함" — §10.3.3 의 책임 분리가 이 부담을 격리한다고 명시했지만 schema-level regression 의 catch 책임 미명시.

---

## LOW

### LOW-R12-1: mount.service.template 의 `WantedBy=default.target` — multi-vault 동시 부팅 시 vfs cache 워밍 contention

**위치**: §10.4.1 (`[Install] WantedBy=default.target`)

**운영 시나리오**: 운영자가 2~3개 vault (gdrive, gdrive2, shared_drive) 동시 운영. reboot 후 모든 mount.service 가 default.target 도달 시점에 동시 시작 → 3개 rclone daemon 이 동시에 Drive API 호출 + vfs cache 초기 워밍. OCI free tier 의 1Gbps egress + Drive quota 압박.

**문제**:
- 첫 부팅 후 워밍 시간 늘어남 → V12 의 "5분 내 사이클 fire" acceptance 위반 가능.
- 운영 visibility — 어느 mount@ 가 느린지 운영자 진단 부담.

**제안**:
- §10.5 미결 Q 표에 추가 (Q9 — multi-vault 동시 부팅 시 staggered start). 또는 mount.service.template 에 `OnBootSec=` 패턴 적용:
  ```ini
  [Unit]
  After=network-online.target wikihub-mount@%i-prev.service
  ```
  → Q9 결정 후 lock.
- v0.1.0 single-vault 가정에서는 LOW. multi-vault 가 v0.2.x 사용 사례 진입 시 surface.

**근거**: §10.4.1 의 `WantedBy=default.target` 만 명시. multi-vault staggered start 정책 부재. plan.md v2 "운영 환경 가정" 의 multi-vault 가정 미명시.

---

### LOW-R12-2: rclone min_version pinning 의 운영 실수 — `rclone_min_version: 1.65.0` 의 의미가 unclear

**위치**: §10.4.4 (yaml `rclone_min_version: 1.65.0`) · §10.4.2 (install.sh `_install_rclone`)

**운영 시나리오**: rclone 1.65.0 → 1.68.0 (가상 release) 의 vfs/refresh API 시그니처 변경. `wikihub.yaml.operations.rclone_min_version: 1.65.0` 만 검증 → 운영자가 OS apt 로 rclone 1.68.0 설치 시 install.sh skip → `_version_ge` 가 1.68.0 ≥ 1.65.0 통과. mount 는 동작하지만 `vfs_refresh` 가 fail.

**문제**:
- min_version 만 검증 + upper bound 미명시. 운영자가 "min_version 이상이면 동작" 가정하나, alpha API (rc commands) 는 breaking change 가능.
- gws 도 동일 패턴 (`gws_min_version`) 사용 → ADR-0015 가 이미 명시 (alpha 가 명시적이라 운영자 인지 가능). rclone 은 stable (v1.x) 이라 운영자가 "stable 의 breaking change 없음" 가정 — 위험.

**제안**:
- §10.4.4 yaml 본문에 `rclone_max_version` 옵션 추가 (v0.2.x deferred 라도 stub) 또는 §10.5 미결 Q 표에 "Q10 — rclone API stability assert (rc vfs/refresh schema)" 추가.
- Step 3 V16 검증 case 보강: "rclone 1.65.0 + 1.x 최신 두 버전에서 vfs/refresh API 응답 동일성".

**근거**: §10.4.4 의 `rclone_min_version` 만 명시. rclone rc API 의 stability guarantee 본문 미참조.

---

## NIT

### NIT-R12-1: V<N> 표의 신규 verification 의 환경 가정 unclear

**위치**: §10.6.2 (V13~V17)

**문제**: V13~V17 본문이 "OCI 인스턴스에서" 또는 "clean ARM Ubuntu" 등 환경 가정을 verification 별로 명시하지만 V15 (race window) 는 환경 명시 부재. V15 가 가장 중요한 (v7 핵심) verification 이라 환경 명시 필요.

**제안**: V15 본문에 "환경: OCI ARM Ubuntu test instance (V12 와 동일 instance — 통합 검증)" 추가. v6 plan.md v2 의 V<N> 표 패턴 (사전 조건 / 운영 가정 §) 와 정합.

**근거**: §10.6.2 V13 "`systemctl --user start wikihub-mount@gdrive`" 명시. V15 본문은 "Drive 에서 파일 X 의 content 수정" 만 명시 — 어느 instance 인지 unclear.

---

## 결론

### 본 라운드 결함의 운영 영향도

v7 의 architectural shift (rclone mount 도입) 는 v6 의 stateless gws subprocess 모델에서 **stateful FUSE daemon 모델** 로 운영 부담을 옮긴다. 본 라운드는 다음 SRE 관점 결함을 surface:

1. **fatal 알림 채널의 silent dead zone** (CRIT-1, HIGH-4): mount StartLimit 소진 + rclone OAuth revoke 의 두 시나리오에서 ops-alert 가 발화 안 함. v0.1.0 acceptance invariant ("사람 개입 없이 자동 재기동") 의 fallback alert 신뢰성 깨짐.
2. **hung mount 가 사이클 hang 으로 propagation** (CRIT-2): `os.statvfs` 의 timeout 부재로 fail-fast 가 fail-block 으로 동작 가능.
3. **supply chain 위험 증가** (HIGH-3): `curl ... | sudo bash` 가 ADR-0023 의 위협 매트릭스보다 큰 surface. sha256 verify 미적용.
4. **운영 visibility/capacity 가이드 부재** (HIGH-1·2·5, MED-1~4): vfs cache 디스크 압박 · refresh latency · port 충돌 · token 노출 · OAuth lifecycle 등 v6 의 stateless 모델에서 없던 운영 변수가 v7 에서 신규.

### v0.1.0 release blocking 분류

**release blocking (Step 2 v7 본문 fix 후 v8 또는 Step 3 spec 보강 필수)**:
- CRIT-R12-1 (mount.service OnFailure 미설정 — fatal 알림 silent)
- CRIT-R12-2 (os.statvfs hang block)
- HIGH-R12-1 (vfs/refresh latency 측정 절차 부재 — V15b 신규)
- HIGH-R12-2 (vfs cache 디스크 압박 + OCI free tier 가이드)
- HIGH-R12-3 (rclone install supply chain — sha256 verify)
- HIGH-R12-4 (rclone OAuth lifecycle alert 부재)
- HIGH-R12-5 (mount ready ↔ active 분류 sequencing race)

위 7건은 v0.1.0 acceptance invariant (V12 reboot resilience + fatal 알림 contract) 정합 위반. Step 2 v7 → v8 revision 또는 Step 3 V<N> 보강 필수.

**v0.2.x deferred 적정 (운영 가이드 명시 + ADR 또는 docs 항목 추가로 충족)**:
- MED-R12-1 (port 충돌 pre-check)
- MED-R12-2 (rclone.conf chmod enforce)
- MED-R12-3 (log-level DEBUG token 노출 가이드)
- MED-R12-4 (gws schema regression detection)
- LOW-R12-1 (multi-vault staggered start)
- LOW-R12-2 (rclone max_version)

위 6건은 v0.1.0 single-vault 운영에서 surface 가능성 낮음 + 운영자 가이드/yaml 옵션으로 mitigation 가능. v0.2.x feature 로 분리 권장.

**NIT**:
- NIT-R12-1 (V15 환경 명시) — Step 2 v7 본문 minor revision.

### 권고 — Step 2 v7 → v8 revision 진입

본 라운드의 CRIT 2건 + HIGH 5건을 §10 본문에 surgical 반영 후 v8 approved 마커 + ADR-0025·0026·0027 본문 작성 진입. v0.2.x deferred 항목은 §10.5 미결 Q 표에 새 Q5~Q10 행으로 추가 + plan.md v3 의 후속 feature 로 분리 권고.
