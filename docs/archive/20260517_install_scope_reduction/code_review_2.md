# Code Review 2 — install_scope_reduction (Spec/Contract alignment)

**Reviewer**: Spec/Contract/Governance alignment persona
**Date**: 2026-05-18
**Scope**: Step 3 implementation (commit `882a882`) — ADR-0009·0010·0023·0030·0031 ↔ implementation cross-check + DoD (C1~C11 / R1~R5 / F1~F7) coverage + V1~V16 readiness

## Summary

Step 3 implementation의 핵심 contract — ADR-0031 §Decision A·B·C·D·E, ADR-0023 Note clone scope, ADR-0030 Note sparse-checkout 영속화 + rollback semantics, ADR-0009 §4 helper 단일성, ADR-0010 yaml.example reassign — 은 모두 정본 spec 과 word-for-word 정합한다. `WIKIHUB_SPARSE_PATHS` 6필드, `--no-cone`, `--no-checkout` sequence, `_apply_sparse_checkout` 호출 위치 (reset --hard 직후), `_rollback_if_failed`의 sparse 호출 + journal log, `atomic_yaml_write`의 PID-suffix + same-directory + fsync + os.replace, 4필드 catalog (mount_path 제외), schema version v1 fail-fast, 비대화 exit 1 모두 spec 그대로. 다만 (1) docs/adr/README.md 인덱스가 stale (ADR-0031 row "5-필드", ADR-0030 미등재), (2) ADR-0030 `## Notes`의 "v0.2.x ADR-0031 신설 검토" 문구가 실제 채택된 ADR-0031 (yaml materialization) 와 의미 충돌, (3) `wikihub.yaml.example` line 2 stale 주석, (4) requirements.txt hash deferral 이 backlog 미반영, (5) Decision B 의 `os.path.expanduser` materialization 시점 미명시 — 정본 drift 5건. CRIT/HIGH 결함 0건, MED 4건, LOW 3건. **승인 권고 (minor changes)**.

## Findings

### [MED-CR2-1] docs/adr/README.md 인덱스가 ADR-0031 v2 갱신 누락

**Where**: `docs/adr/README.md:87`

**Issue**: ADR-0031 인덱스 행이 `wikihub.yaml template materialization — /wh:setup Step 0 단독 writer + **5-필드 patching** + confirm drift fix + ruamel.yaml round-trip` 으로 기재. 실제 ADR-0031 v2 §Decision B 는 **4 필드** (mount_path 제외, HIGH-A1 반영). 인덱스 = ADR 메타데이터의 single source of truth 인데 본문과 mismatch. 또한:
- Date 컬럼이 `2026-05-17` 단일 — v2 (2026-05-18) 명시 없음 (ADR-0015·ADR-0024 처럼 `/ 2026-05-18` 형식 권장).
- ADR-0030 (`update workflow orchestration`) 자체가 인덱스 전체에서 누락 — `update_mode` feature archive 시점 (`a2bacb9`) 의 sweep miss. 본 feature 범위는 아니지만 본 feature 가 ADR-0030 §부정/제약 Note 를 추가하므로 cross-ref 정합 측면에서 surface.

**Recommendation**: ADR-0031 행을 `4-필드 patching` 으로 정정, Date `2026-05-17 / 2026-05-18 (v2 — design review)` 형식. ADR-0030 행 신규 append (별도 Backlog 으로 처리 가능 — 본 feature 의 scope 가 아닌 점은 명시).

**Effort**: 5분 (단일 라인 patch)

---

### [MED-CR2-2] ADR-0030 `## Notes` 의 "v0.2.x ADR-0031 신설 검토" 가 실제 ADR-0031 와 의미 충돌

**Where**: `docs/adr/0030-update-workflow-orchestration.md:90`

**Issue**: ADR-0030 의 마지막 `## Notes` 항목이 다음과 같이 명시:
> 본 ADR 의 4 sub-decision 분할 검토 (R3 Notes): "**ref resolution chain (sub-4) 만 별도 ADR-0031 로 분리 가능**" 제안. v0.1.0 에서는 1 ADR 유지 (동일 관심사 — update workflow safety). v0.2.x release engineering 확장 시 (e.g. tag signature verification) **ADR-0031 신설 검토**.

ADR-0031 은 본 feature 가 이미 발의 (yaml template materialization) — Notes 가 가리키는 "ADR-0031 (ref resolution chain 분리)" 와 ADR ID 가 동일하지만 결정 영역이 전혀 다름. 운영자/리뷰어가 ADR-0030 Notes 만 읽으면 "ADR-0031 = ref resolution" 으로 오해 가능. 결정 = 1 ADR 원칙 (AGENTS.md §3 Step 2) 의 추적성 측면에서 noise.

**Recommendation**: ADR-0030 의 `## Notes` 마지막 줄을 다음 중 하나로 교체:
- "v0.2.x release engineering 확장 시 (e.g. tag signature verification) **별도 ADR 신설 검토** (ADR-0031 은 yaml template materialization 으로 이미 발의됨 — 2026-05-18, `install_scope_reduction`)."
- 또는 `## Notes` 의 해당 문장 삭제 + 위 cross-ref 1줄만 보존.

본 feature 의 ADR-0030 §부정/제약 Note 추가와 함께 처리 권장 (이미 ADR-0030 본문에 install_scope_reduction Note 가 들어가 있어 한 ADR 의 동시 보강).

**Effort**: 5분 (단일 문장 patch)

---

### [MED-CR2-3] `wikihub.yaml.example` line 2 stale 주석 — install.sh 가 복사한다는 표현이 ADR-0031 와 정면 충돌

**Where**: `wikihub.yaml.example:2`

**Issue**: `wikihub.yaml.example` 첫 헤더가 다음과 같이 명시:
```
# WikiHub 운영 정본 — wikihub.yaml 의 example.
# install.sh 가 `~/wikihub-instance/wikihub.yaml` 에 복사 (없을 때만).
```

본 feature 의 핵심 invariant: install.sh 는 yaml 한 글자도 안 만짐 (ADR-0031 §Decision A). example 파일의 주석이 install.sh 복사 책임을 명시 → ADR-0031 §Decision A 와 정면 충돌. 또한 main flow `_step5_yaml` 삭제 + `_step5_instance_dirs` rename 이 본 feature 의 surgical change 핵심인데, 그 출발점 파일이 옛 책임을 광고.

analysis_and_design.md §3.4 "비영향 (의도적 제외)" 에 `wikihub.yaml.example 본문 — schema 무변경` 명시 — schema 무변경은 맞지만 주석 변경은 schema 변경이 아니다. surgical change 측면에서 본 라인 교체는 본 feature scope 내.

**Recommendation**: line 2-3 을 다음으로 교체:
```
# `/wh:setup` Step 0 가 `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml` 에 materialize (ADR-0031).
# install.sh 는 yaml 미관여 — 본 파일은 read-only template.
# 메인테이너가 /wh:setup 후 vault 정의·credentials_path·bootstrap_allowed 등 채운 후 /wh:setup --enable 호출.
```

**Effort**: 5분

---

### [MED-CR2-4] `scripts/requirements.txt` hash hardening 후속이 backlog 에 미반영 — traceability 단절

**Where**: `scripts/requirements.txt:10-16`, `features/backlog.md`

**Issue**: requirements.txt 의 ruamel.yaml 주석:
```python
# 본 line 의 SHA256 hash + 다른 dep 들의 hash 전환 (uv pip --require-hashes 일관) 은
# Step 4 ~ Step 5 사이의 supply-chain hardening 후속 작업으로 lock — `features/backlog.md`
# 의 별도 항목으로 추적.
```

backlog.md 를 grep 해도 본 항목 entry 부재 — "별도 항목으로 추적" 약속이 미이행. ADR-0031 §Consequences "부정/제약" 의 `install.sh Step 3 venv 가 uv pip install --require-hashes -r 로 supply chain 일관` 언급도 backlog 항목 없이 dangling. ADR-0028 의 hash verify (gws · rclone · uv) 패턴과 일관성 보장 측면에서 trace 필수.

**Recommendation**: `features/backlog.md` 의 `## update_mode 산출` 또는 새 `## install_scope_reduction 산출` 섹션 추가 후 항목:
```markdown
| ID | 영역 | 항목 | 해결 방향 |
|---|---|---|---|
| ISR-1 | supply-chain | ruamel.yaml==0.18.6 의 SHA256 hash 미기재 + 다른 dep 의 hash 전환 미수행 — `uv pip install --require-hashes` 일관성 미달 | `uv pip compile --generate-hashes` 출력 + ADR-0028 패턴 정합 |
```

**Effort**: 10분 (backlog 1행 추가)

---

### [LOW-CR2-1] ADR-0031 §Decision B "Patching 조건" 의 `os.path.expanduser` 적용 시점 미명시

**Where**: `docs/adr/0031-yaml-template-materialization.md:96-102`, `_system/commands/setup.md:55-70`

**Issue**: ADR-0031 §Decision B 의 catalog 가 "yaml 값과 env / install-fact 비교" 만 명시. 비교 대상이 `~/wikihub-instance/...` 같은 tilde literal 인지 expanded path 인지 미정. install.sh 의 `WIKIHUB_INSTANCE_ROOT` 는 `_abs_path` 가 tilde expand 후 set (install.sh:74-75) — env 는 expanded. yaml `instance.root` 는 `~/wikihub-instance` 형식으로 round-trip 보존 가능. 단순 string compare 시 항상 drift 검출 가능 (false positive). Step 0 의 confirm prompt 가 매 호출 발화 → 운영자 fatigue.

**Recommendation**: ADR-0031 §Decision B 표에 "비교 정합: 양쪽 `os.path.expanduser` 적용 후 비교" 1줄 추가, setup.md Step 0.2 의 derived 비교 단계에도 명시. Step 4 V<N> 의 V6 (drift 없음 케이스) 통과 가능 여부 확인 필요.

**Effort**: 15분 (ADR + setup.md 2 곳 patch)

---

### [LOW-CR2-2] Step 0.1 schema version 검증의 exit code 가 setup.md 와 ADR-0031 사이 불일치

**Where**: `_system/commands/setup.md:35-49`, `docs/adr/0031-yaml-template-materialization.md:174-201`

**Issue**:
- ADR-0031 §Decision E: `fail-fast (**exit 2**, Step 1 진입 안 함, ops-alert 1회 트리거)`
- setup.md Step 0.1: pseudo-code 만 `fail_fast(reason=..., remediation=...)` — exit code 명시 없음 ("v1 → v1 만 지원" 만 명시).
- setup.md "실패 처리" 표 (line 295-305) 는 `wikihub.yaml 스키마 위반 → exit 1` 만 명시. schema **version** 위반 (Decision E) 행 부재.

운영자가 setup.md 만 읽으면 schema version mismatch 시 exit code 가 1 인지 2 인지 모름. 또한 ops-alert 트리거 여부도 setup.md 미명시.

**Recommendation**: setup.md "실패 처리" 표에 새 행:
```
| Step 0 schema version mismatch (ADR-0031 §Decision E) | exit 2 + ops-alert 1회 트리거 (systemd OnFailure 정합) |
```
+ Step 0.1 pseudo-code 의 `fail_fast` 옆에 `# exit 2` 주석.

**Effort**: 10분

---

### [LOW-CR2-3] LICENSE 표현이 ADR-0023 Note 와 design review LOW-S1 의도 사이 ambiguous

**Where**: `docs/adr/0023-install-script-distribution-curl-pipe.md:103`

**Issue**: ADR-0023 Note 의 LICENSE 행:
```
| `LICENSE` | legal · convention — MIT 의 redistribution scope 가 운영 타깃엔 strict 적용 안 되지만 OSS 관례로 포함 (LOW-S1 design review) |
```

LOW-S1 design review 의 의도 (analysis_and_design.md §10 "미반영 finding") 는 "LICENSE 는 ADR-0023 보강 §"Clone scope" 의 1줄 표현 문제 — Step 3 의 ADR-0023 본문 작성 시 wording 정합". 즉 LOW-S1 은 "표현 약화" 인데 본 행은 "redistribution scope 가 strict 적용 안 됨" + "OSS 관례" 둘 다 명시 — convention 측면에선 부합하나 legal 측면에서 운영 타깃이 "redistribute" 행위인지 의미 모호 (server install ≠ redistribution). MIT 의 attribution 의무는 distribution 시점 — single-instance install 은 distribution 아님.

**Recommendation**: 두 가지 옵션 — (a) 표현 단순화: `| LICENSE | OSS 관례 — repo 정본의 license 명시 (legal 의무 없음, install 은 redistribution 아님) |` (b) 또는 행 자체 제거 — 6필드 → 5필드 로 줄임 (analysis_and_design.md §6 U1 의 (a) 결정으로 회귀). 본 feature scope 가 LICENSE 보존 결정 (U1=(b)) 이라 (a) 권장. 단 ADR-0023 Note 변경은 본 review 결과 반영하는 follow-up commit 으로 처리.

**Effort**: 5분

---

## DoD coverage matrix (analysis_and_design.md §7)

### 기능 DoD (F1~F7) — 검증 대기

| ID | 항목 | 상태 | 근거 |
|---|---|---|---|
| F1 | `$WIKIHUB_HOME` 에 governance 파일 0건 | **Step 4 V1~V3 대기** | `WIKIHUB_SPARSE_PATHS=(_system scripts install.sh wikihub.yaml.example README.md LICENSE)` (install.sh:290) — 6필드 lock |
| F2 | install.sh 직후 wikihub.yaml 부재 | **Step 4 V1 대기** | `_step5_yaml` 삭제 + `_step5_instance_dirs` (install.sh:656-679) — yaml 미관여 검증 가능 |
| F3 | `/wh:setup` 첫 호출 yaml generate | **Step 4 V4 대기** | setup.md Step 0.2 Case A 정의됨 + `yaml_writer.atomic_yaml_write` helper 존재 |
| F4 | `WIKIHUB_INSTANCE_ROOT=/custom` 정합 | **Step 4 V5 대기** | Step 0 derived 4 필드 catalog 정의됨 |
| F5 | drift 검출 동작 | **Step 4 V6·V7·V9 대기** | setup.md Step 0.2 Case B 정의 + 비대화 exit 1 |
| F6 | maintainer field 보존 | **Step 4 V8 대기** | Step 0.3 미관여 필드 catalog 명시 |
| F7 | pre-feature 풀-clone update 자동 sparse 전환 | **Step 4 V3·V11 대기** | `_step2_update` 가 `_apply_sparse_checkout` 호출 (install.sh:989) |

### 정합 DoD (C1~C11)

| ID | 항목 | 상태 |
|---|---|---|
| C1 | AGENTS.md §1 Dev/Ops Zone 정합 | ✅ done (sparse-checkout 6 path) |
| C2 | ADR-0010 경계 명료화 + Note 추가 | ✅ done (`docs/adr/0010-operational-tooling-split.md:9-13` Note + ADR-0031 `Partially supersedes` 정합) |
| C3 | ADR-0023 보강 "Clone scope" 항목 | ✅ done (ADR-0023:90-138, supersede 아님) |
| C4 | ADR-0031 신설 + Status Accepted | ⏳ **partial** — Status `Proposed` 그대로 (Step 4 + V<N> 후 Accepted 가 본 feature 의 contract). docs/adr/README.md 인덱스도 Proposed |
| C5 | setup.md Step 0 + 표 갱신 | ✅ done (setup.md:30-103 + 317-331) |
| C6 | config.py:156 remediation 갱신 | ✅ done (config.py:171-179 — `/wh:setup` 호출 의무 + ADR-0031 명시) |
| C7 | ADR-0009 §4 Note 추가 | ✅ done (ADR-0009:9-17) |
| C8 | ADR-0030 §부정/제약 Note 추가 | ✅ done (ADR-0030:79) |
| C9 | yaml_writer.py 신규 + Step 6 helper migrate | ✅ done (`scripts/lib/yaml_writer.py` + setup.md:263-266) |
| C10 | config.py mount_path soft warn | ✅ done (config.py:109-120) |
| C11 | backlog.md #E·#F closure | ✅ done (backlog.md:16-17, `✅ closed by install_scope_reduction (2026-05-18)`) |

**C4 deferred**: ADR-0031 의 Accepted 승격은 Step 4 + V<N> 통과 후. 본 review 가 그 gate. 본 review 의 결함 (MED 4건, LOW 3건) 이 모두 minor 라 Accepted 진입 가능.

### 회귀 방지 DoD (R1~R5)

| ID | 항목 | 상태 |
|---|---|---|
| R1 | update_mode `_step2_update` 호환 + sparse-checkout 위치 lock | ✅ done (install.sh:989 — `git reset --hard` 직후 `_apply_sparse_checkout`; install.sh:1055 — `_rollback_if_failed` 본문 sparse 호출) |
| R2 | `/wh:setup` Step 1~6 동작 무변경 + Step 6 helper migrate | ✅ done (setup.md:263-266 — `atomic_yaml_write` 호출, 의미론 무변경) |
| R3 | ingest·lint·query 동작 무변경 | ✅ done (영향 없음 — yaml schema 무변경) |
| R4 | Step 0 schema version v1→v1 통과 | **Step 4 V11 대기** (setup.md Step 0.1 pseudo-code 정의됨) |
| R5 | 비대화 drift fallback exit 1 → ops-alert | **Step 4 V9 대기** (setup.md Step 0.2 Case B 비대화 분기 정의됨) |

---

## V1~V16 readiness

### 통과 가능 — 즉시 실행 가능 (V1·V2·V4·V5·V6·V8·V10·V12·V13·V14·V15·V16)

| V | 사전 조건 검증 |
|---|---|
| V1 | wikihub-test-clean 신규 VM 가용 시 즉시. `WIKIHUB_SPARSE_PATHS` 6필드 listing 검증 가능 |
| V2 | V1 통과 후 동일 VM 에서 재호출 — `_step2_update` 분기 진입 |
| V4 | install.sh 직후 `/wh:setup` 호출 — Step 0 Case A 실행. ruamel.yaml round-trip 동작 검증 가능 |
| V5 | `WIKIHUB_INSTANCE_ROOT=/custom bash install.sh` — `_abs_path` 가 tilde expand + Step 0 patching 검증 |
| V6 | V4 직후 재호출 — Step 0 Case B drift=0 분기 (단 LOW-CR2-1 의 `expanduser` 정합 필요) |
| V8 | yaml `vaults[0].options.root_folder_id` 수동 편집 후 재호출 — Step 0.3 미관여 catalog 검증 |
| V10 | ruamel round-trip 의 주석 보존 — `.example` 의 v9 신규 주석 (라인 25, 27, 28) 이 operational yaml 에 살아남는지 |
| V12 | `mount_path` 다른 값 명시 — config.py:109-120 soft warn 검증 (테스트 미보유 — `tests/test_config.py` 에 regression test 추가 권장) |
| V13 | Step 6 bootstrap_allowed 환원 → 주석 보존 검증 — Step 0 + Step 6 helper 단일성 surface |
| V14 | update 도중 인위 fail trigger — `_rollback_if_failed` 의 sparse 재호출 + journal 로그 검증 |
| V15 | `_write_installed_versions_sidecar` 작성 검증 — install.sh:607-626 atomic write 패턴 검증 |
| V16 | install.sh 직후 systemd timer enable 실수 — `_step8_guide` warn 안내 검증 (install.sh:767-768) |

### 검증 환경 제약 — 별도 setup 필요 (V3·V7·V9·V11)

| V | 제약 |
|---|---|
| V3 | wikihub-test VM 의 pre-feature 풀-clone 상태 보존 필수. 본 feature 코드를 받기 전 backup 또는 별도 VM (e.g., wikihub-test-pre-sparse) 필요. `_step2_update` 의 `_apply_sparse_checkout` 호출이 풀-clone 의 governance 파일 자동 삭제하는지 검증 |
| V7 | 대화 모드 prompt + default N 검증 — TTY attach 필요 |
| V9 | systemd OnFailure → ops-alert 발화 검증 — 운영 환경 시뮬레이션 (vault@.service install + manual fire) |
| V11 | pre-feature v0.1.0 yaml 보유 운영 서버 — wikihub-test 의 현 상태 (full clone + 기존 wikihub.yaml) 캡처. 단 본 worktree 에는 wikihub.yaml 없음 (instance_root 외부) — 별도 VM 또는 dev box scp |

**V11 권장 절차**: (1) main branch checkout + install.sh 호출 → 운영 yaml 생성. (2) feature/install_scope_reduction checkout + `/wh:setup` 호출 → Step 0.1 schema v1==v1 통과 + Step 0.2 Case B drift 검출 ([3] gws_min_version 빈 문자열 → patching candidate). (3) 비대화 mode 시 exit 1 확인.

### V11 의 추가 risk — `gws_min_version` 의 비교 정합

`gws_min_version` 의 drift 비교 시 yaml 값 (현재 ".example" 의 `""`) vs `INSTALLED_VERSIONS.json["gws"]` (예: `"0.22.5"`) — 빈 문자열 vs non-empty 항상 drift. 비대화 모드면 **매 호출 exit 1 → ops-alert 1회** → ADR-0024 dedup 으로 alarm fatigue 회피 되지만 운영 진단 부하 surface. analysis_and_design.md §8 V11 에 명시되어 있음 (`(비대화) exit 1`) — 의도된 동작.

---

## Backlog candidates (out of feat scope)

- **ISR-1 (MED-CR2-4)**: requirements.txt 의 `--require-hashes` 전환 + ruamel.yaml SHA256 추가. supply-chain hardening 후속.
- **ISR-2**: docs/adr/README.md 의 ADR-0030 등재 누락 (본 feature 범위는 아니지만 update_mode archive 시점의 sweep miss).
- **ISR-3**: `tests/test_config.py` 에 `mount_path != local_path` soft warn regression test 추가 — C10 항목이 코드 들어갔지만 테스트 미보유.
- **ISR-4**: Step 0 의 `os.path.expanduser` 비교 정합 (LOW-CR2-1) — V6 fail false-positive 회피.

---

## Overall recommendation

**☑ Approve with minor changes**

이유:
- 핵심 contract surface (ADR-0031 §Decision A·B·C·D·E, ADR-0023 Note, ADR-0030 Note, ADR-0009 §4 Note, ADR-0010 Note) 모두 **word-for-word 정본 정합**.
- DoD F1~F7 + C1~C11 + R1~R5 중 코드/문서 의무 완료 (C1·C2·C3·C5~C11), 검증 의무는 Step 4 V<N> 으로 자연 deferred. C4 (ADR-0031 Accepted) 가 본 review gate.
- CRIT 0건, HIGH 0건 — spec drift 측면에서 release-blocker 부재.
- MED 4건 + LOW 3건 모두 follow-up commit 으로 해소 가능 (수정 effort 총 ~1시간).

**Step 5 deferred 정합**: plan.md §"적용 단계 선언" 의 Step 5=deferred + backlog.md "다음 feature 제안" 표의 `install_scope_reduction → Step 3 완료, Step 4 V<N> 대기` 가 consistency. HISTORY.md 항목은 Step 5 미수행이므로 미생성 — AGENTS.md §3 Step 5 의 "생략 시 HISTORY.md 항목 추가도 함께 생략" 정합.

**Follow-up commit 권장 순서**:
1. MED-CR2-3 (wikihub.yaml.example line 2) — 단일 라인 surgical
2. MED-CR2-1 (docs/adr/README.md ADR-0031 row) — 단일 행 patch
3. MED-CR2-2 (ADR-0030 Notes ADR-0031 의미 충돌) — 1 문장 patch
4. MED-CR2-4 (backlog ISR-1 추가) — 1 행 추가
5. LOW-CR2-1·2·3 — ADR + setup.md cross-ref 정합

본 5건 처리 후 Step 4 V<N> 검증 진입 + ADR-0031 → Accepted.

## Notes for synthesis

본 review 는 spec/contract 정합성 단독 persona — design_review_1 (SRE) 의 후속이라 systemd/atomic write 의 실행 측면 결함은 본 review 의 surface 가 아님. code_review_1 (다른 persona) 의 SRE/operational reliability finding 과 본 review 의 spec/governance finding 을 union 한 후 우선순위 정렬 권장 (CRIT/HIGH common → Step 3 복귀, MED ambiguous → 본 feature 또는 backlog 분류).
