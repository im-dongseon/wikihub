# Analysis & Design — hermes_adapter (F5)

- **feat_id**: `hermes_adapter`
- **plan**: [plan.md](./plan.md) (locked 2026-05-18)
- **버전**: v3 (R3 closure review 반영 — narrow patch)
- **approved**: 2026-05-18 (Step 3 진입)
- **선행 ADR**: ADR-0002 (Hermes invocation), ADR-0006 (unified orchestration), ADR-0010 (operational tooling split), ADR-0011 (skill namespace prefix), ADR-0012 (agent invocation abstraction), ADR-0023 (install.sh distribution), ADR-0024 (fatal alert contract), ADR-0030 (update workflow), ADR-0031 (yaml materialization)
- **현재 main HEAD**: `c328548` (install_scope_reduction archive)
- **R2 review 산출**: [design_review_1.md](./design_review_1.md) (CR1 spec, CRIT 3 / HIGH 6), [design_review_2.md](./design_review_2.md) (CR2 SRE, CRIT 2 / HIGH 8)
- **R3 closure 산출**: [design_review_3.md](./design_review_3.md) (CR3-1 spec closure, R2 CRIT/HIGH 9건 CLOSED + 신규 CRIT 2 / HIGH 3), [design_review_4.md](./design_review_4.md) (CR3-2 SRE closure, R2 CRIT/HIGH 10건 중 8 CLOSED 2 PARTIAL + 신규 HIGH 2 / MED 4)

> **핵심 운영 invariant** (plan.md 에서 lock): sync→ingest 자동화 사슬의 **dispatch 결정성**. systemd timer 가 fire 할 때마다 Hermes 가 `wh:ingest` playbook 을 reliably 진입하는 것 — playbook 내부의 LLM tool use 비결정성은 본 feature 범위 밖 (ADR-0006).

---

## 1. 배경 및 목적

### 1.1 v0.1.0 spec 의 가정

ADR-0002 (2026-05-13) lock 결정:
- agent invocation = `hermes -z "<prompt>"` (one-shot CLI subprocess)
- sync→ingest 트리거 = systemd timer → `hermes -z "/wh:ingest --vault X"`

ADR-0011 (2026-05-13) lock 결정:
- skill namespace prefix = `wh:` (default), `wh-` (fallback)
- fallback policy = install.sh 가 colon escape 이슈 시 `wh-` 자동 치환

ADR-0012 (2026-05-13) lock 결정:
- `wikihub.yaml.agent` 스키마: `binary` + `oneshot_args` + `skill_prefix`
- ExecStart 합성: `{agent.binary} {agent.oneshot_args[*]} "<prompt>"`
- install.sh 가 agent type 별 default 매핑 — v0.1.0 은 **hermes default 만 검증**

### 1.2 F4 surface 결함 #12

`features/backlog.md` L:11:

> Hermes 의 `-z` 가 LLM prompt 직접 전달 — wikihub spec 의 `wh:<skill>` slash-command 자동 매핑 안 함. ADR-0002·0011·0012 의 hermes invocation 가정과 실 Hermes 동작 mismatch

### 1.3 본 feature 의 목적

**ADR-0002·0011·0012 의 가정을 실제 Hermes 동작에 맞춰 정합화**. 산출물:
- 5 개 wikihub 명령 (ingest·lint·query·graphify·setup) 의 Hermes skill 등록
- install.sh 의 skill registration step 구현 (현재 `_step6_agent_skill()` stub)
- systemd unit ExecStart 의 skill-dispatch 형 invocation
- ADR Note 또는 신규 ADR (skill 등록 정책)

v0.1.0 acceptance 의 **마지막 blocker** — 본 feature 가 lock 되면 F4+update_mode+install_scope_reduction+F5 일괄 release 가능.

---

## 2. Hermes 실측 결과 (Step 2 핵심 입력)

ADR-0002 참조 docs (`hermes-agent.nousresearch.com/docs`) 확인 결과:

### 2.1 CLI invocation

| 항목 | 실측 |
|---|---|
| `hermes -z "<prompt>"` | "single prompt in, final response text out, nothing else on stdout or stderr" — LLM 직답만 |
| `hermes -z` + `--toolsets` / `-s --skills` 조합 | **docs 에 미문서화** — 보장 안 됨 |
| `hermes chat -q "<prompt>"` | 1회성 query, full transcript (tool output 포함) |
| `hermes chat -s <skill_name> -q "<prompt>"` | **skill 명시 preload + slash-command dispatch 의 표준 path** |

### 2.2 Skills 시스템

| 항목 | 실측 |
|---|---|
| skill 저장 위치 | `~/.hermes/skills/` (primary) |
| 외부 dir | `~/.hermes/config.yaml` 의 `skills.external_dirs` 로 추가 등록 |
| skill 정의 형식 | `SKILL.md` + YAML frontmatter |
| 필수 frontmatter 필드 | `name`, `description`, `version`, `platforms`, `metadata` |
| skill name 의 colon (`:`) 지원 | **docs 미명시** — 예시는 모두 하이픈 (`duckduckgo-search`, `deploy-k8s`) |
| skill 호출 형식 | "Every installed skill is automatically available as a slash command" |
| `hermes skills` subcommand | install/list/inspect/uninstall/update/audit/snapshot/tap/config 등 (no `exec`) |

### 2.3 핵심 mismatch 정리

| ADR 가정 | 실제 Hermes 동작 | 영향 |
|---|---|---|
| `hermes -z "/wh:ingest --vault X"` 가 `wh:ingest` skill 호출 | `-z` 는 LLM-text 전용. skill dispatch 보장 X | **systemd ExecStart 재정의 필요** |
| skill name `wh:ingest` (colon prefix) | docs 예시는 하이픈만 | **ADR-0011 default 를 `wh-` 로 변경** (fallback → default 승격) |
| skill 등록 메커니즘 미명세 | `~/.hermes/skills/` 또는 `external_dirs` | **install.sh 가 둘 중 하나 자동화 필요** |

---

## 3. 현행 진단

### 3.1 install.sh `_step6_agent_skill()` (L:701-706)

```bash
_step6_agent_skill() {
    info "Step 6: agent skill 등록 (stub)"
    # v0.1.0 minimal. Hermes/codex/gemini 별 메커니즘은 ADR-0012 + F5 에서 정본화
    return 0
}
```

**stub 상태** — 실제 skill 등록 0건. F5 의 핵심 구현 target.

### 3.2 `_step8_best_effort_wh_setup()` (L:1200-1215)

```bash
agent_binary="$(... yaml.agent.binary ...)"
timeout 300 "$agent_binary" -z "/wh:setup" 2>&1 | ...
```

**`-z` 직접 호출** — 실측 결과 LLM 자연어 해석에 맡겨짐. `/wh:setup` slash-command 가 skill dispatch 됨을 보장 못함.

### 3.3 `render_systemd_units.py` substitution (L:145-163)

```python
agent_binary = agent.get("binary", "")
oneshot_args = agent.get("oneshot_args") or []
agent_invocation_parts = [agent_binary] + [str(a) for a in oneshot_args]
agent_invocation = " ".join(agent_invocation_parts).strip()
```

ExecStart 합성: `{agent_invocation} "<prompt>"` — yaml 의 `oneshot_args: ["-z"]` 그대로. **skill name 이 invocation 에 안 들어감** — Hermes 가 어떤 skill 을 호출해야 하는지 모름.

### 3.4 `wikihub.yaml.example` (L:52-57)

```yaml
agent:
  type: hermes
  binary: /usr/local/bin/hermes
  oneshot_args: ["-z"]
  skill_prefix: "wh:"
```

`-z` + `wh:` 둘 다 실측과 mismatch.

### 3.5 `_system/skills/` 존재 X

전체 surface 한 결과 디렉토리 미존재. F5 신설 산출물.

---

## 4. 옵션 분석

### 4.1 (α) Hermes skill 등록 + `chat -s -q` dispatch

- `_system/skills/wh-<cmd>/SKILL.md` 5건 정본 (ingest·lint·query·graphify·setup)
- install.sh 가 `~/.hermes/config.yaml` 의 `external_dirs` 에 `$WIKIHUB_HOME/_system/skills` append
- yaml.agent schema 확장 — `oneshot_args` 에 skill placeholder 도입
- systemd ExecStart: `hermes chat --skills wh-<cmd> -q "/wh-<cmd> --flag X"`
- ADR-0002 Note 추가 (-z → chat -q). ADR-0011 default 를 `wh-` 로 (Note 또는 supersede). 신규 ADR-0032 (skill registration policy)

**장점**:
- Hermes 표준 path. agent CLI 의 native dispatch.
- `external_dirs` 사용 시 git pull 만으로 skill 갱신 자동 propagation — update_mode 와 정합.
- ADR-0006 (agent = orchestrator) 정합 — agent 가 procedure 를 read + execute.
- Hermes 의 `hermes skills list` 등 표준 운영 도구 사용 가능.

**단점**:
- ADR-0002 (`-z` 채택) 와 ADR-0011 (`wh:` default) 둘 다 갱신 필요.
- `external_dirs` 가 사용자 `~/.hermes/config.yaml` 을 건드림 — wikihub 외부 파일 변경 (운영자 동의 surface 필요).
- Hermes 가 SKILL.md 의 procedure 를 LLM 으로 해석 — playbook 의 procedural 정확도는 LLM 의존 (단, 이건 ADR-0006 의 기본 가정이라 본 feature 의 새 단점 아님).

### 4.2 (β) wrapper dispatcher script

- `scripts/agent_run.sh "/wh-<cmd> --flag X"` 가 prompt parse → 직접 Python helper 호출 (Hermes 우회)
- systemd ExecStart: `bash $WIKIHUB_HOME/scripts/agent_run.sh "/wh-<cmd> ..."`
- skill 등록 0건. Hermes 는 best-effort 운영자 manual 사용만.

**장점**:
- agent CLI 비의존. determinism 최대.
- Hermes mismatch 우회 — `-z` vs `chat -q` 논쟁 자체 회피.

**단점**:
- **ADR-0006 충돌** — agent 가 orchestrator 라는 정본 가정 위반. Python wrapper 가 procedure 를 실행하면 LLM 의 semantic phase (ingest 의 entity extraction, lint 의 자연어 검증) 가 불가능.
- 본 옵션 채택 시 wikihub 의 핵심 가치 제안 (agent-mediated wiki update) 자체 무효화.
- `_system/commands/*.md` 의 playbook 5건이 전부 procedural script 로 재작성 필요 — v0.1.0 범위 폭발.

### 4.3 (γ) Hybrid — wrapper + skill (옵션 양립)

- systemd ExecStart 가 wrapper script 호출 → wrapper 가 `hermes chat -s -q` 로 dispatch
- 1단계 indirection 추가, but agent-agnostic 보장

**장점**:
- 향후 agent 교체 (codex/gemini) 시 wrapper 만 수정 — systemd unit 영향 0.
- ExecStart line 길이 축소 가독성.

**단점**:
- v0.1.0 에서 wrapper 가 단순 passthrough 면 (α) 대비 indirection 만 추가.
- wrapper 자체 유지보수 부담.
- ADR-0012 의 yaml-driven dispatch 와 일부 중복 — single source of truth 흐림.

### 4.4 권장

**(α) 채택** — ADR-0006 정합 + Hermes 표준 path + external_dirs 의 update propagation.

(γ) 의 agent-agnostic 보강은 v0.2.x (codex/gemini 검증 시점) 까지 deferred — 그 때 wrapper script 도입이 surface 한 needs 기반으로 정당화.

### 4.5 v2 — CR2 관찰-2 의 (α)/(γ) 재평가 결과

CR2 관찰-2: "옵션 (α) 가 vault-fetch.py 의 ADR-0024 last_failure.json producer 책임을 우회 → 알림 사슬 dead. (γ) 부분 도입 (vault-fetch.py 가 hermes subprocess parent) 으로 ADR-0006+0024 둘 다 정합 가능."

**재검토 결과 — (α) 유지 채택**:
- 현 ADR-0006 의 unified orchestration 모델은 이미 vault-fetch.py 가 **agent 의 subprocess** (mechanical phase) — agent 가 parent. v0.1.0 의 vault-fetch.py 헤더 명시: "호출: agent (Hermes·codex·gemini 등) 가 systemd unit ExecStart 의 subprocess 로 실행."
- (γ) hybrid (vault-fetch.py 를 ExecStart entry point 로 승격) 는 ADR-0006 의 orchestration role 자체를 architectural reassign — v0.1.0 범위 폭발 (vault-fetch.py 가 hermes spawn 책임 + exit code mapping + ADR-0024 producer 책임 통합) + ingest 외 lint/query/graphify 의 별도 entry point 가 모두 필요.
- v0.1.0 acceptance 의 minimal change 원칙 (CLAUDE.md §2 Simplicity First) 정합. CR2-CRIT-1 의 알림 dead 사슬은 **install.sh 의 hermes prerequisite gate** (Hermes 미설치 시 systemd render/enable 자체 skip) 로 차단 — vault-fetch.py architectural pivot 불필요.
- (γ) 의 부분 도입은 **v0.2.x feature `hermes_wrapper`** 로 push. trigger 조건 = (a) Hermes exit code 의 transient/permanent contract 가 vault-fetch.py 의 exit 75/2 보장 미달 정량 측정, (b) codex/gemini 등 다른 agent 의 dispatch 추가 시 wrapper 자연 도입 시점.

본 v2 의 §5 설계는 (α) 채택 유지 + CR2 CRIT/HIGH 의 minimal-change 해결책 일괄 반영.

---

## 5. 설계 (옵션 α — v2)

### 5.1 skill 정의 — install-time materialized SKILL.md

5건의 SKILL.md 가 **install-time materialized** (5.2.B 결정 결과 — v2 갱신).

**Repo 상의 frontmatter source (5건, 신규)**:
- `_system/skills/wh-ingest.frontmatter.yaml`
- `_system/skills/wh-lint.frontmatter.yaml`
- `_system/skills/wh-query.frontmatter.yaml`
- `_system/skills/wh-graphify.frontmatter.yaml`
- `_system/skills/wh-setup.frontmatter.yaml`

**Install target (5건, install.sh `_step6_agent_skill` 가 materialized)**:
- `$WIKIHUB_HOME/_system/skills/_generated/wh-<cmd>/SKILL.md`

Materialization 절차:
1. `_system/skills/wh-<cmd>.frontmatter.yaml` 의 YAML 을 load.
2. `_system/commands/<cmd>.md` 본문 (정본 — CR1-CRIT-2 결과로 정본 위치 유지) 을 string 으로 read.
3. SKILL.md = `"---\n{frontmatter_yaml}\n---\n\n{commands_md_body}"` 합성.
4. `_generated/wh-<cmd>/SKILL.md` 에 atomic write (`os.replace`, ADR-0031 의 yaml writer 패턴 동일).

각 frontmatter source 예 (`wh-ingest.frontmatter.yaml`):

```yaml
name: wh-ingest
description: vault 의 변경 콘텐츠를 wiki 에 통합. systemd timer 가 호출하는 sync→ingest 자동화 사슬의 진입점.
version: 0.1.0
platforms: [linux]
metadata:
  tags: [wikihub, vault, ingest]
  category: knowledge-management
  config:
    wikihub_home_required: true
required_environment_variables:
  - WIKIHUB_HOME
  - WIKIHUB_INSTANCE_ROOT
```

> M-1 (frontmatter schema 미결 — `required_environment_variables` 표준 여부) 은 Step 3 VM 실측에서 확정. 미인식 필드는 build-time 검증 + frontmatter source 에서 제거.

### 5.2 playbook 정본 위치 — `_system/commands/` 유지 (5.2.B 채택)

**CR1-CRIT-2 결함**: v1 의 5.2.A 채택 (`_system/skills/` 단독 정본) 이 ADR-0006 §Decision + ADR-0010 §매트릭스 + wiki-schema.md L:20·L:315 의 `_system/commands/` 정본 lock 과 silent 충돌.

**v2 결정**: 5.2.B 채택 — `_system/commands/<cmd>.md` 가 **playbook 정본 유지**. `_system/skills/_generated/wh-<cmd>/SKILL.md` 는 install-time materialized artifact (frontmatter + 본문 결합본). 정본 위치는 ADR-0006 정합 + Hermes external_dirs 가 가리키는 path 는 `_generated/`.

**근거**:
- ADR-0006 §Decision (line 39-48, 53) 의 "`_system/commands/ingest.md` playbook이 전체 흐름의 정본" lock 보존.
- ADR-0010 §매트릭스 L:153 의 playbook path 정본성 보존.
- wiki-schema.md L:20·L:315 의 path 표기 변경 불필요.
- update_mode (ADR-0030) 의 git fetch+reset 흐름 정합 — `_system/commands/` 가 fetch 대상.
- CLAUDE.md §2 Simplicity First 정합 — minimal architectural drift.

**관계도**:
```
_system/commands/<cmd>.md           [정본 — ADR-0006]
  └→ install.sh _step6_agent_skill
       └→ _system/skills/_generated/wh-<cmd>/SKILL.md     [build artifact — git ignore]
            ↑
            external_dirs 가 가리키는 path

_system/skills/wh-<cmd>.frontmatter.yaml     [frontmatter source — git tracked]
  └→ 동일 _step6 가 결합
```

**`_generated/` 처리**:
- `.gitignore` 에 `_system/skills/_generated/` 추가.
- update_mode 의 git fetch+reset 가 `_generated/` 영향 X (untracked).
- install.sh 가 매 호출 시 idempotent 재생성 — `_step6_agent_skill` 책임.

### 5.3 external_dirs 등록 (v2 — CR2-CRIT-2 / HIGH-1·2 반영)

install.sh 의 `_step6_agent_skill()` 신규 책임:

#### 5.3.1 Hermes 존재 검사 + render/enable gate (CR2-CRIT-1)

```
1. `command -v hermes` 또는 `agent.binary` 의 존재·executable 검사.
2. 미존재 시:
   - stderr warn 출력 + install.log 에 명시 record.
   - 후속 step (_step8_systemd_render, _step8_5_systemd_enable_only) **skip flag** (`SKIP_SYSTEMD_RENDER=1`) 세팅.
   - install.sh 종료 코드 = 0 (success). 운영자가 hermes 설치 후 install.sh 재호출.
3. 존재 시 5.3.2 ~ 5.3.5 진행.
```

→ 알림 사슬 dead 회피 (CR2-CRIT-1). systemd unit 미생성이라 매 fire 의 exit 127 자체 발생 안 함.

#### 5.3.2 `~/.hermes/config.yaml` 의 안전 mutate (CR2-CRIT-2)

```
1. `~/.hermes/config.yaml.lock` advisory lock 획득 (`fcntl.flock(LOCK_EX | LOCK_NB)`).
   - 획득 실패 시 5초 retry × 12회 (총 60s). 최종 실패 → fail-fast + 안내 ("Hermes 가 동일 config 를 mutate 중 — install.sh 재시도").
2. PRE_HASH 캡처: `sha256sum ~/.hermes/config.yaml` (없으면 empty).
3. Backup 생성: `cp ~/.hermes/config.yaml ~/.hermes/config.yaml.wikihub-bak.<utc_iso>` (없으면 skip).
   - retention: install.sh 가 7일 초과 wikihub-bak.* 자동 cleanup.
4. ruamel.yaml round-trip load + modify (5.3.3) + `os.replace` atomic write.
5. POST_HASH 캡처. PRE→POST 변경된 경우만 install.log 에 record (path + backup path + diff line 개수).
6. flock release.
```

#### 5.3.3 external_dirs merge 의미론 (CR2-HIGH-1)

```python
wikihub_skill_dir = os.path.realpath(f"{WIKIHUB_HOME}/_system/skills/_generated")

existing = config.setdefault("skills", {}).setdefault("external_dirs", [])
existing_real = [os.path.realpath(p) for p in existing]

if wikihub_skill_dir in existing_real:
    # idempotent — no change
    return False
else:
    # append (operator-registered priority 보존)
    existing.append(wikihub_skill_dir)
    # marker comment (ruamel.yaml 의 CommentedSeq 활용)
    # comment: "managed by wikihub install.sh — remove to disable auto-discovery"
    return True
```

운영자 의도 보호:
- realpath 비교로 `~/wikihub/...` vs `/home/user/wikihub/...` 동치성 검출.
- marker comment 부재 + wikihub path 가 list 에 있으면 → operator 가 의도적 제거 후 직접 재등록한 케이스 → 그대로 보존, 갱신 안 함.
- marker 부재 + wikihub path 부재 → first install — append + marker 등록.

#### 5.3.4 동의 모델 — `WIKIHUB_NONINTERACTIVE=1` 통일 (CR2-HIGH-2)

```
- interactive 모드: 첫 패치 시 명시 prompt — "wikihub 가 ~/.hermes/config.yaml 의 skills.external_dirs 에 path 추가. backup: <path>. 계속? [y/N]".
- non-interactive (WIKIHUB_NONINTERACTIVE=1): 자동 동의 + stderr 안내 + install.log 명시 record. 별도 flag (--accept-hermes-config-patch) 도입 안 함 — 기존 NONINTERACTIVE 모델 일관성.
- README 의 NONINTERACTIVE 설명에 "외부 자산 (~/.hermes/config.yaml) 변경 동의 포함" 명시.
```

#### 5.3.5 등록 후 검증

```
1. Hermes 가 신 external_dirs 즉시 인식하는지 — `hermes skills list --json` 호출 후 `wh-*` 포함 확인.
2. 미포함 시 `hermes skills audit` 1회 호출 후 재검증.
3. 그래도 미포함 → warn ("hermes 재시작 후 인식될 수 있음 — `hermes skills audit` 또는 데몬 재시작 검토").
```

> M-5 (audit 자동 호출 필요 여부) 의 Step 3 VM 실측 결과로 본 단계의 audit 호출 정책 최종화.

#### 5.3.6 Materialization (5.1)

5.3.5 직전 (즉 5.3.2 flock 외부, lock 불필요 — `_generated/` 는 wikihub 내부) 에 5.1 의 SKILL.md materialization 실행. `_step6_agent_skill` 본문:

```
1. Hermes 존재 검사 (5.3.1)
2. 5건 SKILL.md materialization (5.1) → _generated/wh-<cmd>/SKILL.md
3. ~/.hermes/config.yaml 패치 (5.3.2 ~ 5.3.4)
4. 등록 검증 (5.3.5)
```

**copy 대안 기각 유지**: `~/.hermes/skills/` 직접 copy 는 update_mode 의 git fetch+reset 후 propagation 위해 매번 재copy 필요. external_dirs 가 path 참조 → 1회 등록 후 자동 propagation. 채택 유지.

### 5.4 yaml.agent schema 확장 (v2 — CR1-CRIT-1 / HIGH-1·2 반영)

#### 5.4.1 skill_prefix — `wh-` 보수적 lock (CR1-CRIT-1)

v1 의 "Hermes colon 지원 여부 확정 후 결정" 패턴은 Step 2 종료 모순 (§5 전체가 `wh-` 일괄 전제로 작성됨). v2 는 **보수적 `wh-` 선결정**:

- **default**: `skill_prefix: "wh-"`. 모든 spec / ExecStart / README / wiki-schema 표기 `wh-` 로 lock.
- **ADR-0011 처리**: §Decision 의 `wh:` 채택을 **Superseded** 처리 + 신규 ADR-0033 (skill prefix lock — `wh-`). ADR-0011 의 fallback policy (`wh-` 자동 치환) 가 신규 ADR 의 default 와 일치 — semantic 일관.
- **colon 호환 fallback Note**: Step 3 VM 실측에서 Hermes 가 colon 도 받음을 확인 시 → ADR-0033 의 Note 로 "operator override (`skill_prefix: wh:`) 호환 명시" 추가. default 는 `wh-` 유지.

기존 wikihub.yaml 운영본 (`wh:` 잔존 — install_scope_reduction 후 운영자 첫 호출로 생성된 케이스) 처리: 5.4.3 의 migration step.

#### 5.4.2 oneshot_args — contract migration (CR1-HIGH-1)

v1 은 `oneshot_args: ["chat", "--skills", "{skill}", "--query"]` 의 `{skill}` placeholder 를 도입했으나 ADR-0012 §Decision (정적 args) 의 의미론 변경 — Note 가 아니라 contract migration.

v2 결정:

- **ADR-0012 §Decision 갱신** (Status 유지, content 갱신 — Notes 섹션 추가):
  - `oneshot_args` 의 의미를 "정적 args" → "per-unit substitution 가능 args (placeholder: `{skill}`)" 로 명세 확장.
  - 다른 agent (codex/gemini/copilot) 의 매핑은 v0.2.x 검증 시점에 placeholder convention 유지.
- yaml schema (additive only — schema_version v1 호환):

```yaml
agent:
  type: hermes
  binary: /usr/local/bin/hermes
  oneshot_args: ["chat", "--skills", "{skill}", "--quiet", "--query"]   # {skill} placeholder + --quiet (5.4.4)
  skill_prefix: "wh-"
  timeout_sec: 600
  notify_on_fatal: true
```

> v1 의 `--query` 단독 → `--quiet --query` 로 변경 (5.4.4 의 transcript volume mitigation).

#### 5.4.3 operational yaml drift fix (CR1-HIGH-2)

기존 운영자가 install_scope_reduction 후 `wikihub.yaml` 을 생성했다면 `skill_prefix: "wh:"` + `oneshot_args: ["-z"]` 잔존. ADR-0031 §Decision B catalog 의 derived 4필드 (`instance.root`, `vaults[*].local_path` 등) 에 `agent.*` 미포함 → drift fix 미진행.

v2 결정 — **ADR-0031 catalog 에 `agent.skill_prefix` + `agent.oneshot_args` 추가는 ADR-0031 의 "agent.* 의도적 미관여" 정책과 충돌**. 본 v2 는 별도 migration step 채택:

- install.sh `_step6_agent_skill` 의 5.3.1 직후 (Hermes 존재 검사 후) `_migrate_agent_schema()` 신규:
  1. `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml` 의 `agent.skill_prefix` 가 `"wh:"` 이면:
     - interactive: 명시 confirm — "F5 후 default 가 `wh-`. operational yaml 의 `wh:` 를 `wh-` 로 patch? [y/N]".
     - non-interactive: 자동 patch + stderr 안내.
  2. `agent.oneshot_args` 가 `["-z"]` 또는 `{skill}` placeholder 미포함이면 동일 confirm + patch.
  3. ruamel.yaml round-trip + `os.replace` (yaml writer 패턴 일관).
  4. backup: `wikihub.yaml.wikihub-bak.<utc_iso>` (~/.hermes/config.yaml 과 동일 패턴).

ADR-0031 의 의도 (`agent.*` 는 메인테이너 선택 보존) 와 정합 — migration 은 **F5 의 1회성 schema lift**, 이후 운영 시점의 drift 는 잔존하지 않음.

#### 5.4.4 transcript volume mitigation — `--quiet` flag (CR1-HIGH-5 / CR2-HIGH-3)

Hermes docs 의 `hermes chat -Q --quiet` flag 확인 (CR2-HIGH-3 권장). v2 의 oneshot_args 에 `--quiet` 포함 (5.4.2). 효과:

- `chat --query` 의 transcript 출력 → final answer + tool output 일부만 (전체 transcript 미포함).
- systemd journal volume 폭증 방지.
- M-3 미결 → v2 에서 부분 lock (M-3 의 `--quiet` 효과 정확도는 Step 3 VM 실측).

V3 / V6 의 PASS 기준에 "1회 fire 당 stdout 크기 < 10 KB" 정량 기준 추가 (§9.3).

#### 5.4.5 placeholder fail-fast (CR2-HIGH-6)

`render_systemd_units.py` 의 substitution 단계에서 fail-fast 검증 (5.5 에서 상세).

#### 5.4.6 `_migrate_agent_schema` idempotency 보장 (R3 — CR3-1-HIGH-N1)

본 migration 은 **운영자 의도 보호 + idempotent**:

- 2번째 호출 시: 이미 `wh-` + `{skill}` placeholder 형식이면 no-op (string 비교).
- 운영자가 schema patch 후 yaml 을 다시 `wh:` 로 손편집한 경우:
  - 5.3.3 의 marker comment 패턴 적용 — yaml 의 `agent.skill_prefix` 옆에 `# managed by wikihub install.sh — wh:* 사용 시 Hermes dispatch 실패. 운영자 의도면 본 line 제거` marker.
  - 다음 install.sh 호출 시: marker 부재 + `wh:` 가 yaml 에 있으면 → operator 의도 명시 → migration skip + stderr 경고 only.
  - marker 존재 + `wh:` 가 yaml 에 있으면 → drift → 재 patch.

#### 5.4.7 yaml-driven `timeout` 의 read 메커니즘 (R3 — CR3-1-HIGH-N3)

`_step8_wh_setup_skill_meta` 의 `timeout {agent.timeout_sec}` 는 bash 외부 명령 `timeout` 의 인자. yaml read 는 5.3.1 의 `agent_binary` 추출과 동일 패턴:

```bash
timeout_sec="$("$VENV_PATH/bin/python3" -c "import yaml,sys; print(yaml.safe_load(open(sys.argv[1])).get('agent',{}).get('timeout_sec', 600))" "$WIKIHUB_INSTANCE_ROOT/wikihub.yaml")"
timeout "$timeout_sec" "$agent_binary" chat --skills wh-setup --quiet --query "/wh-setup"
```

default fallback = 600 (yaml.example default 정합).

### 5.5 `render_systemd_units.py` substitution 확장 (v2 — CR1-HIGH-3 / CR2-HIGH-6 반영)

#### 5.5.1 per-unit substitution helper

기존 (L:145-163) 의 `agent_invocation` 합성은 unit-agnostic 단일 값. F5 가 per-skill `{skill}` 치환 추가:

```python
def _per_skill_invocation(cfg: dict, skill_name: str) -> str:
    agent = cfg.get("agent") or {}
    binary = agent.get("binary", "")
    oneshot_args = agent.get("oneshot_args") or []
    # placeholder 검증 — fail-fast (CR2-HIGH-6)
    has_placeholder = any("{skill}" in str(a) for a in oneshot_args)
    if not has_placeholder:
        raise SystemExit(
            f"agent.oneshot_args missing '{{skill}}' placeholder — "
            f"wikihub F5 schema requires per-skill substitution. "
            f"yaml path: {cfg.get('_path', 'wikihub.yaml')}"
        )
    resolved = [str(a).format(skill=skill_name) for a in oneshot_args]
    return " ".join([binary] + resolved).strip()
```

#### 5.5.2 substitution dict 확장

`_instance_wide_subs` 에 5건의 per-skill key 추가:

```python
substitutions["agent_invocation_for_wh_ingest"] = _per_skill_invocation(cfg, "wh-ingest")
substitutions["agent_invocation_for_wh_lint"] = _per_skill_invocation(cfg, "wh-lint")
substitutions["agent_invocation_for_wh_query"] = _per_skill_invocation(cfg, "wh-query")
substitutions["agent_invocation_for_wh_graphify"] = _per_skill_invocation(cfg, "wh-graphify")
substitutions["agent_invocation_for_wh_setup"] = _per_skill_invocation(cfg, "wh-setup")
```

기존 `agent_invocation` 단일 key 는 유지 (다른 코드 site 호환 — best-effort wh-setup 호출 등).

#### 5.5.3 systemd unit template ExecStart 변경 (CR1-HIGH-3)

기존 (`{skill_prefix}ingest` — slash 미포함, dispatch fail):

```
# wikihub-vault@.service.template:19
ExecStart={agent_invocation} "{skill_prefix}ingest --vault %i"
```

신규 (slash 명시 + per-skill key):

```
ExecStart={agent_invocation_for_wh_ingest} "/wh-ingest --vault %i"
```

5개 template 일괄 변경:
- `wikihub-vault@.service.template` → `{agent_invocation_for_wh_ingest} "/wh-ingest --vault %i"`
- `lint.service.template` → `{agent_invocation_for_wh_lint} "/wh-lint"`
- (query/graphify timer 는 v0.2.x — v0.1.0 에 timer 없음)

#### 5.5.4 render 후 systemd 문법 검증 (CR2-HIGH-6)

`_step8_systemd_render` 종료 시 `systemd-analyze --user verify ~/.config/systemd/user/*.service` 자동 호출. 실패 시 fail-fast — 신 schema 의 placeholder 누락 등 silent bug 차단.

#### 5.5.5 rollback compatibility (CR2-HIGH-7)

update_mode 의 trap rollback (ADR-0030 sub-3) 시 `_step8_systemd_render` 재호출. F5 이전 ref 로 rollback 된 경우 `render_systemd_units.py` 는 F5 이전 버전 (placeholder 없는 oneshot_args 처리). 본 경우 5.5.1 의 fail-fast 가 발동 → rollback 도 실패 가능.

해결책:
- `render_systemd_units.py` 에 yaml schema version 검증 추가 — `agent.oneshot_args` 의 placeholder 부재 시 fail 메시지에 "F5 이전 코드 — wikihub.yaml 의 oneshot_args 를 `["-z"]` 로 rollback 필요" 안내.
- 운영자 mental model: rollback 은 wikihub repo + operational yaml 둘 다 schema 정합 필요. F5 의 yaml migration (5.4.3) 의 backup (`wikihub.yaml.wikihub-bak.<ts>`) 가 rollback 시 복원 source.
- ADR-0030 §부정/제약 에 cross-feature 영향 surface (Note 추가).

### 5.6 install.sh 변경 (v2 — CR1-CRIT-3 함수명 fix)

| 위치 | 변경 |
|---|---|
| `_step6_agent_skill()` (L:701-706) | stub 제거 → 5.3 절차 (Hermes 존재 검사 + SKILL.md materialization + external_dirs 패치 + 등록 검증). `_migrate_agent_schema()` 호출 추가. |
| `_step8_wh_setup_skill_meta()` (L:1201) — **함수명 v1 오기 fix (`_step8_best_effort_wh_setup` → `_step8_wh_setup_skill_meta`)** | `hermes -z "/wh:setup"` → `hermes chat --skills wh-setup --quiet --query "/wh-setup"`. bash `timeout 300` → `timeout {agent.timeout_sec}` (yaml-driven). |
| 신규 `_migrate_agent_schema()` | 5.4.3 의 절차 (skill_prefix·oneshot_args drift fix + backup). |
| 신규 `SKIP_SYSTEMD_RENDER` flag | 5.3.1 의 Hermes 미존재 시 `_step8_systemd_render` 와 install.sh 후속의 모든 systemd unit enable·daemon-reload 호출 둘 다 skip. install.sh main loop 의 `_step8_systemd_render` (L:1306) + `_step8_wh_setup_skill_meta` (L:1307) 진입 직전 `[[ -n "$SKIP_SYSTEMD_RENDER" ]] && return 0` guard. |

함수명 정합 확인 (CR1-CRIT-3 fix):
- 설계서 §3.2·§5.6 의 함수명을 install.sh 정본 (`_step8_wh_setup_skill_meta` at L:1201) 으로 일관.
- install.sh 의 systemd 후속 단계 구조 (R3-CR3-1-CRIT-N2 fix): main loop 는 `_step8_systemd_render` → `_step8_wh_setup_skill_meta` 순서. 별도 `_step8_5_systemd_enable_only` 함수는 정본에 미존재 — v1 의 가정 오류. enable·daemon-reload 는 `_step8_systemd_render` 내부 책임. SKIP_SYSTEMD_RENDER flag 가 `_step8_systemd_render` 자체를 skip 하면 enable 도 자동 skip.
- 본 함수의 `[[ "$INSTALL_MODE" != "update" ]] && return 0` (L:1202) guard 영향: 신규 install (V1) 시점에는 본 함수 skip → V6 의 검증 timing 은 update path 만 cover. §9.3 V6 PASS 기준에 명시.

### 5.7 `_system/commands/` 처리 (v2 — 5.2.B 채택 결과)

v1 의 5.7.A (stub Note 만) / 5.7.B (디렉토리 삭제) 는 모두 v2 에서 **불필요**. 5.2.B 결정 (`_system/commands/` 가 playbook 정본 유지) 으로 commands/ 디렉토리는 **변경 없음** — 본문도 그대로, path 도 그대로.

본 feature 의 commands/ 영향:
- `_system/commands/ingest.md` 의 §호출 line `<agent_invocation> "/wh:ingest --vault <vault_id>"` → `<agent_invocation_for_wh_ingest> "/wh-ingest --vault <vault_id>"` (skill_prefix lock 정합).
- 5건 모두 동일 패턴 — §호출 부분의 prefix 만 `wh:` → `wh-` (CR1-CRIT-1 결과 정합).
- 본문 procedure 는 그대로 (Hermes 의 LLM 이 SKILL.md materialized 본문으로부터 동일 procedure read 가능).

### 5.8 wikihub.yaml.example 변경 (v2)

```yaml
# Before
oneshot_args: ["-z"]
skill_prefix: "wh:"

# After
oneshot_args: ["chat", "--skills", "{skill}", "--quiet", "--query"]
skill_prefix: "wh-"
```

ADR-0031 의 schema version (v1) 유지 — additive change only. `version` 키 bump 불요 (§Decision E 의 example_version 검증 통과 — schema 의 key 추가/제거 없음, 값만 변경).

operational `wikihub.yaml` 의 drift fix 는 `_migrate_agent_schema()` (5.4.3) 책임.

---

## 6. 개정 전/후 비교

### 6.1 ExecStart 합성

| 항목 | Before | After |
|---|---|---|
| vault@.service | `hermes -z "/wh:ingest --vault gdrive"` | `hermes chat --skills wh-ingest --quiet --query "/wh-ingest --vault gdrive"` |
| lint.service | `hermes -z "/wh:lint"` | `hermes chat --skills wh-lint --quiet --query "/wh-lint"` |
| lint.service (--apply) | `hermes -z "/wh:lint --apply"` | `hermes chat --skills wh-lint --quiet --query "/wh-lint --apply"` |
| `_step8_wh_setup_skill_meta` | `hermes -z "/wh:setup"` | `hermes chat --skills wh-setup --quiet --query "/wh-setup"` |

### 6.2 skill name

| 명령 | Before | After |
|---|---|---|
| ingest | `wh:ingest` | `wh-ingest` |
| lint | `wh:lint` | `wh-lint` |
| query | `wh:query` | `wh-query` |
| graphify | `wh:graphify` | `wh-graphify` |
| setup | `wh:setup` | `wh-setup` |

운영자 mental model: README + commands 본문 + ADR 모두 `wh-` 표기로 일괄.

### 6.3 install.sh 책임

| Step | Before | After |
|---|---|---|
| Step 6 | stub | external_dirs append + Hermes 미설치 detect + 5 skill 인식 검증 |
| Step 8 (best-effort) | `hermes -z "/wh:setup"` | `hermes chat --skills wh-setup --query "/wh-setup"` |

---

## 7. 연계 룰/스킬 정합성 검토

### 7.1 ADR 영향 (v2)

| ADR | 영향 | 처리 |
|---|---|---|
| **ADR-0002** | `-z` 채택 → `chat --skills --quiet --query` 변경 | **Note 추가** (Status 유지) — F5 의 실측 결과 + 옵션 (α) 분기 명시 |
| **ADR-0006** | unified orchestration (agent=orchestrator) | **영향 없음** — 5.2.B 채택으로 commands/ 정본 보존. skill registration 은 build artifact (CR1-CRIT-2 해결) |
| **ADR-0010** | operational tooling split | **Note 추가** — install.sh `_step6_agent_skill` 책임 명시화 (5.3 절차) + L:153 `--playbook` path 표기 정합 검증 (commands/ 유지로 path 변경 0) |
| **ADR-0011** | `wh:` default + `wh-` fallback | **Superseded by ADR-0033** (`wh-` lock — v2 의 CR1-CRIT-1 해결). Step 3 VM 의 colon 부분 동작 결과는 ADR-0033 의 Note 만 |
| **ADR-0012** | agent.binary + oneshot_args + skill_prefix | **§Decision 갱신** (Status 유지, content 변경) — `oneshot_args` 의 placeholder substitution semantics 추가 (CR1-HIGH-1) |
| **ADR-0023** | install.sh distribution + safety guard | **§safety guard 확장 Note** — wikihub 외부 자산 (`~/.hermes/config.yaml`) mutate 의 backup + flock + 동의 surface 추가 (CR1-HIGH-6 / CR2-CRIT-2 해결) |
| **ADR-0024** | fatal alert contract | **Note 추가** — Hermes 미설치 시 systemd unit 미생성 정책 명시 (CR2-CRIT-1 해결). last_failure.json producer 책임 우회 안 함 (install.sh 의 prerequisite gate 가 차단) |
| **ADR-0030** | update workflow orchestration | **§부정/제약 확장 Note** — yaml schema migration 의 rollback 책임 (CR2-HIGH-7 해결). render_systemd_units.py 의 fail-fast 가 schema mismatch detect |
| **ADR-0031** | yaml materialization | **§Decision 보강 Note** — `agent.*` 의 catalog 미포함 정책 유지, F5 의 schema lift 는 별도 `_migrate_agent_schema()` 책임 (CR1-HIGH-2 해결) |
| **ADR-0032 (신규)** | Hermes skill registration policy | 신설 — external_dirs vs copy, materialization 모델, idempotent guard, marker comment, backup/flock policy (CR1-MED-1 권장 따라 sub-decision 분리) |
| **ADR-0033 (신규)** | skill prefix `wh-` lock | 신설 — ADR-0011 supersedes. CR1-CRIT-1 의 보수적 선결정 |

### 7.2 `_system/commands/` 및 wiki-schema 정합

5.2.B 채택 (commands/ 정본 유지) — wiki-schema.md L:20·L:315 의 path 표기 **변경 없음**. orchestration table (L:319-324) 의 `/wh:<cmd>` → `/wh-<cmd>` 표기 일괄 치환만.

치환 대상 파일:
- `_system/wiki-schema.md` (L:319-324)
- `_system/commands/{ingest,lint,query,graphify,setup}.md` 의 §호출 line
- `README.md` L:179 (CR1-MED-6)
- `AGENTS.md` (운영 타깃 안내)
- features/active 의 본 v2 (자기참조 — 변경 불요)
- `docs/adr/*` 의 `/wh:<cmd>` 인용 (검색 후 일괄 — supersede ADR 작성 시 동시)

### 7.3 update_mode (ADR-0030) 정합 (v2)

- `_systemd_stop_before_update` + `_step8_systemd_render` 의 ExecStart 합성은 `render_systemd_units.py` 의 신 placeholder 모델 사용. trap rollback 시 신/구 schema 정합은 5.5.5 의 fail-fast + ADR-0030 §부정/제약 Note 로 surface.
- VERSION bump 불필요 — F4·update_mode·install_scope_reduction 의 `_system/VERSION` 그대로.
- rollback 시 `wikihub.yaml.wikihub-bak.<ts>` (5.4.3 의 backup) 가 schema 복원 source — 운영자가 수동 복원 가능. 자동 rollback 은 v0.2.x 검토 (ADR-0030 §재검토 트리거 항목으로 추가).

### 7.4 install_scope_reduction (ADR-0031) 정합 (v2 — CR1-MED-5 / CR2-HIGH-8 정정)

**v1 의 잘못된 분석 정정**: v1 §7.4 는 "sparse-checkout fetch list 에 `/_system/skills/` 추가 필요" 라고 명시했으나, install.sh:290 의 `WIKIHUB_SPARSE_PATHS=(_system scripts install.sh wikihub.yaml.example README.md LICENSE)` 가 이미 `_system` 전체 fetch. `_system/skills/wh-<cmd>.frontmatter.yaml` 은 **자동 cover**. 별도 patch 불요.

v2 정정: §7.4 = "sparse-checkout 영향 없음 — 신규 frontmatter source 5건은 `_system` 의 자동 cover. 운영-time materialized `_system/skills/_generated/` 는 git untracked".

`/wh:setup` Step 0 (yaml materialization, ADR-0031) — `_migrate_agent_schema()` (5.4.3) 와 별도 책임 (Step 0 = 첫 호출 시 .example → wikihub.yaml 생성, `_migrate_agent_schema` = F5 의 1회성 schema lift). 둘이 idempotent 호환.

---

## 8. 미결 사항 (v2 — lock 진행 + 잔존 항목 분리)

### 8.1 v2 에서 lock 된 항목

| ID (v1) | 결정 | 근거 |
|---|---|---|
| M-2 | (α) 채택 유지 — dispatch 결정성 임계치는 Step 3 VM 의 95%+ 로 변경 (CR1-MED-2 권장) | LLM-mediated dispatch 의 stochastic 특성 인정 + ADR-0006 의 LLM 비결정성 범위 외 invariant |
| M-3 | `--quiet` flag yaml.agent.oneshot_args default 포함 (5.4.4). Step 3 VM 에서 효과 정량 측정 | CR1-HIGH-5 / CR2-HIGH-3 해결 |
| M-4 | ADR-0011 superseded by ADR-0033 (`wh-` lock). VM 의 colon 부분 동작은 ADR-0033 의 Note 만 | CR1-CRIT-1 해결 |
| M-7 | 5.2.B 채택으로 commands/ → skills/ 이전 자체 없음. cross-link 영향 zero | CR1-CRIT-2 해결 |
| M-8 | `--accept-hermes-config-patch` flag 신설 안 함. `WIKIHUB_NONINTERACTIVE=1` 단일 toggle 이 외부 자산 동의 포함 (5.3.4) | CR2-HIGH-2 해결 |

### 8.2 Step 3 VM 실측 의존 잔존 (4건)

| ID | 항목 | VM 검증 |
|---|---|---|
| M-1 | SKILL.md frontmatter schema 의 `required_environment_variables` 표준 여부 | V2 의 `hermes skills list --json` 결과로 frontmatter 인식 필드 surface. 미인식 필드 제거 후 v3 또는 Step 3 backport |
| M-2' | dispatch 결정성 임계치 — 30회 호출 중 28건 (≥93%) 진입 | V3 의 정량 measurement (sample 30, p50/p95 latency 포함) |
| M-5 | `external_dirs` 추가 후 Hermes 즉시 인식 vs `audit` 1회 필요 | V5a (재시작 없이) + V5b (audit 1회) 분리 측정 (CR2-MED-2 권장) |
| M-9 | (신규, CR2-HIGH-4) Hermes exit code contract — 429/503/timeout 의 코드 mapping | V8 신규 — 의도적 LLM fail 케이스의 exit code 측정. 결과 따라 systemd `SuccessExitStatus` 또는 yaml.agent.retryable_exit_codes 결정 |

### 8.3 v0.2.x 이양

| 항목 | 사유 |
|---|---|
| (γ) hermes_wrapper 부분 도입 | CR2-HIGH-4 의 exit code 가 vault-fetch.py 의 exit 75/2 보장 미달 시 trigger. v0.1.0 은 (α) + install.sh prerequisite gate 로 충분 |
| ADR-0024 의 `notify_via_hermes()` stub 채움 | 관찰-1 — F5 는 invocation 정합 한정. notify 본문은 별도 v0.2.x feature |
| per-skill enable/disable 정책 | CR2-MED-7 — 5건 일괄 등록 가정 유지. 운영자 disable 은 Hermes side `skills config disable` |
| skill staleness alert | CR2-MED-4 — `_state/<vault>/last_ingest.json` + ops-alert.py 확장. ADR-0024 의 fallback diagnostic 확장 |
| Hermes binary version 검증 | CR2-MED-1 — gws_min_version 패턴의 hermes_min_version 도입. Hermes versioning stability 확보 후 |

---

## 9. Definition of Done (v2)

### 9.1 Step 2 종료 조건 (analysis_and_design.md)

- [x] R2 multi-model design review (CR1 spec + CR2 SRE)
- [x] CRIT 5 + 핵심 HIGH 5 일괄 반영 (v2)
- [ ] (사용자 결정) v3 재-review 또는 본 v2 lock 후 Step 3 진입
- [ ] 사용자 승인 (`approved: 2026-XX-XX` 마커)

### 9.2 Step 3 종료 조건 (구현)

**산출물 — repo tracked**:
- [ ] `_system/skills/wh-<cmd>.frontmatter.yaml` 5건 신설 (5.1)
- [ ] `_system/commands/<cmd>.md` 5건 — `<agent_invocation>` 표기는 per-skill key 로 갱신 + `wh:` → `wh-` (5.7)
- [ ] `install.sh _step6_agent_skill()` 구현 (5.3 절차 — Hermes detect + materialization + external_dirs 패치 + 검증)
- [ ] `install.sh _step8_wh_setup_skill_meta()` 함수명 정합 + `-z` → `chat --skills --quiet --query` (5.6)
- [ ] `install.sh _migrate_agent_schema()` 신규 (5.4.3)
- [ ] `install.sh SKIP_SYSTEMD_RENDER` flag + `_step8_systemd_render`·`_step8_5_systemd_enable_only` skip 분기 (5.3.1)
- [ ] `scripts/_helpers/render_systemd_units.py` placeholder fail-fast (5.5.1) + per-skill key 5건 (5.5.2) + `systemd-analyze --user verify` 호출 (5.5.4)
- [ ] systemd unit template 5건 ExecStart 갱신 (5.5.3 — slash 포함 + per-skill key)
- [ ] `wikihub.yaml.example` agent 섹션 갱신 (5.8)
- [ ] `_system/wiki-schema.md` L:319-324 orchestration table 표기 갱신 (7.2)
- [ ] `README.md` L:179 (F5 archive) + install snippet prerequisite 신규 (hermes 사전 설치 + ~/.hermes mutate 동의) (CR2-LOW-4)
- [ ] `.gitignore` 에 `_system/skills/_generated/` 추가 (5.2)

**ADR — repo tracked**:
- [ ] ADR-0032 (skill registration policy) — Status Accepted (7.1)
- [ ] ADR-0033 (skill prefix lock `wh-`) — Status Accepted, supersedes ADR-0011 (7.1)
- [ ] ADR-0002 Note 추가
- [ ] ADR-0006 — 영향 없음 명시 (CR1-CRIT-2 의 ADR-0006 정본성 보존)
- [ ] ADR-0010 Note 추가 (Step 6 책임)
- [ ] ADR-0011 Status → Superseded by ADR-0033 + `Superseded by: ADR-0033` 마커
- [ ] ADR-0012 §Decision 갱신 (placeholder semantics) + ADR-0011 cross-ref 가 supersede 후 ADR-0033 로 redirect
- [ ] ADR-0023 §safety guard Note 확장
- [ ] ADR-0024 Note (Hermes 미설치 시 unit 미생성)
- [ ] ADR-0030 §부정/제약 Note (yaml schema migration rollback)
- [ ] ADR-0031 §Decision Note (agent.* catalog 미포함 + F5 의 별도 migration)
- [ ] **ADR-0033 본문 `Supersedes: ADR-0011` 마커** (양방향 link — R3 CR3-1-HIGH-N2)
- [ ] **`docs/adr/README.md` 인덱스 갱신** — ADR-0011 줄에 "(superseded)" + ADR-0033 항목 신규 (R3 CR3-1-HIGH-N2)
- [ ] **`_system/wiki-schema.md` L:340·L:347 의 `wh:` colon 표기 정합** (`wh-` 또는 supersede 명시) (R3 CR3-1-HIGH-N2)

### 9.2.1 R3 추가 DoD — release-time decision + 운영 절차 (R3 CR3-2 권장)

Step 3 진입 후 VM 측정·구현 시 backport 가능한 4 항목. v3 본문 변경 불필요 — DoD 만 확장:

- [ ] **V8 결과 기반 v0.1.0 release-time decision matrix** (R3 CR3-2 B-HIGH-1): Hermes exit code 측정 후 결정 표. transient (LLM 503/429/timeout) → systemd `SuccessExitStatus=0 75` 매핑 vs `retryable_exit_codes` yaml 추가 vs `Restart=on-failure` 추가 중 택1. 결과 lock 시점 = Step 3 VM V8 종료.
- [ ] **`render_systemd_units.py` 의 `timeout_start_sec` placeholder** (R3 CR3-2 B-HIGH-2): yaml.agent.timeout_sec 와 systemd TimeoutStartSec sync — 두 값을 yaml 단일 source 로 render-time substitution. wikihub-vault@.service.template + lint.service.template 의 `TimeoutStartSec={timeout_start_sec}sec` 갱신.
- [ ] **`systemd-analyze --user verify` 실패 처리 절차** (R3 CR3-2 B-MED-4): verify fail 시 install.sh 동작 — (a) 이미 atomic-written unit 의 `.tmp` 가 아닌 정본 파일이라 revert 책임은 install.sh 의 일반 trap (ADR-0030 sub-3 의 `_rollback_if_failed`). verify fail → install.sh exit 1 + 운영자 안내 ("syntax error in rendered unit — render_systemd_units.py 로직 또는 yaml schema 결함 의심").
- [ ] **stale `_generated/wh-*` cleanup step** (R3 CR3-2 B-MED-5): `_step6_agent_skill` 의 materialization 직전 — `_generated/` 내 기존 `wh-*` 디렉토리 중 v2 의 5건 (`wh-ingest·wh-lint·wh-query·wh-graphify·wh-setup`) 외 entries 가 있으면 (v0.2.x 의 skill 이름 변경 또는 deprecated skill) 삭제. orphan cleanup 보장.

### 9.3 VM 테스트 (Step 3 자가 검증, v2)

**VM 환경 행렬** (CR1-MED-3 / CR2-LOW-2):
- **VM-A** (Hermes 설치) → V1~V6, V8
- **VM-B** (Hermes 미설치 — PATH 차단 또는 binary 임시 제거) → V7

| V<N> | 환경 | 검증 항목 | PASS 기준 |
|---|---|---|---|
| V1 | VM-A | install.sh 신규 install + Step 6 진입 | (1) `_system/skills/_generated/wh-*/SKILL.md` 5건 생성. (2) `~/.hermes/config.yaml` 에 wikihub `_generated` realpath 등록 + marker comment. (3) `~/.hermes/config.yaml.wikihub-bak.<ts>` 생성 |
| V2 | VM-A | skill 인식 — `hermes skills list --json` | 5건 (wh-ingest·wh-lint·wh-query·wh-graphify·wh-setup) state=enabled |
| V3 | VM-A | vault@.service 1회 fire — `hermes chat --skills wh-ingest --quiet --query "/wh-ingest --vault gdrive"` | (1) skill dispatch 진입. (2) `wiki/sources/gdrive/log.md` 갱신 (CR1-HIGH-4 fix). (3) stdout 크기 < 10 KB (CR1-HIGH-5) |
| V3' | VM-A | dispatch 결정성 — V3 30회 반복 | ≥ 28건 (≥93%) 진입 (M-2'). p50/p95 latency 기록 |
| V4 | VM-A | 멱등성 — V3 재호출 (vault 변경 없음) | source_mtime drift 0 + log.md 항목 추가 0 (ingest skip) |
| V5a | VM-A | external_dirs 등록 후 즉시 인식 (Hermes 재시작 없이) | V2 결과 5건 표시 → PASS, 미표시 → V5b |
| V5b | VM-A | `hermes skills audit` 1회 후 인식 | 표시되면 install.sh 의 5.3.5 step 에 audit 자동 호출 추가 |
| V6 | VM-A | `_step8_wh_setup_skill_meta` update path 검증 — 2번째 install.sh 호출 (update mode) | exit 0 + skill dispatch + stdout < 10 KB (CR1-LOW-4 명시) |
| V7 | VM-B | Hermes 미설치 detect (CR2-CRIT-1) | (1) `_step6_agent_skill` warn. (2) `SKIP_SYSTEMD_RENDER=1` 세팅. (3) `_step8_systemd_render` + `_step8_5_systemd_enable_only` 둘 다 skip. (4) `systemctl --user list-unit-files | grep wikihub` empty. (5) install.sh exit 0 |
| V8 | VM-A | Hermes exit code contract (CR2-HIGH-4 / M-9) | LLM API 의도적 fail (invalid model spec) 호출 → exit code 측정. systemd `SuccessExitStatus` 또는 yaml.agent.retryable_exit_codes 결정 input |
| V9 | VM-A | rollback compatibility (CR2-HIGH-7) | F5 install 후 update_mode rollback 시뮬레이션 — `wikihub.yaml.wikihub-bak.<ts>` 수동 복원 후 render 성공 |
| V10 | VM-A | flock contention (CR2-CRIT-2) | install.sh 2개 instance 동시 실행 — 1개는 5.3.2 의 5초 retry × 12 안에 lock 획득, 다른 1개는 wait 후 idempotent skip |

### 9.4 Step 4 R≥2 code review

- CR1 spec — ADR 정합 + SKILL.md materialization 정확도 + per-skill substitution + ADR-0033 supersede 처리
- CR2 SRE — flock + backup + Hermes 미설치 gate + update_mode rollback + transcript volume 정량

---

## 10. Out of Scope (v0.1.0 범위 밖)

- codex/gemini/copilot 의 skill 시스템 매핑 (ADR-0012 의 미검증 영역 유지) — v0.2.x
- Hermes skill 의 LLM tool use 비결정성 보강 — ADR-0006 의 가정 유지
- `_system/commands/` 디렉토리 완전 삭제 — 5.2.B 채택으로 v0.2.x 에서도 제거 동기 없음 (commands/ 정본 유지)
- wrapper script dispatcher (γ) 부분 도입 — CR2-HIGH-4 의 exit code contract 미달 또는 codex/gemini 매핑 시점에 v0.2.x `hermes_wrapper` feature
- skill signing / publishing to registry (`hermes skills publish`) — v0.2.x
- ADR-0024 의 `notify_via_hermes()` stub 채움 (Telegram 통지) — v0.2.x 별도 feature
- per-skill enable/disable 정책 (Hermes side `skills config disable` 정합) — v0.2.x
- skill staleness alert (`last_ingest.json` + ops-alert 확장) — v0.2.x
- Hermes binary version 검증 (hermes_min_version) — Hermes versioning stability 확보 후 v0.2.x

---

## 변경 이력

- **v1** (2026-05-18): 초안. Hermes docs 실측 결과 반영. 옵션 (α) 채택 — skill 등록 + external_dirs + chat -s -q.

- **v2** (2026-05-18): R2 multi-model design review (CR1 spec / CR2 SRE) 반영.
  - **CRIT 5건 해결**:
    1. CR1-CRIT-1 — ADR-0011 supersede 비대칭화 (보수적 `wh-` lock, 신규 ADR-0033 — 5.4.1)
    2. CR1-CRIT-2 — 5.2.B 채택 (commands/ 정본 유지, SKILL.md install-time materialized — 5.1·5.2)
    3. CR1-CRIT-3 — 함수명 정합 (`_step8_wh_setup_skill_meta` — 5.6)
    4. CR2-CRIT-1 — Hermes 미설치 시 systemd render/enable skip gate (5.3.1)
    5. CR2-CRIT-2 — flock + backup + atomic + 동의 모델 통일 (5.3.2·5.3.4)
  - **핵심 HIGH 해결**:
    - CR1-HIGH-1 — ADR-0012 §Decision 갱신 (placeholder semantics — 5.4.2 + 7.1)
    - CR1-HIGH-2 — `_migrate_agent_schema()` 신규 (5.4.3)
    - CR1-HIGH-3 — systemd template slash + per-skill key (5.5.3)
    - CR1-HIGH-4 — V3 PASS 기준 `wiki/sources/<vault>/log.md` 로 정합 (9.3)
    - CR1-HIGH-5 / CR2-HIGH-3 — `--quiet` flag default + V3 정량 기준 (5.4.4·9.3)
    - CR1-HIGH-6 / CR2-CRIT-2 — ADR-0023 safety guard 확장 (5.3·7.1)
    - CR2-HIGH-1 — external_dirs merge 의미론 + realpath + marker (5.3.3)
    - CR2-HIGH-2 — `WIKIHUB_NONINTERACTIVE=1` 단일 toggle (5.3.4)
    - CR2-HIGH-6 — placeholder fail-fast + `systemd-analyze verify` (5.5.1·5.5.4)
    - CR2-HIGH-7 — rollback compatibility Note (5.5.5)
    - CR1-MED-5 / CR2-HIGH-8 — §7.4 sparse-checkout 분석 오류 정정
  - **재평가 (CR2 관찰-2)**: (α) 유지 채택 — vault-fetch.py 이미 agent subprocess (ADR-0006). (γ) hybrid 는 v0.2.x `hermes_wrapper` 로 push (4.5)
  - **잔존 미결**: M-1 (frontmatter schema), M-2' (dispatch 결정성 임계치), M-5 (audit 필요성), M-9 (exit code contract) — 4건 모두 Step 3 VM 실측 의존 (V1~V10 matrix — 9.3)
  - **신규 ADR**: ADR-0032 (registration policy), ADR-0033 (`wh-` lock, supersedes ADR-0011)

- **v3** (2026-05-18): R3 closure review (CR3-1 spec / CR3-2 SRE) narrow patch.
  - **CR3-1 신규 CRIT 2건 fix**:
    1. CR3-1-CRIT-N1 — §5.6 v1 stale block (line 510-516) 제거 (헤더 중복 해소)
    2. CR3-1-CRIT-N2 — `_step8_5_systemd_enable_only` 함수 실재 미존재 정합 — install.sh main loop 구조 (`_step8_systemd_render` → `_step8_wh_setup_skill_meta` 직접 순서) 명시. SKIP_SYSTEMD_RENDER 가 `_step8_systemd_render` 자체 skip → enable 도 자동 skip
  - **CR3-1 신규 HIGH 3건 fix**:
    - HIGH-N1 — `_migrate_agent_schema` idempotency 보장 (5.4.6 — marker comment + 3-branch 분기)
    - HIGH-N2 — ADR-0011 supersede 후 cross-reference 갱신 (ADR-0033 본문 마커, docs/adr/README.md 인덱스, wiki-schema.md L:340·L:347) DoD 추가
    - HIGH-N3 — `timeout {agent.timeout_sec}` 의 yaml read 메커니즘 명시 (5.4.7 — python3 yaml.safe_load 패턴)
  - **CR3-2 4 DoD 항목 추가** (Step 3 backport 가능):
    1. V8 결과 기반 release-time decision matrix
    2. `render_systemd_units.py` 의 `timeout_start_sec` placeholder (yaml.agent.timeout_sec sync)
    3. `systemd-analyze --user verify` 실패 처리 절차
    4. stale `_generated/wh-*` cleanup step (orphan 정리)
  - **R3 잔존 (Step 3 backport)**: CR3-1-MED 4건 + CR3-1-LOW 2건 + CR3-2 HIGH 2 PARTIAL (M-9 release-time policy + timeout_start_sec sync 는 DoD 로 lock) + CR3-2 MED 4건 + LOW 3건
  - **v3 narrow patch 분량**: §5.6 stale block 제거 + §5.4.6/7 신규 + §9.2 ADR list 3건 추가 + §9.2.1 신설 (4 DoD 항목)
