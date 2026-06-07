# Code Review #1 — update_mode (spec correctness)

- **Reviewer**: Claude Sonnet 4.6 (subagent, spec correctness angle)
- **Date**: 2026-05-17
- **Branch**: feature/update_mode (HEAD ac80f38)

## Summary

전체적으로 v3 design + ADR-0030 의 4 sub-decision 이 구현에 충실히 반영됐다. 핵심 invariant (mode detect AND-signal, trap rollback w/ systemd re-render, 15min grace + reset-failed + daemon-reload, ref chain --version>BRANCH>latest>local-semver>main) 모두 코드에 정확히 mapping. 다만 **MED 3건 + LOW 6건의 spec/code drift**가 있다 — 주로 (a) VM 테스트 도중 surface된 fix 4건이 analysis_and_design.md 에 back-port 안 됨, (b) §6.1 contract 의 substitution key 목록이 실제 helper 의 key set 과 일치 안 함, (c) `_step8_guide` 가 update 모드에서도 stale F4 text 출력. **CRIT 0 / HIGH 0** — Step 4 DoD `CRIT 0 · HIGH 0` 만족.

## Findings

### MED-1: §6.1 contract 의 substitution key 목록이 실제 helper key set 과 불일치
**File/Line**: features/20260517_update_mode/analysis_and_design.md §6.1 (L704-706) vs scripts/_helpers/render_systemd_units.py:136-178
**Issue**: 설계 §6.1 의 Pass 1/Pass 2 key 예시가 실제 helper 가 산출하는 key 와 다르다.

- 설계 Pass 1 (per-vault) 예시: `{vault_id}`, `{mount_path}`, `{rclone_rc_port}`, `{credentials_path}`, `{sync_interval_sec}`
- 설계 Pass 2 (instance-wide) 예시: `{instance_root}`, `{agent_binary}`, `{agent_oneshot_args}`, `{wikihub_home}`, `{venv_path}`, `{rclone_min_version}`

실제 helper 가 산출하는 key set:
- current-vault scalar (`_current_vault_subs`): `credentials_path`, `sync_interval_sec` ✓
- cross-vault (`_cross_vault_subs`): `remote_name_for_<vid>`, `rc_port_for_<vid>` — 설계에 없는 `_for_<vid>` 명명
- instance-wide (`_instance_wide_subs`): `instance_root`, `venv_path`, `wikihub_home`, `rclone_config_path`, `rclone_bin`, `vfs_cache_max_size`, `lint_interval_hours`, `agent_invocation`, `skill_prefix`

설계 명시 `{vault_id}` / `{mount_path}` 는 helper 미산출 (template 이 systemd `%i` 와 `{instance_root}/vault/%i` 패턴으로 처리). 설계 명시 `{agent_binary}` · `{agent_oneshot_args}` · `{rclone_min_version}` 도 helper 미설정 + templates 미사용 (templates 는 `{agent_invocation}` 단일 키 사용).

**Evidence**:
```python
# render_systemd_units.py:154-164
return {
    "instance_root": ..., "venv_path": ..., "wikihub_home": ...,
    "rclone_config_path": ..., "rclone_bin": ..., "vfs_cache_max_size": ...,
    "lint_interval_hours": ..., "agent_invocation": ..., "skill_prefix": ...,
}
```
templates 의 `grep` 결과: `{agent_binary}` · `{agent_oneshot_args}` · `{rclone_min_version}` · `{vault_id}` 미사용. 대신 `{agent_invocation}` · `{remote_name_for_%i}` · `{rc_port_for_%i}` 사용.

**Suggested fix**: §6.1 의 Pass 1/Pass 2 key 예시 목록을 실제 helper 의 4 그룹 (current-vault scalar / cross-vault `_for_<vid>` / instance-wide / systemd-native `%i`) 으로 갱신. "두 pass 의 key 가 disjoint 여야 함" 명시는 유지 — helper 도 duplicate-key fatal check 보유 (lines 304-307, 322-327).

---

### MED-2: VM 테스트 fix 4건이 analysis_and_design.md 에 back-port 안 됨
**File/Line**: install.sh:909-912, 838-842, 386-395; .gitignore:22 vs analysis_and_design.md §3 Step 2d / §4 path 2 / §3 Step 3
**Issue**: V1·V2·V13·V14 PASS 도중 surface 한 fix 4건이 design 정본 미반영. 향후 리팩토링 시 trace 불가.

1. **refspec normalize** (install.sh:909-910): F4 의 `git clone --branch X --depth 1` 가 refspec 을 single-branch 로 제한 → update path 에서 다른 ref fetch 불가. fix = `git config --replace-all remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'`. 설계 §3 Step 2d 의사코드는 `git fetch origin --tags` 만 명시.
2. **`origin/` prefix normalize** (install.sh:838-842): `_resolve_ref` path 2 가 BRANCH env 에 `origin/` prepend. 설계 §4 path 2 는 "branch name" 만 명시 — prefix 운용 미명시.
3. **unshallow fetch** (install.sh:912): `git fetch --unshallow 2>/dev/null || true` — shallow clone update path 에서 arbitrary ref fetch 가능하게. 설계 미명시.
4. **pip install skip 제거** (install.sh:386-395): 설계 §3 Step 3 MED-N3 의 "requirements.txt 변경 없을 때 pip skip" 최적화 제거. 이유 comment: "venv 가 partial install state 일 때 결함". 설계 §3 Step 3 의사코드는 여전히 skip 분기 보유.
5. **`.venv_path` `.gitignore`** (.gitignore:22): 설치 sidecar 가 working tree 에 떨어지면 `git status --porcelain` 가 dirty 로 분류 → 다음 update 의 unstaged guard fail. 설계 §3 Step 2a unstaged guard 정합을 위한 fix 인데 설계 본문 미언급.

**Evidence**: install.sh:386-388 의 comment —
```
# 이전 MED-N3 의 PRE_UPDATE_REF diff 기반 skip 은 venv 가 partial install state 일 때 결함
# (V1 VM 테스트 surface: previous install 이 Step 3 후 fail → venv 존재하지만 deps 미설치).
```

**Suggested fix**: analysis_and_design.md 에 `## v3.1 closure trace — VM 테스트 4 fix` 섹션 추가 또는 §3 Step 2d / §3 Step 3 / §4 path 2 의사코드 inline patch. ADR-0030 §Decision sub-2/4 본문에는 직접 영향 없음 (operational hardening 만).

---

### MED-3: `_step8_guide` 가 update mode 에서도 호출 + stale F4 text 출력
**File/Line**: install.sh:1202 (main flow) + install.sh:711-763 (_step8_guide body)
**Issue**: main flow 가 `_step8_guide` 를 mode guard 없이 호출. update 모드에서도 fresh 용 안내가 출력. 설계 §3 main flow (v2, L546-589) 는 `_step8_guide` 호출 자체 없음 (`_step11_banner` 단일 출력).

추가로 guide body 가 update_mode feature 정본 미정합:
- L717: `git clone --branch $BRANCH` 표기 — BRANCH default 가 empty 라 변수 unset 노출.
- L739-742: `[update 동작 — clean install pattern (ADR-0023)]` 단락이 "매 install 호출은 $WIKIHUB_HOME 디렉토리를 wipe 후 latest tag 로 다시 clone" 안내 — update_mode feature 가 명시적으로 **폐기** 한 동작 + ADR-0023 Note (2026-05-17) 와 직접 충돌.

**Evidence**:
```bash
# install.sh:1201-1203
    fi
    _step8_guide                 # fresh 의 운영자 안내 (update mode 는 자동 진행)
    _step11_banner
```
comment 가 의도를 "update-skip" 으로 명시하나 실제 호출 가드 없음.

**Suggested fix**: `[[ "$INSTALL_MODE" == "fresh" ]] && _step8_guide` 가드 추가 + guide body L739-742 의 "clean install pattern" 단락을 ADR-0023 Note 의 fresh/update 분리 모델 설명으로 교체 (또는 ADR 링크만).

---

### LOW-1: `_enabled_vaults_yaml` bash fallback 이 `enabled: false` 필터링 안 함
**File/Line**: install.sh:1002-1010
**Issue**: 설계 §3 (v3 본문 L484-489) 는 bash fallback 의 한계로 "enabled: false 필터링은 best-effort (yaml indent 의존)" 라고만 명시. 실제 구현은 **필터링 자체를 안 함** — 모든 `- id:` 항목을 그대로 출력.

```bash
# install.sh:1002-1010
awk '
    /^vaults:/ {in_vaults=1; next}
    in_vaults && /^[^[:space:]]/ {in_vaults=0}
    in_vaults && /^[[:space:]]*-[[:space:]]*id:/ {
        gsub(/^[[:space:]]*-[[:space:]]*id:[[:space:]]*/, "")
        gsub(/[[:space:]]*#.*/, "")
        print
    }
' "$yaml"
```
영향: rollback 도중 venv 손상 분기에서 `_systemd_start_after_update` 가 비활성 vault 까지 start 시도 → spurious failure. V11 (PASS) 의 rollback 시나리오는 venv 정상이라 trigger 안 되는 dormant gap.

**Suggested fix**: awk 에 enabled key lookahead 추가 — 또는 설계 본문 표현을 "필터링 미수행, 모든 vault id 출력" 으로 narrow.

---

### LOW-2: `_resolve_ref` path 2 의 `origin/` prefix 가 fresh/update 분기 비대칭
**File/Line**: install.sh:298-304 (fresh path strip) vs 838-842 (update path prepend)
**Issue**: fresh path 의 `_step2_clone` 는 `git clone --branch X` 의 bare name 요구라 `origin/` strip. update path 의 `git reset --hard X` 는 remote-tracking ref 요구라 `origin/` prepend. 같은 BRANCH env 에 대해 두 코드패스가 정반대로 변환 — 설계 §4 path 2 에 비대칭 명시 없음.

운영 결과 (`BRANCH=feature/foo`):
- fresh: `git clone --branch feature/foo` (정상)
- update: `git reset --hard origin/feature/foo` (정상 if remote 에 push 된 상태)

기능 정합. spec 정본화 누락 — 첫 update path 전환 (F4→update_mode 첫 배포) BRANCH override 회귀 surface 위험.

**Suggested fix**: §4 path 2 본문에 "fresh path 는 bare name, update path 는 `origin/` prefix 정합" 한 줄 추가. 별도 helper `_normalize_branch_for_<context>` 추출 (low priority).

---

### LOW-3: `_resolve_ref` path 1 의 tag 부재 fatal 가 update mode 에만 동작
**File/Line**: install.sh:821-829
**Issue**: 설계 §4 path 1 는 "`--version <tag>` flag 명시 + tag 존재 → `refs/tags/<tag>`. tag 부재 시 fatal exit" 무조건 명시. 구현은 `if [[ "$INSTALL_MODE" == "update" ]]; then git rev-parse … local check` — fresh mode 는 local check skip, `git clone --branch <tag>` native error 위임.

영향: fresh path `--version v9.9.9` 호출 시 `git clone` stderr 노출되지만 설계 명시의 "fetch 후 tag 목록 확인" 메시지 안 나옴.

**Evidence**:
```bash
# install.sh:822-829
if [[ "$INSTALL_MODE" == "update" ]]; then
    if ! git -C "$WIKIHUB_HOME" rev-parse "refs/tags/${EXPLICIT_VERSION}" >/dev/null 2>&1; then
        err "--version ${EXPLICIT_VERSION}: tag 부재."
        err "  fetch 후 tag 목록 확인: git -C $WIKIHUB_HOME tag --list"
        exit 1
    fi
fi
```

**Suggested fix**: fresh path 도 `git ls-remote --tags $WIKIHUB_REPO_URL "refs/tags/${EXPLICIT_VERSION}"` 로 pre-check (network 1회 추가). 또는 설계 §4 path 1 에 "fresh path 는 git clone native error 위임" 명시.

---

### LOW-4: `render_systemd_units.py --get-mount-path` 가 `local_path` fallback (설계 미명시)
**File/Line**: scripts/_helpers/render_systemd_units.py:385-398 vs analysis_and_design.md §6.1 (L730-732)
**Issue**: 설계 §6.1 `--get-mount-path` 동작: "`vaults[*]` 에서 id 매칭 entry 의 `options.mount_path` 출력. 미발견 exit 1". 구현은 `mount_path` 없으면 `local_path` fallback.

```python
# render_systemd_units.py:387-391
mp = (v.get("options") or {}).get("mount_path", "")
if not mp:
    # fallback to local_path
    mp = v.get("local_path", "")
```

yaml.example 에서 두 필드 동일 (`~/wikihub-instance/vault/gdrive`) 라 운영 결과 동일. 설계 정본화 시 의도 명시 필요.

**Suggested fix**: 설계 §6.1 `--get-mount-path` 동작에 "`mount_path` 우선, 부재 시 vault top-level `local_path` 로 fallback (ADR-0019 의 alias)" 추가. 또는 fallback 제거 후 yaml schema 가 `mount_path` 필수 enforce.

---

### LOW-5: `_step10_verify` 가 mount@ 만 검증 — vault@.timer / lint.timer 미검증
**File/Line**: install.sh:1123-1142 vs §9.2 V10·V14
**Issue**: 설계 §3 Step 10 의사코드 (L494-512) 도 mount@ 만 verify — 설계대로 구현됨. 단 §9.2 V10 "active service 의 systemctl show 에 반영" 시나리오 검증 범위가 mount@ 로 한정. mount@ 가 vault@ 의 `Requires=` dependency 라 mount fail = vault fail 동치 → spec 정합. 단 spec 정본 측 범위 명시 누락.

**Suggested fix**: §3 Step 10 본문에 "vault@.timer / lint.timer 는 시간 trigger 라 install.sh 단계에서 is-active 안 되는 게 정상 — verify 는 mount@.service 만" 한 줄 추가.

---

### LOW-6: rollback 의 `_step8_systemd_render` 실패 분기 daemon-reload 단독 fallback 부재
**File/Line**: install.sh:982-983
**Issue**: 설계 §3 `_rollback_if_failed` (L286-287) 마지막 분기에서 `_step8_systemd_render` 호출 후 실패 warn 만 + `systemctl daemon-reload 직접 호출` 운영자 fallback 안내. 구현 동일. CRIT-N2 가 stop 직후 daemon-reload 를 lock 한 이유와 대칭으로, rollback render 실패 분기에도 daemon-reload 만이라도 자동 fallback 호출이 자연스러움 (stale unit 으로 start 시도 위험).

**Suggested fix**: render 실패 분기에 `systemctl --user daemon-reload || true` 단독 fallback 1줄 보강. 설계 §3 의사코드도 동일 줄 추가.

---

## Verdict

**Accept with MED-LOW backlog**.

- CRIT 0 · HIGH 0 — Step 4 DoD 만족.
- MED 3건 중 MED-2 (VM 테스트 4 fix back-port) 와 MED-3 (`_step8_guide` update 호출) 는 **Step 3 영역 내 surgical patch** 로 처리 권장 (analysis_and_design.md 본문 갱신 + install.sh:1202 mode guard 추가).
- MED-1 (§6.1 substitution key drift) 은 spec 정본화 측 정확도 — 운영 영향 없음, helper 변경 시 헷갈림 방지용. analysis_and_design.md §6.1 의 key 예시 갱신 권장.
- LOW 6건 은 backlog (별도 후속 feature 또는 §6.1 doc-patch).

ADR-0030 의 4 sub-decision 모두 코드에 정확히 trace:

| ADR-0030 Decision | 구현 위치 |
|---|---|
| sub-1 stop/start sequence | `_systemd_stop_before_update` (install.sh:1013) + `_systemd_start_after_update` (1043) + `_wait_mount_ready` (1068) |
| sub-2 unstaged guard | `_step2_update` 2a (891-900) + `_validate_wipe_target` (251) + `_confirm_force_fresh_wipe` (279) |
| sub-3 rollback trap | `_step2_update` L877 trap 등록 + `_rollback_if_failed` (951) — SIGINT / pre-reset / post-reset 3분기 |
| sub-4 ref chain | `_resolve_ref` (819) — path 1~5 순서 정합 |

CRIT-N1 (rollback re-render+restart) · CRIT-N2 (stop+daemon-reload) · HIGH-N3 (`--version` 인자 강제 소비) · HIGH-N4 (fd 200 close before exec) 모두 코드에 lock. V1·V2·V13·V14 PASS 결과 일관.

## Notes

- `_step8_systemd_render` 가 fresh 모드에서도 호출 (install.sh:1193 — mode guard 없음). 첫 fresh install 직후 `wikihub.yaml` 이 default `enabled: false` 라 render 결과는 stale-unit 정리만 — 운영 영향 없음. 설계 §3 main flow 와 일치.
- helper 의 atomic write `os.replace(str(tmp), str(out))` 는 POSIX rename atomic — V14 mtime 보존 정합.
- `_step8_wh_setup_skill_meta` 가 update mode 만 호출 (line 1106) — fresh path 의 skill 등록은 `_step6_agent_skill` stub 상태라 F5 완료 시까지 dormant. 설계 §3 Step 6 의 "stub 만 (변경 없음)" 정합.
- ref chain path 4 banner output 이 `warn` (stderr) — 설계 §4 path 4 의 "banner 에 명시" 는 stdout banner 였을 가능성. 실 운영에서 tee 합쳐서 가시성 동일.
- `_step11_banner` (1145-1157) 는 fresh 모드에서 `transition` / `ref` 라인 미출력 — 정상.
- VERSION ↔ banner export chain 정합: `_step2_update` L946-947 export → `_step11_banner` L1152 read. 표기 `v${INSTALL_OLD_VERSION:-?} → v${INSTALL_NEW_VERSION:-?}` 는 설계 §3 Step 11 의 `v0.1.0 → v0.1.1` 와 형식 정합.
- setup.md §Step 2 (line 45-64) 책임 이관 표기 명확 — "install.sh 가 systemd unit render 책임" 명시 + helper Contract §6.1 링크 + placeholder 메시지 정의 모두 있음. Step 3·4·5 등 후속 step 의 `/wh:setup` 책임 분배는 그대로 유지. 정합.
- `_acquire_install_lock` 가 `_detect_mode` 보다 먼저 main 에서 호출 (1164 → 1169) — 설계 §3 main flow 와 정합. 단 install.sh:79 의 `mkdir -p "$WIKIHUB_INSTANCE_ROOT"` 가 top-level 로 lock 호출보다 먼저 수행 — 정합.
- `_step2_update` 의 trap 등록 (L877) 이 `PRE_UPDATE_REF` capture (L875) 보다 한 라인 뒤 — 설계 LOW-N3 "trap 등록을 함수 진입 즉시" 의 의도와 약간 차이. `git rev-parse HEAD` 실패 시 trap 미등록 상태로 `set -e` exit 가능. 운영에선 `.git` 존재가 `_detect_mode` precondition 이라 trigger 안 되는 dormant gap (LOW 미만, 보고 생략).
