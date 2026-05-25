# Design Review 1 — branch_strategy_formalize (메소드론 정합성)

작성일: 2026-05-25
리뷰어: claude (서브에이전트, general-purpose)
검토 대상: `features/20260525_branch_strategy_formalize/analysis_and_design.md` (v1, 222 라인)

---

## 종합 평가

**통과(조건부)** — 방향성과 핵심 규칙(Q1~Q5 default) 은 타당하나, **(a) 메소드론 정본의 다른 절(§5 멀티에이전트 / §1 Separation of Concerns / Step 4 결함 복귀 흐름)과의 정합 누락**, **(b) edge case 6건 미정의(squash 후 결함 발견 / 동시 진행 feature 충돌 / canary force-update 사고 / version 브랜치→main conflict / main release commit 작성자 / hotfix patch 자릿수 부재)**, **(c) "자동"·"즉시" 같은 행위 주체 불명 표현 4건** 이 남아있다. C 1건 + H 5건 보강 후 Step 3 진행 권고.

---

## C 항목 (Critical — 미해결 시 진행 불가)

### C1. squash 후 Step 4 에서 결함 발견 시 복귀 경로 미정의

- **위치**: design.md §2.3 표 B "Step 5 활동" 5 액션 / CLAUDE.md §3 Step 4 "범위 내 결함" 점선 흐름
- **결함**: 현행 CLAUDE.md §3 mermaid 의 `Review4 -.->|"범위 내 결함:<br/>Step 2/3 복귀"| AD` 점선이 본 design 의 변경 후 의미가 깨진다.
  - design 은 "Step 5 액션 1 = squash merge to 버전 브랜치" 를 명시했지만, **Step 4 는 Step 5 *전* 에 수행** 된다(CLAUDE.md §3 Step 4 진입 조건 "구현 결과물 검토"). 즉 squash 전에 review.
  - 그러나 Step 4 통과 → Step 5 squash → **Step 5 도중 (예: canary OCI 검증 도중) 결함 발견** 케이스에 대한 복귀 경로가 없다. 이미 squash 됐으므로 feature 브랜치는 `git branch -D` 됨(액션 3). 새 hotfix feature 를 발급해야 하는지, 같은 feat_id 로 v2 분석을 추가해야 하는지 정본이 침묵.
  - design.md §2.4 mermaid 도 `Squash --> Release` 한 방향 화살표만 있고 Squash 후 복귀 점선이 없다.
- **권고**: design.md §2.3 또는 §2.4 에 다음 케이스 명시 라인 추가.
  ```
  Step 5 액션 1(squash) 이후 canary OCI 검증에서 결함 발견 시:
  - 결함이 본 feature 범위 내 → 같은 feat_id 로 새 feature 브랜치를 버전 브랜치 HEAD 에서 다시 분기,
    추가 commit 1건을 또 squash. analysis_and_design.md 에 `## v2 — 결함 사후 보강` 섹션 append.
  - 결함이 범위 외 → 새 feat_id 발급, 별도 feature 로 squash.
  - 두 경우 모두 canary tag 는 새 commit 으로 다시 force-update.
  ```
  더불어 §2.4 mermaid 에 `Squash -.->|"canary 검증 결함"| Plan` 점선을 추가해 흐름이 닫히게 한다.

---

## H 항목 (High — 강력 권고)

### H1. "자동" 의 주체 불명 — 메소드론은 사람 절차이므로 행위자 명시 필요

- **위치**: design.md §2.2 표 행 "canary tag 갱신": "squash 직후 매번 force-update"; plan.md §3 표: "squash 후 매번 자동 force-update"; §2.4 mermaid 의 "(b) canary tag force-update"
- **결함**: "자동" 의 주체가 (a) 사람(메인테이너가 손으로 명령 실행), (b) shell script, (c) AI 에이전트(`Step 5 진행해줘` 라는 사용자 발화에 trigger) 중 어느 것인지 명시되지 않았다. plan.md §6 Q4 의 default("메소드론에 force-update 절차만 명시 / 자동화 script 미도입") 는 자동화 script 가 없음을 뜻하지만, 그렇다면 "자동" 표현 자체가 misleading.
- **권고**: design.md §2.2 와 §2.3 의 모든 "자동" 표현을 다음 중 하나로 통일.
  - 사람 주체: "**메인테이너가** squash 직후 다음 2 명령을 실행: `git tag -f canary && git push origin canary --force`"
  - 에이전트 주체: "**에이전트가** Step 5 진입 시 자동 실행 (사용자 승인 후)"
  현재 default 흐름은 사람 주체이므로 "자동" → "**즉시 (수동 실행)**" 로 치환 권장. plan.md §3 표의 "자동" 한 단어도 동일 정정 필요.

### H2. 한 버전 브랜치에 여러 feature 동시 진행 시 충돌 해결 절차 부재

- **위치**: design.md §2.1 다이어그램 / §2.2
- **결함**: 다이어그램은 `feature/<feat_id>` 단수형으로 1개만 표현. plan.md §3 의 ASCII 는 3개 feature 가 직렬로 squash 되는 모습만 보임. 그러나 실제로 두 maintainer 또는 두 에이전트 세션이 동시에 같은 버전 브랜치(v0.1.8)에 squash 하면 fast-forward 가 깨진다(`! [rejected] non-fast-forward`).
- 또한 두 feature 가 같은 파일을 수정하면 squash merge 단계에서 conflict 발생. 어느 feature 가 양보하고 base 를 갱신해야 하는지 정본이 침묵.
- **권고**: design.md §2.2 표 또는 §2.3 표 D 에 다음 행 추가.
  ```
  | 동시 진행 충돌 | feature 분기 후 base(버전 브랜치 HEAD) 가 다른 feature 의 squash 로 advance 한 경우,
                   squash 직전 `git fetch && git rebase origin/v0.X.Y` 로 base 갱신. conflict 발생 시
                   현 feature 가 해결 책임 (later-wins).
                   동시 두 feature 가 같은 정본 파일(예: CLAUDE.md) 수정 시 plan.md 단계에서 직렬화. |
  ```

### H3. canary tag force-update 가 잘못된 commit 을 가리킬 때의 rollback 부재

- **위치**: design.md §2.2 "canary tag 갱신" 행 / §2.3 표 B 액션 2
- **결함**: canary 는 lightweight + force-move 라 history 가 없다. 메인테이너가 실수로 `git tag -f canary <wrong-sha>` push 했을 때 이전 canary 위치로 되돌리는 절차가 정본에 없다.
  - 실제로는 버전 브랜치 reflog 에서 직전 HEAD 찾아 다시 force-update 하면 되지만, 정본에 명시 없으면 사고 발생 시 panic.
- **권고**: design.md §2.3 표 B 또는 §2.5 연계 항목에 다음 추가.
  ```
  canary tag 오설정 rollback:
  1. `git -C "$WIKIHUB_SRC" reflog show v0.X.Y` 로 직전 valid commit 확인
  2. `git tag -f canary <prev-sha> && git push origin canary --force`
  3. OCI 운영 서버에서 `install.sh --update --branch canary` 재실행
  (canary 는 history 가 없으므로 reflog 가 유일한 trace 출처.)
  ```

### H4. 버전 브랜치 → main merge --no-ff 가 conflict 발생할 가능성 미정의

- **위치**: design.md §2.2 "버전 브랜치 → main 머지" 행
- **결함**: 표는 `merge --no-ff` 만 명시. 그러나 다음 케이스에 conflict 가능:
  - main 에서 직접 수정 commit 이 있던 경우 (현재는 명시적으로 금지되지 않았음 — 본 design 도 main push 금지를 표 밖에서만 언급 in §2.2 행 "feature 분기 base").
  - 이전 release 의 hotfix 가 main 에 따로 squash 됐는데 다음 minor 버전 브랜치는 그 hotfix 이전에서 분기된 경우.
- 또한 design 은 "main 직접 push 금지" 를 *암묵적으로* 가정하면서도 그 규칙을 §2.2 표의 독립 행으로 분리하지 않았다. plan.md §3 표 첫 행("hotfix 도 버전 브랜치 경유. main 직접 분기 금지") 의 노트로만 존재.
- **권고**:
  1. design.md §2.2 표에 **독립 행** 추가:
     ```
     | main 직접 commit | **금지** | release merge commit (`merge --no-ff`) 만 main 에 도달한다. push 권한이 있더라도 메인테이너는 main 으로 checkout 후 직접 commit 하지 않는다. 위반 시 다음 release 의 history 일관성 깨짐. |
     ```
  2. §2.3 표 B 액션 4 에 "merge --no-ff 시 conflict 발생하면 main 으로 force-push 대신 버전 브랜치에서 `git merge main` 으로 사전 동기화 후 재시도" 절차 추가.

### H5. hotfix 정의가 너무 모호 — Q2 default 가 실제 운영을 충분히 커버하지 못함

- **위치**: design.md §2.2 마지막 행 "hotfix 흐름" / plan.md §6 Q2
- **결함**: Q2 default 는 "patch 자릿수(`v0.1.X.Y`) 도입은 별개 feature 로 결정 / 일단 다음 minor 의 첫 feature 로 흡수" 이다. 그러나 다음 시나리오 미커버:
  - production OCI 에서 v0.1.7 사용 중 critical bug 발견. v0.1.8 은 작업 중이고 다른 feature 와 묶여 있어 즉시 release 불가.
  - 이 경우 v0.1.7 hotfix release 가 필요한데, 본 design 은 "다음 minor 첫 feature 로 흡수" 라서 운영 불가능 (release 기다려야 함 = downtime).
- 또한 design.md §1.2 결함 표 F7 ("hotfix 정의 부재") 을 결함으로 인정해놓고 해결을 "별개 feature 로 미룬다" 는 모순.
- **권고**: 두 선택지 중 명시.
  - **선택지 A (권고)**: 본 design 에서 hotfix 흐름의 **최소 정의** 라도 제공 — "v0.1.X production critical → `hotfix/v0.1.X` 브랜치를 `v0.1.X` annotated tag 에서 분기 → fix squash → annotated `v0.1.X.1` tag + latest force-update + main `merge --no-ff`. 다음 minor 작업 중인 v0.1.X+1 브랜치는 hotfix 를 별도로 cherry-pick 또는 rebase." (patch 자릿수 도입을 본 feature 에 포함)
  - **선택지 B**: hotfix 가 정말 별개 feature 라면 §1.2 결함 표 F7 을 **본 feature 의 범위 외** 로 명시 이동하고 §4 미결 사항에 "Q6: hotfix 흐름은 별도 feature 로 다룬다" 추가. 현재는 결함으로 표시해놓고 미해결.

### H6. 메소드론 §5 "멀티에이전트 접근법" 의 worktree 격리 흐름과 §6 갱신의 호환성 검증 누락

- **위치**: design.md §2.3 표 D §6 Worktree / §2.5 연계 정합
- **결함**: design 은 "feature 분기 base = `v0.X.Y` 버전 브랜치" 로 강제. 그러나 Claude Agent tool 의 `isolation: "worktree"` 옵션(agent_dev_guide.md §"Claude Code Agent tool 연동", line 399-405) 은 임시 worktree 를 **자동 생성** 한다. 임시 worktree 의 base 가 무엇인지 (현재 HEAD? main? feature 브랜치?) 본 design 이 강제하는 "버전 브랜치에서 분기" 규칙을 자동 worktree 가 어기지 않는지 검증 누락.
- 또한 agent_dev_guide.md line 411 ("Worktree 미사용 기본 경로") 의 예시 `git checkout -b feature/[기능개발주제명]` 은 현재 HEAD 에서 분기 — `git checkout v0.X.Y` 가 선행되지 않으면 main 에서 분기될 수 있다. 본 design 변경 시 이 예시도 명시적으로 수정해야 함.
- **권고**:
  - design.md §2.3 표 D §6 의 After 칸을 더 구체화:
    ```
    git checkout v0.X.Y           # 1. 버전 브랜치로 먼저 이동 (필수)
    git worktree add ../wikihub-feat/[date]_[id] -b feature/[id]
                                  # 2. 현 위치(=v0.X.Y) 에서 분기
    ```
  - §2.5 연계 정합 표에 **"agent_dev_guide.md §멀티에이전트의 Agent tool worktree 자동 격리"** 행 추가하고 "임시 worktree 가 현 HEAD 에서 분기되므로, 호출 전 `git checkout v0.X.Y` 가 선행돼야 함" 명시.

---

## M 항목 (Medium — 권고)

### M1. CLAUDE.md §1 Separation of Concerns 의 "`deploy.sh` 를 통해서만 `_system/` 주입" 표현과의 정합

- **위치**: design.md §2.3 표 B Step 5 5 액션
- **결함**: 현행 CLAUDE.md §1 line 13 은 "검증 완료 후 `deploy.sh`를 통해서만 `_system/`을 운영 대상으로 주입" 명시. 그러나 본 design 의 새 Step 5 5 액션에는 `deploy.sh` 호출이 없다(squash / canary tag / branch -D / main merge / version tag). 이는 §1 과의 정합 충돌.
  - 실제로 본 레포에 `deploy.sh` 가 존재하지 않음 (`ls /Users/ds.im/workspace/repo/wikihub/` 결과: `_system, AGENTS.md, CLAUDE.md, docs, features, install.sh, LICENSE, README.md, scripts, ...`). `deploy.sh` 자체가 phantom file.
  - 현실의 배포 메커니즘은 `install.sh --update --branch canary` (OCI 측에서 pull) 흐름.
- **권고**: design.md §3 개정 범위 요약 표에 다음 행 추가.
  ```
  | `CLAUDE.md` §1 line 13 | +1 / -1 | "deploy.sh를 통해서만" → "버전 브랜치 squash + main merge --no-ff 흐름을 통해서만" 정정 |
  ```
  또는 별도 §2.3 표 F 신설로 §1 정합 갱신을 명시. (메소드론 정본 일관성 차원에서 본 feature 범위에 포함 권장.)

### M2. Step 1 plan.md 의 "타겟 버전 브랜치" 필드 — 사후 변경 가능성

- **위치**: design.md §2.3 표 A 마지막 행
- **결함**: Step 1 단계에서 "타겟 버전 브랜치 = v0.1.8" 로 plan.md 에 기록한다. 그러나 작업이 길어져 v0.1.8 이 release 된 후 본 feature 가 계속되는 경우(v0.1.9 로 흘러야 함) plan.md 의 값을 정정해야 한다. 정정 절차가 명시되지 않음.
- **권고**: design.md §2.3 표 A 마지막 행에 부연 추가.
  ```
  본 값은 Step 1 시점의 의도이며, Step 2/3 도중 타겟 minor 가 advance 된 경우 plan.md
  에 `## 타겟 버전 변경` 섹션을 append 하고 base 를 새 버전 브랜치로 rebase 한다.
  ```

### M3. §2.4 mermaid 의 `flowchart TD` vs `graph LR` 선택

- **위치**: design.md §2.4 mermaid (line 149)
- **결함**: 본 흐름은 **분기/병합 노드** 가 핵심(Release 분기, Squash 후 canary, main merge). `flowchart TD` 는 세로 흐름이라 `Release{...}` 결정 노드 좌우 분기가 압축적으로 보이지 않는다. 또한 본 design 의 §2.1 ASCII 다이어그램은 가로/세로 혼용 — mermaid 도 동일 의미가 시각적으로 깨지지 않게 LR(가로) 권장.
- **권고**: 두 가지 검토.
  - **권고**: `flowchart LR` 로 변경. Release 결정 노드와 두 분기(`중간 feature` vs `버전 batch 완료`) 가 좌우로 펴져 가독성 향상.
  - 또는 CLAUDE.md §3 의 기존 mermaid 가 TD 이므로 일관성 차원에서 TD 유지하되, MainMerge 노드를 Close 보다 좌측에 배치하도록 노드 순서 조정.

### M4. "release commit" 의 작성자/책임 주체 명시 누락

- **위치**: design.md §2.2 "버전 브랜치 → main 머지" 행 / §2.3 표 B 액션 4-5
- **결함**: design 은 main 직접 push 가 금지된다는 함의를 가지면서 release commit (merge commit) 자체는 누가 만드는지 명시하지 않음. main 으로 checkout 한 사람이 누구인지 (메인테이너 vs 에이전트 vs GitHub PR merge button) 가 불명.
- **권고**: §2.3 표 B 액션 4 에 다음 부연 추가.
  ```
  메인테이너가 본인 로컬에서 `git checkout main && git merge --no-ff v0.X.Y` 실행 후
  push. 에이전트가 사용자 승인 (`"release 진행해줘"`) 받은 후 동일 명령을 대신 실행할 수도 있음.
  GitHub PR 머지 button 사용 시 squash 옵션을 **선택하지 않도록** 주의 (--no-ff 가 깨짐).
  ```

### M5. annotated tag 메시지 컨벤션 누락

- **위치**: design.md §2.3 표 E §8 (tag 운영 의미 표)
- **결함**: 표는 `vX.Y.Z` 가 annotated 임을 명시하나 annotated tag 의 메시지 컨벤션이 없다. agent_dev_guide.md line 241 의 예시 `git tag -a v0.1.X+1 -m "v0.1.X+1 — <description>"` 가 있긴 하나 본 design 이 정본화하면서 가져오지 않음.
- **권고**: §2.3 표 E 의 tag 운영 의미 표 마지막에 부연 라인 추가.
  ```
  annotated tag message 컨벤션: `vX.Y.Z — <한 줄 요약>` (예: `v0.1.8 — branch strategy formalize + graphify env namespace`)
  ```

---

## L 항목 (Low — 참고)

### L1. design.md §1.4 ADR 미생성 결정의 정합성

- **위치**: design.md §1.4 + plan.md §5
- **참고**: design 은 "운영 절차 결정은 ADR 사안 아님" 이라 ADR 미생성. 그러나 docs/adr/0030-update-workflow-orchestration.md (`_resolve_ref` chain) 도 "운영 절차" 에 가까운데 ADR 로 발급됐다. ADR 발급 기준의 차이가 모호.
- **권고**: design.md §1.4 마지막에 부연 1줄 추가 — "ADR-0030 은 install.sh 의 ref 해석 *알고리즘 선택지* 가 정본 코드에 박혀 있어 ADR 화. 본 feature 는 정본 문서(CLAUDE.md/docs/) 자체가 결정의 정본이므로 ADR 중복."

### L2. plan.md §3 ASCII 다이어그램의 화살표 정렬

- **위치**: plan.md §3 (line 18-33)
- **참고**: ASCII art 의 화살표가 mermaid 와 정보가 중복. design.md §2.1 의 ASCII 와 plan.md §3 의 ASCII 가 약간 다른 양식. 한 쪽으로 통일 권고 (design.md §2.1 가 더 상세하므로 plan.md 는 mermaid 참조로 대체 가능).
- **권고**: 본 feature 의 종료 처리 시 plan.md ASCII 를 mermaid 1 줄 ("§2.1 참조") 로 축약.

### L3. `git branch -D feature/<id>` 의 unmerged warning 무시

- **위치**: design.md §2.2 "feature 브랜치 squash 후 처리" / §2.3 표 D
- **참고**: squash merge 는 git 내부적으로 feature 브랜치를 "머지된 것" 으로 인식하지 않는다 (3-way merge 가 아니라 새 commit 생성). 따라서 `git branch -d feature/<id>` (소문자 d) 는 unmerged 경고로 실패하고, 강제 삭제 `-D` (대문자) 만 동작. design 은 이를 정확히 명시했음.
- **권고**: §2.3 표 D 의 `git branch -D` 옆에 부연 1 줄 — "squash merge 는 git 내부적으로 merged 인식하지 않으므로 `-D` (강제) 필수." 운영자가 의구심 가지지 않게 한다.

### L4. README.md 의 "dev branch" 표현 — 본 design 의 "버전 브랜치" 와 통일 권고

- **위치**: README.md line 149 "v0.1.X+1 dev branch" / design.md §3 개정 범위 표 마지막 행
- **참고**: README.md 와 agent_dev_guide.md 에 "dev branch" 표현 4 회 잔존. design 의 정본 용어는 "버전 브랜치". 정합 권고.
- **권고**: design.md §5 DoD 의 "README.md 검증 채널 절의 'dev branch' 표현 → '버전 브랜치' 정합 (선택)" 의 "(선택)" 을 제거하고 필수로 격상. agent_dev_guide.md line 221, 226, 246 도 동일 정정 항목으로 추가.

### L5. canary tag 의 "버전 브랜치 HEAD" 표기와 README 표기의 충돌

- **위치**: design.md §2.3 표 E (canary 행: "버전 브랜치 HEAD") vs README line 145 (canary 행: "release 전 검증 trace commit")
- **참고**: design 의 정의가 더 엄격(버전 브랜치 HEAD = 모든 squash commit 이 canary 후보). README 는 "검증 trace" 라서 더 느슨. design 정의가 채택되면 README 도 정합 갱신 필요.
- **권고**: design.md §3 개정 범위 표 README.md 행을 "+0~3 / -0" 에서 "+3~5 / -3" 로 상향, 변경 성격 "canary 행 정의 + dev branch 용어 통일" 로 갱신.

---

## 통과 관점 (잘 된 부분)

1. **Q1~Q5 default 흡수와 §4 미결 사항 명시적 처리** — plan.md §6 의 5 미결을 design.md §2.2 결정 표로 정합하게 옮겼다. 미결 사항 "없음" 명시도 메소드론 §3 Step 2 필수 항목 준수.
2. **§1.2 결함 표(F1~F7) 와 §1.3 영향 파일 표의 cross-reference** — 결함 → 갱신 파일 → §2.3 Before/After 표가 일관되게 mapping 됨. F1 → §3 mermaid, F2 → §6 Worktree, F3 → §3 Step 5 식의 추적 가능성 우수.
3. **3 ref 동일 commit 원칙 (main HEAD = vX.Y.Z = latest)** — Q5 default 흡수가 깔끔. install.sh `_resolve_ref` chain (ADR-0030) 과 충돌 없이 작동.

---

## 범위 외 발견 (별도 feature 필요)

### R1. `deploy.sh` phantom 정정

CLAUDE.md §1 의 `deploy.sh` 언급은 phantom file. 본 design 의 M1 권고를 채택하면 부분 해결. 그러나 §1 "Development Zone (Root)" 의 file 목록 ("`features/`, `docs/`, `releases/`, `deploy.sh`") 자체가 현실(`releases/` 도 없음)과 다르므로 별도 cleanup feature 권고.

### R2. patch 자릿수(v0.1.X.Y) 도입

본 H5 권고 선택지 A 를 채택하지 않을 경우 별도 feature 로 분리. Q2 default 의 "별개 feature 로 결정 보류" 가 이미 plan.md 에 선언돼 있으나, F7 결함 표시는 본 feature 내 결함으로 표기됨 — 이 모순 해소를 위해 F7 을 R2 로 명시 이동.

### R3. agent_dev_guide.md §"Claude Code Agent tool 연동" 의 임시 worktree base 검증

H6 의 후속. Agent tool 의 `isolation: "worktree"` 동작이 실제로 어떤 base 에서 분기하는지 (cwd 의 HEAD? main?) 실증 검증 후 정본에 반영. 본 feature 범위 외.

---

*리뷰 격리 원칙 준수: 본 리뷰 작성 도중 design.md 자체에 어떠한 수정도 가하지 않음. 본 파일만 신규 생성.*
