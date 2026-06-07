# Code Review 1 — branch_strategy_formalize (DoD + 정본 정합)

작성일: 2026-05-25
리뷰어: claude (서브에이전트, general-purpose)
검토 대상: AGENTS.md / docs/agent_dev_guide.md / README.md / install.sh / features/backlog.md (5 파일, +158/-70)

---

## 종합 평가

**통과(조건부)** — DoD 16개 중 14개 충족. C 1건(README.md 의 phantom `deploy.sh` 잔존 — AGENTS.md §1 의 F9 정정과 모순), H 2건(agent_dev_guide.md 의 deploy.sh / Workflow 매핑 표 잔존 모순, install.sh 주석의 git 버전 진술 부정확), M 3건, L 3건. C/H 항목 정리 후 통과 권고.

---

## DoD 체크 (16개 항목 vs 실제 변경)

| # | DoD 항목 | 상태 | 근거 (파일:라인) |
|---|---|---|---|
| 1 | AGENTS.md §1 의 "deploy.sh" → "git workflow + install.sh" 갱신 (F9) | ✅ 충족 | AGENTS.md:11 (`features/, docs/, install.sh, scripts/`), AGENTS.md:13 (`git workflow + install.sh (§3 Step 5 참조)`) |
| 2 | AGENTS.md §3 mermaid 가 design §2.4 와 정합 | ✅ 충족 | AGENTS.md:40-65 — Release 분기 노드, MainMerge, squash 후 결함 점선 (`Deploy -.->|"squash 후 결함 발견"| NewF`) 포함 |
| 3 | AGENTS.md §3 Step 1 필수 항목에 "타겟 버전 브랜치" 추가 | ✅ 충족 | AGENTS.md:82 (`- [ ] **타겟 버전 브랜치** ... 사후 변경 시 plan.md ## v2 섹션`) |
| 4 | AGENTS.md §3 Step 5 본문에 §2.3-B 5 액션 git 명령 포함 | ✅ 충족 | AGENTS.md:173-181 — 5 액션 표, 명령 + 예외 처리 완비 |
| 5 | AGENTS.md §3 Feature 종료 처리에 브랜치/worktree 정리 단계 추가 | ✅ 충족 | AGENTS.md:221 (4번 항목 신설, `git branch --list 'feature/<id>'` + `git worktree list` 점검) |
| 6 | AGENTS.md §3 본문에 "main 직접 commit 금지" 규칙 명시 (R1-H4) | ✅ 충족 | AGENTS.md:120 (Step 3, `main 직접 분기·commit 금지`), AGENTS.md:180 (액션 4 예외 처리: `**main 직접 commit 금지** — merge --no-ff 와 annotated tag add 만 허용`) |
| 7 | AGENTS.md §3 본문에 hotfix 흐름 1 단락 (R1-H5) | ✅ 충족 | AGENTS.md:192 (`**hotfix 흐름**: production critical bug → 현 minor 의 버전 브랜치에서 hotfix feature ... patch 자릿수 도입(v0.X.Y.Z) 은 별도 결정 사항`) |
| 8 | AGENTS.md §6 분기 base = `origin/v0.X.Y` 명시 + Agent tool 임시 worktree 구분 | ✅ 충족 | AGENTS.md:276 (`origin/v0.X.Y ... main 직접 분기 금지`), AGENTS.md:283 (worktree add 예), AGENTS.md:291 (Agent tool 임시 worktree 규칙 외 명시) |
| 9 | AGENTS.md §8 에 tag 운영 의미 표 (§2.3-E) 신설 | ✅ 충족 | AGENTS.md:347-355 — `### Tag 운영 의미` 절 + 표 + Release 직후 ref 상태 부연 |
| 10 | docs/agent_dev_guide.md 동일 갱신 (AGENTS.md 와 정합) | ⚠️ 부분 충족 | mermaid·Step 1·Step 5 5 액션·종료 처리는 갱신됨 (agent_dev_guide.md:37-62, 88, 209-219, 282-293). **그러나 §"Workflow 단계별 매핑" 표 (line 423) 와 §"Worktree 사용 시" (line 501) 에 `deploy.sh` 표현 잔존** — H1 참조 |
| 11 | README.md 검증 채널 절 — `install.sh --branch canary` 표준 호출형 명시 | ✅ 충족 | README.md:134 (`bash -s -- --branch canary`), README.md:150 (`--branch canary` (표준 호출형 — `--version canary` 금지)) |
| 12 | install.sh:1462 fetch 에 `--force` 추가 (F8 backing fix) | ✅ 충족 | install.sh:1463 (`git -C "$WIKIHUB_SRC" fetch origin --tags --force`) + 주석 (1462) |
| 13 | features/backlog.md BL-1~BL-4 등록 | ✅ 충족 | backlog.md:172-181 (`## branch_strategy_formalize 산출` 절 + BL-1~BL-4 표) |
| 14 | ADR 미생성 | ✅ 충족 | design §1.4 결정. 실제로 ADR-NNNN 미신설 |
| 15 | HISTORY.md 미변경 (Step 5 생략) | ✅ 충족 | features/HISTORY.md 변경 없음 (git status 확인) |
| 16 | Step 4 멀티 리뷰어 통과 | 🔄 진행 중 | 본 code_review_1.md 가 첫 번째 리뷰어 산출물 |
| 17 (추가) | Feature 종료 시 archive 이동 + 브랜치/worktree 정리 | ⏳ 미수행 | Step 5 종료 후 수행 예정 |
| 18 (추가) | v0.1.8 squash merge | ⏳ 미수행 | Step 5 액션 1 에서 수행 예정 |

**충족률**: 14/16 (DoD 본문) + 2 운영 후행 = **명백한 결함 1 (DoD #10 부분 충족)**.

---

## C 항목 (Critical)

### C1. README.md §"디렉토리 구조" 의 `deploy.sh` 잔존 — AGENTS.md §1 의 F9 정정과 모순

- **위치**: README.md:216, README.md:218
- **결함**:
  ```
  ├── _system/                   # 정본 룰 + 명령어 플레이북 (deploy.sh로만 주입)
  ├── scripts/                   # gdrive-sync.py, watcher 등 인프라
  ├── deploy.sh                  # systemd 배포
  ```
  본 feature 의 F9 (design §1.2/§1.5) 는 "**`deploy.sh` 는 phantom file — 실제로는 존재하지 않거나 ad-hoc**" 이라고 진단. AGENTS.md:13 에서 "git workflow + install.sh 를 통해서만 주입" 으로 정정했다. 그러나 README.md §"디렉토리 구조" 의 "향후 추가될 디렉토리" 블록에 `deploy.sh` 가 **새로 들어올 자산** 으로 표기됨 → 메인테이너/외부 독자가 정본의 두 위치에서 모순된 신호 수신.
  - 추가로 README.md:216 의 주석 `(deploy.sh로만 주입)` 도 직접 모순.
- **권고**:
  1. README.md:216 의 주석을 `(git workflow + install.sh 로 주입 — AGENTS.md §3 Step 5)` 로 정정.
  2. README.md:218 의 `deploy.sh` 라인 자체를 삭제. 대신 `install.sh` 또는 `# (git workflow 가 systemd 배포 역할)` 로 대체.
  3. design §1.3 의 영향 파일 표에 README.md §"디렉토리 구조" 가 누락됨 — 본 feature 범위 확장 필요(또는 별도 cleanup feature 로 이관).

---

## H 항목 (High)

### H1. docs/agent_dev_guide.md §"Workflow 단계별 매핑" 표 (line 423) 의 `deploy.sh` 잔존

- **위치**: docs/agent_dev_guide.md:419-423
- **결함**:
  ```markdown
  ### Workflow 단계별 매핑

  | 단계 | Worktree | 목적 |
  |---|---|---|
  | Implementation | feature worktree | 격리된 환경에서 개발 |
  | Review | main worktree | main 기준 diff로 변경사항 검토 |
  | Deployment | main worktree | merge 후 deploy.sh 실행 |
  ```
  본 feature 의 Step 5 갱신 (§2.3-B 5 액션) 는 `deploy.sh` 호출이 없다 — squash / canary tag / branch -D / main merge / version tag. 위 표의 `Deployment | main worktree | merge 후 deploy.sh 실행` 행은 본 갱신과 직접 모순. line 195 (`도구: git + install.sh (배포는 git workflow 로 수행, deploy 스크립트 없음)`) 와도 모순.
- **권고**: line 423 의 `목적` 칸을 `git workflow (squash → 버전 브랜치 → merge --no-ff → main 의 5 액션)` 로 정정. (DoD #10 의 정합 누락 해소.)

### H2. docs/agent_dev_guide.md:501 "Worktree 사용 시" 부연 라인의 `deploy.sh` 잔존

- **위치**: docs/agent_dev_guide.md:501
- **결함**:
  ```markdown
  **Worktree 사용 시**: Step 3~4는 feature 브랜치 worktree에서 진행하고, Step 5에서 main으로 머지한다.
  ```
  표현 자체는 acceptable 하나, 본 design 의 핵심 (Step 5 = squash → **버전 브랜치**, main merge 는 release 시점) 와 어긋남. "Step 5 에서 main 으로 머지" 가 매 feature 동작인 것처럼 읽힘. 또한 같은 §"Feature 디렉토리 및 결정 기록" 절(line 464-507) 이 본 feature 범위에서 미갱신.
- **권고**: line 501 을 "Step 3~4 는 feature 브랜치 worktree, Step 5 에서 버전 브랜치(`v0.X.Y`)로 squash merge → release 시점에 main 으로 `merge --no-ff`" 로 정정.

### H3. install.sh:1462 주석의 "git 2.20+ requirement" 진술 부정확

- **위치**: install.sh:1462
- **결함**:
  ```bash
  # branch_strategy_formalize (F8): canary lightweight tag force-update 수신 필수 → --force 추가 (git 2.20+ requirement)
  ```
  `--force` 옵션은 **git 2.20+ 의 변경된 동작에 대응** 하기 위해 필요 (이전엔 fetch 가 자동으로 force-update). 표현 "git 2.20+ requirement" 는 "git 2.20 이상에서 요구된다" 로 읽혀, 마치 git 2.19 에선 필요 없는 옵션처럼 모호. design.md §2.3-E (line 178) 의 표현 "fetch 시 `--force` 필요 (git 2.20+)" 가 본 주석보다 명료.
- **권고**: 주석을 다음으로 정정.
  ```bash
  # branch_strategy_formalize (F8): canary lightweight tag force-update 수신 — git 2.20+ 부터
  # fetch 시 --force/+refspec 없으면 'would clobber existing tag' 로 거부 → --force 의무
  ```
  또는 design.md §2.3-E 표현 그대로 차용.

---

## M 항목 (Medium)

### M1. AGENTS.md:178 액션 2 의 `git push v0.X.Y --force-with-lease` 가 design 표와 미세 불일치

- **위치**: AGENTS.md:178, docs/agent_dev_guide.md:214
- **결함**: design.md §2.3-B 액션 2 표는 `git tag -f canary && git push origin canary --force` 만 명시. 두 정본 (AGENTS.md, agent_dev_guide.md) 에서는 v0.X.Y 버전 브랜치도 `--force-with-lease` 로 push 하는 명령이 추가됨. 추가 자체는 design review 2 M3 (`--force-with-lease` race-safe 권고) 흡수의 결과로 보이나, design.md 본문엔 해당 액션이 명시되지 않아 cross-reference 가 깨짐.
  - 추가로 버전 브랜치는 본 design 에서 "append-only via squash" (R2-H3) 라 `--force-with-lease` 자체가 불필요해 보임. 본 push 의 의도가 squash commit 을 origin 으로 publish 하는 routine push 라면 `--force-with-lease` 가 아니라 일반 `git push origin v0.X.Y` 로 충분. 의도가 모호.
- **권고**:
  - **옵션 A**: design.md §2.3-B 표 액션 2 를 갱신해 `git push origin v0.X.Y` (forced 아님) + `git push origin canary --force` 로 분리. AGENTS.md:178 의 `--force-with-lease` 도 동일하게 정정.
  - **옵션 B**: 액션 2 의 `--force-with-lease` 가 의도된 안전장치라면 design.md §2.3-B 표에 행을 추가하고 "버전 브랜치는 history-rewriting 불가가 정본 invariant이지만 메인테이너 mistake 차단 차원에서 lease push" 식의 부연 추가.

### M2. AGENTS.md:178 액션 2 명령에서 `git tag -f canary` 가 인자 없음 (HEAD 암묵 사용)

- **위치**: AGENTS.md:178, docs/agent_dev_guide.md:214, 256
- **결함**:
  ```
  git tag -f canary && git push origin canary --force
  ```
  `git tag -f canary` 는 `HEAD` 를 가리킨다. squash merge 직후 메인테이너의 cwd 가 `v0.X.Y` 브랜치라면 의도된 commit 을 가리키나, 만약 다른 브랜치에서 명령 실행 시 잘못된 commit 을 canary 로 force-update. design.md §2.2 표 ("canary tag 갱신": `git tag -f canary <sha>`) 와 §2.3-B 표 액션 2 ("canary tag force-update + push": `git tag -f canary <sha> && git push origin canary --force`) 모두 `<sha>` 인자를 받는 형태로 명시됨 — 본 갱신에서 인자 없는 형태로 축약됨.
- **권고**: 명령을 다음으로 명시:
  ```
  git tag -f canary <v0.X.Y_HEAD_sha> && git push origin canary --force
  ```
  또는 사전 조건 명시: "메인테이너는 액션 1 직후 `git checkout v0.X.Y` 상태에서 실행 — `git tag -f canary` 가 HEAD 를 가리키게."

### M3. README.md §"개발 방법론" 의 mermaid (line 173-183) 가 본 feature 의 mermaid 와 정합 안 됨

- **위치**: README.md:173-183
- **결함**:
  ```
  flowchart TD
      Plan["Step 1: Plan"]
      ...
      Plan --> AD --> Impl --> Review --> Deploy --> Archive
  ```
  본 feature 의 AGENTS.md mermaid (line 40-65) / agent_dev_guide.md mermaid (line 37-62) 는 모두 (a) Step 1 에 "타겟 버전 브랜치 결정", (b) Release 분기 노드, (c) squash 후 결함 점선이 명시. README.md 의 단순 직선 흐름 mermaid 는 본 갱신과 정합 안 함. README 는 요약이라는 점은 acceptable 하지만, 본 feature 의 핵심 메시지(release batch 분기)가 누락됐다는 점은 weak.
- **권고**: README.md mermaid 에 최소한 `Deploy --> Release{batch?}` 분기 1줄 추가 또는 본문 line 171 ("WikiHub는 5단계 Feature-based Workflow를 따릅니다") 다음에 "자세한 브랜치 토폴로지(main → 버전 브랜치 → feature/<id>) 는 AGENTS.md §3 mermaid 참조" 1줄 추가.

---

## L 항목 (Low)

### L1. AGENTS.md:11 `Development Zone (Root)` 의 파일 목록 변경에서 `releases/` 삭제 — 의도된 cleanup 인지 불명

- **위치**: AGENTS.md:11
- **결함**: Before: `features/, docs/, releases/, deploy.sh 및 이 가이드`. After: `features/, docs/, install.sh, scripts/ 및 이 가이드`. `releases/` 삭제는 design.md 에 명시 없음. 본 feature 의 phantom file 처리 의도와 일관됨(설계 리뷰 1 의 R1 — `releases/` 도 phantom)이지만, surgical change 차원에서 사전 명시 누락. 결과적으로는 정확한 변경이라 통과.
- **권고**: design review 1 R1 (phantom files cleanup) 이 본 feature 범위 외라 했으나, 본 변경은 사실상 그 일부를 흡수함. design.md §1.3 영향 파일 표 또는 §3 개정 범위 표에 이 라인을 명시화하면 traceability 우수.

### L2. AGENTS.md:194 "수행 시 산출물: HISTORY.md — release(액션 4~5) 시점에 한 번 append" — 기존 의미 변경 명시 없음

- **위치**: AGENTS.md:194, docs/agent_dev_guide.md:197
- **결함**: 본 갱신 이전 HISTORY.md 는 "매 feature 마다 append" 의미였다 (CLAUDE.md 원본의 Step 5 "수행 후 에이전트가 자동으로 항목 append"). 본 갱신은 "release 시점에만 1 회" 로 의미 reshape — 매 feature → release 시점. 의미 변경 자체는 자연스럽지만, design.md §2.3-B 본문에 명시되지 않아 reviewer 가 의도 추론에 의존. **단**, design.md §6 DoD line 284 의 "HISTORY.md 미변경 (Step 5 생략 결정 per plan.md)" 와 정합하므로 결함 아님.
- **권고**: design.md 다음 갱신 또는 후속 feature 에서 "HISTORY.md = release 단위 (매 feature 아님)" 를 명시. 본 feature 의 범위 내에선 acceptable.

### L3. agent_dev_guide.md:31 의 Karpathy 4원칙 인용은 새로 추가됐는데 design.md 에 명시 없음

- **위치**: docs/agent_dev_guide.md:31
- **결함**:
  ```markdown
  - **코딩 행동 원칙**: 구현 시 [Karpathy Guidelines](karpathy-guidelines.md) 4원칙(...).
    메소드론과의 매핑은 `AGENTS.md §2` 참조.
  ```
  본 추가는 design.md §1.3 영향 파일 표나 §3 개정 범위 표에 명시되지 않음. AGENTS.md §2 와의 cross-reference 라는 점에서 가치 있으나, design.md 범위 밖 변경 (Karpathy 원칙 §3 — Surgical Changes 위반 가능성). 단, 이미 add 된 상태이며 의미 정합 → 통과.
- **권고**: 본 feature 종료 후 design.md 또는 차기 feature 에서 traceability 보강.

---

## 통과 관점 (잘 된 부분)

1. **mermaid 다이어그램 두 정본 (AGENTS.md, agent_dev_guide.md) 의 동일성** — Plan 노드의 `타겟 버전 브랜치 결정` 부연, Impl 노드의 `feature/<id> on v0.X.Y` 부연, Release 분기, MainMerge 노드, squash 후 결함 점선까지 라벨 단위로 일치 (AGENTS.md:40-65 vs agent_dev_guide.md:37-62). 정본 간 동기화 우수.

2. **Step 5 5 액션 표의 격상** — design §2.3-B 의 5 액션 + 예외 처리 형식이 AGENTS.md:173-181, agent_dev_guide.md:209-219 양쪽에 동일하게 반영됨. 핵심 명령 (`git checkout v0.X.Y && git merge --squash`, `git tag -f canary`, `git worktree remove`, `git merge --no-ff`, `git tag -a v0.X.Y`) 이 코드 블록으로 명시.

3. **`install.sh:1463` 의 `--force` 추가의 surgical 성** — 한 줄 변경 + 명확한 주석 + branch_strategy_formalize feature_id reference. Karpathy §3 (Surgical Changes) 준수. annotated tag immutable invariant 와 충돌 0 (annotated tag 는 force-update 자체가 git 거부).

4. **AGENTS.md §3 Feature 종료 처리 4번 항목 신설** — `git branch --list 'feature/<id>'` + `git worktree list` 의 검증 명령이 명시. design §2.3-C 의 "Step 5 액션 (3) 에서 이미 정리됐어야 함" 정신을 그대로 구현.

5. **README.md:140-152 의 tag 운영 표가 AGENTS.md:347-355 의 표와 정합** — 의미적 동일성 (annotated/lightweight, force-move 여부, 운영 의미) 유지. Cross-document drift 없음.

6. **backlog.md `branch_strategy_formalize 산출` 절 신설** — BL-1~BL-4 이 design §4 의 4 항목을 그대로 가져옴. 우선순위 라벨 부여까지 추가됨 — design 보다 풍부.

---

## 범위 외 발견

### R1. README.md "디렉토리 구조" 의 `deploy.sh` + 주석 — 본 feature 의 핵심 phantom 정정이 README 까지 침투해야 했음 (C1)

C1 권고 참조. 본 feature 범위에 흡수해 정리 권고. 또는 별도 micro feature.

### R2. docs/agent_dev_guide.md §"Feature 디렉토리 및 결정 기록" (line 464-507) 의 갱신 누락

본 feature 의 design §1.3 영향 파일 표는 `docs/agent_dev_guide.md` 행에 라인 35-273, 366-419 만 명시. 그러나 §"Feature 디렉토리 및 결정 기록" (line 464-507) 은 미갱신 — "Worktree 사용 시" (line 501) 의 `deploy.sh` 표현(=H2)이 잔존하는 직접 원인. design.md 범위 정의의 약점.

### R3. AGENTS.md:11 의 `releases/` 삭제 — design review 1 의 R1 (phantom files 별도 cleanup feature) 영역 일부 흡수

이미 흡수된 상태이므로 별도 feature 불필요. backlog.md 의 BL-5 등으로 추가 등록할 수도 있음(`deploy.sh` 의 README 잔존 + `_system/wikihub.yaml.example` 등 향후 추가 자산 검증).

### R4. install.sh 의 `--tags --force` 가 다른 곳에서도 필요한지 검증 누락

`install.sh` 의 다른 `git fetch` 호출 (fresh clone path, rollback path) 도 lightweight tag force-update 케이스를 다룬다면 동일 보강 필요. 본 feature 의 surgical change 차원에서는 line 1463 한 곳만 fix 했으나, 운영자가 fresh install 후 canary 검증 사이클을 돌리는 케이스에서 보강 누락 여부 검증 필요.

---

## 결론

DoD 16개 중 14개 충족 (#10 부분 충족, #16/추가는 후행). 핵심 mermaid·Step 5 5 액션·tag 운영 표·Feature 종료 처리·install.sh fetch fix 모두 design v2 와 정합. 그러나 phantom `deploy.sh` 정정이 README.md (C1) 와 agent_dev_guide.md (H1, H2) 까지 침투하지 못함 — 본 feature 의 F9 정정 의도가 부분만 실현. C1 + H1 + H2 정리 후 통과.

총 결함: C 1건, H 3건, M 3건, L 3건 = 10건. 모두 본 feature 범위 내 fix 가능 (50줄 미만, 모두 문서 변경).

*리뷰 격리 원칙 준수: 본 리뷰 작성 도중 검토 대상 파일에 어떠한 수정도 가하지 않음. 본 파일만 신규 생성.*
