# ADR-0009: `/setup`의 책임 — wikihub.yaml → systemd 동기화 + 환경 검증

- **Status**: Accepted
- **Date**: 2026-05-13 / 2026-05-18 (Note: yaml writer 책임 명시 확장)
- **Feature**: features/20260513_wikihub_schema_v1
- **Supersedes**: 없음
- **Superseded by**: 없음 (supplement: ADR-0022 + ADR-0031 — yaml writer 책임 확장)

> **Note (2026-05-18, feature `install_scope_reduction`)**: 본 ADR §Decision §"1. 환경 검증 (read-only)" 의 **"read-only"** 표현이 ADR-0022 (Step 6 `bootstrap_allowed: true → false` atomic write) 와 ADR-0031 (Step 0 template materialization + drift fix) 이후 더 이상 정확하지 않다. `/wh:setup` 은 다음 책임을 추가로 보유:
>
> ### 4. yaml writer (Step 0 + Step 6 — ADR-0022·ADR-0031 정본)
>
> - **Step 0** (ADR-0031): `wikihub.yaml` 부재 시 `wikihub.yaml.example` 을 template 으로 read → derived 5필드 patching → atomic write. 존재 시 install-derived 필드 drift 검출 + (대화 모드) confirm prompt + (비대화 fallback) 보존+보고.
> - **Step 6** (ADR-0022): 첫 ingest 성공 후 `bootstrap_allowed: true → false` atomic write.
> - 두 writer 는 동일 helper (`scripts/lib/yaml_writer.py` — ADR-0031 §Decision D) 호출 — atomic lock + 주석 보존 정합.
>
> 본 책임 확장은 ADR-0031 의 §Consequences "후속 영향" 에 명시. supersede 아님 — 본 ADR 의 §Decision 1·2·3 (환경 검증·systemd unit 동기화·보고) 은 유지 + §4 추가.

## Context

v0.2.6의 `/setup`은 초기 설치 시 의존성 점검(openpyxl 등), Google OAuth 설정, graphify 설치, 그래프 빌드를 했다. wikihub v0.1.0은 운영 모델이 다르다:

- `wikihub.yaml`이 운영 정본 (F1 §4.3) — 메인테이너가 수기 편집
- systemd timer가 ingest·lint 자동 실행 (ADR-0006·0008)
- timer 주기·vault 등록·인터벌은 `wikihub.yaml`에 정의
- F4(systemd_orchestrator)가 unit template 정의

위 환경에서 `/setup`의 v0.2.6 책임 중 다수가 wikihub에서는 다른 곳으로 이관됨:
- 의존성 점검 → F4 `deploy.sh`
- OAuth 설정 → ADR-0003 (메인테이너 수기 §4.7.1·F1)
- graphify 설치 → F4 `deploy.sh`

남는 책임 + 신규 책임:
- wiki/ 디렉토리 구조 검증·생성
- `wikihub.yaml`의 값을 systemd unit 파일에 반영 (특히 timer 주기)
- OAuth 토큰 유효성 점검
- 환경 일관성 점검

## Considered Options

- **(α) /setup 폐기**: 메인테이너가 yaml 편집 + F4 deploy.sh가 모두 처리. 명령 1개 제거
- **(β) v0.2.6 그대로 lift**: 설치과정 절차 (단 모델 변경으로 대다수 절차가 불필요)
- **(γ) 재정의 — yaml→systemd 동기화 + 환경 검증 helper**: yaml은 메인테이너 정본, /setup이 그 값을 systemd unit으로 반영 + 환경 점검

## Decision

**채택**: (γ) yaml→systemd 동기화 + 환경 검증 helper

`/setup`의 책임 (정본):

### 1. 환경 검증 (read-only)
- `wikihub.yaml` 존재 + 스키마 검증 (`vaults[*].id` 형식, type 인식 가능, local_path 쓰기 권한, etc.)
- vault별 OAuth 토큰 존재 + 유효성 점검 (`creds.valid` 또는 refresh 가능)
- `wiki/` 디렉토리 + 4 카테고리 + `_lint/` + vault별 `sources/{vault}/` 존재 (없으면 생성)
- `_state/<vault_id>/` 디렉토리 존재 (없으면 생성, 빈 cursor·file_map·retry 초기화)
- agent CLI 실행 가능 (`hermes -z "/help"` 또는 equivalent)

### 2. systemd unit 동기화 (write)
`wikihub.yaml`을 source of truth로, 다음 unit 파일을 갱신:

- vault별 `<vault_id>-ingest.timer` — `OnUnitInactiveSec = wikihub.yaml.vaults[<vault_id>].sync_interval_sec`
- vault별 `<vault_id>-ingest.service` — `ExecStart=hermes -z "/ingest --vault <vault_id>"`
- 단일 `lint.timer` — `OnUnitInactiveSec = wikihub.yaml.operations.lint_interval_hours * 3600`
- 단일 `lint.service` — `ExecStart=hermes -z "/lint"`
- 단일 `ops-alert.service` — OnFailure 트리거용
- (F4 검토 후) 필요 시 `hermes.service` (Hermes daemon)

unit 파일은 `~/.config/systemd/user/`에 생성 후 `systemctl --user daemon-reload`. enable·start는 정책에 따라:
- `--enable` 플래그 시 자동 활성화
- 기본은 unit 파일만 생성·갱신 (메인테이너가 직접 enable)

### 3. 보고
- 환경 검증 결과 (각 항목 OK/FAIL)
- 갱신된 unit 파일 목록
- 다음 권장 액션 (예: "systemctl --user enable --now gdrive-ingest.timer")

**호출 시점**:
- 신규 vault 등록 후 (메인테이너가 yaml에 vault 추가 → `/setup`)
- timer 주기 변경 후 (yaml의 interval 수정 → `/setup`)
- 점검 목적의 주기적 호출 가능 (cron 아님, on-demand)

**이유**:
- **wikihub.yaml = 단일 정본**: 모든 운영 값의 single source of truth. /setup이 그 값을 systemd로 전파
- **메인테이너 의사결정 일관**: yaml 편집 → /setup 실행 → systemd 반영. 일관된 절차
- **self-maintaining 목표 정합**: timer 주기 변경도 yaml 편집 + /setup 1회 호출로 완료
- **F4 deploy.sh와 책임 분리**: deploy.sh = 코드·정본 파일 배포, /setup = 운영 상태 동기화. deploy.sh가 unit template 설치, /setup이 yaml 값으로 instance화
- **(α) 기각**: yaml→unit 동기화를 사람이 하면 실수 위험. 자동화 필요
- **(β) 기각**: 모델이 달라 v0.2.6 절차 대다수 무의미

## Consequences

- **긍정**:
  - yaml 변경 후 일관된 적용 절차 (`/setup` 1회)
  - 신규 vault 등록도 동일 패턴 (yaml 추가 → /setup)
  - F4 deploy.sh와 책임 분리 깔끔 (배포 vs 동기화)
  - 환경 검증 entry point 통합

- **부정/제약**:
  - `/setup` 호출 시점이 명시적 — 메인테이너가 yaml 편집 후 잊으면 systemd 미반영 (단, 다음 timer 발사 때 기존 unit으로 실행되어 silent 동작)
  - unit 파일 직접 수정한 메인테이너의 수정이 /setup에 의해 덮어쓰임 (yaml이 정본이므로 의도된 동작이지만 surprise 가능)
  - F4 unit template과의 결합 — template 변경 시 /setup도 반영 필요

- **후속 영향**:
  - F2 `_system/commands/setup.md`: 본 책임 그대로 명세
  - F2 wiki-schema: `_state/<vault_id>/` 초기화 정책 명시
  - F2 wikihub.yaml schema: `operations.lint_interval_hours` 추가
  - F4(systemd_orchestrator): unit template은 placeholder 포함(`{{vault_id}}`, `{{interval}}`). `/setup`이 template + yaml 값으로 instance화
  - **재검토 트리거**: 멀티 운영자 환경에서 yaml ↔ unit drift가 발생하거나, yaml 편집 → /setup 누락이 빈번하면 자동 sync(파일 watcher) 도입 검토
