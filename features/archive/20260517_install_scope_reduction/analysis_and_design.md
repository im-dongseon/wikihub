# Analysis & Design — install_scope_reduction

- **feat_id**: `install_scope_reduction`
- **버전**: v1 (Step 2 초안, 2026-05-17) → **v2 (design review 반영, 2026-05-18)**
- **선행**: `update_mode` (ADR-0030, `0a83135`) — `_step2_update` 정본 안정화 완료
- **plan**: `plan.md` (Step 1 산출물)
- **backlog 결함**: #E (install scope) + #F (yaml provisioning)
- **review 산출**: `design_review_1.md` (SRE/Systems) + `design_review_2.md` (Spec/Architecture) — 2026-05-18
- **approved**: 2026-05-18 (사용자 승인 — v2 의 design review 반영분 일괄 confirm)

> **v2 갱신 요약 (2026-05-18)**: design review 의 CRIT 2건 + HIGH 5건 + MED 6건 + LOW 2건 반영. 본 문서는 v1 본문을 **in-place 갱신** (Step 2 의 정본은 단일 파일 유지) — 변경 항목은 §10 변경 이력에 catalog. ADR-0031 도 v2 로 갱신, ADR-0009·0010·0030 에 supplementary Note 추가.

---

## 1. 배경 및 목적

### 1.1 배경

F4 `install_runtime` 가 v0.1.0 의 install + update 흐름을 정본화했고, `update_mode` 가 그 위에서 dual-mode lifecycle 을 lock 했다. 그러나 두 feature 모두 **install.sh 가 받는 repo 의 범위 (clone scope)** 와 **wikihub.yaml 의 시작 책임** 두 측면을 surgical 외부로 남겨뒀다:

1. `_step2_clone` (install.sh:287) — `git clone --depth 1` 로 repo 전체를 받음. `docs/`·`features/`·`tests/`·`AGENTS.md`·`CLAUDE.md`·`GEMINI.md` 등 메인테이너 governance 산출물 (~1.5 MiB) 이 운영 타깃에 그대로 거주.
2. `_step5_yaml` (install.sh:524-538, update_mode 후에도 유지) — `cp wikihub.yaml.example → wikihub.yaml` 단순 복사. 운영용 값은 메인테이너가 수동 편집 + `/wh:setup` 호출 흐름.

### 1.2 목적

두 결함을 **한 feature** 로 묶어 처리한다 (변경 위치 = install.sh + `_system/commands/setup.md` 동일, 영향 invariant 도 같음).

- **Invariant A (location separation)**: 운영 타깃에는 운영 필수 path 만 거주. AGENTS.md §1 Dev Zone / Ops Zone 분리 invariant 정합.
- **Invariant B (single yaml writer)** — v2 명료화: yaml 의 시작·끝 책임은 `/wh:setup` 단독 — install.sh 는 yaml 한 글자도 안 만짐. 추가로 `/wh:setup` **내부에서도 단일 helper** (`scripts/lib/yaml_writer.py` 의 `atomic_yaml_write`) 가 Step 0 + Step 6 둘 다의 yaml write 책임 — atomic lock + 주석 보존 일관성 (CRIT-A2 반영, ADR-0031 §Decision D).
- **Invariant C (location-based ambiguity removal)**: `.example` 은 repo 의 read-only template, 운영 정본은 instance dir. 위치만으로 "operational vs template" 구분 — 운영자 혼동 0.

### 1.3 메소드론 적용 범위

- 메소드론 전체 적용 (trivial 아님).
- Karpathy §2 (Simplicity First) — sparse-checkout 패턴 비교 시 cone vs no-cone, Step 0 patching 범위, ADR 분리 정책 셋 다 "단순한 답" 우선.
- Karpathy §3 (Surgical Changes) — Step 2 cp 삭제·sparse-checkout·Step 0 신규 외 install.sh 본문 인접 코드 미수정.

---

## 2. 현행 진단

### 2.1 결함 #E — install scope

**근거**:
- install.sh:287-305 `_step2_clone` 가 `git clone --branch <ref> --depth 1` 만 호출. sparse-checkout 미적용.
- 운영 타깃의 `$WIKIHUB_HOME` 디렉토리 listing (현 VM 상태):
  ```
  docs/             260K   ADR · agent_dev_guide · karpathy-guidelines · llm_wiki
  features/         944K   plan · analysis_and_design · review · archive
  tests/            244K   pytest
  AGENTS.md         16K    메인테이너 거버넌스
  CLAUDE.md         (symlink → AGENTS.md)
  GEMINI.md         (symlink → AGENTS.md)
  ```
- `docs/` 의 ADR 본문은 메인테이너의 결정 근거·옵션 탐색 기록 — 운영자가 보지 말아야 할 내부 논의가 운영 서버에 상주 (정보 자체가 민감하진 않지만 governance 경계 위반).
- `features/` 는 plan·design review·code review 등 작업 워크스페이스 — 운영 타깃과 무관.

**영향**:
- 디스크 ~1.5 MiB / 4.7 MiB (32%) 무의미 점유.
- AGENTS.md §1 의 "물리적 격리" 원칙 위반 — Operations Zone 에 Development Zone 산출물 노출.
- 운영자가 ssh 로 접속 시 `cd ~/wikihub && ls` 하면 governance 문서가 보임 — UX 불명료.

### 2.2 결함 #F — yaml provisioning

**근거**:
- install.sh:524-538 `_step5_yaml`:
  ```bash
  cp "$WIKIHUB_HOME/wikihub.yaml.example" "$target"  # raw cp, 값 patching 0
  ```
- `wikihub.yaml.example` (line 9-20):
  ```yaml
  instance:
    root: ~/wikihub-instance       # default literal — 운영자가 env override 했어도 patching 0
    timezone: Asia/Seoul
  vaults:
    - id: gdrive
      local_path: ~/wikihub-instance/vault/gdrive      # instance.root 파생인데 hard-coded
      options:
        credentials_path: ~/wikihub-instance/.credentials/sa_gdrive.json    # 동일
        mount_path: ~/wikihub-instance/vault/gdrive    # 동일
  operations:
    gws_min_version: ""           # 빈 문자열 — 메인테이너가 Step 4 후 채우라는 주석만
  ```
- `/wh:setup` (setup.md:264) 가 이미 yaml writer 책임 (Step 6 의 `bootstrap_allowed: true → false` atomic write). install.sh 가 동일 yaml 의 다른 필드를 동시에 만질 가능성 → race / 이중 정본.

**영향**:
- 메인테이너 수동 편집 단계 강제 — `WIKIHUB_INSTANCE_ROOT` env 로 install 한 경우 yaml 의 `instance.root` 와 mismatch.
- `gws_min_version` 같은 install-time fact 가 비어 있어 `/wh:setup` Step 1 검증 (setup.md:32) 이 매번 skip.
- ADR-0010 의 "install.sh = OS bootstrap / `/wh:setup` = yaml 정합" 경계 모호.

---

## 3. 개정 범위

### 3.1 install.sh

| 함수 | 변경 성격 | 내용 |
|---|---|---|
| `_step2_clone` | 수정 (확장) | **v2 단순화 (HIGH-S2)**: `git clone --no-checkout --depth 1 --branch <ref>` (blob filter 제거 — over-engineering 회피, partial clone + `--unshallow` 호환 위험 회피). `_apply_sparse_checkout` 호출 + `git checkout` 추가. clone scope = `_system`·`scripts`·`install.sh`·`wikihub.yaml.example`·`README.md`·`LICENSE` 6개 |
| `_step2_update` | 수정 (보강) | **v2 위치 정정 (HIGH-S1)**: `_apply_sparse_checkout` 호출을 `git reset --hard "$target_ref"` **이후** 로 lock — working tree mutation 의 origin 시점 = target_ref 채택 후, rollback 시 idempotent 재적용. `_rollback_if_failed` 본문에 `_apply_sparse_checkout` 호출 명시 + journal 로그에 "sparse re-apply (intended)" 가시화 |
| `_install_gws` | 수정 (sidecar 작성) | **v2 신규 (MED-S2)**: `_install_gws` 직후 `$WIKIHUB_HOME/_system/INSTALLED_VERSIONS.json` 에 `{"gws": "<GWS_VERSION>", "rclone": "<pinned>", "uv": "<UV_VERSION>"}` atomic write. Step 0 가 read |
| `_step5_yaml` | **삭제** | 함수 자체 + `main()` 호출 라인 제거. yaml 책임 `/wh:setup` Step 0 이전. instance dir mkdir + credentials chmod 로직은 `_step5_instance_dirs` 로 rename (yaml 외 책임 유지) |
| `_step8_guide` | 수정 (안내문) | **v2 보강 (HIGH-S3)**: line 647-651 흐름 갱신 + line 730 "다음 단계" 블록에 **"⚠ wikihub.yaml 부재 — `/wh:setup` 호출 전 reboot 또는 systemd timer enable 금지"** 명시. update path 안내 별도 추가 (`[[ "$INSTALL_MODE" == "update" ]]` 분기 — update 시에도 yaml 부재 detect → 운영자 안내) |

### 3.2 `_system/commands/setup.md`

| 섹션 | 변경 성격 | 내용 |
|---|---|---|
| Step 0 (신규) | 신규 섹션 | "template materialization · schema version 검증 · drift fix". `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml` 부재 시 `.example` 을 source 로 yaml 생성 + 운영용 derived 값 patching + atomic write. 존재 시 schema version 검증 (v2 신규 — HIGH-A2, ADR-0031 §Decision E) + install-derived 필드 drift 검출 + 정합 동기화 (대화 confirm, 비대화 exit 1) |
| Step 1 사전 조건 (line 19-24) | 수정 | "install.sh가 example을 복사한 상태이면" 문구 삭제. Step 0 가 책임지는 흐름 |
| Step 1 schema 검증 (config.py 정합) | 수정 (v2 — HIGH-A1) | `mount_path != local_path` 시 **soft warn** 추가 (default 패턴 아님 안내, fail 안 함) — advanced 운영자 use case (bind-mount, ramdisk, multi-vault layout 분리) 자연 수용 |
| Step 6 (`bootstrap_allowed: true → false`) | 수정 (v2 — CRIT-A2) | 기존 raw replace 를 `scripts/lib/yaml_writer.py` 의 `atomic_yaml_write` helper 호출로 교체 (~10 줄). 주석 보존 일관성 + atomic lock 단일화 (Step 0 와 helper 공유). ADR-0022 본문 갱신 없음 (helper detail 만 setup.md Step 6 spec 에 반영) |
| "install.sh와의 관계" 표 (line 287-298) | 수정 | `wikihub.yaml.example → wikihub.yaml 복사` 행 변경 — install.sh 컬럼 `✓` 삭제, `/wh:setup` 컬럼 cell 텍스트: **"✓ (Step 0 가 첫 호출 시 generate · 이후 호출 시 drift sync)"** (v2 — LOW-A2 cell wording lock). 새 행 `wikihub.yaml derived 값 patching` 추가 — `/wh:setup` 컬럼 `✓ (Step 0, ADR-0031 §Decision B 4필드)` |
| 출력 산출물 표 (line 257-265) | 수정 | `wikihub.yaml` 행 추가 — "Step 0 첫 호출 시 .example 으로부터 생성, 이후 호출은 drift 동기화. helper = `scripts/lib/yaml_writer.py atomic_yaml_write`" |

### 3.3 ADR

| 파일 | 변경 성격 | 내용 |
|---|---|---|
| `docs/adr/0023-install-script-distribution-curl-pipe.md` | 보강 (supersede 아님) | "clone scope" 항목 추가. Decision 본문에 sparse-checkout fetch list 명시. update path 도 sparse-checkout state 정합 의무 |
| `docs/adr/0031-yaml-template-materialization.md` | 신규 | `/wh:setup` Step 0 의 정본. v2 (2026-05-18) 가 design review 반영 — `Partially supersedes: ADR-0010`, Step 6 helper 흡수, 4필드 catalog (`mount_path` 제외), §E schema version 정책 |
| `docs/adr/0010-operational-tooling-split.md` | **필수 보강** (v2 — CRIT-A1) | Note 추가 (2026-05-18) — yaml.example 복사 책임이 ADR-0031 으로 reassign. line 38·49·80 의 sub-decision 만 supplement (큰 도구 split 결정은 유지) |
| `docs/adr/0009-setup-responsibility.md` | **필수 보강** (v2 — MED-A3) | Note 추가 (2026-05-18) — §Decision §"1. 환경 검증 (read-only)" 의 "read-only" 정정 + §4 신규 (yaml writer Step 0 + Step 6, ADR-0022+0031 정본) |
| `docs/adr/0030-update-workflow-orchestration.md` | **필수 보강** (v2 — HIGH-S1) | §부정/제약 에 Note 추가 (2026-05-18) — sparse-checkout 정책 영속화, rollback 시 governance 파일 비복구 의도. `_apply_sparse_checkout` 호출 위치 (reset --hard 이후) + `_rollback_if_failed` 본문 명시 |

### 3.4 비영향 (의도적 제외)

- `_system/wiki-schema.md` — 지식 모델 무변경.
- `_system/commands/ingest.md`·`lint.md`·`query.md`·`graphify.md` — vault sync / lint / query 의미론 무변경.
- `scripts/*` 의 대부분 — Python 런타임 의미론 무변경.
  - `scripts/lib/config.py:156` remediation 메시지 갱신 (`/wh:setup` 호출 의무 명시) — Step 3.
  - `scripts/lib/config.py` schema 검증에 `mount_path != local_path` soft warn 추가 — Step 3.
  - `scripts/lib/yaml_writer.py` 신규 — Step 0 + Step 6 의 단일 helper (CRIT-A2).
  - `scripts/requirements.txt` 에 `ruamel.yaml==0.18.6 --hash=sha256:<TBD>` 1줄 추가 (MED-S3).
- `wikihub.yaml.example` 본문 — schema 무변경.
- update_mode 산출 (`_step2_update`, ADR-0030) — `_apply_sparse_checkout` helper 호출 추가 (HIGH-S1 위치 정정) 외 의미론 변경 없음.
- `wikihub.yaml` 의 maintainer-controlled 필드 (ADR-0031 §Decision B 의 "미관여 필드" inverted catalog) — Step 0 절대 미관여. v2: `mount_path` 도 maintainer-controlled 로 reclassify (HIGH-A1).

---

## 4. 개정 전/후 비교

### 4.1 운영 타깃 `$WIKIHUB_HOME` listing

**Before**:
```
$WIKIHUB_HOME/
├── _system/                116K     ← 운영 필수 (playbooks)
├── scripts/                252K     ← 운영 필수 (Python)
├── docs/                   260K     ← 무관 (ADR · 가이드)
├── features/               944K     ← 무관 (plan · review · archive)
├── tests/                  244K     ← 무관 (pytest)
├── AGENTS.md               16K      ← 무관 (governance)
├── CLAUDE.md → AGENTS.md   ← 무관
├── GEMINI.md → AGENTS.md   ← 무관
├── install.sh              36K      ← 운영 필수
├── wikihub.yaml.example    4K       ← 운영 필수 (/wh:setup 입력)
├── README.md               8K       ← 운영 필수 (운영자 진단 참고)
└── LICENSE                 1K       ← legal 필수
```

**After** (sparse-checkout 적용):
```
$WIKIHUB_HOME/
├── _system/                116K     ← 운영 필수
├── scripts/                252K     ← 운영 필수
├── install.sh              36K      ← 운영 필수
├── wikihub.yaml.example    4K       ← /wh:setup 입력 (위치 유지)
├── README.md               8K       ← 운영자 참고
└── LICENSE                 1K       ← legal
```

- 디스크 절감: ~1.5 MiB (~32%).
- AGENTS.md §1 Dev Zone 산출물 0건 거주.

### 4.2 install.sh `_step2_clone`

**Before** (install.sh:287-307):
```bash
_step2_clone() {
    _validate_wipe_target
    if [ -e "$WIKIHUB_HOME" ]; then
        rm -rf "$WIKIHUB_HOME"
    fi
    local clone_ref="$(_resolve_ref)"
    # ref normalize
    git clone --branch "$clone_ref" --depth 1 "$WIKIHUB_REPO_URL" "$WIKIHUB_HOME"
    ok "Step 2 repo clone 완료 (ref=$clone_ref)"
}
```

**After** (개념 — Step 3 에서 정확한 라인 lock, **v2 단순화: blob filter 제거**):
```bash
# 정본 fetch list (단일 source — _step2_clone + _step2_update + sparse-checkout helper 가 참조)
WIKIHUB_SPARSE_PATHS=(_system scripts install.sh wikihub.yaml.example README.md LICENSE)

_apply_sparse_checkout() {
    # idempotent — clone 또는 update path 둘 다 호출
    git -C "$WIKIHUB_HOME" sparse-checkout init --no-cone
    git -C "$WIKIHUB_HOME" sparse-checkout set "${WIKIHUB_SPARSE_PATHS[@]}"
}

_step2_clone() {
    _validate_wipe_target
    if [ -e "$WIKIHUB_HOME" ]; then
        rm -rf "$WIKIHUB_HOME"
    fi
    local clone_ref="$(_resolve_ref)"
    # ref normalize 동일
    # v2 (HIGH-S2): --filter=blob:none 제거 — sparse-checkout 만으로 working tree 절감 충분.
    # partial clone + --unshallow 호환 위험 (git 2.27+ 의존 + lazy blob fetch 폭증) 회피.
    git clone --no-checkout --depth 1 \
        --branch "$clone_ref" "$WIKIHUB_REPO_URL" "$WIKIHUB_HOME"
    _apply_sparse_checkout
    git -C "$WIKIHUB_HOME" checkout
    ok "Step 2 repo clone 완료 (ref=$clone_ref, scope=sparse)"
}
```

### 4.3 install.sh `_step2_update` 보강

**Before** (install.sh:892+, update_mode 산출):
```bash
git -C "$WIKIHUB_HOME" config --replace-all remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*' || true
git -C "$WIKIHUB_HOME" fetch --unshallow 2>/dev/null || true
git -C "$WIKIHUB_HOME" fetch origin --tags
git -C "$WIKIHUB_HOME" reset --hard "$target_ref"
```

**After** (**v2 위치 정정 — HIGH-S1**):
```bash
git -C "$WIKIHUB_HOME" config --replace-all remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*' || true
git -C "$WIKIHUB_HOME" fetch --unshallow 2>/dev/null || true
git -C "$WIKIHUB_HOME" fetch origin --tags
git -C "$WIKIHUB_HOME" reset --hard "$target_ref"
_apply_sparse_checkout              # ← v2: reset --hard 직후로 이동. working tree mutation origin = target_ref 채택 후 → rollback 시 idempotent 재적용 안전. PRE_UPDATE_REF 의 governance 파일이 reset 직전에 사라지는 race 회피.
```

추가로 `_rollback_if_failed` 본문에 `_apply_sparse_checkout` 호출 명시 (rollback target 의 working tree 가 sparse subset 만 표시되도록 정합):
```bash
_rollback_if_failed() {
    # ... 기존 rollback 로직 (git reset --hard $PRE_UPDATE_REF) ...
    _apply_sparse_checkout || warn "rollback 후 sparse re-apply fail (working tree 일관성 영향 가능 — 진단 필요)"
    info "sparse re-apply (intended — governance 파일은 rollback 후 미복구, ADR-0030 §부정/제약 참조)"
}
```

### 4.4 install.sh `_step5_yaml` 삭제

**Before** (install.sh:524-538):
```bash
_step5_yaml() {
    mkdir -p "$WIKIHUB_INSTANCE_ROOT"
    mkdir -p "$WIKIHUB_INSTANCE_ROOT/.credentials"
    chmod 700 "$WIKIHUB_INSTANCE_ROOT/.credentials"
    local target="$WIKIHUB_INSTANCE_ROOT/wikihub.yaml"
    if [ -f "$target" ]; then
        ok "Step 5 wikihub.yaml 기존 보존: $target"
    else
        cp "$WIKIHUB_HOME/wikihub.yaml.example" "$target"
        ok "Step 5 wikihub.yaml.example → $target"
    fi
    # credentials chmod enforce ...
}
```

**After**:
- `_step5_yaml` 함수 **삭제**.
- `mkdir $WIKIHUB_INSTANCE_ROOT` + `mkdir .credentials` + `chmod 700 .credentials` + credentials chmod enforce 로직은 **별도 `_step5_instance_dirs` 로 rename** (yaml 외 책임만 유지).
- `main()` 의 `_step5_yaml` 호출 → `_step5_instance_dirs` 로 교체.

### 4.5 `/wh:setup` Step 0 신규

**After** (setup.md 신규 섹션 — Step 1 앞에 삽입):
```markdown
### Step 0. wikihub.yaml materialization & drift fix (ADR-0031)

**진입 조건**: 매 /wh:setup 호출.

**동작 분기**:

#### Case A — `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml` 부재

1. `$WIKIHUB_HOME/wikihub.yaml.example` read (PyYAML safe_load).
2. derived 값 patching (아래 catalog).
3. atomic write `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml` (`.tmp` + rename + fsync).
4. 보고: "wikihub.yaml 생성 — vault id/root_folder_id/bootstrap_allowed/fatal_webhook_url 편집 후 재호출".

#### Case B — `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml` 존재

1. yaml load.
2. derived 필드 drift 검출:
   - `instance.root` vs `$WIKIHUB_INSTANCE_ROOT` env (install.sh 가 export 한 값)
   - `vaults[*].local_path` vs `<instance.root>/vault/<id>` 파생
   - `vaults[*].options.credentials_path` vs `<instance.root>/.credentials/sa_<id>.json` 파생
   - `vaults[*].options.mount_path` vs `local_path` 동일성
   - `operations.gws_min_version` vs `gws --version` 출력
3. drift 발견 시:
   - `WIKIHUB_NONINTERACTIVE` 미설정 + `/dev/tty` 있음 → 사용자 confirm prompt
   - 그 외 → drift 보고만 + 기존 값 보존 (재호출 시 confirm)
4. confirm 시 atomic re-write.

#### Derived 필드 catalog (Step 0 patching 범위 — ADR-0031 lock)

| 필드 | source | patching 조건 |
|---|---|---|
| `instance.root` | `$WIKIHUB_INSTANCE_ROOT` env | env 와 다를 때 |
| `vaults[*].local_path` | `<instance.root>/vault/<id>` | 파생 mismatch 시 |
| `vaults[*].options.mount_path` | `<instance.root>/vault/<id>` (= local_path) | 파생 mismatch 시 |
| `vaults[*].options.credentials_path` | `<instance.root>/.credentials/sa_<id>.json` | 파생 mismatch 시 |
| `operations.gws_min_version` | `gws --version` stdout 파싱 | 빈 문자열 또는 install gws 보다 낮을 때 |

**미관여 필드** (메인테이너 단독): `vaults[*].id`·`enabled`·`type`·`sync_interval_sec`·`options.root_folder_id`·`options.exclude_shared_with_me`·`options.max_file_size_mb`·`options.bootstrap_allowed`·`options.rclone_remote_name`·`options.rclone_rc_port`·`operations.lint_interval_hours`·`operations.max_concurrent_vaults`·`operations.retry.*`·`operations.disk.*`·`operations.fatal_webhook_url`·`operations.fatal_webhook_timeout_sec`·`operations.instance_label`·`operations.rclone_min_version`·`operations.rclone_max_version`·`operations.vfs_cache_max_size`·`operations.vfs_refresh_mode`·`agent.*`.

**산출물**: `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml` 정합 상태로 진입 (Step 1 schema 검증의 사전 조건 충족).
```

### 4.6 ADR-0023 보강 항목 (clone scope)

**추가 섹션 (Decision 후)**:
```markdown
### Clone scope (install_scope_reduction feature 추가, 2026-05-17)

`_step2_clone` 과 `_step2_update` 가 sparse-checkout 적용 — 운영 타깃은 운영 필수 path 만 거주.

**Fetch list 정본** (install.sh `WIKIHUB_SPARSE_PATHS` 배열):
- `_system/` — playbooks
- `scripts/` — Python runtime
- `install.sh` — re-run/update
- `wikihub.yaml.example` — `/wh:setup` Step 0 input
- `README.md` — 운영자 참고
- `LICENSE` — legal

**제외 (의도)**: `docs/`·`features/`·`tests/`·`AGENTS.md`·`CLAUDE.md`·`GEMINI.md`·`.gitignore`·`.env*` 등 — AGENTS.md §1 Development Zone 산출물 + 운영 무관 dev 파일.

**Sparse mode**: `--no-cone` — root 파일 단위 정밀 선택 (cone 모드는 root 의 모든 파일 포함 — governance 파일까지 끌고 옴).

**Update path 정합**: `_step2_update` 가 `_apply_sparse_checkout` 을 매 호출 idempotent 호출 — pre-feature 풀-clone 상태에서 sparse 로 전환 시 unwanted dir 자동 cleanup.

**Supersede 아님** — 본 ADR 의 호출·배포 모델 (curl-pipe + clean install) 은 유지. clone scope 만 보강.
```

### 4.7 ADR-0031 신규 골격

**파일**: `docs/adr/0031-yaml-template-materialization.md`

```markdown
# ADR-0031: wikihub.yaml template materialization 정책

- **Status**: Proposed
- **Date**: 2026-05-17
- **Feature**: features/20260517_install_scope_reduction
- **Supersedes**: 없음
- **Superseded by**: 없음
- **Related**: ADR-0010 (운영 도구 책임 분할), ADR-0023 (install distribution), ADR-0009 (setup 책임)

## Context
install.sh + /wh:setup 두 곳에 분산된 yaml writer 책임을 단일화 + install-derived 필드 자동 patching 정책 lock 필요.

## Considered Options
- (α) install.sh 에서 patching (현재 + 보강)
- (β) /wh:setup Step 0 단독 (본 ADR 채택안)
- (γ) sidecar meta 파일로 derive — install.sh 가 `.install_meta` 작성, /wh:setup 이 read

## Decision
**채택**: (β) /wh:setup Step 0 단독.

(상세 본문은 Step 3 구현 시 작성 — 정책 catalog · drift fix · maintainer field 경계)

## Consequences
- 긍정: yaml writer 단일성, ADR-0010 경계 명료, idempotency 자연
- 부정/제약: /wh:setup 첫 호출 의무 — 미호출 시 wikihub.yaml 부재 (단 install.sh 안내문이 첫 단계로 명시)
```

---

## 5. 연계 룰/스킬 정합성 검토

| 정본 | 정합 영향 | 비고 |
|---|---|---|
| AGENTS.md §1 (Dev/Ops Zone 분리) | ✅ 본 feat 가 invariant 정합 강화 | 핵심 motivation |
| AGENTS.md §3 (feature workflow) | 본 feat 가 절차 정합 — Step 1·2·3·4 수행, Step 5 deferred | plan.md 준수 |
| **ADR-0009** (setup 책임) | **필수 보강** (v2 — MED-A3) — §"read-only" 정정 + §4 신규 (yaml writer Step 0 + Step 6) | Note 완료 (Step 3 전) |
| **ADR-0010** (운영 도구 책임 분할) | **필수 보강** (v2 — CRIT-A1) — yaml.example 복사 sub-decision 이 ADR-0031 으로 reassign. line 38·49·80 supplement | Note 완료 (Step 3 전), ADR-0031 의 `Partially supersedes` 와 짝 |
| ADR-0022 (첫 ingest 진입점) | Step 6 의 raw replace 가 `atomic_yaml_write` helper 호출로 교체 — supplement (v2: CRIT-A2 — 본 feature 흡수) | setup.md Step 6 spec 갱신 (Step 3) |
| ADR-0023 (install distribution) | 보강 (clone scope 항목) — supersede 아님 | §4.6 |
| **ADR-0030** (update workflow) | **필수 보강** (v2 — HIGH-S1) — sparse-checkout 영속화 + rollback 시 governance 파일 비복구 의도 | Note 완료 (Step 3 전) |
| **ADR-0031** (yaml template materialization) | 본 feature 신설 (Proposed → Step 3 후 Accepted). v2 가 design review 반영 | §4.7 |
| `scripts/lib/config.py:156` (remediation 메시지) | "install.sh 가 .example 복사" 문구 갱신 — "/wh:setup 호출 필요" | 메시지 한 줄 갱신 (Step 3) |
| `scripts/lib/config.py` schema 검증 | `mount_path != local_path` soft warn (v2 — HIGH-A1) | Step 3 |
| `scripts/lib/yaml_writer.py` (신규) | Step 0 + Step 6 단일 helper — `atomic_yaml_write(path, data, *, round_trip=True)` (v2 — CRIT-A2) | Step 3 |
| `scripts/requirements.txt` | `ruamel.yaml==0.18.6 --hash=sha256:<TBD>` 1줄 추가 (v2 — MED-S3) | Step 3 |
| `_system/commands/ingest.md`·`lint.md`·`query.md`·`graphify.md` | 영향 없음 (yaml 의미론 무변경) | 정합 OK |
| `wikihub.yaml.example` 본문 | 위치 유지, schema 무변경 | — |
| **`features/backlog.md`** | #E·#F closure 표기 (v2 — LOW-A1) — Step 3 구현 직후 backlog 본문 갱신 의무 | update_mode 의 #A·#B·#C·#D closure 패턴 정합 |

**중복 정의 검출**: 없음. /wh:setup Step 6 의 `bootstrap_allowed` 환원은 Step 0 의 maintainer-controlled 필드 list 에 포함 → Step 0 미관여 → 충돌 없음.

---

## 6. 미결 사항 — 결정 (사용자 confirm 2026-05-17, "U1~U6 추천 그대로 lock")

> 결정의 정본은 ADR-0031 (yaml policy) 및 ADR-0023 보강 본문 (clone scope). 본 표는 옵션 탐색 보존용.

### U1 — sparse-checkout fetch list

**옵션 탐색**:
- (a) `_system`·`scripts`·`install.sh`·`wikihub.yaml.example`·`README.md` 5개
- (b) (a) + `LICENSE` (6개)
- (c) (b) + 개별 file 명시 (redundant)

**결정**: **(b)**. 6 path: `_system`·`scripts`·`install.sh`·`wikihub.yaml.example`·`README.md`·`LICENSE`. ADR-0023 보강 §"Clone scope" 정본.

### U2 — Step 0 patching 필드 범위

**옵션 탐색**:
- (a) instance.root 파생 4개만
- (b) (a) + `operations.gws_min_version`
- (c) (b) + rclone 버전
- (d) (c) + agent.binary auto-detect

**결정**: **(b)**. 5개 필드 (`instance.root`·`vaults[*].local_path`·`vaults[*].options.mount_path`·`vaults[*].options.credentials_path`·`operations.gws_min_version`). ADR-0031 §Decision catalog.

### U3 — idempotent drift fix 정책

**옵션 탐색**:
- (a) Strong sync (덮어쓰기)
- (b) First-only (영구 보존)
- (c) Confirm + 비대화 fallback=보존

**결정**: **(c)**. update_mode invariant 정합. ADR-0031 §Decision Drift Policy.

### U4 — ADR 분리 정책

**옵션 탐색**:
- (a) ADR-0023 보강 단독
- (b) ADR-0023 보강 + ADR-0031 신설

**결정**: **(b)**. 두 결정 분리: clone scope (ADR-0023 보강) + yaml materialization (ADR-0031 신설).

### U5 — `_step2_update` 정합

**옵션 탐색**:
- (a) `_apply_sparse_checkout` 매 update 호출
- (b) clone path 만 관여

**결정**: **(a)**. pre-feature 풀-clone 운영 서버 자동 전환 보장. ADR-0023 보강 §"Update path 정합".

### U6 — `.example` placeholder convention

**옵션 탐색**:
- (a) Default literal + PyYAML round-trip
- (b) 명시 `{{var}}` placeholder
- (c) (a) + ruamel.yaml (주석 보존)

**결정**: **(c)**. ruamel.yaml 0.18+ 을 `scripts/requirements.txt` 에 추가. ADR-0031 §Decision Round-trip Engine.

---

## 7. Definition of Done

### 7.1 기능 DoD

- [ ] **F1**: install.sh 재호출 후 `$WIKIHUB_HOME` 디렉토리 listing 에 `docs/`·`features/`·`tests/`·`AGENTS.md`·`CLAUDE.md`·`GEMINI.md` 없음.
- [ ] **F2**: install.sh 호출 직후 `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml` **존재하지 않음** (Step 5 cp 삭제 검증).
- [ ] **F3**: `/wh:setup` 첫 호출이 `wikihub.yaml` 을 `.example` + derived 값으로 atomic 생성 + Step 1 schema 검증 통과.
- [ ] **F4**: `WIKIHUB_INSTANCE_ROOT=/custom/path bash install.sh` → `/wh:setup` 후 wikihub.yaml 의 `instance.root: /custom/path` 정합 + 모든 derived path 정합.
- [ ] **F5**: `/wh:setup` 재호출 시 install-derived 필드 drift 검출 동작 (U3 정책 정합).
- [ ] **F6**: `/wh:setup` 재호출 시 maintainer-controlled 필드 (`vaults[*].options.root_folder_id` 등) 미관여 (보존).
- [ ] **F7**: `_step2_update` 가 pre-feature 풀-clone 운영 서버에서도 sparse 전환 idempotent.

### 7.2 정합 DoD

- [ ] **C1**: AGENTS.md §1 Dev/Ops Zone 분리 invariant 정합 (운영 타깃에 governance 산출물 0건).
- [ ] **C2**: ADR-0010 의 "install.sh = OS bootstrap / `/wh:setup` = yaml 정합" 경계 강화 — yaml writer 단일성. **v2: ADR-0010 본문에 Note 추가 (line 38·49·80 의 sub-decision supplement)**.
- [ ] **C3**: ADR-0023 본문 보강 ("clone scope" 항목 추가, supersede 아님).
- [ ] **C4**: ADR-0031 신설 + Status `Accepted` (Step 3 완료 + V<N> 검증 통과 후).
- [ ] **C5**: `_system/commands/setup.md` Step 0 추가 + "install.sh와의 관계" 표 + 출력 산출물 표 갱신.
- [ ] **C6**: `scripts/lib/config.py:156` remediation 메시지 갱신 (`/wh:setup` 호출 의무 명시).
- [ ] **C7** (v2 — MED-A3): `docs/adr/0009-setup-responsibility.md` Note 추가 — "read-only" 정정 + §4 yaml writer 추가.
- [ ] **C8** (v2 — HIGH-S1): `docs/adr/0030-update-workflow-orchestration.md` Note 추가 — sparse-checkout 영속화 + rollback 시 governance 파일 비복구.
- [ ] **C9** (v2 — CRIT-A2): `scripts/lib/yaml_writer.py` 신규 — `atomic_yaml_write` 단일 helper, Step 0 + Step 6 둘 다 호출 (Step 6 raw replace migrate).
- [ ] **C10** (v2 — HIGH-A1): `scripts/lib/config.py` schema 검증에 `mount_path != local_path` soft warn 추가.
- [ ] **C11** (v2 — LOW-A1): `features/backlog.md` 의 #E·#F entry closure 표기 (Step 3 구현 직후 backlog 본문 갱신, `~~#E~~`/`~~#F~~` + "✅ closed by …").

### 7.3 회귀 방지 DoD

- [ ] **R1**: update_mode 의 `_step2_update` 정본 호환 (rollback trap·systemd grace 무변경) — **v2 추가**: `_apply_sparse_checkout` 호출 위치가 `git reset --hard` 직후로 lock + `_rollback_if_failed` 본문에 helper 호출 명시 (HIGH-S1).
- [ ] **R2**: `/wh:setup` 의 Step 1·2·3·4·5·5.5·6 기존 동작 무변경 — **v2 단서**: Step 6 의 yaml write 메커니즘만 helper 호출로 교체 (의미론 무변경 — `bootstrap_allowed` 변경 결과 동일).
- [ ] **R3**: ingest·lint·query 명령 동작 무변경 (yaml schema 무변경).
- [ ] **R4** (v2 신규): Step 0 의 schema version 검증이 v0.1.0 → v0.1.0 case 에서 통과 (HIGH-A2).
- [ ] **R5** (v2 신규): drift detection 의 비대화 fallback 이 exit 1 → systemd OnFailure → ops-alert 1회 (HIGH-S3, ADR-0024 dedup 정합).

---

## 8. 검증 계획 (Step 4 후 V<N> phase — Step 5 deferred 라 deploy 검증은 보류)

| V | 시나리오 | 기대 |
|---|---|---|
| V1 | 신규 VM 에서 curl-pipe install.sh (wikihub-test-clean) | `$WIKIHUB_HOME` listing 에 운영 필수 6개만 |
| V2 | 동일 VM 에서 install.sh 재호출 (update path) | sparse state 유지, 재clone 없음 |
| V3 | pre-feature 풀-clone 상태 (wikihub-test 의 현 상태) 에서 install.sh (update) | unwanted 디렉토리 자동 삭제 |
| V4 | /wh:setup 첫 호출 | wikihub.yaml 생성 + Step 1 통과 |
| V5 | `WIKIHUB_INSTANCE_ROOT=/custom` install.sh + /wh:setup | wikihub.yaml 의 instance.root + 파생 path 정합 |
| V6 | /wh:setup 재호출 (drift 없음) | Step 0 no-op + Step 1+ 정상 |
| V7 | yaml 의 `instance.root` 수동 변경 (대화 모드) 후 /wh:setup | drift 검출 + confirm prompt default `N` (LOW-S2) → 유지 |
| V8 | yaml 의 `vaults[0].options.root_folder_id` 수동 편집 후 /wh:setup | 유지 (maintainer field 미관여) |
| V9 | 비대화 모드 (`WIKIHUB_NONINTERACTIVE=1`) 에서 drift | 보존 + 보고 + **exit 1** (v2 — HIGH-S3) → systemd OnFailure → ops-alert 1회 |
| V10 | ruamel round-trip 후 yaml 주석 보존 확인 | .example 의 주석이 operational yaml 에 살아있음 (Step 0 + Step 6 둘 다) |
| **V11** (v2 신규 — HIGH-A2) | pre-feature v0.1.0 yaml 보유 운영 서버 (full clone + 기존 wikihub.yaml) 에서 update → /wh:setup | Step 0 가 schema version v1 == v1 검증 통과 + `gws_min_version` 빈 문자열 drift 검출 + (비대화) exit 1 또는 (대화) confirm → patching |
| **V12** (v2 신규 — HIGH-A1) | `mount_path` 를 `local_path` 와 다른 값으로 명시 분리 후 /wh:setup | Step 0 미관여 (catalog 외) + Step 1 schema 검증 soft warn 만 출력, fail 안 함 |
| **V13** (v2 신규 — CRIT-A2) | Step 6 의 `bootstrap_allowed` 환원 후 yaml 주석 보존 | Step 0 가 보존한 주석이 Step 6 후에도 유지 (helper 단일성 검증) |
| **V14** (v2 신규 — HIGH-S1) | update 도중 `git reset --hard` 직후 인위적 fail trigger | `_rollback_if_failed` 가 `_apply_sparse_checkout` 호출 + journal 로그 "sparse re-apply (intended)" 가시화 + governance 파일 미복구 정합 |
| **V15** (v2 신규 — MED-S2) | `_install_gws` 후 `$WIKIHUB_HOME/_system/INSTALLED_VERSIONS.json` 정합 | file 존재 + `gws` field 가 installed version, Step 0 가 read |
| **V16** (v2 신규 — HIGH-S3) | install.sh 직후 `/wh:setup` 없이 systemd timer enable (운영자 실수) | vault@.service 가 `wikihub.yaml 없음` → exit 2 → OnFailure → ops-alert 발화 (mitigation: `_step8_guide` 의 warn 안내) |

---

## 9. 다음 단계

v1 (2026-05-17):
1. ✅ 사용자가 U1~U6 추천 confirm.
2. ✅ ADR-0031 본문 작성 → `Proposed`.
3. ✅ Step 2 design review — 멀티모델 검토 완료 (`design_review_1.md` SRE + `design_review_2.md` Spec).

v2 (2026-05-18):
4. ✅ design review CRIT 2건 + HIGH 5건 + MED 6건 + LOW 2건 일괄 반영 (본 문서 v2 + ADR-0031 v2 + ADR-0009·0010·0030 Note).
5. ⏳ **사용자 승인 대기** (`approved: YYYY-MM-DD` 마커 추가).
6. ⏳ Step 3 진입 — `install.sh`·`_system/commands/setup.md`·`scripts/lib/yaml_writer.py`·`scripts/lib/config.py`·ADR-0023 보강·ADR-0031 status `Accepted` 일괄 구현.
7. ⏳ Step 4 — code review 멀티모델 (R≥2) + V1~V16 검증 시나리오 실행.

---

## 10. v2 변경 이력 (2026-05-18)

design_review_1.md (SRE/Systems persona) + design_review_2.md (Spec/Architecture persona) 의 finding 일괄 반영.

### 본 문서 (analysis_and_design.md) 변경 catalog

| 변경 | 반영 finding | 영역 |
|---|---|---|
| 헤더 영역에 v1/v2 명시 + review 산출 cross-ref | (formatting) | 메타 |
| §1.2 Invariant B 명료화 — "/wh:setup 단독" + "내부에서도 단일 helper" 추가 | CRIT-A2 | §1.2 |
| §3.1 표 — `_step2_clone` blob filter 제거 (HIGH-S2), `_step2_update` 위치 정정 (HIGH-S1), `_install_gws` sidecar 작성 (MED-S2), `_step8_guide` warn 안내 + update path 분기 (HIGH-S3) | HIGH-S1·S2·S3, MED-S2 | §3.1 |
| §3.2 표 — Step 1 mount_path soft warn (HIGH-A1), Step 6 helper migrate (CRIT-A2), 표 cell wording lock (LOW-A2) | CRIT-A2, HIGH-A1, LOW-A2 | §3.2 |
| §3.3 표 — ADR-0009·0010·0030 행 추가 + "보강 후보" → "필수 보강" 격상 + 신규 파일 (`yaml_writer.py`, `requirements.txt`, backlog.md) 추가 | CRIT-A1, MED-A3, HIGH-S1, LOW-A1 | §3.3 |
| §3.4 비영향 — yaml_writer.py / requirements.txt / config.py soft warn / `_install_gws` sidecar 보강 | (multi) | §3.4 |
| §4.2 After 블록 — blob filter 제거 + 사유 comment | HIGH-S2 | §4.2 |
| §4.3 After 블록 — `_apply_sparse_checkout` 위치 정정 + `_rollback_if_failed` 본문 명시 | HIGH-S1 | §4.3 |
| §5 정합성 검토 표 — ADR-0009·0010·0030 행 격상 + 신규 파일 행 추가 | CRIT-A1, MED-A3, HIGH-S1 | §5 |
| §7.2 정합 DoD — C7~C11 추가 (ADR Note · helper · soft warn · backlog closure) | CRIT-A1, CRIT-A2, MED-A3, HIGH-S1, HIGH-A1, LOW-A1 | §7.2 |
| §7.3 회귀 방지 DoD — R1 단서 + R4·R5 신규 | HIGH-S1, HIGH-S3, HIGH-A2 | §7.3 |
| §8 검증 계획 — V11·V12·V13·V14·V15·V16 신규 + V7·V9·V10 단서 갱신 | HIGH-A2, HIGH-A1, CRIT-A2, HIGH-S1, MED-S2, HIGH-S3, LOW-S2 | §8 |
| §9 다음 단계 — v1·v2 progress 명시 | (process) | §9 |

### 본 feature 의 다른 산출물 갱신

- `docs/adr/0031-yaml-template-materialization.md` → **v2** (Partially supersedes ADR-0010, Step 6 helper 흡수, 4필드 catalog, §E schema version, exact pin + hash, single-writer invariant, 비대화 fallback exit 1)
- `docs/adr/0010-operational-tooling-split.md` → **Note 추가** (yaml.example 복사 책임 ADR-0031 reassign)
- `docs/adr/0009-setup-responsibility.md` → **Note 추가** (read-only 정정 + §4 yaml writer)
- `docs/adr/0030-update-workflow-orchestration.md` → **§부정/제약 Note 추가** (sparse-checkout 영속화 + rollback governance 파일 비복구)

### 미반영 finding (의도적 deferred)

| Finding | 사유 |
|---|---|
| LOW-S1 (LICENSE 표현 약화) | LICENSE 는 ADR-0023 보강 §"Clone scope" 의 1줄 표현 문제 — Step 3 의 ADR-0023 본문 작성 시 wording 정합. 본 문서 v2 의 §변경 대상 아님 |

LOW-S1 외 모든 finding 반영. design review 의 "Approve with major changes" 권고 충족.
