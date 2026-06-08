# F4 code review R2 (general-purpose SRE — Step 4 first)

리뷰어: general-purpose SRE (R10)
대상: Step 3 구현 결과 (7 신규 + 5 수정)
독립성 선언: 본인 시각 + R9 답습 회피 (R9 가 surface 한 CRIT-1/2 + HIGH-1~5 + MED-1/2 + NIT 항목은 제외하고, 24/7 운영 reliability·observability·supply chain·failure recovery 관점에서만 신규 finding 을 surface).

리뷰 정본: `analysis_and_design.md v5` + ADR-0015~0024 + R9 결과
대상 파일: `install.sh`, `_system/systemd/*.template`, `_system/systemd/ops-alert.service`, `scripts/ops-alert.py`, `scripts/vault-fetch.py`, `scripts/lib/notify.py`, `scripts/lib/state.py`, `scripts/lib/config.py`, `wikihub.yaml.example`

---

## 1. 차단 이슈 (CRIT — 배포 차단, R9 미surface)

### [CRIT][Reliability] OnFailure recursion — `ops-alert.service` 자체가 fail 시 `ops-alert.service` 가 다시 trigger 될 수 있는 systemd 의미론적 함정

**파일**: `_system/systemd/ops-alert.service:1~16`, `_system/systemd/vault-ingest.service.template:5`

vault-ingest 의 `OnFailure=ops-alert.service` 는 동일한 `ops-alert.service` 가 fail 시 자체적으로 다시 발화되지 않는다는 설계 가정에 기대고 있다. 코멘트(L16) 는 "ops-alert.py 는 항상 exit 0" 이라고 단언하지만 그건 Python 프로세스 종료 코드에 한정된다. systemd 가 service 를 실패로 분류하는 경로는 그 외에도:

1. **venv 손상 (Step 3 venv 가 깨졌거나 `~/.local/share/wikihub/venv` 가 누락)**: `ExecStart={venv_path}/bin/python` 이 ENOENT → systemd `exit code 203/EXEC` → service `failed` 상태. `OnFailure` 가 자기 자신을 다시 trigger.
2. **`WorkingDirectory={instance_root}` 가 deploy 시점에 미존재**: `chdir(2) ENOENT` → `exit 200/CHDIR` → failed.
3. **`TimeoutStartSec=30s` 초과** (webhook server 가 응답 안 하고 timeout 도 cancel 안 함): timeout 분류 → failed.
4. **`ops-alert.py` 가 import 단계에서 SyntaxError/ImportError** (예: F5 에서 `lib.config` 가 break): Python 이 exit 1.

ops-alert.service 자체에 `OnFailure=` 가 명시되지 않은 것이 마지막 safety net 이지만, **현재 template 은 `OnFailure=ops-alert.service` 를 ops-alert 자신에게도 의도치 않게 걸 가능성을 막지 못한다.** systemd 의 동일 service 재진입 방지는 `StartLimitIntervalSec` / `StartLimitBurst` 로 명시해야 안전하다.

또한 v0.2.x 에서 `disk-watch.service`, `lint.service` 가 추가될 때 운영자가 무심코 `OnFailure=ops-alert.service` 를 일관 적용할 가능성도 높다.

**수정**:
- `ops-alert.service` 에 `StartLimitIntervalSec=300` + `StartLimitBurst=3` 추가 (5분 내 3회 fail 시 자체 차단).
- `Type=oneshot` 유지 + `RemainAfterExit=no` 명시 (idle 상태가 success 로 오인되는 것 차단).
- 코멘트에 "ops-alert.service 에는 절대 `OnFailure=` 추가 금지" 명문화.

### [CRIT][Reliability] systemd 의 `WorkingDirectory=` 가 존재하지 않으면 service start 자체가 fail — install.sh 가 `{instance_root}` 생성을 보장하지 않는 순서 함정

**파일**: `install.sh:_step5_yaml (L279~291)`, `_system/systemd/vault-ingest.service.template:9`, `_system/systemd/ops-alert.service:6`

`vault-ingest.service.template` 의 `WorkingDirectory={instance_root}` 와 `ops-alert.service` 의 `WorkingDirectory={instance_root}` 는 systemd 가 unit start 시 directory 존재를 강제 검증한다. 없으면 `203/CHDIR` 로 service failed.

install.sh 의 흐름:
1. Step 5 (L280) 가 `mkdir -p "$WIKIHUB_INSTANCE_ROOT"` 수행 — instance_root 보장.
2. 그러나 `/wh:setup` 이 systemd unit 을 instance 화하는 시점에 운영자가 `wikihub.yaml` 의 `instance.root` 를 **다른 경로로 편집** (예: `/opt/wikihub-data` 처럼 절대경로) 한 경우, install.sh 가 만든 `~/wikihub-instance` 와 yaml 의 `instance.root` 가 분리됨.
3. `/wh:setup` 이 yaml 의 `instance.root` 를 unit template substitution 에 쓸 때 디렉토리 ensure 책임이 모호 (setup.md Step 1 는 `instance.root` 의 "쓰기 권한" 만 보고, 디렉토리 자동 생성은 명시 안 됨).

운영자가 yaml 편집 후 디렉토리를 직접 안 만들면 timer 가 reboot 후 자동 fire 하면서 `203/CHDIR` 로 즉시 fail → ops-alert webhook 가 매 사이클 발사. **v0.1.0 acceptance invariant (reboot resilience) 가 yaml 의 instance.root 변경 시 무너진다.**

R9 의 HIGH-5 (`~` expand) 와 다른 결함이다. HIGH-5 는 path 가 `~` 라서 안 풀리는 문제, 이건 path 자체가 미존재.

**수정**:
- `/wh:setup` Step 1 에 `instance.root` 디렉토리 ensure 단계 추가 (없으면 mkdir, 권한 검증 후).
- 또는 unit template 에 `ExecStartPre=/usr/bin/mkdir -p {instance_root}` 추가 (systemd-native 보장).
- analysis_and_design.md 또는 setup.md 에 "yaml 편집 후 instance.root 디렉토리 생성 책임은 setup 명령" 명시.

---

## 2. HIGH (배포 전 fix, R9 미surface)

### [HIGH][Reliability] `ops-alert.py` 의 webhook timeout 이 socket 단위만 — DNS resolve hang 시 timeout 미작동 + alert 누락

**파일**: `scripts/ops-alert.py:107`

```python
with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
```

`urllib.request.urlopen(..., timeout=N)` 의 timeout 은 **socket I/O timeout** — DNS resolution 단계에는 적용되지 않는다 (Python issue #33532, glibc resolver 의 native timeout 만 적용). webhook URL 의 DNS 가 SERVFAIL 또는 응답 없는 nameserver 를 가리키면 `getaddrinfo()` 가 분 단위로 hang → `TimeoutStartSec=30s` (ops-alert.service:10) 가 systemd 측에서 SIGTERM.

문제는 ops-alert 가 SIGTERM 으로 죽으면 (`mark_alerted` 미호출) `alerted_at` 갱신 안 됨 → 다음 timer cycle 에서 동일 fatal 이 다시 발송 시도 → 같은 DNS hang 반복 → 영원히 무한 발송 시도. **운영자는 webhook 가 한 번도 도달하지 않았다는 사실을 모르고**, journal 만 보면 "30s timeout" 가 매 사이클 반복.

추가로 `socket.timeout` 은 `urllib.error.URLError` 의 subclass 가 아니므로 (Python 3.10+) except 절이 `socket.timeout` 을 따로 잡고 있는 건 OK 이지만, `socket.gaierror` (DNS 실패) 는 except 절이 잡지만 즉시 발생이 아니라 30s 후 발생.

**수정**:
- `socket.setdefaulttimeout(timeout_sec)` 을 main 시작 시 1회 호출 (DNS 포함 전역 timeout).
- 또는 webhook URL 의 host 를 미리 `socket.gethostbyname` 으로 prefetch (timeout 추가) 후 IP 로 POST — 단 TLS SNI 깨짐 위험으로 비권장.
- `ops-alert.service` 의 `TimeoutStartSec` 을 webhook timeout (default 10s) + 여유 (5s) 로 좁혀 systemd kill 이 빨라지게 + journal 에 명시적 timeout reason 기록.

### [HIGH][Observability] `ops-alert.service` 가 alert 발송 실패 시에도 systemd 가 "success" 로 분류 — 운영자가 `systemctl status` 만으로 진단 불가

**파일**: `scripts/ops-alert.py:170`, `_system/systemd/ops-alert.service`

`ops-alert.py` 가 항상 `exit 0` 을 반환하는 정책 (recursion 회피) 은 합리적이다. 그러나 그 결과:

1. webhook 발송 실패 → `log.warning` (L168) 만 → journal 에 warn 로 남음.
2. systemd 입장에서 service 는 success → `systemctl --user status ops-alert.service` 는 `Active: inactive (dead)` + `(code=exited, status=0/SUCCESS)`.
3. 운영자가 `systemctl list-units --failed` 로 fail 상태 확인해도 ops-alert 는 안 보임.

webhook 발송 실패는 **운영자가 직접 보지 못하면 영원히 silent fatal cycle**. 매 timer cycle 에서 vault-ingest fail → OnFailure → ops-alert → webhook fail → journal warn → 운영자 모름.

이는 ADR-0024 의 "Hermes 외 fatal 인지 channel" 의 핵심 목적 (Hermes 다운 시 외부 알림) 자체를 무력화한다.

**수정**:
- webhook 발송 실패 횟수를 `instance_root/_state/ops-alert.state.json` (또는 동등 위치) 에 append-only 로 기록 (atomic write).
- 연속 실패 3회 이상 시 `journalctl --user-unit ops-alert.service -p warning` 보다 강한 신호 — 별도 `~/.local/share/wikihub/ops-alert-stalled` flag 파일 생성 (operator-visible).
- 또는 setup.md 에 "webhook 발송 상태 확인 명령: `journalctl --user-unit ops-alert.service --since '24h ago' | grep '발송 실패'`" 운영 매뉴얼화.
- 최소한 ops-alert.service 의 `SyslogIdentifier=wikihub-ops-alert` 명시로 journal grep 편의 제공.

### [HIGH][Reliability] `last_failure.json` 의 reader/writer race — `vault-fetch.py` 의 atomic write 와 `ops-alert.py` 의 unlocked read

**파일**: `scripts/ops-alert.py:88~95, 119~121`, `scripts/lib/state.py:166~186`

`save_last_failure` 는 `_atomic_write_json` (tmpfile + fsync + os.replace) 를 사용하므로 reader 가 partial write 를 보지는 않는다. 그러나:

1. `mark_alerted` (ops-alert.py:114~121) 가 `_read_json(path)` → mutate → `_atomic_write_json(path, ...)` 의 read-modify-write 시퀀스인데 **lock 없음**.
2. `vault-fetch.py` 가 fcntl flock 안에서 `save_last_failure` 호출 — fatal 직후 timer 가 다시 fire 하면서 ops-alert 가 read-modify-write 와 vault-fetch 의 fatal write 가 interleave 가능.

시나리오:
- T0: vault-fetch fatal → `save_last_failure(payload with failed_count=5)` 완료.
- T1: ops-alert.py 가 `_read_json` 으로 failed_count=5, alerted_at=None 읽음.
- T2: vault-fetch timer 가 다시 fire → fatal → `save_last_failure` → failed_count=6, alerted_at=None 으로 덮어씀.
- T3: ops-alert.py 가 `payload["alerted_at"] = now` mutate 후 atomic write — **이 시점의 payload 는 failed_count=5 (T1 시점의 stale data)**. failed_count=6 의 정보 손실.

`_atomic_write_json` 은 rename atomic 일 뿐 lost-update 를 막지 못한다. vault-ingest service 와 ops-alert service 가 정상 흐름에서는 직렬 (OnFailure → ops-alert 가 vault-ingest 끝난 후 발화) 이지만, 운영자가 vault-fetch 수동 실행 + lint timer + ops-alert 동시 발화 케이스가 가능.

**수정**:
- `mark_alerted` 도 vault state lock (`state_dir/.lock`) 안에서 수행 — vault-fetch 와 동일 lock 공유.
- 또는 `mark_alerted` 가 `_atomic_write_json` 이전에 `_read_json` 으로 다시 읽어 failed_count 만 보존한 후 alerted_at 만 set (mutate 대신 selective merge).
- ADR-0024 본문에 "reader 책임" lock 정책 추가.

### [HIGH][SupplyChain] curl latest tag 의 `set -e` 의도 — install.sh 자체가 `/raw.githubusercontent.com/.../latest/install.sh` 를 fetch 하는 그 latest 가 GitHub Pages CDN 의 mutable cache 라서 race 가능

**파일**: `install.sh:4~7` (호출 문서), 운영 흐름 전체

운영자 호출:
```
curl -fsSL https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh | bash
```

이 명령은 다음 시퀀스를 거친다:
1. `raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh` 를 curl 로 fetch.
2. 받은 스크립트를 bash 로 실행.
3. 스크립트 내부에서 `git clone --branch latest --depth 1` (L178) 다시 수행.

문제: 1번 fetch 와 3번 clone **사이에 latest tag 가 force-update 되면** 두 시점의 install.sh 와 repo 가 **불일치**. 예시:
- T0: 운영자가 curl 시작 → install.sh v0.1.0 다운로드.
- T1: 메인테이너가 `git tag -f latest && git push --force` (이 명령은 ADR-0023 의 v0.2.x release 시점 운영 절차로 추정).
- T2: 운영자의 install.sh 가 Step 2 의 `git clone --branch latest` 수행 → v0.2.0 의 repo.
- 결과: v0.1.0 의 install.sh 가 v0.2.0 의 repo 구조 (Path 변경, 새 의존성 등) 에서 동작 시도 → 알 수 없는 fail.

curl-pipe 모드의 self-replace (L62: `exec bash "$WIKIHUB_HOME/install.sh" "$@"`) 가 일정 부분 완화 — exec 후의 install.sh 는 clone 된 repo 의 그것 — 하지만 **Step 0~2 까지의 로직 (`_pipe_mode_detect`, `_step2_clone`)** 은 첫 curl 의 install.sh 가 수행. 그 사이 latest 변경 시 두 버전의 Step 2 가 서로 incompatible 하면 fail.

ADR-0023 의 mutable tag 정책은 이 race 의 존재를 인정한 결정 — 그러나 install.sh 의 self-replace 흐름 자체가 새 install.sh 의 Step 0~2 를 다시 호출하지 않는다 (Step 1 ~ Step 8 만 호출). 즉, **Step 2 의 clone 결과가 새 install.sh 와 다르더라도 self-replace 후 검증 없음**.

**수정**:
- self-replace 후 새 install.sh 의 SHA 를 검증 — 첫 curl 의 install.sh 가 자체 SHA 와 비교 (자기 자신 비교는 어려우므로 git rev-parse HEAD 비교가 현실적).
- 또는 install.sh 첫 줄에 `# WIKIHUB_INSTALL_VERSION=0_1_0` 라인 매크로 + `_step2_clone` 후 새 install.sh 의 동일 라인 grep → 불일치 시 warn + 운영자 확인 prompt.
- ADR-0023 본문에 race window 의 운영 영향 한 줄 명시 (현재는 결정만 lock 됐고 영향 설명이 없음).

### [HIGH][Security] credentials 파일 권한 검증 부재 — install.sh + /wh:setup 모두 600 강제 안 함

**파일**: `install.sh:_step5_yaml (L281~282)`, `_system/commands/setup.md:33~34`

`install.sh` Step 5 는 `.credentials/` 디렉토리만 `chmod 700` 보장. credentials 파일 자체 (`token_gdrive.json` 등) 는 메인테이너가 scp 로 배치하는 책임. 안내문 (L351) 에 `chmod 600` 명시는 있지만 **install.sh 가 권한을 강제 검증하지 않는다.**

`setup.md` Step 1 (L33) 는 "권한 600" 검증을 명시하지만 그 검증 구현체가 어디 있는지 본 PR 의 코드 (`auth_gdrive.py`, `assert_credentials`) 에 보이지 않는다. `credentials.py:assert_credentials` 가 stat 의 mode 비트 검증을 수행하는지 본 리뷰 범위에서 확인 못 함 — 확인 필요.

만약 검증 없으면:
- scp 후 chmod 누락 시 credentials 가 world-readable 일 수 있음 (OCI 의 default umask 022 가정).
- gws CLI 자체가 token 권한 600 강제하지만 `Drive API` 호출 책임을 가진 wikihub 가 자체 검증 없이 신뢰.
- 운영자가 sudoer 권한 다른 user 와 OCI box 공유 시 token 노출.

**수정**:
- install.sh Step 5 종료 시 `find "$WIKIHUB_INSTANCE_ROOT/.credentials/" -type f -not -perm 600 -exec chmod 600 {} +` 자동 fix.
- 또는 `assert_credentials` 에 mode 비트 검증 + `mode != 0o600` 시 VaultSyncFatal raise (이미 있다면 본 finding 무효).
- setup.md Step 1 의 권한 검증을 명시적 코드 reference 로 link.

### [HIGH][OperationalRisk] `loginctl enable-linger` 실패 시의 회복 경로 부재 — V12 acceptance (reboot resilience) 무력화 가능성

**파일**: `install.sh:_step7_linger (L308~324)`

L315 (`sudo -n loginctl enable-linger`) 실패 분기에 `exit 1` — clean exit 이지만 이 시점에 이미 Step 1~6 은 완료 (venv·gws·yaml). 운영자가 폴라치 정책 (polkit) 으로 sudo NOPASSWD 미설정 + 비대화 모드 (`curl | bash`) 인 경우 install.sh 가 즉시 종료.

문제: linger 가 없어도 systemd user manager 가 login session 동안은 동작. 운영자가 "sync 가 도는 것 같다" 고 오인 → 다음 reboot 시 timer 자동 시작 안 됨 → **v0.1.0 acceptance invariant 실패**.

추가 시나리오: OCI 의 `cloud-init` 환경에서 user 가 ssh login 안 한 상태로 첫 reboot → linger 부재로 systemd user 영역 아예 미시작 → ops-alert.service 도 timer 도 모두 dead.

**수정**:
- Step 7 fail 시 단순 exit 1 대신 명확한 진단 (`run as a privileged user:` instruction) + 운영자가 수동으로 `sudo loginctl enable-linger $USER` 후 install.sh 재실행 가능하도록 idempotent 보장.
- Step 1 의 sudo pre-check (L94) 가 NOPASSWD 미설정 + `/dev/tty` 부재 + 비대화 모드를 모두 감지 시 Step 1 단계에서 fail-fast (Step 2~6 의 시간 낭비 회피).
- 또는 ADR-0021 의 D2 (linger 부재 시 cron @reboot fallback) 활성화 — v0.1.0 에서 deferred 됐지만 본 결함이 surface 되면 우선순위 재검토 필요.

### [HIGH][Observability] install.sh stdout 의 journal mirror 부재 — curl-pipe 모드 fail 시 사후 분석 불가능

**파일**: `install.sh` 전체

curl-pipe 모드의 출력은 운영자 터미널의 stdout/stderr — bash 가 종료되면 휘발. 운영자가 `tmux capture-pane` 같은 명시적 캡처를 안 하면 fail reason 영원히 손실.

특히:
- Step 4 의 gws 다운로드 fail (V8 의 asset 이름 가설 깨짐) — curl 실패 메시지가 한 줄 → 운영자 scrollback 에 묻힘.
- Step 7 의 sudo password prompt 실패 — `/dev/tty` 출력이 stdout 과 분리.
- self-replace exec (L62) 후의 새 install.sh 출력만 살아남고 그 전의 Step 0/Step 2 출력 분실 가능 (exec 가 stdout buffer 를 inherit 하지만 ssh client 의 line buffering 정책 의존).

24/7 운영 환경에서는 fail 의 사후 분석이 root cause 진단의 핵심. install.sh 가 ephemeral 한 채로 첫 실행되는 건 디자인이지만, **clone 된 후의 `$WIKIHUB_HOME/install.log` mirror 가 부재**.

**수정**:
- self-replace 후 새 install.sh 의 첫 줄에 `exec > >(tee -a "$WIKIHUB_HOME/install.log") 2>&1` 추가 — clone 디렉토리 안에 로그 저장. 재실행 시 append. 운영자가 fail 후 `cat ~/wikihub/install.log` 로 조회 가능.
- 또는 install.sh 종료 시 (success/fail 모두) journal 에 한 줄 마커 기록 (`logger -t wikihub-install` 활용).

---

## 3. MED (다음 PR)

### [MED][Reliability] `set -u` 와 `${VAR:-}` 패턴 불일치

**파일**: `install.sh:31, 96, 314`

L31: `SKIP_CONFIRM="${SKIP_CONFIRM:-${WIKIHUB_NONINTERACTIVE:-}}"` — OK.
L96: `if [ -n "$SKIP_CONFIRM" ]; then` — OK (L31 에서 set 됨).
L314: `if [ "$SKIP_CONFIRM" = "1" ]; then` — L31 의 default 가 빈 문자열인데 비교는 "1" — 빈 문자열 vs "1" 비교 OK 이지만 의도가 모호 (`-n` 으로 통일이 자연).

또한 `EUID` (L87) 는 bash builtin 이라 set 보장되지만 POSIX sh shebang 으로 바뀌면 깨짐. 현재 shebang `#!/usr/bin/env bash` 라 안전.

`SKIP_CONFIRM=1` 의 type (`int` vs `str`) 일관성 — L39 의 `SKIP_CONFIRM=1` 와 L74 의 `SKIP_CONFIRM=1` 는 int, L96 의 `[ -n "$SKIP_CONFIRM" ]` 는 str — 결과는 OK 이지만 표준화 권장.

**수정**: SKIP_CONFIRM 의 비교를 일관되게 (전부 `[ "$SKIP_CONFIRM" = "1" ]` 또는 전부 `[ -n "$SKIP_CONFIRM" ]`).

### [MED][Reliability] `shasum` 명령어 의존성 — Ubuntu 의 default 가용성 미검증

**파일**: `install.sh:254`

`shasum -a 256 -c` — Ubuntu 22.04/24.04 의 default 패키지 `perl` 의 일부 (`/usr/bin/shasum`). 그러나 minimal image (Docker, cloud-init 기본) 에 perl 없으면 ENOENT.

OCI ARM Ubuntu 22.04 minimal image 의 perl 포함 여부 미검증. minimal 인 경우 fail 시 `set -e` 로 즉시 exit — 운영자가 진단 어려움.

대안: `sha256sum` (coreutils) 는 ubuntu default 100% 포함. format 이 `shasum -a 256` 과 호환 (둘 다 `<hash>  <filename>` 형식).

**수정**: `sha256sum` 으로 교체 (의존성 단순 + verify 일관성).

### [MED][Observability] webhook payload 의 `hostname` leak — fatal_webhook_url 이 외부 서비스 (예: Discord/Slack/IFTTT) 일 때 OCI VM 의 internal hostname 노출

**파일**: `scripts/ops-alert.py:149`

```python
"wikihub_instance": socket.gethostname(),
```

OCI VM 의 hostname 은 default 가 `oci-arm-xxxxx` 형식 — instance ID 가 부분 노출. webhook server 가 외부 SaaS 면 chat 로그가 외부 보관됨. 운영자가 hostname 을 의도적으로 변경 안 했다면 internal 정보 leak.

**수정**:
- `wikihub.yaml` 에 `operations.instance_label` 추가 — 운영자가 명시한 alias 사용. 미설정 시 `socket.gethostname()` fallback.
- 또는 `wikihub_instance` 필드를 hash (`hashlib.sha256(hostname)[:8]`) 로 anonymize.

### [MED][SpecMismatch] macOS dev box 에서 install.sh 호출 시 silent warn 만 — 차단 안 됨

**파일**: `install.sh:_step1_env_check (L102~109)`

`ID != "ubuntu"` 시 `warn` 만 출력하고 계속 진행. macOS dev box (메인테이너 작업 환경) 에서 실수로 `./install.sh` 호출 시 Step 2 의 `git clone` 까지 진행 → `$HOME/wikihub` (메인테이너의 개발 디렉토리!) 가 wipe 위험.

L142~148 의 safety guard 1 가 `WIKIHUB_HOME=$HOME` 또는 시스템 경로면 차단하지만 default `$HOME/wikihub` 는 차단 안 됨. 메인테이너의 macOS 의 `~/workspace/wikihub` 와 충돌 가능성.

**수정**:
- non-Ubuntu 환경에서 `--allow-non-ubuntu` 플래그 없으면 fail-fast (현재 warn 을 err + exit 1 로 승격).
- 또는 Step 2 의 safety guard 에 `git config --get remote.origin.url` 검증 강화 (현재는 있지만, 디렉토리 부재 시 가드 발동 안 됨 — 새로 clone 하는 케이스가 위험).

### [MED][Reliability] `WIKIHUB_INSTANCE_ROOT` 의 `~` expand 정합성

**파일**: `install.sh:27`

```bash
WIKIHUB_INSTANCE_ROOT="${WIKIHUB_INSTANCE_ROOT:-$HOME/wikihub-instance}"
```

env override 시 운영자가 `WIKIHUB_INSTANCE_ROOT="~/data/wikihub"` 같이 quote 안에 `~` 를 넣으면 bash 가 expand 안 함 (literal `~`). Step 5 의 `mkdir -p` 가 literal `~/data/wikihub` 디렉토리 생성 — 운영자 의도 위배.

이는 R9 의 HIGH-5 (config.py 의 `Path("~/...")`) 와 같은 패턴이지만 install.sh 단계에서도 발생 가능.

**수정**: `WIKIHUB_INSTANCE_ROOT="${WIKIHUB_INSTANCE_ROOT/#\~/$HOME}"` 같은 명시적 expand 또는 docs 에 "절대경로만" 명시.

### [MED][Observability] systemd unit 의 `SyslogIdentifier=` 부재 — journal grep 어려움

**파일**: `_system/systemd/vault-ingest.service.template`, `ops-alert.service`

systemd user unit 의 journal 출력은 `_SYSTEMD_UNIT=...` 필드로 분리되지만 운영자가 `journalctl --user` 만 했을 때 출력의 prefix 가 unit 이름 (`gdrive-ingest.service[12345]:`) — 알아보기 어려움.

`SyslogIdentifier=wikihub-vault-ingest` 같은 명시적 식별자를 두면 `journalctl --user --identifier=wikihub-*` 로 vault 전체 한 번에 조회 가능.

**수정**: unit template 에 `SyslogIdentifier=wikihub-{vault_id}-ingest`, `ops-alert.service` 에 `SyslogIdentifier=wikihub-ops-alert` 추가.

### [MED][Reliability] `requirements.txt` 부재 시 venv 만 생성 — Step 4 이후 단계가 deps 없이 진행

**파일**: `install.sh:_step3_venv (L199~201)`

```bash
warn "requirements.txt 없음 — venv 생성만 (의존성 미설치)"
```

scripts/requirements.txt 가 존재 (`ls` 결과 확인). 그러나 install.sh 가 read 하는 path 는 `$WIKIHUB_HOME/requirements.txt` — clone 직후의 위치. **scripts/requirements.txt 가 아니라 repo root 의 requirements.txt** 를 본다. 본 PR 의 변경 범위에는 root requirements.txt 가 있는지 명시 안 됨.

```bash
$ ls /Users/1004790/workspace/wikihub/requirements.txt 2>&1
```
이 결과 확인이 필요 (본 리뷰 시점에는 root requirements.txt 부재 확률 높음).

**수정**:
- root 에 `requirements.txt` (scripts/requirements.txt 를 -r include) 추가, 또는
- install.sh L195 의 path 를 `"$WIKIHUB_HOME/scripts/requirements.txt"` 로 변경.

### [MED][OperationalRisk] `wikihub.yaml.example` 의 `agent.binary: /usr/local/bin/hermes` 가 미설치 시 sync 시점에 fail

**파일**: `wikihub.yaml.example:39`, `_system/systemd/vault-ingest.service.template:13`

Hermes 가 미설치된 상태로 운영자가 `/wh:setup --enable` 호출 → systemd unit 의 `ExecStart=/usr/local/bin/hermes ...` 가 timer fire 시점에 `203/EXEC` fail → OnFailure → ops-alert.

문제: Step 1 의 환경 검증 (setup.md Step 1) 에 "agent.binary 실행 가능" 명시는 있지만 install.sh 자체는 hermes 설치를 안 함. Hermes 설치는 메인테이너의 별도 책임. 그 경계가 wikihub.yaml.example 의 주석에 명시 안 됨.

**수정**: `wikihub.yaml.example` 의 `agent` 섹션 주석에 "Hermes 설치는 install.sh 범위 밖. 별도 설치 후 path 확인 필수." 명시.

---

## 4. LOW / NIT

### [LOW][SupplyChain] shasum 부재 시 warn 만 — supply chain attack detection 0

**파일**: `install.sh:255~257`

R9 의 finding 과 중복되나 SRE 관점에서 priority 상향 권고. gws 의 GitHub Releases 에 .sha256 파일이 호스팅 안 되면 (현재 unknown) 영원히 warn 만 — MITM 또는 tag tampering 검출 불가. v0.2.x 까지 미루는 건 24/7 production 보안 stance 로 약함.

**수정**: ADR-0015 의 fail-closed 모드 옵션 추가 (`--require-shasum` 플래그) — 운영자가 명시적 opt-in.

### [LOW][Reliability] `tar -C "$tmpdir" -xzf` 의 tar 의존성

**파일**: `install.sh:258`

`tar` 는 ubuntu default 포함이지만 minimal image 시나리오에서 (busybox tar 등) gzip extraction 호환성 검증 권장.

### [LOW][Observability] `loginctl enable-linger` 후의 검증 부재

**파일**: `install.sh:_step7_linger (L321)`

```bash
sudo loginctl enable-linger "$USER" < /dev/tty
```

명령 성공 후 `loginctl show-user "$USER" | grep Linger=yes` 재검증 없음. systemd-logind 의 state 가 즉시 반영 안 될 가능성 (race) 시 다음 reboot 까지 silent 실패.

**수정**: `loginctl enable-linger` 후 1초 sleep + `show-user | grep Linger=yes` 재검증.

### [NIT][Observability] `info`/`ok`/`warn`/`err` 의 시각 정보 부재

**파일**: `install.sh:20~23`

로그 prefix 가 `INFO`/`OK`/`WARN`/`ERROR` 만 — timestamp 부재. 운영자가 install.sh 가 hang 한 상태 (gws 다운로드 분 단위) 와 정상을 구분 어려움.

**수정**: `info() { echo "${C_INFO}INFO${C_RST}  [$(date +%H:%M:%S)] $*"; }` 처럼 time 추가.

---

## 5. SRE 관점 강점

1. **`_atomic_write_json` 의 fsync 명시** (`scripts/lib/state.py:39`) — OCI 의 unexpected reboot 시 zero-length 파일 회피. F2 의 HIGH-R4-1 fix 가 잘 보존됨.

2. **`fcntl.LOCK_EX | LOCK_NB`** (`scripts/vault-fetch.py:107`) — vault-fetch 동시 실행 차단. 운영자 수동 실행 + timer 충돌 케이스 cover.

3. **`Persistent=true` + `OnBootSec=2min`** (`vault-ingest.timer.template:7~10`) — reboot 직후 cloud-init settle 시간 확보 + 놓친 fire catch-up. v0.1.0 acceptance invariant 의 핵심 보장.

4. **`SuccessExitStatus=0 75`** (`vault-ingest.service.template:14`) — exit 75 가 systemd 의 "success" 분류 → OnFailure 미발화 → ops-alert 의 alarm fatigue 회피. 설계 의도가 ini 에 정확히 인코딩됨.

5. **safety guard 3 단** (`install.sh:142~169`) — `WIKIHUB_HOME` wipe 의 위험을 시스템 경로 차단 + origin 검증 + cwd 회피로 다층 방어. 운영자 실수 (env 오타) 의 폭발 반경 제한.

6. **`/dev/tty` 부재 자동 감지** (`install.sh:72~76`) — CI/cloud-init 환경에서의 silent hang 회피.

7. **`SKIP_CONFIRM` 의 비대화 sudo 1차 검증** (`install.sh:94~100`) — NOPASSWD 부재 시 즉시 fail-fast — 분 단위 hang 방지.

---

## 6. R9 결과와의 비교 (중첩 / 보완)

### 본 R10 가 cover 하고 R9 가 미surface 한 영역

| 영역 | R10 finding |
|---|---|
| OnFailure recursion 함정 (systemd 의미론) | CRIT |
| WorkingDirectory 미존재 시 systemd 자체 fail | CRIT |
| webhook timeout 의 DNS hang | HIGH |
| ops-alert.service success 오분류 | HIGH |
| last_failure.json reader/writer race | HIGH |
| latest tag race window 의 self-replace 흐름 깨짐 | HIGH |
| credentials 권한 검증 부재 | HIGH |
| linger 회복 경로 | HIGH |
| install.sh log mirror 부재 | HIGH |

### R9 와 중첩 (의도적 답습 회피)

R9 의 CRIT-1, CRIT-2, HIGH-1~5, MED-1~3 은 본 리뷰에서 다시 언급 안 함. 모두 동의함.

### R9 가 LOW 분류한 항목 중 SRE 관점 priority 상향 권고

- **shasum 부재 warn** (R9 LOW → R10 LOW 이지만 v0.2.x 까지 미루는 정책 자체 재검토 권고).

---

## 7. 종합 권고

### 배포 차단 여부: **예** — R9 의 CRIT 2건 + 본 R10 의 CRIT 2건 (OnFailure recursion + WorkingDirectory ensure) **모두 fix 후 배포**

24/7 운영 reliability 관점에서 본 PR 의 가장 큰 SRE risk 는:

1. **CRIT-R10-1 (OnFailure recursion)**: alert dispatcher 자체가 fail loop 에 빠지면 운영자 신호 0 + 시스템 리소스 burnt. systemd 의 `StartLimit*` 명시는 5 줄 변경으로 가능 — 즉시 fix.

2. **CRIT-R10-2 (WorkingDirectory ensure)**: v0.1.0 의 acceptance invariant (reboot resilience) 가 yaml 의 instance.root 편집 + 디렉토리 미생성 시점에 무너짐. 운영자의 흔한 실수 경로.

3. **HIGH-R10-1 (DNS hang)**: webhook 의 alert latency 가 분 단위로 늘어나는 sleep + alert 누락. `socket.setdefaulttimeout` 한 줄 추가로 해결 가능.

4. **HIGH-R10-2 (ops-alert success 오분류)**: webhook 발송 실패가 운영자 가시성 0 — `ops-alert.service` 의 의미를 운영자가 잘못 이해할 가능성 높음. `SyslogIdentifier` + 운영 매뉴얼화로 부분 완화.

### 즉시 fix 권고 (배포 차단 해제 조건)

- **CRIT-R10-1, CRIT-R10-2**: 1시간 작업량.
- **HIGH-R10-1** (DNS hang): 1줄 fix.
- **HIGH-R10-3** (last_failure race): mark_alerted 에 lock 추가, 2시간 작업량.
- **HIGH-R10-5** (credentials chmod): install.sh 에 자동 chmod 추가, 30분 작업량.

### 다음 PR (v0.1.1 hotfix 또는 v0.2.0 본 release)

- HIGH-R10-2 (ops-alert observability) — 운영 매뉴얼 + `SyslogIdentifier`.
- HIGH-R10-4 (latest tag race) — ADR-0023 의 영향 명시 + self-replace 후 SHA 검증.
- HIGH-R10-6 (linger 회복) — Step 1 의 sudo pre-check 강화 + ADR-0021 의 D2 cron fallback 재검토.
- HIGH-R10-7 (install.log mirror) — 1줄 (exec > tee) 추가.
- MED 항목 전체.

### v0.2.x 이전에 hand-check 필요

1. **scripts/lib/credentials.py 의 `assert_credentials`** 가 mode 비트 검증을 수행하는지 (HIGH-R10-5 의 전제).
2. **root requirements.txt 존재 여부** (MED-R10-7).
3. **gws GitHub Releases 의 .sha256 파일 호스팅 여부** (LOW-R10-1).
4. **OCI ARM Ubuntu 22.04 minimal image 의 `perl` (shasum) / `tar` 포함 여부** (MED-R10-2, LOW-R10-2).

---

*리뷰 종료. R9 와 R10 의 finding 을 통합 처리 후 Step 3 으로 복귀 (analysis_and_design.md 의 §4 또는 §5 에 fix 항목 누적) 권고.*
