# ADR-0003: 헤드리스 OAuth 전략

- **Status**: Superseded
- **Date**: 2026-05-13
- **Feature**: features/20260513_v030_initial_architecture
- **Supersedes**: 없음
- **Superseded by**: ADR-0029 (Service Account 기반 Drive 인증 — 2026-05-17 V<N> Phase 2 진입 시점 채택)

## Context

WikiHub v0.1.0의 OCI ARM Ubuntu 서버는 GUI 없는 헤드리스 환경이다. WikiCurate v0.2.5의 OAuth 흐름은 `flow.run_local_server()`로 브라우저를 띄우는 방식이라 서버에 부적합. Google Drive API(`drive.readonly`) 접근을 위한 OAuth 인증 방식을 결정해야 한다.

**숨은 제약**: Google OAuth refresh token 만료 정책

| 앱 상태 | refresh token 수명 |
|---|---|
| Production 모드(검증 완료) | 만료 없음 |
| Testing 모드 | **7일** 후 강제 만료 |
| Internal(Workspace 한정) | 만료 없음 |

`drive.readonly`는 restricted scope라 Personal Gmail로 Production 모드 진입에는 Google 검증 절차(수주~수개월) 필요.

## Considered Options

- **(α) Personal + Testing 모드 + device-code flow**: 서버에서 URL+코드 출력 → 폰으로 인증. 매주 재인증
- **(β) Personal + Testing 모드 + token-scp**: macOS dev box에서 OAuth → `.pickle` scp → 서버. 매주 재발급 + 복사
- **(γ) Workspace 전환 + Internal 사용자 유형 + token-scp**: refresh token 무제한. 1회 발급 후 운영 안정

> 옵션 상세 비교는 [features/20260513_v030_initial_architecture/analysis_and_design.md](../../features/20260513_v030_initial_architecture/analysis_and_design.md) §3.4 미결 3 참조.

## Decision

**채택**: (γ) Google Workspace 전환 후 token-scp

**v0.1.0 운영 시작의 선결 조건으로 Google Workspace 마이그레이션을 둔다.** 마이그레이션 완료 후 다음 흐름:

1. Google Cloud Console에서 OAuth 클라이언트 생성, User Type = Internal
2. macOS dev box에서 1회 OAuth(`flow.run_local_server()` 가능)로 `token_{profile}.pickle` 발급
3. `scp token_{profile}.pickle user@oci:/opt/wikihub/.credentials/`
4. 이후 서버는 pickle의 refresh token으로 access token을 무제한 자동 갱신

**이유**:
- **운영 부담 0**: α/β는 매주 사람 개입 필요(7일 refresh 만료). 24/7 daemon 운영 목표와 정면 충돌
- **헤드리스 친화**: 토큰만 있으면 서버는 완전 무인 운영
- **device-code의 환상**: device-code도 7일 사이클을 해소하지 못함. 운영 부담은 동일하고 오직 "어디서 인증하는가"만 다름
- **Personal+Production 검증 경로(미선택)**: 수주~수개월 소요로 운영 시작 시점이 늦어짐. 본 결정과 비교 시 Workspace 전환이 더 단순·즉시 가능

## Consequences

- **긍정**:
  - 운영 시작 후 OAuth 관련 정기 작업 0건
  - macOS dev box에서 1회 OAuth 절차로 끝 → 친숙한 GUI 브라우저 흐름 사용 가능
  - F3(vault_gdrive_api) 구현 단순화: device-code 폴링 로직 불필요

- **부정/제약**:
  - **v0.1.0 운영 시작이 Google Workspace 마이그레이션에 종속**. 마이그레이션 자체는 본 feature 범위 밖이며 사용자 책임
  - Workspace 계정 비용 발생(개인 Workspace 플랜)
  - 운영 대상 Drive가 Workspace 계정 소속으로 이주해야 함(Personal Drive 데이터 이관 작업)
  - macOS dev box 의존(token 발급 시점 한정) — 서버 단독으로는 인증 절차 수행 불가

- **후속 영향**:
  - **사전 작업(메인테이너)**: Workspace 가입 + Personal Drive → Workspace Drive 데이터 이관 + OAuth 클라이언트 등록(User Type = Internal). 본 작업은 F3 시작 전 선행
  - F3(vault_gdrive_api): OAuth 흐름은 macOS용 1회 발급 스크립트 + 서버용 token 로드 모듈로 분리. device-code 구현 불요
  - F4(systemd_orchestrator): `.credentials/token_*.pickle` 위치 표준화, 권한 600 강제
  - **재검토 트리거**: Workspace 마이그레이션이 비현실적이라고 판단되거나 다른 사용자 환경에서 본 시스템을 운영하고자 할 경우 본 ADR을 superseded 처리하고 device-code flow 기반 신규 ADR로 대체
