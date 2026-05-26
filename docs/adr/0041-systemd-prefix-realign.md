# ADR-0041: systemd unit prefix `wikihub-` 일관화 — Hermes skill `wh-` 와 layer 분리

- **Status**: Accepted
- **Date**: 2026-05-26
- **Feature**: features/20260526_systemd_prefix_realign
- **Supersedes**: 없음 (commit `2ed01f8` 의 rename 결정은 ADR 없는 implementation level — 본 ADR 이 직접 정정)
- **Superseded by**: 없음

## Context

v0.1.9 release window 의 commit `2ed01f8` (2026-05-26, `fix(systemd): rename unit files wh-ingest@ / wh-lint for consistency with skill names`) 가 systemd unit 의 prefix 를 Hermes skill 이름과 통일하기 위해 rename:

- `wikihub-vault@.{service,timer}.template` → `wh-ingest@.{service,timer}.template`
- `lint.{service,timer}.template` (no prefix) → `wh-lint.{service,timer}.template`

당시 commit 의 명분: skill name (`wh-ingest`, `wh-lint`) 와 systemd unit name 의 1:1 visual 매핑으로 운영자 인지 부담 감소. GLM 5.1 / Mimo 2.5 Pro 멀티모델 리뷰 통과.

**문제 — 직후 maintainer 검토 (2026-05-26 본 ADR 트리거)**:

- 다른 systemd unit (`wikihub-mount@`, `wikihub-graphify`) 는 `wikihub-*` namespace 유지 → rename 후 systemd namespace 가 `wh-*` (2 unit) + `wikihub-*` (2 unit) + prefix-less (`ops-alert`) 로 **3종 혼재**. 일관성 손상.
- Hermes skill `wh-*` (ADR-0033 `wh-` prefix lock) 와 systemd unit 은 **두 다른 abstraction layer**:
  - Hermes skill = LLM 호출 unit (메인테이너 invocation `/wh-lint`, install.sh `hermes chat --skills wh-lint`)
  - systemd unit = OS service lifecycle unit (`systemctl --user start wikihub-lint.service`)
  - 두 layer 의 직접 매핑은 systemd ExecStart 의 hermes 호출 한 줄만 — visual prefix 통일의 효익이 namespace 일관성 손실 보다 작음.
- v0.1.8 시점의 `pending_alert_age_sec` 같은 yaml 필드 정합 사례 — abstraction layer 가 다르면 prefix 도 분리하는 정공법이 운영자 mental model 에 더 유익.

## Considered Options

- **(α) commit 2ed01f8 유지** — `wh-*` namespace 로 ingest/lint unit 만 운영. namespace 3종 혼재 그대로.
- **(β) systemd unit `wikihub-*` 일관화, Hermes skill `wh-*` 분리** — **채택**. layer 별 prefix.
- **(γ) Hermes skill 도 `wikihub-*` 로 통일** — ADR-0033 supersede 필요 + Hermes skill discovery (`wh-*.frontmatter.yaml`) + install.sh skill 등록 로직 + 메인테이너 muscle memory (`/wh-setup` → `/wikihub-setup`) 광범위 변경. 효익 대비 비용 과다.

## Decision

**채택**: (β) systemd unit prefix `wikihub-` 일관화, Hermes skill `wh-` 분리.

**Rename**:

| Before (commit 2ed01f8) | After (ADR-0041) |
|---|---|
| `_system/systemd/wh-ingest@.service.template` | `_system/systemd/wikihub-ingest@.service.template` |
| `_system/systemd/wh-ingest@.timer.template` | `_system/systemd/wikihub-ingest@.timer.template` |
| `_system/systemd/wh-lint.service.template` | `_system/systemd/wikihub-lint.service.template` |
| `_system/systemd/wh-lint.timer.template` | `_system/systemd/wikihub-lint.timer.template` |

**Layer 분리 정합**:

| Layer | Prefix | 예시 |
|---|---|---|
| systemd unit (OS service) | `wikihub-*` | `wikihub-ingest@<vid>.service`, `wikihub-lint.timer`, `wikihub-mount@<vid>.service`, `wikihub-graphify.service` |
| Hermes skill (LLM 호출 unit, ADR-0033) | `wh-*` | `wh-ingest`, `wh-lint`, `wh-query`, `wh-setup` |
| final dispatcher (ADR-0024, ADR-0040) | prefix 없음 | `ops-alert.service` |

**호출 chain**: `wikihub-lint.timer` (systemd) → `wikihub-lint.service` (systemd) → `hermes chat --skills wh-lint` (skill invocation). 두 layer 가 ExecStart 라인 하나로 연결 — prefix 통일 안 해도 명료.

**이유**:
- systemd namespace 단일화 (`wikihub-*`) — `systemctl --user list-timers '*wikihub*'` 로 모든 wikihub timer 일괄 조회 가능.
- ADR-0033 (skill prefix `wh-` lock) 영향 없음 — skill namespace 그대로.
- 호출 chain 의 명료성: 운영자가 `wikihub-lint.service` ExecStart 라인을 보면 "이 service 가 wh-lint skill 을 호출한다" 명시적.

**기각**:
- (α) namespace 3종 혼재 + commit 2ed01f8 의 명분 (skill 매핑) 이 prefix-level 통일 보다는 ExecStart 라인의 명시적 invocation 으로 더 잘 표현됨.
- (γ) ADR-0033 supersede + Hermes layer 전면 rename 의 비용이 효익 (visual prefix 통일) 보다 과다.

## Consequences

### 긍정

- systemd namespace 단일 — `wikihub-*` 가 4 unit (mount/ingest/lint/graphify) 일관 적용.
- ADR-0033 unchanged — Hermes skill discovery / install.sh 등록 / 메인테이너 invocation 영향 0.
- 운영자 mental model 명료화: "wikihub 의 OS service" vs "wikihub 의 LLM skill" 두 layer 가 prefix 로 구분 가시화.
- `systemctl --user list-timers 'wikihub-*'` 단일 패턴으로 모든 wikihub timer 조회.

### 부정 / 제약

- commit 2ed01f8 (v0.1.9 같은 release window) 의 rename 이 같은 window 안에서 반전 — git log churn. canary 운영자 가 짧은 기간 `wh-*` unit 운영 후 `wikihub-*` 로 재migration 필요 → install.sh upgrade migration block 의 stop+disable 대상 확장으로 mitigation.
- GLM 5.1 / Mimo 2.5 Pro 멀티모델 리뷰 (commit `97ecab2`) 가 `wh-*` 방향을 승인 — 직후 maintainer 검토 결과 다른 방향으로 정정. 리뷰의 가치 손상은 없음 (당시 결정 시점의 정확한 평가) 이나 메소드론 churn cost 인식.
- legacy unit 정리가 한 번 더 누적 (`legacy_singletons` catalog 에 4 entry 추가 + glob 패턴 추가).

### 후속 영향

- `install.sh` upgrade migration block 확장 — `wh-ingest@*.{service,timer}` + `wh-lint.{service,timer}` stop + disable.
- `scripts/_helpers/render_systemd_units.py` 의 `legacy_singletons` catalog 에 `wh-lint.{service,timer}` 추가. `_do_render` stale unit glob 패턴이 `wh-ingest@<vid>.{service,timer}` 매칭하도록 regex 보강.
- `_system/commands/setup.md` / `lint.md` / `graphify.md` 의 systemd unit ref 갱신. skill name ref 는 그대로.
- `_system/wiki-schema.md` inventory tree + namespace catalog 갱신.
- `README.md` systemd unit 예시 갱신.
- `docs/adr/0040-monitor-services-remove.md` 의 직전 narrative (carry-over 표 의 `wh-lint.service` 언급 1건) 갱신.
- v0.1.9 release window 의 git history 가 rename 의 진동 (`9aba573 → 58aaa90 → 2ed01f8 → 본 feature`) 보유 — squash 시점에 단일 commit 으로 정리됨.

### 재검토 트리거

- 본 prefix 분리의 비용 (운영자가 두 prefix 를 동시에 학습) 이 효익 (namespace 명료화) 보다 큰 운영 evidence 가 v0.2.x 시점에 surface 되면 (γ) 의 전면 통일 재검토 가능.
- ADR-0033 의 `wh-` lock 자체에 대한 재고는 별도 검토 (본 ADR 범위 외).

## Cross-references

- **연계 정합**: [ADR-0033](0033-skill-prefix-hyphen-lock.md) — Hermes skill `wh-` prefix lock (본 ADR 이 보존하는 layer).
- **연계 정합**: [ADR-0040](0040-monitor-services-remove.md) — 직전 monitor services remove 의 systemd unit catalog 정합. 본 ADR 이 carry-over 표 narrative 의 unit name 갱신 책임.
- **연계 정합**: [ADR-0030](0030-update-workflow-orchestration.md) — install.sh upgrade migration 의 stop/start orchestration. 본 ADR 의 legacy stop+disable 정합.
- **본 ADR 의 분석 정본**: [features/20260526_systemd_prefix_realign/analysis_and_design.md](../../features/20260526_systemd_prefix_realign/analysis_and_design.md)
- **이전 결정 context**: commit `2ed01f8` (fix(systemd): rename unit files wh-ingest@ / wh-lint for consistency with skill names) + 멀티모델 리뷰 docs/reviews/250526_v018fix_code_review_glm-5.1.md + mimo-v2.5-pro.md.
