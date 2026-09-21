# Review 1 — Correctness (issue #185)

- **Date**: 2026-09-21
- **Subagent**: `review-correctness` (`mode: subagent`) — **정상 호출됨**
- **Actual model**: `ollama-cloud/kimi-k3` (`agent=review-correctness mode=subagent modelID=kimi-k3`)
  - opencode 설정 3자 정합 수정(#190 선행 커밋) 후 첫 실행이며, 의도한 모델로 동작 확인.
- **Primary**: `ollama-cloud/deepseek-v4-flash`
- **Scope**: `git diff HEAD -- _system/commands/ingest.md scripts/lib/config.py docs/adr/0010-operational-tooling-split.md`

## Verdict: NEEDS CHANGES (2 findings, both minor)

| # | 등급 | 내용 | 최PM 처리 |
|---|---|---|---|
| 1 | mid | `tests/test_config.py` — fallback 분기(`path=None`) 미커버. 기존 테스트는 모두 명시 path 전달 | **수정** — env 기반 테스트 3건 추가 (`monkeypatch` + `tmp_path`) |
| 2 | low | `scripts/lib/config.py:180-181` docstring 이 중간 rung(`WIKIHUB_HOME`)을 누락 | **수정** — 3단계 precedence 명시 |

## 최PM 실증

- fallback 분기 테스트 부재 확인: `grep -c 'load_wikihub_yaml()' tests/test_config.py` → **0건**
- 신규 테스트 3건 추가 후 `15 passed` (기존 12 + 신규 3)
- 3번 테스트(`test_default_resolution_no_opt_wikihub`)는 `VaultSyncFatal.reason` 으로 **실제 resolution 경로를 단언**하고 `/opt/wikihub` 부재를 회귀 가드로 검사

## 검증 결과 (실측)

| 항목 | 결과 |
|---|---|
| 하드코딩 제거 | `grep -rn '/opt/wikihub' _system/commands/ scripts/` → 실제 경로 0건 (docstring 설명 문구 1건만 잔존) |
| python syntax | `ast.parse` OK |
| fallback chain (a) `WIKIHUB_YAML` unset + `WIKIHUB_HOME` 지정 | 해당 경로 시도 ✅ |
| fallback chain (b) `WIKIHUB_YAML` 지정 | env 최우선 ✅ |
| 회귀 — 운영 yaml | 정상 파싱 ✅ |
| tests | 15 passed |
