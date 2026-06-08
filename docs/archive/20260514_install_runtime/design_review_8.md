# F4 design review R14 (general-purpose SRE — Step 2 v8)

- **리뷰어**: general-purpose SRE
- **대상**: v7 → v8 transition (§10 v8 patch) — 운영 reliability 만
- **정본**: `analysis_and_design.md` v8 §10 (line 1081~1627), 특히 §10.4.1·§10.4.2·§10.4.3·§10.4.6·§10.5 Q5~Q9·§10.6.2 V14/V15-cost
- **검토 관점**: 24/7 운영 reliability · observability · failure recovery · **fix-induced operational regression**
- **독립성 선언**:
  - R12 (`design_review_6.md`, v7 라운드 SRE) 의 14건 (mount silent dead, `os.statvfs` hang, supply chain curl-pipe, OAuth revoke silent, OCI 디스크 budget, port 충돌 pre-check, rclone.conf chmod, log-level DEBUG token 노출, gws schema regression, multi-vault staggered start, rclone max_version, V15 환경 명시) 은 v8 patch 가 처리 — **재발견 금지**.
  - R13 (병렬 라운드, code-reviewer) 의 internal consistency · yaml-template substitution 정합 · spec 정합 영역 — **회피**.
  - R11 (`design_review_5.md`, v7 라운드 code-reviewer) 의 sync.py 다운로드 헬퍼 교체 · ADR cross-reference · _resolve_mount_path flat lock 등 — **회피**.
- **본 라운드 범위**: v8 patch 가 **새로 도입한** 운영 위험만 surface — fix 의 부작용 (operational regression). v0.1.0 release blocking vs v0.2.x deferred 명확 분류.

## 결함 요약

| 분류 | 건수 | release blocking |
|---|---|---|
| CRIT | 1 | v0.1.0 blocking |
| HIGH | 4 | v0.1.0 blocking |
| MED | 4 | v0.2.x 적정 또는 운영 가이드 |
| LOW | 2 | v0.2.x 적정 |
| NIT | 1 | 권고 |

총 12건. v8 patch 의 fix 자체가 새 운영 위험을 surface — 특히 `OnFailure=ops-alert.service` 추가가 dual-edge (silent dead 차단 ↔ alarm fatigue 양산), `ls -la` 직접 호출이 multi-vault contention 가속화, `assert_mount_alive` 의 `Retryable` 채택이 mount permanently failed 의 silent 진행을 만든 점에 집중.

---

## CRIT

### CRIT-R14-1: mount@ `Restart=always` 의 매 재기동 cycle 마다 `OnFailure` 가 false trigger — ops-alert dedup 폭주

**위치**: §10.4.1 mount@.service.template (`Restart=always`, `RestartSec=10s`, `StartLimitBurst=5`, `OnFailure=ops-alert.service`)

**운영 시나리오**: rclone mount daemon 이 일시적 결함 (Drive API 5xx · 네트워크 flap · 운영자 `kill -9` · OOM · cgroup 제한 등) 으로 4회 죽고 4회 자동 재기동 성공 (StartLimitBurst=5 미만). 매 죽음마다 systemd 가 service 를 `failed` 상태로 분류 후 `RestartSec=10s` 대기 후 재기동.

**문제**:
- systemd 의 `OnFailure=` 의미론은 **service 가 `failed` 상태로 전이할 때마다** 발화 — `Restart=` policy 와 무관하게 trigger. systemd.unit(5) man page 명시:
  > `OnFailure=` ... Lists one or more units that are activated when this unit enters the "failed" state.
- 결과: **4회 fail → 4회 ops-alert.service trigger → 4회 ops-alert.py 실행** (Restart=always 가 5회째 성공 재기동했지만 그 사이 매번 발화). v8 patch 의 의도 ("StartLimitBurst 초과 시 알림 한 번") 와 실제 systemd 동작 불일치.
- ops-alert.py 의 dedup 은 **`last_failure.json` 기반** (`failed_count` + 24h reminder). mount@ 가 `last_failure.json` 을 쓰는 producer 가 **부재** — §10.4.1 본문에 `ExecStopPost=` 또는 별도 last_failure writer 미명시. ops-alert.py 가 mount@ 의 `failed` state 를 인지할 수 있는 last_failure 입력 자체 없음 → ops-alert.py 는 빈 input 으로 실행 → exit 0 → journal 만 남음 → **사실상 4회 ops-alert.py 가 trigger 됐지만 webhook 발화 0건**.
- 더 나쁜 케이스: 일부 vault@ 가 `last_failure.json` 을 쓴 상태에서 mount@ 의 OnFailure trigger 로 ops-alert.py 가 빈번 발화. 이 경우 vault@ 의 fatal 이 mount@ 의 retry cycle 마다 (5회/5min) webhook 4~5회 발화 → **alarm fatigue + dedup 정책 회피** (vault@ 의 `last_failure.json` 은 dedup 됐지만 mount@ trigger 가 dedup 우회).
- R12-CRIT-1 의 의도 (mount StartLimit 소진 후 fatal alert) 는 살아있지만, v8 patch 가 **propagation 비용을 4~5배** 로 증가. R12 가 surface 안 한 새 결함.

**제안**:
- 옵션 (a) **mount@ 전용 OnFailure 분리**: `OnFailure=mount-fail-recorder.service` 신규. mount-fail-recorder.service 가 `_state/<vault_id>/mount_failure.json` 에 fail event 누적 → `failed_count >= StartLimitBurst` 도달 시에만 `last_failure.json` 쓰기 (또는 별도 webhook payload 생성). systemd 의 `OnFailure` 가 매번 trigger 되더라도 dedup 은 recorder 내부에서.
- 옵션 (b) **mount@ 에 `OnFailure` 미설정 + ExecStopPost 기반 detection**: `ExecStopPost=/path/mount-stop-checker.sh` 가 환경변수 `$EXIT_CODE` 와 `$SERVICE_RESULT` 확인 후 5회 누적 도달 시에만 last_failure 쓰기 + 명시적 ops-alert.service trigger (`systemctl --user start --no-block ops-alert.service`).
- 옵션 (c) **systemd `OnFailure=` 의 `JobMode=` 활용**: systemd 256+ 의 `OnFailureJobMode=fail` 로 동시 발화 dedup. 단 OCI Ubuntu 22.04 의 systemd 249 미지원 → 적용 불가.
- **권고**: 옵션 (a). recorder service 패턴 (ADR-0024 의 producer/reader 분리 정합). Step 3 에 V14 보강 — "mount@ 5회 재기동 중 4회 fail 시 ops-alert.py 가 webhook 0건 발화 (recorder 가 StartLimitBurst 도달 시에만 발화)".
- 최소한 §10.4.1 본문에 **mount@ 의 매 fail cycle 마다 ops-alert.service 가 trigger 된다는 사실** 을 명시 + dedup 의존을 `last_failure.json` writer producer 신설로 lock.

**근거**:
- systemd.unit(5) man page — `OnFailure=` 가 매 `failed` 상태 전이 시 발화. `Restart=always` 와의 상호작용은 systemd 가 매 죽음마다 일시적으로 `failed` 분류 후 재기동.
- §10.4.1 본문 line 1198 코멘트 "StartLimitBurst 초과 fail 시 즉시 ops-alert 발화" — 의도와 실제 systemd 동작 불일치.
- ops-alert.py line 90~109 `collect_last_failures` — `_state/<vault_id>/last_failure.json` 만 입력. mount@ producer 부재 시 빈 input.
- ADR-0024 line 53 "Writer 책임 — `scripts/vault-fetch.py` 수정" — mount@ 의 last_failure writer 미정의.

---

## HIGH

### HIGH-R14-1: GitHub Releases 단일 채널 의존 — rclone.org 다중 mirror 운영보다 가용성 회귀

**위치**: §10.4.2 `_install_rclone` (line 1241~1273), Q2 v8 lock

**운영 시나리오**: v0.1.0 release 후 메인테이너가 OCI ARM 서버에 clean install 진행 → `install.sh` Step 5.5 진입 → `curl -fsSL -o /tmp/${archive} ${base}/${archive}` (base = `github.com/rclone/rclone/releases/download/v...`). 이 시점에 **GitHub 가 incident** (e.g., 2024-08 의 LFS/Releases 다운, 2022-06 의 region-level outage) — install.sh fail.

**문제**:
- v7 의 `rclone.org/install.sh | sudo bash` 는 rclone.org 의 CDN 다중 mirror (Fastly + Cloudflare 등) 가용성 + apt fallback 경로 (`apt install rclone` — old version 이지만 동작) 를 운영자가 선택 가능. v8 patch 의 GitHub Releases 단일 채널은 **GitHub 의 단일 fail point 의존**.
- GitHub Releases 의 historical incident 빈도 (2024년 8건 incident, 평균 30분~3시간) 가 rclone.org/CDN 의 빈도보다 높음. supply chain 위협 (R12-HIGH-3) 을 줄이는 대신 **가용성 위험 증가**.
- 더 나쁜 케이스: GitHub Releases 가 다운인데 메인테이너가 install.sh 실행 → `_die "rclone SHA256 verify 실패"` 등 misleading error (실제로는 SHA256SUMS 파일 자체가 404 → grep 빈 결과 → sha256sum -c fail). 운영자가 supply chain 위협으로 오인 → 진단 시간 낭비.
- R12-HIGH-3 의 sha256 verify 목적은 **artifact integrity** — mirror 다양성과 직교. 단일 GitHub 채널 lock 은 over-correction.

**제안**:
- 옵션 (a) **fallback 채널 명시**: 1차 GitHub Releases + 실패 시 2차 rclone.org/downloads (SHA256SUMS 도 rclone.org 에서 fetch 가능 — `rclone.org/v${pinned}/SHA256SUMS`). 두 채널 모두 SHA verify.
- 옵션 (b) **error path 의 진단 개선**: SHA verify 실패 분기를 (i) SHA file 404 (artifact 미존재) vs (ii) hash 불일치 (변조 의심) 로 분리. (i) 는 "GitHub Releases 다운 또는 version 오기재 — fallback 채널 검토" 메시지.
- 옵션 (c) **acceptance 기준 명시**: §10.5 Q2 본문에 "v0.1.0 acceptance 는 GitHub Releases 가용성 가정 — 다운 시 install.sh 재실행 (운영자 부담)" 명시. v0.2.x 에서 mirror 추가 (R12 의 supply chain 위협 모델 정합 유지).
- **권고**: 옵션 (b) 최소 + 옵션 (c) 명시. 옵션 (a) 는 v0.2.x.
- Step 3 V16 보강: "GitHub Releases 가 404 일 때 install.sh 의 error 메시지가 supply chain 위협이 아닌 가용성 문제로 surface 되는지".

**근거**:
- §10.4.2 line 1264~1267 `curl -fsSL -o ... ${base}/${archive}` + `curl -fsSL -o ... ${base}/SHA256SUMS` — 둘 다 GitHub 단일 origin.
- §10.5 Q2 v8 lock 본문 "GitHub Releases binary + SHA256SUMS verify (`rclone.org/install.sh` 폐기)" — fallback 채널 미명시.
- GitHub status historical data (https://www.githubstatus.com/history) — Releases 영역의 incident 빈도.
- R12-HIGH-3 본문 "(a) curl-pipe 대신 직접 binary 다운로드 + sha256 검증" 의 권고는 채널 변경 권고 아님 — verify 추가 권고. v8 patch 가 over-correction.

---

### HIGH-R14-2: `_check_rc_port_available` 가 user-level install 환경에서 false negative — 다른 user 점유 port 비가시

**위치**: §10.4.2 `_check_rc_port_available` (line 1287~1296)

**운영 시나리오**: OCI 인스턴스에 메인테이너 user `ubuntu` 이외에 다른 user `monitoring` 이 prometheus-node-exporter 실행 (port 5572 미사용이지만 5573 점유). `monitoring` user 가 systemd-user 모드로 daemon 운영. 메인테이너가 `ubuntu` 로 `install.sh` 실행 (이 시점 sudo 가능). install.sh Step 5.5c `ss -tlnH "( sport = :${port} )"` 호출.

**문제**:
- `ss -tlnH` 는 default 로 **all namespaces · all users 의 listening socket** 을 보여주지만, 일부 환경에서:
  - non-root user 가 `ss -p` (process info) 호출 시 다른 user 소유 process info 가 redacted — 그러나 port 자체는 보임.
  - **그러나 user-network-namespace 가 격리된 경우** (예: `systemd-nspawn` container 안 또는 `unshare -n` 후 실행) port 가 비가시.
- v8 patch 의 본문은 단순 `ss -tlnH` — sudo 미사용. ARM Ubuntu 22.04 default 에서 `ss -tln` 은 모든 listening port 가시 (`ip_netns` 격리 없는 가정). 그러나 가정 부재.
- false negative 시나리오: port 5572 가 (i) 다른 user 가 점유 + (ii) install.sh 가 비가시 → pre-check pass → mount.service 시작 → rclone bind fail → mount daemon 즉시 exit → `Restart=always` 무한 retry → 위 CRIT-R14-1 의 alarm fatigue.
- 더 미묘한 케이스: SO_REUSEADDR/SO_REUSEPORT 점유. `ss -tlnH` 가 LISTEN 만 보지만 REUSEPORT bind 된 다른 process 의 port 는 같은 host 의 새 bind 가능 (Linux 의 SO_REUSEPORT 의미). false positive 가능.

**제안**:
- §10.4.2 5.5c 본문에 **명시**:
  ```bash
  _check_rc_port_available() {
    local port="$1"
    # ss 는 user namespace 가 host 와 동일하다는 가정 (OCI ARM Ubuntu 22.04 default)
    # multi-user 환경 (다른 user 가 daemon 실행) 에서는 sudo ss 가 필요할 수 있음
    if ! ss -tlnH 2>/dev/null | grep -qE ":${port}\s"; then
      return 0
    fi
    _die "rclone rc port ${port} 이 이미 사용 중 (ss 가시 범위 내) — wikihub.yaml.vaults[*].options.rclone_rc_port 변경"
  }
  ```
- pre-check **실패 fallback**: rclone mount.service 의 `ExecStartPre=` 에도 동일 port check (실 bind 직전 한 번 더). install.sh 시점의 가시성 한계를 mount.service 시작 시점에 보완. rclone 자체가 bind fail 시 exit code 1 이지만 명시적 진단 message 가 systemd journal 에 남도록.
- §10.5 Q3 본문 보강: "v0.1.0 단일 user 가정 (메인테이너 user = ubuntu) — multi-user 환경은 v0.2.x".
- V17 보강: "port 5572 가 (i) install.sh 와 동일 user 의 다른 process · (ii) 다른 user 의 process 두 케이스 각각 pre-check pass/fail 확인".

**근거**:
- §10.4.2 line 1290 `ss -tlnH "( sport = :${port} )"` — sudo 미사용, namespace 가정 미명시.
- `ss` man page (iproute2): `-H` 는 header 억제. user namespace 격리는 자동 처리 안 됨 — `--all` (`-a`) 도 listening 외 추가 정보지만 namespace 통과는 별개.
- SO_REUSEPORT semantics: `man 7 socket`.

---

### HIGH-R14-3: `assert_mount_alive` 의 `subprocess.run(['ls', '-la', mount_path])` 가 매 사이클 VFS cache warming 폭주 + 사이클 latency 증가

**위치**: §10.4.6 `assert_mount_alive` (line 1471~1488), v8 patch (R12-CRIT-2 fix)

**운영 시나리오**: OCI ARM 서버에 vault 1개 (gdrive) 운영, vault 크기 = 5,000 파일 (Drive 폴더 평탄 배치). `wikihub-vault@gdrive.timer` 가 10min 주기 fire → 매 사이클 시작 시:
1. `assert_mount_alive("/vault/gdrive", timeout=5s)` → `subprocess.run(['ls', '-la', '/vault/gdrive'], timeout=5)`
2. `vfs_refresh` (recursive=true) → rclone 이 root level + 1 depth refresh
3. `gws drive changes list` → 변경 감지

**문제**:
- `ls -la` 는 mount path 의 모든 entry 의 **`stat()` 호출** 을 트리거 — 5,000 파일에 대해 rclone FUSE 가 각각 metadata fetch (vfs cache 가 cold 인 첫 fire 또는 `dir-cache-time 5m` 만료 후 fire). 매 사이클 시작에 5,000회 `stat()` 부하.
- rclone `--dir-cache-time 5m` 이라 5min 내 fire 면 cache hit (저비용), 그러나 `vault-ingest.timer` 의 `OnUnitActiveSec=10min` 가 5min 보다 길어 **매 사이클이 cache miss** 가능성 높음.
- `--vfs-cache-mode full` 의 의도는 download 캐싱 — `ls -la` 의 metadata stat 은 별도 vfs metadata cache (`dir-cache-time` 영역). 매 사이클 cache miss → 매 사이클 5,000 회 Drive metadata API 호출 → **OCI free tier egress + Drive API quota 압박**.
- **timeout=5s 의 cover 가능성 의문**: vault 가 1,000 파일이면 5s 내 충분히 응답하나, 10,000 파일 시 5s 도달 가능 → `subprocess.TimeoutExpired` → `VaultSyncRetryable(reason="mount path ls timeout")` → 사이클 abort. v8 의 V14(b) 가 검증할 hung mount 시나리오와 **정상 큰 vault** 의 ls 응답이 동일 분기 진입 → false retryable.
- R12-LOW-1 (multi-vault contention) 의 단일 vault 버전. v0.1.0 single-vault 운영에서도 큰 vault 시 surface.
- v6 의 `os.statvfs` (CRIT-R12-2) fix 의 부작용 — `statvfs` 는 filesystem-level stat (entry count 무관) 였으나 `ls -la` 는 entry 비례 비용. **fix 가 새 운영 위험 surface**.

**제안**:
- 옵션 (a) **`ls -la` → `ls` (no -la)**: `-la` 의 `-l` (long format) 이 `stat()` 트리거. 단순 entry 나열 (`ls /vault/gdrive`) 은 `readdir()` 만 — metadata fetch 회피.
- 옵션 (b) **`stat` 명령어로 mount root 만 확인**:
  ```python
  result = subprocess.run(
      ["stat", "-f", "-c", "%T", str(mount_path)],  # filesystem type 만
      capture_output=True, text=True, timeout=timeout_sec, check=False,
  )
  # 결과가 "fuseblk" 또는 "fuse" 이면 mount alive
  ```
  `stat -f` 는 filesystem-level — entry 무관. Linux `man 1 stat` 확인.
- 옵션 (c) **rclone rc 만 사용**: `rclone rc --rc-addr ${rc_addr} core/version` 호출. rclone daemon 자체 health check — mount path 의 FUSE 응답과 별개지만 daemon 죽음은 catch. mount path 의 FUSE 응답성은 vfs_refresh 가 다음 step 에서 확인.
- **권고**: 옵션 (b) — `stat -f` 가 entry 무관 cost 보장 + FUSE 응답성 검증. 옵션 (a) 는 `readdir` 자체도 큰 vault 에서 비용 있음.
- §10.4.6 본문에 "`ls -la` 가 entry 비례 비용 → 큰 vault 에서 timeout 가능. `stat -f` 로 filesystem-level 확인" 명시.
- Step 3 V14(d) 신규: "vault 5,000 / 10,000 파일 케이스에서 `assert_mount_alive` latency 측정 + timeout 5s 안전 한도 확인".

**근거**:
- §10.4.6 line 1472~1475 `subprocess.run(["ls", "-la", str(mount_path)], ...)` — `-l` flag 가 entry 별 `stat()` 트리거.
- rclone docs (`--dir-cache-time`): default 5min, refresh 트리거는 `vfs/refresh` 또는 expiry. mount FS `stat()` 자체는 vfs metadata cache 적중 시 빠르지만 miss 시 Drive API 호출.
- POSIX `ls` semantics: `-l` 은 entry 별 metadata 표시 — 구현상 `stat()` 호출 필수.
- v6 `os.statvfs` semantic 비교: `statvfs` (2) 는 mount point 의 statfs syscall — entry 무관. v8 의 `ls -la` 는 entry 비례.

---

### HIGH-R14-4: `assert_mount_alive` 가 `VaultSyncRetryable` 만 raise — mount permanently failed 시 사이클이 silent 영구 abort

**위치**: §10.4.6 `assert_mount_alive` (line 1482~1488), §10.5 Q5 v8 잠정

**운영 시나리오**: mount@.service 가 StartLimitBurst=5/300s 초과 → systemd 가 `failed` state 유지 + 재기동 안 함. vault@.timer 는 10min 주기로 계속 fire → vault@.service 의 `Requires=wikihub-mount@%i.service` 가 mount@ 의 failed 상태로 dependency fail. systemd 가 vault@.service 를 dependency-failed 분류 → ExecStart 미실행.

**문제**:
- §10.4.7 본문 (line 1550~1556) 의 race 처리 의도 — `assert_mount_alive` 가 `Retryable` raise → exit 75 → `SuccessExitStatus=0 75` 로 success 분류 → ops-alert 미발화. 이 의도는 **reboot 직후 첫 사이클** (mount@ 가 starting → ready transition 중) 에 한정 효과.
- 그러나 **mount permanently failed** 상태에서는:
  - vault@.service 가 systemd `Requires=` propagation 으로 dependency-failed → ExecStart 미실행 → assert_mount_alive 호출조차 안 됨 → exit 75 분기도 진입 안 함.
  - systemd 의 dependency-failed 결과는 `OnFailure=ops-alert.service` 가 발화 — 그러나 vault@ 의 fatal scope (`last_failure.json`) writer 는 vault-fetch.py 내부에서만 호출. ExecStart 미실행이라 writer 미호출 → `last_failure.json` 미기록 → ops-alert.py 가 빈 input → webhook 0건.
  - 결과: mount permanently failed → vault@.service 가 매 timer fire 마다 dependency-failed (조용히) → ops-alert.py 가 매번 발화하지만 webhook 0건 → **운영자 인지 0**.
- §10.5 Q5 본문 "운영자 개입: `systemctl --user reset-failed wikihub-mount@<vid>` → start" — Hermes 자동 운영 환경에서 **운영자 SSH 접속 없음** 가정. R12-CRIT-1 의 mount@ OnFailure 추가가 위 fail mode 의 일부만 cover (CRIT-R14-1 의 한계 + writer 부재).
- Q5 의 "자동 복구는 v0.1.0 미지원" 은 ADR-0021 의 acceptance invariant ("OS reboot 후 사람 개입 없이 자동 재기동") 와 직접 충돌. v8 patch 가 surface 만 했지 해소 안 됨.

**제안**:
- 옵션 (a) **vault@.service 에 `BindsTo=` 대신 `Wants=` 사용** + ExecStart 진입 후 `assert_mount_alive` 가 mount permanently failed 분기 추가:
  ```python
  # mount.py
  def assert_mount_alive(...):
      ...
      # mount@.service 상태도 확인 — systemctl is-failed 호출
      result = subprocess.run(
          ["systemctl", "--user", "is-failed", f"wikihub-mount@{vault_id}.service"],
          capture_output=True, text=True, timeout=2,
      )
      if result.stdout.strip() == "failed":
          raise VaultSyncFatal(
              vault_id=vault_id,
              reason=f"mount@ permanently failed — StartLimitBurst 초과. systemctl --user reset-failed wikihub-mount@{vault_id} 후 start",
              remediation="ssh ... && systemctl --user reset-failed wikihub-mount@{vid} && systemctl --user start wikihub-mount@{vid}",
          )
  ```
- 옵션 (b) **mount permanently failed 시 last_failure.json producer 신설** (CRIT-R14-1 의 옵션 (a) 와 통합 — `mount-fail-recorder.service` 가 StartLimitBurst 도달 시 last_failure.json 쓰기).
- 옵션 (c) **v0.1.0 acceptance 기준 명시 수정**: ADR-0021 본문에 "mount@ permanently failed 케이스는 운영자 SSH 개입 필수 — acceptance invariant 의 예외" 명시 + 운영 매뉴얼에 escalation 절차 명시.
- **권고**: 옵션 (b) 가 CRIT-R14-1 와 통합 — 단일 producer 가 두 fail mode (매 cycle alarm fatigue + permanently failed silent) 모두 cover. 옵션 (a) 는 vault@ ExecStart 가 실행되는 가정 — `Requires=` 의 dependency-failed 분기는 cover 못 함. 옵션 (c) 는 acceptance 후퇴.
- Step 3 V14(e) 신규: "mount@ StartLimitBurst 5회 도달 + vault@ timer 3회 fire 후 webhook 도달 확인 (현 spec 0회 도달 예상)".

**근거**:
- systemd.unit(5) `Requires=`: 의존 unit 이 failed 면 본 unit 은 dependency-failed (시작 안 함). `OnFailure=` 는 unit 이 active state 진입 후 fail 한 경우 발화 (dependency-failed 도 일부 systemd 버전에서 OnFailure trigger 하지만 vault-fetch.py 의 last_failure writer 는 ExecStart 실행 가정).
- §10.4.7 line 1543 `SuccessExitStatus=0 75` — exit 75 분기 가정 (ExecStart 실행).
- §10.5 Q5 v8 잠정 line 1574 "운영자 개입" — Hermes 자동 운영 가정과 충돌.
- ADR-0021 본문 "OS reboot 후 사람 개입 없이 자동 재기동" — Q5 의 "자동 복구는 v0.1.0 미지원" 과 충돌.

---

## MED

### MED-R14-1: `--log-level NOTICE` 의 trouble-shooting 운영성 회귀 — DEBUG override 경로 부재

**위치**: §10.4.1 mount@.service.template (line 1210, v8 patch — INFO → NOTICE), R12-MED-3 fix

**운영 시나리오**: v0.1.0 운영 중 mount 가 간헐 fail (Restart=always 가 회복). 메인테이너가 SSH 접속 → `journalctl --user -u wikihub-mount@gdrive.service` 로 진단 → NOTICE level 이라 **fail 원인이 표시 안 됨** (rclone 의 retry/backoff INFO log 가 NOTICE 보다 verbose). 진단 정보 부족 상태로 escalation.

**문제**:
- v7 의 `--log-level INFO` 가 token 노출 위험 (R12-MED-3) 으로 NOTICE 로 낮춤. 정합. 그러나 **trouble-shooting 경로** 가 spec 에 부재:
  - mount.service.template 직접 편집 → `systemctl --user daemon-reload` → `systemctl --user restart wikihub-mount@gdrive` 사이클 (운영자 부담).
  - 또는 `RCLONE_LOG_LEVEL=DEBUG` env override — §10.4.1 line 1229 본문에 "운영자가 일시적으로 ... env 로 override 후 token 노출 가능성 인지 (운영 매뉴얼)" 명시 — **운영 매뉴얼 자체 미존재** (Q7 운영 매뉴얼이 v0.2.x deferred).
- 운영 매뉴얼 부재 + DEBUG override 경로 미spec → 메인테이너가 ad-hoc 으로 mount.service 편집 → 편집 후 install.sh 재실행 시 template 가 운영자 편집 덮어쓰기 (idempotent 의도) → 진단 중인 mount 가 NOTICE 로 회귀.
- v8 patch 의 fix 자체는 옳지만 **fix 의 운영 후속 비용** 미spec.

**제안**:
- §10.4.4 yaml 본문에 `operations.rclone_log_level: NOTICE` 추가 + substitution variable `{rclone_log_level}` 로 mount.service.template 의 `--log-level` 치환. 운영자가 yaml 편집 + `systemctl --user restart wikihub-mount@<vid>` 만으로 DEBUG 전환 가능. 진단 후 yaml 원복.
- §10.4.5 setup.md 또는 README 운영 진단 섹션에 DEBUG 절차 + token redaction 안내 (`journalctl --user --vacuum-time=1d` 또는 `--rotate`).
- §10.5 Q6 (rclone OAuth revoke 감지) 와 통합 — DEBUG 운영 시 OAuth error 패턴 검증 가능.
- **v0.1.0 release blocking 여부**: 메인테이너 1인 운영 가정 + Hermes 통제 가정에서 진단 latency 가 수 시간 가능 — release blocking 까지는 아니지만 v0.1.0 첫 incident 진단 시 surface.

**근거**:
- §10.4.1 line 1210 `--log-level NOTICE` (v8) + line 1229 "운영자가 일시적으로 RCLONE_LOG_LEVEL=DEBUG env 로 override 후 token 노출 가능성 인지 (운영 매뉴얼)" — 운영 매뉴얼 미존재.
- R12-MED-3 의 권고 line 316~321 — `rclone_log_level: INFO | DEBUG` yaml 옵션 추가. v8 patch 가 이 권고를 부분 채택 (NOTICE 로 fix) 했지만 yaml override 경로는 미반영.
- §10.5 Q7 v8 잠정 — "운영 매뉴얼" v0.2.x deferred. trouble-shooting 의존도 deferred.

---

### MED-R14-2: `vfs_refresh` 의 elapsed time logging 부재 — drift 진단 불가

**위치**: §10.4.6 `vfs_refresh` (line 1491~1509), V15-cost (v8 신규)

**운영 시나리오**: v0.1.0 launch 후 6개월. vault 가 1k → 7k 파일 증가. 사이클 latency 가 점차 증가 (refresh 비용 누적). 메인테이너가 사이클 timeout 빈도 증가 인지 → 진단:
- `journalctl --user -u wikihub-vault@gdrive.service --since "7 days ago"` → 사이클 elapsed 만 보임 (ExecStart 전체).
- `vfs_refresh` 자체의 elapsed 가 별도 logging 안 됨 → refresh 가 병목인지, gws changes 가 병목인지, ingest extraction 이 병목인지 분리 진단 불가.

**문제**:
- R12-HIGH-1 의 권고 (line 93~100) — `vfs_refresh` 호출에 elapsed time 로그 추가:
  ```python
  start = time.monotonic()
  result = subprocess.run(...)
  elapsed = time.monotonic() - start
  log.info("vfs_refresh: elapsed=%.1fs recursive=%s", elapsed, recursive)
  ```
- v8 patch 가 V15-cost (vault 1k/5k/10k latency 측정) 를 신설했지만 **운영 단계의 drift 진단** 은 미spec. V15-cost 는 Step 3 verification 1회 — 6개월 후 drift 추적은 별도 mechanism 필요.
- §10.4.6 의 `vfs_refresh` 본문 (line 1491~1509) 에 elapsed logging 미포함.

**제안**:
- §10.4.6 `vfs_refresh` 본문에 elapsed logging 추가 (R12-HIGH-1 권고 그대로):
  ```python
  import time
  start = time.monotonic()
  result = subprocess.run(...)
  elapsed = time.monotonic() - start
  log.info("vfs_refresh: vault_id=%s elapsed=%.1fs recursive=%s rc=%d",
           vault_id, elapsed, recursive, result.returncode)
  ```
- `assert_mount_alive` 도 동일 패턴 (HIGH-R14-3 의 큰 vault latency 진단 정합).
- §10.5 Q7 운영 매뉴얼 v0.2.x 와 연계 — 운영 매뉴얼에 "vfs_refresh elapsed > 30s 시 K2 마이그레이션 검토" 명시.
- §10.6.2 V15-cost 본문에 "본 측정은 Step 3 1회 — 운영 drift 는 elapsed logging 으로 추적" 명시.

**근거**:
- §10.4.6 line 1499~1509 `vfs_refresh` 본문 — elapsed logging 없음.
- R12-HIGH-1 권고 답습 회피 의무지만 v8 patch 가 권고를 일부만 (V15-cost) 채택. **logging 영역은 v8 patch 가 surface 안 한 채로 남음** → 본 라운드에서 별도 finding.

---

### MED-R14-3: `_handle_removed` unlink 제거 후 vfs cache 의 stale binary 잔존 가능성

**위치**: §10.4.3 sync.py patch (line 1306~1372), R11-CRIT-3 fix

**운영 시나리오**: 운영자가 Drive 에서 파일 `confidential.docx` 삭제 → 다음 사이클에서 gws changes 가 `removed` event 감지 → §10.4.3 step 4 `operation == "removed/trashed" → wiki page 삭제 + file_map 갱신. vault local unlink 안 함`. 그러나 mount FS 의 `--vfs-cache-mode full` 에서 이 파일은 **vfs cache 에 영속 저장** (이전 다운로드 시점) → vfs cache directory (`~/.cache/rclone/vfs/<remote>/<path>`) 에 binary 잔존.

**문제**:
- §10.4.3 line 1355 본문 "vault binary 미러 일관성은 mount FS 가 read-through 로 자동 보장 (Drive 에서 삭제된 파일은 vfs/refresh 후 mount 에서도 사라짐)" — mount path 에서의 가시성은 정합. 그러나 **vfs cache directory 자체의 잔존** 미spec.
- rclone `--vfs-cache-mode full` 의 의미: 모든 read 가 local cache 경유. 삭제된 파일은 mount path 에서 사라지지만 cache directory 의 binary 가 evict 되는 시점이 별개 — rclone 의 `--vfs-cache-max-age` (default 1h) 또는 size eviction (LRU).
- 결과:
  - vfs cache directory 가 `--vfs-cache-max-size 10G` 정책으로 LRU 운영 — Drive 에서 삭제된 파일이 LRU evict 안 되면 cache 잔존 가능.
  - **보안 시나리오**: 운영자가 `confidential.docx` 를 Drive 에서 삭제했으나 OCI 서버의 `~/.cache/rclone/vfs/gdrive/confidential.docx` 잔존 → OCI compromise 시 leak. v8 의 chmod 0600 (rclone.conf) 와 별개 — cache binary 의 permission 정책 미spec.
- mount FS 가 Drive 에서 삭제 알면 rclone 이 cache 도 자동 invalidate 하는지 — rclone docs 의 default 행동 확인 필요 (v0.1.0 spec 미언급).

**제안**:
- 옵션 (a) **`--vfs-cache-max-age` 단축**: §10.4.1 mount@.service.template 에 `--vfs-cache-max-age 4h` 명시 — 삭제된 파일이 4h 내 evict.
- 옵션 (b) **운영 매뉴얼 명시**: vfs cache directory 가 `~/.cache/rclone/vfs/<remote>/` 위치 — chmod 0700 enforce + boot 시 cleanup (`rclone cache clean` 명령).
- 옵션 (c) **`_handle_removed` 에 vfs cache forget 추가**:
  ```python
  # rclone rc vfs/forget file=<path> 호출 — 특정 path 의 cache invalidate
  subprocess.run(["rclone", "rc", "--rc-addr", rc_addr, "vfs/forget", f"file={path}"], ...)
  ```
- **권고**: 옵션 (a) + 옵션 (b) 결합. (c) 는 v0.1.0 minimal scope 초과.
- §10.5 Q10 신규 미결 항목: "vfs cache directory 의 stale binary 정책 — `--vfs-cache-max-age` default 결정 + cache directory permission".
- Step 3 V14(f) 신규: "Drive 삭제 후 24h 경과 시 vfs cache directory 의 binary 잔존 여부".

**근거**:
- §10.4.3 line 1355 "vault binary 미러 일관성은 mount FS 가 read-through 로 자동 보장" — cache directory 미spec.
- rclone docs `--vfs-cache-max-age`: default 1h0m0s. `--vfs-cache-mode full` 시 의미.
- §10.4.1 line 1206~1212 mount args — `--vfs-cache-max-size` 만 명시, `--vfs-cache-max-age` 미명시 (default 1h 의존).
- R12 의 14건 중 vfs cache directory permission/lifecycle 미커버 — R14 신규 영역.

---

### MED-R14-4: Q8 deferred 의 v0.1.0 silent stale 위험 — gws breaking change 의 release 후 첫 incident 가능성

**위치**: §10.5 Q8 v8 deferred (line 1577)

**운영 시나리오**: v0.1.0 launch 후 N주. gws 가 v0.7.0 → v0.8.0 minor 업데이트 (alpha — breaking change 가능). 메인테이너가 OCI 서버에서 `gws self-update` 또는 install.sh idempotent re-run → gws v0.8.0 자동 설치 (`operations.gws_min_version: 0.7.0` 통과). `gws drive changes list` 응답 schema 가 v0.8.0 에서 변경 (예: `kind` field 제거 + 새 field 도입). vault-fetch.py 의 parsing 이:
- 분기 (i): KeyError raise → VaultSyncFatal → last_failure → ops-alert (정상 감지).
- 분기 (ii): silent — gws 가 `[]` 빈 응답 반환 (downgrade graceful) → sync.py 가 "변경 없음" 인식 → cursor 진행 안 함 → 누적 stale.

**문제**:
- R12-MED-4 의 권고 (line 339~349): `sync.py` 의 changes.list 호출 직후 schema assert. v8 patch 가 이 권고를 **deferred** (Q8 v0.2.x). 임시 mitigation 으로 `operations.gws_min_version` + `gws_max_version` 추가.
- 그러나 `gws_max_version` 운영 효과:
  - install.sh 가 `_install_gws` 시점에 max version 초과 시 fail-fast — install 시점에는 mitigation.
  - **install 후 운영 중 `gws self-update` 또는 외부 apt source 로 gws 가 업데이트** 되면 install.sh 미경유 → max_version 검증 우회.
  - 사이클 runtime 에 gws version assert 부재 → silent stale 분기 (ii) 잔존.
- v8 patch 가 R12-MED-4 의 권고 답습 회피하면서 임시 mitigation 만 추가 — **v0.1.0 운영 중 surface 가능성** 잔존.
- 추가로 v0.1.0 release 후 gws v0.8.0 breaking 발생 시 `gws_max_version` 운영자 수동 갱신 필수 — Hermes 자동 운영 환경에서 운영자 부담 surface.

**제안**:
- 옵션 (a) **runtime version assert**: `scripts/lib/gws.py` 의 `run_gws` 첫 호출 시 `gws --version` 의 출력 확인 + `wikihub.yaml.operations.gws_min_version ≤ ver ≤ gws_max_version` runtime 검증 → 위반 시 VaultSyncFatal.
- 옵션 (b) **lightweight schema assert**: changes.list 응답의 필수 field 1~2개만 assert (`newStartPageToken` 또는 `kind`). v0.2.x 의 full schema validation 보다 cheap.
- 옵션 (c) **v0.1.0 release 후 incident 발생 시 hot fix release** — release blocking 아님 (현 v8 의 lock 유지).
- **권고**: 옵션 (b) — 30줄 미만 추가, runtime 첫 호출 시 한 번만 검증 (cache). v0.1.0 release blocking 아니지만 surgical addition 으로 deferred → addressed 전환 가치.
- Q8 본문에 "v0.1.0 임시 mitigation = `gws_max_version` 만으로는 install 후 silent upgrade catch 못 함 — runtime assert 권장 (opt-in)" 명시.

**근거**:
- §10.5 Q8 line 1577 — v0.2.x deferred. 임시 mitigation = `gws_max_version`.
- §10.4.4 line 1394 `gws_min_version: 0.7.0` — install.sh 시점 검증만.
- R12-MED-4 line 332~351 — runtime schema assert 권고. v8 이 deferred 처리.
- gws CLI alpha (v0.x) 의 breaking change 가능성 — ADR-0014 본문 명시.

---

## LOW

### LOW-R14-1: V14 hung mount 시뮬레이션 (`tc qdisc add dev eth0 root netem delay 30s`) 의 검증 환경 가정 불명확

**위치**: §10.6.2 V14 (line 1593), v8 patch (R12-CRIT-2 검증)

**운영 시나리오**: 메인테이너가 V14 검증 수행 — OCI ARM 서버에서 `tc qdisc add dev eth0 root netem delay 30s` 실행 → `assert_mount_alive` 가 5s 내 `VaultSyncRetryable` raise 확인.

**문제**:
- `tc qdisc` 는 **`CAP_NET_ADMIN` 필요** — OCI free tier ARM A1 의 default user (ubuntu) 가 sudo 통해 `tc` 호출 가능한지 확인 필요. 일반적으로 sudo 가능하지만 confirm 부재.
- 메인테이너 dev box (macOS) 에서는 `tc` 미존재 — V14 의 (b) hung mount 시뮬레이션 검증을 macOS 에서 못 함. OCI server 에서만 가능 → 검증 cycle 시간 증가.
- 더 안전한 대안 — Drive API 자체 변조 없이 hung 시뮬레이션:
  - (i) `iptables -A OUTPUT -p tcp --dport 443 -j DROP` 후 검증 (R12-CRIT-2 권고 line 67).
  - (ii) rclone mount 의 `--vfs-read-chunk-size` 를 1KB 로 낮춰 큰 파일 read 시 인공적으로 느려지게.
  - (iii) network namespace 격리 후 outbound 차단.
- §10.6.2 V14 본문이 `tc qdisc` 만 명시 — 대안 미명시. 메인테이너가 검증 차단 시 fallback 부재.

**제안**:
- §10.6.2 V14 본문에 환경 가정 + 대안 명시:
  ```
  V14 (b) — hung mount 시뮬레이션:
    환경: OCI ARM Ubuntu 22.04, sudo 사용 가능.
    1차: tc qdisc add dev eth0 root netem delay 30s (sudo)
    대안: iptables -A OUTPUT -p tcp --dport 443 -j DROP (network 차단)
    macOS dev box 에서는 micro test 만 가능 (subprocess timeout 단위 테스트) — 실 hung 검증은 OCI 에서만.
  ```
- §10.5 Q5 운영 매뉴얼에 V14 절차 명시 — 운영 환경에서 hung mount 재현 시 운영자가 따라할 수 있도록.

**근거**:
- §10.6.2 V14 line 1593 `tc qdisc add dev eth0 root netem delay 30s` — 환경 가정 미명시.
- R12-CRIT-2 권고 line 67~68 — iptables 대안 명시. v8 patch 가 tc 채택 (대안 인지 부재).
- OCI ARM A1 free tier docs — sudo 권한 가정 (확인 필요).

---

### LOW-R14-2: V15-cost 의 10k 파일 60s 임계 근거 부재 — TimeoutStartSec 안전 여유 계산 미spec

**위치**: §10.6.2 V15-cost (line 1595), v8 신규

**운영 시나리오**: V15-cost 검증 결과 — 10k 파일 vault 에서 `vfs/refresh recursive=true` 가 평균 65s. v8 본문 "60s 초과 시 K2 마이그레이션 검토" → 65s 가 K2 trigger.

**문제**:
- §10.6.2 V15-cost 본문 "10k 파일에서 응답 < 60s 이면 vault@.service `TimeoutStartSec=15min` 안전 한도" — 60s 임계 근거 부재. 계산:
  - `TimeoutStartSec=15min = 900s`.
  - 사이클 구성: `assert_mount_alive` (~1s) + `vfs_refresh` (X s) + `gws drive changes list` (5~30s, vault 크기 의존) + per-file `_read_from_mount` (file 수 * 평균 read time) + extraction + write.
  - vfs_refresh 60s 면 사이클 잔여 840s — 충분. 그러나 vault 가 10k 면 changes list 도 큰 부담 + per-file read 가 누적.
- 60s 가 어디서 왔는지 — 보수적이지만 임계 근거 미spec.
- 더 나쁜 케이스: 60s 임계 통과해도 사이클 전체가 900s 도달 → SIGTERM → 다음 사이클 retry → cumulative latency.

**제안**:
- §10.6.2 V15-cost 본문에 임계 산정 근거 추가:
  ```
  60s 임계 근거: TimeoutStartSec=15min(900s) 의 7% (60/900).
  사이클 잔여 = 900 - assert_mount_alive(1s) - vfs_refresh(X) - gws_changes(30s) - read_loop(N * 0.5s) - extraction
  N=10k, vfs_refresh=60s 시 잔여 = 900 - 1 - 60 - 30 - 5000 = -4191 → 사이클 자체 불가능.
  따라서 실제 안전 임계는 vault 크기 + per-file read time 의존 — V15-cost 가 측정해야 할 항목.
  v0.1.0 default: 60s (보수). 측정 후 yaml `vfs_refresh_timeout_sec` 로 운영자 override.
  ```
- §10.5 Q4 (vfs_refresh 실패 fallback) v8 lock 본문에 "60s 도달 시 K2 (per-file refresh) 자동 migration 또는 yaml override" 명시.
- v0.1.0 vault 평균 파일 수 추정 부재 — F4 plan.md 의 운영 환경 가정에 "v0.1.0 vault 평균 파일 수 < 1k" 명시 권고 (V15-cost 의 10k 가 stretch goal).

**근거**:
- §10.6.2 V15-cost line 1595 — 60s 임계 산정 근거 미spec.
- §10.4.7 `TimeoutStartSec=15min` — 사이클 전체 한도.
- §10.4.6 vfs_refresh `timeout_sec=120` line 1491 — refresh 자체 timeout 120s. 60s 임계와 불일치 (120s 면 K2 trigger 안 함).

---

## NIT

### NIT-R14-1: v8 patch 본문이 v8 마커 (R12-XXX) 표기 + v8 patch 마커 (`v8 (R12-XXX)`) 가 line-level 에서 dense — 가독성 회귀

**위치**: §10.4.1 (line 1189~1232), §10.4.2 (line 1236~1304), §10.4.3 (line 1308~1372), §10.4.6 (line 1445~1516), §10.4.7 (line 1520~1564)

**문제**: v8 patch 가 31건의 patch 마커 (`v8 (R11-XXX)`, `v8 (R12-XXX)`) 를 본문에 inline 표기 → 본문이 patch history 와 spec 정본이 섞임. 향후 v9 patch 시 마커가 누적 → 가독성 추가 회귀.

**제안**:
- v8 approve 직후 (Step 3 진입 전) **patch 마커 normalize**: 본문에서 inline 마커 제거 + 별도 §10.9 (v7→v8 change log) 섹션에 일괄 기록.
- 또는 patch 마커는 git commit message + analysis_and_design.md 상단 changelog 에서만 참조 — spec 정본에는 미수록.
- ADR-0024 의 R10 마커 pattern 참조 — ADR 본문은 정본만, change log 는 별도.

**근거**:
- §10.4.1 ~ §10.4.7 의 31건 patch 마커 — spec 정본과 history 혼합.
- ADR template (`docs/adr/template.md`) — patch history 미표기 패턴.
- §10.6.2 V15 "(v8 R11-LOW-1)" + "(v8 R12-NIT)" 등 — Step 3 verification 본문에 patch history 노출.

---

## 결론

### 본 라운드 결함의 운영 영향도

v8 patch 는 R11/R12 의 27건 finding 을 surgical 처리했지만, **fix 자체가 새 운영 위험을 surface**:

1. **`OnFailure=ops-alert.service` 추가가 dual-edge** (CRIT-R14-1, HIGH-R14-4): R12-CRIT-1 의 silent dead 차단 의도가 매 fail cycle 마다 ops-alert.py trigger 양산 + last_failure writer 부재로 webhook 0건 잔존. CRIT-R14-1 의 alarm fatigue + HIGH-R14-4 의 mount permanently failed silent 가 동일 producer 부재 root cause.
2. **fix 의 비용 회귀** (HIGH-R14-3, HIGH-R14-1): `os.statvfs` → `ls -la` 가 entry 비례 비용 + GitHub Releases 단일 채널 의존이 가용성 회귀.
3. **operational governance 부재** (MED-R14-1, MED-R14-2, MED-R14-3, MED-R14-4): NOTICE level + vfs cache directory permission + vfs_refresh elapsed logging + gws schema runtime assert 등 4개 영역이 v8 patch 의 fix 후 운영 매뉴얼/spec 으로만 cover 가능한데 매뉴얼 자체가 v0.2.x deferred.

### v0.1.0 release blocking 분류

**release blocking (Step 2 v8 → v9 surgical patch 또는 Step 3 V<N> 보강 필수)**:
- **CRIT-R14-1**: mount@ OnFailure 매 cycle alarm fatigue + last_failure writer 부재 → v9 patch (mount-fail-recorder.service 신설 또는 OnFailure 제거 후 ExecStopPost 기반 dedup).
- **HIGH-R14-1**: GitHub Releases 단일 채널 — v9 patch (error 진단 메시지 분리 + v0.2.x fallback 채널 명시).
- **HIGH-R14-2**: `_check_rc_port_available` user namespace 가정 — v9 patch (가정 명시 + mount.service ExecStartPre 보완).
- **HIGH-R14-3**: `ls -la` 의 entry 비례 비용 — v9 patch (`stat -f` 로 교체) + V14(d) 신규.
- **HIGH-R14-4**: mount permanently failed silent — CRIT-R14-1 와 통합 v9 patch (mount-fail-recorder 또는 systemctl is-failed assert) + V14(e) 신규.

위 5건 중 CRIT-R14-1 + HIGH-R14-4 가 ADR-0024 (fatal alert contract) 의 invariant 직접 위반 — release blocking 우선순위 최고. HIGH-R14-3 은 acceptance 의 timeout=5s 가정과 직접 충돌.

**v0.2.x deferred 적정 (운영 매뉴얼 또는 후속 feature)**:
- MED-R14-1 (NOTICE → DEBUG yaml override 경로) — Q7 운영 매뉴얼 통합.
- MED-R14-2 (vfs_refresh elapsed logging) — V15-cost 의 runtime drift 추적 mechanism.
- MED-R14-3 (vfs cache directory stale binary) — Q10 신규 미결 추가.
- MED-R14-4 (gws schema runtime assert) — Q8 v0.2.x 권고에 runtime assert 권고 추가.
- LOW-R14-1 (V14 tc qdisc 환경 가정) — V14 본문 보강.
- LOW-R14-2 (V15-cost 60s 임계 근거) — V15-cost 본문 보강.

**NIT**:
- NIT-R14-1 (patch 마커 가독성 회귀) — v8 approve 직후 normalize.

### 권고 — v9 surgical patch 진입

v8 patch 가 R11/R12 의 27건을 처리했지만, **fix 의 부작용 (operational regression) 이 새로 5건 surface**. CRIT-R14-1 + HIGH-R14-1~4 (총 5건 release blocking) 을 v9 surgical patch 로 처리 후 Step 2 approved 권고. 핵심:

1. **mount-fail-recorder.service 신설** — `_state/<vault_id>/mount_failure.json` producer + StartLimitBurst 도달 시에만 `last_failure.json` 쓰기. CRIT-R14-1 + HIGH-R14-4 동시 해소.
2. **`assert_mount_alive` 의 `ls -la` → `stat -f` 교체** — entry 비례 비용 회피.
3. **install.sh error 진단 분리** — SHA file 404 vs hash 불일치 별도 메시지.
4. **`_check_rc_port_available` 가정 명시 + mount.service ExecStartPre 보완**.

v0.2.x deferred 6건 (MED 4건 + LOW 2건) 은 §10.5 Q 표에 Q10~Q13 신규 행 + 운영 매뉴얼 (Q7 통합) 으로 추적. NIT 1건 (patch 마커 normalize) 은 Step 2 v8 approve 직후 cleanup.

v8 patch 의 spec 145줄 추가는 R11/R12 권고 적용 측면에서는 적절하지만, **surgical fix 의 운영 부작용** 측면에서 v9 patch 필요. ADR cascade 없음 (ADR-0021 의 acceptance invariant 본문은 mount permanently failed escalation 명시 추가 필요할 수 있으나, mount-fail-recorder 가 acceptance invariant 유지하면 ADR 변경 불필요).
