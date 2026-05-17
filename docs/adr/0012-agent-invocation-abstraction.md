# ADR-0012: agent invocation 추상화 — `wikihub.yaml.agent.invocation` 분리

- **Status**: Accepted
- **Date**: 2026-05-13
- **Feature**: features/20260513_wikihub_schema_v1
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

ADR-0006(unified orchestration) 채택 시 agent invocation 예시로 `hermes -z "<prompt>"`를 사용했고, F2 작성 중에도 spec·playbook 전반에 `agent -z "..."` 표기가 사용됨. 그러나 **`-z`는 Hermes의 one-shot 플래그**이며, 다른 agent들은 다른 syntax를 갖는다:

| Agent | one-shot 호출 형식 (잠정) |
|---|---|
| Hermes | `hermes -z "<prompt>"` (검증됨) |
| codex-cli | `codex exec "<prompt>"` 추정 (F4·F5 검증 필요) |
| gemini-cli | `gemini -p "<prompt>"` 추정 |
| copilot CLI | one-shot 명료성 불확실 |

`agent -z` 표기는 ADR-0011의 "agent-agnostic spec" 원칙을 위반한다. wikihub의 spec은 특정 agent 종속이 아니어야 한다.

## Considered Options

- **(α) `wikihub.yaml.agent`에 invocation 분리 + install.sh가 default 매핑 (권장)**: yaml에 `binary` + `oneshot_args` 명시. install.sh가 agent type prompt 후 매핑. spec은 추상 표기 `<agent_invocation>`
- **(β) wrapper script로 통일**: `scripts/agent_run.sh "<prompt>"`가 yaml read 후 dispatch. spec은 `agent_run.sh "<prompt>"`
- **(γ) 현 상태 유지 (install.sh에 매몰)**: spec은 `agent -z` 그대로, install.sh가 알아서 처리. spec은 misleading

## Decision

**채택**: (α) wikihub.yaml에 invocation 분리 + install.sh default 매핑

### `wikihub.yaml.agent` 스키마

```yaml
agent:
  type: hermes                  # 'hermes' | 'codex' | 'gemini' | 'copilot' | 'custom'
  binary: /usr/local/bin/hermes # 실행 파일 절대경로 또는 PATH 인식 가능 이름
  oneshot_args: ["-z"]          # one-shot 호출 시 binary 다음에 들어가는 args (prompt는 args 끝에 append)
  skill_prefix: "wh:"           # ADR-0011
  timeout_sec: 600              # 단일 호출 timeout
  notify_on_fatal: true         # ADR-0002·F1 §4.6.6
```

### spec 표기 규약

playbook + ADR + wiki-schema의 호출 예시는 추상 placeholder 사용:

```
<agent_invocation> "/wh:ingest --vault <vault_id>"
```

- `<agent_invocation>` = `agent.binary` + `agent.oneshot_args` 합 (공백 join)
- 실제 호출 예 (Hermes): `/usr/local/bin/hermes -z "/wh:ingest --vault gdrive"`
- 실제 호출 예 (codex, 가설): `/usr/local/bin/codex exec "/wh:ingest --vault gdrive"`

### install.sh의 agent type 매핑 (F4 책임)

신규 설치 시 사용자 prompt → 매핑 → `wikihub.yaml`에 기록:

```bash
# install.sh 의사 코드
read -p "agent type [hermes/codex/gemini/copilot/custom] (default: hermes): " AGENT_TYPE
AGENT_TYPE=${AGENT_TYPE:-hermes}

case "$AGENT_TYPE" in
  hermes)  BINARY="hermes"; ONESHOT_ARGS='["-z"]' ;;
  codex)   BINARY="codex";  ONESHOT_ARGS='["exec"]' ;;     # 검증 필요
  gemini)  BINARY="gemini"; ONESHOT_ARGS='["-p"]'  ;;      # 검증 필요
  copilot) BINARY="?";      ONESHOT_ARGS='[?]'      ;;     # 검증 필요
  custom)
    read -p "binary path: " BINARY
    read -p "oneshot args (JSON array): " ONESHOT_ARGS
    ;;
esac

# yaml에 기록 (또는 example의 default 값을 sed로 치환)
```

매핑 정확도는 F4·F5에서 각 agent 실측 후 확정. v0.1.0은 **hermes default만 검증**됨. 다른 agent는 잠정 매핑.

### systemd unit 생성 (/wh:setup)

`/wh:setup`이 unit instance화 시 `ExecStart` 구성:

```
ExecStart={agent.binary} {agent.oneshot_args[*]} "<prompt>"
```

예 (Hermes):
```
ExecStart=/usr/local/bin/hermes -z "/wh:ingest --vault gdrive"
```

예 (codex 가설):
```
ExecStart=/usr/local/bin/codex exec "/wh:ingest --vault gdrive"
```

**이유**:
- **agent-agnostic 원칙 정합**: spec이 특정 agent 종속이 아님 (ADR-0011 연장)
- **wikihub.yaml = single source of truth**: agent 변경도 yaml 편집 + `/wh:setup`으로 처리 (다른 운영 변경과 동일 패턴)
- **install.sh의 dispatch helper**: 메인테이너는 agent type만 선택, syntax는 기본 매핑이 처리
- **추상 표기의 명료성**: `<agent_invocation>`은 명시적 placeholder — 산문보다 정확
- **(β) 기각**: wrapper script는 1단계 indirection 추가 + script 자체 유지보수 부담
- **(γ) 기각**: spec misleading. 새 agent 사용자가 spec 읽고 `agent -z` 그대로 시도하면 오류

## Consequences

- **긍정**:
  - spec이 진정한 agent-agnostic
  - agent 교체 시 yaml 편집 + `/wh:setup` 만으로 완료
  - install.sh의 default 매핑이 사용자 onboarding 부담 흡수
  - `<agent_invocation>` placeholder가 ADR·spec의 일관 어휘

- **부정/제약**:
  - **codex·gemini·copilot 매핑 미검증**: v0.1.0은 hermes default만 동작 보장. 다른 agent는 F4·F5 검증 시점에 확정 (custom type으로 우회 가능)
  - **추상 표기의 가독성**: 산문 "agent의 one-shot으로 ..."에 비해 `<agent_invocation>`은 약간 기계적. 그러나 정확성 우위
  - **systemd unit instance화 복잡도**: F4 unit template이 placeholder 처리 + /wh:setup이 적용 — 구현 분량 약간 증가

- **후속 영향**:
  - **F2 산출물 갱신** (본 ADR 즉시 적용):
    - `_system/wiki-schema.md`: `agent` 스키마 추가, 추상 표기 설명
    - `_system/commands/{ingest,lint,query,graphify,setup}.md`: `agent -z` → `<agent_invocation>` 일괄 치환
  - **F4 install.sh**: agent type prompt + default 매핑 함수
  - **F4 unit template**: `ExecStart` placeholder 처리
  - **F4·F5 검증**: codex·gemini·copilot의 실제 one-shot syntax 확인 → install.sh 매핑 보강
  - **재검토 트리거**: 어떤 agent가 one-shot syntax 자체를 갖지 않으면(예: 항상 interactive) wrapper script 도입(β 옵션) ADR 발의

### 미검증 agent의 user-facing 실패 모드 (O7)

`codex`·`gemini`·`copilot` 같은 미검증 agent type 사용 시 운영 시나리오:

1. 메인테이너가 install.sh에서 agent type = `codex` 선택
2. install.sh가 default mapping `oneshot_args=["exec"]` (잠정) 적용 → `wikihub.yaml`에 기록
3. `/wh:setup`이 systemd unit 생성: `ExecStart=/usr/local/bin/codex exec "/wh:ingest --vault X"`
4. **실제 codex가 `exec` 인자를 받지 않거나 prompt를 마지막 인자로 받지 않으면 → systemd timer 매번 실패**
5. 메인테이너가 `journalctl --user -u <vault>-ingest.service` 로 발견
6. **수기 조정**: `wikihub.yaml.agent.oneshot_args` 수정 (예: `["chat", "-q"]` 또는 `[]`) → `/wh:setup` 재호출 → 재검증

**install.sh 측 안내**:
- 미검증 agent type 선택 시 install.sh가 명시적 경고 출력: `"<type> mapping은 미검증 — 실패 시 wikihub.yaml.agent.oneshot_args 수기 조정 + /wh:setup 재호출 필요"`
- F4·F5가 매핑 검증 완료 시 install.sh의 경고 제거 + 본 ADR `Considered Options` 표 갱신
