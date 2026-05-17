# ADR-0001: 소스 페이지 충돌 정책

- **Status**: Accepted
- **Date**: 2026-05-13
- **Feature**: features/20260513_v030_initial_architecture
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

WikiHub v0.1.0은 다중 외부 vault(Google Drive, NAS 등)를 단일 위키로 통합한다. 서로 다른 vault에 동명 파일이 존재할 경우(예: `vault-gdrive/report.md`와 `vault-nas/report.md`) `wiki/sources/` 하위에 어떻게 표현할지 결정이 필요하다. WikiCurate v0.2.6은 단일 vault 가정이었으므로 이 문제 자체가 없었다.

## Considered Options

- **(α) Vault namespace 분리**: `wiki/sources/{vault}/{path}` 구조. 같은 이름이라도 다른 파일로 취급
- **(β) Title 기반 merge**: 한 페이지에 `sources: [gdrive/report.md, nas/report.md]` 다중 vault 매핑. 사용자에게는 단일 페이지로 보임
- **(γ) Hash dedup**: 콘텐츠 해시 일치 시 자동 병합

> 옵션 상세 비교는 [features/20260513_v030_initial_architecture/analysis_and_design.md](../../features/20260513_v030_initial_architecture/analysis_and_design.md) §3.4 미결 1 참조.

## Decision

**채택**: (α) Vault namespace 분리

**이유**:
- **결정론**: 파일 경로가 vault를 직접 표현하므로 sync 결과가 예측 가능. β는 LLM 동일성 판단 필요(비결정적), γ는 편집 중 사본을 의도와 무관하게 병합할 위험
- **디버깅 용이**: 파일 시스템 경로만으로 어느 vault에서 온 페이지인지 확인 가능
- **단순한 sync 책임**: vault-X의 sync는 `wiki/sources/X/` 하위만 책임. 다른 vault sync와 격리
- **마이그레이션 비용**: α→β는 후환 적음(vault 단일이면 자연 merge), β/γ→α는 어려움(어떤 vault 소유인지 재구성 필요). 초기에 보수적 선택

**부수 결정**: `[[link]]` 규약을 vault-prefix로 확장하고 **단축형은 금지**한다.

- WikiCurate v0.2.6의 `[[link]] === title === filename` invariant는 α 채택으로 깨진다(동명 파일이 vault별로 존재 가능)
- 새 규약: `[[gdrive/report]]`, `[[nas/report]]` 형식의 path-prefix 링크만 표준으로 인정
- 단축형 `[[report]]` 금지(전체 위키에 단 1개일지라도). 근거:
  - α 채택 사유인 "결정론·예측 가능성"과 일관: 리졸버가 위키 전체를 스캔하지 않아도 링크 해석이 결정됨
  - 추후 동명 파일이 다른 vault에 추가될 경우 기존 단축 링크가 한꺼번에 모호해지는 운영 리스크 차단
  - 작성 편의 손실은 작성 시점 자동완성 도구(에디터 측 책임)로 보완 가능

## Consequences

- **긍정**:
  - sync 스크립트 책임 경계가 vault namespace로 명확
  - 다중 vault에 같은 파일명이 자연스럽게 공존
  - 후속 dedup 기능(필요 시) 도입은 별도 feature로 가능

- **부정/제약**:
  - 같은 문서가 두 vault에 존재할 때 위키에는 두 페이지로 보임(사용자 모델과 불일치 가능)
  - `[[link]]` 표기가 길어짐(vault prefix 필수)
  - vault 간 이주(예: gdrive→nas) 시 페이지 history 단절

- **후속 영향**:
  - F2(wikihub_schema_v1): `wiki-schema.md`에 vault namespace 디렉토리 구조와 `[[vault/page]]` 링크 문법 명시
  - F2: `sources:` frontmatter 포맷 정의(단일 vault 경로)
  - 향후: 동일 문서 인지 필요성이 운영에서 발생하면 별도 feature로 `aliases:` 프론트매터 또는 dedup 도입 검토
