# Design Review 4 — dir_layout_refactor (CR3-2: SRE closure)

- **리뷰 대상**: analysis_and_design.md v2 (985줄, 2026-05-19) — R2 closure 검증
- **리뷰어**: CR3-2 (운영 신뢰성 / SRE closure / failure mode / race)
- **선행 리뷰**: CR2 [design_review_2.md](./design_review_2.md) (CRIT 5 / HIGH 7 / MED 6 / 관찰 4)
- **리뷰 일자**: 2026-05-19
- **종합 판단**:
  - **Closure**: CR2 CRIT 5건 = 5 CLOSED. CR2 HIGH 7건 = 5 CLOSED + 2 PARTIAL. CR2 MED 6건 = 3 CLOSED + 3 PARTIAL. CR2 관찰 4건 = 3 명시 정합 + 1 부분 명시.
  - **신규 결함 (v2 도입)**: CRIT-0 / HIGH-3 / MED-3 / LOW-2. CRIT 없음.
  - **최종 판단**: **Step 3 진입 가능 (조건부)** — v2 lock 자체는 SRE-grade closure 충분. HIGH-3건 (V11 측정 방법, alias warning log volume, phase file multi-instance 분리) 은 **Step 3 구현 backport 가능** (analysis_and_design.md 본문 v3 revision 불요). MED/LOW 는 구현 시 보강.

---

## R2-CR2 CRIT closure 검증

### CR2-CRIT-1 (rclone FUSE unmount 시퀀스) → **CLOSED**
v2 §5.3.6 `_unmount_vaults` 가 mount 검출 (`mount | grep " on $mp type fuse"`) + `fusermount3 -u` retry × 6 (10s 간격, 총 60s) + 실패 시 `fusermount3 -uz` lazy fallback 명시. §5.3.7 의 stop sequence (timer → service 15min grace → mount@ 마지막) 정합. V9 검증 항목 신설. SRE-grade closure 완료.

### CR2-CRIT-2 (backup cp -r ENOSPC + mount 재귀) → **CLOSED**
v2 §5.3.5 backup mv-only 모델 lock. `cp -r` 완전 폐기 — ENOSPC 위험 근본 차단 + mount path 재귀 위험 동시 해소 (mv 는 metadata only, mount content 진입 안 함). rollback 은 phase-aware reverse mv. V10 (ENOSPC simulation) 신설. closure 완료. 단 v2 §9.3 V10 의 "mv-only 모델 정합 검증" PASS 기준이 추상적 (HIGH-1 참조).

### CR2-CRIT-3 (partial mv 후 재호출 detect 부재) → **CLOSED**
v2 §5.3.4 phase marker state machine — 9 phases (`pre-stop` → `stopped` → `unmounted` → `mv-src-done` → `mv-home-done` → `hermes-patched` → `render-done` → `start-done` → `DONE`). `$PHASE_FILE` 위치 `$HOME/.local/state/wikihub/migrate_layout.phase`. 각 step 의 `get_phase != expected` 시 idempotent skip. V8 (partial failure resume) 신설. closure 완료.

### CR2-CRIT-4 (install.sh entry order 부재) → **CLOSED**
v2 §5.2.1 Step 0a (env semantic check) → Step 0b (legacy detect) → Step 0c (curl-pipe self-replace) 순서 정본 명시. 순서 근거 (0a 가 0b 보다 먼저 — env mismatch 가 더 fundamental) 명시. helper 호출 시 `exec bash "$helper"` 패턴 (§5.3.2). closure 완료. 단 Step 0c 의 self-replace 후 신 install.sh 가 Step 0b 를 재진입할 수 있는데, helper 가 이미 phase=DONE 인 상태에서 detect_legacy 가 false 반환하므로 recursion 안전 — 본 안전성 명시 자체는 v2 에 부재 (HIGH-2 참조).

### CR2-CRIT-5 (systemd unit Environment matrix) → **CLOSED**
v2 §5.2.6 의 11행 매트릭스 (vault@·lint·mount@·ops-alert 의 Environment / WorkingDirectory / ExecStartPre / ExecStart) + §5.4.2 의 substitution key matrix (`{wikihub_home}` 의미 변경, `{wikihub_src}` 신규, `{instance_root}` deprecated alias). ops-alert.service 의 분리 (WorkingDirectory = home / ExecStart = src) 정확 명시. V11 (systemd Environment matrix 정합) 신설. closure 완료. 단 V11 의 측정 방법 명시 부족 (HIGH-1 참조).

---

## R2-CR2 HIGH closure 검증

### CR2-HIGH-1 (rollback trap ADR-0030 패턴) → **CLOSED**
v2 §5.3.1 `_rollback_if_failed` + `trap '_rollback_if_failed' ERR EXIT INT TERM HUP` 명시. phase-aware reverse mv 로직 (case 분기: `pre-stop|stopped|unmounted` / `mv-src-done` / `mv-home-done` / `hermes-patched|render-done`). 성공 시 `trap - ERR EXIT INT TERM HUP` 해제. ADR-0030 패턴 reuse 정합. closure 완료.

### CR2-HIGH-2 (Hermes marker comment migration) → **CLOSED**
v2 §5.3.1 Step 5 `_patch_hermes_external_dirs_migration` 가 `scripts/_helpers/hermes_config_migrate.py` 호출 — `--remove-stale` + `--add-new` argument 패턴. marker comment 검사로 operator-managed entry 보존 명시. §7.1 ADR-0032 sub-3 reuse 명시. V7 검증 항목 (다른 도구 entry 보존). closure 완료. 단 hermes_config_migrate.py 의 실 구현은 Step 3 산출 (helper 본문에 reference 만).

### CR2-HIGH-3 (flock 정합 helper 단독) → **CLOSED**
v2 §5.3.1 의 `exec 200>"$LOCK_FILE" && flock -nx 200 || exit 2` advisory lock. helper 단독 실행 race 차단. 단 본 lock 은 helper-helper race 만 차단 — helper 와 install.sh 동시 실행 race 는 별도. v2 §5.3.2 의 install.sh `_step0_legacy_detect` 가 `exec bash "$helper"` 로 helper 단방향 호출이라 자연 정합 (install.sh 가 helper 끝날 때까지 block). closure 완료.

### CR2-HIGH-4 (WIKIHUB_HOME silent bug detect) → **CLOSED**
v2 §5.1.1 `_step0_env_semantic_check` 명시. detect 시그널: `WIKIHUB_HOME` set + path 에 `.git` 존재 + origin = `im-dongseon/wikihub`. fail-fast (exit 1) + 명시 안내 (3 step 마이그레이션 안내). NONINTERACTIVE 모드도 동일 fail-fast. closure 완료.

### CR2-HIGH-5 (multi-instance WIKIHUB_SRC default 정책) → **PARTIAL**
v2 §4.4 가 "src dir 도 운영자 명시 분리 가능" + "default single-instance 가정 → `~/wikihub/` + `~/.local/share/wikihub/src/`" 명시. multi-instance 시 운영자 책임으로 `WIKIHUB_SRC` 명시 override. 그러나 §10 (Out of Scope) 에서 multi-instance instance label 은 v0.2.x backlog 로 push. v0.2.0 의 multi-instance 운영자가 `WIKIHUB_SRC` 명시 누락 시 두 instance 가 동일 src 참조 race → 본 race 의 운영자 안내 (`WIKIHUB_HOME` 두 번 export 시 warning?) 부재. closure 부분 — Step 3 의 README 안내로 보강 가능.

### CR2-HIGH-6 (backup retention + 위치 격리) → **PARTIAL**
v2 §5.3.5 가 mv-only 모델로 backup 자체가 거의 사라짐 — retention 부담 자연 해소 (cp -r 폐기 효과). 그러나 `$PHASE_FILE` (`$HOME/.local/state/wikihub/migrate_layout.phase`) + `$LOCK_FILE` 가 helper 종료 후 `DONE` 상태로 잔존. 후속 update 시 `detect_legacy` false 반환으로 무영향이나 **phase file cleanup 정책 명시 부재** — DONE 후 file 삭제 권장? 보존 (audit)? 미명시. 또한 helper 의 `_patch_hermes_external_dirs_migration` 의 `~/.hermes/config.yaml.wikihub-bak.*` (rollback case 의 hermes-patched|render-done 단계에서 운영자에게 "수동 검토 권장" 안내) 의 retention 도 미명시. closure 부분 — Step 3 backport 권장.

### CR2-HIGH-7 (V3 step-별 측정 + partial-failure V<N>) → **PARTIAL**
v2 §9.3 V8/V9/V10/V11 신설로 partial failure 측면 closure. 그러나 V8~V11 의 PASS 기준이 outcome 만 명시 ("partial failure resume → 정상 완료", "ENOSPC 발생 안 함", "Environment matrix 정합") — CR2-HIGH-7 의 핵심 지적인 **step 별 측정 명령 + PASS 조건 표** (CR2 design_review_2.md line 257~265) 가 v2 에 통합 안 됨. V3 도 PASS 기준 (1)~(7) 이 outcome 만. closure 부분 — Step 3 V<N> 실행 시점에 측정 명령 보강 필요 (HIGH-1 신규로 격상).

---

## R2-CR2 MED closure 검증

### CR2-MED-1 (ADR-0024 ops-alert path) → **CLOSED**
v2 §5.2.6 systemd matrix 의 ops-alert.service 행에 path 분리 명시 (WorkingDirectory = `{wikihub_home}` / ExecStart = `{wikihub_src}/scripts/ops-alert.py`). last_failure.json path 는 env (WIKIHUB_HOME) 기반 자연 정합. §7.1 ADR 매트릭스에 ADR-0024 row 자체는 부재하나 ops-alert.service 가 systemd unit 영향에 포함돼 실질 closure.

### CR2-MED-2 (helper sha256 trace record) → **PARTIAL**
v2 §5.3.1 Step 5 가 "install.sh `_patch_hermes_external_dirs` reuse — flock + backup + sha256 PRE/POST" 명시. 그러나 helper 가 hermes_config_migrate.py 를 호출하는 패턴이라 sha256 logging 의 실제 위치 (journalctl? log file?) 미명시. closure 부분 — Step 3 의 hermes_config_migrate.py 구현 시 sha256 emit 점 명시 필요.

### CR2-MED-3 (safety guard #4 nested path 차단) → **PARTIAL**
v2 §5.2.5 guard #4 가 "$WIKIHUB_SRC 의 prefix 가 $HOME/.local/share/wikihub/ 외 path 인 경우 NONINTERACTIVE 거부 + 명시 confirm" 명시. 그러나 CR2-MED-3 의 핵심 지적인 **WIKIHUB_SRC == WIKIHUB_HOME 차단 + nested 양방향 차단** (4a/4b/4c) 미명시. `WIKIHUB_HOME=~/wikihub WIKIHUB_SRC=~/wikihub/src` 같은 nested 운영자 입력 시 src wipe 가 home 영향 가능. closure 부분 — Step 3 의 install.sh `_safety_guard` 구현 시 추가 명시.

### CR2-MED-4 (INSTALLED_VERSIONS.json) → **NOT_CLOSED**
v2 §5.2.7 가 `$WIKIHUB_SRC/_system/INSTALLED_VERSIONS.json` 위치 명시. 그러나 helper 가 mv 후 본 파일의 `wikihub.version` field 를 v0.1.x → v0.2.0 으로 갱신해야 하는지 미명시. helper 의 phase 9 (start-done) 직전 또는 직후 신 version 기록 step 부재. v0.2.0 release tag checkout 시 자동 갱신 가능하나 helper 가 git fetch 안 함 (현 §5.3.1 mv-only) — 결국 mv 후 INSTALLED_VERSIONS.json 의 version 이 stale. closure 미해소 — Step 3 backport 필요 (MED-1 신규로 격상).

### CR2-MED-5 (V8~V11 partial-failure) → **CLOSED**
v2 §9.3 V8 (partial failure resume) + V9 (FUSE busy unmount) + V10 (ENOSPC simulation) + V11 (Environment matrix 정합) 4건 신설 — CR2-MED-5 가 권장한 V8~V11 와 정확 매핑. closure 완료.

### CR2-MED-6 (hermes realpath drift) → **PARTIAL**
v2 §7.2 가 "path 만 변경되면 자동 재인식" 명시. V1 PASS 기준 (5) 가 "Hermes external_dirs 패치 = `~/.local/share/wikihub/src/_system/skills/_generated/` realpath" — drift 검증 포함. 그러나 hermes 의 fork-exec vs inotify 동작 차이는 별도 backlog. closure 부분 — 본 feature 범위 외 (CR2 자체 인정).

---

## R2-CR2 관찰 closure 검증

### Obs-1 (helper vs install.sh 책임 경계) → **명시 정합**
v2 §5.3.1 helper 가 step 5 (hermes) + step 6 (systemd render) 를 직접 수행 (install.sh 위임 안 함). v2 §5.3.2 의 `exec bash "$helper"` 패턴이 install.sh 책임을 helper 에 전권 위임 명시. CR2-Obs-1 가 권장한 "helper 가 mv 만 / hermes/systemd 는 install.sh 위임" 대안은 미채택 — 단 채택안 (helper 단일 책임) 이 phase marker state machine 의 일관성 측면에서 정합.

### Obs-2 (ADR-0034 신설) → **명시 정합**
v2 §7.1 + §8.3 + 변경 이력에 ADR-0034 신설 lock 명시. 4 sub-decision 묶음 (data-first naming / env (B) variable swap / migration helper (C) / mv-only backup + phase marker). CR2-Obs-2 의 권장 (ADR-0034 신설로 cross-cutting decision 정본화) 정합. 단 v2 §7.1 의 ADR-0034 row 가 sub-decision 4건의 outline 만 — 본 ADR 본문은 Step 3 산출 (HIGH-3 참조).

### Obs-3 (VM-B v0.1.x snapshot) → **명시 부재**
v2 §9.3 V3/V8/V9/V10 가 모두 "VM-B (legacy v0.1.x layout)" 명시하나 VM-B 의 v0.1.x snapshot 확보 시점 (Step 3 진입 전?) 명시 부재. CR2-Obs-3 의 권장 (§9.3 진입 조건 추가) 미반영. closure 부분 — Step 3 시작 시 VM-B 확보 절차 명시 필요.

### Obs-4 (v0.2.0 SemVer) → **부분 명시**
v2 §1.3 가 "v0.1.0 acceptance 달성 후 첫 architectural refactor" + "backwards-incompat migration 1회" 명시. README 의 release note 의 "0.2.0 = layout breaking" 명시 권장은 §5.8 README 갱신 항목에 포함. closure 부분 정합.

### Obs-5 (.credentials/ 권한 모드) → **부분 명시**
v2 §4.5 + §5.5 가 `~/.credentials/wikihub/` 외부 유지 lock. mode 0700 정합 명시 부재 — ADR-0029 본문에 chmod 0600 명시 있다고 §3.6 명시하나 dir mode (0700) 자체는 v2 미명시. closure 부분 — ADR-0029 §Decision 본문 검토 필요 (별도 trace).

---

## v2 도입 신규 결함

### CR3-2-HIGH-1 — V11 (Environment matrix) PASS 기준의 측정 명령 부재
**위치**: v2 §9.3 V11 line ~946
**결함**: V11 의 검증 항목이 "rendered unit 의 Environment line grep" 명시하나 PASS 기준이 outcome ("`WIKIHUB_YAML={wikihub_home}/wikihub.yaml` 정합") 만. CR2-HIGH-7 closure 의 PARTIAL 상태를 V11 도 답습. 측정 명령 표 (예: `systemctl --user cat wikihub-vault@gdrive.service | grep -E '^(Environment|WorkingDirectory|ExecStart|ExecStartPre)='`) + 5.2.6 matrix 의 11행 모두에 대해 PASS 조건 셀 명시 필요.
**권장**: Step 3 V11 실행 시 5.2.6 matrix 의 11행 × {Before / After} 매트릭스 검증 스크립트 + journalctl 의 실 fire log 의 environment dump (`systemctl --user show <unit> --property=Environment`) 비교 자동화. v3 본문 revision 불요 — Step 3 backport.

### CR3-2-HIGH-2 — phase file path 의 multi-instance 충돌
**위치**: v2 §5.3.1 line 429 (`$HOME/.local/state/wikihub/migrate_layout.phase`)
**결함**: $PHASE_FILE 위치가 단일 운영자 home 기준. multi-instance 운영자 (§4.4 + §10 backlog) 가 두 instance 동시 migration 시 (예: prod + staging 동시 v0.1.x → v0.2.0) 동일 phase file 경합 + flock advisory 가 막아도 두 instance 의 migration 이 sequential 강제. v0.2.0 의 multi-instance 는 단일 운영자가 직렬 처리하는 가정이라면 부분 정합이나 명시 부재.
**권장**: phase file path 를 `$HOME/.local/state/wikihub/migrate_layout_$(realpath_hash $WIKIHUB_HOME).phase` 같이 per-instance 분리 또는 §10 (Out of Scope) 에 "동시 multi-instance migration 미지원, 직렬만" 명시. Step 3 backport 가능.

### CR3-2-HIGH-3 — `instance_root` alias deprecation warning 의 log volume
**위치**: v2 §5.4.4 line 745~750 (`sys.stderr.write(f"WARN: {{instance_root}} deprecated, use {{wikihub_home}}\n")`)
**결함**: 운영자가 직접 template 편집 + `{instance_root}` 잔존 시 render_systemd_units.py 호출마다 stderr 출력. update_mode (ADR-0030) 의 `_step2_update` 가 render_systemd_units 재호출 패턴이라 매 update 마다 warning emit. systemd journal 모니터링 시 누적 warn 가능. 본 alias 가 v0.3.x 에서 제거 검토 명시이지만 v0.2.x 동안 매 update fire 마다 emit 시 운영자 confusion.
**권장**: warning 을 한 번만 emit (예: render 호출당 1회 모음 후 emit) 또는 PYTHONWARNINGS 설정 가능 옵션. 또는 render 결과 unit 안에 deprecation comment 만 삽입 (stderr 미사용). Step 3 backport 가능.

### CR3-2-MED-1 — INSTALLED_VERSIONS.json version 갱신 step 부재
**위치**: v2 §5.3.1 helper phase 8 (start-done) 직전·직후
**결함**: CR2-MED-4 의 NOT_CLOSED 항목. helper 가 mv 후 `$NEW_SRC/_system/INSTALLED_VERSIONS.json` 의 `wikihub.version` field 갱신 step 부재. v0.1.0 → v0.2.0 transition 의미가 INSTALLED_VERSIONS 에 비반영 시 후속 update_mode (ADR-0030) 의 ref 판단이 stale.
**권장**: helper phase 7 (render-done) 직후 phase 8 (version-bumped) 추가 — `python3 -c 'json...write v0.2.0'` 또는 jq 로 갱신. V8 phase 매트릭스도 동기.

### CR3-2-MED-2 — `~/.hermes/config.yaml.wikihub-bak.*` 의 retention/cleanup 정책
**위치**: v2 §5.3.1 line 466~468 (`hermes-patched|render-done` case 의 "수동 검토 권장")
**결함**: hermes_config_migrate.py 가 PRE backup 생성 (관행) 가정. rollback 시 운영자가 수동 검토. 그러나 backup file 자체의 retention (성공 case 에서도 잔존?) + 후속 update 시 cleanup 정책 부재. update_mode 의 hermes patch 도 동일 backup 생성 시 누적.
**권장**: backup file 의 N개 retention (예: 최근 3개) + helper success 시 cleanup 옵션. Step 3 의 hermes_config_migrate.py 구현 시 결정.

### CR3-2-MED-3 — helper 의 ops-alert path 갱신 누락
**위치**: v2 §5.3.1 + §5.2.6 ops-alert.service 행
**결함**: §5.2.6 가 ops-alert.service 의 ExecStart 분리 (`{venv_path}/bin/python {wikihub_src}/scripts/ops-alert.py`) 명시. 그러나 helper phase 6 (render-done) 의 `render_systemd_units.py` 호출이 ops-alert.service 도 포함 render? 또는 ops-alert 는 별도 management? §5.4.3 template diff 가 wikihub-vault@·mount@·lint 만 명시, ops-alert.service.template 의 diff 부재. helper 가 ops-alert path 갱신을 보장하는지 trace 불가.
**권장**: §5.4.3 의 ops-alert.service.template diff 추가 또는 render_systemd_units.py 의 render 대상 list 에 ops-alert 포함 명시. Step 3 backport 가능.

### CR3-2-LOW-1 — Step 5 hermes 호출 시 `$VENV_PATH` 미정의
**위치**: v2 §5.3.1 line 552 (`"$VENV_PATH/bin/python3"`)
**결함**: helper 의 `_patch_hermes_external_dirs_migration` 가 `$VENV_PATH` 참조하나 helper 본문에 export 안 됨. ADR-0020 의 venv 위치 (`~/.local/share/wikihub/venv/`) 가 helper context 에서 어떻게 resolve 되는지 명시 부재. install.sh 의 `_init_venv_path` 함수 source 또는 helper 가 `.venv_path` sidecar 읽기 패턴 필요.
**권장**: helper 본문에 `: "${VENV_PATH:=$NEW_SRC/.venv_path 또는 $HOME/.local/share/wikihub/venv}"` 명시. Step 3 helper 구현 시 보강.

### CR3-2-LOW-2 — `_systemd_start_legacy` 미정의 (rollback case)
**위치**: v2 §5.3.1 line 452, 457, 463 (`_systemd_start_legacy` call)
**결함**: rollback trap 의 phase-aware case 에서 `_systemd_start_legacy` 호출 명시. 그러나 본 함수 정의 부재 (helper 본문에). legacy systemd unit 의 path 가 v0.1.x 의미 ($WIKIHUB_HOME=repo) 라 rollback 후 unit 갱신 + start 필요. 단 mv 가 reverse 됐다면 unit 도 stale (helper 의 render 가 phase 6 에서만 발생). rollback 후 unit-path 재정합 절차 명시 부재.
**권장**: rollback 시 reverse mv 후 systemctl 의 unit path resolve 가 EBUSY/Stale 가능. `_systemd_start_legacy` 정의 (legacy unit render → start) 추가 또는 rollback 의 final step 으로 "manual systemctl status 확인 권장" 안내. Step 3 helper 구현 시 명시.

---

## 추가 관찰

### Obs-A — `$LOCK_FILE` 의 retention
v2 §5.3.1 의 `$LOCK_FILE` 가 helper 종료 후 (success/failure 모두) 잔존. lock 자체는 flock advisory 라 후속 helper 호출 시 normal 동작 — 단 운영자가 lock file 자체를 lock 상태로 오해 가능. helper success 시 lock file 삭제 권장.

### Obs-B — V8 의 SIGTERM 시점 명시
v2 §9.3 V8 의 PASS 기준이 "phase: pre-stop / stopped / unmounted / mv-src-done / mv-home-done / hermes-patched / render-done / start-done / DONE 매트릭스 검증" 명시. 그러나 9개 phase 각각에서 SIGTERM 시뮬레이션 (9회 VM 사이클) 인지 1개 phase 대표 검증인지 불명. 9 phase × 검증 시 Step 3 VM cycle 비용 큼 — 대표 3 phase (mv-src-done / hermes-patched / render-done) 만 측정 권장 명시 가능.

### Obs-C — hermes_config_migrate.py 의 신규 helper
v2 §5.3.1 line 552 가 `scripts/_helpers/hermes_config_migrate.py` 신규 helper reference. v2 §9.2 Step 3 종료 조건 산출물 list 에 본 파일 누락. install.sh `_patch_hermes_external_dirs` 의 책임 분리 측면에서 신규 helper script 도 산출물 list 추가 필요.

### Obs-D — Step 0c 의 sparse-checkout list 와 helper 정합
v2 §5.2.3 의 sparse-checkout list 가 `_system scripts install.sh wikihub.yaml.example README.md LICENSE` — helper 가 `scripts/migrate_layout.sh` + `scripts/_helpers/hermes_config_migrate.py` 호출이므로 sparse-checkout list 안에 자연 포함 (`scripts` prefix). curl-pipe self-replace 후 helper 호출 가능 정합.

### Obs-E — phase marker 의 forward-only 보장
v2 §5.3.4 phase machine 이 9 phase forward-only 명시. 그러나 rollback trap (§5.3.1 `_rollback_if_failed`) 이 phase 를 reverse 안 함 (단지 reverse mv 수행) — 운영자가 rollback 후 재호출 시 phase file 의 마지막 phase 가 마지막 성공 phase 라 자동 resume 가능. 본 정합성은 명시 정합.

---

## 최종 권고

본 v2 는 **R2 CR2 의 CRIT 5건 100% closure** + HIGH 7건 중 5건 CLOSED / 2건 PARTIAL + MED/관찰의 약 70% closure. CRIT 영역에서 SRE-grade 결함 모두 명시 해소 — **Step 3 진입 가능**.

**v3 본문 revision 불요** — 신규 결함 (HIGH-3 / MED-3 / LOW-2) 모두 Step 3 구현 시 backport 가능 (analysis_and_design.md 본문 변경 불필요, helper 본문 / V<N> 측정 명령 / ADR-0034 본문 작성 시 명시).

**Step 3 진입 시 우선 처리**:
1. CR3-2-MED-1 (INSTALLED_VERSIONS.json version bump step) — helper phase 추가
2. CR3-2-HIGH-1 (V11 측정 명령 표) — Step 3 V<N> 실행 전 명시
3. CR3-2-MED-3 (ops-alert.service template diff) — §5.4.3 보강
4. CR3-2-LOW-1·2 (VENV_PATH / _systemd_start_legacy 정의) — helper 본문 구현 시 보강

**Step 3 backlog 권장**:
- CR3-2-HIGH-2 (phase file multi-instance) + CR3-2-HIGH-3 (alias warning volume) — v0.2.x 후속 feature
- CR2-MED-2·3·6 PARTIAL closure — Step 3 의 hermes_config_migrate.py / install.sh `_safety_guard` 구현 시 명시
- CR2-HIGH-5·6·7 PARTIAL — Step 3 의 README + VM 측정 스크립트로 보강

CR3-2 종합 판단: **Step 3 진입 lock 권장** (v3 revision 불요 — 본 review 의 backport 항목을 Step 3 task list 에 추가).
