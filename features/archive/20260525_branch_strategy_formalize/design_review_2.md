# Design Review 2 — branch_strategy_formalize (브랜치 토폴로지 + git 액션)

작성일: 2026-05-25
리뷰어: claude (서브에이전트, Plan, 독립 리뷰)

---

## 종합 평가

**통과(조건부)** — 토폴로지 설계와 핵심 규칙은 일관되며 의도된 흐름이 명확하다. 그러나 **canary tag 의 lightweight + force-update 운용**과 **운영자측(OCI) install.sh 의 `git fetch origin --tags` (force 없음)** 사이의 결합이 빠져 있어, 그대로 정본에 반영되면 v0.1.8 첫 운용에서 OCI 가 stale canary 를 잡는 사고가 발생할 가능성이 있다. C1, C2 해결 후 통과.

---

## C 항목 (Critical — 미해결 시 진행 불가)

### C1. `git fetch origin --tags` 는 force-updated lightweight tag 를 자동 갱신하지 않음 (git 2.20+)

- **위치**: design.md §2.2 "canary tag 갱신" 행 + §2.3-B "(2) canary tag force-update + push" 액션. 그리고 운영자 측 install.sh `_step2_update` (`install.sh:1462`).
- **결함**:
  - `git fetch` man page (git 2.54): "Since Git version 2.20, fetching to update refs/tags/* works the same way as when pushing. I.e. any updates will be rejected without `+` in the refspec (or `--force`)."
  - `install.sh:1462` 의 호출은 `git -C "$WIKIHUB_SRC" fetch origin --tags` — `--force` 없음. maintainer 가 `git tag -f canary <new-sha> && git push origin canary --force` 로 갱신해도, OCI 측은 fetch 시 *"would clobber existing tag"* 경고와 함께 **로컬 `canary` tag 를 갱신하지 않은 채** path 2 로 들어가 `origin/canary` 로 reset 한다. 다음 두 조건에서 문제:
    1. fresh clone path 에서 force-update 된 후의 fresh clone 은 **tag 가 detached HEAD** 로 들어가 sparse-checkout 동작에 분기.
    2. update mode 에서 `_resolve_ref` path 2 가 `origin/canary` 반환 — branch 로 취급. 그러나 canary 는 정본상 tag → **tag 와 branch 의미 충돌** 잠재.
- **권고**:
  1. design.md §2.3-B (2) 의 액션에 **fetch 측 force 옵션 의무** 명시. 운영자 호출 흐름을 정본에 적어두려면:
     - install.sh `_step2_update` 의 fetch 를 `git fetch origin --tags --force` 또는 `git fetch origin '+refs/tags/*:refs/tags/*'` 로 보강 (별도 feature 또는 본 feature 의 범위 확장).
  2. design.md §8 tag 운영 의미 표 행 `canary` 에 *"fetch 시 `--force` 필요"* 주석 명기.

### C2. `_resolve_ref` 의 canary 경로 검증 누락 (install.sh 정합성 미보장)

- **위치**: design.md §2.5 "ADR-0030 (`_resolve_ref` chain)" 행.
- **결함**: `install.sh:1351-1407` 의 `_resolve_ref`:
  - path 2: `--branch <ref>` → `origin/<ref>` 또는 입력 그대로 반환
  
  canary 는 path 2 에 의존. 호출형이 `--version canary` 와 `--branch canary` 중 어느 쪽인지 design.md 미명시.
- **권고**: §2.5 에 "canary 운영자 호출형 = `install.sh --branch canary`" 표준화. §2.3-E 표에 행 추가.

---

## H 항목 (High — 강력 권고)

### H1. `git worktree remove` 의 dirty 상태 처리 미명시

- **위치**: design.md §2.3-D 제거 시점 행.
- **결함**: `git worktree remove` 는 clean worktree 만 제거 가능. dirty 시 `--force` 필요. 5 액션 중 (3) 이 fail 하면 (1)(2) 끝났는데 (4) 진입 못 함 — partial state.
- **권고**: §2.3-D 명령을 보강:
  ```bash
  git -C ../wikihub-feat/<id> status --porcelain | grep -q . && {
      echo "dirty worktree — clean first"; exit 1
  }
  git worktree remove ../wikihub-feat/<id>
  ```

### H2. squash merge 후 conflict 처리 절차 미정의

- **위치**: design.md §2.3-B 5 액션.
- **결함**: 액션 (1)/(4) 모두 conflict 발생 가능. 회복 절차 없음.
- **권고**: §2.3-B 표에 "예외 처리" 행:
  - 액션 (1) conflict → 해결 후 `git commit -m "..."` 또는 `git reset --hard HEAD` 회복.
  - 액션 (4) conflict → 해결 후 commit. PR 사용 여부 명시 필요.

### H3. `merge --no-ff` 후 "3 ref 동일 commit" 명제 + 버전 브랜치 release 후 처리

- **위치**: design.md §2.1 ASCII, §2.4 mermaid, §4 Q5.
- **검증**:
  - `git merge --no-ff` 가 새 merge commit M 생성 → `main HEAD == refs/tags/v0.X.Y == refs/tags/latest == M`. **명제 성립**.
  - 그러나 `refs/heads/v0.X.Y` 는 여전히 M.parents[1] = release 직전 commit. design.md 의 "3 ref" 표현은 정확.
  - 버전 브랜치 release 후 보존 여부 미명시.
- **권고**: §2.2 또는 §2.3-B 표에 행 추가 — "release 후 버전 브랜치 처리":
  - hotfix base 후보로 **보존** (Q2 default 와 정합).

### H4. canary tag 와 release tag 의 일시 공존

- **검증**: release flow 직후 canary 는 v0.X.Y_HEAD (M 부모), v0.X.Y annotated tag 는 M → 서로 다른 commit. OCI 가 `--branch canary` 로 install 하면 release commit 이 아닌 직전 candidate 받음.
- **권고**: §2.3 또는 §2.4 에 "release 시점 canary 처리" 명시. 옵션:
  - (a) main merge 직후 canary tag 를 M 으로 force-update (canary == latest 일시 동일).
  - (b) canary tag delete.
  - (c) 그대로 유지.

---

## M 항목 (Medium — 권고)

### M1. `--no-commit` 잉여 표기

- `--squash` 가 이미 implicit no-commit. design.md 의 선택은 정확하나 미래 메인테이너 질문 차단 위해 footnote 권고.

### M2. GitHub protected tag 충돌 가능성

- repo 의 Tag protection rules 가 `v*` 또는 `*` 패턴이면 force-push 거부. canary 는 protect 금지 명시 필요.

### M3. `--force-with-lease` 옵션 미언급

- 단일 maintainer 모델이면 `--force` 무방하나, `--force-with-lease` 가 race-safe.
- annotated v0.X.Y tag 는 force 금지 (immutable). design.md §2.3-B (5) 가 모호.

### M4. `-D` vs `-d` 의 정당성

- squash merge 는 git fully-merged 인식 안 함 → `-D` 가 정답. footnote 권고.

### M5. feature 브랜치 분기 syntax — `v0.X.Y` local vs remote

- `git worktree add ../wikihub-feat/... -b feature/[id] v0.X.Y` — local v0.X.Y 가 없으면 fail.
- 권고:
  ```bash
  git fetch origin
  git worktree add ../wikihub-feat/[date]_[id] -b feature/[id] origin/v0.X.Y
  ```

---

## L 항목 (Low — 참고)

### L1. ASCII §2.1 의 "OCI 검증 batch" 라벨 모호 — "OCI 검증 (continuous on canary update)" 권고.
### L2. annotated vs lightweight 기술적 정의 본문 없음 — 명령 예시 블록 추가 권고.
### L3. §2.4 mermaid 와 §2.1 ASCII 일관성.
### L4. `--version canary` 도 lightweight tag 통과하나 의미 충돌 — `--branch canary` 표준화.
### L5. 5 액션 누락 방지 helper script (promote_canary.sh 등) backlog 등록 권고.

---

## 통과 관점

1. feature 분기 base 의 명시화 — F2 결함 직접 차단 + hotfix 통일.
2. `git branch -D` 채택 정확.
3. tag 운영 의미 표 — ADR-0010(latest tag) 과 의 분리 거버넌스 깔끔.
4. mermaid §2.4 의 release 분기점 — "중간 feature" vs "버전 batch 완료" 두 경로 한 그림 표현.

---

## 범위 외 발견 (별도 feature 필요)

1. install.sh `_step2_update` 의 fetch 보강 (C1 backing fix) — 본 feature 또는 별도.
2. canary/release tag 의 GitHub Tag protection 정책 (M2).
3. promote_canary.sh / release.sh 헬퍼 (L5).
4. patch 자릿수 도입 (plan.md Q2 default 보류).
5. squash commit 다중 feat_id naming (Q3 edge case).

---

## 결론

토폴로지 + squash/merge --no-ff/tag 라이프사이클 결정은 일관. 그러나 **canary lightweight tag force-update + 운영자측 install.sh fetch force 없음** 결합 결함(C1, C2) 차단 필요. C1/C2 를 §2.3-E 또는 §2.5 에 명시 + install.sh 보강을 본 feature 범위에 포함 (또는 별도 feature 트래킹) 후 본 feature 진행 권고.
