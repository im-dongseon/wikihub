# ADR-0023: install.sh 배포·호출 모델 — curl-pipe + clean install

- **Status**: Accepted
- **Date**: 2026-05-14
- **Feature**: features/20260514_install_runtime
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

ADR-0018 이 install.sh 를 단일 모델로 채택했지만 **실제 호출 방식** 미정. rustup·nodejs·ohmyzsh 처럼 한 줄 명령으로 호출 가능해야 운영자 학습 비용 최소화. 또한 update 시 기존 repo 의 in-place 갱신 (git pull) 의 edge case (detached HEAD, broken .git, in-place 편집 잔재) 를 회피하기 위해 **clean install pattern** 결정 필요.

## Considered Options

**배포·호출 모델**:
- **(α) H1**: curl-pipe (`curl -fsSL <URL>/install.sh | bash`) — install.sh 자체가 repo clone 책임.
- **(β) H2**: 메인테이너 사전 clone (`git clone … && ./install.sh`).
- **(γ) H3**: 별도 release artifact (tarball / installer binary).

**Update 패턴**:
- **(i)** git fetch + reset (incremental).
- **(ii)** 매번 `rm -rf` + clean clone (clean install).

> 옵션 상세는 [features/20260514_install_runtime/analysis_and_design.md §3.8](../../features/20260514_install_runtime/analysis_and_design.md) 참조.

## Decision

**채택**: (α) H1 (curl-pipe) + (ii) clean install pattern.

**호출 명령**:
```bash
curl -fsSL --proto '=https' --tlsv1.2 \
    https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh | bash
```

**hosting**: `raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh`. tag `latest` 는 mutable — 메인테이너가 release 마다 `git tag -f latest && git push --force origin latest`.

**clean install pattern**:
1. install.sh 가 호출되면 `WIKIHUB_HOME` 결정 (default `~/wikihub`, env override).
2. 기존 디렉토리가 있으면 wikihub repo 검증 후 `rm -rf` → 신규 clone.
3. raw URL 의 install.sh 는 bootstrap 책임만 — clone 후 `exec ~/wikihub/install.sh "$@"` 로 self-replace.
4. 새 process 의 `$BASH_SOURCE[0]` 가 file path 이므로 Step 0 의 curl-pipe 감지 분기 미진입 (무한 루프 방지).

**safety guard 3개**:
1. `WIKIHUB_HOME` 가 시스템 path (`/`, `/usr`, `/etc`, `/opt`, `/home`, `$HOME`, 빈 문자열) 면 즉시 exit 1.
2. 기존 디렉토리에 `.git` 서브디렉토리 존재 시에만 wipe 허용.
3. `git config --get remote.origin.url` 가 `im-dongseon/wikihub` 일 때만 wipe — dev box 메인테이너 작업 디렉토리 보호.

**`--update` flag 비채택**: 모든 호출이 동일한 clean install. update / 신규 설치 의미 구분 없음.

**이유**:
- H1 (curl-pipe) 는 표준 OSS 설치 UX — 운영자 단계 최소.
- H2 는 운영자 step 수 증가 (clone → cd → install) — 1줄 명령 의도 어긋남.
- H3 는 release 마다 installer artifact 별도 build 필요 — v0.1.0 부담.
- (i) git fetch + reset 은 edge case 다수 — idempotency 가 시나리오마다 다름.
- (ii) clean install 은 매 호출 동일 상태 — idempotency 단순.

## Consequences

- **긍정**: 1줄 명령으로 설치/업데이트. idempotency 단순. update 마다 깨끗한 상태.
- **부정/제약**:
  - `~/wikihub` 안의 메인테이너 수동 편집 손실 — repo 는 read-only 정책 (CLAUDE.md).
  - bandwidth 비용 — 매 호출이 full clone (단 shallow `--depth 1` 로 100~300KB).
  - mutable tag `latest` 의 race — 메인테이너 force-push 직후 호출하면 어느 commit 받는지 비결정적.
  - **self-replace race window (R10 HIGH-4)**: curl-pipe 모드는 (1) raw URL 로 첫 install.sh fetch → (2) Step 0~2 실행 → (3) clone 후 self-replace 흐름이다. (1) 과 (3) 사이에 메인테이너가 force-push 하면 첫 curl install.sh 와 clone repo 의 install.sh 가 incompatible 일 수 있음 — Step 0/Step 2 의 흐름 (예: `_pipe_mode_detect` 의 감지 방식, `_step2_clone` 의 wipe 정책) 이 깨지면 fail. v0.1.0 mitigation: 메인테이너의 force-push 직후 운영자 안내 + 매뉴얼 재시도. v0.2.x 강화: install.sh 첫 줄 version 매크로 + clone 후 grep 검증 + 불일치 시 warn.
- **후속 영향 / 보안 위협 매트릭스 (v0.1.0)**:

| 위협 | mitigation | v0.2.x 로 미루는 것 |
|---|---|---|
| TLS MITM | `--proto '=https' --tlsv1.2` + 시스템 CA | (없음) |
| GitHub 계정 탈취 | 메인테이너 GitHub 의 2FA + 권한 최소화 (mitigation 없음) | signed commit + GPG tag verification |
| CDN cache stale | GitHub raw CDN TTL ~5분 — 운영자 안내 정합 | mirror 또는 versioned URL |
| mutable tag race | `gws --version` + yaml `gws_min_version` cross-check | tag commit SHA fingerprint 보고 |
| gws binary 변조 | `gws-installer.sh.sha256` shasum verify (ADR-0015 CH2) | GPG sig + reproducible build |

  - v0.1.0 의 보안 모델 = 메인테이너 GitHub 계정 보안 + TLS + shasum (gws) 의 3중. v0.2.x 에서 signed commit/tag · CodeSign · reproducible build 추가 계획.
  - V11 verification 이 idempotency 회귀 방지 (4 시나리오 — wipe+clone 재구성, 운영 state 무영향, safety guard fail-fast, origin 검증).
