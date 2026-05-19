# ADR-0014: Drive 접근 메커니즘 재검토 — `gws` CLI 채택

- **Status**: Superseded
- **Date**: 2026-05-13
- **Feature**: features/20260513_wikihub_schema_v1 (F2 종료 후 F3 시작 직전 reversal)
- **Supersedes**: ADR-0004
- **Superseded by**: ADR-0035 (2026-05-19 — gws CLI 폐기 + rclone 단독화)

## Note (2026-05-19, ADR-0035 supersede)

gws alpha 의존성·stderr 매핑 부담·인증 비대칭 위험이 v0.1.0 운영 진입 직전 누적 surface. ADR-0035 가 rclone `lsjson` (Drive API files.list backend 호출) 의 `ID`·`MimeType` 노출을 입증하여 gws `drive changes list` 정보를 등가 대체 — 본 ADR 의 §부정/제약 (alpha 의존성·stderr 매핑) 부담이 cascade 자체 해소로 의미 없어짐. 본문은 역사적 맥락 보존을 위해 유지.

## Context

ADR-0004는 v0.1.0 Drive 접근 메커니즘으로 **Direct Drive API (`google-api-python-client`)**를 채택하고 `googleworkspace/cli` (gws)를 5가지 사유로 기각:

1. 알파 (pre-v1.0), breaking changes 예고
2. Google 공식 지원 없음
3. `changes.list` 증분 sync 미검증 (Discovery 동적 노출이지만 pagination·error semantics 미검증)
4. 5-level exit code의 에러 세분도 부족 (Retryable/Fatal 분류용)
5. F2 ingest.md §Step 2 정본 JSON schema의 자료형 정확도 미보장

F2 종료 직후, F3 plan 발의 시점에 메인테이너가 reverse 결정. 메인테이너 사유 (원문):

> "gdrive 같은 파이썬 라이브러리를 사용할 수도 있는데 gws 사용하는것도 나쁘지 않을 것 같아서.
> 지금 빠르게 버전업이 되어가고 있기도하고, 에이전트가 사용하기에는 api 방식보다 더 편할 것 같다."

ADR-0004의 5개 사유 중:
- **#1 알파 우려 → 약화됨**: 빠른 versioning이 production 진입 가능성 신호. v0.1.0 운영 시작 시점에 v1.0 도달 가능
- **#2 비공식 → 부분 약화**: official 아니지만 Google Workspace 조직 산하 repo. 활발한 유지보수
- **#3 changes.list 미검증 → F3 검증 단계로 이관**: F3 구현 단계에서 실증
- **#4 에러 세분도 → 약화**: Python wrapper가 stderr·exit code 둘 다 파싱 가능
- **#5 자료형 정확도 → 약화**: gws JSON 출력이 well-formed면 Python wrapper가 schema 강제

추가 긍정 측면:
- **구현 분량 절감**: Drive API 클라이언트 boilerplate(~수백 줄) → gws subprocess 호출(~수십 줄)
- **ADR-0006 unified orchestration과 패턴 대칭**: agent도 subprocess, vault fetch도 subprocess
- **향후 Workspace 확장 (Sheets·Calendar·Chat 등) 시 단일 도구**

ADR-0010 install.sh가 venv에 gws를 pinned 버전으로 설치하면 alpha breaking change는 install.sh update 시점에만 노출 → 운영 중 sudden break 위험 차단.

## Considered Options

이번 reversal에서 추가로 surface된 architectural variant — F3 산출물(`vault-fetch.py`)의 책임 분할:

- **(A) Python wrapper around gws (권장)**: `vault-fetch.py`가 내부에서 `gws drive changes list ...` subprocess 호출. 외부 인터페이스(ingest.md §Step 2 JSON contract)는 그대로. state·error 분류는 Python 책임
- (B) Agent direct: agent playbook이 gws를 직접 호출, Python wrapper 제거. state는 agent가 관리. **ADR-0006 LLM 비용 정신 약화** + ingest.md spec 큰 변경
- (C) Hybrid: 책임 경계 흐려짐

## Decision

**채택**: gws CLI 사용 (Path A — Python wrapper around gws subprocess)

### F3 `vault-fetch.py`의 내부 구조 변화

```
# 이전 (ADR-0004): google-api-python-client SDK 직접
from googleapiclient.discovery import build
service = build('drive', 'v3', credentials=creds)
changes = service.changes().list(pageToken=cursor).execute()

# 새 (ADR-0014): gws CLI subprocess
import subprocess, json
result = subprocess.run(
    ['gws', 'drive', 'changes', 'list', '--params', json.dumps({'pageToken': cursor})],
    capture_output=True, text=True, check=False
)
if result.returncode != 0:
    classify_gws_error(result.returncode, result.stderr)  # F3 책임
changes = json.loads(result.stdout)
```

**유지되는 것**:
- `vault-fetch.py`의 외부 인터페이스 (ingest.md §Step 2 stdout JSON schema)
- exit code 0/75/2 semantics
- state file (cursor·file_map·last_sync·retry) atomic JSON write
- F1 §4.7.5 Drive 403 분기 (gws의 exit code + stderr 파싱으로 매핑)
- ADR-0006 unified orchestration
- ADR-0007 all JSON

**바뀌는 것**:
- Drive API 호출 메커니즘만 (SDK → subprocess)
- 의존성: `google-api-python-client` 제거, `gws` binary (install.sh가 venv 또는 system에 설치) 추가
- ADR-0003 OAuth pickle 처리: gws는 `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` 환경변수로 credentials 받음 → install.sh가 이 환경변수 또는 그 동등 표현을 systemd unit Environment로 주입 (F4 책임)

### error 분류 (F1 §4.7.5 lift, ingest.md §Step 2 표 정합)

gws exit code 매핑:

| gws exit | 의미 | F3 분류 |
|---|---|---|
| 0 | 성공 | 정상 |
| 1 | API 에러 (Drive HTTP 4xx·5xx) | stderr 파싱 → 403 quota/rate → 75 (Retryable), 403 scope/forbidden → 2 (Fatal), 401 → 2, 5xx → 75 |
| 2 | 인증 에러 | exit 2 (Fatal — token 무효/scope 회수) |
| 3 | 검증 에러 (인자 오류) | exit 2 (Fatal — F3 코드 버그) |
| 4 | Discovery 에러 (gws 내부) | exit 2 (Fatal — gws 자체 문제) |
| 5 | 내부 에러 | exit 2 (Fatal) |

stderr 패턴 매칭은 F3 구현 단계에서 실측 후 확정 (gws 버전별 변동 가능 — install.sh의 pinned version에 따라 표 갱신 책임).

### gws 버전 핸들링

- `wikihub.yaml.operations.gws_min_version` (또는 등가) — F4가 install.sh의 pinned 버전과 일치하도록 명시. `/wh:setup`이 시작 시점에 `gws --version` 확인
- gws breaking change 발생 시 install.sh update가 새 pinned 버전으로 deploy → `/wh:setup` 재호출 → systemd unit 재시작

**이유**:
- 사유 #1·#2·#4·#5는 ADR-0004 작성 시점 우려 → 본 ADR에서 재평가로 약화
- 구현 분량 절감 + 패턴 대칭 + 향후 확장의 trade-off가 alpha 리스크를 상회한다고 판단
- alpha 리스크는 install.sh의 pinned version + rollback 가능성으로 격리
- (B) 기각: LLM 토큰 비용 + ingest.md spec 대량 변경. (C) 기각: 책임 경계 흐려짐

## Consequences

- **긍정**:
  - F3 구현 단순화 (boilerplate 수백 줄 → 수십 줄)
  - ADR-0006 패턴 대칭 (agent·sync 모두 subprocess)
  - Workspace API 확장 시 동일 도구로 처리 가능
  - gws의 활발한 유지보수 활용

- **부정/제약**:
  - **alpha 의존성 부담**: gws v1.0 도달 전 breaking change 가능성. install.sh pinned version + rollback 필요
  - **공식 지원 부재 유지**: Google SLA 안에 있지 않음
  - **stderr 패턴 매칭의 깨지기 쉬움**: gws 버전 업그레이드 시 error 분류 매핑 표 갱신 필요 (F3 운영 부담)
  - **Direct API의 정밀 제어 손실**: 일부 Drive API 옵션 (예: 특정 pagination 파라미터)이 gws에서 노출 안 될 가능성 — F3 검증 단계에서 surface

- **후속 영향**:
  - **`_system/commands/ingest.md` §Step 2**: "Drive API changes.list" → "gws drive changes list (via vault-fetch.py)". 에러 분류 표를 gws exit code 기준으로 갱신
  - **`_system/wiki-schema.md` extraction tool 표**: Google native export 메커니즘을 "Drive API export"에서 "gws drive files export"로
  - **F3 (`vault_gdrive_api`)**: 구현 분량·구조 변경. Python SDK 대신 gws subprocess 패턴
  - **F4 install.sh**: gws binary 설치 + version pinning + 환경변수(`GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`) 주입 책임
  - **재검토 트리거**: 
    - gws의 changes API·export API에 critical bug 발견 시
    - gws v1.0 도달 전 breaking change가 빈발해 운영 부담 초과 시
    - 둘 중 하나면 ADR-0014 supersede + Direct API 회귀 또는 wrapper script 분리 ADR 발의

## Cross-references

- **Supersedes**: ADR-0004 (Direct Drive API). 본 ADR이 정본
- **F2 archive `analysis_and_design.md` §4.2.6**: ADR-0004 참조 — archive 영속 기록이라 수정 안 함. 본 ADR의 supersede 사실로 충분
- 운영 spec(`_system/*`)은 본 ADR에 맞춰 update (별도 작업)
