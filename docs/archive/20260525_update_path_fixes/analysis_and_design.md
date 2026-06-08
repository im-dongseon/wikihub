approved: 2026-05-25 (D1~D4 + D3 재결정 (B 채택) + Step 5 전까지 자동 진행 위임)

# Analysis & Design — update_path_fixes (v2)

작성일: 2026-05-25 → v2 (2026-05-26 D3 재결정)
연계 plan: `plan.md`

> **D 결정 final**: D1=v0.1.8 통합 / D2=단일 feature / **D3=(B) graphify hermes 스킬 폐기 + systemd service 격상** / D4=yaml.example 자동 sync
>
> v1 의 D3=(a) multi-skill load 가 hermes 의 실제 동작 (system prompt preload, Reviewer 2 의 hermes source 검증) 과 mismatch 발견 → (B) 채택. wh-graphify hermes 스킬은 Layer 1 LLM wrapper (deterministic bash 작업) 라 over-engineering — 폐기.

---

## 1. 분석

### 1.1 R1 결함 재정의 (Reviewer 2 의 hermes source 검증 흡수)

**hermes 실제 동작** (`/Users/ds.im/.hermes/hermes-agent/agent/skill_commands.py:475` + `cli.py:14869-14881`):

```python
# --skills wh-lint,wh-graphify 의 의미
skills_prompt, ... = build_preloaded_skills_prompt(parsed_skills, ...)
cli.system_prompt = "\n\n".join((cli.system_prompt, skills_prompt)).strip()
```

→ multi-skill flag = **두 SKILL.md 본문을 system prompt 에 prepend** (single LLM session). **자동 sub-skill spawn 메커니즘 부재**. delegation tool 은 LLM 의 명시 `tool_call` 시에만 작동.

→ **`<agent_invocation> "/wh-graphify"` text 패턴 = LLM 의 자유 응답** — hermes 가 detect 후 자동 spawn 하지 않음. wh-lint LLM 의 "Step 9 ▶ 실행 중 (proc_xxx)" = hallucination.

### 1.2 LLM 호출의 두 layer 분리 인식

```
Layer 1 (over-engineering, 폐기 대상):
  wh-graphify hermes 스킬 LLM (deepseek-v4-flash)
  - graphify.md spec 의 step-by-step execution wrapper
  - deterministic bash 작업 (which/yq/graphify CLI)
  - LLM 가치 0

Layer 2 (본질, 유지):
  graphify CLI 내부 LLM (ollama_cloud gemma4:31b-cloud)
  - wiki/ semantic extraction
  - NetworkX nodes/edges 생성
  - graph.json 작성
```

(B) 안 = **Layer 1 폐기 + Layer 2 유지** + trigger 책임 = lint cycle (변경 감지 시만, cost gate 보존).

### 1.3 R2 결함 (v1 동일, 변경 없음)

`_migrate_agent_schema` 가 v0.1.0 → v0.1.8 큰 jump 시 yaml 신설 field 자동 추가 안 됨. legacy_migration_cleanup (`fd7f0fe`) 의 "운영자 base v0.1.4+ 가정" 위반 surface (multipass test).

### 1.4 영향받는 파일 (v2 — (B) 채택 정정)

| 파일 | 변경 | 라인 |
|---|---|---|
| `_system/commands/graphify.md` | **spec 격하** — hermes skill 폐기 명시 + scripts/wikihub_graphify.sh 로 reference. ADR-0036/0038 cross-link | +20 / -180 |
| `_system/skills/wh-graphify.frontmatter.yaml` | **삭제** (hermes skill 등록 폐기) | -20 |
| `_system/systemd/wikihub-graphify.service.template` | **신설** — oneshot, lint Step 9 가 systemctl trigger | +25 |
| `scripts/wikihub_graphify.sh` | **신설** — graphify.md Step 2 backend dispatch 정본 (ADR-0036 §D6 single-source) | +60 |
| `_system/commands/lint.md` Step 9 | spec 정정 — `<agent_invocation>` → `systemctl --user start wikihub-graphify.service` (변경 감지 분기 명시) | +15 / -10 |
| `install.sh` `_WIKIHUB_SKILLS` (render_systemd_units.py:141) | `wh-graphify` 제거 (5→4 skills: ingest/lint/query/setup) | -1 |
| `install.sh` `_step6_agent_skill` (skill materialize) | wh-graphify SKILL.md 정리 — Step 6 가 4 skill 만 materialize | +5 / -5 |
| `install.sh` systemd 3 위치 (stop / try-restart) | `wikihub-graphify.service` 추가 (timer 없음 — start sequence 미진입) | +3 |
| `install.sh` `_migrate_agent_schema` | hardcode Group B/C → yaml.example read sync (R2 fix) + Group A_yolo_missing 복원 | +35 / -40 |
| `wikihub.yaml.example` | (R2 fix 자체는 yaml schema 변경 없음 — sync 메커니즘만 변경) | 0 |
| `docs/adr/0036-graphify-cli-integration.md` §"후속 영향" | graphify hermes skill 폐기 → systemd service 격상 1줄 (B 채택) | +1 |
| `docs/adr/0038-graphify-env-namespace-isolation.md` §"후속 영향" | wh-graphify skill 폐기 후 env namespace 정합 명시 | +1 |
| `docs/adr/0031-yaml-template-materialization.md` §"후속 영향" | yaml.example sync 일반화 (R2 fix) 1줄 | +1 |
| `docs/adr/0032-hermes-skill-registration-policy.md` §"후속 영향" | _WIKIHUB_SKILLS 4 skills 정합 (wh-graphify 폐기) | +1 |
| `README.md` | §"동작" 의 5 skill → 4 skill 정정 + graphify systemd service 1행 | +2 / -1 |
| `_system/wiki-schema.md` | directory tree — wh-graphify SKILL.md 제외 + wikihub-graphify.service.template 포함 | +1 / -1 |
| `features/backlog.md` | (R1+R2 의 fallback design 또는 후속 항목, 추가 시) | +0~5 |

**총 +170 / -257 (net -87 — 주로 graphify.md spec 격하)**

### 1.5 ADR 영향

| ADR | 영향 | 갱신 |
|---|---|---|
| ADR-0036 (graphify CLI integration) | §"후속 영향" 1줄 — graphify hermes skill 폐기 → systemd service 격상. ADR §D6 single-source 정신 정합 유지 (정본만 systemd service 로 이동) |
| ADR-0038 (graphify env namespace isolation) | §"후속 영향" 1줄 — wh-graphify skill 폐기 후 env namespace `WIKIHUB_GRAPHIFY_<PROFILE>_*` 가 wikihub_graphify.sh 의 정본 |
| ADR-0031 (yaml template materialization) | §"후속 영향" 1줄 — yaml.example sync 일반화 (hardcoded dict → yaml.example read) |
| ADR-0032 (Hermes skill registration policy) | §"후속 영향" 1줄 — `_WIKIHUB_SKILLS` 4 skills 정합 (graphify 제외) |
| ADR-0033 (skill prefix wh-) | 영향 없음 (wh- prefix lock 유지) |
| ADR-0008 (lint permission model) | 영향 없음 (Step 9 spec 정정만, --apply 폐기 정합 그대로) |
| ADR-0039 (entity/concept alias frontmatter) | 영향 없음 |

신설 ADR 미생성 — 본 fix 가 메소드론/architectural 결정이 아닌 운영 정정. 단 wh-graphify hermes skill 폐기는 architectural 결정 가치 — `legacy_migration_cleanup` 의 정신 정합 (over-engineering 제거). ADR-NNNN 신설 가능하나 ADR-0036 §"후속 영향" 1줄로 충분 판단. Step 3 진입 시 재확인.

---

## 2. 설계

### 2.1 graphify systemd service 신설

#### 2.1.1 `_system/systemd/wikihub-graphify.service.template`

```ini
[Unit]
Description=WikiHub graphify — knowledge graph build (lint Step 9 chain)
After=network-online.target
Wants=network-online.target
# bootstrap fail (exit 2) 시만 ops-alert 발화 — runtime fail (exit 75/124) 은 SuccessExitStatus 정합
OnFailure=ops-alert.service

[Service]
Type=oneshot
WorkingDirectory={wikihub_home}
ExecStartPre=/bin/mkdir -p {wikihub_home}
Environment=PATH={venv_path}/bin:/usr/local/bin:/usr/bin:/bin
Environment=WIKIHUB_HOME={wikihub_home}
Environment=WIKIHUB_YAML={wikihub_home}/wikihub.yaml
Environment=WIKIHUB_SRC={wikihub_src}
EnvironmentFile=-%h/.config/wikihub/env
ExecStart={wikihub_src}/scripts/wikihub_graphify.sh
SuccessExitStatus=0 75
# graphify CLI 의 wrapper timeout — yaml `operations.graphify_timeout_sec` (default 900s = 15분)
# 단 systemd 차원의 TimeoutStartSec 는 그보다 약간 길게 (graphify CLI wrapper + 후처리 margin)
TimeoutStartSec=1200
SyslogIdentifier=wikihub-graphify

# Restart= 미설정 — oneshot, lint Step 9 가 trigger 책임. 변경 없으면 fire 안 함.
# [Install] 미작성 — timer 없음 (사용자 명시 — 변경 시만 fire, cost gate)
```

설계 결정:
- **timer 없음** — lint Step 9 의 변경 감지 분기가 유일 trigger. cost gate 보존 (사용자 핵심 의도).
- **Type=oneshot** — graphify CLI 완료 후 종료. lint.service 와 같은 패턴.
- **SuccessExitStatus=0 75** — runtime retry (timeout, transient) 는 success 분류. lint chain 정합.
- **OnFailure=ops-alert.service** — bootstrap fail (exit 2) 만 surface (wikihub_monitor / lint-apply 패턴 정합)
- **TimeoutStartSec=1200** — graphify_timeout_sec (900s wrapper) + 300s margin (LLM cloud latency + 후처리)

#### 2.1.2 `scripts/wikihub_graphify.sh`

`graphify.md` Step 2 backend dispatch 의 정본화. ADR-0036 §D6 single-source 정합 유지 (정본만 hermes skill → systemd service shell script 로 이동).

```bash
#!/usr/bin/env bash
# wikihub_graphify.sh — graphify CLI 호출 정본 (ADR-0036 §D6 single-source)
#
# 호출자:
# 1. wikihub-graphify.service ExecStart (lint Step 9 가 systemctl trigger)
# 2. 메인테이너 manual: systemctl --user start wikihub-graphify.service
#    (또는 직접: WIKIHUB_HOME=... WIKIHUB_YAML=... ./scripts/wikihub_graphify.sh)
#
# v0.1.8 update_path_fixes — graphify hermes skill 폐기 후 systemd service 격상.
set -euo pipefail

: "${WIKIHUB_HOME:?WIKIHUB_HOME unset}"
: "${WIKIHUB_YAML:?WIKIHUB_YAML unset}"

# Step 1. graphify CLI 존재 확인
command -v graphify >/dev/null || { echo "ERROR: graphify CLI 미설치 — install.sh 재실행" >&2; exit 2; }

# Step 2. yaml read + profile resolve (ADR-0038 namespace 격리)
profile="$(yq '.operations.graphify_profile // ""' "$WIKIHUB_YAML")"
backend="$(yq '.operations.graphify_backend // "ollama"' "$WIKIHUB_YAML")"
timeout_sec="$(yq '.operations.graphify_timeout_sec // 900' "$WIKIHUB_YAML")"

if [[ ! "$profile" =~ ^[a-z][a-z0-9_]*$ ]]; then
    echo "ERROR: graphify_profile '$profile' invalid — must match ^[a-z][a-z0-9_]*$" >&2
    exit 2
fi

profile_upper="$(echo "$profile" | tr '[:lower:]' '[:upper:]')"
endpoint_var="WIKIHUB_GRAPHIFY_${profile_upper}_ENDPOINT"
api_key_var="WIKIHUB_GRAPHIFY_${profile_upper}_API_KEY"
model_var="WIKIHUB_GRAPHIFY_${profile_upper}_MODEL"
endpoint="${!endpoint_var:-}"
api_key="${!api_key_var:-}"
model="${!model_var:-}"

[[ -z "$model" ]] && { echo "ERROR: $model_var unset — env profile bundle 확인" >&2; exit 2; }

# ollama endpoint pattern → env name 분기 (graphify.md Step 2 정합)
ollama_env_name=""
if [[ "$backend" == "ollama" ]]; then
    case "$endpoint" in
        http://localhost:*|http://127.0.0.1:*|http://\[::1\]:*) ollama_env_name="OLLAMA_HOST" ;;
        *)                                                       ollama_env_name="OLLAMA_BASE_URL" ;;
    esac
fi

# concurrency 휴리스틱 (graphify.md Step 2 정합)
case "$model" in *cloud*) concurrency=4 ;; esac
if [[ -z "${concurrency:-}" ]]; then
    case "$endpoint" in
        http://localhost:*|http://127.0.0.1:*|http://\[::1\]:*) concurrency=1 ;;
        *)                                                       concurrency=4 ;;
    esac
fi

# --rebuild 분기 (graphify.md Step 2 정합)
if [[ "${1:-}" == "--rebuild" ]]; then
    rm -f "$WIKIHUB_HOME/graphify-out/graph.json"
fi

# Step 3. backend dispatch (graphify.md Step 2 정합 — 6 case)
case "$backend" in
    ollama)
        timeout "$timeout_sec" env \
            "$ollama_env_name=$endpoint" \
            OLLAMA_API_KEY="${api_key:-local-daemon}" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend ollama --model "$model" \
                --max-concurrency "$concurrency" --out "$WIKIHUB_HOME"
        ;;
    openai)
        timeout "$timeout_sec" env OPENAI_API_KEY="$api_key" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend openai --model "$model" \
                --max-concurrency 4 --out "$WIKIHUB_HOME"
        ;;
    claude)
        timeout "$timeout_sec" env ANTHROPIC_API_KEY="$api_key" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend claude --model "$model" \
                --max-concurrency 4 --out "$WIKIHUB_HOME"
        ;;
    gemini)
        timeout "$timeout_sec" env GEMINI_API_KEY="$api_key" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend gemini --model "$model" \
                --max-concurrency 4 --out "$WIKIHUB_HOME"
        ;;
    deepseek)
        timeout "$timeout_sec" env DEEPSEEK_API_KEY="$api_key" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend deepseek --model "$model" \
                --max-concurrency 4 --out "$WIKIHUB_HOME"
        ;;
    kimi)
        timeout "$timeout_sec" env MOONSHOT_API_KEY="$api_key" \
            graphify extract "$WIKIHUB_HOME/wiki" \
                --backend kimi --model "$model" \
                --max-concurrency 4 --out "$WIKIHUB_HOME"
        ;;
    *)
        echo "ERROR: unknown graphify_backend '$backend'" >&2
        exit 2
        ;;
esac

# Step 4. 결과 검증 + partial failure 가드 (graphify.md Step 3 정합)
[[ -f "$WIKIHUB_HOME/graphify-out/graph.json" ]] || { echo "graph.json 미생성" >&2; exit 1; }

# JSON validity check
keys="$(jq -r 'keys | join(",")' "$WIKIHUB_HOME/graphify-out/graph.json" 2>/dev/null)" || {
    echo "ERROR: graph.json invalid JSON (timeout 도중 partial write 의심) — 삭제 후 exit" >&2
    rm -f "$WIKIHUB_HOME/graphify-out/graph.json"
    exit 1
}

# partial failure 가드 (ADR-0036 §재검토 트리거 — Pass 3 silent partial failure)
N="$(jq -r '.nodes | length' "$WIKIHUB_HOME/graphify-out/graph.json")"
M="$(find "$WIKIHUB_HOME/wiki" -name '*.md' -not -path '*/_lint/*' -not -path '*/_state/*' | wc -l)"
threshold="$(yq '.operations.graphify_partial_failure_threshold // 0.5' "$WIKIHUB_YAML")"

if [[ "$M" -gt 0 ]]; then
    ratio="$(awk "BEGIN {print $N/$M}")"
    if awk "BEGIN {exit !($ratio < $threshold)}"; then
        echo "WARNING: graphify partial failure 의심: N=$N, M=$M, ratio=$ratio" >&2
        # ops-alert trigger (별도 — 본 fix scope 외, BL 등록)
    fi
fi

echo "graph rebuilt: $N nodes, $M docs" >&2
exit 0
```

### 2.2 lint.md Step 9 spec 정정

```markdown
### Step 9. graphify chain trigger (v0.1.8 update_path_fixes — D3 (B) 채택)

**조건 분기** (운영자 cost gate 정합):

```bash
graphify_enabled="$(yq '.operations.graphify_enabled // true' "$WIKIHUB_HOME/wikihub.yaml")"
```

1. **`graphify_enabled == false`** → skip + `_lint/report.md` 에 1줄 `graphify chain skipped (yaml toggle)`
2. **lint cycle 변경 없음** (Step 3 자동 stub 생성 0건 + Step 5 index.md 변경 없음 + Step 7 archive 0건) → skip + `_lint/report.md` 에 1줄 `graph rebuild skipped (no changes)` ← **cost gate (사용자 핵심 의도)**
3. **lint cycle 변경 있음 + graphify_enabled=true** → 다음 명령 호출 (fire-and-forget):
   ```bash
   systemctl --user start wikihub-graphify.service
   ```
   + `_lint/report.md` 에 1줄 `graphify chain triggered — see journalctl --user -u wikihub-graphify.service`

**책임 분리** (ADR-0036 §D6 single-source 정합):
- **lint Step 9 책임 = trigger 만** (변경 감지 + systemctl 호출)
- **graphify CLI 호출 책임 = `wikihub-graphify.service` (정본 `scripts/wikihub_graphify.sh`)**

**fire-and-forget**: `systemctl start` 가 비동기. lint.service 즉시 종료. graphify 결과는 `wikihub-graphify.service` 의 별도 journal + `graphify-out/graph.json` 으로 surface.

**v0.1.7 era spec 변경**: 기존 `<agent_invocation> "/wh-graphify"` 표현 폐기 — hermes 의 자동 sub-skill spawn 메커니즘 부재 (Reviewer 2 hermes source 검증). graphify hermes skill 자체도 폐기 (Layer 1 LLM wrapper 폐기 — wikihub_monitor 의 D1 정정 정신 정합).
```

### 2.3 `_system/commands/graphify.md` spec 격하

현행 graphify.md = hermes skill 본문 (~240 줄). v0.1.8 (B) 채택 후 = bash script reference + ADR cross-link 만 (~50 줄):

```markdown
# graphify

> **v0.1.8 update_path_fixes 정정** (2026-05-25): graphify 는 hermes skill 이 아닌 systemd service 로 격상.
>
> - **정본 코드**: `scripts/wikihub_graphify.sh` (ADR-0036 §D6 single-source)
> - **systemd unit**: `wikihub-graphify.service` (timer 없음 — lint Step 9 가 trigger)
> - **메인테이너 manual 호출**: `systemctl --user start wikihub-graphify.service`
> - **자동 trigger**: `wh-lint` Step 9 (변경 감지 시만, cost gate)
>
> hermes skill `wh-graphify` 폐기 — Layer 1 LLM wrapper 가 deterministic bash 작업을 over-engineering 했음 (wikihub_monitor 의 D1 정정 정신 정합). semantic extraction 의 LLM 호출은 graphify CLI 내부 (Layer 2, ollama_cloud) 유지.

## 호출 흐름

(생략 — wikihub_graphify.sh + lint.md Step 9 + systemctl start 의 운영 흐름 1 단락)

## backend / profile / timeout

ADR-0038 의 `WIKIHUB_GRAPHIFY_<PROFILE>_*` env namespace 정합. yaml `operations.graphify_*` 정합. 자세한 backend 별 cookbook → `docs/graphify-backend-test-reference.md` §6.

## 관련 ADR

- ADR-0036 (graphify CLI integration) §"후속 영향" — systemd service 격상
- ADR-0038 (graphify env namespace isolation) — env profile bundle 정본
- ADR-0032 (Hermes skill registration policy) §"후속 영향" — `_WIKIHUB_SKILLS` 4 skills (graphify 제외)
```

### 2.4 install.sh 변경

#### 2.4.1 `_WIKIHUB_SKILLS` tuple 정정

`scripts/_helpers/render_systemd_units.py:141`:
```python
# Before
_WIKIHUB_SKILLS = ("wh-ingest", "wh-lint", "wh-query", "wh-graphify", "wh-setup")
# After (B 채택, v0.1.8)
_WIKIHUB_SKILLS = ("wh-ingest", "wh-lint", "wh-query", "wh-setup")
```

#### 2.4.2 `_migrate_agent_schema` yaml.example sync (R2 fix)

현행 Group B 의 hardcoded `_op_defaults` dict → yaml.example read 기반:

```python
# install.sh _migrate_agent_schema 의 PYEOF Python heredoc 안:
import os
# R2 fix (v0.1.8): WIKIHUB_SRC env 부재 시 fail-fast (Reviewer 2 M1 흡수)
wikihub_src = os.environ.get("WIKIHUB_SRC", "")
if not wikihub_src:
    print("ERROR: WIKIHUB_SRC env unset — _migrate_agent_schema cannot read wikihub.yaml.example", file=sys.stderr)
    sys.exit(2)
example_path = wikihub_src + "/wikihub.yaml.example"

example_yaml = YAML()
with open(example_path) as f:
    example = example_yaml.load(f)

# 깊이 제한: operations + agent top-level dict 만 (Reviewer 2 M2 흡수)
# vaults[] array 는 별도 hardcoded loop 유지 (배열 semantics 모호 — 운영자 의존)
for top in ("operations", "agent"):
    example_top = example.get(top, {}) or {}
    target_top = data.setdefault(top, {})
    if isinstance(example_top, dict) and isinstance(target_top, dict):
        for k, default_v in example_top.items():
            if k not in target_top:
                target_top[k] = default_v
                flags.append(f"B_sync:{top}.{k}")
```

**set semantics 한계** (Reviewer 2 H1 흡수): `if k not in target_top` 는 운영자의 "자연 부재" 와 "명시 삭제" 구분 불가. 운영자 명시 삭제 의도가 본 fix 로 자동 복원되어 의도 손상 가능. 본 fix 의 scope 는 "자연 부재 (큰 jump)" 만 cover — 명시 삭제는 별도 backlog.

#### 2.4.3 Group A `A_yolo_missing` 복원 (legacy_migration_cleanup 부분 inversion)

```python
# install.sh _migrate_agent_schema Group A 부분 (legacy_migration_cleanup 에서 삭제됨, B 채택과 무관하게 복원):
agent_args = agent.get("oneshot_args") or []
if isinstance(agent_args, list) and "--query" in agent_args and "--yolo" not in agent_args:
    # --yolo 누락 시 --query 앞에 insert (in-place modification)
    idx = agent_args.index("--query")
    agent_args.insert(idx, "--yolo")
    flags.append("A_yolo_missing")
```

**legacy_migration_cleanup decision 부분 inversion** (Reviewer 2 H2 흡수):
- 직전 feature `legacy_migration_cleanup` 의 Group A 전체 삭제 결정 = "운영자 base v0.1.4+ 가정"
- multipass test 의 v0.1.0 yaml = 그 가정 위반 실 surface
- `A_yolo_missing` 만 복원 — `A_skill_prefix` (wh:→wh-) 는 미복원 (v0.1.4+ 부터 ADR-0033 lock 정합, value mutation 회피)
- `A_oneshot_legacy` (placeholder 부재) 도 미복원 — render_systemd_units.py:154-163 의 fail-fast 가 edge case cover

### 2.5 ADR cross-link 갱신

| ADR | §"후속 영향" 추가 1줄 |
|---|---|
| ADR-0036 | "2026-05-25: `update_path_fixes` (v0.1.8) — graphify hermes skill 폐기 → `wikihub-graphify.service` systemd 격상. `scripts/wikihub_graphify.sh` 가 정본 (§D6 single-source 정합 유지). lint Step 9 가 systemctl trigger, 변경 감지 시만 fire (cost gate)." |
| ADR-0038 | "2026-05-25: `update_path_fixes` (v0.1.8) — wh-graphify hermes skill 폐기 후 env namespace `WIKIHUB_GRAPHIFY_<PROFILE>_*` 정합 유지 — `scripts/wikihub_graphify.sh` 가 systemd EnvironmentFile 통해 동일 env 변수 read." |
| ADR-0031 | "2026-05-25: `update_path_fixes` (v0.1.8) — `_migrate_agent_schema` Group B 의 hardcoded dict → `wikihub.yaml.example` read 기반 자동 sync 일반화 (큰 jump 운영자 경로 안정성). 신규 field 추가 시 yaml.example 갱신만으로 자동 보강 — install.sh 변경 0." |
| ADR-0032 | "2026-05-25: `update_path_fixes` (v0.1.8) — `_WIKIHUB_SKILLS` 4 skills (wh-graphify 폐기, ingest/lint/query/setup 유지). graphify 호출 책임이 systemd service 로 격상 — hermes skill registration scope 외." |

---

## 3. 미결 사항 (잔여)

| ID | 미결 | 시점 |
|---|---|---|
| Q1 | 메인테이너 manual graphify 호출 UX — `systemctl --user start wikihub-graphify.service` 가 너무 길면 alias 신설 가치 (예: `~/.local/bin/wikihub-graphify` symlink) | backlog 등록 후 운영 감지 |
| Q2 | wikihub_monitor 보고서에 `wikihub-graphify.service` 결과 surface — `BL-N7` 와 통합 | 별도 feature |
| Q3 | `wikihub_graphify.sh` 의 partial failure ratio 가 ops-alert trigger 하는 path (현 spec 은 stderr warn 만) | BL 등록 |

---

## 4. Definition of Done

- [ ] `_system/skills/wh-graphify.frontmatter.yaml` **삭제**
- [ ] `_system/commands/graphify.md` spec **격하** (skill 폐기 + bash script reference)
- [ ] `_system/systemd/wikihub-graphify.service.template` **신설**
- [ ] `scripts/wikihub_graphify.sh` **신설** + chmod +x
- [ ] `_system/commands/lint.md` Step 9 spec 정정 (`<agent_invocation>` → `systemctl --user start`)
- [ ] `scripts/_helpers/render_systemd_units.py:141` `_WIKIHUB_SKILLS` 정정 (wh-graphify 제거)
- [ ] `install.sh` `_step6_agent_skill` 의 skill materialize 정합 (4 skills 만)
- [ ] `install.sh` systemd 3 위치 (stop / try-restart) — wikihub-graphify.service 추가 (timer 없음 — start 흐름 없음)
- [ ] `install.sh` `_migrate_agent_schema` — yaml.example sync 일반화 (R2 fix) + Group A_yolo_missing 복원 + WIKIHUB_SRC env guard
- [ ] `docs/adr/0036-*` / `0038-*` / `0031-*` / `0032-*` 의 §"후속 영향" 각 1줄
- [ ] `README.md` §"동작" 의 5 skill → 4 skill + graphify systemd service 1행
- [ ] `_system/wiki-schema.md` directory tree 정합 (wh-graphify skill 제외, wikihub-graphify.service.template 포함)
- [ ] multipass 실측: v0.1.0 yaml → `_migrate_agent_schema` 후 `--yolo` + 신설 field 모두 자동 추가
- [ ] multipass 실측: lint cycle 변경 시 `systemctl start wikihub-graphify.service` trigger → `graphify-out/graph.json` 생성 + journal surface
- [ ] multipass 실측: lint cycle 변경 없을 때 graphify trigger 안 함 (cost gate)
- [ ] Step 4 멀티 리뷰어 통과
- [ ] **Step 5 사용자 승인** + squash → v0.1.8 → canary force-update

---

## 5. 버전 이력

### v1 — 2026-05-25 (초안, D1~D4 결정 흡수)

D1=v0.1.8 통합 / D2=단일 / D3=(a) multi-skill load / D4=yaml.example sync.

### v2 — 2026-05-26 (D3 재결정 + Reviewer 1/2 흡수)

**D3 재결정 ((a) → (B))**:
- Reviewer 2 의 hermes source 직접 검증 결과 — `--skills X,Y` 는 system prompt preload (single LLM session) 라 D3=a 의 가정 (sub-skill spawn) mismatch.
- 사용자 의문 ("graphify 가 hermes 스킬?") trigger — wh-graphify hermes skill = Layer 1 LLM wrapper (deterministic bash 작업 over-engineering). `wikihub_monitor` 의 D1 정정 정신 정합.
- (B) 채택 — graphify hermes 스킬 폐기 + `wikihub-graphify.service` systemd 격상 + `scripts/wikihub_graphify.sh` 정본화. trigger = lint Step 9 (변경 감지 시만, cost gate 보존).

**Reviewer 1 (spec 정합 + ADR) 흡수**:
- C1 fallback skeleton — (B) 채택으로 자연 해소 (skeleton 자체가 본 design)
- C2 ADR-0033 mismatch — (B) 채택으로 lint.service ExecStart 변경 없음 → mismatch 해소
- H1 ADR-0031 cross-link → §2.5 명시
- H2 yaml.example sync 깊이 명시 → §2.4.2 명시 (operations + agent top-level dict 만, vaults[] 별도)
- H3 A_yolo_missing 복원 narrowing rationale → §2.4.3 명시 (legacy_migration_cleanup 부분 inversion)
- H4 AgentConfig.skill_chains — (B) 채택으로 skill_chains 폐기 → AgentConfig 변경 없음 (M3 부속)

**Reviewer 2 (hermes 동작 + 운영 안전성) 흡수**:
- C1 hermes 동작 mismatch → (B) 채택으로 정합
- H1 set semantics 한계 → §2.4.2 명시
- H2 legacy_migration_cleanup decision 부분 inversion → §2.4.3 명시
- M1 WIKIHUB_SRC env guard → §2.4.2 fail-fast 추가
- M2 vaults[] array 별도 처리 → §2.4.2 명시
- M3 design-stage hermes source 검증 → 본 v2 에 인용
- M4 N/M check inline 의미 → (B) 채택으로 `wikihub_graphify.sh` 책임 (§2.1.2)

**scope 변화 (v1 → v2)**:
- v1: net +20 line (multi-skill load + yaml.example sync)
- v2: net -87 line (graphify hermes skill 폐기 + spec 격하 -180 / -257 vs 신설 +170)

approved: 2026-05-25 → v2 (2026-05-26 D3 재결정). 사용자 위임 "Step 5 전까지 자동 진행". Step 3 진입.

### v3 — 2026-05-26 (Step 4 멀티 code review 흡수)

**Reviewer 1 (DoD + spec 정합)** 흡수:
- **C1** wikihub-graphify.service.template `SuccessExitStatus=0 75` 가 timeout exit 124 미포함 → `0 75 124` 정정 (shell `timeout` builtin 의 124 propagate)
- **H1** wiki-schema.md 의 `/wh-graphify` hermes skill reference 본문 4 위치 (L196/234/301/343) 정정
- **M1** = R2-H2 (graphify_partial_failure_threshold yaml.example 부재) → 통합 fix
- **M2** `--rebuild` flag systemd 경로 전달 불가 → BL-N14 등록
- **M3** _migrate_agent_schema detect/write heredoc 분리 → BL-N15 등록

**Reviewer 2 (운영 안전성)** 흡수:
- **C1** ops-alert silent skip (wikihub_monitor H2 inheritance) → BL-N12 등록 (scope 증가, 별도 처리)
- **C2** install.sh try-restart 의 wikihub-graphify.service — oneshot+RemainAfterExit=no 라 no-op → try-restart 에서 제거 + NOTE 코멘트
- **H1** ruamel.yaml `target_top[k] = default_v` reference assignment → `copy.deepcopy(default_v)` 정정
- **H2** graphify_partial_failure_threshold yaml.example 부재 → 1 줄 추가
- **H3** lint Step 9 변경 감지 LLM 정확도 의존 → lint.md spec 명시 (보수적 default = 변경 없음 시 skip)
- **H4** install.sh start sequence 의 graphify info 부재 → 정합 (timer 없음, start 안 함)

**deferred (backlog)**:
- BL-N12 graphify bootstrap fail alert (R2 C1)
- BL-N13 wikihub_monitor 의 wh-graphify surface
- BL-N14 --rebuild systemd 전달
- BL-N15 _migrate_agent_schema heredoc 통합
- BL-N16 N/M partial failure ops-alert trigger
- BL-N17 _install_graphify auto trigger

**bash -n + py_compile 검증 통과**. Step 5 squash merge 사용자 검토 대기 (사용자 명시 흐름).

### Critical fix 적용 후 net diff

- v2 추정: +170 / -257 (net -87)
- v3 실제: code_review_1 보고에 따르면 +163 / -350 (graphify.md 격하가 design 추정보다 큼) + Critical fix 5건 추가

Step 4 흡수 후 v0.1.8 squash 진행 가능 — 사용자 승인 필수 (D2/D1 정합).
