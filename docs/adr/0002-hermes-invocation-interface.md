# ADR-0002: Hermes 호출 인터페이스

- **Status**: Accepted
- **Date**: 2026-05-13
- **Feature**: features/20260513_v030_initial_architecture
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

WikiHub의 sync 스크립트(예: `gdrive-sync.py`)가 외부 vault에서 변경 콘텐츠를 로컬에 떨어뜨린 후, 위키 갱신을 담당하는 Hermes daemon에 `/ingest` 등 명령을 트리거해야 한다. 호출 메커니즘을 결정해야 한다.

Hermes는 외부 컴포넌트로 이미 존재하며 인터페이스는 고정되어 있다(참조: <https://hermes-agent.nousresearch.com/docs>). sync ↔ Hermes 분리(sync 실패와 agent 실패의 격리)는 본 feature 분석 §3.1 항목 4 (에이전트 호출 모델)에서 합의된 원칙이다.

## Considered Options

- **(α) CLI subprocess**: sync가 `hermes -z "<prompt>"` 같은 CLI를 subprocess로 호출
- **(β) HTTP**: Hermes가 localhost 엔드포인트 노출, sync가 POST로 트리거
- **(γ) IPC**: Unix socket / file flag / signal 기반 OS 레벨 트리거

> 옵션 상세 비교는 [features/20260513_v030_initial_architecture/analysis_and_design.md](../../features/20260513_v030_initial_architecture/analysis_and_design.md) §3.4 미결 2 참조.

## Decision

**채택**: (α) CLI subprocess via `hermes -z` (또는 `hermes chat -q`)

**이유**:
- **Hermes 실제 인터페이스에 맞춤**: Hermes 공식 문서상 외부 스크립트 친화 진입점은 `hermes -z "<prompt>"`(one-shot, 동기)와 `hermes chat -q "<prompt>"`. HTTP 엔드포인트는 노출되지 않음
- **sync 측 복잡도 최저**: subprocess 호출 한 줄이면 충분. 별도 HTTP 클라이언트나 socket 코드 불필요
- **표준 디버깅 경로**: stdout/exit code로 결과 확인 가능
- **β/γ는 Hermes가 지원하지 않음**: HTTP 서버 노출 옵션이 문서상 없으므로 채택 불가. IPC도 마찬가지

## Consequences

- **긍정**:
  - sync 구현이 단순(`subprocess.run(["hermes", "-z", prompt])`)
  - Hermes 자체 변경 없이 통합 가능
  - 향후 Hermes의 `hermes cron`·`hermes webhook subscribe` 같은 내장 메커니즘으로 확장 여지 보존

- **부정/제약**:
  - **동시성 책임이 호출자(systemd) 측에 있다**: Hermes는 명시적 락 정책을 문서화하지 않음. systemd timer가 overlap 방지(`OnUnitInactiveSec`, 또는 timer + service `Type=oneshot`)로 동시 호출을 차단해야 함
  - **동기 호출**: `hermes -z`는 완료까지 block. sync 스크립트 실행 시간이 ingest 시간만큼 늘어남(타임아웃·실패 처리 필요)
  - **프롬프트 포맷이 인터페이스**: `/ingest --vault gdrive` 같은 slash-command 스타일 프롬프트의 정확한 형식은 Hermes skill 구성에 의존 → F5(hermes_adapter)에서 확정

- **후속 영향**:
  - F4(systemd_orchestrator): timer + service 구조로 overlap 방지. `Type=oneshot` + `RemainAfterExit=no` 권장. 타임아웃 정책 결정
  - F5(hermes_adapter): sync→Hermes 트리거 프롬프트 표준화. 실패 시 재시도 정책. Hermes skill 정의(`/ingest`, `/lint`, `/query`, `/graphify`)
  - 운영 중 동시성 충돌이 빈발하면 `hermes cron`/`hermes webhook` 기반 재설계 검토 가능(supersede 트리거)
