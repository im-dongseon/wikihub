# F4 design review R3 (feature-dev:code-reviewer — v4 검증)

리뷰어: feature-dev:code-reviewer (R3 — 2차 라운드, v4 검증)
대상: `features/20260514_install_runtime/analysis_and_design.md` v4
이전 라운드 참조: `design_review_1.md` (R1), `design_review_2.md` (R2)

---

## 1. CRIT 7건 fix 정합성 검증

| 원래 항목 | R1·R2 원래 권고 | v4 실제 lock | 평가 |
|---|---|---|---|
| **R1 §2.13 = R2-1** (`Restart=on-failure` + exit 2 자기모순) | `SuccessExitStatus=0 75` + `Restart=` 제거 (옵션 A) | §4.2 service template: `Restart=` 미설정 + `SuccessExitStatus=0 75` | **정합** — F1 archive L1404·L1412 와 정확히 일치. 단 §3.4 [D] 추천 단락에 구 spec 잔류 (NEW-1) |
| **R2-2** (StartLimitBurst 도달 후 stuck) | `Restart=` 제거로 자연 해소 | `Restart=` 미설정 → StartLimit 비적용 | **자연 해소 정합** |
| **R1 §2.14** (`GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` 누락) | service template 에 env 추가 + `{credentials_path}` 치환변수 | §4.2 L595: `Environment=GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE={credentials_path}` | **정합** — ADR-0014 이행. 단 `{credentials_path}` 가 setup.md 치환 변수 목록에 미등록 (NEW-2) |
| **R1 §2.1** (`{venv_path}` 획득 경로 미명시) | yaml 필드 또는 사이드카 결정 | §4.1 Step 3: `~/wikihub/.venv_path` 사이드카 | **정합** — 단 `{venv_path}` 도 setup.md 치환 변수 목록에 미등록 (NEW-2) |
| **R1 §2.2** (PIPE_MODE env 무한 루프) | `$BASH_SOURCE[0]` 단독 감지 | §4.1 Step 0: `[ -z "${BASH_SOURCE[0]:-}" ] \|\| [ ! -f "${BASH_SOURCE[0]}" ]` | **정합** |
| **R1 §2.3** (`--update` flag 공백) | flag 제거 또는 동작 lock | §4.1 CLI: `--update` 제거 | **정합** |
| **R2-3** (ADR-0022 흐름 역전) | 첫 ingest 성공 후 timer enable | §3.5 [E] v4 + §4.4 Step 6 | **정합 (설계 수준)** — 단 exit 75 시 bootstrap_allowed 환원 미실행 + 다음 사이클 정합 모호 (NEW-5) |
| **ops-alert.service 추가** | F1 L1434~1452 lift | §4.2 ops-alert.service 정의 | **부분 정합** — `StandardOutput/Error` 미lift + `.sh→.py` 변경 ADR 부재 (NEW-3) |

**F1 §4.8.2 surgical lift 세부 검증**: `Type=oneshot`·`Restart=` 미설정·`SuccessExitStatus=0 75`·`TimeoutStartSec=15min`·`OnBootSec=2min`·`OnUnitInactiveSec`·`AccuracySec=1min`·`Persistent=true`·`OnFailure=ops-alert.service` 9개 directive 모두 정합. `StandardOutput/StandardError=append:...` 만 미lift (NEW-3).

---

## 2. R1·R2 잔여 항목 처리 검증

| 잔여 항목 | v4 처리 | 평가 |
|---|---|---|
| R1 §2.4 (WIKIHUB_HOME normalize edge case) | `\|\| true` 패턴 유지, trailing slash fix 미명시 | **미해소** |
| R1 §2.10 (wiki-schema.md / ingest.md 경로 모델) | §4 산출물 목록에 미포함 | **미해소** |
| R1 §2.11 (WIKIHUB_YAML 주입 경로 명시) | template 에 env 있으나 config.py read 명시 부재 | **부분** |
| R1 §2.12 (WantedBy 혼재) | service `[Install]` 미작성 명시 | **해소** |
| R1 §2.15 (naming 혼재) | ADR-0019 draft 미작성 — DoD §8 필수 항목 잔여 | **부분** |
| R1 §2.16 (auth_gdrive.py 구 경로) | §4.5 + Step 8 도식에 신경로 명시 | **사실상 해소** |
| R1 §2.17 (V13 bootstrap_allowed 환원 검증) | §6 V13 에 환원 명시 | **정합** — 단 exit 75 케이스 미포함 (NEW-5) |
| R1 §2.18 (§8 DoD ADR 수) | "8건" 으로 갱신 | **해소** |
| R2 HIGH-R2-1 (비대화 모드 정규화) | `$SKIP_CONFIRM` 미정의 잔류 | **미해소** |
| R2 HIGH-R2-2 (partial install trap) | `trap` 패턴 미추가 | **미해소** |
| R2 HIGH-R2-3 (OnBootSec 120s) | 2min 갱신 | **해소** |
| R2 HIGH-R2-4 (ADR-0023 위협 모델) | 5×위협 매트릭스 추가 | **해소** |
| R2 HIGH-R2-6 (OnUnitInactiveSec) | 변경 | **해소** |
| R2 HIGH-R2-7 (F1 surgical lift directive) | 대부분 해소 — StandardOutput/Error만 미lift (NEW-3) | **해소** |
| R2 HIGH-R2-8 (multi-vault 직렬화 주석) | 미추가 | **미해소** |
| R2 MED-R2-5 (Python 3.11 Ubuntu 22.04 절차) | 불완전 잔류 | **미해소** |
| R2 MED-R2-6 (V8 gws ARM64 asset) | "Step 3 직전 hand-check" 잔류 | **명시적 미완** |

---

## 3. 새 결함 surface

### [CRIT][RegressionFix] NEW-1: §3.4 [D] 의 폐기된 spec 잔류

**파일**: `analysis_and_design.md` §3.4 [D] L169

§3.4 [D] "추천" 단락에 v4 가 폐기한 문장 잔류:
> "service `Restart=on-failure` + `RestartSec=60` + `StartLimitInterval=600` + `StartLimitBurst=5` 로 exit 75 자동 재시도 + 무한 루프 방지."

ADR-0021 작성 시 이 단락을 그대로 옮기면 잘못된 ADR. §3.4 의 결정 근거 vs §4.2 구현 모순.

**권장**: 해당 문장을 "service `Restart=` 미설정 (ADR-0021 v4 lock — oneshot 재시도는 timer 책임. F1 §4.8.2 정합)" 으로 교체.

---

### [CRIT][SpecMismatch] NEW-2: setup.md 치환 변수 목록 3개 미등록

**파일**: `analysis_and_design.md` §4.2 vs `_system/commands/setup.md` L54~60

v4 §4.2 template 이 사용:
- `{venv_path}` — service L593, ops-alert L629·631
- `{credentials_path}` — service L595
- `{wikihub_home}` — ops-alert L631 (`ExecStart={venv_path}/bin/python {wikihub_home}/scripts/ops-alert.py`)

세 변수 모두 setup.md 정본 (L54~60) 의 치환 변수 목록에 부재. Step 3 구현자가 setup.md 기준으로 Python helper 작성 시 literal 로 기록 → 모든 unit 시작 실패.

**권장**: setup.md §Step 2 치환 변수 목록에 3줄 추가 + §4.4(§4.5.3) "setup.md 갱신 폭" 에 병기.

---

### [HIGH][DesignGap] NEW-3: ops-alert.service 의 StandardOutput/Error F1 lift 누락

**파일**: §4.2 ops-alert.service vs F1 L1445~1446

F1 의 `StandardOutput=append:.../ops-alert.log` 와 `StandardError=append:...` 미반영. ops-alert.py 가 `.sh` 에서 `.py` 로 변경된 근거도 ADR 부재.

**권장**: `StandardOutput=journal` + `StandardError=journal` 추가 + `.sh→.py` 결정 1줄 주석.

---

### [HIGH][NewBug] NEW-4: V10 검증 설명이 폐기된 spec 으로 잔류

**파일**: §6 V10 (L809)

> V10 | systemd user unit Restart=on-failure 동작 + exit 75 trigger | ...

v4 는 `Restart=` 제거. V10 이 검증해야 할 것은:
- `Restart=` 없는 oneshot 에서 exit 75 후 timer 가 `OnUnitInactiveSec` 경과 후 자동 재 fire
- `SuccessExitStatus=0 75` 로 exit 75 가 journal success 기록
- exit 2 시 `OnFailure=ops-alert.service` trigger

**권장**: V10 설명 전면 교체.

---

### [HIGH][DesignGap] NEW-5: exit 75 시 bootstrap_allowed 환원 미실행 → 다음 timer 사이클 fatal

**파일**: §3.5 [E] L208, §4.4 step 4

§3.5: "exit 0 (또는 75 with changes) 인 vault 만 다음 단계 진입"
§4.4 step 4: bootstrap_allowed 환원은 "exit 0 시에만"

exit 75 후 cursor 미생성 케이스: 다음 timer 사이클에서 `vault-fetch.py` 가 `--bootstrap` flag 없이 실행 → F3 의 bootstrap 가드 ("bootstrap 허용됐으나 --bootstrap 플래그 누락") → **VaultSyncFatal (exit 2) → fatal loop**.

**권장**: §4.4 step 4 에 exit 75 케이스 분기 — cursor 존재 확인 후 환원/보류 결정.

---

### [HIGH][DesignGap] NEW-6: §4.4 하위 번호 충돌 (§4.5.1·2·3 vs §4.5 auth_gdrive)

**파일**: §4.4 (L701) + §4.5 (L768)

§4.4 의 하위 섹션이 `§4.5.1`/`.2`/`.3` 으로 잘못 책정 → 독립 §4.5 `auth_gdrive.py` 와 번호 충돌. §3.5 [E] L221 의 "§4.5 참조" 가 모호.

**권장**: §4.4 하위를 `§4.4.1`/`.2`/`.3` 으로 재번호.

---

### [HIGH][NewBug] NEW-7: exit 2 반복 사이클의 ops-alert 빈도 dedup 부재

**파일**: §4.2 핵심 결정 lock L643

매 timer cycle (600s) 마다 fatal repeat → ops-alert 매번 발화 → Telegram alarm fatigue.

**권장**: §4.2 lock 에 "ops-alert 빈도 = sync_interval_sec 마다 최대 1건. Step 3 구현 시 cool-down 정책 결정" 추가.

---

### [MED][SpecMismatch] NEW-8: setup.md Step 4 의 `--enable` 동작이 v4 흐름 역전과 충돌

**파일**: setup.md L103 vs §4.4 갱신 폭

setup.md 현재 정본: `--enable` 시 즉시 `enable --now`. v4 는 Step 6 후 enable.

**권장**: §4.4 의 setup.md 갱신 폭에 "Step 4 의 `--enable` 동작 변경: enable --now → daemon-reload 만 (enable 은 Step 6 결과에 위임)" 명시.

---

### [MED][DesignGap] NEW-9: ops-alert.py spec 부재

**파일**: §4.2 L637

"별도 §4.x 에서 spec" 인데 그 §4.x 가 v4 에 없음.

**권장**: 신규 §4.x — `scripts/ops-alert.py` minimal spec (last_failure.json glob, webhook payload, timeout 연동, exit code 정책).

---

### [MED][NewBug] NEW-10: venv 생성 실패 시 사이드카 미기록 처리 미명시

**파일**: §4.1 Step 3

venv 생성 실패 후 `.venv_path` 미기록 상태로 install.sh exit → `/wh:setup` 호출 시 substitution 실패.

**권장**: Step 3 에 "venv 생성 실패 시 exit 2 — `.venv_path` 기록 skip" 명시.

---

### [LOW][DesignGap] NEW-11: F1 §4.8.3·§4.8.4·§4.8.5 미반영

**파일**: F1 vs §4.2

§4.8.3 Overlap 방지 검증 표 / §4.8.4 다중 vault 직렬화 / §4.8.5 로깅·관측 — v4 미인용.

**권장**: §4.2 에 "v0.1.0 단일 vault 라 §4.8.4 비활성. §4.8.5 로깅 결정은 NEW-3 와 묶음" 1단락.

---

### [LOW][DocMismatch] NEW-12: ADR-0022 Status 표기 v1↔v4 모호

**파일**: §7 ADR 표 L828

`ADR-0022 | ... | Accepted | 본 문서 v1, V13 이 회귀 방지` — v4 의 흐름 역전이 supersede 인지 개정인지 불명.

**권장**: 표 행에 "v4 에서 흐름 역전 추가" 명시.

---

## 4. 결론

### Step 3 진입 차단 여부: **조건부 차단 (CRIT 2건 즉시 fix 필수)**

**즉시 fix 필수**:
1. NEW-1 — §3.4 [D] 구 spec 단락 교체
2. NEW-2 — setup.md 치환 변수 목록 3건 등록

**Step 3 진입 전 권장**:
3. NEW-4 — V10 설명 교체
4. NEW-5 — exit 75 + cursor 미생성 케이스 분기
5. NEW-6 — 번호 충돌 수정
6. NEW-8 — setup.md Step 4 `--enable` 동작 변경 spec

**Step 3 도중 자가 검증**:
- NEW-3, NEW-7, NEW-9, NEW-10

**권장 후속**: CRIT 2건 + HIGH 4건 fix 후 v5 lock → ADR 8건 (`docs/adr/`) 파일 작성 → Step 3 진입.
