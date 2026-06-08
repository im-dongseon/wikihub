# Plan: WikiHub schema v1 — `_system/` 정본 룰·명령어 구현

- **Feature ID**: `20260513_wikihub_schema_v1`
- **작성일**: 2026-05-13 (KST)
- **선행 feature**: [F1 `20260513_v030_initial_architecture`](../archive/20260513_v030_initial_architecture/) (archive, approved 2026-05-13)
- **참조 결정**: ADR-0001 (vault namespace + `[[link]]` 단축형 금지)

## 작업 분류

- **문서** (정본 룰·명령어 spec 작성). 코드는 F3·F5가 책임.

## 적용 단계 선언

| 단계 | 수행 여부 | 사유 |
|---|---|---|
| Step 1 Plan | 수행 (본 문서) | F1 메소드론 first cycle 완수 후 두 번째 feature — 추적성 유지 |
| Step 2 Analysis & Design | 수행 | 본 feature의 핵심 산출물(`_system/wiki-schema.md`)이 spec 그 자체. analysis 섹션은 lightweight(F1이 이미 §4.5에서 분석 완료) |
| Step 2 Design Review | **선택** | 작성 후 복잡도 판단. F3·F5가 본 spec을 정본 참조하므로 cascade 영향 고려해 멀티모델 리뷰 권장 가능 |
| Step 3 Implementation | 수행 | `_system/wiki-schema.md` + `_system/commands/*.md` 실제 작성 |
| Step 4 Code Review | **수행 권장** | 변경 50줄 초과 + 다중 파일 + 외부 인터페이스(스키마·명령어 의미론) 정의 → 생략 조건 충족 X |
| Step 5 Deployment | **생략** | 사유: deploy.sh와 그 배포 대상(Hermes daemon, sync 스크립트)가 모두 부재(F3·F4가 만들 예정). 운영 시스템 미반영해도 무방. F4가 deploy.sh 첫 실행 시 본 산출물 자연 배포 |
| Feature 종료 처리 | 수행 | ADR 검증 + `features/archive/`로 이동 (필수) |

생략 조건 매핑:
- Step 5 생략: AGENTS.md §3 Step 5 생략 조건 중 "운영 환경 — 운영 시스템에 미반영해도 무방한 변경" 조항 적용. F2 산출물(`_system/*`)은 정본이지만 이를 소비하는 코드(Hermes skill, sync 트리거)가 아직 없어 미반영 무방. HISTORY.md 항목 추가도 함께 생략.

## 생성 예정 ADR

분석·설계 단계에서 미결 사항이 surface될 때만 발의. 현재 식별된 후보:

**확정 ADR (Step 2 진행 중 결정 완료)**:

| ID | Title | 결정 요지 |
|---|---|---|
| ADR-0005 | wiki/index.md·log.md 위치성 | index 단일 + /lint 갱신 / log vault별 |
| ADR-0006 | ingest 오케스트레이션 모델 | agent가 orchestrator (unified). systemd → `hermes -z /ingest` → script subprocess + semantic |
| ADR-0007 | state 저장 방식 | all JSON 통일 (F1 §4.4.4 SQLite retract) |
| ADR-0008 | /lint 권한 분류 | 비파괴 자동 / 파괴 `--apply` |
| ADR-0009 | /setup의 책임 | wikihub.yaml → systemd unit 동기화 + 환경 검증 |
| ADR-0010 | 운영 도구 책임 분할 | install.sh (install+update, git 의존 없음, tag `latest` 기준) + /wh:setup. deploy.sh 폐기 |
| ADR-0011 | Agent skill namespace prefix | `wh:` (default), `wh-` (fallback) |
| ADR-0012 | Agent invocation 추상화 | `wikihub.yaml.agent.invocation` (binary+oneshot_args 분리) + install.sh type별 default 매핑 |
| ADR-0013 | entity·concept 추출 정책 | 분류 규칙(고유명사 vs 보통명사), 임계, 1줄 요약 source 정책 (외부 지식 generation 금지) |

**잠정 ADR 후보 (Step 2 잔여 use case에서 결정 시 발의)**:

| ID (잠정) | Title (잠정) | 발의 트리거 |
|---|---|---|
| ADR-0014 | non-sources 카테고리 link prefix 정책 | entities/concepts/analyses에서 동명 충돌 시 카테고리 prefix 의무화 (F1 §4.5.2 노트). 현 v0.1.0은 Wikipedia disambiguator로 잠정 처리 |
| ADR-0015 | log.md rotation 정책 | 단일 파일 유지 vs 월별 분할 (`log-2026-05.md`) — F1 §4.5.4 노트 |
| ADR-0016 | /wh:lint report push 알림 정책 | Telegram·email·webhook 푸시 (현 v0.1.0은 메인테이너 자발적 확인, ADR-0008 §부정 명시) |
| ADR-0017 | entity·concept alias·동의어 정책 | ADR-0013 §부정/제약 — 한국어·영어 동의어 통합 |

위 4건은 plan 단계 가설. Step 2 설계 도중 추가·제거·변경 가능.

## 예상 영향 범위

- **추가** (정본 신규):
  - `_system/wiki-schema.md` — 지식 모델 정본
  - `_system/commands/ingest.md` (= `/wh:ingest` playbook)
  - `_system/commands/lint.md` (= `/wh:lint` playbook)
  - `_system/commands/query.md` (= `/wh:query` playbook)
  - `_system/commands/graphify.md` (= `/wh:graphify` playbook)
  - `_system/commands/setup.md` (= `/wh:setup` playbook)
  - `_system/VERSION` (단일 라인 — v0.2.6 패턴 lift, install.sh가 비교)
  - `docs/adr/000N-*.md` — 본 단계에서 결정되는 ADR (해당 시)

- **F4로 이관 (본 feature 외)**:
  - `install.sh` (root, executable) — ADR-0010
  - `_system/systemd/*.{service,timer}` template (placeholder 포함)
  - `wikihub.yaml.example` (root)
  - ~~`deploy.sh`~~ — ADR-0010으로 폐기
- **추가** (workspace 산출물):
  - `features/20260513_wikihub_schema_v1/{plan.md, analysis_and_design.md, design_review_N.md(선택), code_review_N.md}`
- **수정**: 없음 (F1 산출물·기존 `_system/*` 모두 미변경 — 후자는 그 자체가 부재)
- **삭제**: 없음
- **종료 후 이동**: `features/20260513_wikihub_schema_v1/` → `features/archive/20260513_wikihub_schema_v1/`

후속 feature 참조 관계:
- **F3 (`vault_gdrive_api`)**: `/ingest` 입력 포맷(F1 `last_sync.json` 형식)을 본 spec이 정본화 → F3 sync 스크립트가 본 포맷 준수
- **F5 (`hermes_adapter`)**: 본 spec을 Hermes skill로 실체화 — `_system/commands/*.md` 1대1 매핑

## 메소드론 적용 여부

- **적용**: Step 1~5 (Step 5만 생략)
- **사유**: F3·F5가 본 산출물을 정본 참조하므로 결함이 cascade. 추적성·리뷰 필수

## 입력 자료

- F1 `analysis_and_design.md` §4.5 (wiki/sources 모델, frontmatter, log.md 포맷)
- F1 `analysis_and_design.md` §4.5.5 (신뢰 경계 — `/ingest`·`/query` skill 책임 분리)
- F1 `analysis_and_design.md` §4.6.2 (Hermes prompt 포맷 — `/ingest` 명령 인자)
- ADR-0001 (vault namespace + 단축형 금지)
- WikiCurate v0.2.6의 `_system/wiki-schema.md` + `_system/commands/{ingest,lint,query,graphify,setup}.md` — reference base. 다중 vault 변형을 ADR-0001에 맞춰 lift

## 다음 단계

본 plan.md 확정 후 → analysis_and_design.md 작성. 분석 섹션은 lightweight(F1 §4.5의 결정을 옮겨오는 수준), 설계 섹션이 실질 본문. Step 3에서 정본 6 파일 작성.
