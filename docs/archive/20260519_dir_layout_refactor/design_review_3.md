# Design Review 3 — dir_layout_refactor (CR3-1: spec closure)

- **리뷰 대상**: analysis_and_design.md v2 (985줄, R2 closure 검증)
- **리뷰어**: CR3-1 (spec / ADR 정합 closure)
- **선행 리뷰**: CR1 design_review_1.md (CRIT 5 / HIGH 8 / MED 8 / LOW 5)
- **리뷰 일자**: 2026-05-19
- **종합 판단**:
  - **Closure 평가**: CR1-CRIT 5건 = (4 CLOSED / 1 NOT_CLOSED). CR1-HIGH 8건 = (5 CLOSED / 2 PARTIAL / 1 NOT_CLOSED). CR1-MED 8건 = (1 CLOSED / 5 PARTIAL / 2 NOT_CLOSED) — MED 는 §변경이력 v2 entry 가 "Step 3 backport" 로 일괄 deferred. CR1-LOW 5건 = (2 CLOSED / 3 PARTIAL).
  - **신규 결함 (v2 도입)**: CRIT-1 (CR3-NEW-CRIT-1: §3.6 진단이 ADR-0029 §Decision line 52 와 모순) / HIGH-2 / MED-3 / LOW-1
  - **최종 판단**: **v3 revision 필요** — CR3-NEW-CRIT-1 의 ADR-0029 §Decision 본문 vs v2 §3.6 진단 mismatch 가 진입 차단. CR1-CRIT-1 의 closure 라고 §변경이력 v2 entry 가 주장하지만 실제로는 진단이 잘못된 방향으로 정정됨. 1건 spec patch + 2건 명시 보강 후 Step 3 진입 가능.

---

## R2-CR1 closure 검증

### CR1-CRIT-1 (ADR-0029 진단 mismatch) → **NOT_CLOSED**

v2 §3.6 가 "ADR-0029 §Decision 본문의 정본 path 는 `~/.credentials/wikihub/sa_*.json`" 라고 적었으나 실제 `docs/adr/0029-service-account-auth.md` §Decision line 52 는:

> "scp → OCI `~/wikihub-instance/.credentials/sa_<vault_id>.json` → chmod 0600."

즉 v2 §3.6 의 진단이 **반대 방향으로 잘못 정정**. CR1-CRIT-1 의 권장 ("v2 §3.6 를 정확히 정정") 의 의도는 ADR-0029 §Decision **본문 변경** (현 `~/wikihub-instance/.credentials/`  → 신 `~/.credentials/wikihub/`) 이었으나 v2 는 ADR-0029 본문이 이미 외부 path 라고 잘못 진단. §7.1 ADR-0029 row 가 "Note 추가" 로 표시된 것도 같은 misreading. → 신규 결함 CR3-NEW-CRIT-1.

### CR1-CRIT-2 (ADR-0023 safety guard §Decision 갱신 격상) → **CLOSED**

v2 §5.2.5 가 "ADR-0023 §Decision 본문의 'safety guard 3개' 명세는 §Decision 본문 갱신 필요" 명시. §7.1 ADR-0023 row 도 "**§Decision 본문 변경** (Note 만 불충분 — CR1-CRIT-2)" 으로 격상. safety guard 4번째 (`$HOME/.local/share/wikihub/` 외 prefix detect) 도 §5.2.5 에 명세. §5.7 ADR list 의 ADR-0023 항목도 "safety guard 4번째 추가" 로 일관. 단 §5.7 ADR-0023 항목 표현이 "Note" 단어 잔존 — LOW.

### CR1-CRIT-3 (WIKIHUB_HOME silent bug detect) → **CLOSED**

v2 §5.1.1 의 `_step0_env_semantic_check` 가 `WIKIHUB_HOME_EXPLICIT` 또는 `WIKIHUB_HOME` env set + path 의 `.git` + origin `im-dongseon/wikihub` detect → fail-fast 명시. 메시지도 운영자 mental model 자연. §5.2.1 의 Step 0a 진입 순서 정본화로 detect 분기 명세 완결.

### CR1-CRIT-4 (migration idempotency phase marker) → **CLOSED**

v2 §5.3.1 의 phase marker state machine + §5.3.4 의 명시 매핑. phase values 9개 (`pre-stop → DONE`) 명세. 각 step 의 `get_phase()` guard + `set_phase()` 진행. `$PHASE_FILE` 위치 정본화 (`~/.local/state/wikihub/migrate_layout.phase`). flock advisory 도 추가.

### CR1-CRIT-5 (systemd in-flight grace race) → **CLOSED**

v2 §5.3.7 + §5.3.1 의 `_systemd_stop_legacy` 가 timer first → service grace (`timeout 900`, 15min) → mount@ last → reset-failed 순서 명시. ADR-0030 §sub-1 stop sequence 정본 따름. mv (`_mv_src`) 는 stop 완료 후 phase `unmounted` 진입한 다음만 실행 — race 차단.

## R2-CR1 HIGH closure

### CR1-HIGH-1 (ADR-0030 4 sub-decision 정합) → **PARTIAL**

v2 §7.1 ADR-0030 row 가 "4 sub-decision 모두 cwd 변경만 정합 — sub-1 stop sequence · sub-2 unstaged guard · sub-3 rollback trap · sub-4 ref resolution chain 의 모든 git 명령이 `$WIKIHUB_SRC` 에서 실행" 으로 1줄 매트릭스. CR1 권장의 "각 sub 1줄씩" 충족. 단 CR1 권장의 "sub-2 의 mental model 자연화 효과를 §1.2 에 보강" 부분은 §1.2 본문 미반영 — PARTIAL.

### CR1-HIGH-2 (ADR-0031 schema version E) → **CLOSED**

v2 §7.1 ADR-0031 row 가 "schema version 본 변경에 따라 v1 → v1 (key 변경 없음, 값 의미 변경 — schema version bump 불요 §Decision E 정합)" 명시. ADR-0031 §Decision E 의 v1→v2 transition 별도 ADR 요구는 본 feature 미해당 확정.

### CR1-HIGH-3 (Hermes marker comment migration) → **CLOSED**

v2 §5.3.1 의 `_patch_hermes_external_dirs_migration` 이 `hermes_config_migrate.py --remove-stale --add-new` 호출 명시. §7.1 ADR-0032 row 도 "sub-3 (marker comment + realpath 비교) 가 migration helper 에도 적용 — stale wikihub entry 자동 식별 + 제거" 명시. marker 부재 entry 는 보존 (warn-only). 단 helper 의 hermes_config_migrate.py 신규 파일이 §9.2 산출물 목록에 미포함 — MED.

### CR1-HIGH-4 (ADR-0034 신설 lock + 4 sub-decision) → **CLOSED**

v2 §7.1 ADR-0034 row 가 4 sub-decision 묶음 명시 (sub-1 data-first naming / sub-2 env (B) swap / sub-3 migration (C) helper / sub-4 backup mv-only state machine). §변경이력 v2 entry 도 "ADR-0034 신설 lock" 명시. §8.3 의 "(나) ADR-0034 신설" 권장 lock 도 §7.1 매트릭스에 반영.

### CR1-HIGH-5 (.venv_path sidecar 위치 영향) → **PARTIAL**

v2 §5.2.6 (line 402~404) 가 "sidecar 는 `$WIKIHUB_SRC/.venv_path` 로 이동 (run-time 생성)" 명시. render_systemd_units.py 의 read path 갱신 의무는 §5.4.1 path helper 함수에 `_wikihub_src()` 신규로 묵시 보강. 단 CR1 권장의 "`--force-fresh` 의 wipe → systemd stop sequence 선행이라 race 없음 (명시)" 부분 미반영 — PARTIAL.

### CR1-HIGH-6 (`_system/VERSION` v0.2.0 detect 분기) → **CLOSED**

v2 §5.2.1 의 entry order Step 0a (env check) → Step 0b (legacy detect: `$HOME/wikihub/.git + $HOME/wikihub-instance + origin`) → Step 0c (curl-pipe self-replace) 순서 정본화. CR1 권장의 3단계 분기 순서 (legacy → v0.2.0 update → fresh) 가 Step 0b 의 legacy 우선 검사 + Step 0c 의 self-replace 분기로 표현. 단 Step 0c 안의 v0.2.0 update vs fresh 분기 명세는 §5.2.x 분산 — 명시 통합 없음 — 운영자 trace 가능.

### CR1-HIGH-7 (migration backup cp -r → mv) → **CLOSED**

v2 §5.3.5 명시 — "ENOSPC 회피 위해 `cp -r` 모델 폐기. mv-only 사용. cross-fs 시 mv 가 자동 cp+rm. 운영자 명시 backup 원할 시 helper 호출 전 직접 `cp -r` 권고 — README 안내." CR1 권장 (γ) hardlink 옵션은 미채택했으나 (β) mv-only + rollback trap 으로 통일.

### CR1-HIGH-8 (`WIKIHUB_SRC` 명명 검토) → **PARTIAL**

v2 §5.1.2 명시 — "대안: `WIKIHUB_REPO`. 단 본 feature 채택 = `WIKIHUB_SRC`" + 3개 사유. CR1 권장의 3-option 비교 표는 부재하나 lock decision + 사유 명시. ADR-0034 sub-2 의 정본화. 단 CR1 의 추천 (`WIKIHUB_REPO`) 반영 안 함 — 의도적 기각.

## R2-CR1 MED closure (요약)

| ID | closure |
|---|---|
| MED-1 v0.1.x base 가정 명시 | **PARTIAL** — §1.3 미수정 (v1 그대로) |
| MED-2 multi-instance SyslogIdentifier | **PARTIAL** — §4.4 보강 없이 §10 Out of Scope 만 명시 |
| MED-3 V3 PASS 기준 측정 | **CLOSED** — §9.3 V3 row 7단계 PASS 기준 명시 |
| MED-4 V4 wipe scope 측정 | **NOT_CLOSED** — §9.3 V4 의 sha256 snapshot 측정 부재 |
| MED-5 V5 fail-fast 안내 정확도 | **PARTIAL** — §5.3.3 메시지 명시. CR1 권장의 stderr/exit code 표 형식은 부재 |
| MED-6 INSTALLED_VERSIONS mixed state | **NOT_CLOSED** — §5.2.7 fallback 로직 부재 (단순 위치만 명시) |
| MED-7 substitution key 매트릭스 | **CLOSED** — §5.4.2 의 12 row 매트릭스 명시 |
| MED-8 schema migration guide URL | **PARTIAL** — §5.8 의 "migration 안내" 만 (anchor 미명시) |

## R2-CR1 LOW closure (요약)

LOW-1 §5.7 vs §7.1 일관성: **PARTIAL** — §5.7 의 ADR-0023 항목이 여전히 "Note" 단어. LOW-2~5 는 minor — closure 불요.

---

## v2 도입 신규 결함

### CR3-NEW-CRIT-1 — §3.6 의 ADR-0029 진단이 실제 ADR-0029 §Decision 본문과 모순

- **위치**: v2 §3.6 (line 131~135) + §7.1 ADR-0029 row (line 838) + §변경이력 v2 entry (line 971)
- **결함**: v2 §3.6 가 "ADR-0029 §Decision 본문 (`docs/adr/0029-service-account-auth.md`) 의 default path 는 `~/.credentials/wikihub/sa_*.json` (repo 외부)" 라고 명시. 그러나 실제 `docs/adr/0029-service-account-auth.md` §Decision line 52 는:
  > "배포: scp → OCI `~/wikihub-instance/.credentials/sa_<vault_id>.json` → chmod 0600. wikihub.yaml 의 `credentials_path` 가 본 파일 지정."

  즉 ADR-0029 §Decision 본문의 정본 path 는 `~/wikihub-instance/.credentials/` (instance 내부) — v2 §3.6 의 주장과 정반대. v2 가 "wikihub.yaml.example 의 default 가 v0.1.0 의 잘못된 default 정정 기회" 라고 적은 것도 ADR-0029 와의 정합 검증 실패. §7.1 ADR-0029 row 의 "Note 추가" 처리도 본 misreading 기반.
- **권장 해결책**: v3 에서 두 선택지 중 명시 lock:
  - **(α) v0.2.0 후에도 `~/wikihub-instance/.credentials/` 정본 보존** — 그러나 instance dir 폐기되므로 path 자체 무효. 본 옵션 불가.
  - **(β) `~/.credentials/wikihub/` 외부 보존 채택** — ADR-0029 §Decision line 52 의 **본문 갱신** 의무. v3 §3.6 정정 = "ADR-0029 §Decision line 52 가 instance 내부 path. 본 feature 가 외부 path 로 §Decision 본문 갱신." §7.1 ADR-0029 row 도 "Note 추가" → "**§Decision 본문 변경**" 격상.
  - **(γ) `~/wikihub/.credentials/`** (data-first 자연 매핑) — ADR-0029 §Decision 본문 갱신 + ADR-0034 sub-3 신설 가능. 운영자 자산 시각화 일관.
  
  현 v2 의 wikihub.yaml.example 의 `credentials_path: ~/.credentials/wikihub/sa_gdrive.json` (§5.5 line 766) 도 (β) 전제 — (β) lock 시 정합. v3 §변경이력 v2 entry 의 "CR1-CRIT-1 closure" 주장도 정정 필요 (NOT_CLOSED 인정).

### CR3-NEW-HIGH-1 — Step 0a/0b/0c entry order 의 fail-fast 후 helper 호출 정합

- **위치**: v2 §5.2.1 (line 312~333) + §5.3.2 의 `_step0_legacy_detect` (line 617~635)
- **결함**: Step 0a (env check) 가 `WIKIHUB_INSTANCE_ROOT` set 시 exit 1. 그러나 v0.1.x 운영자가 shell rc 에 `export WIKIHUB_INSTANCE_ROOT=...` 보유 + legacy layout 사용 중 → install.sh 호출 시 Step 0a 에서 exit 1 → 운영자가 migration 진입 못함. 운영자는 unset 후 재호출 → Step 0b 진입 → helper 호출. 그러나 helper 자체가 `LEGACY_INSTANCE` env 도 받지만 `WIKIHUB_INSTANCE_ROOT` 의 fallback 으로 명시되지 않음. 결과: 운영자 mental model 의 silent gap — env 폐기 안내 후 다음 단계 안내 부재.
- **권장 해결책**: v3 §5.3.3 의 fail-fast 메시지에 "legacy layout 사용 중이면 우선 본 env unset 후 `bash scripts/migrate_layout.sh` 호출 → helper 가 layout 자동 detect" 명시. Step 0a 의 exit 메시지가 Step 0b 의 helper 호출 path 를 명시.

### CR3-NEW-HIGH-2 — §5.3.1 phase 의 잘못된 state 진입 시 동작 부재

- **위치**: v2 §5.3.1 의 `get_phase()` + `_systemd_stop_legacy` (line 478~491)
- **결함**: phase value 9개 (`pre-stop / stopped / unmounted / mv-src-done / mv-home-done / hermes-patched / render-done / start-done / DONE`) 명세. 그러나 운영자가 `$PHASE_FILE` 을 직접 편집 (e.g. `echo "DONE" > $PHASE_FILE` 후 helper 재호출) 또는 손상된 marker (e.g. `unmount-done` 같은 typo) 의 경우 동작 미명시. 각 helper step 의 `[[ "$phase" != "<expected>" ]] && return 0` 패턴은 expected 외 모든 값 skip → 잘못된 phase 에서 helper 가 silent no-op + main 의 `set_phase "DONE"` 직진 → migration 실제 미수행. CR1-CRIT-4 의 state machine closure 의 sub-gap.
- **권장 해결책**: v3 §5.3.1 에 명시 — (a) phase value validation (whitelist match 외 fail-fast), (b) main 의 `set_phase "DONE"` 직전에 actual progress invariant check (예: `[[ -d "$NEW_SRC/.git" ]] && [[ -f "$NEW_HOME/wikihub.yaml" ]]`) — 두 invariant 부족 시 fail-fast.

### CR3-NEW-MED-1 — §5.3.5 mv-only 의 cross-filesystem 사후 ENOSPC

- **위치**: v2 §5.3.5 (line 663~668)
- **결함**: "cross-fs 시 mv 가 자동 cp+rm" 명시. 그러나 cross-fs 의 cp 중간에 destination FS 의 ENOSPC 발생 가능 (예: `$LEGACY_INSTANCE` = NAS 마운트 (multi-TB), `$NEW_HOME` = local home (50GB free)). 이 경우 cp 진행 중 ENOSPC → mv fail → partial copy 잔존 → rollback trap 의 reverse mv 도 어려움 (src 는 일부 mv 후 상태). 단순 mv 폐기 의도 (ENOSPC 회피) 자체가 cross-fs 시 무효.
- **권장 해결책**: v3 §5.3.5 에 cross-fs detect + disk free check 추가 — `_mv_home` 전에 `df` 로 destination filesystem free 와 source size 비교, 부족 시 fail-fast + 안내. cross-fs 운영자에게 별도 manual migration path 안내 (예: rsync 후 mv).

### CR3-NEW-MED-2 — `instance_root` deprecated alias vs yaml.instance.root 의미 분리 미명시

- **위치**: v2 §5.4.4 (line 740~753) + §5.5 (line 758~767)
- **결함**: §5.4.4 의 `_SafeDict.__missing__` 가 `instance_root` substitution 진입 시 `wikihub_home` 으로 fallback. 그러나 §5.5 wikihub.yaml.example 의 `instance.root: ~/wikihub` 키는 보존 (ADR-0031 §Decision B catalog 정합). 두 의미 분리:
  - yaml 의 `instance.root` key = derive source (값 = 운영 자산 dir path)
  - systemd unit template 의 `{instance_root}` placeholder = render-time substitution (deprecated)
  운영자가 `{instance_root}` 와 `instance.root` 의 동일성을 가정할 수 있으나 본 feature 후 둘 다 같은 값 (`$WIKIHUB_HOME`) 으로 우연 일치. v0.3.x 에서 `{instance_root}` 제거 시 yaml `instance.root` 와 시각적 inconsistency 발생 가능.
- **권장 해결책**: v3 §5.4.4 에 "yaml.instance.root key (ADR-0031 catalog 정본 — 보존) vs systemd template `{instance_root}` placeholder (deprecated alias, v0.3.x 제거 예정) 의 의미 분리 명시" 추가. README 의 migration anchor 에도 명시.

### CR3-NEW-MED-3 — ADR-0034 4 sub-decision 묶음이 ADR 컨벤션과 정합한지 명시 부재

- **위치**: v2 §7.1 ADR-0034 row + §변경이력 v2 entry
- **결함**: ADR-0034 가 4 sub-decision 묶음. CLAUDE.md §3 의 "결정 = 1 ADR" 원칙. ADR-0030 의 4 sub-decision 묶음 패턴 reuse 가 묵시적이나 ADR-0034 본문에 "동일 architectural concern 의 sub-decision 4건 묶음 (ADR-0030 패턴 reuse)" 명시 부재. ADR 신설 PR review 시 "sub-decision 분리해야 하지 않나?" 검토 surface.
- **권장 해결책**: v3 §7.1 ADR-0034 row 본문에 1줄 추가 — "ADR-0030 의 4 sub-decision 묶음 패턴 reuse. 단일 architectural decision (XDG layout refactor) 의 cross-cutting sub-decision 4건 묶음. CLAUDE.md §3 의 '결정 = 1 ADR' 원칙은 'architectural concern = 1 ADR' 로 해석."

### CR3-NEW-LOW-1 — §변경이력 v2 entry 의 "CRIT 10건 해결" 표현 vs 실제 closure

- **위치**: v2 §변경이력 v2 entry (line 970)
- **결함**: "**CRIT 10건 해결**" 표현. 실제로는 CR1-CRIT 5건 + CR2-CRIT 5건 = 10건이나 본 review 가 CR1-CRIT-1 NOT_CLOSED 확정 → 9건 closure. 본 표현 정확도 누락. (CR2 closure 는 CR3-2 별도 review 에서 검증 — 본 review 범위 밖)
- **권장 해결책**: v3 §변경이력 v2 entry 정정 — "CRIT 9건 closure (CR1-CRIT-1 은 ADR-0029 §Decision 본문 mismatch 로 v3 에서 재처리)". v3 entry 추가 시 CR1-CRIT-1 본 closure 명시.

---

## 추가 관찰

### 관찰 1 — v1 unchanged 섹션의 v2 정합

§3 (현행 진단) 의 §3.1·3.2·3.3·3.4·3.5·3.7·3.8 unchanged. §3.6 만 v2 정정. §4 (옵션 분석) 의 권장 lock 도 v2 유지. §6 (개정 전/후 비교) 의 3 표 모두 v2 §5 정합. §10 (Out of Scope) v2 미수정 — 정합.

### 관찰 2 — §6 의 3 표 정합

§6.1 env 변수 표 — v2 §5.1 정합. §6.2 디렉토리 위치 표 — v2 §5.2 정합 (단 `.credentials/sa_*.json` row 가 "변경 없음" 으로 명시 → CR3-NEW-CRIT-1 의 ADR-0029 정정 후 본 row 갱신 필요). §6.3 호출 예 표 — Step 0a/0b/0c entry order 와 정합.

### 관찰 3 — §8 잔존 미결 (v2 표 갱신)

v2 §8.1 의 #1~#5 lock 표 — 5건 모두 권장 lock 정합. §8.2 VM 실측 의존 (M-1·M-2·M-3) 명시. §8.3 의 ADR-0034 신설 vs 7건 Note 옵션 표 — v2 가 (나) 신설 lock 했으나 §8.3 표 자체는 v1 표 그대로 잔존 — minor inconsistency.

### 관찰 4 — ADR-0011 영향 부재

ADR-0011 (Superseded by ADR-0033) — v2 §7.1 표 미포함. layout 변경이 ADR-0011 (skill namespace prefix) 영향 0 — 정합. 명시 부재라도 누락 아님.

### 관찰 5 — §5.7 ADR Notes 목록의 §7.1 매트릭스와 표현 일관성

§5.7 ADR list 8건 (ADR-0010·0020·0023·0029·0030·0031·0032 + ADR-0034 신설). 모든 ADR 가 "Note" 단어 사용. §7.1 매트릭스는 §Decision 갱신 6건 / Note 추가 1건 / 신설 1건 — 두 표 미일관 (LOW-1 의 잔존). v3 에서 §5.7 ADR list 의 표현 정합 갱신 권장.

---

## 종합 — v3 에서 우선 처리

1. **CR3-NEW-CRIT-1**: ADR-0029 §Decision 본문 vs v2 §3.6 진단 mismatch 정정. §3.6 + §7.1 ADR-0029 row + §변경이력 v2 entry 의 CR1-CRIT-1 closure 표현 정정. ADR-0029 §Decision line 52 본문 갱신 의무 명시.
2. **CR3-NEW-HIGH-1·2**: Step 0a fail-fast 메시지에 helper 호출 path 명시 + phase value validation + main 의 invariant check.
3. **CR1-HIGH-1 PARTIAL closure**: §1.2 에 sub-2 unstaged guard 자연화 효과 1줄 추가.
4. **CR1-HIGH-5 PARTIAL closure**: §5.2.6 에 `--force-fresh` race 명시 1줄.
5. **CR1-MED-4·6 NOT_CLOSED**: V4 sha256 snapshot 측정 + §5.2.7 INSTALLED_VERSIONS fallback 추가 검토 (v3 또는 Step 3 backport).
6. **CR3-NEW-MED-3**: ADR-0034 4 sub-decision 묶음의 ADR 컨벤션 정합 명시.

CR3-NEW-CRIT-1 의 해결이 본 R3 의 핵심. 이 1건만 정정 후 Step 3 진입 가능.
