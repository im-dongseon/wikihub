# F4 design review R1 (feature-dev:code-reviewer)

리뷰어: feature-dev:code-reviewer (R1 — 본 feature 의 design review 1차)
대상: `features/20260514_install_runtime/plan.md`, `analysis_and_design.md v3`
참조: F1·F2·F3 archive + `_system/` 정본 + ADR 0001~0014

---

## 1. 결정 8건 정합성 검증

| 결정 | 채택 | 평가 | 근거 (file:section) |
|---|---|---|---|
| [A] install.sh ↔ deploy.sh | A1 단일 | **정합** | ADR-0010 §Decision (γ)와 완전 일치. `deploy.sh` 명시 폐기 선언됨. |
| [B] systemd unit 패턴 | B2 per-vault + Python helper | **정합 (조건부)** | `setup.md` L46~62의 치환 변수 목록과 일치. 단 `{venv_path}` 변수가 setup.md 치환 변수 목록에 **없음** — §2.1 |
| [C] venv 위치 | C1 XDG | **정합** | [D1] 결합 근거 타당. ADR-0010 L133 precondition 의 `/opt/wikihub` default 와 다르지만 ADR-0010 자체가 위치를 hard-code 하지 않으므로 충돌 아님. |
| [D] reboot resilience | D1 user-level + linger | **정합 (조건부)** | F1 archive §4.1.2 (`systemctl --user` 명시) + F2 setup.md 전반과 일치. V12 fail 시 D2 fallback 절차가 있으나 D2 마이그레이션 중 `credentials` owner 변경 시 `assert_credentials` 권한 600 검증 실패 가능성 미언급 — §2.6 |
| [E] 첫 ingest 진입점 | E3 (install.sh 안내 + /wh:setup Step 6) | **부분 결함** | setup.md 에 Step 6 추가가 필요하지만 v3 §4 산출물 목록에 `setup.md` 수정이 명시되지 않음. §2.7 |
| [F] gws version pinning + 채널 | F1 latest + CH2 | **정합** | ADR-0014 §gws 버전 핸들링과 일치. `wikihub.yaml.operations.gws_min_version` 언급이 ADR-0014에 있으나 v3의 `wikihub.yaml.example` 에 해당 키 미포함 — §2.5 |
| [G] gws stderr starting regex | G1 F3 archive 그대로 | **정합** | `scripts/lib/errors.py` 실제 코드와 일치 확인. `scope` 컬럼 포함 (CRIT-R4-3 fix) 명시됨. |
| [H] install.sh 배포·호출 모델 | H1 curl-pipe + clean install | **부분 결함** | self-replace `exec` 의 stdin 손실·`--update` flag 의미 공백·mutable tag 보안 위협 명시 부족 — §2.2, §2.3, §2.9 |

---

## 2. 새 결함 surface

### 2.1 [HIGH][SpecMismatch] `{venv_path}` 치환 변수가 setup.md 정본과 충돌

**파일**: `analysis_and_design.md` §4.2, `_system/commands/setup.md` §Step 2 (L54~60)

setup.md 의 치환 변수 목록: `{vault_id}, {sync_interval_sec}, {lint_interval_hours}, {instance_root}, {agent_invocation}, {skill_prefix}` — `{venv_path}` 없음.

v3 §4.2 service template 의 `Environment=PATH={venv_path}/bin:/usr/bin:/bin` 가 setup.md 치환 변수 목록에 없는 변수 사용. `/wh:setup` Python helper 가 venv_path 를 어디서 획득할지 명시 부재. wikihub.yaml.example 에 `venv_path` 키도 없음.

**권장**: yaml 에 `venv_path` 필드 추가 또는 install.sh 가 `_system/VERSION` 옆 사이드카에 기록 → `/wh:setup` 이 read.

### 2.2 [CRIT][NewBug] `exec ~/wikihub/install.sh "$@"` 의 무한 루프 가능성

**파일**: `analysis_and_design.md` §4.1 Step 0, §3.8 [H]

Step 0 의 `WIKIHUB_PIPE_MODE=1` 이 export 되면 exec 후 새 process 도 분기에 재진입 → 무한루프. v3 가 `unset WIKIHUB_PIPE_MODE` 또는 `WIKIHUB_PIPE_MODE=0` 명시 안 함.

**권장**: Step 0 spec 에 `bootstrap_clone_then_exec` 내 exec 직전 `unset WIKIHUB_PIPE_MODE` 명시, 또는 PIPE_MODE 감지를 `$BASH_SOURCE[0]` 단독 조건으로 단순화.

### 2.3 [CRIT][NewBug] `--update` flag 의미 공백 — idempotency 깨짐 가능

**파일**: `analysis_and_design.md` §4.1 CLI, Step 2

v3 가 "`--update` 는 안내 메시지에만 영향" 으로 의도적 단순화. 그러나 운영자가 `--update` 호출 시에도 `rm -rf` + 재 clone 발생 — clean install 동작이 운영자 기대와 어긋날 수 있다. Step 4 code review 에서 구현자가 `--update` 에 다른 분기 추가하면 V11 시나리오 3·4 와 충돌 가능.

**권장**: `--update` 를 CLI 에서 제거 ("모든 호출 = clean install") 또는 v3 에 "update 모드와 신규 설치 모드의 유일한 차이는 안내 메시지 — clean install 동작은 동일" 을 명시 lock.

### 2.4 [HIGH][NewBug] `WIKIHUB_HOME` normalize 의 parent-does-not-exist 케이스

**파일**: `analysis_and_design.md` §4.1 Step 2

`cd "$(dirname ...)" 2>/dev/null && pwd` 가 parent 미존재 시 silent fail. `|| true` 가 error 삼킴 → `WIKIHUB_HOME` 이 빈 문자열이 됨 → safety guard 1 의 `case "" in` 분기로 exit 1 — 단 안내 메시지는 "WIKIHUB_HOME 이 시스템 path" 라는 엉뚱한 내용.

**권장**: normalize 실패 시 `|| true` 제거하고 명시 에러 출력 후 exit 1. symlink 허용 여부도 v3 에 1줄 명시.

### 2.5 [HIGH][SpecMismatch] `wikihub.yaml.example` 에 `operations.gws_min_version` 미포함

**파일**: `analysis_and_design.md` §4.3, `docs/adr/0014-drive-access-mechanism-revisited.md` §gws 버전 핸들링

ADR-0014 가 명시: `wikihub.yaml.operations.gws_min_version` — F4 가 install.sh 의 pinned 버전과 일치하도록 정의. v3 에 누락.

**권장**: `operations.gws_min_version: ""` placeholder 추가 (V6 후 채움), 또는 `_system/VERSION` 사이드카로 관리 결정 v3 에 명시.

### 2.6 [HIGH][DesignGap] D2 fallback 시 `assert_credentials` 권한 검증 실패 미언급

**파일**: `analysis_and_design.md` §3.4 [D] u5, `scripts/lib/credentials.py`

D2 마이그레이션 절차 (d) "credentials 파일의 owner 변경" 후 `assert_credentials` 가 권한 600 검증 → owner 가 wikihub service user 로 바뀐 후 기존 운영 user 기준으로 파일을 못 읽는다. `/wh:setup` 호출 방식 (sudo -u wikihub) 도 변경 필요.

**권장**: D2 fallback 절차에 "`/wh:setup` 호출은 `sudo -u wikihub agent -z '/wh:setup'`" + "credentials 권한 600 유지 + owner = wikihub 확인" 명시.

### 2.7 [HIGH][SpecMismatch] setup.md Step 6 추가가 §4 산출물 spec 에서 누락

**파일**: `analysis_and_design.md` §3.5 [E], §4

§3.5 [E] 가 ADR-0022 결정대로 `/wh:setup` Step 6 추가 결정. 그러나 v3 §4 산출물 목록에 `_system/commands/setup.md` 수정 spec 없음. Step 3 구현자가 누락 위험.

**권장**: §4 에 "4.5 `_system/commands/setup.md` Step 6 추가" 신설. 최소 spec: prompt 화면 출력, bootstrap_allowed flip 책임, flag 처리 방식.

### 2.8 [HIGH][DesignGap] `bootstrap_allowed: true` 환원 책임 미명시

**파일**: `analysis_and_design.md` §3.5 [E], §4.3

yaml.example 주석에 "자동 환원" 적혀 있지만 누가/언제 환원하는지 spec 없음. F3 의 `lib/config.py` 는 read-only 라 yaml write 컴포넌트 부재.

**권장**: v3 §3.5 또는 §4.2.6 신설로 환원 책임 lock. V13 이 흐름 포함하도록 갱신.

### 2.9 [HIGH][SecRisk] `git clone --branch latest --depth 1` mutable tag 보안

**파일**: `analysis_and_design.md` §4.1 Step 2, §3.8 [H]

mutable tag 의 위협 모델 (GitHub 계정 탈취 → force-push) 이 curl-pipe install.sh 와 동일. v3 §3.8 "보안 고려" 가 "v0.1.0 acceptable" 라 모호.

**권장**: ADR-0023 본문에 "curl-pipe 와 git clone 의 공통 위협 모델 = GitHub 계정 보안 + force-push 제어. v0.2.x 에서 signed commit 또는 tag verification 추가 예정" 명시.

### 2.10 [MED][SpecMismatch] `wiki-schema.md` / `ingest.md` 의 경로가 v3 와 어긋남

**파일**: `_system/wiki-schema.md` §디렉토리 구조, `_system/commands/ingest.md` L17·L43

기존 정본은 `/opt/wikihub/` 기본 — v3 는 `~/wikihub-instance/`. `ingest.md` L43 의 `/opt/wikihub/scripts/vault-fetch.py` 하드코딩 vs v3 의 경로 모델 충돌. F4 산출물 목록에 이 수정 누락.

**권장**: §4 에 `_system/commands/ingest.md` L43 경로 수정 + `_system/wiki-schema.md` 기본 경로 갱신 명시.

### 2.11 [MED][DesignGap] `WIKIHUB_YAML` 환경변수 주입 경로 미명시

**파일**: `analysis_and_design.md` §4.2 service template, `scripts/lib/config.py`

template `Environment=WIKIHUB_YAML={instance_root}/wikihub.yaml` — `lib/config.py:load_wikihub_yaml()` 가 이 env 를 실제로 read 하는지 v3 미검증. agent → vault-fetch.py subprocess 상속 명시 부재.

**권장**: v3 §4.2 에 "Environment=WIKIHUB_YAML 은 agent 및 child process 에 상속됨. `lib/config.py` 가 `os.environ.get('WIKIHUB_YAML')` 로 read" 명시.

### 2.12 [MED][DesignGap] timer `WantedBy=timers.target` vs service `WantedBy=default.target` 혼재

**파일**: `analysis_and_design.md` §4.2

service `WantedBy=default.target` 은 timer 없이 직접 활성화 시 의미. timer 가 service 를 trigger 한다면 service 의 WantedBy 는 불필요하거나 비워두는 게 표준.

**권장**: service template 의 WantedBy 제거 또는 이유 1줄 명시.

### 2.13 [CRIT][NewBug] `Type=oneshot` + `Restart=on-failure` + exit 2 의 자기모순

**파일**: `analysis_and_design.md` §4.2 service template, plan.md DoD V10

systemd `Restart=on-failure` 는 exit 0 외 모두 재시도. exit 75 + exit 2 둘 다 trigger. plan.md DoD `exit 2 는 더 이상 재시도 안 함 (V10)` 과 충돌. `RestartPreventExitStatus=2` 또는 `SuccessExitStatus=0 75` 필요.

**권장**: service template 에 `RestartPreventExitStatus=2` 추가.

### 2.14 [CRIT][SpecMismatch] `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` 환경변수 누락

**파일**: `analysis_and_design.md` §4.2, ADR-0014

ADR-0014 명시: F4 가 systemd unit Environment 로 주입 책임. v3 template 에 누락. vault-fetch.py 가 자체 설정 안 함 (credentials.py 의 `ensure_env_var` 는 dict 반환만, systemd 환경에서는 적용 안 됨).

**권장**: service template 에 `Environment=GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE={credentials_path}` 추가 + 치환 변수 `{credentials_path}` 명시.

### 2.15 [MED][SpecMismatch] `{vault_id}-ingest` vs `wikihub-vault@{vault_id}` naming 혼재

**파일**: `analysis_and_design.md` §3.2, §4.2

ADR-0019 본문에 B1 (instantiated `wikihub-vault@.service`) 이 비교용으로 남아 있어 독자 혼란. B2 의 최종 파일명 (`{vault_id}-ingest.service`) 이 §4.2 template 섹션에 분리되어 cross-reference 불명확.

**권장**: ADR-0019 draft 에 "B2 채택 시 최종 파일명 = `{vault_id}-ingest.service`/`.timer`" 명시.

### 2.16 [LOW][DocMismatch] F3 `auth_gdrive.py` 가 구 경로 (`/opt/wikihub/`) 안내

**파일**: `scripts/auth_gdrive.py` L73

scp 안내가 `/opt/wikihub/.credentials/` — v3 의 `~/wikihub-instance/.credentials/` 와 다름. F4 범위인지 F3 후속인지 명시 필요.

### 2.17 [LOW][TestGap] V13 의 `bootstrap_allowed` 자동 환원 포함 불명확

**파일**: `analysis_and_design.md` §6 V13

§2.8 의 결함과 연동 — 환원 책임 결정 후 V13 에 검증 항목 추가 필요.

### 2.18 [LOW][DocMismatch] §8 Definition of Done v2 와 v3 불일치

**파일**: `analysis_and_design.md` §8

§8 Step 2 DoD 가 "신규 ADR 5건" — v3 는 8건 (ADR-0015·0017·0023 추가). 갱신 누락.

---

## 3. 결론

### Step 3 진입 차단 여부: **조건부 차단 (CRIT 3건 해소 후 진입)**

**즉시 fix 필요 (Step 3 전 v4 lock)**:
1. **§2.13** — service template 에 `RestartPreventExitStatus=2` (V10 DoD 충돌 해소).
2. **§2.14** — service template 에 `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE={credentials_path}` + 치환 변수 추가.
3. **§2.1** — `{venv_path}` 획득 경로 명시 (yaml 필드 또는 사이드카).
4. **§2.2** — Step 0 의 `unset WIKIHUB_PIPE_MODE` 명시 또는 감지 단순화.
5. **§2.3** — `--update` flag 의미 lock (CLI 제거 또는 안내-only 명시).

**Step 3 도중 surface 가능 (진입은 허용)**:
- §2.7 setup.md Step 6 spec, §2.8 bootstrap_allowed 환원 책임, §2.11 WIKIHUB_YAML 주입 경로

**Step 4 까지 미뤄도 됨**:
- §2.4 normalize edge case, §2.5 gws_min_version, §2.6 D2 fallback 보완, §2.9 mutable tag security, §2.10 경로 모델, §2.12 WantedBy, §2.15 naming, §2.16~18 문서/DoD

### 권장 후속

design v4 에서 CRIT 5건 lock + HIGH 일부 해소 후 Step 3 진입.
