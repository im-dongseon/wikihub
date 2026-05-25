# ADR-0008: `/lint` 권한 분류 — 비파괴 자동 / 파괴 수동

- **Status**: Accepted
- **Date**: 2026-05-13
- **Feature**: features/20260513_wikihub_schema_v1
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

`/lint`는 wiki 일관성·구조 점검 명령. v0.2.6은 자동 수정(자동 stub 생성·dangling link 제거·orphan 페이지 archive·모순 클레임 갱신)을 모두 자동으로 수행했다. 단 v0.2.6은 **사용자 명시 호출** 모델이라 의도된 변경이 보장됐다.

wikihub v0.1.0은 다음 두 가지 변화로 권한 재검토 필요:

- **systemd timer 주기 자동 실행** (사용자 trigger 없이 변경 발생)
- ADR-0005에 따라 `/lint`가 `wiki/index.md` 재구성 책임도 보유 → 자동 실행 필수

이 환경에서 v0.2.6의 "모든 자동 수정" 정책을 그대로 lift하면 의도치 않은 변경(잘못 추출된 entity stub 양산, 의도한 dangling link 자동 제거 등)의 blast radius가 증폭된다.

본 시스템의 명시적 목표는 **self-maintaining wiki — 사용자 의사결정 최소화**. 따라서 자동화는 강하게 추구하되, **정보 손실 가능한 작업은 명시 의도에서만** 수행해야 한다.

## Considered Options

- **(A) report-only**: 아무 자동 수정 안 함. `/lint`는 진단 보고서만 생성. 사용자가 수동 조치
- **(B) 위험도별 계층화**: 안전 작업만 자동, 위험 작업은 `--apply`. 위험도 기준 분류
- **(B') 가역성별 계층화**: **비파괴 작업만 자동**, **파괴 가능 작업은 `--apply`**. 가역성 기준 분류
- **(C) v0.2.6 lift (모두 자동)**: 위험 여부 무관 모두 자동

옵션 상세는 [features/20260513_wikihub_schema_v1/analysis_and_design.md](../../features/20260513_wikihub_schema_v1/analysis_and_design.md) `/lint` 권한 use case 절 참조.

## Decision

**채택**: (B') 가역성별 계층화

자동/수동 분류 매트릭스 (정본):

| 작업 | 기본 모드 (자동) | `--apply` 필요 |
|---|---|---|
| `wiki/index.md` 재구성 | ✓ | |
| 카테고리 디렉토리 생성 (없으면) | ✓ | |
| ADR-0001 위반 link 보고 (`[[X]]` 단축형, vault-prefix 누락 등) | ✓ (보고만 — `wiki/_lint/report.md`) | |
| 언급된 개념의 stub 자동 생성 (`wiki/entities/`, `wiki/concepts/`) | ✓ (추가만) | |
| orphan 페이지에 cross-ref 추가 (`referenced_by`) | ✓ (추가만) | |
| log.md append (lint 사이클 결과) | ✓ | |
| dangling link 제거 (`[[gdrive/old/file]]` 대상 부재) | | ✓ (정보 손실) |
| `referenced_by` 0건 entity·concept archive 이동 | | ✓ (정보 손실) |
| 모순 클레임 자동 본문 갱신 | | ✓ (정보 손실) |
| 폴더 구조 위반 페이지 자동 이동 (`wiki/` 루트 → 적절 카테고리) | | ✓ (위치 변경 = 링크 깨짐 위험) |

**원칙**: "추가·생성·append만 자동. 제거·archive·덮어쓰기는 명시 의도(`--apply`)에서만"

**이유**:
- **self-maintaining 목표 정합**: 비파괴 작업은 자동화 → 사용자 개입 0건. 파괴 작업만 의도 확인 → 데이터 손실 차단
- **가역성 = 자동화 결정 기준**: 잘못 만든 stub은 다음 lint 사이클이나 사용자가 정리 가능. 잘못 archive된 entity는 (`.archived/`에서 복구 가능하지만) 검색 결과에서 사라져 발견 늦음
- **systemd timer 안전 보장**: 자동 실행이 정보 손실을 일으키지 않음
- **(A) 기각**: report-only는 self-maintaining 목표와 충돌. 매번 메인테이너 수동 개입 부담
- **(C) 기각**: 자동 archive·자동 본문 수정은 blast radius 너무 큼. v0.2.6의 단일 사용자 모델과 다른 운영 환경

**운영 권장값** (F4가 `wikihub.yaml`/timer에 반영):
- `/lint` 자동 실행 주기: **하루 1회** (예: `OnCalendar=*-*-* 03:00:00 KST`). 초기 데이터 sparse 환경 가정
- 데이터 증가 시 12시간 → 6시간 주기로 단축 가능 (`wikihub.yaml.operations.lint_interval_hours`)
- `--apply` 실행은 메인테이너가 `wiki/_lint/report.md` read 후 의도적으로 수동 호출

## Consequences

- **긍정**:
  - 자동 운영 보장 (사용자 개입 0건 가능)
  - 정보 손실 위험 차단 (파괴 작업은 명시 의도에서만)
  - index 재구성·stub 자동 생성으로 검색·탐색 UX 자동 개선
  - `wiki/_lint/report.md`가 메인테이너의 단일 점검 진입점

- **부정/제약**:
  - **stub noise 가능**: 자동 stub 생성이 잘못된 추출을 양산할 수 있음. 메인테이너가 가끔 정리 필요
  - **dangling link 누적**: `--apply` 미실행 시 dangling이 영구 잔존. report만 봤지만 조치 안 한 경우 운영 부담
  - **report 누적 + push 알림 부재 (O4 명시)**: 매일 report 생성 → 메인테이너가 안 보면 의미 없음. **v0.1.0은 push 알림 없음 — 메인테이너 자발적 확인 가정 (Telegram·email·webhook 푸시는 v0.2.x 후속 ADR 후보)**

- **후속 영향**:
  - F2 `_system/commands/lint.md`: 본 분류 매트릭스 그대로 명세
  - F2 wikihub.yaml schema: `operations.lint_interval_hours`(기본 24) 키 추가 가정 명시 (정본은 F4 yaml.example)
  - F4(systemd_orchestrator): `lint.timer`(단일, vault-agnostic) + `lint.service` unit. `ExecStart=hermes -z "/lint"`. `--apply`는 timer 호출 안 함
  - **재검토 트리거**: 운영 중 (1) stub noise가 심하면 자동 stub을 `--apply` 영역으로 격상, (2) report 미점검이 빈번하면 push 알림 정책 추가, (3) 데이터 증가로 lint 시간이 timer 주기 초과 시 주기 조정
  - 2026-05-25 (v0.1.8 `lint_operations_improvements`): **`--apply` flag 폐기 결정** — wikihub 데이터 모델 (sources = immutable, wiki/ = LLM derivative) 정합 정리로 "파괴 가능" 가정 자체가 약해짐 (LLM 본문 reword 도 원본 변경 0). lint = 매 cycle 진단 + 적용 default. 본 ADR 의 분류 매트릭스 (자동 vs `--apply`) 폐기. lint.md Step 7 표현 갱신 + `ADR-0039` (entity/concept alias frontmatter) 가 LLM 재생성 무한 loop 차단 추가. 본 ADR Status 는 보존 (historical record).
