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

## Note (2026-05-19, feature `dir_layout_refactor`) — §Decision 갱신 (ADR-0034)

ADR-0034 data-first layout invert 후 본 ADR §Decision 의 path 변경:

### external_dirs path 변경

- **Before**: `$WIKIHUB_HOME/_system/skills/_generated/` (이전 `WIKIHUB_HOME` = repo 의미)
- **After**: `$WIKIHUB_SRC/_system/skills/_generated/` (ADR-0034 시스템 코드 dir)

### sub-decision 영향

- **sub-1 (`external_dirs` 채택)**: path 변경만, 정책 유지.
- **sub-2 (install-time materialized)**: frontmatter source 위치 = `$WIKIHUB_SRC/_system/skills/wh-<cmd>.frontmatter.yaml`. commands body = `$WIKIHUB_SRC/_system/commands/<cmd>.md`. 결합 결과 = `$WIKIHUB_SRC/_system/skills/_generated/wh-<cmd>/SKILL.md`.
- **sub-3 (marker comment + realpath 비교 idempotent guard)**: install.sh `_step6_agent_skill _patch_hermes_external_dirs` 가 realpath 비교 — path 만 변경되면 자동 detect. migration helper (`scripts/_helpers/hermes_config_migrate.py`) 가 stale entry (이전 `$WIKIHUB_HOME/_system/skills/_generated/`) 제거 + 신규 entry 추가 (marker comment 검증으로 wikihub-managed 만 영향, 운영자 등록 entry 보존).
- **sub-4 (flock + backup + sha256 + retention)**: 정책 유지. migration helper 도 동일 safety 패턴.

### migration 자동화 (ADR-0034 §sub-3 정합)

`scripts/migrate_layout.sh` 의 Step 5 가 `scripts/_helpers/hermes_config_migrate.py` 호출:
- `--remove-stale "$LEGACY_REPO/_system/skills/_generated"`
- `--add-new "$NEW_SRC/_system/skills/_generated"`

운영자가 직접 등록한 marker 부재 entry 는 보존 (CR2-HIGH-1 정합).

Status 변경 없음. path + migration 자동화 추가.

## Note (2026-05-19, feature `hermes_yolo_flag`) — oneshot_args 에 `--yolo` 보강

### 발견

v0.1.2 OCI 실증 — install.sh post-install `hermes chat --skills wh-setup --quiet --query "/wh-setup"` 가 Hermes 의 보안 승인 layer (tirith) 에 의해 `Choice [o/s/D]: ✗ Denied` 로 중단. `/wh-setup` playbook 의 yaml 검증·상태 확인이 inline python 호출 (`cat | python3`, `python3 -c`) 로 구성돼 있어 tirith 가 위험 명령으로 분류 → prompt → noninteractive context (install.sh + systemd timer) 에서 응답 불가 → deny 폴백.

### 결정

agent 의 oneshot 호출 cmdline 에 `--yolo` 인자를 표준 형태로 포함.

**Before**: `["chat", "--skills", "{skill}", "--quiet", "--query"]`
**After**:  `["chat", "--skills", "{skill}", "--quiet", "--yolo", "--query"]`

`--yolo` = Hermes 의 noninteractive auto-approve. install.sh 의 직접 호출 (`_step8_wh_setup_skill_meta`) + systemd unit ExecStart (vault@/lint timer 가 호출) 모두 동일 plumbing.

§sub-3 (cmdline schema) 본문은 미수정 — 운영자가 yaml 에서 override 가능한 형태 그대로. yaml.example 의 default form 만 갱신.

### 적용 layer

- `wikihub.yaml.example` — `agent.oneshot_args` default
- `install.sh` F5 migration default literal (update path 의 schema 자동 갱신)
- `install.sh _step8_wh_setup_skill_meta` 의 직접 호출 cmdline
- `scripts/_helpers/render_systemd_units.py` fail-fast 안내 메시지

### Trust 가정 변화

`--yolo` 가 tirith 의 prompt 를 자동 승인 → noninteractive 운영 환경에선 효과 동일 (prompt 없으니 deny 만 발생했음). interactive 운영자 manual hermes 호출은 영향 받지 않음 (yaml override 또는 직접 cmdline 사용 시 trust 모델 본인 책임).

본 변경의 분석 정본: [features/archive/20260519_hermes_yolo_flag/analysis_and_design.md](../../features/archive/20260519_hermes_yolo_flag/analysis_and_design.md)

## Note (2026-05-20, feature `migration_prompt_simplify` v0.1.5) — `_migrate_agent_schema` prompt 분기 제거

### 발견

v0.1.4 의 `[[ -t 0 ]]` 기반 noninteractive 분기 (`install.sh:_migrate_agent_schema`) 가 Hermes OCI 환경에서 무력화. 원인 — Hermes 의 terminal tool 이 subprocess 에 PTY 할당 → stdin = pty slave = terminal-like → `[[ -t 0 ]]` true → prompt fire → 응답 hook 부재 → empty input → default N → migration 거부 → yaml `--yolo` 미반영 → systemd unit `--yolo` 누락 → Hermes 매번 수동 patch.

v0.1.3 의 `--yolo` 누락 + v0.1.4 의 schema-drift 무력화와 **동일 패턴** — install.sh 의 noninteractive 검출 layer 가 "운영 환경의 실 호출 경로 = Hermes terminal subprocess" 모델링 못함.

### 결정 (서브에이전트 2건 design review 후)

`_migrate_agent_schema` 의 prompt 분기 자체 제거. backup (`.wikihub-bak.<utc_iso>`) 가 의도 override safety net — transformation 자체가 idempotent + scoped (skill_prefix + oneshot_args 만, 다른 yaml 필드 미터치).

- 옵션 (1) 채택 — prompt 완전 제거 + 항상 auto-proceed.
- 옵션 (2) [escape hatch `WIKIHUB_SKIP_MIGRATION` 도입] 은 외부 운영자 의도 override 시나리오 가설 — v0.2.x 시점 surface 시 별도 feature 로 추출 (재검토 트리거).
- 옵션 (3)/(4) [default Y flip / read -t 5 timeout] 은 stdin-shape 휴리스틱 cycle 잔존으로 drop.

### 효과

- v0.1.3 → v0.1.4 → v0.1.5 의 동일 root cause cycle 종료.
- Hermes / `curl|bash` / manual tty 3 환경 모두 동일 동작.
- backup 자동 생성으로 운영자 사후 trace 보장.
- 운영자 의도 override 의 매번 yaml 재편집 friction — v0.2.x 외부 운영자 사례 surface 후 escape hatch 도입.

본 변경의 분석 정본: [features/archive/20260520_migration_prompt_review/](../../features/archive/20260520_migration_prompt_review/) (context.md + design_review_1.md + design_review_2.md + plan.md)

## Note (2026-05-20, feature `agent_model_per_skill` v0.1.5) — per-skill model override + 출력 언어 정책

### 발견 (Hermes OCI 진단)

1. **reasoning 모델 hang**: `deepseek-v4-pro` / `deepseek-v4-flash` 가 hermes agent 의 default `max_tokens` (작은 값) 에서 thinking 토큰 다 소모 → content="" → agent hang. `lock.acquire()` 5분 대기 + 운영자 수동 SIGINT.
2. **출력 언어 한자 섞임**: MiniMax M2.5 등 일부 모델이 한국어 응답에 한자(漢字) 표기를 섞어 출력 — "기획(企劃)" 같은 패턴. wiki 의 entity·concept 페이지 명명 일관성 훼손.

### 결정 — per-skill model override

`agent.oneshot_args` 는 instance-wide (모든 wh-* skill 공통). hermes config.yaml.model.default 는 platform-wide (Telegram, CLI 등 모두). lint 만 다른 모델 쓰려면 systemd unit 의 ExecStart 차원에서 `--model <id>` 명시 필요.

yaml schema 신설:
```yaml
agent:
  models:                         # per-skill model override (default 빈 dict — hermes config default 사용)
    wh-lint: minimax-m2.5         # non-reasoning fast-response, 다른 wh-* skill 미명시 → hermes default
```

`scripts/_helpers/render_systemd_units.py:_per_skill_invocation` 가 `agent.models[<skill>]` 검사 → 명시되면 `oneshot_args` 의 `--query` 앞에 `--model <id>` inject (hermes_yolo_flag 의 `--yolo` 패턴과 동일 mechanism).

### 결정 — 출력 언어 정책 (한자 → 한글 변환)

`_system/commands/lint.md` 의 LLM 호출 step (Step 3 stub 생성 / Step 4 cross-ref / Step 5 index 재구성 / Step 6 모순 점검) 공통 적용:
- 출력 언어 = 한국어 (wiki source 본문 정합)
- 한자 감지 시 한글 변환. 고유명사 (한국 외 출처) 만 예외
- 영어 약어 (OKR, PM, API 등) 그대로 유지

본 정책은 wiki-schema.md 의 신뢰 경계 출력 sanitize layer 와 정합. 다른 wh-* skill (ingest, query, graphify) 의 LLM 응답도 같은 결함 surface 시 동일 정책 lift 권장 — v0.1.5 시점 **lint + ingest 적용** (Hermes 실증). query/graphify 는 후속 surface 시 추가. ingest 의 fallback model = `qwen3.6-plus` (non-reasoning + 한국어 안정) — `deepseek-v4-pro` (reasoning) 의 max_tokens hang risk 대안.

### Cross-references

- ADR-0036 §Note (2026-05-20 graphify_backend_flexibility) — backend 선택 layer. 본 §Note 는 backend 가 정해진 상태에서 skill 별 model 분리.
- backlog 260520-backlog.md (deepseek-v4-pro 로 lint 분리 시도 → reasoning hang surface 진단). 본 §Note 가 backlog §C-1 의 옵션 1 (systemd unit `--model` 추가) 을 yaml-driven 으로 격상.

본 변경의 분석 정본: features/archive/20260520_agent_model_per_skill/ (예정)

---

## Note (2026-05-22, feature `v016_operational_default_align` v0.1.6) — wh-lint default 갱신 + hermes delegation.model 권장

### 발견

운영자가 v0.1.5 배포 이후 자기 환경에서 누적 적용한 결정 ↔ wikihub repo 정본 default 와 mismatch:

1. **wh-lint 운영 = `deepseek-v4-flash`** (260521 §B latency 측정 2.6~6.4s/call, ExecStart verified) ↔ 정본 = `minimax-m2.5`
2. **hermes `delegation.model` = `minimax-m2.5`** (운영자 적용, 260520 §M) ↔ wikihub 가이드 부재
3. **vault `sync_interval_sec` = 3600 (1h)** (운영 적용 + 16:40 KST cycle verified) ↔ 정본 default = 600 (10분)

### 결정

#### A. yaml.example `agent.models.wh-lint` default 갱신

`minimax-m2.5` → `deepseek-v4-flash`. 사유:

- 운영자 검증된 latency 이점 (2.6~6.4s vs 5~10s 추정) 새 운영자에게 자동 전수
- wh-ingest (`deepseek-v4-pro`) 와 동일 DeepSeek 패밀리 + opencode-go backend 일관성 (fast-response tier vs reasoning tier 명확 분리)
- 한자→한글 보호는 lint.md "출력 언어 정책" 섹션이 v0.1.5 에서 이미 model-agnostic layer 로 강화됨 — DeepSeek 한자 섞임 risk 에도 동일 보호 적용 (이전 §Note 2026-05-20 의 minimax 한정 가정 해제)

#### B. install.sh `_step8_guide` + setup.md Step 1 — hermes `delegation.model` 권장 안내

wh-lint Step 6 등 subagent 호출 시 적용되는 `delegation.model` 권장값 `minimax-m2.5` 명시. wikihub 가 hermes config 를 자동 patch 하지 않음 (Hermes 는 wikihub 외 사용처 존재 가능 — 의도 침범 회피) — 안내만, warn 만.

`wh-ingest`·`wh-lint` 메인은 wikihub `agent.models` 가 systemd `--model` 으로 lock — hermes `model.default` 와 완전 독립. 운영자가 hermes `model.default` 를 어떻게 바꾸든 wikihub 자동 운영 영향 없음.

#### C. (별도 align, 본 §Note 인접) yaml.example `sync_interval_sec` default 600 → 3600

직접적 §Decision 갱신 아님 — 운영 IO·log noise 절감 결정. mechanical phase 의 has_changes=false 경로 LLM cost 는 0 이지만 lsjson + log append 빈도가 6배 감소.

### 영향

- 새 운영자 install 직후 wh-lint default = deepseek-v4-flash → latency 이점 자동 전수
- 기존 운영자 (이미 `deepseek-v4-flash` 적용) wikihub.yaml 영향 없음
- setup.md Step 1 의 warn 출력에 `delegation.model` 정합 체크 1줄 추가 — 정보 출력만
- ADR-0036 §Note (graphify backend flexibility) 의 backend catalog 와 install.sh env template GEMINI 블록 정합 (별도 결정 — backend 가이드 보강)

### Cross-references

- 운영 정본 근거: backlog `260520_wikihub_backlog.md` §V·§M (lint 모델 분리 trial trail), `260521_wikihub_backlog.md` §B·§C2·§F (TimeoutStartSec 1200·graphify backend·non-reasoning 정책)
- ADR-0036 §Note (graphify backend flexibility) — backend 선택 layer 와 본 §Note 의 모델 선택 layer 분리
- 이전 §Note (2026-05-20 agent_model_per_skill) — wh-lint default `minimax-m2.5` 결정. 본 §Note 가 운영 검증 trail 로 갱신 (한자→한글 정책이 v0.1.5 에서 model-agnostic layer 가 되며 minimax 한정 안전 가정 해제)

본 변경의 분석 정본: features/archive/20260522_v016_operational_default_align/ (예정)

---

## Note (2026-05-22, feature `yaml_schema_drift_migration` v0.1.7) — `_migrate_agent_schema` 확장

### 발견

본 §Note 의 직전 §Note (v0.1.6 `v016_operational_default_align`) 에서 yaml.example default 를 운영 정본에 align 했으나, **운영자의 wikihub.yaml 은 .example 자동 sync 안 됨** — ADR-0031 §Decision A 의 "install.sh 가 yaml 미관여" 정책 정합. 결과: v0.1.5+ 신설 field (`agent.models`, `agent.timeout_sec`, `operations.pending_alert_age_sec` 등) 운영 yaml 부재 → render 가 default 600·flag 미주입 fallback → 운영자 manual systemd unit edit 4건 overwrite 사건 (2026-05-22 OCI).

기존 `_migrate_agent_schema` 함수 (`install.sh:751`) 는 ADR-0033 (skill prefix `wh:` → `wh-`) + ADR-0032 §Note 2026-05-19 (oneshot_args `--yolo` 누락) 만 처리. 신설 field 자동 추가 미처리.

### 결정 — `_migrate_agent_schema` 확장

ADR-0031 §Note (v0.1.7) 의 schema mutation 책임 정합으로 본 함수의 처리 범위 확장:

#### Group A — 기존 처리 (불변)
- `agent.skill_prefix: "wh:" → "wh-"` (ADR-0033)
- `agent.oneshot_args` legacy form → F5 schema (ADR-0032)
- `agent.oneshot_args` 의 `--yolo` 누락 → in-place 삽입 (ADR-0032 §Note 2026-05-19)

#### Group B — 자동 추가 (안전 default, **부재 시만**) — v0.1.7 신설
- `agent.timeout_sec: 1200`
- `agent.models: {wh-lint: deepseek-v4-flash, wh-ingest: deepseek-v4-pro}`
- `operations.pending_alert_age_sec: 3600`
- `operations.lint_contradiction_check: true`
- `operations.graphify_enabled: true`
- `operations.graphify_backend: ""`
- `operations.graphify_min_version: "0.8.0"`
- `operations.graphify_max_version: "0.99.99"`

#### Group C — 자동 삭제 (ADR-0035 폐기 field cleanup) — v0.1.7 신설
- `vaults[].options.bootstrap_allowed`
- `vaults[].options.credentials_path`
- `vaults[].options.root_folder_id`
- `vaults[].options.cursor_path`

#### 정책 — PTY-safe + idempotent + 보수적

- **prompt 0** — v0.1.5 §Note 2026-05-20 의 PTY-safe 정책 일관성. Hermes PTY 환경에서 `[[ -t 0 ]]` 거짓 양성 회피.
- **값 변경 자동 회피** — 값이 이미 존재하면 미터치 (운영자 의도 vs schema drift 구분 불가, 보수적 보호). 운영자가 새 default 적용 원하면 yaml 직접 편집 + install.sh 재실행.
- **backup** — `.wikihub-bak.<utc_iso>` 변경 발생 시 자동 생성. safety net.
- **idempotent** — 재실행 시 no-op (자동 추가는 부재 시만, 자동 삭제는 존재 시만).

### 적용 layer

`install.sh:751-870` 의 `_migrate_agent_schema` 단일 함수. 호출처 (`install.sh:1053`) 영향 없음. drift detect 단계의 Group A/B/C flag 분리 + Python heredoc mutation logic 확장.

### Trust 가정

ADR-0031 §Note v0.1.7 와 정합: **mutation 의 두 종류 분리**
- **value mutation** — 운영자 trust boundary (install.sh 미관여)
- **schema mutation** — yaml.example schema 의 single source of truth (install.sh 책임)

### Cross-references

- ADR-0031 §Note (2026-05-22 v0.1.7) — install.sh 의 yaml mutation 책임 boundary (value vs schema)
- ADR-0035 — 폐기 field catalog (Group C cleanup 의 자료)
- ADR-0036 — graphify 관련 신설 field (Group B 의 `graphify_*` 자료)
- ADR-0037 — `pending_alert_age_sec` (Group B 자료)
- 사건 trail: 2026-05-22 OCI 운영 사건 — 운영자 manual systemd unit edit 4건 손실 → 운영 yaml schema drift 진단 → 본 §Note 의 implementation trigger

본 변경의 분석 정본: features/archive/20260522_yaml_schema_drift_migration/ (예정)
