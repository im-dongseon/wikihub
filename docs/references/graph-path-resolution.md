# Reference — graph.json 경로 resolution 정합

**Date:** 2026-05-26
**Related:** [ADR-0036 §"후속 영향"](../adr/0036-graphify-cli-integration.md), [features/20260526_graphify_path_absolute](../../features/20260526_graphify_path_absolute/)
**Trigger:** OCI 운영 중 발견된 wh-lint 의 stale graph 읽기 결함

---

## 이슈 요약

wh-lint cycle 이 graphify-out/graph.json 을 읽고 graph-based 점검을 수행할 때, **상대 경로** `graphify-out/graph.json` 이 wh-lint skill (LLM) 의 implicit CWD context 에 따라 잘못된 위치로 resolution 되는 결함.

### 증상

- wh-lint report.md 에 `edges: 0` 또는 비정상적으로 낮은 edge 수.
- graphify journal 은 정상 — `graph rebuilt: 262 nodes, 131 docs` 등 정상 완료 로그.
- `_state/<vault>/last_failure.json` 부재 — fatal alert 발화 안 함.
- 운영자가 직접 `find $WIKIHUB_HOME -name graph.json` 실행 시 **2 파일** 발견:
  - `$WIKIHUB_HOME/graphify-out/graph.json` (정상, 최신)
  - `$WIKIHUB_HOME/wiki/graphify-out/graph.json` (stale, 더 큰 node/edge count)

### 2026-05-26 발견 사례

- 정상 graph: `$WIKIHUB_HOME/graphify-out/graph.json` (262 nodes, 131 edges, 매 cycle 갱신)
- Stale graph: `$WIKIHUB_HOME/wiki/graphify-out/graph.json` (934 nodes, 826 edges, 2026-05-24 생성, 4.6MB)
- wh-lint 가 stale 을 읽음 → orphan/dangling 진단 결과 회귀

---

## 근본 원인

### CWD drift

wh-lint skill 의 playbook (`_system/commands/lint.md`) 은 wiki-centric:

- Step 2: `wiki/sources/...` 경로의 link 검증
- Step 4.5: `wiki/entities/`, `wiki/concepts/` page list scan
- Step 5: `wiki/index.md` 재구성
- Step 7: `wiki/.archived/<category>/...` 이동

LLM (Hermes 호출 wh-lint skill) 이 playbook 을 따르며 wiki/ 를 작업 컨텍스트로 internalize. `_system/systemd/wikihub-lint.service.template` 의 `WorkingDirectory={wikihub_home}` 은 systemd 단위 CWD 만 보장 — LLM 의 inline subprocess / bash command 호출 시 explicit `cd wiki/` 또는 wiki-relative path 가 흔하게 발생.

결과: 상대 경로 `graphify-out/graph.json` 이 `$WIKIHUB_HOME/wiki/graphify-out/graph.json` 으로 resolution.

### Stale `wiki/graphify-out/` 의 출처

- pre-v0.1.8 era 의 graphify 호출 (graphify CLI 가 `--out` 인자 default 가 CWD 였던 버전 + wh-lint 가 CWD=wiki/ 로 호출)
- 운영자 manual `graphify extract wiki/` 호출 시 `--out` 누락 → output 이 wiki/graphify-out/ 으로 fallback
- pre-v0.1.8 의 `wh-graphify` hermes skill 폐기 시점 (ADR-0036 §"후속 영향" 2026-05-26 update_path_fixes) 의 잔존물

### 비교 — 정상 graphify 호출

`scripts/wikihub_graphify.sh` (ADR-0036 §D6 single-source):

```bash
graphify extract "$WIKIHUB_HOME/wiki" \
    --backend ollama --model "$model" \
    --max-concurrency "$concurrency" --out "$WIKIHUB_HOME"
```

- input: `$WIKIHUB_HOME/wiki` (절대 경로)
- output: `--out "$WIKIHUB_HOME"` → graphify 가 `$WIKIHUB_HOME/graphify-out/` 에 작성
- CWD: `wikihub-graphify.service` 의 `WorkingDirectory={wikihub_home}` = `$WIKIHUB_HOME`

→ 정상 경로 (`$WIKIHUB_HOME/graphify-out/`) 만 생성. `wiki/graphify-out/` 미생성.

---

## 진단 명령

운영자가 OCI 에서 본 결함 재발 의심 시:

### 1. graph.json 위치 확인

```bash
find "$WIKIHUB_HOME" -name 'graph.json' -not -path '*/.archived/*' 2>/dev/null
```

- 정상: 1 파일 (`$WIKIHUB_HOME/graphify-out/graph.json`)
- **결함**: 2+ 파일 (`wiki/graphify-out/graph.json` 동반) → 본 reference 의 cleanup 절차로 진행

### 2. node/edge count 비교

```bash
for f in $(find "$WIKIHUB_HOME" -name 'graph.json' -not -path '*/.archived/*'); do
    n=$(jq -r '.nodes | length' "$f")
    e=$(jq -r '.links // .edges | length' "$f")
    mt=$(stat -c '%y' "$f" 2>/dev/null || stat -f '%Sm' "$f")
    echo "$f → nodes=$n edges=$e mtime=$mt"
done
```

- 정상 graph 가 가장 최근 mtime + 작은 size (수렴된 production graph)
- Stale 이 더 큰 node/edge count + 오래된 mtime → 과거 era 잔존

### 3. wh-lint report.md edge count 확인

```bash
grep -E 'edges|graph' "$WIKIHUB_HOME/wiki/_lint/report.md"
```

- 정상: graphify journal 의 edge count 와 일치
- **결함**: report.md edge=0 또는 graphify journal 보다 큰 수 (stale 읽음 의미)

---

## 정합 경로 catalog

| 항목 | 정합 위치 | 책임 layer | 검증 |
|---|---|---|---|
| graphify 출력 root | `$WIKIHUB_HOME/graphify-out/` | `scripts/wikihub_graphify.sh` 의 `--out "$WIKIHUB_HOME"` | 절대 경로 |
| graph.json | `$WIKIHUB_HOME/graphify-out/graph.json` | graphify CLI 자동 생성 | NetworkX node-link |
| analysis | `$WIKIHUB_HOME/graphify-out/.graphify_analysis.json` | graphify CLI 자동 생성 | community detection |
| manifest | `$WIKIHUB_HOME/graphify-out/manifest.json` | graphify CLI 자동 생성 | run metadata |
| archive | `$WIKIHUB_HOME/graphify-out/.archived/` | wh-lint Step 7 (v0.1.10+) | stale dir recovery |
| **never** here | ~~`$WIKIHUB_HOME/wiki/graphify-out/`~~ | — | stale 잔존 — wh-lint Step 7 cleanup 책임 |

---

## Recovery 절차

`wiki/graphify-out/` 발견 시:

### Option A — wh-lint Step 7 자동 cleanup (v0.1.10+)

`wikihub-lint.timer` 다음 fire 시점에 자동 archive 이동 → recovery 자동. 운영자 개입 불필요.

### Option B — 즉시 수동 archive (운영자가 다음 lint cycle 기다리지 않고)

```bash
utc="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$WIKIHUB_HOME/graphify-out/.archived"
mv "$WIKIHUB_HOME/wiki/graphify-out" \
   "$WIKIHUB_HOME/graphify-out/.archived/wiki-graphify-out-$utc"

# 다음 lint cycle 즉시 trigger (option, fire-and-forget)
systemctl --user start wikihub-lint.service
```

**중요**: `rm -rf` 절대 금지 — archive 이동 (recoverable) 만. graphify Pass 3 의 LLM 호출 비용이 누적된 graph 가 손실되면 재계산 비용 발생.

### Option C — graphify-out/.archived/ 도 누적 정리 필요 시

`graphify-out/.archived/` 디렉토리 자체는 무한 누적. v0.2.x 에서 retention policy 검토 (backlog 항목). 현재는 운영자 수동 정리.

```bash
# 30일 이상 archive 삭제 (운영자 책임)
find "$WIKIHUB_HOME/graphify-out/.archived" -type d -mtime +30 -exec rm -rf {} +
```

---

## 회귀 차단 layer

v0.1.10 (graphify_path_absolute feature) 가 4-layer 회귀 방어 구축:

1. **wh-lint playbook absolute path** — `_system/commands/lint.md` 의 5 위치 `graphify-out/graph.json` 참조 → `$WIKIHUB_HOME/graphify-out/graph.json` 절대 경로. CWD-independent.
2. **wh-lint Step 7 stale cleanup** — `wiki/graphify-out/` 발견 시 자동 archive 이동. legacy 잔존 자가 회복.
3. **`.graphifyignore` defense-in-depth** — `graphify-out/` ignore 추가. graphify CLI 가 자기 출력을 input 으로 재scan 시 noise 차단 (잘못된 manual `--out` 호출 시 안전망).
4. **진단 가이드** — 본 문서. 운영자 자가 진단 + recovery.

---

## graphify schema 호환 노트 (v0.7 → v0.8+)

graphify CLI v0.8 부터 graph.json 의 edge 키가 변경:

- **v0.7-**: `{"nodes": [...], "edges": [...]}`
- **v0.8+**: `{"nodes": [...], "links": [...]}` (NetworkX node-link 표준 정합)

wh-lint playbook (`_system/commands/lint.md` Step 3) 의 edge parsing 은 양쪽 호환:

```python
edges = d.get('links', d.get('edges', []))
```

graphify CLI 버전 transition 중 silent break 회피.

---

## 관련 ADR

- [ADR-0036](../adr/0036-graphify-cli-integration.md) — graphify CLI 통합. §D6 single-source 정합 (정본 위치).
- [ADR-0033](../adr/0033-skill-prefix-hyphen-lock.md) — wh-lint skill 의 namespace 정합.
- [ADR-0041](../adr/0041-systemd-prefix-realign.md) — systemd unit `wikihub-lint.service` namespace.
