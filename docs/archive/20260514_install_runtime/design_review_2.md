# F4 design review R6 (SRE 독립 검토)

- 리뷰어: general-purpose SRE (R6) — claude-opus-4-7, fresh context
- 대상: `features/20260514_install_runtime/plan.md`, `features/20260514_install_runtime/analysis_and_design.md` v3
- 독립성 선언: 본 리뷰는 plan/design 두 문서와 F1·F2·F3 archive 만 입력으로 사용하여 본인 시각으로 작성했다. 다른 리뷰어 결론을 일절 참고하지 않았다.
- 범위: production reliability·observability·failure recovery·security 4축. 본 feature 가 v0.1.0 의 acceptance invariant("OS reboot 후 사람 개입 없이 sync 자동 재기동")을 실제로 지키는지를 SRE 직관으로 surface.

> 종합: design v3 는 의도(curl-pipe + clean install)와 ADR 매핑에서는 정합하나, **24/7 daemon 운영의 표준 SRE 결함 다수가 systemd unit template 과 install.sh state machine 에 잔존**한다. 특히 **systemd unit 의 exit code 매핑 모순 1건 (CRIT)**, **재시도 burst limit 도달 시 dead-state stuck 1건 (CRIT)**, **첫 ingest 시 systemd timer 이미 enable 상태에서 fatal loop 1건 (CRIT)** 은 Step 3 진입 전 spec 수준에서 fix 가 필요하다. 이하 본문 참조.

---

## 1. 차단 이슈 (CRIT — Step 3 진입 차단)

### CRIT-R6-1 [Reliability / SpecMismatch] systemd unit 의 `Restart=on-failure` 와 exit code 매핑이 자기모순 — exit 2 (Fatal) 도 Restart 트리거 → 무한 재시작 (`analysis_and_design.md` §4.2 vault-ingest.service.template)

**무엇이**: v3 §4.2 의 service template:
```ini
Restart=on-failure
RestartSec=60
StartLimitInterval=600
StartLimitBurst=5
# exit 0: 정상; 75: Retryable (Restart 트리거); 2: Fatal (Restart 안 함)
```

주석은 "75 만 Restart, 2 는 Restart 안 함" 의도를 명시. 그러나 **`Restart=on-failure` 의 systemd 정의**는 "exit code 0 + `SuccessExitStatus` 에 등록된 코드"를 제외한 모든 종료를 failure 로 간주하여 Restart 트리거. 즉:
- exit 0 → success → no restart (의도)
- exit 75 → failure → restart (의도)
- exit 2 (Fatal) → failure → **restart** (의도와 정반대)

F3 의 `lib/errors.py` 가 exit 2 를 emit 하는 상황 (auth invalid, scope error, gws not found 등) 은 정의상 **운영자 개입 없이는 회복 불가**. 그런데 systemd 는 매 60초마다 vault-fetch.py 를 재시작 → 매번 exit 2 → StartLimitBurst=5 도달까지 5×60=300초 동안 fatal 무한 루프. 그동안 journald 폭주 + 운영자에게 동일 fatal 5회 alert.

**왜 위험한가**:
- 5분 동안 무의미한 5회 시도 + ops-alert 도배. F1 archive §4.6.6 의 `OnFailure=ops-alert.service` 가 매 fatal 마다 발동 → telegram 5연발.
- 운영자 입장에서 "auth 만료" 한 사건이 매번 5건 alert 로 보임 → alert fatigue → 진짜 fatal 무시 위험.

**왜 선행 검토가 놓쳤나** (추정): plan.md `Definition of Done` 에서 "exit 75 가 systemd Restart=on-failure 로 자동 재시도, exit 2 는 더 이상 재시도 안 함 (V10)" 으로 spec 수준에서 의도만 명시했고, systemd 의 `Restart=on-failure` semantics 와의 충돌은 짚지 않았다.

**어떻게 고칠까** — 두 옵션 중 하나 선택을 ADR 또는 v4 본문에서 lock:

옵션 A (권장 — F1 archive §4.8.2 정합):
```ini
[Service]
Type=oneshot
Restart=on-failure
RestartSec=60
SuccessExitStatus=0 75       # 75 를 "success" 로 인정 → systemd 가 failure 로 기록 안 함
                              # → Restart 도 안 함 (다음 timer fire 가 책임)
                              # → Fatal(2) 만 'failed' 표시 + OnFailure 발동
```

옵션 B (반대 — 75 만 Restart 명시):
```ini
[Service]
Restart=on-failure
RestartPreventExitStatus=2
RestartSec=60
StartLimitInterval=600
StartLimitBurst=3
```

**우선 권장 = 옵션 A**:
- F1 archive §4.8.2 의 `gdrive-sync.service` 가 정확히 옵션 A 패턴 (`SuccessExitStatus=0 75`) 을 lock 했음. F4 design 이 F1 정본을 ignore 한 회귀.
- 옵션 A 는 "75 = next timer cycle 이 retry 책임" 이라는 ADR-0006 의 unified orchestration 정신과 일치 — systemd 의 `Restart=` 가 sync interval 보다 짧으면 timer 와 race.
- design v3 §4.2 의 `OnUnitActiveSec={sync_interval_sec}s` (600s) 와 `RestartSec=60` 의 충돌: exit 75 후 RestartSec=60 으로 즉시 retry → 60s 만에 다시 fail → ... 정상 600s interval 이 사실상 60s interval 로 단축. design 의 retry 정책과 모순.

**스펙 수정 위치**: §4.2 service template 의 `Restart`/`RestartSec` 블록 + 주석 + ADR-0017 본문에 "Restart 책임은 timer 가 짐 (옵션 A)" 명시. ADR-0021 본문에도 "exit code 매핑 = F1 §4.8.2 lift" 한 줄 추가.

---

### CRIT-R6-2 [Reliability] StartLimit 도달 후 systemd 가 unit 을 `failed` 상태로 두고 멈춤 — 운영자 수동 `reset-failed` 까지 영구 stuck (`analysis_and_design.md` §4.2)

**무엇이**: 옵션 B 채택 시 (또는 옵션 A 라도 `Restart=` 가 살아있는 한) StartLimitBurst=5 + StartLimitInterval=600 으로 5 fail 후 systemd 는 `start-limit-hit` 상태 진입. **이 상태에서는 timer 가 unit 을 다시 활성화하지 못함** — `systemctl --user reset-failed <unit>` 수동 호출 필요.

운영 시나리오:
- OAuth 토큰이 7일 후 만료 (refresh 실패 등) → exit 2 5회 → start-limit-hit → vault stuck.
- 운영자가 토큰 갱신 + scp 했음에도 unit 이 self-recover 안 함 — 24/7 daemon invariant 깨짐.
- v0.1.0 acceptance ("사람 개입 없이 sync 자동 재기동") 와 일치하지 않음. 단 reboot 시점에는 reset 되지만 reboot 없이는 stuck.

**왜 위험한가**: design v3 의 acceptance 가 reboot resilience 만 다루지 **OAuth lifecycle resilience** (refresh 실패 후 자동 회복) 는 ADR scope 에서 누락. OCI 운영 시 reboot 보다 토큰 만료가 빈번한 fail mode 라는 점이 SRE 직관.

**어떻게 고칠까**:
1. 옵션 A 채택 (CRIT-R6-1 fix) — 그러면 StartLimit 의 영향권에서 벗어남 (75 는 success 처리되므로 limit 안 침범).
2. 또는 ops-alert.service 가 `ExecStartPost=systemctl --user reset-failed <unit>` 로 자동 복구. 다만 alert 의 SRE 의미 약화 (failure 가 silent 회복).
3. timer 의 `OnCalendar=` 추가 (e.g. `OnCalendar=*:0/10`) — `OnUnitActiveSec` 단독은 start-limit-hit 후 fire 안 함이지만 OnCalendar 는 wall-clock 기반이라 fire. v3 §4.2 에는 OnCalendar 없음.

**스펙 수정 위치**: §4.2 의 timer template 에 `OnCalendar=` 추가 옵션 발의, 또는 옵션 A 채택으로 StartLimit 우회. ADR-0021 본문에 fail mode (i)·(ii)·(iii) 외에 **"(iv) StartLimit 도달 후 자동 회복 부재"** 추가하여 fallback 절차 lock.

---

### CRIT-R6-3 [Reliability / DesignGap] 첫 ingest fatal 시 systemd timer 가 이미 enable 상태 → fatal loop + ops-alert 도배 (`analysis_and_design.md` §3.5 [E3], §6 V13)

**무엇이**: ADR-0022 (E3) 가 lock 한 흐름:
1. install.sh → 메인테이너 yaml 편집 + credentials scp → `/wh:setup --enable` 호출
2. /wh:setup Step 4 가 `systemctl --user enable --now {vault_id}-ingest.timer` 실행 — **timer 가 즉시 활성화 + OnBootSec=60s 가 첫 fire 예약**
3. /wh:setup Step 5/6 에서 prompt: "첫 ingest 를 지금 실행할까요?"
4. 운영자가 Y → vault-fetch.py --bootstrap 직접 실행 → fatal (예: credentials 형식 오류, root_folder_id 오타) → exit 2

이 시점에 **systemd timer 가 이미 enable + 60초 후 자동 fire 예정**. 첫 ingest fatal 종료 후 60초 뒤 timer 가 다시 vault-fetch.py 호출 → 동일 fatal → CRIT-R6-1/2 의 fatal loop 진입.

**왜 위험한가**:
- 운영자가 "첫 ingest 실패 - 디버그 후 재시도" 하는 동안 (보통 5~30분) systemd 가 background 에서 동일 사이클 반복 → journal 폭주 + retry queue 데이터 손상 가능.
- ADR-0022 본문은 prompt 와 trigger 만 다루고 **timer enable 시점과 첫 ingest 사이의 race** 는 spec 외.
- v3 §3.5 의 "Y 응답 시 vault-fetch.py 직접 호출 + stdout JSON 보고 + bootstrap_allowed 자동 false 환원" 만 명시 — fatal 시 동작 미정.

**어떻게 고칠까** — 두 옵션:

옵션 A (권장 — 첫 ingest 가 성공해야 timer enable):
- /wh:setup `--enable` 의 단계 순서 변경: yaml 검증 → unit 파일 작성 → daemon-reload → **첫 ingest 수동 1회 성공** → 그 후에야 timer enable.
- 첫 ingest 실패 시 timer 는 disable 상태로 유지 — 운영자가 fix 후 `/wh:setup --enable` 재호출.

옵션 B (mask 패턴 — 첫 ingest 진행 중에는 timer mask):
- /wh:setup 이 첫 ingest 직전에 `systemctl --user mask {vault_id}-ingest.timer` 로 timer 강제 정지.
- 첫 ingest 완료 (성공/실패 무관) 후 mask 해제.
- 단 mask 한 상태에서 운영자가 ctrl-c → mask 영구 stuck. ops-alert 도 안 옴.

**우선 권장 = 옵션 A**. ADR-0022 본문에 "첫 ingest 성공이 timer enable 의 전제조건" 으로 명시 lock. v3 의 `--enable` flag semantics 변경 필요.

**스펙 수정 위치**: ADR-0022 본문 + `_system/commands/setup.md` Step 4 의 enable 시점 재배치 + design v3 §3.5 [E3] 의 "책임 분할" 단락에 첫 ingest fatal 분기 명시.

---

## 2. HIGH (Step 3 진입 전 spec 보강)

### HIGH-R6-1 [Reliability] `WIKIHUB_NONINTERACTIVE=1` + sudo NOPASSWD 미설정 시 fail-loud 보장 부족 (`analysis_and_design.md` §4.1 Step 1 / Step 7)

**무엇이**: §4.1 Step 1 의 sudo pre-check:
```bash
if ! sudo -n true 2>/dev/null; then
    if [ -n "$SKIP_CONFIRM" ]; then
        echo "ERROR: --skip-confirm 모드인데 sudo 비대화 호출 실패. NOPASSWD 설정 필요." >&2
        exit 1
    fi
    ...
fi
```

`$SKIP_CONFIRM` 은 v3 본문에서 한 번도 정의되지 않은 변수명. `--skip-confirm` flag 가 어떻게 환경변수로 mapping 되는지 spec 부재. argparse 또는 manual parse 단계가 §4.1 spec 에서 누락 → 구현자가 임의 mapping 시 검증 통과/실패가 비결정.

비대화 모드의 진입 경로 3개:
1. `WIKIHUB_NONINTERACTIVE=1` env (Step 0)
2. `--skip-confirm` flag (Step 1 의 `$SKIP_CONFIRM`)
3. `/dev/tty` 부재 (Step 0 이 `WIKIHUB_NONINTERACTIVE=1` 자동 활성화)

세 경로의 정합 검증 변수가 §4.1 spec 에 없음. SRE 시각: install.sh 가 silent hang 또는 silent skip 어느 하나도 안 됨이 fail-loud 원칙. spec 수준에서 단일 진실값 (`$NONINTERACTIVE` 통일) lock 필요.

**어떻게 고칠까**: §4.1 Step 0 ~ Step 1 사이에 **"플래그 정규화"** 단락 신설:
```bash
# Step 0.5 — 입력 정규화 (모든 분기를 단일 변수로 흡수)
WIKIHUB_NONINTERACTIVE="${WIKIHUB_NONINTERACTIVE:-}"
for arg in "$@"; do
    case "$arg" in
        --skip-confirm) WIKIHUB_NONINTERACTIVE=1 ;;
    esac
done
if [ ! -c /dev/tty ]; then
    WIKIHUB_NONINTERACTIVE=1
fi
readonly WIKIHUB_NONINTERACTIVE
```
- Step 7 의 `sudo` 호출도 동일 변수를 참조.
- `< /dev/tty` redirect 는 `WIKIHUB_NONINTERACTIVE=0` 모드에서만 시도. `=1` 모드에서 sudo -n 실패하면 명시 fail-loud (exit 1) 이미 §4.1 에 있음.

---

### HIGH-R6-2 [Idempotency] partial install 회복 — Step 4 (gws 다운로드) 실패 시 잔존 tmpdir + Step 7 sudo 실패 시 state 잔존 (`analysis_and_design.md` §4.1 Step 4, Step 7, V11)

**무엇이**:
- Step 4 의 `TMPDIR=$(mktemp -d) ... rm -rf "$TMPDIR"` 패턴: shasum verify 또는 tar extract 실패 시 `set -e` 활성이면 `rm -rf "$TMPDIR"` 도 안 돌고 즉시 exit. tmpdir 잔존 (디스크 leak + 다음 install 시 stale).
- Step 7 의 linger 활성화 sudo 실패 시: venv·gws·repo 는 이미 만들어졌지만 user manager 가 reboot 후 안 뜨는 상태. 다음 install.sh 호출이 idempotent 여야 하는데 spec 에 미정.
- V11 acceptance 가 "두 번 호출해도 안전" 만 명시. **"실패한 첫 호출 + 정상 두 번째 호출 → 정상 state" 시나리오 미지정**.

**어떻게 고칠까**:
- §4.1 Step 4 에 `trap 'rm -rf "$TMPDIR"' EXIT` 패턴 lock — set -e 라도 cleanup 보장.
- §4.1 Step 7 의 linger 활성화는 본인이 idempotent (`loginctl show-user | grep Linger=yes` 사전 확인 이미 있음) — 단 sudo 자체가 실패하면 즉시 exit 후 다음 호출도 동일 sudo 시도. **이 경우 venv·gws 가 이미 있으므로 다음 호출이 skip 진입하는지 자가 검증 추가**.
- V11 spec 에 "(5) Step 4 중간 실패 후 재호출 시 tmpdir 잔존 없음, (6) Step 7 sudo 실패 후 재호출 시 모든 prior step skip 진입" 추가.

---

### HIGH-R6-3 [Reliability] `OnBootSec=60s` 가 OCI ARM 의 boot 시간 + cloud-init + network-online 실 대기 시간 보다 짧을 위험 (`analysis_and_design.md` §4.2 timer template)

**무엇이**: v3 §4.2 의 timer:
```ini
OnBootSec=60s
```
F1 archive §4.8.2 는 `OnBootSec=2min` (= 120s). F4 가 임의로 60s 로 단축. 근거 spec 부재.

OCI ARM Ubuntu 의 cloud-init + 첫 boot 절차:
- kernel boot ~10s
- cloud-init `network` stage ~20s
- cloud-init `final` stage ~30s
- network-online.target ~40s (단 google API DNS resolve 가능 시점은 더 늦음, 외부 DNS query 가능 시점은 보통 boot+60~90s)

`After=network-online.target` 가 있어도 network-online 의 정의는 "디폴트 게이트웨이 ping 도달 가능" 수준. **google API 가 외부 DNS resolve + TLS handshake + token refresh 까지 가능한 시점은 통상 boot+90s 이상**.

따라서 OnBootSec=60s 는 boot 직후 첫 fire 가 DNS 실패 또는 TLS handshake 실패로 exit 75 또는 timeout exit 2 — CRIT-R6-1 의 fatal loop 진입 위험.

**왜 위험한가**:
- 메인테이너 reboot 직후 항상 첫 사이클이 spurious failure 로 alert.
- alert fatigue.
- F1 archive 의 `OnBootSec=2min` 결정이 정합 lift 되지 않은 회귀.

**어떻게 고칠까**:
- §4.2 timer template 의 `OnBootSec` 을 **120s 이상** 으로 lock. F1 §4.8.2 lift 명시.
- 또는 vault-fetch.py 자체가 network 도달 가능 + token refresh 가능 시점까지 in-process wait (단 timeout 까지 5분 내 budget). v0.1.0 acceptance.

---

### HIGH-R6-4 [Security] curl-pipe + raw.githubusercontent.com 의 supply chain 위협 — install.sh 또는 latest tag 단일점 (`analysis_and_design.md` §3.8 [H] + ADR-0023)

**무엇이**: v3 §3.8 "보안 고려" 가 TLS 강제 + raw URL 도메인 신뢰 만 명시. README 의 SHA/GPG 비교는 v0.2.x 로 deferred. v0.1.0 acceptable 로 결정.

SRE 시각 위협 모델:
1. **GitHub 계정 탈취**: 메인테이너 (`im-dongseon`) credentials 탈취 → 공격자가 install.sh + latest tag 둘 다 갱신 → 다음 운영자 호출 시 mass compromise.
2. **CDN cache 변질**: raw.githubusercontent.com 은 Fastly/Cloudflare 캐시 통과. 캐시 TTL ~5분. 메인테이너가 새 install.sh push 한 직후 운영자가 stale install.sh 받을 가능성 — 운영 동작이 비결정.
3. **Tag race**: `git tag -f latest && git push --force` 자체가 race. 운영자가 force-push 도중 clone 하면 미완 tag 받을 수 있음.

v0.1.0 acceptance:
- 위협 1 (계정 탈취) 은 GPG 또는 SHA pin 으로만 완화 가능. v0.2.x 로 deferred 가 SRE 시각 acceptable (단 ADR 본문에 위협 모델 명시 필요).
- 위협 2 (CDN cache) 는 release 후 5~10분 wait 운영 절차로 완화 가능. ADR-0023 본문에 "release 절차" 항목 추가 필요 — "tag 갱신 후 10분 wait 후 announce".
- 위협 3 (tag race) 은 `git tag -f` 의 atomic 성을 git 이 보장 (single ref update). 다만 force-push 직후 mirror 동기화 latency 가 0 아님 — 동일 완화.

**어떻게 고칠까** — Step 3 진입 전 spec 변경:
- ADR-0023 본문에 **"v0.1.0 위협 모델 + 미완화 leak 항목"** 단락 신설:
  - "계정 탈취 → mass compromise" 가 미완화 leak 임을 명시.
  - v0.2.x 에서 GPG signed tag + install.sh 의 self-verify (e.g. `INSTALL_SHA256=... bash` 로 운영자가 release note 의 SHA 비교) 도입 commit.
- ADR-0023 본문에 **"release 절차"** 명시: 메인테이너가 `git tag -f latest && git push --force origin latest && sleep 600` 후 announce.
- install.sh 자체가 시작 시 `git ls-remote --tags origin latest` 의 SHA 와 `~/wikihub` clone 후 `git rev-parse HEAD` 의 SHA 일치 검증 — race 보호.

---

### HIGH-R6-5 [Idempotency] `git clone --branch latest --depth 1` + mutable tag — git client 가 stale clone 캐시 사용 가능 (`analysis_and_design.md` §4.1 Step 2)

**무엇이**: v3 의 clean install 패턴이 매 호출마다 `rm -rf ~/wikihub` 후 `git clone --branch latest --depth 1` 호출. tag `latest` 는 **mutable tag** (메인테이너가 매 release 마다 force-update).

git client 동작:
- `--branch <tag>` 는 tag 를 ref 로 fetch. **fresh clone 이므로 캐시 없음 — 매번 remote 의 현재 latest 가져옴**. mutability 문제는 없음 (clean install 이 이를 해소).
- 단 **메인테이너 dev box 또는 OCI 가 git daemon 캐시 또는 corporate proxy 뒤에 있으면** stale 가능.

SRE 시각: clean install 자체는 mutability 문제 해소 — 본 항목은 일부 환경 (corporate proxy) 에서만 영향. **다만 spec 에 명시 부재**. ADR-0023 본문에 "mutable tag 안전성은 fresh clone 에 의존 — proxy 캐시 우회 책임은 운영자" 한 줄 추가 권장.

---

### HIGH-R6-6 [Reliability / SpecMismatch] timer template 의 `OnUnitActiveSec` 와 F1 의 `OnUnitInactiveSec` 차이 — interval semantics 비호환 (`analysis_and_design.md` §4.2)

**무엇이**: v3 §4.2 timer:
```ini
OnUnitActiveSec={sync_interval_sec}s
```
F1 archive §4.8.2 timer:
```ini
OnUnitInactiveSec=10min
```

systemd semantics:
- `OnUnitActiveSec=600s` — 직전 service **활성화 시점** 으로부터 600s 후 다음 활성화. **service 가 600s 안에 종료 안 했으면 다음 fire 가 더 일찍 도래 가능** (단 oneshot 이므로 active 상태에서 fire 무시 — 결과는 같음).
- `OnUnitInactiveSec=600s` — 직전 service **inactive 진입 시점** (= 종료 시점) 으로부터 600s 후. service 가 9분 걸리면 다음 fire = 종료 + 600s = 19분 후.

운영 의도: vault 동기화는 "직전 사이클 종료 후 600s 대기" 가 자연 (Drive API rate limit / quota 측면도). F1 의 `OnUnitInactiveSec` 가 정합. F4 가 `OnUnitActiveSec` 으로 회귀 — 사유 spec 부재.

**왜 위험한가**:
- 정상 상황에서는 oneshot 의 active 가 ~30s 라 둘이 거의 같음.
- 그러나 vault-fetch.py 가 timeout (15분 = 900s) 까지 끌리면:
  - OnUnitActiveSec=600s → timeout 시점에 이미 active+600s=10분 경과 → systemd 가 fire 시도, 단 oneshot 이라 무시. 종료 후 즉시 fire (= 다음 사이클이 종료 직후 시작).
  - OnUnitInactiveSec=600s → timeout 종료 후 정확히 600s 대기.
- 결과: timeout 발생 시 fire interval 이 사실상 0s → vault stuck loop. CRIT-R6-1 의 fatal loop 와 결합 시 시너지.

**어떻게 고칠까**: §4.2 timer template 의 `OnUnitActiveSec` 을 **`OnUnitInactiveSec` 으로 변경**. F1 §4.8.2 lift. ADR-0021 본문에 정합 명시.

---

### HIGH-R6-7 [Reliability / DesignGap] F1 archive §4.8.2 의 `SuccessExitStatus=0 75` · `TimeoutStartSec=15min` · `OnFailure=ops-alert.service` 누락 (`analysis_and_design.md` §4.2)

**무엇이**: F1 archive §4.8.2 의 `gdrive-sync.service` 정본 spec 에 다음 directive 가 명시:
- `SuccessExitStatus=0 75` (CRIT-R6-1 fix 의 핵심)
- `TimeoutStartSec=15min` (sync.py 의 hard timeout)
- `[Unit] OnFailure=ops-alert.service` (fatal 알림 경로)

v3 §4.2 의 vault-ingest.service.template 에 **세 줄 모두 부재**. F1 정본의 surgical lift 누락.

**왜 위험한가**:
- `TimeoutStartSec` 부재 → vault-fetch.py 가 무한 stuck 시 systemd 가 kill 안 함. 다음 timer fire 무시 (oneshot 이라).
- `OnFailure=ops-alert.service` 부재 → exit 2 시 운영자 통지 경로 없음. v3 design 의 "ops-alert" 언급은 §6 V12 fail mode 에만 있을 뿐, 정본 spec 에 directive 없음.

**어떻게 고칠까**: §4.2 service template 에 세 줄 직접 추가 + F1 §4.8.2 의 unit 패턴 인용 명시.

```ini
[Unit]
Description=WikiHub vault ingest — {vault_id}
After=network-online.target
Wants=network-online.target
OnFailure=ops-alert.service       # F1 §4.8.2 lift

[Service]
Type=oneshot
WorkingDirectory={instance_root}
Environment=PATH={venv_path}/bin:/usr/bin:/bin
Environment=WIKIHUB_YAML={instance_root}/wikihub.yaml
ExecStart={agent_invocation} "{skill_prefix}ingest --vault {vault_id}"
SuccessExitStatus=0 75            # F1 §4.8.2 lift — CRIT-R6-1 fix
TimeoutStartSec=15min             # F1 §4.8.2 lift
Restart=on-failure
RestartSec=60
# 단 SuccessExitStatus 가 75 를 success 로 보면 Restart 트리거 안 됨 — timer 가 retry 책임
```

또한 ops-alert.service unit 자체의 spec 이 v3 design 어디에도 없음. F1 §4.8.2 lift 가 필요 — install.sh Step 5 또는 /wh:setup Step 2 가 ops-alert.service 도 생성하는 것으로 명시.

---

### HIGH-R6-8 [Concurrency] F3 의 fcntl.flock 도입과 systemd `Type=oneshot` 의 직렬화 보장 정합 — multi-vault timer 동시 fire 시 lock 동작 미명시 (`analysis_and_design.md` §4.2)

**무엇이**: F1 archive §4.8.4 가 multi-vault timer 동시 fire 시 직렬화 옵션 (i)·(ii)·(iii) 발의. F3 archive R4 의 HIGH-R4-2 fix 가 `fcntl.flock(LOCK_EX|LOCK_NB)` 도입 — concurrent run 시 `VaultSyncRetryable` (exit 75) 반환.

F4 design 의 `wikihub.yaml.example` 에 `max_concurrent_vaults: serial` 옵션 있으나 **systemd 측에서 직렬화 보장 directive 부재** (`Conflicts=`, `JobsRunningQueue=` 등).

운영 시나리오 (vault 2개, 동일 interval):
- gdrive-ingest.timer + nas-ingest.timer 가 동일 분에 fire.
- 두 service 가 동시 active. F3 의 fcntl.flock 은 **vault 별 state_dir/.lock** — 다른 vault 의 lock 은 침범 안 함. 즉 lock 은 단일 vault 내 concurrent run 만 차단 (CRIT-R6-1 의 RestartSec=60 vs interval=600s race 등).
- multi-vault 의 직렬화는 spec 외 — gdrive + nas 동시 fire 시 두 vault-fetch.py 가 동시 실행됨.

**왜 위험한가**:
- v0.1.0 의 단일 vault 시점에는 영향 없음. **v0.2.x 의 NAS vault 추가 시 spec gap 으로 표면화**.
- F3 가 `max_concurrent_vaults: serial` 을 yaml 옵션으로만 lock — 실제 enforce 책임이 어디에도 명시되지 않음.

**어떻게 고칠까** (spec 수준):
- §4.2 timer template 에 주석으로 "v0.1.0 = 단일 vault, multi-vault 직렬화는 F6 시점 별도 결정" 명시.
- 또는 v0.1.0 시점에 미리 service template 에 `Conflicts=` 또는 단일 multi-vault wrapper service (`wikihub-sync-all.service`) 옵션 발의.
- ADR-0019 본문의 "재검토 트리거" 에 **"multi-vault 직렬화 enforce 시점"** 추가.

---

## 3. MED (Step 3 도중 surface 가능)

### MED-R6-1 [Idempotency] Step 0 의 self-replace exec 무한 루프 검증 부족 (`analysis_and_design.md` §4.1 Step 0)

§4.1 Step 0 코드 스니펫:
```bash
if [ ! -t 0 ] && [ ! -e "${BASH_SOURCE[0]}" ]; then
    WIKIHUB_PIPE_MODE=1
fi
if [ "$WIKIHUB_PIPE_MODE" = "1" ]; then
    bootstrap_clone_then_exec "$@"
fi
```

self-replace 의도: curl-pipe → clone → `exec ~/wikihub/install.sh "$@"` → 두 번째 invocation 은 `BASH_SOURCE[0]=~/wikihub/install.sh` 존재 → `WIKIHUB_PIPE_MODE` 가 1 아닌 상태 → 정상 진행.

검증 필요:
- bash 의 `BASH_SOURCE[0]` 가 `exec` 후에도 실제 파일 경로로 set 되는지 검증 (curl 의 stdin 으로 받은 bash 는 BASH_SOURCE 가 빈 문자열). **`[ ! -e "" ]` 는 true** → curl-pipe 첫 호출에서 `[ ! -e "${BASH_SOURCE[0]}" ]` 가 true 로 평가 (의도 일치).
- 두 번째 호출 (`exec ~/wikihub/install.sh`) 에서는 BASH_SOURCE[0]=~/wikihub/install.sh — `-e` 가 true → `! -e` 가 false → pipe mode 진입 안 함 (의도 일치).
- **단, 두 번째 호출에서도 stdin 이 curl pipe 인 경우** (rare — e.g. `bash <(curl …)` + `exec` 가 stdin 유지) → `[ ! -t 0 ]` 가 true + `[ ! -e ... ]` 가 false → `&&` 가 false → pipe mode 진입 안 함. 정합.

**SRE 결론**: 로직 자체는 일관. 다만 **두 번째 호출에서 stdin 처리** 가 §4.1 spec 에 미정 — `exec` 가 stdin 을 closure 하는지 / 유지하는지. Step 7 의 `< /dev/tty` 가 두 번째 호출에서도 동작해야 함 → spec 명시 권장.

§4.1 Step 0 의 `bootstrap_clone_then_exec` 함수 본문이 spec 외 (구현 위임). 함수가 stdin 을 `< /dev/null` 로 닫고 `exec` 하는지 명시 필요.

---

### MED-R6-2 [Reliability] WIKIHUB_HOME normalize 절차의 corner case (`analysis_and_design.md` §4.1 Step 2)

`WIKIHUB_HOME` normalize 코드:
```bash
WIKIHUB_HOME="$(cd "$(dirname "$WIKIHUB_HOME")" 2>/dev/null && pwd)/$(basename "$WIKIHUB_HOME")" || true
```

corner cases:
1. `WIKIHUB_HOME=/foo/bar/` (trailing slash) → `dirname` = `/foo/bar`, `basename` = `bar` → normalized = `/foo/bar/bar` (잘못).
2. `WIKIHUB_HOME=~/wikihub` (literal `~`, not expanded) → cd 에서 fail → `pwd` 빈 → normalized = `/wikihub` (시스템 path safety guard 가 catch — 정합).
3. `WIKIHUB_HOME=` (빈 문자열) → safety guard 가 catch (정합).
4. `WIKIHUB_HOME=symlink-to-dev-box-repo` → `cd` 가 symlink 따라감 → normalized = symlink target. safety guard 2 (`.git` + origin remote) 가 catch — 정합.
5. `WIKIHUB_HOME=./relative/path` (relative) → `dirname` = `./relative`, cd 후 pwd = `/current/dir/relative` → normalized = `/current/dir/relative/path` (정합).
6. `WIKIHUB_HOME=/` (정확히 루트) → safety guard 1 case statement 의 `"/"` 가 catch (정합).
7. `WIKIHUB_HOME=$HOME` (정확히 home) → safety guard 의 `"$HOME"` 가 catch (정합).

**유일한 미해결 = (1) trailing slash**. fix:
```bash
WIKIHUB_HOME="${WIKIHUB_HOME%/}"   # trailing slash 제거
```
normalize 전에 추가 필요. §4.1 Step 2 spec 보강.

---

### MED-R6-3 [Reliability] Step 4 의 gws GitHub API call rate limit 미설명 (`analysis_and_design.md` §4.1 Step 4)

§4.1 Step 4 의 latest tag 조회:
```bash
GWS_VERSION=$(curl -fsSL https://api.github.com/repos/googleworkspace/cli/releases/latest | grep '"tag_name"' | ...)
```

GitHub API 의 unauthenticated rate limit = **시간당 60회 / IP**. 메인테이너 + 여러 운영자 + CI 가 동일 OCI 외부 IP 를 공유하는 경우 가능.

운영 영향:
- 60회 도달 시 install.sh 의 latest tag 조회가 403 → install.sh exit 1.
- 운영자에게 "rate limit" 이라는 의미 있는 stderr 노출 필요. 현재 §4.1 Step 4 는 curl -fsSL 의 silent fail 만 — exit code 만 보임.

**어떻게 고칠까**:
- §4.1 Step 4 에 `curl -fsSL --retry 3 --retry-delay 5` 추가 + 403 응답 시 명시 안내.
- 또는 `GWS_VERSION` env 가 `latest` 일 때 GitHub API 우회하여 `git ls-remote --tags https://github.com/googleworkspace/cli.git` 으로 latest tag 추출 (rate limit 없음, anonymous).

---

### MED-R6-4 [Observability] install.sh 자체의 로그 경로 미정 (`analysis_and_design.md` §4.1, §5)

§4.1 의 모든 Step 이 stdout 으로 직접 echo. curl-pipe 모드에서:
- 운영자가 `bash <(curl …)` 또는 `curl … | bash` → stdout 이 운영자 터미널.
- `bash <(curl …) > /var/log/wikihub-install.log` 같은 redirect 가 운영자 책임 — spec 부재.

install.sh 실패 후 운영자 debugging 경로:
- journalctl 에는 install.sh 자체의 stdout 안 들어감 (systemd 외).
- 운영자가 직접 stderr 봐야 함 — terminal close 시 lose.

**어떻게 고칠까**: §4.1 Step 0 또는 Step 1 에 **자체 log file** 정책 추가:
```bash
exec > >(tee -a "$HOME/.local/share/wikihub/install.log") 2>&1
```
- log file 위치: `~/.local/share/wikihub/install.log` (XDG_DATA_HOME 정합).
- 매 install.sh 호출이 append → 운영 trail 보존.

또는 spec 에서 "운영자가 redirect 책임" 으로 명시 — 단 24/7 daemon 인프라 정신상 자동 log 가 정합.

---

### MED-R6-5 [Reliability / DesignGap] Python 3.11+ 의 Ubuntu 22.04 apt 가용성 spec 부재 (`analysis_and_design.md` §4.1 Step 1)

§4.1 Step 1: "Python 3.11+ 또는 3.12+ 존재 확인. 없으면 `apt install python3-venv python3-pip`."

Ubuntu 22.04 default = Python 3.10. `apt install python3-venv` 는 3.10 venv 만 설치. Python 3.11+ 강제하려면:
- `apt install python3.11 python3.11-venv` (deadsnakes PPA 필요) — system 변경 큼.
- 또는 pyenv / asdf — 별도 의존성.
- 또는 v0.1.0 의 Python 요구사항을 **3.10+** 으로 완화 (F3 의 `process_group=0` 가 Python 3.11+ 라 일부 fix 회귀 — 단 v3 본문은 3.11+ 명시).

Ubuntu 24.04 default = 3.12 (정합).

**왜 위험한가**:
- 22.04 운영자가 `apt install python3-venv` 한 후 install.sh 가 `python3.11 --version` 검증 fail → exit 1. 운영자 혼란.
- spec 이 "3.11+ 필요" 만 명시, 22.04 절차 미정.

**어떻게 고칠까**: §4.1 Step 1 에 분기 명시:
- Ubuntu 22.04 → `deadsnakes` PPA add → `apt install python3.11-venv` (sudo). 또는 24.04 권장.
- Ubuntu 24.04 → `apt install python3-venv` 만.
- 또는 v0.1.0 의 Python 요구사항을 3.10+ 로 완화 (F3 본문 검증 후).

ADR-0020 본문에 Python 최소 버전 + 배포 절차 명시.

---

### MED-R6-6 [Reliability] gws ARM64 binary 의 release asset 이름 검증 미완료 (`analysis_and_design.md` §4.1 Step 4)

§4.1 Step 4 의 starting draft 가 `ASSET="gws-${OS}-${ARCH}.tar.gz"` 패턴 사용. v3 본문 자체에 **"V8 후속에서 정확한 asset 이름 확정"** 명시 — 즉 Step 3 진입 전 미해결.

SRE 시각 위험:
- googleworkspace/cli 가 ARM64 binary 를 제공 안 하면 → CH3 (npm) 또는 build-from-source 로 회귀 → install.sh 전면 재작성.
- V8 verification 이 fail 하면 ADR-0023 (curl-pipe 단일 install.sh) 의 idempotency 가 약화.

**어떻게 고칠까**: Step 3 진입 전에 V8 hand-check 완료 — design v4 또는 plan.md 의 fixed.

---

### MED-R6-7 [Security] credentials path 누설 risk lift (`analysis_and_design.md` §4.3)

`wikihub.yaml.example` 의 `credentials_path: ~/wikihub-instance/.credentials/token_gdrive.json`. F3 의 MED-R4-6 (credentials_path 가 fatal reason 메시지에 노출) 이 archive 됐는지 ADR-0017 본문 검증 필요.

v3 본문 §5 의 lift 매트릭스에는 ADR-0017 만 언급 — F3 의 MED-R4-6 fix 가 ADR-0017 의 scope 안에 들어가야 함. 만약 별도 ADR 또는 별도 fix 라면 F4 가 surface 해야.

---

### MED-R6-8 [Compatibility] git 의존 미명시 (`analysis_and_design.md` §4.1 Step 1)

§4.1 Step 1 의 환경 검증에서 `git` binary 존재 검증 부재. Step 2 가 `git clone` 호출 시 git 미설치면 silent fail (또는 exit 127).

OCI 의 cloud-images Ubuntu 22.04/24.04 default 는 git 포함. 그러나:
- custom image (cloud-init disabled, slim image) 일 가능성.
- corporate image 가 git 제외할 가능성.

**어떻게 고칠까**: §4.1 Step 1 에 `command -v git || apt install git` 한 줄 추가 — sudo 필요. linger 활성화와 동일 sudo budget.

---

## 4. LOW / NIT

### LOW-R6-1 [Observability] §4.2 timer template 의 `Persistent=true` semantics — 다중 missed fire 처리 명세 부족

`Persistent=true` 는 reboot 중 놓친 fire 를 부팅 후 **단 1회** catch up (F1 §4.8.3 명시). 그러나 v3 §4.2 timer template 의 주석은 "reboot 중 놓친 fire 를 부팅 후 catch up" 만 — 다중 missed fire 가 1회로 collapse 됨을 명시 안 함. 운영자 혼선 가능.

**fix**: §4.2 timer template 주석에 "(중복된 missed fire 는 1회로 collapse — backlog 안 만듦)" 추가.

---

### LOW-R6-2 [Idempotency] §4.1 Step 4 의 `gws --version` parsing — fragile (`analysis_and_design.md` §4.1 Step 4)

```bash
if command -v gws &>/dev/null && gws --version 2>/dev/null | grep -q "$GWS_VERSION"; then
```
gws --version 출력 형식이 alpha 라 변동 가능 (예: `gws version 1.2.3` vs `1.2.3` vs `v1.2.3`). `grep -q "$GWS_VERSION"` 의 substring match 가 우연 match 가능 (e.g. `0.1.0` 이 `10.1.0` 에 substring).

**fix**: §4.1 Step 4 에 정확한 version compare 함수 spec 추가 또는 V6 verification 에 포함.

---

### NIT-R6-1 [Observability] §4.2 service template 의 stdout/stderr 라우팅 미명시

F1 §4.8.2 는 `StandardOutput=append:/opt/wikihub/logs/sync.log` 명시. v3 §4.2 는 없음. journal 기본 (default) — 단 명시 부재.

**fix**: §4.2 service template 에 명시:
```ini
StandardOutput=journal
StandardError=journal
```
또는 F1 의 file append 패턴 lift. ADR 또는 spec 결정.

---

### NIT-R6-2 [Code Quality] §4.1 Step 7 의 sudo redirect — 안내 메시지 의도 vs 실제 비일치

§4.1 Step 1 의 sudo pre-check 안내:
```
INFO: sudo 권한이 필요합니다 (linger 활성화 Step 7 에서 1회). 진행 시 password prompt 가 나타날 수 있습니다.
```
"1회" 라고 안내했으나 MED-R6-8 fix (git 자동 설치) + Step 7 (linger) → 사실상 sudo 2회. spec 정합 갱신 필요.

---

## 5. SRE 관점 강점 (잘 정렬된 부분)

본 검토는 결함 surface 목적이지만 다음 항목은 production-grade SRE 표준 만족:

1. **clean install pattern (ADR-0023)** — `rm -rf + git clone` 이 update idempotency 의 가장 안전한 형태. 운영 state 분리 (`~/wikihub-instance` 별도 경로) 도 정합.
2. **safety guard 3개 (ADR-0023)** — 시스템 path / `.git` 검증 / origin remote 검증의 layered defense 가 dev box 보호에 SRE 표준 정합. 사용자가 직접 결정한 매트릭스가 SRE 시각에서도 견고.
3. **`SuccessExitStatus=0 75` 의도** — exit code semantics 와 systemd Restart 정책의 분리가 ADR-0006 unified orchestration 과 정합. 단 CRIT-R6-1 의 spec 누락만 fix 하면 prod-ready.
4. **user-level + linger 패턴 (ADR-0021)** — root 권한 노출 최소화. F1 정합.
5. **첫 ingest prompt + bootstrap_allowed 자동 환원 (ADR-0022)** — 운영자 통제와 자동화의 균형. 단 CRIT-R6-3 만 fix 하면 SRE-ready.
6. **V12 fallback 절차 (D2 회귀) lock** — failure mode 별 마이그레이션 절차 사전 정의가 SRE 의 disaster recovery 표준 정합. v2 의 surface 가 적절.
7. **`exit 1` (환경 결함) vs `exit 2` (install 도중 결함)** 분리 — 운영자 debugging 진입점 명확.
8. **EUID != 0 assert + sudo pre-check** — silent hang 회피의 fail-loud 원칙 정합 (단 HIGH-R6-1 의 변수명 명시만 보강).

---

## 6. 종합 권고

### Step 3 진입 차단 (CRIT — design v4 에서 lock 필수)

1. **CRIT-R6-1**: §4.2 service template 의 `SuccessExitStatus=0 75` 추가 + `Restart=` 주석 정합. F1 §4.8.2 lift.
2. **CRIT-R6-2**: StartLimit 도달 후 자동 회복 부재 — ADR-0021 fail mode (iv) 추가 + fallback 절차 lock.
3. **CRIT-R6-3**: ADR-0022 본문에 "첫 ingest 성공 후 timer enable" 순서 lock. /wh:setup `--enable` 의 단계 순서 변경.

### Step 3 진입 전 spec 보강 (HIGH — design v4 또는 명시 보강)

4. **HIGH-R6-1**: §4.1 의 비대화 모드 정규화 단락 신설.
5. **HIGH-R6-2**: §4.1 Step 4 의 trap cleanup + V11 spec 에 partial install 회복 시나리오 추가.
6. **HIGH-R6-3**: §4.2 timer 의 `OnBootSec` 을 120s 이상으로 lock. F1 lift.
7. **HIGH-R6-4**: ADR-0023 본문에 위협 모델 + release 절차 (`sleep 600`) 명시.
8. **HIGH-R6-5**: ADR-0023 에 mutable tag + proxy 캐시 단락 추가.
9. **HIGH-R6-6**: §4.2 timer 의 `OnUnitActiveSec` → `OnUnitInactiveSec` 변경. F1 lift.
10. **HIGH-R6-7**: §4.2 service template 에 `TimeoutStartSec=15min` + `OnFailure=ops-alert.service` 추가. ops-alert.service unit 자체 spec 도 §4.2 에 lift.
11. **HIGH-R6-8**: multi-vault 직렬화 책임 lock — §4.2 주석 + ADR-0019 재검토 트리거 보강.

### Step 3 도중 surface 가능 (MED — Step 3 v 구현 도중 자가 검증)

12. **MED-R6-1**: §4.1 Step 0 의 self-replace exec 의 stdin 처리 명시.
13. **MED-R6-2**: WIKIHUB_HOME trailing slash 제거.
14. **MED-R6-3**: GitHub API rate limit 대응.
15. **MED-R6-4**: install.sh 자체 log file 정책.
16. **MED-R6-5**: Python 3.11+ 의 Ubuntu 22.04 절차 명시.
17. **MED-R6-6**: V8 hand-check 의 asset 이름 확정 (Step 3 진입 전).
18. **MED-R6-7**: ADR-0017 의 credentials path 누설 fix scope 검증.
19. **MED-R6-8**: §4.1 Step 1 에 git 의존성 검증.

### LOW/NIT (Step 4 code review 단계에서 처리 가능)

20. **LOW-R6-1**: `Persistent=true` 의 1회 collapse semantics 주석.
21. **LOW-R6-2**: `gws --version` 의 정확 version compare.
22. **NIT-R6-1**: stdout/stderr 라우팅 명시.
23. **NIT-R6-2**: sudo "1회" 안내 정합.

### 종합 판정

design v3 의 의도와 ADR 매핑은 **production 진입 가능 방향**으로 정렬되어 있다. 그러나 **CRIT 3건 (특히 CRIT-R6-1 systemd exit code 매핑 모순) 은 Step 3 진입 차단** — 구현이 시작되면 spec 모호가 그대로 코드에 새겨져 V10/V12 verification 단계에서 surface 시 spec 으로 회귀해야 함. **design v4 에서 §4.2 service template + ADR-0021 + ADR-0022 세 정본을 한 라운드에 lock 한 후 Step 3 진입 권장**.

HIGH 8건은 design v4 에서 같이 처리 가능 — 모두 spec 본문 수정 수준이며 추가 검증 부담 작음. F1 archive §4.8.2 의 unit spec 을 surgical lift 하면 7개 중 4개 (HIGH-R6-3·6·7 + CRIT-R6-1) 가 한 번에 해소된다 — design v3 가 F1 정본을 incomplete lift 한 회귀가 본 검토의 가장 큰 finding.

추정 명시:
- gws ARM64 binary 의 GitHub Releases 가용성은 V8 hand-check 결과를 본 검토자가 확인하지 못함 (design 본문의 V8 starting fact 결론 ("googleworkspace/cli" + 3개 channel) 만 입력).
- OCI ARM Ubuntu 의 cloud-init + network-online 타이밍 (HIGH-R6-3) 은 일반 OCI 운영 패턴 추정 — 실제 검증은 V12 verification 단계에서.
- mutable tag 의 git proxy 캐시 (HIGH-R6-5) 는 corporate proxy 환경 추정 — 본 운영 환경 (OCI free tier) 에서는 비해당 가능.

본 R6 검토를 R5 (있다면) 와 비교 후 공통 지적 항목 우선순위화 + design v4 lock 진행 권장.
