# ADR-0042: alias-aware wiki link resolver — frontmatter `aliases` 기반 canonical page 매핑

- **Status**: Accepted
- **Date**: 2026-05-28
- **Feature**: issue #37 (출처: ADR-0039 §재검토 트리거, L99)
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

ADR-0039 (`entity/concept alias frontmatter`) 가 v0.1.8 에서 entity/concept page 의 frontmatter 에 `aliases: [<form1>, ...]` 필드를 도입했다. 본 필드는 **duplicate detection** (lint Step 4.5) 과 **LLM 재생성 무한 loop 차단** (ingest / lint stub 생성 가드) 에만 사용된다.

그러나 wiki 본문의 `[[link]]` resolver 는 alias 를 인식하지 않는다 — `[[mini-max]]` 가 `aliases: [MiniMax, mini-max, minimax]` 를 보유한 `entities/MiniMax.md` 로 자동 resolve 되지 않고 dangling 으로 처리된다. ADR-0039 §재검토 트리거 (L99) 에서 본 항목을 별도 ADR 로 위임했다.

운영 시나리오:
- ingest LLM 이 source 본문의 변형 form (`mini-max`) 을 `[[link]]` 으로 작성 — 현재는 dangling
- 운영자가 의도된 alias form 으로 `[[link]]` 작성 — 현재는 dangling
- alias 페이지 수가 누적될수록 link 정합성 저하 가시화

또한 ADR-0039 §Considered Options (δ) — "wiki link resolver case-insensitive" — 는 Linux filesystem 의 case-sensitivity 와 충돌해 데이터 정합 깨짐 위험으로 기각됐다. **frontmatter `aliases` 기반 resolver** 가 본 ADR 의 정공법.

## Considered Options

- **(α) alias index 자동 구축 + 2-pass resolve**: lint 가 wiki/entities + wiki/concepts 의 모든 frontmatter `aliases` 를 lowercase normalize 한 inverted index (`Dict[lowercase_alias, canonical_filename]`) 빌드. resolver 가 `[[<name>]]` 을 받으면 (1) case-sensitive exact match (`<category>/<name>.md` 존재) → 그 페이지, (2) 부재 시 alias index 에 `lowercase(name).strip()` lookup → 매핑 canonical 페이지로 resolve, (3) 둘 다 부재 → dangling.
- **(β) alias redirect stub 자동 생성**: 각 alias 별로 별도 `.md` redirect page 자동 생성 (예: `entities/mini-max.md` → frontmatter `redirect_to: MiniMax`). filesystem 직접 일치라 resolver 무변경. 단점: 페이지 수 폭증 (alias 당 1 파일) + redirect chain 처리 복잡 + frontmatter 새 필드 (`redirect_to`) 도입.
- **(γ) resolver 호출 시점 매 회 wiki 전수 frontmatter 스캔**: index cache 없이 매 resolve 마다 wiki/entities + wiki/concepts frontmatter scan. 단점: O(N) per resolve — wiki 페이지 수 증가 시 lint cycle latency 증가.

> 옵션 상세 비교는 issue #37 본문 §제안 해결 방향 참조.

## Decision

**채택**: (α) alias index 자동 구축 + 2-pass resolve

**알고리즘 정본**:

```python
def build_alias_index(wiki_root: Path) -> dict[str, str]:
    """wiki/entities + wiki/concepts 전수 스캔 → {lowercase_alias: canonical_name}."""
    index: dict[str, str] = {}
    for category in ("entities", "concepts"):
        for page_path in (wiki_root / category).glob("*.md"):
            canonical = page_path.stem   # 파일명 (확장자 제외) = canonical
            fm = read_frontmatter(page_path)
            for alias in (fm.get("aliases") or [canonical]):
                key = alias.strip().lower()
                if key in index and index[key] != canonical:
                    # alias 충돌 — lint Step 4.5 duplicate detection 책임
                    continue
                index[key] = canonical
    return index


def resolve_link(name: str, category: str, wiki_root: Path,
                 alias_index: dict[str, str]) -> Path | None:
    """case-sensitive exact match → alias index lookup → dangling."""
    exact = wiki_root / category / f"{name}.md"
    if exact.is_file():
        return exact
    key = name.strip().lower()
    canonical = alias_index.get(key)
    if canonical:
        return wiki_root / category / f"{canonical}.md"
    return None
```

**규약**:
- **resolver scope**: `category ∈ {entities, concepts}` 만. sources 는 ADR-0001 정합 — vault-prefix 필수 + 단축형 금지라 alias 개념 없음. sources `[[link]]` 는 lint Step 2 의 기존 위반 1/2/3 path 그대로.
- alias index 는 **lint cycle 시작 시 1회 build** — Step 1 (디렉토리 검증) 이후 Step 2 진입 전. **소비자**: Step 2 dangling 검사 (resolver 호출 site). Step 4.5 duplicate detection 은 별도 subprocess (`detect_alias_duplicates.py`) 가 wiki 를 자체 스캔 — 본 index 와 독립 (alias 충돌 보고 책임 분담).
- alias `aliases[0]` 는 ADR-0039 정합 — canonical name (= 파일명 stem) 과 일치. 부재 시 lint 가 자동 보강 (Step 4.5 alias migration).
- alias 충돌 (같은 lowercase form 의 2+ canonical) 시 index build 가 무시 + lint Step 4.5 가 duplicate 로 보고 — resolver 가 충돌 임시 처리 책임 지지 않음.
- resolver 결과 dangling 시 Step 2 가 보고. Step 7 sed 치환 (variant→canonical) 은 명시적 카테고리 prefix link 만 매칭 — 단축형 `[[<name>]]` 의 자동 정정은 resolver 가 alias 인식하므로 dangling 안 됨 → 정정 불필요.

**이유**:
- frontmatter 기반 — ADR-0039 데이터 모델 그대로 활용 (신규 필드 없음).
- lint cycle 1회 build → resolver O(1) lookup (B/C 옵션 대비 cost gate).
- alias redirect page 폭증 회피 — wiki 페이지 수 inflation 0.
- case-sensitivity 유지 — filesystem invariant 보존 (ADR-0039 의 δ 기각 사유 회피).

## Consequences

- **긍정**:
  - `[[mini-max]]` 같은 alias form link 가 `MiniMax.md` 로 자동 resolve — dangling 보고 0 (alias 셋에 등록된 form 한정).
  - 운영자/LLM 이 본문 자연 표기로 link 작성 가능 — wiki UX 개선.
  - duplicate detection (Step 4.5) 와 같은 frontmatter 정본 사용 → 정합성 보장.
  - Step 7 sed 치환의 단축형 case 가 사실상 무용 — resolver 가 처리 → 코드 단순화 가능 (별도 작업).

- **부정/제약**:
  - lint cycle 시작 시 wiki/entities + wiki/concepts 전수 frontmatter read 비용 (페이지 수 N 에 대해 O(N)) — 일반 운영 규모 (수십~수백 페이지) 에서 무시 가능.
  - alias index build 실패 (frontmatter 파싱 오류 등) 시 resolver fallback 정책 필요 — exact match 만 사용 (degraded mode) 후 lint Step 4.5 가 frontmatter 결함 보고.
  - alias 충돌 (2+ canonical 이 같은 lowercase alias) 시 resolver 결과 비결정 (build 순서 의존) — Step 4.5 가 duplicate 보고 + 운영자 수동 정정 책임. resolver 자체는 안전 (충돌 무시 + build 시 첫 등록 유지).
  - **첫 cycle (aliases 부재 page) 동작**: ADR-0039 Step 4.5 가 부재 frontmatter 를 `aliases: [<canonical>]` 으로 auto-migrate 하지만 그 단계는 Step 4.5 — Step 1.5 보다 늦음. 첫 cycle 의 Step 1.5 는 `(fm.get("aliases") or [canonical])` fallback 으로 canonical 자체를 alias 로 등록 → exact match 시나리오만 cover (alias form link 는 dangling). Step 4.5 migration 완료 후 다음 cycle 부터 정상 동작 — 운영 영향 0 (점진 수렴).
  - **ingest LLM prompt 무영향**: ingest 가 본문 form 으로 `[[link]]` 작성 가능 — resolver 가 alias 매핑 처리. ADR-0039 의 ingest stub 가드 (alias 셋 기반 skip) 그대로 유지.
  - **graphify CLI 의 alias 인식 여부는 외부 도구 책임**: lint Step 9 graphify chain 이 호출하는 외부 CLI 가 `[[link]]` 를 어떻게 node 매핑하는지는 wikihub 책임 밖. 본 ADR 은 lint Step 2 resolver 만 다룬다.

- **후속 영향**:
  - **lint Step 2 dangling 검사**: 단순 파일 존재 검사 → `resolve_link()` 호출로 교체. alias-aware dangling 보고.
  - **lint Step 4.5 duplicate detection**: alias index build 시 충돌 발생하면 같은 duplicate 로 보고 (기존 spec 정합).
  - **lint Step 5 index 재구성**: 직접 영향 없음 — index.md 는 페이지 enumeration 만, link resolve 안 함.
  - **wiki-schema.md** `[[link]]` 규약 섹션에 alias resolution 정책 명시 (1 단락 보강).
  - **ADR-0039**: §재검토 트리거의 link resolver 항목 closure — 본 ADR 가 처리. cross-ref 갱신.
  - **재검토 트리거**:
    - alias index 가 N=10k+ 페이지에서 lint latency bottleneck 으로 surface 시 — caching (mtime 기반 incremental rebuild) 도입 검토.
    - alias 충돌 운영 사례가 빈번 surface 시 — 충돌 해소 알고리즘 (e.g. `canonical` 명시 frontmatter 필드) 도입 검토.
