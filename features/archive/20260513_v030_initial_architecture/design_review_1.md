# Design Review 1 — feature-dev:code-reviewer

- **Reviewer**: feature-dev:code-reviewer subagent (Claude, context-fresh)
- **Date**: 2026-05-13
- **Target**: `analysis_and_design.md` §4 (Design) + ADR-0001~0004
- **Files read**: `analysis_and_design.md` (full), `plan.md`, ADR-0001~0004, `AGENTS.md`, `docs/agent_dev_guide.md`
- **External verification**: `hermes -z` flag confirmed valid via live Hermes docs

## Summary

설계는 구조적으로 견고. ADR-0001~0004의 결정이 §4에 충실히 반영됨 (vault namespace 분리, CLI subprocess 트리거, Workspace OAuth, Direct Drive API). systemd unit 설계·`_state/` 일관성·F2~F6 의존 그래프 모두 정합. 다만 **must-fix spec 버그 4건**이 Python pseudo-code 계약에 있어 F3/F5 구현자를 직접 오도함: `VaultSyncFatal`의 `vault_id` 누락(silent AttributeError로 fatal-alert 경로가 무력화), `main()`의 cfg 미전달 시그니처 충돌 2건, 토큰 atomic write의 prose/code 모순. 추가로 시퀀스 다이어그램과 §4.6.2 프롬프트 설계가 모순. **Verdict: minor revisions required.**

## Findings

### High confidence — must fix before approval

#### H1. §4.2.3 + §4.6.6 — `VaultSyncFatal`이 `vault_id` 필드 누락

§4.2.3 정의:
```python
class VaultSyncFatal(Exception):
    reason: str
    remediation: str
```

§4.6.6 접근 사이트:
```python
f"/ops alert vault={err.vault_id} severity=fatal\n"
```

**Evidence**: lines 367–370 (class), line 917 (access)

**Impact**: 최상위 운영 안전망인 fatal-alert 경로가 매번 `AttributeError`를 발생시키고, outer `except Exception: pass`가 이를 silent로 삼킴. 메인테이너는 fatal vault 실패의 Telegram 알림을 영영 받지 못함. 본 spec에서 **가장 심각한 운영 갭**.

**Suggested fix**:
```python
class VaultSyncFatal(Exception):
    vault_id: str      # 추가
    reason: str
    remediation: str
```
§4.7.4의 모든 raise 사이트도 `vault_id` 전달하도록 갱신.

---

#### H2. §4.2.5 — `main()`의 호출 시그니처 2건 불일치

`main()` 라인 404에서 `config = load_wikihub_yaml()` 로드하지만 다음 두 호출에 전달 안 함:

1. Line 409: `notify_via_hermes_optional(e)` — 1 arg. §4.6.6 정의: `notify_via_hermes_optional(err, cfg)` — 2 args 요구
2. Line 415: `invoke_hermes(vault_id, result)` — 2 args. §4.6.3 정의: `invoke_hermes(vault_id, result, cfg)` — 3 args 요구

**Evidence**: lines 403–418 (main body), line 848 (invoke_hermes), line 913 (notify_via_hermes_optional)

**Impact**: F3 구현자가 main() pseudo-code를 따르면 두 사이트 모두 `TypeError`. config 변수가 스코프에 있는데도 누락되어 일관성 깨짐.

**Suggested fix**:
```python
except VaultSyncFatal as e:
    log_error(e); notify_via_hermes_optional(e, config)
    sys.exit(2)
...
if result.has_changes:
    invoke_hermes(vault_id, result, config)
```

---

#### H3. §4.1.2 vs §4.6.2 — 시퀀스 다이어그램이 프롬프트 설계와 모순

§4.1.2 다이어그램:
```
Sync->>Hermes: hermes -z "/ingest --vault gdrive --files [...]"
```

§4.6.2 명시:
> "변경 파일 목록을 프롬프트에 직접 임베딩하지 않는다. Hermes가 `last_sync.json`을 파일 시스템 read tool로 직접 읽음"

실제 렌더링되는 프롬프트:
```
/ingest --vault gdrive --changed-count 3 --deleted-count 1
변경 파일 목록은 _state/gdrive/last_sync.json 참조.
```

**Evidence**: line 262 (diagram), lines 818–834 (§4.6.2)

**Impact**: F5가 다이어그램을 먼저 보고 Hermes skill을 `--files [...]` 입력 가정으로 구현하면 F3의 `--changed-count + last_sync.json` 출력과 정합 안 됨. 통합 단계에서 reconciliation 비용.

**Suggested fix**: 다이어그램 label을 §4.6.2와 일치시킴.

---

#### H4. §4.7.4 — 토큰 pickle 갱신 코드가 prose의 atomic write 요구와 모순

§4.7.4 prose (lines 1029–1030):
> "갱신된 pickle을 매번 atomic write로 덮어씀"
> "atomic write는 `pickle.dumps` 후 tmpfile + `os.rename` 패턴 사용"

§4.7.4 code (line 1017):
```python
token_path.write_bytes(pickle.dumps(creds))  # 비atomic 직접 덮어쓰기
token_path.chmod(0o600)
```

**Evidence**: line 1017 (code), lines 1029–1030 (prose)

**Impact**: F3는 같은 절에서 모순된 지시 받음. 코드를 따르면 SIGKILL 중 pickle 파손 + chmod 분리로 인한 잠깐의 default-umask 노출. 신뢰성 + 보안 리스크.

**Suggested fix**:
```python
import os as _os
data = pickle.dumps(creds)
tmp = token_path.with_suffix('.tmp')
tmp.write_bytes(data)
tmp.chmod(0o600)
_os.rename(tmp, token_path)   # POSIX atomic
```

---

### Medium confidence — should consider

#### M1. §4.6.3 — TimeoutExpired 핸들러가 zombie 남김 + kill 시맨틱 오기재

§4.6.3 line 864–865의 `except subprocess.TimeoutExpired:` 즉시 return하고 `proc.wait()` 안 함. Python 3의 `subprocess.run`은 timeout 시 SIGKILL을 직접 보냄(SIGTERM 우선이 아님). line 885 코멘트("SIGTERM 전송, 응답 없으면 SIGKILL")는 부정확.

**Impact**: 실무상 v0.1.0 단일 vault에서는 저위험. 코멘트 오류가 graceful shutdown 가정을 유발할 수 있음.

**Suggested fix**: line 885 코멘트를 "SIGKILL 직접 전송 (proc.kill)"로 정정. 선택: handler에서 `exc.process.communicate()` 호출하여 zombie reap.

---

#### M2. ADR-0002 — `§3.1.4` stale reference

ADR-0002 Context: "본 feature 분석 §3.1.4에서 합의된 원칙"

`§3.1`은 평면 7항목 리스트로 subsection 없음. `§3.1.4` heading 부재.

**Impact**: 낮음 — 결정은 명확함. 미래 독자가 §3.1을 스캔해야 함.

**Suggested fix**: `§3.1 항목 4 (에이전트 호출 모델)` 로 변경.

---

### Low confidence / nits — optional

#### L1. §4.4.4 — `retry.db` `attempts` 카운터 시맨틱 명시 부족

INSERT 시 0, 실패마다 +1, `>= max_attempts`에서 폐기. `max_attempts: 5`는 "초기 실패 후 5회 재시도(총 6회 시도)"를 의미하지만 YAML 코멘트는 모호.

**Suggested fix**: YAML 코멘트 `max_attempts: 5  # 초기 실패 이후 최대 재시도 횟수 (총 6회 시도)`.

---

## What I checked but found OK

- ADR-0001~0004 모두 §4에 충실 반영
- `VaultSyncRetryable`/`VaultSyncFatal` 시맨틱 일관(§4.2~§4.8 전체)
- `SyncResult`·`ChangedFile` 필드 참조 일관
- systemd `Type=oneshot` + `SuccessExitStatus=0 75` + `OnUnitInactiveSec` + `Persistent=true` 모두 정확
- `_state/` atomic write 정책, SQLite WAL — 정합
- AGENTS.md Step 2 필수 체크리스트 전항목 충족
- Karpathy Simplicity First / Surgical Changes 위반 없음
- Mermaid·YAML 문법 오류 없음
- F2~F6 의존 그래프 순환 없음

## Open questions for author

1. **`VaultSyncFatal`에 `vault_id` 추가 시 인자 위치**: keyword-only로 두면(`vault_id` 먼저, 그 후 `reason`/`remediation`) 기존 raise 사이트가 모두 명확히 깨져서 F3 갱신 강제. positional이면 silent 오류 위험.
2. **prompt injection 신뢰 사슬 명시화**: `{vault_id}` 치환은 YAML 스키마 검증(§4.3.2 `[a-z][a-z0-9_]*`) 통과한 값을 그대로 사용. 본 신뢰 사슬을 명시할지, F3에서 template-format 시점에 재검증을 defence-in-depth로 강제할지.
