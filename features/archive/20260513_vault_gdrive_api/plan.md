# Plan: vault_gdrive_api — gws CLI 기반 vault sync 구현

- **Feature ID**: `20260513_vault_gdrive_api`
- **작성일**: 2026-05-13 (KST)
- **선행 feature**: [F1 `v030_initial_architecture`](../archive/20260513_v030_initial_architecture/), [F2 `wikihub_schema_v1`](../archive/20260513_wikihub_schema_v1/)
- **참조 결정**:
  - F2 spec: `_system/commands/ingest.md` §Step 2 (JSON contract 정본), `_system/wiki-schema.md` (frontmatter·파일명·extraction tool 표)
  - ADR-0001 (vault namespace), 0003 (OAuth), 0006 (unified orchestration), 0007 (state JSON), 0014 (gws CLI)

## 작업 분류

- **기능** (Python 구현 — wikihub 첫 코드 feature). F1·F2는 doc·spec only, F3가 첫 runnable 산출

## 적용 단계 선언

| 단계 | 수행 여부 | 사유 |
|---|---|---|
| Step 1 Plan | 수행 (본 문서) | F1·F2 패턴 따라 |
| Step 2 Analysis & Design | 수행 | 코드 feature이므로 모듈 구조·테스트 전략·gws 인터페이스 실증 필요 |
| Step 2 Design Review | 권장 (선택) | gws 매핑 정확성·error 분류 정확성 검증 (alpha 의존성 우려). 멀티모델 가능 |
| Step 3 Implementation | 수행 | `scripts/vault-fetch.py` + 부속 모듈 + 테스트 |
| Step 4 Code Review | **수행 (권장)** | 첫 코드 feature. 50줄 초과 + 다중 파일 + 외부 인터페이스(F2 JSON contract) 정합 검증 필수. 멀티모델 |
| Step 5 Deployment | **생략** | 사유: install.sh와 systemd unit이 모두 부재(F4 산출물). F3 단독으로는 운영 시스템 배포 불가 — F4 통합 시 함께 deploy. dev box 단위 e2e 테스트는 Step 3 자가 검증에 포함 |
| Feature 종료 처리 | 수행 | ADR 검증 + `features/archive/`로 이동 (필수) |

생략 조건 매핑:
- Step 5 생략: AGENTS.md §3 Step 5 생략 조건 중 "운영 시스템에 미반영해도 무방한 변경 (개발 단계 산출물 등)" 적용. F3는 scripts/ 만 추가하지만 이를 systemd unit에 연결하는 F4가 없으면 실제 동작 불가. F4 완료 시점에 install.sh가 본 F3 산출물을 fetch해서 자연 deploy. HISTORY.md 항목도 함께 생략

## 생성 예정 ADR

본 단계에서 surface될 수 있는 ADR 후보 (Step 2 결정 시 발의):

| ID (잠정) | Title (잠정) | 발의 트리거 |
|---|---|---|
| ADR-0015 | gws version pinning 값 | install.sh의 venv 또는 system 설치 시 어느 버전을 정본으로 고정할지 (F4가 명문화 책임이나 F3 테스트 기준이 우선 정해져야 함) |
| ADR-0016 | Python 모듈 구조 | 단일 `vault-fetch.py` 모놀리식 vs `vault_fetch/__init__.py` + 서브모듈 분할. 분할 시 entry point 위치 |
| ADR-0017 | gws stderr 패턴 매칭 표 | gws exit code 1(API 에러) + stderr 키워드로 Drive 403 분기(F1 §4.7.5) 구현. 버전 변경 시 표 갱신 책임 |

위 3건은 plan 단계 가설. Step 2 도중 surface 시 발의·확정.

## 예상 영향 범위

- **추가** (정본 신규):
  - `scripts/vault-fetch.py` — 단일 진입점 (`--vault <vault_id>` + 선택 `--bootstrap`)
  - `scripts/auth_gdrive.py` — macOS dev box용 1회성 OAuth 발급 (F1 §4.7.2 lift)
  - `scripts/lib/` (Python 모듈 — Step 2에서 분할 결정 시):
    - `_state.py` — JSON atomic write·load helper
    - `_errors.py` — gws exit code 분류 → 75/2 매핑
    - `_extraction.py` — binary extraction dispatch (python-pptx·python-docx·openpyxl·pdfminer.six)
    - `_credentials.py` — OAuth pickle load + refresh + env var injection
  - `scripts/requirements.txt` 또는 `pyproject.toml` — 의존성 명시
  - `tests/test_vault_fetch.py` 등 — pytest 단위 테스트 (mocked gws)
  - `features/20260513_vault_gdrive_api/{plan.md, analysis_and_design.md, design_review_N.md(선택), code_review_N.md}`

- **수정**: 없음 (F1·F2·ADR 산출물 모두 정본 그대로 사용)
- **삭제**: 없음
- **종료 후 이동**: `features/20260513_vault_gdrive_api/` → `features/archive/...`

후속 feature 참조 관계:
- F4(`systemd_orchestrator`): F3의 `vault-fetch.py`를 systemd unit ExecStart의 subprocess target으로 참조. install.sh가 본 F3 산출물을 fetch
- F5(`hermes_adapter`): F3의 stdout JSON output을 read해 semantic phase 처리 (ingest.md §Step 4 정합)

## 메소드론 적용 여부

- **적용**: Step 1~4 (Step 5만 생략)
- **사유**: 코드 feature는 spec 준수·error 분기·테스트 정합성 검증 필수. 첫 코드라 future feature의 reference 패턴 역할도 있음

## 입력 자료

- F2 `_system/commands/ingest.md` §Step 2 — script stdout JSON schema (정본)
- F2 `_system/wiki-schema.md` — frontmatter 자료형 표, 파일명 규약 표, extraction tool dispatch 표
- F2 `_system/commands/setup.md` §Step 1 — 초기 state JSON 형식
- ADR-0001 vault namespace + `[[link]]` 규약 (sync 작성 source 페이지의 link 형식)
- ADR-0003 Workspace + token-scp OAuth
- ADR-0007 all JSON state
- ADR-0014 gws CLI 채택
- F1 archive `analysis_and_design.md` §4.2 (vault 인터페이스), §4.4 (state), §4.7 (OAuth), §4.7.5 (403 분기)
- WikiCurate v0.2.6 reference `_system/wiki-schema.md` 바이너리 처리 섹션 (binary extraction 패턴 lift)

## 사전 조건 / 운영 가정

- **gws CLI 동작 가능 환경**: macOS dev box (F3 구현·테스트)
- **Google Workspace 계정**: ADR-0003 — token 발급용. OAuth 클라이언트 등록 + drive.readonly scope
- **Test Workspace + `wikihub-test/` 폴더 + fixture 파일 3~5개** (L2 정합): E2E test용. V4 의도적 403 trigger 시 production credentials 손상 차단 — 별도 OAuth client 또는 권한 회수 후 복구 절차 포함
- **Python 3.11+** + venv 또는 uv

## 다음 단계

본 plan.md 확정 후 → `analysis_and_design.md`:
1. gws 인터페이스 실증 (changes.list, files.export, credentials env var) — F3가 첫 ADR-0014 verifier
2. Python 모듈 구조 결정 (ADR-0016 후보)
3. error 분류 매핑 표 확정 (ADR-0017 후보)
4. test 전략 (mocked gws vs sandbox vault)
5. v0.2.6 binary extraction 패턴 lift

Step 3 = 실제 코드 작성. Step 4 = 멀티모델 code review.
