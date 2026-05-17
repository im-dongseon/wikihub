# Step 4 R16 — general-purpose SRE

**리뷰어**: claude (general-purpose subagent — SRE 관점)
**범위**: F4 install_runtime feature 의 V<N> Phase 2 fix 9건 + 운영 reliability (supply chain, 장애 격리, observability, fix-induced regression, update 시나리오)
**일자**: 2026-05-17
**Internal consistency 는 R15 별도 담당** — 본 라운드는 운영 reliability 측면만.

---

## CRIT (반드시 fix)

**(없음)**

V<N> Phase 2 11건 acceptance gate 통과 + 9건 fix 정본화 후 코드를 정밀 점검한 결과, **운영 사이클을 중단시키거나 데이터 손실을 일으킬 수준의 결함은 surface 되지 않음**. 아래 HIGH/MED 는 모두 "추가 운영 견고화" 권고 — v0.1.0 Step 5 배포 전 fix 권장이지만 release blocker 아님.

---

## HIGH (fix 권장)

### HIGH-1. `install.sh:448` `RCLONE_MIN_VERSION` dead variable — pinned-only 정책 위반 시 detection 부재

**위치**: `/Users/ds.im/workspace/repo/wikihub/install.sh:447-460` `_install_rclone`.

**현상**: `local min_version="${RCLONE_MIN_VERSION:-1.65.0}"` 가 정의되나 함수 본문에서 reference 안 됨. 기존 설치 detection 분기 (`if [[ "$current" == "$pinned" ]]; then skip`) 는 **string equality** 만 검사 — 운영자가 수동으로 newer rclone (e.g. `1.70.0`) 을 깔아둔 경우에도 자동 downgrade 가 일어남.

**SRE 영향**:
- pinned=1.69.1 보다 newer 가 깔린 환경에서 `install.sh` re-run 시 silent downgrade. 운영자 관점에서 의도치 않은 회귀.
- `config.py` 의 `rclone_min_version=1.65.0, rclone_max_version=1.99.99` 도 어디서도 enforce 되지 않음 (dead config). `mount.py:assert_mount_alive` / `vault-fetch.py` 모두 rclone version 검사 안 함.

**권고**:
1. `min_version` 변수 제거 (dead code) 또는 detection 분기 수정 — `current >= min_version && current <= max_version` 이면 skip, 외 재설치. semantic compare 가 부담스러우면 v0.2.x 로 명시 lift.
2. `_install_rclone` 진입 시 `current` 값을 stdout 로 명시 출력 ("rclone 1.70.0 detected — pinned=1.69.1 와 다름, 재설치"). 현재는 info 한 줄이지만 운영자 confusion 회피용으로 stronger 권고 OK.
3. config 의 `rclone_min/max_version` 을 mount.py 또는 install.sh 에서 enforce 하거나, config schema 에서 제거. **dead config 가 정본에 남아 있으면 운영자가 yaml 편집해도 무효**.

ADR-0025 (`rclone-mount-runtime`) 의 D? 결정에 pinned-only vs semver-range 가 명시돼 있는지 R15 와 분담 검증 필요.

### HIGH-2. `install.sh:447, 467` rclone pinned 버전 (`1.69.1`) 의 SHA256 verify 가 사실상 only-source-of-trust — known-good baseline 부재

**위치**: `install.sh:472-475`.

**현상**: rclone SHA256SUMS 는 같은 GitHub Release 디렉토리에서 다운로드. 공급망 공격자가 release artifact 전체를 교체하면 SHA256SUMS 도 함께 교체 가능 — sha256 verify 가 **transport tamper** 만 차단하지 **release-time supply chain compromise** 는 차단 못 함. GPG signature 검증 또는 hardcoded SHA256 (in repo) 가 부재.

**SRE 영향**: GitHub 계정 takeover / release replacement 시 OCI 서버가 자동 install. v0.1.0 시점에 즉시 fix 는 과한 부담이나, 운영 spec 에 "v0.2.x 에서 hardcoded SHA256 / GPG verify 강화 예정" 명시 권고.

**권고**: analysis_and_design.md §4.5 (rclone install) 또는 ADR-0025 §Consequences 에 **공급망 위협 잔존 + v0.2.x deferred** 명시. 동일 위협이 gws (`install.sh:355`) · uv (`install.sh:235`) 에도 존재 (gws/uv 는 sha256 sidecar 부재 시 TLS-only fallback 까지 허용 — 더 약함). 본 리뷰의 MED-2 와 짝.

### HIGH-3. `mount.py:227, 225` `_RCLONE_AUTH_PATTERNS.search(error_full)` — truncate 제거 후 stderr 가 매우 큰 경우 latency spike

**위치**: `/Users/ds.im/workspace/repo/wikihub/scripts/lib/mount.py:225-227`.

**현상**: V18 결함 #6 fix 보강 (`2d10cd4`) 으로 `error_full` 의 `[:500]` truncate 제거됨 — Drive API URL 의 `fields` 파라미터 250+ char 로 핵심 키워드 (`private key should be`) 가 잘리는 case 회피 목적. 정합한 fix.

**잔존 risk**:
- `error_full = result.stderr or rc_error_msg`. `result.stderr` 는 rclone subprocess stderr 전체 — `subprocess.run(capture_output=True)` 에서 buffer 제한 없음. mount daemon 이 long-running 중에 ERROR 가 누적 + `--log-level NOTICE` 라도 burst 에러 시 수 MB 가능.
- `_RCLONE_AUTH_PATTERNS` 의 패턴 중 `oauth2.*invalid`, `service account.*disabled`, `key.*disabled`, `no such file or directory.*sa_` 는 `.*` greedy. Python `re` 는 alternation backtracking 이 catastrophic 까지는 아니지만 (linear-ish), 수 MB stderr 에 `re.IGNORECASE | re.DOTALL` 아님 (DOTALL 부재) 라 newline 마다 reset 되어 사실상 linear. **catastrophic ReDoS risk 는 낮음**.
- 단 `re.search` 자체가 수 MB 전체 스캔 → 100ms~수백ms latency. `vfs_refresh` 의 timeout=120s 안에는 들어가나 vault@.service `TimeoutStartSec=15min` 의 다른 step 과 합쳐서 사이클 지연 가능.

**권고**:
- truncate 완전 제거는 결함 #6 fix 의 정당화된 결정 — 회귀 시키지 말 것.
- 대신 **regex pre-scan size cap** 도입: `error_full` 길이가 예: 1MB 초과 시 마지막 100KB 만 search (rclone error 는 보통 stderr 끝에 출력). 현재 `error_snippet = error_full[:500]` 은 reason 메시지용이라 별도 변수로 분리.
- 또는 패턴 안의 `.*` 를 `[^\n]*` 로 제한 (newline 안 가로지름 — auth error 는 한 줄 메시지) — 안전 + 빠름.

```python
# 권고 예시 — 라인 단위 search 로 backtracking 자체 차단
error_full = result.stderr or rc_error_msg
# 1MB 초과 시 끝에서 100KB 만 — rclone error 는 stderr 끝에 출력
search_target = error_full[-102400:] if len(error_full) > 1048576 else error_full
if _RCLONE_AUTH_PATTERNS.search(search_target):
    ...
```

### HIGH-4. `sync.py:288-304` 결함 #9 fix 의 `_source_relpath` 변경 — incremental sync 시 `name` change 가 fileId 추적 깨짐

**위치**: `/Users/ds.im/workspace/repo/wikihub/scripts/lib/sync.py:288-304`, `sync.py:534-546` (`_handle_removed`), `sync.py:675` (`operation` 결정).

**현상**: 결함 #9 fix 는 Google native 파일의 `_source_relpath` 가 mimeType 기반 확장자 (`.docx`/`.xlsx`/`.pptx`) 를 자동 추가. 그러나:

1. `file_map["files"]` 의 key 는 `source_relpath` (name 기반) — `fileId` 가 아님.
2. `_handle_removed` 는 `next((p for p, v in file_map["files"].items() if v.get("source_id") == file_id), None)` 로 source_id 역방향 lookup — OK.
3. **그러나 `operation = "modified" if source_relpath in file_map["files"] else "created"`** (sync.py:675) — 같은 fileId 의 `name` 이 Drive 측에서 변경되면 `source_relpath` 가 달라져서 **기존 entry (old name) 와 mismatch → "created" 오분류 + 기존 wiki page leak (orphan)**.

**예시**:
- T0: bootstrap. `file_map["files"]["test.docx"] = {source_id: "abc"}`. wiki page = `wiki/sources/v/test.docx.gdoc.md` (실제 mime 매핑 따라).
- T1: 운영자가 Drive 에서 `test` → `test-renamed` rename. mount 의 export 도 `test-renamed.docx`.
- T2: incremental cycle. `changes.list` 가 fileId=abc + name=`test-renamed` 반환.
- T3: `_source_relpath` = `test-renamed.docx`. `file_map["files"]` 의 키 `test.docx` 와 mismatch → `operation="created"`. `file_map["files"]["test-renamed.docx"]` 신규 추가. **기존 `test.docx` entry 는 그대로 leak** — orphan wiki page + state 폭증.

**SRE 영향**:
- Drive 에서 자주 rename 하는 vault 의 `file_map` 이 무한 누적. 100 파일 vault 에서 평균 5회 rename 시 1년 후 500+ orphan entries.
- wiki/sources 디렉토리에도 orphan markdown 누적 — 검색 결과에 stale content 포함.
- V15 (rename mechanism) 은 통과했으나 file_map 정합성까지 검증한 것 아닌 듯 (progress.md:263 의 V15 설명 — content 정합만 확인).

**권고** (v0.2.x 또는 v0.1.x patch):
- `file_map` 의 primary key 를 `source_id` (fileId) 로 변경 → `source_relpath` 는 value 의 한 필드. 단 schema breaking — F5/F2 의 wiki-schema.md 도 동시 변경 필요.
- 또는 minimum fix: `_sync_loop` 에서 fileId 기반 lookup 추가 — 동일 source_id 의 기존 entry 가 다른 source_relpath 로 존재하면 (a) 기존 entry 삭제 + wiki page rename, (b) 새 entry 추가, (c) `operation="modified"`.
- 본 결함은 R15 (internal consistency) 가 잡지 못할 cross-cutting issue — bootstrap/incremental + state schema + extraction dispatch 가 얽혀 있음. **별도 feature 권장 + V<N> Phase 2 결함 #11 으로 surface 권고**.

### HIGH-5. `wikihub-mount@.service.template:14, 24` `ExecStartPre=-/bin/fusermount3 -u` 의 `-` prefix — mount busy/in-use 시 silent skip → restart loop 재발 가능

**위치**: `/Users/ds.im/workspace/repo/wikihub/_system/systemd/wikihub-mount@.service.template:14`.

**현상**: 결함 #5 fix 로 `ExecStartPre=-/bin/fusermount3 -u {mount_path}` 추가됨. `-` prefix 가 exit code 무시 — stale FUSE entry 의 `Transport endpoint is not connected` 결함 차단 목적. 정합한 fix.

**잔존 risk**:
- `fusermount3 -u` 가 fail 하는 경우는 두 가지: (a) mount 안 됨 (no-op, 정상), (b) **다른 process 가 mount path 안에 cwd 또는 open file 보유 — "Device or resource busy"**. (b) 는 `-` prefix 로 무시되지만 후속 `mkdir -p` 가 fail (이미 stale entry 존재) → restart loop 재발.
- v0.1.0 의 vault@.service 가 mount path 하위에 cwd 두지 않으므로 (b) 빈도 낮음. 단 운영자가 mount path 안에서 `ls`/`du` 등 진단 중인 케이스 — drill 시 hung.

**권고**:
- `ExecStartPre=-/bin/fusermount3 -u -z` (`-z` lazy unmount) 로 강화. busy 시에도 lazy detach + 새 mount 가능. fusermount3 의 `-z` 는 systemd 환경에서 안전 (kernel 측 lazy unmount).
- 또는 `ExecStop` 도 `-z` 추가 (대칭성). 현재 `ExecStop=/bin/fusermount3 -u` 는 prefix 없음 — service stop 시 busy 면 fail 후 sigterm/sigkill 의존.

---

## MED (선택)

### MED-1. `ops-alert.service:9, 19` `TimeoutStartSec=30s` — `collect_mount_fallback_failures` 가 5+ vault 시 timeout risk

**위치**: `/Users/ds.im/workspace/repo/wikihub/_system/systemd/ops-alert.service:18`, `/Users/ds.im/workspace/repo/wikihub/scripts/ops-alert.py:107-117`.

**현상**:
- `collect_mount_fallback_failures` 가 vault 마다 `systemctl is-failed` (timeout=5s) + `journalctl -u` (timeout=10s). N vault 시 최악 N*15s.
- 5 vault 일 때 75s → service `TimeoutStartSec=30s` 초과 가능. mount@ permanently failed 가 동시에 여러 vault 면 ops-alert 자체가 timeout fail → `StartLimitBurst=3/300s` 카운트 소진 → **3회 fail 후 ops-alert silent — fatal 누락**.

**권고**:
- vault 별 timeout 합산이 `TimeoutStartSec` 보다 작아야 함. 옵션:
  1. `TimeoutStartSec=180s` 로 상향 (5 vault * 30s + 여유).
  2. `collect_mount_fallback_failures` 의 vault 루프를 concurrent.futures.ThreadPoolExecutor 로 parallel — 가벼운 변경.
  3. 각 vault 의 `journalctl` timeout 을 10s → 3s 로 단축 (tail -n 100 은 빠름).
- 운영 vault count 가 v0.1.0 에서 보통 1~2 라 즉시 hit 안 함 — Operator Guide 의 spec 한 줄로 충분.

### MED-2. uv install (`install.sh:235-278`) — `.sha256` sidecar 부재 시 TLS-only fallback 허용

**위치**: `install.sh:252-256`.

**현상**:
```bash
if _curl_with_retry "${url}.sha256" "$tmpdir/${asset}.sha256" 2>/dev/null; then
    ( cd "$tmpdir" && sha256sum -c "${asset}.sha256" )
else
    warn "uv sha256 sidecar 없음 — TLS 만으로 verify"
fi
```

astral-sh/uv 의 release 형식은 실제로 `uv-${triple}.tar.gz.sha256` 가 아닌 SHA256SUMS 단일 파일로 묶여 있을 가능성 — 첫 install 시 sidecar 미발견 → **TLS-only 통과**. gws 도 같은 패턴 (`install.sh:361-365`).

**SRE 영향**: HIGH-2 와 같은 위협 — supply chain compromise 시 verification skip.

**권고**:
- uv 의 정확한 sidecar 명명 확인 (실제 release URL 검증) + 분기 수정.
- 또는 sidecar 부재 시 fatal exit + 운영자에게 "v0.1.0 SHA256 sidecar 부재" 명시 안내 (TLS-only fallback 제거). pinned 버전 정책이라 sidecar 명명만 정정하면 됨.
- v0.2.x 에서 rclone 처럼 SHA256SUMS aggregate file 처리 path 추가.

### MED-3. `mount.py:212` `rc_response.get("result", {}).get("", "")` — rclone rc API 응답 schema 변경 시 silent return → backend error 잠재 누락

**위치**: `/Users/ds.im/workspace/repo/wikihub/scripts/lib/mount.py:209-219`.

**현상**: V18 결함 #6 fix 로 rclone `vfs/refresh` rc API 의 backend error 가 응답 JSON 의 `result.""` (빈 문자열 key) 에 들어오는 case 처리. 단:
- rclone 1.69.1 가 정본인데 1.70+ 에서 response schema 변경 시 (e.g. `result.error`, `result.errors[]`) silent return → backend error 미감지.
- HIGH-1 의 dead version check 와 합쳐서 — rclone 자동 newer install 시 schema 변경 + silent error 가능.

**권고**:
- `rc_response.get("result", {})` 가 dict 일 때 빈 키 외에도 `error`, `errors`, `failed` 등 키 추가 검사. 또는 unknown 키 발견 시 warn log.
- rclone version 을 launch 직후 1회 로깅 (`rclone version` subprocess) — schema 변경 detect 용 forensic data.
- v0.2.x 에서 rclone version 정합성 check 를 mount.py 진입 시 1회 수행.

### MED-4. `ops-alert.py:178` socket-level `setdefaulttimeout` race — process-wide side effect

**위치**: `/Users/ds.im/workspace/repo/wikihub/scripts/ops-alert.py:165-181`.

**현상**: `socket.setdefaulttimeout(timeout_sec)` 는 process global. ops-alert.py 가 single-shot Type=oneshot 이라 영향 없으나, 만약 향후 long-running mode 로 전환 시 다른 socket 호출에 부작용. finally 의 `setdefaulttimeout(None)` 으로 복원하지만 동시에 다른 thread 가 socket 호출 시 race.

**권고**: 현 시점 issue 없음. v0.2.x F5 (Hermes 통합) 에서 ops-alert.py 가 long-running 으로 전환된다면 `socket.setdefaulttimeout` 패턴 제거 + `urlopen(timeout=...)` 만 사용 (이미 적용됨 — line 175 `urlopen(req, timeout=timeout_sec)`).

### MED-5. `wikihub-vault@.timer.template:11` `OnUnitInactiveSec={sync_interval_sec}s` — sync_interval_sec 미설정/극소 값 시 hot loop

**위치**: `/Users/ds.im/workspace/repo/wikihub/_system/systemd/wikihub-vault@.timer.template:11`.

**현상**: deploy.sh / setup.md 가 `{sync_interval_sec}` substitution. 운영자가 yaml 에 `sync_interval_sec=5` 처럼 극소 값 설정 시 — 5초마다 vault@ fire → Drive API quota 폭주 + ops-alert 후속 알림 burst.

**권고**: `config.py:load_wikihub_yaml` 에서 `sync_interval_sec` 의 lower bound (예: 60s) enforce. 현재 schema 에서 validation 없음 — `OperationsConfig` 확인 필요.

### MED-6. `last_failure.json schema` 의 `scope` 필드 — Operator Guide 에서 가시화 부재

**위치**: `last_failure.json` schema (vault_id, severity, scope, reason, remediation, failed_count, alerted_at).

**현상**: ADR-0024 v9 + V<N> 결함 #7 fix 로 `scope` 필드 ("vault" vs "mount") 추가됨. 정합한 fix. 단:
- `vault-fetch.py:174` 는 `getattr(e, "scope", "vault")` — `VaultSyncFatal` 외 다른 exception 의 fatal path (예: `except Exception as e: return 2` at line 184) 는 last_failure.json 자체 작성 안 함. ops-alert 가 fallback diagnostic 발화 — OK.
- 운영자가 `cat _state/<vault>/last_failure.json | jq .scope` 로 본 후 `mount` 인지 `vault` 인지 알 수 있어야 진단 효율 — install.sh:653 `_step8_guide` 의 운영 진단 명령에 `last_failure.json` 가시화 명령 미포함.

**권고**: `_step8_guide` 의 "운영 진단 명령" 섹션에 다음 한 줄 추가:
```
  last_failure 요약: for s in $WIKIHUB_INSTANCE_ROOT/_state/*/last_failure.json; do echo "─ $s"; jq -C . "$s"; done
```
또는 setup.md 에 진단 cheatsheet 별도 정리.

### MED-7. install.sh `_step3_venv` 의 `uv pip install --quiet` — supply chain attack visibility 저하

**위치**: `install.sh:305`.

**현상**: `uv pip install --quiet -r "$req_file"` 의 `--quiet` 가 의존성 install 시 어떤 패키지가 어떤 버전으로 설치됐는지 stdout 출력 안 함. install.log 에 mirror 되더라도 운영자 확인 어려움. `scripts/requirements.txt` 에 pin 안 된 패키지가 있으면 transitive deps 가 매번 다른 버전.

**권고**:
- `--quiet` 제거 또는 `-v` 한 단계 (verbose=1). install.log 가 의존성 trace 보존.
- 별도로 `scripts/requirements.txt` 가 `==` pinned 인지 R15 와 분담 검증 (`requirements.txt` 의 정합성).

---

## LOW (참고)

### LOW-1. `mount.py:248` `error_snippet[:200]` — log line 의 `repr` quote 가 escape char 포함 시 가독성 낮음

`reason=f"... {error_snippet[:200]!r}"` — `!r` 의 backslash escape 가 stderr 의 raw newline/utf-8 한글 메시지에서 `\x...` 로 보일 수 있음. 운영자 grep 시 keyword 매칭 안 됨. `!r` → `!s` + 별도 newline strip 권고.

### LOW-2. `install.sh:67` `exec > >(tee -a "$INSTALL_LOG") 2>&1` — install.log 의 rotation 없음

OCI ARM small instance 에서 install.sh 반복 호출 (update 시나리오 — progress.md:#B 별도 feature) 시 install.log 무한 누적. `logrotate` 또는 install.sh 진입 시 `> /dev/null` truncate 권고. v0.2.x 별도 feature 의 update_mode 와 함께 처리.

### LOW-3. `wikihub-mount@.service.template:21` `--log-level NOTICE` — ADR-0025 R12-MED-3 token redaction 정합

NOTICE level 은 OAuth/SA token URL parameter 노출 위험을 회피한 정합 결정. 단 운영자가 `RCLONE_LOG_LEVEL=DEBUG` override 시 token 누출. systemd `Environment=RCLONE_LOG_LEVEL=DEBUG` 일시 override 후 원복 빠뜨릴 risk — `_step8_guide` 의 trouble-shoot 가이드에 "DEBUG 사용 후 즉시 NOTICE 환원" 명시 권고.

### LOW-4. `vault-fetch.py:131` `fcntl.flock` lock 의 stale lock 처리 — process kill -9 시 lock 해제는 OS 자동이지만 NFS mount 시 미보장

`state_dir/.lock` 이 NFS 등 network FS 에 있을 가능성 (instance_root 가 cloud-init customizable). v0.1.0 OCI ARM 은 local disk 가정이라 issue 없음. v0.2.x distributed 시 namespace.

### LOW-5. `sync.py:573-581` SA credentials JSON load 시 fail-silent — credentials.py 가 이미 검증한다는 가정

```python
try:
    with open(credentials_path) as f:
        creds_type = json.load(f).get("type", "")
    if creds_type == "service_account" and exclude_swm:
        exclude_swm = False
except (OSError, json.JSONDecodeError):
    pass
```

credentials.py 의 `assert_credentials` 가 이미 호출됐다는 가정 정합 — but 함수 순서 의존성이 vault-fetch.py 의 control flow (line 99 `assert_credentials` 후 line 140 `sync()` 호출) 에 잠재됨. 직접 sync() unit test 시 SA override 가 silent skip 됨. 보호적 코딩 — vault-fetch.py 와 sync() 모듈 경계에 명시적 invariant comment 추가 권고.

### LOW-6. `ops-alert.py:230-233` `instance_label or socket.gethostname()` — hostname fallback 의 leak

OCI internal hostname (예: `inst-2x4-arm-ubuntu`) 이 webhook payload 에 노출. 외부 SaaS 가 Slack 등이면 acceptable. 단 R10 MED-3 fix 가 이미 명시한대로 운영자가 `instance_label` 명시 권장 — Operator Guide 의 wikihub.yaml.example 에 placeholder 추가 (해당 시 별도 분리).

---

## 통과 항목 (운영 안정성 정합 확인)

### 장애 격리 (Failure Isolation)

- ✅ **mount@ permanently failed → vault@ trigger cancel + mount@ OnFailure escalation (layer 2)**: `wikihub-vault@.service.template:5 Requires=wikihub-mount@%i.service` + `wikihub-mount@.service.template:7 OnFailure=ops-alert.service` — `Requires=` 의 stop propagation + OnFailure 2-layer 메커니즘 정합. systemd semantics 정합.
- ✅ **vault@ Retryable (exit 75) → SuccessExitStatus 로 success 분류**: `wikihub-vault@.service.template:20 SuccessExitStatus=0 75` — ops-alert 오발화 차단. timer 의 OnUnitInactiveSec 자연 재시도. `mount.py:MOUNT_RETRYABLE_FATAL_THRESHOLD=6` 약 1시간 임계 — 적정.
- ✅ **ops-alert recursion 차단**: `ops-alert.service:5-6 StartLimitBurst=3/300s` + `OnFailure 미설정` + `RemainAfterExit=no` + `ops-alert.py:276 return 0 always`. 4중 안전망. **CRIT-1 fix (R10) 의 4가지 메커니즘 모두 코드에 반영됨**.
- ✅ **last_failure.json scope="mount" vs "vault" 정합**: `mount.py:138, 250` 명시 `scope="mount"` raise + `vault-fetch.py:174 getattr(e, "scope", "vault")` fallback. 결함 #7 fix 완성. ops-alert 의 `collect_mount_fallback_failures` 가 last_failure 부재 시 보완 — diagnostic completeness 보장.
- ✅ **vfs_refresh fail vs mount permanently failed 두 layer**: `vault-fetch.py:118 assert_mount_alive` (layer 1: stat-based liveness) → `vfs_refresh` (layer 2: rc API + auth error pattern). 각각 별도 raise path. 정합.

### Observability

- ✅ **journalctl syslog identifier 정합**: 모든 unit 에 `SyslogIdentifier=wikihub-{mount-%i|vault-%i|lint|ops-alert}` 명시. `_step8_guide:654-657` 의 운영 진단 명령과 정합.
- ✅ **ops-alert fallback diagnostic**: `collect_mount_fallback_failures` 가 `systemctl is-failed` + `journalctl --user -u ... --since 30min ago -n 100` 첨부. payload `fallback_diagnostic` 필드. 5000 char cap.
- ✅ **rclone `--log-level NOTICE`** (token redaction): mount@.service `--log-level NOTICE` 명시 + 주석으로 ADR-0025 R12-MED-3 reference. 정합.
- ✅ **last_failure.json schema 완전성**: vault_id, severity, scope, reason, remediation, failed_count, alerted_at, alerted_failed_count, first_failed_at, last_failed_at, source_id — ADR-0024 의 11필드 schema 완전 반영. `sync.py`/`mount.py`/`ops-alert.py` 모두 일관.

### Supply Chain (기본 방어선)

- ✅ **rclone SHA256SUMS verify**: `install.sh:472-475` — release artifact + SHA256SUMS 둘 다 `_curl_with_retry` (3회 retry @5min) + `grep -E ... | sha256sum -c -` strict mode. SHA fail 시 `exit 2` fatal.
- ✅ **rclone pinned `1.69.1`** + SHA verify — transport tamper 차단.
- ✅ **SA JSON 보호**: `~/.credentials/wikihub/` repo 외부 격리 + `.gitignore` SA pattern 추가 (`6a85d6e`) + install.sh `chmod 700 .credentials/` + 운영 서버 `chmod 600 <cred>` enforce (`install.sh:531-548`).
- ✅ **uv pinned `0.11.14`** + rclone/gws/uv 패턴 일관 (ADR-0028).
- ✅ **gws pinned `0.22.5`** + Rust target triple (ADR-0015 Accepted).

### Fix-Induced Regression — 안전 확인

- ✅ **결함 #1 (mount.py --rc-addr → --url)**: `RCLONE_RC_ADDR` env 와 `--rc-addr` CLI 의 comma-join 결함 차단. mount@.service 의 server-side `--rc-addr` flag 와 vault@.service 의 `RCLONE_RC_ADDR` env 가 명확히 분리됨.
- ✅ **결함 #5 (timer trailing comment 제거)**: vault@.timer.template, lint.timer.template 의 `[Timer]` 섹션 후 inline comment 없음 — grep 검증 결과 (`grep -nE "^\s*[A-Z][A-Za-z]+=.*#"` 빈 결과). systemd 의 verify 시 잡힐 위험 차단.
- ✅ **결함 #7 (VaultSyncFatal.scope)**: default `"vault"` (exceptions.py:32) + mount.py 명시 `"mount"` (138, 250). `getattr(e, "scope", "vault")` (vault-fetch.py:174) 의 fallback 까지 정합.
- ✅ **결함 #8 (gws getStartPageToken camelCase)**: sync.py:165 `["drive", "changes", "getStartPageToken"]` — gws v0.22.5 정본 subcommand. 진입 시 fail-fast (cursor 없으면 즉시 호출).
- ✅ **결함 #10 (install.sh main guard)**: `install.sh:694 if [[ "${BASH_SOURCE[0]}" == "${0}" ]] || [[ -z "${BASH_SOURCE[0]:-}" ]]; then main "$@"; fi` — source 시 main 미실행, curl-pipe + 직접 실행 둘 다 정합. progress.md V17 incident 의 root cause fix 완성.

### Update 시나리오 검토 (별도 feature 권장 — progress.md:#A~#D)

- ✅ **#A~#D 식별 + 별도 feature 권장 정본화**: progress.md L427-443. 현재 install.sh 가 "reinstall" 만 지원, "update" 부적합이라는 결론 surface. 별도 feature `update_mode` 권장 명시. **본 SRE 라운드에서 추가로 surface 할 update issue 없음** — progress 의 분석이 충분.
- ✅ **현재 update 절차 정합 명시**: `git pull` → `uv pip install -r requirements.txt` → `/wh:setup` → `daemon-reload + restart mount@`. 운영자가 따라 할 수 있는 manual path 보존.

---

## 종합 의견

**Verdict: SRE 측면에서 v0.1.0 Step 5 배포 진행 가능**.

### 평가 요약

- **CRIT 없음** — V<N> Phase 2 의 9건 fix 가 운영 사이클의 critical path (mount lifecycle, ops-alert recursion, fatal scope 정합, SA 자동 override, getStartPageToken, install.sh main guard) 를 모두 closure. 결함 #6 의 truncate 제거는 정당화된 결정 (HIGH-3 의 latency mitigation 권고 별도).
- **HIGH 5건** — 모두 v0.1.0 직후 minor patch 또는 v0.2.x deferred 가능. release blocker 아님:
  - HIGH-1 (RCLONE_MIN_VERSION dead var): 코드 정리 + config dead field 제거.
  - HIGH-2 (supply chain 잔존 위협): spec 명시 + v0.2.x deferred.
  - HIGH-3 (regex latency): 패턴 보강 또는 size cap — 1줄 변경.
  - HIGH-4 (rename 시 file_map orphan): **별도 feature 권장 + 결함 #11 surface 권고** — schema 변경 동반.
  - HIGH-5 (fusermount3 `-z` lazy): 1글자 추가.
- **MED 7건 / LOW 6건** — 모두 operational polishing. 운영 시작 후 1주 관찰 데이터로 우선순위 결정 권고.

### 운영 안정성 강점

1. **4중 OnFailure recursion 방어선** (ops-alert): StartLimitBurst + OnFailure 부재 + RemainAfterExit=no + exit 0 always. 운영 dispatcher 의 dead-letter 정합.
2. **2-layer fatal escalation** (mount@ + vault@): mount permanently failed 시 vault@ trigger cancel + mount@ 직접 OnFailure. ops-alert 의 fallback diagnostic 으로 last_failure.json 부재 case 도 커버.
3. **Retryable threshold escalation** (assert_mount_alive 의 MOUNT_RETRYABLE_FATAL_THRESHOLD=6): 일시 mount stutter 는 흡수 + 1시간 누적 시 Fatal escalate. ops-alert 오발화 빈도 제어 + 진짜 문제는 surface.

### 다음 액션 권고

1. **Step 5 배포 직전 fix 권고 (선택)**:
   - HIGH-3 (regex size cap) — 1줄 변경, 5분.
   - HIGH-5 (fusermount3 -z) — 1글자, 1분.
   - LOW-3 (token redaction 가이드) — `_step8_guide` 주석 추가.
2. **별도 feature 권고 (v0.1.x patch 또는 v0.2.x)**:
   - **결함 #11 surface**: HIGH-4 의 `file_map` orphan — Drive rename 시나리오에서 file_map primary key 가 source_relpath 인 한계.
   - update_mode feature (progress.md #A~#D) — release 전략 + idempotent update + mount stop/start orchestration.
3. **R15 와 분담 검증 필요**:
   - HIGH-1 의 `rclone_min/max_version` config field 정합 (dead config 제거 vs enforce 추가) — config schema 측면 R15.
   - LOW-5 의 sync.py SA override 의 invariant 명시 — 모듈 경계 의존성 R15.

### V<N> Phase 2 acceptance gate 통과 + 9건 fix 의 SRE quality

V8/V10/V12/V14/V15/V15a/V17/V18/V19 의 결함 surface → fix → 재검증 사이클이 **운영자 관점에서 reproducible 한 결함만 fix** 했음. progress.md 의 결함 표가 commit id 와 evidence 를 모두 추적 — 사후 audit 가능. SRE 가 새 운영자 onboarding 시 결함 history 가 즉시 학습 자료가 됨. 정본화 quality 가 평균 이상.

---

**리뷰 종료**.
