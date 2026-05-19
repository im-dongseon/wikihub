---
approved: 2026-05-19
---

# Analysis & Design — hermes_yolo_flag

## 1. 배경 및 목적

2026-05-19 OCI 실증 (v0.1.2 install.sh 직후):

> "install.sh 마지막 단계에서 `hermes chat --skills wh-setup --quiet --query "/wh-setup"` 를 호출하는데, hermes 가 내부에서 위험 명령 (cat | python3, python3 -c 등) 을 실행하려고 하고, Hermes 의 보안 승인 (tirith) 이 이를 차단 (`Choice [o/s/D]: ✗ Denied`) 해서 프로세스가 중단"

`/wh-setup` playbook 의 yaml 검증·상태 확인은 Python 인라인 스크립트로 구성 (ruamel.yaml, json, pathlib 등) — Hermes tirith 가 외부 process exec 을 위험 명령으로 분류해 매번 prompt. install.sh 와 systemd timer 는 noninteractive context 라 prompt 응답 불가 → deny 폴백 → 흐름 중단.

해결: Hermes `--yolo` flag = noninteractive auto-approve mode. install.sh 의 자동 호출과 systemd timer 가 호출하는 oneshot_args 둘 다 동일 plumbing 필요.

## 2. 현행 진단

### 결함 1 — install.sh `_step8_wh_setup_skill_meta` 직접 호출 cmdline

`install.sh:1486-1487` (v0.1.2):
```bash
WIKIHUB_NONINTERACTIVE=1 timeout "$timeout_sec" "$agent_binary" \
    chat --skills wh-setup --quiet --query "/wh-setup" \
    || warn ...
```

`--yolo` 부재 → tirith deny → `||` warn 분기. install.sh 가 성공으로 보이나 실제 skill 메타 갱신·setup playbook 미실행.

### 결함 2 — systemd timer 가 호출하는 oneshot_args (yaml.example + render helper)

`wikihub.yaml.example:57`:
```yaml
oneshot_args: ["chat", "--skills", "{skill}", "--quiet", "--query"]
```

이 array 는 `scripts/_helpers/render_systemd_units.py:147-167` 가 `{skill}` 치환 + ExecStart 의 인자로 그대로 사용. 즉 wh-vault@*.timer 가 fire → wh-ingest service ExecStart → 위 array + `"/wh-ingest"` 로 hermes 호출. 동일하게 tirith deny.

### 결함 3 — install.sh F5 migration code 의 default literal

`install.sh:716-718`:
```python
oneshot = agent.get("oneshot_args") or []
if not any("{skill}" in str(a) for a in oneshot):
    agent["oneshot_args"] = ["chat", "--skills", "{skill}", "--quiet", "--query"]
```

update path 의 schema migration 이 default 값으로 위 array 를 박아넣음. `--yolo` 없는 form 으로 운영자 yaml 을 매번 덮어씀 → 영구 결함.

### 결함 4 — render_systemd_units.py 의 운영자 안내 메시지

`scripts/_helpers/render_systemd_units.py:158-159`:
```
yaml 의 oneshot_args 를 `["chat", "--skills", "{skill}", "--quiet", "--query"]` 로 갱신 필요
```

운영자가 fail-fast 시 보는 권장 form — `--yolo` 부재. 위 결함 1~3 fix 와 동기화 필요.

## 3. 개정 범위

| 파일 | 변경 | 라인 |
|---|---|---|
| `wikihub.yaml.example` | `agent.oneshot_args` 에 `"--yolo"` 추가 | +0 / -0 (array 항목 1개 추가) |
| `install.sh` (F5 migration default) | array literal 에 `"--yolo"` 추가 | +0 / -0 |
| `install.sh` (`_step8_wh_setup_skill_meta`) | cmdline 에 `--yolo` 추가 (info 로그 string 도 동기화) | +0 / -0 |
| `scripts/_helpers/render_systemd_units.py` (안내 메시지) | 권장 form 의 array literal 갱신 | +0 / -0 |

기능 코드 영향 없음 — `{skill}` placeholder 검출 로직은 `--yolo` 유무와 무관.

## 4. 개정 전/후 비교

### yaml.example

Before:
```yaml
oneshot_args: ["chat", "--skills", "{skill}", "--quiet", "--query"]     # ADR-0032 — `{skill}` per-unit placeholder, `--quiet` 로 transcript 차단
```

After:
```yaml
oneshot_args: ["chat", "--skills", "{skill}", "--quiet", "--yolo", "--query"]   # ADR-0032 + 2026-05-19 — `--yolo`: tirith auto-approve (noninteractive 환경 필수, ADR-0032 §sub-3 보강)
```

### install.sh F5 migration

Before:
```python
agent["oneshot_args"] = ["chat", "--skills", "{skill}", "--quiet", "--query"]
```

After:
```python
agent["oneshot_args"] = ["chat", "--skills", "{skill}", "--quiet", "--yolo", "--query"]
```

### install.sh `_step8_wh_setup_skill_meta`

Before:
```bash
"$agent_binary" chat --skills wh-setup --quiet --query "/wh-setup"
```

After:
```bash
"$agent_binary" chat --skills wh-setup --quiet --yolo --query "/wh-setup"
```

(인접 info 로그 string 도 함께 갱신.)

### render_systemd_units.py 안내 메시지

Before:
```
yaml 의 oneshot_args 를 `["chat", "--skills", "{skill}", "--quiet", "--query"]` 로 갱신 필요
```

After:
```
yaml 의 oneshot_args 를 `["chat", "--skills", "{skill}", "--quiet", "--yolo", "--query"]` 로 갱신 필요
```

## 5. 연계 룰/스킬 정합성 검토

- **ADR-0032 (agent invocation, F5)**: `oneshot_args` schema 정합 정본. `--yolo` 는 본 array 의 1 항목 추가로 기존 schema 유지 (form invariant: `{skill}` placeholder 보유). ADR-0032 §sub-3 (agent invocation cmdline) §Note 추가 권장.
- **ADR-0024 (fatal alert contract)**: hermes 호출 실패 → OnFailure ops-alert 경로 영향 없음. `--yolo` 부재로 deny 시 exit code 가 비0이면 OnFailure 발화는 동일.
- **ADR-0023 (install.sh distribution)**: install.sh 변경 1줄 — pipeline 자체 무관. 안전.
- **F5 migration logic invariant**: `{skill}` placeholder 검출 로직은 `--yolo` 유무와 무관 → migration code 의 detect 분기 영향 없음.

ADR-0032 §Note 추가 — `--yolo` 결정 기록.

## 6. 미결 사항

없음.

## 7. Definition of Done

- [ ] `wikihub.yaml.example:57` 의 `oneshot_args` 에 `"--yolo"` 추가 + 주석 갱신
- [ ] `install.sh:718` F5 migration default literal 갱신
- [ ] `install.sh:1486-1487` `_step8_wh_setup_skill_meta` cmdline 에 `--yolo` 추가 + info 로그 string 동기화
- [ ] `scripts/_helpers/render_systemd_units.py:158-159` 안내 메시지 갱신
- [ ] `docs/adr/0032-agent-invocation.md` 에 §Note 추가 (2026-05-19, `--yolo` 결정)
- [ ] `_system/VERSION` 0.1.2 → 0.1.3 bump
- [ ] `features/HISTORY.md` 항목 append
- [ ] systemd render dry-run — wikihub-vault@gdrive.service ExecStart 에 `--yolo` 포함 확인
- [ ] feature dir archive 이동
