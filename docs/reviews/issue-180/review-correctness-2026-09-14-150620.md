# Review — issue #180 (correctness)

- **일시**: 2026-09-14 (KST)
- **대상**: `_system/commands/lint.md`, `_system/commands/ingest.md` (Step 0 동시 실행 가드 재설계)
- **리뷰 실행**: `opencode run` (primary `ollama-cloud/deepseek-v4-flash`) → `review-correctness` subagent
- **Verdict (초회)**: NEEDS CHANGES — [mid] 1, [low] 2

## 지적과 독립 검증

| 등급 | 지적 | 검증 |
|---|---|---|
| [mid] | `ingest.md:44` 가 `race window 0% 회피 (lint.md Step 0 와 동일 패턴)` 로 남아 상호 참조가 거짓이 됨 | **사실 확인** — lint.md 는 flock 을 보조로 격하해 더 이상 "동일 패턴"이 아님 |
| [low] | lint.md "ingest.md 와 동일 구조" 가 전체 스택 동일로 오독될 수 있음 | 사실 — 표현 축소 |
| [low] | lint.md 에 placeholder 날짜 `2024-xx-xx` 존재 | **오독** — 해당 문자열 없음 (grep 확인) |

## 조치

1. `ingest.md` Step 0 재작성 — systemd 1차 가드 명시, flock 2차 보조로 격하, fd 상속 무력 경고 추가 (lint.md 와 동일 구조)
2. `ingest.md` `## 동시성` 우선순위 정합 (flock=2차, systemd=1차)
3. `ingest.md` 의 거짓 상호 참조 제거
4. lint.md 문구 축소 ("ingest.md 도 동일한 systemd 유닛 가드를 씁니다")

## 재검증

```
ingest.md 'race window 0%' 긍정 표현        → 없음
ingest.md 'lint.md Step 0 와 동일 패턴'      → 제거됨
lint.md / ingest.md  1차 가드 = systemd 명시 → 양쪽 존재
lint.md / ingest.md  flock 무력화 경고       → 양쪽 존재
```

## Verdict (재검증)

**PASS** — [high]/[mid] 0건.

## 기술적 주장 검증 (리뷰 확인)

- (a) fd 기반 flock 은 프로세스 경계를 넘지 못함 — **정확**
- (b) `Type=oneshot` 실행 중 중복 start 드롭 — **정확** (로컬 실측: 실행 중 유닛 start 3회 → 실행 1회)
- (d) 무조건 보장 표현 잔존 없음 — **정확**
