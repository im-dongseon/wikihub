# Review — issue #176 (correctness)

- **일시**: 2026-09-14 (KST)
- **대상**: `scripts/_helpers/detect_alias_duplicates.py` (distinct-path 필터)
- **리뷰 실행**: `opencode run` (primary `ollama-cloud/deepseek-v4-flash`) → `review-correctness` subagent
- **Verdict (초회)**: NEEDS CHANGES — [mid] 2, [low] 1

## 초회 지적

| 등급 | 지적 | 검증 결과 |
|---|---|---|
| [mid] | 출력 `pages` 에 같은 path 가 중복 보고될 수 있음 | **사실 확인** — 변형 alias + 타 페이지 공유 시 동일 경로 2회 출력 |
| [mid] | 이 모듈에 대한 테스트 부재 | **사실 확인** — `tests/` 에 미존재 |
| [low] | `p["path"]` 무가드 접근 | 유지 — `_collect_aliases()` 가 항상 경로를 채움 |

## 조치

- 출력 직전 path 기준 dedupe 추가 (`by_path` → `unique_pages`)
- `tests/test_alias_duplicates.py` 신규 7케이스 (오탐 방지 2 / 탐지 유지 2 / dedupe 1 / stem fallback 1 param×2)

## 검증

```
tests/test_alias_duplicates.py ....... 7 passed
tests/ (전체) .......................... 81 passed, 1 skipped

운영 wiki(/home/ubuntu/wikihub) 실측:
  HEAD(미패치) case_variant=3 → 패치 case_variant=0
  (xguru / effort / prompt engineering)
```

## Verdict (재검증)

**PASS** — [high]/[mid] 0건.
