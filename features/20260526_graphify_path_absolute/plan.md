# Plan — graphify_path_absolute

**Date:** 2026-05-26
**Feat ID:** graphify_path_absolute
**Source:** OCI runtime fix sync — wh-lint skill 의 `graphify-out/graph.json` 상대 경로 resolution 이슈

---

## 작업 분류

버그 fix + 운영 hardening. OCI 운영 중 발견된 stale `wiki/graphify-out/` (934 nodes, 826 edges, 2026-05-24 생성, 4.6MB) 결함의 source code 반영.

## 타겟 버전 브랜치

`v0.1.9` — 직전 squash commit (3135864) 이미 land. 본 fix 도 같은 release window 흡수 (v0.1.9 micro-release 또는 v0.1.10 시점 결정).

## 적용 단계

| Step | 수행 | 사유 |
|---|---|---|
| Step 1 (Plan) | ✅ | 본 문서 |
| Step 2 (Analysis & Design) | ✅ | lint.md 5 위치 + reference doc 신규 + ignore 보강 → 통합 설계 |
| Step 3 (Implementation) | ✅ | feature/graphify_path_absolute 분기 진행 |
| Step 4 (Code Review) | ❌ 생략 (확정 2026-05-26) | 사용자 결정 (Step 3 완료 후). 사유 — (1) OCI 운영 실증 완료 (사용자가 직접 patch deploy + 동작 확인), (2) mechanical path absolutization (semantic 불변), (3) Step 7 신규 cleanup logic 도 recoverable archive 만 (rm -rf 금지 명시) — destructive 없음, (4) `_system/commands/lint.md` 단일 본문 변경 + ADR 신설 없음 (implementation hardening), (5) grep verify (3 위치 절대 경로 정합 + links/edges 호환 명시) + pytest 57 pass / 1 skip 검증 통과. CLAUDE.md §3 Step 4 §"생략 가능 조건" 의 변경 크기 (50줄 초과) 는 strict 미충족이나 직전 ADR-0036/0040/0041 일련 feature 의 멀티모델 리뷰가 graphify layer 정합을 이미 surface 한 점 + OCI 실증 trail 을 근거로 메인테이너 판단 생략. |
| Step 5 (Deploy) | ✅ | `_system/commands/lint.md` + `_system/templates/wiki/.graphifyignore` 변경 — 운영 영향 (lint 동작 변경) |

## 예상 영향 범위

**수정 (1 파일):**
- `_system/commands/lint.md` — 5 위치 graph.json 절대 경로 + Step 3 edge 키 호환 + Step 7 stale 디렉토리 정리 + Step 8 보고 형식 + 사전 조건 경고

**추가 (2 파일):**
- `_system/templates/wiki/.graphifyignore` — `graphify-out/` 추가 (defense-in-depth)
- `docs/references/graph-path-resolution.md` — 이슈 분석 + 판별법 reference doc

**ADR:**
- `docs/adr/0036-graphify-cli-integration.md` §"후속 영향" 1줄 add (ADR 신설 불필요 — architectural 결정 변경 없음, implementation hardening)

## 메소드론 적용 여부

적용. 단일 파일 50줄 초과 + 외부 인터페이스 (lint 동작 변경 — stale dir cleanup 신규 책임).

## DoD (preliminary)

- [ ] lint.md 5 위치 `graphify-out/graph.json` → `$WIKIHUB_HOME/graphify-out/graph.json` (절대 경로)
- [ ] lint.md Step 3 — graphify v0.8+ schema 호환 (`d.get('links', d.get('edges', []))`) 명시
- [ ] lint.md Step 7 — stale `wiki/graphify-out/` 감지 시 `graphify-out/.archived/wiki-graphify-out-<utc_iso>/` 이동 로직
- [ ] lint.md 사전 조건 — 경로 주의 + stale 감지 안내
- [ ] lint.md Step 8 보고 형식 — stale cleanup 항목 추가
- [ ] `.graphifyignore` — `graphify-out/` 추가
- [ ] `docs/references/graph-path-resolution.md` 신설
- [ ] ADR-0036 §"후속 영향" cross-ref
- [ ] pytest pass (변경 없음 예상)
- [ ] grep verify — `graphify-out/graph.json` 단독 (절대 경로 prefix 없는) ref 0건 in lint.md

## Open Question

1. **Step 4 review 생략 여부**: mechanical path absolutization + add new cleanup logic. OCI 운영 검증 완료. Step 3 완료 후 grep + pytest 검증으로 충분한지 결정.
2. **`docs/references/` 디렉토리 신설**: 현재 부재. 본 feature 가 첫 도입. 이후 reference doc 의 정착 위치로 명명 확정 (`docs/references/` 채택).
