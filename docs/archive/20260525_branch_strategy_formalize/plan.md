# Plan — branch_strategy_formalize

작성일: 2026-05-25 (KST)
작업자: wikihub maintainer

## 1. 작업 분류

**운영 (governance / methodology)** — `CLAUDE.md`와 `docs/agent_dev_guide.md`의 개발 프로세스 정본을 갱신한다. 코드 변경 없음.

## 2. 배경 및 동기

v0.1.7~v0.1.8 진행 과정에서 메인 브랜치에 직접 push 했다가 회귀(revert)한 사고가 있었음 (4f5f206 + 4b90fc0 — `_install_yq` / interval default). 원인은 "버전 단위 통합 지점이 명시되지 않은 채 feature 별 commit 이 곧장 main 으로 흘러간 것".

v0.1.8 부터는 canary 채널을 도입하면서 `버전 브랜치 → canary tag → OCI 검증 → main` 흐름을 자연발생적으로 운용 중이지만, **이 흐름이 메소드론에 명시돼 있지 않다.** 사용자가 흐름을 명시적으로 정의해 향후 모든 feature 가 동일 절차로 흘러가도록 한다.

## 3. 정립 목표 — 브랜치 전략

```
main
  └─ v0.X.Y (버전 브랜치, integration branch)
        ├─ feature/<feat_id> (feature 브랜치) ──squash──┐
        ├─ feature/<feat_id> (feature 브랜치) ──squash──┤
        └─ feature/<feat_id> (feature 브랜치) ──squash──┤
                                                        ▼
                                                  v0.X.Y HEAD
                                                  + canary tag (force-update, 자동)
                                                        │
                                                   OCI batch 검증
                                                        │
                                            ──merge --no-ff──▶ main
                                                                + v0.X.Y annotated tag
                                                                + latest tag (force-update)
```

### 핵심 규칙 (사용자 확정)

| 항목 | 결정 | 비고 |
|---|---|---|
| feature 브랜치 분기 base | **버전 브랜치에서만** | main 직접 분기 금지. hotfix 도 버전 브랜치 경유. |
| feature → 버전 브랜치 머지 | **squash merge** | 1 feature = 1 commit on 버전 브랜치. |
| feature 브랜치 squash 후 처리 | **즉시 삭제 + worktree 정리** | `git branch -D feature/*` + `git worktree remove`. 흔적은 `features/archive/` 만. |
| canary tag 갱신 | **squash 후 매번 자동 force-update** | 버전 브랜치 모든 commit 이 canary 후보. Step 5 Deploy 의 명시 액션. |
| 버전 브랜치 → main 머지 | **merge commit (--no-ff)** | 버전 단위 history 가 main 에 보존. version annotated tag 가 머지 commit 에 부착. |
| main 머지 = release | version annotated tag + latest tag force-update | latest 는 항상 main HEAD 의 release commit 을 가리킴. |

## 4. 적용 단계 선언

| 단계 | 수행 여부 | 사유 |
|---|---|---|
| Step 2 Design | **수행** | 메소드론 정본(§3, §6, §7, §8) 다수 절 동시 갱신 → 정합성 보장 필요. |
| Step 2 Design Review | **수행** (멀티 리뷰어) | 거버넌스 변경 → 후속 누적 비용 큼. 독립 리뷰 2 인 권장. |
| Step 3 Implementation | **수행** | `CLAUDE.md` + `docs/agent_dev_guide.md` 갱신. |
| Step 4 Code Review | **수행** (멀티 리뷰어) | 메소드론은 코드보다 한 번 잘못 쓰면 회복 비용이 큼. 멀티 리뷰 유지. |
| Step 5 Deployment | **생략** | `_system/` + 인프라 스크립트 둘 다 미변경. CLAUDE.md §5 의 "메인테이너 가이드만 변경" 조건 충족. → HISTORY.md 항목 추가도 생략. |

## 5. 예상 영향 범위

| 파일 | 변경 성격 |
|---|---|
| `CLAUDE.md` §3 (Feature-based Workflow) | 브랜치 흐름 다이어그램 + Step 1/5 절차에 git 액션 명시. |
| `CLAUDE.md` §6 (Worktree) | 분기 base 명시(`feature/<id>` from `v0.X.Y`) + 정리 시점 명시. |
| `CLAUDE.md` §7 (Feature Dir & ADR) | 변경 없음 (구조 유지). |
| `CLAUDE.md` §8 (Version Management) | 버전 브랜치 ↔ tag 매핑 표 추가. |
| `docs/agent_dev_guide.md` Step 1/2/3/5 + mermaid | CLAUDE.md 와 정합. |
| `README.md` | canary 절(이미 존재)에 "버전 브랜치 → canary → main → latest" 흐름 1 단락 추가 (선택). |

> ADR 신설 여부: 본 정립은 **운영 절차 결정**으로 ADR 사안(아키텍처 결정) 보다 메소드론 갱신에 가까움. ADR 미생성을 기본으로 하되, Step 2 분석에서 ADR 필요성 재확인.

## 6. 미결 사항

| ID | 미결 사항 | Step 2 에서 결정 |
|---|---|---|
| Q1 | 본 feature 를 v0.1.8 브랜치에 묶을지, v0.1.9 신설할지 | (a) v0.1.8 에 묶음 — 새 프로세스의 첫 적용 대상이 cleanup 다음 feature → 메타 변경도 같은 release. (b) v0.1.9 신설 — Atomic Change 엄격 해석. |
| Q2 | hotfix 의 정의와 흐름 | 운영 production 에서 발견된 critical bug — 새 hotfix 버전 브랜치(v0.1.8.1 같은 patch 자릿수 승격) 신설할지, 다음 minor 의 첫 feature 로 다룰지. |
| Q3 | feature 단위 squash 의 commit message convention | "feat(<feat_id>): ..." vs "feat: <feat_id> ...". 기존 commit 들과 일관성 검토. |
| Q4 | canary tag 자동화 수준 | 메소드론에 "Step 5 deploy 시 force-update" 만 명시할지, 자동화 script(`scripts/canary_push.sh` 등) 까지 도입할지. |
| Q5 | latest tag = main HEAD 인지, version tag 와 동일 commit 인지 명시 | 항상 같지만 (merge commit 에 모두 부착) 문서상 명시 위치 결정. |

## 7. Definition of Done (Plan)

- [ ] `CLAUDE.md` §3 다이어그램 + Step 5 절차에 git 액션 라인 포함
- [ ] `CLAUDE.md` §6, §8 갱신
- [ ] `docs/agent_dev_guide.md` 동일 변경 반영 (mermaid 포함)
- [ ] Step 2 의 미결 Q1~Q5 모두 결정 (또는 명시적 "보류" 처리)
- [ ] Step 4 멀티 리뷰어 (2 명 이상) 리뷰 통과
- [ ] HISTORY.md 미변경 (Step 5 생략 결정)
- [ ] Feature 종료 시 archive 이동

## 8. Methodology 적용

본 절차 자체 적용 — 메타 거버넌스 변경은 trivial 이 아님 (영향 범위 광범위).

---

## v2 — 2026-05-25 (Step 4 code review 후 자기-적용성 모순 명문화)

본 feature 는 새 메소드론(branch_strategy_formalize) 자체를 정립하는 PR 이므로 **정립 이전의 흐름** (v0.1.8 브랜치에 직접 modify) 으로 진행한다. 즉 본 PR 자체는 새로 정의된 5 액션 (`feature/<id>` 분기 → squash) 을 따르지 않는다.

- 진행 환경: v0.1.8 브랜치의 working tree 에 직접 변경 누적.
- squash 시점: 본 PR 의 working tree 변경을 v0.1.8 의 다음 commit 으로 일반 commit (squash merge 아님) 처리.
- 흡수: squash commit 이 만들어진 시점부터 새 메소드론이 차기 feature 부터 적용됨.

이 자기-적용성 모순은 의도된 결정 — 메소드론을 자기 자신에게 적용하려면 메소드론이 먼저 존재해야 하는 부트스트랩 문제. code_review_2 §"메소드론 자기-적용성 검증" 참조.
