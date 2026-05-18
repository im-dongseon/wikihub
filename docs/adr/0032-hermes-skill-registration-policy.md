# ADR-0032: Hermes skill 등록 정책 — external_dirs + install-time materialized SKILL.md

- **Status**: Accepted
- **Date**: 2026-05-18
- **Feature**: features/20260518_hermes_adapter
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

ADR-0002·0011·0012 가 lock 한 wikihub 의 agent 호출 모델 (`hermes -z "/wh:ingest"`) 이 실제 Hermes 의 `-z` 가 LLM-text 전용 (skill dispatch 불보장) 이라 silent mismatch. F4 backlog 결함 #12.

Hermes 의 skill 시스템 docs 실측 결과:
- skill 저장 위치 = `~/.hermes/skills/` (primary) + `external_dirs` (additional, in `~/.hermes/config.yaml`).
- 정의 형식 = `SKILL.md` (Markdown + YAML frontmatter).
- 호출 = `hermes chat --skills <name> --query "/<name> ..."` (auto-dispatch slash-command).

F5 feature 가 5건의 wikihub skill (ingest·lint·query·graphify·setup) 의 Hermes 등록 메커니즘 정본화. wikihub 의 정본 playbook (`_system/commands/<cmd>.md`, ADR-0006) 과의 single-source 정합 + update_mode (ADR-0030) 의 git fetch+reset 자동 propagation 호환 필요.

## Considered Options

본 ADR 은 **single-decision** 이 아니라 skill registration 의 4 sub-decision 묶음 (Hermes 와의 wire/registration 메커니즘 — 동일 관심사).

### sub-decision 1 — skill 위치

- **(α) `~/.hermes/skills/` 에 copy**: install.sh 가 5건 SKILL.md 를 직접 copy. update_mode 마다 재copy.
- **(β) `external_dirs` 에 wikihub path 추가**: `~/.hermes/config.yaml` 의 `skills.external_dirs` 에 wikihub 의 generated path 등록.

### sub-decision 2 — materialization 모델

- **(α) repo 에 SKILL.md 정본 직접 commit**: `_system/skills/wh-<cmd>/SKILL.md` 5건. ADR-0006 의 `_system/commands/` 정본성과 dual source — 정본 분산.
- **(β) install-time materialized**: repo 에 `_system/skills/wh-<cmd>.frontmatter.yaml` (frontmatter only) + install.sh 가 `_system/commands/<cmd>.md` 본문과 결합 → `_system/skills/_generated/wh-<cmd>/SKILL.md` 생성.

### sub-decision 3 — idempotent guard + 운영자 의도 보호

- **(α) 무조건 덮어쓰기**: install.sh 가 매 호출 마다 external_dirs 재추가 + SKILL.md 재생성. 운영자 의도 무시.
- **(β) marker comment + realpath 비교**: external_dirs 의 wikihub path 옆에 marker comment. realpath 정규화 비교로 중복 회피. 운영자 명시 제거 (marker 부재 + path 잔존) 는 보호.

### sub-decision 4 — safety guard (외부 자산 mutate)

- **(α) atomic write 만**: ruamel.yaml round-trip + `os.replace`. 외부 race 미보호.
- **(β) flock + backup + sha256 hash**: `~/.hermes/config.yaml.lock` advisory lock + write 전 backup (`*.wikihub-bak.<ts>`) + PRE/POST hash record. 7일 retention.

> 옵션 상세 비교는 [features/20260518_hermes_adapter/analysis_and_design.md §4·§5.3](../../features/20260518_hermes_adapter/analysis_and_design.md) 참조.

## Decision

**채택**: 모든 sub-decision (β).

- **sub-1 β**: `external_dirs` 에 `$WIKIHUB_HOME/_system/skills/_generated` realpath 추가. wikihub 내부 path 참조라 git pull (update_mode) 만으로 자동 propagation.
- **sub-2 β**: install-time materialized — `_system/skills/wh-<cmd>.frontmatter.yaml` (5건, git tracked) + `_system/commands/<cmd>.md` 본문 (ADR-0006 정본 유지) → `_step6_agent_skill` 가 결합하여 `_system/skills/_generated/wh-<cmd>/SKILL.md` 5건 생성. `_generated/` 는 `.gitignore`.
- **sub-3 β**: `~/.hermes/config.yaml` 의 `external_dirs` 항목에 marker comment (`# managed by wikihub install.sh — remove to disable auto-discovery`) 부착. 재실행 시 marker 존재 + path 일치면 no-op. marker 부재 + path 잔존이면 (operator 의도 보존) skip + stderr 경고.
- **sub-4 β**: install.sh `_step6_agent_skill` 의 mutate 단계 = (1) `~/.hermes/config.yaml.lock` advisory lock (`fcntl.flock(LOCK_EX | LOCK_NB)`, 5초 retry × 12회), (2) backup (`*.wikihub-bak.<utc_iso>`), (3) PRE_HASH sha256, (4) ruamel atomic write, (5) POST_HASH 비교, (6) install.log 명시 record, (7) flock release. 7일 초과 backup 자동 cleanup.

**이유**:

- **sub-1**: copy 는 update_mode 마다 재copy 필요 + Hermes internal cache 의 stale 위험. external_dirs 는 path reference 라 git pull 만으로 자동 propagation. update_mode (ADR-0030) 의 git fetch+reset 흐름 정합.
- **sub-2**: repo 에 SKILL.md 정본 두면 ADR-0006 의 `_system/commands/` 정본성과 dual-source 충돌 — playbook 의 single-source 위반. install-time materialization 은 commands/ 정본 보존 + Hermes wire format (`SKILL.md` + frontmatter) 만족.
- **sub-3**: wikihub 가 사용자 home 의 외부 자산 (다른 도구 - codex/aider 등 - 의 skill 도 같은 config 에 등록 가능) 을 mutate. 운영자 명시 제거 의도 보호 + idempotent 보장 필수.
- **sub-4**: 외부 자산 mutate 는 wikihub.yaml 의 내부 atomic write 패턴만으로 부족 — Hermes 자체가 동일 파일을 mutate 할 수 있음 (advisory lock 가정). backup + hash 가 사후 trace 보장. ADR-0023 §safety guard 의 wikihub 외부 path mutate 확장 정합.

## Consequences

- **긍정**:
  - F4 backlog #12 closure. Hermes 의 skill dispatch path 정합.
  - update_mode 와의 자동 propagation — git pull 만으로 skill 본문 갱신 인식.
  - ADR-0006 정본성 보존 (commands/ 정본, skills/_generated/ 는 build artifact).
  - 운영자 의도 명시 보호 (marker comment).
  - 외부 자산 mutate 의 safety (flock + backup + hash).
- **부정/제약**:
  - Hermes 가 advisory lock 을 같이 쓰지 않으면 protection 부분적 (install.sh 의 중복 호출 race 만 cover).
  - `_generated/` 가 install.sh 호출마다 재생성 — 운영자가 직접 편집 시 덮어쓰임.
  - Hermes 의 `~/.hermes/config.yaml` 형식 변경 시 wikihub 의 ruamel 호환성 깨질 수 있음 (Hermes versioning stability 의존). hermes_min_version 검증은 v0.2.x.
- **후속 영향**:
  - **ADR-0023** §safety guard 확장 Note — wikihub 외부 자산 mutate (~/.hermes/config.yaml) 의 backup + flock + 동의 surface 정책 정본화.
  - **ADR-0011** Superseded by ADR-0033 — skill name prefix 가 `wh:` (colon) → `wh-` (hyphen). Hermes docs 미지원 colon 의 결정.
  - **ADR-0012** §Decision 갱신 — `oneshot_args` 의 `{skill}` placeholder semantics 추가 (per-unit substitution).
  - **ADR-0006** 영향 없음 — `_system/commands/` 정본성 보존 (install-time materialization 패턴).
  - **재검토 트리거**: (1) Hermes 가 advisory lock 도입 시 sub-4 protection 강화 가능. (2) codex/gemini 등 다른 agent 의 skill 시스템 매핑 추가 시 ADR-0012 의 agent-agnostic 모델과 본 ADR 의 wire format 정합 재평가. (3) Hermes 가 `external_dirs` 의 즉시 인식 보장 (재시작 불요) 안 하면 install.sh 가 `hermes skills audit` 자동 호출 정책 추가.
