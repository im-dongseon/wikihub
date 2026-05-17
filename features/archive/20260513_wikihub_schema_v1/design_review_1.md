# Design Review 1 — feature-dev:code-reviewer

- **Reviewer**: feature-dev:code-reviewer subagent (Claude, context-fresh)
- **Date**: 2026-05-13
- **Target**: F2 (`wikihub_schema_v1`) — `_system/*` + ADR-0005~0012

## Summary

F2 spec is architecturally sound and ready for approval after four targeted fixes. The core design — agent-as-orchestrator (ADR-0006), all-JSON state (ADR-0007), permission layering by reversibility (ADR-0008), `wh:` skill prefix (ADR-0011), and `<agent_invocation>` abstraction (ADR-0012) — is internally coherent and faithfully reflected across the five playbooks. F1 ADRs (0001–0004) are not contradicted anywhere. Four high-confidence issues were found: a field-name mismatch in `ingest.md` that will produce a silent data-loss bug in F3/F5 implementation, a control-flow ordering inversion in the same file that will cause divergent implementations, a stale internal-review reference, and a typo in an operator-visible install instruction. Three medium-confidence observations round out the findings.

## Findings

### High confidence — must fix before approval

#### H1. ingest.md §Step 1 bullet 1 — `pending_ingest.json` field names contradict Step 3 schema

Step 1 instructs the agent to read `changed_files` and `deleted_files` from `pending_ingest.json`. Step 3 defines the actual JSON schema of that same file with fields `changed` and `deleted`.

**Evidence**:
- `_system/commands/ingest.md` line 28: `파일 read → \`changed_files\`, \`deleted_files\` 추출`
- Same file lines 86–87 (Step 3 schema block): `"changed": [...], "deleted": [...]`

**Impact**: F5 (or any agent implementing this playbook) reads non-existent keys on recovery. The pending file parses successfully as JSON but `changed_files`/`deleted_files` resolve to null/empty. Step 4 runs with empty change list — all pending vault changes are **silently lost**. The `attempts` counter eventually fires the max-exceeded quarantine path without changes ever being processed. **Data-loss failure mode with no visible error.**

**Suggested fix**: In Step 1 bullet 1, change `changed_files` → `changed` and `deleted_files` → `deleted`.

---

#### H2. ingest.md §Step 1 bullets 3–4 — `attempts` increment listed after unconditional jump

Step 1 is a numbered list. Bullet 3 says "Step 4(semantic phase)로 점프" (unconditional forward jump). Bullet 4 says "`attempts` += 1. ... 초과 시: [quarantine + exit 2]". A sequential reader executing bullet 3 never reaches bullet 4.

**Evidence**: ingest.md lines 30–34

**Impact**: As written, the `attempts` guard is permanently inactive — retry loop runs forever and pending files are never quarantined. Implementers who infer the intended order will implement it correctly, but the spec is inverted. Three plausible readings produce divergent F5 behavior.

**Suggested fix**: Reorder bullets so increment + check precede the jump:
```
1. 파일 read → `changed`, `deleted` 추출
2. `attempts` += 1. max_attempts 초과 시: 
   - pending_ingest.dead.<utc_iso>.json 이동
   - ops-alert 트리거 + systemd OnFailure
   - exit 2
3. script subprocess 건너뜀
4. Step 4 진행
```

---

#### H3. ingest.md §Step 1 bullet 4 — stale reference `§C2` not resolvable from `_system/`

Bullet 4 says: `운영자 알림 (notify 경로 §C2 + systemd OnFailure)`. `§C2` is internal notation from the F1 SRE design review. Not resolvable from `_system/commands/ingest.md`.

**Evidence**: ingest.md line 33

**Impact**: Any reader of `ingest.md` as canonical spec cannot resolve `§C2`. Per CLAUDE.md §1, `_system/` is Operations Zone and must be self-contained. Cross-references into `features/` workspace violate this boundary.

**Suggested fix**: Remove `§C2` entirely. Replace with: `ops-alert 트리거 + systemd OnFailure`.

---

#### H4. graphify.md §Step 1 — `pip install graphifyy` typo (double-y)

**Evidence**: graphify.md line 30: `"graphify 미설치 — install.sh 재실행 또는 \`pip install graphifyy\` 안내"`

**Impact**: Agent emits message directing operator to install non-existent `graphifyy` package. Operator gets "package not found" from pip on an already-confused situation.

**Suggested fix**: `pip install graphify` (single y). Verify actual PyPI package name — if internal/unreleased, remove pip fallback from agent-visible output.

---

### Medium confidence — should consider

#### M1. ingest.md §실패 처리 — "Hermes 채널" agent-specific (ADR-0012 위반)

**Evidence**: ingest.md line 160: `notify 이중 경로 발동(Hermes 채널 + systemd OnFailure)`

ADR-0012는 spec이 agent-agnostic이어야 함을 요구. "Hermes 채널"이 Hermes-specific 개념 baking. codex-cli·gemini-cli 구현자는 misread 가능.

**Suggested fix**: Replace with `ops-alert 트리거 + systemd OnFailure (agent.notify_on_fatal 경로)`.

---

#### M2. query.md §Step 6 — `hermes.service` hardcoded in diagnostics example

**Evidence**: query.md line 109: `journalctl --user -u hermes.service`

systemd unit name은 `wikihub.yaml.agent.binary`에 따라 다름. 항상 `hermes`가 아님.

**Suggested fix**: `journalctl --user -u <agent-service>` + 괄호 안내 `(예: hermes.service, agent.binary 기준)`.

---

#### M3. wiki-schema.md §참조 — ADR range "0001~0011" omits ADR-0012

**Evidence**: wiki-schema.md line 318: `결정 기록: \`docs/adr/\` (ADR-0001 ~ 0011 + 후속)`

ADR-0012가 F2 deliverable인데 본문 3회 참조(라인 215, 280, 286). 참조 섹션의 명시적 range가 0011에서 끊기는 건 부정확.

**Suggested fix**: `ADR-0001 ~ 0012 + 후속`.

---

### Low confidence / nits — optional

#### L1. setup.md §Step 1 — `operations.disk.*` yaml 키 F2 미정의

setup.md Step 1이 `operations.disk.*` 검증을 명시하나(라인 32, 47) 구조는 F2 어디에도 정의 없음. F4의 yaml.example이 정본인데 그 시점 전까지 검증 spec이 없음.

**Suggested fix**: setup.md Step 1에 노트 추가: `operations.disk.* — 스키마는 F4 산출물에서 정의. F4 완료 전까지 검증 생략 가능`.

---

#### L2. setup.md §Step 1 — initial JSON structure for `cursor.json`·`file_map.json` 미정

ADR-0007이 `retry.json`의 완전한 스키마는 주나 `cursor.json`·`file_map.json`의 초기 값(빈 상태)은 명시 X. F3 구현자가 추측해야.

**Suggested fix**: 초기값 예시 추가 (`cursor.json: {}` 또는 `{"page_token": null}`) — setup.md 또는 ADR-0007 §Consequences에.

---

## What I checked but found OK

- **ADR-0006 unified orchestration**: ingest.md correctly implements mechanical phase (subprocess → JSON output → has_changes check) followed by semantic phase. Early exit on has_changes=false present. pending_ingest.json lifecycle (write Step 3, delete Step 6) matches ADR-0006 design.
- **ADR-0007 all-JSON consistency**: wiki-schema.md correctly shows `retry.json`. No SQLite references survive in F2. 5-file state schema consistent across wiki-schema.md and ingest.md.
- **ADR-0005 index/log locality**: ingest.md output table explicitly marks wiki/index.md as "본 명령은 수정 안 함". lint.md Step 5 correctly owns index reconstruction. log.md vault-specific throughout.
- **ADR-0008 permission matrix**: lint.md's auto/--apply split exactly matches ADR-0008's matrix. No drift found.
- **ADR-0011 `wh:` prefix compliance**: all 5 playbook 호출 sections use `<agent_invocation> "/wh:command"`. wiki-schema.md command table uses `/wh:*` consistently.
- **ADR-0012 `<agent_invocation>` compliance**: all 5 playbooks use placeholder in procedure step bodies. Single concrete `hermes -z` example in wiki-schema.md correctly labeled "예 (Hermes)".
- **ADR-0001 vault namespace + link convention**: wiki-schema.md `[[link]]` section correctly mandates vault-prefix for sources, prohibits shorthand. lint.md Step 2 catches all 3 violation types. query.md Step 3 uses correct format.
- **ADR-0009 setup responsibility**: setup.md correctly scoped to yaml→systemd sync + validation. Legacy v0.2.6 tasks absent.
- **ADR-0010 deploy.sh 폐기**: no deploy.sh references anywhere. install.sh correctly described as update mechanism.
- **ADR-0003 OAuth**: setup.md Step 1 validates credentials consistently.
- **ADR-0004 Direct Drive API**: not contradicted. F2 correctly defers to F3.
- **ADR-0002 compatibility with ADR-0012**: ADR-0002 generalized by ADR-0012 without contradiction.
- **F1 §4.5.5 신뢰 경계 lift**: wiki-schema.md faithfully lifts F1's 5-layer trust boundary.
- **F1 §4.1.3 timestamp policy lift**: wiki-schema.md correctly lifts UTC ISO 8601 / KST-label convention.
- **VERSION file**: `0.1.0` consistent.
- **graphify.md ↔ lint.md integration**: lint.md Step 9 correctly handles graphify failure without propagating to lint's exit code.
- **wiki-schema.md 책임 매트릭스**: covers all resources including `_state/` agent write scope (`pending_ingest.json` only).
- **`wiki/.archived/` path consistency**: lint.md Step 7 and wiki-schema.md tree both use same path.

## Open questions for author

1. **`operations.retry.max_attempts` default**: ingest.md references this key but no default in F2. yaml에서 키 부재 시 hardcoded default(예: 3) fallback 여부 명시 필요.

2. **`operations.hermes_concurrency` 키명**: F1 §4.6.5에서 정의된 키명이 "hermes"를 포함 → ADR-0012 정신 위반. F4가 yaml.example 작성 전에 `operations.max_concurrent_vaults` 등으로 rename 권장.

3. **`graphify` PyPI 패키지명**: graphify.md가 `pip install graphify` 가능 가정. unreleased면 production 실패. 확인 또는 fallback 제거.

4. **lint.md Step 7 interactive sub-mode**: ADR-0008은 `--apply`만 gating. lint.md Step 7은 "사용자가 수정·제거 표시한 것" qualifier 추가 → 다음 문장이 F5 deferral + v0.1.0 batch-apply로 해소. v0.1.0 batch-apply 명시 확정 권장.
