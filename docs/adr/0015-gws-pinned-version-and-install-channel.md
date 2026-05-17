# ADR-0015: gws pinned version + 설치 채널

- **Status**: Accepted
- **Date**: 2026-05-14 (Proposed) / 2026-05-17 (Accepted — V8 hand-check 결과 lock)
- **Feature**: features/20260514_install_runtime
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

ADR-0014 가 `gws` CLI (googleworkspace/cli) 를 Drive 접근 메커니즘으로 채택했지만, 두 결정 미확정:
1. **버전 pinning 값** — `latest` 추적 vs 특정 버전 고정
2. **설치 채널** — pip / npm / GitHub Releases binary / curl-installer

추가로 V6 (gws version pin) / V8 (asset 이름 hand-check) 결과로 두 가지 detail 도 lock 필요:
- asset 이름 명명 규약 (Rust 빌드 산출물의 target triple 사용 여부)
- `GWS_VERSION` install.sh default — `latest` 시 GitHub API rate limit 위협 (V8 1차 surface 결함 #3)

gws 가 alpha 단계 (ADR-0014 명시) 라 API breaking 가능 → 버전 정책 부재 시 install.sh 호출마다 동작 변경 위험.

## Considered Options

**버전 pinning**:
- **(α) F1**: V6 시점의 latest stable tag (GitHub Releases) — 메인테이너가 release 마다 수동 갱신.
- **(β) F2**: 특정 minor 고정 (예: `0.5.x`).
- **(γ) F3**: pinning 안 함 — `latest` 추적.

**설치 채널**:
- **(α) CH1**: curl-installer script (`gws-installer.sh | sh`).
- **(β) CH2**: GitHub Releases binary + shasum verify → `~/.local/bin/gws`.
- **(γ) CH3**: npm — `npm install -g @googleworkspace/cli`.

**asset 이름 명명 규약** (V8 hand-check 결과로 결정):
- (N1) `gws-${os}-${arch}.tar.gz` (V8 잠정 가설 — 보편적 GitHub Releases 패턴)
- **(N2) `google-workspace-cli-${rust_target_triple}.tar.gz`** (V8 hand-check 결과 — Rust 빌드 산출물)

**`GWS_VERSION` install.sh default**:
- (D1) `latest` — GitHub API 호출로 동적 조회 (V8 1차 surface 결함 #3: unauthenticated rate limit 60/h)
- **(D2) pinned value (예: `0.22.5`)** — 결정적 동작, env override 시 `latest` 분기 보존

> 옵션 상세 비교는 [features/20260514_install_runtime/analysis_and_design.md §3.6](../../features/20260514_install_runtime/analysis_and_design.md) 참조.

## Decision

**채택**:
- 버전 = **(α) F1** latest stable @ V8 시점 = **`0.22.5`** (2026-05-17 lock)
- 채널 = **(β) CH2** GitHub Releases binary + SHA256 verify → `$HOME/.local/bin/gws`
- asset 명명 = **(N2)** `google-workspace-cli-${rust_target_triple}.tar.gz` (V8 hand-check 정본)
- arch → target triple 매핑:
  - `aarch64`/`arm64` → `aarch64-unknown-linux-gnu`
  - `x86_64`/`amd64` → `x86_64-unknown-linux-gnu`
- `GWS_VERSION` install.sh default = **(D2)** `0.22.5` pinned, `latest` env override 분기 보존 (메인테이너 명시 호출 시만 GitHub API)

**이유**:
- F3 (pinning 안 함) 은 alpha 단계 gws 의 breaking change 누출 — 채택 못 함.
- F2 는 v0.1.0 에 과도 — V6 의 실제 stable 관측 후 결정 가능. V8 시점 = `0.22.5`.
- CH3 (npm) 는 Node.js 의존 추가 — v0.1.0 의 Python venv only 원칙과 어긋남.
- CH2 (binary + shasum) 가 가장 안전 (third-party installer script 신뢰 불필요).
- 배치 위치 `~/.local/bin/gws` 는 ADR-0020 의 user-level path 정합.
- N2: V8 실수행 결과 (Multipass Ubuntu 22.04.5 ARM64, 2026-05-17) — 실제 asset 이름은 `google-workspace-cli-aarch64-unknown-linux-gnu.tar.gz` (Rust 명명). tar 내부 구조는 가설 정합 (`./gws` 최상위 binary + `./LICENSE`·`./CHANGELOG.md`·`./README.md` + SHA256 sidecar `${asset}.sha256`).
- D2: V8 1차 surface 결함 #3 (GitHub API rate limit 403) 회피 + 운영 결정성. ADR-0023 (curl-pipe one-liner) 정신 정합 — 운영자 한 줄 호출이 always-reproducible.

## Consequences

- **긍정**:
  - install.sh 의 gws 설치가 idempotent + verify 가능. 메인테이너 override 용이.
  - V8 결함 #3·#4a 동시 해결.
  - asset 이름 lock — install.sh 의 추정 가설 제거.
- **부정/제약**:
  - `GWS_VERSION` 의 정기 갱신 책임 (gws release 마다 메인테이너 수동 update). ADR-0028 의 `UV_VERSION` 패턴 일관.
  - mass compromise (메인테이너 GitHub 계정 + 또는 GitHub 자체) 시 binary 변조 가능 — TLS + SHA256 만으로 mitigation 한도.
- **후속 영향**:
  - V8 통과 — 본 ADR Status `Accepted`.
  - v0.2.x 에서 GPG signature verify 추가 검토 (ADR-0023 의 supply chain 매트릭스 정합).
  - gws v0.23 이상 release 시 `GWS_VERSION` 갱신 검토 (breaking change 모니터링).
  - 재검토 트리거: gws 가 stable (v1.0) 진입 시 pinning 정책 (F1 → F2 검토).
