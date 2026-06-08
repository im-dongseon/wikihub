---
approved: false
version: v1
---

# Plan: graphify-bug

## 작업 분류
- **분류**: 버그 수정
- **타겟 버전 브랜치**: `v0.1.10`

## 문제 요약
`graphify` CLI가 `--out "$WIKIHUB_HOME"`으로 메인 출력은 올바르게 보내지만, 입력 경로 아래에 `graphify-out/cache/` (per-file semantic 분석 캐시)를 side effect로 생성함. 이 cache가 남아있으면 lint가 다음 cycle에서 다시 발견→아카이빙하는 lint→graphify 무한 루프 발생.

## 해결 방안
`wikihub_graphify.sh` 종료 전(Step 5)에 `$WIKIHUB_HOME/wiki/graphify-out/` cache 디렉토리를 `rm -rf`로 정리.
- cache를 유지할 가치가 낮음 (증분 빌드의 진정한 메커니즘은 manifest.json의 AST hash)
- 남겨두면 lint→graphify 무한 루프만 재생됨
- `.graphifyignore`는 방어망으로 유지

## 적용 단계 선언
| 단계 | 수행 | 사유 |
|---|---|---|
| Step 1 (Plan) | ✅ | 본 문서 |
| Step 2 (A&D) | ✅ | 변경 영향 분석 필요 |
| Step 3 (구현) | ✅ | wikihub_graphify.sh 수정 |
| Step 4 (검토) | ❌ 생략 | 단일 파일, 5줄 이하 변경, 외부 인터페이스 미변경 |
| Step 5 (배포) | ❌ 생략 | OCI 직접 적용 후 repo backport 예정 |

## 예상 영향 범위
- `scripts/wikihub_graphify.sh` — Step 5 cache cleanup 1개 블록 추가 (~5줄)

## 메소드론 적용 여부
- **적용** (변경 절차가 단순하나 시스템 동작에影響 → plan + A&D 작성)
