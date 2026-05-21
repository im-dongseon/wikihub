# Analysis & Design — yaml_schema_drift_migration

approved: 2026-05-22

---

## 분석

### 1. 배경 및 목적

2026-05-22 v0.1.6 배포 후 OCI 운영 server `install.sh --update` 직후 surface 된 사건:

- 운영자가 manual 편집한 systemd unit 4건 (`lint.service --model` / `vault@.service --model` / `lint.service TimeoutStartSec` / `vault@.timer OnUnitInactiveSec`) 이 install.sh 의 render 재실행 시 모두 default 로 복원
- 진단: 운영자의 `~/wikihub/wikihub.yaml` 이 v0.1.0 era schema 에 동결 — v0.1.5+ 신설 field (`agent.models`, `agent.timeout_sec`, `operations.pending_alert_age_sec` 등) 부재 + ADR-0035 폐기 field (`bootstrap_allowed` 등) 잔존
- 결과: render 가 부재 field 에 대해 default 600·flag 미주입 으로 unit 출력 → 운영자의 manual edit 손실

ADR-0031 의 "install.sh 의 wikihub.yaml 미관여" 원칙은 *operational value 보호* 가 의도. 그러나 신설 field 의 부재로 인한 unit 의 unsafe default fallback 은 운영 risk — 본 feature 가 install.sh `_migrate_agent_schema` 를 확장해 **신설 field 자동 추가 + legacy field cleanup** 으로 schema drift 보호 layer 신설.

### 2. 현행 진단

`install.sh:751-828` 의 `_migrate_agent_schema` 는 ADR-0033 (skill prefix `wh:` → `wh-`) + ADR-0032 §Note (`oneshot_args --yolo` 누락) 의 2건만 처리. v0.1.5+ 신설 field 의 drift 는 미처리:

| drift 유형 | 처리 여부 | 결과 |
|---|---|---|
| `agent.skill_prefix: "wh:" → "wh-"` | ✓ 처리 (ADR-0033) | OK |
| `agent.oneshot_args` legacy form → F5 schema | ✓ 처리 (ADR-0032) | OK |
| `agent.oneshot_args` 의 `--yolo` 누락 | ✓ 처리 (ADR-0032 §Note 2026-05-19) | OK |
| `agent.timeout_sec` 부재 (v0.1.5 신설) | ✗ 미처리 | `TimeoutStartSec=600sec` fallback |
| `agent.models` 부재 (v0.1.5 신설) | ✗ 미처리 | `--model` flag 미주입 → hermes default fallback |
| `operations.pending_alert_age_sec` 부재 (ADR-0037 신설) | ✗ 미처리 | pending monitor 미발화 |
| `operations.graphify_*` 부재 (v0.1.5 신설) | ✗ 미처리 | toggle/backend default 추정 |
| `vaults[].options.bootstrap_allowed` 잔존 (ADR-0035 폐기) | ✗ 미처리 | schema noise |
| `vaults[].options.credentials_path` 잔존 (ADR-0035 폐기) | ✗ 미처리 | schema noise |
| `vaults[].options.root_folder_id` 잔존 (ADR-0035 폐기) | ✗ 미처리 | schema noise |

### 3. 미결 사항 — 결정

#### M1. 자동 동의 모델 — **(a) 완전 자동 (단, value override 없음)** 으로 단순화

plan.md 의 (a)/(b)/(c) 선택지 + M3 (PTY-safe) 제약 종합 검토 결과:

- (b) "자동 추가 + value 변경은 prompt" 는 PTY-safe 정책 (M3) 와 충돌 — Hermes PTY 환경에서 prompt 가 v0.1.3~v0.1.4 cycle 의 root cause (v0.1.5 §Note 2026-05-20)
- (c) 완전 prompt 는 update path 자동성 깨짐
- **(a)** 완전 자동 — **단, 부재 field 만 추가, value 변경 자동 회피**

즉:
- 신설 field 자동 추가 (안전 default, **부재 시만**)
- legacy field 자동 삭제 (ADR-0035 폐기)
- **값이 이미 존재하면 미터치** — 운영자 의도 (또는 schema drift) 인지 install.sh 가 구분 불가 → 보수적으로 운영 값 보호

운영자가 새 default (예: `sync_interval_sec: 600 → 3600`) 원하면 yaml 직접 편집 후 install.sh 재실행. install.sh 가 자동 변경 안 함.

→ PTY-safe + idempotent + 운영자 trust boundary 정합.

#### M2. ruamel.yaml round-trip — `yaml_writer.atomic_yaml_write` 재사용

`scripts/lib/yaml_writer.py` 의 정본 helper:

```python
from yaml_writer import atomic_yaml_write, load_yaml_rt
data = load_yaml_rt(yaml_path)
# ... mutations ...
atomic_yaml_write(yaml_path, data, round_trip=True)
```

장점:
- 주석 보존 (ADR-0031 §Decision D 정합)
- atomic write (tmpfile + fsync + os.replace)
- stale .tmp cleanup
- ENOSPC 대응

기존 `_migrate_agent_schema` 의 inline ruamel.yaml load/dump 패턴을 helper 호출로 lift.

#### M3. PTY-safe — **prompt 완전 회피**

v0.1.5 의 `_migrate_agent_schema` prompt 제거 결정 일관성 유지. 본 feature 는 prompt 0 — auto-migration only.

운영자가 변경 직후 backup 파일 (`*.wikihub-bak.<utc_iso>`) 로 즉시 rollback 가능 — safety net.

### 4. Field catalog 확정 (정본 = wikihub.yaml.example v0.1.6)

#### 4.1 자동 추가 (안전 default, 부재 시만)

| field | yaml.example default | 부재 시 영향 |
|---|---|---|
| `agent.timeout_sec` | 1200 | 600 fallback → DeepSeek/MiniMax SIGINT risk |
| `agent.models` (블록 자체) | `{wh-lint: deepseek-v4-flash, wh-ingest: deepseek-v4-pro}` | `--model` 미주입 → hermes default fallback |
| `operations.pending_alert_age_sec` | 3600 | pending monitor 미발화 (운영 안전 default) |
| `operations.lint_contradiction_check` | true | toggle 부재 → render fallback 추정 |
| `operations.graphify_enabled` | true | toggle 부재 → backward-compat |
| `operations.graphify_backend` | `""` | auto-detect (현 동작 유지) |
| `operations.graphify_min_version` | `"0.8.0"` | documentation only |
| `operations.graphify_max_version` | `"0.99.99"` | documentation only |

**제외**: `operations.lint_interval_hours` (24 → 3 default 변경) — **값 이미 있으면 미터치** (운영자 trust). 부재 시만 정본 default 3 추가.

**제외**: `vaults[].sync_interval_sec` — 값 이미 있으면 미터치 (운영 yaml 의 600 그대로 보존). 부재 시만 정본 default 3600 추가.

#### 4.2 자동 삭제 (ADR-0035 폐기 field cleanup)

| field | 폐기 ADR | cleanup 안전성 |
|---|---|---|
| `vaults[].options.bootstrap_allowed` | ADR-0035 (2026-05-19) | 안전 — render·sync 미사용 |
| `vaults[].options.credentials_path` | ADR-0035 | 안전 — rclone.conf 단일 인증으로 대체 |
| `vaults[].options.root_folder_id` | ADR-0035 | 안전 — rclone_remote_path 로 대체 |
| `vaults[].options.cursor_path` | ADR-0035 | 안전 — file_map.json diff 로 대체 |

삭제 시 info log: `"ADR-0035 폐기 field cleanup: vaults[<id>].options.<field>"`.

#### 4.3 값 자체 변경 — **완전 회피** (운영자 trust)

| field | 운영자 typical value | 정본 v0.1.6 default | 처리 |
|---|---|---|---|
| `vaults[].sync_interval_sec` | 600 (legacy) | 3600 | **미터치** — 운영자 yaml 직접 편집 후 재 render 권장 |
| `operations.lint_interval_hours` | 24 (legacy) | 3 | **미터치** — 동일 |

→ install.sh 종료 시 info log 로 안내 + drift detect 결과 surface.

### 5. 개정 전/후 비교

#### 5.1 `_migrate_agent_schema` 구조 변경

**Before** (current ADR-0033 + ADR-0032 만):
```
1. yaml load
2. drift detect (skill_prefix / oneshot_args)
3. needs_migrate 0 이면 early return
4. backup
5. python heredoc 으로 mutation
6. atomic write (inline ruamel API)
```

**After** (확장):
```
1. yaml load (yaml_writer.load_yaml_rt)
2. drift detect 3-group:
   (a) ADR-0033/0032 (기존 — skill_prefix / oneshot_args)
   (b) ADR-0035 폐기 field cleanup (vaults[].options.*)
   (c) v0.1.5+ 신설 field 자동 추가 (안전 default, 부재 시만)
3. 어떤 group 도 변경 없으면 early return
4. backup (.wikihub-bak.<utc_iso>)
5. python heredoc 으로 3-group mutation (yaml_writer helper 사용)
6. atomic_yaml_write
7. info log — 변경된 field list
```

#### 5.2 backup 정책 — 변경 없음

`*.wikihub-bak.<utc_iso>` 패턴 유지. 운영자가 의도와 다르면 `cp backup yaml` 1회로 즉시 복원.

#### 5.3 idempotent 보장

- 자동 추가: 값 존재 여부만 체크 → 재실행 시 no-op
- 자동 삭제: field 존재 여부만 체크 → 재실행 시 no-op
- backup: 매 실행마다 생성? → **변경 발생 시만 backup** (기존 정책 유지)

### 6. 연계 룰/스킬 정합성

| 룰/스킬 | 영향 | 검증 |
|---|---|---|
| ADR-0031 (install.sh yaml 미관여) | §Note 추가 — drift fix 예외 lift | 본 feature 의 ADR 갱신 대상 |
| ADR-0032 (skill registration) | §Note 추가 — `_migrate_agent_schema` 확장 범위 | 본 feature 의 ADR 갱신 대상 |
| ADR-0035 (rclone unify) | §Note 선택 — cleanup layer 등록 | 본 feature 의 ADR 갱신 대상 (선택) |
| `/wh-setup` Step 0 (yaml materialize / drift fix) | 영향 없음 — drift fix scope 가 다름 (Step 0 는 `.example` ↔ yaml derived field patching) | 정합 |
| `render_systemd_units.py` | 영향 없음 — 정본 schema 정합 yaml 을 자료원으로 사용 | 정합 |

### 7. Definition of Done

- [ ] `install.sh _migrate_agent_schema` 확장 — §4.1 자동 추가 + §4.2 자동 삭제 + idempotent
- [ ] `yaml_writer.atomic_yaml_write` + `load_yaml_rt` 사용 (inline ruamel API 제거)
- [ ] info log — 변경된 field list 출력 + 운영자 안내 (yaml.example 참조 권장)
- [ ] backup 정책 유지 (`*.wikihub-bak.<utc_iso>`)
- [ ] ADR-0031 §Note + ADR-0032 §Note 갱신
- [ ] `_system/VERSION` 0.1.6 → 0.1.7
- [ ] `features/HISTORY.md` v0.1.7 항목
- [ ] **Step 4 — 서브에이전트 review** — 운영자 yaml mutate destructive risk + idempotent + PTY-safe 검증
- [ ] Step 5 — git push + tag v0.1.7 + latest force-update
- [ ] 운영 server 재현 검증 — install.sh 재실행 → 운영 yaml 자동 보강 + render unit 4건 정합 자동 회복

### 8. 한계 + 후속 backlog

#### 8.1 본 feature 의 한계

- 값 자체 변경 (sync_interval_sec 600 → 3600, lint_interval_hours 24 → 3) 은 미수행 — 운영자 manual edit 필요
- yaml.example 의 신설 field 가 추가될 때 본 함수의 catalog 도 동기 갱신 필요 — 정본 schema 변경의 추가 maintenance cost

#### 8.2 v0.1.8+ 후속

- yaml schema versioning — `schema_version: N` field 도입 + version 별 migration step 분리 (v0.1.x 의 schema drift 처리 시 운영자가 어떤 version 에서 왔는지 명시적)
- value 변경 prompt — `WIKIHUB_INTERACTIVE_MIGRATE=1` opt-in flag 도입 (PTY-safe 보장된 환경에서만)

## 설계

### Karpathy 4원칙 매핑

| 원칙 | 적용 |
|---|---|
| **Think Before Coding** | M1/M2/M3 결정 사유 명시 — PTY-safe 정책 + 운영자 trust boundary + idempotent. plan.md 의 3-갈래 (a/b/c) 검토 후 단순화로 (a) 절충 |
| **Simplicity First** | prompt 0 + value 변경 0 → 코드 분기 최소. 자동 추가/삭제만. inline ruamel.yaml dump 제거 → yaml_writer helper 재사용 |
| **Surgical Changes** | `_migrate_agent_schema` 함수 내부 확장만 — 함수 시그너처 / 호출처 / 다른 install.sh step 영향 없음 |
| **Goal-Driven Execution** | DoD 9 항목 — backup 정책 + idempotent + PTY-safe + ADR §Note 정합 + 운영 server 재현 검증 |

### 자가 검증 절차 (Step 3 implementation 후)

1. 시뮬레이션 — v0.1.0 era yaml fixture 생성 → install.sh `_migrate_agent_schema` 호출 → 결과 yaml 의 신설 field 추가 + legacy field 삭제 확인
2. idempotent 재실행 — 동일 yaml 에 2회 호출 → 두 번째 호출에서 no-op 확인
3. backup 파일 검증 — `.wikihub-bak.<utc_iso>` 생성 + 원본 보존
4. render 정합 — migration 후 yaml 으로 `render_systemd_units.py --render --out tmp/` 호출 → 4개 unit 정합 (lint --model · vault@ --model · TimeoutStartSec=1200 · OnUnitInactiveSec=3600)
5. yaml comment 보존 — operational yaml 의 기존 주석이 migration 후에도 살아남는지 확인 (`yaml_writer.atomic_yaml_write(round_trip=True)` 의 정합 검증)
