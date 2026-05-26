# Analysis & Design — graphify_path_absolute

approved: 2026-05-26

---

## 배경 및 목적

OCI 운영 중 발견 — wh-lint cycle 이 0 edges 보고. 진단 결과:

- 정상 graph: `$WIKIHUB_HOME/graphify-out/graph.json` (262 nodes, 131 edges)
- Stale graph: `$WIKIHUB_HOME/wiki/graphify-out/graph.json` (934 nodes, 826 edges, 2026-05-24 생성, 4.6MB)
- wh-lint skill 이 stale 을 읽고 동작 → 회귀

**근본 원인**: `_system/commands/lint.md` 의 graph.json 참조가 **상대 경로** (`graphify-out/graph.json`). wh-lint skill (LLM) 의 CWD context 가 wiki/ 로 implicit drift (playbook 의 대부분 path 가 `wiki/sources/...` 등 wiki-relative) → 상대 경로가 `$WIKIHUB_HOME/wiki/graphify-out/graph.json` 으로 잘못 resolution.

**OCI 에서 적용된 runtime fix** (사용자 직접 patch, source code 미반영):
1. Step 3 그래프 경로 절대화 (`$WIKIHUB_HOME/graphify-out/graph.json`)
2. 사전 조건 경로 주의 경고
3. Step 7 stale `wiki/graphify-out/` 정리 로직
4. Edge 파싱 키 호환 (`d.get('links', d.get('edges', []))` — graphify v0.8+)
5. `references/graph-path-resolution.md` reference doc

본 feature 가 위 5 항목을 source code 에 반영 + defense-in-depth 추가.

## 현행 진단

| # | 위치 | 결함 | 영향 |
|---|---|---|---|
| 1 | `_system/commands/lint.md:20` (사전 조건) | `(선택) graphify-out/graph.json` 상대 경로 | LLM CWD drift 시 wiki/ 기준 resolution |
| 2 | `_system/commands/lint.md:63` (Step 3 intro) | `graphify-out/graph.json 있으면 사용` 상대 경로 | 동상 |
| 3 | `_system/commands/lint.md:238` (Step 9 fire-and-forget) | `graphify-out/graph.json 으로 surface` 상대 경로 | LLM context 일관성 |
| 4 | `_system/commands/lint.md:61` (Step 3) | edge 파싱 key 미명시 — graphify v0.7 (`edges`) vs v0.8+ (`links`) | graphify upgrade 시 silent break |
| 5 | `_system/commands/lint.md:17-20` (사전 조건) | `wiki/graphify-out/` stale dir 감지 안내 부재 | 운영자가 결함 진단 어려움 |
| 6 | `_system/commands/lint.md:150` (Step 7) | stale dir cleanup 책임 미정의 | stale 잔존 → 다음 cycle 도 회귀 위험 |
| 7 | `_system/commands/lint.md:174` (Step 8 report.md format) | stale cleanup 항목 보고 형식 부재 | 운영자 가시성 0 |
| 8 | `_system/templates/wiki/.graphifyignore` | `graphify-out/` 미포함 | graphify CLI 가 자기 출력 (있을 시) 을 input 으로 재scan 가능 |
| 9 | `docs/references/` | 디렉토리 자체 부재 | reference doc 정착 위치 없음 |
| 10 | `docs/adr/0036-graphify-cli-integration.md` | 본 fix 의 §"후속 영향" cross-ref 부재 | ADR 결정 trail 미보존 |

## 개정 범위

### `_system/commands/lint.md` (단일 파일, 5+ 위치)

#### 위치 1 — 사전 조건 (L17-20)

**Before:**
```
- `wikihub.yaml` 존재
- wiki/ 디렉토리 + 4 카테고리(`sources/`, `entities/`, `concepts/`, `analyses/`) + `_lint/` 존재 (없으면 생성 — 본 명령이 자동)
- (선택) `graphify-out/graph.json` — 있으면 그래프 기반 점검, 없으면 wiki 순회
```

**After:**
```
- `wikihub.yaml` 존재
- wiki/ 디렉토리 + 4 카테고리(`sources/`, `entities/`, `concepts/`, `analyses/`) + `_lint/` 존재 (없으면 생성 — 본 명령이 자동)
- (선택) `$WIKIHUB_HOME/graphify-out/graph.json` — 있으면 그래프 기반 점검, 없으면 wiki 순회. **절대 경로 사용 필수** — wh-lint skill 의 CWD context 가 wiki/ 로 drift 가능 → 상대 경로 시 stale `wiki/graphify-out/` 읽기 회귀 위험 ([graph-path-resolution.md](../../docs/references/graph-path-resolution.md) 참조).
- **stale 감지**: `$WIKIHUB_HOME/wiki/graphify-out/` 존재 시 (legacy 또는 잘못된 graphify 호출 경로 잔존) → Step 7 cleanup + Step 8 보고. lint 가 이 디렉토리를 graph source 로 읽지 않음.
```

#### 위치 2 — Step 3 (L61-63)

**Before:**
```
### Step 3. 그래프 기반 점검 (자동)

`graphify-out/graph.json` 있으면 사용, 없으면 wiki 순회로 폴백:
```

**After:**
```
### Step 3. 그래프 기반 점검 (자동)

`$WIKIHUB_HOME/graphify-out/graph.json` (**절대 경로**) 있으면 사용, 없으면 wiki 순회로 폴백:

**graphify schema 호환 (v0.7 → v0.8+ migration)**: graph.json 의 edge 키가 v0.7 = `edges`, v0.8+ = `links` 로 변경됨. parsing 시 `d.get('links', d.get('edges', []))` 패턴으로 양쪽 호환.
```

#### 위치 3 — Step 7 (L150)

Step 7 본문 끝에 새 bullet 추가:

```
- **stale `wiki/graphify-out/` cleanup (v0.1.10)**: `$WIKIHUB_HOME/wiki/graphify-out/` 존재 감지 시 → `$WIKIHUB_HOME/graphify-out/.archived/wiki-graphify-out-<utc_iso>/` 로 이동 (recoverable archive, 삭제 안 함). 본 디렉토리는 graphify CLI 의 잘못된 호출 (pre-v0.1.8 era 또는 운영자 manual 호출 시 `--out` 누락) 잔존물. archive 후 lint 가 다시 stale 을 source 로 읽지 않음.
```

#### 위치 4 — Step 8 보고 형식 (L174 이후)

report.md 예시에 새 섹션 추가:

```markdown
## Stale cleanup (v0.1.10 — graph_path_resolution)
- `wiki/graphify-out/` (934 nodes, 826 edges, 2026-05-24 생성, 4.6MB) → `graphify-out/.archived/wiki-graphify-out-20260526T093000Z/` 이동
```

#### 위치 5 — Step 9 fire-and-forget reference (L238)

**Before:**
```
graphify 결과는 `wikihub-graphify.service` 의 별도 journal + `graphify-out/graph.json` 으로 surface.
```

**After:**
```
graphify 결과는 `wikihub-graphify.service` 의 별도 journal + `$WIKIHUB_HOME/graphify-out/graph.json` 으로 surface.
```

### `_system/templates/wiki/.graphifyignore`

**Before:**
```
_lint/
_state/
**/log.md
```

**After:**
```
_lint/
_state/
**/log.md

# Defense-in-depth (2026-05-26, graph_path_resolution feature) — graphify CLI 의 잘못된
# 호출 (--out wiki) 시 자기 출력을 input 으로 재scan 회피. 정상 graphify 호출은
# scripts/wikihub_graphify.sh 가 --out $WIKIHUB_HOME 명시 → wiki/graphify-out/ 미생성.
graphify-out/
```

### `docs/references/graph-path-resolution.md` (신규)

이슈 분석 + 판별법 + 정합 경로 catalog. 운영자가 OCI 에서 동일 결함 재발 시 진단 가이드.

내용 outline:
- 이슈 요약 (2026-05-26 OCI 발견)
- 근본 원인 (wh-lint skill 의 CWD drift)
- 진단 명령 (`find` / `ls` / `wc -l` 등)
- 정합 경로 catalog (Where graphify writes / Where lint reads / 정상 vs stale 구분)
- recovery 절차 (archive 이동 + lint cycle 재실행)
- 본 feature (graph_path_resolution) 의 fix 가 회귀 차단

### `docs/adr/0036-graphify-cli-integration.md`

§"후속 영향" 끝에 1줄 추가:

```
- 2026-05-26 (graphify_path_absolute feature): wh-lint playbook 의 graph.json 참조 절대 경로 정합화 + stale `wiki/graphify-out/` cleanup 책임 lint Step 7 신규. OCI 운영 실증 fix. ADR 결정 변경 없음 (implementation hardening). references/graph-path-resolution.md 진단 가이드 신설.
```

## 개정 전/후 비교

### Before (OCI 결함 발생 가능)

```
wh-lint skill (LLM, CWD context = wiki/ implicit):
  - `graphify-out/graph.json` 읽기 시도 → $WIKIHUB_HOME/wiki/graphify-out/graph.json 으로 resolution
  - stale 934 nodes/826 edges 읽음 → 0 edges 잘못 보고 (또는 entity 누락)

wiki/graphify-out/ 잔존 (v0.1.7 이전 era 또는 잘못된 graphify --out 호출):
  - 영구 잔존 — lint cycle 이 cleanup 책임 없음
  - 매 cycle 동일 회귀

`.graphifyignore`:
  - _lint/, _state/, **/log.md 만 제외
  - graphify CLI 가 wiki/graphify-out/ 를 input 으로 재scan 시 noise (graphify 가 자기 출력을 dependency 로 인식 위험)
```

### After

```
wh-lint skill (LLM):
  - `$WIKIHUB_HOME/graphify-out/graph.json` 명시 → CWD-independent absolute resolution
  - graphify v0.7 (edges) / v0.8+ (links) schema 양쪽 호환

wiki/graphify-out/ 감지 시 (legacy 잔존):
  - lint Step 7 가 매 cycle automatic detect + archive 이동
  - report.md (Step 8) 에 cleanup 항목 명시 → 운영자 가시성

`.graphifyignore`:
  - graphify-out/ 추가 — graphify CLI 가 자기 출력 input 재scan 회귀 차단 (defense-in-depth)

docs/references/graph-path-resolution.md:
  - 운영자 진단 가이드 — 동일 결함 재발 시 즉시 판별 가능
```

## 연계 룰/스킬 정합성 검토

| 영역 | 영향 | 처리 |
|---|---|---|
| ADR-0036 (graphify CLI integration) | implementation hardening 추가, 결정 변경 없음 | §"후속 영향" 1줄 add |
| ADR-0033 (skill prefix lock) | wh-lint skill 의 playbook 변경 (Step 3/7/8 보강) — skill prefix 미변경 | 무영향 |
| ADR-0041 (systemd prefix realign) | systemd unit 변경 없음 | 무영향 |
| `_system/skills/wh-lint.frontmatter.yaml` | skill metadata 무변경 (playbook 본문만 변경) | 무영향 |
| `scripts/wikihub_graphify.sh` | `--out "$WIKIHUB_HOME"` 절대 경로 이미 정합 | 무영향 |
| `_system/systemd/wikihub-{lint,graphify}.service.template` | `WorkingDirectory={wikihub_home}` 정합 | 무영향 |
| `_system/commands/graphify.md` | L59-61 이미 `$WIKIHUB_HOME/graphify-out/` 절대 경로 정합 | 무영향 |
| `_system/commands/ingest.md` | graph.json 미참조 | 무영향 |

## 미결 사항

없음. 3 Open Question (plan.md) 모두 본 design 에서 해소:
1. Step 4 review 생략 → plan.md 에서 잠정 생략 선언, Step 3 완료 후 사용자 재확인
2. `docs/references/` 디렉토리 신설 → 본 feature 가 첫 도입 위치 (operator 진단 가이드 정착처)

## Definition of Done

- [ ] **D1**: `_system/commands/lint.md` 5 위치 절대 경로 (L20, L63, L238)
- [ ] **D2**: lint.md Step 3 — graphify schema 호환 (`links`/`edges`) 명시
- [ ] **D3**: lint.md Step 7 — stale `wiki/graphify-out/` cleanup 로직 추가
- [ ] **D4**: lint.md Step 8 — report.md 보고 형식 stale cleanup 섹션 추가
- [ ] **D5**: lint.md 사전 조건 — 경로 주의 + stale 감지 안내
- [ ] **D6**: `_system/templates/wiki/.graphifyignore` — `graphify-out/` 추가
- [ ] **D7**: `docs/references/graph-path-resolution.md` 신설
- [ ] **D8**: `docs/adr/0036-graphify-cli-integration.md` §"후속 영향" 1줄 add
- [ ] **D9**: pytest 57 pass / 1 skip 불변
- [ ] **D10**: grep verify — `graphify-out/graph.json` 단독 (절대 경로 prefix 없는) ref 0건 in `_system/commands/lint.md`
- [ ] **D11**: HISTORY.md append (Step 5 squash 시점 — 본 feature + monitor_services_remove + systemd_prefix_realign 통합 entry)

## 참조

- [plan.md](plan.md)
- [_system/commands/lint.md](../../_system/commands/lint.md) (변경 대상)
- [_system/commands/graphify.md](../../_system/commands/graphify.md) (참조 — 이미 정합)
- [scripts/wikihub_graphify.sh](../../scripts/wikihub_graphify.sh) (참조 — 이미 정합)
- [docs/adr/0036-graphify-cli-integration.md](../../docs/adr/0036-graphify-cli-integration.md) (§Note add 대상)
