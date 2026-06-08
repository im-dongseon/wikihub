# Review Context — install.sh `_migrate_agent_schema` prompt 처리

## 문제

v0.1.4 의 fix (line 751 `[[ -t 0 ]] && [[ -z "${WIKIHUB_NONINTERACTIVE:-}" ]]`) 가 Hermes OCI 환경에서 무력화. 원인 — Hermes 의 terminal tool 이 subprocess 에 PTY 할당 → stdin = pty slave = terminal-like → `[[ -t 0 ]]` 가 true 반환 → prompt fire → Hermes 가 응답 못 채워 (empty input) → default N → migration 거부 → yaml 의 `--yolo` 미반영 → systemd unit 의 `--yolo` 누락 → Hermes 매번 수동 patch.

`curl -fsSL .../install.sh | bash` (ADR-0023 default invocation) 만 가정한 fix 였음. Hermes 의 호출 경로 (PTY 할당) 미고려.

## 현재 코드 (install.sh:740-779)

```bash
_migrate_agent_schema() {
    local yaml="$WIKIHUB_HOME/wikihub.yaml"
    [[ -f "$yaml" ]] || return 0
    local needs_migrate=0
    local skill_prefix oneshot_args_str
    # ... yaml 파싱 (skill_prefix, oneshot_args_str)

    # drift detection (3 trigger 조건)
    if [[ "$skill_prefix" == "wh:" ]]; then
        needs_migrate=1
        info "operational yaml drift: agent.skill_prefix=\"wh:\" → \"wh-\" (ADR-0033)"
    fi
    if [[ ",$oneshot_args_str," != *"{skill}"* ]]; then
        needs_migrate=1
        info "operational yaml drift: agent.oneshot_args legacy form → F5 schema (ADR-0032)"
    elif [[ ",$oneshot_args_str," != *",--yolo,"* ]]; then
        needs_migrate=1
        info "operational yaml drift: agent.oneshot_args F5 form 인데 --yolo 누락 → in-place 삽입 (ADR-0032 §Note 2026-05-19)"
    fi

    [[ "$needs_migrate" == 0 ]] && return 0

    # prompt (v0.1.4 fix — Hermes PTY 로 인해 무력화 됨)
    if [[ -t 0 ]] && [[ -z "${WIKIHUB_NONINTERACTIVE:-}" ]]; then
        echo "F5 migration: wikihub.yaml 의 agent.skill_prefix·oneshot_args 갱신 필요. 진행? [y/N]"
        read -r reply
        [[ "${reply,,}" == "y" || "${reply,,}" == "yes" ]] \
            || { warn "schema migration 거부 — 운영자가 직접 갱신 후 install.sh 재호출 권장"; return 0; }
    else
        info "noninteractive (stdin 미-tty 또는 WIKIHUB_NONINTERACTIVE) → schema migration 자동 진행"
    fi

    # backup + transform
    local backup="$yaml.wikihub-bak.$(date -u +%Y%m%dT%H%M%SZ)"
    cp -p "$yaml" "$backup"

    "$VENV_PATH/bin/python3" - "$yaml" <<'PYEOF'
    # ruamel.yaml round-trip load + transform + atomic write
    # (skill_prefix wh: → wh-, oneshot_args F5 form + --yolo in-place insert)
PYEOF
}
```

## migration transformation 의 본질

3가지 정합화만 수행 (well-defined, scoped):
1. `skill_prefix: "wh:"` → `"wh-"` (ADR-0033 hyphen lock)
2. `oneshot_args` legacy form (no `{skill}` placeholder) → `["chat", "--skills", "{skill}", "--quiet", "--yolo", "--query"]` (F5 schema)
3. `oneshot_args` F5 form without `--yolo` → `--query` 앞에 `--yolo` insert (운영자 다른 인자 보존)

각 변환:
- **idempotent** — 이미 갱신된 yaml 에 재실행 no-op (drift 미detect → return 0)
- **부분 변경** — `agent` section 외 yaml 필드 미터치
- **운영자 다른 인자 보존** — `--yolo` insert 는 in-place

추가 safety:
- **Auto-backup**: `$yaml.wikihub-bak.<utc_iso>` 생성 매 migration 호출 전
- **macOS dev box 무영향**: yaml 부재 → 즉시 return 0
- **drift 미존재 시 no-op**

## 4가지 fix 옵션

### 옵션 (1) — prompt 완전 제거 + 항상 auto-proceed

```bash
[[ "$needs_migrate" == 0 ]] && return 0
info "schema drift detected — auto migration (backup: $backup)"
# (backup + transform 진행, prompt 분기 없음)
```

장점: 매우 단순. Hermes/CI/manual 모두 동일 동작. 코드 line 감소.
단점: 운영자가 의도적으로 `--yolo` 없는 yaml 운영하려 할 때 매 install.sh 가 덮어씌움. 운영자 의도 무력화.

### 옵션 (2) — prompt 제거 + `WIKIHUB_SKIP_MIGRATION=1` opt-out env

```bash
[[ "$needs_migrate" == 0 ]] && return 0
if [[ -n "${WIKIHUB_SKIP_MIGRATION:-}" ]]; then
    info "WIKIHUB_SKIP_MIGRATION=1 → schema migration skip (운영자 의도 우선)"
    return 0
fi
info "schema drift detected — auto migration (backup: $backup)"
# (backup + transform 진행)
```

장점: (1) 의 단순성 + 운영자 escape hatch. 의도 override 시나리오 친화.
단점: 운영자가 env 설정 잊으면 (1) 과 동일 결과.

### 옵션 (3) — prompt 유지 + default Y flip

```bash
if [[ -t 0 ]] && [[ -z "${WIKIHUB_NONINTERACTIVE:-}" ]]; then
    echo "F5 migration: ... 진행? [Y/n]"
    read -r reply
    [[ "${reply,,}" == "n" || "${reply,,}" == "no" ]] \
        && { warn "schema migration 거부"; return 0; }
fi
```

장점: Hermes/CI 의 empty input → default Y → 자동 진행. 운영자 명시 `n` 입력 시 거부. prompt 의 documentation 가치 유지 (운영자에게 visible).
단점: 운영자 typo 'n' (실수) 로 의도 외 거부 위험. `[[ -t 0 ]]` 미신뢰 — Hermes PTY 가 여전히 true 반환하나 default Y 라 자동 진행 → 실은 OK.

### 옵션 (4) — prompt 유지 + `read -t 5` timeout + default Y

```bash
if [[ -t 0 ]] && [[ -z "${WIKIHUB_NONINTERACTIVE:-}" ]]; then
    echo "F5 migration: ... 5초 안에 'n' 입력으로 거부, 미입력 시 진행"
    if read -t 5 -r reply; then
        [[ "${reply,,}" == "n" || "${reply,,}" == "no" ]] \
            && { warn "schema migration 거부"; return 0; }
    else
        info "5초 응답 없음 — auto-proceed"
    fi
fi
```

장점: 운영자 5초 내 reaction window 보존. Hermes/CI auto-proceed. 운영자 의도 가시화.
단점: 매 호출 최대 5초 delay (install.sh 가 빈번 호출되면 누적 부담). `read -t` 의 Bash 4+ 의존성. PTY/non-PTY 모두 5초 wait.

## 리뷰 요청

각 옵션 평가:
1. **운영적 적정성** — Hermes / CI / 운영자 manual 3 컨텍스트 모두 정합인가?
2. **운영자 의도 override risk** — `--yolo` 의도 제거 시나리오의 friction 정도?
3. **Karpathy §2 Simplicity First** — 어느 옵션이 가장 정합? 어느 게 over-engineering?
4. **CLAUDE.md §8 Atomic Change** — 본 fix 가 단일 목적 (migration prompt 동작 정합화) 외 다른 목적이 섞이는가?
5. **ADR-0023 (install.sh distribution) + ADR-0030 (update lifecycle)** 와의 정합성.

권장 옵션 + 사유 + 부수 고려사항 (escape hatch 변형, 향후 변경 예측 등).
