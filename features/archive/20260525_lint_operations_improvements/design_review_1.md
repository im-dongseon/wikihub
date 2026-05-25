# Design Review 1 — lint_operations_improvements

작성일: 2026-05-25 (KST)
리뷰어: Claude (독립 컨텍스트, design_review_1)
검토 대상: `features/20260525_lint_operations_improvements/analysis_and_design.md` v1 (approved)
검토 관점: lint.md / graphify.md spec 정합 + ADR 정합 + systemd 정합

---

## 종합 평가

**conditional approve — H 1건 closure 후 Step 3 진입 권고.**

설계는 운영 surface 3건 (I1~I3) 의 결정 D1~D5 + default Q1-a/Q2-b/Q2-c 를 정합하게 흡수했고, 코드베이스 정본 (`lint.md`, `graphify.md`, `OperationsConfig`, `_migrate_agent_schema`, `wikihub.yaml.example`, render glob, lint.service.template) 과의 cross-check 도 대부분 통과한다. 특히:

- graphify.md L112/120/126/132/138/144 의 `timeout 720` 6 위치는 모두 동형 hard-code 로, 단일 변수화 가능 — 본 design §2.1.2 의 변경 패턴이 그대로 적용된다.
- `lint.md:183` 의 `timeout 300 graphify` 표현은 실제 본문에서 발견되지 않는다 — `lint.md` 의 현재 L183 은 `graphify.md Step 2 가 단일 책임 ... timeout 발생 시 (exit 124) report 에 'graph rebuild timeout' 기록` 으로, 300 이라는 숫자는 본문 어디에도 없다. design §2.1.3 의 "기존 line 183: `timeout 발생 시 (exit 124) report 에 ...`" 인용은 정확하나, design §1.2 표의 `_system/commands/lint.md:183` "timeout 300 graphify 표현 — 부정확 (실제 720)" 은 **현재 lint.md 가 이미 표현 분리** 된 결과를 잘못 회상한 항목이다 (graphify.md L156 의 코멘트만 "v0.2.x deferred" 로 남아 있음). 이 회상은 ADR-0036 §Note `--추가 보강 — lint Step 9 의 timeout wrapper` 의 `timeout 300 graphify ...` 표현 (제안 시점 표현, 그 후 graphify.md 로 lift) 에서 끌어왔을 가능성. H1 참조.
- systemd template 신설 (wikihub-lint-apply.{service,timer}) 의 모든 placeholder (`{wikihub_home}`, `{venv_path}`, `{agent_invocation_for_wh_lint}`, `{timeout_start_sec}`) 가 render_systemd_units.py `_instance_wide_subs` (L211/214/222) + `_per_skill_invocation` (L227) 에 이미 등록돼 있어 별도 helper 변경 불필요. `_PER_VAULT_PATTERN` (`@\.` regex, L48) 매치 안 함 → singleton 처리 정상. design §1.3 의 "render_systemd_units.py 변경 0" 정합.
- OperationsConfig 의 2 field 추가 + `_parse_operations` 2 line 갱신 + `_migrate_agent_schema` Group B 2 flag + writer defaults 4 줄 변경은 v0.1.8 monitor_* 필드 흡수 패턴 (config.py L62-64, install.sh L811-817/L856-858/L908-910) 과 1:1 정합.

H1 (lint.md:183 표현 정정 항목의 거짓 결함) 만 closure 하면 Step 3 진행 가능. M/L 항목은 implementation 또는 follow-up 으로 흡수.

---

## C (Critical) — 0건

없음.

---

## H (High) — 1건

### H1. design §1.2 F1 표의 `lint.md:183` 결함 묘사가 코드베이스 정본과 불일치 — Step 3 의 변경 대상이 모호해짐

**위치**: `analysis_and_design.md` L28 + L91-101 (Step 9 표현 정정 §2.1.3)

**인용**:
```
| `_system/commands/lint.md:183` | "timeout 300 graphify" 표현 — **부정확** (실제 720) |
```

및 §2.1.3:
```
기존 line 183:
```
timeout 발생 시 (exit 124) report 에 `graph rebuild timeout` 기록
```
→ 변경:
```
timeout 발생 시 (exit 124, default 900s — yaml `operations.graphify_timeout_sec`) report 에 `graph rebuild timeout` 기록
```
```

**검증**: 현재 `_system/commands/lint.md` L183 은 다음과 같음 (실 read 결과):

```
**graphify 호출 형태**: graphify.md Step 2 가 단일 책임 (ADR-0006 single-source + ADR-0038 namespace 격리). lint.md 는 `<agent_invocation> "/wh-graphify"` 만 호출 — backend dispatch / profile resolve / endpoint 분기 / timeout 의 detail 은 graphify.md 참조. timeout 발생 시 (exit 124) report 에 `graph rebuild timeout` 기록 + lint 계속 (graphify partial 보호는 graphify.md Step 3 가 책임).
```

- 본 L183 에는 **`timeout 300 graphify` 또는 `timeout 720` 같은 wrapper 표현 자체가 이미 없다** (graphify.md Step 2 로 위임 완료 — ADR-0038 v0.1.7 follow-up 단계에서 lift). 즉 design §1.2 표의 "표현 drift" 결함은 현 시점 코드베이스에 존재하지 않는다. 운영자 보고 "300초 timeout" 종료의 lint.md spec 책임은 v0.1.7 시점부터 graphify.md 로 이전.
- design §2.1.3 의 "→ 변경" 패치 자체는 정확 (현 L183 본문 → default 900s 정보 추가). 단 결함 묘사 표현이 코드와 어긋남 → Step 3 구현자가 grep 으로 "300" 을 찾으면 발견 안 됨 → 변경 위치 confusion 발생 가능.

**권고**:

(a) §1.2 표의 `_system/commands/lint.md:183` 행을 다음으로 정정:
```
| `_system/commands/lint.md:183` | timeout 표현이 graphify.md 로 위임 완료 (ADR-0038 follow-up). 단 default 값 (900s) + yaml key (`operations.graphify_timeout_sec`) 정보가 lint Step 9 보고 형식에서 누락 — 운영자 진단 시 yaml field 명 hop 1 추가 |
```

(b) §2.1.3 의 "기존 line 183:" 인용 본문도 실제 lint.md L183 의 `timeout 발생 시 (exit 124) report 에 \`graph rebuild timeout\` 기록 + lint 계속` 전체 문장으로 정확히 인용하면 Step 3 patch 시점 confusion 차단.

**Severity**: H — 결함 묘사 자체가 invalid 라 Step 3 가 grep "300" 으로 못 찾고, 또한 §6 의 "(ii) 또는 graphify 의 다른 timeout source (LLM API call timeout)" 가설을 부정하는 근거 약화. 패치 자체는 동작 가능하나, Step 3 자가 검증에서 "왜 300 이 안 보이지?" 단계를 거쳐야 함.

---

## M (Medium) — 5건

### M1. graphify.md §"graphify 호출 형태" 부분 자체에 `--api-timeout` default 명시 누락 — wrapper 900s 와 CLI 600s 의 관계 surface

**위치**: graphify.md L156 의 코멘트 + design §2.1.2 변경 패치

design §2.1.2 의 변경 후 코멘트:
```
- `timeout $timeout_sec`: yaml `operations.graphify_timeout_sec` 정본 (default 900, v0.1.8 yaml expose).
  graphify 의 `--api-timeout` (default 600s) + LLM 호출 누적 대비 wrapper 보호 margin.
```

**검토**: graphify CLI 의 `--api-timeout default 600s` 는 **per-request** timeout (ADR-0036 §Note 2026-05-24 §발견). 다중 Pass 3 LLM call 누적 시 wrapper 900s 가 부족할 수 있는 시나리오 (Pass 3 에서 N개 source LLM call × 평균 latency = 누적). 본 design 의 default 900s 가 D4 결정 (사용자 "15분") 이므로 변경 권고 안 함. 단:

- graphify CLI 의 `--api-timeout` 도 yaml 격상 검토 필요한지 surface — Q-A/B/C 의 후속 backlog 후보.
- 현 default 900s 가 wiki 500+ page 규모 + DeepSeek/MiniMax (CPU 10.6s/call) 에서 충분한지 운영 데이터 surface 후 D4 재방문 트리거 등록 필요.

**권고**: design §4 (미결 사항) 또는 ADR-0036 §재검토 트리거에 1줄 추가 — "wrapper timeout 900s 충분성 운영 데이터 surface 시 graphify `--api-timeout` (per-request) yaml 격상 검토".

### M2. lint.md Step 4.5 의 `--apply` 작업 추가가 Step 7 의 v0.1.0 "일괄 적용 (interactive 없음)" 정책과 정합 명시 부재

**위치**: lint.md L125 + design §2.2.2

lint.md L125:
```
**v0.1.0 정책 (확정)**: `--apply` 호출 시 **일괄 적용** (interactive per-item confirm 없음). 메인테이너는 `_lint/report.md` read → 의도 확인 → `<agent_invocation> "/wh-lint --apply"` 1회 호출로 모든 위험 작업 적용. interactive 세분화는 v0.2.x 후속 ADR 후보.
```

design §2.2.2 의 추가 작업 (case-variant normalize + cross-category merge) 은 본 정책에 자연 정합 (일괄 적용). 단 **자동 호출** (wikihub-lint-apply.timer) 경로에서 일괄 적용의 위험도가 수동 호출 대비 다르다 — 메인테이너가 report.md 를 read 한 후 의도 확인하는 v0.1.0 정책의 전제가 자동 모드에서 무너짐. design §2.3.3 의 "메인테이너 수동 호출 (`/wh-lint --apply`) 은 항상 진행 (gate 무관)" 은 정합하나, 자동 호출 모드의 "report.md 의도 확인" 단계가 운영자 책임으로 이전됨이 spec 본문에 명시 안 됨.

**권고**: lint.md Step 7 의 gate 본문 또는 v0.1.0 정책 단락 옆에 1 줄 추가:
> "v0.1.8 자동 호출 (wikihub-lint-apply.timer + `operations.lint_auto_apply: true`) 진입 시: 운영자가 직전 cycle 의 `_lint/report.md` 를 사전 review 한 상태로 가정 — opt-in 책임."

### M3. 신규 wikihub-lint-apply.service 의 OnFailure 부재 결정 사유의 가시화 약함

**위치**: design §2.3.1 service template 의 코멘트
```
# OnFailure=ops-alert.service 부재 (lint.service 와 동일 패턴 — auto-apply 실패는 일상 lint 재시도가 자연 처리)
```

**검증**: 실제 lint.service.template L5 은 `OnFailure=ops-alert.service` **있음**. wikihub-monitor.service.template L7 은 `OnFailure=ops-alert.service` 있음 + L5-6 코멘트 "bootstrap fail (exit 2) 만 ops-alert 발화. runtime fail (exit 75) 은 SuccessExitStatus 정합 → 미발화". design §2.3.1 의 "lint.service 와 동일 패턴" 은 **부정확** — lint.service 는 OnFailure 보유.

본 service 의 OnFailure 결정의 정합 모델은 wikihub-monitor 의 "SuccessExitStatus=0 75" 와 동일하다 (runtime fail 은 미발화, bootstrap fail 만 발화). lint-apply 도 SuccessExitStatus=0 75 로 한 결정 (design §2.3.1 L182) 이 정합하므로 **OnFailure=ops-alert.service 추가 권장** — wikihub-monitor 패턴 정합.

**권고**: design §2.3.1 의 service template 에 `OnFailure=ops-alert.service` 추가 + 코멘트 정정:
```
OnFailure=ops-alert.service
# wikihub-monitor 패턴 정합 — bootstrap fail (exit 2) 만 alert 발화, runtime fail (exit 75) 은 SuccessExitStatus 로 swallow.
```

### M4. cross-category merge 후 referenced_by 갱신의 wiki/ 전체 grep 가능성 검증 부재

**위치**: design §2.2.1 Step 4.5 + §2.2.2 Step 7 확장

cross-category merge 시 작업:
1. concept 페이지의 본문 + referenced_by 를 entity 페이지로 LLM merge
2. concept 페이지를 `.archived/concepts/<name>.md` 이동
3. wiki/ 전체에서 `[[concepts/<name>]]` link 를 `[[entities/<name>]]` 로 갱신

**검증**:
- wiki-schema.md L193, L221 에 따르면 `referenced_by` field 는 frontmatter list — 페이지 간 ADR-0001 link 가 `[[concepts/<name>]]` 형식이면 grep 으로 발견 가능.
- 단 sources 에서의 link 는 wiki-schema.md ADR-0001 vault prefix 정합 — `[[gdrive/...]]` 형식이라 concept link grep 시 sources 안의 cross-reference 까지 caught.
- entity 우선 merge 시 같은 이름의 entity 가 이미 존재 (cross-category 의 정의) — entity 페이지의 frontmatter `referenced_by` 에 concept 의 referenced_by source 들을 set-union 으로 추가하는 알고리즘 명시 부재.

**권고**: design §2.2.2 의 cross-category merge bullet 에 알고리즘 한 줄 추가:
```
- concept.frontmatter.referenced_by 의 source paths 를 entity.frontmatter.referenced_by 에 set-union 추가 (Step 4 의 set semantics 패턴 정합)
- 본문 merge 는 LLM 책임 (한국어 출력 정책 적용, 출력 언어 정책 섹션 정합)
- wiki/ 전체 grep `[[concepts/<old_name>]]` → `[[entities/<new_name>]]` 치환 (sed -i 또는 LLM batch)
```

### M5. lint_auto_apply gate 의 위치 — service 가 아닌 lint.md Step 7 본체에서 yaml read 의 systemd 시점 부정합

**위치**: design §2.3.1 의 코멘트 + §2.3.3 gate

design §2.3.1 의 service template 코멘트:
```
# yaml `operations.lint_auto_apply` toggle 은 wh-lint 스킬 본체가 확인 (lint.md Step 7 진입 직전 gate).
```

design §2.3.3 의 gate:
```
lint_auto_apply="$(yq '.operations.lint_auto_apply // false' "$WIKIHUB_HOME/wikihub.yaml")"
# wikihub-lint-apply.service 호출 시 lint_auto_apply=false 면 즉시 exit 0 (no-op)
```

**검토**: gate 가 lint.md Step 7 안에서 yaml 을 직접 read 하면 — Hermes (agent) 가 LLM 호출 (system prompt 처리, model load, tokenize) 끝에 진입 → 그 시점에 yaml false 면 exit 0. **운영적으로 cost overhead 발생** (agent 가 처음부터 끝까지 invocation, default false 일 때도 매일 03:00 KST agent latency 1회). wikihub-monitor 패턴 — config.py 의 `monitor_enabled: false` 면 `wikihub_monitor.py` 가 즉시 exit 0 (python startup 만, agent 없음). lint-apply 는 agent 가 mediate 라 monitor 와 다르다 — agent invocation 시작 전에 gate 가 좋다.

**권고**:
- (option α, 권고) service template 의 ExecStartPre 또는 ExecStart 앞에 inline check 추가 — `ExecStartPre=/bin/bash -c 'yq ".operations.lint_auto_apply // false" $WIKIHUB_YAML | grep -qx true || exit 0'`. 단 ExecStartPre 가 fail 시 main 호출 안 됨 — exit 0 가 SuccessExitStatus=0 75 정합.
- (option β, 단순) lint.md Step 7 gate 그대로 유지 + 03:00 agent invocation cost 운영 데이터 surface 시 α 로 재방문 — backlog 등록.

설계는 β 채택 (단순성) 정합. 단 운영적 cost 명시 + backlog 등록 권고.

---

## L (Low) — 4건

### L1. design §1.3 표의 라인 카운트 불일치

design §1.3 의 row sum:
- lint.md: +60/-5
- graphify.md: +10/-8
- systemd .template 2 file: +40
- config.py: +5
- wikihub.yaml.example: +6
- install.sh: +20
- render_systemd_units.py: 0

총합: +141 / -13 (net +128). design §1.3 fineprint 일치. 단:
- graphify.md +10 / -8 — 6 위치 × 2 line (timeout 720 → timeout $timeout_sec) 만 해도 6 줄 변경 + 1 줄 변수 선언 (yq read) = +1/-0 또는 +7/-6. design 추정이 보수적이나 graphify.md L156 코멘트 정정 (+3/-2) 포함 시 +10/-8 근접.
- install.sh +20 — Group B drift detect (4줄) + info log case (2줄) + yaml writer defaults (2줄) + systemd stop/start/try-restart (3 위치 × 1 = 3줄) = ~11줄. +20 는 보수적.

**Severity**: L — 실제 patch 시점 결정.

### L2. systemd-analyze verify 가 신규 unit 도 자동 cover (render glob)

`render_systemd_units.py` L461 의 `services = sorted(out_dir.glob("wikihub-*.service")) + sorted(out_dir.glob("wikihub-*.timer"))` 가 신규 wikihub-lint-apply.{service,timer} 자동 cover. design §1.3 의 "변경 0" 정합. 추가 검증 불필요.

**Severity**: L — 정합 confirm.

### L3. 03:00 KST fire 시점이 graphify cycle 의 cost peak 와 충돌 가능성

design §2.3.2 결정:
- 03:00 KST — 운영자 idle 시간

검토: lint.timer 가 3h 주기 (OnUnitInactiveSec=3h) — fire 시점이 install.sh 시점 + 3h 누적 offset. 03:00 ± 5min 의 race 확률은 design §2.8 에서 "5분 ÷ 180분 = 2.8%" 추정. 운영적 영향 낮음 정합. 단 lint-apply 가 그 자체로 graphify chain (Step 9) 호출 → 03:00 에 LLM API cost spike 가능. wikihub_monitor.py 가 09:00 / 21:00 fire — 03:00 의 lint-apply 결과를 09:00 monitor 에서 surface 가능 (backlog BL-N7 정합).

**Severity**: L — design §2.6 + §2.8 에서 이미 backlog 등록.

### L4. lint.md "출력 언어 정책" (한국어 + 한자→한글 변환) 의 case-variant normalize 영향

lint.md L22-30 의 "출력 언어 정책" 은 LLM 응답의 출력 언어 (한국어) 와 한자 sanitize 를 명시. case-variant normalize 가 entity 이름의 lowercase 변환을 LLM 호출 없이 mechanical 하게 수행 — 본 정책의 LLM 출력 sanitize layer 와 무관. 단 cross-category merge 시 LLM 호출 (본문 merge) 은 본 정책 적용 대상 — design §2.2.2 의 cross-category merge bullet 에 1줄 코멘트 ("LLM 호출은 lint.md 출력 언어 정책 정합") 추가 권고.

**Severity**: L — implementation 시 자동 적용 가능.

---

## 통과 관점 (정합 confirm — 변경 불요)

다음 항목은 검토 결과 정합. design 그대로 진행 OK:

1. **graphify.md 6 위치 hard-code → yaml expose**: L112/120/126/132/138/144 의 `timeout 720 env ...` 패턴이 모두 동형 (case statement 안 backend 별 6분기). design §2.1.2 의 변경 패턴 (`timeout_sec` 변수화) 적용 가능. 변수 선언은 Step 2 의 profile resolve block (L42) 직후가 자연.

2. **OperationsConfig 2 field 추가**: config.py L62-64 의 monitor_* 패턴과 1:1 정합. default 값 (`graphify_timeout_sec: int = 900`, `lint_auto_apply: bool = False`) 의 type 정합.

3. **`_migrate_agent_schema` Group B 2 flag**: install.sh L811-817 (B_monitor_* 3 flag) + L856-858 (info log) + L908-910 (writer defaults) 패턴 정합. design §2.5 의 변경 위치 정확.

4. **wikihub.yaml.example operations 블록**: L48-51 의 monitor_* 3 줄 패턴 — design §2.1.1 의 graphify_timeout_sec 1 줄 + lint_auto_apply 1 줄이 자연 추가 가능. L62 의 graphify_profile 뒤가 적절한 위치.

5. **render_systemd_units.py 변경 0**: L352 `tpl_dir.glob("*.template")` 가 신규 2 template 자동 발견. L48 `_PER_VAULT_PATTERN` regex (`@\.`) 매치 안 함 → singleton 처리. L211/214/222/227 의 placeholder substitution 4 key 모두 이미 등록.

6. **install.sh systemd 3 위치 (stop/start/try-restart)**:
   - L1602: `systemctl --user stop wikihub-monitor.timer` 옆에 `wikihub-lint-apply.timer` 추가.
   - L1621: `'wikihub-monitor.service' 'wikihub-monitor.timer'` 옆에 `'wikihub-lint-apply.service' 'wikihub-lint-apply.timer'` 추가.
   - L1656: `systemctl --user start wikihub-monitor.timer ...` 옆에 `wikihub-lint-apply.timer` 추가.
   - L1702: `try-restart` 의 list 에 `wikihub-lint-apply.timer` 추가.

7. **OnCalendar 03:00 KST**: wikihub-monitor.timer 의 `*-*-* 09,21:00:00 Asia/Seoul` (L8) 와 충돌 없음. 03:00 fire 가 09:00 / 21:00 monitor 와 분리. Persistent=true 패턴 정합.

8. **SuccessExitStatus=0 75**: lint.service.template L19, wikihub-monitor.service.template L21 모두 `0 75` — design §2.3.1 정합.

9. **ADR-0036 §"timeout wrapper" 의 v0.2.x deferred 해소**: graphify.md L156 의 "yaml expose 는 v0.2.x deferred" 코멘트가 본 feature 의 결정 D4 로 해소. design §2.7 의 "ADR-0036 §"후속 영향" 1 줄 cross-link" 정합. 단 ADR-0036 의 §재검토 트리거 도 함께 1줄 추가 ("v0.1.8 lint_operations_improvements 에서 D4 해소") 권고.

10. **ADR 신설 안 함 결정**: D3 (--apply 자동화) 는 wikihub 데이터 모델 (wiki/ 는 sources 의 LLM derivative — 원본 변경 0) 의 직접 도출, wikihub_monitor 의 D1 정정 패턴 정합. D2 (lowercase + entity 우선) 도 spec 본문 충분. ADR 미생성 합리적.

11. **race / 동시성 (lint.timer + wikihub-lint-apply.timer)**: design §2.8 의 2.8% 추정 + backlog BL-N8 등록 정합. 실 운영 영향 낮음.

12. **wikihub 의미론 정합**: case-variant normalize 는 entity 또는 concept 각 카테고리 안에서. cross-category 는 entity 우선 merge — "entity 가 더 구체적 의미 (실체 대상) 보존" 가 wiki-schema.md ADR-0001 의 카테고리 의미 (entities = 실체, concepts = 추상 개념) 정합.

---

## 범위 외 (별도 feature 또는 backlog)

1. **graphify CLI 의 `--api-timeout` (default 600s) yaml expose** — wrapper 와 별도. M1 참조.
2. **lint.timer + wikihub-lint-apply.timer race 가드 (file lock)** — design BL-N8 등록 정합.
3. **wikihub_monitor 가 lint-apply 결과 surface** — design BL-N7 등록 정합.
4. **case normalization 의 알고리즘 — 한국어/한자 entity 이름의 lowercase 의미** — 한국어 이름은 case 무관 (lowercase 동등), 한자/Latin alphabet 이름만 의미 있음. 운영 데이터 surface 후 별도 결정.

---

## 결론 및 다음 단계 권고

1. **H1 closure 필수 (design §1.2 + §2.1.3 본문 정정)** — Step 3 구현자가 grep 으로 변경 위치 찾기 위한 필수 조건.
2. **M3 권고 (OnFailure=ops-alert.service 추가)** — wikihub-monitor 패턴 정합, 1 줄 추가만으로 가능.
3. **M4 권고 (cross-category merge 알고리즘 명시)** — Step 3 LLM merge 구현 시 set-union + grep 치환 알고리즘 명확.
4. **M2 / M5 / L1~L4 는 Step 3 implementation 또는 follow-up backlog 흡수 가능.**
5. **Step 3 진입 권고** — H1 본문 정정 후 자동 진행. design 의 핵심 결정 (D1~D5) 은 모두 정합 통과.

---

## 검토 자료원

- `_system/commands/lint.md` (L1~230, 실제 read)
- `_system/commands/graphify.md` (L1~238, 실제 read — L112/120/126/132/138/144 의 timeout 720 6 위치 confirm)
- `_system/systemd/lint.service.template` (L1~25)
- `_system/systemd/lint.timer.template` (L1~20)
- `_system/systemd/wikihub-monitor.service.template` (L1~26)
- `_system/systemd/wikihub-monitor.timer.template` (L1~16)
- `docs/adr/0036-graphify-cli-integration.md` (L1~311, §D2 + §Note 2026-05-20 + §Note 2026-05-24)
- `scripts/lib/config.py` (L40-170, OperationsConfig + _parse_operations)
- `install.sh` (L766-925, _migrate_agent_schema + writer; L1580-1705, systemd stop/start/try-restart)
- `scripts/_helpers/render_systemd_units.py` (L195-285, _instance_wide_subs + render; L340-441, _do_render + stale cleanup)
- `wikihub.yaml.example` (L30-77, operations + agent)
- `_system/wiki-schema.md` (L30/89/123/193/221/281/285, referenced_by + .archived semantics)
- `features/20260525_lint_operations_improvements/analysis_and_design.md` (v1, L1-330)
- `features/20260525_lint_operations_improvements/plan.md` (L1-150)
- `features/backlog.md` (구조 확인)
