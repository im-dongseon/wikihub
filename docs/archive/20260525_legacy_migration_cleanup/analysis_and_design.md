# Analysis & Design — legacy_migration_cleanup (v0.1.8)

approved: 2026-05-25

> 본 문서는 plan.md 의 결정 (Q1=a / Q2=a / Q3=a + OCI 검증 deferred) 을 전제로 작성. 신규 ADR 없음 — 기존 ADR-0034/0036/0038 의 §"후속 영향" 추가/정리만 (Step 2 design review 5건 흡수).

---

## 분석

### 1. 배경 및 목적

v0.1.0~v0.1.6 era 의 1회성 migration 코드가 install.sh 에 누적된 상태. 운영자 base 가 v0.1.7 정착 후 본 코드들은 **영구 no-op** — drift 0 detect 후 early return 만 발화. 코드 자체의 가독성·유지보수성 부담은 그대로.

v0.1.7 follow-up (`graphify_profile_namespace`) 의 backlog #M~#Q 에 정합 cleanup 일괄 정리 정본화. 본 feature 가 그 정리를 실행 — install.sh ~170줄 + `scripts/migrate_layout.sh` 220줄 = 약 390줄 감소.

### 2. 현행 진단 (결함 목록 및 근거)

| ID | 결함 | 위치 | 도입 ADR | 운영자 정착 시점 | 영구 no-op 근거 |
|---|---|---|---|---|---|
| **D-M** | `_migrate_graphify_env` 함수 — v0.1.7 follow-up 의 1회성 env 마이그레이션 | install.sh:994-1107 (함수 본체) + 1986 (호출) | ADR-0038 | v0.1.7 follow-up `install.sh --update` 1회 실행 후 | 운영자 env 파일에 `WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_*` 3 키 + legacy 0건 → drift detect 첫 line 의 early return |
| **D-N** | `_migrate_agent_schema` Group A — `wh:`→`wh-` + oneshot legacy + `--yolo` 삽입 | install.sh detect: 807-816, migration: 917-936, info case: 877-879 | ADR-0033 (skill_prefix) + ADR-0032 (oneshot) + ADR-0032 §Note (yolo) | v0.1.1~v0.1.4 era install 운영자 모두 정착 | yaml 의 `agent.skill_prefix` = `"wh-"` + `oneshot_args` 에 `{skill}` + `--yolo` 동시 존재 → 3 flag 모두 부재 |
| **D-O** | `_migrate_agent_schema` Group C — `vaults[].options` legacy field cleanup | install.sh detect: 854-862, migration: 970-981, info case: 892 (`C_*` glob), `_legacy_vault_opts` tuple 2 위치 | ADR-0035 (gws SA + cursor 폐기) | v0.1.5+ install 운영자 정착 | yaml 의 `vaults[].options` 에 `bootstrap_allowed` / `credentials_path` / `root_folder_id` / `cursor_path` 4 키 모두 부재 → flag 0 emit |
| **D-P** | `WIKIHUB_HOME` silent bug detect — pre-v0.1.0 layout 운영자 fail-fast | install.sh:98-109 (`if [[ -d "$WIKIHUB_HOME/.git" ]] ... remote.origin.url ... im-dongseon/wikihub`) | ADR-0034 (data-first layout transition) | pre-v0.1.0 (release 전 시점, base 0건 가정) | ADR-0034 §sub-3 가 "release 전 마지막 architectural fix" 명시 — v0.1.0 이후 install 운영자는 `$HOME/wikihub` 가 운영 자산 dir, `.git` 부재. 본 detect 가 발화하면 운영자가 의도적으로 legacy 흉내 |
| **D-Q** | `scripts/migrate_layout.sh` — pre-v0.1.0 → v0.1.0 transition helper (9-phase state machine) | `scripts/migrate_layout.sh` 220줄 전체 | ADR-0034 §sub-3 | 동일 (pre-v0.1.0) | install.sh:104 의 안내 reference 외에 호출 site 0. 운영자가 직접 실행 가능하나 v0.1.0 이후 운영자는 발화 시나리오 자체 부재 |

### 3. 보존 명확화 (cleanup 대상 아님)

본 feature 가 보존하는 영구 가치 코드:

| 항목 | 위치 | 보존 사유 |
|---|---|---|
| `_migrate_agent_schema` 함수 자체 (Group B 만 유지) | install.sh:728- (함수 정의), 그 안의 Group B detect + migration | yaml.example schema 와의 single source of truth 보장. v0.1.5+ 신설 field (`timeout_sec` / `models` / `pending_alert_age_sec` / `lint_contradiction_check` / `graphify_enabled` / `graphify_backend` / `graphify_min/max_version` / `graphify_profile`) 부재 시 자동 추가. 향후 새 field 도입 시 본 dict 확장만으로 영구 보강 |
| `_migrate_agent_schema` A4 W_graphify_profile_invalid warn | detect: 838-844, info case: 880 | 운영자 yaml 편집 mistake (정규식 fail: 대문자/특수문자/공백) 의 install-time fail-fast surface. ADR-0031 §Note value-mutation 정합 (warn 만, 자동 수정 안 함) |
| `_step5_instance_dirs` env template (default `WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_*` 3 키 + Telegram placeholder + chmod 600) | install.sh:692-714 | fresh install 시 영구 필요 — `_migrate_graphify_env` 삭제 후에도 운영자가 처음 install.sh 실행 시 env 파일 자동 생성 |
| `_migrate_agent_schema` Group B per-vault (`vaults[].sync_interval_sec` 부재 시 3600 추가) | detect: 825-829, migration: 964-968, info case: 882 | (v0.1.7 follow-up 시 추가된 자동 보강 — 영구 schema 보강 패턴) |

---

## 설계

### 1. 개정 범위 (8 파일)

| 파일 | 변경 성격 | 줄 수 |
|---|---|---|
| `install.sh` | 5 항목 (#M·#N·#O·#P 코드 + #Q reference 정리) 삭제 | -170 줄 |
| `scripts/migrate_layout.sh` | 파일 전체 삭제 | -220 줄 |
| `docs/adr/0034-data-first-layout.md` | §"후속 영향" 1줄 추가 | +1 줄 |
| `docs/adr/0036-graphify-cli-integration.md` | §Note 2026-05-24 의 §Rollback procedure + §배포 Gap window 분석 두 절 전체 삭제 — 둘 다 `_migrate_graphify_env` referent (cleanup 후 dead text). §Cross-references 갱신 끝에 cleanup 완료 1줄 추가 | -32 줄 (line 302-333 두 절) + ~1 줄 cleanup 명시 |
| `docs/adr/0038-graphify-env-namespace-isolation.md` | §"후속 영향" 3 변경: cleanup bullet 1줄 추가 + line 74 `Rollback procedure` bullet 삭제 (dead link — ADR-0036 의 참조 대상 절 cleanup 으로 부재) + line 73 의 stale parenthetical (`_migrate_graphify_env 가 값 보존`) 갱신 | +1 / -1 / ~1 줄 |
| `features/backlog.md` | "graphify_profile_namespace 산출 §v0.1.8 cleanup 묶음" 의 #M~#Q 5 row 에 기존 컨벤션 정합 closed marker — strikethrough on 앞 3 컬럼 (~~#M~~ / ~~영역~~ / ~~항목~~) + 결정 컬럼에 `✅ **closed** by \`legacy_migration_cleanup\` (2026-05-25)` prefix | ~10 줄 변경 (5 row × 2 컬럼) |
| `_system/VERSION` | `0.1.7` → `0.1.8` | 1줄 |
| `README.md` | badge `v0.1.7` → `v0.1.8`, 개발 상태 1줄 갱신 (v0.1.8 cleanup 누적 명시) | ~2 줄 |
| `features/HISTORY.md` | `[2026-05-25] legacy_migration_cleanup (v0.1.8)` entry append | +20 줄 |

**총 영향**: 코드 -390 줄, 문서/메타 +30 줄. 순감 ~360 줄.

### 2. 각 항목 (#M~#Q) 의 삭제 boundary 명세

#### #M — `_migrate_graphify_env` 전체 삭제

**install.sh 의 삭제 대상 line ranges**:

1. **함수 본체 + 머리 코멘트** (line 993-1107, 약 115줄):
   - Line 993 빈 줄 (preserve 1 line spacing 정합)
   - Line 994-1000: 머리 코멘트 ("1회성 env file 마이그레이션 — ADR-0038 ... v0.1.8 cleanup 예정 marker ...")
   - Line 1001-1107: `_migrate_graphify_env() { ... }` 함수 본체

2. **main flow 호출** (line 1986):
   ```bash
   _migrate_graphify_env   # ADR-0038 (v0.1.7 follow-up): 기존 env 파일의 legacy 키 마이그레이션 (fresh install 직후엔 no-op)
   ```
   삭제 — `_step5_instance_dirs` 직후 호출 1줄.

**docs/adr/0036-graphify-cli-integration.md 의 §Note 2026-05-24 정리**:
- §Rollback procedure (line 302-324) — 전체 절 삭제. backup file (`env.wikihub-bak.<utc>` / `wikihub.yaml.wikihub-bak.<utc>`) 의 생성 주체 자체가 `_migrate_graphify_env` 였으므로 cleanup 후 backup 자체가 발생 안 함 → dead text.
- §배포 Gap window 분석 (line 326-333) — 전체 절 삭제. "install.sh 가 running service 중 env 파일 rewrite" 시나리오 자체가 `_migrate_graphify_env` 동작 referent → cleanup 후 referent 부재 → dead text.
- 남은 §Note 구조: §결정 A~F (실 code 결정 정본, 유지) + §Cross-references 갱신 (끝에 v0.1.8 cleanup 1줄 추가) + §본 §Note 의 분석 정본 (feature archive ref, 유지)

#### #N — `_migrate_agent_schema` Group A 삭제

**install.sh 의 삭제 대상**:

1. **detect block** (line 807-816 안의 Group A 부분, 약 10줄):
   ```python
   # Group A — ADR-0033 / ADR-0032 기존 drift
   if agent.get("skill_prefix") == "wh:":
       flags.append("A_skill_prefix")
   oneshot = list(agent.get("oneshot_args") or [])
   has_placeholder = any("{skill}" in str(a) for a in oneshot)
   has_yolo = any(str(a) == "--yolo" for a in oneshot)
   if not has_placeholder:
       flags.append("A_oneshot_legacy")
   elif not has_yolo:
       flags.append("A_yolo_missing")
   ```

2. **migration block** (line 917-936 의 Group A 부분, 약 20줄):
   ```python
   # Group A — ADR-0033 / ADR-0032
   agent = data.setdefault("agent", {})
   if agent.get("skill_prefix") == "wh:":
       agent["skill_prefix"] = "wh-"
   oneshot = list(agent.get("oneshot_args") or [])
   has_placeholder = any("{skill}" in str(a) for a in oneshot)
   has_yolo = any(str(a) == "--yolo" for a in oneshot)
   if not has_placeholder:
       agent["oneshot_args"] = ["chat", "--skills", "{skill}", "--quiet", "--yolo", "--query"]
   elif not has_yolo:
       new_args = []
       inserted = False
       for arg in oneshot:
           if str(arg) == "--query" and not inserted:
               new_args.append("--yolo")
               inserted = True
           new_args.append(arg)
       if not inserted:
           new_args.append("--yolo")
       agent["oneshot_args"] = new_args
   ```

3. **info log case** (line 877-879, 3 줄):
   ```bash
   A_skill_prefix)        info "  - [ADR-0033] agent.skill_prefix \"wh:\" → \"wh-\"" ;;
   A_oneshot_legacy)      info "  - [ADR-0032] agent.oneshot_args legacy → F5 schema (`{skill}` + --yolo)" ;;
   A_yolo_missing)        info "  - [ADR-0032 §Note] agent.oneshot_args 의 --yolo 누락 → in-place 삽입" ;;
   ```

4. **함수 머리 코멘트 marker** (line 781):
   ```
   #   #N: Group A 삭제 (A_skill_prefix / A_oneshot_legacy / A_yolo_missing) — v0.1.0~v0.1.3 era 1회성
   ```
   → "v0.1.8 cleanup 예정" marker 자체 삭제 (cleanup 이 완료된 상태). 함수 머리 코멘트 전체 단순화.

#### #O — `_migrate_agent_schema` Group C 삭제

**install.sh 의 삭제 대상**:

1. **detect block** (line 854-862, 약 9줄):
   ```python
   # Group C — ADR-0035 폐기 field 잔존 (자동 삭제)
   _legacy_vault_opts = ("bootstrap_allowed", "credentials_path", "root_folder_id", "cursor_path")
   for idx, v in enumerate(vaults):
       if not isinstance(v, dict):
           continue
       opts = v.get("options") or {}
       for lo in _legacy_vault_opts:
           if lo in opts:
               flags.append(f"C_vaults[{idx}].options.{lo}")
   ```

2. **migration block** (line 970-981, 약 12줄):
   ```python
   # Group C — ADR-0035 폐기 field cleanup
   _legacy_vault_opts = ("bootstrap_allowed", "credentials_path", "root_folder_id", "cursor_path")
   for v in vaults:
       if not isinstance(v, dict):
           continue
       opts = v.get("options")
       if not isinstance(opts, dict):
           continue
       for lo in _legacy_vault_opts:
           if lo in opts:
               del opts[lo]
   ```

3. **info log case** (line 892, 1 줄):
   ```bash
   C_*)                        info "  - [ADR-0035] 폐기 field cleanup: ${f#C_}" ;;
   ```

4. **함수 머리 코멘트 marker** (line 782):
   ```
   #   #O: Group C 삭제 (vaults[].options.{bootstrap_allowed,credentials_path,root_folder_id,cursor_path}) — v0.1.4/v0.1.5 era 1회성
   ```
   → 동일하게 삭제.

#### #P — `WIKIHUB_HOME` silent bug detect 삭제

**install.sh:98-109 의 약 12줄 block 전체 삭제**:

```bash
# WIKIHUB_HOME silent bug detect: 명시 설정됐고 그 path 가 이전 의미 repo (= .git + im-dongseon/wikihub) 면 fail-fast
# !!! v0.1.8 cleanup 예정 #P (features/backlog.md "graphify_profile_namespace 산출 §v0.1.8 cleanup 묶음") — pre-v0.1.0 layout transition 1회성 detect, 운영자 base 정착 후 영구 무용 !!!
if [[ -d "$WIKIHUB_HOME/.git" ]] && \
   (cd "$WIKIHUB_HOME" 2>/dev/null && git config --get remote.origin.url 2>/dev/null | grep -q "im-dongseon/wikihub"); then
    err "WIKIHUB_HOME=$WIKIHUB_HOME 가 이전 semantic (repo dir) 로 사용됨."
    err "ADR-0034 후 WIKIHUB_HOME 의 의미 = 운영 자산 dir (data-first)."
    err "  마이그레이션 helper: ~/.local/share/wikihub/src/scripts/migrate_layout.sh (legacy detect 자동 진입 권장)"
    err "    export WIKIHUB_HOME=<운영 자산 dir>"
    err "    export WIKIHUB_SRC=$WIKIHUB_HOME"
    exit 1
fi
```

**보존**: install.sh:84-96 의 `WIKIHUB_INSTANCE_ROOT` env detect block (별개 — ADR-0034 의 env 변수명 폐기 안내, 영구 가치).

#### #Q — `scripts/migrate_layout.sh` 파일 전체 삭제

`git rm scripts/migrate_layout.sh` — 220줄.

**참조 site 검증** (삭제 안전성):
- install.sh:104 — 삭제 대상 #P block 안에 있음 (#P 삭제로 동반 정리)
- 다른 파일에서의 `migrate_layout` reference 검색 → ADR-0034 + ADR-0032 + ADR-0030 의 본문 history 기록만 (cross-link history 보존)
- 운영 server 의 systemd unit / hermes config / 다른 script 에서 호출 0

### 3. ADR cross-link 갱신 (3건)

#### ADR-0034 §"후속 영향"

말미에 1줄 추가:

```markdown
- **v0.1.8 cleanup** (2026-05-25, feature `legacy_migration_cleanup`) — `scripts/migrate_layout.sh` + install.sh `WIKIHUB_HOME` silent bug detect block 삭제. pre-v0.1.0 → v0.1.0 transition 의 1회성 helper 가 운영자 base (v0.1.7+) 정착으로 영구 무용 — atomic refactor. ADR 본문 결정 자체는 history record 로 그대로 보존.
```

#### ADR-0036 §Note 2026-05-24 정리

§Rollback procedure + §배포 Gap window 분석 두 절 전체 삭제 (둘 다 `_migrate_graphify_env` referent, cleanup 후 dead text). §Cross-references 갱신 의 마지막 bullet 으로 1줄 추가:

```markdown
- ADR-0038 §"후속 영향" + 본 §Note — v0.1.8 cleanup (2026-05-25, feature `legacy_migration_cleanup`) 으로 `_migrate_graphify_env` 함수 삭제 + 관련 운영 가이드 절 (Rollback procedure / Gap window 분석) 삭제 완료. §결정 A~F (CLI v8 sync 본체) 는 실 code 정본이므로 그대로 유지.
```

#### ADR-0038 §"후속 영향" — 3 변경

**(1) 신규 bullet 추가** — 기존 "관련 ADR" 또는 "재검토 트리거" 끝에:

```markdown
- **v0.1.8 cleanup** (2026-05-25, feature `legacy_migration_cleanup`) — `_migrate_graphify_env` 함수 삭제 (운영자 base 정착 후 영구 no-op). §Decision 3 (auto-migration) 의 1회성 본체 polish 완료. §Decision 1·2·4·5 (namespace 격리 자체 + Hermes trust 가정) 은 영구 유효 — supersede 아님.
```

**(2) 기존 `Rollback procedure` bullet 삭제** — line 74:

```markdown
- **Rollback procedure**: ADR-0036 §Note 2026-05-24 끝 절 참조 (env + yaml backup 복원, systemctl restart 또는 timer fire 자동 적용).
```

이유: 참조 대상 (ADR-0036 §Note 2026-05-24 끝 절 = §Rollback procedure 절) 가 본 cleanup 으로 삭제됨 → dead link.

**(3) 기존 line 73 의 stale parenthetical 갱신**:

```markdown
# Before
- ADR-0037 — TELEGRAM_ALERT_* env 영역 영향 없음 (`_migrate_graphify_env` 가 값 보존)

# After
- ADR-0037 — TELEGRAM_ALERT_* env 영역 영향 없음 (v0.1.7 follow-up 의 마이그레이션 + v0.1.8 cleanup 후에도 영역 영향 없음)
```

이유: cleanup 후 `_migrate_graphify_env` 자체 부재 → parenthetical stale. 본 문장의 결론 (영역 영향 없음) 은 그대로 유효 — historical 정합 + 현재 정합 둘 다 만족하는 phrasing 으로 갱신.

### 4. release artifact 갱신

#### `_system/VERSION`

```
0.1.7 → 0.1.8
```

#### `README.md`

1. Title + Status badge + Version badge:
   - `# WikiHub v0.1.7` → `# WikiHub v0.1.8`
   - `Status-v0.1.7%20ready-green` → `Status-v0.1.8%20ready-green`
   - `Version-0.1.7-blue` → `Version-0.1.8-blue`

2. 개발 상태 1줄 갱신 — v0.1.8 cleanup 누적 명시:
   ```
   ... (v0.1.7 follow-up — ADR-0038 신설 ...) ... **legacy migration cleanup (v0.1.8 — install.sh 의 v0.1.0~v0.1.6 era 1회성 migration 코드 일괄 정리 + scripts/migrate_layout.sh 삭제, 약 390줄 감소)**
   ```

#### `features/backlog.md`

"graphify_profile_namespace 산출 §v0.1.8 cleanup 묶음" 의 표 5 row 를 기존 컨벤션 정합으로 갱신 — strikethrough on 앞 3 컬럼 + 결정 컬럼에 `✅ **closed** by ` prefix.

기존 컨벤션 reference (backlog.md F4 산출 의 closed 항목):
```
| ~~#12~~ | ~~agent integration~~ | ~~Hermes 의 ...~~ | ✅ **closed** by `hermes_adapter` (2026-05-18) — ... |
```

본 patch 적용 후:
```
| ~~#M~~ | ~~install.sh `_migrate_graphify_env`~~ | ~~함수 전체 (약 110줄 ...) ...~~ | v0.1.7 follow-up (2026-05-24) | (v0.1.7→v0.1.8 = 1 minor) | ✅ **closed** by `legacy_migration_cleanup` (2026-05-25) — namespace 정착 후 drift 0 영구 no-op. 보존: `_step5_instance_dirs` env template ... |
| ~~#N~~ | ~~install.sh `_migrate_agent_schema` **Group A**~~ | ~~drift detect ... 약 30줄~~ | ADR-0033 ... | 4 minor | ✅ **closed** by `legacy_migration_cleanup` (2026-05-25) — A_skill_prefix + A_oneshot_legacy + A_yolo_missing 모두 운영자 base v0.1.4+ 정착 |
| ~~#O~~ | ~~install.sh `_migrate_agent_schema` **Group C**~~ | ~~drift detect ... 약 20줄~~ | ADR-0035 ... | 2-3 minor | ✅ **closed** by `legacy_migration_cleanup` (2026-05-25) — vaults legacy options 4 키 자동 삭제 영구 no-op |
| ~~#P~~ | ~~install.sh `WIKIHUB_HOME` silent bug detect~~ | ~~line 98-109 (12줄) ...~~ | ADR-0034 ... | 7+ minor | ✅ **closed** by `legacy_migration_cleanup` (2026-05-25) — pre-v0.1.0 운영자 base 0건 정합 |
| ~~#Q~~ | ~~`scripts/migrate_layout.sh`~~ | ~~220줄 파일 전체~~ | ADR-0034 ... | 7+ minor | ✅ **closed** by `legacy_migration_cleanup` (2026-05-25) — pre-v0.1.0 → v0.1.0 transition helper 영구 무의미 |
```

§"v0.1.8 cleanup feature 의 시작 안내" 절 (backlog.md:160~) 도 historical reference 로 보존 — 시작 안내 의미는 historical 정합 그대로 의미 있음. 또는 §"✅ closed" marker 1줄 섹션 끝에 추가하여 운영자 read 시 명확화 (선택).

#### `features/HISTORY.md` 신규 항목

```markdown
## [2026-05-25] legacy_migration_cleanup (v0.1.8)

- **목적**: v0.1.0~v0.1.6 era 의 1회성 migration 코드 5건 (#M~#Q) 일괄 정리. 운영자 base 가 v0.1.7 정착 후 영구 no-op state 인 코드를 install.sh 에서 제거하여 가독성·유지보수성 개선.
- **로직**: install.sh 5 항목 + scripts/migrate_layout.sh 파일 전체 삭제. (a) `_migrate_graphify_env` 함수 + main flow 호출 (#M, ADR-0038 의 v0.1.7 follow-up 1회성), (b) `_migrate_agent_schema` Group A (`wh:`→`wh-` + oneshot legacy + `--yolo`, #N, ADR-0033/0032 의 v0.1.0~v0.1.3 era), (c) `_migrate_agent_schema` Group C (vaults legacy options 4 키 cleanup, #O, ADR-0035 의 v0.1.4/v0.1.5 era), (d) `WIKIHUB_HOME` silent bug detect block (#P, ADR-0034 의 pre-v0.1.0 transition), (e) `scripts/migrate_layout.sh` 220줄 파일 (#Q, ADR-0034 transition helper). 보존 — `_migrate_agent_schema` Group B (v0.1.5+ field auto-add) + A4 W_invalid warn + `_step5_instance_dirs` env template (영구 가치).
- **생성 ADR**: 없음 (refactoring, 신규 결정 0). 단 ADR-0034 §"후속 영향" 1줄 추가 + ADR-0036 §Note 의 §Rollback procedure / §배포 Gap window 분석 두 절 삭제 + §Cross-references 갱신 1줄 추가 + ADR-0038 §"후속 영향" 3 변경 (cleanup bullet 1줄 추가 + Rollback procedure bullet 삭제 + TELEGRAM parenthetical 갱신) — cleanup 완료 정합 명시 + stale cross-link 정리.
- **트레이드오프**:
  - pre-v0.1.7 yaml/env 운영자 base 가 등장하면 (예: 외부 backup 복원, 새 OCI 인스턴스에 옛 자료 이식) 본 cleanup 후의 install.sh 는 schema 자동 보강 불가 — 운영자 수동 yaml/env 갱신 필요. 단일 OCI server (메인테이너 자신) 환경 + v0.1.7 정착 가정으로 risk 무시 가능.
  - ADR 본문 (v0.1.0 era 결정 기록) 은 그대로 — history record 보존. cleanup 은 §"후속 영향" 에만 명시.
- **결론**: install.sh 약 170줄 감소 + scripts/migrate_layout.sh 220줄 파일 삭제 = 약 390줄 감소. VERSION 0.1.7 → 0.1.8. canary tag 검증 cycle (`docs/agent_dev_guide.md §Step 5 "배포 채널 — canary tag 활용"`) 의 첫 dogfooding — canary 부여 → OCI 검증 → 통과 시 latest promote. v0.1.8 release 의 첫 atomic feature.
- **참조**: features/archive/20260525_legacy_migration_cleanup/
```

---

## 개정 전/후 비교

### `install.sh`

| 위치 | Before | After |
|---|---|---|
| 84-109 (WIKIHUB_INSTANCE_ROOT detect + WIKIHUB_HOME silent bug) | 2 detect block (총 ~26줄) | WIKIHUB_INSTANCE_ROOT 만 유지 (~13줄) |
| 728-779 (`_migrate_agent_schema` 함수 머리 코멘트) | "v0.1.8 cleanup 예정" marker 2 줄 (#N + #O) | 단순 도입 코멘트 (~5줄) |
| 781-786 (Group A detect) | 10줄 | 삭제 |
| 808-816 (Group A flag append) | 10줄 | 삭제 |
| 854-862 (Group C detect) | 9줄 | 삭제 |
| 877-879 (Group A info case) | 3줄 | 삭제 |
| 892 (Group C info case) | 1줄 | 삭제 |
| 917-936 (Group A migration block) | 20줄 | 삭제 |
| 970-981 (Group C migration block + `_legacy_vault_opts` tuple) | 12줄 | 삭제 |
| 993-1107 (`_migrate_graphify_env` 함수 + 머리 코멘트) | 115줄 | 삭제 |
| 1986 (main flow `_migrate_graphify_env` 호출) | 1줄 | 삭제 |

**Net install.sh: ~170 줄 감소**

### `scripts/migrate_layout.sh`

| Before | After |
|---|---|
| 220줄 파일 | 부재 |

### `docs/adr/0034-data-first-layout.md`

§"후속 영향" 또는 §"재검토 트리거" 절에 1줄 추가 (위 §3 명세).

### `docs/adr/0036-graphify-cli-integration.md`

§Note 2026-05-24 의 §Rollback procedure + §배포 Gap window 분석 두 절 전체 삭제 (둘 다 `_migrate_graphify_env` referent — cleanup 후 dead text). §Cross-references 갱신 끝에 cleanup 완료 1줄 추가.

### `docs/adr/0038-graphify-env-namespace-isolation.md`

§"후속 영향" 또는 §"재검토 트리거" 절에 1줄 추가.

### `features/backlog.md`

#M~#Q 5 row 에 기존 컨벤션 정합 closed marker 적용 (위 §4 본문 참조) — strikethrough on 앞 3 컬럼 + 결정 컬럼에 `✅ **closed** by \`legacy_migration_cleanup\` (2026-05-25)` prefix. F4 산출의 closed 항목 (예: `~~#12~~ ... ✅ **closed** by `hermes_adapter`) 와 동일 형식.

### `_system/VERSION`

```
0.1.7
```
↓
```
0.1.8
```

### `README.md`

Title (1줄) + Status badge (1줄) + Version badge (1줄) + 개발 상태 (1줄) = 4 위치 갱신.

### `features/HISTORY.md`

새 entry append (~20줄, 위 §4 명세).

---

## 연계 룰/스킬 정합성 검토

| 대상 | 영향 | 결과 |
|---|---|---|
| **ADR-0031** (yaml-template-materialization) §Note | Group A·C 삭제 = 코드 단순화. 운영자 yaml 값 영향 0 (Group A·C 는 schema mutation 만, 값 보존). ADR-0031 §Note (schema vs value mutation) 정합 그대로 — 본 cleanup 은 schema mutation 코드 자체의 삭제 (= 미발화 코드 제거) | 정합 — §Note 갱신 불필요 |
| **ADR-0033** (skill-prefix-hyphen-lock) | 본 ADR 의 wh:→wh- transition migration 코드 (Group A_skill_prefix) 삭제. ADR 본문의 결정 자체는 영구 (skill_prefix = "wh-" lock). history record 보존 | 정합 — ADR 본문 변경 0 |
| **ADR-0032** (hermes-skill-registration) | oneshot_args F5 schema + `--yolo` 삽입 migration (Group A_oneshot_legacy + A_yolo_missing) 삭제. ADR 본문 + §Note 의 결정 자체는 영구 | 정합 — ADR 본문 변경 0 |
| **ADR-0034** (data-first-layout) | pre-v0.1.0 transition helper (`migrate_layout.sh`) 삭제. ADR 본문 §sub-3 "release 전 마지막 architectural fix" 정합 — release 후 transition 완료. §"후속 영향" 에 cleanup 1줄 추가 | 본 patch 가 ADR-0034 갱신 |
| **ADR-0035** (rclone-only-unified-oauth) | vaults legacy options 4 키 cleanup migration (Group C) 삭제. ADR-0035 의 본문 결정 (gws SA + cursor 폐기) 정합 그대로 — 4 키는 폐기 후 자취 없음 | 정합 — ADR 본문 변경 0 |
| **ADR-0036** (graphify-cli-integration) §Note 2026-05-24 | §Rollback procedure + §배포 Gap window 분석 두 절 전체 삭제 (둘 다 `_migrate_graphify_env` referent — cleanup 후 dead text). §결정 A~F (CLI v8 sync 본체) 는 실 code 정본이므로 보존 | 본 patch 가 §Note 정리 |
| **ADR-0038** (graphify-env-namespace-isolation) | `_migrate_graphify_env` (§Decision 3 auto-migration) 의 1회성 본체 삭제. §Decision 본문 (namespace 격리 자체) 은 영구 유효 | 본 patch 가 §"후속 영향" 3 변경 — cleanup bullet 1줄 추가 + 기존 `Rollback procedure` bullet 삭제 (dead link) + TELEGRAM parenthetical stale 갱신. supersede 아님 |
| `_system/commands/*.md` (lint, ingest, graphify, query, setup) | 호출 site 영향 0 — 본 cleanup 은 install.sh 내부 함수만 변경 | 정합 — 변경 없음 |
| `_system/systemd/*.template` | EnvironmentFile= path 변경 0. unit substitution key 변경 0 | 정합 — 변경 없음 |
| `scripts/render_systemd_units.py` | 본 cleanup 과 무관 | 정합 |
| `scripts/ops-alert.py` / `vault-fetch.py` / `pending_monitor.py` | 본 cleanup 과 무관 | 정합 |
| canary tag 운영 절차 (`docs/agent_dev_guide.md §Step 5`) | 본 feature 가 canary 첫 dogfooding — 절차 자체에 영향 없음 | 정합 — 본 feature 가 canary 검증 운영 trace 제공 |
| `features/20260524_graphify_profile_namespace/` archive | 본 cleanup 이 §v0.1.8 cleanup 묶음 의 정착 후속 작업 — cross-reference 정합 | 정합 |

---

## 미결 사항

**없음** — plan.md 의 Q1=(a) / Q2=(a) / Q3=(a) + OCI 검증 deferred 모두 확정.

---

## Definition of Done

### 코드 정합

- [ ] install.sh 의 5 항목 (#M·#N·#O·#P 코드 + #Q reference) 삭제 완료
- [ ] `bash -n install.sh` syntax pass
- [ ] `_migrate_agent_schema` 함수 안에 Group B + A4 만 남음 — `_op_defaults` dict + per-vault sync_interval_sec 보강 동작
- [ ] `scripts/migrate_layout.sh` 파일 부재
- [ ] `_step5_instance_dirs` env template 그대로 동작 — fresh install fixture 통과
- [ ] install.sh main flow 의 step 호출 순서 정합 (`_step5_instance_dirs` 직후의 `_migrate_graphify_env` 호출 1줄 삭제, 그 외 step 영향 0)

### ADR / 문서 정합

- [ ] ADR-0034 §"후속 영향" 1줄 추가
- [ ] ADR-0036 §Note 2026-05-24 의 §Rollback procedure + §배포 Gap window 분석 두 절 전체 삭제 + §Cross-references 갱신 끝에 cleanup 완료 1줄 추가
- [ ] ADR-0038 §"후속 영향" 3 변경 — cleanup bullet 1줄 추가 + 기존 `Rollback procedure` bullet 삭제 (dead link) + line 73 TELEGRAM_ALERT_* parenthetical 갱신 (stale `_migrate_graphify_env` reference 제거)
- [ ] ADR-0033 / ADR-0032 / ADR-0035 본문 변경 0 — history record 보존 확인

### release artifact

- [ ] `_system/VERSION` = `0.1.8`
- [ ] README badge `v0.1.8` + 개발 상태 1줄 갱신
- [ ] HISTORY.md entry 추가
- [ ] backlog.md #M~#Q 5 row closed marker — 기존 컨벤션 정합 (strikethrough on 앞 3 컬럼 + 결정 컬럼에 `✅ **closed** by \`legacy_migration_cleanup\` (2026-05-25)` prefix)

### 거버넌스 / canary 검증

- [ ] canary tag 부여 (`git tag -f canary <commit> && git push origin canary --force`)
- [ ] OCI 검증 deferred (운영자가 batch 진행) — 본 feature 의 Step 5 는 canary push 까지만, latest promote + v0.1.8 annotated tag 는 OCI 검증 통과 후 운영자 선언으로 진행
- [ ] feature archive 이동 — `features/archive/20260525_legacy_migration_cleanup/`
