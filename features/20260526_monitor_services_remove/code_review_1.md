# Code Review 1 — monitor_services_remove (runtime correctness)

**Date:** 2026-05-26
**Reviewer:** Claude subagent (Sonnet)
**Branch:** feature/v018-fix
**Scope:** post-Step 3 diff for monitor_services_remove feature

---

## Assessment: Approved with notes

전반적으로 deletion이 깨끗하고 inline회수도 호출 측 의미를 보존했습니다. 운영 안전(upgrade migration)도 적절히 구성됐습니다. ADR cross-reference 일관성에서 historical leftovers 한두 건이 신경 쓰이지만 차단성 결함은 없습니다. Step 5 진행 전에 Low 항목들만 가볍게 정리하면 좋겠습니다.

---

## Issues Found

### 🟡 Medium 1 — `docs/adr/0032-hermes-skill-registration-policy.md`:248, 264, 299

ADR-0032 §Note 본문이 `operations.pending_alert_age_sec` 를 "v0.1.5+ 신설 field 의 대표 예시"로 인용 (L248의 "신설 field (...`operations.pending_alert_age_sec` 등)", L264의 "operations.pending_alert_age_sec: 3600", L299의 "ADR-0037 — `pending_alert_age_sec` (Group B 자료)"). 본 ADR-0040 이 이 field 를 제거했기 때문에 ADR-0032 본문이 더 이상 존재하지 않는 yaml field 를 운영 정본의 예시로 들고 있는 상태. 운영자가 ADR-0032 §Note 를 보고 yaml에 그 키를 추가하면 `_parse_operations` 가 그냥 무시(extra key)하므로 runtime crash는 없지만, ADR documentation source-of-truth 정합 위반.

ADR-0031 §"후속 영향" L312·L320 도 동일한 예시를 들지만 이건 historical event 의 진단 narrative (2026-05-22 OCI 사건) 이라 ADR-0032 보다는 영향 약함.

**제안 수정**: ADR-0032 L248·L264·L299 의 `operations.pending_alert_age_sec` 인용을 다른 살아있는 field (예: `operations.graphify_timeout_sec` 또는 `agent.timeout_sec`) 로 1-token 치환. ADR-0031 historical narrative 는 그대로 둬도 무방 (plan.md 가 ADR-0024 의 historical 언급을 유지하기로 한 정합).

설계서 §"연계 룰/스킬 정합성 검토" 표에 ADR-0032 / ADR-0031 row 가 없어 누락된 정합 항목. design feedback 으로 surface 권장.

---

### 🔵 Low 1 — `scripts/ops-alert.py`:185-213 (inline send_telegram 의 payload semantics)

원본 `lib/telegram.py` 의 `send_telegram` 은 `if parse_mode: payload["parse_mode"] = parse_mode` 로 `parse_mode` 키를 조건부 삽입. inline 후 새 함수는 항상 `"parse_mode": "HTML"` 을 payload 에 포함. **단일 호출자 (ops-alert.py) 가 항상 HTML 모드로 호출**하므로 wire-level 동일 — Telegram API 입장에서 `parse_mode: "HTML"` 명시 vs 그 키 명시 자체가 항상 들어가는 형태 차이만 존재. 운영 영향 없음.

다만 docstring (L191 `"HTML message 전송 (ADR-0040 §D1 carry-over of ADR-0037 §D1)"`) 이 HTML 고정임을 명시했고, 함수 signature 도 `parse_mode` 인자 제거 — 의미적 정합. 기각 의견: docstring 의 ADR 표기가 "ADR-0040 §D1" 인데 ADR-0040 본문에는 §D1 / §D2 형식 섹션 구조가 없고 `Considered Options (α/β/γ)` + `Carry-over from ADR-0037` 표 구조. ops-alert.py L257, L314 에도 동일하게 "ADR-0040 §D1" / "ADR-0040 §D1 (carry-over of ADR-0037 §D1)" 표기. 큰 문제는 아니나 ADR-0040 의 실제 섹션 구조와 일치시키려면 "ADR-0040 §Decision (carry-over of ADR-0037 §D1)" 또는 "ADR-0040 §Carry-over from ADR-0037 (ADR-0037 §D1)" 표기가 더 정확.

**제안 수정**: L191 docstring + L257 + L314 의 "ADR-0040 §D1" 3개 occurrence 를 ADR-0040 의 실제 섹션 명 (Carry-over from ADR-0037) 로 교정. 또는 ADR-0040 본문에 anchor §D1 추가. 어느 쪽이든 1-token edit.

---

### 🔵 Low 2 — `docs/adr/0040-monitor-services-remove.md`:89 (upgrade migration block 명세 부정확)

ADR-0040 §"후속 영향" L89: "install.sh upgrade migration block 추가 — 기존 v0.1.9 instance 의 `wikihub-monitor.timer` + `wikihub-pending-monitor.timer` 를 stop + disable (orphan 회피)."

실제 install.sh L1631-1633 은:
- stop: `.timer` + `.service` 양쪽 4 unit 모두 stop (정합)
- disable: `.timer` 2개만 disable (정합 — `.service` 는 `enable` 대상이 아님)

ADR-0040 의 문장이 ".timer" 만 언급 — service 단위 stop 도 함께 한다는 implementation detail 이 누락. operator 가 ADR-0040 만 읽으면 "어 service는 왜 안 멈춰?" 의문 가능. 실제 install.sh 동작은 더 thorough.

**제안 수정**: ADR-0040 L89 를 "...의 `wikihub-monitor.{service,timer}` + `wikihub-pending-monitor.{service,timer}` 를 stop + disable (timer 만 disable — `.service` 는 enable 대상 외)" 로 1줄 보강.

---

### 🔵 Low 3 — `install.sh`:1284 + L745 (선존 stale: `wikihub-ops-alert.service`)

본 branch 외 결함이지만 review 중 surface — install.sh L745 comment 와 L1284 banner 가 `wikihub-ops-alert.service` 를 가리키나 실제 unit 파일은 `ops-alert.service` (no prefix). 운영자가 banner 명령을 그대로 복붙하면 `Unit wikihub-ops-alert.service not loaded` 에러. blame 상 b4561c58 (2026-05-20) + 27966bc3 (2026-05-17) 로 본 branch 도입 아님. ADR-0024 fatal alert contract 의 unit 명명 일관성 별도 micro-feature 권장.

본 review 의 scope (monitor_services_remove) 외 — 별도 plan/feature 로 분리 권장.

---

## Verified Correct

- **삭제 7 파일 확정**: template 4 (`wikihub-monitor.{service,timer}.template`, `wikihub-pending-monitor.{service,timer}.template`) + script 2 (`scripts/wikihub_monitor.py`, `scripts/pending_monitor.py`) + lib 1 (`scripts/lib/telegram.py`) = `git status --short` 의 7 `D` 줄과 정확히 일치.
- **`lib.telegram` import 잔존 0**: `grep -rn 'from lib.telegram' --include='*.py'` 결과 archive 외 0건 — caller 가 완전히 inline 회수됨.
- **`parse_mode` semantics 보존**: 원본 `send_telegram(parse_mode="HTML")` 호출이 → inline 후 `parse_mode="HTML"` 고정 payload 와 동일. wire-level 동일 (Telegram API 입장에서 차이 0).
- **upgrade migration sequence 정합**: install.sh L1631-1633 의 stop → disable → daemon-reload (L1640) → render (L1704) → daemon-reload (L1709) 순서가 race-free. render 의 legacy_singletons (render_systemd_units.py L431-447) 가 stale unit file 6개를 cleanly unlink — disable + 파일 삭제 의 2단계 cleanup 정합.
- **render_systemd_units.py legacy cleanup 6 entry**: `wikihub-lint.{service,timer}` (v0.1.9 carry-over) + `wikihub-monitor.{service,timer}` + `wikihub-pending-monitor.{service,timer}` 모두 cleanup 대상. orphan unit file 회피.
- **dead `pass` 정리**: render_systemd_units.py L336-337 의 `if not name.startswith("wikihub-") and name not in ("ops-alert.service",): pass` no-op block 완전 제거 (Phase B). 함수 동작 동일 (dead branch 였음).
- **yaml + config 4 필드 제거 정합**: `wikihub.yaml.example` L46-49 4 줄 + `scripts/lib/config.py` L60-62, L167-169 `OperationsConfig` 4 field + `_parse_operations` 4 line 모두 삭제. **잔존 코드 0** — `grep -rn 'monitor_enabled\|pending_alert_age_sec\|monitor_report' scripts/` 결과 0.
- **TELEGRAM_MONITOR_* env key 보존**: ops-alert.py L258-259 가 그대로 읽음. install.sh L749-750 env template 도 그대로. operator `~/.config/wikihub/env` 무수정 보장 — 설계 결정 §1 정합.
- **ADR cross-reference chain**: ADR-0037 Status: Superseded + Superseded by: ADR-0040 / ADR-0040 Supersedes: ADR-0037 / ADR-0024 §Note 끝에 ADR-0040 reference 1줄 추가 / docs/adr/README.md index 의 ADR-0037 Status: Superseded + ADR-0040 entry 추가 — convention 4방향 모두 정합.
- **commands docs 정리**: setup.md (Step 4 enable list + Step 5 산출물 + ADR-0008 reference) + lint.md (Step 0/8/9 + wikihub_monitor reference + ADR-0009 reference) + graphify.md (호출 흐름 + 운영 흐름 + wikihub_monitor reference) — 모든 활성 monitor 언급 정리. 5개 위치 모두 grep 0.
- **`format_telegram_alert_message` 정확 inline**: 원본 L67-78 ↔ 새 L216-228 라인 단위 동일 (alert dict key access pattern, HTML escape policy, message structure 모두 보존).

---

## DoD Check (analysis_and_design.md §"Definition of Done")

- [x] **D1 Deletion**: 7 files removed — template 4 + script 2 + lib 1. `git status --short` 의 `D` 줄 7개로 confirm.
- [x] **D2 install.sh**: monitor / pending-monitor / pending_monitor / wikihub_monitor 활성 참조 0. banner L1283 (timer 상태 명령) 의 monitor 한 줄 제거 + stop L1612-1617 + start L1670-1673 + try-restart L1719 + reset-failed L1636-1637 5 위치 정합. **추가**: upgrade migration block L1630-1633 신규 추가 (설계서엔 명시 안 됐으나 ADR-0040 §"후속 영향" 에 반영).
- [x] **D3 yaml + config**: `pending_alert_age_sec` + `monitor_enabled` + `monitor_report_vault` + `monitor_report_subpath` 4 필드 모두 삭제 (설계서엔 2 필드라 적혔으나 실제 4 필드 = 정확 — analysis_and_design.md L38 의 "두 키" 표현이 부정확. ADR-0040 §"후속 영향" L74 에는 4 필드 정확 기재).
- [x] **D4 ops-alert.py inline**: `send_telegram` (~28 line) + `format_telegram_alert_message` (~13 line) 회수. `parse_mode` 인자 제거 + HTML 고정. import `from lib.telegram` 라인 삭제.
- [x] **D5 commands docs**: setup.md (4 위치) + lint.md (3 위치) + graphify.md (3 위치) 정리. lint Step 9 의 `wikihub_monitor D1 정정` precedent reference 정리 — 정확.
- [x] **D6 ADR**: ADR-0040 신설 (Accepted, Supersedes ADR-0037) + ADR-0037 Status: Superseded + ADR-0024 §Note 1줄 추가 + docs/adr/README.md index 갱신. **Note**: 신규 ADR-0040 의 docstring 의 §D1 / §D2 anchor 표기 (ops-alert.py L191·L257·L314) 가 ADR-0040 실제 섹션 구조와 미정합 — Low 1 참조.
- [x] **D7 Phase B 흡수**: `render_systemd_units.py:336-337` dead pass 정리. Phase A 와 같은 commit 흡수.
- [ ] **D8 Verify**: 본 review 가 grep 검증 = 활성 코드 monitor reference 0 confirm. 단 ADR-0032 / ADR-0031 의 historical example 잔존 — Medium 1 참조. `pytest` 실행은 본 review scope 외 (정적 분석만).
- [ ] **D9 Code Review**: 본 파일이 1개. 설계서가 "≥ 2개 멀티모델 리뷰" 요구 — 추가 리뷰어 (Gemini / Codex / 별도 Claude 컨텍스트) 필요.

---

## 종합

설계서의 7 deletion + 1 inline + ADR chain + upgrade migration 모두 정확히 구현됨. runtime-breaking bug 0건. Medium 1 (ADR-0032 historical example) 은 documentation consistency 결함이며 runtime 영향 0. Low 3개는 docstring 정합 / ADR 문구 보강 / 선존 결함 surface. **본 branch deploy 차단 없음** — Medium 1 은 cosmetic doc fix 로 micro-feature 분기 가능. 두 번째 리뷰어 (D9) 추가 후 Step 5 진행 권장.
