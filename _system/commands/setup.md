# /wh-setup

`wikihub.yaml`(운영 정본) **생성 + 검증**, wiki/`_state/` 디렉토리 ensure, systemd unit 동기화, agent skill 메타 갱신. **install.sh가 1회 bootstrap을 끝낸 뒤** 호출.

## 호출

```
<agent_invocation> "/wh-setup"                # yaml materialize (첫 호출) 또는 drift sync + 검증 + unit 동기화
<agent_invocation> "/wh-setup --enable"       # 추가로 systemctl --user enable --now까지 수행
```

- **트리거**: 메인테이너 수동 (timer 아님 — `/wh-setup` 자체가 timer 설정 명령)
- **호출 시점**:
  - **install.sh 직후 (첫 호출)** — Step 0 가 `.example` 으로부터 `wikihub.yaml` 생성 (ADR-0031)
  - yaml maintainer field 편집 완료 후 (운영 시작)
  - vault 추가·삭제 후
  - `sync_interval_sec` 또는 `lint_interval_hours` 변경 후
  - unit template 갱신 후 (install.sh로 정본 update 후)

## 사전 조건

- install.sh가 OS bootstrap·venv·deps·skill 등록을 완료 (ADR-0010)
- `$WIKIHUB_HOME/wikihub.yaml.example` 존재 (sparse-checkout fetch list, ADR-0023)
- `$WIKIHUB_HOME/_system/INSTALLED_VERSIONS.json` 존재 권장 (Step 0 의 `gws_min_version` source, ADR-0031 §Decision B)
- `~/.config/systemd/user/` 쓰기 권한
- F4 산출물인 unit template이 `_system/systemd/`에 존재 (install.sh가 fetch)

## 절차

### Step 0. wikihub.yaml materialization · schema version 검증 · drift fix (ADR-0031)

본 Step 은 `/wh-setup` 의 **yaml writer 책임**의 정본 (ADR-0009 §4 + ADR-0031 §Decision A·B·C·E).
yaml 의 시작·끝 책임은 `/wh-setup` 단독 — install.sh 는 yaml 미관여.

#### Step 0.1. Schema version 검증 (ADR-0031 §Decision E)

```python
example_data = yaml_writer.load_yaml_rt(Path("$WIKIHUB_HOME/wikihub.yaml.example"))
example_version = int(example_data["version"])

if target.exists():
    operational_data = yaml_writer.load_yaml_rt(target)
    operational_version = int(operational_data.get("version", 1))
    if operational_version != example_version:
        fail_fast(
            reason=f"schema version mismatch: operational v{operational_version} vs example v{example_version}",
            remediation="install.sh --version <prev-tag> 로 rollback 또는 schema migration guide 참조",
        )
```

v1 → v1 만 지원 (v0.1.0). v2 도입 시 별도 ADR.

#### Step 0.2. Materialize 또는 Drift Sync 분기

##### Case A — `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml` 부재

1. `yaml_writer.load_yaml_rt($WIKIHUB_HOME/wikihub.yaml.example)` 로 round-trip load (주석 보존).
2. **Derived 4필드 patching** (ADR-0031 §Decision B catalog):
   - `instance.root` → `$WIKIHUB_INSTANCE_ROOT` env
   - `vaults[*].local_path` → `<instance.root>/vault/<vault.id>`
   - `vaults[*].options.credentials_path` → `<instance.root>/.credentials/sa_<vault.id>.json`
   - `operations.gws_min_version` → `$WIKIHUB_HOME/_system/INSTALLED_VERSIONS.json` 의 `gws` 필드 (file 부재 시 `gws --version` stdout fallback)
3. `yaml_writer.atomic_yaml_write($WIKIHUB_INSTANCE_ROOT/wikihub.yaml, data, round_trip=True)` (`scripts/lib/yaml_writer.py` — PID-suffix `.tmp` + fsync + os.replace).
4. 보고:
   ```
   wikihub.yaml 생성 완료 (.example → operational, 4 필드 patching 적용).
   다음 단계: maintainer field 편집 (vault id, root_folder_id, enabled, bootstrap_allowed,
   fatal_webhook_url, instance_label 등) 후 /wh-setup --enable 재호출.
   ```
5. Step 1 진입.

##### Case B — `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml` 존재

1. `yaml_writer.load_yaml_rt(target)` 로 round-trip load.
2. Step 0.1 의 schema version 검증.
3. **Drift 검출** — derived 4필드 각각:
   - 현재 값 vs 예상값 (env / install-time fact 기반).
   - drift 의 source 분류 — "install-time env 와 매번 mismatch" vs "derived 만 mismatch".
4. drift 있는 필드 0건 → Step 0 no-op. Step 1 진입.
5. drift 1건 이상:
   - **대화 모드** (`/dev/tty` 있음 + `WIKIHUB_NONINTERACTIVE` 미설정 + `SKIP_CONFIRM` 미설정):
     - 각 drift 필드 보고 (현재 값 vs 예상값 + source 분류).
     - prompt (default 보수 — LOW-S2 design review):
       ```
       위 변경은 install-time env 값으로 yaml 을 덮어씁니다.
       메인테이너 hand-edit 가 있으면 N 선택. [y/N] (default N)
       ```
     - `Y` → `yaml_writer.atomic_yaml_write(target, data, round_trip=True)` 재기록.
     - `N` → 보존 + "재호출 시 다시 prompt" 안내. Step 1 진입 (exit 0).
   - **비대화 모드** (`WIKIHUB_NONINTERACTIVE=1` 또는 `/dev/tty` 부재):
     - drift 보고 (stderr) + 보존.
     - **exit 1** (HIGH-S3 design review — silent mismatch 회피). systemd OnFailure → ops-alert 1회 트리거 (ADR-0024 dedup 정합).

#### Step 0.3. 미관여 필드 invariant (ADR-0031 §Decision B "미관여 필드")

위 4필드 외 **모든 yaml 필드**는 maintainer-controlled — Step 0 절대 미관여. 명시 예시:
- `version`, `instance.timezone`
- `vaults[*]`: `id`·`enabled`·`type`·`sync_interval_sec`·`options.root_folder_id`·`options.exclude_shared_with_me`·`options.max_file_size_mb`·`options.bootstrap_allowed`·`options.mount_path`·`options.rclone_remote_name`·`options.rclone_rc_port`
- `operations`: `lint_interval_hours`·`max_concurrent_vaults`·`retry.*`·`disk.*`·`fatal_webhook_url`·`fatal_webhook_timeout_sec`·`instance_label`·`rclone_min_version`·`rclone_max_version`·`vfs_cache_max_size`·`vfs_refresh_mode`
- `agent.*` 전체

특히 `mount_path` 는 Path C+ default 패턴에선 `local_path` 와 동일하지만, advanced 운영자가 bind-mount / ramdisk / multi-vault layout 분리로 명시 분리 가능 (HIGH-A1 design review). Step 1 schema 검증의 soft warn 만 발생, Step 0 미관여.

### Step 1. 환경 검증 (Step 0 후 — yaml writer 분기와 분리)

검증 항목 (실패 항목은 수집해 보고):

- **wikihub.yaml 스키마**: `version == 1`, `instance.root` **(없으면 mkdir -p — 운영자가 yaml의 `instance.root`를 install.sh 기본값 외로 편집한 경우 자동 생성, 이후 쓰기 권한 검증)**, 각 `vaults[*]`의 `id` 형식(`^[a-z][a-z0-9_]*$`)·`type`·`enabled`·`sync_interval_sec ≥ 60`·`local_path` (없으면 mkdir + 쓰기 권한 검증), `operations.lint_interval_hours ≥ 1`, `agent.binary` 실행 가능 (`agent.type`별 ADR-0012 매핑 정합). **`operations.disk.*` 스키마는 F4 산출물(`wikihub.yaml.example`)에서 정의됨 — F4 완료 전까지 본 항목 검증 생략 가능 (L1)**
  - **CRIT-R10-2**: `instance.root` 디렉토리 ensure 가 본 Step의 명시적 책임. 미존재 시 unit template의 `WorkingDirectory={instance_root}`가 `203/CHDIR`로 즉시 fail → OnFailure → ops-alert 매 사이클 발화. **추가 안전망**으로 unit template `ExecStartPre=/bin/mkdir -p {instance_root}` 보유 (정상 운영에서는 redundant, yaml 편집 직후 reboot 등 race window 방어).
- **OAuth 토큰 유효성** (enabled gdrive_api vault만): 각 vault의 `credentials_path` 파일 존재 + 권한 600 + load 가능 + valid 또는 refresh 가능
  - **권한 검증 추가 (O8)**: `creds.valid` 확인 후 light API call(`drive.about.get` 등)로 실제 Drive 접근 가능 여부 검증. 401/403 발생 시 보고 + 해당 vault 제외 (해당 vault unit 생성 skip)
- **wiki/ 디렉토리**: 4 카테고리(`sources/`, `entities/`, `concepts/`, `analyses/`) + `_lint/` + 각 vault별 `sources/{vault_id}/` 존재 (없으면 생성)
- **_state/ 디렉토리**: 각 enabled vault의 `_state/{vault_id}/` + 초기 state 파일 (없을 때만 — ADR-0007 all JSON, `pending_ingest.json`은 제외)
  - **초기 파일 형식 (L2 정본)**:
    - `cursor.json` → `{"vault_id": "<id>", "vault_type": "<type>", "cursor": "", "cursor_updated_at": null}`
    - `file_map.json` → `{"vault_id": "<id>", "updated_at": null, "files": {}}`
    - `retry.json` → `{"vault_id": "<id>", "next_id": 1, "queue": []}`

실패 시: stdout 상세 보고 + exit 1. unit 동기화는 일부만 진행하거나 전체 중단 (정책: 스키마 위반은 전체 중단, OAuth 토큰 무효는 해당 vault만 unit 갱신 제외).

### Step 2. systemd unit 동기화 (책임 이관 — 2026-05-17, ADR-0030)

> **책임 이관 (update_mode feature, ADR-0030)**: v0.1.0 의 update_mode feature 부터 **systemd unit template 의 render·daemon-reload 책임은 install.sh 로 이관**. `/wh-setup` 은 본 Step 2 를 더 이상 수행하지 않음. 이유:
>
> 1. install.sh 가 정본 변경 (`_system/systemd/*.template` 갱신) 직후 자동 render → unit 갱신 race window 차단.
> 2. install.sh 가 hermes·F5 가용성과 독립적으로 동작 — F5 미완 상태에서도 update path full functional.
> 3. `/wh-setup` 은 hermes skill 메타 갱신·yaml validate·first ingest prompt 책임으로 축소.
>
> install.sh 의 책임:
> - `scripts/_helpers/render_systemd_units.py --render --out ~/.config/systemd/user/` 호출.
> - 2-pass substitution + idempotent atomic write + enabled=false vault 의 stale unit 정리.
> - render 후 `systemctl --user daemon-reload`.
> - 대상 unit 목록 · 치환 변수 · substitution 순서의 정본 spec 은 [features/20260517_update_mode/analysis_and_design.md §6.1](../../features/20260517_update_mode/analysis_and_design.md#61-scripts_helpersrender_systemd_unitspy-contract) 의 helper Contract.
>
> 본 step 은 호환을 위해 placeholder 로 유지 — `/wh-setup` 이 호출됐을 때 운영자 안내만:
>
> ```
> Step 2: skip — install.sh 가 systemd unit render 책임 (ADR-0030).
>         최신 spec 적용은 \`install.sh\` 재호출.
> ```

### Step 3. agent skill 메타 갱신

agent CLI에 wikihub skill의 메타(vault 목록, 운영 모드 등) 알림. 변경된 항목:
- 신규/제거된 vault → skill description 갱신
- skill_prefix가 fallback으로 변경된 경우 (install.sh가 yaml에 기록한 값을 agent에 전달)

agent별 메커니즘은 install.sh가 1회 등록 시 결정. /wh-setup은 그 등록 상태를 재확인·갱신만.

### Step 4. systemd 반영 (v0.1.0 v5 — ADR-0022 흐름 역전 정합)

- `systemctl --user daemon-reload`
- `--enable` 플래그 시: `lint.timer` (+ 조건부 `disk-watch.timer`) **만** `enable --now`. **vault-ingest.timer 는 Step 6 결과에 위임** — 첫 ingest 성공한 vault 만 enable.
- 미플래그 시: 권장 액션 출력만.

### Step 5. 보고

```
SETUP 결과 — 2026-05-13 15:30 KST

✓ wikihub.yaml 스키마 OK (1 vault enabled: gdrive)
✓ vault gdrive: OAuth 토큰 유효 (Workspace Internal, refresh 가능)
✓ wiki/ 디렉토리: 생성 0, 기존 5
✓ _state/gdrive/: 생성 0, 기존 3
✓ agent skill_prefix: wh-

systemd unit 갱신:
  gdrive-ingest.service (interval 600s)
  gdrive-ingest.timer
  lint.service (interval 24h)
  lint.timer
  ops-alert.service

daemon-reload 완료.

다음 권장 액션 (--enable 미사용 시):
  systemctl --user enable --now gdrive-ingest.timer lint.timer
  systemctl --user list-timers
```

### Step 5.5. rclone Service Account 등록 (ADR-0025 Path C+ + ADR-0029 SA 정본, vault 별 1회성)

**진입 조건**: Step 1~5 통과 + `vaults[*].options.rclone_remote_name` 정의 + `~/.config/rclone/rclone.conf` 의 해당 remote 미등록 + `~/wikihub-instance/.credentials/sa_<vault_id>.json` 배치 완료 (SA JSON key, chmod 0600).

**SA 사전 준비** (메인테이너 1회):
1. Google Cloud Console → IAM & Admin → Service Accounts → "Create service account"
2. Drive API 활성화 (Cloud Console → APIs & Services → Library → "Google Drive API" → Enable)
3. SA 의 키 발급: Service Accounts → 본 SA → Keys → "Add Key" → "Create new key" → JSON → download
4. **dev box (macOS) 로컬 보관** — repo working tree 외부 격리:
   ```bash
   mkdir -p ~/.credentials/wikihub && chmod 0700 ~/.credentials ~/.credentials/wikihub
   mv ~/Downloads/<project>-<hash>.json ~/.credentials/wikihub/sa_<project>.json
   chmod 0600 ~/.credentials/wikihub/sa_<project>.json
   ```
   repo 내부에 절대 두지 말 것 — `.gitignore` 패턴 의존 금지 (메인테이너 가이드 §1 Separation of Concerns).
5. **운영 VM/서버 로 scp**:
   ```bash
   ssh user@oci 'mkdir -p ~/wikihub-instance/.credentials && chmod 0700 ~/wikihub-instance/.credentials'
   scp ~/.credentials/wikihub/sa_<project>.json user@oci:~/wikihub-instance/.credentials/sa_<vault_id>.json
   ssh user@oci 'chmod 0600 ~/wikihub-instance/.credentials/sa_<vault_id>.json'
   ```
   로컬 파일명은 `sa_<project>.json` (Cloud project 1:1), 운영 파일명은 `sa_<vault_id>.json` (vault 1:1 — yaml `credentials_path` 와 정합).
6. Drive vault 폴더 (`root_folder_id`) UI → "Share" → SA 이메일 (`<sa>@<project>.iam.gserviceaccount.com`) **Editor** 권한 부여

**Interactive mode** (default — 운영자가 SSH 세션 에 직접 입력):

1. `rclone config` 실행 — 안내
2. `n` (new remote) → name 입력 (`wikihub.yaml.vaults.<id>.options.rclone_remote_name` 과 정합, 권장: `gdrive`)
3. type 선택: `18` (drive)
4. client_id/secret: 빈칸 (rclone 기본 사용)
5. scope: `1` (full access)
6. **service_account_file**: `~/wikihub-instance/.credentials/sa_<vault_id>.json` (절대 경로) — SA JSON key (ADR-0029)
7. Edit advanced config: `n`
8. Use auto config — SA 채택 시 browser OAuth flow 불필요, 자동 skip
9. Configure as Shared Drive: `n` (메인테이너 Personal Drive 의 폴더 공유 모델)
10. 완료 후 `~/.config/rclone/rclone.conf` 에 `[<remote_name>]` + `service_account_file = ...` 라인 확인
11. **`chmod 0600 ~/.config/rclone/rclone.conf`** 실행 — SA 키 경로 노출 차단 (v9 R12-MED-2 정합)

**Non-interactive 빠른 등록** (권장 — ADR-0029 자동화 친화):
```bash
rclone config create <remote_name> drive \
    scope=drive \
    service_account_file=$HOME/wikihub-instance/.credentials/sa_<vault_id>.json
chmod 0600 ~/.config/rclone/rclone.conf
```

**검증**:
- `rclone lsd <remote_name>:` 로 SA 동작 확인 (Drive root listing — SA 공유받은 폴더만 보임)
- 실패 시: SA 이메일이 폴더에 공유됐는지 + `private_key` 유효성 (Cloud Console → SA → Keys 의 상태 확인)

**책임 분배 (v9 R12-MED-2)**:

| 책임자 | 위치 | 시점 |
|---|---|---|
| install.sh §Step 4.5 `_enforce_rclone_conf_perms` | 자동 chmod 0600 (정본 enforce) | 매 install.sh 호출 |
| setup.md §Step 5.5 step 11 | 운영자 수동 setup 직후 한 번 더 확인 | 첫 OAuth 발급 시 |
| mount.service | `Environment=RCLONE_CONFIG=` 만 주입 (권한 검증은 install.sh 책임) | mount 시작 시 |

ADR-0022 (첫 ingest 진입점) 와 정합 — Step 5.5 가 끝나야 Step 6 진입 가능.

### Step 6. 첫 ingest prompt + timer enable 게이트 (v0.1.0 v5 신설 — ADR-0022)

**진입 조건**: `--enable` 플래그 + Step 1~5 통과 + `bootstrap_allowed: true` vault 1개 이상.

**동작**:

1. enabled vault 중 `bootstrap_allowed: true` 인 vault 별로 prompt:
   ```
   vault 'gdrive' 의 첫 ingest 를 지금 실행하시겠습니까? [Y/n] (default Y)
   ```
   비대화 모드 (`--run-first-ingest` / `--skip-first-ingest` / `WIKIHUB_FIRST_INGEST=yes/no` env / `/dev/tty` 부재 시 자동 비대화) 면 prompt skip + 사전 결정 사용.

2. **`Y` 응답**:
   - `vault-fetch.py --vault <id> --bootstrap` 직접 호출 (timer 우회).
   - stdout JSON 보고 + exit code 캡처.
   - **exit 0**: timer enable + `bootstrap_allowed: true → false` atomic write.
   - **exit 75 + cursor 존재**: timer enable + `bootstrap_allowed` 환원 + “일시 결함, 다음 사이클 재시도” 안내.
   - **exit 75 + cursor 미생성**: timer enable **보류** (fatal loop 회피) + “cursor 미생성, 진단 후 수동 enable” 안내.
   - **exit 2**: timer enable **보류** + `last_failure.json` 영속화 (ADR-0024) + “fatal — 진단 후 수동 enable” 안내.

3. **`N` 응답**: vault-fetch + timer enable 모두 skip.

4. **bootstrap_allowed 환원** (`Y` + exit 0/75 with cursor 시):
   - `yaml_writer.load_yaml_rt(target)` → 해당 vault `bootstrap_allowed: True → False` → `yaml_writer.atomic_yaml_write(target, data, round_trip=True)`.
   - **단일 helper 호출** (ADR-0031 §Decision D + CRIT-A2 design review) — Step 0 와 동일 `scripts/lib/yaml_writer.py` 사용. round-trip 모드라 메인테이너 편집한 주석·key 순서·indent 보존.
   - yaml writer 책임은 ADR-0009 §4 (Step 0 + Step 6) + ADR-0022 + ADR-0031 정본.

5. **timer enable** (`Y` + exit 0/75 with cursor 시):
   - `systemctl --user enable --now {vault_id}-ingest.timer`.

**비대화 모드 spec**:

| flag / env | 동작 |
|---|---|
| `--run-first-ingest` | 모든 vault 의 prompt 자동 `Y` |
| `--skip-first-ingest` | 모든 vault 의 prompt 자동 `N` |
| `WIKIHUB_FIRST_INGEST=yes` | `--run-first-ingest` 동등 |
| `WIKIHUB_FIRST_INGEST=no` | `--skip-first-ingest` 동등 |
| 미지정 + `/dev/tty` 부재 | default `Y` |

## 출력 산출물

| 변경 대상 | 조건 |
|---|---|
| `wikihub.yaml` (Step 0 — materialize 또는 drift sync) | 첫 호출: `.example` 으로부터 generate + derived 4필드 patching. 재호출: drift 검출 시 confirm prompt (대화) 또는 exit 1 (비대화). helper = `scripts/lib/yaml_writer.py atomic_yaml_write` (PID-suffix `.tmp` + fsync + os.replace). **ADR-0031 정본** |
| `wiki/` 카테고리 디렉토리 | 없을 때만 생성 |
| `_state/{vault_id}/` 초기 파일 | 없을 때만 생성 |
| `~/.config/systemd/user/*.service`·`*.timer` | 매 호출 시 yaml 값으로 갱신 (덮어쓰기 — yaml이 정본) |
| systemd state | daemon-reload + (선택) enable. **vault-ingest.timer 는 Step 6 결과 위임** |
| agent skill 메타 | 변경 시만 갱신 |
| `wikihub.yaml` (Step 6 — bootstrap_allowed: true → false) | Step 6 의 `Y` + (exit 0 또는 exit 75 with cursor) 시만. **동일 helper `atomic_yaml_write` 호출** (Step 0 와 단일성, CRIT-A2). **ADR-0022 정본** |

## 실패 처리

| 실패 시점 | 동작 |
|---|---|
| wikihub.yaml 스키마 위반 | stdout 보고 + exit 1. unit 동기화 안 함 |
| OAuth 토큰 무효 (일부 vault) | 해당 vault의 unit은 생성하되 enable 권장에서 제외. 보고 + exit 0 |
| OAuth 토큰 무효 (모든 vault) | 보고 + exit 1 (운영 시작 불가 상태) |
| systemd unit 파일 쓰기 실패 | exit 2 (권한 의심) |
| daemon-reload 실패 | exit 2 + ops-alert 트리거 |
| agent skill 갱신 실패 | 보고 + exit 0 (skill 동작 자체에는 영향 없을 가능성. 다음 호출에서 재시도) |
| Step 6 첫 ingest exit 2 | timer enable 보류 + 사용자 안내 + 보고에 "timer 비활성" 명시 + exit 0 (Step 6 자체는 정상 종료) |
| Step 6 첫 ingest exit 75 + cursor 미생성 | timer enable 보류 (exit 2 동등 취급, fatal loop 회피) + 사용자 안내 + exit 0 |
| Step 6 yaml writer 실패 (bootstrap_allowed 환원 실패) | 안내 + timer enable 은 진행 + exit 0 (위생 결함이라 fatal 아님) |

## 멱등성 보장

- 디렉토리·초기 state는 존재 확인 후 생성
- unit 파일은 매번 덮어쓰기 (yaml = always 정본)
- `--enable`은 idempotent

## install.sh와의 관계

ADR-0010 의 도구 split (install.sh = OS bootstrap / `/wh-setup` = wiki·yaml 정합) + ADR-0031 의 yaml writer 단일성 정합. install.sh 는 yaml 미관여.

| 항목 | install.sh (1회 bootstrap + 반복 update) | /wh-setup (첫 호출 + yaml 변경 시 반복) |
|---|---|---|
| OS deps (Python venv, libs) | ✓ | — |
| 정본 파일 fetch (`_system/`, `scripts/`) — sparse-checkout (ADR-0023 §"Clone scope") | ✓ | — |
| `INSTALLED_VERSIONS.json` sidecar 작성 (Step 0 input) | ✓ (`_write_installed_versions_sidecar`, ADR-0031 §Decision B) | — |
| `wikihub.yaml` 생성 (`.example` 으로부터 materialize) | — | ✓ (Step 0 첫 호출 시 generate · 이후 호출 시 drift sync, ADR-0031) |
| `wikihub.yaml` derived 값 patching (4필드) | — | ✓ (Step 0, ADR-0031 §Decision B catalog) |
| `wikihub.yaml` (Step 6 — `bootstrap_allowed` 환원) | — | ✓ (Step 6, ADR-0022 — Step 0 와 동일 helper) |
| `instance.root` mkdir + `.credentials/` chmod 700 | ✓ (`_step5_instance_dirs`) | — |
| credentials chmod 600 enforce | ✓ (`_step5_instance_dirs`) | — |
| agent skill 초기 등록 | ✓ | — (메타 갱신만) |
| wiki/·_state/ 디렉토리 | — | ✓ |
| systemd unit 생성·갱신 (template + yaml 값 instance화) | ✓ (`_step8_systemd_render`, ADR-0030 update_mode 정본) | ✓ (재진입 호출 — `/wh-setup` 단독 호출 시) |
| OAuth 토큰 검증 | — | ✓ |
| daemon-reload·enable | — | ✓ |

## 관련 ADR

- ADR-0003 OAuth (Step 1 토큰 검증)
- ADR-0006 unified orchestration (ExecStart의 명령 형식)
- ADR-0007 state all JSON (Step 1 초기 파일)
- ADR-0008 lint 권한 (lint.timer는 기본 모드만)
- ADR-0009 setup 책임 (본 명령의 정본 — §4 yaml writer 확장 Note 정합)
- ADR-0010 운영 도구 책임 분할 (install.sh와의 경계 — yaml.example 복사 책임은 ADR-0031 으로 reassign)
- ADR-0011 skill namespace prefix (Step 3 메타 갱신 시 prefix 적용)
- ADR-0022 첫 ingest 진입점 (Step 6 — `bootstrap_allowed` 환원, Step 0 와 동일 helper)
- ADR-0030 update workflow orchestration (`_step2_update` + sparse-checkout 영속화)
- ADR-0031 yaml template materialization (Step 0 정본 — 4필드 catalog + drift fix + helper 단일성)
