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
- `$WIKIHUB_HOME/_system/INSTALLED_VERSIONS.json` 존재 권장 (ADR-0031 §Decision B). ADR-0035 후엔 `rclone` 버전만 기록 — `gws` 키 폐기
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

##### Case A — `$WIKIHUB_HOME/wikihub.yaml` 부재

1. `yaml_writer.load_yaml_rt($WIKIHUB_HOME/wikihub.yaml.example)` 로 round-trip load (주석 보존).
2. **Derived 필드 patching** (ADR-0031 §Decision B catalog, ADR-0035 — credentials_path/gws_min_version 폐기):
   - `instance.root` → `$WIKIHUB_HOME` env
   - `vaults[*].local_path` → `<instance.root>/vault/<vault.id>`
3. `yaml_writer.atomic_yaml_write($WIKIHUB_HOME/wikihub.yaml, data)` (`scripts/lib/yaml_writer.py` — PID-suffix `.tmp` + fsync + os_replace, round-trip only).
4. 보고:
   ```
   wikihub.yaml 생성 완료 (.example → operational, derived 필드 patching 적용).
   다음 단계: maintainer field 편집 (vault id, rclone_remote_path, enabled,
   fatal_webhook_url, instance_label 등) 후 /wh-setup --enable 재호출.
   ```
5. Step 1 진입.

##### Case B — `$WIKIHUB_HOME/wikihub.yaml` 존재

1. `yaml_writer.load_yaml_rt(target)` 로 round-trip load.
2. Step 0.1 의 schema version 검증.
3. **Drift 검출** — derived 필드 각각 (ADR-0035 후 2필드):
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
     - `Y` → `yaml_writer.atomic_yaml_write(target, data)` 재기록.
     - `N` → 보존 + "재호출 시 다시 prompt" 안내. Step 1 진입 (exit 0).
   - **비대화 모드** (`WIKIHUB_NONINTERACTIVE=1` 또는 `/dev/tty` 부재):
     - drift 보고 (stderr) + 보존.
     - **exit 1** (HIGH-S3 design review — silent mismatch 회피). systemd OnFailure → ops-alert 1회 트리거 (ADR-0024 dedup 정합).

#### Step 0.3. 미관여 필드 invariant (ADR-0031 §Decision B "미관여 필드")

위 derived 필드 외 **모든 yaml 필드**는 maintainer-controlled — Step 0 절대 미관여. 명시 예시 (ADR-0035 정합):
- `version`, `instance.timezone`
- `vaults[*]`: `id`·`enabled`·`type`·`sync_interval_sec`·`options.exclude_shared_with_me`·`options.max_file_size_mb`·`options.false_delete_threshold`·`options.mount_path`·`options.rclone_remote_name`·`options.rclone_remote_path`·`options.rclone_rc_port`
- `operations`: `lint_interval_hours`·`lint_contradiction_check`·`graphify_enabled`·`max_concurrent_vaults`·`retry.*`·`disk.*`·`fatal_webhook_url`·`fatal_webhook_timeout_sec`·`instance_label`·`rclone_min_version`·`rclone_max_version`·`vfs_cache_max_size`·`vfs_refresh_mode`·`graphify_min_version`·`graphify_max_version`·`graphify_backend`·`graphify_profile`·`graphify_timeout_sec`·`graphify_partial_failure_threshold` (v0.1.7~v0.1.8 신설 field 들)
- `agent.*` 전체 (특히 `agent.models` 의 per-skill model override — ADR-0032 §Note 2026-05-20)

특히 `mount_path` 는 Path C+ default 패턴에선 `local_path` 와 동일하지만, advanced 운영자가 bind-mount / ramdisk / multi-vault layout 분리로 명시 분리 가능 (HIGH-A1 design review). Step 1 schema 검증의 soft warn 만 발생, Step 0 미관여.

### Step 1. 환경 검증 (Step 0 후 — yaml writer 분기와 분리)

검증 항목 (실패 항목은 수집해 보고):

- **wikihub.yaml 스키마**: `version == 1`, `instance.root` **(없으면 mkdir -p — 운영자가 yaml의 `instance.root`를 install.sh 기본값 외로 편집한 경우 자동 생성, 이후 쓰기 권한 검증)**, 각 `vaults[*]`의 `id` 형식(`^[a-z][a-z0-9_]*$`)·`type`·`enabled`·`sync_interval_sec ≥ 60`·`local_path` (없으면 mkdir + 쓰기 권한 검증), `operations.lint_interval_hours ≥ 1`, `agent.binary` 실행 가능 (`agent.type`별 ADR-0012 매핑 정합). **`operations.disk.*` 스키마는 F4 산출물(`wikihub.yaml.example`)에서 정의됨 — F4 완료 전까지 본 항목 검증 생략 가능 (L1)**
  - **CRIT-R10-2**: `instance.root` 디렉토리 ensure 가 본 Step의 명시적 책임. 미존재 시 unit template의 `WorkingDirectory={instance_root}`가 `203/CHDIR`로 즉시 fail → OnFailure → ops-alert 매 사이클 발화. **추가 안전망**으로 unit template `ExecStartPre=/bin/mkdir -p {instance_root}` 보유 (정상 운영에서는 redundant, yaml 편집 직후 reboot 등 race window 방어).
- **rclone.conf 검증** (enabled gdrive_api vault만, ADR-0035): `~/.config/rclone/rclone.conf` 파일 존재 + 권한 0600 + `[<rclone_remote_name>]` 섹션 등록. 추가로 light call `rclone about <remote>:` 로 OAuth 유효성 검증. 401/Forbidden 시 보고 + 해당 vault 제외 (해당 vault unit 생성 skip)
- **graphify env file 검증** (ADR-0036 + ADR-0038 v0.1.7 follow-up): `~/.config/wikihub/env` 파일 존재 (install.sh `_step5_instance_dirs` 가 보장) + 권한 0600. **active profile 3-키 (`WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL>`) 존재 검증** — 부재 시 운영자 안내 (yaml `operations.graphify_profile` + env 의 namespace 매칭 확인). 추가 profile cookbook → `docs/graphify-backend-test-reference.md` §6.
  - **Hermes terminal.env_passthrough 안내 — v0.1.7 follow-up 정합 (ADR-0038)**: namespace 격리 후 **불필요**. wikihub 가 `WIKIHUB_GRAPHIFY_*` namespace 보유 후 graphify 호출 시점에 `env <K=V> graphify ...` 로 explicit 주입 → Hermes parent 는 backend env (OLLAMA_*/ANTHROPIC_API_KEY 등) 를 안 봄, tirith strip 도 우회. 운영자가 hermes config 의 `terminal.env_passthrough` 편집 안 함.
  - **Hermes delegation.model 권장 안내** (ADR-0032 §Note 2026-05-22 — v0.1.6): wh-lint Step 6 등 subagent 호출 시 `~/.hermes/config.yaml` 의 `delegation.model` 이 적용됨. 권장값 `minimax-m2.5` (non-reasoning 안정성 + 한자→한글 정합). 부재·다른 모델 시 보고 + warn (정보 출력만, 자동 patch 미수행 — Hermes config 는 wikihub spec 외부). wh-ingest·wh-lint 메인 모델은 wikihub `agent.models` 가 `--model` 으로 systemd lock — hermes `model.default` 와 무관.
- **wiki/ 디렉토리**: 4 카테고리(`sources/`, `entities/`, `concepts/`, `analyses/`) + `_lint/` + 각 vault별 `sources/{vault_id}/` 존재 (없으면 생성)
- **wiki/.graphifyignore** (ADR-0036 §D3): 부재 시 default template 배치 — `_system/templates/wiki/.graphifyignore` 를 `cp -n` 으로 복사 (`-n`: 존재 시 미덮어쓰기, idempotent). default 내용은 `_lint/`, `_state/`, `**/log.md`, `graphify-out/` 제외 (gitignore 문법). 메타 디렉토리가 graphify 그래프의 noise 노드로 포함되는 것 차단. 운영자가 vault 별 추가 패턴 직접 편집 가능.
  - **`graphify-out/` line-level idempotent migration** (v0.1.10, graphify_path_absolute follow-up): 기존 instance (pre-v0.1.10) 의 `.graphifyignore` 는 `graphify-out/` line 부재. install.sh `_migrate_graphifyignore` 가 매 install (update + fresh) 시점에 `^graphify-out/?$` regex 부재 시만 append 보강. 운영자 customization 보존 (`/graphify-out`, `**/graphify-out/` 등 다른 형태는 본 regex 미매칭 — touch 안 함).
- **_state/ 디렉토리**: 각 enabled vault의 `_state/{vault_id}/` + 초기 state 파일 (없을 때만 — ADR-0007 all JSON, ADR-0035 cursor 폐기)
  - **초기 파일 형식**:
    - `file_map.json` → `{"vault_id": "<id>", "updated_at": null, "files": {}}` (ADR-0035: primary key 는 source_id)
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
- `--enable` 플래그 시: `wikihub-lint.timer` **만** `enable --now`. **wikihub-ingest@<vid>.timer 는 Step 6 결과에 위임** — 첫 ingest 성공한 vault 만 enable.
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
  wikihub-ingest@gdrive.service (interval 600s)
  wikihub-ingest@gdrive.timer
  wikihub-lint.service (interval 3h, v0.1.5 default — 24h → 3h)
  wikihub-lint.timer
  wikihub-mount@gdrive.service
  wikihub-graphify.service
  ops-alert.service

daemon-reload 완료.

다음 권장 액션 (--enable 미사용 시):
  systemctl --user enable --now wikihub-ingest@gdrive.timer wikihub-lint.timer
  systemctl --user list-timers
```

### Step 5.5. rclone OAuth 발급 (ADR-0035 정본, vault 별 1회성)

**진입 조건**: Step 1~5 통과 + `vaults[*].options.rclone_remote_name` 정의 + `~/.config/rclone/rclone.conf` 의 해당 remote 미등록.

**ADR-0035**: rclone OAuth (rclone 기본 client, Production 검증 통과) 가 단일 인증 자료. SA·gws 폐기. mount + lsjson 변경 감지 둘 다 동일 OAuth user 컨텍스트.

**Interactive mode** (default — 운영자가 SSH 세션에 직접 입력, headless 환경은 `rclone authorize` headless-OAuth flow):

1. `rclone config` 실행
2. `n` (new remote) → name 입력 (`wikihub.yaml.vaults.<id>.options.rclone_remote_name` 과 정합, 권장: `gdrive`)
3. type 선택: `drive`
4. client_id/secret: **빈칸** (rclone 기본 client — 이미 Production 검증 통과, 7일 refresh 만료 없음). 별도 GCP 프로젝트 OAuth client 발급 불요.
5. scope: `1` (drive — full access)
6. service_account_file: **빈칸** (ADR-0035 — SA 폐기)
7. Edit advanced config: `n`
8. Use auto config:
   - dev box (브라우저 가능): `y` → 브라우저 인증 → 자동 토큰 발급
   - 운영 서버 (headless): `n` → 출력된 URL 을 로컬 브라우저로 열기 → 인증 → 토큰 코드 복사 → 서버 prompt 에 paste
   - 또는 dev box 에서 `rclone authorize "drive"` 실행 후 출력 JSON 을 서버 prompt 에 paste
9. Configure as Shared Drive: `n` (Personal Drive)
10. 완료 후 `~/.config/rclone/rclone.conf` 에 `[<remote_name>]` + `token = {...}` 라인 확인
11. **`chmod 0600 ~/.config/rclone/rclone.conf`** 실행 — OAuth token 평문 노출 차단

**검증**:
- `rclone lsd <remote_name>:` 로 OAuth 동작 확인 (Drive root listing — OAuth user 의 owned 파일 + shared 파일 보임)
- `rclone about <remote_name>:` 로 OAuth user identity + quota 확인
- 실패 시: OAuth client publishing status (GCP Console — rclone 기본 client 사용 시 무관) 또는 token refresh 거동 확인

**책임 분배 (v9 R12-MED-2)**:

| 책임자 | 위치 | 시점 |
|---|---|---|
| install.sh §Step 4.5 `_enforce_rclone_conf_perms` | 자동 chmod 0600 (정본 enforce) | 매 install.sh 호출 |
| setup.md §Step 5.5 step 11 | 운영자 수동 setup 직후 한 번 더 확인 | 첫 OAuth 발급 시 |
| mount.service | `Environment=RCLONE_CONFIG=` 만 주입 (권한 검증은 install.sh 책임) | mount 시작 시 |

ADR-0022 (첫 ingest 진입점) 와 정합 — Step 5.5 가 끝나야 Step 6 진입 가능.

### Step 6. 첫 ingest prompt + timer enable 게이트 (v0.1.0 v5 신설 — ADR-0022)

**진입 조건**: `--enable` 플래그 + Step 1~5 통과 + `enabled: true` vault 1개 이상 (ADR-0035 — `bootstrap_allowed` 폐기, file_map 비어있는 first-run 이 자연 bootstrap).

**동작**:

1. enabled vault 별로 prompt (ADR-0035 — bootstrap_allowed 폐기 후 cursor 의미 부재. 모든 enabled vault 가 대상):
   ```
   vault 'gdrive' 의 첫 ingest 를 지금 실행하시겠습니까? [Y/n] (default Y)
   ```
   비대화 모드 (`--run-first-ingest` / `--skip-first-ingest` / `WIKIHUB_FIRST_INGEST=yes/no` env / `/dev/tty` 부재 시 자동 비대화) 면 prompt skip + 사전 결정 사용.

2. **`Y` 응답** (ADR-0035: `--bootstrap` 플래그 폐기, cursor 모델 폐기):
   - `vault-fetch.py --vault <id>` 직접 호출 (timer 우회). first-run 은 file_map 비어있어 모든 파일이 created 분류 — 자연 bootstrap.
   - stdout JSON 보고 + exit code 캡처.
   - **exit 0**: timer enable.
   - **exit 75**: timer enable + "일시 결함 — 다음 사이클 재시도" 안내.
   - **exit 2**: timer enable **보류** + `last_failure.json` 영속화 (ADR-0024) + "fatal — 진단 후 수동 enable" 안내.

3. **`N` 응답**: vault-fetch + timer enable 모두 skip.

4. **timer enable** (`Y` + exit 0/75 시):
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
| `wikihub.yaml` (Step 0 — materialize 또는 drift sync) | 첫 호출: `.example` 으로부터 generate + derived 필드 patching (ADR-0035: 2필드). 재호출: drift 검출 시 confirm prompt (대화) 또는 exit 1 (비대화). helper = `scripts/lib/yaml_writer.py atomic_yaml_write` (PID-suffix `.tmp` + fsync + os.replace). **ADR-0031 정본** |
| `wiki/` 카테고리 디렉토리 | 없을 때만 생성 |
| `_state/{vault_id}/` 초기 파일 | 없을 때만 생성 (ADR-0035: cursor.json 폐기) |
| `~/.config/systemd/user/*.service`·`*.timer` | 매 호출 시 yaml 값으로 갱신 (덮어쓰기 — yaml이 정본) |
| systemd state | daemon-reload + (선택) enable. **vault-ingest.timer 는 Step 6 결과 위임** |
| agent skill 메타 | 변경 시만 갱신 |

## 실패 처리

| 실패 시점 | 동작 |
|---|---|
| wikihub.yaml 스키마 위반 | stdout 보고 + exit 1. unit 동기화 안 함 |
| rclone.conf 무효 (일부 vault) | 해당 vault의 unit은 생성하되 enable 권장에서 제외. 보고 + exit 0 |
| rclone.conf 무효 (모든 vault) | 보고 + exit 1 (운영 시작 불가 상태) |
| systemd unit 파일 쓰기 실패 | exit 2 (권한 의심) |
| daemon-reload 실패 | exit 2 + ops-alert 트리거 |
| agent skill 갱신 실패 | 보고 + exit 0 (skill 동작 자체에는 영향 없을 가능성. 다음 호출에서 재시도) |
| Step 6 첫 ingest exit 2 | timer enable 보류 + 사용자 안내 + 보고에 "timer 비활성" 명시 + exit 0 (Step 6 자체는 정상 종료) |

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
| `instance.root` mkdir | ✓ (`_step5_instance_dirs`) | — |
| `~/.config/rclone/rclone.conf` chmod 600 | ✓ (`_step45_rclone` — `_enforce_rclone_conf_perms`, ADR-0035) | — |
| agent skill 초기 등록 | ✓ | — (메타 갱신만) |
| wiki/·_state/ 디렉토리 | — | ✓ |
| systemd unit 생성·갱신 (template + yaml 값 instance화) | ✓ (`_step8_systemd_render`, ADR-0030 update_mode 정본) | ✓ (재진입 호출 — `/wh-setup` 단독 호출 시) |
| OAuth 토큰 검증 | — | ✓ |
| daemon-reload·enable | — | ✓ |

## 관련 ADR

- ADR-0006 unified orchestration (ExecStart의 명령 형식)
- ADR-0007 state all JSON (Step 1 초기 파일, ADR-0035: cursor.json 폐기)
- ADR-0008 lint 권한 (wikihub-lint.timer는 기본 모드만)
- ADR-0009 setup 책임 (본 명령의 정본 — §4 yaml writer 확장 Note 정합)
- ADR-0010 운영 도구 책임 분할 (install.sh와의 경계 — yaml.example 복사 책임은 ADR-0031 으로 reassign)
- ADR-0022 첫 ingest 진입점 (ADR-0035: `--bootstrap` 플래그 폐기, file_map 비어있는 first-run 이 자연 bootstrap)
- ADR-0030 update workflow orchestration (`_step2_update` + sparse-checkout 영속화)
- ADR-0031 yaml template materialization (Step 0 정본 — derived 필드 catalog + drift fix + helper 단일성)
- ADR-0033 skill namespace prefix `wh-`
- ADR-0035 rclone 단독 + OAuth 단일 인증 (gws·SA 폐기 — Step 5.5 정본)
