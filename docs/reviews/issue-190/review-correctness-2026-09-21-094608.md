# Review 1 — Correctness (issue #190)

- **Date**: 2026-09-21
- **Subagent**: `review-correctness` 요청 (프롬프트에 subagent 명시)
- **Actual execution**: `agent=build mode=primary` — **primary 가 직접 리뷰**함 (subagent 미호출)
  - 원인: `--agent` 플래그 없이 실행했고, primary 가 task 도구를 쓰지 않고 자체 리뷰를 수행
  - ⚠️ 정직 기록: 이번 회차 리뷰는 **subagent 가 아닌 primary(`deepseek-v4-flash`) 직접 수행**이다.
    모델 사용 내역에 그대로 기재한다.
- **Scope**: `git diff HEAD -- install.sh wikihub.yaml.example docs/agent_dev_guide.md`

## Verdict: SOUND — FAIL-CLOSED 가드 3중, 데이터 파괴 경로 없음

## 확인된 정확성
- `_hermes_root()` parameter expansion: `/profiles/<name>/home` 3-segment 제거 정상, trailing slash 없음
- `_hermes_stray_candidates()` dedup: `_a` 리셋 후 `-n "$_a"` false → `_b` 만 emit, 로직 정확
- **FAIL-CLOSED 3중**: candidates 필터 + loop 가드 + `[[ -f ]]` — 어떤 profile canonical 도 선택 불가
- `set -euo pipefail` 하에서 loop abort 경로 없음 (`&&`/`||` 면제, `|| true` 보호, `return 0`)
- 파괴 경로 없음: `cp -p` 백업 + 7일 retention + `noop`/`read_error` 시 백업 회수

## 최PM 실증 (실환경 조건, 실제 파일 미접촉)

| 케이스 | 결과 |
|---|---|
| CASE 1 실환경(`HOME=/home/ubuntu`, `HERMES_HOME=profiles/jisaseo`) | `config_path` = **정본** ✅, 후보 1건(잔재) |
| CASE 2 `HERMES_HOME` 미설정 (SSH) | 정본 도달 ✅ (step 3) |
| CASE 3 `HOME=<profile_home>` (구 실행 방식) | 정본 도달 ✅, dedup 동작 |
| CASE 4 **default 정본 보호** | 후보 포함 **0건** ✅ |
| CASE 5 `HERMES_CONFIG_HOME` override | 정본 ✅ (모드 B 가드 유지) |
| CASE 6 Docker/custom root (`HERMES_HOME=/opt/data`) | `/opt/data/config.yaml` ✅ |

실제 stray 정리 시뮬레이션: default 정본 **무변경**(sha256), 프로필 정본 무변경, 잔재만 삭제 + 백업 생성.

**두 실패 모드 대조 재현**:
- 모드 A (v0.1.16): `config_path` = `$HOME/.hermes/config.yaml` = default 정본 → skill 이 잘못된 곳에 기록. 새 코드는 정본 도달 ✅
- 모드 B (v0.1.16 + `HERMES_CONFIG_HOME`): default 정본에서 wikihub entry 제거 확인(sha256 변경). 새 코드는 후보 0건 ✅
