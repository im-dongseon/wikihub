# install_update_hardening — plan.md

## 작업 분류

버그 fix — install.sh update flow 의 3 결함 (v0.1.8 canary 검증 중 surface).

## 타겟 버전 브랜치

`v0.1.8` (canary 누적 중, release 직전 hotfix 흡수).

## 적용 단계 선언

| Step | 수행 | 사유 |
|---|---|---|
| 1 Plan | 수행 | 본 문서 |
| 2 Analysis & Design | 수행 | 3 결함의 fix 안 명시 + 미결 사항 결정 |
| 3 Implementation | 수행 | install.sh + .gitignore patch |
| 4 Review | **생략** | 변경 크기 < 50줄 + 단일 파일 + 외부 인터페이스 미변경 (CLAUDE.md §3 Step 4 생략 조건 3항목 충족). 자가 검증 + 사용자 승인으로 대체. |
| 5 Deploy | 수행 | install.sh 변경 — 운영 영향. squash to v0.1.8 + canary force-update. |

## 예상 영향 범위

| 파일 | 변경 성격 |
|---|---|
| `install.sh` | `_install_graphify` PATH prepend (~3줄), update flow self-restart (~5줄) |
| `.gitignore` | `_system/INSTALLED_VERSIONS.json` 1줄 추가 |
| `docs/adr/` | self-restart 정책이 결정으로 ADR 발의 — Step 2 에서 미결 사항으로 surface |

총 변경 ~10줄.

## 결함 surface 경위

v0.1.8 canary (`a9f971e`) 검증 중 multipass `wikihub-test` 에서 `install.sh --version canary` 실행 → 3회 fail (회피 거쳐 통과):

1. `_system/INSTALLED_VERSIONS.json` untracked → `git status --porcelain` 가 `??` detect → update guard L1439 차단
2. `git reset --hard canary` 직후 bash 가 이미 read 한 `WIKIHUB_SKILLS=` 5건 유지 (2c4b42d source) → a9f971e 의 4 skill list 와 mismatch → wh-graphify lookup fail → rollback
3. `_install_graphify` 가 venv/bin 을 PATH prepend 안 함 → `command -v graphify` fail → exit 2

## 메소드론 적용

수행 — install.sh update flow 정합성에 영향. trivial 아님.
