# Design Review 1 — update_path_fixes (independent reviewer)

작성일: 2026-05-25 (KST)
리뷰어: Claude (독립 세션, 컨텍스트 초기화)
대상: `analysis_and_design.md` v1 (approved 2026-05-25) + `plan.md`
검토 관점: spec 정합 + ADR 정합 + 운영 의미

---

## 종합 평가

본 feature 는 v0.1.8 release 직전 multipass 실 검증으로 surface 한 2 결함의 hotfix.

| ID | 결함 성격 | critical 도 |
|---|---|---|
| **R1** | lint Step 9 의 `<agent_invocation> "/wh-graphify"` 가 silent skip (graphify subprocess 미spawn) | **C — silent broken chain** |
| **R2** | `_migrate_agent_schema` 가 큰 jump (v0.1.0 → v0.1.8) 시 yaml 신설 field 미반영 → 모든 systemd cycle Denied | **H — 빈도 낮으나 영향 큼** |

**D3 (multi-skill load) + D4 (yaml.example sync) 두 결정은 방향 자체는 정합.** 단 R1 fix 의 hermes 동작 가정이 **Step 3 multipass 실측 시점에 검증**되는 구조라 design 단계에서 fallback path (β/γ) 가 surface 안 됨 — Step 2 design review 의 핵심 (실측 fail 의 fallback design 선결정) 누락. R2 fix 의 yaml.example sync 일반화는 ADR-0031 §"yaml template materialization" 와 미묘한 긴장 있음 (install.sh 가 yaml.example 을 schema authority 로 read) — design 본문이 §Decision A 의 `value mutation` vs `schema mutation` 분리 보강 cross-link 권장.

**핵심 진단**:
- R1 fix 의 `agent.skill_chains` schema 신설은 ADR-0032/0033 와 충돌 0 (orthogonal 결정).
- R1 fix 의 hermes multi-skill 동작 가정이 design 의 핵심 unknown — Q1 미결을 Step 3 까지 끌고 가는 design 결정 자체는 정합 (D3=a 의 가장 작은 변경 + ADR 보존 가치 우선). 단 fallback design (β systemctl trigger / γ subagent_skills frontmatter) 본문 1~2 줄 skeleton 권장.
- R2 fix 의 `_migrate_agent_schema` 일반화는 design 자체는 합리적이나 — multipass test 의 yaml 이 **v0.1.0 era** 라는 가정에 대한 실 surface 의미 (운영 실 base 는 v0.1.5+) 가 §1.2 영향 분석에 잘 묘사돼 있음. **본 fix 의 ROI 는 multipass test 자체의 setup 안정화** > 실 운영자 protection (v0.1.5+ 가정 정합).

**release 권고**: v0.1.8 hotfix 통합 (D1=a) 정합. 단 design 의 미결 Q1~Q3 모두 Step 3 까지 끌리는 구조 — Step 3 진입 전 본 review 의 C/H 항목 흡수 후 design v2 작성 권장.

---

## C — Critical (반드시 흡수)

### C1. R1 fix 의 hermes multi-skill 동작 가정이 design 단계에서 미검증 — fallback path 본문 누락

**위치**: `analysis_and_design.md` line 121-136 (§2.1.3 hermes 동작 가정 + 검증 plan)

**인용**:
```
가정: `--skills wh-lint,wh-graphify` 로 hermes 가 두 skill 모두 load 시 wh-lint LLM 의
      `<agent_invocation> "/wh-graphify"` 출력 → hermes orchestrator 가 wh-graphify subprocess spawn.

**Step 3 implementation 시점 multipass 실측 필수**:
```

**문제**:

1. design 의 D3=a 채택 근거는 "가장 작은 변경 + ADR 정합 보존 + lint.md spec 무변경" (plan.md line 33). 그러나 hermes 의 `--skills wh-lint,wh-graphify` multi-load 후 wh-lint LLM 의 `<agent_invocation>` orchestration 동작 = **검증 안 된 hermes internal**.

2. ADR-0032 §sub-2 의 hermes skill dispatch 는 single skill load → `--query "/<name>"` slash command dispatch 가 정본. multi-skill load 후 sub-skill spawn (LLM `<agent_invocation>` → orchestrator dispatch) 은 ADR 도 spec 도 비명시 — hermes 의 implicit behavior 의존.

3. design 의 fallback (line 133-136) 은 `(β) systemctl --user start wikihub-graphify.service` 와 `(γ) SKILL.md subagent_skills frontmatter` 두 옵션을 1줄씩만 surface. **design 본문이 아니라 미결 항목 형태** — Step 3 실측 fail 시 design v2 재작성 부담.

**평가**:

R1 결함의 실 root cause 는 wh-lint LLM 이 `<agent_invocation>` 출력 후 hermes 가 dispatch 안 한 것 (1.1 실측: "wh-lint LLM 이 fake `proc_xxx` ID 출력 (hallucination)"). 이는 **hermes 의 sub-skill spawn semantic 자체가 외부 spec** — wikihub 가 multi-skill load 한다고 자동 해결될 보장 없음. hermes 의 `delegation.orchestrator_enabled` (plan.md line 42 언급) 설정 + `max_spawn_depth=1` 가 dependency.

design review 의 핵심 = "구현 진입 전 결정 정확성 검증". multipass 실측 결과를 step 3 까지 끌고 가면:
- 실측 pass → fix 완료 (Q1 closure).
- 실측 fail → design v2 재작성 (β/γ 중 선택) → Step 2 재진입 → Step 3 재시작. **methodology 의 Step 3 가 retry loop 됨**.

**권고**:

design v2 에서 다음 보강:

(a) **§2.1.3 본문에 fallback design β/γ 의 결정 trigger 명시 + skeleton 보강**:
- β (systemctl trigger): lint.md Step 9 의 `<agent_invocation>` 를 `systemctl --user start wikihub-graphify.service` 로 spec 변경. 신설 systemd unit (`_system/systemd/wikihub-graphify.{service,timer}.template`) 필요. plan.md line 50-53 의 Option (c) 와 동일 — D3=c 회귀.
- γ (subagent_skills frontmatter): wh-lint SKILL.md frontmatter 에 `subagent_skills: [wh-graphify]` 명시. hermes-specific schema — hermes docs 확인 필수 + 부재 시 reject. ADR-0032 §sub-2 β (install-time materialization) 의 frontmatter source (`_system/skills/wh-lint.frontmatter.yaml`) 갱신 책임.

(b) **실측 fail 시 결정 권한 surface**: "실측 fail → β 자동 채택" 또는 "실측 fail → design review 재진입" 의 의사결정 흐름 lock. methodology §3 의 Step 4 "범위 초과 결함 → 새 Feature" 적용 시 D3=c 회귀가 단일 feature scope 인지 분리인지 사용자 결정.

(c) **hermes docs 의 sub-skill spawn 실 검증 reference**: hermes 의 `--skills` flag multi-value 시 LLM `<agent_invocation>` orchestration 동작이 hermes docs 의 어느 섹션 (또는 backlog/실험 trail) 에 명시인지 link. 부재면 design 의 D3=a 자체가 "ADR 정합 보존" 보다 "검증 안 된 가정 의존" 으로 평가 reframe.

(d) **Q1 미결을 Step 2 종료 전 closure 권장** — multipass 1회 실측 (D3=a 호출 + journal 검증) 을 design 단계에 흡수. plan.md 의 9 "사용자 흐름" 의 Step 2~4 자동 흐름과 충돌하나, hermes 동작 자체가 외부 dependency 라 design 결정의 가장 큰 unknown.

---

### C2. lint.service ExecStart 의 D3=a 변경이 ADR-0033 §"agent 호출 예 (정본)" 와 다른 정본 형식 도입 — ADR 갱신 책임 누락

**위치**: `analysis_and_design.md` line 116-119 (결과 lint.service ExecStart)

**인용**:
```
결과 lint.service ExecStart:
```
hermes chat --skills wh-lint,wh-graphify --quiet --yolo --query "/wh-lint"
```
```

**문제**:

ADR-0033 line 51-60 의 "agent 호출 예 (정본)" 은 single skill load 만 정본화:
```
hermes chat --skills wh-ingest --quiet --query "/wh-ingest --vault gdrive"
hermes chat --skills wh-lint --quiet --query "/wh-lint"
...
hermes chat --skills wh-graphify --quiet --query "/wh-graphify"
```

D3=a 가 lint cycle 만 `--skills wh-lint,wh-graphify` 의 multi-value 정본화 → ADR-0033 의 "정본" 명시와 silently mismatch. analysis_and_design.md §2.3 "ADR 신설 여부" (line 201-206) 는 D3 의 ADR 가치를 보류 + "후속 chain 결정 재발 시 ADR 격상" 만 명시 — **현재 결정 자체의 ADR-0033 갱신 책임 미surface**.

**평가**:

ADR-0033 의 "정본" 명시는 single-skill load 의 dispatch 형식 lock. D3=a 가 lint 한 unit 만 multi-value 도입 → ADR-0033 의 "정본" 의 의미 모호 (모든 unit 인지 vs default 인지). ADR-0032 §sub-2 의 hermes skill dispatch + ADR-0012 의 agent invocation abstraction 도 영향 — multi-skill load 가 spec layer 어디 정합인지 design 미surface.

**ADR 신설 vs ADR-0032/0033 §Note 추가** 의 결정:
- **ADR 신설 후보**: D3=a 가 wh-lint → wh-graphify 의 chain 정책 첫 정본화 — 후속 (e.g. wh-ingest → wh-query) 재발 시 ADR-NNNN 의 catalog 확장 가능. plan.md 의 D3=a 의 "최소 변경 + ADR 정합 보존" 정신이 ADR 정합 보존 = ADR 본문 변경 0 의도였다면 ADR 신설로 정합 보존.
- **§Note 추가**: ADR-0033 §"agent 호출 예 (정본)" 또는 ADR-0032 §sub-2 에 chain semantic 의 1줄 + 본 feature link.

**권고**:

design v2 에서:

(a) ADR-0032 §sub-2 또는 ADR-0033 의 "agent 호출 예 (정본)" 에 § Note (2026-05-25, feature update_path_fixes) 신설 — chain 형식 (`--skills <primary>,<sub>,...`) 의 정본화.
(b) §2.3 의 "ADR 신설 보류" 결정 재검토 — D3=a 가 chain 정책의 **첫 사례** 이므로 ADR 신설 가치 높음 (ADR-NNNN-skill-chain-orchestration). 본 feature scope 작음 (yaml field 1개 + render 5줄) 이라 ADR 본문도 짧음.
(c) `wikihub.yaml.example` 의 `agent.skill_chains` 신설 시 comment 안내 — chain 의미 + ADR cross-link.

---

## H — High (강력 권고)

### H1. R2 fix 의 `_migrate_agent_schema` 일반화가 ADR-0031 §"yaml template materialization" 의 정신과 미묘한 긴장 — design 본문 cross-link 부족

**위치**: `analysis_and_design.md` line 138-186 (§2.2 R2 fix)

**인용**:
```
신규 흐름 — `wikihub.yaml.example` parse 후 default 자동 sync:
```python
example_path = os.environ.get("WIKIHUB_SRC", "") + "/wikihub.yaml.example"
with open(example_path) as f:
    example = yaml.load(f)
```
```

**문제**:

ADR-0031 §Decision A (line 54): "**writer: (β) `/wh:setup` 단독** — install.sh 의 yaml 개입 0건". 그러나 v0.1.7 `yaml_schema_drift_migration` feature 가 §Note (line 308-329) 로 schema mutation 만 install.sh 책임 lift:
- value mutation = `/wh:setup` Step 0 (drift fix 4 필드)
- schema mutation = install.sh `_migrate_agent_schema` (field 추가/삭제)

design 의 R2 fix 는 schema mutation 의 **source 가 hardcode dict → yaml.example read** 로 변경 — **두 번째 lift**.

**평가**:

R2 fix 의 design 자체는 정합 (ADR-0031 §Note v0.1.7 의 schema mutation 책임 lift 와 일관). 단 **design 본문이 ADR-0031 §Note v0.1.7 의 schema mutation 책임 lift 와 본 fix 의 source 변경 (hardcode → yaml.example read) 의 관계** 를 cross-link 안 함:

- §2.3 (line 202-205) 가 "ADR-0031 §"yaml template materialization" 의 후속 영향 1 줄 cross-link" 만 명시 — 1줄로 fit 안 함. 본 fix 가 schema authority 의 **소스 변경**:
  - v0.1.7: hardcode dict in install.sh = schema authority (yaml.example 과 sync 책임 메인테이너)
  - v0.1.8 (본 fix): yaml.example = schema authority (install.sh = read-only consumer)

- yaml.example 이 schema authority 되면 install.sh 의 yaml.example **read path** 가 install-time invariant — yaml.example 부재 (e.g. 운영자 yaml.example 삭제, sparse-checkout fail) 시 fail-fast 처리 필요. design 의 line 156-158 은 `WIKIHUB_SRC + "/wikihub.yaml.example"` read 만 명시, 부재 시 처리 미명시.

- ADR-0031 §Decision A 의 "install.sh 의 yaml 개입 0건" 이 §Note v0.1.7 + 본 §Note 2건으로 누적 — ADR 본문 의 "yaml" 의미 모호 (operational yaml 의 value 만 vs schema 도 포함). ADR-0031 자체의 결정 명료성 약화.

**권고**:

design v2 에서:

(a) **§2.2.1 본문에 ADR-0031 §Decision A + §Note v0.1.7 의 cross-link 본문 추가** (1줄 footer 아니라 2~3 paragraph):
- "install.sh 의 yaml 개입 0건" 의 의미 = **value mutation 0건**. schema mutation 의 source 진화: v0.1.5 hardcode dict → v0.1.7 hardcode + drift detect → v0.1.8 yaml.example read.
- 본 fix 후 yaml.example 가 single schema authority — install.sh + `/wh-setup` 모두 read-only consumer.

(b) **yaml.example 부재 시 fail-fast** 명시 (line 156 의 `open(example_path)` 직전 + 부재 시 `sys.exit(2)` + ops-alert 의도):
- WIKIHUB_SRC env 미설정 시 default path (e.g. `~/.local/share/wikihub/src`)
- yaml.example 부재 → schema migration 거부 + 운영자 진단 trigger (sparse-checkout 의심)

(c) **ADR-0031 §"후속 영향" 갱신 1줄 → §Note (2026-05-25, feature update_path_fixes) 신설 권장**: schema mutation 의 source = yaml.example 의 정본화 명시. ADR 본문의 의도 보존 (yaml writer 단일성 + schema authority 단일성 두 invariant 의 명료화).

---

### H2. yaml.example sync 의 list/dict 깊이 처리 미정의 — `vaults[]` array + `retry` nested dict 처리 design fail

**위치**: `analysis_and_design.md` line 161-179 (`_sync_field` 함수) + line 191-198 (jagged corner)

**인용**:
```python
def _sync_field(target: dict, source: dict, key_path: str):
    """target dict 에 source 의 key 가 없으면 default 자동 추가. 운영자 명시 값 보존 (set semantics)."""
    keys = key_path.split(".")
    t, s = target, source
    for k in keys[:-1]:
        t = t.setdefault(k, {})
        s = s.get(k, {}) if isinstance(s, dict) else {}
    last = keys[-1]
    if last not in t and isinstance(s, dict) and last in s:
        t[last] = s[last]
        flags.append(f"B_sync:{key_path}")

# operations / agent 의 모든 default field 일괄 sync
for top in ("operations", "agent"):
    example_top = example.get(top, {})
    if isinstance(example_top, dict):
        for k in example_top:
            _sync_field(data, example, f"{top}.{k}")
```

**문제**:

1. **`vaults[]` array 미처리** — `_sync_field` 가 `operations / agent` top 만 iterate. `vaults[]` 의 array 안 field (e.g. `sync_interval_sec`, `options.exclude_shared_with_me`) 는 본 helper 미커버. v0.1.7 `_migrate_agent_schema` 의 line 822-826 (existing code) 의 `for idx, v in enumerate(vaults)` 패턴은 본 helper 일반화에 흡수 안 됨. **vault-level field 부재 시 drift 미surface** = 본 fix 의 일반화 의도 위반.

2. **`operations.retry` nested dict 미처리** — `retry: {max_attempts: 5, backoff_base_sec: 60}` 는 dict-of-dict. `_sync_field` 가 `operations.retry` 전체를 dict 로 setdefault 하면 `max_attempts` / `backoff_base_sec` sub-field 부재 시 graceful default 미적용. iterate 가 top-level key 1단계만 — sub-field iteration 부재.

3. **value-level dict (`agent.models`) 처리 모호** — `models: {wh-lint: deepseek-v4-flash, wh-ingest: deepseek-v4-pro}` 는 dict-of-string. 운영자가 `models` 전체 dict 부재 시 sync 가 yaml.example 의 dict 전체 복사. 운영자가 `models: {wh-lint: minimax-m2.5}` 만 보유 (wh-ingest 부재) 시 — wh-ingest sub-key 자동 추가? design fail (iterate top-level key 만).

4. **line 192-193 의 jagged corner** — multipass v0.1.0 의 oneshot_args = `['chat', '--skills', '{skill}', '--quiet', '--query']` (--yolo 만 부재). design 의 결론 (line 196-199): "Group A `A_yolo_missing` 만 복원" — 이 복원 자체는 정합. 단 **본 design 의 yaml.example sync helper 본체로는 처리 불가** (list 는 atomic).

**평가**:

R2 fix 의 일반화 design 이 actual yaml schema 의 복잡성 (array + nested dict + list) 흡수 못함. line 174-179 의 `for top in ("operations", "agent")` + line 178 의 `for k in example_top` 는 **flat dict 의 1단계 만 동작** — yaml.example 의 실 구조 (line 16 `vaults:` array, line 39 `retry: {...}` nested) 와 mismatch.

multipass v0.1.0 의 yaml 의 jagged 패턴 (oneshot_args list, --yolo 부재) 의 분리 처리 (`A_yolo_missing` 만 복원) 는 정합 결정이나 — **본 design 의 helper 는 R2 결함의 50% 만 cover**:
- ✅ cover: `agent.timeout_sec` 부재, `operations.monitor_enabled` 부재 등 scalar field 부재
- ❌ 미cover: `vaults[].sync_interval_sec` 부재 (현행 hardcode 가 별도 처리), `operations.retry.max_attempts` 부재 (sub-field), `agent.models.wh-ingest` 부재 (dict-of-string sub-key)

design 의 §Q3 (line 263) "yaml.example sync 의 list/dict 깊이 (top-level 만 vs 재귀)" 미결을 Step 3 까지 끌고 가는 design 결정 자체는 정합 (D4=b 의 일반화 ROI vs 깊이 trade-off). 단 design 본문이 깊이 결정 lock 안 함.

**권고**:

design v2 에서:

(a) **§2.2.1 의 `_sync_field` 일반화 design 의 깊이 spec lock**:
- (i) **shallow (top-level scalar only)**: `agent.<key>` / `operations.<key>` 의 scalar만. `vaults[]` array + `retry` nested dict 는 별도 처리 hardcode 유지. design 단순 + 본 fix 의 ROI (큰 jump 운영자 protection) 의 80% 달성.
- (ii) **recursive (dict 깊이 + array iterate)**: yaml.example 의 모든 leaf scalar 까지 sync. 일반화 완전성 ↑ 그러나 design 복잡 + edge case (운영자 명시 array element 보존 등) 부담.
- (iii) **shallow + 예외 hardcode**: shallow + `vaults[].sync_interval_sec` 같은 known case 만 hardcode. design 의 line 822-826 (existing) 패턴 보존.

(b) **본 design 의 일반화 ROI 재평가**: 운영자 base v0.1.5+ 정착 가정 (multipass v0.1.0 는 test setup 부산물) 이면 큰 jump 운영자 protection 의 실 ROI 낮음 → D4=b 의 ROI 자체 약화. **D4=a (현행 hardcode dict 유지 + 신규 field add 시 install.sh 갱신 책임 명시)** 의 trade-off 재고려 권장. design 의 §1.2 (line 35-60) 가 multipass test 의 v0.1.0 yaml 이 본 fix 의 실 surface — 운영 실 base 와 거리. R2 fix 의 ROI 가 "multipass test 자체 setup 안정화" 라면 multipass setup 의 fresh install path 정합 검토 (큰 jump 시뮬 자체 회피) 가 root cause fix 일 수 있음.

(c) **Q3 closure 시점 Step 2 까지 끌어내림**: 깊이 결정은 helper 코드 행 수에 직접 영향 — Step 3 진입 시점에 line 변동 risk 큼. design v2 의 closure 권장.

---

### H3. `A_yolo_missing` 복원 결정이 design 본문에 "Group A 복원 안 함" 의 일관성과 일부 모순

**위치**: `analysis_and_design.md` line 196-199 (§2.2.2 jagged corner)

**인용**:
```
본 design 채택: **(i) Group A `A_yolo_missing` 만 복원** + yaml.example sync (R2 fix 본체) 결합.
legacy_migration_cleanup 의 `A_skill_prefix` (wh: → wh-) 등 다른 Group A 는 복원 안 함
(운영자 base v0.1.4+ 정착 가정 정합).
```

**문제**:

legacy_migration_cleanup (`fd7f0fe`) 의 Group A 삭제 근거 (analysis_and_design.md line 22): "v0.1.1~v0.1.4 era install 운영자 모두 정착". 즉 **3개 Group A flag (A_skill_prefix / A_oneshot_legacy / A_yolo_missing) 가 동일 근거로 삭제**.

본 design 의 R2 fix 가 `A_yolo_missing` 만 복원 + 나머지 2개 (A_skill_prefix / A_oneshot_legacy) 는 복원 안 함 — **근거의 비대칭** surface:

- multipass v0.1.0 의 yaml 이 `oneshot_args = ['chat', '--skills', '{skill}', '--quiet', '--query']` — F5 schema 의 `{skill}` placeholder 보유 (A_oneshot_legacy 발화 안 함), `wh-` prefix 보유 (A_skill_prefix 발화 안 함), **`--yolo` 만 부재** (A_yolo_missing 만 발화).
- multipass v0.1.0 = "F5 적용 후의 v0.1.0~v0.1.2 era yaml" (`--yolo` 도입 전, hermes_yolo_flag feature `2026-05-19` 직전).
- 만약 운영자 base 가 v0.1.0~v0.1.2 era (F5 적용 후 / yolo 도입 전) 라면 — **A_yolo_missing 발화는 필연**.

그러나 design 의 §1.2 (line 60) 명시: "실 운영자 base 는 v0.1.5+ 정착 가정이라 발생 빈도 낮으나 본 multipass test 가 실 surface". 즉 **실 운영자 protection ROI 자체가 낮음** — A_yolo_missing 복원이 multipass test 단독 ROI.

**평가**:

A_yolo_missing 복원의 design 결정 자체는 jagged corner 의 합리적 처리. 단:

1. legacy_migration_cleanup 의 design 정합 (Group A 3건 삭제) 이 본 fix 로 부분 reverse — design v2 에서 `legacy_migration_cleanup` design rationale 의 정합 명시 필수. "운영자 base v0.1.4+ 가정" → "운영자 base v0.1.4+ 가정 + multipass test fresh install 의 v0.1.0~v0.1.2 yaml surface 의 backstop 1건" 의 narrowing.

2. A_yolo_missing 만 복원 + A_oneshot_legacy / A_skill_prefix 복원 안 함 의 비대칭 의도 부각 — 만약 운영자가 v0.1.0 yaml (skill_prefix `wh:` 보유) 운영 중이면 본 R2 fix 후에도 systemd unit 의 skill 명 mismatch surface 안 됨. design 의 R2 fix 가 multipass test 의 yaml 만 cover.

**권고**:

design v2 에서:

(a) **§2.2.2 본문에 `A_yolo_missing` 복원 결정의 narrowing 명시**:
- multipass v0.1.0 yaml = F5 적용 후 / yolo 도입 전 (v0.1.0~v0.1.2 era yaml) — yaml의 oneshot_args list element 1개 부재의 jagged 패턴 surface.
- A_skill_prefix / A_oneshot_legacy 의 복원 안 함 = legacy_migration_cleanup 의 운영자 base v0.1.4+ 가정 보존.
- **본 fix 는 multipass test 의 fresh install 안정화 ROI** — 실 운영자 v0.1.0~v0.1.2 era yaml 운영 중이면 manual 보강 필요 (운영자 진단 책임).

(b) **legacy_migration_cleanup design 의 cross-link** — `features/archive/20260525_legacy_migration_cleanup/analysis_and_design.md` 의 D-N entry 참조. 본 fix 가 D-N 의 부분 reverse 임을 surface.

(c) **multipass test setup 의 fresh install path 정합 검증** — multipass test 가 v0.1.0 → v0.1.8 jump 시뮬 의도였다면, multipass test 자체의 fresh install 권장 (큰 jump 시뮬 안 함). 본 R2 fix 의 ROI 가 multipass test 의 의도 mismatch 자체일 수 있음 → Q3 의 Q와 분리하여 **별도 미결**: multipass test 의 fresh install path 의 정합 (큰 jump 시뮬 가치 vs fresh install 가치).

---

### H4. AgentConfig 의 `skill_chains` field 추가 시 backward-compat 보강 필요

**위치**: `analysis_and_design.md` line 69 (영향받는 파일) + line 213 (변경 범위)

**인용**:
```
| `scripts/lib/config.py` `AgentConfig` | `skill_chains: dict[str, list[str]] | None = None` field 추가 |
```

**문제**:

`scripts/lib/config.py:35-42` 의 `AgentConfig` dataclass + `_parse_agent` (line 140-148):
```python
@dataclass
class AgentConfig:
    type: str
    binary: str
    oneshot_args: list[str]
    skill_prefix: str
    timeout_sec: int
    notify_on_fatal: bool
```

`skill_chains` 추가 design 의 정합 의도 — 그러나 다음 보강 필요:

1. **dataclass field default**: `skill_chains: dict[str, list[str]] | None = None` — 정합. 단 dataclass field 순서 (default 없는 field 와 default 있는 field 의 순서 규칙). 현행 dataclass 가 모두 default 없음 → `skill_chains` 만 default 면 field 순서 끝.

2. **`_parse_agent` 추가 처리**: line 140-148 에 `skill_chains=acfg.get("skill_chains")` 추가 필요. None default 정합.

3. **타입 validation**: yaml 의 `skill_chains` 값이 dict 형식인지 validate — 현행 `_parse_agent` 가 None-tolerant `acfg.get(...)` 만 호출, schema 위반 (e.g. `skill_chains: "wh-lint"` 처럼 string) 시 fail-fast 안 됨. design v2 에서 `if skill_chains is not None and not isinstance(skill_chains, dict): raise VaultSyncFatal(...)` 추가 권장.

4. **render_systemd_units.py 의 `_per_skill_invocation` 의 chain key 부재 graceful** — design line 105-110 의 `(cfg.get("agent") or {}).get("skill_chains") or {}` 는 None-tolerant. 단 chain 의 sub-skill 명이 `_WIKIHUB_SKILLS` 5건 외 이면 (e.g. 오타 `wh-graphfy`) — render 시점 detect 안 됨, hermes 시점 silent skip. design 본문에 sub-skill 의 5건 catalog 검증 추가 권장 (1줄).

**평가**:

design line 69 + line 213 만 fragmentary 명시 — 실 코드 변경 detail (default 순서, validation, error path) 부재. config.py 의 변경이 5줄 미만이라 design 본문 보강 ROI 높음.

**권고**:

design v2 에서:

(a) **§2.1.1 또는 신설 §2.1.4 에서 config.py 변경 spec 구체화**:
- AgentConfig field 추가 line + default
- `_parse_agent` 의 `skill_chains` parse 1줄
- validation: dict 형식 + sub-skill 명 catalog (`_WIKIHUB_SKILLS` import)
- error path: invalid 시 `VaultSyncFatal(vault_id="__config__", reason="agent.skill_chains 형식 위반", ...)`

(b) **render_systemd_units.py `_per_skill_invocation` 의 sub-skill 검증 1줄** — chain 의 sub-skill 명이 `_WIKIHUB_SKILLS` 5건 외 이면 fail-fast (현행 placeholder 부재 검증 line 154-163 패턴 정합).

---

## M — Medium (보강 권장)

### M1. `Q2` 미결의 closure 시점이 Step 3 — design 결정의 일관성 약화

**위치**: `analysis_and_design.md` line 261-262 (Q2)

**인용**:
```
| Q2 | `_migrate_agent_schema` Group A 의 다른 항목 (`A_skill_prefix` 등) 복원 여부 | Step 3 — multipass 의 v0.1.0 yaml 가 wh: → wh- 변환 필요한지 확인 |
```

**문제**:

§2.2.2 (line 199) 가 이미 결론: "다른 Group A 는 복원 안 함 (운영자 base v0.1.4+ 정착 가정 정합)". 그러나 Q2 가 "복원 여부" 를 Step 3 까지 미결 둠 — design 본문 결론 (line 199) 과 미결 항목 (line 262) 의 정본성 충돌.

**평가**: design v2 에서 Q2 closure (line 262 의 항목 자체 제거 또는 "Q2 = §2.2.2 line 199 의 결론 lock") 1줄 정정.

---

### M2. design v1 의 line count 추정 (+60 / -40) 의 R2 fix 부분 underestimate

**위치**: `analysis_and_design.md` line 215-220 (§2.4 변경 범위)

**인용**:
```
| `install.sh` `_migrate_agent_schema` Group B | hardcode dict → yaml.example read 기반 sync (Group B/C 통합) | +30 / -40 |
| `install.sh` `_migrate_agent_schema` Group A_yolo_missing | 복원 (legacy_migration_cleanup 부분 되돌림) | +10 |
```

**문제**:

현행 `_migrate_agent_schema` 의 Group B detect (line 790-820) + migration (line 880-925) 합치면 약 60줄. 이걸 yaml.example read 기반 일반화로 치환 시:
- Python heredoc 의 yaml.example read + `_sync_field` 함수 정의: +25 줄
- iterate top-level keys: +5 줄
- flags emit: +5 줄
- info case `B_sync:*`: +3 줄

→ +38 / -50 = net -12. design 의 +30 / -40 estimate 와 약간 mismatch. 단 line 차이 자체는 본 fix critical path 영향 없음 — Step 3 implementation 시점 의 actual diff 측정.

**권고**: design v2 의 line estimate 정확성 보강 — Step 3 진입 시 diff stat 의 reference 정합 trace 가치.

---

### M3. `wikihub.yaml.example` 의 `agent.skill_chains` 신설 시 default value choice 명확화 부족

**위치**: `analysis_and_design.md` line 82-90 (§2.1.1 yaml schema 신설)

**인용**:
```yaml
agent:
  # ...
  skill_chains:                      # v0.1.8 신설 — multi-skill orchestration (R1 fix)
    wh-lint: [wh-graphify]           # lint cycle 의 Step 9 graphify chain 활성
    # wh-ingest: []                   # 단일 skill (default), 명시 안 함도 가능
```

**문제**:

`skill_chains` 의 default 가 yaml.example 에 명시 = `{wh-lint: [wh-graphify]}` — 운영자 fresh install 시 lint cycle 의 graphify chain 자동 활성. `operations.graphify_enabled: true` (yaml.example line 37 default) 정합.

단:
- 운영자가 `graphify_enabled: false` toggle 시 — render_systemd_units.py 의 `_per_skill_invocation` 가 `skill_chains.wh-lint` 도 무시해야 하나? design 미명시.
- 만약 무시 안 함 — `wh-lint` ExecStart 가 `--skills wh-lint,wh-graphify` 그대로 → wh-graphify skill load 되어도 lint.md Step 9 가 toggle 검사로 skip → wh-graphify 호출 안 됨. **동작 정합** 단 hermes process resource 만 낭비.
- 만약 무시 — render 시점 yaml `operations.graphify_enabled` 의존 추가 필요. **design 복잡 ↑** + agent.skill_chains 의 정합 의미 모호.

**권고**:

design v2 에서 §2.1.2 의 chain expansion 정책 명시:
- (a) **skill_chains 무조건 expand** — `operations.graphify_enabled: false` 시에도 ExecStart 는 multi-skill. lint.md Step 9 의 toggle 검사가 actual graphify 호출 차단. 단순 + render 변경 5줄 유지.
- (b) **graphify_enabled 검사 후 expand** — render 시점 yaml `operations.graphify_enabled` 검사. `_per_skill_invocation` 의 dependency 증가.

→ (a) 권장 (design 의 D3=a 의 "최소 변경" 정신 정합).

---

### M4. multipass 실측 plan (§2.5) 의 verification criteria 가 weak

**위치**: `analysis_and_design.md` line 222-253 (§2.5 multipass 실측 계획)

**인용**:
```bash
# 3. lint 재시도 + graphify chain 실 동작 검증
multipass exec wikihub-test -- bash -c '
  systemctl --user start wikihub-lint.service
  # 5분 대기 후
  ls -la ~/wikihub/graphify-out/graph.json && echo "✅ R1 fix verified" || echo "❌ fallback design 필요"
'
```

**문제**:

verification criteria = `graph.json` 존재 여부 (binary). 그러나:

1. **timing dependency** — "5분 대기" 가 magic number. 실제 LLM backend latency (DeepSeek 등) + graphify subprocess 가 15분 timeout (yaml `graphify_timeout_sec: 900`). 5분 후 fail 시 `graphify-out/graph.json` 부재 = "R1 fix fail" vs "timing 부족" 구분 불가.

2. **silent partial success** — graph.json 생성됐으나 nodes 0 (LLM 실패 graceful) → verification pass but actual 결함. graphify 의 partial failure self-check (lint.md line 240-249 의 N/M ratio check) 활용 권장.

3. **fake `proc_xxx` hallucination 재현 detection 부재** — wh-lint LLM 이 multi-skill load 후에도 fake proc ID 출력하는 패턴 잔존 가능. journal grep 로 hermes orchestrator 의 wh-graphify spawn log 확인 권장.

**권고**:

design v2 에서 §2.5 verification:
- (a) **graph.json 존재 + 노드 수 ≥ 1** (binary → quantitative)
- (b) **journal log 의 graphify subprocess spawn line 명시 grep** (e.g. `journalctl --user -u wikihub-lint.service --since "5 min ago" | grep -i "graphify"`)
- (c) **timing flexibility** — `systemctl --user is-active wikihub-lint.service` polling 또는 `wait` until exit
- (d) **fail criteria 의 fallback design β/γ 선결정** — C1 권고와 연동

---

## L — Low (선택)

### L1. design 의 R1/R2 fix 의 testing surface 분리 표기 부족

§2.5 의 multipass plan 이 R1 + R2 fix 의 verification 을 통합. R2 fix 의 verification (큰 jump yaml 의 신설 field 자동 추가) 은 별도 시나리오 — yaml backup → field 삭제 → install.sh --update → field 자동 추가 확인.

**권고**: §2.5 의 verification 시나리오를 R1 fix + R2 fix 별로 분리.

### L2. ADR cross-link 의 directionality 부족

design 의 §2.3 (line 202-205) 는 ADR-0031 §"후속 영향" 의 cross-link 1줄만 명시. ADR-0032 / ADR-0033 / ADR-0036 (lint.md Step 9 의 graphify call) 의 cross-link 미명시.

**권고**: design v2 의 §2.3 에 영향 ADR catalog 작성 (ADR-0031 / ADR-0032 / ADR-0033 의 §"후속 영향" 또는 §Note 갱신 책임).

### L3. `_lint/report.md` 의 graphify chain status 의 운영자 surface 결정 부재

§1.1 (line 33): "운영자가 `_lint/report.md` 의 'graph.json 없음' 메시지 보고도 의미 인식 어려움". R1 fix 후의 report.md 명시 형식 (`graph rebuilt: N nodes, M edges` 또는 `graphify chain skipped (yaml toggle)`) 의 운영자 actionable 분리는 lint.md Step 9 (line 234-235) 가 spec — 본 fix 의 lint.md spec 무변경 정합. 단 R1 fix verification 의 user-facing 안내가 강화될 가치.

**권고**: design v2 의 §2.5 verification 의 report.md 확인 단계 추가.

### L4. `features/backlog.md` BL-N? 추가 명시 (line 219) 의 backlog 컨벤션 미준수

§2.4 line 219: "BL-N? 추가 (R1 fallback design β/γ if hermes 실측 fail)" — BL-N? 의 N 미지정. backlog 의 next id 확인 필요.

**권고**: design v2 에서 actual BL-N id 명시 또는 "Step 3 실측 시점에 발급" 로 명확화.

---

## 통과 관점

다음 design 결정은 정합 + 본 review 의 통과:

1. **D1=v0.1.8 hotfix 통합** — release 전 발견 결함의 hotfix 정합 (plan.md line 31).
2. **D2=단일 feature `update_path_fixes`** — R1/R2 두 결함이 모두 운영자 update path 결함 + canary cycle 정합 (plan.md line 32).
3. **D3=a multi-skill load** — lint.md spec 무변경 + ADR-0032/0033 보존 정합 (가장 작은 변경 path). 단 C1/C2 의 fallback + ADR 갱신 책임은 흡수.
4. **D4=b yaml.example sync** — schema authority 의 single source of truth 보존 (ADR-0031 §Note v0.1.7 정합). 단 H1/H2 의 깊이 spec + cross-link 보강.
5. **§2.1.2 의 `_per_skill_invocation` 변경 5줄 design** — 기존 placeholder substitution 패턴 정합 + chain expansion 의 작은 추가.
6. **§Decision D4=b 의 `_migrate_agent_schema` 일반화 방향** — schema mutation 의 yaml.example single authority 정합 (단 깊이 spec 보강).
7. **plan.md line 33 의 D3=a "ADR 정합 보존" 결정** — multi-skill load 자체가 hermes 의 multi-value `--skills` flag spec 정합 (단 chain semantic 의 ADR 갱신 책임 surface 필요 — C2).
8. **A_yolo_missing 만 복원 결정** — multipass test 의 jagged corner narrow 처리 (단 narrowing rationale 본문 보강 — H3).

---

## 범위 외 (본 feature scope 외 — 후속 처리 권장)

1. **multipass test 의 fresh install path 정합 검토** — 본 review 의 H3 권고. multipass test 의 v0.1.0 → v0.1.8 jump 시뮬 의도가 fresh install 의 의도 mismatch 일 수 있음 — 별도 feature scope.

2. **hermes `--skills` flag multi-value semantic 의 정본 docs trail** — design 의 D3=a 의 hermes 동작 가정이 ADR/spec 외 — hermes upstream docs 의 link 또는 wikihub 의 hermes_min_version 검증 등 별도 feature scope.

3. **`features/backlog.md` 에 hermes external dependency tracking** — R1 결함의 root cause 가 hermes 의 sub-skill spawn semantic. wikihub 의 hermes versioning + 호환성 정책 별도 feature scope (BL- 신설 권장).

4. **ADR-NNNN skill-chain-orchestration 신설 검토** — design 의 §2.3 "ADR 신설 보류" 의 reframe (C2 권고). 본 feature scope 작아 ADR 신설 ROI 의문 — 별도 feature 로 분리 가능 (v0.1.9 또는 v0.2.x).

---

## 권장 흐름

1. **본 review 의 C1/C2/H1/H2/H3/H4 흡수 → design v2 작성** (Step 2 재진입).
2. design v2 의 multi-reviewer (Gemini/Codex CLI 또는 별도 Claude 세션) 1건 추가 권장 — 본 review 가 단일 reviewer.
3. design v2 의 사용자 승인 후 Step 3 진입.
4. Step 3 의 multipass 실측이 fail 시 design v2 의 fallback (β/γ) skeleton 으로 즉시 design v3 작성 가능 — Step 3 retry loop 회피.
