# ADR-0006: ingest 오케스트레이션 모델 — agent가 orchestrator

- **Status**: Accepted
- **Date**: 2026-05-13
- **Feature**: features/20260513_wikihub_schema_v1
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

F1 (`20260513_v030_initial_architecture`)의 §4.6·§4.8 설계는 sync 스크립트(`gdrive-sync.py`)가 오케스트레이터 역할이라고 가정했다. systemd timer → sync.py → Drive API 다운로드·binary 추출 → `hermes -z "/ingest --vault X"`로 agent invoke → agent가 entities/concepts/analyses 갱신. 두 프로세스 + 두 systemd unit + 두 로그 도메인 + 두 retry 전략 + 두 부분실패 시나리오를 운영해야 한다.

F2 Step 2 설계 도중 다음 simplification이 surface됨:

- **단일 파일 모델** 채택: sync가 `wiki/sources/{vault}/path.md`를 직접 작성. agent /ingest의 mechanical 책임이 entities/concepts로 축소
- 이 시점에서 sync↔agent 분리의 근거 5가지(LLM 비용·실패 격리·lifecycle·권한·로그) 중 본질은 **#1 LLM 비용/신뢰성** 하나. 나머지 4가지는 #1의 자연스러운 귀결
- agent가 Python script를 **subprocess로 호출**하면 LLM은 결정론적 작업에 토큰을 안 쓰므로 #1이 보존됨 — 즉 분리 없이 #1을 만족 가능

오케스트레이터를 agent에 두면 sync.py가 별도 entry-point에서 agent의 **도구**로 강등되어 모델이 단순화된다.

## Considered Options

- **(α) Split orchestration (F1 기본 가정)**: systemd → sync.py → `hermes -z`. sync.py가 orchestrator, agent가 semantic worker
- **(β) Unified orchestration**: systemd → `hermes -z "/ingest"` → agent가 script subprocess + semantic 모두 수행. agent가 orchestrator, script가 도구
- **(γ) Agent daemon owns sync** (Hermes daemon이 Drive sync까지 내부 스케줄링): hermes.service만 존재. **ADR-0002와 충돌**(Hermes는 외부 고정 인터페이스 컴포넌트 — Drive sync 책임 부여 불가) → 기각

옵션 상세는 [features/20260513_wikihub_schema_v1/analysis_and_design.md](../../features/20260513_wikihub_schema_v1/analysis_and_design.md) 의 sync/ingest 분리 검토 절 참조.

## Decision

**채택**: (β) Unified orchestration

오케스트레이션 모델:
```
systemd timer (예: gdrive-ingest.timer, 10min)
    ↓
hermes -z "/ingest --vault gdrive"          ← 단일 trigger, 단일 명령
    ↓
agent가 _system/commands/ingest.md playbook 실행:
    Step 1: subprocess → python scripts/vault-fetch.py --vault gdrive
              (Drive API → /opt/vault-gdrive/ + wiki/sources/gdrive/*.md 작성)
              JSON으로 결과 반환: {has_changes, changed:[...], deleted:[...]}
    Step 2: has_changes=false → 조기 종료 (LLM 추론 최소화)
    Step 3: 변경된 source 페이지 read
    Step 4: entities/concepts/analyses 갱신
    Step 5: wiki/sources/{vault}/log.md append
    Step 6: 종료
```

**이유**:
- **단순화**: systemd unit 2개 → 1개, 명령 2개 → 1개, 로그 도메인 2개 → 1개, retry 전략 2개 → 1개
- **단일 진실의 원천**: `_system/commands/ingest.md` playbook이 전체 흐름의 정본
- **부분 실패 처리 단순화**: 단일 workflow → atomic 추적. F1의 `pending_ingest.json`은 agent 측에서만 영속화
- **LLM 비용 본질 유지**: mechanical work는 여전히 Python script (subprocess). agent는 변경 0건 시 조기 종료
- **ADR-0002 준수**: agent invocation은 여전히 CLI subprocess (`hermes -z`). 누가 호출하는지(sync.py vs systemd)는 ADR-0002 범위 밖
- **(γ) 기각 근거**: Hermes는 외부 고정 인터페이스이므로 Drive sync 책임 부여 불가. 또한 agent uptime에 sync가 종속되어 fragile

## Consequences

- **긍정**:
  - F4(systemd_orchestrator) 작업 분량 감소 — unit template 2종 → 1종
  - F5(hermes_adapter) 작업이 F3(vault_gdrive_api)와 자연 통합 — script는 agent playbook의 일부
  - 운영 진단 1개 로그·1개 systemd status로 충분
  - playbook이 spec과 구현 사이의 단일 다리

- **부정/제약**:
  - **agent CLI 시동 비용**: 변경 0건일 때도 매 사이클 `hermes -z` 1회 실행. script subprocess + JSON parse + 조기 종료로 LLM 토큰 거의 0이지만 프로세스 시동 비용은 발생
  - **playbook 책임 비대**: `_system/commands/ingest.md`가 mechanical + semantic 둘 다 명세. 분량 증가
  - **단일 오류 경로**: script 실패와 semantic 실패가 같은 retry 정책 — 세밀한 차별화 어려움(필요 시 F5에서 playbook 내 분기)

- **후속 영향**:
  - **F1 archive 문서 무영향(decision-level)**: ADR-0001~0004 모두 유효. F1의 archive `analysis_and_design.md` §4.6·§4.8·§4.9는 split 모델 가정으로 기술됐으나 archive는 영속 기록이므로 수정하지 않음. 본 ADR이 supersede한다는 사실로 충분
  - **F2(wikihub_schema_v1)**: `_system/commands/ingest.md`가 unified orchestration playbook으로 작성됨. wiki-schema.md의 "wiki/sources/{vault}/ 쓰기는 /ingest mechanical phase가 책임"으로 boundary 정의
  - **F3(vault_gdrive_api)**: 산출물 명칭·구조 단순화 — `scripts/gdrive-sync.py` + 진입 스크립트 분리 대신 `scripts/vault-fetch.py --vault gdrive` 단일 도구
  - **F4(systemd_orchestrator)**: `{vault}-sync.service` + `{vault}-sync.timer` 분리 폐기 → `{vault}-ingest.service` + `{vault}-ingest.timer` 단일화. `ExecStart=hermes -z "/ingest --vault {vault}"`
  - **F5(hermes_adapter)**: 책임 축소 — `/ingest` playbook은 F2가 정의하므로 F5는 Hermes skill 등록과 `/query`·`/lint`·`/graphify` 표준화에 집중
  - **재검토 트리거**: 운영 중 agent CLI 시동 비용이 의외로 크다고 측정되거나, mechanical/semantic 실패 분기가 빈번해 retry 정책 세분화 필요성이 발생하면 본 ADR을 superseded 처리하고 split 모델 신규 ADR로 대체
