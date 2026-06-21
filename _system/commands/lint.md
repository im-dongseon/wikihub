# /wl

wiki 의 정합성·일관성 검증. graphify 자동 호출 가능. wikihub spec — _system/commands/lint.md playbook.

## 호출

```
<agent_invocation> "/wl"            # 진단 + 적용 (timer 자동 호출 + 메인테이너 수동 호출 동일 동작)
```

- **트리거 (자동)**: systemd timer (3시간 1회, v0.1.5 default `wikihub.yaml.operations.lint_interval_hours: 3`. 24h 이전 default 에서 변경 — graphify chain 의 cost 8배 증가하나 wiki 위생 사이클 빠른 surface 가치 우선)
- **트리거 (수동)**: 메인테이너가 `wiki/_lint/report.md` 즉시 확인 + 변경 적용 의도 시
- **vault 무관 (wiki-wide)**: 단일 명령으로 전체 wiki 점검
- **v0.1.8 ADR-0039 정합**: `--apply` flag 폐기 — wikihub `wiki/` 는 sources (vault, immutable) 의 LLM derivative 라 원본 변경 0. 매 cycle 진단 + 적용 default. 별도 dry-run 모드 필요 시 v0.2.x 검토.

## 사전 조건

- `wikihub.yaml` 존재
- wiki/ 디렉토리 + 4 카테고리(`sources/`, `entities/`, `concepts/`, `analyses/`) + `_lint/` 존재 (없으면 생성 — 본 명령이 자동)
- (선택) `$WIKIHUB_HOME/graphify-out/graph.json` — 있으면 그래프 기반 점검, 없으면 wiki 순회. **절대 경로 사용 필수** — wl skill (LLM) 의 CWD context 가 wiki/ 로 implicit drift 가능 → 상대 경로 시 stale `wiki/graphify-out/` 읽기 회귀 위험. 자세한 분석 + 진단 가이드: [docs/references/graph-path-resolution.md](../../docs/references/graph-path-resolution.md).
- **stale 감지**: `$WIKIHUB_HOME/wiki/graphify-out/` 존재 시 (legacy v0.1.7 이전 또는 잘못된 `graphify --out` 호출 잔존) → Step 7 가 cleanup, Step 8 가 보고. 본 디렉토리는 Step 3 graph source 로 절대 read 안 함.

## 출력 언어 정책 (LLM 호출 step 들 공통)

본 playbook 의 Step 3 (entity·concept stub 생성), Step 4 (cross-ref), Step 5 (index 재구성), Step 6 (모순·갱신 점검) 의 모든 LLM 응답 / wiki 본문 작성에서:

- **출력 언어 = 한국어** (wiki 의 source 본문이 한국어 위주, ADR-0001 vault-prefix link 도 한국어 entity/concept 명 정합).
- **한자 (漢字) 감지 시 한글로 변환** — MiniMax M2.5 등 일부 모델이 동음이의 한국어를 한자 표기로 출력하는 결함 발견 (Hermes OCI 실증, 2026-05-20). 예: "기획(企劃)" → "기획"; "권한(權限)" → "권한". 고유명사 (인명·지명·조직명 중 한국 외 출처) 는 예외 허용.
- **영어 약어** (OKR, PM, CRM, API 등) 는 그대로 유지 — 한국어 source 의 관용.

본 정책은 wiki-schema.md 의 신뢰 경계 출력 sanitize layer 와 정합.

## 절차

### Step 0. wiki-wide flock 가드 (v0.1.8 — race 가드)

wikihub-lint.service (3h 주기 timer) + 메인테이너 수동 호출 `/wl` 의 동시 실행 race 차단. 진행 중 lint 가 있으면 즉시 exit 0 (no-op).

```bash
exec 200>"$WIKIHUB_HOME/.wl.lock"
flock -n 200 || { echo "lint 이미 진행 중 — exit 0 (race 가드)"; exit 0; }
# lock 은 process 종료 시 자동 해제 (kernel-managed)
```

`flock -n` 은 non-blocking — lock 획득 fail 시 즉시 exit. systemd 가 success 로 처리 (다음 fire 자연 재시도). race window 0% 회피.

### Step 1. 디렉토리 구조 검증 (자동)

- `wiki/` 직속 파일 중 `index.md` 외 페이지 → `_lint/report.md`에 보고 (이동은 Step 7 에서 자동)
- 4 카테고리·`_lint/`·vault별 `sources/{vault}/` 디렉토리 부재 시 생성

### Step 1.5. alias index build (v0.1.10 — ADR-0042)

본 cycle 의 Step 2 dangling 검사가 사용할 alias inverted index 를 1회 빌드. (Step 4.5 duplicate detection 은 별도 subprocess `detect_alias_duplicates.py` 가 wiki 자체 스캔으로 처리 — 본 index 와 독립.)

```python
alias_index: dict[str, str] = {}   # lowercase_alias → canonical_filename
for category in ("entities", "concepts"):
    for page in (wiki_root / category).glob("*.md"):
        canonical = page.stem
        fm = read_frontmatter(page)
        for alias in (fm.get("aliases") or [canonical]):
            key = alias.strip().lower()
            if key in alias_index and alias_index[key] != canonical:
                continue   # 충돌 — Step 4.5 가 duplicate 보고
            alias_index[key] = canonical
```

비용: O(N) frontmatter read (N = entities + concepts 페이지 수). frontmatter 파싱 오류 발생 페이지는 skip + Step 4.5 가 결함 보고. 본 cycle 내 모든 resolver 호출이 같은 index 공유 (consistency).

### Step 2. ADR-0001 link 규약 검증 (자동, 보고만 — ADR-0042 resolver 적용)

전체 wiki 페이지의 `[[link]]` 추출 후:

- **위반 1 — sources의 단축형 link**: source 카테고리 페이지 또는 source 페이지로 향하는 link 중 vault prefix 누락 (`[[report]]` 같은 형식) → 위반 항목 `_lint/report.md`에 기록
- **위반 2 — 잘못된 vault prefix**: `[[unknown/path]]`에서 `unknown`이 `wikihub.yaml.vaults[*].id`에 없음 → 보고
- **위반 3 — vault 존재하나 path 없음 (dangling)**: `[[gdrive/old/file]]`에서 `wiki/sources/gdrive/old/file.md` 부재 → 보고

**entities / concepts 단축형 `[[<name>]]` dangling 검사 (ADR-0042 resolver)** — **category ∈ {entities, concepts} 한정**. sources 는 위반 1·2·3 path 그대로.

```python
def resolve_link(name, category):
    # 호출 전제: category in {"entities", "concepts"}
    exact = wiki_root / category / f"{name}.md"
    if exact.is_file():
        return exact
    canonical = alias_index.get(name.strip().lower())
    if canonical:
        return wiki_root / category / f"{canonical}.md"
    return None   # dangling
```

`[[<name>]]` 가 entities/concepts 단축형이면 `resolve_link(name, "entities")` 또는 `resolve_link(name, "concepts")` 호출 — alias 매핑된 canonical 페이지가 존재하면 valid (dangling 아님). 둘 다 부재 시 dangling 보고. 예: `[[mini-max]]` 가 `aliases: [MiniMax, mini-max, minimax]` 보유한 `entities/MiniMax.md` 로 resolve → 보고 안 함.

검출만, 자동 수정 X (단축형의 의도된 동의어 가능성, dangling의 "나중에 만들 페이지" 의도 가능성).

### Step 3. 그래프 기반 점검 (자동)

`$WIKIHUB_HOME/graphify-out/graph.json` (**절대 경로 필수** — CWD-independent resolution) 있으면 사용, 없으면 wiki 순회로 폴백.

**graphify schema 호환 (v0.7 → v0.8+ migration)**: graph.json 의 edge 키가 v0.7 = `edges`, v0.8+ = `links` 로 변경됨. parsing 시 `d.get('links', d.get('edges', []))` 패턴으로 양쪽 호환 (graphify CLI 버전 transition 중 silent break 회피).

진단 항목:

- **고아 페이지** (인바운드 엣지 0건):
  - source 페이지: 보고만 (사용자가 직접 본문 읽고 자료로 활용 중일 수 있음)
  - entities/concepts: 보고 + Step 7 에서 `.archived/` 자동 이동
- **dangling 엣지** (존재하지 않는 노드 가리킴): Step 2와 중복 가능. 통합 보고
- **언급된 개념의 페이지 부재**: source 본문에서 LLM이 식별한 entity·concept 중 `wiki/entities/`·`wiki/concepts/`에 페이지 없음 → **자동 stub 생성** (frontmatter + 1줄 LLM 요약 + `referenced_by`)
  - **alias 인식 (v0.1.8 — ADR-0039)**: stub 생성 전 wiki/entities/ + wiki/concepts/ 의 기존 page frontmatter `aliases` 셋을 lowercase 로 normalize 한 후, 본문 form 의 lowercase 가 그 셋에 포함되면 stub 생성 **skip** (LLM 재생성 무한 loop 차단). 기존 page 의 referenced_by 만 갱신.

### Step 4. 자동 cross-ref 추가 (자동)

- 각 source의 본문에서 entity·concept 언급 식별
- 해당 entity·concept 페이지의 `referenced_by`에 source 경로 추가 (set semantics — 중복 X)
- 추가 외에 본문·다른 frontmatter 필드는 수정 안 함

### Step 4.5. Duplicate detection (자동, 보고만 — v0.1.8 ADR-0039)

wiki/entities/ + wiki/concepts/ 의 page list 를 scan 해 두 종류 duplicate 탐지. **alias 기반 인식** — 단순 lowercase 비교가 아닌 frontmatter `aliases` 셋 비교 (ADR-0039 정합).

**구현**: `scripts/_helpers/detect_alias_duplicates.py` (Python subprocess helper, token 0화). LLM 호출 대신 deterministic subprocess 로 동일한 알고리즘을 처리한다:

```bash
# WIKIHUB_HOME 기준 wiki/entities/ + wiki/concepts/ scan → JSON stdout
python3 "$WIKIHUB_SRC/scripts/_helpers/detect_alias_duplicates.py" \
    --wiki-home "$WIKIHUB_HOME"
```

출력 JSON 구조:
```json
{
  "case_variant": [
    {
      "alias": "minimax",
      "category": "entity",
      "category_dir": "entities",
      "pages": [
        {"path": "wiki/entities/MiniMax.md", "original": "MiniMax"},
        {"path": "wiki/entities/minimax.md", "original": "minimax"}
      ]
    }
  ],
  "cross_category": [
    {
      "alias": "docker",
      "pages": [
        {"path": "wiki/entities/Docker.md", "original": "Docker", "category": "entity"},
        {"path": "wiki/concepts/Docker.md", "original": "Docker", "category": "concept"}
      ]
    }
  ]
}
```

→ `_lint/report.md` 의 `## Duplicates (case-variant)` + `## Duplicates (cross-category)` 섹션에 결과를 변환해 기록. Step 7 에서 자동 처리.

**검증 기준** (ADR-0039 정합):
- 비교는 **alias 셋의 lowercase normalize** — `MiniMax` 와 `minimax` 의 alias 셋이 공통 lowercase form 1+ 공유하면 같은 entity (단일 page 내 변형 alias 들은 다른 page 와 분리).
- case-variant = 같은 카테고리 내 2+ page 가 공통 lowercase form 보유.
- cross-category = entity normalize 셋 ∩ concept normalize 셋 ≠ ∅.

**Alias migration** (idempotent, 매 cycle — 기존 유지, Python subprocess 외 보조):
- 각 entity/concept page 의 frontmatter `aliases` 부재 시 — `aliases: [<canonical>]` 자동 추가 (canonical = 페이지 파일명 base).
- 빈 `aliases: []` 도 동일 처리.
- **책임 경계 (ingest vs lint)**: ingest 가 stub 생성 시 `aliases: [<본문 form>]` 명시 (ingest.md:152) → lint Step 4.5 는 ingest 미작성 page (legacy 또는 운영자 직접 생성) 만 보강. ingest 의 aliases 셋 위에 lint 가 overwrite 하지 않음.
- **atomic write**: frontmatter 갱신은 `<page>.tmp` write → `os.rename` atomic 이동 패턴. concurrent ingest / 운영자 수동 편집과의 race 가드. (운영자가 `aliases:` 수동 편집 중 lint cycle fire 시에도 atomic 보장)

### Step 5. wiki/index.md 재구성 (자동)

ADR-0005에 따라 `/wl`가 index 재구성 책임 보유:

```markdown
# WikiHub

## Sources
### gdrive
- [[gdrive/meetings/2026-Q1.pptx]]
- [[gdrive/notes/idea]]
### nas (있을 시)
...

## Entities
- [[홍길동]]
- ...

## Concepts
- [[OKR]]
- ...

## Analyses
- [[2026-H1-회의-결정-비교]]
- ...
```

- frontmatter 미포함 (사람 가시 진입점)
- 카테고리별 섹션. sources는 vault별 sub-section
- 각 항목: `[[link]]` (wikilink만 — 설명·참조 수 제거, index는 카탈로그 역할에 집중)
- 통째 덮어쓰기 (이전 index는 backup 없이 대체 — 결정론적 재계산이므로 손실 무의미)
- **권한 설정**: index.md write 직후 `chmod 644 <path>` 실행.

### Step 6. 모순·정보 갱신 점검 (보고만)

**Toggle 확인 (v0.1.5)**:

```bash
contradiction_check="$(yq '.operations.lint_contradiction_check // true' "$WIKIHUB_HOME/wikihub.yaml")"
```

- `contradiction_check == false` → 본 단계 skip + `_lint/report.md` 에 1줄 `contradiction check skipped (yaml toggle)`. Step 7 으로 jump.
- `contradiction_check == true` (default) → 아래 진행.

각 페이지를 LLM으로 점검:

- **idempotency (Issue #39)**: entity 페이지 frontmatter에 `merged_from` 필드 존재 시 → 해당 entity는 이미 cross-category merge 완료 상태. LLM merge(본문 갱신) 재호출 금지. 본문 불변, `referenced_by` 만 갱신 대상.
- 페이지 간 모순되는 클레임
- 더 최신 source로 무효화 가능성 있는 내용
- 본문에 언급되지만 entity·concept 페이지가 없는 항목 (Step 3에서 자동 생성됐어야 하나 누락 케이스)

→ `_lint/report.md`에 보고 + Step 7 에서 LLM 본문 갱신 자동. wikihub `wiki/` = LLM derivative 라 원본 변경 0 (ADR-0039 정합).

### Step 7. 적용 작업 (매 cycle 자동, v0.1.8 ADR-0039 정합)

`--apply` flag 폐기 — wikihub 데이터 모델상 wiki/ 가 sources 의 LLM derivative 라 원본 변경 0. 매 lint cycle 의 default 동작에 흡수.

매 cycle 진행:

- dangling link 제거 (Step 2 보고 항목)
- `referenced_by` 0건 entity·concept → `wiki/.archived/<category>/<name>-<utc_iso>.md` 이동
- 폴더 위반 페이지 → 적절한 카테고리 이동 (단 vault prefix 필요한 sources는 메인테이너 명시 매핑)
- 모순 클레임 본문 갱신 (Step 6 보고 항목)
- **case-variant duplicate 처리 (Step 4.5 보고 항목, ADR-0039)**:
  - canonical 선택: alias 셋의 첫 form (또는 운영자 `canonical: <name>` frontmatter 명시 시 그것). 보존.
  - 다른 form 의 page → `.archived/<category>/<name>-<utc_iso>.md` 이동
  - canonical page 의 alias 셋 ∪ archive 된 page 의 alias 셋 — 합집합 frontmatter 갱신
  - canonical page 의 referenced_by ∪ archive 된 page 의 referenced_by — 합집합
  - wiki/ 전체 sed 치환: 변형 form 의 link `[[<variant>]]` → `[[<canonical>]]` (명시적 카테고리 prefix link 만 매칭. 단축형 `[[<name>]]` 은 link resolver 가 새 page 위치 자동 인식)
  - **idempotency**: archive 후 같은 form 의 page 가 ingest 사이클에서 재생성되지 않도록 ingest.md alias 인식 (Step 4) 정합 — 같은 alias 보유 시 stub 생성 skip
- **cross-category duplicate 처리 (Step 4.5 보고 항목, ADR-0039)**:
  - entity 우선 — concept 페이지의 본문 + referenced_by + alias 셋을 entity 페이지로 **LLM merge**
  - **merge 수행 후 entity frontmatter에 `merged_from: [<concept-page-slug>]` 추가** (idempotency 마커, Issue #39)
  - concept 페이지를 `.archived/concepts/<name>-<utc_iso>.md` 이동
  - **idempotency gate (Issue #39)**: archive 후 concept page 가 ingest cycle 의 새 source 변화로 재등장 시:
    - entity frontmatter 에 `merged_from` 존재 → **entity 본문 LLM merge 재호출 안 함**
    - concept 본문 + `referenced_by` + alias 만 합집합 추가 (entity 본문 git history churn 차단)
    - `merged_from` 부재 시 (첫 merge) → LLM merge 정상 수행 후 `merged_from` 추가

- **stale `wiki/graphify-out/` cleanup (v0.1.10 — graphify_path_absolute)**:
  - `$WIKIHUB_HOME/wiki/graphify-out/` 존재 감지 시 → `$WIKIHUB_HOME/graphify-out/.archived/wiki-graphify-out-<utc_iso>/` 로 이동 (recoverable archive — `rm -rf` 절대 금지, `mv` 만).
  - 본 디렉토리는 pre-v0.1.8 era graphify 호출 또는 잘못된 `graphify --out` 인자 잔존물. 정상 graphify (`scripts/wikihub_graphify.sh` 가 `--out "$WIKIHUB_HOME"` 명시) 는 `wiki/graphify-out/` 미생성.
  - archive 후 lint 가 다시 stale 을 graph source 로 읽지 않음 + Step 3 의 절대 경로 정합으로 회귀 차단.

**v0.1.8 정책 (확정, --apply flag 폐기)**: 매 cycle 일괄 적용 (interactive per-item confirm 없음). 메인테이너 수동 호출 (`/wl`) 도 즉시 적용. 진단만 받고 싶으면 `wiki/_lint/report.md` read.

### Step 8. log 작성

- `wiki/_lint/report.md`: 본 사이클의 진단 + 자동 수정 내역 (overwrite)

```markdown
# Lint Report — 2026-05-13 03:00 KST

- **Mode**: auto (매 cycle 진단 + 적용 — v0.1.8 ADR-0039)
- **Duration**: 12.3s

## 자동 수정 완료
- index.md 재구성: 23 sources, 47 entities, 12 concepts, 5 analyses
- 신규 stub 생성: entities/김철수 (1 source 참조), concepts/CRM (2 source)
- cross-ref 추가: 18건 (entities 12 + concepts 6)
- 카테고리 디렉토리 생성: wiki/_lint/

## Stale cleanup (v0.1.10 — graphify_path_absolute, 해당 시만)
- `wiki/graphify-out/` (934 nodes, 826 edges, 2026-05-24 생성, 4.6MB) → `graphify-out/.archived/wiki-graphify-out-20260526T093000Z/` 이동 (recoverable archive)

## Duplicates (case-variant) — v0.1.8 ADR-0039
- `Claude-Code` / `claude-code` (entity) → Step 7 에서 canonical 보존 + alias 합집합
- ...

## Duplicates (cross-category) — v0.1.8 ADR-0039
- `Docker` (entity + concept) → Step 7 에서 entity 보존, concept 본문 LLM merge + archive
- ...

## 보고 (Step 7 에서 자동 처리됨)
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
- **권한 설정**: report.md write 직후 `chmod 644 <path>`. `_lint/` 디렉토리 write 전 `mkdir -p` 후 `chmod 755`.

### Step 9. graphify chain trigger (v0.1.8 update_path_fixes — D3 (B) 채택)

**책임 분리** (ADR-0036 §D6 single-source 정합):
- **lint Step 9 책임 = trigger 만** — 변경 감지 + `systemctl --user start wikihub-graphify.service` 호출
- **graphify CLI 호출 책임 = `wikihub-graphify.service` (정본 `scripts/wikihub_graphify.sh`)**
- v0.1.7 era 의 `<agent_invocation> "/wh-graphify"` 표현 폐기 — hermes 의 자동 sub-skill spawn 메커니즘 부재 (Reviewer 2 hermes source 검증). graphify hermes skill 자체도 폐기 (Layer 1 LLM wrapper 가 deterministic bash 작업의 over-engineering).

**조건 분기**:

```bash
graphify_enabled="$(yq '.operations.graphify_enabled // true' "$WIKIHUB_HOME/wikihub.yaml")"
```

1. **`graphify_enabled == false`** → skip + `_lint/report.md` 에 1줄 `graphify chain skipped (yaml toggle)`
2. **lint cycle 변경 없음** (다음 모두 0건: Step 3 자동 stub 생성 / Step 4.5 duplicate 처리 / Step 5 index.md 변경 / Step 7 archive 이동) → skip + `_lint/report.md` 에 1줄 `graph rebuild skipped (no changes)` ← **cost gate (사용자 핵심 의도, v0.1.8 신설)**
3. **lint cycle 변경 있음 + graphify_enabled=true** → 다음 호출 (fire-and-forget):
   ```bash
   systemctl --user start wikihub-graphify.service
   ```
   + `_lint/report.md` 에 1줄 `graphify chain triggered — see journalctl --user -u wikihub-graphify.service`

**fire-and-forget 의미**: `systemctl --user start` 가 비동기 — wikihub-lint.service 즉시 종료. graphify 결과는 `wikihub-graphify.service` 의 별도 journal + `$WIKIHUB_HOME/graphify-out/graph.json` 으로 surface. lint exit code 는 graphify 결과 무관.

**graphify 결과 검증 위치** (ADR-0036 §재검토 트리거 — Pass 3 silent partial failure 가드):
- `scripts/wikihub_graphify.sh` 의 Step 4 (`N / M < threshold` ratio check) — 정본
- `wikihub-graphify.service` 의 journal 에 `WARNING: graphify partial failure 의심: N=<N>, M=<M>, ratio=<r>` 출력
- threshold = yaml `operations.graphify_partial_failure_threshold` (default 0.5)
- 운영자 별 진단 path: `journalctl --user -u wikihub-graphify.service --since "1 day ago" | grep -E "partial|graph rebuilt"`

## 출력 산출물

| 변경 대상 | 모드 | 비고 |
|---|---|---|
| `wiki/index.md` | 자동 | 통째 재구성 |
| `wiki/entities/<name>.md` 신규 | 자동 | LLM 식별 + stub 생성 |
| `wiki/concepts/<name>.md` 신규 | 자동 | 동일 |
| 기존 entities·concepts `referenced_by` | 자동 | 추가만 |
| `wiki/_lint/report.md` | 자동 | overwrite |
| 카테고리 디렉토리 (없으면) | 자동 | mkdir |
| dangling link 제거·entity archive·본문 갱신 | 매 cycle 자동 (v0.1.8 ADR-0039) | wiki/ = LLM derivative, 원본 변경 0 |

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
- ADR-0008 `/wl` 권한 분류 (v0.1.0 era — 자동/`--apply` 구분, v0.1.8 ADR-0039 에서 폐기)
- ADR-0009 `/wh-setup`이 wikihub-lint.timer 주기를 wikihub.yaml에서 동기화
