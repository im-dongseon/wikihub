# Feature Plan — install_scope_reduction

- **feat_id**: `install_scope_reduction`
- **시작일 (KST)**: 2026-05-17
- **버전**: v1
- **선행 feature**: `update_mode` (archive 완료, squash `0a83135` — ADR-0030 lock 됨)
- **연계 backlog**: `features/backlog.md` 의 결함 **#E (install scope)** + **#F (yaml provisioning)**
- **목적**: install.sh 의 **clone scope** 와 **yaml provisioning 책임** 두 결함을 동시 정합. (1) `_step2_clone` 가 repo 전체를 받아 메인테이너 내부 산출물(`docs/`·`features/`·`tests/`·`AGENTS.md` 등 ~1.5 MiB)이 운영 타깃에 노출되는 AGENTS.md §1 Dev/Ops Zone 분리 invariant 위반을 sparse-checkout 으로 닫고, (2) install.sh + `/wh:setup` 두 곳에 분산된 yaml writer 책임을 `/wh:setup` 단독으로 lock 해 race·이중 정본 위험 제거.

> **핵심 운영 invariant**: 운영 타깃에는 운영 필수 path 만 거주. yaml 의 시작·끝 책임은 `/wh:setup` 단독 (install.sh 의 yaml 개입 0건). `.example` 은 repo 의 read-only template, 운영 정본은 instance dir — 위치 분리로 운영자 혼동 차단.

---

## 작업 분류

**기능 추가** (sparse-checkout · `/wh:setup` Step 0) + **scope 축소 refactor** (install.sh Step 5 cp 삭제) + **결함 묶음 fix** (#E·#F).

---

## 적용 단계 선언

| 단계 | 수행 | 사유 |
|---|---|---|
| Step 1 Plan | ✅ 본 문서 | feat scope lock 필요 (sparse-checkout fetch list + `/wh:setup` Step 0 의 patching 범위 + ADR-0023 보강 vs 신규 ADR-0031 분리) |
| Step 2 Analysis & Design | ✅ 수행 | install.sh 외부 인터페이스(clone scope) 변경 + `/wh:setup` 의 yaml writer 책임 확장 — 결정 경계 lock 필요. 미결 U1~U5 (아래) |
| Step 2 Design Review | ✅ 수행 (R≥2) | install.sh + `/wh:setup` 두 정본 동시 변경. clone scope 의 sparse-checkout 패턴 정합성 + Step 0 의 idempotent drift fix 정책 — 멀티모델 검증 필수 |
| Step 3 Implementation | ✅ 수행 | install.sh `_step2_clone` + Step 5 삭제 + Step 8 안내문 갱신, `_system/commands/setup.md` Step 0 신규, ADR-0023 보강, ADR-0031 신설 |
| Step 4 Code Review | ✅ 수행 (R≥2) | install.sh 의 sparse-checkout 분기 + `/wh:setup` Step 0 의 yaml writer (`atomic_write` + drift detect) — multi-model 검증 필수 |
| Step 5 Deployment | ⏸ **deferred** | v0.1.0 다른 feature (F5 hermes_adapter) 미완성. update_mode 와 같은 사유로 v0.1.0 전체 완성 후 일괄 deploy |

메소드론 적용: **전체 적용** — trivial 변경 아님. install.sh 의 lifecycle 정본 변경 (clone scope) + `/wh:setup` 의 외부 인터페이스 확장 (Step 0).

---

## 예상 영향 범위

### 신규

- `features/20260517_install_scope_reduction/analysis_and_design.md` — Step 2 산출물.
- `docs/adr/0031-yaml-template-materialization.md` — `/wh:setup` Step 0 의 정책 정본화. (예비 — Step 2 에서 ADR-0023 보강만으로 충분한지 재확인)
- `_system/commands/setup.md` 내 **Step 0** 섹션 신규 — `wikihub.yaml` 부재 시 `.example` template 으로 materialize + derived 값 patching + idempotent drift fix.

### 수정

- `install.sh`:
  - `_step2_clone` — `git clone --filter=blob:none --no-checkout --depth 1` + `sparse-checkout init --cone` + `set _system scripts wikihub.yaml.example install.sh README.md` 패턴. (update_mode 의 `_step2_update` 와 정합 — Step 2 에서 검토)
  - `_step5_yaml` — **함수 자체 삭제** (yaml cp 책임 제거). `main()` 의 호출 순서 갱신.
  - `_step8_guide` — 운영자 안내문 갱신: "1. `/wh:setup` 호출 (yaml 자동 생성) → 2. yaml 편집 → 3. `/wh:setup --enable`" 흐름 명확화. 기존 "wikihub.yaml.example → wikihub.yaml 복사" 표현 제거.
- `_system/commands/setup.md`:
  - "install.sh와의 관계" 표 (line 287-298) — `wikihub.yaml.example → wikihub.yaml 복사` 행의 install.sh 컬럼 `✓` 삭제, `/wh:setup` 컬럼에 `✓` 추가.
  - Step 1 의 사전 조건 — "install.sh가 example을 복사한 상태" 문구 제거, Step 0 가 책임지는 흐름으로 갱신.
- `docs/adr/0023-install-script-distribution-curl-pipe.md` — "clone scope" 항목 보강 (supersede 아님, Decision 본문에 sparse-checkout fetch list 추가).

### 비영향 (의도적 제외)

- `_system/wiki-schema.md` — 지식 모델 무변경.
- `_system/commands/ingest.md`·`lint.md`·`query.md`·`graphify.md` — vault sync / lint / query 의미론 무변경.
- `scripts/*` — Python 런타임 무변경.
- `wikihub.yaml.example` 본문 — template schema 무변경 (위치만 정합, 내용 미수정).
- update_mode 산출 (`_step2_update`, ADR-0030) — sparse-checkout 패턴 적용 외 의미론 변경 없음. Step 2 에서 update path 의 sparse-checkout 정합성 검증만.

---

## 미결 사항 (Step 2 에서 lock)

| ID | 항목 | 후보 |
|---|---|---|
| U1 | sparse-checkout fetch list | `_system`·`scripts`·`install.sh`·`wikihub.yaml.example`·`README.md` 5개. `LICENSE` 포함 여부 (legal 측면) Step 2 확인 |
| U2 | `/wh:setup` Step 0 의 patching 필드 범위 | (a) instance.root override + 파생 path (`local_path`·`mount_path`·`credentials_path`) 만 / (b) 추가로 install-time fact (`gws_min_version`·`rclone_min_version`·`rclone_max_version`) 포함 / (c) agent.binary 자동 detect (`command -v hermes`) 까지 |
| U3 | idempotent drift fix 정책 | (a) Step 0 가 매 호출 install-derived 필드 강제 재patching (메인테이너 편집 덮어쓰기) / (b) 첫 generate 시만 patching, 이후 호출은 drift 보고만 (편집 보존) / (c) drift 검출 시 사용자 confirm 후 patching (update_mode invariant 정합) |
| U4 | ADR 분리 정책 | (a) ADR-0023 보강 단독 (clone scope 만) / (b) ADR-0023 보강 + ADR-0031 신설 (yaml template materialization 분리) / 결정 = 1 ADR 원칙 고려 시 (b) 가 자연 |
| U5 | install.sh `_step2_update` (update_mode 산출) 와 sparse-checkout 정합 | update path 도 sparse-checkout 으로 일관성 유지 필요. `git sparse-checkout set` 의 idempotency 검증 |
| U6 | `.example` template 본문의 placeholder convention | (a) 현재처럼 default 값 (`~/wikihub-instance`) literal 유지 — Step 0 가 string match 로 detect / (b) `{{instance_root}}` 같은 명시 placeholder 도입 — patching 안전성 ↑ 단 yaml 표면 가독성 ↓ |

신규 ADR 후보: **ADR-0031 (yaml template materialization)** — U2·U3·U6 의 정책을 1건으로 묶음. `/wh:setup` Step 0 의 template materialization 흐름 + derived 필드 범위 + drift fix idempotency 를 정본화. ADR-0023 의 후속 (supersede 아님, 보강).

---

## DoD 미리보기 (Step 2 에서 정밀화)

- install.sh 재호출 시 운영 타깃에 `docs/`·`features/`·`tests/`·`AGENTS.md` 등 메인테이너 내부 산출물이 거주하지 않음 (sparse-checkout 검증).
- install.sh 호출 직후 `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml` 이 **존재하지 않음** (Step 5 cp 삭제 검증).
- `/wh:setup` 첫 호출이 `wikihub.yaml` 을 `.example` template + derived 값으로 atomic 생성.
- `/wh:setup` 재호출이 메인테이너 편집을 의도와 다르게 덮어쓰지 않음 (U3 정책 정합).
- update_mode 의 `_step2_update` path 와 sparse-checkout 정합 (재호출 idempotent).
- 결함 #E + #F 모두 closed.
- ADR-0023 본문 보강 완료, (U4 결정에 따라) ADR-0031 Accepted.

---

## 다음 단계

사용자 확정 후 `features/20260517_install_scope_reduction/analysis_and_design.md` 작성 진입. 진입 시점에서 미결 U1~U6 surface 우선.
