# ADR-0039: entity/concept alias frontmatter — duplicate detection 정합 + LLM 재생성 무한 loop 방지

- **Status**: Accepted
- **Date**: 2026-05-25
- **Feature**: features/20260525_lint_operations_improvements
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

`wh-lint` cycle 운영 중 case-variant duplicate (`Claude-Code` vs `claude-code`) 와 cross-category duplicate (entity `Docker` + concept `Docker`) 가 누적 surface. v0.1.8 lint_operations_improvements 의 D2 결정 = "auto-normalize 전체" — case lowercase + cross-category entity 우선 merge.

그러나 단순 lowercase 강제 시 두 결함:

1. **product noun case 손상** — `MiniMax`, `DeepSeek`, `GitHub` 같은 brand 의 의도된 대소문자 보존 깨짐.
2. **LLM 재생성 무한 loop** — ingest 스킬 (LLM) 이 sources 본문 보고 entity stub 생성 시 본문에 등장한 `MiniMax` 그대로 사용 → 다음 lint cycle 이 `MiniMax` + `minimax` 를 case-variant 로 인식 → 다시 lowercase normalize → 다음 ingest 가 또 `MiniMax` 생성. **사이클 무한 반복**.

본 ADR 은 위 두 결함 해소를 위한 데이터 모델 결정.

## Considered Options

- **(α) lowercase 강제 적용**: 모든 page 이름 lowercase. brand case 손상 + 무한 loop. 본 ADR 의 결함 surface 자체.
- **(β) lowercase 적용 대상 좁힘 (hyphen 만 다른 경우)**: `Claude-Code` + `claude-code` 처럼 제한적 정규화. `MiniMax` + `minimax` 는 보존. 결함 부분 해소하나 LLM 재생성 cycle 여전히 무한 loop 가능 (`Claude-Code` 가 lowercase 됐는데 다음 cycle ingest 가 또 `Claude-Code` 생성).
- **(γ) alias frontmatter 도입**: entity/concept page 의 frontmatter 에 `aliases: [<form1>, <form2>, ...]` 필드 추가. duplicate detection 이 alias 비교 — 같은 alias 셋이면 정합 (단일 page 가 모든 form 보유), 다른 alias 셋이면 duplicate. LLM 재생성 시 prompt 에 "기존 page 의 aliases 확인 후 같은 form 발견 시 stub 생성 skip + referenced_by 갱신" 명시.
- **(δ) wiki link resolver case-insensitive**: 데이터 모델 변경 없이 link resolver 가 대소문자 무관 매칭. wiki-schema 의 link 규약 + LLM prompt 모두 무영향. 단 page 파일명은 case-sensitive 라 `MiniMax.md` 와 `minimax.md` 가 filesystem 공존 가능 (Linux case-sensitive) → 데이터 정합 깨짐. 본 ADR 의 데이터 모델 결함 미해소.

## Decision

**채택**: (γ) alias frontmatter 도입

**이유**:
- (β) 의 부분 해소가 LLM 재생성 cycle 의 근본 원인 (다음 ingest 가 또 변형 form 생성) 을 해결 못 함. (γ) 가 LLM 의 동작 변경까지 포함해 완결.
- 데이터 모델 갱신 부담 있으나 wiki-schema 의 기존 `referenced_by` frontmatter 패턴과 정합 — frontmatter 1 필드 추가만.
- 운영자가 alias 명시 가능 — `aliases: [MiniMax, mini-max, minimax]` 같이 product brand 의 변형 명시. brand case 보존 + 변형 form 도 같은 entity 로 인식.
- (δ) 의 link resolver 변경은 wiki-schema 의 link 규약 (ADR-0001) 갱신 부담 + Linux filesystem case-sensitive 영향. 본 ADR 범위 외.

## Decision 세부

### 1. frontmatter spec (entity / concept page)

```markdown
---
aliases: [MiniMax, mini-max, minimax]   # 첫 alias = canonical (페이지 파일명 base)
referenced_by:
  - sources/gdrive/notes/idea.md
---

# MiniMax

(본문 — entity/concept 정의)
```

규칙:
- `aliases[0]` = canonical name = 페이지 파일명 base (예: `MiniMax.md` → `aliases[0] = "MiniMax"`)
- `aliases[1+]` = 같은 entity/concept 로 인식할 변형 (lowercase form, hyphen variant, abbreviation 등)
- `aliases` 빈 list 불가 — 최소 canonical 1개. 빈 경우 lint 가 자동 보강 (페이지 파일명 기반)
- alias 비교는 **lowercase 무시** (즉 `MiniMax` 와 `minimax` 의 alias 셋이 같은 lowercase form 1+ 공유하면 같은 entity)

### 2. alias 생성 책임

| 단계 | 책임 |
|---|---|
| ingest 스킬 (LLM) | sources 본문에서 entity/concept 새로 발견 시 stub 생성 + `aliases: [<본문에 등장한 form>]` 명시. 기존 page 의 aliases 가 본문 form 을 포함하면 stub 생성 skip + referenced_by 만 갱신 |
| lint Step 3 (자동 stub 생성) | 같은 alias 보유 page 확인 후 skip |
| lint Step 4.5 (duplicate detection) | wiki 전체 scan — 같은 lowercase form 의 2+ page 가 다른 alias 셋이면 duplicate 보고. 같은 alias 셋 1+ 공유면 정합 (보고 안 함). |
| lint Step 4.5 (alias migration) | 기존 wiki page 의 frontmatter `aliases` 부재 시 — `aliases: [<canonical>]` 자동 추가 (첫 cycle migration). idempotent. |
| lint Step 7 (매 cycle 자동 — v0.1.8 `--apply` flag 폐기) | case-variant duplicate → canonical 보존 (alias 셋의 첫 form 또는 운영자 명시 `canonical: <name>`) + 다른 form page archive + alias 셋 통합 + link reference 갱신 |

### 3. LLM 재생성 무한 loop 방지 (ingest / lint prompt 보강)

ingest.md / lint.md Step 3 의 LLM prompt 에 명시:

> entity / concept stub 생성 전 — 같은 lowercase form 의 alias 보유 page 확인. 발견 시 stub 생성 skip + 기존 page 의 `referenced_by` 만 갱신.

## Consequences

- **긍정**:
  - product noun case 보존 — `MiniMax` brand 형 그대로
  - LLM 재생성 cycle 무한 loop 차단 — 같은 alias 인식하면 stub 생성 skip
  - 운영자가 alias 명시로 의도된 변형 form 합치기 가능
  - duplicate detection 정확도 향상 — 단순 lowercase 비교가 아닌 alias 셋 비교

- **부정/제약**:
  - wiki-schema 데이터 모델 변경 (frontmatter 1 필드 추가) — 기존 wiki 의 migration (lint 첫 cycle 자동)
  - ingest / lint 의 LLM prompt 보강 — token 사용량 약간 증가 (alias 확인 단계)
  - 운영자 학습 곡선 — alias 명시 패턴 인지 필요

- **후속 영향**:
  - **wiki-schema.md** §"entity/concept 페이지 frontmatter" 절 신설 — aliases 필드 정의
  - **ingest.md** LLM prompt 보강 — alias 인식 후 stub 생성 skip 패턴
  - **lint.md Step 3 / Step 4.5 / Step 7** — alias 처리 흐름 명시
  - **wikihub.yaml.example** — 변경 없음 (alias 는 page-level frontmatter, yaml 무관)
  - **install.sh** — 변경 없음 (alias migration 책임이 lint Step 4.5 자체)
  - **ADR-0001 (link 규약)** — 변경 없음. link `[[<name>]]` 단축형 그대로. alias 는 frontmatter 만.

- **재검토 트리거**:
  - LLM 재생성 cycle 의 alias skip 정확도가 운영 데이터에서 부족 surface 시 — prompt 보강 또는 lint Step 4.5 의 알고리즘 정밀화
  - alias 가 운영자에게 부담 surface 시 — 자동 추론 default 강화 (예: sources 본문 등장 form 모두 자동 alias)
  - wiki-schema 의 link resolver 가 alias 인식 (`[[mini-max]]` 가 `MiniMax` page 로 자동 해석) 필요 시 — 별도 ADR

## Cross-references

- ADR-0001 (link 규약) — link 단축형 `[[<name>]]` 그대로 사용. alias 는 frontmatter 만.
- ADR-0036 (graphify CLI integration) — graphify_timeout_sec yaml expose 가 본 feature 의 다른 부분 (I1).
- features/20260525_lint_operations_improvements/analysis_and_design.md §2.9 — alias 도입 결정 흐름
