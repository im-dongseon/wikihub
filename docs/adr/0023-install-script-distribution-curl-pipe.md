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

## Note (2026-05-17, feature `update_mode`)

본 ADR 의 clean wipe 패턴 (`rm -rf + git clone`) 의 **scope 가 fresh install + `--force-fresh` 명시 호출** 로 한정. update path 는 ADR-0030 (`update workflow orchestration`) 의 `git fetch + reset --hard` 로 분리.

- detect 시그널 = `$WIKIHUB_HOME/_system/VERSION` AND `$WIKIHUB_HOME/.git` 존재. 둘 다 있으면 update path, 둘 다 없으면 fresh, 한쪽만 있으면 fatal partial state.
- 운영자가 의도적 clean wipe 가 필요한 경우 `--force-fresh` flag 명시 — 5초 confirm + 3중 safety guard (system path · git+origin · cwd) 통과 후 진행.
- 본 ADR 의 "매 호출 동일 상태" idempotency 는 update path 에서도 보존 — 동일 ref 재호출 시 `git fetch + reset` 의 no-op 처리로 동등.
- Decision §`--update` flag 비채택은 유지 — update path 진입은 ADR-0030 의 detect 시그널 자동 분기 (flag 없음).

Status 변경 없음. 의미론 일관, 운영 scope 만 명시화.

## Note (2026-05-18, feature `install_scope_reduction`) — Clone scope

본 ADR 의 `git clone` 책임에 **sparse-checkout 적용** — 운영 타깃에는 운영 필수 path 만 거주. AGENTS.md §1 Dev Zone / Ops Zone 분리 invariant 정합.

### Fetch list 정본 (`install.sh:WIKIHUB_SPARSE_PATHS`)

| path | 사유 |
|---|---|
| `_system/` | `/wh:*` 명령 playbook · systemd template · VERSION |
| `scripts/` | Python runtime (vault-fetch · ops-alert · lib/* · requirements.txt) |
| `install.sh` | re-run / update |
| `wikihub.yaml.example` | `/wh:setup` Step 0 의 template input (ADR-0031) |
| `README.md` | 운영자 참고 (운영 진단 시 useful) |
| `LICENSE` | legal · convention — MIT 의 redistribution scope 가 운영 타깃엔 strict 적용 안 되지만 OSS 관례로 포함 (LOW-S1 design review) |

### 제외 (의도)

`docs/` · `features/` · `tests/` · `AGENTS.md` · `CLAUDE.md` · `GEMINI.md` · `.gitignore` · `.env*` 등 — AGENTS.md §1 Development Zone 산출물 + 운영 무관 dev 파일.

### Sparse mode

`--no-cone` — root 파일 단위 정밀 선택. cone 모드는 root 의 모든 파일을 자동 포함하여 governance 파일까지 끌고 옴.

### Clone 패턴 (install.sh `_step2_clone`)

```bash
git clone --no-checkout --depth 1 --branch "$clone_ref" "$URL" "$WIKIHUB_HOME"
git -C "$WIKIHUB_HOME" sparse-checkout init --no-cone
git -C "$WIKIHUB_HOME" sparse-checkout set _system scripts install.sh wikihub.yaml.example README.md LICENSE
git -C "$WIKIHUB_HOME" checkout
```

**blob filter (`--filter=blob:none`) 미사용** — HIGH-S2 design review (partial clone + `--unshallow` 호환 위험 + lazy blob fetch 폭증 회피). sparse-checkout 만으로 working tree 절감 충분.

### Update path 정합 (`install.sh _step2_update`)

`_apply_sparse_checkout` 호출은 `git reset --hard $target_ref` **직후** — working tree mutation 의 origin = target_ref 채택 후. pre-feature 풀-clone 운영 서버가 첫 update 시 자동 sparse 전환 + 이후 update 는 idempotent.

`_rollback_if_failed` 본문에도 `_apply_sparse_checkout` 호출 포함 — rollback 후에도 sparse state 정합 (ADR-0030 §부정/제약 의 sparse-checkout 영속화 Note 정합).

### Supersede 아님

본 ADR 의 호출·배포 모델 (curl-pipe + clean install + safety guard 3개) 는 유지. clone scope 만 보강. Status 변경 없음.

### Related

- ADR-0031 §"Clone scope" (의 Related 명시) — yaml writer 책임 reassign 과 짝.
- ADR-0030 §부정/제약 sparse-checkout 영속화 — update path + rollback 시 working tree 동작.
