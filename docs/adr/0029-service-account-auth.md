# ADR-0029: Service Account 기반 Drive 인증 — OAuth 대체

- **Status**: Accepted (2026-05-17, V<N> Phase 2 acceptance gate 11건 모두 통과)
- **Date**: 2026-05-17 (Proposed) → 2026-05-17 (Accepted)
- **Feature**: features/20260514_install_runtime (V<N> Phase 2 진입 시점)
- **Supersedes**: ADR-0003
- **Superseded by**: 없음

## Context

ADR-0003 은 v0.1.0 의 헤드리스 OAuth 전략으로 **Workspace Internal user-type + token-scp** 를 결정. 핵심 동기: refresh token 7일 만료 회피 (Testing 모드) + 헤드리스 환경 친화.

V8 acceptance gate (2026-05-17) 통과 후 V<N> Phase 2 진입 시점에 ADR-0003 의 두 가지 운영 부담 surface:

1. **Workspace 마이그레이션 진입 장벽**: ADR-0003 의 핵심 acceptance 조건 (Personal → Workspace 마이그레이션) 이 운영 시작의 선결 조건. Workspace 미가입 사용자 (= 본 V<N> 검증 환경 포함) 는 OAuth Production 검증 수개월 대기 또는 Testing 모드 (7일 사이클) 양자택일.
2. **interactive OAuth flow 의존**: macOS dev box 의 `flow.run_local_server()` 1회 OAuth + scp. V<N> 검증 (특히 V13~V19, V18 — OAuth revoke 감지) 매번 token 발급/배포 필요. 자동화·반복 검증 친화도 낮음.

추가로 V8 hand-check 에서 gws CLI 가 SA 인증을 `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` env var 로 지원 확인 (user/SA JSON 둘 다 수용). rclone 도 `service_account_file` 옵션으로 SA 지원. 두 도구 모두 OAuth 와 SA 를 호환 — 책임 분리 (ADR-0027) 영향 없음.

본 ADR 은 ADR-0003 의 Workspace+OAuth+token-scp 모델을 **Service Account (JSON key) 기반 인증** 으로 전환. ADR-0003 Superseded.

## Considered Options

**인증 mechanism**:
- (α) **OAuth Workspace Internal + token-scp** (ADR-0003 기존)
- **(β) Service Account + JSON key file** — 본 ADR 채택
- (γ) Application Default Credentials (ADC) — gcloud auth + Workload Identity Federation

**Drive 폴더 권한 모델 (SA 채택 시)**:
- (P1) **명시 공유 (Editor 또는 Viewer)** — SA 이메일을 vault 폴더에 명시 공유. 메인테이너 1회 작업.
- (P2) Domain-wide Delegation — Workspace 도메인 모든 사용자 impersonate. SA 가 user 위임 — 더 강한 권한. 본 use case 과한 권한.

**SA 키 발급 위치**:
- (K1) **Google Cloud Console + JSON 다운로드** — 메인테이너 1회 발급. install.sh 영향 없음.
- (K2) Workload Identity Federation — keyless. OCI 서버를 GCP 서비스로 인식 설정 필요. v0.1.0 과한 범위.

**SA 키 배포**:
- (D1) **메인테이너 scp** — dev box 에서 OCI 서버로 scp + chmod 0600. 기존 ADR-0003 의 scp 절차 1:1 대체.
- (D2) Secret manager (Vault·AWS SM·GCP SM) — 외부 의존성 추가. v0.1.0 과한 범위.

> 옵션 상세 비교 — `features/20260514_install_runtime/analysis_and_design.md` §12 참조.

## Decision

**채택**: (β) Service Account + JSON key + (P1) 명시 공유 + (K1) Cloud Console 발급 + (D1) scp 배포.

**구체적 결정**:
- 인증: SA JSON key file. `gws CLI` 는 `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=$SA_PATH`, `rclone` 은 `rclone.conf` 의 `service_account_file = $SA_PATH`.
- credentials JSON 의 `type` 필드: `service_account` (기존 `authorized_user` 대체).
- Drive 폴더 권한: 메인테이너가 GCP Console 에서 SA 이메일 (`<sa-name>@<project>.iam.gserviceaccount.com`) 을 vault 폴더에 **Editor** 공유 (rclone mount 의 write 가정 위한 — vault 자체 mount 정신). 단 read-only 운영도 가능 (vfs cache 다운로드만).
- 키 발급: Google Cloud Console → IAM → Service Accounts → JSON 키 다운로드 → macOS dev box 1회.
- 배포: scp → OCI `~/wikihub-instance/.credentials/sa_<vault_id>.json` → chmod 0600. wikihub.yaml 의 `credentials_path` 가 본 파일 지정.

**이유**:
- (β) SA: refresh token 7일 문제 자체 부재 — Workspace 마이그레이션 의존 제거. Personal Google 도 동등하게 운영 가능 (SA 는 Google Cloud project 의 IAM 자원, Workspace 무관).
- (P1) 명시 공유: trust boundary narrow — vault 폴더만 접근, 다른 사용자 데이터 자동 접근 없음. ADR-0003 OAuth 의 user-token (ownedByMe 전체 접근) 대비 정합성 향상.
- (K1) Cloud Console: keyless (Workload Identity) 는 OCI ↔ GCP 신뢰 설정 (Workload Identity Federation) 필요 — v0.1.0 범위 밖.
- (D1) scp: ADR-0003 의 배포 모델 (`scp token_*.pickle`) 과 1:1 대체 — 운영자 학습 부담 0.

**기각 사유**:
- (α) ADR-0003: 위 §Context 의 운영 부담 누적. SA 채택으로 진입 장벽 제거.
- (γ) ADC: gcloud + Workload Identity 설정 필요. install.sh 외부 의존 binary 추가 + supply chain surface 증가.
- (P2) Domain-wide Delegation: Workspace 전제 + 폴더 외 권한 — 과한 trust.
- (K2): 위 (K1) 사유 동일.
- (D2): 외부 secret manager 의존 — v0.1.0 범위 밖.

## Consequences

**긍정**:
- ADR-0003 의 Workspace 마이그레이션 의존 제거 — Personal Google 으로 v0.1.0 운영 가능. V<N> 검증 환경도 동일.
- refresh token 7일 만료 (Testing 모드) 문제 자체 부재 — SA 키는 명시 revoke 전까지 유효.
- gws + rclone 둘 다 동일 SA JSON 사용 (책임 분리 ADR-0027 영향 없음).
- trust boundary narrow — vault 폴더만 명시 공유. ADR-0003 의 ownedByMe 전체 접근 대비 보안 향상.
- V<N> 검증 (특히 V18 OAuth revoke 감지) 의 mechanism 단순화 — SA 키 revoke 는 Cloud Console 1회 클릭.
- `scripts/auth_gdrive.py` (OAuth flow 도구) 제거 가능 — 코드 표면적 감소.

**부정/제약**:
- 메인테이너가 SA 이메일을 vault 폴더에 명시 공유하는 1회 작업. 폴더 추가 시마다 반복 (Personal/Workspace Drive UI 의 "Share" 메뉴).
- Personal Drive 의 SA 사용 제약: SA 가 ownedBy 가 될 수 없음 — read/write 는 가능하나 "Storage" 는 항상 메인테이너 계정 quota 에 누적. v0.1.0 의 vault polling/mount 시나리오는 OK.
- SA 키 파일 (JSON) 노출 시 vault 접근 가능 — chmod 0600 + scp 만 + git ignore 필수. ADR-0003 의 OAuth token 보호와 동일 수준.
- gws CLI 의 SA env var (`GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`) 가 user JSON 과 SA JSON 둘 다 수용 — credentials.py 의 `type` 분기 검증 필요 (보안 측면에서 어떤 종류든 동작은 정합).

**후속 영향**:
- ADR-0003 Status `Accepted` → `Superseded`. `Superseded by: ADR-0029` 명시. 본문은 그대로 (역사적 맥락 보존).
- `scripts/lib/credentials.py:assert_credentials` 의 `type` 검증 — `authorized_user` → `service_account`. required fields 도 SA 용 (`private_key`, `client_email`).
- `scripts/lib/gws.py` 영향 없음 — `env_extra` 로 `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` 받는 구조 그대로.
- `scripts/auth_gdrive.py` 제거 — OAuth flow 불필요.
- `_system/commands/setup.md` Step 5.5 — rclone OAuth interactive → `rclone config create gdrive drive service_account_file <path>` 1줄.
- `wikihub.yaml.example` — `credentials_path` 주석 갱신 (OAuth token → SA JSON key).
- 운영 가정 갱신 (progress.md §운영 환경 가정): "Google Workspace Internal user-type OAuth" → "Google Cloud project 의 Service Account JSON key (Personal Google 도 OK)".
- V18 (rclone OAuth revoke 감지) — SA 채택 후엔 "SA 키 revoke 감지" 로 의미 갱신. 본 검증 mechanism 은 동일 (rclone stderr 패턴 매칭, `_RCLONE_AUTH_PATTERNS`).
- 재검토 트리거: SA 키 노출 사고 발생 시 (D2) secret manager 검토 또는 (K2) Workload Identity Federation 으로 keyless 전환.
