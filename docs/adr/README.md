# Architecture Decision Records (ADR)

WikiHub의 모든 아키텍처/설계 결정을 영구 기록합니다. 결정의 **정본(source of truth)** 은 이 디렉토리의 개별 ADR 파일이며, `features/` 산출물과 `features/HISTORY.md`는 ADR을 참조만 합니다.

## 작명 규칙

```
NNNN-{kebab-case-title}.md
```

- `NNNN`: 4자리 0-padded 시퀀스 (`0001`, `0002`, …). 1부터 시작.
- `kebab-case-title`: 소문자 + 하이픈. 결정 주제를 간결히 표현 (예: `source-collision-policy`).

## Status

| Status | 의미 |
|---|---|
| **Proposed** | 제안됨. 아직 미결정 (사용 빈도 낮음 — 보통 결정 후에 ADR 작성) |
| **Accepted** | 채택됨. 활성 결정 |
| **Deprecated** | 더 이상 권장되지 않음 (대안 ADR이 명시되지 않은 경우) |
| **Superseded** | 다른 ADR로 대체됨. `Superseded by: ADR-NNNN` 필드로 연결 |

## 결정 변경 정책

결정을 뒤집을 때:

1. 새 ADR 생성. `Status: Accepted`, `Supersedes: ADR-NNNN` 명시
2. 기존 ADR Status를 `Superseded`로 변경. `Superseded by: ADR-MMMM` 추가
3. 기존 ADR은 **삭제하지 않는다** — 과거 결정 맥락을 보존해야 supersede 이유가 추적됨

## 참조 형식

다른 문서에서 ADR을 참조할 때는 식별자만 사용:

```markdown
… ADR-0001 채택에 따라 …
```

링크가 필요하면:

```markdown
[ADR-0001](../../docs/adr/0001-source-collision-policy.md)
```

## 신규 ADR 작성

`template.md`를 복사해 다음 시퀀스 번호로 이름을 짓는다.

```bash
cp docs/adr/template.md docs/adr/NNNN-{slug}.md
```

작성 시점은 메소드론 Step 2(분석및설계) 중 미결 사항을 결정하는 시점.

## 인덱스

| ID | Title | Status | Date | Feature |
|---|---|---|---|---|
| _(없음 — 첫 ADR 생성 시 추가)_ | | | | |

> 신규 ADR을 추가할 때마다 이 표에 1행씩 append.
