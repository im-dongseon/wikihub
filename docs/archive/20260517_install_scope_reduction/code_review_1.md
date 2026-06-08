# Code Review 1 — install_scope_reduction (Implementation angle)

**Reviewer**: Code correctness / Implementation reliability persona
**Date**: 2026-05-18
**Scope**: Step 3 implementation (commit 882a882) — install.sh + scripts/lib/yaml_writer.py + scripts/lib/config.py + scripts/requirements.txt + _system/commands/setup.md + docs/adr/0023 Note + features/backlog.md

## Summary

전반적으로 design v2 의 lock 항목 (CRIT-A1·A2, HIGH-S1·S2·S3·A1·A2) 은 코드에 정확히 반영됐다. sparse-checkout 의 위치(`reset --hard` 직후, rollback 본문 포함) · yaml_writer 의 PID-suffix `.tmp` 패턴 · ruamel exact pin · 비대화 fallback exit 1 의 setup.md 명시 등 핵심 결정이 모두 정합. 다만 **3 건의 명백한 결함**이 V<N> 진입 전 fix 권장: (1) `wikihub.yaml.example:2-3` 의 header 주석이 supersede 된 동작 ("install.sh 가 복사") 을 여전히 명시 — 운영자 혼동 + ADR-0031 §Decision A 위반, (2) `docs/adr/0030 §Notes` 가 "ref resolution chain → ADR-0031 신설 검토" 라는 stale placeholder 보유 — ADR-0031 이 이미 yaml template materialization 으로 점유돼 ADR number 충돌, (3) `_write_installed_versions_sidecar` 가 ADR-0031 §Decision A 의 atomic write spec (fsync + 실패 시 .tmp 정리) 을 부분만 따르고 cleanup hook 부재 — set -euo pipefail 환경에서 `cat > $tmp` 실패 시 orphan tmp 잔존. 그 외는 minor.

## Findings

### [HIGH-CR1-1] `wikihub.yaml.example` header 주석이 ADR-0031 위반된 옛 동작을 명시

**Where**: `wikihub.yaml.example:2-3`

**Issue**:
```yaml
# install.sh 가 `~/wikihub-instance/wikihub.yaml` 에 복사 (없을 때만).
# 메인테이너가 vault 정의 + credentials_path + bootstrap_allowed 채운 후 /wh:setup 호출.
```
설계 v2 와 `_step5_yaml → _step5_instance_dirs` 의 구현 변경 핵심은 "install.sh 는 yaml 한 글자도 안 만짐" (analysis_and_design.md §1.2 Invariant B). 그런데 본 파일 헤더가 정확히 그 옛 책임을 자기 정본화한 채로 남아있음. 운영자가 `.example` 을 열어보면 첫 줄에서 잘못된 안내를 읽고 install.sh 가 yaml 을 만들었다고 기대 → `/wh:setup` 첫 호출 의무 누락 → V16 시나리오 (yaml 부재 상태 systemd timer enable) 가 실제 운영에서 발생.

**Recommendation**: 헤더 2-3 줄을 다음과 같이 갱신.
```yaml
# WikiHub 운영 정본 (wikihub.yaml) 의 read-only template — ADR-0031.
# `/wh:setup` 첫 호출이 본 파일을 read → derived 4필드 patching → $WIKIHUB_INSTANCE_ROOT/wikihub.yaml 에 atomic write.
# 이후 메인테이너가 operational yaml 에서 vault 정의 + credentials_path + bootstrap_allowed 채운 후 /wh:setup --enable 재호출.
```
또한 변경하더라도 본 파일은 sparse-checkout fetch list 에 포함이므로 운영 타깃에 그대로 배포됨 — text drift 가 운영자 first-touch UX 결정.

**Effort**: small

### [HIGH-CR1-2] ADR-0030 §Notes 의 "ADR-0031 신설 검토" placeholder 가 ADR-0031 점유와 충돌

**Where**: `docs/adr/0030-update-workflow-orchestration.md` §Notes (commit 0a83135 부터 거주, Step 3 에서 supersede Note 추가됐지만 본 §Notes 는 미수정)

**Issue**: 본문에 "ref resolution chain (sub-4) 만 별도 ADR-0031 로 분리 가능" + "v0.2.x release engineering 확장 시 (e.g. tag signature verification) **ADR-0031 신설 검토**" 라는 stale placeholder 가 남아있음. ADR-0031 은 본 feature 가 yaml template materialization 으로 이미 채택 + Status `Proposed` (Step 4 후 Accepted) → V<N> 통과 후 영구 점유. v0.2.x 의 ref resolution 분리 요구가 발생하면 ADR-0032 이상으로 신설해야 하는데, 본 §Notes 가 ADR-0031 을 미래 후보로 가시화 → 두 ADR 간 의도 ambiguity. `docs/adr/README.md` 의 인덱스를 보는 작업자가 ADR-0031 의 실제 정본 (yaml) 과 ADR-0030 §Notes 의 미래 placeholder (ref resolution) 간 혼란 발생.

**Recommendation**: ADR-0030 §Notes 의 마지막 줄을 "v0.2.x release engineering 확장 시 (e.g. tag signature verification) **별도 ADR 신설 검토** (현 시점 ADR-0031 은 yaml template materialization 에 점유)." 로 수정. ADR-0009·0010·0030 의 Note 추가는 design DoD C2·C7·C8 으로 lock 됐는데 본 detail 만 누락 — feature scope 내 결함.

**Effort**: small

### [HIGH-CR1-3] `_write_installed_versions_sidecar` atomic write 가 ADR-0031 §Decision A 의 spec 일부 미충족

**Where**: `install.sh:607-625`

**Issue**: 주석은 `tmpfile + os.replace 패턴 (bash 환경). same-directory + PID suffix` 라고 약속하나 실제 구현은:
1. `set -euo pipefail` 활성 + trap 등록은 `_step2_update` 안에서만 → fresh path 호출 시 trap 없음. `cat > "$tmp" <<EOF` 가 `ENOSPC` 또는 권한 결함으로 fail 시 errexit → process 즉시 종료 → orphan `${target}.tmp.$$` 잔존. 다음 호출의 sidecar writer 는 PID 가 다르므로 stale 식별·cleanup 메커니즘이 없다 (yaml_writer.py 의 `_cleanup_stale_tmp` 와 달리 bash 측은 부재).
2. `mv "$tmp" "$target"` 전 `sync` (또는 file fsync) 호출 부재 — OCI 의 unexpected reboot 시 INSTALLED_VERSIONS.json 이 zero-byte 또는 부재 상태로 진입 가능. 다음 install.sh 호출이 자동 재작성하므로 fatal 은 아니지만 sidecar 부재 상태 `/wh:setup` Step 0 호출 시 `gws --version` stdout fallback 으로 떨어짐 (MED-S2 가 회피하려던 brittle path 가 다시 활성).
3. `tmp` 파일 위치는 `$WIKIHUB_HOME/_system/INSTALLED_VERSIONS.json.tmp.$$` — same-directory OK, PID suffix OK. mv 의 atomic rename 도 same-FS 보장 OK. 다만 stale `.tmp.*` 누적 위험.

ADR-0031 §Decision A "atomic write 정합" 표의 `SIGTERM mid-write` 행이 "다음 helper 호출 진입 시 자신의 PID 와 다른 `.tmp.*` 발견 시 unlink" 를 invariant 로 명시. 본 bash sidecar 는 이 cleanup 절차가 없음.

**Recommendation**: `_write_installed_versions_sidecar` 진입 시 `find "$(dirname "$target")" -maxdepth 1 -name "$(basename "$target").tmp.*" -mmin +5 -delete 2>/dev/null || true` 추가 (5분 이상 된 stale tmp 정리) + `cat > "$tmp" <<EOF ... EOF` 다음에 `sync` 호출 (또는 `sync -f "$tmp"` GNU coreutils 8.24+, Ubuntu 22.04+ 보장). 그리고 `mv` 전에 cleanup trap 추가:
```bash
local tmp="${target}.tmp.$$"
trap "rm -f '$tmp'" RETURN ERR
```
RETURN 은 정상 종료 시도 cleanup 시도하나 mv 후엔 file 부재라 no-op — 안전.

**Effort**: small

### [MED-CR1-4] yaml_writer.py `round_trip=False` 분기의 lazy import 가 install 시점 supply chain 검증 lock 우회

**Where**: `scripts/lib/yaml_writer.py:64-67`

**Issue**: round_trip=False 시 `import yaml as _pyyaml` 을 함수 내부에서 lazy import. PyYAML 은 별도 hash-pinned dep (`requirements.txt:4`) 라 일반 케이스는 OK. 그러나:
1. 본 분기는 코드 주석에 "v0.1.0 사용처 없음" 명시 — 그러면 왜 분기를 유지하는가? Karpathy §2 (Simplicity First) 위반 — 약 50% 코드라인이 dead 분기.
2. lazy import 가 venv 미활성 환경에서 NameError → AttributeError 우회 → 디버깅 어려움.

**Recommendation**: v0.1.0 scope 내에선 `round_trip=False` 분기 자체 삭제 — 호출처 (`atomic_yaml_write(round_trip=True)` default) 가 한 곳도 안 쓰니 삭제하고, 미래 필요 시 다시 추가. analysis_and_design.md §4.4 의 spec 도 `atomic_yaml_write(path, data, *, round_trip=True)` 만 정합. False default 케이스를 keep 하려면 backlog 항목으로 분리.

**Effort**: small

### [MED-CR1-5] yaml_writer `_cleanup_stale_tmp` 가 stat 권한 결함 시 silent — entry 가 directory 일 때 `unlink()` 실패 분리 안 함

**Where**: `scripts/lib/yaml_writer.py:96-103`

**Issue**: `entry.unlink()` 가 `IsADirectoryError` (Python OSError subclass) 일 때도 `OSError` 분기로 silent pass. `.<name>.tmp.<digits>` 패턴 디렉토리는 정상 운영에선 안 생기지만, 운영자가 실수로 동일 명명 디렉토리를 만들면 본 helper 가 매 호출 디렉토리를 unlink 시도하다가 silent fail → 무한 시도. 영향 작지만 진단 어려움. 또한 `entry.is_file()` 가드 부재.

**Recommendation**: `if not entry.is_file(): continue` 를 `try: stale_pid = int(...)` 직전에 추가. ADR-0031 §Decision A atomic write 표의 "concurrent 호출" cell 정합.

**Effort**: small

### [MED-CR1-6] `_apply_sparse_checkout` 실패 분기 부재 — `_step2_clone` 에서 빈 sparse 로 진입 시 `git checkout` 무동작

**Where**: `install.sh:294-300, 320-322`

**Issue**: `git sparse-checkout init --no-cone >/dev/null` 또는 `git sparse-checkout set ... >/dev/null` 실패 (예: 디스크 풀, git 버전 too old — Ubuntu 22.04 의 git 2.34 는 지원하지만 OCI custom image 가 2.20 이하면 init 시 unknown subcommand) 시 `set -e` 로 process 종료. _step2_clone 안에는 trap 없음. `git clone --no-checkout` 직후 `_apply_sparse_checkout` fail 하면 `$WIKIHUB_HOME/.git` 만 있고 working tree 부재 상태로 process 종료 → 다음 install.sh 재호출 시 `_validate_wipe_target` 가 `.git` 만 보고 통과 → wipe + re-clone. 회복 OK 지만 운영자가 fail 사유 알기 어려움. 또한 `set "${WIKIHUB_SPARSE_PATHS[@]}"` 가 bash array expansion 인데 install.sh 가 `#!/usr/bin/env bash` 라 OK, 그러나 sh fallback 으로 호출되면 array 미지원 (bash 강제 shebang 정합).

**Recommendation**: `_apply_sparse_checkout` 본문 명시 fail 처리:
```bash
_apply_sparse_checkout() {
    git -C "$WIKIHUB_HOME" sparse-checkout init --no-cone >/dev/null 2>&1 \
        || { err "sparse-checkout init 실패 — git 버전 (>=2.27 필요): $(git --version)"; return 2; }
    git -C "$WIKIHUB_HOME" sparse-checkout set "${WIKIHUB_SPARSE_PATHS[@]}" >/dev/null \
        || { err "sparse-checkout set 실패 — paths: ${WIKIHUB_SPARSE_PATHS[*]}"; return 2; }
}
```

**Effort**: small

### [MED-CR1-7] setup.md Step 0.2 의 `vaults[*].local_path` derived 정의가 yaml.example 의 default 와 다른 path 패턴

**Where**: `_system/commands/setup.md:50` (Step 0.2 derived 4필드 catalog)

**Issue**: spec 은 `vaults[*].local_path → <instance.root>/vault/<vault.id>` (single `vault/`) — 그런데 `wikihub.yaml.example:18` 의 default 는 `~/wikihub-instance/vault/gdrive` 로 정합 (단수 `vault/`). 그러나 install.sh `_step8_guide` 의 안내 (line 728-729 commit 후) 는:
```
├── vault-<vault_id>/               # vault local mirror (자동)
```
패턴이 `vault-<id>/` (하이픈, 단일 디렉토리 per-vault). spec 과 install.sh 가이드와 `wikihub.yaml.example` 의 default 가 3 종 사이에서 일관성 없음. Step 0 가 patching 시 `<instance.root>/vault/<vault.id>` 로 작성하면 example default 와 정합 (단복수 일관) → 운영자가 `_step8_guide` 의 안내 (`vault-<vault_id>/`) 를 신뢰해 mkdir 수동 생성하면 yaml mismatch. drift 분기 트리거. install.sh 가이드 텍스트만 후행 정합 fix 필요.

**Recommendation**: install.sh `_step8_guide` line 728-729 의 `vault-<vault_id>/` 를 `vault/<vault_id>/` 로 변경. 또는 spec / yaml.example 을 `vault-<id>` 로 표준화 — 후자는 path 호환성 깨짐, 전자가 1자 edit. 본 issue 는 install_scope_reduction feature scope 내 — `_step8_guide` 의 yaml-aware 갱신이 Step 3 의 명시 작업 항목 (§4.3).

**Effort**: small

### [LOW-CR1-8] yaml_writer.py module-level `_yaml_rt` 싱글톤이 동시 호출 thread-safety 없음

**Where**: `scripts/lib/yaml_writer.py:21-23`

**Issue**: `_yaml_rt = YAML(typ="rt")` 가 모듈 import 시 1회 생성. ruamel.yaml 의 YAML 인스턴스는 thread-safe 가 아님 (공식 doc — internal state 보유). v0.1.0 의 /wh:setup 은 single-threaded 라 문제 없음. v0.2.x 에서 vault-fetch 가 multi-thread (현재 multiprocessing 만) 또는 다른 호출처가 들어오면 데이터 corruption 위험. ADR-0031 §Decision A "single-writer invariant" 가 file-level 만 명시 — module-level singleton 의 reentrancy 는 미명시.

**Recommendation**: module docstring 또는 함수 docstring 에 "본 helper 는 single-threaded 호출 가정 (ruamel YAML 인스턴스 singleton)" 명시. 향후 thread/process 분기 추가 시 instance 를 function-local 로 생성하도록 변경.

**Effort**: tiny

### [LOW-CR1-9] `_step8_guide` 의 update 안내에서 `--branch $BRANCH` 표기가 stale

**Where**: `install.sh:756` (이전 `git clone --branch $BRANCH` → diff 후 `git clone — sparse, ADR-0023`)

**Issue**: diff 에선 `# repo (install.sh 가 git clone — sparse, ADR-0023)` 로 변경됐는데 `$BRANCH` 변수 reference 제거 됐음 — OK. 다만 그 다음 줄들의 안내 텍스트가 fresh path 만 호출되는데도 update path 도 포함된 듯한 광범위 안내 (`업데이트는 같은 명령 한 번 더`) 유지 — 의미적 일관 OK. 단순 stylistic.

**Recommendation**: 변경 불필요. backlog item 후보.

**Effort**: tiny

### [LOW-CR1-10] `config.py:_log.warning` 의 logging handler 의존성 — install/setup invocation 시 stderr 로 도달하는지 미확인

**Where**: `scripts/lib/config.py:118-122`

**Issue**: `_log = logging.getLogger(__name__)` 만 정의. Module 호출자 (`vault-fetch.py`, `/wh:setup` 의 Python invocation) 가 `logging.basicConfig()` 호출 안 하면 default handler 는 `WARNING` 이상을 stderr 로 출력 — Python 3.2+ default `lastResort` handler 가 stderr 로 보냄, OK. 다만 systemd journal 의 ops-alert 와 분리되는지 검증 필요. V12 시나리오 (mount_path != local_path soft warn) 실행 시 운영자가 메시지를 어디서 볼 수 있는지 (journal 의 vault-fetch unit stderr) 미확인.

**Recommendation**: 운영 테스트 (V12) 시 `journalctl --user -u wikihub-vault@<id> | grep mount_path` 확인. 코드 fix 불필요.

**Effort**: tiny (검증만)

## Verification readiness check (V1~V16 from analysis_and_design.md §8)

| V | 실행 가능? | 비고 |
|---|---|---|
| V1 (sparse fresh) | ✓ | `WIKIHUB_SPARSE_PATHS` + `_apply_sparse_checkout` lock 정합 |
| V2 (재호출 sparse 유지) | ✓ | `.git/info/sparse-checkout` 영속 보장 |
| V3 (pre-feature full→sparse) | ✓ | `_step2_update` 의 `_apply_sparse_checkout` 호출이 reset 직후 |
| V4 (/wh:setup 첫 호출 materialize) | ⚠ | setup.md Step 0 spec 은 lock — 단 V4 실행 자체는 setup.md 가 hermes/F5 의 dispatch 의존이라 V5 정합 검증 가능한 상태인지 확인 필요 (F5 미완) |
| V5 (WIKIHUB_INSTANCE_ROOT custom) | ⚠ | V4 와 동일 의존 — yaml_writer.py 호출은 spec 만, runtime 호출처 (setup.md Step 0 의 실제 Python entry script) 가 본 feature 의 산출물에서 누락 |
| V6 (재호출 drift no-op) | ⚠ | V4 의존 |
| V7~V13 | ⚠ | V4·V5 의존 — Step 0 의 Python implementation 부재로 모두 blocked. spec → runnable 코드 gap 가 본 feature 의 미완 항목 |
| V14 (rollback sparse re-apply) | ✓ | `_rollback_if_failed` 본문 sparse 호출 lock |
| V15 (INSTALLED_VERSIONS.json) | ✓ | `_write_installed_versions_sidecar` 동작 검증 가능 — HIGH-CR1-3 의 robustness 강화 후 권장 |
| V16 (yaml 부재 systemd timer enable) | ✓ | `_step8_guide` warn + `_step11_banner` update warn 가시화 검증 가능 |

**핵심 gap**: V4~V13 의 Step 0 runtime 코드 (`/wh:setup` 의 실제 Python entry — `scripts/_helpers/wh_setup.py` 또는 동등) 가 본 commit 에 부재. setup.md 의 spec 만 lock 됐고 코드 실현은 hermes/F5 dispatcher 에 의존. analysis_and_design.md §4.5 도 pseudo-code 만 명시, 실제 Python module 신규 항목 없음. 본 feature 의 DoD F3 (`/wh:setup` 첫 호출이 wikihub.yaml 을 atomic 생성`) 은 hermes adapter 가 setup.md 의 pseudo-code 를 실행 가능한 Python 으로 번역할 때만 충족. **이는 본 feature scope 가 spec-only 임을 시사** — Step 4 V<N> 의 V4~V13 은 hermes 호출 또는 manual Python script 로만 fire 가능.

## Backlog candidates (out of feat scope)

- yaml_writer thread-safety hardening (LOW-CR1-8 의 확장) — v0.2.x multi-process vault-fetch 와 단일 helper 호출 공존 시.
- `_step8_guide` 의 path layout 안내와 yaml.example default 의 통일 (MED-CR1-7 의 root cause) — 단복수 정합 hardening + `vault-<id>` vs `vault/<id>` 표기 1 source 화.
- bash `_write_installed_versions_sidecar` 를 Python 으로 마이그레이션 — yaml_writer.py 와 동일 atomic invariant share. v0.2.x 검토.
- ruamel.yaml dependency 의 `--hash=sha256:<TBD>` lock (현 requirements.txt 4-9 line 의 후속 hardening 주석 명시).

## Overall recommendation

- [ ] Approve as-is
- [x] **Approve with minor changes** (HIGH-CR1-1·2·3 fix 후 V<N> 진입 — 모두 small effort)
- [ ] Approve with major changes (HIGH items)
- [ ] Request rework (CRIT items)

HIGH-CR1-1 (yaml.example header drift) + HIGH-CR1-2 (ADR-0031 number 충돌) + HIGH-CR1-3 (sidecar atomic robustness) 셋 다 small effort 로 fix 가능. MED·LOW 는 backlog 또는 V<N> 후 fix 권장. 코드 본체 (sparse-checkout 위치·rollback 분기·setup.md Step 0 spec·yaml_writer 패턴) 는 design v2 와 정합. V4~V13 의 runtime gap 은 본 feature 의 spec 책임 vs hermes runtime 책임 split 에서 후자 영역 — backlog 항목 `hermes_adapter` (F5) 으로 추적.

## Notes for synthesis

본 리뷰는 implementation reliability 측면. spec/architecture 또는 security 측면의 second reviewer 가 (a) yaml.example 의 sparse 배포 시 license/header 정책 (b) ADR cross-reference graph 의 정합성 (c) Step 0 의 runtime entrypoint 책임 위치 (`/wh:setup` Python module vs hermes adapter 의 dispatch) 를 검토하면 V<N> 진입 전 더 robust 한 closure. 본 리뷰의 HIGH-CR1-1·2·3 는 spec 측 리뷰어와 무관하게 fix 권장.
