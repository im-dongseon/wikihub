# ADR-0013: entity·concept 추출 정책 — semantic phase 정본

- **Status**: Accepted
- **Date**: 2026-05-13
- **Feature**: features/20260513_wikihub_schema_v1
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

`/wh:ingest`의 semantic phase(F2 ingest.md §Step 4)는 새 source 페이지에서 entity·concept를 추출해 `wiki/entities/`·`wiki/concepts/`에 stub을 만들거나 기존 페이지의 `referenced_by`를 갱신한다. `/wh:lint` §Step 3도 graph 기반 점검 시 동일 추출을 수행 (orphan 처리, 빠진 stub 자동 생성).

F2 Step 2 design review에서 다음 ambiguities surface:

- entity vs concept 분류 기준 모호 (예: OKR이 entity인가 concept인가?)
- 추출 임계 (1회 언급 OK인가? N회 이상?)
- 1줄 요약의 source (본문 발췌인가 LLM 외부 지식 generation인가?)
- 동의어 처리 (한국어·영어 동일 인물, 다른 표기)
- LLM prompt template 정본

이 모호가 해소되지 않으면 F5 implementer가 prompt를 짤 때 정본이 없어 구현마다 동작이 달라진다. 또한 외부 지식 generation은 F1 §4.5.5 신뢰 경계의 "agent의 출력에 외부 지식이 섞이면 출처 미상" 원칙을 위반할 수 있다.

## Considered Options

- **(α) 정책 미정 (현 F2 spec)**: 한 줄 카테고리 설명만, F5 implementer가 알아서 결정. 비결정적
- **(β) 본 ADR로 정책 명문화 + F5는 prompt 표현만 책임 (권장)**: 분류·임계·source 정책을 spec으로 고정. F5는 본 정책을 LLM이 따르도록 prompt 작성
- **(γ) LLM 자유 판단**: agent가 매번 분류·임계를 결정. 가장 유연하나 결과가 가장 비결정적

## Decision

**채택**: (β) 본 ADR로 정책 명문화

### 1. 분류 규칙

- **entity** = 고유명사 (Proper noun). 이름이 있는 개별 객체
  - 인물 (예: 홍길동, John Doe)
  - 조직 (예: 전략기획팀, Anthropic, 마케팅본부)
  - 제품 (예: Claude, iPhone, ChatGPT)
  - 프로젝트 (예: "Q1 OKR Initiative", "2026 신제품 출시")
- **concept** = 보통명사·추상 개념 (Common noun · abstract idea)
  - 방법론 (예: 애자일, OKR, Scrum)
  - 용어 (예: KPI, ARR, MRR, churn rate)
  - 프레임워크 (예: BPMN, ADR, AARRR)
- **둘 다 아닌 경우 추출 안 함** — false positive 누적이 stub noise를 만들어 self-maintaining 목표 훼손. **false positive < false negative** 우선

**경계 사례 정책**:
- 약어 (OKR, KPI 등)는 concept (방법론·용어 카테고리). 단 제품·조직 약어는 entity (예: AWS = entity)
- 모호한 경우 entity·concept 어느 쪽도 아니면 추출 보류

### 2. 추출 임계

- source 본문에서 **1회 이상 명시적 언급** (substring match)
- 제외:
  - `etc.`·`...`·범용 표현 안의 언급
  - 헤더 link만 있고 본문에 설명 없는 항목
  - frontmatter 안의 언급 (frontmatter는 메타데이터)
- 표기 정규화:
  - **한국어/영어 동의어는 가장 자주 쓰인 표기를 canonical**으로 사용
  - 다른 표기는 v0.1.0에서는 별개 entity·concept로 처리 (별도 ADR로 alias 도입 후보)

### 3. 1줄 요약 source 정책

- **source 본문에서 가장 인접한 정의·설명 문장 발췌**
- **외부 지식 generation 금지** — 신뢰 경계(F1 §4.5.5) 정책: agent의 출력에 외부 지식이 섞이면 출처 미상
- 본문에 적절한 정의가 없으면:
  - `"<entity·concept name> — (1 source 참조)"` 자리 표시
  - LLM이 외부 지식으로 채우려 시도하지 말 것

### 4. LLM prompt template

본 ADR은 **정책만 정의**, prompt 표현은 F5 책임. F5는 다음 invariant를 prompt에 명문화해야 함:

```
F5가 작성해야 할 prompt invariant:
1. 추출 대상은 entity (고유명사) + concept (보통명사·추상 개념)만
2. false positive < false negative — 모호하면 추출 안 함
3. 1줄 요약은 본문 발췌만, 외부 지식 generation 금지
4. 동의어는 가장 자주 쓰인 표기 1개만 추출 (alias는 future ADR)
5. 추출 임계: 본문 1회 이상 명시 언급
```

### 5. 새 source 추가 시 vs 기존 source 갱신 시

- **새 source (operation='created')**: 본문 전체 스캔 → 모든 entity·concept 추출 → 각각 stub 생성 또는 `referenced_by` 추가
- **기존 source 갱신 (operation='modified')**: 본문 전체 스캔 → set semantics로 `referenced_by` 갱신 (추가만, 제거 안 함). 새 본문에서 사라진 entity의 orphan ref는 `/wh:lint`가 정리 (v0.1.0은 `--apply` 필요한 archive 작업)

### 6. `/wh:lint`와의 분담

- `/wh:ingest`: 새/변경 source의 entity·concept를 자동 추출·갱신
- `/wh:lint`: graph 기반 orphan(인바운드 0건) 점검 + 본문 mention vs 페이지 부재 gap 검출 + (--apply) archive

본 정책은 둘 다 동일하게 적용.

**이유**:
- **결정론적 분류**: F5 구현자별 다른 분류 결과 방지
- **신뢰 경계 정합**: 외부 지식 generation 금지 → agent 출력의 출처 보장
- **운영 안전성**: false positive < false negative로 stub noise 누적 차단 → self-maintaining 목표 보호
- **F5의 자유도 보존**: prompt 표현은 F5 책임. agent (Hermes·codex·gemini)별 prompt engineering 차이 흡수

## Consequences

- **긍정**:
  - F5 implementer가 본 ADR을 prompt 구현 정본으로 사용 가능
  - entity/concept 분류 결과 일관성 보장
  - 신뢰 경계 보호 (외부 지식 generation 금지)
  - stub noise 누적 방지 → self-maintaining 목표 보호

- **부정/제약**:
  - **동의어 처리 미완**: 한국어·영어 같은 인물이 두 entity로 분리 가능. v0.1.0은 메인테이너 수동 통합 또는 후속 ADR
  - **약어 vs 정식 명칭**: 같은 개념의 약어와 풀네임이 두 entity로 분리될 가능성 (동의어 정책 후속 ADR로 해소 가능)
  - **prompt 표현은 F5 책임**: 본 ADR이 prompt 자체를 정의하지 않음 — F5가 LLM별 차이를 직접 다뤄야

- **후속 영향**:
  - **F2 ingest.md §Step 4**: 본 ADR 참조 + invariant 요약 추가
  - **F2 lint.md §Step 3**: 동일
  - **F2 wiki-schema.md**: entities/concepts 카테고리 설명에 본 ADR 참조 한 줄
  - **F5(hermes_adapter)**: LLM prompt template 작성 시 본 ADR §4 invariant 5건 enforce. agent별 prompt engineering은 F5 책임
  - **재검토 트리거**: 운영 중 (1) 동의어로 인한 entity·concept 분리 빈발, (2) 잘못 분류된 stub noise 누적, (3) LLM이 외부 지식 generation 시도하는 경우 발견 시 별도 ADR로 alias·classifier 보강
