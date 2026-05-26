# Plan — monitor_services_remove

**Date:** 2026-05-26
**Feat ID:** monitor_services_remove
**Author:** maintainer + Claude

---

## 작업 분류

기능 (deletion). `wikihub-monitor` (12hr 운영 보고서) + `wikihub-pending-monitor` (pending age 모니터) 두 systemd 서비스와 부속 plumbing 제거.

## 타겟 버전 브랜치

`v0.1.9` — 현재 작업 중인 `feature/v018-fix` 브랜치가 squash 시점에 push 하는 정본 버전 브랜치. v0.1.9 bump 는 이미 commit `eb93253` 에 반영 — 본 feature 는 같은 release window 흡수 (별도 bump 없음).

## 적용 단계

| Step | 수행 여부 | 사유 |
|---|---|---|
| Step 1 (Plan) | ✅ | 본 문서 |
| Step 2 (Analysis & Design) | ✅ | 다중 파일 + ADR-0037 Status 변경 (architectural) → 통합 설계서 필요 |
| Step 3 (Implementation) | ✅ | feature/v018-fix 누적 commit 으로 진행 |
| Step 4 (Code Review) | ✅ | 변경 크기 50줄 초과 + ADR/env 의미 변경 → 멀티모델 리뷰 필수 |
| Step 5 (Deploy) | ✅ | `_system/` + `install.sh` 둘 다 변경 — 운영 영향 있음. v0.1.9 release window 흡수. |

## 예상 영향 범위

**삭제 대상:**
- `_system/systemd/wikihub-monitor.service.template`
- `_system/systemd/wikihub-monitor.timer.template`
- `_system/systemd/wikihub-pending-monitor.service.template`
- `_system/systemd/wikihub-pending-monitor.timer.template`
- `scripts/wikihub_monitor.py`
- `scripts/pending_monitor.py`

**수정 대상:**
- `install.sh` — stop/start/render/banner 8곳 (`grep -n` 결과 1282, 1614-1617, 1636-1637, 1671-1673, 1719)
- `_system/commands/setup.md:153,305` — enable list / ADR-0008 참조
- `_system/commands/lint.md:172,222` — wikihub_monitor 보고서 / D1 정정 언급
- `_system/commands/graphify.md:14` — wikihub_monitor D1 정정 언급
- `scripts/lib/telegram.py` — 호출자 ops-alert.py 단독 → inline 회수 or 유지 (Step 2 결정)
- `TELEGRAM_MONITOR_*` env key — ops-alert 단독 사용으로 환원 (Step 2 결정: 의미 정정 vs 운영자 마이그레이션 부담 회피)

**ADR:**
- `docs/adr/0037-alert-pipeline-architecture.md` — Status `Accepted` → `Superseded` (§D2 + v0.1.8 follow-up wikihub_monitor 결정 폐기). §D1 (Telegram channel for ops-alert) 부분은 보존.
- 신규 ADR-0038 (가칭): "wikihub-monitor / wikihub-pending-monitor 폐기 — Karpathy §2 Simplicity 정합". Supersedes ADR-0037 §D2 + 2026-05-25 wikihub_monitor 추가 결정.
- `docs/adr/0024-fatal-alert-contract.md:210` — pending-monitor 언급은 historical 로 유지 (touch 안 함).
- `docs/adr/0036-graphify-cli-integration.md:129` — wikihub_monitor D1 정정 언급은 historical 정신 인용 → 그대로 유지.

## 작업 시퀀싱 (Step 3 내부)

사용자 결정: 삭제 → rename 결함 재검토 순.

1. **Phase A — Service deletion**: 6 삭제 + 1 ADR 신설 + ADR-0037 supersede + install.sh / commands 정정.
2. **Phase B — Rename defect re-check**: Phase A 후 잔존 stale 참조 재조사 (GLM/Mimo 가 지적한 6건 중 2건은 `wikihub_monitor.py` / `pending_monitor.py` 통째 삭제로 자동 해소). 나머지 4건 (`setup.md`, `lint.md`, `graphify.md` rename 흔적 + `render_systemd_units.py:336-337` dead pass) 은 Phase A 가 같은 파일을 touch 하므로 같은 commit 흡수 검토.

> Phase B 가 Phase A 와 같은 파일을 touch 한다는 점이 Karpathy §3 Surgical Changes 와 충돌처럼 보이나, 두 변경의 **목적이 다르다** (deletion vs rename consistency) — analysis_and_design.md 에서 명시 분리. 같은 commit / 다른 commit 결정은 Step 2 에서.

## 메소드론 적용 여부

적용 (생략 조건 미충족 — 50줄 초과 + 외부 인터페이스 영향 + ADR 결정 변경).

## Open Question (Step 2 에서 결정)

1. **`scripts/lib/telegram.py` 처리**: ops-alert 단독 호출자 → (a) lib 그대로 유지 (수정 0줄), (b) ops-alert.py 로 inline 회수 (Karpathy §2 Simplicity 정합, ~50줄 이동).
2. **`TELEGRAM_MONITOR_*` env key rename**: (a) 그대로 유지 (운영자 ~/.config/wikihub/env 무수정), (b) `TELEGRAM_ALERT_*` 로 재변경 (의미 정확성 — fatal alert 단독).
3. **신규 ADR-0038 vs ADR-0037 §Note 만 추가**: §D1 보존 + §D2/follow-up 폐기를 ADR-0037 한 파일에서 in-place 갱신 (Status 는 그대로 Accepted 유지, §D2 만 Superseded 표기) — convention 위반. **신규 ADR-0038 신설 + ADR-0037 전체 Superseded** 가 정공법 — Step 2 에서 컨벤션 정합 검토 후 확정.

## DoD (Definition of Done — preliminary)

- [ ] 6 파일 삭제 완료 (template 4 + script 2)
- [ ] `install.sh` 의 monitor 참조 0건 (grep verify)
- [ ] `_system/commands/*.md` 의 monitor 참조 0건 (grep verify)
- [ ] ADR-0037 Status 정정 + 신규 ADR (가칭 0038) Accepted
- [ ] `render_systemd_units.py` dry-run — 잔존 unit (ingest / lint / graphify / mount / ops-alert) 만 출력
- [ ] pytest pass (변경 없음 또는 신규 fixture)
- [ ] Phase B rename defect 4건 정리 (또는 별도 micro-feature 분기 결정)
- [ ] 멀티모델 리뷰 ≥ 2건 (Step 4)
