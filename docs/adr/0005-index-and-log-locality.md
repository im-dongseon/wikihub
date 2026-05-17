# ADR-0005: `wiki/index.md`·`log.md` 위치성 정책

- **Status**: Accepted
- **Date**: 2026-05-13
- **Feature**: features/20260513_wikihub_schema_v1
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

F1 (`20260513_v030_initial_architecture`)의 §4.5.1·§4.5.4는 두 항목을 F2 결정으로 이관했다.

- **`wiki/index.md`** 자동 생성·갱신 정책 (F1 §4.5.1: "선택, F2에서 결정")
- **`log.md` 위치성**: F1 §4.5.4는 vault별 `wiki/sources/{vault}/log.md`로 잠정 결정했으나 다중 vault 검색 use case가 surface되지 않은 상태

F2 Step 2에서 검색·운영 use case를 분석한 결과 두 항목은 **본질이 다른 파일**이라는 점이 드러났다.

- index = 검색·탐색의 진입점 → 통합이 자연
- log = 쓰기 책임자(vault sync)별 활동 이력 → 분리가 자연

## Considered Options

- **(α) 단일 `wiki/index.md` + vault별 `wiki/sources/{vault}/log.md`**: index는 통합, log는 격리
- **(β) 둘 다 vault별**: 모든 메타 파일을 vault별 분리. 검색 진입점이 N개로 단편화
- **(γ) 둘 다 단일**: 모든 메타 파일 통합. vault sync가 동일 log.md에 동시 append → race
- **(δ) `wiki/index.md` 폐기 + log vault별**: index는 graphify의 GRAPH_REPORT.md로 대체, 자동 갱신 책임 제거

옵션 상세는 [features/20260513_wikihub_schema_v1/analysis_and_design.md](../../features/20260513_wikihub_schema_v1/analysis_and_design.md) 의 검색·운영 use case 절 참조.

## Decision

**채택**: (α) 단일 `wiki/index.md` + vault별 `wiki/sources/{vault}/log.md`

**index.md 갱신 책임**: `/lint` 명령이 재구성. `/ingest`는 index 미수정.

**이유**:

- **본질의 일관성**: index는 진입점(통합 본질), log는 활동 이력(분리 본질). 본질에 맞게 위치성 부여
- **검색 use case**: agent가 graphify 폴백 시 `wiki/index.md` 1회 read로 카탈로그 확보. vault별이면 N회
- **사용자 수동 탐색**: 단일 카탈로그가 단편화된 N개보다 친숙
- **race condition 회피**: `/ingest`가 index 미수정 → 다중 vault 동시 ingest 시 lock 불필요. F1 §4.6.5 동시성 책임 단순화
- **/lint 권위**: wiki 일관성 책임이 이미 /lint에 있으므로 index 재구성 책임도 같은 사이클에 묶임
- **stale tolerable**: index가 다음 /lint 사이클까지 약간 stale해도 graphify(real-time-ish)가 검색의 1차 → 손실 작음
- **vault 격리**: log vault별 분리는 F1 §4.1.1 vault 간 격리 원칙과 정합. sync가 자기 vault log에만 append → 책임 명확

**(δ) 기각 근거**: graphify가 미설치/실패 시 fallback이 필요. 단일 index는 그 fallback 역할 + 사용자의 수동 진입점.

## Consequences

- **긍정**:
  - 검색 진입점 명확 (단일 wiki/index.md)
  - vault sync는 자기 log에만 책임 — concurrent multi-vault 안전
  - /ingest 사이클 가벼움 (index lock 없음)
  - /lint의 책임 통합(wiki 일관성 + index 재구성)

- **부정/제약**:
  - **index는 약간 stale 가능**: ingest와 다음 lint 사이의 시간차. 운영 중 lint 주기로 조정
  - **/lint 비용 증가**: 단순 결함 점검 외에 index 재구성 작업 추가
  - **vault별 log 수집 비용**: "전체 활동 시간순" 분석은 N개 파일 합쳐 정렬 필요(드문 use case)

- **후속 영향**:
  - F2 `_system/commands/lint.md`: 본 ADR 결정 반영 — index 재구성 단계 명시
  - F2 `_system/commands/ingest.md`: index 갱신 책임 명시적 제외
  - F2 `_system/wiki-schema.md`: wiki/index.md = "agent /lint가 재구성하는 카탈로그"로 정의
  - F4(systemd_orchestrator): /lint 주기를 별도 timer로 (예: 1시간 또는 매일). ingest timer와 분리
