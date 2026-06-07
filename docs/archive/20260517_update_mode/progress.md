# Progress — update_mode

**종료 처리 완료 (2026-05-17)**: Step 1 → Step 4 모두 완료, **Step 5 Deployment 는 deferred** (F5 hermes_adapter 미완성 — v0.1.0 일괄 deploy 시점에 진행). archive 이동.

---

## 단계별 산출물 (timestamp 순)

### Step 1 Plan (2026-05-17 오전)

`plan.md` — 적용 단계 선언, 영향 범위, 미결 U1~U5 (사용자 confirm 으로 lock).

### Step 2 Analysis & Design

| 버전 | 변경 |
|---|---|
| v1 | 초안. ADR-0010 conformance + F4 결함 #A·#B·#C·#D + R16-L2. design_review_1·2 회부. |
| v2 | R1·R2 (CRIT 5 + HIGH 9) 일괄 반영. ADR-0010 `latest` 정본 유지 (semver derive 제거), curl-pipe mode-aware, install.sh 가 systemd render 직접 수행 (hermes 독립), rollback trap, 15min stop grace, force-fresh safety guard 추출. |
| v3 (approved) | R3 (CRIT-N 2 + HIGH-N 4 + PARTIAL 5건 + MED/LOW 8건) 반영. rollback 에 systemd re-render 추가 (CRIT-N1), stop 직후 daemon-reload (CRIT-N2), §6.1 render_systemd_units.py Contract 신설 (HIGH-N1), bootstrap exec 전 fd close (HIGH-N4), SIGINT 분기 + progress output, helper 단일화. |

### Step 3 Implementation

- `install.sh` dual-mode 본 구현 (~530 lines 추가)
- `scripts/_helpers/render_systemd_units.py` 신규 (~400 lines)
- `_system/commands/setup.md` Step 2 책임 이관 표기
- `docs/adr/0030-update-workflow-orchestration.md` 신규 Proposed
- `docs/adr/0023-…md` Note 추가 (clean wipe scope → fresh / --force-fresh 한정)
- `README.md` install/update snippet + roadmap 갱신
- `.gitignore` `.venv_path` 추가 (VM 테스트 surface)

### VM 자가검증 (multipass wikihub-test)

| ID | 시나리오 | 결과 |
|---|---|---|
| V1 | fresh F4 → update path 첫 호출 + 동일 ref 재호출 (멱등) | ✅ PASS |
| V2a/b | dirty tree / `.git/index.lock` 잔존 | ✅ PASS |
| V13 | 동시 install.sh 호출 (flock) | ✅ PASS |
| V14 | render_systemd_units.py idempotency (mtime 보존) | ✅ PASS |
| V11-ish | `--version v9.9.9` (tag 부재) → trap rollback pre-reset 분기 | ✅ PASS |
| V15-ish | trap signal registration (ERR EXIT INT TERM HUP) | ✅ PASS |

VM 도중 surface + fix (5건):
1. `.gitignore .venv_path` — runtime sidecar 가 unstaged guard 오발화 → ignored
2. F4 single-branch refspec/shallow → unshallow + default refspec normalize
3. `_resolve_ref` path 2 `origin/` prefix (local branch 부재 해소)
4. venv 재생성 후 pip skip 결함 — skip 자체 제거 (uv pip install 가 자체 idempotent)
5. (Step 4 의 CR2-CRIT-1 fix — `_step4_gws` trap EXIT → RETURN — 이 fix 의 surface 는 R2 review 결과)

### Step 4 Code Review (R1·R2)

| 리뷰어 | 각도 | 결과 |
|---|---|---|
| code_review_1 (Claude Sonnet 4.6 서브에이전트) | spec correctness | Accept with MED-LOW backlog (CRIT 0 · HIGH 0 · MED 3 · LOW 6) |
| code_review_2 (Claude Opus 4.7 서브에이전트) | SRE operational safety | Fix CRIT-1 + HIGH 1-5 before lock (CRIT 1 · HIGH 5 · MED 8 · LOW 6) |

**Must 묶음 fix (7건, commit `8601406`)**:
- CR2-CRIT-1: `_step4_gws` trap EXIT → RETURN (rollback EXIT trap clobber 차단)
- CR2-HIGH-1: `_resolve_ref` fresh path 가 `git ls-remote` probe 로 `latest` tag 도달성 회복
- CR2-HIGH-2: `FETCH_FAILED` flag 도입 — stale `latest` local cache 신뢰 안 함 + 명시 warn
- CR2-HIGH-3: rollback trap 에 `TERM HUP` 추가 — ssh disconnect / OOM kill 시 rollback 보장
- CR2-HIGH-4: `_step10_verify` 실패 시 git rollback 분리 (warn-only) — invariant #1 (state divergence) 보호
- CR2-HIGH-5: `_systemd_stop_before_update` 가 desired (yaml) ∪ loaded (`--all`) union 사용 — failed/inactive vault 미스 차단
- CR1-MED-3: `_step8_guide` fresh mode 만 호출 + stale F4 clean install pattern 단락 제거

회귀 검증 (Must fix 후): V1·V11-ish·V15-ish 모두 PASS.

### Step 5 Deployment — deferred

v0.1.0 의 다른 feature (F5 hermes_adapter) 가 미완성. 본 feature 단독 deploy 시 운영 시작 의미 약함 (F4 와 동일 정책).

v0.1.0 spec 완성 시점에 메인테이너가:
1. `git tag v0.1.0 <commit>` 발급
2. `git tag -f latest <commit> && git push -f origin latest`
3. OCI 운영 서버에서 `curl -fsSL https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh | bash` → F4 (현행) → update_mode 첫 전환 발생.

### 종료 처리 (2026-05-17)

- ADR-0030 Status: Proposed → **Accepted**
- ADR-0023 Note (clean wipe scope → fresh / --force-fresh 한정) 유지
- features/backlog.md 의 #A·#B·#C·#D + R16-L2 closed mark
- README.md roadmap update_mode 항목 ✅ archive
- `git mv features/20260517_update_mode → features/archive/...`

## 백로그 (v0.2.x 후속)

**Should/MED 미수행분 — operational hardening**:
- CR2-MED-1: rollback 도중 operator systemctl race (문서화)
- CR2-MED-2: helper `.tmp` 잔존 정리
- CR2-MED-3: `os.path.expandvars` for `credentials_path`
- CR2-MED-5: non-Ubuntu (macOS) 호환성 보강 — `find -executable`·`timeout` etc
- CR2-MED-6: `agent_binary` allowlist (v0.2.x security)
- CR2-MED-7: dead variable `venv_was_recreated` 정리
- CR2-MED-8: `RandomizedDelaySec` for Persistent timer catch-up flood
- CR1-MED-1·2: §6.1 substitution key drift 보정 + VM fix back-port 명시화

**LOW 12건**: 별도 doc-patch 또는 R3 후속 review 시점 처리.

**미수행 V<N>**: V3·V4·V5·V6·V7·V8·V9·V10·V12. 운영 surface 또는 v0.2.x 검증 시점.
