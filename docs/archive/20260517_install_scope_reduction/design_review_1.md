# Design Review 1 — install_scope_reduction (SRE/Systems angle)

**Reviewer**: Senior SRE / Systems Reliability persona
**Date**: 2026-05-18
**Scope**: Step 1 plan + Step 2 analysis_and_design + ADR-0031 (Proposed) + ADR-0023 보강 §4.6

## Summary

설계의 큰 골조 — install.sh 의 yaml 개입 0건화 + sparse-checkout 으로 Dev Zone 격리 — 는 invariant 정합으로 옳다. 그러나 **운영 서버 전환 시점의 race·rollback 상호작용 3건** (sparse-checkout 적용 시점 vs `_step2_update` trap, partial-clone + `--unshallow` 호환성, `/wh:setup` 첫 호출 의무의 systemd race) + **idempotent drift fix 의 silent fallback** 이 v0.1.0 운영 서버에 도달하면 즉시 incident 가 된다. 전체적으로 **major 결함 (HIGH 3건)** 이 있어 redesign 까지는 아니나 §4.3·§4.5·§7.2 보강 필요.

## Findings

### [HIGH-S1] `_apply_sparse_checkout` 호출 시점이 `_step2_update` 의 PRE_UPDATE_REF trap 흐름을 깨뜨릴 수 있음

**Where**: `analysis_and_design.md` §4.3 ("After" 블록, line 215-222) + `install.sh:892-948` (`_step2_update` 본문)

**Issue**:
설계서가 `_apply_sparse_checkout` 을 `git fetch origin --tags` 와 `git reset --hard "$target_ref"` 사이에 삽입한다. 그러나:

1. `_step2_update` 진입 시점에 trap (`ERR EXIT INT TERM HUP → _rollback_if_failed`) 이 이미 등록돼 있고 PRE_UPDATE_REF 가 캡처됐다 (install.sh:894-897).
2. `git sparse-checkout init --no-cone` + `set <list>` 는 **현재 HEAD 의 index 에 대해 working tree 를 mutate** 한다. 즉 `_apply_sparse_checkout` 이 호출되는 시점의 HEAD = PRE_UPDATE_REF, 그러므로 sparse-checkout 이 working tree 에서 `docs/`·`features/`·`tests/`·`AGENTS.md` 를 **삭제**한다 — 아직 reset 도 안 했는데.
3. 만약 직후 `git reset --hard "$target_ref"` 가 disk-full 등으로 fail → `_rollback_if_failed` 가 `git reset --hard $PRE_UPDATE_REF` 호출. 하지만 sparse-checkout 정책은 `.git/info/sparse-checkout` 에 영속 → rollback 후에도 governance 파일은 **복구되지 않음**.
4. 운영자가 사후 trace 시 "rollback 후 `docs/` 없음" 을 보면 부분 손상으로 오인 가능. 실제로는 의도된 sparse state 인데 PRE_UPDATE_REF 의 install.sh 는 sparse 를 모른다.

**Recommendation**:
- `_apply_sparse_checkout` 호출 **위치를 `git reset --hard` 직후로 이동**. 의미: working tree mutation 의 origin 시점 = target_ref 채택 후 → rollback 시 같은 helper 가 idempotent 로 재적용 됨.
- `_rollback_if_failed` 본문에 `_apply_sparse_checkout` 호출 명시 — rollback 후에도 sparse state 정합.
- 추가로 ADR-0030 §"부정/제약" 에 "sparse-checkout 정책 영속화 → rollback 시 governance 파일 비복구 (의도)" 한 줄 명시.

**Effort**: small (라인 이동 + rollback 보강)

---

### [HIGH-S2] `--filter=blob:none` partial clone 와 `_step2_update --unshallow` 의 호환 검증 미수행

**Where**: `analysis_and_design.md` §4.2 (After 블록) + `install.sh:932` (`fetch --unshallow`)

**Issue**:
설계서가 fresh path 에서 `git clone --filter=blob:none --no-checkout --depth 1` 을 채택한다. partial clone (`filter=blob:none`) 은 `.git/config` 의 `remote.origin.promisor=true` + `remote.origin.partialclonefilter=blob:none` 을 남긴다. 이후 update path 의 `git fetch --unshallow` (install.sh:932) 가 호출되면:

1. partial clone + unshallow 조합은 git 2.27 이전엔 fail, 이후엔 동작하나 **모든 missing blobs 를 lazy fetch** 하는 의도와 충돌. fetch 자체는 성공하지만 `git reset --hard` 시 lazy blob fetch 가 매 파일 발생 → 100~수백개 round-trip 으로 update 시간 폭증 (OCI ARM 의 GitHub 대역폭 한계).
2. 운영 서버에서 첫 update 가 분단위 → 15min systemd grace 와 충돌 → vault@.service mid-sync 가 자연 종료하기 전에 git fetch 가 차단됨.
3. 또한 `--depth 1 + --filter=blob:none` 조합은 git release notes (2.27~2.30) 에서 incremental 개선 — 운영 타깃의 Ubuntu 22.04 LTS default git (2.34) 은 OK 지만 OCI ARM 의 ubuntu-minimal (2.25) 이미지 가능성도 surface 필요.

**Recommendation**:
- Step 2 §4.2 "After" 블록에 sparse-checkout 만으로 충분한지 재검토. **`--filter=blob:none` 제거 + sparse-checkout 만** 으로도 fetch list 외 파일은 working tree 에 안 떨어짐 (blob 은 .git 안에만 있고 working tree size 절감 동일). 운영 서버의 1.5 MiB disk 절감 동기는 working tree 만 보는 metric → blob filter 추가는 over-engineering.
- 만약 blob filter 유지 시 `_step2_update` 의 `fetch --unshallow` 동작을 V11 acceptance gate 에 추가 — pre-feature 풀-clone 서버에서 sparse 로 전환 + 다음 update 시 fetch + reset 정상 동작 검증.
- 최소한 install.sh require min git version (`git version >= 2.27`) check 추가 + ALLOW_NON_UBUNTU 분기 명시.

**Effort**: medium (clone command 단순화 또는 git version check 추가 + V11 추가 시나리오)

---

### [HIGH-S3] `/wh:setup` 첫 호출 의무 vs systemd timer fire race — silent ops-alert flood 가능

**Where**: `analysis_and_design.md` §6 U3 결정 + ADR-0031 §Decision C Case B 의 비대화 분기 + setup.md:33 (CRIT-R10-2 mkdir behavior)

**Issue**:
설계가 install.sh exits → yaml 부재 상태 → 운영자가 `/wh:setup` 호출해야 yaml 생성으로 흐름을 lock 한다. 그러나 install.sh `_step8_systemd_render` (install.sh:1115) 가 `wikihub.yaml` 부재 시 **`return 0`** (skip + warn) 한다. 메인테이너가 install.sh 호출 후 `/wh:setup` 호출 전에 reboot 또는 ssh 끊김:

1. systemd timer 가 이미 enable 돼 있으면 (ADR-0021 linger 활성화) vault@.timer fire → vault@.service ExecStart → `wikihub.yaml` 없음 → `config.py:155` `VaultSyncFatal` → exit 2 → `OnFailure=ops-alert.service`.
2. ops-alert 도 `last_failure.json` 부재 + yaml 부재 → fallback diagnostic 으로 journal tail 만 → webhook URL 미설정이면 silent. journal 만 매 사이클 (default 10min) 누적.
3. 더 위험: install.sh 가 fresh path 에선 unit render 가 yaml 부재로 skip → enable 도 안 되므로 timer fire 안 함. 그러나 **update path 에서는 기존 unit 이 활성 상태로 남아 있음** — pre-feature 운영 서버가 본 feature 적용 후 첫 update 에서 sparse-checkout 가 적용되며 동시에 `_step5_yaml` 가 삭제됐으니 yaml 그대로 유지 (instance dir 손 안 댐). 그런데 만약 메인테이너가 의도적으로 instance dir 의 yaml 을 삭제했거나 instance dir 자체를 wipe + restore 한 시나리오에서는 update path → yaml 부재 + timer 활성 = silent flood.

**Recommendation**:
- ADR-0031 §Decision C Case B 비대화 분기를 **exit 0 → exit 1** 로 변경하거나, **드라이언 보고만 + ops-alert 1회 강제 발화** 채택. install-derived 필드와 환경 mismatch 가 silent 으로 운영 진입하면 vault-fetch 가 yaml 의 잘못된 path 로 file_map.json 작성 → cursor 누적 위치 분리 → 다음 호출 시 무한 re-bootstrap 위험 (file_map 불일치).
- 또는 setup.md Step 0 보고에 ops-alert webhook 강제 1회 (drift 발견 + 비대화 모드 시) 추가. ADR-0024 의 fatal severity = "warning" 신규 enum 신설 검토.
- 추가로 install.sh `_step8_guide` 출력에 **"⚠ wikihub.yaml 부재 — `/wh:setup` 호출 전 reboot 또는 systemd timer enable 금지"** 명시. update path 에선 `_step8_guide` 가 호출 안 됨 → update mode 전용 안내가 별도 필요.

**Effort**: medium (ADR-0031 decision 보강 + ops-alert severity 확장 또는 단순한 exit code 변경 + guide 분기)

---

### [MED-S1] Atomic write 의 cross-filesystem `.tmp` 잔존 위험 — recovery path 미정의

**Where**: ADR-0031 §Decision A (line 67 "atomic write `.tmp` + `os.fsync` + `os.replace`") + setup.md Step 0 신규 spec

**Issue**:
설계가 `os.replace` 으로 atomic 보장하나:

1. `$WIKIHUB_INSTANCE_ROOT` 와 `/tmp` 가 다른 filesystem (OCI ARM Ubuntu 의 boot disk vs block volume 등) 이면 `.tmp` 를 `/tmp` 에 작성 후 `os.replace` 가 `EXDEV` fail. 설계서는 `.tmp` 위치 명시 안 됨 — `Path(target).parent / ".wikihub.yaml.tmp"` 같은 same-FS 패턴이 ADR 본문에 lock 안 됨.
2. SIGTERM mid-write (systemd shutdown 도중) — `.tmp` 잔존 → 다음 `/wh:setup` 호출 시 `.tmp` 의 의미 모호. backlog 의 CR2-MED-2 (`_atomic_write_if_changed` 의 `.tmp` 잔존 정리) 와 동일 이슈가 본 helper 에도 반복.
3. 디스크 full 케이스 — `os.fsync` 가 `ENOSPC` raise → `.tmp` 잔존 + 실 yaml 미생성. 다음 호출이 어떻게 detect 하는지 미정의.

**Recommendation**:
- ADR-0031 §Decision A 에 "atomic write 의 .tmp 는 target 의 same-directory" 명시 + ENOSPC / EXDEV / SIGTERM 3 케이스의 recovery path 명시 (재호출 시 .tmp 발견 → 무시 후 새 .tmp, 또는 .tmp.PID 패턴).
- `scripts/lib/yaml_materialize.py` (Step 3 신규 helper) 가 `_atomic_write_if_changed` 와 helper 통일 — backlog CR2-MED-2 같이 묶음 처리.

**Effort**: small (ADR 본문 1 paragraph + helper 작성 시 spec 정합)

---

### [MED-S2] `gws --version` 파싱 brittleness — stdout 형식 변경 시 patching 무한 루프

**Where**: ADR-0031 §Decision B Catalog (`operations.gws_min_version` ... `gws --version` stdout 파싱 결과)

**Issue**:
설계가 `gws --version` 의 stdout 을 파싱해서 yaml 의 `gws_min_version` 과 비교. drift 검출 후 confirm 시 패칭. 그러나:

1. gws 1.x 의 출력 형식이 변경되면 (`gws version 1.5.0` → `Google Workspace CLI v1.5.0` 등) 파싱이 빈 문자열 또는 noise 반환 → "drift detected: '' vs '1.5.0'" 매 호출 prompt → 운영자 alarm fatigue.
2. ADR-0015 의 gws pinned version + install.sh `_install_gws` 가 이미 정본 — install.sh 가 install-time 에 file 에 기록 (예: `$WIKIHUB_HOME/_state/gws.version`) 후 setup.md Step 0 가 그 file 을 read 하면 stdout 파싱 회피.
3. `_semver_gt` (install.sh:883) helper 가 이미 있음 — 같은 패턴을 yaml_materialize.py 에서 활용 가능.

**Recommendation**:
- ADR-0031 §Decision B 의 `gws_min_version` source 를 "`gws --version` stdout 파싱" → **"install.sh 가 작성하는 `$WIKIHUB_HOME/_system/INSTALLED_VERSIONS.json` (또는 동등 file)"** 로 변경. install.sh `_install_gws` 직후 file 작성 → setup.md Step 0 read. stdout 파싱 fallback 은 file 부재 시.
- 또는 patching scope 에서 `gws_min_version` 자체 제외 (5필드 → 4필드) + 메인테이너 수동 편집 책임. 운영 단순성 ↑.

**Effort**: small (install.sh 1 줄 추가 + helper spec 정합)

---

### [MED-S3] ruamel.yaml supply-chain risk — version pin 정밀화 필요

**Where**: ADR-0031 §Decision D ("`ruamel.yaml >= 0.18`")

**Issue**:
1. `>=0.18` 은 minor bump 허용 → 0.19, 0.20 등의 잠재 breaking change 가 운영 서버에 silent 진입 (install.sh Step 3 의 `uv pip install -r requirements.txt` 가 latest 채택).
2. ruamel.yaml 은 PyPA 잘 알려진 패키지지만 0.17 → 0.18 migration 시 round-trip API 변경 사례 있음 — 메인테이너 community 기록 (RTD changelog) 확인 필요.
3. install.sh 의 uv·rclone·gws 가 모두 SHA256 verify 패턴 — ruamel.yaml 만 verify 0건 (uv pip 의 hash 모드 활성화 안 함). 일관성 깨짐.

**Recommendation**:
- pin 형식 변경: `ruamel.yaml >=0.18,<0.19` 또는 `ruamel.yaml ==0.18.6` exact pin. ADR-0028 (uv) 의 pinned version 패턴 정합.
- `scripts/requirements.txt` 에 `--hash=sha256:...` 첨부 (`uv pip compile --generate-hashes` 출력). install.sh Step 3 의 `uv pip install --require-hashes -r requirements.txt` 호출 - supply chain 일관성.
- ADR-0031 §Decision D 에 위 두 항목 lock + Consequences "외부 dep 추가" mitigation 강화.

**Effort**: small (pin syntax + requirements.txt 라인 1줄)

---

### [LOW-S1] LICENSE 의 sparse-checkout 포함은 MIT 라 의무 아님 (관례)

**Where**: `analysis_and_design.md` §6 U1 결정 + ADR-0023 §"Clone scope" 보강

**Issue**:
LICENSE 파일은 MIT License (확인). MIT 는 "copies or substantial portions" 에 license 포함 의무인데 운영 서버는 binary/source redistribution 이 아님 (메인테이너 1인 운영). 즉 운영 타깃의 `~/wikihub/LICENSE` 는 legal 의무 fulfilment 라기보단 관례.

이 자체는 결함 아니지만 ADR-0023 §"Clone scope" 의 "LICENSE — legal" 표현이 강하게 의무처럼 읽힘 → 향후 메인테이너가 fetch list 정리 시 잘못된 sacred-cow 로 남을 위험.

**Recommendation**:
ADR-0023 §"Clone scope" 의 LICENSE 항목 표현 약화: `LICENSE — legal · convention (MIT, redistribution scope 가 아니지만 OSS 관례)`. 또는 fetch list 에서 제외 후 install.sh 가 `_step8_guide` 에 license URL 만 안내.

**Effort**: small (한 줄 표현 조정)

---

### [LOW-S2] Drift confirm prompt 의 reentrant safety — 메인테이너 hand-edit 시 Y/n 의미 모호

**Where**: ADR-0031 §Decision C Case B step 4 ("각 drift 필드 보고")

**Issue**:
메인테이너가 의도적으로 `instance.root` 를 `~/wikihub-instance` → `/data/wikihub` 로 편집 후 `/wh:setup` 재호출. 그런데 install.sh 호출 시 env override 가 `WIKIHUB_INSTANCE_ROOT=/data/wikihub` 가 아니었다면 drift 검출 = "yaml: /data/wikihub vs env: ~/wikihub-instance" → confirm prompt "Y/n (default Y)" → **운영자가 무심코 enter** 시 yaml 의 의도된 편집이 env 값으로 **덮어쓰임**.

설계서 §6 U3 결정이 "confirm + 비대화 fallback=보존" 이지만 confirm default 가 `Y` 라 hand-edit 가 우선 손실 위험.

**Recommendation**:
- Confirm prompt default 를 `n` 으로 변경 (보수적). 또는 prompt 문구를 "**이 변경은 install-time env 값으로 덮어씁니다. 메인테이너 hand-edit 가 있으면 N**. [y/N] (default N)" 로 명시.
- 더 좋은 안: drift 의 source 가 (a) install-time env 와 매번 mismatch vs (b) install-time env 와 일치하지만 derived 만 mismatch 인지 분리 보고. (a) 는 hand-edit 의심 → preserve, (b) 는 derived 실수 → patch.

**Effort**: small (prompt 문구 + default 변경)

---

## Backlog candidates (out of feat scope)

- **comment preservation fallback**: ruamel.yaml 의 round-trip 이 메인테이너 hand-edit 후 comment association 깨지는 케이스 (multiline scalar 의 anchor + comment 등) — v0.2.x 의 yaml editing UX feature 로 분리.
- **derived path catalog 확장** (multi-vault): ADR-0031 §"v0.2.x 재검토 트리거" 에 이미 명시됨. 본 feat 범위 밖.
- **install.sh 의 instance dir 외부화 옵션**: `$WIKIHUB_INSTANCE_ROOT` 가 path 인데 `~/wikihub-instance` 기본값이 home 안 — multi-instance 운영 (예: `wikihub-prod` + `wikihub-staging` 동일 서버) 시 path 분리 정책 v0.2.x.
- **systemd OnCalendar drift detection job**: instance dir 의 yaml 과 install env 의 silent mismatch 를 주 1회 detect + alert. v0.2.x ops 강화.

---

## Overall recommendation

- [ ] Approve as-is
- [ ] Approve with minor changes (LOW/MED items addressed)
- [x] **Approve with major changes (HIGH items addressed)**
- [ ] Request redesign (CRIT items present)

HIGH-S1·S2·S3 는 운영 서버에 첫 update 적용 시점에 발화 가능한 시나리오라 Step 3 진입 전 §4.3·§4.5 보강 + ADR-0031 §Decision C 비대화 분기 강화가 prerequisite. MED 4건 (atomic write spec / gws 파싱 / ruamel pin / LICENSE 표현) 은 Step 3 구현 중 lock 가능.

## Notes for synthesis

Reviewer 2 (typically code-quality/spec-consistency angle) 가 sparse-checkout fetch list 의 ADR-0023 보강 본문 정합·setup.md "install.sh와의 관계" 표 정합·ruamel API 활용 정합 위주로 보면 본 SRE 리뷰의 HIGH 3건 (rollback/trap interaction, partial-clone+unshallow, systemd timer race) 과 직교한 finding 이 묶일 것. HIGH-S1·S2 는 sparse-checkout 패턴의 install.sh 통합 detail 이라 코드 리뷰 시점에도 재발견될 가능성 높음 — Step 2 에서 lock 하는 게 yield 높다.
