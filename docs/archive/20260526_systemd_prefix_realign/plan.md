# Plan — systemd_prefix_realign

**Date:** 2026-05-26
**Feat ID:** systemd_prefix_realign

---

## 작업 분류

리팩토링 (rename). systemd unit prefix 를 skill prefix 와 분리해 namespace 정합 회복.

- **systemd unit**: `wh-ingest@` / `wh-lint.*` → `wikihub-ingest@` / `wikihub-lint.*`
- **Hermes skill** (`wh-ingest`, `wh-lint`, `wh-query`, `wh-setup`): 변경 없음 (ADR-0033 lock 유지)

## 타겟 버전 브랜치

`v0.1.9` — 현재 작업 중인 `feature/v018-fix` 누적. v0.1.9 bump (eb93253) 이미 반영, 본 rename 도 같은 release window 흡수.

## 적용 단계

| Step | 수행 | 사유 |
|---|---|---|
| Step 1 (Plan) | ✅ | 본 문서 |
| Step 2 (Analysis & Design) | ✅ | 21 install.sh refs + 30 wiki-schema + 4 template rename + ADR 신설 → 통합 설계 필요 |
| Step 3 (Implementation) | ✅ | feature/v018-fix 누적 commit |
| Step 4 (Code Review) | ❌ 생략 (확정 2026-05-26) | 사용자 결정 (Step 3 완료 후 재평가 결과). 사유 — (1) 변경 성격 mechanical (search-replace + skill/unit categorization 명시), (2) semantic 불변 (rename 만, 동작 변경 0), (3) render dry-run 으로 ExecStart 의 skill name 보존 + 7 unit 정확 출력 검증, (4) pytest 57 pass / 1 skip 변동 없음, (5) grep verify 로 잔존 13건 모두 의도된 historical/migration. CLAUDE.md §3 Step 4 의 "생략 가능 조건" 중 변경 크기 (50줄 초과) 와 외부 인터페이스 (systemd unit name) 두 항목은 strict 미충족이나, 직전 monitor_services_remove (ADR-0040) 의 멀티모델 리뷰가 본 layer 정합 검토를 이미 surface 한 점 + 본 변경의 검증 가능성이 정적 검증으로 완결되는 점을 근거로 메인테이너 판단 생략. |
| Step 5 (Deploy) | ✅ | `_system/systemd/` template + `install.sh` 변경 → 운영 영향 있음. v0.1.9 같은 release window |

## 예상 영향 범위

**Rename 4 template:**
- `_system/systemd/wh-ingest@.service.template` → `wikihub-ingest@.service.template`
- `_system/systemd/wh-ingest@.timer.template` → `wikihub-ingest@.timer.template`
- `_system/systemd/wh-lint.service.template` → `wikihub-lint.service.template`
- `_system/systemd/wh-lint.timer.template` → `wikihub-lint.timer.template`

**수정:**
- `install.sh` — 21 systemd unit refs (stop/start/disable/reset-failed/try-restart/banner). skill name refs (`--skills wh-*`) 는 그대로.
- `_system/commands/setup.md` (8), `lint.md` (9), `graphify.md` (2)
- `_system/wiki-schema.md` (30 — inventory + namespace catalog)
- `scripts/_helpers/render_systemd_units.py` (5 — glob/regex/legacy_singletons)
- `README.md` (5)
- `docs/adr/0040-monitor-services-remove.md` (1 — 직전 작성 narrative)
- `wikihub.yaml.example` — 주석에 systemd unit 언급 있으면

**Upgrade migration (canary 운영자 대응):**
- v0.1.9 canary 가 이미 `wh-ingest@*` + `wh-lint.*` unit 으로 운영 중일 가능성 — install.sh 의 upgrade migration block 에 stop + disable + render legacy cleanup 추가 필요.

**신규 ADR-0041:**
- 결정: systemd unit `wikihub-*` namespace, Hermes skill `wh-*` namespace (ADR-0033) 의 두 레이어 분리 정합.
- Supersedes: ADR-0033 본문 X (skill prefix 결정 자체는 그대로) — 다만 commit 2ed01f8 의 rename 결정 (systemd unit 을 skill 과 통일) 을 반전. 2ed01f8 은 ADR 없는 implementation level 결정이라 ADR Supersedes 형식 부적합 — 신규 ADR-0041 이 직접 결정.

## 메소드론 적용

적용 (생략 조건 미충족 — 단일 파일 50줄 초과).

## Open Question

1. **Step 4 review 생략 여부**: 본 rename 이 mechanical (skill name 보존, semantic 불변) 이고 직전 monitor_services_remove 가 멀티모델 리뷰 완료 → 본 feature 는 §4 생략 가능. 사용자 결정 후 plan.md 갱신.
2. **legacy_singletons 확장 catalog**: 현재 monitor 4종 + `wikihub-lint.{service,timer}` (pre-rename) 가 등록. 본 rename 후 `wh-lint.{service,timer}` + `wh-ingest@<vid>.{service,timer}` 도 cleanup 대상 추가 필요. glob 패턴 정합 검토.

## DoD (preliminary)

- [ ] 4 template rename + 21+ refs 일괄 갱신
- [ ] Hermes skill name (`wh-*`) 0 회 touched (grep verify)
- [ ] systemd unit name `wh-*` 0 회 잔존 (intentional upgrade-migration/legacy_singletons 제외)
- [ ] render dry-run → `wikihub-ingest@`, `wikihub-lint.*` 출력 확인
- [ ] pytest pass
- [ ] ADR-0041 Accepted + ADR README index
- [ ] install.sh upgrade migration block — `wh-*` legacy stop+disable + render cleanup 추가
