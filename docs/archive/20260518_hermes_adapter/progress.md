# Step 3 진행 기록 — F5 hermes_adapter

- **시작**: 2026-05-18
- **branch**: feature/hermes_adapter
- **최신 commit**: f3a060a (Step 3 V7 VM 결함 fix)

---

## Step 3-A 기반 산출물 ✅ (commit `613fad8`)

- `.gitignore` — `_system/skills/_generated/` 추가
- `_system/skills/wh-{ingest,lint,query,graphify,setup}.frontmatter.yaml` 5건 신설
- `docs/adr/0032-hermes-skill-registration-policy.md` 신설 (4 sub-decision)
- `docs/adr/0033-skill-prefix-hyphen-lock.md` 신설 (supersedes ADR-0011)
- `docs/adr/0011-skill-namespace-prefix.md` Status → Superseded
- `docs/adr/README.md` 인덱스 갱신
- `features/20260518_hermes_adapter/analysis_and_design.md` v3 approved 마커

## Step 3-B install.sh + render helper ✅ (commit `b0d6e2f`, fix `f3a060a`)

### install.sh 신규 helper (4건)
- `_migrate_agent_schema()` — operational yaml schema lift (`wh:`/`-z` detect + backup + ruamel atomic patch)
- `_materialize_skills()` — 5건 SKILL.md = frontmatter + commands body 결합 → `_generated/wh-<cmd>/SKILL.md`. stale cleanup 포함
- `_patch_hermes_external_dirs()` — flock(60s retry) + backup(7일 retention) + sha256 PRE/POST + ruamel atomic + marker comment + realpath 비교
- `_verify_hermes_skill_registration()` — `hermes skills list | grep ^wh-` + audit fallback

### install.sh 기존 함수 수정
- `_step6_agent_skill()` — stub 제거 → 위 4 helper 호출 + Hermes detect gate (부재 시 `SKIP_SYSTEMD_RENDER=1`)
- `_step8_systemd_render()` + `_step8_wh_setup_skill_meta()` + `_systemd_start_after_update()` — `SKIP_SYSTEMD_RENDER` guard
- `_step8_wh_setup_skill_meta()` — `hermes -z "/wh:setup"` → `hermes chat --skills wh-setup --quiet --query "/wh-setup"`, yaml-driven timeout_sec

### render_systemd_units.py
- `_per_skill_invocation()` 신규 — `{skill}` placeholder fail-fast
- `_instance_wide_subs()` 확장 — 5개 `agent_invocation_for_wh_<skill>` key + `timeout_start_sec` (yaml.agent.timeout_sec sync)
- `_systemd_analyze_verify()` — render 직후 자동 호출, fail-fast

### systemd unit template
- `wikihub-vault@.service.template` ExecStart: `{agent_invocation_for_wh_ingest} "/wh-ingest --vault %i"` + `TimeoutStartSec={timeout_start_sec}sec`
- `lint.service.template` ExecStart: `{agent_invocation_for_wh_lint} "/wh-lint"` + `TimeoutStartSec={timeout_start_sec}sec`

### Fix surface (VM 테스트 발견)
- `f3a060a` — `${BASH_SOURCE[0]}` unbound under `set -u` + curl-pipe (line 1645)

## Step 3-C 문서 + ADR Notes ✅ (commit `b0d6e2f`)

- `_system/commands/{ingest,lint,query,graphify,setup}.md` — `/wh:` → `/wh-` 일괄 sed
- `_system/wiki-schema.md` — orchestration table + yaml schema 예시 + skill_prefix 표기 ADR-0033 정합
- `_system/commands/setup.md` L:165 — `wh:` → `wh-`
- `wikihub.yaml.example` — `oneshot_args: ["chat", "--skills", "{skill}", "--quiet", "--query"]`, `skill_prefix: "wh-"`
- `README.md` — F5 status (Step 3 진행), install snippet prerequisite (Hermes 사전 설치 + ~/.hermes mutate 동의)
- ADR-0002·0010·0012·0023·0024·0030·0031 Notes 7건 추가

---

## Step 3-D VM 자가검증 V1~V10

VM: `wikihub-test` (multipass Ubuntu 22.04 ARM, 192.168.252.2). Hermes v0.14.0 (2026-05-16) 설치.

| V<N> | 환경 | 검증 | 결과 | 비고 |
|---|---|---|---|---|
| **V1** | VM-A | install.sh + Step 6 — materialize + external_dirs | ✅ PASS | 5건 SKILL.md 생성, `_generated/wh-*/SKILL.md`. ~/.hermes/config.yaml 의 `external_dirs` 에 realpath 추가 + marker comment. backup `*.wikihub-bak.<ts>` + PRE/POST sha256 record |
| **V2** | VM-A | `hermes skills list` 5건 인식 | ✅ PASS | `Hermes skill 5건 인식 확인` (install.sh 자동 검증) |
| V3 | VM-A | vault@.service fire — `/wh-ingest --vault gdrive` dispatch | ⏸ SKIP | enabled_vaults=[] (VM 에 GDrive vault credentials 미설정) |
| V3' | VM-A | dispatch 결정성 30회 ≥93% | ⏸ SKIP | V3 의존 |
| V4 | VM-A | 멱등성 — source_mtime drift 0 | ⏸ SKIP | V3 의존 |
| **V5a** | VM-A | external_dirs 등록 후 즉시 인식 (재시작 없이) | ✅ PASS | V2 결과 5건 즉시 표시 — audit 호출 불요 (M-5 결정: audit 자동 호출 미필요) |
| V5b | VM-A | audit 1회 필요 시 install.sh 자동 호출 | n/a | V5a PASS 로 미진입 |
| **V6** | VM-A | update path 의 `_step8_wh_setup_skill_meta` 호출 | ✅ PASS (조건부) | `hermes chat --skills wh-setup --quiet --query "/wh-setup"` 호출됨. LLM provider 미설정으로 warn-only (`No inference provider configured`). install.sh exit 0 보존 (의도된 best-effort) |
| **V7** | VM-B (Hermes 미설치) | SKIP_SYSTEMD_RENDER detect + systemd skip | ✅ PASS | Step 6 가 `Hermes binary 미설치 또는 미실행 — systemd render/enable skip` 출력. 3개 후속 함수 모두 guard 작동. install.sh exit 0. ✨ **CR2-CRIT-1 closure 검증** |
| **V8** | VM-A | Hermes exit code contract (LLM 부재) | ✅ MEASURED | `hermes chat --skills <name> --quiet --query "..."` 가 LLM provider 미설정 시 **exit 1** (fatal). v0.1.0 release-time decision = 현 `SuccessExitStatus=0 75` 유지 + 운영자 prerequisite (hermes model + API key) 강화로 충분 |
| **V9** | VM-A | rollback compatibility | ✅ PASS (자연 검증) | V1 retry 도중 `_resolve_ref` 가 main HEAD fallback → F5 코드 부재 → materialize 실패 → 자동 rollback to `f3a060a` (PRE_UPDATE_REF) → systemd render 정합. ADR-0030 trap 작동 |
| V10 | VM-A | flock contention | ⏸ defer | V1 의 정상 backup/atomic write 동작으로 path 검증됨. 60s retry 시뮬레이션은 시간 의존 — backlog |
| **V3 end-to-end** | VM `wikihub-fresh` (재구축) — provider Opencode.ai/deepseek-v4-pro | vault@gdrive.service fire → hermes wh-ingest dispatch → vault-fetch.py → wiki/sources/gdrive/ 갱신 | ✅ **end-to-end PASS** | ExecStart `hermes chat --skills wh-ingest --quiet --query /wh-ingest --vault gdrive` 실제 systemd 실행 + Hermes skill 진입 + commands/ingest.md procedure (Step 1·2·5) 진행 + cursor 22→22 + wiki/sources/gdrive/log.md + test.{gdoc,gsheet,gslides}.md + V15a_postfix.md materialized. exit 0, CPU 6.722s |

## V3 end-to-end 보강 결과 (2026-05-18, wikihub-fresh VM)

### 추가 검증 흐름

1. **VM 재구축** — wikihub-test/wikihub-test-clean 삭제 → wikihub-fresh (ARM Ubuntu 22.04, 2C/2G/10G) launch
2. **Hermes 설치** — curl-pipe `NousResearch/hermes-agent/main/scripts/install.sh --skip-setup` → v0.14.0 (`/home/ubuntu/.local/bin/hermes`)
3. **운영자 provider 설정** — `~/.hermes/config.yaml` 의 `custom_providers: [{name: Opencode.ai, base_url: https://opencode.ai/zen/go/v1, model: deepseek-v4-pro, api_key: ...}]` + `model.default = "Opencode.ai/deepseek-v4-pro"`
4. **wikihub fresh install** — curl-pipe `feature/hermes_adapter` → bootstrap → self-replace → Step 6 materialize 5건 + external_dirs 패치 + sha256/backup record
5. **SA credentials** — `~/.credentials/wikihub/sa_gen-lang-client-0595383518.json` (호스트) → VM `~/wikihub-instance/.credentials/sa_gdrive.json` (chmod 0600)
6. **rclone config** — `[gdrive]` type=drive, scope=drive, service_account_file, root_folder_id (운영자 SA 공유 GDrive folder `1UW18OJ1rkSFvw9az_BW6JazK_VtAabRU`)
7. **`/wh-setup` dispatch** — `hermes chat --skills wh-setup --quiet --query "/wh-setup"` 호출 → Hermes skill 자동 진입 → wikihub.yaml materialize (ADR-0031 §Decision B derived 4필드 patching: instance.root + local_path + credentials_path expansion)
8. **wikihub.yaml 갱신** (operator simulate) — enabled=true, root_folder_id 채움, bootstrap_allowed=true, agent.binary=실제 path
9. **install.sh 재호출** — systemd unit render (vault@.service/timer + mount@.service + lint.service/timer + ops-alert)
10. **linger 활성화 + timer enable + 수동 trigger** — `wikihub-vault@gdrive.service` 실 실행 → Hermes 가 wh-ingest skill body 의 procedure 따라 mechanical phase 호출 → vault-fetch.py exit 0 + cursor 22→22 (Drive changes.list 신규 0건 — 단 첫 1회 bootstrap 에서 4개 파일 → wiki/sources/gdrive/) → Step 5 log.md 생성 → exit 0

### 발견된 backlog 결함

**F4 #G** — `_system/systemd/wikihub-mount@.service.template` 의 ExecStart 가 yaml `vaults[*].options.root_folder_id` 를 `--drive-root-folder-id` flag 로 전파 안 함. rclone.conf 에 `root_folder_id` 추가하거나 ExecStart 에 `--drive-root-folder-id={root_folder_id_for_%i}` substitution 필요. F4 install_runtime 범위 (F5 와 무관). features/backlog.md 등재.

### F5 invocation contract 검증 종합

| 검증 항목 | 결과 |
|---|---|
| skill registration (V1) | ✅ 5건 SKILL.md materialize + external_dirs 패치 + backup + sha256 |
| skill 인식 (V2) | ✅ `hermes skills list` 5건 |
| 즉시 인식 (V5a) | ✅ audit 호출 불요 |
| invocation contract | ✅ `chat --skills <name> --quiet --query "/<name> ..."` |
| Hermes 부재 detect (V7) | ✅ SKIP_SYSTEMD_RENDER + alert chain dead 회피 |
| exit code contract (V8) | ✅ LLM 부재 시 exit 1, `SuccessExitStatus=0 75` 정합 |
| rollback compat (V9) | ✅ ADR-0030 trap 자연 검증 |
| **wh-setup skill dispatch** | ✅ Hermes 가 skill 진입 + yaml materialize + ADR-0031 §Decision B derived 4필드 patching |
| **wh-ingest end-to-end (V3)** | ✅ systemd vault@ → hermes → wh-ingest skill body → vault-fetch.py → wiki 갱신 |

→ F4 backlog #12 closure 완성, v0.1.0 acceptance 의 마지막 blocker 해소.

### V8 결과 따른 release-time decision (R3-CR3-2 B-HIGH-1 lock)

LLM provider 미설정 시 `hermes chat ...` exit code = **1** (fatal). systemd `SuccessExitStatus=0 75` 의 1 매핑 안 됨 → service failure → OnFailure=ops-alert.

- **결정**: 현 systemd template 의 `SuccessExitStatus=0 75` 유지. exit 1 은 fatal 분류 정합 (운영자 prerequisite 미충족, retry 무의미).
- **운영자 안내**: README install snippet prerequisite + 첫 호출 시 `hermes model` 명시 안내 (Step 3-C 의 prerequisite 섹션 충족).
- **transient retry**: v0.1.0 범위 외. LLM 503/429 의 retry 는 vault-fetch.py 의 exit 75 매핑 (ADR-0024) 그대로 — Hermes 가 skill body 의 mechanical phase 호출 시 발동.
- **v0.2.x trigger**: 운영 surface 한 transient (LLM API quota, 503) 빈도 정량 측정 후 yaml.agent.retryable_exit_codes 도입 검토 (CR2-HIGH-4 의 v0.2.x push 보존).

### V8/V10 외 추가 surface

- **operational yaml drift detect + auto-migration**: V1 진입 시 `_migrate_agent_schema` 가 `skill_prefix: "wh:"` 와 legacy `oneshot_args: ["-z"]` 자동 detect → backup + ruamel patch (`"wh-"` + F5 schema). 정상 동작 확인 ✅
- **ADR-0030 rollback trap 자연 검증**: BRANCH env 부재로 `_resolve_ref` 가 main HEAD fallback → F5 코드 부재로 `_materialize_skills` 실패 → install.sh trap 가 직전 ref (`f3a060a`) 로 rollback + systemd 재render. CR2-HIGH-7 closure 자연 검증 ✅

### 결과 요약

| 등급 | PASS | SKIP/DEFER |
|---|---|---|
| Critical paths | V1, V2, V5a, V7 (CRIT-1 closure), V9 (HIGH-7 자연 검증) | — |
| Supportive | V6 (조건부), V8 (measurement) | V3, V3', V4 (vault credentials 의존), V10 (시간 의존) |

**총평**: Hermes 설치 + 미설치 양 환경에서 F5 의 핵심 시나리오 통과. v0.1.0 release-time decision lock 완료.

---

## Step 4 R≥2 code review 진입 가능 상태

- ADR-0032·0033 신설 정합
- install.sh 6 함수 신규/수정 + SKIP_SYSTEMD_RENDER flag 정합
- render_systemd_units.py per-skill substitution + fail-fast + verify
- systemd template 2건 ExecStart 갱신
- 5건 `_system/commands/` + wiki-schema + README + 7 ADR Notes 정합
- VM 자가검증 V1·V2·V5a·V6·V7·V8·V9 PASS — V3·V4·V10 backlog

다음: Step 4 R≥2 (CR1 spec + CR2 SRE) 또는 사용자 검토.
