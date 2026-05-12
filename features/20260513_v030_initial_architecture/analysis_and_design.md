# Analysis & Design: WikiHub v0.1.0 초기 아키텍처

- **Feature ID**: `20260513_v030_initial_architecture`
- **작성일**: 2026-05-13 (KST)
- **목적 범위**: 본 feature는 **계획 + 분석및설계** 단계만 다룬다. 구현은 본 문서를 기준으로 후속 feature로 분리한다.

---

## 1. 배경 및 목적

### 1.1 출발점

`WikiCurate` v0.2.6은 macOS 로컬 단일 vault 모델로 안정화된 LLM 기반 자율 지식 관리 시스템이다. 핵심 구성:

- 단일 vault: `_system/` + `wiki/` + `raw/` + `wiki-inbox/`
- 자동화: launchd + fswatch + `wiki-inbox → raw` 이동 + 10분 주기 `/ingest` + `/lint` + graphify
- 에이전트: codex / claude / gemini CLI fallback chain
- 지원 포맷: MD/PDF/Office/CSV/TSV/Google 스텁(.gdoc/.gsheet/.gslides)

### 1.2 새 운영 요구사항

- **운영 환경**: OCI ARM Ubuntu 서버 (24/7 daemon 운영)
- **인터페이스**: Telegram 연동된 `Hermes` 에이전트 (자연어 질의·관리)
- **소스 백엔드**: Google Drive (1차), 향후 개인 NAS, Notion 등 확장 가능성
- **사용자 경험**: 사용자는 Google Drive에 파일을 떨구기만 하고, 위키 검색·관리는 Telegram에서 자연어로 처리

### 1.3 본 feature의 목적

WikiCurate v0.2.6은 macOS 로컬 단일 vault 가정 위에 설계되어 새 요구사항(서버 운영, 다중 소스, daemon 에이전트)과 인프라 레이어가 부적합하다. 따라서:

- v0.2.6 리포지토리는 **reference로 보존**하고
- 신규 리포지토리 `wikihub`에서 **server-first + multi-vault** 모델로 v0.1.0을 출범한다
- 본 feature는 그 v0.1.0의 **초기 아키텍처를 정의**하는 것을 목적으로 한다

지식 모델(위키 페이지 형식, 4-카테고리, `[[link]]` 컨벤션, 명령어 의미론)과 메인테이너 방법론(features/ 워크플로우)은 v0.2.6에서 그대로 이식한다.

---

## 2. 현행 진단 (v0.2.6의 부적합 항목)

### 2.1 토폴로지

| 항목 | 진단 | 근거 |
|---|---|---|
| 단일 vault 모델 | 다중 소스 백엔드 통합 불가 | "1 vault = 1 wiki + 1 raw + 1 wiki-inbox" 가정. Google Drive와 NAS를 하나의 위키로 합치려면 각각 독립 vault가 되거나, raw/가 다중 출처 디렉토리를 가리켜야 함 |
| `raw/` 내부 위치 | vault 외부 마운트와 충돌 | `raw/`는 `_system/`/`wiki/`와 같은 vault 디렉토리 안에 있어, raw 자체를 NAS 마운트 / Drive 미러로 두기 어려움 |
| `wiki-inbox/` mv 흐름 | Drive에는 mv 의미가 약함 | inbox→raw 이동은 사용자가 macOS Finder로 파일을 떨구는 워크플로우에 최적화. Drive에서는 파일이 "이미 정착"되어 있고 이동 개념이 부정합 |

### 2.2 인프라

| 항목 | 진단 | 근거 |
|---|---|---|
| launchd 의존 | Linux 서버 부적합 | macOS 전용 스케줄러 |
| fswatch 의존 | Linux는 inotify가 표준 | macOS 친화 도구. Google Drive 마운트 이벤트는 그조차도 불안정해서 v0.2.6에서 wiki-inbox로 감시 대상을 옮긴 이력 있음 |
| `/opt/homebrew/bin/*` 경로 | Linux에는 존재하지 않음 | Apple Silicon Homebrew 경로 의존 |
| 시스템 Python 사용 | Ubuntu 22.04+ PEP 668 차단 | `pip3 install ...` 직접 호출이 externally-managed-environment로 거부됨 |
| OAuth `run_local_server()` | 헤드리스 서버 부적합 | v0.2.5 도입한 흐름이 브라우저를 띄움. OCI 서버에는 GUI 없음 |

### 2.3 소스 흡수

| 항목 | 진단 | 근거 |
|---|---|---|
| Google 스텁 다단 fallback | 임시방편 | `.gdoc`/`.gsheet`/`.gslides`에 대해 OAuth helper → 인증 실패 시 URL만 기록. Drive API를 직접 호출하면 export로 정상 콘텐츠 획득 가능 |
| daily-rescan Pass 1 | redundant 가능 | 스텁 파일의 콘텐츠 변경을 감지하지 못해 6회/일 강제 재ingest. Drive API `changes.list`가 권위 있는 변경 소스 |
| `wiki-schema.md`의 GSHEET/GDOC/GSLIDES + DOC/XLS/PPT 섹션 | 비대화 | 약 250줄 분량. API 기반 동기화로 통합 시 사라질 수 있는 분량 |

### 2.4 에이전트 호출

| 항목 | 진단 | 근거 |
|---|---|---|
| `watch-ingest.sh`의 CLI spawn 패턴 | Hermes(daemon) 결합 어려움 | codex/claude/gemini CLI를 매번 spawn하는 방식. Hermes는 Telegram을 polling하는 long-running daemon이므로 RPC/IPC로 트리거 받는 모델이 자연스러움 |
| 에이전트 fallback chain 하드코딩 | 단일 에이전트 운영 모델에 부적합 | 서버 운영에서는 Hermes 하나만 띄우는 게 일반적 |

---

## 3. 개정 범위

### 3.1 본 feature가 결정하는 것

본 feature는 다음을 **정의**한다 (구현 X):

1. **토폴로지**: wikihub 인스턴스(`_system/` + `wiki/` + `_state/`) + 외부 vault 디렉토리 N개
2. **Vault 추상**: vault type(`gdrive_api`, `directory`, 향후 추가)별 sync 인터페이스 명세
3. **소스 흡수 메커니즘**:
   - 결정론적 sync 스크립트가 vault에 변경 콘텐츠를 떨어뜨림
   - 변경 감지 시 Hermes에 `/ingest` 트리거
   - inbox 개념 폐기 (Drive에서 사용자가 직접 떨굼)
4. **에이전트 호출 모델**:
   - Hermes daemon이 `/ingest`, `/lint`, `/query`, `/graphify` 수행
   - sync ↔ Hermes 분리 (sync 실패와 agent 실패가 격리됨)
   - Hermes 호출 인터페이스(CLI/HTTP/IPC)는 본 단계에서 결정
5. **명령어 의미론** (v0.2.6 lift + multi-vault 변형):
   - `/ingest`: 등록 vault 목록 순회 → type별 sync 트리거 → vault-aware 처리
   - `/lint`, `/query`, `/graphify`: vault-aware
   - `/setup`: 신규 vault 등록 + 의존성 확인
6. **wiki 페이지 모델** (v0.2.6 lift + multi-vault 변형):
   - 4-카테고리 유지: `sources/`, `entities/`, `concepts/`, `analyses/`
   - `sources/` 하위 vault namespace 부여 (정책은 미결 1)
   - `sources:` frontmatter에 vault prefix
   - 파일명 = `title:` = `[[link]]` invariant 유지
   - `index.md` / `log.md` 컨벤션 유지 (log.md 포맷에 vault 식별자 포함)
7. **운영 환경**:
   - Linux/systemd (Ubuntu ARM, OCI 타깃)
   - macOS 미지원 (개발은 가능, 배포는 Linux 전용)
   - OAuth는 헤드리스 친화 방식 (구체 방식은 미결 3)

### 3.2 본 feature의 산출물

- `features/20260513_v030_initial_architecture/plan.md` (Step 1)
- `features/20260513_v030_initial_architecture/analysis_and_design.md` (본 문서, Step 2)
- `features/20260513_v030_initial_architecture/design_review_N.md` (Step 2 리뷰, 선택)

### 3.3 본 feature가 결정하지 않는 것 (후속 feature로 이관)

| 후속 Feature 후보 | 범위 |
|---|---|
| F2: `wikihub_schema_v1` | `_system/wiki-schema.md`(Operator Guide) + `_system/commands/*` 구현. 본 analysis_and_design.md의 명세를 정본으로 변환 |
| F3: `vault_gdrive_api` | `scripts/gdrive-sync.py` + Drive API + OAuth 헤드리스 + cursor/file_map 영속화 |
| F4: `systemd_orchestrator` | `deploy.sh` + systemd user units (`.service`/`.timer`) + `wikihub.yaml` 스키마 + 로깅 |
| F5: `hermes_adapter` | Hermes 호출 어댑터(설계서 미결 2 결정에 따라). 자동 트리거 흐름 및 수동 명령 처리 |
| F6: `vault_directory` (선택) | NAS / 로컬 디렉토리 vault type. inotifywait 통합. NAS 운영 시작 시점 |

본 문서의 설계 섹션은 위 후속 feature들이 참조할 인터페이스(파일 경로, 설정 키, 데이터 형식)를 정의한다.

### 3.4 미결 사항 (본 단계에서 결정)

본 문서의 설계 섹션에서 다음 3건을 명시적으로 결정한다.

#### 미결 1. 소스 페이지 충돌 정책

`vault-gdrive`에 `report.md`가 있고 `vault-nas`에도 `report.md`가 있을 때 wiki/sources/ 처리 방식.

| 옵션 | 설명 | 장점 | 단점 |
|---|---|---|---|
| (α) Vault namespace 분리 | `wiki/sources/gdrive/report.md`, `wiki/sources/nas/report.md` | 결정론적, 예측 가능 | 같은 문서가 두 vault에 있어도 두 페이지 |
| (β) Title 기반 merge | 한 페이지에 `sources: [gdrive/report.md, nas/report.md]` | 사용자에게 단일 페이지로 보임 | 동일성 판단을 에이전트에 위임 → 비결정적 |
| (γ) Hash dedup | 콘텐츠 해시 일치 시 자동 병합 | 정확한 동일성 | 편집 중 사본 등 거의 같은 문서를 강제 병합해 정보 손실 위험 |

**잠정 권장**: (α). 결정론과 예측 가능성을 우선. 추후 동일 문서 인지가 필요하면 별도 feature로 dedup 도입 가능.

#### 미결 2. Hermes 호출 인터페이스

sync 스크립트가 Hermes에 `/ingest` 트리거를 보내는 메커니즘.

| 옵션 | 설명 | 장점 | 단점 |
|---|---|---|---|
| CLI | `hermes invoke --command ingest` 같은 CLI 호출 | 간단, sync는 subprocess만 spawn | Hermes에 CLI 인터페이스 필요. 동시성 처리는 Hermes 책임 |
| HTTP | Hermes가 localhost HTTP 엔드포인트 노출 | 표준적, 도구 친화 | Hermes 측 HTTP 서버 구현 필요 |
| IPC (Unix socket / file flag / DBus) | OS-level 신호 | 의존성 적음 | 디버깅 어려움. Hermes 측 listener 필요 |

**결정에 필요한 정보**: Hermes 자체가 어떤 인터페이스를 제공/추가할 수 있는지. design 단계에서 Hermes 운영 모델을 같이 정한다.

#### 미결 3. OAuth 헤드리스 방식

Drive API 접근을 위한 OAuth 인증을 헤드리스 OCI 서버에서 처리하는 방법.

| 옵션 | 설명 | 장점 | 단점 |
|---|---|---|---|
| token-scp | 로컬 macOS에서 OAuth → 발급된 `token_{profile}.pickle`을 OCI로 scp 복사 | 즉시 구현 가능 | 토큰 만료 시 재발급 부담. refresh_token이 살아 있으면 자동 갱신되나 정책상 만료 가능 |
| device-code flow | 서버가 URL + 코드 출력 → 사용자가 폰으로 인증 | 자동화 친화, 만료 시 같은 절차로 재발급 | Google의 device-code 지원 스코프 확인 필요. drive.readonly는 일반적으로 지원 |

**잠정 권장**: device-code flow. 운영 자동화에 적합.

---

## 4. Definition of Done

본 feature의 완료 기준:

- [ ] **Step 1 (plan)**: `plan.md` 작성 및 사용자 확정
- [ ] **Step 2 (analysis & design)**: 본 문서 — 분석 섹션 사용자 검토 완료
- [ ] **Step 2 (analysis & design)**: 본 문서 — 설계 섹션 작성. 다음 항목 모두 포함:
  - [ ] 토폴로지 다이어그램 (디렉토리, 데이터 흐름)
  - [ ] vault type 인터페이스 명세 (sync 함수 signature, 상태 영속화 스키마)
  - [ ] `wikihub.yaml` 스키마 (vaults 목록, agent, 인터벌 등)
  - [ ] `_state/` 구조 (cursor, file_map, retry DB)
  - [ ] `wiki/sources/` 디렉토리 모델 (미결 1 결정 반영)
  - [ ] `sources:` frontmatter 포맷, `log.md` 포맷 (vault 식별자 포함)
  - [ ] Hermes 호출 인터페이스 (미결 2 결정 반영)
  - [ ] OAuth 헤드리스 흐름 (미결 3 결정 반영)
  - [ ] systemd unit 구조 (service/timer 분리, 사용자 vs 시스템 레벨)
  - [ ] 후속 feature(F2~F6)의 의존 관계와 분할 합의
- [ ] **Step 2 리뷰**: 멀티모델 design review 최소 1건 (Claude 컨텍스트 초기화 또는 Gemini/Codex) — 선택
- [ ] **Step 2 사용자 승인**: 본 문서 상단에 `approved: YYYY-MM-DD` 마커
- [ ] **Step 3 이후는 후속 feature로 이관**

본 feature는 본 문서 승인 시점에 종료된다. 후속 feature가 시작되면 본 feature는 종결.

---

## 5. 참조

- v0.2.6 reference: `/Users/ds.im/workspace/repo/wikicurate/`
  - 지식 모델: `_system/wiki-schema.md`
  - 명령어 의미론: `_system/commands/{ingest,lint,query,graphify,setup}.md`
  - 메인테이너 방법론: `AGENTS.md`, `docs/agent_dev_guide.md` (본 리포로 이식 완료)
  - 인프라 패턴: `scripts/watch-ingest.sh`, `scripts/watcher.sh`, `scripts/daily-rescan.sh`, `deploy.sh`
  - 배포 이력: `features/HISTORY.md`, `releases/CHANGELOG.md`
