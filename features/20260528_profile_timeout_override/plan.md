# Plan — profile_timeout_override

**Date:** 2026-05-28
**Feat ID:** profile_timeout_override
**Source:** GitHub Issue #36 — graphify timeout 이 backend 구분 없이 단일 값 적용

---

## 작업 분류

기능 추가. profile-level timeout override 도입으로 ollama(로컬 LLM, 30분+)와 cloud API(수분) 간 latency 차이를 반영.

## 타겟 버전 브랜치

`v0.1.10` — graphify_path_absolute feature 이후 동일 release window 흡수.

## 적용 단계

| Step | 수행 | 사유 |
|---|---|---|
| Step 1 (Plan) | ✅ | 본 문서 |
| Step 2 (Analysis & Design) | ✅ | 4 파일 변경 + ADR 불필요 (기존 ADR-0036/0038 확장, architectural 결정 변경 없음) |
| Step 3 (Implementation) | ✅ | feature/profile_timeout_override 분기 진행 |
| Step 4 (Code Review) | ❌ 생략 | (1) 변경 크기: `wikihub_graphify.sh` yq 로직 1줄 변경, yaml.example 3줄 추가, graphify.md 표 행 추가, install.sh 변경 0. 전체 ~10줄 미만. (2) 변경 성격: timeout fallback chain 추가 — semantic 불변 (기존 global timeout 동작 보존). (3) 영향 범위: 외부 인터페이스 미변경 (yaml schema 확장 only, 기존 필드 보존). CLAUDE.md §3 Step 4 §"생략 가능 조건" 3항 모두 충족. |
| Step 5 (Deploy) | ✅ | `wikihub_graphify.sh` + `wikihub.yaml.example` 변경 — 운영 영향 (graphify timeout 동작 변경 가능성) |

## 예상 영향 범위

**수정 (1 파일):**
- `scripts/wikihub_graphify.sh` — L73 timeout_sec 읽기 로직: profile-specific timeout 우선 조회 → global fallback → default 900

**수정 (1 파일):**
- `wikihub.yaml.example` — L59 이후 `graphify_profiles` dict 예시 추가

**수정 (1 파일):**
- `_system/commands/graphify.md` — L48 timeout 설명 표 행 추가 + backend/profile 별 timeout 설명 보강

**자동 (0 파일):**
- `install.sh` `_migrate_agent_schema` — yaml.example 기반 자동 backfill (신규 `graphify_profiles` 필드는 예시에만 추가하면 자동). install.sh 변경 불필요.

## 메소드론 적용 여부

적용. 변경 크기 50줄 미만이지만 graphify timeout 동작 변경 = 운영 영향.

## DoD (preliminary)

- [ ] `scripts/wikihub_graphify.sh` L73 — profile-specific timeout 우선 조회 로직 (yq 3단 fallback)
- [ ] `wikihub.yaml.example` — `graphify_profiles` dict 예시 (`ollama_gemma: timeout_sec: 1800`)
- [ ] `_system/commands/graphify.md` — timeout 우선순위 체인 표 + profile 별 timeout 설명
- [ ] `_migrate_agent_schema` 영향 분석 — yaml.example sync 로 충분 확인
- [ ] yq 쿼리 검증 — profile 미설정 시 global fallback 동작, profile 설정 시 profile-specific 값 사용

## Open Question

1. **`graphify_profiles` dict 의 scope**: timeout_sec 만 둘지, 향후 profile-level concurrency 등 확장 필드를 고려할지. 본 feature 는 timeout_sec 만 (Atomic Change 원칙). 향후 확장 시 dict 구조가 자연스러움.
2. **ADR 신설 불필요**: 기존 ADR-0036 (graphify CLI integration) + ADR-0038 (env namespace isolation) 의 자연스러운 확장. timeout override 는 architectural 결정 변경이 아닌 operational parameter 세분화. §"후속 영향" 1줄 add 만으로 충분.
