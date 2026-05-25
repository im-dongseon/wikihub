# ADR-0034: data-first layout — `~/wikihub/` = 운영 자산 + `~/.local/share/wikihub/src/` = 시스템 코드

- **Status**: Accepted
- **Date**: 2026-05-19
- **Feature**: features/20260519_dir_layout_refactor
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

v0.1.0 acceptance 직후 (F5 hermes_adapter archive 후) 운영자 surface 의문:

> 실제 사용하는건 instance 인데 이게 왜 `wikihub` 가 아니지?

이전 layout 의 naming convention 은 **code-first** — OSS 일반 패턴 (`~/<tool-name>/` = tool's repo) 따른 결과:
- `WIKIHUB_HOME = ~/wikihub/` (repo, 시스템 코드)
- `WIKIHUB_INSTANCE_ROOT = ~/wikihub-instance/` (운영 데이터)

그러나 wikihub 는 "tool" 보다 **데이터 + 자동화 시스템** 의 결합체:
- 운영자 일상 자산 = wiki 페이지·yaml·state·vault mount (= 현 `wikihub-instance/`)
- 시스템 코드 = install.sh·_system/·scripts/ (= 현 `wikihub/`)
- 사용자 mental model 의 "wikihub" = 운영 자산. 시스템 코드는 엔진.

v0.1.0 미배포 (운영자 base 0건) 시점이라 backwards-incompat refactor 비용 0 — release 전 마지막 architectural fix.

## Considered Options

본 결정은 단일 architectural 결정이 아니라 **layout invert + 운영 transition** 의 4 sub-decision 묶음 (동일 관심사 — XDG layout 정본화).

### sub-decision 1 — layout 위치

- **(α) `~/wikihub/.system/`** (hidden) — 시스템 코드 hidden subdirectory. less change. 단 `--force-fresh` 시 운영 자산 wipe 위험.
- **(β) `~/.local/share/wikihub/src/`** (XDG) — 시스템 코드 XDG dir. ADR-0020 venv 와 동일 root. `--force-fresh` 가 src 만 wipe → 운영 자산 절대 안전.
- **(γ) `~/wikihub-src/`** (sibling) — minimal naming change. home cluttering 부분 해소.

### sub-decision 2 — env 명명

- **(A) 신규 `WIKIHUB_SRC` 도입, `WIKIHUB_HOME` semantic swap**: 의미 변경 silent bug 위험.
- **(B) 변수 swap 완전** — `WIKIHUB_HOME` 의미 = 운영, `WIKIHUB_SRC` 신규, `WIKIHUB_INSTANCE_ROOT` 폐기.
- **(C) 둘 다 deprecated 후 새 env** — `WIKIHUB_DATA` + `WIKIHUB_SRC`. 변경 폭 최대.

### sub-decision 3 — migration 자동화

- **(A) install.sh 자동 detect + 명시 confirm 후 자동 mv**: install.sh 복잡도 증가.
- **(B) install.sh detect 후 안내만 — 운영자 manual mv**: 운영자 부담.
- **(C) 별도 `scripts/migrate_layout.sh` helper + install.sh 의 `_step0_legacy_detect` 가 helper 호출 prompt**: 책임 분리 + 운영자 신중함.

### sub-decision 4 — backup 모델

- **(α) `cp -r` backup 후 wipe**: ENOSPC 위험 (운영자 wiki 콘텐츠 대용량 시).
- **(β) mv-only + phase-aware reverse-mv rollback trap**: ENOSPC 회피. atomic same-filesystem mv. cross-fs mv 의 자동 cp+rm 은 운영자 책임 (드문 케이스).

> 옵션 상세는 [features/20260519_dir_layout_refactor/analysis_and_design.md §4](../../features/20260519_dir_layout_refactor/analysis_and_design.md) 참조.

## Decision

**채택**: sub-1 (β) + sub-2 (B) + sub-3 (C) + sub-4 (β).

### sub-1 (β) — XDG src layout

- 운영 dir (data-first): `~/wikihub/` — 사용자 일상 자산. wiki·yaml·state·vault mount. install.sh 가 mkdir + materialize 보조, 운영자 일상 편집 대상.
- 시스템 코드: `~/.local/share/wikihub/src/` — install.sh·_system/·scripts/·.git. install.sh 가 git clone target. ADR-0020 의 `~/.local/share/wikihub/venv/` 와 동일 XDG root 공유.

### sub-2 (B) — 변수 swap

| env | 의미 | default |
|---|---|---|
| `WIKIHUB_HOME` | **운영 자산 dir** (semantic swap) | `~/wikihub` |
| `WIKIHUB_SRC` (신규) | **시스템 코드 dir** | `~/.local/share/wikihub/src` |
| `WIKIHUB_INSTANCE_ROOT` | **폐기** | — |

backwards-incompat — install.sh `_step0a_env_semantic_check` 가:
- `WIKIHUB_INSTANCE_ROOT` env detect 시 fail-fast + 안내.
- `WIKIHUB_HOME` 가 v0.1.x repo 의미 (.git + im-dongseon/wikihub) 로 사용 중이면 silent bug detect → fail-fast.

multi-instance: `WIKIHUB_HOME=/var/wikihub-prod WIKIHUB_SRC=/var/wikihub-src/prod` 식 env override 그대로.

### sub-3 (C) — `scripts/migrate_layout.sh` helper

- install.sh `_step0_legacy_detect` 가 `~/wikihub/.git` + `~/wikihub-instance/` 둘 다 존재 + origin 검증 통과 시 → helper 호출 prompt.
- helper 단독 실행 가능 (운영자 신중한 검증). flock advisory.
- 9-phase state machine (pre-stop → stopped → unmounted → mv-src-done → mv-home-done → hermes-patched → render-done → start-done → DONE).
- 중간 실패 시 phase resume (운영자 재호출 idempotent).
- rollback trap (ADR-0030 패턴) — phase-aware reverse-mv.

### sub-4 (β) — mv-only backup

- `mv` 만 사용 (cp 없음). same-filesystem 시 atomic + disk 0. cross-fs 는 cp+rm 자동 fallback (드문 케이스, 운영자 책임).
- rollback path = reverse mv (phase marker 기준).
- 운영자 명시 backup 원할 시 helper 호출 전 직접 `cp -r` 권고 — README 안내.

### 추가: rclone FUSE unmount + hermes config migration

- rclone FUSE mount busy detect → retry × 6 × 10s + lazy fallback (`fusermount3 -uz`).
- ~/.hermes/config.yaml 의 external_dirs migration: stale entry 제거 (marker 검증 — wikihub-managed 만, 운영자 등록 entry 보존) + 신규 entry 추가. (helper `scripts/_helpers/hermes_config_migrate.py` 는 v0.1.8 cleanup 으로 삭제 — pre-v0.1.0 transition 1회성, §"후속 영향" cleanup bullet 참조).

## Consequences

- **긍정**:
  - 운영자 mental model 자연화 — `~/wikihub/` = "내 wikihub 자산". 시스템은 hidden XDG.
  - `--force-fresh` 가 src 만 wipe → 운영 자산 절대 안전 (이전 `~/wikihub-instance/` 외부 분리 효과 보존 + 더 단순).
  - ADR-0020 (venv XDG) 와 완벽 정합 — XDG root 공유.
  - multi-instance 자연 지원 (env override 그대로).
  - 보안: SA credentials `~/.credentials/wikihub/` 외부 격리 (ADR-0029 §Decision 갱신 정합 — 운영 자산 dir 내부 비밀 미배치).
  - migration 도구 명시 — 운영자 신뢰 + 부분 실패 resume.

- **부정/제약**:
  - backwards-incompat — `WIKIHUB_INSTANCE_ROOT` env 폐기. v0.1.0 미배포 시점이라 영향 0 (운영자 base 부재).
  - install.sh 의 `WIKIHUB_HOME` semantic 변경 — Step 0a fail-fast 안전망으로 silent bug 차단. 단 운영자가 detect 메시지 무시 시 명시 unset 권장.
  - `_system/commands/` playbook 의 path 인용이 layout 변경 정합 필요 (ADR-0031 §Decision B catalog 의 derived 값 변경).
  - migration helper 의 phase marker state machine 의 운영자 직접 편집 시 silent corruption — `_validate_phase` 가 invalid phase value detect.

- **후속 영향**:
  - **ADR-0010** (operational tooling split) — §Decision 갱신. install.sh = src dir 책임, `/wh-setup` = home dir 책임. path 변경 명시화.
  - **ADR-0020** (venv XDG) — §Decision 갱신. src 도 같은 XDG root 공유 명시.
  - **ADR-0023** (install.sh safety guard) — §Decision 본문 변경. wipe target = `$WIKIHUB_SRC`, safety guard 4번째 추가 (XDG path 외 wipe 명시 confirm).
  - **ADR-0029** (SA auth) — §Decision 본문 변경. default credentials_path = `~/.credentials/wikihub/sa_<vault_id>.json` (외부, 운영 자산 dir 내부 비밀 미배치).
  - **ADR-0030** (update workflow) — §Decision 갱신. cwd = `$WIKIHUB_SRC`. 4 sub-decision 모두 path 변경만 정합.
  - **ADR-0031** (yaml materialization) — §Decision 갱신. `instance.root` default = `~/wikihub`. derived 4필드 값 변경.
  - **ADR-0032** (Hermes skill registration) — §Decision 갱신. external_dirs path = `$WIKIHUB_SRC/_system/skills/_generated`. migration helper 가 stale entry 자동 제거 (marker 검증).
  - **재검토 트리거**: (1) multi-instance 운영자 base 증가 시 `WIKIHUB_SRC` 의 per-instance vs 공유 default 재검토. (2) cross-fs mv 의 ENOSPC 빈도 surface 시 backup 정책 재검토 (현 mv-only).
  - **v0.1.8 cleanup** (2026-05-25, feature `legacy_migration_cleanup`) — `scripts/migrate_layout.sh` (313줄, 9-phase state machine) + `scripts/_helpers/hermes_config_migrate.py` (helper, migrate_layout.sh 의 유일 caller 부재로 orphan) + install.sh `WIKIHUB_HOME` silent bug detect block + ADR-0032 §sub-3 의 migration 자동화 절차 안내 dead reference 정리 — 모두 pre-v0.1.0 → v0.1.0 transition 의 1회성 자산. 운영자 base (v0.1.7+) 정착으로 영구 무용 → atomic refactor. ADR 본문 결정 (data-first layout) 자체는 history record 로 그대로 보존.
