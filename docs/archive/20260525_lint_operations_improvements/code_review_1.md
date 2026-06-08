# Code Review 1 — lint_operations_improvements (Step 4 구현 검증)

작성일: 2026-05-25 (KST)
리뷰어: Claude (독립 컨텍스트, code_review_1 — 이전 conversation 없음)
검토 대상: design v2 (approved) + 신규 ADR-0039 + 13 변경/신규 파일
검토 자료원: 실제 git working tree (HEAD = dba0ee1) 의 read 결과.

---

## 종합 평가

**조건부 통과 — H 1건 + M 2건 closure 후 Step 5 진입 권고.**

DoD 항목 16개 (analysis_and_design.md §5) 의 핵심 라인은 모두 구현체에 반영됐고, design v2 §2.9 (ADR-0039 alias frontmatter) 흡수도 lint.md / ingest.md / wiki-schema.md 3 파일에 정합하게 분산됐다. graphify.md 6 위치 timeout yaml expose 는 line 115/123/129/135/141/147 모두 `timeout "$timeout_sec"` 로 변환 완료 (확인: `grep -c 'timeout "$timeout_sec"'` = 6, `grep -c 'timeout 720'` = 0). systemd template 2건도 wikihub-monitor 의 `SuccessExitStatus=0 75` / `OnFailure=ops-alert.service` 패턴과 정합.

다만:

- **H1** — design_review_2 H2 흡수가 install.sh 에 `systemctl --user start` 1줄로만 구현. design v2 §흡수 항목 정리 H2 본문은 "install.sh `_systemd_start_after_update` 에 `systemctl --user start wikihub-lint-apply.timer` 추가" 만 명시했고 enable 책임은 wikihub-monitor.timer 와 동일 패턴 (start-only) 으로 처리됐다. 그러나 reboot 후 timer fire 보장이 enable 없이는 시스템 의존적 — 본 feature 도입 신규 timer 의 운영 가시화가 약함. **하지만 monitor.timer 등 기존 패턴과 일관** → severity H 가 아닌 M 으로 강등 가능. 그래도 design v2 표 §"H2" 가 "install.sh `_systemd_start_after_update` 에 추가" 까지만 명시 + setup.md `--enable` 분기에 lint-apply.timer 미명시 → H1 으로 남김.
- **M1** — code review 1 (본 리뷰) 가 race window 산정에서 lint.service 실 duration (5~30분) 변수 반영 안 함은 backlog BL-N8 등록되어 closure. 단 lint.md Step 0 의 flock 가드 부재가 daily 03:00 fire 의 wiki/ 동시 변경 race 를 lint_auto_apply=true 운영자에게 노출 → M1.
- **M2** — design v2 의 v1 → v2 라인 카운트 (+240/-13) 가 실 구현 (graphify.md +35 추정 / install.sh +30 추정 / wiki-schema.md +18) 와 약 ±10% 격차. 실 구현 시점 결정으로 closure 가능.

H1 closure (setup.md `--enable` 분기에 wikihub-lint-apply.timer 1 줄 추가 + 또는 design v2 표 §"H2" 의 enable 책임 backlog 등록) 후 Step 5 진행 가능.

---

## C (Critical) — 0건

없음. 핵심 yaml expose + alias frontmatter + systemd template 신설 + install.sh 마이그레이션 + 모든 정본 파일이 정합 통과.

---

## H (High) — 1건

### H1. wikihub-lint-apply.timer 의 enable 책임 부재 — setup.md `--enable` 분기에 미명시 + install.sh `_systemd_start_after_update` 는 start-only

**위치**:
- `install.sh:1669` —
  ```bash
  systemctl --user start wikihub-lint-apply.timer 2>/dev/null || warn "lint-apply.timer start 실패"
  ```
- `_system/commands/setup.md:153` (현행 미수정) —
  > `--enable` 플래그 시: `lint.timer` (+ 조건부 `disk-watch.timer`) **만** `enable --now`. **vault-ingest.timer 는 Step 6 결과에 위임** — 첫 ingest 성공한 vault 만 enable.

**검증**:
- `grep -n "lint-apply\|wikihub-lint-apply" _system/commands/setup.md` → **0건** (setup.md 변경 없음).
- `grep -n "enable --now\|enable wikihub-\|enable wh-" install.sh` → **0건** (install.sh 의 어떤 timer 도 명시적 enable 호출 없음 — start 만).
- wikihub-monitor.timer (v0.1.8) 도 동일 패턴 — install.sh:1667 가 `start` 만 호출.

**파급**:
- design v2 §"흡수 항목 정리 — Reviewer 2 H2" 가 명시 "install.sh `_systemd_start_after_update` 에 `systemctl --user start wikihub-lint-apply.timer` 추가" — 본 라인 자체는 구현 완료 (install.sh:1669). 단 design_review_2 H2 의 원래 권고는 **"enable --now"** 였고 design v2 가 이를 "start" 로 축소 흡수 → wikihub-monitor.timer 와 동일 패턴 일관성 우선. 일관성 정합 OK.
- 그러나 setup.md 의 `--enable` 분기는 v0.1.8 신규 timer (wikihub-monitor.timer + wikihub-lint-apply.timer) 둘 다 미명시. **setup.md spec 이 v0.1.8 변경 흡수 0** — 운영자가 setup.md read 시 lint-apply 의 fire 메커니즘 미인지.
- 실 운영: install.sh 가 `start` 만 호출하지만, systemd-user 가 daemon-reload 후 timer unit 의 `[Install] WantedBy=timers.target` 절이 적용되는 시점은 첫 `enable` 호출 후. 즉 install.sh fresh 경로에서 lint-apply.timer 의 첫 fire 보장은 운영자가 `systemctl --user enable wikihub-lint-apply.timer` 별도 호출 시점에 발화. (단 wikihub-monitor.timer 도 동일하므로 본 feature 가 새 surface 한 결함 아님.)

**권고**:

(a) **setup.md spec 갱신** — `--enable` 분기 (line 153) 에 v0.1.8 timer 흡수 1 줄 추가:
```
`--enable` 플래그 시: `lint.timer` + `wikihub-monitor.timer` + `wikihub-lint-apply.timer` (+ 조건부 `disk-watch.timer`) **만** `enable --now`.
```

(b) 또는 backlog BL-N13 등록 — "install.sh + setup.md 의 v0.1.8 신규 timer (monitor + lint-apply) enable 책임 spec 일관화". design v2 §흡수 H2 의 축소 흡수가 wikihub-monitor.timer 와 정합이라 본 feature 범위 외 가능.

**Severity**: H → 실 운영 결함은 아니나 spec 정본 (setup.md) 가 v0.1.8 timer 흡수 0 — 운영자 학습 곡선 + 차후 feature 의 정합 기준점 부재.

---

## M (Medium) — 2건

### M1. lint.md Step 0 의 flock 가드 부재 — daily 03:00 fire 시 wiki/ 동시 변경 race (BL-N8 등록되어 있으나 closure 안 됨)

**위치**:
- `_system/commands/lint.md` (Step 0 부재 — 본 lint.md 는 Step 1 부터 시작)
- `features/backlog.md:128` — BL-N8 등록:
  > `lint.service` + `wikihub-lint-apply.service` 의 wiki/ working tree 동시 변경 — lint.md Step 0 flock 가드 검토. 03:00 KST race window 산정 실측 필요

**검증**: lint.md L34 가 Step 1 (디렉토리 구조 검증) 으로 직접 진입 — `flock`/`lockfile` 호출 부재. lint.service.template + wikihub-lint-apply.service.template 둘 다 같은 working tree (`{wikihub_home}`) 에서 동작. systemd `Type=oneshot` 은 **같은 unit** 의 중복 실행만 차단 — 다른 unit (lint.service vs wikihub-lint-apply.service) 의 동시 실행은 차단 안 함.

**파급**:
- design v2 §2.8 의 race 산정 "5분 ÷ 180분 = 2.8%" 가 design_review_2 M2 에서 "lint duration 5~30분 변수 반영 안 함 → 실 17%" 로 정정 권고. design v2 는 BL-N8 backlog 로 deferred.
- lint_auto_apply=true 활성화 운영자 (cloud backend 사용 기준 동시 fire 시 cost burden + wiki/ 동시 write 의 비결정성) 에게 surface 안 됨.

**권고**:
- (option α) lint.md Step 1 진입 직전 1 줄 flock 추가:
  ```bash
  exec 200>"$WIKIHUB_HOME/.wh-lint.lock"
  flock -n 200 || { echo "lint 이미 진행 중 — exit 0"; exit 0; }
  ```
  본 변경은 lint.md +3 줄, 본 feature scope 안에서 cheap closure.
- (option β, 현행 결정) BL-N8 유지 — Step 5 배포 후 운영 데이터 surface.

**Severity**: M — 실 race 빈도 (2.8~17%) 가 lint_auto_apply=false (default) 운영자에게는 영향 없음. opt-in 운영자만 노출. design v2 결정 (backlog) 도 정합이지만, cheap closure 가능 + design_review_2 M2 의 권고와 정합.

### M2. lint.md Step 7 의 cross-category merge LLM 호출이 출력 언어 정책 (한국어 + 한자→한글) 명시 부재

**위치**:
- `_system/commands/lint.md:162-166` — Step 7 의 cross-category 처리 본문
- `_system/commands/lint.md:22-30` — 출력 언어 정책 (Step 3·4·5·6 명시, Step 7 미명시)

**검증**: lint.md L22 가 `본 playbook 의 Step 3 (entity·concept stub 생성), Step 4 (cross-ref), Step 5 (index 재구성), Step 6 (모순·갱신 점검) 의 모든 LLM 응답 / wiki 본문 작성에서` 로 명시. **Step 7 의 cross-category merge LLM 호출 (line 163: "concept 페이지의 본문 + referenced_by + alias 셋을 entity 페이지로 LLM merge")** 가 본 정책 적용 대상에서 누락. 그 외 Step 7 의 contradiction reword 도 같은 결함.

**파급**:
- design_review_1 L4 가 surface 한 항목. design v2 가 흡수 정리에서 L4 명시적 closure 표시 안 됨.
- lint_auto_apply=true 운영자가 cross-category merge 결과 (entity 본문 LLM merge) 의 한자/한글 일관성 surface 안 됨.

**권고**: lint.md L22 의 출력 언어 정책 본문에 "Step 7 (--apply 시 contradiction reword + cross-category merge 의 LLM 호출)" 추가:
```
본 playbook 의 Step 3 (entity·concept stub 생성), Step 4 (cross-ref), Step 5 (index 재구성), Step 6 (모순·갱신 점검), Step 7 (--apply 시 contradiction reword + cross-category LLM merge) 의 모든 LLM 응답 / wiki 본문 작성에서:
```

본 변경은 lint.md +1 줄, cheap closure.

**Severity**: M — 정책 적용 대상 명시 누락. 실 LLM 호출의 sanitize layer 자체는 model-agnostic 가드라 미명시여도 동작 가능 (LLM 이 system prompt 의 "출력 언어 정책" 절을 자동 적용 가능), 단 spec 정본의 명시성 약함.

---

## L (Low) — 4건

### L1. lint.md Step 7 본문의 `--apply` 정책 단락 안 `(--apply 자동 호출 일괄 적용)` 표기 — 자동 호출 + 수동 호출 두 경로의 운영 안전성 1 줄 명시 부재

**위치**: `_system/commands/lint.md:168` —
```
**v0.1.0 정책 (확정, v0.1.8 자동 호출 gate 추가)**: `--apply` 호출 시 **일괄 적용** (interactive per-item confirm 없음). 메인테이너는 `_lint/report.md` read → 의도 확인 → ... 자동 timer (lint_auto_apply=true) 는 운영자가 daily review 책임 — wikihub_monitor 보고서 또는 `_lint/report.md` 일일 확인 권장.
```

design_review_1 M2 권고 ("자동 호출 모드의 'report.md 의도 확인' 단계가 운영자 책임으로 이전됨이 spec 본문에 명시 안 됨") 의 흡수 — design v2 §흡수 표 M2 라인 = "lint.md spec 본문 1 줄 명시" → 구현 완료 (line 168 의 `자동 timer (lint_auto_apply=true) 는 운영자가 daily review 책임 — wikihub_monitor 보고서 또는 _lint/report.md 일일 확인 권장`).

**Severity**: L — 정합 confirm. 변경 불요.

### L2. graphify.md L156(현 L159) 코멘트의 "수정 완료" 표기

**위치**: `_system/commands/graphify.md:159` —
```
- `timeout "$timeout_sec"`: yaml `operations.graphify_timeout_sec` 정본 (default 900s = 15분, v0.1.8 yaml expose — ADR-0036 §"후속 영향"). graphify 의 `--api-timeout` (default 600s) + LLM 호출 누적 대비 wrapper 보호 margin. 운영자가 yaml 조정 가능.
```

design v2 §2.1.2 의 변경 패턴 그대로 적용 완료:
- v0.2.x deferred 표기 폐기 (정합)
- v0.1.8 yaml expose 명시
- ADR-0036 §"후속 영향" cross-link (정합 — ADR-0036:128 의 "2026-05-25: lint_operations_improvements (v0.1.8) ..." 항목과 cross-link 정합)

**Severity**: L — 정합 confirm.

### L3. wiki-schema.md aliases 절의 cross-category 정책이 5 행 표로 흡수 — design v2 §2.9 의 "4 행 표" 명시와 +1 행 격차

**위치**: `_system/wiki-schema.md:211-217` — aliases 필드 표 (5 행: 의미 / 비교 / LLM loop / duplicate detection / cross-category 정책)

**검증**: design v2 §2.9 "신규 §2.9 — alias frontmatter" 의 본문은 4 항목 (의미 / 비교 / LLM loop / duplicate detection) 명시. cross-category 정책은 design v2 §"흡수 H1" 에서 "wiki-schema 에 cross-category merge 정책 1 줄 추가" 로 명시 → 실 구현은 5 번째 행에 추가 (정합 흡수). design v2 본문과 1 행 격차는 **흡수 항목 정리**에 일치하므로 정합.

**Severity**: L — design 본문 vs 흡수 항목의 표현 격차. 실 구현은 정합.

### L4. backlog.md BL-N12 (wiki link resolver alias 인식) 항목의 source 인용이 "ADR-0039 §재검토 트리거"

**위치**: `features/backlog.md:132`
```
| BL-N12 | data model | wiki link resolver 의 alias 인식 — `[[mini-max]]` 가 `MiniMax` page 로 자동 해석. 현행 `--apply` 가 sed 치환으로 link 정합. resolver layer 통합 시 별도 ADR | ADR-0039 §"재검토 트리거" | low |
```

design 본문 (analysis_and_design.md §v2 흡수 §"v2 영향 범위 증가") 의 BL 등록 라인이 `BL-N9~N11 추가 +6` 만 명시했고, BL-N12 는 ADR-0039 의 §"재검토 트리거" 에서 자연 추출. ADR-0039 §재검토 트리거 line 99 가 정확히 "wiki-schema 의 link resolver 가 alias 인식 (`[[mini-max]]` 가 `MiniMax` page 로 자동 해석) 필요 시 — 별도 ADR" 로 명시 → backlog BL-N12 cross-link 정합. design 본문이 BL-N9~N11 만 적시했으나 ADR-0039 가 추출한 BL-N12 가 자연 추가됨 — 정합 흡수.

**Severity**: L — design 본문 cover count 와 실 backlog count 의 +1 격차. backlog 갱신은 정합.

---

## 통과 관점 (정합 confirm — 변경 불요)

다음 항목은 검토 결과 정합. 구현체 그대로 OK:

1. **graphify.md 6 위치 timeout yaml expose**: line 115/123/129/135/141/147 모두 `timeout "$timeout_sec" env ...` 로 변환 (`grep -c 'timeout "\\$timeout_sec"'` = 6). `timeout_sec` 변수 정의 (line 111: `timeout_sec="$(yq '.operations.graphify_timeout_sec // 900' "$WIKIHUB_HOME/wikihub.yaml")"`) 가 case 진입 (line 113) 전 적절한 위치. 6 분기 ollama/openai/claude/gemini/deepseek/kimi 모두 동일 패턴 적용. `timeout 720` 0건 (`grep -c 'timeout 720'` = 0). v0.2.x deferred 표기 폐기 완료.

2. **ADR-0036 §"후속 영향" cross-link**: ADR-0036 line 128 = `2026-05-25: lint_operations_improvements (v0.1.8) 가 graphify timeout wrapper 의 yaml expose 작업 완료. graphify.md Step 2 의 6 위치 hard-coded timeout 720 가 timeout "$timeout_sec" 로 변경 (yaml operations.graphify_timeout_sec 정본, default 900s = 15분). 운영자 backend 별 조정 가능. graphify.md:156 의 "yaml expose 는 v0.2.x deferred" 코멘트 폐기 처리.` — design v2 §2.7 정합.

3. **wikihub-lint-apply.service.template**:
   - `OnFailure=ops-alert.service` (line 8) — wikihub-monitor.service.template:7 패턴 정합. design v2 §흡수 M3 closure 확인.
   - `SuccessExitStatus=0 75` (line 20) — wikihub-monitor 의 runtime fail swallow 패턴 정합.
   - `ExecStart={agent_invocation_for_wh_lint} "/wh-lint --apply"` (line 19) — `render_systemd_units.py` line 227 의 `_per_skill_invocation` 자동 등록 정합 (skill `wh-lint` → `agent_invocation_for_wh_lint` 키).
   - 4 placeholder (`{wikihub_home}`, `{venv_path}`, `{agent_invocation_for_wh_lint}`, `{timeout_start_sec}`) 모두 `_instance_wide_subs` (line 211/214/222) + `_per_skill_invocation` 에 등록 — render 시 정합 치환.
   - `_PER_VAULT_PATTERN` (`@\.` regex) 매치 안 함 → singleton 처리.

4. **wikihub-lint-apply.timer.template**:
   - `OnCalendar=*-*-* 03:00:00 Asia/Seoul` (line 8) — design v2 §2.3.2 명시 정합. wikihub-monitor.timer (09,21:00) 와 분리.
   - `Persistent=true` (line 9), `AccuracySec=5min` (line 10) — design v2 결정 정합.
   - `[Install] WantedBy=timers.target` (line 12) — systemd user-level timer 정합.

5. **install.sh _migrate_agent_schema Group B**:
   - `B_graphify_timeout_sec` (line 820) + `B_lint_auto_apply` (line 822) flag detect 정합.
   - info log case 2건 추가 (line 864/865) — 형식 정합 (`[v0.1.8 ADR-0036] / [v0.1.8 ADR-0039]`).
   - yaml writer `_op_defaults` 에 2 field 추가 (line 918/919) — `graphify_timeout_sec: 900` + `lint_auto_apply: False`.

6. **install.sh systemd 3 위치 (stop / reset-failed / start / try-restart) 모두 lint-apply 추가**:
   - `stop` (line 1612): `systemctl --user stop wikihub-lint-apply.timer 2>/dev/null || true` 정합.
   - `reset-failed` (line 1632): `'wikihub-lint-apply.service' 'wikihub-lint-apply.timer'` 추가 정합.
   - `start` (line 1669): `systemctl --user start wikihub-lint-apply.timer ...` 정합.
   - `try-restart` (line 1715): unit list 의 마지막에 `wikihub-lint-apply.timer` 추가 정합.

7. **config.py OperationsConfig**:
   - dataclass 에 2 field 추가 (line 66/67): `graphify_timeout_sec: int = 900` + `lint_auto_apply: bool = False` — design §2.4 정합.
   - `_parse_operations` (line 174/175): `int(ocfg.get("graphify_timeout_sec", 900))` + `bool(ocfg.get("lint_auto_apply", False))` — default 값 정합.
   - `py_compile config.py` pass (검증 완료).

8. **wikihub.yaml.example**:
   - line 52-54: 안내 주석 + 2 field 추가 정합. 코멘트가 ADR-0036 §"후속 영향" + ADR-0039 alias frontmatter cross-link 명시.
   - `lint_auto_apply: false` 의 코멘트 (line 54) 가 "활성화 시 graphify chain 도 매일 1회 추가 호출 (cloud backend 사용 시 API token cost 증가)" 명시 — design_review_2 H4 closure 정합.

9. **wiki-schema.md aliases 절**:
   - line 193 의 entity sample frontmatter 에 `aliases: [홍길동]` 추가 — design v2 §2.9 + ADR-0039 §Decision 1 정합.
   - line 209-217 의 §"aliases 필드" 5 행 표 — 의미 / 비교 / LLM loop / duplicate detection / cross-category 정책 (entity 우선 merge) 모두 명시.
   - ADR-0039 §Decision 의 1/2/3 단계와 정확히 정합.

10. **lint.md alias 처리 (Step 3 / Step 4.5 / Step 7) — ADR-0039 정합**:
    - **Step 3 (line 58)** — stub 생성 전 기존 page `aliases` 셋의 lowercase normalize 비교, 본문 form lowercase 가 셋에 포함 시 stub 생성 skip + referenced_by 만 갱신. ADR-0039 §Decision 3 정합 + LLM 재생성 무한 loop 차단 명시.
    - **Step 4.5 (line 66-83)** — alias migration (부재 시 자동 보강) + case-variant duplicate detection (alias 셋의 lowercase normalize 비교 + 공통 form 1+ 시 duplicate) + cross-category duplicate (entity ∩ concept 의 lowercase normalize 비교). 알고리즘 정합.
    - **Step 7 (line 156-166)** — case-variant: canonical 보존 + alias 합집합 + 다른 form archive + sed 치환. cross-category: entity 우선 + LLM merge (본문 + referenced_by + alias) + concept archive + sed 치환 `[[concepts/<name>]]` → `[[entities/<name>]]`.

11. **ingest.md alias 인식 (line 148/150)**:
    - `2. entity·concept 추출 — ADR-0013 정책 정본` 의 마지막 bullet 에 ADR-0039 추가: `- 동의어 처리는 frontmatter aliases 필드 — ADR-0039 (v0.1.8 신설)`
    - `3. 각 entity·concept에 대해` 의 첫 sub-bullet 에 alias 인식 명시: `alias 인식 (ADR-0039): 본문 form 의 lowercase 가 기존 page 의 frontmatter aliases 셋 (lowercase normalize) 1+ 공통 → 기존 page 로 간주. referenced_by 만 추가 (alias 셋 미변경, stub 생성 skip — LLM 재생성 무한 loop 차단)`
    - 신규 stub 생성 시 `aliases: [<본문 form>]` 명시 (line 152). ADR-0039 §Decision 2 정합.

12. **ADR-0039 §Decision 1~3 의 lint.md / ingest.md / wiki-schema.md 분산 흡수**:
    - §Decision 1 (frontmatter spec) → wiki-schema.md L193 + L209-217 + sample (정합)
    - §Decision 2 (alias 생성 책임) → ingest.md L148/150/152 + lint.md Step 3 (L58) + Step 4.5 alias migration (L70-72) + Step 7 (L156-160) (정합)
    - §Decision 3 (LLM 재생성 무한 loop 방지) → ingest.md L150 + lint.md Step 3 L58 (정합)

13. **bash -n install.sh + py_compile config.py 모두 pass** (DoD §5 마지막에서 두 번째 항목 — 검증 완료).

14. **backlog.md BL-N7~N12 등록**:
    - BL-N7 (line 127): wikihub_monitor 가 wh-lint-apply 결과 surface — design §2.6 cross-link.
    - BL-N8 (line 128): lint.service + lint-apply race — design_review_2 운영 안전성 cross-link.
    - BL-N9 (line 129): `--api-timeout` (600s) vs wrapper (900s) — design_review_1 M1.
    - BL-N10 (line 130): lint_auto_apply gate ExecStartPre 의 fail-fast cost 절감 — design_review_1 M5.
    - BL-N11 (line 131): graphify_timeout_sec backend 별 toggle — design_review_2 H3.
    - BL-N12 (line 132): wiki link resolver alias 인식 — ADR-0039 §재검토 트리거.

15. **race / 동시성 confirm**: lint.timer (3h interval, AccuracySec=15min) + wikihub-lint-apply.timer (daily 03:00 KST, AccuracySec=5min) — systemd 가 같은 unit 만 차단, 다른 unit 동시 활성 가능. design v2 §2.8 의 2.8% race window 산정 (lint duration ~5min 가정) → BL-N8 backlog 등록 정합. M1 권고 (flock 가드) 는 cheap closure 가능.

---

## 범위 외 (별도 feature 또는 backlog)

1. **wiki link resolver 의 case-sensitivity 정책** (design_review_2 C1 검토 중 surface) — ADR-0001 link 규약의 case-sensitivity 미명시. 현 구현은 sed 치환으로 link 정합 → BL-N12 등록.
2. **graphify_timeout_sec backend 별 toggle** — design_review_2 H3 권고. BL-N11 등록.
3. **lint.timer + wikihub-lint-apply.timer race window 실측 + flock 가드** — BL-N8 등록.
4. **wikihub_monitor 가 wh-lint-apply 결과 surface** — BL-N7 등록.
5. **ExecStartPre 의 fail-fast gate** (lint_auto_apply=false 시 agent invocation cost 절감) — BL-N10 등록.
6. **wikihub-monitor.timer + wikihub-lint-apply.timer 의 install.sh enable 책임 일관성** — H1 closure 또는 별도 BL.

---

## 결론 및 다음 단계 권고

1. **H1 closure (필수, cheap)**: setup.md L153 의 `--enable` 분기에 wikihub-monitor.timer + wikihub-lint-apply.timer 1 줄 추가. install.sh 의 start-only 패턴은 wikihub-monitor.timer 와 일관 정합 유지.
2. **M1 권고 (cheap closure 가능)**: lint.md Step 1 진입 직전 flock 1 줄 추가 — 또는 BL-N8 backlog 유지. design v2 결정 (backlog) 도 정합.
3. **M2 권고 (cheap)**: lint.md L22 의 출력 언어 정책 본문에 "Step 7 (cross-category LLM merge)" 추가 — 1 줄.
4. **L1~L4 는 모두 정합 confirm — 변경 불요**.
5. **DoD §5 의 16+ 항목 모두 통과** — Step 5 진입 권고. H1 closure 만 받으면 Step 5 squash + 사용자 최종 승인.

본 feature 의 핵심 결정 (graphify timeout yaml expose + alias frontmatter 도입 + lint --apply 자동화 timer + cross-category merge spec) 모두 정합하게 구현됐고, ADR-0039 의 §Decision 1~3 도 lint.md / ingest.md / wiki-schema.md 3 파일에 분산 흡수됨. design v2 의 v1 → v2 alias 도입 (Reviewer 2 C2 결함 + 사용자 명시) 가 적절히 구현체에 반영됨.

---

## 검토 자료원

- `_system/commands/lint.md` (L1~281, 실제 read — Step 3 alias / Step 4.5 / Step 7 / Step 9 4 위치 확인)
- `_system/commands/graphify.md` (L1~241, 실제 read — L111 변수 정의 / L115/123/129/135/141/147 6 위치 timeout 확인 + L159 코멘트)
- `_system/commands/ingest.md` (L1~236, 실제 read — L148/150/152 alias 확인)
- `_system/wiki-schema.md` (L1~391, 실제 read — L193 sample + L209-217 aliases 절)
- `_system/systemd/wikihub-lint-apply.service.template` (L1~26, OnFailure / SuccessExitStatus / ExecStart 확인)
- `_system/systemd/wikihub-lint-apply.timer.template` (L1~14, OnCalendar / Persistent / AccuracySec 확인)
- `_system/systemd/lint.service.template` + `wikihub-monitor.service.template` (cross-template 패턴 비교)
- `scripts/lib/config.py` (L65-67 dataclass + L173-175 _parse_operations)
- `install.sh` (L780-870 _migrate_agent_schema Group B + L883-936 yaml writer + L1602-1670 systemd start/stop + L1714-1715 try-restart)
- `wikihub.yaml.example` (L52-54 신규 2 field 안내 주석)
- `docs/adr/0036-graphify-cli-integration.md` (L119-128 §"후속 영향" cross-link)
- `docs/adr/0039-entity-concept-alias-frontmatter.md` (L1~105 전체 — Decision 1/2/3 + Consequences + Cross-references)
- `scripts/_helpers/render_systemd_units.py` (L195-230 _instance_wide_subs placeholder 등록 확인)
- `features/backlog.md` (L127-132 BL-N7~N12 등록)
- `_system/commands/setup.md` (L153 — `--enable` 분기, lint-apply 미명시 확인)
- `features/20260525_lint_operations_improvements/analysis_and_design.md` (v2 approved, L1~430)
- `features/20260525_lint_operations_improvements/design_review_1.md` + `design_review_2.md` (전체)
- bash -n install.sh + py_compile config.py 둘 다 pass

---

리뷰어: code_review_1 (Claude, 독립 컨텍스트)
보고 라인 수: 약 300 줄
