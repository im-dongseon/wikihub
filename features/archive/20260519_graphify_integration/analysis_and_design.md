---
approved: 2026-05-19
---

# Analysis & Design — graphify_integration

## 1. 배경 및 목적

2026-05-19 사용자 검토 (graphify.net 페이지 + WebSearch 결과):

- graphify.net 의 graphify CLI (PyPI `graphifyy`) 가 wikihub `_system/commands/graphify.md` 의 가정과 **정확 일치** — 출력 디렉토리 `graphify-out/`, 파일 `graph.json` + `GRAPH_REPORT.md` + `graph.html`, CLI `graphify <path>` (build) / `graphify <path> --update` (incremental).
- 3-pass 아키텍처: (1) Tree-sitter local code parse, (2) faster-whisper local audio/video, (3) Claude/OpenAI subagent semantic extraction on markdown/PDF/image.
- 라이선스: MIT (graphifyy 본체) + NetworkX BSD + Tree-sitter MIT.
- API key: `ANTHROPIC_API_KEY` (default) 또는 `OPENAI_API_KEY` — headless / CI 모드 (wikihub 의 hermes subprocess invocation 컨텍스트).
- `.graphifyignore`: gitignore 문법, repo root 1개로 subfolder 호출 시에도 정합.

본 통합의 목적:

1. install.sh 가 실제로 graphify CLI 를 설치하도록 plumbing 추가 — 현재 결함: wh-lint Step 9 의 `command -v graphify` false → 매 사이클 Fatal.
2. graphify Pass 3 의 LLM 호출 자료 (API key) 의 운영자 입력 경로 표준화.
3. 잠정으로 남아있던 `commands/graphify.md` 의 4항목 (패키지명·MIN 버전·CLI 시그니처·ignore 정책) 확정.
4. graphify 도입에 따른 결정 (PyPI 의존성·LLM 비용·non-deterministic 가정) 을 ADR-0036 으로 기록.

## 2. 현행 진단

### 결함 1 — install.sh 가 graphify CLI 설치 안 함

- `install.sh:660` `WIKIHUB_SKILLS=(wh-ingest wh-lint wh-query wh-graphify wh-setup)` — skill list 등록만.
- `_install_rclone` 와 같은 `_install_graphify` 함수 부재. `_write_installed_versions_sidecar` 의 INSTALLED_VERSIONS.json 도 graphify key 없음.
- wh-lint timer fire → lint playbook → Step 9 `<agent_invocation> "/wh-graphify"` chain → graphify playbook Step 1 `command -v graphify` → false → exit 2 Fatal → ops-alert 발화. 운영자 base 부재 (v0.1.0 미배포 시점) 라 surface 안 됐을 뿐.

### 결함 2 — `_system/commands/graphify.md` 의 4항목 잠정

| 위치 | 잠정 내용 | 확정 |
|---|---|---|
| L18 / L31 | "PyPI 패키지명 확정·release 상태 잠정" | `graphifyy` (2 y) |
| L36 | "MIN_GRAPHIFY_VERSION 잠정" | `>=0.8.0,<1.0.0` (v0.1.0 시작 — 검토 시점 0.8.x release) |
| L44 / L47 | `graphify update <path>` (잠정 cli) | `graphify <path> --update` (확정 시그니처) |
| L50 | "underscore-prefix 디렉토리 자동 제외 가정" | `.graphifyignore` (gitignore 문법) 명시 — wiki root 배치 |
| L83 | "graphify deterministic 가정" | Tree-sitter (Pass 1) deterministic, Pass 3 (LLM) non-deterministic — graphify 내부 cache + 증분으로 stability 책임 |

### 결함 3 — API key 운영자 입력 경로 부재

- graphify Pass 3 (Claude/OpenAI subagent) 가 호출되는 hermes subprocess (`hermes chat --skills wh-lint`) 의 systemd unit `wikihub-lint.service` 가 API key env 미주입.
- 운영자 수동 export 만으로는 systemd unit 환경에 inject 안 됨 (systemd --user 도 manager env 제한적).
- 표준 경로 필요: 운영자 1회 입력 + systemd unit 이 안정적으로 읽음.

### 결함 4 — graphify install (Claude Code hook) 의 wikihub 컨텍스트 부적합

graphify.net 의 `graphify install` = Claude Code 용 PreToolUse hook + `CLAUDE.md` directive 설치. wikihub agent 는 Hermes — 본 명령 호출 시 wikihub agent 와 충돌 없는 별도 hook 이라도 의미 부재.

→ install.sh 에서 `graphify install` 호출 안 함. (CLI 자체는 설치하되 hook 통합은 skip.)

## 3. 결정 (ADR-0036 §Decision 으로 기록)

### D1. PyPI 패키지 + 버전 pinning

- 패키지: `graphifyy` (PyPI), CLI 명령: `graphify`. install.sh 가 `$VENV_PATH/bin/pip install "graphifyy>=0.8.0,<1.0.0"` 로 설치.
- wikihub.yaml 의 `operations.graphify_min_version` / `graphify_max_version` 으로 range 표현. v0.1.0 에선 documentation only (rclone 와 동일 — 실제 enforce 는 v0.2.x).
- INSTALLED_VERSIONS.json 에 `graphify` 키 추가 — fact 기록.

### D2. API key 저장 경로 — `~/.config/wikihub/env` (EnvironmentFile)

- 새 파일: `~/.config/wikihub/env` — `KEY=VALUE\n` 형식 (systemd EnvironmentFile 호환).
- install.sh 가 `~/.config/wikihub/` 디렉토리 (chmod 700) + `env` 파일 (chmod 600) ensure. 운영자가 수동으로 `ANTHROPIC_API_KEY=sk-ant-...` 채움.
- systemd `lint.service.template` 에 `EnvironmentFile=-%h/.config/wikihub/env` (lenient prefix `-` — 부재 시 unit start fail 안 함). hermes 가 호출하는 graphify subprocess 가 PassEnvironment 으로 자연 상속.
- default env var name: `ANTHROPIC_API_KEY` (wikihub agent = Hermes/Claude 정합). yaml 의 `operations.graphify_api_key_env_name` 으로 override (e.g. `OPENAI_API_KEY`).
- ADR-0035 가 폐기한 `~/.credentials/wikihub/` (SA JSON) 와는 별도 경로 — secret material 의 새 layer.

### D3. .graphifyignore 정책 — wiki root 배치

- `wiki/.graphifyignore` template 을 install.sh 또는 wh-setup playbook 의 wiki/ ensure 단계가 배치.
- default 제외:
  ```
  # wikihub 메타 디렉토리 — graphify 분석 대상 아님
  _lint/
  _state/
  ```
- sources/ 는 vault mirror — graphify 가 source 콘텐츠를 wiki page 와 함께 분석하는 것은 정합이라 제외 안 함. (사용자 후속 결정 시 별도 ADR.)

### D4. non-deterministic 가정의 멱등성 영향

- Pass 1 (Tree-sitter) deterministic — 같은 입력 → 같은 syntax tree.
- Pass 3 (LLM) non-deterministic — temperature / sampling. graphify 내부 cache (graph.json) 가 증분 단계에서 변경되지 않은 노드는 보존 → cycle 간 churn 부분 완화.
- wikihub `graphify.md` L83 "deterministic 가정" 은 false. §Note 추가 — Pass 1 만 deterministic, Pass 3 churn 가능성 인지. wh-lint Step 9 의 `graph rebuilt: N nodes, M edges` 보고가 cycle 간 N/M drift 시 정상 (panic 아님).

### D5. graphify install (Claude Code hook) skip

- install.sh `_install_graphify` 는 PyPI 설치 + version check 만. `graphify install` (Claude Code hook + CLAUDE.md) 호출 안 함.
- wikihub agent (Hermes) 가 graphify 를 subprocess 로 호출 — hook 의존 없음.

### D6. 운영 비용 모델 — Pass 3 LLM 호출 cost

- wiki page N → Pass 3 subagent N 호출 (대략). graphify 의 token-budget 옵션 (`--token-budget`) + backend 선택 (`--backend ollama` 등 local LLM 옵션) 으로 cost 통제 가능.
- v0.1.0 default: graphify CLI default (Anthropic + 기본 token-budget). 운영자가 wh-lint timer 주기 (`operations.lint_interval_hours`) 로 호출 빈도 통제.
- setup.md / install.sh `_step8_guide` 에 cost 환기 메시지 추가.

## 4. 개정 범위

| 파일 | 변경 |
|---|---|
| `install.sh` | `_install_graphify` 함수 + `_step5_instance_dirs` 의 `~/.config/wikihub/env` ensure + sidecar JSON 의 graphify key + `_step8_guide` 의 API key 안내 + cost 환기 |
| `wikihub.yaml.example` | `operations.graphify_min_version` / `graphify_max_version` / `graphify_api_key_env_name` 추가 |
| `_system/systemd/lint.service.template` | `EnvironmentFile=-%h/.config/wikihub/env` 추가 + 주석 ADR-0036 인용 |
| `_system/commands/graphify.md` | 4항목 확정 + L83 §Note + 운영 비용 환기 1줄 |
| `_system/commands/setup.md` | Step 0 entry condition (env file 존재 + API key 채워짐) + maintainer catalog 갱신 |
| `scripts/_helpers/render_systemd_units.py` | `_write_installed_versions_sidecar` 호환 — render 가 graphify 버전 검증 (rclone pattern) |
| `wiki/.graphifyignore` (template) | install.sh 또는 wh-setup playbook 가 배치 (template 자체는 repo 의 어딘가, 예: `_system/templates/graphifyignore`) |
| `docs/adr/0036-graphify-cli-integration.md` | 신규 (위 6 결정 기록) |
| `docs/adr/0005-...md` | §Note 추가 (graphify 도구 정해짐) |
| `docs/adr/0023-...md` | §Note 추가 (graphify install.sh 책임) |
| `docs/adr/README.md` | index 갱신 (ADR-0036 추가) |
| `_system/VERSION` | 0.1.3 → 0.1.4 |
| `features/HISTORY.md` | 항목 append |

## 5. 연계 룰/스킬 정합성 검토

- **ADR-0005 (wiki/index.md fallback)**: 본 ADR §Decision 본문 (graphify primary, index fallback) 그대로. graphify 도구가 정해진 시점만 §Note 추가.
- **ADR-0023 (install.sh distribution)**: install.sh 가 외부 binary (rclone) 설치 책임 + supply chain verify (SHA256). graphify 는 PyPI 패키지라 pip 의 signature/hash 의존 — install.sh 의 supply chain verify 격리. §Note.
- **ADR-0024 (fatal alert)**: graphify 실패 → exit 2 → OnFailure ops-alert. 변경 없음.
- **ADR-0026 (vfs refresh)**: 무관.
- **ADR-0032 (agent invocation)**: hermes 가 graphify 호출 — agent invocation cmdline 영향 없음 (graphify 가 hermes 가 띄운 subprocess). `--yolo` 가 hermes-level, graphify 는 별도.
- **ADR-0033 (skill prefix)**: 본 변경은 skill 정의 미변경.
- **ADR-0035 (rclone OAuth)**: rclone 의 인증과 graphify 의 API key 는 다른 layer. ADR-0035 의 `~/.config/rclone/rclone.conf` vs 본 ADR 의 `~/.config/wikihub/env` — 경로/책임 모두 별개. 충돌 없음.

## 6. 미결 사항

없음. 모든 결정 D1~D6 명시.

## 7. Definition of Done

- [ ] `install.sh:_install_graphify` 신설 — `pip install graphifyy>=0.8.0,<1.0.0` + `command -v graphify` 사후 검증 + `_write_installed_versions_sidecar` 의 graphify version 기록
- [ ] `install.sh:_step5_instance_dirs` 에 `~/.config/wikihub/` (chmod 700) + `env` 파일 (chmod 600, 미존재 시 빈 template) ensure
- [ ] `install.sh:_step8_guide` 에 API key 안내 + cost 환기 추가
- [ ] `wikihub.yaml.example` 의 `operations.*` 에 `graphify_min_version` / `graphify_max_version` / `graphify_api_key_env_name` 추가
- [ ] `_system/systemd/lint.service.template` 에 `EnvironmentFile=-%h/.config/wikihub/env` 추가
- [ ] `_system/commands/graphify.md` 의 4항목 잠정 → 확정 + L83 §Note
- [ ] `_system/commands/setup.md` Step 0 entry condition + maintainer catalog 갱신
- [ ] `wiki/.graphifyignore` template 정의 (repo 위치: `_system/templates/wiki/.graphifyignore` 또는 inline in install.sh)
- [ ] `docs/adr/0036-graphify-cli-integration.md` 신규 + Status: Accepted + 본 AD 와의 cross-reference
- [ ] `docs/adr/{0005,0023}-*.md` 에 §Note 추가
- [ ] `docs/adr/README.md` 의 index 갱신
- [ ] `_system/VERSION` 0.1.4 + `features/HISTORY.md` 항목
- [ ] systemd render dry-run — `wikihub-lint.service` 의 `EnvironmentFile=-` 직선 확인
- [ ] pytest regression — 57 pass 유지
- [ ] feature dir archive 이동
