# Design Review 1 — wikihub_monitor (메소드론/ADR 정합)

작성일: 2026-05-25
리뷰어: claude (서브에이전트, general-purpose)

본 리뷰는 `analysis_and_design.md` v1 + `plan.md` 를 컨텍스트 격리(이전 대화 미시청) 가정으로 처음 검토하는 독립 리뷰어 시각. 정합성·운영성 위주.

---

## 종합 평가

**통과(조건부)** — 전체 design 방향(Python 직접 + 정적 보고서 + lib/telegram.py 분리)은 ADR-0024/0037/0036 의 의도와 정합하나, **(C1) 보고서 → ops-alert 채널 동일화로 인한 noise/혼동 risk**, **(C2) monitor.service 자체 silent dead 의 인지 경로 부재**, **(H1) Telegram 4096 chars limit 의 fail mode 미정의**, **(H2) `Persistent=true` 의 12hr 윈도우 catch-up 시맨틱 정의 누락** 4건이 Step 3 진입 전 결정되어야 한다.

조건부 통과 = 위 4건 중 C 항목 2건은 design.md 본문 갱신, H 항목 2건은 Step 3 default 채택으로 흡수 가능.

---

## C 항목 (Critical — Step 3 진입 전 반드시 해소)

### C1. monitor 보고서 ↔ ops-alert 동일 Telegram 채널 → noise 이중화 + 운영자 혼동

**근거**:
- `analysis_and_design.md:86-87` — `EnvironmentFile=-%h/.config/wikihub/env` 로 `TELEGRAM_ALERT_BOT_TOKEN` + `TELEGRAM_ALERT_CHAT_ID` 재사용 명시
- ADR-0037 §D1 (`0037-alert-pipeline-architecture.md:51-57`) — 같은 env 키 = ops-alert.service 의 fatal alert 채널
- 결과: vault@ 실패 → 즉시 ops-alert (HTML "🚨 Wikihub Alert") → 같은 chat → 12hr 뒤 monitor 보고서 ("🔭 WikiHub Monitor") 가 같은 실패를 plain text 로 **재보고**

**문제**:
- design.md §"운영 안내" 가 본 의도된 design 여부 명시 없음. Q (사용자 제시 검토 관점 4번째 항목) 와 정확히 매치되는 risk.
- 운영자가 ops-alert HTML message 받고 진단/조치 완료 → 12hr 후 monitor 가 "실패 1건" 라인 재발화 → "이미 처리한 건 아닌가?" 인지 부담
- ADR-0024 §Dedup 정책의 `alerted_failed_count` + 24h reminder mechanism 이 ops-alert 측엔 있지만 monitor 측엔 **없음** — monitor 는 단순히 journal 윈도우 내 모든 실패를 라인 단위로 dump

**권고**:
- (a) **design.md §2.3 보고서 포맷에 "이미 ops-alert 발화된 실패는 별도 마커" 추가** — 예: `2026-05-25 11:00 : 실패 (exit 2, rclone mount stale) [ops-alert 발화됨]` — `_state/<vid>/last_failure.json` 의 `alerted_at` 가 윈도우 안에 있으면 마커 부착
- (b) 또는 design.md §"운영 안내" 절 신설하여 "monitor 는 ops-alert 와 의도적 redundancy — fatal 즉시 + 12hr 후 회고용 dual surface" 명시 + 운영자가 이 ergonomic 을 받아들이는 design intent 라고 declare
- (c) 운영자가 ops-alert chat 과 monitor chat 을 분리하고 싶을 때 escape hatch — `MONITOR_TELEGRAM_CHAT_ID` env override 옵션 backlog 등록 (Q12 같은 라인에)

design.md 가 (b) intent 라면 본문에 명시 + ADR-0037 §"후속 영향" 1줄에도 "monitor 가 같은 채널 재사용 = intentional redundancy" 한 글자 더해야 ADR 정본이 그 redundancy 인지함.

### C2. monitor.service 자체 silent dead — 운영 black hole

**근거**:
- `analysis_and_design.md:77` — `# OnFailure 미설정 — monitor 자체 실패는 ops-alert 트리거 안 함 (가시성 layer 가 가시성 layer 를 깨우는 재귀 회피)`
- `analysis_and_design.md:100` — 같은 설명

**문제**:
- monitor.service 가 silently dead (예: `wikihub_monitor.py` 신규 버그, venv 손상, Python import error, journalctl 호출 자체 fail) 시 운영자는 **"오늘 보고서 안 왔네"** 를 직접 의식해야 인지
- 12hr 주기라 1~2회 누락은 운영자가 모를 가능성 — "오늘 너무 평화로워서 무소식인가? monitor 가 죽었나?" 의 inherent uncertainty
- 본 design 의 자체 목적이 "무소식이 좋은 소식인 운영 모드의 결함 해소" (analysis_and_design.md:13) 인데, monitor 자체가 같은 결함에 빠짐 — 자기 부정
- ADR-0037 §"후속 영향" 의 pending_monitor 가 같은 패턴 채택했으나 그건 ops-alert 호출 producer 라 자체 dead 가 ops-alert dead 와 등가 — wikihub_monitor 는 read-only consumer 라 dead 시 직접적 시그널 없음

**권고**:
- (a) **`scripts/wikihub_monitor.py` 의 exit code 정책 분리** — venv/import/config load fail = exit 2 (Fatal) + `OnFailure=ops-alert.service` 설정. journalctl/parse 단계 fail = exit 75 (Retryable, 다음 fire 자연 복구). Telegram API fail = exit 75. → "재귀 회피" 의도는 **monitor 자신이 Telegram 으로 발송하는 path** 에 한정되어야지, monitor 가 venv 손상 같은 환경 결함 시에도 ops-alert 를 못 깨우는 건 over-protection.
- (b) 또는 별도 heartbeat 마커 — `_state/monitor_last_run.json` 에 마지막 fire 타임스탬프 영속 + 다음 fire 시 비교 → 24hr 이상 stale 검출 시 self-alert. 하지만 fire 가 안 되면 stale 검출 자체가 안 됨 — closed loop. (a) 가 더 단순.
- (c) 최소한 design.md 본문에 "monitor 자체 silent dead 의 운영자 인지 = 운영자가 12hr/24hr 후 chat 무소식 감지 (intentional, MVP)" 라고 design intent 를 declare 하고 risk 인지 명시. backlog 에 `monitor_health` heartbeat 등록.

design.md §2.1.1 의 `SuccessExitStatus=0 75` + exit code 정책이 이 분리를 자연 지원할 수 있음 — exit 2 만 OnFailure 발화하면 재귀 회피 + 환경 결함 surface 둘 다 충족.

---

## H 항목 (High — Step 3 default 결정으로 흡수 가능, 본문 명시 필수)

### H1. Telegram message 4096 chars limit 의 fail mode 미정의

**근거**:
- `analysis_and_design.md:356` (Q11) — `cap 4000 + truncate, 분할은 backlog` 결정으로 표시
- §2.3 보고서 예시 — `(윈도우 내 12회 실행)` 표현 + 라인 단위 표기

**문제**:
- 12hr 윈도우 + ingest 1hr cycle = vault 당 12 라인 (현재 단일 vault) — 그러나 multi-vault N개 + lint 4회 + 각 라인 reason 100 chars = 보고서 길이 가속적 증가
- 5 vault + 모두 실패 (reason 100 chars 씩) = 5 × 12 × ~150 chars/line ≈ 9000 chars — **4000 cap 초과**
- truncate 시 마지막 vault 의 lint 보고가 통째로 사라짐 → 운영자가 중요한 정보 누락
- Telegram bot API 30 msg/sec rate limit — single timer fire 의 1 message 라 영향 미미하나, multi-message 분할 시 고려

**권고**:
- (a) **§2.3 보고서 포맷에 길이 cap 정책 명시** — 4000 chars 초과 시 (1) reason cap 100 → 60 으로 자동 축소 (2) 카운트 요약만 남기고 라인 dump 제거 (3) "보고서 길이 초과 — 상세는 journal 참조" 1줄 fallback
- (b) Q11 의 "분할은 backlog" 결정을 design.md 의 §"미결 사항" backlog list 에 explicit 으로 push — `features/backlog.md` 에 항목 추가 (현재 design.md §2.9 가 "본 feature 항목 없음" 인데 Q11 backlog 등록은 필요)
- (c) 또는 **카운트 요약 우선 + 실패 라인만 dump** — 성공 라인 12 행 표기 vs `(12회 모두 성공)` 1줄 압축 — 운영자가 정상 cycle 의 라인을 12회 매번 봐야 하는지 redundancy 의문 (§5 별도 항목)

### H2. `Persistent=true` 의 12hr 윈도우 catch-up 시맨틱 미정의

**근거**:
- `analysis_and_design.md:112` — `Persistent=true` 명시
- `analysis_and_design.md:122` — "시스템 휴면/재부팅 시 마지막 fire 시점 보존, 누락된 fire 시점에 catch-up. 단 윈도우 정의가 '지난 12 시간' 단순이라 catch-up 도 그 시점의 12hr 윈도우" — 짧게 다뤘으나 corner case 미해결

**문제**:
- 시스템 30시간 다운 → 부팅 후 즉시 catch-up fire — 윈도우 = 부팅 시점 - 12hr (downtime 안 포함하는 영역) — 첫 24hr 의 실패 누적은 영구 누락
- design.md §2.2.2 의 `window_end = datetime.now(tz=KST); window_start = window_end - timedelta(hours=12)` 가 monotonic 정의 — catch-up fire 시 의도된 윈도우 (전날 21:00 ~ 당일 09:00) 가 아니라 부팅 시점 wall clock 기준의 12hr 윈도우
- Q4 (plan.md:82) 에서 단순화 선택했으나, Persistent=true 와의 상호작용은 explicit 으로 검토 안 됨

**권고**:
- (a) **§2.2.2 의 윈도우 계산 명시** — `Persistent=true` 의 catch-up 의미는 "직전 미발화 시점에 즉시 발화" 이지 "직전 의도 시점의 윈도우를 retroactive 계산" 이 아님. catch-up fire 도 그 시점의 wall clock 기준 12hr → 의도와 정합 (운영자가 다운타임 후 첫 보고서를 "지난 12hr 정상" 으로 받으면 misleading 가능)
- (b) 또는 **윈도우를 timer fire 시점 기준이 아니라 직전 fire 마커 기준** — `_state/monitor_last_run.json` 에 마지막 window_end 영속 + 다음 fire 의 window_start = 직전 window_end. 단순화 깨지나 다운타임 후 정확
- (c) MVP 는 (a) 채택 + design.md 에 "다운타임 후 첫 보고서는 wall clock 12hr 윈도우 — downtime 직전 데이터는 ops-alert 가 이미 발화했어야 정상" caveat 명시. (b) 는 backlog.

`Asia/Seoul` TZ 와 systemd monotonic clock 의 상호작용은 사용자 검토 관점 3번째 항목에 언급된 대로 — systemd OnCalendar 의 `Asia/Seoul` suffix 는 wall clock 기반 next fire 계산용이고 monotonic 영역은 `Persistent=true` 의 last-fire bookmark — 별도 layer 라 충돌 없음. KST DST 없으니 추가 검증 불요. **단 design.md 에 1줄 명시 권장** — "Asia/Seoul TZ suffix + Persistent=true 는 systemd 가 internal 처리 (next fire 는 wall clock, catch-up bookmark 는 monotonic) — KST DST 없어 corner case 없음".

### H3. ADR-0036 §D6 single-source 정합 — graphify 결과의 monitor surface 정합

**근거**:
- design.md §2.5 graphify 상태 분기 — journal MESSAGE pattern matching
- ADR-0036 §D6 (`docs/adr/0036-graphify-cli-integration.md:96-225`) — "wh-lint Step 9 chain 이 graphify 의 single-source dispatch" + lint Step 9 의 timeout wrapper 가 `graph rebuild timeout` 마커 기록
- lint.md:170-191 — 정확한 마커 문자열 ("graphify chain skipped (yaml toggle)", "graphify partial failure 의심: N=<N>, M=<M>, ratio=<r>")
- ADR-0036 §"후속 v0.1.6" — `operations.graphify_enabled: false` 시 lint Step 9 skip

**문제**:
- design.md §2.5 의 마커 문자열이 **lint.md 의 정본 마커와 정확히 일치하는지 verify** 필요:
  - design.md: `"graphify chain skipped (yaml toggle)"` ✓ (lint.md:170 와 일치)
  - design.md: `"graph rebuild timeout"` ✓ (ADR-0036:197 / lint.md:183 와 일치)
  - design.md: `"graphify partial failure 의심"` — lint.md:191 의 정확한 문자열은 `"graphify partial failure 의심: N=<N>, M=<M>, ratio=<r>"` — design.md 가 prefix 매칭이라 매치 OK, 단 N/M/ratio 값 추출하면 reason 더 풍부
- `EXIT_STATUS 124` 가 lint.service 전체 의 exit code 인지 graphify subprocess 의 exit code 인지 모호 — lint.md Step 9 의 `timeout 300 graphify ...` wrapper 가 exit 124 받고도 lint 본체는 정상 진행 → `wikihub-lint.service` 의 EXIT_STATUS = 0 (lint 본체 성공). graphify timeout 마커는 journal MESSAGE 에만 — design.md §2.5 의 "EXIT_STATUS 124" 분기는 **부정확**

**권고**:
- (a) **§2.5 의 graphify_status 추출 로직을 EXIT_STATUS 분기 제거 + MESSAGE pattern matching only 로 단순화** — `wikihub-lint.service` 의 EXIT_STATUS 가 124 일 일은 graphify timeout 만으로는 발생 안 함 (wrapper 가 흡수)
- (b) `graphify partial failure 의심` 마커의 N/M/ratio 캡처 — reason 에 부가
- (c) lint Step 9 마커 문자열은 lint.md 가 정본 — wikihub_monitor.py 가 정규식 컴파일할 때 lint.md 의 문자열을 source-of-truth 로 명시 (코드 주석 + ADR-0036 cross-reference) → 추후 lint.md 가 마커 표현 바꿔도 monitor 가 broken 됨을 인지

---

## M 항목 (Medium — Step 3 자가 검증 또는 Step 4 결정 가능)

### M1. ADR 신설 미생성 결정 — `scripts/lib/telegram.py` 분리는 ADR 격상 가치 있는가

**근거**:
- design.md §1.5 — "ADR 신설 불필요 ... over-engineering"

**검토**:
- ADR-0037 가 이미 ops-alert 의 send_telegram 을 정본으로 lock — lib/ 추출은 refactor 성격이고 architectural 결정은 ADR-0037 안에 이미 있음
- 단 lib/telegram.py 가 향후 weekly digest / alert summary 등 **3번째 caller** 가 등장하면 그 시점 ADR 격상이 자연스러움 — 본 feature 의 2번째 caller (monitor) 만으로는 ADR 격상 임계점 미만
- ADR-0037 §"후속 영향" 1줄 cross-link 로 추적성 충분 — design.md 결정 타당

**권고**: ADR 미생성 결정 **유지**. 단 ADR-0037 §"후속 영향" 추가 줄에 `lib/telegram.py` 의 의도 (parse_mode 옵션화 + 향후 3번째 caller 시 ADR 격상 트리거) 한 글자 더 — "scripts/lib/telegram.py 로 추출됨 (parse_mode 옵션화). **3번째 caller (예: weekly digest) 등장 시 ADR 격상 재검토 트리거.**"

### M2. branch_strategy_formalize 메소드론과 본 feature 진행 흐름 정합

**근거**:
- plan.md:14 — `feature/wikihub_monitor` from `origin/v0.1.8` 분기 완료 명시
- `git branch --show-current` 결과 = `feature/wikihub_monitor` (확인됨)
- agent_dev_guide.md:209-217 — 5 액션 git workflow 의 squash → 버전 브랜치 → canary force-update 흐름

**검토**:
- plan.md §"적용 단계 선언" 의 Step 5 = "5 액션 git workflow 적용" 명시 — 정합
- DoD §5 의 "Step 5 5 액션 squash → v0.1.8 → canary force-update" 도 정합
- analysis_and_design.md §"버전 이력" v1 — 정합

**권고**: 정합. 단 Step 5 진입 시 액션 (1) 의 commit message 형식이 `<type>(<feat_id>): ... (vX.Y.Z)` 명시되어 있는데, 본 feature 는 type=feat + feat_id=wikihub_monitor + (v0.1.8) — design.md 또는 plan.md 의 Step 5 절차 명시에 commit message draft 예시 1줄 추가 권장 (Step 3 후 자동 흡수 가능 — Step 2 의무는 아님).

### M3. `_system/wiki-schema.md` 와의 정합성

**근거**:
- design.md §"연계 룰/스킬 정합성" — wiki-schema.md 미언급
- CLAUDE.md §3 Step 3 자가 검증 — "`wiki-schema.md`와의 정합성 (지식 모델 정의 준수)" 필수 체크

**검토**:
- 본 feature 가 wiki/ 디렉토리의 schema 를 건드리지 않음 — read-only consumer of journal — wiki-schema.md 영향 없음
- 단 자가 검증 항목이 plan.md/design.md 에 explicit 확인 흔적 없음

**권고**: design.md §2.9 "연계 룰/스킬 정합성" 표에 `_system/wiki-schema.md` row 추가 — "변경 없음 (monitor 가 wiki/ 읽지 않음, journal only)". Step 3 자가 검증 누락 방지.

### M4. install.sh `_migrate_agent_schema` Group B 정합

**근거**:
- design.md §2.8 `install.sh _migrate_agent_schema Group B` 의 `B_monitor_enabled` 플래그 + info log 추가
- `analysis_and_design.md:316-319` — pseudo-code 가 "if monitor_enabled not in operations" 인데 실제 install.sh 의 group B 로직 형식 확인 안 됨

**검토**:
- 실제 install.sh 의 `_migrate_agent_schema` 가 어떤 형식으로 group B flag 를 등록하는지 (bash array? Python helper 호출?) design.md 가 추상화 — Step 3 진입 시 실제 코드 패턴에 맞춰 정합

**권고**: design.md §2.8 의 pseudo-code 를 "install.sh `_migrate_agent_schema` 의 기존 group B 패턴 정합" 으로 phrasing 단순화. Step 3 의 자가 검증 항목으로 "기존 group B flag 의 발화 → info log → yaml_writer.py default 의 3 layer 정합 확인" 1줄 추가.

### M5. Q12 corner case — vault_ids 빈 리스트 시 동작

**근거**:
- design.md:357 (Q12) — "wh-ingest: vault 미등록" 라인 + lint 만 보고 = default

**검토**:
- 첫 install 직후 운영자가 yaml 의 vaults 절을 비워 둔 상태 + monitor 만 단독 fire — 보고서가 "vault 미등록" 1줄 + lint 0회 (lint 도 vault 없으면 의미 없음)
- ops-alert 에선 vault 없으면 last_failure 도 없어 no-op — monitor 가 이를 정상 surface 하면 운영자에게 "yaml 미설정 인지" 도움

**권고**: Q12 default 채택 OK. 단 보고서 포맷 예시 (§2.3) 에 빈 윈도우 1줄 형식 명시되어 있으므로 vault 미등록 시 형식 1줄 추가 — "`wh-ingest: (vault 미등록 — wikihub.yaml.vaults 비어있음)`".

---

## L 항목 (Low — design.md 가독성 / Step 4 시점 흡수 가능)

### L1. 보고서 포맷의 라인 단위 표기 vs 카운트 요약 redundancy

**근거**:
- design.md §2.3 보고서 예시 — 12 라인 + 카운트 요약 1줄

**검토** (사용자 제시 검토 관점 5번째 항목):
- 정상 cycle 12 라인 dump = `2026-05-25 09:00 : 성공` 같은 라인이 12번 반복 — 카운트 요약 `(12회 모두 성공)` 1줄과 의미 동등 + 가독성 떨어짐
- 실패 라인은 reason 포함 — line dump 필수
- multi-vault N × 12 라인 = 보고서 길이 폭증 (H1 와 연계)

**권고**:
- (a) **성공 라인 압축 모드** — 연속 성공은 `09:00-12:00 : 성공 (3회)` 또는 `2026-05-25 09:00 ~ 11:00 : 성공 (12회)` 의 range collapse
- (b) 또는 **성공/실패 분리 섹션** — 실패 라인만 dump + 성공은 카운트만
- (c) MVP 는 현행 design 그대로 + Q11 cap 정책으로 자연 제어 — 단 backlog 등록 (`monitor_report_compact: true` toggle)

### L2. `vault@<vid>` 의 vid escape — future-proof

**근거**:
- 사용자 검토 관점 3번째 항목 — "vault@<vid> 의 vid 가 특수문자 포함 시 보고서 escape"
- design.md §2.3 보고서 예시 — `[vault: gdrive]` (영문자만)

**검토**:
- ADR-0019 (per-vault systemd unit substitution) + vault@.service.template 의 instance name 제약은 systemd 가 internal escape (e.g. `-` → `\x2d`) — wikihub.yaml 의 `vaults[*].id` 가 실제 ASCII alnum + `_` 제약인지 확인 필요
- design.md parse_mode=None plain text 라 HTML escape 불요 → 특수문자 raw dump OK
- 단 vid 가 multi-byte (한국어) 인 경우 telegram api 의 UTF-8 처리는 정상이나, 라인 정렬 width 변동 — cosmetic

**권고**: backlog `vid_charset_validation`. design.md §2.3 에 "vid 는 wikihub.yaml schema 의 ASCII alnum + `_` 제약 가정" 1줄. 현행 단일 vault `gdrive` 라 immediate impact 없음.

### L3. `_system/commands/` 의 wh-monitor 스킬 부재 → Hermes 카탈로그 부정합?

**근거**:
- plan.md:31 — `~~_system/commands/monitor.md~~ 삭제 (D1 정정)` — Hermes 스킬 안 만듦
- ADR-0032 (Hermes skill registration policy) — wh-* 스킬은 _system/commands/ 의 SKILL.md 정본화

**검토**:
- monitor 는 systemd-driven Python 직접 호출 → Hermes 스킬 아님 → _system/commands/ 등록 불요
- 단 사용자/운영자가 `claude` 안에서 `/wh-monitor` 같은 자연어 invocation 기대 가능 — 본 design 은 그걸 의도적으로 회피
- design.md §2.9 `_system/commands/*` row = "변경 없음 (스킬 안 만듦)" — 명시되어 있음

**권고**: 정합. 운영자가 monitor 보고서를 ad-hoc 트리거하고 싶을 때 path = `systemctl --user start wikihub-monitor.service` (DoD V 검증 절차와 동일). 이를 design.md §"운영 안내" 절 신설하면 더 명확 — 1줄 추가: "운영자 ad-hoc 트리거: `systemctl --user start wikihub-monitor.service` (스킬 invocation 없음 — systemd 직접)".

### L4. ADR-0024 §"v0.1.5 Note" 와 본 feature 의 관계 명시 미흡

**근거**:
- ADR-0024:208-211 (v0.1.5 Note) — "본 ADR 의 contract 본문 그대로 유지. dispatch architecture 는 ADR-0037 confirm. v0.2.x notify_via_hermes stub 도 ADR-0037 이 직접 Telegram bot API 호출로 대체"
- design.md §2.9 — ADR-0024 row = "monitor 가 fatal channel 과 분리된 가시성 layer — 의미 충돌 없음. 변경 없음"

**검토**:
- ADR-0024 의 contract = "fatal → alert" 의무 — monitor 는 fatal alert 가 아니라 daily summary → contract 무관 OK
- 단 ADR-0024 § Note 가 "v0.1.5 wave" 만 추가됐고 본 feature (v0.1.8 monitor) 가 같은 Telegram 채널 재사용한다는 명시 부재 — ADR-0037 § "후속 영향" 만으로 cross-link 충분한지

**권고**: ADR-0024 본문 미수정 유지 (contract 그대로). ADR-0037 § "후속 영향" 의 1줄 cross-link 가 정본 추적 충분. (L4 는 fully L 수준 — Step 4 검토 시 한 번 더 확인.)

### L5. monitor.service 의 `Restart=` 미설정 명시 — lint/vault 패턴 정합 확인

**근거**:
- design.md:93 — `# Restart= 미설정 — oneshot, timer 책임.`
- lint.service.template — 동일 패턴 (lint.service.template:24)

**검토**: 정합. lint.service / vault@.service / pending-monitor.service 모두 oneshot + Restart= 미설정 — monitor 도 같은 패턴.

**권고**: 정합. 본문 명시되어 있음 — 추가 조치 없음.

---

## 통과 관점 (정합 확인된 항목)

- **D1 정정 (Hermes 스킬 + LLM 요약 → Python 직접 + 정적 보고서)** — ops-alert.py / pending_monitor.py 패턴 정합. ingest/lint/graphify 의 결정적 report 패턴과 의미론적 일관 (analysis_and_design.md:23-25). LLM token cost 0 + 디버깅 용이성 + latency 의 3 이점 명확.
- **lib/telegram.py 분리** — parse_mode 옵션화로 ops-alert 의 HTML / monitor 의 plain text 분기 안전 (analysis_and_design.md:226-247). ADR-0037 §D1 의 send_telegram 시그니처 확장 → backward-compat.
- **systemd OnCalendar `*-*-* 09,21:00:00 Asia/Seoul`** — systemd 242+ 의 TZ suffix 지원 (analysis_and_design.md:121). KST DST 없어 corner case 없음.
- **EnvironmentFile=-%h/.config/wikihub/env** — ADR-0036 §D2 / ADR-0037 §D1 정합. lenient prefix `-` 로 파일 부재 시 unit start fail 안 함.
- **SuccessExitStatus=0 75** — lint.service / vault@.service 와 정합. Retryable exit 75 = 다음 fire 자연 재시도.
- **`operations.monitor_enabled` yaml toggle + install.sh `_migrate_agent_schema` Group B 자동 추가** — yaml drift migration 패턴 정합 (ADR-0035 patch policy).
- **graphify chain single-source from lint Step 9 (ADR-0036 §D6)** — monitor 가 lint.service journal 만 수집 + lint.md 의 graphify 마커 reading → ADR-0036 의 single-source 정합 (단 H3 의 EXIT_STATUS 124 분기 정정 조건부).
- **ADR-0023 sparse-checkout** — scripts/lib/telegram.py 신규 파일은 scripts/ 디렉토리 단위로 sparse 자동 포함 (analysis_and_design.md:337). 정합.
- **branch_strategy_formalize 5 액션 git workflow** — plan.md 의 v0.1.8 feature/wikihub_monitor 분기 + Step 5 squash → canary force-update 흐름 정합.
- **Q3 Q4 Q5 Q6 등 plan 단계 미결 사항이 design 단계에서 explicit 결정됨** — design.md §"미결 사항 (잔여)" 가 plan.md 의 Q1-Q8 중 다수를 흡수 + Q9-Q13 의 잔여로 좁힘.
- **design.md §2.9 의 7 row 연계 정합 매트릭스** — ADR-0023/0024/0030/0032/0036/0037 + commands/* + backlog 의 모든 영향 영역 행별 확인. 누락 = M3 의 wiki-schema.md 1건만.
- **§5 DoD 13 체크리스트** — implementation 단계의 검증 가능 기준 (Karpathy 원칙 4: Goal-Driven Execution) 충족.

---

## 범위 외 발견 (별도 feature / backlog 대상)

### X1. `_state/monitor_last_run.json` heartbeat — monitor 자기 가시성

C2 의 자기 부정 risk 해소 path 중 (b) heartbeat — closed loop 아닌 enriched path 가능: monitor 가 매 fire 시 `_state/monitor_last_run.json` 영속 + **pending_monitor.py 가 같은 file age 검사하여 24hr 이상 stale 시 ops-alert 발화**. pending_monitor 가 이미 age-based monitor 패턴이라 자연 흡수. — 별도 feature `monitor_self_health` 후보.

### X2. monitor 보고서의 actionable diagnostics — operator-facing 운영 안내

사용자 검토 관점 4번째 항목 — "vault@gdrive 실패 시 운영자가 어떻게 진단?" — 보고서에 진단 명령 예시 1줄 추가 (예: "조치: `journalctl --user -u wikihub-vault@gdrive.service -n 100`"). 본 feature 의 §2.3 포맷 확장 또는 별도 follow-up — design.md §"운영 안내" 절 신설하면 자연 흡수. backlog `monitor_actionable_remediation`.

### X3. weekly digest / monthly summary 의 3번째 caller — lib/telegram.py ADR 격상 트리거

M1 에서 언급. monitor 다음의 weekly aggregate (예: 1주일 ingest 성공률 / lint chain churn rate) 가 등장하면 `lib/telegram.py` 가 3 caller 보유 → ADR-NNNN 격상. 본 feature 범위 외.

### X4. multi-channel dispatch — Slack/Discord/email

ADR-0037 §"재검토 트리거" 의 dispatch 추상화 — 운영자가 Telegram 외 채널 원할 때. monitor 가 Telegram 외 채널도 지원하면 lib/dispatch.py 같은 채널 추상화 layer 필요. 본 feature 범위 외.

### X5. monitor 보고서 → wiki 자동 인덱싱

monitor 의 매 fire 보고서를 wiki/_meta/operations/ 같은 위치에 markdown 으로 영속 + lint chain 이 wiki 의 일부로 인덱싱 — 운영 history 영구 trace. 본 feature MVP 범위 외. backlog `monitor_report_persistence`.

### X6. install.sh `_step8_guide` 의 monitor 검증 명령 안내

design.md DoD 의 V 검증 절차 (`systemctl --user start wikihub-monitor.service`) 는 design 의무 — install.sh `_step8_guide` 의 운영자 안내 문구에 monitor 검증 1줄 추가 권장 (Step 3 에서 자연 흡수 가능 — 본 feature 범위 안). C2 권고와 묶어 design.md §"운영 안내" 절 신설 시 함께 흡수.

---

## 우선순위 요약 (Step 3 진입 전 권장 조치)

| # | 항목 | 분류 | 조치 | 예상 design.md 갱신 |
|---|---|---|---|---|
| 1 | C1 — ops-alert 채널 동일화 noise | C | 보고서 포맷에 ops-alert 발화 마커 OR design intent declare | §2.3 + §"운영 안내" 신설 (+10 줄) |
| 2 | C2 — monitor 자체 silent dead | C | exit code 분리 (config/import fail=2, runtime fail=75) + OnFailure 부분적 설정 | §2.1.1 + §2.2.2 (+5 줄) |
| 3 | H1 — Telegram 4096 chars limit | H | 길이 cap 정책 + backlog 등록 | §2.3 (+3 줄) + backlog 1항목 |
| 4 | H2 — Persistent=true catch-up 시맨틱 | H | 윈도우 wall clock 정의 명시 + caveat | §2.2.2 (+2 줄) |
| 5 | H3 — graphify_status EXIT_STATUS 분기 정정 | H | MESSAGE pattern only 로 단순화 | §2.5 (-3 줄) |
| 6 | M3 — wiki-schema.md 정합성 row | M | 연계 매트릭스에 1 row | §2.9 (+1 줄) |
| 7 | L3 — 운영 안내 절 (ad-hoc 트리거) | L | §"운영 안내" 절 신설 | 별도 신규 절 (+5 줄) |

총 예상 design.md 갱신: **+25~30 줄 / -3 줄** — v2 로 승격 후 사용자 승인 → Step 3 진입.

---

## 종합 결론

**통과(조건부)**. 본 design 의 architectural 방향 (Python 직접 + 정적 보고서 + lib/telegram.py 분리 + OnCalendar 09/21 KST + EnvironmentFile 재사용) 은 ADR-0024 / ADR-0036 / ADR-0037 의 의도와 정합하고 ops-alert.py / pending_monitor.py / lint.service 의 기존 패턴과 의미론적 일관성을 유지한다.

조건부 = C1 (ops-alert ↔ monitor noise) + C2 (monitor 자기 silent dead) 2건은 design.md 본문 갱신 후 v2 승격 + 사용자 승인 필수. H 항목 3건은 Step 3 default 채택 흡수 가능하나 design.md 에 explicit 명시 권장.

D1 정정 (LLM → Python 직접) 의 의사결정 자체는 사용자 검토 후 정정된 것으로 trace 명확 + 정합. 본 feature 의 정본은 plan.md + design.md + (ADR-0037 § "후속 영향" 1줄) 로 충분 — ADR 신설 미생성 결정 타당.
