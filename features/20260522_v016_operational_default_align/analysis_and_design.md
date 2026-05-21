# Analysis & Design — v016_operational_default_align

approved: 2026-05-22

---

## 분석

### 1. 배경 및 목적

운영자가 v0.1.5 배포 이후 자기 환경 (`~/wikihub/wikihub.yaml` + `~/.hermes/config.yaml` + `~/.config/wikihub/env` + systemd unit) 에서 누적 적용한 운영 결정 (260520·260521 backlog) 이 wikihub repo 의 정본 default 와 일부 mismatch 상태. 새 운영자 / fork / install 직후 사용자가 운영자의 검증된 결정을 자동 전수받지 못함.

본 feature 의 목적: 4건의 정본 default·가이드를 운영 결정에 align + ADR §Note 로 결정 사유 정본화 + README v0.1.x 누적 안내.

### 2. 현행 진단 (결함 목록 및 근거)

| # | 정본 (v0.1.5) | 운영 정본 (verified) | 결함 |
|---|---|---|---|
| 1 | `vaults[].sync_interval_sec: 600` (10분, `wikihub.yaml.example:20`) | 3600 (1h) — 260520 §V + 16:40 KST cycle 1h 간격 verified | 새 운영자 설치 시 ingest mechanical phase 가 10분 cycle → IO·log.md noise 누적. has_changes=false 경로라 LLM cost 는 0 이지만 lsjson + log append 가 6배. |
| 2 | `install.sh:700-718` env template — backend 예시 5건 (Anthropic / OpenAI / ollama-OpenAI-compat / ollama-local / claude-cli) | 운영자가 (현재 minimax-m2.5 ollama-OpenAI-compat 사용 중) 260521 시점 GEMINI 시도 경험 + yaml.example catalog 에 `gemini` 등록 | env template 의 backend 예시 catalog 가 yaml.example catalog 와 비대칭. `graphify_backend: gemini` 선택 시 운영자가 어떤 env var 필요한지 가이드 없음. |
| 3 | hermes config (`~/.hermes/config.yaml`) 의 `delegation.model` 권장값 가이드 부재 | 운영자: `delegation.model: minimax-m2.5` 적용 | wh-lint Step 6 subagent 가 hermes default 모델 fallback 시 한자 섞임·비용·latency 불일치 risk. wikihub install.sh / setup.md 어디에도 권장 안내 없음. |
| 4 | `agent.models.wh-lint: minimax-m2.5` (`wikihub.yaml.example:69`) | `deepseek-v4-flash` (ExecStart verified) | 정본 default 가 운영자 검증 결정과 mismatch. 새 운영자 설치 시 latency 5~10s/call (추정) → 운영자 검증된 fast-response 2.6~6.4s/call 이점 미전수. wh-ingest (`-pro`) 와의 DeepSeek 패밀리·opencode-go backend 일관성도 단절. |

추가 — README (line 5, 11-12, 19, 217-228) 의 버전 표기·로드맵 표 가 v0.1.0 acceptance 기준에 동결. v0.1.1~v0.1.5 의 정본화 항목 (ADR-0035 rclone unify·ADR-0036 graphify·ADR-0037 alert pipeline 등) 미반영 → 본 feature 의 v0.1.6 승격과 함께 직결 부분만 갱신.

### 3. 개정 범위

| 파일 | 변경 성격 | 라인 수 |
|---|---|---|
| `wikihub.yaml.example` | 정본 default 2건 (sync_interval, wh-lint model) + 코멘트 | ~6 |
| `install.sh` | env template GEMINI 블록 + _step8_guide hermes 권장 안내 블록 | ~15 |
| `_system/commands/setup.md` | hermes delegation.model 안내 (Step 1 부속) | ~10 |
| `docs/adr/0032-hermes-skill-registration-policy.md` | §Note 추가 | ~12 |
| `README.md` | 버전 badge + 로드맵 표 v0.1.x 항목 + 개발 상태 1줄 | ~10 |
| `features/HISTORY.md` | v0.1.6 항목 | ~10 |
| `_system/VERSION` | 0.1.5 → 0.1.6 | 1 |
| **합계** | | **~64줄** |

50줄 경계를 약간 넘지만 외부 인터페이스 (스키마·명령어 의미론·공개 API) 미변경 — Step 4 생략 조건 유지 (plan.md 선언 정합).

### 4. 개정 전/후 비교

#### 4.1 `wikihub.yaml.example:20` — sync_interval_sec

**Before**
```yaml
sync_interval_sec: 600     # 10분
```

**After**
```yaml
sync_interval_sec: 3600    # 1h (v0.1.6 default 600 → 3600 — mechanical phase IO·log.md noise 절감, 260520 §V 운영 결정 align). has_changes=false 경로의 LLM cost 는 0 이지만 lsjson + log append cycle 빈도 6배 감소. 변경 detect 지연 (~1h) 트레이드오프 → 운영자가 더 짧게 원하면 600 으로 override.
```

#### 4.2 `install.sh:700-718` env template — GEMINI 블록 추가

**Before** (5개 backend 예시 — 4·5 사이에 신규 6 삽입)

**After** — 신규 블록:
```bash
# 6. Google Gemini (`--backend gemini`, OpenAI-compatible endpoint):
#    GEMINI_API_KEY=...
#    GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
#    GEMINI_MODEL=gemini-2.5-flash-lite
#    # graphify Pass 3 는 content 필드 직접 파싱 → non-reasoning flash-lite 계열 필수 (260521 §F).
```

#### 4.3 `install.sh:1153+` _step8_guide — hermes 권장 안내

**Before** (graphify Pass 3 비용 환기 다음에 신규 블록 삽입)

**After** — 신규 블록:
```
[Hermes config.yaml 권장 (wikihub 정본 영역 외 — 운영자 책임)]
  ~/.hermes/config.yaml 의 다음 필드 권장 설정:
    delegation.model: minimax-m2.5         # wh-lint Step 6 등 subagent 의 non-reasoning 안정성 + 한자→한글 정합
  wh-ingest·wh-lint 메인 모델은 wikihub agent.models 가 systemd `--model` 으로 lock — hermes model.default 무관.
  Telegram 대화·미명시 skill (wh-query·wh-graphify·wh-setup) 의 model.default 는 운영자 일반 선호로 결정.
```

#### 4.4 `wikihub.yaml.example:69` — wh-lint default

**Before**
```yaml
wh-lint: minimax-m2.5      # non-reasoning fast-response (Hermes 실증, 2026-05-20). wiki 전체 LLM 점검 (Step 3·4·5·6) — 한국어 출력 안정성 우선.
```

**After**
```yaml
wh-lint: deepseek-v4-flash # non-reasoning fast-response (latency 2.6~6.4s/call, 260521 §B 측정). wh-ingest (`-pro`) 와 동일 DeepSeek 패밀리 + opencode-go backend 일관성. 한자→한글 출력 안정성은 lint.md 의 "출력 언어 정책" 섹션이 model-agnostic 보호 layer 로 담당. minimax-m2.5 보수적 default 원할 시 운영자 override.
```

#### 4.5 `_system/commands/setup.md` — hermes 권장 안내 부속

setup.md Step 1 (wikihub.yaml 검증) 부분에 hermes config.yaml 의 `delegation.model` 정합 정보 출력 추가 (자동 patch 미수행, warn 만).

#### 4.6 README — 버전·로드맵·개발 상태

- Title `# WikiHub v0.1.0` → `# WikiHub v0.1.6`
- Status badge `v0.1.0%20ready` → `v0.1.6%20ready`
- Version badge `Version-0.1.0` → `Version-0.1.6`
- 개발 상태 line 19 — v0.1.x 누적 1줄 추가
- 로드맵 표 — v0.1.x 항목 row 1줄 추가 (v0.1.1~v0.1.6 묶음 안내)

ADR-0035·0036·0037 일괄 align (Mermaid · F3·F4 description · graphify URL) 은 별도 feature 분리 — 본 feature scope 초과 (plan.md §3 참조).

### 5. 연계 룰/스킬 정합성 검토

| 룰/스킬 | 영향 | 검증 |
|---|---|---|
| `render_systemd_units.py:_per_skill_invocation` | `wh-lint: deepseek-v4-flash` 변경 시 `--model deepseek-v4-flash` 자동 주입 | 이미 동작 검증됨 (운영 ExecStart 와 정합) — 본 feature 변경 없음 |
| `_system/commands/lint.md` 출력 언어 정책 | minimax → deepseek 변경 시 한자→한글 보호 layer 유효성 | model-agnostic 표현 (lint.md 정본 그대로) — DeepSeek 의 한자 섞임에도 동일 보호 적용 |
| `_system/commands/ingest.md` 출력 언어 정책 | 영향 없음 (wh-ingest default 변경 없음) | 정본 그대로 |
| `_system/systemd/wikihub-vault@.timer.template` | `OnUnitInactiveSec={sync_interval_sec}s` template 변수 | sync_interval_sec 3600 변경 시 `OnUnitInactiveSec=3600s` (1h) 자동 반영 — render 시 정합 |
| ADR-0024 (fatal alert) | 영향 없음 | 정본 그대로 |
| ADR-0032 (skill registration) | wh-lint default 변경 사유를 §Note 로 정본화 | 본 feature 갱신 대상 |
| ADR-0036 (graphify) | env template GEMINI 추가 — backend catalog 의 사실 layer 변경 | §Note 추가 불요 (이미 catalog 명시) |
| ADR-0037 (alert pipeline) | 영향 없음 | 정본 그대로 |

### 6. 미결 사항

**없음** — 4건 결정 모두 운영자 verified state 가 정본 align 대상으로 명확.

### 7. Definition of Done

- [ ] `wikihub.yaml.example` 2건 변경 + 코멘트 갱신
- [ ] `install.sh` env template GEMINI 블록 + _step8_guide hermes 안내 블록
- [ ] `_system/commands/setup.md` hermes delegation.model 정보 출력 (warn 만)
- [ ] `docs/adr/0032-hermes-skill-registration-policy.md` §Note 추가 (wh-lint default 변경 사유)
- [ ] `_system/VERSION` 0.1.5 → 0.1.6
- [ ] `README.md` 버전 + 로드맵 + 개발 상태 1줄 (본 feature scope 한정)
- [ ] `features/HISTORY.md` v0.1.6 항목 (HISTORY 형식 정합)
- [ ] `render_systemd_units.py` dry-run — 8 unit 정상 출력 + `--model deepseek-v4-flash` (wh-lint) + `OnUnitInactiveSec=3600s` (vault@.timer) 정합 확인
- [ ] git commit + tag v0.1.6 + push (Step 5)

## 설계

### Karpathy 4원칙 매핑

| 원칙 | 적용 |
|---|---|
| **Think Before Coding** | 4건 mismatch 의 결정 사유를 운영자 backlog (260520 §V·260521 §B·§F) + ExecStart verified state 로 surface. 모든 변경의 운영 정본 근거 인용. |
| **Simplicity First** | yaml default 변경은 1줄, 코멘트 1줄. install.sh 추가 블록 2개. unnecessary abstraction (예: backend 별 env wrapper) 도입 안 함. |
| **Surgical Changes** | README 의 ADR-0035 일괄 align 은 별도 feature 분리 — 본 feature scope 초과 자제. 4건 mismatch 직결 부분만 변경. |
| **Goal-Driven Execution** | DoD 8 항목 — render dry-run 검증 + ADR §Note 인용 정합 + HISTORY 형식 정합. 약한 기준 ("default 잘 align") 회피. |

### 자가 검증 절차 (Step 3 implementation 후)

1. `python3 scripts/_helpers/render_systemd_units.py --dry-run` 실행
   - wh-lint.service 의 ExecStart 에 `--model deepseek-v4-flash` 포함 확인
   - wikihub-vault@gdrive.timer 의 `OnUnitInactiveSec=3600s` 확인
   - 총 8 unit 출력 (lint·vault@·mount@·pending-monitor·ops-alert 세트)
2. `grep -n "v0.1.6" _system/VERSION wikihub.yaml.example README.md features/HISTORY.md` — 모든 정본 v0.1.6 정합 확인
3. lint.md 의 "출력 언어 정책" 섹션 — DeepSeek 모델에서도 적용되는 model-agnostic 표현 유지 확인
4. ADR-0032 §Note 의 인용 ID (260520 §V, 260521 §B) 정합 확인
