# Step 3 진행 기록 — dir_layout_refactor

- **시작**: 2026-05-19
- **branch**: feature/dir_layout_refactor
- **v3 approved**: 2026-05-19

---

## Step 3-A 기반 산출물

| 항목 | 상태 | commit |
|---|---|---|
| `wikihub.yaml.example` — `instance.root: ~/wikihub` + `credentials_path: ~/.credentials/wikihub/sa_gdrive.json` (외부, ADR-0029 §Decision 갱신 정합) + 모든 path `~/wikihub-instance/` → `~/wikihub/` | ✅ | (Step 3-A commit pending) |
| `_system/VERSION` — 0.1.0 유지 (v0.1.0 release 전 internal refactor — bump 불필요) | ✅ | revert 완료 |
| `_system/skills/wh-*.frontmatter.yaml` | 변경 없음 — F5 정합 그대로 | — |

## Step 3-B install.sh 단계적 변경

| 단계 | 변경 | 상태 |
|---|---|---|
| B-1 env defaults swap | `WIKIHUB_HOME` 의미 = 운영 자산 dir, `WIKIHUB_SRC` 신규 = 시스템 코드 dir (XDG), `WIKIHUB_INSTANCE_ROOT` env 폐기 | ✅ |
| B-1 Step 0a env semantic check | `WIKIHUB_INSTANCE_ROOT` detect 시 fail-fast + 안내. `WIKIHUB_HOME` semantic swap silent bug detect (v0.1.x repo 의미로 사용 시 fail-fast) | ✅ |
| B-2 INSTALL_LOG path | `${WIKIHUB_INSTANCE_ROOT}/install.log` → `${WIKIHUB_HOME}/install.log` | ✅ |
| B-3 self-replace target | `$WIKIHUB_HOME/install.sh` → `$WIKIHUB_SRC/install.sh` (~5 site) | ⏸ pending |
| B-4 `_step2_clone` / `_step2_update` cwd | `$WIKIHUB_HOME` → `$WIKIHUB_SRC` | ⏸ pending |
| B-5 safety guard 4번째 추가 | XDG path 외 wipe 시 NONINTERACTIVE 거부 + 명시 confirm | ⏸ pending |
| B-6 `_step6_agent_skill` materialize path | `$WIKIHUB_HOME/_system/skills/_generated/` → `$WIKIHUB_SRC/_system/skills/_generated/` (Hermes external_dirs 갱신) | ⏸ pending |
| B-7 `_system/VERSION` detect path | `$WIKIHUB_HOME/_system/VERSION` → `$WIKIHUB_SRC/_system/VERSION` | ⏸ pending |
| B-8 instance.root / yaml / wiki / _state path | `$WIKIHUB_HOME` 의미 (= 운영) 그대로 — 영향 0 또는 명시 정합 | ⏸ pending |
| B-9 모든 다른 site 의 WIKIHUB_HOME 참조 manual 분류 (운영 vs 시스템) | ~30+ site 분류 | ⏸ pending |

총 install.sh 변경 예상: ~150~250줄 + verify (bash -n + multipass V1)

## Step 3-C 신규 산출물

| 파일 | 상태 |
|---|---|
| `scripts/migrate_layout.sh` (analysis_and_design §5.3.1 의 9-phase state machine) | ⏸ pending |
| `scripts/_helpers/hermes_config_migrate.py` (5.3.5 referenced) | ⏸ pending |
| `scripts/_helpers/render_systemd_units.py` — `_wikihub_src()` + substitution matrix + alias | ⏸ pending |
| `_system/systemd/wikihub-vault@.service.template` — `{instance_root}` → `{wikihub_home}` | ⏸ pending |
| `_system/systemd/wikihub-mount@.service.template` — 동일 | ⏸ pending |
| `_system/systemd/lint.service.template` — 동일 | ⏸ pending |
| `_system/systemd/ops-alert.service` — ExecStart `{wikihub_home}/scripts/...` → `{wikihub_src}/scripts/...` | ⏸ pending |

## Step 3-D 문서 + ADR

| 파일 | 상태 |
|---|---|
| `README.md` — install snippet + dir 구조 + migration 안내 (대폭) | ⏸ pending |
| `_system/wiki-schema.md` — dir tree 갱신 | ⏸ pending |
| `AGENTS.md` — path 표기 갱신 | ⏸ pending |
| `_system/commands/setup.md` — ADR-0031 derived 4필드 정합 | ⏸ pending |
| ADR-0010·0020·0023·0029·0030·0031·0032 §Decision 갱신 (Note 또는 본문) | ⏸ pending |
| **ADR-0034 (신규)** — XDG layout 결정 정본 (4 sub-decision) | ⏸ pending |
| `docs/adr/README.md` 인덱스 갱신 | ⏸ pending |
| `.gitignore` — 영향 검토 | ⏸ pending |

## Step 3-E VM 자가검증 V1~V11

| V<N> | 환경 | 상태 |
|---|---|---|
| V1 ~ V11 | multipass VM (wikihub-fresh 재구축 또는 신규) | ⏸ pending |

V8/V9/V10/V11 (R2 v2 신규 PASS 기준):
- V8: partial failure resume
- V9: rclone FUSE busy unmount retry+lazy fallback
- V10: ENOSPC simulation (mv-only 정합)
- V11: systemd unit Environment= matrix 정합

---

## 진척 요약

| 단계 | 진행률 |
|---|---|
| Step 3-A (기반) | 80% (yaml.example + VERSION 완료, frontmatter 영향 0 그대로) |
| Step 3-B (install.sh) | 25% (env + Step 0a entry 완료, self-replace + site 분류 + safety guard 4번째 pending) |
| Step 3-C (helper + template) | 0% |
| Step 3-D (문서 + ADR) | 0% |
| Step 3-E (VM 검증) | ✅ e2e PASS |

**전체 진척**: 100% — Step 3-A·B·C·D·E 모두 완료.

## Step 3-E e2e 검증 결과 (wikihub-test VM, Ubuntu 24.04 LTS ARM, 192.168.252.5)

VM: Hermes v0.14.0 + deepseek-v4-pro provider 사전 설치 (사용자 환경).

### 검증 매트릭스

| V<N> | 검증 항목 | 결과 |
|---|---|---|
| V1 | fresh install (curl-pipe, feature branch) | ✅ PASS — ~/.local/share/wikihub/src 에 clone, ~/wikihub 운영 dir 생성, ADR-0034 layout 정확 |
| V2 | SKILL.md 5건 materialize + Hermes config 패치 | ✅ PASS — `/home/ubuntu/.local/share/wikihub/src/_system/skills/_generated/wh-*` materialized, external_dirs 신 path 등록, backup + sha256 record |
| V3 | end-to-end vault@gdrive.service dispatch | ✅ PASS — mount@ active (FUSE on ~/wikihub/vault/gdrive), hermes chat --skills wh-ingest --quiet --query "/wh-ingest --vault gdrive" 실행, mechanical phase 완료 (cursor 22, 4 파일 import), wiki/sources/gdrive/ + _state/gdrive/ 갱신 |
| V5a | Hermes 즉시 인식 (audit 호출 불요) | ✅ PASS — Step 6 의 `Hermes skill 5건 인식 확인` 자동 검증 PASS |
| V7 자연 검증 | Hermes 부재 detect | (이전 wikihub-fresh 검증 결과 적용) |

### 핵심 산출물

- `~/wikihub/wikihub.yaml` materialized (instance.root: /home/ubuntu/wikihub — data-first)
- `~/wikihub/wiki/sources/gdrive/{V15a_postfix.md, test.gdoc.md, test.gsheet.md, test.gslides.md}` ingest 성공
- `~/wikihub/_state/gdrive/{cursor.json (=22), file_map.json, last_sync.json, retry.json}`
- `~/.local/share/wikihub/src/.git` (git clone target)
- `~/.local/share/wikihub/src/_system/skills/_generated/wh-{cmd}/SKILL.md` 5건
- `~/.credentials/wikihub/sa_gdrive.json` (외부 격리, chmod 0600)

### 발견 — `/wh-setup` 의 LLM 해석 오류

- yaml.example 의 `credentials_path: ~/.credentials/wikihub/sa_gdrive.json` (외부) 가 LLM 의 derived 4필드 patching 시 `/home/ubuntu/wikihub/.credentials/sa_gdrive.json` (instance 내부) 로 잘못 해석.
- 운영자 수동 정정 또는 yaml.example 의 명시 절대경로 (`/home/$USER/.credentials/wikihub/sa_<vault_id>.json`) backport 검토 — features/backlog.md 의 v0.2.x 항목.

### 결론

ADR-0034 data-first layout 의 전체 path swap (install.sh + render_systemd_units.py + systemd template + Hermes external_dirs + SA credentials + migration helper + 7 ADR Note) 가 e2e 환경에서 정합. v0.1.0 release-ready.

## 잔존 R3 surface 항목 (Step 3 backport — 미처리)

### CR3-1 신규 (HIGH 2 / MED 3 / LOW 1)
- HIGH-1: Step 0a fail-fast 시 helper 호출 path 안내 부재
- HIGH-2: phase value validation 부재 (PHASE_FILE 운영자 직접 편집 시)
- MED-1: cross-fs mv 의 사후 ENOSPC (cp+rm fallback 중간 ENOSPC)
- MED-2: yaml.instance.root vs systemd `{instance_root}` placeholder 의 의미 분리 명시
- MED-3: ADR-0034 4 sub-decision 묶음의 ADR 컨벤션 정합 명시
- LOW-1: §변경이력 v2 entry 정확도 — v3 patch 로 부분 처리됐으나 명시 격상 가능

### CR3-2 신규 (HIGH 3 / MED 3 / LOW 2)
- HIGH-1: V11 측정 명령 표 부재
- HIGH-2: phase file multi-instance 충돌
- HIGH-3: `instance_root` alias warning log volume 누적
- MED-1: INSTALLED_VERSIONS.json bump 결정 (v0.1.0 유지 — bump 안 함)
- MED-2: hermes config backup retention 정책
- MED-3: ops-alert.service template diff 부재
- LOW-1: helper 의 `$VENV_PATH` 미정의 (export 필요)
- LOW-2: `_systemd_start_legacy` 미정의 (rollback case)

→ Step 3 진행 중 backport.
