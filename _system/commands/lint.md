# /wl

wiki 의 정합성·일관성 검증. graphify 자동 호출 가능. wikihub spec — _system/commands/lint.md playbook.

## 호출

```
# 권장 (1차 race 가드 적용 — systemd 경유)
systemctl --user start wikihub-lint.service

# Hermes 채팅 직접 호출 (systemd 우회 — 동시 실행 가드 미적용, Step 0.5 참조)
<agent_invocation> "/wl"
```

- **트리거 (자동)**: systemd timer (3시간 1회, v0.1.5 default `wikihub.yaml.operations.lint_interval_hours: 3`. 24h 이전 default 에서 변경 — graphify chain 의 cost 8배 증가하나 wiki 위생 사이클 빠른 surface 가치 우선)
- **트리거 (수동)**: 메인테이너가 `wiki/_lint/report.md` 즉시 확인 + 변경 적용 의도 시. **`systemctl --user start wikihub-lint.service` 를 사용** — timer 발화와 겹쳐도 systemd 가 동일 유닛 중복을 드롭 (Step 0)
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

### Step 0. 동시 실행 가드 (race 가드)

wikihub-lint.service (3h 주기 timer) + 메인테이너 수동 호출의 동시 실행 race 차단. 진행 중 lint 가 있으면 즉시 exit 0 (no-op).

**1차 가드 = systemd** (`Type=oneshot`). 동일 유닛이 실행 중이면 중복 발화가 systemd 자체에서 드롭됩니다 (ingest.md 도 동일한 systemd 유닛 가드를 씁니다).

```
systemctl --user start wikihub-lint.service
```

systemd 가 이미 실행 중인 유닛에 start 를 반복 요청해도 실제 실행 인스턴스는 1개입니다 (2026-09-14 실측: 실행 중 유닛에 start 3회 → 실행 1회). timer 와 수동 호출이 겹쳐도 동일 유닛이므로 중복이 생기지 않습니다.

**2차 가드 = flock 파일** (보조 layer). **단일 bash 프로세스가 세션 전체를 소유할 때만** 유효합니다.

```bash
# 세션 전체를 소유하는 단일 bash 프로세스 (예: 실행 스크립트) 내부에서만
exec 200>"$WIKIHUB_HOME/.wl.lock"
flock -n 200 || { echo "lint 이미 진행 중 — exit 0 (race 가드)"; exit 0; }
# lock 은 이 bash 프로세스가 종료할 때까지 유지 (kernel-managed)
```

> **⚠️ 이 패턴은 Hermes 경유 호출에서 무력하다 (2026-09-14 실증)**
>
> `flock(2)` 는 **열린 fd** 에 lock 을 걸고, fd 는 프로세스 수명과 함께 사라집니다. Hermes agent 가 terminal tool 로 **명령을 매번 별도 subprocess 로 실행**하는 환경에서는 lock 을 잡은 명령이 끝나는 순간 커널이 해제되므로, 다음 명령은 새 fd 라 무관하게 통과합니다. 실측:
>
> ```
> 명령 1: exec 200>lock; flock -n 200  → 획득 후 프로세스 종료
> 명령 2: exec 200>lock; flock -n 200  → 획득됨 (가드 무력)
> flock -n 200 단독 실행 (해당 shell 에 fd 200 미할당) → "Bad file descriptor"
> ```
>
> 운영 로그 실측: `/wl` 세션 3개 동시 실행, 셋 다 lock 미점유 (2026-09-14 02:43 KST).
> **fd 상속 방식은 이 실행 모델에서 `race window 0%` 를 보장하지 못합니다.** 세션을 소유하는 단일 프로세스가 없는 호출 경로에서는 가드로 성립하지 않습니다.

**결론 — 본 가드의 실효 범위**

| 계층 | 실효성 | 근거 |
|---|---|---|
| systemd 유닛 (`Type=oneshot`) | **유효 — 1차 가드** | 동일 유닛 중복 발화를 systemd 가 드롭 (실측: 실행 중 유닛에 start 3회 → 실행 1회) |
| flock 파일 (보조) | **무효 — Hermes 경유 시** | fd-scoped lock 이 subprocess 종료와 함께 해제됨 (위 실측) |

따라서 **동시 실행 차단은 systemd 유닛에 의존한다.** flock 은 단일 bash 프로세스가 세션
전체를 소유하는 경로(예: 실행 스크립트 내부)에서만 보조로 유효하다.

flock 무효를 이유로 **세션을 중단하거나 clarify 를 호출하지 않는다** — 중복 위험은
systemd 계층이 막고 있으므로 본 Step 은 그대로 진행한다.

### Step 0.5. Hermes 채팅 `/wl` 직접 호출 경로 (미해결 — 후속 결정)

Hermes 채팅에서 `/wl` 을 직접 호출하면 systemd 유닛을 경유하지 않으므로 **1차 가드가 적용되지 않습니다.** 이 경로에서는 위 flock 2차 가드도 무력합니다 (fd 상속 불가).

- 현재 상태: 메인테이너가 timer 발화와 겹쳐 `/wl` 을 직접 호출하면 lint cycle 이 중복 실행될 수 있음
- **권장 경로**: 수동 실행도 `systemctl --user start wikihub-lint.service` 를 사용 (1차 가드 적용)
- 처리 방향(경로 폐기 / 프로세스-무관 가드 도입)은 후속 결정 사항 — 이슈 #180 참조

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

**graphify 질의 우선 (3계층 — issue #173)**

전체 `graph.json`(수 MB)을 컨텍스트에 올리는 대신 아래 순서로 질의한다.

| 계층 | 도구 | 용도 | 비용 |
|---|---|---|---|
| **1차** | `graphify query` / `graphify explain` | 특정 노드·source 의 연결/이웃 확인 | ~1-2k tokens |
| **2차** | `graph.json` 직접 읽기 | 1차로 전체 구조가 필요하다고 판명된 경우 (폴백) | 기존과 동일 |
| **3차** | deterministic helper | 고아 페이지 등 **전체 노드 순회** 필요 항목 | 0 (LLM 호출 없음) |

호출 형식:

```bash
"$WIKIHUB_VENV/bin/graphify" query "<질의>" --graph "$WIKIHUB_HOME/graphify-out/graph.json"
"$WIKIHUB_VENV/bin/graphify" explain "<노드명>" --graph "$WIKIHUB_HOME/graphify-out/graph.json"
```

- `$WIKIHUB_VENV` 는 `~/.config/wikihub/session-env.sh`(#186)가 export 하고,
  Hermes `terminal.shell_init_files` 등록으로 세션에 주입된다 (Step 5 의 다른 helper 호출과 동일 패턴).
- PATH 에도 venv `bin` 이 있으므로(unit) `graphify` 단독 호출도 동작한다 — 경로가 확실한 쪽을 쓴다.
- `--graph` 는 **절대 경로**로 넘긴다 (CWD-independent).
- **고아 페이지(degree=0) 탐지는 query 로 불가**하다 — 전체 노드 순회가 필요하므로 3차 계층(helper)을 쓴다.
  1차 계층으로 시도하지 않는다.
- ⚠️ `graphify god-nodes` 는 **고아 탐지가 아니다** — "가장 연결이 많은 노드(architectural hubs)"를 나열한다
  (실측 2026-09-22: `God nodes (most connected): ... - 67 edges`). degree=0 탐지에 쓰면 **정반대 결과**를 얻는다.
  고아 탐지는 Python helper(전체 노드 순회)로만 가능하다.
- 1차 질의가 빈 결과·오류를 내면 **2차로 폴백**하고 그 사실을 report 에 1줄 기록한다.
- 질의 실패를 이유로 **중단하거나 clarify 를 호출하지 않는다** (headless 규칙).

진단 항목:

- **고아 페이지** (인바운드 엣지 0건):
  - source 페이지: 보고만 (사용자가 직접 본문 읽고 자료로 활용 중일 수 있음)
  - entities/concepts: 보고 + Step 7 에서 `.archived/` 자동 이동
- **dangling 엣지** (존재하지 않는 노드 가리킴): Step 2와 중복 가능. 통합 보고
- **언급된 개념의 페이지 부재**: source 본문에서 LLM이 식별한 entity·concept 중 `wiki/entities/`·`wiki/concepts/`에 페이지 없음 → **자동 stub 생성** (frontmatter + 1줄 LLM 요약 + `referenced_by`)
  - **alias 인식 (v0.1.8 — ADR-0039)**: stub 생성 전 wiki/entities/ + wiki/concepts/ 의 기존 page frontmatter `aliases` 셋을 lowercase 로 normalize 한 후, 본문 form 의 lowercase 가 그 셋에 포함되면 stub 생성 **skip** (LLM 재생성 무한 loop 차단). 기존 page 의 referenced_by 만 갱신.
  - **권한 설정**: `_atomic_write_wiki_page` 가 write 시 `chmod 644` 를 코드로 보장한다 (issue #201 ①). 별도 `chmod` 는 불필요하다 — 과거 mktemp 기본값 600 보정용 지시였으나 코드가 흡수했다.

### Step 4. 자동 cross-ref 추가 (자동)

- 각 source의 본문에서 entity·concept 언급 식별
- 해당 entity·concept 페이지의 `referenced_by`에 source 경로 추가 (set semantics — 중복 X)
  - **`referenced_by:` 가 빈 값(`''`/`null`)인 페이지는 제외**한다 — 빈 값에 항목을 넣는 것은 "등록"이며 자동 등록 금지 대상이다 (issue #167, `## 실패 처리` 표). 리스트 0건(`[]`)은 추가 대상이다
- 추가 외에 본문·다른 frontmatter 필드는 수정 안 함

### Step 4.5. Duplicate detection (자동, 보고만 — v0.1.8 ADR-0039)

wiki/entities/ + wiki/concepts/ 의 page list 를 scan 해 두 종류 duplicate 탐지. **alias 기반 인식** — 단순 lowercase 비교가 아닌 frontmatter `aliases` 셋 비교 (ADR-0039 정합).

**구현**: `scripts/_helpers/detect_alias_duplicates.py` (Python subprocess helper, token 0화). LLM 호출 대신 deterministic subprocess 로 동일한 알고리즘을 처리한다:

```bash
# WIKIHUB_HOME 기준 wiki/entities/ + wiki/concepts/ scan → JSON stdout
"$WIKIHUB_VENV/bin/python3" "$WIKIHUB_SRC/scripts/_helpers/detect_alias_duplicates.py" \
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

### Step 4.6. frontmatter 무결성 검사 (자동, 보고만)

매 cycle 아래 4종을 검사해 `_lint/report.md` 에 기록한다. **4종 모두 `yaml.safe_load` 를
통과**하므로 파서 검증만으로는 검출되지 않는다 — 별도 검사가 필요하다.

| 검출 항목 | 판정 | 함정 |
|---|---|---|
| **키 중복** | frontmatter top-level 키가 2회 이상 (특히 `referenced_by`·`aliases`) | YAML 은 마지막 키만 채택 → 첫 블록에 쓴 갱신이 실효값에 반영되지 않음 |
| **여는 `---` 뒤 개행 소실** | `startswith('---\n')` 가 거짓 | `---aliases:` 로 붙어 frontmatter 파손 + alias index 탈락 |
| **`aliases` 안의 경로 문자열** | `aliases` 항목에 `sources/` 포함 | run 경계 없이 스캔해 뒤따르는 키의 리스트를 흡수 (alias 오염) |
| **항목 병합** | `referenced_by` **항목 값 안에** `.md-` 가 포함 | 삽입 오프셋이 직전 항목 "줄 끝" 이라 개행 없이 붙음 (`sources/a/x.md- sources/a/y.md`) |

**삽입 규칙 정본은 `_system/commands/ingest.md` Step 4** ("referenced_by 삽입 경계 조건 4종") 다.
본 검사는 그 규칙이 지켜졌는지 사후 확인하는 역할이다.

`ingest.md` Step 4 의 들여쓰기 규칙과 동일하게 — **2칸 고정을 강제하지 않는다.** 0칸 run 은
정상이며 YAML block sequence 로 유효하다. 페이지 단위 혼용(0칸+2칸)만 결함으로 본다.
(운영 실측 기준 0칸 run 이 다수 — 정확한 항목 수는 `ingest.md` Step 4 의 실측치를 참조.
 wiki 는 매 cycle 갱신되므로 수치는 고정값이 아니다.)

**검증 기준** (ADR-0039 정합):
- 비교는 **alias 셋의 lowercase normalize** — `MiniMax` 와 `minimax` 의 alias 셋이 공통 lowercase form 1+ 공유하면 같은 entity (단일 page 내 변형 alias 들은 다른 page 와 분리).
- case-variant = 같은 카테고리 내 2+ page 가 공통 lowercase form 보유.
- cross-category = entity normalize 셋 ∩ concept normalize 셋 ≠ ∅.

**Alias migration** (idempotent, 매 cycle — 기존 유지, Python subprocess 외 보조):
- 각 entity/concept page 의 frontmatter `aliases` 부재 시 — `aliases: [<canonical>]` 자동 추가 (canonical = 페이지 파일명 base).
- 빈 `aliases: []` 도 동일 처리.
- **책임 경계 (ingest vs lint)**: ingest 가 stub 생성 시 `aliases: [<본문 form>]` 명시 (`ingest.md` Step 4.3) → lint Step 4.5 는 ingest 미작성 page (legacy 또는 운영자 직접 생성) 만 보강. ingest 의 aliases 셋 위에 lint 가 overwrite 하지 않음.
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
- **권한 설정**: index.md write 직후 `chmod 644 "<path>"` 실행.

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
- `referenced_by` 가 **리스트이고 0건**인 entity·concept → `wiki/.archived/<category>/<name>-<utc_iso>.md` 이동
  - **`referenced_by:` 가 빈 값(`''`/`null`)인 경우는 archive 대상이 아니다** — 리스트 0건(`[]`)과 의미가 다르다. 자동 등록·archive 모두 금지하고 보고만 한다 (issue #167, `## 실패 처리` 표 동일 항목)
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

**v0.1.8 정책 (확정, --apply flag 폐기)**: 매 cycle 일괄 적용 (interactive per-item confirm 없음). 메인테이너 수동 호출도 즉시 적용 (호출 경로는 `## 호출` 참조 — systemd 경유 권장). 진단만 받고 싶으면 `wiki/_lint/report.md` read.

### Step 7.1. 편입 등록 원장 형식 정본 (issue #191)

편입(embedding) 등록 회차는 `_state/<vault>/_semantic_<YYYYMMDD>_<HHMM>.json` 원장에 결과를 기록한다.
**원장 형식이 회차마다 달라 실제 상태와 문자열 대조가 어긋난다** — 아래를 정본으로 고정한다.

> 파일명은 **`_semantic_<YYYYMMDD>_<HHMM>.json`** (날짜 포함). 과거 `_semantic_<HHMM>.json`
> (날짜 없음) 형식은 다른 날 같은 시각 회차가 서로를 덮어쓰므로 신규 회차에 사용하지 않는다.
> 기존 파일명은 소급 변경하지 않는다 (`round` 필드가 정본 시각을 갖는다).

```json
{
  "round": "YYYYMMDD__HH_MM__lint",
  "applied": ["concepts/Durable-Workflow.md", "entities/Google-Drive.md"],
  "skipped": {},
  "base": "<canonical 집합 산출 근거>",
  "backup": "/tmp/wi_backup_<vault>_<YYYYMMDD_HHMM>",
  "applied_at": "<UTC ISO-8601>",
  "source": "sources/<vault>/project/wikihub/report/<round>.md"
}
```

**필수 규칙**

1. `applied` 항목은 **canonical 경로 + `.md` 접미 포함**으로 기록한다
   (현행 wiki 파일명 규약: 공백 → 하이픈, 카테고리 귀속 반영). 접미 없는 항목은
   실제 파일과 문자열 대조가 불가능하다.
2. `base` 키를 **항상 포함**한다 — canonical 집합 산출 근거(어느 회차·페이지 수)를 남긴다.
3. `applied_at` 은 UTC ISO-8601, `backup` 은 실제 존재하는 경로여야 한다.

**회차 검증 (필수)**

`applied` 기록 후 **실제 반영 수를 대조**해 `_lint/report.md` 에 1줄 남긴다.

```
applied=N 실제=M  (경로 정규화: NFC + .md 접미 정규화 후 실재 + 참조 보유 검사)
```

- `N == M` → 정상
- `N != M` → **보고** + 누락 항목을 경로와 함께 기재. 누락 유형을 구분해 적는다.
  - `NOFILE` — 원장 경로에 파일 없음 (파일명 규약 불일치 또는 아카이브 이동)
  - `NO_REF` — 파일은 있으나 해당 회차 참조가 없음 (실제 등록 실패)

**대조 시 정규화 주의**: 원장 경로와 실제 파일명이 공백↔하이픈·카테고리(entities↔concepts)·
NFC/NFD 로 다를 수 있다. **정규화 후 비교**하고, 정규화로도 대응이 없을 때만 `NOFILE` 로
판정한다 — 그렇지 않으면 형식 차이를 등록 실패로 오탐한다.

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
- **권한 설정**: report.md write 직후 `chmod 644 "<path>"`. `_lint/` 디렉토리 write 전 `mkdir -p` 후 `chmod 755`.

### Step 8.1. 보고만 항목 이월 규칙 (issue #167)

`## 보고만 (승인 대기)` 항목이 회차마다 반복되어도 **매번 재판단하지 않는다.**
판단 주체가 다르거나 자동 적용이 금지된 항목이므로, 반복 자체는 결함이 아니다.

**이월 표기 (필수)** — 매 회차 보고 시 각 항목에 아래를 함께 적는다:

| 필드 | 내용 |
|---|---|
| **회차 수** | `(N회차 유지)` — 동일 항목이 몇 회차 연속 보고됐는지 |
| **귀속** | `메인테이너 판단` / `개발 소관` / `운영 소관` 중 하나 |
| **변화** | 직전 회차 대비 증감. 변화 없으면 `변화 없음` |

**회차 수·변화 산출 출처** — `_lint/report.md` 는 overwrite 이므로 직전 회차 내용이 남지 않는다.
**발행된 이전 report 를 읽어 산출**한다:

```bash
# 직전 회차 report (vault 실경로, 발행본)
ls -t "$WIKIHUB_HOME/vault/<vault>/project/wikihub/report/"*lint.md 2>/dev/null | sed -n '2p'
```

발행본이 없으면(신규 vault·발행 실패) 회차 수를 `(1회차)` 로 적고 변화는 `기준 없음` 으로
표기한다 — **산출 불가를 이유로 판단을 유보하거나 clarify 를 호출하지 않는다.**

**재판단 금지** — 이미 `귀속` 이 정해진 항목은 회차마다 판단 근거를 다시 서술하지 않는다.
1줄 이월 표기만 한다. 판단 근거 전문은 **최초 보고 회차에만** 적는다.

**자동 적용 금지 목록** (위반 시 되돌리기 어려운 변경이 발생):

- append-only 파일(`log.md`) 의 접두 보존 대상 — 플레이스홀더 치환 포함
- `referenced_by:` 가 빈 값인 페이지의 등록·archive
- sources 본문 (vault 원문) 의 한자·표기 변환
- 구조 잔재 페이지(본문 실질 1줄 이하·frontmatter 다중 빈 줄 등)의 삭제·이동 (편집 여부는 메인테이너 결정)

**개발 소관 승격 조건** — 아래에 해당하면 `메인테이너 판단` 이 아니라 `개발 소관` 으로
분류하고, report 의 개발 소관 절에 모아 적는다:

- playbook(`_system/commands/*.md`) 또는 `scripts/lib/*` 의 규칙 부재·결함이 원인일 때
- 운영 로컬 헬퍼(`_scripts/*`) 의 계상이 정본과 다를 때
- 구조적 결함(경로 이중 계상, 권한 코드 누락 등)이 원인일 때

**정본 우선 원칙** — 운영 로컬 헬퍼와 정본 계상이 다르면 **정본을 인용**하고 불일치
사실만 1줄 기록한다. 헬퍼 수치를 report 본문에 그대로 싣지 않는다.

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

## 동시성

- **1차 가드 = systemd `Type=oneshot`** — `wikihub-lint.service` 는 단일 유닛이므로 timer 발화와 `systemctl --user start` 수동 호출이 겹쳐도 중복 실행이 드롭된다. 실행 중 유닛에 start 를 반복 요청해도 실제 인스턴스는 1개 (2026-09-14 실측).
- **2차 가드 = 파일 flock (`.wl.lock`)** — **세션 전체를 소유하는 단일 bash 프로세스가 있을 때만** 유효하다. Hermes agent 의 terminal tool 처럼 명령마다 별도 subprocess 를 만드는 실행 모델에서는 fd 상속이 불가해 무력하다 (Step 0 경고 참조).
- **미해결 경로**: Hermes 채팅에서 `/wl` 을 직접 호출하면 systemd 를 경유하지 않아 1차 가드가 적용되지 않는다. 이 경로의 처리(폐기 또는 프로세스-무관 가드 도입)는 후속 결정 사항 — Step 0.5.
- ingest 는 vault별 unit + per-vault lock 으로 직렬화한다 (ingest.md `## 동시성` 참조). lint 는 wiki-wide 단일 unit 이며 vault 무관.

## headless 실행 규칙 (issue #167)

본 playbook 은 `wikihub-lint.service` (systemd oneshot, `--quiet --yolo`) 로 실행되며
**사용자 응답을 받을 수단이 없다.** 따라서:

1. **사용자 입력을 요구하는 도구를 호출하지 않는다.** `clarify` 를 비롯해 운영자 응답을
   기다리는 모든 tool(`clarify`, 승인 confirm 계열 등)이 대상이다. `--yolo` 는 **위험 명령
   승인 프롬프트만** 우회하고, agent 가 자율 호출하는 tool 은 범위 밖이다.
   호출 시 증상: 응답 불가 → tool 자체 timeout(실측 120s) → 복구 시도 실패 →
   `TimeoutStartSec` 소진 → systemd SIGINT → **exit 130** (실측, 2026-07).

2. **판단이 필요한 상황의 기본값은 "보고만"이다.** 예외·대량 오류·모호한 상태를 만나면
   자동 수정하지 않고 report 에 기록한 뒤 **다음 Step 으로 진행**한다. "이걸 자동 처리해도
   되는가" 를 묻지 않고 "기본값은 보고만" 을 적용한다.

3. **규모와 무관하게 동일하다.** 오류 157건이든 1건이든 skip-and-continue. 규모가 크다는
   이유로 판단을 유보하거나 사용자에게 넘기지 않는다.

4. **메인테이너 판단 항목은 결정을 요구하지 않는다.** §Step 8.1 의 이월 규칙에 따라
   기록·이월만 하고, 회차마다 동일 질문을 반복하지 않는다.

> 위반 시 증상: 세션이 응답 대기로 멈추고 `TimeoutStartSec` (unit 실측 `1800sec`) 소진 후
> systemd 가 SIGINT 를 보내 `exit 130`. journal 에 `Deactivated successfully` 없이 `Failed` 로
> 남는다. (tool 자체 timeout 은 120s, unit timeout 은 1800s — 두 값은 별개다.)

## 실패 처리

| 실패 시점 | 동작 |
|---|---|
| graph.json 손상 | wiki 순회로 폴백 + report에 노트 |
| LLM 응답 실패 (entity 추출 등) | 해당 source skip + report에 노트. exit 0 (다음 사이클 재시도) |
| index.md write 실패 (disk full 등) | exit 1 + ops-alert |
| 카테고리 디렉토리 생성 실패 | exit 2 (Fatal, 권한 문제 의심) + notify |
| chmod 실패 (소유권·읽기전용 FS·NFS ACL) | warn-only + report에 노트. exit 0 (권한 실패가 wiki 내용 손실로 이어지지 않음) |
| **frontmatter parse error (N건)** | 해당 page skip + report 에 건수·패턴 기록. **exit 0** (다음 cycle 재시도). 규모와 무관하게 skip-and-continue — 대량 오류를 한 회차에 자동 수정하려 시도하지 않는다 (issue #167 재발 방지) |
| **판단 보류 항목 (보고만)** | 자동 적용 금지. `## 보고만 (승인 대기)` 에 기록만 하고 **exit 0**. 매 cycle 동일 항목이 반복되어도 회차마다 재판단하지 않는다 — §Step 8.1 의 이월 규칙을 따른다 |
| **`referenced_by:` 가 빈 값** | 자동 등록·archive **모두 금지**. 보고만. `''` 은 리스트 0건과 의미가 다르므로 Step 7 archive 조건에 포함하지 않는다 |
| **append-only 파일의 미치환 플레이스홀더** | 보고만. 접두 보존이 원칙이므로 자동 수정 금지. 건수만 계상하고 이월 기록 |
| **sources 본문 한자** | 보고만. vault 원문이므로 ingest 책임 경계 — lint 가 변환하지 않는다 |
| **검출기와 정본 계상 불일치** | 정본 계상을 신뢰하고 헬퍼 계상은 인용하지 않는다. 불일치 사실을 report 에 1줄 기록 (정본 수치를 함께 적음) |

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
