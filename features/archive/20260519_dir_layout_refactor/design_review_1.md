# Design Review 1 — dir_layout_refactor (CR1: spec)

- **리뷰 대상**: analysis_and_design.md v1 (618줄)
- **리뷰어**: CR1 (spec / ADR 정합 / schema 정확도)
- **리뷰 일자**: 2026-05-19
- **종합 판단**: **Accept with revisions** — δ-2 XDG src 채택과 env (B) 변수 swap 권장은 타당. 단 (1) ADR-0023·0030·0031 의 §Decision 본문 변경이 "Note 추가" 로 처리 불가능한 핵심 명세 변경이고, (2) v1 의 ADR-0029 credentials_path 현황 진단 (§3.6) 이 ADR-0029 §Decision 본문과 불일치하며, (3) migration helper 의 idempotency·race·disk model 미명시가 CRIT 수준이라 v2 에서 8건 명시 갱신 필요.

---

## CRIT — 진입 차단

### CR1-CRIT-1 — ADR-0029 credentials_path 진단 (§3.6) 이 ADR-0029 §Decision 본문과 불일치
- **위치**: analysis_and_design.md §3.6 line 132~138
- **결함**: §3.6 가 현행 default 를 `~/wikihub-instance/.credentials/sa_gdrive.json` 로 적은 뒤 "또는 보안 권장 (CLAUDE.md): `~/.credentials/wikihub/sa_*.json` (repo 외부)" 라고 양립 가능한 듯 기술. 그러나 ADR-0029 §Decision line 52 는 단일 정본을 명시:
  > "scp → OCI `~/wikihub-instance/.credentials/sa_<vault_id>.json` → chmod 0600. wikihub.yaml 의 `credentials_path` 가 본 파일 지정."
  즉 ADR-0029 의 v1 명세는 `~/wikihub-instance/.credentials/` (instance 내부) 가 **정본** 이고 "repo 외부" 권장은 별도 ADR 가 아니다. 이 상태에서 본 feature §5.5 (미결 #5 권장 (B)) 가 `~/.credentials/wikihub/` 외부 유지를 "보존" 한다고 표현하면 무엇을 보존하는지 trace 불가능. 실제로는 ADR-0029 의 **변경** 임.
- **권장 해결책**: v2 §3.6 를 정확히 다음과 같이 정정 — "ADR-0029 §Decision 의 default 가 `~/wikihub-instance/.credentials/sa_<vault_id>.json`. 본 feature 가 `~/wikihub/.credentials/sa_*.json` (data-first 자연 매핑) 또는 `~/.credentials/wikihub/sa_*.json` (repo 외부 보안 격리) 중 lock 필요." 그리고 §7.1 ADR-0029 row 를 "Note 추가" 가 아니라 **§Decision 갱신** 으로 격상 (현 path → 신 path). §5.5 도 "현행 정책 유지" 문구 제거하고 "ADR-0029 §Decision 의 credentials_path default 를 명시 변경" 으로 정정.

### CR1-CRIT-2 — ADR-0023 의 "safety guard 4번째 추가" 가 §Decision 본문 변경 (Note 으로 처리 불가)
- **위치**: analysis_and_design.md §5.2.5 + §7.1 ADR-0023 row
- **결함**: ADR-0023 §Decision (line 44~47) 은 "safety guard 3개" 를 **숫자까지 정본 명세** 로 못박음:
  > "**safety guard 3개**: 1. ... 2. ... 3. ..."
  4번째 추가는 §Decision 본문의 명시 명세 변경. CLAUDE.md §3 의 ADR 컨벤션상 §Decision 명세 변경은 **Note 추가** 가 아니라 **§Decision 갱신** (또는 Status `Superseded` + 신규 ADR) 으로 처리해야 함. v1 §7.1 ADR-0023 row 는 이미 "§Decision 갱신" 으로 적어 정합하나 §5.7 의 ADR Notes 목록 (line 438) 은 "Note 추가" 로 부정합 — 두 표 mutual contradiction.
- **권장 해결책**: v2 §5.7 ADR-0023 항목을 "§Decision 본문의 'safety guard 3개' → 'safety guard 4개' 갱신 + 신규 guard #4 명세 추가" 로 정정. Note 가 아니라 §Decision 본문 patch.

### CR1-CRIT-3 — `WIKIHUB_HOME` semantic swap 의 silent bug surface (R10 self-replace race 와의 결합)
- **위치**: analysis_and_design.md §4.1 옵션 (B) + §5.1
- **결함**: ADR-0023 §Consequences (line 65) 는 self-replace race window R10-HIGH-4 를 명시:
  > "(1) 과 (3) 사이에 메인테이너가 force-push 하면 첫 curl install.sh 와 clone repo 의 install.sh 가 incompatible 일 수 있음"
  본 feature 가 `WIKIHUB_HOME` 의 의미를 swap 하면 transition 기간 동안 운영자 (또는 자동화 스크립트) 가 양쪽 의미를 혼동할 수 있고, 특히 **v0.1.x install.sh 의 self-replace 가 신 install.sh 를 실행** 하는 transition 시점에서 `WIKIHUB_HOME` 환경변수가 의미 mismatch 로 cross-version 호출 (예: 이전 install.sh 가 `WIKIHUB_HOME` 을 repo dir 로 export 한 후 신 install.sh 가 그 값을 운영 dir 로 해석) 발생 가능. v1 §5.3.3 의 `WIKIHUB_INSTANCE_ROOT` detect 는 다루지만 `WIKIHUB_HOME` 자체의 **의미론 충돌 detect** 부재.
- **권장 해결책**: v2 §5.3 에 추가 detect 로직 명시 — 신 install.sh 가 `WIKIHUB_HOME` env 가 set 된 상태에서 그 path 가 `~/.git/` 보유 + origin 이 wikihub 이면 (이전 의미로 set 된 것) **fail-fast** + 안내 ("v0.2.0 부터 WIKIHUB_HOME 의미 변경. 현 값이 repo dir 로 보임 — unset 후 재호출 또는 WIKIHUB_SRC 로 명시 export"). 이 detect 없이는 silent migration 손상 위험.

### CR1-CRIT-4 — migration helper 의 idempotency 부재 (partial state recovery 미명시)
- **위치**: analysis_and_design.md §5.3.1 의사 코드
- **결함**: helper 의 step 1~7 (systemd stop → backup → mv repo → mv instance → hermes patch → render → systemd start) 가 **모두 atomic block 가정** — 그러나 step 3 (mv repo) 성공 + step 4 (mv instance) 실패 시 partial state 발생:
  - `~/wikihub/` = repo 잔재 (mv 전) + instance 일부 (mv 중 실패)
  - `~/.local/share/wikihub/src/` = 정상 mv 완료
  - `~/wikihub-instance/` = 부분 mv (디스크/EXDEV 실패 시)
  - 운영자가 helper 재호출 시 step 1 의 `detect_legacy()` 는 `$LEGACY_REPO/.git` 부재 (이미 mv 됨) → false 반환 → migration skip → 운영자는 시스템 부분 상태에서 install.sh 재호출 → 운영자 자산 손실 가능.
- **권장 해결책**: v2 §5.3.1 에 helper 의 **state machine** 명시 추가:
  - phase marker file (`~/.local/state/wikihub/migration.state`) 에 현재 phase 기록 (예: `pre-step3`, `post-step3`, `post-step4`, ...).
  - re-entry 시 marker 읽고 해당 phase 부터 재개. 모든 phase 의 op 는 idempotent (mv 가 target 존재 시 skip 또는 conflict resolve 명시).
  - rollback 진입 조건 (어느 phase 까지는 rollback 가능, 그 이후엔 forward-only) 명시.

### CR1-CRIT-5 — systemd unit ExecStart 의 stale path 와 mv 순서의 race
- **위치**: analysis_and_design.md §5.3.1 step 1·6, §5.4
- **결함**: v1 §5.3.1 step 1 ("systemd unit stop") 시점에 ExecStart 의 path 는 **v0.1.x 의 `{wikihub_home}/scripts/...`** (= 현 `~/wikihub/scripts/...`). step 3 mv 후 path 가 stale → step 7 (systemd start) 직전에 render 재호출 (step 6) 로 path 갱신은 명시. 그러나:
  - **step 1 의 stop 이 in-flight job 의 15min grace 를 기다리는 동안** (ADR-0030 §sub-1 sub-decision 의 stop sequence — vault@.timer stop → vault@.service grace 15min → mount@ stop) — 이 동안 vault@.service 가 `{wikihub_home}/scripts/vault_fetch.py` 를 spawn 가능 → 이 process 가 grace 내에 끝나기 전 step 3 mv 가 실행되면 process 의 cwd / 실행 binary path resolve 실패.
  - in-flight grace 가 끝날 때까지 mv 를 **postpone** 한다는 명시 부재.
- **권장 해결책**: v2 §5.3.1 의사 코드를 다음 순서로 명시:
  1. systemd stop (모든 vault@.timer + lint timer first)
  2. **wait until `systemctl --user is-active vault@*.service` 모두 inactive** (혹은 timeout 15min + fail-fast)
  3. mount@ stop
  4. backup
  5. mv repo
  6. mv instance
  7. hermes patch
  8. render (신 path)
  9. daemon-reload
  10. systemd start
  
  v1 의 step 1 단순화 ("systemd unit stop") 는 ADR-0030 §sub-1 의 stop sequence (β 옵션 채택) 와 정합 보장 불가능 — 명시적 sequence 필수.

---

## HIGH — Step 2 v2 에서 반영 권장

### CR1-HIGH-1 — ADR-0030 의 `_step2_update` cwd 변경이 sub-decision 4건 (sub-1~sub-4) 모두 정합 검증 부재
- **위치**: analysis_and_design.md §3.4, §7.3
- **결함**: v1 §7.3 가 단순히 "cwd = `$WIKIHUB_SRC`" 만 명시. 그러나 ADR-0030 §Decision 의 4 sub-decision 각각 정합 점검 필요:
  - **sub-1** (systemd stop/start sequence): stop sequence 가 unit 의 ExecStart path 를 resolve — src dir 의 ExecStart 가 mv 시점 stale. ADR-0030 sub-1 의 sequence 자체는 영향 없으나 timing 정합 필요 (CR1-CRIT-5 와 연결).
  - **sub-2** (unstaged 보호): `git status --porcelain` empty 검증 대상이 src dir. **운영자의 일상 yaml 편집 (`~/wikihub/wikihub.yaml`) 은 git tree 외부** 라 영향 없음 — 즉 v0.1.x 보다 unstaged guard 의 mental model 자연화. 본 효과를 §7.3 에 명시하면 PR.
  - **sub-3** (rollback trap): PRE_UPDATE_REF capture cwd = src dir — 정합. 단 trap 실행 시 daemon-reload 후의 render 재호출이 신 path 환경에서 동작해야 함 — `render_systemd_units.py` 의 fallback 동작 (env 미설정 시 default) 검증 필요.
  - **sub-4** (ref resolution): `git for-each-ref` cwd = src dir — 정합. 영향 없음.
- **권장 해결책**: v2 §7.3 를 sub-decision 4건 각 한 줄씩 정합 상태 명시. sub-2 의 mental model 자연화 효과는 §1.2 (목적) 의 "선행 feature 의 정본성 보존" 에 보강 (positive consequence).

### CR1-HIGH-2 — ADR-0031 의 `instance.root` default 변경이 schema version (§Decision E) 검증과 충돌 가능
- **위치**: analysis_and_design.md §5.5, §7.4
- **결함**: ADR-0031 §Decision E (line 178~201) 가 `wikihub.yaml.example` 의 `version` 필드와 operational yaml 의 `version` mismatch 시 fail-fast 를 정본화. 본 feature 가 `_system/VERSION` 을 v0.1.0 → v0.2.0 bump 한다 (§9.2). 그러나:
  - **`wikihub.yaml.example` 의 `version: 1` 변경 여부 미명시**. ADR-0031 §Decision E 의 v1→v2 transition 은 "별도 ADR" 요구. 본 feature 가 yaml schema 의 `instance.root` default 만 변경하고 schema 자체 version 은 유지 (`version: 1` 그대로) 한다면 v1 호환 — 이 가정을 v2 에 명시 필수.
  - 반대로 `instance.root` default 변경이 silent schema 변경으로 해석되면 ADR-0031 의 v2 ADR 발의 요구.
- **권장 해결책**: v2 §5.5 에 명시 — "`wikihub.yaml.example` 의 `version: 1` **유지** (schema 자체 변경 없음, default 값만 변경). ADR-0031 §Decision E 의 v1 호환 가정 유효. operational yaml 의 drift check (Decision C Case B) 가 `instance.root` 의 v0.1.x default (`~/wikihub-instance`) → v0.2.0 default (`~/wikihub`) mismatch 를 detect → confirm prompt 또는 비대화 모드 exit 1. migration helper 가 이 drift 를 미리 해소 — helper 가 yaml 의 `instance.root` 도 새 path 로 atomic re-write."

### CR1-HIGH-3 — Hermes external_dirs marker comment 의 migration 후 적용 누락
- **위치**: analysis_and_design.md §5.3.1 step 5, §7.2
- **결함**: ADR-0032 §sub-3 (β) 가 marker comment 패턴 명시 ("`# managed by wikihub install.sh — remove to disable auto-discovery`"). v1 의 migration helper step 5 ("~/.hermes/config.yaml 의 external_dirs realpath 갱신") 는 **stale entry 제거 + 신규 entry 추가** 명시하나, 신규 entry 에 ADR-0032 의 marker comment 부착 여부 미명시. 부착 안 하면 다음 install.sh 호출 시 `_step6_agent_skill _patch_hermes_external_dirs` 가 marker 부재 detect → "운영자 의도 보존" 분기 → skip → 운영자가 다음 update 에서 hermes 가 신 path 미인식 issue surface.
- **권장 해결책**: v2 §5.3.1 step 5 명시 추가: "신규 entry 에 ADR-0032 §sub-3 의 marker comment (`# managed by wikihub install.sh — remove to disable auto-discovery`) 부착. 다음 `_step6_agent_skill` 호출 시 idempotent no-op 보장."

### CR1-HIGH-4 — ADR-0034 신설 vs 7건 Note 의 결정 부재가 §9.1 종료 조건 의존
- **위치**: analysis_and_design.md §8.3, §9.1
- **결함**: v1 §9.1 가 "ADR-0034 신설 여부 lock" 을 Step 2 종료 조건에 포함. 그러나 본 feature 의 영향 매트릭스 (§7.1) 가 ADR Note 추가 7건 + ADR-0034 신설 (선택) 으로 옵션 두 가지 모두 살아있음. CLAUDE.md §3 의 ADR 컨벤션 ("결정 = 1 ADR") + Step 2 의 미결 사항 lock 원칙상 **둘 다 active 상태로 Step 3 진입 불가**.
  - 또한 **단일 architectural 결정 (XDG layout) 의 cross-cutting 효과** 라는 점에서 ADR-0034 단일 신설이 자연. ADR-0030 의 4 sub-decision 묶음 모델 (§Considered Options 의 "동일 관심사 sub-decision 묶음 허용") 과 동형.
- **권장 해결책**: v2 §8.3 를 lock 결정 표로 격상 — **ADR-0034 (XDG layout 정본화) 신설 권장**. 본문에 4 sub-decision 묶음:
  - sub-1: layout 채택 (δ-2 XDG src)
  - sub-2: env 명명 (B 변수 swap)
  - sub-3: credentials_path 격리 (B 외부 유지 또는 A data-first)
  - sub-4: migration helper 책임 분리 (C 별도 script)
  
  ADR-0010·0020·0023·0029·0030·0031·0032 는 cross-reference Note 만. 결정 정본은 ADR-0034 본문. 이 모델이 §7.1 의 영향 매트릭스 분산과 §8.3 의 옵션 (가/나) 의 단일 답 lock.

### CR1-HIGH-5 — `.venv_path` sidecar 와 venv 위치의 dir 분리 영향 미명시
- **위치**: analysis_and_design.md §5.2.6
- **결함**: ADR-0020 §Decision (line 39) 의 "venv path 사이드카: install.sh Step 3 가 `~/wikihub/.venv_path` 에 절대 경로 기록. /wh:setup 의 Python helper 가 systemd unit substitution 시 read." 본 feature 후 sidecar 가 `$WIKIHUB_SRC/.venv_path` (= `~/.local/share/wikihub/src/.venv_path`) 로 이동 (v1 §5.2.6). venv 자체는 `~/.local/share/wikihub/venv/` 유지 (변경 없음). 즉 sidecar 와 venv 가 같은 `~/.local/share/wikihub/` 의 sibling dir — 자연. 단:
  - `render_systemd_units.py` 가 sidecar 를 read 하는 path resolution 명시 부재. v0.1.x 는 `$WIKIHUB_HOME/.venv_path` (= repo dir) 였음.
  - `--force-fresh` 시 src dir 가 wipe → sidecar 같이 wipe → install.sh 가 재생성 → render 호출 → OK. 단 wipe 와 재생성 사이에 systemd unit fire 시 sidecar 부재 → render fail 가능 — 본 race 의 명시 부재.
- **권장 해결책**: v2 §5.2.6 에 추가 명시:
  - sidecar 절대 경로 정본 = `$WIKIHUB_SRC/.venv_path` (변경)
  - `render_systemd_units.py` 의 read path 갱신 — `_wikihub_src() / ".venv_path"`
  - `--force-fresh` 의 wipe → systemd stop sequence (ADR-0030 sub-1) 이 선행이라 race 없음 (명시).

### CR1-HIGH-6 — `_system/VERSION` v0.2.0 bump 가 update_mode (ADR-0030) detect 분기에 미치는 영향
- **위치**: analysis_and_design.md §9.2
- **결함**: ADR-0023 의 Note (2026-05-17, update_mode feature, line 79~88) 가 detect 시그널 = "`$WIKIHUB_HOME/_system/VERSION` AND `$WIKIHUB_HOME/.git` 존재" 명시. 본 feature 후 detect 시그널은 `$WIKIHUB_SRC/_system/VERSION` + `$WIKIHUB_SRC/.git` (v1 §5.2.7 명시). 단:
  - v0.1.x 운영자가 본 feature 적용 전 install.sh 호출 시 v0.2.0 install.sh 가 fetch 되면 detect 가 v0.1.x layout 의 `~/wikihub/.git` 발견 → update path 진입 시도 → src dir 부재로 fail. 이 transition 시점 detect 분기 명시 부재.
  - v1 §5.3.2 의 legacy detect 분기가 이 case 를 catch 하나 detect 조건 순서가 명시 안 됨 (legacy detect 가 v0.2.0 detect 보다 우선 검사?).
- **권장 해결책**: v2 §5.3.2 에 detect 순서 명시 추가:
  1. **첫 검사**: legacy v0.1.x layout (`~/wikihub-instance/` + `~/wikihub/.git` + origin 검증) — 발견 시 migration helper 호출 또는 fail-fast.
  2. **두번째 검사**: v0.2.0 update path (`$WIKIHUB_SRC/_system/VERSION` + `$WIKIHUB_SRC/.git`) — 발견 시 update_mode.
  3. **셋째 검사**: fresh install — 둘 다 없으면 신규 clone.
  - 이 분기 순서가 ADR-0023 Note + ADR-0030 의 detect 시그널 명세와 정합.

### CR1-HIGH-7 — migration helper 의 backup 디스크 사용량 (cp -r) — 대용량 wiki 운영자 영향
- **위치**: analysis_and_design.md §5.3.1 step 2
- **결함**: helper step 2 가 `cp -r $LEGACY_INSTANCE ${LEGACY_INSTANCE}.pre-migration.<ts>` — 즉 `~/wikihub-instance/` 전체 cp. v0.1.x 운영자가 wiki 콘텐츠 GB 단위 보유 시 (sources/<vault>/ 의 PDF/PPT 다수) **2배 디스크 사용량** 발생. OCI free tier (50GB) 운영자에게 무시 못할 부담.
  - 대안: `mv-then-rollback` — backup 안 만들고 mv 만. 실패 시 rollback 으로 reverse mv. ext4 의 same-FS mv 는 atomic — disk space 0 추가.
  - 그러나 mv-only 는 rollback 시 부분 상태 (CR1-CRIT-4) 와 결합 위험.
- **권장 해결책**: v2 §5.3.1 step 2 의 backup 형식 옵션을 명시:
  - **(α) cp -r backup**: 안전. disk 2배. — 본 v1 default.
  - **(β) mv-only + transactional state file**: disk 0 추가. rollback 은 reverse mv. CRIT-4 의 state machine 과 결합.
  - **(γ) cp -rl hardlink backup** (same-FS only): disk overhead 거의 0 + rollback 시 backup dir 의 hardlink 보존. ext4 표준 지원.
  
  default = (γ) hardlink — XDG src 와 instance dir 가 같은 FS (운영자 home) 가정. cross-FS 시 (α) cp -r fallback. 디스크 free space 사전 확인 (instance dir size + 20% headroom) 후 진행.

### CR1-HIGH-8 — `WIKIHUB_SRC` 명명의 의미 모호성 + XDG 표준 정합
- **위치**: analysis_and_design.md §4.1, §5.1
- **결함**: v1 의 `WIKIHUB_SRC` 명명이 "source code dir" 의미. 그러나 XDG 표준의 `XDG_DATA_HOME` (`~/.local/share/`) 은 **data** 의미. 운영자가 `WIKIHUB_SRC` 를 보고 "이게 어디로 가나" 직관 약함. 또한 `~/.local/share/wikihub/src/` 의 "src" 가 XDG 의미와 충돌 ("data" 위치인데 "src" 하위).
  - 대안 1: `WIKIHUB_REPO` (= repo dir, .git 보유). install.sh 가 git clone 대상이라 명확.
  - 대안 2: `WIKIHUB_CODE` (= code dir). 일반 단어.
  - 대안 3: `WIKIHUB_SRC` 유지 — Python venv 의 "src layout" 관례 (PEP 517·518) 와 친밀. 그러나 본 feature 는 Python project 아닌 install hub.
- **권장 해결책**: v2 §4.1 옵션 (B) 의 sub-option 추가 — env 명명 후보 3개 (`WIKIHUB_SRC` vs `WIKIHUB_REPO` vs `WIKIHUB_CODE`) 비교. 추천: **`WIKIHUB_REPO`** — git clone target 의미 명확 + XDG data dir 와 의미 충돌 없음 + multi-instance 시 "prod-repo / staging-repo" 자연. lock 결정은 사용자 선호 의존.

---

## MED — backlog 처리 가능

### CR1-MED-1 — v0.1.x 운영자 base 측정 또는 가정 명시 부재
- **위치**: analysis_and_design.md §1.3, §4.1 옵션 (B) 단점
- **결함**: v1 이 "v0.1.0 운영자 base 가 적어 migration 부담 낮음" 을 가정 (§1.3). 실제 운영자 수의 측정·근거 부재. v0.2.0 release 시점 운영자가 1명 (메인테이너) 이면 backwards-incompat 부담 0; 운영자 다수면 부담 surface.
- **권장 해결책**: v2 §1.3 에 명시 — "현 운영자 = 메인테이너 1인 (v0.1.0 acceptance 직후 시점). multi-machine deployment 미적용. 따라서 backwards-incompat 의 외부 영향 0. 본 가정이 v0.2.0 release 시점에 무효 (예: 외부 사용자 운영) 면 ADR-0034 의 migration 정책 강화 (예: dual-mode 지원 기간 명시) 추가 검토."

### CR1-MED-2 — multi-instance 시 systemd SyslogIdentifier 분기 미명시
- **위치**: analysis_and_design.md §4.4
- **결함**: v1 §4.4 가 multi-instance 운영 시 systemd unit 의 SyslogIdentifier 가 vault_id 만 구분 — instance label 미도입 (v0.2.x deferral). 그러나 본 feature 가 multi-instance 지원을 "default" 로 보이게 만드는 효과 — `WIKIHUB_HOME=/var/wikihub-prod` 사용자가 별도 instance label 없이 logs 진단 시 충돌.
- **권장 해결책**: v2 §4.4 에 deferred TODO 명시 + Out of Scope §10 와 cross-reference. 본 feature 범위 밖이지만 multi-instance UX 의 next step 식별.

### CR1-MED-3 — V3 (legacy migration) PASS 기준 7단계의 측정 방법 부재
- **위치**: analysis_and_design.md §9.3 V3
- **결함**: V3 의 PASS 기준이 (1)~(7) 7 단계 — 각 step 의 측정 방법 (예: "ExecStart path 정합 확인" 어떻게? `grep -r ExecStart ~/.config/systemd/user/wikihub-*.{service,timer}` + 신 path 매칭?) 부재.
- **권장 해결책**: v2 §9.3 V3 row 의 각 step 마다 1줄 measurement:
  - (1) systemd stop → `systemctl --user is-active vault@*.service` 모두 `inactive`
  - (2) backup → `ls -la ${LEGACY_INSTANCE}.pre-migration.*` 존재 + size 검증
  - (3) mv repo → `ls -la ~/.local/share/wikihub/src/.git/` 존재 + `~/wikihub/.git/` 부재
  - (4) mv instance → `ls -la ~/wikihub/wikihub.yaml` 존재 + `~/wikihub-instance/` 부재 (또는 backup 만)
  - (5) hermes patch → `grep "_generated" ~/.hermes/config.yaml` 가 신 path realpath
  - (6) render → `grep -r "ExecStart" ~/.config/systemd/user/wikihub-*` 가 신 path
  - (7) systemd start + vault@.service fire → `journalctl --user -u vault@<id>.service --since=1m` 가 "OK" 라인

### CR1-MED-4 — V4 (`--force-fresh` wipe scope) 측정 방법 부재
- **위치**: analysis_and_design.md §9.3 V4
- **결함**: "(2) `~/wikihub/` (운영 자산) 변경 없음" PASS 기준의 측정 방법 부재. 단순 mtime 비교 또는 sha256 등 명시.
- **권장 해결책**: v2 §9.3 V4 row 에 명시 — "wipe 직전 `find ~/wikihub/ -type f -exec sha256sum {} \;` snapshot 캡처. wipe 후 동일 명령 재실행 → diff 0 라인. 만약 운영 자산 timestamp 만 변경되고 content 동일하면 OK (예: vault@.service 가 file_map.json 갱신)."

### CR1-MED-5 — V5 (WIKIHUB_INSTANCE_ROOT detect fail-fast) exit code + 안내 정확도 부재
- **위치**: analysis_and_design.md §9.3 V5, §5.3.3
- **결함**: §5.3.3 의사 코드가 `exit 1` 명시. 그러나 V5 의 PASS 기준은 "exit 1 + 안내" 만 — 안내 정확 문구 (예: 사용 운영자의 다음 액션) 와 stderr/stdout 구분 명시 부재.
- **권장 해결책**: v2 §5.3.3 의 fail-fast 메시지 정본화:
  ```
  stderr:
    ✗ WIKIHUB_INSTANCE_ROOT env 는 v0.2.0 부터 폐기됨.
    
    v0.1.x layout (~/wikihub-instance) 사용 중이면:
      → 마이그레이션: bash scripts/migrate_layout.sh
      → 또는 자동: install.sh 가 legacy detect → helper 호출 prompt
    
    v0.2.0 신규 설치면:
      → unset WIKIHUB_INSTANCE_ROOT
      → 필요 시 export WIKIHUB_HOME=<운영 자산 dir> WIKIHUB_SRC=<시스템 코드 dir>
  
  exit code: 1
  ```

### CR1-MED-6 — `_system/INSTALLED_VERSIONS.json` mixed state detect 부재
- **위치**: analysis_and_design.md §5.2.7
- **결함**: ADR-0031 §Decision B (line 101) 의 `gws_min_version` source 가 `$WIKIHUB_HOME/_system/INSTALLED_VERSIONS.json`. 본 feature 후 path = `$WIKIHUB_SRC/_system/INSTALLED_VERSIONS.json`. v0.1.x → v0.2.0 transition 중 mixed state (v0.1.x INSTALLED_VERSIONS.json 가 `~/wikihub/_system/` 에 있고 신 install.sh 가 `~/.local/share/wikihub/src/_system/` 에서 찾음 → 부재) 가능.
- **권장 해결책**: v2 §5.2.7 에 fallback 명시 — "신 path 부재 시 legacy path (`~/wikihub/_system/INSTALLED_VERSIONS.json`) 조회 fallback. migration helper 가 INSTALLED_VERSIONS.json 도 src 안으로 mv 명시 (helper step 3 의 일부)."

### CR1-MED-7 — `render_systemd_units.py` 의 substitution key 영향 매트릭스 부재
- **위치**: analysis_and_design.md §5.4
- **결함**: v1 §5.4 가 `{wikihub_home}`·`{wikihub_src}`·`{instance_root}` 명시. 그러나 systemd unit template 에 다른 substitution key (예: `{venv_path}`·`{vault_id}`·`{instance_label}` 등) 존재 가능 — 매트릭스 부재로 영향 평가 불완전.
- **권장 해결책**: v2 §5.4 에 substitution key 전수 표 추가:
  | key | source | Before | After |
  |---|---|---|---|
  | `{wikihub_home}` | env / default | repo dir | 운영 dir |
  | `{wikihub_src}` (신규) | env / default | — | src dir |
  | `{instance_root}` (deprecated) | env / default | instance dir | alias of `{wikihub_home}` 또는 제거 |
  | `{venv_path}` | sidecar file | `~/.local/share/wikihub/venv` | 변경 없음 |
  | `{vault_id}` | systemd `%i` | (변경 없음) | (변경 없음) |
  - 추가 key 가 있으면 Step 3 진입 전 코드베이스 grep 으로 enumerate.

### CR1-MED-8 — Schema migration guide URL 미명시
- **위치**: analysis_and_design.md §9.2 + ADR-0010 §line 169
- **결함**: ADR-0010 §line 169 ("schema migration guide URL 안내 + fail-fast") 가 v1 → v2 transition 시 URL 제공 의무. 본 feature 가 `_system/VERSION` v0.1.0 → v0.2.0 bump 하지만 schema migration guide URL 명시 부재 — README 의 어느 섹션, 어느 anchor?
- **권장 해결책**: v2 §5.8 에 추가 — "`README.md#v01x-v02-migration` anchor 신설. install.sh 가 schema mismatch detect 시 안내 URL 출력. ADR-0010 §line 169 + ADR-0031 §Decision E 의 migration guide 약속과 정합."

---

## LOW — 참고

### CR1-LOW-1 — v1 의 "ADR Notes (cross-feature 정합)" 표현 (§5.7) 과 §7.1 의 처리 분류 일관성 약함
- **위치**: §5.7 (line 434~443) vs §7.1 (line 491~504)
- **결함**: §5.7 는 ADR 7건 모두 "Note 추가" 로 통일. §7.1 는 ADR-0023·ADR-0030 만 "§Decision 갱신" + 나머지 "Note 추가" 로 분리. 두 표 정합 불완전. CR1-CRIT-2 도 본 항목의 surface.
- **권장 해결책**: v2 에서 §5.7 와 §7.1 의 표 통일 — 단일 source. ADR-0034 신설 lock 시 두 표 모두 cross-reference Note 로 통일.

### CR1-LOW-2 — v1 §3.7 의 `_instance_root_default()` 함수명 정확도
- **위치**: §3.7 (line 146)
- **결함**: 실제 `render_systemd_units.py` 의 함수명 확인 필요. v1 본문이 실제 구현과 정합 검증 부재.
- **권장 해결책**: v2 Step 3 진입 전에 `grep -n "_instance_root_default\|_wikihub_home" scripts/_helpers/render_systemd_units.py` 로 실제 명세 확인 후 반영.

### CR1-LOW-3 — README 의 install snippet 갱신 분량 (§5.8)
- **위치**: §5.8 (line 446~450)
- **결함**: README install snippet 의 변경 분량 (+30~50줄, plan.md §영향 범위) — `WIKIHUB_HOME` semantic 변경 안내 + migration guide + multi-instance 예시 + XDG 설명 등. 분량 통제 명시 부재.
- **권장 해결책**: v2 §5.8 에 README 갱신 sub-section 목록 명시 (1. install snippet, 2. directory structure diagram, 3. v0.1.x→v0.2.0 migration anchor, 4. multi-instance section). 각 sub-section 길이 가이드.

### CR1-LOW-4 — `~/.credentials/wikihub/` 외부 유지 (§5.5 미결 #5 (B)) 의 ADR-0029 cross-reference 정합
- **위치**: §5.5 (line 261, 427)
- **결함**: §5.5 의 "(B) 유지" 가 ADR-0029 §Decision 의 default path (`~/wikihub-instance/.credentials/`) 와 정합 안 함 — CR1-CRIT-1 와 결합. (B) 채택은 ADR-0029 §Decision 본문 변경 의무.
- **권장 해결책**: CR1-CRIT-1 의 해결과 함께 처리. v2 §5.5 의 "권장: (B) 유지" 문구 → "권장: (B) 외부 격리 — ADR-0029 §Decision default 갱신 필요" 로 정정.

### CR1-LOW-5 — `feat_id` 의 KST 표기 (§7 Features 디렉토리 컨벤션)
- **위치**: features/20260519_dir_layout_refactor/ (디렉토리명)
- **결함**: CLAUDE.md §8 의 feature 디렉토리 명명 규칙 (`YYYYMMDD = 작업 시작일 KST`). 현 디렉토리 `20260519` — 시작일 2026-05-19 KST 정합 OK. 단 plan.md line 5 의 "**시작일 (KST)**: 2026-05-19" 와 v1 의 timestamp 정합 OK. 본 항목 영향 없음.
- **권장 해결책**: 없음 (검증 통과).

---

## 추가 관찰

### 관찰 1 — 본 feature 의 정본성 보존 범위 (§1.2) 가 ADR-0006 명시 부재
- v1 §1.2 의 "선행 feature 의 정본성 보존" 목록 (ADR-0006/0010/0020/0030/0031/0032) — ADR-0006 (agent orchestration) 만 영향 없음 명시. ADR-0010/0020/0030/0031/0032 는 변경 영향 있음 — "정본성 보존" 표현이 모호. v2 에서 "정본성 보존" 의 의미를 "**책임 모델·invariant 보존, path 변경만**" 으로 명확화 권장.

### 관찰 2 — ADR-0010 의 install.sh + /wh-setup 책임 split 의 path 매트릭스 명시 효과
- v1 §7.1 ADR-0010 row 의 "Dev/Ops Zone 분리가 XDG path 로 명시화. install.sh = src dir 책임, /wh-setup = data dir 책임" 표현이 정확. 단 ADR-0010 §"도구별 책임 매트릭스" (line 42~48) 의 path 컬럼이 갱신되어야 함 (install.sh 의 path = `~/.local/share/wikihub/src/install.sh`, `/wh:setup` 의 yaml write target = `~/wikihub/wikihub.yaml`). 본 효과를 §7.1 ADR-0010 row 에 추가 명시 권장.

### 관찰 3 — ADR-0034 신설 권장 (CR1-HIGH-4) 의 추가 효과
- ADR-0034 단일 ADR 묶음 채택 시 본 review 의 7건 cross-feature 분산을 1건 정본 + 7건 Note 로 압축 — trace 단순화. CLAUDE.md §3 의 "ADR-NNNN 식별자 참조" 원칙과 자연 정합. 추천 강도 높음.

### 관찰 4 — sparse-checkout 영속화 (ADR-0023/0030) 의 본 feature 영향 미명시
- ADR-0023 의 2026-05-18 Note (line 90~138) sparse-checkout + ADR-0030 §부정/제약 의 sparse-checkout 영속화 (line 79) 가 본 feature 의 `$WIKIHUB_SRC/` 에 그대로 적용되어야 함. v1 의 sparse-checkout 영향 명시 부재. v2 §5.2 install.sh 변경 항목에 추가 — "sparse-checkout 정책은 `$WIKIHUB_SRC/` 의 clone 에서도 동일 적용. ADR-0023 Note + ADR-0030 §부정/제약 정합 유지."

### 관찰 5 — Migration helper 의 `WIKIHUB_NONINTERACTIVE=1` 분기와 ADR-0032 의 동의 surface 정합
- ADR-0032 §sub-4 (β) 의 `WIKIHUB_NONINTERACTIVE=1` 단일 toggle 이 외부 자산 동의 포함 (CR2-HIGH-2 해결 — F5). 본 feature 의 migration helper 가 hermes config patch 도 수행 — 동일 NONINTERACTIVE flag 가 본 feature 의 helper 도 적용되는지 명시 필요. v2 §5.3.1 의 helper 헤더에 명시 권장.

---

## 종합 — v2 에서 우선 처리 권장

1. **CR1-CRIT-1, CR1-CRIT-2**: ADR-0023 §Decision 본문 갱신 + ADR-0029 §Decision 본문 갱신. "Note 추가" 처리 분류 정정.
2. **CR1-CRIT-3, CR1-CRIT-4, CR1-CRIT-5**: migration 의 silent bug surface · idempotency state machine · systemd in-flight grace 명시.
3. **CR1-HIGH-4**: ADR-0034 신설 lock — 4 sub-decision 묶음. 7건 ADR Note 는 cross-reference 만.
4. **CR1-HIGH-1, CR1-HIGH-2, CR1-HIGH-3, CR1-HIGH-5, CR1-HIGH-6, CR1-HIGH-7, CR1-HIGH-8**: 각 항목 명시 갱신.
5. MED 8건은 v2 또는 Step 3 진입 전 backlog 정리.
6. LOW 5건은 v2 의 §7.1 vs §5.7 통일 + 함수명 검증 등 minor cleanup.

CRIT 5건 모두 v2 반영 후 사용자 lock 권장. ADR-0034 신설 + env 명명 (B) 변수 swap lock 가 v2 의 핵심.
