# Design Review #1 — update_mode (spec internal consistency)

- **Reviewer**: Claude Sonnet 4.6 (subagent, spec angle)
- **Date**: 2026-05-17
- **Target**: features/20260517_update_mode/analysis_and_design.md v1

## Summary

설계는 ADR-0010 의 dual-mode lifecycle 회복이라는 큰 골조는 정합하나, **curl-pipe entrypoint 와 update path 의 진입 순서 충돌**(CRIT-1) 및 **자가 호출 cycle (install.sh → /wh:setup → install.sh)** 위험(CRIT-2)이라는 구조적 결함 2건이 있다. 그 외 ADR-0010 의 `latest` 의미와 §4 ref resolution 의 의미 충돌(HIGH-1), V10 검증 불가능(HIGH-2), Step 6 systemd unit template render 누락(HIGH-3) 등 HIGH 3건, MED/LOW 다수. 총 CRIT 2 · HIGH 4 · MED 5 · LOW 4.

## Findings

### CRIT-1: curl-pipe bootstrap 이 무조건 `_step2_clone` 호출 → update path 의 unstaged guard 우회

**File/section**: `install.sh:93-103, 111-119, 687-692` vs `analysis_and_design.md §3 Step 0, §3 main flow (L249-281)`

**Issue**: 설계의 main flow 는 `_pipe_mode_detect → bootstrap_clone_then_exec` 가 가장 먼저 실행되고, `bootstrap_clone_then_exec` 는 현행 `_step2_clone` 을 호출한다 (`install.sh:96`). 즉 curl-pipe 호출이라면 **mode detect 보다 먼저 `rm -rf $WIKIHUB_HOME` 가 일어난다** (`install.sh:222`). 운영 시 메인테이너의 표준 update 경로는 그대로 curl-pipe 인데 (`README.md:155` 갱신 후에도 동일), 이 경로는 설계 §3 Step 0/Step 2 가 보호하려는 unstaged guard·user 파일 보존 invariant 를 통과조차 못 한다. 결함 #B 가 닫히지 않는다.

**Evidence**:
- `install.sh:111` `if _pipe_mode_detect; then ...` 분기에서 즉시 `bootstrap_clone_then_exec` 호출
- `install.sh:96` 이 함수는 `_step2_clone` (wipe + clone) 을 무조건 부른다
- 설계 §3 main flow L250 `if _pipe_mode_detect; then bootstrap_clone_then_exec "$@"; fi` — 그대로 유지한다고 명시
- 결과: curl-pipe 호출 → wipe → exec 새 install.sh → 새 process 에서 `_detect_mode` 가 돌지만 이미 `_system/VERSION` 은 새 clone 의 것 → 무조건 `fresh` 분기

**Suggested fix**:
- Option A: bootstrap_clone_then_exec 를 **mode-aware** 로 분기. `_pipe_mode_detect` 직후 raw URL 의 install.sh 가 `$WIKIHUB_HOME/_system/VERSION + .git` 만 sniff (rm 전) → update mode 면 self-replace 없이 in-place `exec bash "$WIKIHUB_HOME/install.sh" "${ORIGINAL_ARGS[@]}"` 만 수행. (clone 책임 위임 — `_step2_update` 가 fetch+reset 으로 갱신).
- Option B: curl-pipe 진입점 자체를 분리 (`update.sh` 별도). ADR-0010 의 "동일 curl 1줄" 위배라 비추천.
- Option A 채택 시 §3 Step 0 의 detect 로직을 bootstrap_clone_then_exec 전에 이동해야 함을 명시.

---

### CRIT-2: Step 8 `_step8_wh_setup` 이 호출하는 `/wh:setup` 의 substitution 책임이 미해결 → 자기 호출 cycle 가능성

**File/section**: `analysis_and_design.md §3 Step 6 (L156-158)`, `§3 Step 8 (L163-180)`, `_system/commands/setup.md §Step 2 (L46-86)`

**Issue**: 설계는 update path 에서 `_step6_agent_skill` 만 호출하고 systemd unit template render 는 `/wh:setup` 가 책임진다고 가정한다 (§3 Step 8). 그런데 `setup.md §Step 2` 는 unit template substitution 본체 — 즉 update path 의 unit 갱신이 install.sh 가 아니라 `/wh:setup` 에 의해 일어난다. 동시에 `/wh:setup` 의 §Step 6 (첫 ingest prompt + bootstrap_allowed flip) 은 update 호출에서는 부적합하다 (이미 first ingest 완료). 설계는 `--reorchestrate` flag 로 분기한다고 하나 (§3 Step 8 L179) 이 flag 의 의미 경계가 §7 O1 에서 여전히 **미결**로 남아 있다. Step 2 종료 시점에 미결이면 Step 3 진입 자체가 막힌다 (CLAUDE.md §3 Step 2 진입 조건: 미결 사항 없음 또는 결정 명시).

또 hermes 미설치 시 (`§3 Step 8 L172`) warn-only 로 return 0 — 그러면 unit template render 가 **아예 수행되지 않는다** → 결함 #D 가 update 의 hermes 부재 경로에서 닫히지 않는다. F5 미완 상태에서 hermes 부재는 default 시나리오인데도 설계는 이 gap 을 §3 Step 8 L173 "수동 호출 안내" 로만 처리하고 §9 DoD V10 은 자동 반영을 요구한다 — 자기 모순.

**Evidence**:
- `analysis_and_design.md:179` `--reorchestrate 는 /wh:setup 가 받는 flag (Step 3 구현 시 setup.md 갱신)` — Step 2 단계에서 의미 미정
- `analysis_and_design.md:350` O1: `별도 flag 두지 말고 /wh:setup 자체가 fully idempotent` 추천 — Step 2 미결로 surface
- `analysis_and_design.md:172-176` hermes 미설치 시 `warn ... return 0`
- `analysis_and_design.md:402` V10 `systemd unit template 변경 사항이 active service 에 반영` — hermes 없이는 불가능한 검증

**Suggested fix**:
- O1 을 Step 2 lock 시점에 결정. 권장: 추천대로 `--reorchestrate` flag 제거, `/wh:setup` 자체가 idempotent. 설계 §3 Step 8 의 `hermes -z "/wh:setup"` 만 유지.
- hermes 미설치 path 의 대응: **fallback 으로 install.sh 가 직접 unit template render + daemon-reload + restart** 수행 (즉 `_step8_systemd_render` 를 hermes 의존성 없이 in-script 로 구현). hermes 는 skill 메타 갱신만 책임.
- F5 미완 상태에서 V10 acceptance 불가능을 §9 에 명시하든가, in-script fallback 으로 V10 가능하게 만들든가 둘 중 하나.

---

### HIGH-1: ADR-0010 의 `latest` (이동 태그) 와 §4 의 `latest` (semver sort) 의미 충돌

**File/section**: `docs/adr/0010-…md:59, 84-86`, `docs/adr/0023-…md:36`, `analysis_and_design.md §4 (L287-300)`

**Issue**: ADR-0010 §Decision (L59) 은 `tag latest (이동 태그, 항상 현재 stable release 가리킴)` 이며 L84-86 은 release 절차로 `git tag -f latest <commit> && git push -f origin latest` 를 명문화한다. ADR-0023 §Decision L36 도 동일 — `tag latest 는 mutable — 메인테이너가 release 마다 git tag -f latest && git push --force origin latest`.

설계 §4 는 path 3 으로 `git ls-remote --tags origin | grep ... | sort -V | tail -1` (semver sort) 를 default 로 두고 (L291) "ADR-0010 의 `latest` 는 본 feature 에서 **derive** (path 3) — origin 에 별도 `latest` tag 부여 불필요" 라고 주장한다 (L300).

이는 **ADR-0010 spec 변경이지 conformance 회복이 아니다**. ADR-0010 L84-86 의 release 절차가 `git tag -f latest` 를 운영 책임으로 명시한다. 또한 curl-pipe entrypoint URL 자체가 `https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh` (ADR-0023 §Decision L33) — 이 URL 은 git tag `latest` 가 origin 에 존재해야 동작. semver sort 로 derive 한 결과는 install.sh 내부 일관성에는 통할지 몰라도, curl-pipe URL 자체는 여전히 origin tag `latest` 가 필요하다.

설계는 이 비대칭을 인지 못 한 채 path 3 만으로 충분하다고 주장 — ADR-0030 가 ADR-0010 보강이 아니라 부분 supersede 가 되어버리는데, 그 점이 명시되지 않음.

**Evidence**:
- ADR-0010 L84-86 — release 절차의 `git tag -f latest` 가 정본
- ADR-0023 L33 — raw URL 이 `/latest/install.sh` 로 origin tag `latest` 의존
- `analysis_and_design.md:300` — `별도 latest tag 부여 불필요` 주장
- `analysis_and_design.md:296` — `본 feature ship 시점에는 origin tag 부재 → fallback 4 path 활성` — 이 시점에 curl-pipe URL 도 동작 불가 (`/latest/install.sh` → 404)

**Suggested fix**: 둘 중 택일.
- A. ADR-0010 의 `latest` 정본 유지 — 설계 §4 path 3 의 semver sort 를 제거하고, origin `latest` tag 를 ADR-0010 L84-86 절차대로 메인테이너가 push. 설계는 그 tag 를 resolve 만 한다. v0.1.0 spec 완성 시 메인테이너가 tag cut + tag latest 동시 push.
- B. 명시적 ADR-0030 가 ADR-0010 의 `latest` 의미를 supersede 함을 선언. 그러면 curl-pipe URL 도 `/main/install.sh` 또는 새 ref 로 바꿔야 함 (ADR-0023 갱신).

---

### HIGH-2: V10 검증 불가능 — template 변경 없으면 effect 없음

**File/section**: `analysis_and_design.md §9.2 V10 (L402)`

**Issue**: V10 은 `/wh:setup` 자동 호출 후 systemd unit template 변경 사항이 active service 에 반영됨을 verify 하라고 하면서 예시로 `mount template 의 --vfs-cache-max-size 갱신` 을 든다. 그러나 본 feature 의 §6 Cross-file impact (L337) 는 `_system/systemd/*.{service,timer}.template — 무영향 (template 자체는 미변경)` 으로 명시한다. 즉 template 미변경 state 에서 V10 은 **불가능한 검증** (변경된 게 없는데 반영 여부를 어떻게 검증?).

이는 검증자가 v0.1.0 단발 검증으로는 통과시킬 수 없다. 별도 fixture commit (template 일부러 갱신) 을 만들고 그걸로 update flow 회전을 돌려야 V10 검증 가능.

**Evidence**:
- `analysis_and_design.md:337` template 무영향 선언
- `analysis_and_design.md:402` V10 이 template 변경 반영을 요구

**Suggested fix**: V10 을 "검증 fixture: template 의 한 placeholder 추가/제거 commit → `update_mode` 호출 → active service 의 `systemctl show` 결과에 반영" 으로 명시화. 또는 V10 을 "active service 의 `Environment=` 가 install.sh 가 render 한 값과 byte-equal" 형태의 weak verifier 로 약화.

---

### HIGH-3: Step 6 `_step6_agent_skill` 가 update 에서 systemd unit render 책임을 갖는지 미정

**File/section**: `analysis_and_design.md §3 Step 6 (L156-158)`, `setup.md L46-86, L82`

**Issue**: 현행 install.sh L564-569 `_step6_agent_skill` 는 v0.1.0 stub 으로 systemd unit render 안 함. systemd unit template render 는 `setup.md §Step 2` (`Step 6 _step6_agent_skill 또는 /wh:setup 의 본 Step 2 가 호출`, L82) 의 ambiguous claim 만 존재 — 즉 책임자가 install.sh 인지 /wh:setup 인지 정본화 안 됨. 설계는 §3 Step 6 에서 "agent skill 메타 재등록 — 기존 유지" 라고만 하고 systemd render 는 Step 8 의 `/wh:setup` 위임. 그러나 fresh path 도 Step 6 후 Step 7 linger → Step 8 guide 만 — fresh 도 systemd render 미수행. 즉 **install.sh 단독으로 unit 파일을 만들지 않는다**.

그러면 fresh install 직후 (yaml 편집 전) 운영자가 `/wh:setup` 호출 전까지 `~/.config/systemd/user/wikihub-*` 자체가 비어 있다. update path 의 §3 Step 9 `_systemd_start_after_update` 가 `systemctl --user start wikihub-mount@...` 하면 unit 부재 → fail.

설계가 가정하는 invariant: update 이전에 운영 중이면 unit 은 이미 deploy 됨 (이전 `/wh:setup` 호출 결과). 그 가정은 §3 Step 9 가 의존하는 핵심 precondition 인데 §3 어디에도 명시 안 됨. precondition 누락은 race·rollback 경로에서 silent fail 위험.

**Evidence**:
- `install.sh:564-569` 현 stub
- `setup.md:82` ambiguous claim
- `analysis_and_design.md:157` "변경 가능성 낮음, idempotent" — render 책임 회피
- `analysis_and_design.md:182-198` Step 9 가 unit 존재 가정

**Suggested fix**: §3 Step 9 의 precondition (이전에 `/wh:setup` 1회 이상 호출되어 unit 이 존재) 을 명시. 또는 §3 Step 8 의 `_step8_wh_setup` 이 hermes 부재 시에도 unit render 만큼은 in-script 로 fallback 수행 (CRIT-2 의 fix 와 짝).

---

### HIGH-4: `--version` flag 와 기존 `--gws-version` 의 의미 충돌

**File/section**: `install.sh:76`, `analysis_and_design.md §4 (L289)`

**Issue**: install.sh 현행 CLI 는 `--gws-version <ver>` 를 받고 `GWS_VERSION` env 도 별도 존재 (gws CLI 버전 pin 용, L32). 설계 §4 는 새로 `--version <tag>` flag 도입 — wikihub 자체 version pin 용. 두 flag 의 의미 차이는 일관되지만 사용자 입장에서 `--gws-version` 와 `--version` 의 namespace 가 일관되지 않다 (`--wikihub-version` 또는 `--ref` 가 더 명확).

특히 `--version` 은 GNU CLI 관례상 "프로그램 자체 버전 출력" 으로 흔히 쓰임 (`install.sh --version` → 0.1.0 출력) — 운영자가 헷갈리기 쉽다.

ADR-0010 §Decision L66 가 `--version v0.1.0` 을 그대로 명시하므로 spec 정합성 측면에서는 이 flag 이름이 정본이지만, naming 자체에 대한 ADR 결정 흔적이 없다 — ADR-0010 의 1회성 사용 예시일 뿐.

**Evidence**:
- `install.sh:76` `--gws-version`
- ADR-0010 L66 `--version v0.1.0`
- `analysis_and_design.md:289` 그대로 채택

**Suggested fix**: ADR-0030 에 flag naming 결정을 명시. 또는 `--version` 의 GNU 관례 충돌을 인지하고 `install.sh --version` (인자 없음) 호출 시 program version 출력 분기 추가 — 인자 있으면 ref pin, 없으면 version print.

---

### MED-1: 결함 #A closure 가 incomplete — BRANCH=latest 의 silent fallback path 미커버

**File/section**: `analysis_and_design.md §4 (L290-291)`, `install.sh:31`

**Issue**: 결함 #A 는 "BRANCH default=latest 가 GitHub 부재 — release 전략 미정" (backlog.md L13). 설계 §4 우선순위 2 (`BRANCH env 또는 --branch <name> flag 명시 → branch name 직접 (back-compat)`) 가 그대로 유지. 그런데 install.sh:31 의 default `BRANCH="${BRANCH:-latest}"` 는 그대로면 path 2 진입 — `latest` 를 branch name 으로 해석. branch `latest` 부재 → `git clone --branch latest` fail (현행 #A 와 동일 증상).

설계는 path 3 (semver sort) 를 default 라고 했지만 BRANCH env 의 default 가 `latest` 인 한 path 2 가 우선 매칭됨. install.sh:31 의 default 를 `BRANCH=""` 로 바꿔야 path 3 진입. 설계는 이 변경을 §3 Step 0 / §4 어디에도 명시하지 않음.

**Evidence**:
- `install.sh:31` `BRANCH="${BRANCH:-latest}"`
- `analysis_and_design.md:290` path 2 `BRANCH env 또는 --branch <name> flag 명시 → branch name 직접`
- `analysis_and_design.md:291` path 3 가 default — 그러려면 BRANCH env 가 empty 여야 함

**Suggested fix**: §3 Step 0 또는 §4 에 명시: `BRANCH` env default 를 빈 문자열로 변경, path 2 는 사용자가 명시적으로 export BRANCH=<name> 또는 `--branch <name>` 호출 시에만 진입. (install.sh:31 의 default 값 갱신 항목을 §6 impacted files 에 추가).

---

### MED-2: U3·U4 가 plan.md 에서 lock 됐다 했으나 §7 미결 항목이 surface

**File/section**: `plan.md L60-66`, `analysis_and_design.md §7 (L348-353)`

**Issue**: plan.md 는 U1~U5 가 "사용자 confirm 으로 lock 완료" (L57) 라고 했고 그중 U3 (unstaged 보호) · U4 (systemd orchestration) 는 신규 ADR-0030 후보. 그런데 analysis_and_design.md §7 미결 O1 (`--reorchestrate` 의미) · O2 (`_enabled_vaults` 구현) 가 새로 surface. CLAUDE.md §3 Step 2 의 종료 조건은 "사용자의 명시적 승인". 미결 항목 surface 후 사용자 승인 없는 상태에서 Step 3 진입 불가.

이 자체는 미결 surface 가 잘못된 건 아니지만, plan.md 의 lock 선언과 §7 surface 사이의 trace 가 안 됨 — plan.md 에서 `미결 사항 없음` 이라 했지만 design 단계에서 O1·O2 추가 surface 됐다고 명시할 필요. 사용자가 이 차이를 인지 못 하고 승인 가능.

**Evidence**:
- `plan.md:56` `미결 사항 (사용자 confirm 으로 lock 완료 — 2026-05-17)`
- `analysis_and_design.md:348` 미결 O1·O2

**Suggested fix**: §7 도입부에 "plan.md 의 U1~U5 는 lock. 설계 진행 중 surface 한 신규 미결 (O1·O2) 만 본 표에 기재" 를 명시. 그리고 O1·O2 가 Step 3 진입 전 lock 필요한지, Step 3 구현 단계에서 lock 해도 무방한지 명시.

---

### MED-3: `_enabled_vaults` 가 venv 의존 — Step 0 / Step 2c 의 stop sequence 호출 시점에는 venv 미생성 가능

**File/section**: `analysis_and_design.md §3 Step 2 (L116-118), §7 O2 (L351)`, `setup.md L60-86` (helper Python)

**Issue**: §3 Step 2c 의 `_systemd_stop_before_update` 가 enabled vault 목록을 알아야 stop 대상 systemd unit (`vault@<id>.timer` 등) 을 식별 가능. 설계 §7 O2 는 yaml parse helper 를 `scripts/_helpers/list_enabled_vaults.py` 로 venv python 호출 가정. 그런데 Step 2c 는 fetch + reset 이전 — 새 정본의 `scripts/_helpers/list_enabled_vaults.py` 가 아직 disk 에 없다. 직전 ref 의 scripts/ 사용? 직전 ref 에 이 helper 가 없으면 fail (v0.1.0 spec 완성 후에야 helper 가 ship 되므로 fresh install → update 첫 사이클은 OK, 다음부터는 OK; 단 helper 자체가 본 feature 의 fresh ship 후 등장하므로 첫 update 가 첫 helper 도입과 겹침).

또 venv 자체는 Step 3 에서 install — Step 2c (Step 3 이전) 에는 venv 가 이미 존재한다고 가정하는 것은 update mode 라 valid 하나 그 invariant 가 §3 어디에도 explicit 하지 않음.

**Evidence**:
- `analysis_and_design.md:351` O2 venv python helper 추천
- `analysis_and_design.md:117` `_systemd_stop_before_update` — Step 2c
- `analysis_and_design.md:263` main flow 의 `_step3_venv` 가 Step 2 이후

**Suggested fix**:
- helper 를 venv 의존하지 않는 minimal pure-python (또는 yq fallback) 로 작성 + venv interpreter 가용 여부 검사 + fallback 명시.
- Step 2c invariant 명시: update mode → 이전 install.sh 호출의 venv 가 존재.

---

### MED-4: §6 cross-file impact 가 `install.sh` line-level scope 누락 + setup.md 의 Step 6 (bootstrap_allowed) 영향 누락

**File/section**: `analysis_and_design.md §6 (L332-343)`, `setup.md §Step 6`

**Issue**: §6 가 `_system/commands/setup.md` 변경을 `--reorchestrate flag 신규` 로만 기재. 그러나 update path 에서 `/wh:setup` 자동 호출 시 `setup.md §Step 6 (첫 ingest prompt)` 분기가 trigger 되면 안 된다 (이미 first ingest 완료, `bootstrap_allowed=false`). `bootstrap_allowed: true` vault 1개 이상 시에만 진입 (`setup.md:218`) 이라 정합 — false 면 자동 skip. 그러나 `--enable` flag 와의 상호작용 (update path 에서 `--enable` 을 같이 줄지) 가 §3 어디에도 정의 안 됨. 호출은 `hermes -z "/wh:setup --reorchestrate"` 만 — `--enable` 누락 → daemon-reload 만 일어나고 timer enable 안 됨 → §3 Step 9 의 `start` 가 enable 없이 manual `start` 만 → reboot 시 timer 안 살아남음.

또 §6 에 `install.sh` 자체가 빠져 있음 (정본 수정 대상인데). impact 표는 "install.sh: 본 feature 의 정본 — §3 의 모든 변경" 행이 명시되어야 trace 완전.

**Evidence**:
- `analysis_and_design.md:332-343` 표
- `setup.md:128` `--enable` flag 의미

**Suggested fix**: §6 표에:
- `install.sh` 행 추가 (정본 수정 대상).
- `_system/commands/setup.md` 의 Step 6 무영향 (bootstrap_allowed false 자동 skip) 명시.
- §3 Step 8 의 `hermes -z` 호출에 `--enable` 추가 여부 결정 — 또는 `/wh:setup` 자체가 enable idempotent 라 매번 안전한지 lock.

---

### MED-5: ADR-0023 부분 supersede 결정 deferred — Step 2 lock 시점에 미정

**File/section**: `analysis_and_design.md §6 (L342), §8 (L370-372)`

**Issue**: §6 표 마지막 행 `ADR-0023 ... ADR-0023 Status 갱신 검토 — Step 3 lock 시점에 결정`. §8 도 `Note 추가` 안이지만 결론은 Step 3 까지 deferred. ADR 결정이 정본인데 (CLAUDE.md §3 Step 2 의 ADR 추출 원칙: "결정 = 1 ADR") Step 3 까지 미루는 건 메소드론 위배. Step 2 종료 시점에 ADR-0030 작성 + ADR-0023 갱신 여부를 lock 해야 한다.

ADR-0023 의 Decision §2 `기존 디렉토리가 있으면 wikihub repo 검증 후 rm -rf → 신규 clone` 은 본 feature 가 update path 에서 **명시적으로 위배**. 부분 supersede 가 아니라 **scope 분할** (fresh path / `--force-fresh` path 는 ADR-0023; update path 는 ADR-0030). 이걸 ADR-0023 Note 1줄로 처리할지 ADR-0030 가 ADR-0023 부분 supersede 로 명시할지는 명시적 결정.

**Evidence**:
- `analysis_and_design.md:342, 370-372`
- ADR-0023 §Decision clean install pattern §2
- CLAUDE.md §3 Step 2 ADR 추출 원칙

**Suggested fix**: Step 2 종료 전 ADR-0030 draft 와 ADR-0023 갱신 (Note 추가 OR Status `Accepted (partial)`) 둘 다 결정 + 본 feature 의 §8 에 결론 명시.

---

### LOW-1: `_system/VERSION` 파일이 `0.1.0\n` (trailing newline) — Step 2e 의 string compare 가 OK 한지 미확인

**File/section**: `analysis_and_design.md §3 Step 2 (L99, L126)`, `_system/VERSION`

**Issue**: `cat _system/VERSION` 결과는 `0.1.0\n` (trailing newline 포함). bash `[[ "$current_version" == "$new_version" ]]` 비교는 양쪽 newline 포함이라 통과하지만, banner 출력 `v${new_version}` 은 `v0.1.0\n` 가 되어 출력에 추가 줄바꿈. trivial 하지만 사용자 UX.

**Evidence**: `_system/VERSION` L1 `0.1.0\n`

**Suggested fix**: §3 Step 2 의 cat 을 `tr -d '\n'` pipe 또는 `IFS= read -r current_version < ...` 로 strip.

---

### LOW-2: Step 11 `_rotate_install_log` 의 `stat -c` 가 Linux 전용 (macOS 미동작)

**File/section**: `analysis_and_design.md §3 Step 11 (L224)`, `install.sh:548` (이미 동일 패턴 존재)

**Issue**: `stat -c %Y` 는 GNU coreutils. macOS BSD stat 는 `-f %m`. install.sh:548 은 `stat -c '%a' 2>/dev/null || stat -f '%Lp' 2>/dev/null` 패턴으로 둘 다 처리. 설계 §3 Step 11 은 GNU 만 호출 — Step 1 의 `os_id != ubuntu` fail-fast 가 이걸 보장하긴 하나, `ALLOW_NON_UBUNTU=1` (macOS dev box test) 에서는 fail. 설계는 Linux 전용 환경 invariant 를 명시 (또는 OS-branch).

**Evidence**: `analysis_and_design.md:224`, `install.sh:152-159` (ALLOW_NON_UBUNTU)

**Suggested fix**: §3 Step 11 의 stat 호출에 BSD fallback 추가 또는 "ALLOW_NON_UBUNTU 모드에서 log rotation skip" 명시.

---

### LOW-3: §3 Step 12 banner 의 `v0.1.0 → v0.1.1` hardcoded 예시 — 변수 표기 정합 부족

**File/section**: `analysis_and_design.md §3 Step 12 (L237-243)`

**Issue**: banner 예시가 hardcoded version 만 표시. 구현 시 변수 대입 명시 필요 (`v${current_version} → v${new_version}`). 또 §3 Step 2e (L127-131) 가 이미 transition 출력하는데 §3 Step 12 banner 가 다시 출력하면 중복.

**Evidence**: `analysis_and_design.md:240`, L127-131

**Suggested fix**: banner 에 transition 표시 시 §3 Step 2e 의 ok line 과 중복 안 되게 일원화. 또는 §3 Step 2e 의 ok 를 보고하지 말고 banner 에서 전담.

---

### LOW-4: `Step 6 systemd unit auto-redeploy + mount stop/start orchestration` 의 trace — plan.md L43 에 install.sh Step 6 수정 명시했으나 design 은 Step 8 (별도 호출) 로 처리 → trace 약함

**File/section**: `plan.md L43`, `analysis_and_design.md §3 Step 6 (L156-158), Step 8 (L163-180)`

**Issue**: plan.md L43 의 install.sh 수정 항목 중 `Step 6 systemd unit auto-redeploy + mount stop/start orchestration`. design 은 이 책임을 `_step8_wh_setup` + `_systemd_stop_before_update` / `_systemd_start_after_update` 로 분산 — plan.md 의 `install.sh Step 6` 위치 명시와 다름. trace 가 끊김. 메소드론 §3 Step 2 의 "개정 범위 (대상 파일, 변경 성격)" 정확성 부족.

**Evidence**: `plan.md:43`, `analysis_and_design.md:156-198`

**Suggested fix**: §3 Step 2 도입부에 "plan.md L43 의 'install.sh Step 6 systemd ...' 은 design 의 Step 2c/Step 8/Step 9 로 책임 분할" 명시.

---

## Verdict

**fix HIGH+ before lock**. CRIT-1·CRIT-2 가 둘 다 결함 #B (curl-pipe bypass) · 결함 #D (template render 미수행) 의 closure 실패로 직결 — 본 feature 의 acceptance criteria 자체를 깨는 구조적 결함. HIGH-1·HIGH-2·HIGH-3 는 ADR conformance / DoD 검증 가능성 / Step precondition 누락. Step 2 v2 revision 필요. MED·LOW 는 v2 revision 또는 Step 3 진입 전 in-line fix 로 처리 가능.

특히 CRIT-2 는 O1 미결 항목과 직결 — Step 2 종료 전 O1 lock 필수.

## Notes (not findings — just observations)

- §1 invariant 4건 (재호출=정합 동기화 / vault race 차단 / unstaged silent 손실 0 / idempotent) 은 명확. acceptance criteria 원천으로 좋은 정의.
- §2.2 의 결함 ID → step 매핑 표 (L45-51) 는 trace 측면에서 모범. 다만 §3 Step 6 의 `#A` 매핑은 §3 Step 6 안에 `--version` 처리가 없음 — §4 ref resolution 으로 옮겨야 정확 (`§3 Step 6` 으로 표기됐으나 본문은 `§4`).
- §3 의 Step 번호 (0,1,2,3,4,4.5,5,6,7,8,9,10,11,12) 가 install.sh 현행 step 번호 (1,2,3,4,4.5,5,6,7,8) 와 부분 일치 + 신규 (0,9,10,11,12) 추가. main flow 의 호출 순서 (L249-281) 와 step 정의 순서가 일치하지만 9/10 의 indexing (start 가 9, verify 가 10) 이 main flow L275-276 에서 stop 이 Step 2c 안에 묻혀 있어 가독성 떨어짐. 구현 시 함수명 prefix 통일 권장.
- ADR-0030 의 Decision 4개 항목 (§8) 은 ADR 1건에 결정 1개 원칙 (CLAUDE.md §3 Step 2) 위배 — 4건이 한 ADR 에 묶임. 분할 검토.
- F4 archive 의 V11 (clean install idempotency) verification 이 본 feature 의 fresh path 회귀 검증으로 그대로 유효한지 §9 verification 에 명시 권장.
