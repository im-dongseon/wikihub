# ADR-0004: Google Drive 접근 메커니즘

- **Status**: Superseded
- **Date**: 2026-05-13
- **Feature**: features/20260513_v030_initial_architecture
- **Supersedes**: 없음
- **Superseded by**: ADR-0014

> 본 결정은 F2 종료 후 F3 plan 발의 시점에 ADR-0014로 supersede됨. 메인테이너의 reverse 사유는 gws의 빠른 versioning(alpha 우려 약화) + agent-friendly 호출 방식 + 구현 분량 절감. ADR-0014 참조.

## Context

WikiHub의 `gdrive_api` vault type(F3 구현 예정)이 Google Drive에 접근하는 방식을 결정해야 한다. 본 결정은 ADR-0002(Hermes 호출은 subprocess CLI 패턴)와 ADR-0003(Workspace + token-scp OAuth)이 확정된 후 설계 진행 중 surfacing되었다.

설계상 두 갈래가 존재한다.

1. Google 공식 Python SDK(`google-api-python-client`)를 직접 호출
2. 외부 도구 `googleworkspace/cli`(gws) — Discovery Service 기반으로 모든 Workspace API를 CLI로 노출하는 Rust 바이너리. ADR-0002의 subprocess 패턴과 대칭

본 ADR은 둘 중 v0.1.0 운영 사이클에 어느 쪽을 채택할지 결정한다.

## Considered Options

- **(α) Direct Drive API**: `google-api-python-client` 직접 호출. F3에서 Python 모듈로 구현
- **(β) gws CLI subprocess**: `gws drive changes list ...`, `gws drive files export ...`를 subprocess로 호출. 헤드리스 OAuth는 `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` 환경변수

비교의 상세 표는 [features/20260513_v030_initial_architecture/analysis_and_design.md](../../features/20260513_v030_initial_architecture/analysis_and_design.md) §4 작성 중 추가된 검토 노트 참조(본 ADR에 결과만 기록).

## Decision

**채택**: (α) Direct Drive API

**이유**:

- **공식 지원 / SLA**: Google 공식 SDK는 안정 API. gws는 명문상 "not officially supported"이며 알파(pre-v1.0, "expect breaking changes")
- **sync layer는 foundational**: 데이터 흐름의 진입점이므로 운영 daemon이 의존하는 라이브러리는 안정·예측 가능해야 함. 알파 의존성은 운영 부담
- **세분화된 에러 처리**: 본 feature §4.2.3에서 `VaultSyncRetryable` vs `VaultSyncFatal` 분류를 위해 HTTP status·reason 코드를 직접 읽어야 정확함. gws의 5단계 exit code(0/1/2/3/4/5)는 세분도 부족
- **검증 부담**: gws의 `drive.changes.list`·`drive.files.export`는 Discovery 동적 노출로 호출은 가능하지만 pagination·error semantics가 검증되지 않음. v0.1.0 일정 안에 검증 비용을 떠안기 어려움
- **상태 영속화 책임**: cursor·file_map·retry 큐 atomic write 책임은 어느 쪽이든 sync 스크립트 측이므로, 라이브러리 선택이 이쪽 복잡도를 줄여주지 않음

**기각된 (β)의 매력 (포기하는 가치)**:
- 구현 분량 절감 (수백 줄 → 수십 줄)
- ADR-0002와 패턴 대칭(둘 다 subprocess)
- 향후 Sheets/Calendar/Chat 통합 시 단일 도구로 확장

## Consequences

- **긍정**:
  - F3 구현이 well-trodden path 위에서 진행됨. 예시·trouble-shooting 자료 풍부
  - 에러 시맨틱·MIME export 제어가 코드 레벨에서 명시적
  - Drive API의 breaking change는 Google의 deprecation policy 보호 안에 있음

- **부정/제약**:
  - 구현 분량 증가 (Python Drive 클라이언트 boilerplate)
  - ADR-0002와 패턴 비대칭 (Hermes는 subprocess, Drive는 라이브러리)
  - Sheets/Calendar 등 향후 Workspace 확장 시에도 동일하게 직접 API 호출 코드를 작성하거나 본 ADR을 재검토해야 함

- **후속 영향**:
  - F3(vault_gdrive_api): `google-api-python-client` + `google-auth` 기반 구현. `drive.changes.list`, `drive.files.export`, `drive.files.get` 메서드 사용. MIME export map은 `wikihub.yaml.vaults[*].options.export_mime_map`(§4.3.1) 참조
  - 외부 vault tool로 gws를 메인테이너 개인 도구(개발 보조)로 활용하는 것은 본 ADR 범위 밖이며 자유
  - **재검토 트리거**: 
    - gws가 stable v1.0 도달하고 6개월 이상 breaking change 없음 확인된 경우
    - Drive 외 Google Workspace API(Sheets, Calendar 등)와의 통합 필요성이 다수 발생해 단일 도구 표준화가 운영상 유리한 경우
    - 이 중 하나가 충족되면 본 ADR을 superseded 처리하고 신규 ADR로 gws 채택 재평가
