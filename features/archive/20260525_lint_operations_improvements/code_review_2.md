# Code Review 2 — lint_operations_improvements (운영 안전성 + LLM 동작 + 데이터 모델)

작성일: 2026-05-25
리뷰어: claude (서브에이전트, Plan)

---

## 종합 평가

**조건부 통과** — H 3건 + M 5건. ADR-0039 + design v2 의 핵심 결정 (alias frontmatter + entity 우선 + yaml opt-in) 정합 통과. 단 자동화 cost 누설 + race + bootstrap silent 가드 필요.

---

## H 항목 (High)

### H1. 자동 호출 모드의 cost 누설 — yaml gate 가 false 일 때도 lint 전체 + graphify chain 매일 1회 추가

- **위치**: `wikihub-lint-apply.service.template:19` + `lint.md` Step 7 gate
- **결함**: timer fire → ExecStart 가 `wh-lint --apply` 호출 → lint Step 1~6 + Step 8 + Step 9 (graphify chain) 모두 진행 → Step 7 만 yaml gate 로 skip. 즉 default `lint_auto_apply=false` 운영자도 매일 03:00 KST 에 lint 전체 cycle + graphify chain 1회 추가 (cloud backend cost +12.5%).
- **파급**: yaml.example 의 코멘트 "true 시 ... 자동" 표현이 운영자 mental model 오도. cost 누설.
- **권고**:
  - (α) ExecCondition fail-fast — `ExecCondition=/bin/bash -c 'test "$(yq -r .operations.lint_auto_apply ...)" = "true"'`. systemd 가 fail 시 success 처리 (OnFailure 미발화).
  - (γ) 최소: wikihub.yaml.example 코멘트 강화 — "false 시에도 service 매일 fire, Step 7 만 skip + graphify chain 매일 1회 cost"

### H2. alias migration 의 frontmatter race + atomic write 미명시

- **위치**: `lint.md` Step 4.5 의 "Alias migration" + 동시 실행 가능한 ingest
- **결함**: lint Step 4.5 가 매 cycle `aliases` 부재 page 의 frontmatter modify (자동, no `--apply` 필요). file lock 부재 → ingest 동시 실행 시 race + 운영자 수동 편집 overwrite 가능.
- **권고**: lint.md Step 4.5 에 atomic write 명시 1 줄 + ingest/lint 책임 경계 명시.

### H3. wikihub-lint-apply.service bootstrap fail silent

- **위치**: `wikihub-lint-apply.service.template:5-8` `OnFailure=ops-alert.service`
- **결함**: agent invocation 자체 실패 시 ops-alert.py 가 last_failure.json 부재로 silent. wikihub_monitor 의 `_emit_bootstrap_alert` 패턴 미적용.
- **권고**: backlog 등록 (BL-N? bootstrap fail self-alert) + design 명시 1 줄.

---

## M 항목 (Medium)

### M1. sed 치환 `[[concepts/<name>]]` → `[[entities/<name>]]` 표현 — wiki-schema 단축형과 미정합 명료화 필요

`lint.md:165` 의 sed 치환은 명시적 카테고리 prefix link 만 매칭 (0건 매칭 가능). 단축형 `[[<name>]]` 은 resolver 자동 fallback — 명료화 1 줄 권고.

### M2. race window 산정 과소평가 — lint duration 30분 가정 시 17%+ 가능

design §2.8 의 5min ÷ 180min = 2.8% 산정이 lint duration 평균 5분 가정. 실 운영 30분 + lint-apply AccuracySec 5분 = 17%. lint.md Step 0 flock 가드 권고 (cheap fix).

### M3. wikihub-lint-apply.timer enable 부재 — reboot 후 자동 fire 안 됨

install.sh start-only 패턴 (BL-N5 backlog). 운영자가 `lint_auto_apply: true` 활성화 시 setup.md / install.sh 안내 1 줄 필요.

### M4. lint Step 4.5 알고리즘 책임 위치 (LLM vs Python) 미명시 — daily token cost 결정적

deterministic Python helper 또는 LLM. 매 cycle wiki 전체 frontmatter read × 8회/일 = daily cost. lint.md spec 책임 명시 1 줄 + helper 신설 backlog 권고.

### M5. cross-category LLM merge 비결정성 + 매 cycle drift

archive 후 concept 재등장 (ingest cycle) 시 LLM merge 재호출 가능 → entity 본문 drift. idempotency gate 1 줄 권고.

---

## L 항목

- **L1** wikihub-lint-apply.service timeout `{timeout_start_sec}` = 1200s 이 lint+graphify 합산 30분+ 가능 시 hit 위험 — BL backlog 후보
- **L2** ADR-0039 link resolver alias 인식 (BL-N12) 미해소 시 sed 치환 edge case
- **L3** wikihub.yaml.example:54 코멘트 운영자 mental model 오도 (H1 동일)
- **L4** ADR-0039 운영자 학습 곡선 surface 부재 — setup.md 안내 권고

---

## 통과 관점 (12건)

- OnFailure=ops-alert.service 추가 정합 (M3-R1 흡수)
- ExecStart agent_invocation_for_wh_lint placeholder 정합
- WIKIHUB_HOME / WIKIHUB_YAML Environment 명시 추가
- Persistent=true + AccuracySec=5min 패턴 정합
- OperationsConfig 2 field 추가 정합
- `_parse_operations` 갱신 정합
- install.sh Group B 2 flag + info log + writer defaults 정합
- render_systemd_units.py 변경 0 (glob 자동 발견 정합)
- wiki-schema.md aliases 필드 spec 추가 정합
- ADR-0036 §"후속 영향" cross-link 정합
- ingest.md Step 4 alias 인식 갱신 정합
- graphify.md 6 위치 timeout 변수화 정합 + 코멘트 정정

---

## 범위 외 (backlog)

- BL-N5 timer enable catalog 정비
- BL-N8 lint Step 0 flock guard
- BL-N11 graphify_timeout_sec backend 별 toggle
- BL-N12 link resolver alias 인식
- lint Step 4.5 deterministic Python helper 신설 (M4)
- wikihub-lint-apply.service bootstrap fail self-alert (H3)

---

## 결론

H1+H2+H3 + M2 closure 권고. design v2 의 핵심 결정 (alias frontmatter, entity 우선 merge, yaml opt-in) 모두 정합 통과. Step 5 squash 전 cheap fix 가치.
