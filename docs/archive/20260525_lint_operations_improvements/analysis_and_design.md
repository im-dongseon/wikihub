approved: 2026-05-25 (사용자 위임 — "step 5 전까지 자동 진행")

# Analysis & Design — lint_operations_improvements

작성일: 2026-05-25 (KST)
작업자: wikihub maintainer
연계 plan: `plan.md`

---

## 1. 분석

### 1.1 배경

운영 surface 3건:
- **I1**: 운영자 보고 "wh-lint 300초 timeout 종료" — lint cycle 의 안정성 결함
- **I2**: lint report 의 case-variant duplicates (7건) + cross-category duplicates (20건) — lint 가 현재 감지 안 함, 운영자 수동 발견
- **I3**: `--apply` 가 메인테이너 수동 호출만 — 자동화 부재로 운영 부담

### 1.2 현행 진단

#### F1. graphify timeout 의 yaml expose 부재 + 표현 drift

| 위치 | 현행 |
|---|---|
| `_system/commands/graphify.md:112-144` | `timeout 720` 6 위치 hard-code (12분) |
| `_system/commands/graphify.md:156` | "yaml expose 는 v0.2.x deferred" 코멘트 |
| `_system/commands/lint.md:183` | "timeout 300 graphify" 표현 — **부정확** (실제 720) |

운영자 보고 "300초 timeout" 은 (i) lint.md:183 의 부정확한 표현을 spec 으로 인지 (ii) 또는 graphify 의 다른 timeout source (LLM API call timeout) — 본 design 은 (a) lint.md spec 정정 + (b) graphify timeout yaml toggle 화 + default 900 (사용자 D4 명시) 으로 양쪽 해소.

#### F2. lint duplicate detection 부재

lint.md Step 1~9 어디에서도 case-variant / cross-category duplicate 감지 절차 없음. 결과 = 운영자가 wiki/ 디렉토리 ls 또는 manual report read 로 발견.

#### F3. `--apply` 자동화 부재

lint.timer (3h 주기) 가 `wh-lint` (no flag) 만 호출. `--apply` 는 lint.md:13 의 "메인테이너 수동 호출" 정책. 자동화 시 위험 (정보 손실 가능) 가정으로 default 수동 — 단 wikihub 데이터 모델상 `wiki/` 는 sources (vault, immutable) 의 LLM derivative → contradiction reword 도 LLM 이 자기 생성 페이지 자기 갱신, 원본 변경 0. 위험 재평가 시 자동화 가능 (yaml opt-in).

### 1.3 영향받는 정본/코드 파일

| 파일 | 변경 성격 | 라인 추정 |
|---|---|---|
| `_system/commands/lint.md` | Step 4.5 신규 (duplicate detection) + Step 7 (--apply) 확장 + Step 8 보고서 섹션 + Step 9 timeout 표현 정정 | +60 / -5 |
| `_system/commands/graphify.md` | `timeout 720` 6 위치 → yaml `operations.graphify_timeout_sec` read 한 값으로 변경. coment 정정 | +10 / -8 |
| `_system/systemd/wikihub-lint-apply.{service,timer}.template` (신설) | 1일 1회 (03:00 KST) `/wh-lint --apply` 호출 | +40 |
| `scripts/lib/config.py` | OperationsConfig 에 `graphify_timeout_sec: int = 900` + `lint_auto_apply: bool = False` 추가 | +5 |
| `wikihub.yaml.example` | `operations.graphify_timeout_sec: 900` + `operations.lint_auto_apply: false` | +6 |
| `install.sh` `_migrate_agent_schema` Group B | `B_graphify_timeout_sec` + `B_lint_auto_apply` flag + yaml writer defaults + systemd 3 위치 (stop/start/try-restart) wikihub-lint-apply 추가 | +20 |
| `scripts/render_systemd_units.py` | 변경 0 (glob 자동 발견 — branch_strategy_formalize 정합) | 0 |

**총: +141 / -13 (net +128)**

### 1.4 ADR 신설 여부

- **D3 (--apply 자동화)** — wiki 자동 변경 정책 결정. 그러나 plan.md §6 D3 결정 (yaml opt-in, default false, wikihub 데이터 모델 의존 위험 0) 의 근거가 ADR 가치 격상. **ADR 미생성 — wikihub_monitor 의 D1 정정 패턴 정합** (운영 결정, 메소드론 갱신에 가까움). 단 lint.md spec 안에 자동화 정책 1 단락 추가.
- **D4 (graphify timeout yaml expose)** — graphify.md:156 의 "v0.2.x deferred" 가 본 feature 에서 해소. ADR-0036 (graphify CLI) §"후속 영향" 1 줄 cross-link.
- **D2 (duplicate normalization)** — case lowercase + entity 우선 merge 정책. wikihub_monitor 처럼 spec 본문에 명시 + ADR 미생성.

---

## 2. 설계

### 2.1 I1 — graphify timeout yaml expose + spec 정합

#### 2.1.1 `wikihub.yaml.example`

```yaml
operations:
  # ...
  graphify_timeout_sec: 900           # v0.1.8 신설 — graphify subprocess wrapper timeout (15분). v0.1.5~v0.1.7 era hard-coded 720s 에서 yaml expose 격상. LLM backend latency 누적 대비 default 900s. operations.graphify_min_version 과 무관 — wrapper 보호 margin.
```

#### 2.1.2 `graphify.md` 변경

```bash
# 6 위치 (line 112, 120, 126, 132, 138, 144) 모두:
# 기존: timeout 720 env ...
# 변경:
timeout_sec="$(yq '.operations.graphify_timeout_sec // 900' "$WIKIHUB_HOME/wikihub.yaml")"
timeout "$timeout_sec" env \
  ...
```

graphify.md:156 의 코멘트 정정:
```
- `timeout $timeout_sec`: yaml `operations.graphify_timeout_sec` 정본 (default 900, v0.1.8 yaml expose).
  graphify 의 `--api-timeout` (default 600s) + LLM 호출 누적 대비 wrapper 보호 margin.
```

#### 2.1.3 `lint.md` Step 9 표현 정정

기존 line 183:
```
timeout 발생 시 (exit 124) report 에 `graph rebuild timeout` 기록
```

→ 변경:
```
timeout 발생 시 (exit 124, default 900s — yaml `operations.graphify_timeout_sec`) report 에 `graph rebuild timeout` 기록
```

#### 2.1.4 wh-ingest timeout

현행 `agent.timeout_sec=1200` (vault@.service TimeoutStartSec) 유지. Q1-a default = 1200 충분 가정 (운영자 실측 surface 시 별도 feature).

### 2.2 I2 — duplicate detection + auto-normalize

#### 2.2.1 신규 `lint.md` Step 4.5 — Duplicate detection

기존 Step 4 (자동 cross-ref 추가) 다음에 Step 4.5 신규:

```markdown
### Step 4.5. Duplicate detection (자동, 보고)

wiki/ 의 entity + concept 페이지 list 를 scan 해 두 종류 duplicate 탐지:

**Case-variant duplicates** (같은 카테고리 안):
- entity 페이지 list 의 모든 페이지 이름을 lowercase 로 normalize → 2+ 페이지가 같은 lowercase form 이면 duplicate
- concept 페이지 list 도 동일 적용
- 예: `Claude-Code` + `claude-code` → case-variant duplicate (lowercase `claude-code`)
- → `_lint/report.md` 의 `## Duplicates (case-variant)` 섹션에 보고

**Cross-category duplicates** (entity ↔ concept):
- entity 페이지 이름 list (lowercase normalize) ∩ concept 페이지 이름 list (lowercase normalize)
- 예: entities/Docker + concepts/Docker → cross-category duplicate
- → `_lint/report.md` 의 `## Duplicates (cross-category)` 섹션에 보고

`--apply` 시 (Step 7):
- case-variant: 모두 lowercase 로 rename (entity 와 concept 각각 안에서). link reference 갱신 (`[[entities/Claude-Code]]` → `[[entities/claude-code]]`)
- cross-category: **entity 우선 merge** — concept 페이지의 내용을 entity 페이지에 LLM merge (referenced_by + 본문). concept 페이지는 `.archived/` 이동. entity 가 더 구체적 의미 (실체 대상) 보존.
```

#### 2.2.2 Step 7 (`--apply` 작업) 확장

기존 Step 7 의 작업 list 에 추가:

```markdown
- **case-variant normalize** (Step 4.5 보고 항목):
  - 모든 entity / concept 페이지 이름 lowercase 변환 (예: `Claude-Code.md` → `claude-code.md`)
  - wiki/ 전체에서 link reference 갱신 (`[[entities/Claude-Code]]` → `[[entities/claude-code]]`)
  - file 충돌 시 (`.archived/` 이동 후 신규 lowercase 생성)
- **cross-category merge** (Step 4.5 보고 항목, entity 우선):
  - concept 페이지의 본문 + referenced_by 를 entity 페이지로 LLM merge
  - concept 페이지를 `.archived/concepts/<name>.md` 이동
  - wiki/ 전체에서 `[[concepts/<name>]]` link 를 `[[entities/<name>]]` 로 갱신
```

#### 2.2.3 Step 8 보고서 섹션 추가

```markdown
## Duplicates (case-variant) — auto-normalize 가능
- `Claude-Code` / `claude-code` (2 entity, 7 source references) → `--apply` 시 lowercase `claude-code` 로 통일
- ...

## Duplicates (cross-category) — entity 우선 merge
- `Docker` (entity + concept) → `--apply` 시 entity 보존, concept 본문 merge + archive
- ...
```

### 2.3 I3 — lint --apply 자동화 (1일 1회)

#### 2.3.1 신규 `_system/systemd/wikihub-lint-apply.service.template`

```ini
[Unit]
Description=WikiHub lint --apply (auto, daily) — v0.1.8
After=network-online.target
Wants=network-online.target
# OnFailure=ops-alert.service 부재 (lint.service 와 동일 패턴 — auto-apply 실패는 일상 lint 재시도가 자연 처리)

[Service]
Type=oneshot
WorkingDirectory={wikihub_home}
ExecStartPre=/bin/mkdir -p {wikihub_home}
Environment=PATH={venv_path}/bin:/usr/local/bin:/usr/bin:/bin
Environment=WIKIHUB_HOME={wikihub_home}
Environment=WIKIHUB_YAML={wikihub_home}/wikihub.yaml
EnvironmentFile=-%h/.config/wikihub/env
# yaml `operations.lint_auto_apply` toggle 은 wh-lint 스킬 본체가 확인 (lint.md Step 7 진입 직전 gate).
ExecStart={agent_invocation_for_wh_lint} "/wh-lint --apply"
SuccessExitStatus=0 75
TimeoutStartSec={timeout_start_sec}sec
SyslogIdentifier=wikihub-lint-apply

# Restart= 미설정 — oneshot, timer 책임. lint.service 와 동일.
```

#### 2.3.2 신규 `_system/systemd/wikihub-lint-apply.timer.template`

```ini
[Unit]
Description=WikiHub lint --apply timer — 매일 03:00 KST (조용한 시간대)

[Timer]
Unit=wikihub-lint-apply.service
OnCalendar=*-*-* 03:00:00 Asia/Seoul
Persistent=true
AccuracySec=5min

[Install]
WantedBy=timers.target
```

설계 결정:
- **03:00 KST** — 운영자 idle 시간, lint cycle (3h interval) 과 충돌 가능성 낮음 (단 03:00 ± 5min 에 lint.timer 가 fire 가능 — 동시 실행 시 race 검토). systemd 가 같은 service 의 동시 invocation 차단 (Type=oneshot + Active 상태).
- **Persistent=true** — 시스템 휴면 후 catch-up.
- **AccuracySec=5min** — wikihub-monitor.timer (1min) 보다 느슨. 03:00 fire 가 5분 ± 무관.

#### 2.3.3 lint.md Step 7 gate

기존 Step 7 본문 시작에 추가:

```markdown
### Step 7. `--apply` 작업 (수동 호출 시에만 + 자동 호출)

**자동 호출 gate** (v0.1.8 신규):

```bash
lint_auto_apply="$(yq '.operations.lint_auto_apply // false' "$WIKIHUB_HOME/wikihub.yaml")"
# wikihub-lint-apply.service 호출 시 lint_auto_apply=false 면 즉시 exit 0 (no-op)
# 수동 호출 (`/wh-lint --apply`) 은 lint_auto_apply 무관 — 메인테이너 의도가 이미 명시
```

- 운영자가 yaml `operations.lint_auto_apply: true` 설정 + 본 service 가 wikihub-lint-apply.timer 로 fire → 자동 진행
- yaml false (default) 면 systemd timer 가 fire 해도 service 가 즉시 exit 0 — wiki 변경 없음
- 메인테이너 수동 호출 (`/wh-lint --apply`) 은 항상 진행 (gate 무관)

기본 모드 (no flag) 에서는 Step 7 skip. `--apply` 플래그 있을 때:
- (이하 기존 Step 7 내용 + Step 4.5 의 case-variant + cross-category 작업 추가)
```

### 2.4 `scripts/lib/config.py` 갱신

```python
@dataclass
class OperationsConfig:
    # ... (기존)
    # wikihub_monitor (v0.1.8)
    monitor_enabled: bool = True
    monitor_report_vault: str | None = None
    monitor_report_subpath: str = "project/wikihub/report"
    # lint_operations_improvements (v0.1.8)
    graphify_timeout_sec: int = 900       # graphify wrapper timeout (15분, D4)
    lint_auto_apply: bool = False         # wikihub-lint-apply.timer (1일 1회) gate
```

`_parse_operations` 갱신:
```python
graphify_timeout_sec=int(ocfg.get("graphify_timeout_sec", 900)),
lint_auto_apply=bool(ocfg.get("lint_auto_apply", False)),
```

### 2.5 `install.sh` `_migrate_agent_schema` Group B 갱신

```python
if "graphify_timeout_sec" not in operations:
    flags.append("B_graphify_timeout_sec")
if "lint_auto_apply" not in operations:
    flags.append("B_lint_auto_apply")
```

info log + yaml writer defaults 동일 패턴.

systemd 3 위치 (stop / start / try-restart) 에 `wikihub-lint-apply.service` + `wikihub-lint-apply.timer` 추가.

### 2.6 wikihub_monitor.py 영향

본 feature 의 변경이 wikihub_monitor 보고서에 surface 되는지 검토:
- `wikihub-lint-apply.service` 가 새로 추가됨 — monitor 가 수집할지?
- 결정: **수집 안 함** (단순성 유지). 운영자가 lint-apply 결과 확인은 journalctl 또는 _lint/report.md (lint --apply 가 자동 실행 후에도 report.md 갱신).
- 후속 feature 로 monitor 가 wh-lint-apply 결과까지 surface 가능 — backlog 등록 (BL-N7).

### 2.7 연계 ADR 정합성

| ADR | 정합 검토 | 조치 |
|---|---|---|
| ADR-0036 (graphify CLI integration) §"timeout wrapper" | graphify.md:156 의 "v0.2.x deferred" 가 본 feature 에서 해소 — yaml expose | §"후속 영향" 1 줄 cross-link |
| ADR-0030 (`_resolve_ref` chain) | 본 feature 와 무관 | 변경 없음 |
| ADR-0023 (sparse-checkout) | scripts/ 변경 없음, _system/systemd/ 신규 — 자동 포함 | 변경 없음 |
| 메소드론 (branch_strategy_formalize) | feature/lint_operations_improvements 분기 + squash 흐름 정합 | — |

### 2.8 race / 동시성 검토

- **lint.timer (3h) 와 wikihub-lint-apply.timer (03:00 KST)** 동시 fire 가능성 — systemd 가 같은 service 차단? 두 timer 가 **다른 service** (`lint.service` vs `wikihub-lint-apply.service`) 를 fire 하므로 systemd 차단 없음.
- 두 service 가 같은 wiki/ working tree 변경 — race window 발생 가능 (lint 가 자동 수정 중 lint-apply 가 별도 수정).
- 가드: lint.md Step 0 에 file lock (또는 flock) 추가 검토. 본 feature 범위 외 — backlog (BL-N8) 권고. 03:00 fire 가 lint.timer 와 정확히 겹칠 확률 ≪ 5분 ÷ 180분 = 2.8% 라 실 운영 영향 낮음.

---

## 3. 개정 범위 요약

§1.3 표 그대로. 총 +141 / -13 (net +128).

---

## 4. 미결 사항 (잔여)

| ID | 미결 | default | 시점 |
|---|---|---|---|
| Q-A | lint.md Step 4.5 의 LLM merge (cross-category) — 본문 merge 책임이 lint 자체인지 graphify인지 | lint 자체 (Step 7 안에서 LLM 호출, Step 6 의 contradiction 처리와 같은 패턴) | Step 3 |
| Q-B | wikihub-lint-apply.service 의 timeout — lint.service 와 동일 `agent.timeout_sec` 사용 vs 별도 신설 | 동일 사용 (단순) | Step 3 |
| Q-C | yaml opt-in default false 의 첫 설치 시 운영자 인지 — install.sh `_step5_instance_dirs` 의 env template 또는 README 안내 | wikihub.yaml.example 의 코멘트 명시 + install.sh _step10_print_next_steps 에 1 줄 | Step 3 |

---

## 5. Definition of Done

- [ ] `_system/commands/lint.md` — Step 4.5 신규 + Step 7 확장 + Step 8 보고서 섹션 + Step 9 timeout 표현 정정
- [ ] `_system/commands/graphify.md` — `timeout 720` 6 위치 yaml read + 코멘트 정정 (v0.2.x deferred → v0.1.8 해소)
- [ ] `_system/systemd/wikihub-lint-apply.{service,timer}.template` 신설
- [ ] `scripts/lib/config.py` — OperationsConfig 2 field 추가 (graphify_timeout_sec / lint_auto_apply) + _parse_operations 갱신
- [ ] `wikihub.yaml.example` — 2 field 안내 코멘트 추가
- [ ] `install.sh` `_migrate_agent_schema` Group B 2 flag + yaml writer defaults + systemd 3 위치
- [ ] `docs/adr/0036-graphify-cli-integration.md` §"후속 영향" 1 줄 cross-link
- [ ] `features/backlog.md` BL-N7 (monitor 가 wh-lint-apply 결과 surface) + BL-N8 (lint.service / wikihub-lint-apply.service race 가드) 등록
- [ ] V 검증: VM 또는 OCI 에서 `systemctl --user start wikihub-lint-apply.service` ad-hoc — lint_auto_apply=false 면 즉시 exit 0, true 면 --apply 진행
- [ ] bash -n install.sh + py_compile config.py 모두 pass
- [ ] Step 4 멀티 리뷰어 통과
- [ ] **Step 5 squash 전 사용자 승인 필수** (사용자 명시)

---

## 6. 버전 이력

### v1 — 2026-05-25 (초안, plan.md 결정 흡수)

D1~D5 + Q1-a/Q2-b/Q2-c default 모두 흡수. 본 design 으로 Step 2.5 멀티 리뷰어 진행.

### v2 — 2026-05-25 (Step 2.5 멀티 리뷰어 흡수 — alias frontmatter 도입 + 결함 8건 fix)

**Reviewer 2 C2 결함 + 사용자 정정**: lowercase 강제가 product noun (MiniMax, DeepSeek, GitHub) 의 의도된 case 손상 + LLM 재생성 cycle 무한 loop 위험 → **alias frontmatter 도입** (사용자 명시).

#### 신규 §2.9 — alias frontmatter (wiki-schema 데이터 모델 확장)

entity / concept page 의 frontmatter 에 `aliases` 필드 추가:

```markdown
---
aliases: [MiniMax, mini-max, minimax]
referenced_by:
  - sources/gdrive/notes/idea.md
---

# MiniMax

(본문 — entity 또는 concept 의 정의)
```

규칙:
- **첫 alias = canonical name** (페이지 파일명 base). 예: `MiniMax.md` → `aliases[0] = "MiniMax"`.
- 추가 alias = 같은 entity/concept 로 인식할 변형 (lowercase, hyphen variant, abbreviation 등).
- **빈 aliases 불가** — 최소 canonical 1개. 빈 경우 lint 가 자동 보강 (페이지 파일명 기반).

#### alias 생성 책임 (reasonable default)

| 단계 | 책임 |
|---|---|
| ingest (스킬) | sources 본문에서 entity / concept 새로 발견 시 stub 생성 + alias = 본문에 등장한 form |
| lint Step 4.5 | wiki 전체 scan — 같은 lowercase 변형의 2+ 페이지 가 다른 alias 셋이면 duplicate 보고. 같은 alias 셋이면 정합 (보고 안 함). |
| lint Step 4.5 (alias migration) | 기존 wiki page 의 frontmatter `aliases` 부재 시 — `aliases: [<canonical>]` 자동 추가 (첫 cycle migration) |
| lint Step 7 (`--apply`) | case-variant duplicate 발견 시 → 첫 등장 form (또는 frontmatter `canonical` 명시) 보존 + 다른 form 의 page 는 archive + alias 셋 통합 + link reference 갱신 |

#### duplicate detection 알고리즘 (Step 4.5 갱신)

```
1. wiki/entities/, wiki/concepts/ 각각의 page list 수집
2. 각 page 의 frontmatter aliases set 추출 (부재 시 [<canonical>])
3. **case-variant duplicate**: 같은 카테고리 안에서 2+ page 의 alias set 가 lowercase 비교 시 1+ 공통 요소
   → "공유 alias 인지" — alias 셋이 정합이면 false positive (보고 안 함). 단일 page 가 모든 form 의 alias 보유.
   → "다른 entity 인지" — alias 셋이 완전 분리면 duplicate. 보고.
4. **cross-category duplicate**: entity alias set ∩ concept alias set (lowercase 비교) 가 비공집합
   → 보고. entity 우선 merge (--apply 시).
```

LLM 재생성 무한 loop 방지: LLM (ingest / lint Step 3 자동 stub 생성) prompt 에 "기존 entity/concept page 의 aliases frontmatter 확인 후 같은 form 발견 시 stub 생성 skip + 기존 page 의 referenced_by 만 갱신" 명시.

#### wiki-schema 갱신

`_system/wiki-schema.md` 의 entity / concept page spec 에 frontmatter 절 추가:

```markdown
### Entity / Concept 페이지 frontmatter (v0.1.8 신설)

| field | 의미 | 필수 |
|---|---|---|
| `aliases` | 같은 entity/concept 로 인식할 form list. 첫 alias = canonical (페이지 파일명 base) | 필수 (lint Step 4.5 가 자동 보강) |
| `referenced_by` | source page list (기존) | 그대로 |
```

#### ADR 신설 결정

wiki-schema 데이터 모델 변경 + LLM prompt 규약 + lint 알고리즘 → **ADR-NNNN (다음 ADR 번호) 신설 가치**. Step 3 진입 시 ADR 발급.

**ADR 후보 제목**: "entity/concept alias frontmatter 도입 — duplicate detection 정합 + LLM 재생성 무한 loop 방지"

---

#### 흡수 항목 정리

**Reviewer 1 (spec 정합 + ADR)**:
- **H1** §1.2 표의 lint.md:183 묘사 정정 — graphify.md 로 책임 위임 완료 (ADR-0038 v0.1.7 follow-up) 정확 반영
- **M1** graphify `--api-timeout` 600s vs wrapper 900s — backlog 등록 (BL-N9 wrapper/api-timeout 정합 검증)
- **M2** 자동 호출 모드 운영자 책임 — lint.md spec 본문 1 줄 명시
- **M3** lint-apply.service.template 의 `OnFailure=ops-alert.service` 추가 (wikihub-monitor 패턴 정합 — lint.service 도 OnFailure 보유한 사실 확인)
- **M4** cross-category merge 알고리즘 명시 — design §2.2.2 보강
- **M5** lint_auto_apply gate 위치 — ExecStartPre 의 fail-fast vs lint 본체 진입 후 yaml read 비교. 단순성 위해 본체 진입 후 gate 유지 (운영자 cost = agent invocation 시작만, ~1초). backlog 등록 (BL-N10)

**Reviewer 2 (운영 안전성 + LLM 동작)**:
- **C1** link reference 패턴 정정 — wiki-schema 의 단축형 `[[<name>]]` 사용. 카테고리 prefix 가 의무 아님 (ADR-0001 정합). lint 의 link 갱신 = lowercase rename 후 `[[<name>]]` (변형 form) → `[[<canonical>]]` 갱신. wiki-schema 의 link resolver 가 alias 인식 시 자동 — 단 본 feature 가 link resolver 까지 변경하면 범위 확대. **결정**: link resolver 는 그대로 (단축형 그대로), `--apply` 가 변형 form 의 page 를 archive 이동 시 wiki 안 모든 `[[<variant>]]` 를 `[[<canonical>]]` 로 sed 치환.
- **C2** product noun lowercase — **alias frontmatter 도입으로 해소** (위 §2.9)
- **H1** wiki-schema disambiguator (`<name> (disambig).md`) 규약 + cross-category entity 우선 merge — wiki-schema 에 cross-category merge 정책 1 줄 추가
- **H2** wikihub-lint-apply.timer enable 책임 — install.sh `_systemd_start_after_update` 에 `systemctl --user start wikihub-lint-apply.timer` 추가. 단 yaml `lint_auto_apply: false` (default) 면 timer fire 해도 service 가 yaml gate 로 no-op — 시각적 fail-loop 없음.
- **H3** graphify_timeout_sec backend 별 — backlog (BL-N11, per-backend toggle 검토)
- **H4** daily +1회 graphify cost — wikihub.yaml.example 의 `lint_auto_apply` 주석 + setup.md `--enable` 안내에 cost 명시 (cloud backend 사용 시 daily 1회 추가 + ollama 는 무료)
- **M1~M5**: 각각 정합 패치

#### v2 영향 범위 증가

| 추가 영역 | 변경 성격 | 라인 |
|---|---|---|
| `_system/wiki-schema.md` | entity/concept page frontmatter spec 추가 (aliases 필드 정의) + cross-category merge 정책 1 절 | +25 |
| `_system/commands/ingest.md` | LLM prompt 보강 — entity/concept stub 생성 시 기존 page 의 aliases frontmatter 확인 + 같은 form 발견 시 referenced_by 만 갱신 (재생성 무한 loop 방지) | +15 |
| `_system/commands/lint.md` Step 3 (자동 stub 생성) | 같은 alias 보유 page 확인 후 skip 명시 | +5 |
| `docs/adr/00XX-entity-concept-alias-frontmatter.md` (신설) | ADR — 결정의 정본 | +50 |
| `features/backlog.md` | BL-N9~N11 추가 | +6 |

v1 의 +141/-13 → v2 의 **+240/-13 (net +230)**.

approved 마커: 사용자 위임 "step 5 전까지 자동 진행" + alias frontmatter 결정 명시. Step 3 진입.

### v3 — 2026-05-25 (Step 4 code review 흡수)

**Reviewer 2 (운영 안전성) 의 H 항목 즉시 fix**:
- **H1** 자동화 cost 누설 → `wikihub-lint-apply.service.template` 에 `ExecCondition` 추가 — yaml `lint_auto_apply=false` 시 service 전체 no-op (lint cycle + graphify chain cost 0). wikihub.yaml.example 코멘트도 정확화 ("Step 7 만 skip 아님 — service 전체 skip").
- **H2** alias migration race + atomic write → lint.md Step 4.5 의 Alias migration 섹션에 atomic write 패턴 (`<page>.tmp` write → rename) + ingest/lint 책임 경계 명시 추가.
- **H3** bootstrap fail silent → 본 feature 범위 외 (wikihub_monitor 의 `_emit_bootstrap_alert` 패턴 적용 필요하나 lint-apply ExecStart 가 LLM agent 라 wrapper script 필요). backlog 등록 (BL-N13 후속 feature).
- **M2** race window 산정 → lint.md 신규 Step 0 (wiki-wide flock 가드) 추가. lint.service running 중 lint-apply.service fire 시 즉시 no-op. 17% race window 0% 회피.

**Reviewer 1 (DoD + ADR 정합) 의 H 항목 즉시 fix**:
- **H1** setup.md `--enable` 분기 미명시 → setup.md Step 4 의 `--enable` catalog 에 `wikihub-pending-monitor.timer` (ADR-0037) + `wikihub-monitor.timer` + `wikihub-lint-apply.timer` 명시 추가 (lint-apply 는 ExecCondition 으로 default no-op 명시).

**deferred (backlog)**:
- R2-H3 wikihub-lint-apply bootstrap fail self-alert
- R2-M1 sed 치환 표현 명료화
- R2-M3 timer enable (BL-N5 통합)
- R2-M4 lint Step 4.5 deterministic Python helper
- R2-M5 cross-category LLM merge idempotency
- R1-M1 lint.md Step 0 flock (Step 0 추가로 closure ✅)
- R1-M2 lint.md L22 출력 언어 정책 Step 7 명시
- L 항목들

**bash -n + py_compile 검증 통과**. Step 5 squash merge 사용자 검토 대기 (사용자 명시 흐름).

### v5 — 2026-05-25 (사용자 추가 정정: `--apply` flag 폐기)

**사용자 의견** (Step 5 검토 시점): "굳이 apply 용을 만들어야 할까? 어차피 원본은 변경없이 거기에 대한 문서만 LLM 이 업데이트하는건데. lint 진행하면서 바로 apply 해도 되지 않을까?"

**근거 (사용자 + 메인테이너 정합 인정)**:
- wikihub 데이터 모델: sources (vault) = immutable 원본. wiki/ = LLM derivative.
- lint 의 `--apply` 가 원래 "정보 손실 가능" 우려 (v0.1.0 lint.md:114) 였으나, derivative 모델에서는 항상 LLM 재생성 가능 → 위험 낮음.
- 메인테이너가 `--apply` 명시 호출하는 패턴 = wikihub 모델 위에서 over-protection.

**결정 (사용자 명시)**: `--apply` flag 완전 제거. lint = 매 cycle 진단 + 적용 default.

**삭제**:
- `_system/systemd/wikihub-lint-apply.{service,timer}.template` (이전 v2 신설분)
- `wikihub.yaml.example` 의 `operations.lint_auto_apply` field
- `scripts/lib/config.py` 의 `OperationsConfig.lint_auto_apply` field + `_parse_operations` 갱신
- `install.sh` 의 `B_lint_auto_apply` flag + info log case + yaml writer default + systemd 3 위치 (stop/start/try-restart) wikihub-lint-apply
- `_system/commands/setup.md` 의 `wikihub-lint-apply.timer` enable catalog 언급
- `features/backlog.md` 의 BL-N7 (lint-apply 결과 surface), BL-N8 (lint-apply race), BL-N10 (yaml gate cost) — 모두 무효화

**갱신**:
- `_system/commands/lint.md` 호출 절: `/wh-lint --apply` 표현 제거. 매 cycle 진단 + 적용 default 명시.
- `_system/commands/lint.md` Step 7: yaml gate 제거. 매 cycle 자동 실행. case-variant + cross-category 처리 자동.
- `_system/commands/lint.md` 의 `--apply` 표현 8 위치 모두 "Step 7 에서 자동 처리" 또는 "매 cycle 자동" 으로 갱신.
- `_system/commands/lint.md` Step 0 flock 의 lint-apply 언급 제거 — lint.timer + 메인테이너 수동 호출 race 만 가드.
- `docs/adr/0039-*` 의 lint Step 7 표현 갱신 ("매 cycle 자동, v0.1.8 `--apply` flag 폐기").

**보존**:
- ADR-0039 (alias frontmatter 정책) — 변경 없음
- I1 graphify timeout yaml expose (D4)
- I2 duplicate detection + auto-normalize (D2) + alias 기반 LLM 재생성 cycle 차단

**운영 영향**:
- lint.timer 매 3h cycle 마다 진단 + 적용 (이전엔 진단만, --apply 시 적용)
- contradiction check 매 cycle 자동 LLM reword → cloud backend daily 8회 token cost (운영자 인지된 trade-off)
- 메인테이너 `/wh-lint` 수동 호출 = 즉시 진단 + 적용

**범위 축소**: v0.1.8 신설 systemd unit = wikihub-monitor.{service,timer} (이미 squash 완료) 만. wikihub-lint-apply 신설 폐기.

**다음 단계**: Step 5 squash merge 사용자 승인 대기.
