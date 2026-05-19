# /wh-lint

wiki 일관성·구조 점검과 비파괴 자동 정비를 수행한다. 본 명령은 self-maintaining wiki의 핵심 — 사용자 개입 없이 위키 위생을 유지한다.

## 호출

```
<agent_invocation> "/wh-lint"            # 기본 모드: 비파괴 작업만 (timer 자동 호출)
<agent_invocation> "/wh-lint --apply"    # 파괴 가능 작업까지 수행 (메인테이너 수동 호출)
```

- **트리거 (기본)**: systemd timer (하루 1회 권장, `wikihub.yaml.operations.lint_interval_hours`)
- **트리거 (`--apply`)**: 메인테이너가 `wiki/_lint/report.md` read 후 의도적 수동 호출
- **vault 무관 (wiki-wide)**: 단일 명령으로 전체 wiki 점검

## 사전 조건

- `wikihub.yaml` 존재
- wiki/ 디렉토리 + 4 카테고리(`sources/`, `entities/`, `concepts/`, `analyses/`) + `_lint/` 존재 (없으면 생성 — 본 명령이 자동)
- (선택) `graphify-out/graph.json` — 있으면 그래프 기반 점검, 없으면 wiki 순회

## 절차

### Step 1. 디렉토리 구조 검증 (자동)

- `wiki/` 직속 파일 중 `index.md` 외 페이지 → `_lint/report.md`에 보고 (이동은 `--apply` 시)
- 4 카테고리·`_lint/`·vault별 `sources/{vault}/` 디렉토리 부재 시 생성

### Step 2. ADR-0001 link 규약 검증 (자동, 보고만)

전체 wiki 페이지의 `[[link]]` 추출 후:

- **위반 1 — sources의 단축형 link**: source 카테고리 페이지 또는 source 페이지로 향하는 link 중 vault prefix 누락 (`[[report]]` 같은 형식) → 위반 항목 `_lint/report.md`에 기록
- **위반 2 — 잘못된 vault prefix**: `[[unknown/path]]`에서 `unknown`이 `wikihub.yaml.vaults[*].id`에 없음 → 보고
- **위반 3 — vault 존재하나 path 없음 (dangling)**: `[[gdrive/old/file]]`에서 `wiki/sources/gdrive/old/file.md` 부재 → 보고

검출만, 자동 수정 X (단축형의 의도된 동의어 가능성, dangling의 "나중에 만들 페이지" 의도 가능성).

### Step 3. 그래프 기반 점검 (자동)

`graphify-out/graph.json` 있으면 사용, 없으면 wiki 순회로 폴백:

- **고아 페이지** (인바운드 엣지 0건):
  - source 페이지: 보고만 (사용자가 직접 본문 읽고 자료로 활용 중일 수 있음)
  - entities/concepts: 보고. `--apply` 시 `.archived/` 이동 후보
- **dangling 엣지** (존재하지 않는 노드 가리킴): Step 2와 중복 가능. 통합 보고
- **언급된 개념의 페이지 부재**: source 본문에서 LLM이 식별한 entity·concept 중 `wiki/entities/`·`wiki/concepts/`에 페이지 없음 → **자동 stub 생성** (frontmatter + 1줄 LLM 요약 + `referenced_by`)

### Step 4. 자동 cross-ref 추가 (자동)

- 각 source의 본문에서 entity·concept 언급 식별
- 해당 entity·concept 페이지의 `referenced_by`에 source 경로 추가 (set semantics — 중복 X)
- 추가 외에 본문·다른 frontmatter 필드는 수정 안 함

### Step 5. wiki/index.md 재구성 (자동)

ADR-0005에 따라 `/wh-lint`가 index 재구성 책임 보유:

```markdown
# WikiHub

## Sources
### gdrive
- [[gdrive/meetings/2026-Q1.pptx]] — 2026 Q1 회의자료 (sources/gdrive/meetings/)
- [[gdrive/notes/idea]] — 아이디어 메모
### nas (있을 시)
...

## Entities
- [[홍길동]] — 전략기획팀 PM (5 sources 참조)
- ...

## Concepts
- [[OKR]] — Objectives and Key Results (3 sources 참조)
- ...

## Analyses
- [[2026-H1-회의-결정-비교]] — 2026-05-13 작성
- ...
```

- frontmatter 미포함 (사람 가시 진입점)
- 카테고리별 섹션. sources는 vault별 sub-section
- 각 항목: `[[link]] — 1줄 요약 (참조 수 또는 위치)`
- 통째 덮어쓰기 (이전 index는 backup 없이 대체 — 결정론적 재계산이므로 손실 무의미)

### Step 6. 모순·정보 갱신 점검 (보고만)

**Toggle 확인 (v0.1.5)**:

```bash
contradiction_check="$(yq '.operations.lint_contradiction_check // true' "$WIKIHUB_HOME/wikihub.yaml")"
```

- `contradiction_check == false` → 본 단계 skip + `_lint/report.md` 에 1줄 `contradiction check skipped (yaml toggle)`. Step 7 으로 jump.
- `contradiction_check == true` (default) → 아래 진행.

각 페이지를 LLM으로 점검:

- 페이지 간 모순되는 클레임
- 더 최신 source로 무효화 가능성 있는 내용
- 본문에 언급되지만 entity·concept 페이지가 없는 항목 (Step 3에서 자동 생성됐어야 하나 누락 케이스)

→ `_lint/report.md`에 보고. `--apply` 시 본문 갱신 (위험: 정보 손실 가능).

### Step 7. `--apply` 작업 (수동 호출 시에만)

기본 모드에서는 skip. `--apply` 플래그 있을 때:

- dangling link 제거 (Step 2 보고 항목 중 사용자가 수정·제거 표시한 것)
- `referenced_by` 0건 entity·concept → `wiki/.archived/<category>/<name>-<utc_iso>.md` 이동
- 폴더 위반 페이지 → 적절한 카테고리 이동 (단 vault prefix 필요한 sources는 메인테이너 명시 매핑)
- 모순 클레임 본문 갱신

**v0.1.0 정책 (확정)**: `--apply` 호출 시 **일괄 적용** (interactive per-item confirm 없음). 메인테이너는 `_lint/report.md` read → 의도 확인 → `<agent_invocation> "/wh-lint --apply"` 1회 호출로 모든 위험 작업 적용. interactive 세분화는 v0.2.x 후속 ADR 후보.

### Step 8. log 작성

- `wiki/_lint/report.md`: 본 사이클의 진단 + 자동 수정 내역 (overwrite)

```markdown
# Lint Report — 2026-05-13 03:00 KST

- **Mode**: auto (--apply 미사용)
- **Duration**: 12.3s

## 자동 수정 완료
- index.md 재구성: 23 sources, 47 entities, 12 concepts, 5 analyses
- 신규 stub 생성: entities/김철수 (1 source 참조), concepts/CRM (2 source)
- cross-ref 추가: 18건 (entities 12 + concepts 6)
- 카테고리 디렉토리 생성: wiki/_lint/

## 보고 (--apply 필요)
### Dangling links (3건)
- [[gdrive/old/archive]] — referenced from sources/gdrive/notes/idea.md:23
- ...

### Orphan entities (2건)
- [[entities/홍길동2]] — referenced_by 0건. 의도 확인 후 archive 가능
- ...

### 모순 의심 (1건)
- [[OKR]] vs [[gdrive/policies/promotion]] — promotion.md가 "OKR은 분기" 명시하나 OKR.md는 "연간"

## 통계
- 전체 페이지: 87
- 정상: 80, 자동 정비: 5, 보고 대기: 6
```

- `wiki/log.md`(global)는 만들지 않음. lint는 vault-agnostic이라 vault별 log에 append 부적합 → `_lint/report.md`가 진단 + 이력 통합 (overwrite는 진단 성격상 OK, 과거 보고서 보존 필요 시 향후 별도 ADR)

### Step 9. /wh-graphify 자동 호출

**Toggle 확인 (v0.1.5)**:

```bash
graphify_enabled="$(yq '.operations.graphify_enabled // true' "$WIKIHUB_HOME/wikihub.yaml")"
```

- `graphify_enabled == false` → 본 단계 skip + `_lint/report.md` 에 1줄 `graphify chain skipped (yaml toggle)`. Step 3 의 wiki 순회 fallback 으로 lint 본체 정상 동작 — graph.json 갱신만 미수행 (다음 cycle 까지 graph stale).
- `graphify_enabled == true` (default) → 아래 진행.

lint 사이클 마지막에 graphify 갱신을 자동 호출 (graphify spec 참조: lint 후 자동 호출 = 하루 1회 자연 갱신).

```bash
<agent_invocation> "/wh-graphify"
```

- 성공 → `wiki/_lint/report.md`에 추가: `graph rebuilt: N nodes, M edges`
- 실패 → report에 `graph rebuild failed: <reason>` + ops-alert 트리거 (graph 없으면 다음 사이클 /wh-query·/wh-lint 정확도 저하)
- 본 단계의 exit code는 lint의 exit code에 영향 안 줌 (graphify 실패가 lint 자체를 fail시키지 않음 — graph는 보조 자원)

**graphify 호출 형태 (ADR-0036 §Note 2026-05-20 — backend flexibility)**:

`/wh-graphify` playbook 이 yaml `operations.graphify_backend` 를 읽어 다음 형태로 graphify CLI subprocess 호출:

```bash
backend="$(yq '.operations.graphify_backend // ""' "$WIKIHUB_HOME/wikihub.yaml")"
backend_flag=""
[[ -n "$backend" ]] && backend_flag="--backend $backend"
timeout 300 graphify "$WIKIHUB_HOME/wiki" --update $backend_flag
```

- `--backend $backend`: yaml override (빈 문자열이면 flag 생략 → graphify auto-detect).
- `timeout 300`: graphify 가 어떤 사유로든 hang 하면 SIGTERM (exit 124). lint 본체 보호.
- exit 124 시 report 에 `graph rebuild timeout (300s, backend=$backend)` 기록 + lint 계속 (ADR-0036 §D6 정합).

**graphify 결과 self-check (ADR-0036 §재검토 트리거 — Pass 3 silent partial failure 가드)**:

- graphify 호출 성공 (exit 0) 후 `graphify-out/graph.json` read → 노드 수 = `N`
- `wiki/` 전체 페이지 수 = `M` (mechanical count — `**/*.md` 재귀 카운트, `_lint/`·`_state/` 제외)
- `M == 0` (빈 wiki) → check skip — 정상 첫 사이클
- `N / M < 0.5` (graph 가 wiki 의 절반 이하 표현) → **Pass 3 partial failure 의심**:
  - report 에 `graphify partial failure 의심: N=<N>, M=<M>, ratio=<r>` 추가
  - ops-alert 트리거 (운영자 진단 trigger — API key/quota/network 점검)
  - 본 check 실패는 lint exit 에 영향 없음 (graph 는 보조 자원, ADR-0036 §D6 정합)
- threshold `0.5` 는 보수적 default — wiki 규모가 작거나 entity stub 누적이 적은 초기 운영 시점에 false positive 우려 → 운영자가 yaml `operations.graphify_partial_failure_threshold` 로 override 가능 (v0.2.x 검토 트리거: 운영 데이터 surface 후 자동 ranging)

## 출력 산출물

| 변경 대상 | 모드 | 비고 |
|---|---|---|
| `wiki/index.md` | 자동 | 통째 재구성 |
| `wiki/entities/<name>.md` 신규 | 자동 | LLM 식별 + stub 생성 |
| `wiki/concepts/<name>.md` 신규 | 자동 | 동일 |
| 기존 entities·concepts `referenced_by` | 자동 | 추가만 |
| `wiki/_lint/report.md` | 자동 | overwrite |
| 카테고리 디렉토리 (없으면) | 자동 | mkdir |
| dangling link 제거·entity archive·본문 갱신 | `--apply` | 정보 손실 가능 |

## 실패 처리

| 실패 시점 | 동작 |
|---|---|
| graph.json 손상 | wiki 순회로 폴백 + report에 노트 |
| LLM 응답 실패 (entity 추출 등) | 해당 source skip + report에 노트. exit 0 (다음 사이클 재시도) |
| index.md write 실패 (disk full 등) | exit 1 + ops-alert |
| 카테고리 디렉토리 생성 실패 | exit 2 (Fatal, 권한 문제 의심) + notify |

## 멱등성 보장

- index 재구성은 결정론적
- stub 생성은 존재 확인 후 (이미 있으면 skip)
- cross-ref 추가는 set semantics
- 같은 wiki 상태에 대해 N회 실행해도 동일 결과

## 관련 ADR

- ADR-0001 vault namespace + `[[link]]` 단축형 금지 (Step 2 검증)
- ADR-0005 wiki/index.md 갱신 책임 (Step 5)
- ADR-0008 `/wh-lint` 권한 분류 (자동/`--apply`)
- ADR-0009 `/wh-setup`이 lint.timer 주기를 wikihub.yaml에서 동기화
