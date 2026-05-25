# Code Review 2 — branch_strategy_formalize (실제 적용 가능성 + 운영 안전성)

작성일: 2026-05-25
리뷰어: claude (서브에이전트, Plan)
검토 대상: HEAD vs working tree diff (+158/-70 across 5 files)

---

## 종합 평가

**통과(조건부)** — 5 액션 표는 메인테이너가 따라갈 수 있을 만큼 구체화되었고 install.sh:1462 의 `--force` 보강은 F8 backing fix 로 정확히 작동한다. H1/H2 보강 후 통과 권고.

---

## H 항목 (High — 강력 권고)

### H1. AGENTS.md vs agent_dev_guide.md 의 액션 (2) 명령 표기 불일치 — 정본 정합성

- **AGENTS.md:178** (액션 2): `git tag -f canary && git push origin v0.X.Y --force-with-lease && git push origin canary --force`
- **agent_dev_guide.md:214** (액션 2): `git push origin v0.X.Y --force-with-lease`<br/>`git tag -f canary && git push origin canary --force`
- **결함**:
  1. 명령 순서 차이 (AGENTS.md 는 tag 먼저, guide 는 push 먼저). 두 정본의 동기화 어긋남.
  2. AGENTS.md 의 `&&` 3-chain — 중간 push 실패 시 local 과 remote silently divergent.
- **권고**: 정합한 순서로 통일:
  ```
  git push origin v0.X.Y --force-with-lease   # 1. 브랜치 push (lease-protected)
  git tag -f canary                            # 2. local tag move
  git push origin canary --force               # 3. tag push (force)
  ```
  세 줄로 분리.

### H2. clean check 의 fragile `exit 1` — 인터랙티브 shell 종료 위험

- **위치**: AGENTS.md:179 + agent_dev_guide.md:215, §6 worktree (AGENTS.md:286 등):
  ```
  git -C ../wikihub-feat/<id> status --porcelain | grep -q . && { echo "dirty"; exit 1; }
  ```
- **결함**: 메인테이너가 인터랙티브 shell 에서 복사-붙여넣기 하면 `exit 1` 가 현재 터미널 종료. `.DS_Store`, `*.swp` 등 임시 파일도 dirty 로 판정되어 worktree remove 자체가 막힘 — script vs interactive 동작 차이.
- **권고**: `git worktree remove` 자체가 dirty 시 거부하므로 grep check 잉여. 단순화:
  ```bash
  git -C ../wikihub-feat/<id> status --porcelain  # 사람이 출력 확인
  git worktree remove ../wikihub-feat/<id>        # dirty 시 git 이 자동 차단
  git branch -D feature/<id>
  ```

---

## M 항목 (Medium — 권고)

### M1. `_resolve_ref` path 2 의 canary tag 해석 — V 검증 DoD 누락

- **위치**: install.sh:1351-1407 의 `_resolve_ref`
- **검증**:
  - `--branch canary` → path 2 → `origin/canary` 출력 → `git reset --hard origin/canary` 호출
  - canary 는 tag (lightweight), `refs/remotes/origin/canary` 부재 — git 의 dwim 으로 `refs/tags/canary` 로 fallback 되는지 별도 검증 필요
- **권고**: analysis_and_design.md DoD 에 V 항목 추가:
  > [ ] OCI test 환경에서 `install.sh --update --branch canary` 실행 → `_resolve_ref` 가 canary tag 정확히 식별 → `git reset --hard` 성공 검증

### M2. AGENTS.md §6 의 `git fetch origin` 선행 — "필수" 명시 권고

- 메인테이너가 fetch 안 한 상태에서 `origin/v0.X.Y` 는 stale → 다른 feature squash 와 base 부정합. 코멘트 1 줄 보강.

### M3. 액션 (4) main checkout 의 dirty working tree 처리 미명시

- `git checkout main` 은 dirty 시 막힘. 예외 처리 칸에 1 줄 추가 권고.

### M4. README.md "§3 Step 5 액션 2" 참조 모호 — "AGENTS.md §3 의 Step 5 액션 (2)" 가 더 명확

### M5. install.sh:1462 의 `--force` 부작용 — 통과

- annotated tag 영향 없음, lightweight tag 만 force-update 수신. F8 fix 정합.

---

## L 항목 (Low — 참고)

### L1. agent_dev_guide.md:423 의 "Workflow 단계별 매핑" 표 — `deploy.sh` 잔존

- 본 PR 의 F9 정정에서 누락된 1 행.
- "merge 후 deploy.sh 실행" → "5 액션 git workflow 실행 (위 §Step 5 참조)".

### L2. AGENTS.md:178 의 "canary 는 protect 금지" footnote — BL-2 와 정합

### L3. AGENTS.md:188-190 의 release 후 ref 상태 + canary rollback — meta-consistency 통과

### L4. README.md `--update --branch canary` 호출 표기 정합

### L5. install.sh:1462 코멘트 패턴 — 기존 ADR cross-reference 와 정합

---

## 통과 관점 (잘 된 부분)

1. **install.sh:1462 의 `--tags --force` 보강** — git 2.20+ 의 force-updated lightweight tag 수신 요구사항을 정확히 다룸. annotated tag 영향 0.
2. **AGENTS.md §3 Step 5 5 액션 표** — 명령 + 예외 처리 + (1)~(3) vs (4)~(5) 분리.
3. **mermaid `Deploy -.->|"squash 후 결함 발견"| NewF` 점선** — R1-C1 정확 흡수.
4. **AGENTS.md §6 worktree base = `origin/v0.X.Y`** — design.md §2.3-D 명령 syntax 정확.
5. **Tag 운영 의미 표** — annotated/lightweight/force-update 성격 차이 + fetch 시 force 필요 주석.
6. **feature 종료 처리 §4 — 브랜치/worktree 정리 확인 단계 신설**.
7. **backlog 등록 BL-1~BL-4** — 범위 외 결정 명시적 분리.

---

## 범위 외 발견 (별도 feature 필요)

### O1. install.sh `_resolve_ref` path 2 의 canary tag 해석 V 검증 — OCI test 환경 필요

### O2. AGENTS.md vs agent_dev_guide.md 정본 분리 모델 재검토 — 중복 표 → 참조 축약

### O3. `git push --force-with-lease` 의 첫 push (lease 부재 시) 동작 — 사실상 `--force` 와 동등, race-safe 미보장

### O4. AGENTS.md §3 의 hotfix 흐름 단락 — production OCI 사고 시 patch 자릿수 미도입 상태에서 실제 행동 불가

---

## 메소드론 자기-적용성 검증

본 PR 자체는 새 메소드론을 따르지 않고 v0.1.8 브랜치에 직접 modify — 메소드론 정립 이전 흐름 (현행 v0.1.x 실태와 일치). squash 시점에 새 메소드론 흡수.

**권고**: plan.md 의 "## v2" 섹션에 "본 PR 은 메소드론 정립 자체이므로 정립 이전 흐름으로 진행, squash 시점에 새 메소드론 흡수" 명시.

---

## 결론

핵심 메시지 (메소드론 갱신 + F8 backing fix) 일관되게 표현. (H1) 정본 동기화, (H2) clean check fragile 처리 보강 + (M1) DoD V 항목 추가 후 통과.
