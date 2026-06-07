# Analysis & Design: WikiHub schema v1

- **Feature ID**: `20260513_wikihub_schema_v1`
- **작성일**: 2026-05-13 (KST)
- **선행 feature**: [F1 `20260513_v030_initial_architecture`](../archive/20260513_v030_initial_architecture/) (archive, approved 2026-05-13)
- **목적 범위**: 본 feature는 **정본 룰·명령어 spec(`_system/wiki-schema.md` + `_system/commands/*.md`) + ADR 추가 발의** 산출. F2 산출물은 그 자체가 spec이라 본 문서는 thin wrapper — 결정 종합·rationale·DoD 기록 역할
- **approved**: 2026-05-13

### Revision Log

| Version | Date | 변경 요지 |
|---|---|---|
| v1 | 2026-05-13 | F2 plan 확정 후 use-case 기반 결정 라운드 + 5개 command playbook 초안 + wiki-schema.md v1 + ADR-0005~0012 (8건) |
| v2 | 2026-05-13 | 멀티모델 design review 2건(`design_review_1.md` 코드 정합성, `design_review_2.md` F3/F5 implementer 관점) 결과 28+건 전수 반영. R1 high·med·low (9건) + R2 critical·significant·operational (20건). 추가 발의: ADR-0013 (entity·concept 추출 정책) |

---

## 1. 배경

본 feature는 **F1 §4.5의 wiki 모델 결정을 정본 룰·명령어 파일로 실체화**한다. F1이 wiki 모델·OAuth·orchestration·systemd 등 architecture를 결정했고, F2는 그 결정을 `_system/*`의 정본 spec으로 변환한다.

F1 §4.5와 다른 결정 추가:

- **단일 파일 모델 (this session)**: 사이드카 분리 폐기 — `wiki/sources/{vault}/path.ext.md` 하나가 frontmatter + 추출 본문 모두 담음. sync(F3)가 직접 작성. agent는 entities/concepts/analyses만 만짐
- **agent-agnostic spec**: Hermes 종속 표기 제거. `<agent_invocation>` placeholder + `wikihub.yaml.agent` 분리 (ADR-0012)
- **wh: skill namespace** (ADR-0011): 다른 도구와 충돌 방지
- **install.sh + /wh:setup, deploy.sh 폐기** (ADR-0010): git pull 없이 curl 1줄로 install+update. 운영 도구 4개 → 2개
- **/wh:lint 권한 모델** (ADR-0008): 비파괴 자동, 파괴 `--apply`. self-maintaining + 데이터 손실 차단

## 2. 핵심 결정 종합 (ADR-0005 ~ 0013, 9건)

| ADR | 결정 |
|---|---|
| 0005 | wiki/index.md 단일 + /wh:lint 갱신 / log vault별 |
| 0006 | Unified orchestration — agent가 orchestrator. systemd timer → `<agent_invocation> "/wh:ingest --vault X"` 직접 |
| 0007 | State 저장 방식 all JSON (F1 §4.4.4 SQLite retract) |
| 0008 | /wh:lint 권한 분류 — 비파괴 자동 / 파괴 `--apply` |
| 0009 | /wh:setup 책임 — wikihub.yaml → systemd unit 동기화 + 환경 검증 |
| 0010 | install.sh + /wh:setup (deploy.sh 폐기, git 의존 없음, tag `latest`) |
| 0011 | Skill namespace prefix `wh:` (default), `wh-` (fallback) |
| 0012 | Agent invocation 추상화 (`wikihub.yaml.agent.invocation` + install.sh 매핑) |
| 0013 | entity·concept 추출 정책 (분류·임계·신뢰 경계) |

## 3. 산출물

### 3.1 정본 파일 (`_system/`)

| 파일 | 줄 수 (대략) | 비고 |
|---|---|---|
| `_system/VERSION` | 1 | `0.1.0` (install.sh 비교 기준) |
| `_system/wiki-schema.md` | ~400 | Operator Guide — agent-agnostic. 디렉토리·카테고리·frontmatter·link·timezone·신뢰 경계·명령 참조 |
| `_system/commands/ingest.md` | ~270 | unified orchestration (script subprocess + semantic). pending_ingest 부분 실패 복구. JSON contract 정본. 403 분기 lift |
| `_system/commands/lint.md` | ~160 | 비파괴 자동 + `--apply`. Step 9에서 /wh:graphify 자동 호출. index 재구성 책임 |
| `_system/commands/query.md` | ~170 | Telegram·CLI 둘 다. graphify 1차/index 폴백. **저장 trigger 키워드만 analyses에 저장** (v0.1.0 안전 default) |
| `_system/commands/graphify.md` | ~100 | v0.2.6 lift + lint 통합 |
| `_system/commands/setup.md` | ~170 | yaml→systemd 동기화. **ExecStart 조립 규약** (B4 정본). drive.about.get 권한 검증 |

### 3.2 ADR (`docs/adr/`)

ADR-0005 ~ 0013 (9건) — 위 2절 참조.

### 3.3 잠정 ADR 후보 (F2 진행 중 surface, 운영·F3·F5에서 결정 시 발의)

- ADR-0014: non-sources 카테고리 link prefix 정책 (현 v0.1.0은 Wikipedia disambiguator로 처리)
- ADR-0015: log.md rotation 정책
- ADR-0016: /wh:lint report push 알림 정책
- ADR-0017: entity·concept alias·동의어 정책

## 4. F1 결정 lift 매트릭스

F1 산출물의 결정이 F2 spec에 어떻게 반영됐는지 추적:

| F1 결정 | F2 lift 위치 |
|---|---|
| §4.1.1 디렉토리 책임 매트릭스 | wiki-schema.md §디렉토리 구조 + 책임 매트릭스 |
| §4.1.3 timestamp 정책 (UTC 영속 / KST 표기) | wiki-schema.md §시간·timezone 정책 |
| §4.2.2 ChangedFile dataclass | ingest.md §Step 2 script JSON schema (필드 1:1 lift) |
| §4.2.3 VaultSyncRetryable/Fatal | ingest.md §script exit code + 에러 분류 표 |
| §4.4.5 _state/ 일관성 | wiki-schema.md (ADR-0007이 SQLite → JSON으로 simplification) |
| §4.4.6 bootstrap 가드 | ingest.md §Step 2 bootstrap 가드 (lift, O3) |
| §4.5 wiki/sources 모델·frontmatter·log.md | wiki-schema.md §위키 페이지 형식 (단일 파일 모델로 진화) |
| §4.5.5 신뢰 경계 | wiki-schema.md §신뢰 경계 + query.md §신뢰 경계 |
| §4.6 Hermes 호출 인터페이스 | ADR-0006 unified orchestration + ADR-0012 agent-agnostic (Hermes 종속 supersede) |
| §4.6.4 pending_ingest 패턴 | ingest.md §Step 1·3 (단일 파일 모델 변형 + 재진입 정책) |
| §4.6.6 notify 이중 경로 | ingest.md §실패 처리 + setup.md `ops-alert.service` |
| §4.7 OAuth 흐름 | setup.md §Step 1 (OAuth 검증). 발급 절차는 F1 archive 참조 |
| §4.7.5 Drive 403 분기 | ingest.md §script 에러 분류 표 (A6 lift) |
| §4.8 systemd unit 구조 | ADR-0006 + setup.md §Step 2 + ADR-0009 (yaml→unit instance화) |
| §4.8.6 deploy.sh | **ADR-0010이 폐기**. install.sh + /wh:setup으로 통합 |
| §4.9 F2~F6 의존 그래프 | 본 F2가 그 안의 F2를 실현. F4 unit template·install.sh, F5 agent skill, F3 vault-fetch.py 책임 일부 reframe |

## 5. Definition of Done

F2 plan.md의 계획 단계 명시:

- [x] **Step 1 (plan)**: `plan.md` 작성 및 사용자 확정
- [x] **Step 2 (analysis & design)**: 본 문서 (산출물 references + 결정 종합)
- [x] **Step 2 (산출물)**: `_system/wiki-schema.md` + `_system/commands/*.md` (5) + `_system/VERSION`
- [x] **ADR 추출**: ADR-0005 ~ 0013 (9건) + 잠정 후보 4건 (0014~0017)
- [x] **Step 2 멀티모델 design review**: `design_review_1.md` (feature-dev:code-reviewer), `design_review_2.md` (general-purpose F3/F5 implementer 관점). 지적 28+건 v3 전수 반영
- [x] **Step 2 사용자 승인**: `approved: 2026-05-13` (상단)
- [ ] **Step 3 implementation**: 본 feature는 Step 3 = 산출물 직접 작성과 동일 (doc-only feature). 산출물이 곧 spec
- [ ] **Step 4 code review**: 멀티모델 design review와 동등 (위 항목). 별도 code review 없음 — 산출물이 spec
- [ ] **Step 5 deployment**: **생략 (plan 선언)** — F4 install.sh가 정본 fetch 시 본 산출물 자연 배포. HISTORY.md 항목 없음
- [ ] **Feature 종료 처리**: `git mv features/20260513_wikihub_schema_v1 features/archive/...`. 사용자 트리거(`feature 종료해줘`)로 진행

## 6. 참조

- F2 plan: `plan.md`
- F2 산출물 (정본): `_system/*`
- F2 design review: `design_review_1.md`, `design_review_2.md`
- F2 ADR: `docs/adr/0005~0013-*.md`
- F1 archive (선행 결정): `features/archive/20260513_v030_initial_architecture/`
- WikiCurate v0.2.6 reference: <https://github.com/im-dongseon/wikicurate>
