# Plan: WikiHub v0.1.0 초기 아키텍처

- **Feature ID**: `20260513_v030_initial_architecture`
- **작성일**: 2026-05-13 (KST)

## 작업 분류

- **운영** (메타 결정: WikiCurate v0.2.6의 후속으로 신규 리포 `wikihub`의 v0.1.0 아키텍처를 정의)

본 feature는 코드 구현이 아니라 아키텍처 정의가 산출물. 구현은 후속 feature(F2~F6)로 분리한다.

## 적용 단계 선언

| 단계 | 수행 여부 | 사유 |
|---|---|---|
| Step 1 Plan | 수행 (본 문서) | 메소드론 정립 직후 첫 feature이므로 명시적으로 작성 |
| Step 2 Analysis & Design | 수행 | 아키텍처 정의가 본 feature의 핵심 산출물 |
| Step 2 Design Review | **선택** | 사용자 판단. design 작성 후 결정 |
| Step 3 Implementation | **본 feature에서는 미수행** | 후속 feature로 이관 |
| Step 4 Code Review | **본 feature에서는 미수행** | 구현이 없으므로 적용 불가 |
| Step 5 Deployment | **생략** | 변경 대상이 `_system/` 및 `scripts/` 둘 다 미변경 (메인테이너 가이드 + features/ 산출물만). 운영 시스템에 미반영해도 무방 |
| Feature 종료 처리 | 수행 | ADR 검증 + `features/archive/`로 이동 (필수) |

생략 조건 매핑:
- Step 5 생략: 변경 대상이 features/ 산출물(plan + analysis_and_design)뿐. AGENTS.md/docs/는 본 feature와 별개로 부트스트랩 단계에서 갱신됨. `_system/`과 `scripts/`는 이 feature가 손대지 않음 → AGENTS.md §2 Step 5의 "변경 대상" 조건 충족 → 배포 절차 생략 가능. HISTORY.md 항목도 추가하지 않음.

## 생성 예정 ADR

| ID | Title | 비고 |
|---|---|---|
| ADR-0001 | source-collision-policy | 소스 페이지 충돌 정책 (α/β/γ) |
| ADR-0002 | hermes-invocation-interface | Hermes 호출 인터페이스 (CLI/HTTP/IPC) |
| ADR-0003 | headless-oauth-strategy | OAuth 헤드리스 방식 (token-scp / device-code) |
| ADR-0004 | drive-access-mechanism | Drive 접근 메커니즘 (Direct API vs gws CLI) — Step 2 진행 중 추가 발의 |

각 ADR은 Step 2(분석및설계)에서 결정 시점에 `docs/adr/`에 생성된다.

## 예상 영향 범위

- **추가**: 
  - `features/20260513_v030_initial_architecture/{plan.md, analysis_and_design.md, design_review_N.md(선택)}`
  - `docs/adr/{0001, 0002, 0003}-*.md` + `docs/adr/README.md` 인덱스 갱신
- **수정**: 없음 (정본 `_system/` 미변경)
- **삭제**: 없음
- **종료 후 이동**: `features/20260513_v030_initial_architecture/` → `features/archive/20260513_v030_initial_architecture/`

후속 feature가 시작되면 본 feature가 생성한 ADR-0001~0003을 결정 참조로 사용한다. 본 feature 자체는 정본(`_system/`)을 건드리지 않는다.

## 메소드론 적용 여부

- **적용**: Step 1 + Step 2 (이후 단계는 위 표대로 생략 또는 후속 feature로 이관)
- **사유**: 후속 feature 다수의 기반 결정을 정의하므로 추적성이 필수. 새 메소드론의 first instance로서 본보기를 남기는 의미도 있음.

## 다음 단계

본 plan.md 확정 후 → `analysis_and_design.md`의 분석 섹션은 이미 작성 완료. 설계 섹션 추가 작성 + 미결 3건 결정 + ADR-0001~0003 추출로 진행. 본 feature 종료 시점에 archive로 이동.
