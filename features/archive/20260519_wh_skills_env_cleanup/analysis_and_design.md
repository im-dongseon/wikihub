---
approved: 2026-05-19
---

# Analysis & Design — wh_skills_env_cleanup

## 1. 배경 및 목적

2026-05-19 메인테이너 세션 (macOS Claude Code) 에서 `🔑 Skill Setup Required — Enter value for WIKIHUB_HOME` secure prompt 가 매 세션 시작 시 surface. 추적 결과 `_system/skills/wh-*.frontmatter.yaml` 5개 파일의 `required_environment_variables: [WIKIHUB_HOME, WIKIHUB_INSTANCE_ROOT]` 선언이 원인.

본 cleanup 의 목적: 잘못된 layer 의 frontmatter 메타 제거 — false prompt 제거 + Hermes secret-store 의미적 정확성 회복.

## 2. 현행 진단

### 결함 1 — Hermes 디자인 의도와의 불일치

Hermes 의 `required_environment_variables` 디자인 의도 (`~/.hermes/hermes-agent/CONTRIBUTING.md:468-470`):
> "The skill uses an API key or token that should be collected securely at load time"

즉 **secret (API key/token)** 용. 예: `TENOR_API_KEY`, `NOTION_TOKEN`. Hermes 의 처리 흐름:
1. skill load 시 missing entries 발견.
2. secure prompt 띄움 (CLI-only — gateway 세션에선 `gateway_setup_hint` 만 노출).
3. callback 으로 값 수집 → secret-store 에 저장.
4. `register_env_passthrough()` 로 sandbox 통과 등록 (`~/.hermes/hermes-agent/tools/env_passthrough.py:70`).

### 결함 2 — WIKIHUB_HOME / WIKIHUB_INSTANCE_ROOT 의 실제 provisioning

이 두 변수는 **secret 이 아닌 path 상수**:
- `install.sh` 가 shell rc (`.bashrc`/`.zshrc`) 에 `export WIKIHUB_HOME=...` 작성 (ADR-0023).
- `_system/systemd/wikihub-vault@.service.template` 등이 `Environment=WIKIHUB_HOME=...` directive 보유.
- Hermes process 가 systemd user unit 으로 기동될 때 systemd Environment 으로 주입 → `os.environ` 에 무조건 존재.

따라서 secure prompt 가 트리거될 일이 없어야 정상. **그러나 frontmatter 가 unconditionally 선언하면 Hermes 가 env passthrough 등록 절차를 수행 — 이때 macOS Claude Code (개발 환경 — install.sh 미실행) 에서는 `os.environ` 에 부재하므로 prompt 트리거**.

### 결함 3 — 부작용 정리

| 부작용 | 영향 |
|---|---|
| macOS 메인테이너 세션에서 매번 prompt | 개발 UX 저하 (ESC 5번/세션) |
| Hermes secret-store 에 path 상수 등록 (운영 환경) | semantic noise — "skill 이 secret 요구" false signal |
| `register_env_passthrough` 의 sandbox 통과 허용 등록 | path 상수에 불필요한 surface — security model 약화는 아니지만 의미 부재 |

## 3. 개정 범위

| 파일 | 변경 | 라인 |
|---|---|---|
| `_system/skills/wh-setup.frontmatter.yaml` | `metadata.config` + `required_environment_variables` 블록 제거 | -5 |
| `_system/skills/wh-ingest.frontmatter.yaml` | 동일 | -5 |
| `_system/skills/wh-query.frontmatter.yaml` | 동일 | -5 |
| `_system/skills/wh-lint.frontmatter.yaml` | 동일 | -5 |
| `_system/skills/wh-graphify.frontmatter.yaml` | 동일 | -5 |

총: 5 파일, -25 라인. 신규 추가 0 라인.

코드/명령어 playbook 변경 없음. ADR 변경 없음.

## 4. 개정 전/후 비교

### Before (모든 wh-* frontmatter 동일 패턴)

```yaml
name: wh-setup
description: ...
version: 0.1.0
platforms: [linux]
metadata:
  tags: [wikihub, setup, bootstrap, materialization]
  category: knowledge-management
  config:
    wikihub_home_required: true
required_environment_variables:
  - WIKIHUB_HOME
  - WIKIHUB_INSTANCE_ROOT
```

### After

```yaml
name: wh-setup
description: ...
version: 0.1.0
platforms: [linux]
metadata:
  tags: [wikihub, setup, bootstrap, materialization]
  category: knowledge-management
```

## 5. 연계 룰/스킬 정합성 검토

- **ADR-0009 setup-responsibility**: frontmatter env 선언 관련 결정 부재 → 변경 영향 없음.
- **ADR-0023 install-script-distribution**: shell rc export 책임을 install.sh 에 부여 → 변경 후에도 env provisioning 보증 유지. 영향 없음.
- **ADR-0034 dir-layout-refactor**: `WIKIHUB_HOME` / `WIKIHUB_INSTANCE_ROOT` 정의를 systemd Environment + shell rc 로 명시 → frontmatter 와 무관. 영향 없음.
- **systemd unit templates** (`_system/systemd/wikihub-{vault,mount}@.service.template`): `Environment=WIKIHUB_HOME=...` 보유 → 변경 후에도 systemd-launched process 의 env 보증 유지.
- **playbook 코드** (`_system/commands/setup.md`, `ingest.md` 등): `$WIKIHUB_HOME` 참조 → env 존재 가정 그대로. 변경 영향 없음.

따라서 frontmatter 의 `required_environment_variables` 는 **다른 layer 가 이미 강제하는 보증의 중복 선언** → 제거해도 의미적 보증 유지.

## 6. 미결 사항

없음.

## 7. Definition of Done

- [ ] 5개 yaml 파일에서 `metadata.config` (line 8-9) + `required_environment_variables` (line 10-12) 블록 제거됨.
- [ ] 5개 파일 모두 yaml 파싱 가능 (round-trip 손상 없음).
- [ ] `_system/skills/` 의 기타 frontmatter 파일에 동일 패턴 잔존 없음 (grep 검증).
- [ ] `_system/commands/setup.md` 의 env 의존성 명시 부분 영향 없음 확인 (참조만, 변경 없음).
- [ ] `features/HISTORY.md` 항목 append (Step 5 수행 시).
- [ ] feature 디렉토리 archive 이동.
