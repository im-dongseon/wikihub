# /wh-graphify

`graphify` CLI로 wiki 지식 그래프를 빌드한다. `graphify-out/graph.json` + `GRAPH_REPORT.md` 생성. `/wh-query`·`/wh-lint`의 1차 검색·진단 자원.

## 호출

```
<agent_invocation> "/wh-graphify"          # 증분 빌드 (graph.json 있으면 update, 없으면 최초 빌드)
<agent_invocation> "/wh-graphify --rebuild" # 강제 전체 재빌드
```

- **트리거 (주, 자동)**: `/wh-lint` 종료 시 자동 호출 (lint playbook의 마지막 Step) — 하루 1회 자연 갱신
- **트리거 (보조, 수동)**: 메인테이너가 graph 즉시 갱신 필요 시 직접 호출
- **vault-agnostic**: wiki/ 전체를 입력으로 받음

## 사전 조건

- `graphify` CLI 실행 가능 — install.sh `_install_graphify` 가 `$VENV_PATH/bin/pip install "graphifyy>=0.8.0,<1.0.0"` 으로 venv 에 설치 (PyPI 패키지 `graphifyy`, 2 y; ADR-0036)
- `wiki/` 디렉토리 존재 (페이지 0개여도 OK — 빈 그래프 생성)
- `instance.root`/`graphify-out/` 쓰기 권한
- `~/.config/wikihub/env` 의 LLM API key 채워짐 — Pass 3 (Claude/OpenAI subagent semantic extraction) 가 호출 (ADR-0036). default env var: `ANTHROPIC_API_KEY` (yaml `operations.graphify_api_key_env_name` 으로 override)

## 절차

### Step 1. graphify CLI 사전 확인

```bash
command -v graphify >/dev/null
```

- 없음 → "graphify 미설치 — install.sh 재실행 안내" + exit 2 (Fatal, ops-alert)
  - PyPI 패키지: `graphifyy` (2 y; ADR-0036). CLI 명령: `graphify`. install.sh `_install_graphify` 가 venv 에 설치.
- 있음 → 버전 확인:
  ```bash
  graphify --version
  ```
  버전이 `operations.graphify_min_version` (default `0.8.0`, ADR-0036; v0.1.0 documentation only — 실 enforce 는 v0.2.x) 미만: stderr 경고 + 진행. GRAPH_REPORT.md 없으면 wiki/index.md 폴백 (ADR-0005)

### Step 2. 빌드 모드 결정

- `--rebuild` 플래그 있음 → 전체 재빌드 (graph.json 기존 파일 무시):
  ```bash
  graphify "$WIKIHUB_HOME/wiki"
  ```
- `--rebuild` 없음 + `graphify-out/graph.json` 존재 → **증분 빌드** (`--update` 플래그):
  ```bash
  graphify "$WIKIHUB_HOME/wiki" --update
  ```
- `--rebuild` 없음 + graph.json 부재 → **최초 빌드**:
  ```bash
  graphify "$WIKIHUB_HOME/wiki"
  ```

> wiki/ 경로는 `instance.root`/wiki 기준 (`$WIKIHUB_HOME/wiki`, ADR-0034). 메타 디렉토리 제외는 `wiki/.graphifyignore` 파일이 책임 (gitignore 문법; ADR-0036 §D3) — install.sh 또는 wh-setup 가 default template 배치 (`_lint/`, `_state/` 제외). 운영자가 vault 별 추가 패턴 직접 편집 가능.

### Step 3. 결과 검증

- `graphify-out/graph.json` 존재 + 유효 JSON
- `graphify-out/GRAPH_REPORT.md` 존재 (없으면 graphify 버전 노후 경고)
- 노드 수·엣지 수 stdout 출력

### Step 4. (트리거가 /wh-lint인 경우) lint report에 통합

- lint playbook이 본 명령을 호출한 경우, graphify 결과를 lint report에 추가 — lint.md Step 8 참조
- 수동 호출 시 lint report 만지지 않음

## 출력 산출물

| 대상 | 조건 |
|---|---|
| `graphify-out/graph.json` | 매 호출 (증분 또는 재빌드) |
| `graphify-out/GRAPH_REPORT.md` | graphify 최신 버전 사용 시 |
| `wiki/` | 본 명령은 wiki 자체 만지지 않음 (read-only) |
| systemd journal | 빌드 사이클 (agent runtime) |

## 실패 처리

| 실패 시점 | 동작 |
|---|---|
| graphify 미설치 | exit 2 (Fatal) + ops-alert |
| graphify 빌드 자체 실패 (wiki/ 권한 등) | exit 1 + stderr 상세 |
| graphify-out/ 쓰기 실패 (disk full) | exit 1 + ops-alert |
| 증분 빌드 실패 → fallback | stderr 경고 + `--rebuild` 전체 재시도 1회 (이것도 실패 시 exit 1) |

## 멱등성

- 같은 wiki 상태에 대해 N회 빌드 → graph.json **structural** 동등.
  - Pass 1 (Tree-sitter code analysis) deterministic — 같은 입력 → 같은 syntax tree.
  - Pass 3 (LLM semantic extraction) **non-deterministic** (temperature / sampling, ADR-0036 §D4). graphify 내부 cache (graph.json 보존) 가 증분 단계에서 unchanged 노드는 보존 → cycle 간 churn 부분 완화. 노드 메타데이터의 minor drift 는 operational normal (panic 아님).
- 증분 빌드는 stale graph.json도 안전히 갱신.
- `--rebuild`는 항상 전체 재계산 = always 정합 (Pass 3 churn 포함).

## 자동 호출 흐름 (lint와 통합)

```
/wh-lint (timer, 하루 1회)
   ├─ Step 1~7: wiki 점검·정비
   ├─ Step 8: lint report 작성
   └─ Step 9 (추가): subprocess → /wh-graphify 자동 호출
            ├─ 성공 → lint report에 "graph rebuilt: N nodes, M edges" 추가
            └─ 실패 → lint report에 "graph rebuild failed" + ops-alert
```

본 통합은 lint.md Step 9에 명시 (lint playbook 갱신 필요 — F2 작성 중 reflection).

## 관련 ADR

- ADR-0005 wiki/index.md vs graphify 관계 (graphify는 1차, index는 폴백)
- ADR-0006 unified orchestration (본 명령도 lint 사이클의 일부로 자동 호출)
- ADR-0008 lint 권한 — graphify는 비파괴 (graphify-out만 만지므로 자동 OK)
- ADR-0036 graphify CLI 통합 — PyPI 패키지 `graphifyy` + `~/.config/wikihub/env` API key + Pass 3 non-deterministic 가정 + `.graphifyignore` 정책 + 운영 비용 모델
