# Design Review 2 — lint_operations_improvements (운영 안전성 + LLM 동작 + 의미론)

리뷰 시점: 2026-05-25 (KST)
검토 대상: analysis_and_design.md v1 (approved) + plan.md
리뷰어 perspective: 운영 안전성 + LLM 동작 의미론 (case normalize / cross-category merge / --apply 자동화 cycle / graphify timeout / race)
참조 코드 (검증): `_system/commands/lint.md`, `_system/commands/graphify.md`, `_system/wiki-schema.md` §[[link]] 규약, `scripts/lib/config.py`, `_system/systemd/lint.{service,timer}.template`, `_system/systemd/wikihub-monitor.{service,timer}.template`, `scripts/_helpers/render_systemd_units.py`, `install.sh` `_migrate_agent_schema` + `_systemd_{stop_before,start_after}_update`, `_system/commands/setup.md`, `docs/adr/0001-source-collision-policy.md`

---

## 종합 평가

**조건부 통과** — 핵심 yaml expose + systemd timer 신설 부분의 설계는 기존 패턴 정합. 다만 의미론 layer 에서 **C 급 결함 2건** (link reference 패턴 가정 오류, case normalize 의 product noun 손상) + **H 급 결함 2건** (wiki-schema disambiguator 규약 충돌, wikihub-lint-apply.timer enable 누락) 발견. C 결함은 Step 3 진입 전 design 보강 필수. H 는 구현 시점 가드 명시 필요.

전체 의도 (3 운영 issue 통합) + 패턴 정합 (yaml expose + wikihub-monitor 신설 패턴 답습) 은 견고. 단 design.md §2.2 의 case-variant + cross-category 처리가 wikihub 의 link 규약 / 카테고리 prefix 보류 정책 / filesystem 동작과 정합성이 미흡.

---

## C (Critical) — 구조적 의미 손상, 구현 진입 전 재설계 필수

### C1. `[[entities/<name>]]` link reference 갱신 가정이 wikihub link 규약과 불일치

**위치**: analysis_and_design.md:130, 141, 146

**문제**: design.md 가 `[[entities/Claude-Code]]` → `[[entities/claude-code]]` link 갱신을 명시. 그러나 `_system/wiki-schema.md:253-263` (ADR-0001 link 규약) 가 정의하는 link 형식은:

| 카테고리 | 형식 |
|---|---|
| `entities/<name>` | `[[<name>]]` (단축형 — 카테고리 prefix 없음) |
| `concepts/<name>` | `[[<name>]]` (단축형) |
| `analyses/<slug>` | `[[<slug>]]` |

즉 entity/concept link 는 **`[[Claude-Code]]` 만 존재**, design.md 의 `[[entities/Claude-Code]]` 패턴은 wiki 본문에 거의 없을 가능성. 실제 lint.md:153 의 예시도 `[[OKR]]`, `[[gdrive/policies/promotion]]` 단축형/vault-prefix만 — 카테고리 prefix 형식 부재.

**파급**:
- design.md 의 case-variant rename + link 갱신 Step 7 작업이 실제 wiki 의 link 0개 갱신 (no-op) — 단 파일명만 `Claude-Code.md` → `claude-code.md` 변환되어 단축형 `[[Claude-Code]]` 가 dangling (referenced filename 변경됨, link text 미갱신).
- cross-category merge (`[[concepts/<name>]]` → `[[entities/<name>]]`) 도 동일 문제 — 본문의 `[[Docker]]` 는 카테고리 ambiguous 상태로 남음 (entity Docker 가 존재하고 concept Docker 가 archived 되면 link resolution 은 entity 로 자연 fallback 가능, 단 wiki-schema 가 resolver 명시 안 함).

**권고**:
- design.md §2.2.1 + §2.2.2 의 link 갱신 패턴을 **단축형 `[[<name>]]` 기준** 으로 재작성:
  - case-variant rename: 파일명 lowercase + 본문 link `[[Claude-Code]]` → `[[claude-code]]` (wikihub link 가 case-sensitive 가정 — wiki-schema 명시 없음, ADR-0001 정합 확인 필요 — 만약 link resolver 가 case-insensitive 매칭이면 link 갱신 자체가 불필요).
  - cross-category merge: 단축형 `[[Docker]]` 는 entity Docker 가 정본이 되므로 link 갱신 자체 불필요 (filename 보존). archive 만 진행.
- wiki-schema §[[link]] 규약 의 case-sensitivity 정책을 먼저 정의 (별도 1 줄 spec 보강). 본 feature 의 case normalize 가 link resolver 동작에 의존.

### C2. case lowercase 강제가 product noun / 의도된 PascalCase 손상 위험

**위치**: analysis_and_design.md:127 (Q2-b: 모두 lowercase) + plan.md:127

**문제**: design.md 가 `--apply` 시 모든 entity/concept 페이지 이름을 lowercase 강제. 그러나:
- product 이름은 의도된 case 보유: "GitHub", "WikiHub", "MiniMax", "DeepSeek", "OpenCode", "Hermes", "OCI" 등 — 운영자가 PascalCase / CamelCase 의도로 작성.
- lowercase 강제 시 `GitHub` → `github`, `MiniMax` → `minimax`. 사용자 또는 source 본문이 본래 이름으로 언급 시 LLM stub 재생성 cycle 마다 case 가 다시 등장 → lint 가 매번 `Claude-Code` ↔ `claude-code` duplicate 보고 → `--apply` rename 무한 loop 가능 (LLM 이 `Claude-Code` 형식으로 stub 재생성 → 다음 cycle case-variant 다시 등장).
- 한국어 entity 는 case 무관 (`홍길동`, `김철수`) — 영문/한글 혼재 wiki 에서 lowercase 정책이 한쪽만 영향.

**대안**:
1. **kebab-case + 영문 첫 글자만 lowercase**: `Claude-Code` 와 `claude-code` 만 normalize (case-variant 만), product noun PascalCase 는 첫 등장 form 보존. 단 case-variant 만 충돌일 때 (lowercase 형이 minority) majority 형 채택.
2. **alias frontmatter 도입**: `aliases: [Claude-Code, claude-code]` 명시 — lint 가 case-variant 감지 시 alias 통합, 파일명 변경 X. 정보 손실 0 + link 갱신 0 + lint 멱등.
3. **사용자 현재 default 유지 + LLM stub 생성 step (lint.md Step 3) 보강**: LLM prompt 에 "기존 페이지 case 우선, 신규 생성 시 lowercase 첫 글자" 정책 주입 → 재현 case-variant 감소.

**권고**: design.md 가 D2 default lowercase 채택 근거 ("URL-friendly, filesystem stable, 운영자 멘탈 부담 낮음") 가 wikihub 가 URL 노출이 아니라는 점 + filesystem (OCI Linux, ext4) 이 case-sensitive 라는 점에서 약함. **alias frontmatter 도입 (대안 2)** 이 정보 손실 0 + LLM 재생성 cycle 안정. design.md §2.2 를 alias 패턴으로 보강 권고. 만약 사용자 D2 default 유지 의지면, 최소 (3) LLM stub prompt 보강 + lint cycle 멱등성 보장 mechanism 필수.

---

## H (High) — 운영 안전성 / 정합 결함, 구현 시 가드 추가 필수

### H1. wiki-schema §"entities/concepts 동명 충돌 정책" 의 disambiguator 규약과 cross-category merge 정책 충돌

**위치**: analysis_and_design.md:131 + wiki-schema.md:265-270

**현행 wiki-schema 규약** (line 265-269):
> entities/concepts 동명 충돌 정책 (현 v0.1.0):
> - 동일 카테고리에 동명이 발생할 경우 `<name> (disambiguator).md` 형식으로 disambiguator 추가
> - 예: `entities/홍길동 (전략기획팀).md`, `entities/홍길동 (재무팀).md`
> - **카테고리 prefix (`[[entities/홍길동]]`) 의무화는 보류** — 단순성 우선

design.md 의 cross-category 정책 ("entity 우선 merge") 은 wiki-schema 의 **동일 카테고리 안의 동명 정책 (disambiguator 도입)** 과 다른 layer. 그러나 wiki-schema 는 cross-category (entity ↔ concept 동명) 정책을 명시 안 함. 즉:

- 현행 wiki-schema 는 `entities/Docker` + `concepts/Docker` 공존을 **허용 가능 상태로 방치** (link `[[Docker]]` 의 resolver 정책 미정).
- design.md 가 cross-category merge 를 일률 entity 우선으로 강제하면 wiki-schema 미정 영역에 정책 도입 — **wiki-schema.md spec 갱신이 design.md scope 에 누락**.

**파급**:
- 일부 cross-category 동명은 **의미론적으로 별도 entity 와 concept** 가 정당 — 예: `entities/Docker` (회사 = Docker, Inc.) vs `concepts/Docker` (컨테이너 기술 개념). 양쪽 의미 보존 가치.
- design.md 의 "entity 가 더 구체적 의미 보존" 가정 (plan.md:128) 이 보편적이지 않음 — `entities/React` (라이브러리 = entity) vs `concepts/React` (UI 패러다임 = concept) 같은 경우 양쪽 의미 분리 가치.

**권고**:
- design.md §2.2 에 wiki-schema.md cross-category 정책 1 단락 갱신 명시 (Step 3 file list 에 wiki-schema.md 추가).
- cross-category merge 시 **LLM 의미 분리 가능성 판단 step 추가**: concept 와 entity 의 본문이 의미적으로 동일 (concept 가 entity 의 1줄 stub) 인 경우만 merge, 의미 분리되면 disambiguator 도입 (`entities/Docker (회사).md` + `concepts/Docker (개념).md` 또는 entity/concept 한쪽에 alias).
- alternative: **운영자 정책 toggle**: `operations.lint_cross_category_policy: merge_to_entity | disambiguate | report_only`. default `report_only` (보수적) — `--apply` 가 자동 merge 하지 않고 운영자가 정책 명시. design.md 의 D2 default (auto-merge) 정합 검토 필요.

### H2. wikihub-lint-apply.timer 의 enable 책임 누락 — install.sh / setup.md 둘 다 명시 부재

**위치**: analysis_and_design.md §2.5 + setup.md:153, install.sh _systemd_{stop,start}

**현행 enable 정책** (setup.md:153):
> `--enable` 플래그 시: `lint.timer` (+ 조건부 `disk-watch.timer`) **만** `enable --now`. **vault-ingest.timer 는 Step 6 결과에 위임**.

design.md §2.5 는 install.sh stop/start/try-restart 3 위치에 `wikihub-lint-apply` 추가만 명시. 그러나:
- **enable --now**: 신규 timer 가 `~/.config/systemd/user/` 에 render 되어도 `enable` 안 하면 timer fire 자체가 안 됨. setup.md `--enable` 가 명시적으로 enable 하지 않으면 운영자가 수동 enable 필요.
- wikihub-monitor.timer 도 동일 패턴 검토 — install.sh:1656 가 `start wikihub-monitor.timer` 만 호출 (enable 부재). 실증 운영에서 reboot 후 monitor.timer 가 fire 되는지 검증 필요. (단 systemd 가 user instance reboot 후 enable 된 timer 만 fire — `start` 만으로는 unit start 시점만 active.)

**파급**:
- design.md 가 lint-apply.timer 의 enable 책임을 install.sh OR setup.md 어디서 처리할지 미결.
- lint_auto_apply=false (default) 운영자가 opt-in 시 yaml 편집 + install.sh 재실행 만으로 timer fire 가 되어야 함 — 그러나 enable 누락이면 운영자가 추가로 `systemctl --user enable wikihub-lint-apply.timer` 호출 필요. 운영자 학습 곡선 미설계.

**권고**:
- design.md §2.5 install.sh `_systemd_start_after_update` 에 `enable wikihub-lint-apply.timer` 추가 (단 lint_auto_apply=false 면 enable 만 + start 안 함 — yaml 정합 분기).
- 또는 wikihub-monitor.timer 와 동일 패턴 (start 만, enable 책임 setup.md `--enable` 에 위임) 채택 + setup.md §"`--enable` 시 lint.timer + disk-watch.timer + wikihub-monitor.timer + wikihub-lint-apply.timer" 명시.
- DoD §5 에 setup.md spec 갱신 추가.

### H3. graphify_timeout_sec default 900 의 backend 별 적정성 — partial failure threshold 와 정합 부재

**위치**: analysis_and_design.md §2.1 + lint.md:194 (graphify_partial_failure_threshold)

**문제**:
- design.md 가 graphify timeout 720 → 900 (15분) 으로 일괄 인상. 그러나 backend 별 latency 차이:
  - Ollama local (gemma4:31b): wiki 100 페이지 ~ 5분, 500 페이지 ~ 30분
  - DeepSeek-v4-pro API: per-call 2-6s, wiki 100 페이지 + concurrency 4 ~ 1분
  - Claude Anthropic API: per-call ~5s, ~3분
  - 즉 900 default 가 ollama backend 의 wiki 200+ 페이지 시점에 부족, 그 외 backend 에 과도.
- `--max-concurrency` 휴리스틱 (graphify.md:82-94) 이 endpoint pattern 으로 backend 추정 — local 일 때 1 (느림), cloud 일 때 4 (빠름). timeout 도 동일 패턴 분기 가치.

**파급**:
- ollama backend 운영자가 wiki 누적 시 timeout 빈도 증가 → ADR-0036 §"partial failure 의심: N/M < 0.5" gate 가 false positive 증가 (timeout 중 partial write 되면 graph.json 노드 수 적음 → partial failure 의심 alert 발화 빈도 증가).
- design.md 의 §2.1.4 가 "운영자 실측 surface 시 별도 feature" 로 deferred — 단 본 feature 가 900 default 채택 후 ollama 운영자의 timeout 빈도 surface 가 새 운영 부담.

**권고**:
- design.md 가 backend profile 별 timeout 까지는 가지 않더라도, **wiki 페이지 수 기준 timeout 자동 ranging** 1 줄 spec 명시:
  ```bash
  page_count=$(find "$WIKIHUB_HOME/wiki" -name "*.md" | wc -l)
  # ollama backend + page_count > 200 시 default 900 부족 가능 — yaml override 권고 stderr 경고
  ```
- 또는 lint.md Step 9 의 graph rebuild timeout 보고 시 `graph rebuild timeout (N pages, backend=<X>, threshold=<T>s) — yaml operations.graphify_timeout_sec 조정 권장` 운영자 surface 강화.

### H4. wikihub-lint-apply.service 의 graphify chain 자동 호출이 daily API/cost burden 증가

**위치**: analysis_and_design.md §2.3 + lint.md Step 9

**문제**:
- lint.md Step 9 가 `/wh-graphify` 자동 호출 (lint cycle 마지막). 즉 `wikihub-lint-apply.service` (매일 03:00 KST fire) 가 Step 1~9 전체 진행 → graphify chain 1회 추가 호출.
- 현행 lint.timer (3h 주기) = 1일 8회 graphify chain 호출. lint-apply.timer 추가로 +1회 (총 9회/일). cost 증가는 +12.5%.
- ollama local 은 cost 0 (electricity only). 그러나 cloud backend (OpenAI/Anthropic/DeepSeek) 운영자에게 API token 사용량 증가.

**파급**:
- design.md 가 lint_auto_apply=false default 라 opt-in 만 영향. 단 opt-in 운영자가 cost 부담 surface 미명시.

**권고**:
- design.md §2.3 에 1 줄 추가: "lint_auto_apply=true 활성화 시 daily graphify chain +1회 (cost +12.5%). cloud backend 운영자는 token 사용량 monitoring 권고."
- 또는 lint-apply.service 가 `/wh-lint --apply --skip-graphify` 형태로 호출 — design.md scope 외 이지만 cost 보호 가치. lint.md 가 `--skip-graphify` 플래그 미지원 시 신설 필요.

---

## M (Medium) — 운영 명확성 / spec 표현 / 검증 가능성

### M1. lint_auto_apply gate 의 위치 명시 불명확 — service 안 vs lint.md Step 7 안

**위치**: analysis_and_design.md §2.3.1 + §2.3.3

**문제**: design.md 가 두 곳에 gate 를 동시 명시:
- §2.3.1 service template comment: "yaml `operations.lint_auto_apply` toggle 은 wh-lint 스킬 본체가 확인 (lint.md Step 7 진입 직전 gate)"
- §2.3.3 lint.md Step 7 본문: gate bash 스크립트 명시

즉 gate 는 `wh-lint` 스킬 본체 안 (lint.md Step 7 진입 직전) 에서 동작. 그러나 lint-apply.service 가 `<agent_invocation_for_wh_lint> "/wh-lint --apply"` 호출 — agent 진입 → LLM 이 lint.md spec 읽고 진행 → Step 7 진입 직전 yq 호출 → false 면 exit 0. **즉 매일 03:00 에 agent 호출 + LLM 호출 + yq 1회 만 일어남 (lint 본체 진행 안 됨)** — overhead 작지만 0 아님 (agent 시작 + LLM 응답).

**권고**:
- gate 를 systemd unit level 에 두면 더 lean — `ExecStartPre=/bin/bash -c 'test "$(yq ...)" = "true" || exit 0'`. service 가 `SuccessExitStatus=0 75` 라 gate fail 시 자동 exit 0.
- 또는 design.md 가 현재 패턴 유지 시, lint.md Step 7 의 gate 가 "--apply 자동 호출 (lint-apply.service) 일 때만 yaml 확인" 인지 "수동 호출 포함" 인지 더 명시. design.md §2.3.3 가 "수동 호출 (`/wh-lint --apply`) 은 lint_auto_apply 무관" 명시했지만 LLM 이 그 분기를 어떻게 식별? agent 호출 args 차별 없으면 수동/자동 구분 불가능 — service 에 환경변수 (`WIKIHUB_LINT_AUTO=1`) 명시 후 lint.md gate 가 그 변수 + yaml 동시 확인 필요.

### M2. race window 2.8% 산정 근거 부족 — lint.service 평균 duration 가정 명시 없음

**위치**: analysis_and_design.md §2.8

**문제**: design.md 가 "03:00 fire 가 lint.timer 와 정확히 겹칠 확률 ≪ 5분 ÷ 180분 = 2.8%" 명시. 단:
- 5분 = lint-apply.timer 의 AccuracySec.
- 180분 = lint.timer 주기 (3h).
- 그러나 race window 의 실제 정합은 **두 service 의 활성 중첩 시간** = max(lint duration, lint-apply duration). lint duration 이 5분 ~ 30분 (LLM 호출 + graphify chain) 가변.
- 즉 race window 실제 = (lint.timer 의 3h 주기 안에서 lint-apply 가 lint 활성 시간에 fire 할 확률) = lint duration / 180min = 5~30/180 = 2.8% ~ 17%.

design.md 의 2.8% 는 lint duration ~ 5분 가정 — 실증 wiki 100+ 페이지 + graphify ollama backend 시점에 30분 가능 → 17% race risk.

**파급**:
- design.md 가 race 가드 (lock) 를 backlog (BL-N8) 로 deferred. race 발생 시 wiki/ 동시 변경 = 비결정적 결과. 17% 빈도 (월 5회) 는 deferred 가치 의심.

**권고**:
- design.md §2.8 의 race 산정을 lint duration 변수 반영하여 재산정. 또는 본 feature 에서 lint.md Step 0 (entry 시점) 에 `flock` 1 줄 추가 (Step 3 작업 1 줄 — backlog 보다 cheap).
- 권장 lock 패턴:
  ```bash
  exec 200>"$WIKIHUB_HOME/.wh-lint.lock"
  flock -n 200 || { echo "lint 이미 진행 중 — exit 0"; exit 0; }
  ```

### M3. lint.md Step 7 의 `--apply` 일괄 실행 정책 + Step 4.5 cross-category LLM merge 의 idempotency 미명시

**위치**: analysis_and_design.md §2.2.2 + lint.md Step 7

**문제**: design.md 가 cross-category merge 시 "concept 페이지의 본문 + referenced_by 를 entity 페이지에 LLM merge" 명시. 그러나:
- LLM merge 결과가 cycle 마다 동일한지 (idempotent) 미검증. design.md 가 LLM merge 의 cost / 일관성 surface 없음.
- 2회차 `--apply` 호출 시 concept 페이지가 이미 archive 되어 cross-category duplicate 가 사라짐 → no-op. 그러나 LLM 이 entity 본문 자체를 재정렬할지 보장 없음.

**파급**:
- daily auto-apply (lint_auto_apply=true) 시 entity 본문이 LLM merge 의 non-determinism 으로 매일 미세 drift 가능 → git history churn.

**권고**:
- design.md 가 Step 4.5 의 LLM merge 를 **"concept 이 이미 archive 되었거나 cross-category duplicate 가 sole match 아닌 경우 skip"** idempotency gate 명시.
- 또는 LLM merge 후 entity 본문 hash 보존 — 본문 변경이 cross-category merge 외 사유면 skip.

### M4. design.md `_lint/report.md` 의 Duplicates 섹션이 "auto-normalize 가능" 표현 — 운영자 의도와 다른 정규화 신호 부재

**위치**: analysis_and_design.md §2.2.3

**문제**: 보고서 표현 "Duplicates (case-variant) — auto-normalize 가능" 은 `--apply` 시 자동 처리 명시. 그러나 운영자가 `Claude-Code` 와 `claude-code` 둘 다 의도적 보유 (서로 다른 의미) 케이스 surface 안 됨.

**권고**:
- 보고서 항목에 LLM 의미 비교 결과 1 줄 추가: "본문 cosine similarity = 0.95 (동일 의미 가능성 높음)" 또는 "본문 첫 100자 비교: A=..., B=..." — 운영자 검토 가능성 surface.
- design.md §2.2.3 에 보고서 형식 보강.

### M5. install.sh `_migrate_agent_schema` Group B 추가 시 info log 표현 일관성

**위치**: analysis_and_design.md §2.5 + install.sh:846-860

**문제**: design.md 가 `B_graphify_timeout_sec` + `B_lint_auto_apply` flag 추가. install.sh 기존 패턴 (line 846-860) 의 info 메시지 형식:
```
info "  - [v0.1.5] operations.lint_contradiction_check 부재 → true 추가"
info "  - [v0.1.8] operations.monitor_enabled 부재 → true 추가"
```

본 feature 의 메시지 형식이 design.md 에 미명시. 권고 형식:
```
info "  - [v0.1.8] operations.graphify_timeout_sec 부재 → 900 추가 (graphify wrapper, D4)"
info "  - [v0.1.8] operations.lint_auto_apply 부재 → false 추가 (default opt-in)"
```

design.md DoD 또는 Step 3 가이드에 1 줄 명시 권고.

---

## L (Low) — 표현 정정 / 부차

### L1. graphify.md:156 코멘트 정정 시 line 6 위치 모두 동기 변경 필요

design.md §2.1.2 가 코멘트 1 위치 정정만 명시. 단 graphify.md:156 의 코멘트가 line 112-144 의 6 위치 timeout wrapper 위치를 묶어서 설명 — 코멘트 위치 1 곳만 갱신해도 6 위치 timeout 변환은 별도 작업. design.md DoD 가 두 변경을 분리 명시 권고.

### L2. design.md ADR 영향 (ADR-0036 §"후속 영향") 갱신 책임 + 양식

design.md §2.7 가 ADR-0036 cross-link 1 줄 추가 명시. 단 ADR template 이 "후속 영향" 섹션이 별도 ADR 가리킬 때 `→ features/<feature_id>` 또는 1 줄 인용 어느 패턴? 기존 ADR-0036 의 다른 후속 영향 cross-link 패턴과 정합 확인 필요. design.md DoD 에 ADR 갱신 예시 1 줄 명시 권고.

### L3. 03:00 KST 가 lint.timer fire 와 정확 충돌 가능 — AccuracySec 조정

lint.timer 의 OnUnitInactiveSec = 3h + AccuracySec=15min. 즉 lint 가 fire 한 시점 기준 ±15min 변동. 만약 lint 가 00:00 fire → 다음 fire 가 03:00 ± 15min → lint-apply.timer 의 03:00 ± 5min 와 5-15분 중첩 가능. design.md §2.8 가 systemd 가 같은 service 차단 명시했지만 두 service 가 다른 unit 이라 동시 활성 → wiki/ race. M2 권고 (flock) 가 가드.

### L4. plan.md D3 결정의 근거 "wiki/ 는 sources (vault, immutable) 의 LLM derivative" 가 contradiction reword 정책에는 정합하지만 cross-category merge 에는 불정합

plan.md:123 의 D3 결정 근거가 "contradiction reword 도 LLM 이 자기 생성 페이지 자기 갱신, 원본 변경 0" — entity/concept stub 갱신 + sources 의 referenced_by 추가는 정합. 그러나 cross-category merge 는 concept 페이지 archive + link 갱신 — sources 의 link reference 도 갱신 대상 (단축형 `[[Docker]]` 가 카테고리 ambiguous 라 source 본문 link 변경 가능). 즉 D3 가 가정한 "원본 변경 0" 이 보장되지 않음.

design.md 가 D3 근거 재확인 + cross-category merge 시 source 본문 link 변경 가능성 명시 권고.

### L5. 본 feature 의 backlog 진입 BL-N7 (monitor 가 lint-apply 결과 surface) — 첫 운영 cycle 의 운영자 인지 부담

design.md §2.6 가 monitor 의 lint-apply 결과 surface 를 backlog. 단 lint_auto_apply=true 활성화 첫 운영자가 daily wiki 변경을 어떻게 인지? journalctl + _lint/report.md 둘 다 운영자가 명시적으로 read 해야 함. 본 feature 의 첫 운영 cycle 에서 운영자 onboarding 1 줄 (예: install.sh _step10_print_next_steps 의 "lint_auto_apply=true 활성화 시 daily report 확인 권고" 안내) 명시 권고. design.md §4 Q-C 와 정합.

---

## 통과 관점 (재검토 가치 낮음 — 본 perspective 에서 우려 없음)

- **yaml expose 패턴**: `graphify_timeout_sec` + `lint_auto_apply` 의 OperationsConfig 추가 + `_parse_operations` + `_migrate_agent_schema` Group B 패턴은 기존 (monitor_enabled, pending_alert_age_sec 등) 패턴 답습. 정합.
- **systemd unit template 신설**: `wikihub-lint-apply.{service,timer}.template` 의 render_systemd_units.py glob 자동 발견 (line 352 `tpl_dir.glob("*.template")`) 정합. `wikihub-lint-apply` prefix 가 line 333 의 `name.startswith("wikihub-")` 조건 통과 → filename 그대로 출력 정합.
- **graphify timeout 720 → 900 변환** 자체 (yaml expose 격상): graphify.md 의 6 위치 hard-code 를 `timeout_sec` variable 로 대체. bash variable scope (Step 2 시작 부분 정의 → Step 2 안 6 위치 사용) 정합.
- **lint.md Step 9 표현 정정** (300 → 900): plan.md F1 진단 정합.
- **wikihub-lint-apply.timer Persistent=true + AccuracySec=5min**: wikihub-monitor.timer 패턴과 유사 + lint.timer 의 AccuracySec=15min 보다 빡빡. 03:00 KST 명시 정합.

---

## 범위 외 (본 feature 결정 아님, 별도 추적)

- **wh-ingest timeout 정책** (plan.md Q1-c): agent.timeout_sec=1200 유지. ingest 의 graphify-like sub-timeout 부재. 본 feature 결정 외 (D4 가 graphify 만 다룸). 별도 feature 필요 시점은 운영자 surface 후.
- **wiki link resolver 의 case-sensitivity 정책**: C1 에서 surface — wiki-schema 미정. 본 feature 가 link 갱신 책임 가지지만 resolver 동작 정의는 더 깊은 spec 작업 (wiki-schema spec 갱신 + ADR). 본 feature 가 spec 갱신 1 줄 추가 가능, full 정책은 별도 feature.
- **lint.md Step 0 의 flock guard** (M2 권고): backlog BL-N8 vs 본 feature 포함 결정. M2 권고는 본 feature 포함이 cheap 하지만, design.md 결정 (backlog) 도 정합 — 사용자 명시 시 변경.
- **wikihub-monitor 와 wikihub-pending-monitor 의 enable 일관성** (H2 검토 중 surface): install.sh 가 start 만 호출, enable 미명시. 본 feature 외 — 기존 패턴 surface.

---

## 결론

본 design v1 은 **C1 + C2 의 의미론 결함 + H1 + H2 의 spec 정합 결함** 으로 인해 Step 3 진입 전 1 회 보강 필요.

권고 보강 순서:
1. **C1 + H1**: wiki-schema link 규약 + cross-category 정책 spec 갱신 1 줄 추가 (design.md §2.2 + Step 3 file list 에 wiki-schema.md 포함). link reference 갱신 패턴을 단축형 `[[<name>]]` 기준 재작성.
2. **C2**: case lowercase default 의 product noun 손상 위험 surface — alias frontmatter 도입 검토 또는 lint.md Step 3 LLM prompt 보강.
3. **H2**: install.sh _systemd_start_after_update 또는 setup.md `--enable` 에 wikihub-lint-apply.timer enable 책임 명시.
4. **H3 + H4**: graphify timeout backend profile 별 조정 + lint-apply 의 graphify chain cost 1 줄 surface.
5. **M2**: race window 산정 정정 또는 flock 가드 본 feature 포함.

본 보강 후 v2 진입 → Step 3 자동 진행 가치.

---

리뷰어: 운영 안전성 + LLM 동작 의미론 perspective
보고 라인 수: 약 360 줄
