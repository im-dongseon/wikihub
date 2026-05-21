# Plan — yaml_schema_drift_migration

- **시작일**: 2026-05-22 KST
- **버전 목표**: v0.1.6 → v0.1.7 (patch 승격)
- **트리거**: 2026-05-22 OCI 운영 server `install.sh --update` 직후 운영 unit 4건 manual edit 손실 사건 (lint·ingest `--model` 제거 + `TimeoutStartSec` 600 복원 + `OnUnitInactiveSec` 600 복원). 진단 — 운영 yaml schema drift (v0.1.5+ 신설 field 부재).
- **관련**: ADR-0031 (install.sh yaml 미관여) + ADR-0030 (update workflow) + ADR-0032 (skill registration + `_migrate_agent_schema` 확장)

---

## 1. 작업 분류

**운영 + 안정성** — 운영자의 wikihub.yaml schema drift 자동 detect + migration. 데이터 손실 방지·재발 차단.

- 기능 추가 ✓ (`_migrate_agent_schema` 확장 — 새 field 자동 추가)
- 리팩토링 ✗
- 버그 ✓ (drift 미처리로 인한 데이터 손실 — manual edit overwrite)
- 문서 ✓ (ADR-0031 §Note·ADR-0032 §Note·setup.md 안내)
- 운영 ✓

## 2. 적용 단계 선언

| Step | 수행 | 사유 |
|---|---|---|
| Step 1 Plan | ✓ | 본 문서 |
| Step 2 Analysis & Design | ✓ | drift detection 정책 + auto-migration vs prompt 결정 + ruamel.yaml round-trip + idempotent guard 설계 |
| Step 3 Implementation | ✓ | install.sh `_migrate_agent_schema` 확장 + yaml.example schema reference + ADR §Note |
| Step 4 Review | **권장 수행** | 운영자 yaml mutate — destructive risk. 외부 인터페이스 (스키마 의미론) 의 lift. 멀티 reviewer (Claude + 서브에이전트) |
| Step 5 Deployment | ✓ | install.sh 변경 → 운영 server `install.sh --update` 흐름 (운영 yaml 즉시 fix 효과) |

## 3. 예상 영향 범위

### 정본 변경

| 파일 | 변경 |
|---|---|
| `install.sh` `_migrate_agent_schema` | 신설 field detection + 추가 (idempotent + ruamel.yaml round-trip) |
| `install.sh` `_step8_guide` | drift migration 안내 추가 (어떤 field 추가됐는지 출력) |
| `wikihub.yaml.example` | schema reference 코멘트 보강 (v0.1.5+ 신설 field 의 운영자 manual sync 권장 시점) |
| `docs/adr/0031-install-yaml-policy.md` | §Note — install.sh 의 schema migration 역할 lift (기존 "yaml 미관여" 원칙의 예외 — drift fix 한정) |
| `docs/adr/0032-hermes-skill-registration-policy.md` | §Note — `_migrate_agent_schema` 확장 범위 갱신 |

### 부속

| 파일 | 변경 |
|---|---|
| `_system/VERSION` | 0.1.6 → 0.1.7 |
| `features/HISTORY.md` | v0.1.7 항목 |

## 4. 대상 drift field — auto-migration 범위 결정

### 4.1 자동 추가 (안전 — schema reference 값으로)

| field | yaml.example default | 자동 추가 안전? | 근거 |
|---|---|---|---|
| `agent.timeout_sec` | 1200 | ✓ | 부재 시 render default 600 → DeepSeek/MiniMax SIGINT risk. 1200 추가가 운영 안전. |
| `agent.models` 블록 자체 | `{wh-lint, wh-ingest}` | ✓ | 부재 시 `--model` 미주입 → hermes default fallback (의도 미일치). yaml.example default 가 운영 정본 align (v0.1.6). |
| `operations.pending_alert_age_sec` | 3600 | ✓ | ADR-0037 신설. 부재 시 ops-alert 미발화 — 운영 안전 기본값. |
| `operations.graphify_enabled` | true | ✓ | v0.1.5 toggle. 부재 시 render default 추정 — true 가 backward-compat (graphify chain 동작 유지). |
| `operations.graphify_backend` | `""` | ✓ | v0.1.5 신설. 부재 시 graphify auto-detect (현 동작 유지) — `""` 명시가 동일. |
| `operations.lint_contradiction_check` | true | ✓ | v0.1.5 toggle. 부재 시 true 가 backward-compat. |
| `operations.lint_interval_hours` | 3 | ⚠ prompt | v0.1.5 에서 24 → 3 변경. 운영자 의도 (시간 cost 통제) 영향 — 자동 추가 시 timer 빈도 8배 증가. **운영자 prompt 권장**. |
| `operations.graphify_min_version` / `max_version` | 0.8.0 / 0.99.99 | ✓ | documentation only (실 enforce 는 v0.2.x). 자동 추가 안전. |

### 4.2 자동 변경 회피 — 운영자 prompt 만 (값 변경은 운영자 trust boundary)

| field | 운영 vs 정본 | 처리 |
|---|---|---|
| `vaults[].sync_interval_sec` (600 → 3600) | 운영자 의도 변경 영향 — 변동 detect 지연 trade-off | 운영자 prompt — "v0.1.6 default 3600 권장. 변경하시겠습니까?" Yes/No |
| `vaults[].options.false_delete_threshold` | ADR-0035 §ζ2 신설 — false-delete 가드. 부재 시 render default 0.3 사용 (변경 없음) | 자동 추가 (안전 default) |

### 4.3 자동 삭제 (legacy field cleanup)

| field | 폐기 시점 | 처리 |
|---|---|---|
| `vaults[].options.bootstrap_allowed` | ADR-0035 (2026-05-19) | 자동 삭제 + info log ("ADR-0035 폐기 field cleanup") |
| `vaults[].options.credentials_path` | ADR-0035 | 자동 삭제 |
| `vaults[].options.root_folder_id` | ADR-0035 | 자동 삭제 |
| `vaults[].options.cursor_path` | ADR-0035 | 자동 삭제 (state 측면에선 별도 `rm cursor.json` 운영자 책임) |

## 5. 미결 사항

### M1. auto-migration 의 운영자 동의 모델

선택지:

**(a) 완전 자동** — 모든 새 field 자동 추가, 운영자 prompt 없음. install.sh 가 silent migration.
- 장점: 마찰 0, install.sh 의 idempotent 흐름 유지
- 단점: 운영자 의도 침범 — 특히 `lint_interval_hours` 처럼 cost/빈도 영향 field

**(b) 자동 추가 + value 변경은 prompt** — §4.1 의 ✓ 항목 자동, ⚠ prompt 항목은 운영자 confirm 후 적용
- 장점: 안전 default 자동, 의도 영향 field 만 prompt
- 단점: noninteractive 모드 (`WIKIHUB_NONINTERACTIVE=1`) 에서 prompt 처리 정책 필요

**(c) 완전 prompt** — 모든 drift 변경에 운영자 confirm
- 장점: 운영자 의도 완전 보호
- 단점: install.sh 의 자동 update 흐름 깨짐 — 운영자 입력 필요

→ Step 2 design 에서 결정. 잠정 권고 **(b)**.

### M2. ruamel.yaml round-trip 처리

설계 시점에 결정 — drift fix 시 주석 보존 + atomic write (`yaml_writer.atomic_yaml_write`) 사용. ADR-0031 의 yaml writer helper 와 동일 패턴.

### M3. `_migrate_agent_schema` 의 stdin/tty 처리

이전 v0.1.5 의 `_migrate_agent_schema` 가 Hermes PTY 환경에서 prompt 무한 cycle issue → 모든 prompt 제거 (v0.1.5 결정). 새로 prompt 도입 시 동일 risk — `(b)` 의 `lint_interval_hours` prompt 가 PTY 환경에서 fail loop risk.

→ Step 2 에서 noninteractive 모드 (`WIKIHUB_NONINTERACTIVE=1`) 와 PTY detect 정책 명시. 잠정: noninteractive + PTY 환경에선 conservative default (운영 값 유지) + info log.

## 6. ADR cascade 영향

| ADR | 영향 |
|---|---|
| ADR-0031 (install.sh yaml 미관여) | §Note — drift fix 예외 lift. "신설 field 자동 추가 + legacy field cleanup 은 install.sh 책임. 값 변경은 운영자 prompt." |
| ADR-0032 (skill registration) | §Note — `_migrate_agent_schema` 확장 범위 (기존 `wh:` → `wh-` + `--yolo` 외에 신설 field 자동 추가) |
| ADR-0030 (update workflow) | 영향 없음 — drift fix 가 update path 내부에 통합 |
| ADR-0033 (skill prefix lock) | 영향 없음 |
| ADR-0034 (data-first layout) | 영향 없음 |
| ADR-0035 (rclone unify) | §Note (선택) — legacy field cleanup (`bootstrap_allowed` 등) 의 install.sh 자동 처리 layer 등록 |
| ADR-0036 (graphify) | 영향 없음 |
| ADR-0037 (alert pipeline) | 영향 없음 |

## 7. Definition of Done

- [ ] install.sh `_migrate_agent_schema` 확장 — §4.1 의 ✓ field 자동 추가 + §4.3 의 legacy field 자동 삭제 + §4.1 의 ⚠ field 운영자 prompt (PTY-safe)
- [ ] yaml.example schema reference 코멘트 보강 — 신설 field 의 manual sync 시점 안내
- [ ] ADR-0031 §Note + ADR-0032 §Note 갱신
- [ ] _system/VERSION 0.1.6 → 0.1.7
- [ ] features/HISTORY.md v0.1.7 항목
- [ ] Step 4 — 멀티 reviewer (Claude + 서브에이전트) 검토 — 운영자 yaml mutate destructive risk 검증
- [ ] Step 5 — git push + tag v0.1.7 + latest 재설정 + 운영 server `install.sh --update`
- [ ] 운영 server 재현 검증 — install.sh 실행 후 운영 yaml 의 누락 field 자동 추가 + render unit 4건 정합 확인

## 8. 메소드론 적용 여부

본 절차 (Step 1~5) 적용. 운영자 yaml mutate + ADR Note 갱신 + 멀티 reviewer 검토 — trivial 아님.

## 9. 다음 단계

`"바로 진행"` 또는 `"확정할게요"` 응답 후 Step 2 (analysis_and_design.md) 시작. analysis 에서 핵심 결정:

- M1 (자동 동의 모델) — (a)/(b)/(c) 결정
- M2 (ruamel.yaml round-trip 패턴 spec)
- M3 (PTY-safe prompt 정책 — v0.1.5 `_migrate_agent_schema` prompt 제거 결정과의 정합)
- §4.1·§4.2·§4.3 의 final field catalog 확정 (yaml.example 정본과 cross-check)
- `_migrate_agent_schema` 의 sub-skill (helper) 분리 vs inline 결정 (이전 `_patch_hermes_external_dirs` 패턴 참조)
