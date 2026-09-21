# Review — issue #177 (correctness)

- **일시**: 2026-09-14 (KST)
- **대상**: `scripts/wikihub_graphify.sh` openai 분기 (OPENAI_BASE_URL 전달)
- **리뷰 실행**: `opencode run` (primary `ollama-cloud/deepseek-v4-flash`) → `review-correctness` subagent
- **Verdict (초회)**: NEEDS CHANGES — [mid] 1

## 초회 지적과 독립 검증

| 등급 | 지적 | 검증 |
|---|---|---|
| [mid] | `$endpoint` 미설정 시 `OPENAI_BASE_URL=""` 가 명시 전달되어, 미설정 profile(문서 §6.4 `openai_gpt4`)이 깨질 수 있음 | **사실 확인 (실증)** |

### 실증 근거

1. 리뷰가 인용한 파일명 `docs/graphify-backend-test-cases.md` 는 **오기** — 실제 파일은 `docs/graphify-backend-test-reference.md`. 해당 §6.4 에 `openai_gpt4` 프로필이 ENDPOINT 없이 API_KEY+MODEL 만 설정하는 형태로 **실재**한다.
2. graphify 0.9.32 소스 `llm.py:153`:
   ```python
   "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
   ```
   → 키가 **존재하면** 빈 문자열도 그대로 반환. fallback이 발동하지 않는다.
3. 실측:
   ```
   미설정:    os.environ.get(...) → 'https://api.openai.com/v1'
   빈 문자열: os.environ.get(...) → ''
   OpenAI(api_key='sk-x', base_url='') → base_url ''
   ```
4. 스크립트 경로 실측 (stub graphify):
   ```
   패치(초회): endpoint 미설정 → OPENAI_BASE_URL is SET (len=0)   ← 회귀
   미패치 HEAD:                 → OPENAI_BASE_URL is ABSENT
   ```

## 조치

endpoint 가 비어 있으면 변수 자체를 넘기지 않도록 배열 구성으로 변경:

```bash
openai_env=(OPENAI_API_KEY="$api_key")
if [[ -n "$endpoint" ]]; then
    openai_env+=(OPENAI_BASE_URL="$endpoint")
fi
timeout "$timeout_sec" env "${openai_env[@]}" ...
```

## 검증 (재실측)

```
A) endpoint 설정   → OPENAI_BASE_URL is SET (len=27) 'https://zen.test.invalid/v1'
B) endpoint 미설정 → OPENAI_BASE_URL is ABSENT          (openai_gpt4 경로 보존)
C) ollama 분기     → OPENAI_BASE_URL is ABSENT, 무영향
bash -n 통과
```

## Verdict (재검증)

**PASS** — [high]/[mid] 0건.

## 부수

- tests/ 에 graphify dispatch 자동 테스트 없음(bats/CI hook 미도입) — 기존 상태, 본 이슈 범위 밖으로 보고만.
- `:142` 하드코딩 `--max-concurrency 4` (ollama 는 `$concurrency` 휴리스틱) — 기존 설계, 무변경.
