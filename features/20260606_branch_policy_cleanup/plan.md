# Plan: 브랜치 정책 cleanup/bootstrap 분리

## 메타

- **분류**: 리팩토링 (스크립트 + 문서 + 스킬)
- **타겟 버전 브랜치**: v0.1.12
- **적용 단계**: Step 4 (리뷰) 포함, Step 5 (배포) PR까지 — 머지는 사용자

## 배경

fc99d8b (v0.1.12) 에서 release.sh에 post-release 자동 bootstrap(v0.1.13 branch + canary tag 생성)을 통합했으나, 사용자가 다음 두 가지 문제를 제기:

1. **고아 branch**: release 직후 이슈 0개여도 v0.X.Y branch가 미리 생성됨
2. **canary tag 무의미**: 다음 issue 없으면 canary가 main HEAD에 고정되어 trace 가치 없음

## 목표

`release.sh`의 책임을 **release-time cleanup만**으로 한정하고, **새 버전 시작**은 on-demand로 분리.

## 변경 범위

| # | 파일 | 변경 |
|---|---|---|
| 1 | `scripts/release.sh` | post-release 단계 (라인 185~244) 제거 — cleanup만 유지 |
| 2 | `scripts/bootstrap_version.sh` | **신규** — release.sh post-release 부분 추출 + doc 갱신 통합 |
| 3 | `AGENTS.md` | §3 Step 5 / §8 Tag 운영 표 갱신 |
| 4 | `docs/agent_dev_guide.md` | post-release ref 상태, bootstrap 절차 추가 |
| 5 | `.hermes/skills/github/github-dev-flow/SKILL.md` | Step 4 진입 시 `origin/{base_branch}` 부재 감지 → bootstrap_version.sh 자동 호출 |
| 6 | `docs/changelog.md` | (이번 release에서만) v0.1.13 (canary) entry 추가 |

## 핵심 결정 (user 확정)

| # | 결정 |
|---|---|
| 1 | bootstrap trigger 위치: **github-dev-flow Step 4 진입 시 자동** |
| 2 | 다음 버전 번호: **patch+1 유지** (v0.1.13 → v0.1.14) |
| 3 | 적용 시점: **v0.1.12 release 직전** (v0.1.12 진행 중이지만 release 전 머지) |

## 영향 분석

- v0.1.12 release 시: cleanup만. v0.1.13 자동 생성 X
- v0.1.12 release 후 첫 issue: dev-flow Step 4에서 origin/v0.1.13 부재 감지 → bootstrap_version.sh 자동 호출
- hotfix base 변경 없음: `refs/tags/v0.X.Y` (annotated, main HEAD) 유지
- 사용자 워크플로: release 명령은 동일. 첫 새 issue 시 추가 작업 1회 (bootstrap) 자동

## DoD

- [ ] `release.sh` post-release 6, 7 단계 제거 (cleanup만)
- [ ] `scripts/bootstrap_version.sh` 신규 — cleanup + 새 branch + canary + doc 갱신
- [ ] `AGENTS.md` §3 / §8 갱신
- [ ] `docs/agent_dev_guide.md` post-release ref / bootstrap 절차 갱신
- [ ] `github-dev-flow` Step 4 auto-trigger 추가
- [ ] `changelog.md` v0.1.13 (canary) entry (bootstrap 시 사용 가능)
- [ ] dry-run 검증: `release.sh --dry-run v0.1.12` 정상 종료
- [ ] Review 1/2 (background) 통과
- [ ] PR 생성, 사용자 머지 대기

## 비범위

- 버전 명명 정책 (semver 정식 도입) — 별도 ADR
- hotfix workflow 변경 — 현행 유지
- `promote_canary.sh` (있다면) 변경 — release.sh와 별개
