# ADR-0031: wikihub.yaml template materialization 정책

- **Status**: Accepted
- **Date**: 2026-05-17 (v1) / 2026-05-18 (v2 — design review 반영 + Step 4 code review 통과 후 Accepted 승격)
- **Feature**: features/20260517_install_scope_reduction
- **Supersedes**: 없음
- **Partially supersedes**: ADR-0010 §"도구별 책임 매트릭스" line 38 (`install.sh ... wikihub.yaml.example 복사`) + §"wikihub.yaml lifecycle" 단계 2 (line 49) + §"install.sh 의 동작" step 7 (line 80) — yaml writer 책임만 reassign, 도구 split 결정은 유지
- **Superseded by**: 없음
- **Related**: ADR-0009 (setup 책임 — yaml writer 확장 supplement), ADR-0010 (운영 도구 책임 분할 — 부분 supplement), ADR-0022 (첫 ingest 진입점 — Step 6 yaml writer 정합), ADR-0023 (install distribution — clone scope 보강과 짝), ADR-0030 (update workflow orchestration — sparse-checkout 영속화)

## Context

F4 `install_runtime` 와 `update_mode` 까지 v0.1.0 의 install + update 흐름이 정본화됐지만 **wikihub.yaml 의 시작 책임** 이 install.sh + `/wh:setup` 둘에 분산:

1. `install.sh _step5_yaml` (install.sh:524-538) — `cp wikihub.yaml.example → wikihub.yaml` raw 복사. 운영용 값 patching 0.
2. `/wh:setup` Step 6 (setup.md:264) — `wikihub.yaml` 의 `bootstrap_allowed: true → false` atomic write. 이미 yaml writer.

두 곳이 같은 yaml 을 만지면 (1) race · 이중 정본 위험, (2) `$WIKIHUB_INSTANCE_ROOT` env override 와 yaml `instance.root` mismatch 문제, (3) `operations.gws_min_version` 같은 install-time fact 의 미충전 → `/wh:setup` Step 1 검증 (setup.md:32) 매번 skip.

또한 ADR-0010 ("install.sh = OS bootstrap / `/wh:setup` = yaml 정합") 경계가 모호 — install.sh 가 yaml 을 만지면서도 schema 검증은 `/wh:setup` 책임이라 책임 split.

## Considered Options

### Materialization writer

- **(α) install.sh 단독**: 현재 `_step5_yaml` + 값 patching 추가. install.sh 가 yaml-aware 가 됨.
- **(β) `/wh:setup` 단독**: install.sh 의 yaml 개입 0. `/wh:setup` Step 0 신규 가 template 으로부터 materialize. (본 ADR 채택안)
- **(γ) sidecar meta**: install.sh 가 `.install_meta` 작성 (env override, gws version 등), `/wh:setup` 이 meta + .example 결합.

### Patching 필드 범위 (U2)

- (a) instance.root 파생 4개만 (`instance.root`·`vaults[*].local_path`·`vaults[*].options.mount_path`·`vaults[*].options.credentials_path`)
- (b) (a) + `operations.gws_min_version`
- (c) (b) + `operations.rclone_min_version`·`rclone_max_version`
- (d) (c) + `agent.binary` 자동 detect

### Drift fix 정책 (U3)

- (a) Strong sync — 매 호출 install-derived 필드 강제 재patching (메인테이너 편집 덮어쓰기)
- (b) First-only — 첫 generate 시만 patching, 이후 호출은 영구 보존
- (c) Confirm — drift 검출 시 사용자 confirm prompt, 비대화 모드 fallback = 보존 + 보고

### Round-trip engine (U6)

- (a) PyYAML safe_load/safe_dump — 의존성 0, 주석 손실
- (b) string replace (placeholder `{{var}}`) — .example 이 invalid yaml
- (c) ruamel.yaml round-trip — 주석 보존, 작은 pure-Python dep 추가

> 옵션 상세 비교(장단점 표 등)는 [features/20260517_install_scope_reduction/analysis_and_design.md §6](../../features/20260517_install_scope_reduction/analysis_and_design.md) 참조.

## Decision

**채택**:
- Writer: **(β) `/wh:setup` 단독** — install.sh 의 yaml 개입 0건.
- Patching scope: **(b) 변형 — 4 필드** (v2: mount_path 제외, 자세한 사유는 §Decision B).
- Drift fix: **(c) 변형 — confirm + 비대화 fallback=exit 1** (v2: HIGH-S3 반영).
- Round-trip engine: **(c) ruamel.yaml**, exact pin (v2: MED-S3 반영).

### Decision A — Materialization writer 단일성 + atomic write 정합

`/wh:setup` 이 yaml 의 시작·끝 책임을 단독 보유. install.sh 는 `_step5_yaml` 함수 자체를 삭제 (yaml 한 글자도 안 만짐).

흐름:
1. install.sh 완료 시점에 `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml` 은 **존재하지 않음**. `.example` 은 `$WIKIHUB_HOME/wikihub.yaml.example` 에 read-only 상주.
2. `/wh:setup` 첫 호출이 Step 0 에서 yaml materialize:
   - read `$WIKIHUB_HOME/wikihub.yaml.example` (ruamel.yaml round-trip load)
   - derived 값 patching (Decision B catalog 참조)
   - atomic write `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml` (자세한 atomicity spec 은 아래)
3. 보고 — "wikihub.yaml 생성. maintainer field (vault id/root_folder_id/enabled/fatal_webhook_url 등) 편집 후 재호출".
4. maintainer 가 yaml 편집 → `/wh:setup --enable` 재호출 → Step 0 drift check (없으면 no-op) → Step 1 schema 검증 → Step 2~6 진행.

#### Atomic write 정합 (v2 신규 — MED-S1 반영)

`scripts/lib/yaml_writer.py` 의 단일 helper `atomic_yaml_write(path, data, *, round_trip=True)` 가 다음 invariant 보장:

| 결함 모드 | 동작 |
|---|---|
| `.tmp` 위치 | `Path(target).parent / f".{target.name}.tmp.{os.getpid()}"` — **target 의 same-directory + PID suffix**. cross-FS `EXDEV` 회피 + concurrent 호출 시 충돌 회피 |
| `os.fsync(.tmp)` 실패 (`ENOSPC` 등) | exception raise + `.tmp` 즉시 unlink. operational yaml 미변경 |
| SIGTERM mid-write | `.tmp` 만 잔존 (PID suffix 라 stale 식별 가능). 다음 helper 호출 진입 시 자신의 PID 와 다른 `.tmp.*` 발견 시 unlink (정합 cleanup) |
| `os.replace` (`.tmp → target`) | atomic rename 보장 — POSIX guarantee |

본 helper 는 Step 0 **와 Step 6** (`bootstrap_allowed: true → false`) **둘 다 호출** (§Decision D — Step 6 흡수).

#### Single concurrent writer invariant (v2 신규 — MED-A1 반영)

본 ADR 의 atomicity 는 file-level. **동시 `/wh:setup` 호출 race 보호는 본 ADR 범위 밖**:
- v0.1.0 가정: 단일 메인테이너 1인 운영 — 동시 호출 회피 책임은 메인테이너.
- v0.2.x: `flock $WIKIHUB_INSTANCE_ROOT/wikihub.yaml.lock` 기반 mutex 도입 검토 (별도 ADR).
- 본 helper 는 PID suffix `.tmp` 로 atomic rename 자체는 안전 — race 시 마지막 writer 가 wins.

### Decision B — Step 0 patching scope (4필드, v2 revision)

> **v2 변경**: `mount_path` 제거 (HIGH-A1 반영). `gws_min_version` 의 source 변경 (MED-S2 반영).

| 필드 | source | patching 조건 |
|---|---|---|
| `instance.root` | `$WIKIHUB_INSTANCE_ROOT` env (install.sh export 또는 `/wh:setup` 호출 env) | env 값과 yaml 값 불일치 시 |
| `vaults[*].local_path` | `<instance.root>/vault/<vault.id>` | 파생값과 yaml 값 불일치 시 |
| `vaults[*].options.credentials_path` | `<instance.root>/.credentials/sa_<vault.id>.json` | 파생값과 yaml 값 불일치 시 |
| `operations.gws_min_version` | **`$WIKIHUB_HOME/_system/INSTALLED_VERSIONS.json` 의 `gws` 필드** (install.sh `_install_gws` 가 작성) — file 부재 시 `gws --version` stdout fallback | yaml 값이 빈 문자열 또는 install gws 보다 낮을 때 |

**v2 변경 사유**:
- **`mount_path` 제거 (HIGH-A1)**: 의미론적으로 `local_path` 와 별개 필드 — advanced 운영자가 bind-mount, ramdisk, multi-vault layout 분리 등으로 명시 분리할 use case 존재. ADR-0025 본문도 `mount_path = local_path` 를 spec 으로 명시하지 않음 (`.example` 의 주석 안내일 뿐). Step 0 가 강제 동일화하면 silent override. 따라서 `mount_path` 는 **maintainer-controlled 로 reclassify**. `scripts/lib/config.py` Step 1 schema 검증에 **soft warn** 추가 (`mount_path != local_path` 시 default 패턴 아님 안내, fail 안 함).
- **`gws_min_version` source 변경 (MED-S2)**: 기존 v1 의 `gws --version` stdout 파싱은 gws 출력 형식 변경 시 brittle. install.sh `_install_gws` 가 install-time 에 `_system/INSTALLED_VERSIONS.json` 작성 (예: `{"gws": "0.22.5", "rclone": "1.65.0", "uv": "0.4.0"}`) → Step 0 가 file read. file 부재 (pre-feature 운영 서버 마이그레이션 등) 시 fallback 으로 `gws --version` stdout 파싱 — graceful degradation.

**미관여 필드 (Step 0 절대 미관여)** — v2: inverted catalog 로 명시 (MED-A2 반영):

> 본 catalog 의 4필드 **외 모든 yaml 필드** 는 maintainer-controlled. `wikihub.yaml.example` (v0.1.0 schema v1) 의 신규 필드 추가 시 본 ADR 보강 의무 (default = maintainer-controlled, install-derived 명시 추가 case 만 catalog 갱신).

명시 예시 (운영자 단독 편집):
- **schema · root level**: `version`, `instance.timezone`
- **vault**: `vaults[*].id`·`enabled`·`type`·`sync_interval_sec`·`options.root_folder_id`·`options.exclude_shared_with_me`·`options.max_file_size_mb`·`options.bootstrap_allowed`·`options.mount_path` (v2 신규)·`options.rclone_remote_name`·`options.rclone_rc_port`
- **operations**: `lint_interval_hours`·`max_concurrent_vaults`·`retry.*`·`disk.*`·`fatal_webhook_url`·`fatal_webhook_timeout_sec`·`instance_label`·`rclone_min_version`·`rclone_max_version`·`vfs_cache_max_size`·`vfs_refresh_mode`
- **agent**: `agent.*` 전체

**rclone 버전 미포함 이유**: `.example` 에 이미 reasonable default 가 있고 install.sh Step 4.5 `_step45_rclone` 가 별도 검증. /wh:setup 이 yaml 의 rclone 버전 필드를 덮어쓸 이유 약함.

**agent.binary 미포함 이유**: 메인테이너가 hermes·codex·gemini 중 선택. `/wh:setup` 호출자 agent 와 yaml `agent.type` 이 의도적으로 다를 수 있음 (테스트 등).

### Decision C — Drift fix 정책 (v2 — 비대화 fallback 강화)

> **v2 변경 (HIGH-S3 반영)**: 비대화 분기를 "보존 + 보고 + exit 0" → "보존 + 보고 + **exit 1**" 로 강화. install-derived 필드의 silent mismatch 가 운영 진입하면 vault-fetch 가 잘못된 path 로 file_map.json 작성 → cursor 누적 위치 분리 → 무한 re-bootstrap 위험 (file_map 불일치).

매 `/wh:setup` 호출 시 Step 0 분기:

#### Case A — `wikihub.yaml` 부재

→ materialize (Decision A 흐름). 모든 derived 필드 patching, 보고, exit 0.

#### Case B — `wikihub.yaml` 존재

1. yaml load (ruamel.yaml round-trip 모드).
2. Decision B catalog 4필드 각각 drift 검출.
3. drift 있는 필드 0건 → Step 0 no-op (Step 1 진입).
4. drift 1건 이상:
   - **대화 모드** (`/dev/tty` 있음 + `WIKIHUB_NONINTERACTIVE` 미설정 + `SKIP_CONFIRM` 미설정):
     - 각 drift 필드 보고 (현 값 vs 예상값, drift 의 source 분류 — "install-time env 와 매번 mismatch" vs "derived 만 mismatch").
     - prompt (LOW-S2 반영 — default 보수): "**install-time env 값으로 yaml 을 덮어씁니다. 메인테이너 hand-edit 가 있으면 N 선택**. [y/N] (default N)"
     - `Y` → atomic re-write (helper).
     - `N` → 보존 + "재호출 시 다시 prompt" 안내 + exit 0 (의도된 보존).
   - **비대화 모드** (`WIKIHUB_NONINTERACTIVE=1` 또는 `/dev/tty` 부재):
     - drift 보고 (stderr) + 보존.
     - **exit 1** (v2 — silent mismatch 회피). systemd OnFailure → ops-alert 트리거.
     - 운영자가 SSH 로 직접 `/wh:setup` 호출 (대화 모드) 시 confirm prompt → 정합 동기화.

### Decision D — Round-trip engine + helper 단일성 (v2 — Step 6 흡수)

> **v2 변경 (CRIT-A2 반영)**: Step 0 + Step 6 의 yaml writer 를 동일 helper 로 통합. Step 6 의 raw string replace → ruamel round-trip 마이그레이션을 본 feature 의 sub-task 로 흡수 (v0.2.x deferral 아님).

**라이브러리**: `ruamel.yaml ==0.18.6` (exact pin — MED-S3 반영).

**`scripts/requirements.txt` 신규 라인**:
```
ruamel.yaml==0.18.6 \
    --hash=sha256:<TBD>  # uv pip compile --generate-hashes 출력으로 lock
```

**helper**: `scripts/lib/yaml_writer.py` 신규 — 단일 함수 `atomic_yaml_write(path, data, *, round_trip=True)` 가:
- ruamel.yaml `YAML(typ='rt')` 인스턴스로 load · dump (round-trip — 주석·key 순서·indent 보존).
- atomic write protocol (Decision A 의 atomicity spec).
- PID-suffix `.tmp` cleanup.

**Step 0** (본 ADR Decision A): `atomic_yaml_write(target, materialized_data)` 호출 — derived 4필드 patching 결과 write.

**Step 6** (ADR-0022): `bootstrap_allowed: true → false` 도 동일 helper 호출. 기존 raw replace 코드 (~10줄, setup.md line 264 정본) 가 본 feature 의 Step 3 구현 시 helper 호출로 교체 — 주석 보존 일관성 확보 + atomic lock 단일화.

**이유**:
- operational `wikihub.yaml` 은 메인테이너가 편집할 파일 — `.example` 의 풍부한 주석이 보존되면 편집 UX ↑.
- Step 0 가 ruamel 로 보존한 주석/순서가 Step 6 의 raw replace 에서 손실되면 invariant B (single yaml writer 의 정합성) 부분 위반.
- ruamel.yaml 은 pure Python, 작은 의존성, 활성 maintain.
- PyYAML 은 `scripts/lib/config.py` 등 read-only safe_load 모듈은 그대로 활용 — 두 라이브러리 공존, write 만 ruamel 단일화.

### Decision E — Schema version 정책 (v2 신규 — HIGH-A2 반영)

> Step 0 의 schema version 검증 책임. ADR-0010 §"schema migration (O5)" line 163-167 의 install.sh 책임을 **Step 0 로 이관** (install.sh 가 본 feature 로 yaml 미관여 → Step 0 가 inherit).

#### 검증 시점 — Step 0 진입 직후

```python
# pseudo-code
example_data = yaml_load("$WIKIHUB_HOME/wikihub.yaml.example")
example_version = example_data["version"]   # 정본 schema version

if target.exists():
    operational_data = yaml_load(target)
    operational_version = operational_data["version"]
    if operational_version != example_version:
        fail_fast(
            reason=f"schema version mismatch: operational v{operational_version} vs example v{example_version}",
            remediation="install.sh --version <prev-tag> 로 rollback 또는 schema migration guide 참조",
        )
```

#### 정책

- **v1 → v1 only handling**. operational yaml 과 example 의 `version` 필드 불일치 시 **fail-fast** (exit 2, Step 1 진입 안 함, ops-alert 1회 트리거).
- v2 도입 (schema 변경) 시 **별도 ADR** 발의 — migration 자동화 / 운영자 수기 guide / dual-version 운영 정책 lock.
- v0.1.0 → v0.1.x 는 동일 schema v1 가정 — patch level 의 yaml 추가 키는 Step 0 의 catalog 갱신으로 흡수.

**이유**: backward compat 측면 critical — pre-feature v0.1.0 운영 서버 (yaml v1 보유) 에 본 feature 적용 시 첫 `/wh:setup` 의 Step 0 가 example v1 와 정합 검증 → 통과. 만약 미래 example 이 v2 로 변경되면 운영 yaml 의 silent migration 회피.

## Consequences

### 긍정
- **Yaml writer 단일성**: race · 이중 정본 위험 0. ADR-0010 의 책임 경계 명료화 (install.sh = OS bootstrap, `/wh:setup` = yaml 정합). v2: Step 0 + Step 6 helper 통합으로 `/wh:setup` 내부 단일성도 보장.
- **Install-time fact 자동 동기화**: `gws_min_version` 같은 필드가 첫 `/wh:setup` 에서 채워짐 → setup.md Step 1 검증 (gws min version 비교) 활성화. v2: sidecar file 채택으로 stdout 파싱 brittleness 회피.
- **`WIKIHUB_INSTANCE_ROOT` env override 정합**: env 와 yaml mismatch 자동 해소.
- **메인테이너 편집 보존**: drift fix 정책이 confirm 기반 — install-derived 필드만 명확히 격리 + v2: 비대화 모드 fallback 이 exit 1 로 silent mismatch 차단.
- **주석 보존 UX**: ruamel.yaml round-trip 으로 `.example` 의 풍부한 주석이 operational yaml 에 살아있음. v2: Step 6 도 동일 helper 사용 — 주석 보존 일관성.
- **Advanced 운영자 use case 수용** (v2): `mount_path` 가 maintainer-controlled — bind-mount / ramdisk / multi-vault layout 분리 자연 수용.
- **Schema version 검증** (v2): pre-feature 운영 서버의 silent migration 회피.

### 부정/제약
- **`/wh:setup` 첫 호출 의무**: install.sh 직후엔 yaml 부재 → 메인테이너가 반드시 `/wh:setup` 호출해야 yaml 생성. install.sh `_step8_guide` 안내문이 첫 단계로 명시 (mitigation). v2: 비대화 모드 fallback exit 1 로 silent mismatch 차단 (HIGH-S3).
- **외부 dep 추가**: `ruamel.yaml==0.18.6` (exact pin, hash verify). `scripts/requirements.txt` 1줄 추가, install.sh Step 3 venv 가 `uv pip install --require-hashes -r` 로 supply chain 일관 (mitigation: ruamel.yaml 은 PyPA 잘 알려진 패키지, 활성 maintain, ADR-0028 의 hash verify 패턴 정합).
- **Step 6 코드 마이그레이션** (v2): 기존 ~10 줄 raw replace 가 helper 호출로 교체 — 본 feature 의 Step 3 sub-task. 회귀 방지 검증 필수.
- **drift confirm 의 비대화 fallback 의 exit 1 영향** (v2): systemd 자동 호출 사이클에서 drift 검출 시 매번 ops-alert 발화 가능 — ADR-0024 의 dedup 정책 (`failed_count` + `alerted_at`) 으로 alarm fatigue 회피, 단 운영자가 drift 진단 + `/wh:setup` 호출 까지는 매 사이클 fail 누적.
- **concurrent /wh:setup race** (v2): 본 ADR 범위 밖. v0.2.x flock 도입까지 메인테이너 책임.
- **mount_path soft warn 의 UX 비용** (v2): config.py Step 1 검증 가 `mount_path != local_path` 시 warn — default 운영자에게 noise 가능 (advanced use case 가 아니라면 warn 무시 가이드 명시 필요).

### 후속 영향
- **ADR-0009** (setup 책임) — v2: yaml writer 책임 확장 (Step 0 + Step 6) 을 본 ADR 정합으로 lock. ADR-0009 본문에 Note 추가 (2026-05-18, supplement — supersede 아님).
- **ADR-0010** (운영 도구 책임 분할) — v2: install.sh 의 yaml.example 복사 책임이 본 ADR 으로 reassign — `Partially supersedes` 명시. ADR-0010 본문에 Note 추가.
- **ADR-0022** (첫 ingest 진입점) — v2: Step 6 의 yaml writer 가 본 ADR 의 helper 사용 — supplement (raw replace → ruamel migrate). ADR-0022 본문 갱신 없음 (helper 호출 detail 은 setup.md 의 Step 6 spec 에 반영).
- **ADR-0023** (install distribution) — 본 ADR 과 짝으로 보강 (clone scope) 동시 진행. install.sh `_step5_yaml` 삭제는 ADR-0023 의 "clean install pattern" 와 충돌 없음 (yaml 은 instance dir 산출물이라 wipe 대상 아님).
- **ADR-0030** (update workflow) — v2: sparse-checkout 영속화 + rollback 시 governance 파일 비복구 의도 lock. ADR-0030 §부정/제약 에 Note 추가.
- **v0.2.x 재검토 트리거**: 
  - multi-vault·multi-instance 운영 시 derived path catalog 가 vault 별로 분기 필요. 현 catalog 는 단일 vault 가정 (v0.1.0 정합).
  - schema v2 도입 시 별도 ADR (Decision E 명시).
  - concurrent `/wh:setup` flock mutex 도입 시 본 ADR 의 §Decision A "Single concurrent writer invariant" 갱신.

---

## v2 변경 이력 (2026-05-18)

design review (`design_review_1.md` SRE/Systems + `design_review_2.md` Spec/Architecture) 의 CRIT 2건 + HIGH 5건 + MED 6건 반영.

| 변경 | 반영 finding |
|---|---|
| `Partially supersedes: ADR-0010 §lifecycle step 2 + §step 7` 명시 | CRIT-A1 |
| §Decision D — Step 6 yaml writer 가 동일 helper 호출, raw replace → ruamel migrate 본 feature 흡수 | CRIT-A2 |
| §Decision A — atomic write 의 PID-suffix `.tmp` + same-directory + ENOSPC/EXDEV/SIGTERM recovery + single-writer invariant | MED-S1, MED-A1 |
| §Decision B catalog — `mount_path` 제거 (4필드) + `gws_min_version` source 변경 (sidecar file + fallback) | HIGH-A1, MED-S2 |
| §Decision B "미관여 필드" — inverted catalog 표현 + `version`·`timezone` 명시 | MED-A2 |
| §Decision C Case B — 비대화 fallback exit 0 → exit 1 + confirm default Y → N | HIGH-S3, LOW-S2 |
| §Decision D — `ruamel.yaml==0.18.6` exact pin + `--require-hashes` | MED-S3 |
| §Decision E (신규) — schema version 검증 정책 + V11 검증 시나리오 trigger | HIGH-A2 |
| §Consequences "후속 영향" — ADR-0009·0010·0022·0030 supplement 명시 | CRIT-A1, MED-A3, HIGH-S1 |

원본 review 파일 보존: `features/20260517_install_scope_reduction/design_review_1.md` + `design_review_2.md`.

## Note (2026-05-18, feature `hermes_adapter` F5)

본 ADR §Decision B catalog (derived 4필드 — `instance.root`, `vaults[*].local_path`, `vaults[*].rclone_remote_name`, `vaults[*].options.mount_path`) 의 **agent.* 미관여 정책 유지** — F5 의 schema lift 는 본 catalog 외부에 별도 책임:

### F5 의 agent schema 1회성 lift — `_migrate_agent_schema()` 신규

기존 운영자 wikihub.yaml 에 `agent.skill_prefix: "wh:"` 또는 `agent.oneshot_args: ["-z"]` 잔존 시:

- ADR-0031 §Decision B catalog (drift fix 대상 4필드) 에 `agent.*` 미포함 → `/wh-setup` Step 0 의 drift fix 가 본 필드 미관여.
- **F5 의 `_step6_agent_skill _migrate_agent_schema()` 가 1회성 schema lift 책임** — install.sh 진입 시 1회 detect + 명시 confirm (또는 NONINTERACTIVE 자동 동의) + backup + atomic patch.

### 책임 분리

| 책임 | source-of-truth | trigger |
|---|---|---|
| `/wh-setup` Step 0 | yaml writer (materialize + 4필드 drift fix) | 첫 호출 또는 매 호출 |
| F5 `_migrate_agent_schema` | agent.* schema lift (1회성) | install.sh `_step6_agent_skill` 진입 |

### idempotency

`_migrate_agent_schema` 는 idempotent — 2번째 호출 시 이미 `wh-` + `{skill}` placeholder 형식이면 no-op. 운영자가 patch 후 yaml 을 다시 `wh:` 로 손편집한 경우는 marker comment (ADR-0032 §sub-3) 패턴 적용 — 운영자 의도 명시 보호.

Status 변경 없음. §Decision B catalog 의 의도 (agent.* 미관여) 보존.

## Note (2026-05-19, feature `dir_layout_refactor`) — §Decision 갱신 (ADR-0034)

ADR-0034 data-first layout invert 후 본 ADR §Decision B catalog 의 default 값 변경:

### `instance.root` default 변경

- **Before**: `~/wikihub-instance` (이전 `WIKIHUB_INSTANCE_ROOT` 의미)
- **After**: `~/wikihub` (ADR-0034 의 `WIKIHUB_HOME` = 운영 자산 dir)

### derived 4필드 catalog 값 변경

| 필드 | After (ADR-0034 정합) |
|---|---|
| `instance.root` | `$WIKIHUB_HOME` (default: `~/wikihub`) |
| `vaults[*].local_path` | `$WIKIHUB_HOME/vault/<vault_id>` |
| `vaults[*].options.mount_path` | `$WIKIHUB_HOME/vault/<vault_id>` |
| `vaults[*].options.credentials_path` | `~/.credentials/wikihub/sa_<vault_id>.json` (ADR-0029 §Decision 갱신 정합 — 외부 격리) |

### schema version

`version: 1` 유지 (ADR-0031 §Decision E 정합 — key 변경 없음, 값 의미 변경. schema version bump 불요).

### `/wh-setup` Step 0 의 single-writer 정책 보존

`/wh-setup` 이 `$WIKIHUB_HOME/wikihub.yaml` atomic write 단독 책임 (ADR-0031 §Decision A). install.sh yaml 미관여 정책 ADR-0034 후에도 그대로.

Status 변경 없음. default 값 정합.
