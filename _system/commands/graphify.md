# /wh:graphify

`graphify` CLI로 wiki 지식 그래프를 빌드한다. `graphify-out/graph.json` + `GRAPH_REPORT.md` 생성. `/wh:query`·`/wh:lint`의 1차 검색·진단 자원.

## 호출

```
<agent_invocation> "/wh:graphify"          # 증분 빌드 (graph.json 있으면 update, 없으면 최초 빌드)
<agent_invocation> "/wh:graphify --rebuild" # 강제 전체 재빌드
```

- **트리거 (주, 자동)**: `/wh:lint` 종료 시 자동 호출 (lint playbook의 마지막 Step) — 하루 1회 자연 갱신
- **트리거 (보조, 수동)**: 메인테이너가 graph 즉시 갱신 필요 시 직접 호출
- **vault-agnostic**: wiki/ 전체를 입력으로 받음

## 사전 조건

- `graphify` CLI 실행 가능 (install.sh가 Python venv에 설치)
- `wiki/` 디렉토리 존재 (페이지 0개여도 OK — 빈 그래프 생성)
- `instance.root`/`graphify-out/` 쓰기 권한

## 절차

### Step 1. graphify CLI 사전 확인

```bash
command -v graphify >/dev/null
```

- 없음 → "graphify 미설치 — install.sh 재실행 안내" + exit 2 (Fatal, ops-alert)
  - 참고: graphify PyPI 패키지명 확정·release 상태는 F4 install.sh 구현 시점에 확인 (현재 잠정). install.sh가 venv에 pinned 버전 설치 가정
- 있음 → 버전 확인:
  ```bash
  graphify --version
  ```
  버전이 `MIN_GRAPHIFY_VERSION` 미만 (현 잠정 — F4가 install.sh의 pinned 버전과 일치하도록 본 값 확정): stderr 경고 + 진행. GRAPH_REPORT.md 없으면 wiki/index.md 폴백 (ADR-0005)

### Step 2. 빌드 모드 결정

- `--rebuild` 플래그 있음 → 전체 재빌드 (graph.json 기존 파일 무시)
- `--rebuild` 없음 + `graphify-out/graph.json` 존재 → **증분 빌드**:
  ```bash
  graphify update /opt/wikihub/wiki
  ```
- `--rebuild` 없음 + graph.json 부재 → **최초 빌드**:
  ```bash
  graphify /opt/wikihub/wiki
  ```

> wiki/ 경로는 `instance.root`/wiki 기준. 메타 디렉토리(`wiki/_lint/`)는 graphify가 underscore-prefix 디렉토리를 자동 제외한다는 가정. 미제외 시 noise 노드 발생 → F4에서 `.graphifyignore` 같은 제외 설정 검토

### Step 3. 결과 검증

- `graphify-out/graph.json` 존재 + 유효 JSON
- `graphify-out/GRAPH_REPORT.md` 존재 (없으면 graphify 버전 노후 경고)
- 노드 수·엣지 수 stdout 출력

### Step 4. (트리거가 /wh:lint인 경우) lint report에 통합

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

- 같은 wiki 상태에 대해 N회 빌드 → 동일 graph.json (graphify가 deterministic 가정)
- 증분 빌드는 stale graph.json도 안전히 갱신
- `--rebuild`는 항상 전체 재계산 = always 정합

## 자동 호출 흐름 (lint와 통합)

```
/wh:lint (timer, 하루 1회)
   ├─ Step 1~7: wiki 점검·정비
   ├─ Step 8: lint report 작성
   └─ Step 9 (추가): subprocess → /wh:graphify 자동 호출
            ├─ 성공 → lint report에 "graph rebuilt: N nodes, M edges" 추가
            └─ 실패 → lint report에 "graph rebuild failed" + ops-alert
```

본 통합은 lint.md Step 9에 명시 (lint playbook 갱신 필요 — F2 작성 중 reflection).

## 관련 ADR

- ADR-0005 wiki/index.md vs graphify 관계 (graphify는 1차, index는 폴백)
- ADR-0006 unified orchestration (본 명령도 lint 사이클의 일부로 자동 호출)
- ADR-0008 lint 권한 — graphify는 비파괴 (graphify-out만 만지므로 자동 OK)
