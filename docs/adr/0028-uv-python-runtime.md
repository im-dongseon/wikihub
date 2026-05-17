# ADR-0028: uv 기반 Python runtime 관리 — install.sh Step 3 재설계

- **Status**: Accepted
- **Date**: 2026-05-17
- **Feature**: features/20260514_install_runtime (V8 surgical fix)
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

F4 v9 의 V8 1차 실수행 (Multipass Ubuntu 22.04.5 LTS aarch64) 결과 install.sh Step 1·3 에서 2건 결함 surface:

- **결함 #1**: `python3-venv` apt 패키지 부재로 `python3 -m venv` fail. Ubuntu 22.04 default 에 `python3` binary 는 있으나 `python3-venv` 는 별도 apt 패키지. Step 1 환경 검증 (`install.sh:171~179`) 이 binary 만 검증하고 venv 모듈 가용성 미검증 — 자체 surface 부재.
- **결함 #2**: venv 부분 생성 후 재실행 시 `bin/pip` 부재. Step 3 의 `[ -d "$VENV_PATH" ]` 분기 (`install.sh:235~241`) 가 빈 디렉토리도 "기존 사용" 으로 통과 — V11 (idempotency) 위반.

추가로 `progress.md:209` 운영 가정은 "Python 3.11 또는 3.12 apt 설치 가능" 인데, Ubuntu 22.04 apt default 는 Python 3.10. 3.11/3.12 설치는 deadsnakes PPA 또는 별도 채널 필요 — install.sh 의 fail-fast 가정과 충돌.

본 ADR 은 install.sh Step 1·3 의 Python 환경 관리 방식을 **uv 단독 + GitHub Releases binary supply chain** 으로 재설계.

## Considered Options

**(α) Python 환경 관리 도구**:
- (α1) `python3-venv` apt 의존 유지 + Step 1 검증 강화: 결함 #1 우회 가능하나 Python 3.11/3.12 pinning 부재. apt 외부 채널(deadsnakes PPA) 도입 시 supply chain 가정 약화.
- **(α2) uv 단독**: Python install (`uv python install 3.12`) + venv 생성 + 패키지 install 모두 uv. apt 의존 제거. 결함 #1·#2 자연 해결.
- (α3) mise + uv 조합: mise 가 Python + uv binary 관리. wikihub 는 현재 Python only — mise 의 다중 언어 강점 미활용. install.sh 외부 의존 binary 2개로 증가.

**(β) uv binary 설치 채널**:
- (β1) `curl -fsSL https://astral.sh/uv/install.sh | sh`: 공식 install script. 단순. install.sh 자체가 curl-pipe (ADR-0023) 인데 내부에서 또 다른 curl-pipe 호출 — 트러스트 계층 추가, supply chain 가시성 저하.
- **(β2) GitHub Releases binary + SHA256 verify**: gws (ADR-0015) / rclone (ADR-0025) 와 동일 패턴. install.sh 내부 일관성 + mutable artifact 위협 차단.
- (β3) cargo install: Rust toolchain 의존 필요. install.sh 의 외부 의존성 폭증.

**(γ) Python 버전 pinning**:
- (γ1) Python 3.10 (Ubuntu 22.04 default): mise/uv 없이도 동작. wheel 호환성 일부 제한.
- (γ2) Python 3.11: 안정성 높음. 대부분 wheel 가용.
- **(γ3) Python 3.12**: 최신 stable. wheel 최적화. 운영 가정 `progress.md:209` 의 상한.

**(δ) uv version pinning**:
- (δ1) `latest` (자동): GitHub API rate limit 위협 (결함 #3 과 동일 패턴) + breaking change silent 도입.
- **(δ2) pinned + min/max range**: ADR-0025 패턴 (rclone `1.65.0` min, `1.99.99` max) 일관. install.sh 에서 `UV_VERSION` env override 가능.

## Decision

**채택**: (α2) uv 단독 + (β2) GitHub Releases binary + SHA256 + (γ3) Python 3.12 + (δ2) `UV_VERSION=0.11.14` pinned

**이유**:
- (α2): 결함 #1·#2 동시 해결. `uv venv` 는 자체 idempotent (기존 venv 검증 + 무효 시 재생성). `uv python install` 로 apt 외부 채널 불필요.
- (β2): install.sh 내부 supply chain 일관성 (gws/rclone 과 동일 패턴). astral-sh/uv 가 GitHub Releases 에 SHA256 sidecar 제공 — verify 가능.
- (γ3): `progress.md:209` 운영 가정 상한 + 최신 wheel 최적화.
- (δ2): ADR-0015·0025 의 version pinning 패턴 일관 + breaking change 방어. V8 재검증 후 latest tag 확인 시점에 `UV_VERSION` 갱신.

**기각 사유**:
- (α1): Python 3.10 강제 또는 deadsnakes PPA 외부 의존. 결함 #2 별도 fix 필요.
- (α3): wikihub 의 Python only 가정 + install.sh 외부 의존 최소화 원칙 위배.
- (β1): trust 계층 추가 + ADR-0023 의 supply chain 가시성 정신 약화.
- (γ1·γ2): 3.12 대비 명확한 이점 없음. 3.10 은 운영 가정 위배.
- (δ1): GitHub API rate limit (결함 #3) 동일 패턴 재발.

## Consequences

**긍정**:
- 결함 #1 (python3-venv 미감지) 해결 — apt 의존 제거.
- 결함 #2·#6 (venv idempotency) 해결 — `bin/python` 가용성 + 버전 일치 검증 분기 + 무효 시 wipe + `uv venv --seed` 재생성. `uv venv` 는 자체적으로는 기존 venv 존재 시 error 로 fail (`Caused by: A virtual environment already exists`), 명시적 검증·wipe 필요 (V8 2nd-run 에서 surface).
- Python 3.12 pinned — 운영 가정 정합.
- install.sh 내부 supply chain 패턴 일관 (gws·rclone·uv 모두 GitHub Releases + SHA256).
- `uv pip install` 속도 (pip 대비 10~100x) — install.sh 실행 시간 단축, V8 재검증 효율 상승.

**부정/제약**:
- 외부 의존 binary 1개 추가 (uv) — install.sh 코드 라인 ~70 라인 증가 (gws Step 4 패턴 재사용).
- `UV_VERSION` 의 정기 갱신 책임 — astral-sh/uv breaking change 모니터링 필요 (rclone `rclone_max_version` 패턴 일관).
- macOS dev box 의 install.sh dry-run 시 uv binary 의 darwin asset 분기 추가 가능성 — v0.1.0 범위 밖.
- `PYTHON_BIN` env var 제거 — `_step3_venv` 외 참조 없음 확인 완료.

**후속 영향**:
- ADR-0023 (curl-pipe one-liner) — uv install 도 같은 trust 모델 따름. 변경 없음.
- ADR-0015 (gws pinned version) — 동일 패턴 적용. uv 의 `_install_uv` 함수가 `_step4_gws` 의 sibling.
- ADR-0021 (reboot resilience) — uv binary 가 `$HOME/.local/bin/uv` 에 user-level 설치. systemd user unit 의 PATH 영향 없음 (venv path 만 referencing).
- 운영 가정 갱신: `progress.md:209` "Python 3.11 또는 3.12 apt 설치 가능" → "uv 가 Python 3.12 binary 자체 install (apt python3 의존 없음)".
- V8 재검증 후 결함 #3 (gws latest GitHub API rate limit) 가 후속 surface 예상 — 본 ADR 범위 밖, 별도 fix. 결함 #5 (unzip 미설치) 는 본 ADR 의 Step 1 surgical patch 로 같이 해결 (자동 apt install).
- V11 (idempotency) 검증 통과 — 검증 분기로 정상 venv skip + 무효 wipe + 재생성.
- 재검토 트리거: uv 0.12.x 또는 1.0 release 시 breaking change 확인 후 `UV_VERSION` 갱신.
