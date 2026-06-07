# Plan — update_path_fixes

작성일: 2026-05-25 (KST)
작업자: wikihub maintainer

## 1. 작업 분류

**버그 (운영자 update path 결함)** — multipass `wikihub-test` 실 검증에서 surface 한 v0.1.8 의 2건 결함 fix.

## 2. 배경

`feature/lint_operations_improvements` (v0.1.8 ADR-0039 alias frontmatter) 의 multipass 실 검증 중 발견:

| ID | 결함 | 운영 영향 |
|---|---|---|
| **R1** | `wh-lint` Step 9 의 `<agent_invocation> "/wh-graphify"` 가 실제 wh-graphify subprocess spawn 안 됨 (LLM 의 fake `proc_xxx` 응답으로 silent skip) | graphify chain 운영자 인지 불가 — `graphify-out/graph.json` 미생성, lint cycle 은 success 종료. silent broken. |
| **R2** | `_migrate_agent_schema` 가 v0.1.0 → v0.1.8 큰 jump 시 yaml 신설 field 자동 추가 안 됨. 특히 `agent.oneshot_args` 의 `--yolo` 누락 시 모든 hermes-driven cycle (ingest/lint) 가 dangerous command Denied 로 stuck | 운영자 큰 jump update 시 systemd 자동 cycle 모두 fail. 운영자가 yaml 수동 보강 필요. |

## 3. 타겟 버전 브랜치

**D1 미결** — 사용자 결정 필요. 옵션:
- (a) **v0.1.8 hotfix** — release 전 fix. v0.1.8 의 운영자 update path 안정성 보장. release scope 확장.
- (b) **v0.1.9 신설** — v0.1.8 먼저 release 후 v0.1.9 첫 feature. v0.1.8 의 R1/R2 결함은 운영자 자체적 대응 필요 (yaml 수동 보강).

작업 브랜치: `feature/update_path_fixes` (from `origin/v0.1.8`, 분기 완료).

## 4. 사용자 결정 확정 (2026-05-25)

| ID | 결정 | 근거 |
|---|---|---|
| **D1** scope | **(a) v0.1.8 통합** | release 전 test 중 발견된 결함 — release 안 했으므로 v0.1.8 안에서 fix |
| **D2** 분리/통합 | **(a) 통합 — 단일 feature `update_path_fixes`** | D1 의 v0.1.8 통합 정합 + 두 결함 모두 운영자 update path 관련 (의미 연결) |
| **D3** R1 fix | **(a) multi-skill load** — `--skills wh-lint,wh-graphify` | 가장 작은 변경 + ADR 정합 보존 + lint.md spec 무변경. hermes 동작 실측 (multipass) 후 검증 |
| **D4** R2 fix | **(b) yaml.example 자동 sync helper** | 일반화 — 신규 field 추가 시 migration 코드 수정 불요. legacy_migration_cleanup 의 정신 정합 |

## 5. 분석 (R1 + R2 추가 세부)

### R1 fix 방향 검증 (Step 2 design)

**Option (a) multi-skill load 검증 필요**:
- hermes 의 sub-skill spawn 이 `--skills wh-lint,wh-graphify` 로 multi-load 했을 때 wh-lint LLM 의 `<agent_invocation>` 이 실제 wh-graphify spawn 으로 이어지는지
- hermes 의 `delegation.orchestrator_enabled=true` + `max_spawn_depth=1` 정합
- 실측 — multipass wikihub-test 에서 `hermes chat --skills wh-lint,wh-graphify --quiet --yolo --query "/wh-lint"` 호출 + journal 검증

**Option (b) bash inline 검증 필요**:
- lint.md Step 9 가 직접 bash subprocess 로 graphify CLI 호출 → graphify.md spec 의 backend dispatch (profile resolve + endpoint env mapping + 6 case dispatch) 를 lint LLM 의 bash 본문에 inline
- ADR-0036 §D6 single-source ("graphify CLI 호출 책임 = wh-graphify skill 만") 위반 — ADR-0036 §"후속 영향" 또는 supersede 결정 필요
- 단순 — graphify.md Step 2 의 bash block 을 lint.md Step 9 안에 복제

**Option (c) 별도 systemd unit** — scope 큼:
- `_system/systemd/wikihub-graphify.service.template` + `wikihub-graphify.timer.template`
- install.sh 의 stop/start/try-restart 3 위치 + render_systemd_units.py
- lint.md Step 9 의 호출 = `systemctl --user start wikihub-graphify.service` (fire-and-forget)

### R2 fix 방향 검증

**Option (a) Group A migration 재추가**:
- legacy_migration_cleanup (`fd7f0fe`) 의 Group A delete 부분 일부 되돌림 (yolo / skill_prefix migration)
- "v0.1.4+ base 가정" 위반 surface (multipass test 의 v0.1.0 운영자 실제 surface)
- legacy_migration_cleanup 의 design 자체 정정 — `_migrate_agent_schema` 의 보존 책임 더 강화

**Option (b) yaml.example 자동 sync**:
- `_migrate_agent_schema` 가 yaml.example 의 모든 default field 를 ~/wikihub/wikihub.yaml 에 자동 보강
- 운영자 명시 값은 보존 (`if k not in ops:` 패턴)
- 일반화 — 신규 field 추가 시 Group A/B/C migration 코드 수정 없이 자동

**Option (c) 운영자 안내**:
- spec 변경 없음. README + install.sh 의 운영자 안내 추가
- 큰 jump 시 `--force-fresh` 권장 (yaml 보존 안 됨 — 운영자 backup 책임)
- 가장 lean 하나 운영자 부담

## 6. 적용 단계 선언

| 단계 | 수행 여부 | 사유 |
|---|---|---|
| Step 2 Design | 수행 | 두 결함 fix 의 정확성 검증 필요 (특히 R1 의 hermes multi-skill 실측) |
| Step 2 Design Review | 수행 (멀티) | R1 fix 의 ADR 정합 + hermes 동작 / R2 fix 의 운영 안전성 |
| Step 3 Implementation | 수행 | install.sh + lint.md + graphify.md 또는 systemd unit + render |
| Step 4 Code Review | 수행 (멀티) | install.sh + spec 변경 정합 |
| Step 5 Deployment | 수행 | D1 결정 — v0.1.8 hotfix 또는 v0.1.9 신설 |

## 7. 예상 영향 범위 (D3/D4 default = a/b 가정)

| 영역 | 변경 |
|---|---|
| `_system/commands/lint.md` Step 9 | spec 정정 (D3 옵션에 따라 다름) |
| `_system/commands/graphify.md` | (D3=b 시) backend dispatch inline 영향 |
| `_system/systemd/wikihub-graphify.{service,timer}.template` | (D3=c 시 신설) |
| `scripts/_helpers/render_systemd_units.py` | (D3=a 시 lint.service ExecStart skills list 확장 + render 변경) |
| `install.sh` `_migrate_agent_schema` | R2 fix — Group A 재추가 (D4=a) 또는 yaml.example sync (D4=b) |
| `docs/adr/0036-graphify-cli-integration.md` | (D3=b 시 §D6 single-source 갱신) |
| `docs/adr/0008-lint-permission-model.md` | (D3 결정 별 영향) |
| `wikihub.yaml.example` | (필요시) |

추정 라인: D3+D4 default 가정 시 +80~150 / -10~30.

## 8. Methodology 적용

본 절차 적용 — 다중 결함 fix + ADR 영향 가능.

## 9. 사용자 흐름 (이전 feature 와 정합)

| 단계 | 진행 방식 |
|---|---|
| Step 1 plan + D1~D4 결정 | **사용자 검토 필수** |
| Step 2~4 자동 | 사용자 검토 후 |
| Step 5 squash | **사용자 승인 필수** |
