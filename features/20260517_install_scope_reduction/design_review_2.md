# Design Review 2 — install_scope_reduction (Spec/Architecture angle)

**Reviewer**: Spec / Architecture / Governance persona
**Date**: 2026-05-18
**Scope**: Step 1 plan + Step 2 analysis_and_design + ADR-0031 (Proposed) + ADR-0023 보강 §4.6

## Summary

전반적으로 결함 #E + #F 의 motivation 과 invariant 정합 (AGENTS.md §1 Dev/Ops Zone) 은 견고하고, ADR 분리 정책 (U4 → ADR-0031 신설 + ADR-0023 보강) 도 결정=1 ADR 원칙에 맞다. 다만 **ADR-0010 의 본문 (line 38·49·80) 이 install.sh 의 yaml cp 책임을 명시**하고 있어 본 feature 가 그 sub-decision 을 *수정/철회* 한다는 사실이 analysis_and_design 와 ADR-0031 의 "Related" 메모로만 처리되었다 — supersede 또는 명시 보강이 필요. 또한 ADR-0031 의 derived-field catalog 가 `mount_path` 를 `local_path` 와 동일하게 강제하는 점 + 첫 호출 yaml writer (Step 0) 와 기존 Step 6 yaml writer (ADR-0022) 의 helper 단일성이 명시되지 않은 점, 그리고 schema migration / multi-vault 미래 시나리오의 위임이 명료해야 함. 4 CRIT/HIGH + 3 MED + 1 LOW 로 정리.

## Findings

### [CRIT-A1] ADR-0010 본문이 명시한 "install.sh = wikihub.yaml.example 복사" sub-decision 의 supersede 처리 부재

**Where**: `docs/adr/0010-operational-tooling-split.md` line 38 ("install.sh 책임 … `wikihub.yaml.example` 복사"), line 49 (lifecycle 단계 2 — `install.sh: wikihub.yaml.example → /opt/wikihub/wikihub.yaml 복사 (이미 있으면 skip — never overwrite)`), line 80 ("7. `wikihub.yaml.example` → `wikihub.yaml` 복사 (신규 모드, 없을 때만)") vs `features/20260517_install_scope_reduction/analysis_and_design.md` §3.1 (Step 5 `_step5_yaml` 삭제) + `docs/adr/0031-yaml-template-materialization.md` §Decision A

**Issue**: ADR-0010 의 §Decision §"도구별 책임 매트릭스" 와 §"wikihub.yaml lifecycle" 두 곳 모두 install.sh 의 yaml.example 복사를 명시한 **결정 본문**이다. 본 feature 는 이 결정을 reverse 하지만:
- ADR-0010 Status 는 그대로 Accepted (변경 없음)
- ADR-0031 은 `Supersedes: 없음` 으로 선언 (ADR-0031 line 5)
- ADR-0030 의 "Note" 패턴 (ADR-0023 에 `## Note (2026-05-17, feature update_mode)` 항목 추가로 scope 명시화) 같은 in-place 갱신도 ADR-0010 에 부재.

이는 ADR governance 의 invariant 위반이다 — `docs/adr/README.md` 의 "결정 변경 정책" §1 ("새 ADR 생성. `Status: Accepted`, `Supersedes: ADR-NNNN` 명시") 또는 §3 ("기존 ADR 의 in-place 보강 — supersede 아님" — ADR-0023 Note 가 그 선례) 둘 중 하나의 explicit handling 필요.

**Recommendation**: 두 방법 중 하나:
1. **(권장)** ADR-0031 에 `Partially supersedes: ADR-0010 §Decision lifecycle step 2 (line 49) + §install.sh 동작 step 7 (line 80)` 추가 + ADR-0010 본문 line 38·49·80 에 ADR-0023 Note 패턴으로 supplementary 섹션 추가 ("## Note (2026-05-17, feature install_scope_reduction): yaml.example 복사 책임은 ADR-0031 에 의해 /wh:setup Step 0 단독으로 이전됨. 본 ADR 의 도구 split 결정 (install.sh + /wh:setup 2 도구) 은 유지, yaml writer 책임만 reassign.").
2. design 문서의 "연계 룰/스킬 정합성 검토" §5 표에 ADR-0010 행을 보강 후보가 아닌 **필수 보강** 로 격상 + Step 3 DoD §7.2 C2 항목 강화 ("ADR-0010 본문에 supplementary Note 추가").

현재 §5 표의 "Step 3 검토" "보강 후보" wording 은 governance critical 한 결정을 deferral 처럼 다룬다 — 격상 필요.

**Effort**: small (ADR-0010 에 5~10 줄 Note 추가 + ADR-0031 의 Supersedes 필드 1 줄 + design §5 표 1 행 수정)

---

### [CRIT-A2] Step 0 yaml writer 와 Step 6 yaml writer 의 helper 단일성 미확정 → "yaml writer 단일" invariant 부분 위반 위험

**Where**: `_system/commands/setup.md` line 188 (Step 6 의 `bootstrap_allowed: true → false atomic write — yaml writer 는 본 명령의 새 책임 (ADR-0009 확장)`) vs `docs/adr/0031-yaml-template-materialization.md` §Decision A step 2 (Step 0 의 ruamel.yaml round-trip + atomic write) + §Consequences "후속 영향" (ADR-0022 의 "raw replace" 가 v0.2.x 후속)

**Issue**: 본 feature 의 핵심 invariant B (analysis_and_design §1.2) 는 "single yaml writer". 그러나 `/wh:setup` 내부에는 두 writer 가 동시 존재하게 된다:
- **Step 0 writer**: ruamel.yaml round-trip + atomic write (`.tmp` + fsync + rename) — derived 5필드 patching
- **Step 6 writer**: 기존 (ADR-0022·setup.md line 188) — `bootstrap_allowed` 환원, "raw replace" + atomic write

ADR-0031 §Consequences 가 "Step 6 도 ruamel.yaml round-trip 으로 마이그레이션 후보 (현재는 raw replace). Step 3 또는 v0.2.x 후속" 라고 deferral 한 점이 문제:
- Step 6 가 raw string replace 면 Step 0 가 ruamel 로 보존한 주석/순서가 Step 6 에서 손실될 수 있다.
- 두 writer 가 atomic write 의 lock 메커니즘을 공유하지 않으면 `.tmp` 파일 충돌 가능.
- analysis_and_design §1.2 의 "single yaml writer" 는 "install.sh 0 / /wh:setup 단독" 이지 "/wh:setup 내부 단일 함수" 는 아니라 invariant 자체는 깨지지 않으나, "yaml writer 단일" 표현이 mis-leading.

ADR-0031 의 §Decision D 마지막 줄 ("`scripts/lib/yaml_materialize.py` 신규 (또는 `scripts/lib/config.py` 확장 — Step 3 결정)") 가 lock 되지 않은 채로 Step 3 진입하면 helper 책임 분할이 ad-hoc 으로 결정될 위험.

**Recommendation**:
1. Step 0 + Step 6 의 yaml writer 가 **동일 helper 함수** 호출하도록 lock — `scripts/lib/yaml_writer.py` 신설 (또는 `config.py` 확장) 에 `atomic_yaml_write(path, data, *, round_trip=True)` 단일 함수. ADR-0031 §Decision D 에 명시 추가.
2. Step 6 의 raw replace → ruamel round-trip 마이그레이션을 v0.2.x deferral 이 아닌 **본 feature 의 sub-task** 로 흡수 (코드 변경 ~10 줄, 주석 보존 일관성 확보).
3. analysis_and_design §1.2 의 "Invariant B (single yaml writer)" 를 "install.sh 0 + /wh:setup 단독 helper" 로 명료화.

**Effort**: medium (helper 1 함수 + Step 6 의 5 줄 수정 + ADR-0031 본문 1 단락)

---

### [HIGH-A1] Derived-field catalog 의 `mount_path` 강제 동일성 — 미래 advanced 운영자 use case 차단 위험

**Where**: `docs/adr/0031-yaml-template-materialization.md` §Decision B catalog 4번째 행 (`vaults[*].options.mount_path` = `<instance.root>/vault/<vault.id>` (= local_path) — 동일성 mismatch 시 patching) + `wikihub.yaml.example` line 18 (local_path) vs line 26 (mount_path — "local_path 와 동일")

**Issue**: 현재 wikihub.yaml.example 의 `local_path` 와 `mount_path` 는 같은 값이지만, 의미론적으로 **별개 필드**다:
- `local_path` = wikihub 가 vault content 를 보는 path
- `mount_path` = rclone 이 마운트하는 mountpoint path

v0.1.0 단일 vault + Path C+ (ADR-0025) 에서 두 값이 일치하는 게 default 일 뿐, advanced 운영자가 다음을 원할 수 있다:
- bind-mount 또는 symlink — `mount_path=/srv/rclone/gdrive`, `local_path=~/wikihub-instance/vault/gdrive` (별도 backup pre-image)
- ramdisk-based mount — `mount_path=/dev/shm/vault/gdrive`
- 멀티 vault 환경에서 mount layout 분리 (v0.2.x)

ADR-0031 §Decision B 가 "동일성 mismatch 시 patching" 으로 강제하면 위 use case 가 silent override 된다 — 운영자가 yaml 에 `mount_path` 를 수동 분리해도 `/wh:setup` 호출 직후 confirm prompt + 동일화. 운영자가 confirm 모드에서 N 선택할 수 있으나, `WIKIHUB_NONINTERACTIVE` 환경 (systemd self-call 등) 에서는 보존만 되고 확정 안 됨 — UX 모호.

또한 ADR-0025 (rclone mount 채택) 본문은 `mount_path = local_path` 를 spec 으로 명시하지 않는다 — `.example` 의 주석 + `wikihub.yaml.example` line 26 의 "local_path 와 동일" 안내만 있을 뿐, **별개 yaml 필드 = 별개 의미** 가 schema 정본.

**Recommendation**:
- Catalog 에서 `mount_path` 행 제거 → maintainer-controlled 로 reclassify (ADR-0031 §Decision B "미관여 필드" 섹션으로 이동).
- 대신 Step 1 schema 검증 (`scripts/lib/config.py`) 에 **soft warn** 추가 — `mount_path != local_path` 시 warn (default 가 아니라는 안내) 하되 fail 안 함.
- 이렇게 하면 v0.2.x 의 advanced mount layout 도 자연 수용 + Path C+ default (동일) 도 유지.
- 또는 Catalog 유지하되 ADR-0031 §Decision B 에 명시 단서 추가: "본 patching 은 `local_path` 와 `mount_path` 가 둘 다 default 패턴 (`<instance.root>/vault/<id>`) 인 경우만 — 운영자가 명시 분리 시 보존" + Step 0 의 detect 로직에 "둘 다 default pattern 매칭" 조건 추가.

**Effort**: small (catalog 1 행 + soft warn 1 함수)

---

### [HIGH-A2] ADR-0031 의 schema version migration 침묵 + v0.2.x multi-vault 확장 시 derived-path catalog 의 분기 책임 미정의

**Where**: `docs/adr/0031-yaml-template-materialization.md` §Consequences "v0.2.x 재검토 트리거" (1 줄) + ADR-0010 §"schema migration (O5 — F4 정본)" line 163-167 (yaml.version v1 → v2 정책)

**Issue**: ADR-0031 의 catalog 와 round-trip 정책은 **현 schema version 1** 만 다룬다. 다음 두 미래 시나리오에 대한 책임 위임이 부재:

1. **Schema version mismatch detect**: `.example` 의 `version: 2` (미래) 와 operational yaml `version: 1` (기존 운영 서버) 일 때 Step 0 동작. ADR-0010 line 163-167 가 `install.sh` 에 이 책임을 위치시켰으나, install.sh 는 본 feature 로 yaml 미관여 → Step 0 가 inherit 해야 함. ADR-0031 침묵.
2. **Multi-vault 의 derived path catalog**: 현재 catalog 는 `vaults[*]` 반복문 가정이라 자연 generalize 되나, 메인테이너가 N 번째 vault 를 ad-hoc 으로 추가 시 (`/wh:setup` 호출 사이에 yaml 직접 편집) Step 0 의 detect 가 "신규 vault 의 derived path 가 default 패턴" 인지 검증해야 함. ADR-0031 catalog 는 detection rule (어떤 default 패턴을 검증할지) 명시 부재.

특히 (1) 은 backward compat 측면 critical — pre-feature 운영 서버 (v0.1.0 yaml 보유) 에 본 feature 적용 시 첫 `/wh:setup` 호출이 가장 큰 drift 를 만든다 (`gws_min_version` 빈 문자열 등). 본 feature 의 V8 검증 시나리오 (analysis_and_design §8) 에 "기존 운영 서버 마이그레이션" 시나리오 부재.

**Recommendation**:
1. ADR-0031 §Decision 에 §E (또는 §Consequences 보강) 추가 — "schema version 정책": "Step 0 는 `.example.version == operational.version` 검증 필수. 불일치 시 fail-fast + 안내 ('install.sh `--version <prev>` 로 rollback 또는 schema migration guide 참조'). v1 → v1 only handling, v2 도입은 별도 ADR".
2. analysis_and_design §8 검증 계획에 V11 추가: "기존 v0.1.0 운영 서버 (yaml 보유, install.sh `_step5_yaml` 이전 산출) 에서 update_mode 후 `/wh:setup` 호출 → Step 0 drift 검출 (`gws_min_version` 빈 문자열, instance.root 정합) → 비대화 모드 fallback 보존 동작".
3. ADR-0031 의 multi-vault catalog 일반화는 v0.2.x 트리거 (현 위치 유지) 로 OK 하되, **detect rule** 의 정본 (Step 0 가 default 패턴을 어떻게 검증할지 — regex 또는 path arithmetic) 만 Step 3 sub-task 로 lock.

**Effort**: small (ADR §E 추가 + 검증 시나리오 1 행)

---

### [MED-A1] 동시 호출 (concurrent /wh:setup) 시 yaml race

**Where**: `docs/adr/0031-yaml-template-materialization.md` §Decision A step 2 (atomic write `.tmp + os.fsync + os.replace`) — race 보호 없음 + setup.md 전체에 lock 메커니즘 부재

**Issue**: ADR-0031 은 atomic write 의 file-level atomicity 는 보장하나, **두 agent 가 동시 /wh:setup 호출** 시 (한 명은 macOS dev box → ssh, 다른 한 명은 OCI 직접) 다음 race 가능:
- A 가 Step 0 read → derived patching 계산 (메모리)
- B 가 Step 0 read → 동시 patching
- A 가 atomic write → wins
- B 가 atomic write → A 의 변경 (예: maintainer 가 직전 편집 한 root_folder_id) 덮어쓰지 않으나, B 의 derived patching 이 A 의 atomic write 직후 maintainer field 를 못 봐서 stale 상태로 write

ADR-0030 의 `_step2_update` 는 `.git/index.lock` 잔존 detect 로 race 회피 (line 911-915 install.sh) 하지만, `/wh:setup` 의 yaml writer 는 lock 메커니즘 부재. v0.1.0 단일 메인테이너 가정에서 surface 안 되나 governance 명료성 측면에서 ADR-0031 에 single-writer-process invariant 명시 필요.

**Recommendation**: ADR-0031 §Decision A 에 "single concurrent `/wh:setup` invariant" 1 단락 추가 — "동시 호출은 본 ADR 범위 밖. 메인테이너가 동시 호출 회피 책임. 운영 서버 내에서 `flock` 기반 mutex 는 v0.2.x deferred". 또는 Step 0 진입에 `flock $WIKIHUB_INSTANCE_ROOT/wikihub.yaml.lock` 추가 (~5 줄).

**Effort**: small (ADR 1 단락 또는 flock helper 5 줄)

---

### [MED-A2] Maintainer-controlled field 목록의 wikihub.yaml.example 라인-바이-라인 정합 — `version` 필드 + `timezone` 누락

**Where**: `docs/adr/0031-yaml-template-materialization.md` §Decision B "미관여 필드" 섹션 vs `wikihub.yaml.example` line 7 (`version: 1`) + line 11 (`instance.timezone: Asia/Seoul`)

**Issue**: ADR-0031 §Decision B 의 "미관여 필드" 카탈로그가 명시한 필드는 `vaults[*].id·enabled·type·sync_interval_sec·options.*` + `operations.*` + `agent.*` 만. 다음 필드가 catalog 누락:
- **`version`** (line 7) — schema version. Step 0 의 patching 대상이 아니나 명시 부재 시 운영자/리뷰어가 "Step 0 가 version 도 만질 수 있나?" 추측 가능. CRIT-A2 의 schema migration 책임과 연결.
- **`instance.timezone`** (line 11) — 운영자 단독. `instance.root` 와 같은 계층에 있어 catalog 에서 "instance.*" 전체 위임 같은 sweeping rule 이 없으면 verification 시 누락 위험.

Catalog 의 "미관여" 가 완전 (exhaustive) 인지 minimal example 인지 ADR-0031 본문에 명시되지 않음.

**Recommendation**: ADR-0031 §Decision B "미관여 필드" 의 위 두 필드 추가 + "본 목록은 `wikihub.yaml.example` (v0.1.0 schema v1) 의 모든 maintainer field 의 완전 catalog. 신규 필드 추가 시 본 ADR 보강 의무" 명시. 또는 카탈로그 정책을 invert — "Step 0 patching 필드 5개 외 모든 필드 는 maintainer-controlled" — implicit catalog 로 단순화.

**Effort**: small (ADR 본문 2~3 줄)

---

### [MED-A3] ADR-0009 본문 보강 책임 deferral — /wh:setup 의 yaml writer 책임 확장이 ADR-0009 본문 부재

**Where**: `docs/adr/0009-setup-responsibility.md` §Decision 3대 책임 (환경 검증 / systemd unit 동기화 / 보고) — yaml writer 책임 없음. vs `docs/adr/0031-yaml-template-materialization.md` §Consequences "후속 영향" — "ADR-0009 본문에 yaml writer 책임이 명시 추가될 후보 (supersede 아닌 보강)" + analysis_and_design §5 표 "Step 3 결정"

**Issue**: ADR-0022 가 이미 Step 6 의 `bootstrap_allowed` 환원으로 `/wh:setup` 에 1차 yaml writer 책임을 부여한 시점에 ADR-0009 본문 갱신이 이미 누락된 상태. 본 feature 의 Step 0 도입은 이 책임을 **template materialization 전체** 로 widen. ADR-0009 의 §Decision §"1. 환경 검증 (read-only)" 문구가 Step 0 와 모순 ("read-only" 가 거짓).

본 feature 가 ADR-0009 본문 보강 (Note 또는 §Decision 4 추가) 을 명시적으로 책임지지 않으면 ADR-0009 의 본문이 잘못된 spec 으로 남는다.

**Recommendation**: analysis_and_design §3.3 ADR 표에 새 행 추가:
```
| `docs/adr/0009-setup-responsibility.md` | 보강 (supersede 아님) | §Decision 에 §4 "yaml writer (Step 0 + Step 6)" 추가 — ADR-0022 + ADR-0031 의 책임이 본 ADR 본문에 흡수. §1 "read-only" 문구 정정. |
```
또는 §3.3 의 ADR-0023 보강과 ADR-0031 신설 사이에 ADR-0009 Note 추가를 Step 3 의 explicit task 로 lock. 현재 analysis_and_design §5 표의 "보강 후보" wording 은 governance critical 한 결정을 deferral 처리 — 격상 필요 (CRIT-A1 과 같은 패턴).

**Effort**: small (ADR-0009 에 5~10 줄 Note + design §3.3 표 1 행)

---

### [LOW-A1] backlog.md #F entry 가 ADR-0031 의 5필드 catalog 와 phrasing mismatch

**Where**: `features/backlog.md` line 17 (#F entry — "운영용 값 (instance.root override, vault paths, gws_min_version 등) 메인테이너 수동 편집 의존") vs ADR-0031 §Decision B 5필드

**Issue**: #F entry 가 "instance.root override, vault paths, gws_min_version 등" 으로 3 항목 (paths 가 묶음) 만 명시. ADR-0031 의 5필드 catalog (instance.root + local_path + mount_path + credentials_path + gws_min_version) 가 #F 보다 surface. governance 추적 측면에서 #F closure 시 backlog.md 본문에 "✅ closed by `install_scope_reduction` (ADR-0031 의 5필드 catalog 로 lock)" 명시 필요. 본 feature 의 Step 5 deferred 라 closure 자체가 deferred 이나, design 단계에서 backlog cross-ref 정합 명시 부재.

**Recommendation**: analysis_and_design §3.3 ADR 표 또는 §7.2 정합 DoD 에 "backlog.md #E + #F entry 의 closure 표기 (✅ closed by …)" 행 추가. Step 5 deferred 라도 Step 3 구현 직후 backlog 본문 갱신 의무 명시 — update_mode 의 #A·#B·#C·#D closure 표기 패턴 정합.

**Effort**: trivial (backlog 2 행 갱신)

---

### [LOW-A2] setup.md "install.sh와의 관계" 표의 신규 행 정합성 — design 의 §3.2 ↔ 실제 표 컬럼 의미

**Where**: `_system/commands/setup.md` line 235-247 (install.sh와의 관계 표) vs analysis_and_design §3.2 표 (Step 0 신규 + 표 갱신 spec)

**Issue**: design §3.2 가 "install.sh 컬럼 `✓` 삭제, `/wh:setup` 컬럼 `✓ (Step 0)` 추가" 라고 명시했으나, 현재 setup.md 표 컬럼 의미는 "1회 bootstrap + 정본 update" (install.sh) vs "yaml 변경 시 반복" (/wh:setup) — Step 0 는 "첫 호출 시 generate + 이후 호출 시 drift sync" 로 두 컬럼 의미와 정확히 일치하지 않는다. 표 헤더 자체의 조정이 필요할 수도 (예: `/wh:setup` 헤더에 "(첫 호출 시 yaml generate 포함)" 추가).

**Recommendation**: Step 3 진입 전 표 갱신 spec 의 정확한 cell 텍스트를 design §3.2 또는 §4.5 에 lock — 단순 `✓` 갱신이 아니라 cell 안의 wording 까지 (예: "✓ (Step 0 가 generate 또는 drift sync)").

**Effort**: trivial (design §3.2 spec wording 1 줄)

---

## Backlog candidates (out of feat scope)

- **Schema v2 migration policy ADR** (HIGH-A2 의 위임) — `version: 1 → 2` 시 Step 0 의 fail-fast / 자동 마이그레이션 / 운영자 안내 policy. v0.2.x.
- **flock 기반 /wh:setup mutex** (MED-A1 의 위임) — multi-process invocation race protection. v0.2.x 또는 multi-maintainer 도입 시점.
- **Multi-vault derived-path catalog generalization** (HIGH-A2 의 위임) — vault 별 분기 + ad-hoc 신규 vault detection rule. v0.2.x F6 (`wiki_query`) 또는 별도 feature.
- **Step 6 ruamel.yaml round-trip 마이그레이션** (CRIT-A2 의 위임) — 본 review 는 본 feature 흡수 권장하나 deferred 결정 시 backlog 항목.
- **mount_path != local_path advanced 운영자 use case 검증** (HIGH-A1 의 위임) — bind-mount / ramdisk / multi-vault 시 schema 정합.

---

## Overall recommendation

- [x] **Approve with major changes**
- [ ] Approve as-is
- [ ] Approve with minor changes
- [ ] Request redesign

CRIT-A1 (ADR-0010 supersede/Note 처리) + CRIT-A2 (Step 0/Step 6 writer 통합) 는 본 feature 가 명시적으로 closure 해야 하는 governance / invariant 책임이라 Step 3 진입 전 lock 필수. HIGH-A1·A2 도 Step 0 의 catalog spec 의 future-proof 측면에서 ADR-0031 본문 보강 권장. MED·LOW 는 surgical 정합이라 Step 3 sub-task 흡수 가능. 본 review 의 4 CRIT/HIGH 만 반영하면 Step 3 진입 OK.

## Notes for synthesis

본 review 의 **CRIT-A1 (ADR-0010 supersede)** 와 **CRIT-A2 (Step 0+Step 6 writer 단일 helper)** 가 핵심 — design_review_1 (다른 페르소나) 의 finding 과 겹치면 우선순위 최상위. HIGH-A1 (mount_path) 는 운영 사용자 use case 측면 finding 이라 다른 리뷰어가 못 잡았을 가능성 — 합의 시 ADR-0031 §Decision B revise 권장.
