# Analysis & Design — profile_timeout_override

---

## 배경 및 목적

graphify timeout이 백엔드(ollama vs cloud) 구분 없이 단일 `operations.graphify_timeout_sec` 값(기본 900s)으로 적용되어, ollama(로컬 LLM, wiki 200+ 페이지에서 30분+)와 cloud API(수분) 간 latency 차이를 반영하지 못함.

**해결**: profile-level timeout override 도입. 우선순위 체인:
1. `operations.graphify_profiles.<profile>.timeout_sec` (profile-specific, 신규 yaml dict)
2. `operations.graphify_timeout_sec` (global override, 기존)
3. `900` (default, 기존)

## 현행 진단

| # | 위치 | 결함 | 영향 |
|---|---|---|---|
| 1 | `scripts/wikihub_graphify.sh:73` | timeout_sec 이 `graphify_timeout_sec` 단일 값만 읽음 | ollama profile (30분+) 과 cloud profile (수분) 에 동일 timeout 적용 → ollama 에서 timeout 남발 또는 cloud 에서 불필요하게 긴 timeout |
| 2 | `wikihub.yaml.example` | `graphify_profiles` dict 예시 부재 | 운영자가 profile-level timeout 설정 방법을 알 수 없음 |
| 3 | `_system/commands/graphify.md:48` | timeout 표에 profile-level override 설명 부재 | 명령어 문서가 timeout 우선순위 체인을 설명하지 않음 |

## 개정 범위

### 1. `scripts/wikihub_graphify.sh` (L73)

#### 변경 성격: timeout_sec 읽기 로직 — profile-specific 우선 조회 추가

**Before:**
```bash
timeout_sec="$(yq '.operations.graphify_timeout_sec // 900' "$WIKIHUB_YAML")"
```

**After:**
```bash
timeout_sec="$(yq ".operations.graphify_profiles.\"${profile}\".timeout_sec // .operations.graphify_timeout_sec // 900" "$WIKIHUB_YAML")"
```

**yq fallback chain 설명:**
1. `.operations.graphify_profiles.<profile>.timeout_sec` — profile-specific 값 조회 (신규)
2. `.operations.graphify_timeout_sec` — global override (기존)
3. `900` — hardcoded default (기존)

**주의사항:**
- yq string interpolation: `"${profile}"` 은 bash 변수 치환. yq 내부에서 `.<profile>` 이 아닌 `."${profile}"` 사용 (profile 명에 하이픈 등 특수문자 대비 — 현재 profile regex `^[a-z][a-z0-9_]*$` 에서는 불필요하지만 defense-in-depth).
- `//` chain: yq 의 alternative operator. null/미설정 시 다음 단계로 fallback. `graphify_timeout_sec` 자체가 미설정이면 900 으로 최종 fallback.
- 기존 동작 보존: `graphify_profiles` 미사용 시 (대부분의 현재 환경) L1 → null → L2 (`graphify_timeout_sec` 또는 900) 로 동일 동작.

### 2. `wikihub.yaml.example` (L59 이후)

#### 변경 성격: `graphify_profiles` dict 예시 추가

**Before (L55-59):**
```yaml
  # ADR-0036 — graphify CLI (PyPI graphifyy):
  graphify_min_version: "0.8.0"       # install.sh `_install_graphify` 의 min (v0.1.0 documentation only — 실 enforce 는 v0.2.x)
  graphify_max_version: "0.99.99"     # ADR-0036 breaking change 방어
  graphify_backend: ollama            # graphify --backend = protocol (graphify CLI 의 코드 경로). v8 backends: gemini | kimi | claude | openai | deepseek | ollama. ADR-0036 §Note (2026-05-24, v0.1.7 follow-up) — `ollama` backend 는 endpoint 형식 자동 분기 (loopback → native OLLAMA_HOST API, 외부 → OLLAMA_BASE_URL OpenAI-compat).
  graphify_profile: ollama_gemma      # endpoint+key+model bundle 선택자. env 의 WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL> 와 1:1 매칭 (ADR-0038, v0.1.7 follow-up). 다중 profile 동시 보유 + yaml 한 줄 swap. 기본 ollama_gemma = local Ollama daemon + gemma4:31b-cloud. 추가 profile cookbook → docs/graphify-backend-test-reference.md §6.
```

**After (L55 이후):**
```yaml
  # ADR-0036 — graphify CLI (PyPI graphifyy):
  graphify_min_version: "0.8.0"       # install.sh `_install_graphify` 의 min (v0.1.0 documentation only — 실 enforce 는 v0.2.x)
  graphify_max_version: "0.99.99"     # ADR-0036 breaking change 방어
  graphify_backend: ollama            # graphify --backend = protocol (graphify CLI 의 코드 경로). v8 backends: gemini | kimi | claude | openai | deepseek | ollama. ADR-0036 §Note (2026-05-24, v0.1.7 follow-up) — `ollama` backend 는 endpoint 형식 자동 분기 (loopback → native OLLAMA_HOST API, 외부 → OLLAMA_BASE_URL OpenAI-compat).
  graphify_profile: ollama_gemma      # endpoint+key+model bundle 선택자. env 의 WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL> 와 1:1 매칭 (ADR-0038, v0.1.7 follow-up). 다중 profile 동시 보유 + yaml 한 줄 swap. 기본 ollama_gemma = local Ollama daemon + gemma4:31b-cloud. 추가 profile cookbook → docs/graphify-backend-test-reference.md §6.
  graphify_profiles:                  # (v0.1.10) profile-level timeout override. graphify_timeout_sec 보다 우선. 미설정 시 global → 900 fallback. Issue #36.
    ollama_gemma:
      timeout_sec: 1800               # ollama local LLM (gemma4:31b-cloud) — wiki 200+ 페이지 시 30분+ 소요. cloud profile 은 미설정 시 global 900s 사용.
```

**`_migrate_agent_schema` 영향 분석:**
- `_migrate_agent_schema` (install.sh:836-843) 는 `operations` + `agent` top-level dict 의 key 를 yaml.example 과 sync.
- `graphify_profiles` 가 `operations` 하위 dict 이므로, 기존 yaml 에 없으면 자동 추가됨.
- **depth 한계**: sync 는 top-level key 만 (`for k in example_top`). `graphify_profiles` dict 내부의 `ollama_gemma.timeout_sec` 까지는 자동 추가 안 됨 — dict 자체가 통째로 추가됨.
- **실제 영향**: 기존 운영 yaml 에 `graphify_profiles` 자체가 없으므로, `_migrate_agent_schema` 가 yaml.example 의 `graphify_profiles` dict 를 deepcopy 하여 추가. 이는 `ollama_gemma: {timeout_sec: 1800}` 을 포함한 전체 dict 가 추가됨 = **의도대로 동작** (기본 profile 에 대한 timeout override 자동 적용).
- **install.sh 변경 불필요**: yaml.example 에만 추가하면 `_migrate_agent_schema` 가 자동 처리.

### 3. `_system/commands/graphify.md` (L41-49)

#### 변경 성격: timeout 우선순위 체인 표 추가 + backend/profile 별 timeout 설명 보강

**Before (L41-49):**
```markdown
## backend / profile / timeout

| yaml field | 정본 default | 의미 |
|---|---|---|
| `operations.graphify_enabled` | `true` | false 시 lint Step 9 가 graphify trigger 안 함 (운영자 cost / API key 부재 대응) |
| `operations.graphify_backend` | `""` (auto-detect 또는 명시) | `ollama` / `openai` / `claude` / `gemini` / `deepseek` / `kimi` 중 하나 |
| `operations.graphify_profile` | `ollama_gemma` | env namespace prefix (lowercase, ^[a-z][a-z0-9_]*$) — ADR-0038 |
| `operations.graphify_timeout_sec` | `900` (15분) | graphify CLI wrapper timeout — ADR-0036 §"후속 영향" |
| `operations.graphify_partial_failure_threshold` | `0.5` | N/M ratio threshold (Pass 3 silent partial failure 가드) |
| `operations.graphify_min_version` / `graphify_max_version` | `0.8.0` / `0.99.99` | graphify CLI 버전 범위 |
```

**After (L41-):**
```markdown
## backend / profile / timeout

| yaml field | 정본 default | 의미 |
|---|---|---|
| `operations.graphify_enabled` | `true` | false 시 lint Step 9 가 graphify trigger 안 함 (운영자 cost / API key 부재 대응) |
| `operations.graphify_backend` | `""` (auto-detect 또는 명시) | `ollama` / `openai` / `claude` / `gemini` / `deepseek` / `kimi` 중 하나 |
| `operations.graphify_profile` | `ollama_gemma` | env namespace prefix (lowercase, ^[a-z][a-z0-9_]*$) — ADR-0038 |
| `operations.graphify_profiles.<profile>.timeout_sec` | (미설정) | **(v0.1.10)** profile-specific timeout. 지정 시 `graphify_timeout_sec` 보다 우선. Issue #36. |
| `operations.graphify_timeout_sec` | `900` (15분) | graphify CLI wrapper timeout — ADR-0036 §"후속 영향". profile-specific 미설정 시 fallback. |
| `operations.graphify_partial_failure_threshold` | `0.5` | N/M ratio threshold (Pass 3 silent partial failure 가드) |
| `operations.graphify_min_version` / `graphify_max_version` | `0.8.0` / `0.99.99` | graphify CLI 버전 범위 |

**timeout 우선순위 체인** (v0.1.10, Issue #36):

```
graphify_profiles.<profile>.timeout_sec  →  graphify_timeout_sec  →  900
       (profile-specific)                    (global override)      (default)
```

- **ollama (로컬 LLM)**: wiki 200+ 페이지 시 30분+ 소요. `graphify_profiles.ollama_gemma.timeout_sec: 1800` 권장.
- **cloud API (openai/claude/gemini/deepseek/kimi)**: 수분. profile-specific 설정 없으면 global 900s 충분.
- **미설정 시**: `graphify_profiles` 자체를 생략하면 기존 동작 (global → 900) 과 100% 동일.
```

## 개정 전/후 비교

### Before (현재)

```
wikihub_graphify.sh:
  timeout_sec = graphify_timeout_sec (yaml) || 900 (hardcoded)
  → 모든 profile 에 동일 timeout 적용
  → ollama_gemma (로컬 LLM, 30분+) 에서 timeout 남발 가능
  → cloud profile (수분) 에서 불필요하게 긴 900s timeout

wikihub.yaml.example:
  graphify_profiles 필드 부재
  → 운영자가 profile-level timeout 설정 방법을 알 수 없음

graphify.md:
  timeout 표에 profile-level override 설명 부재
  → 명령어 문서가 timeout 우선순위를 설명하지 않음
```

### After

```
wikihub_graphify.sh:
  timeout_sec = graphify_profiles.<profile>.timeout_sec (yaml)
             || graphify_timeout_sec (yaml)
             || 900 (hardcoded)
  → profile-specific timeout 적용 가능
  → ollama_gemma 에 timeout_sec: 1800 설정 시 30분 허용
  → cloud profile 은 미설정 시 global 900s fallback

wikihub.yaml.example:
  graphify_profiles.ollama_gemma.timeout_sec: 1800 예시 추가
  → 운영자가 profile-level timeout 설정 방법 즉시 파악

graphify.md:
  timeout 우선순위 체인 표 + backend 별 timeout 권장 설명
  → 명령어 문서가 timeout 우선순위를 명확히 설명

install.sh (_migrate_agent_schema):
  변경 없음 — yaml.example sync 로 graphify_profiles 자동 추가
```

## 연계 룰/스킬 정합성 검토

| 영역 | 영향 | 처리 |
|---|---|---|
| ADR-0036 (graphify CLI integration) | timeout override chain 추가. 결정 변경 없음 (operational parameter 세분화) | §"후속 영향" 1줄 add |
| ADR-0038 (env namespace isolation) | profile-level timeout 은 env namespace 와 독립 (yaml dict). env 변경 없음 | 무영향 |
| `scripts/wikihub_graphify.sh` | L73 timeout_sec 읽기 로직만 변경. profile env bundle resolve (L82-89) 무변경 | yq 쿼리 변경 |
| `_system/systemd/wikihub-graphify.service.template` | systemd unit 변경 없음 | 무영향 |
| `_system/commands/lint.md` | graphify timeout 미참조 | 무영향 |
| `install.sh` `_migrate_agent_schema` | yaml.example sync 로 graphify_profiles 자동 추가. install.sh 코드 변경 없음 | 무영향 (자동) |

## 미결 사항

없음. 모든 미결이 본 design 에서 해소:
1. `graphify_profiles` dict scope → timeout_sec 만 (Atomic Change 원칙, 향후 확장 시 dict 구조 자연스러움)
2. ADR 신설 불필요 → ADR-0036 §"후속 영향" 1줄 add 만으로 충분

## Definition of Done

- [ ] **D1**: `scripts/wikihub_graphify.sh` L73 — profile-specific timeout 우선 조회 로직 (yq 3단 fallback chain)
- [ ] **D2**: `wikihub.yaml.example` L59 이후 — `graphify_profiles.ollama_gemma.timeout_sec: 1800` 예시 추가
- [ ] **D3**: `_system/commands/graphify.md` — timeout 우선순위 체인 표 + profile 별 timeout 설명 행 추가
- [ ] **D4**: `docs/adr/0036-graphify-cli-integration.md` §"후속 영향" 1줄 add (Issue #36 timeout override)
- [ ] **D5**: `_migrate_agent_schema` 영향 분석 — yaml.example sync 로 충분 (install.sh 변경 불필요) 확인
- [ ] **D6**: yq 쿼리 동작 검증 — (1) profile 미설정 시 global fallback, (2) profile 설정 시 profile-specific 값, (3) 둘 다 미설정 시 900

## 참조

- [plan.md](plan.md)
- [scripts/wikihub_graphify.sh](../../scripts/wikihub_graphify.sh) (변경 대상 — L73)
- [wikihub.yaml.example](../../wikihub.yaml.example) (변경 대상 — L59 이후)
- [_system/commands/graphify.md](../../_system/commands/graphify.md) (변경 대상 — L41-49)
- [docs/adr/0036-graphify-cli-integration.md](../../docs/adr/0036-graphify-cli-integration.md) (§"후속 영향" add 대상)
- [install.sh](../../install.sh) `_migrate_agent_schema` L795+ (변경 없음 — 영향 분석만)
