# Design Review 1 — F5 hermes_adapter (CR1: spec)

- **리뷰 대상**: analysis_and_design.md v1
- **리뷰어**: CR1 (spec / ADR 정합 / schema 정확도)
- **리뷰 일자**: 2026-05-18
- **종합 판단**: **Accept with revisions** — ADR-0011 supersede 트리거 조건이 Step 2 종료 조건과 모순(C1) + `_system/commands/` ↔ ADR-0006 정본성 충돌(C2) + 함수명/line ref drift(C3) 3건이 Step 2 v2 lock 전에 반드시 해결되어야 함. 나머지는 backlog 처리 가능.

---

## CRIT — 진입 차단

### CR1-CRIT-1 — ADR-0011 supersede 결정이 Step 3 VM 실측에 의존하면 Step 2 종료 불가

- **위치**: analysis_and_design.md §5.4 (line 274), §7.1 (line 381), §8 (M-4)
- **결함**: §7.1 의 처리 표에 "Hermes colon 미지원 확정 시 ADR-0011 supersede + 신규 ADR (`wh-` lock). 일부 동작 시 Note 만. **Step 3 VM 검증 결과로 결정**" 라고 명시. 그런데 본 설계서는 §5 전체 (skill name 5건, yaml.skill_prefix default, systemd ExecStart, wiki-schema 일괄 치환, README/AGENTS 등) 가 이미 **`wh-` 일괄 채택을 전제로 작성됨**. supersede 결정이 Step 3 의존이면 Step 2 종료 조건(§9.1) 의 "사용자 승인 — approved 마커" 시점에 ADR-0011 의 정본 상태가 미정. ADR-0011 §"agent 호출 예" L:43-51 가 colon 표기를 정본 호출 예시로 lock 한 상태라 silent drift.
- **권장 해결책**:
  1. Step 2 단계에서 ADR-0011 의 처리를 **선결정**으로 lock — colon support 가 불확실하면 보수적 `wh-` supersede 결정 + Step 3 VM 가 colon 도 동작함을 발견하면 신규 ADR 의 Note 로 "colon 도 호환 — operator override 가능" 추가하는 비대칭 fallback. 거꾸로 (default colon 유지 + 미동작 시 supersede) 는 Step 2 v2 의 spec 정합 불가.
  2. 또는 §5 전체를 "옵션 X — `wh-` 채택 가정" 의 conditional 로 marking + `wh:` fallback 의 spec 도 v1 에 병기. 현재 v1 은 둘을 섞어 작성 — 호출자 (메인테이너·리뷰어) 가 어느 path 가 정본인지 알 수 없음.

### CR1-CRIT-2 — `_system/commands/` 정본 이전(§5.2.A) 이 ADR-0006 의 source-of-truth 정의와 silent 충돌

- **위치**: analysis_and_design.md §5.2 (line 235), §5.7 (line 322)
- **결함**: §5.2.A 채택 — "`_system/skills/wh-<cmd>/SKILL.md` 가 단독 정본. `_system/commands/<cmd>.md` 는 본 feature 에서 본문 그대로 skill 로 이전 + 원본은 '이전됨' Note 만". 그러나:
  - **ADR-0006 §Decision (line 39-48, line 53)**: "`_system/commands/ingest.md` playbook이 전체 흐름의 정본" — 명시적으로 playbook = 정본 lock. §"이유": "단일 진실의 원천: `_system/commands/ingest.md` playbook이 전체 흐름의 정본". §"긍정": "playbook이 spec과 구현 사이의 단일 다리".
  - **ADR-0010 §"도구별 책임 매트릭스"** L:153: "hermes skill add --name <prefix><cmd> --playbook /opt/wikihub/_system/commands/<cmd>.md" — playbook path 의 정본을 commands/ 로 lock.
  - **wiki-schema.md L:20** "commands/ # /wh:* 명령어 playbook" + **L:315** "명령어 — `_system/commands/` playbook 참조" — 정본 path 표기.
  - §7.2 의 정합 분석은 wiki-schema.md L:319-324 "표기 갱신" 만 명시 — **정본 위치 변경 (L:20·L:315) 누락**.
  - 즉 §5.2.A 채택은 ADR-0006·0010 의 `_system/commands/` 정본성을 silent override. 본 변경은 Note 가 아니라 **ADR-0006 의 supersede 또는 partial supersede (yaml writer 책임 reassign 패턴, ADR-0031 → ADR-0010) 가 필요한 architectural change**.
- **권장 해결책**: 둘 중 택1.
  - **(a) 5.2.A 채택 유지 시**: §7.1 의 ADR-0006 행을 "영향 없음" → "**Partially superseded by ADR-0032 — playbook 정본 위치를 `_system/commands/` → `_system/skills/wh-<cmd>/SKILL.md` 로 reassign**" 으로 격상. ADR-0006 본문에 Note 추가 + ADR-0010 L:153 의 `--playbook` path 갱신 의무 + wiki-schema.md L:20·L:315 의 path 표기 갱신 의무를 §9.2 Step 3 종료 조건에 추가.
  - **(b) 안전 fallback**: §5.2.C (build-time include 또는 symlink) 또는 §5.2.B (commands 가 정본, SKILL.md 가 frontmatter wrapper) 재검토. v0.1.0 의 minimal change 원칙 (CLAUDE.md §2 Simplicity First) 정합 — ADR-0006 정본성 보존이 가장 적은 architectural drift.

### CR1-CRIT-3 — install.sh 함수명/line reference 가 실제 코드와 drift

- **위치**: analysis_and_design.md §3.2 (line 99-104), §5.6 표 (line 311-312), §9.2 Step 3 종료 조건
- **결함**: 설계서가 함수명을 **`_step8_best_effort_wh_setup()`** 으로 표기 (§3.2 line 99, §5.6 line 312). 실제 install.sh:1201 의 함수명은 **`_step8_wh_setup_skill_meta()`**. 설계서가 Step 3 구현 진입 시 grep target 이 안 맞음 — `sed -i` 또는 grep-replace 가 silent miss. 또한 §3.3 의 `render_systemd_units.py` line range (L:145-163) 는 정확하나, §3.1 의 `_step6_agent_skill()` line range (L:701-706) 는 실제 (L:701-706) 와 일치 — drift 는 §3.2·§5.6 에 국한.
- **권장 해결책**: 설계서 v2 에서 함수명을 install.sh 의 정본 (`_step8_wh_setup_skill_meta`) 으로 교정 + 본 함수의 [INSTALL_MODE != update] guard (L:1202) 와의 호환성 surface — 신규 install 의 첫 호출 시 본 함수 skip → V6 의 PASS 조건 ("exit 0 + skill dispatch") 가 update mode 만 검증함을 명시.

---

## HIGH — Step 2 v2 에서 반영 권장

### CR1-HIGH-1 — `oneshot_args` 의 `{skill}` placeholder 가 ADR-0012 추상화 모델을 깸

- **위치**: analysis_and_design.md §5.4 (line 266), §7.1 ADR-0012 행
- **결함**: ADR-0012 §"`wikihub.yaml.agent` 스키마" + §"systemd unit 생성" L:86: `ExecStart={agent.binary} {agent.oneshot_args[*]} "<prompt>"` — `oneshot_args` 가 **agent 의 one-shot 호출 args** (semantic 고정: prompt 가 마지막에 append). 본 설계의 `oneshot_args: ["chat", "--skills", "{skill}", "--query"]` 는 `oneshot_args` 안에 **per-call placeholder 도입** — schema 의미론이 "정적 args" → "동적 args (per-unit substitution)" 로 silent migration. ADR-0012 §"이유" 의 "agent-agnostic 원칙 정합" 도 영향 — 다른 agent (codex/gemini) 가 placeholder convention 을 따른다는 보장 없음.
- 또한 §7.1 표가 "ADR-0012: **Note 추가**" 로 분류했으나, oneshot_args 의 semantic 변경 (정적 → 동적) 은 **additive 가 아니라 contract migration**. ADR-0031 의 yaml schema v1 호환 (additive only) 조건 (§Decision E) 도 의심.
- **권장 해결책**:
  1. 설계서 v2 에서 ADR-0012 처리를 "Note 추가" → "**§Decision 갱신 — `oneshot_args` 의 placeholder substitution semantics 추가** (Status 유지, content 변경)" 로 격상. ADR-0012 본문에 "`{skill}` placeholder 가 per-unit substitute" 절 추가.
  2. 또는 placeholder 를 `oneshot_args` 가 아닌 별도 키 (`skill_invocation_args: ["chat", "--skills", "{skill}", "--query"]`) 로 분리 — `oneshot_args` 의 기존 semantic 보존. install_scope_reduction (ADR-0031) 의 catalog 명시 패턴 정합.

### CR1-HIGH-2 — `wikihub.yaml.example` 의 `skill_prefix` default 변경이 운영본 drift 처리 미명세

- **위치**: analysis_and_design.md §5.4 (line 269), §5.8 (line 326-336)
- **결함**: `skill_prefix: "wh:"` → `"wh-"` 변경. install_scope_reduction archive (2026-05-18) 후 운영자가 이미 `/wh:setup` 첫 호출로 `wikihub.yaml` 을 생성했다면 operational yaml 의 `skill_prefix` 는 `wh:`. F5 적용 후 update 호출 시 ADR-0031 §Decision B catalog 의 4필드에 `agent.*` 는 미포함 — Step 0 drift fix 가 본 필드를 안 다룸 (line 119 "agent.binary 미포함 이유: ... 의도적으로 다를 수 있음"). 즉 **operational `skill_prefix` 는 `wh:` 잔존 → systemd render 시 `{skill_prefix}lint` 가 `wh:lint` 로 합성 → Hermes dispatch fail (M-4 미결)**.
- **권장 해결책**:
  1. ADR-0031 §Decision B catalog 에 `agent.skill_prefix` 추가 (install-derived 로 reclassify) — install-time 의 `wh-` lock 을 operational 에 강제 동기화. 그러나 ADR-0031 의 "agent.* 미관여" 정책 (line 119) 과 모순 — 추가 정책 결정 필요.
  2. 또는 F5 가 별도 migration step 명시 — install.sh `_step6_agent_skill` 진입 시 `WIKIHUB_INSTANCE_ROOT/wikihub.yaml` 의 `agent.skill_prefix` 값이 `wh:` 이면 명시 confirm 후 `wh-` 로 patch (ruamel atomic write).
  3. §5.8 에 본 drift 시나리오 명시 + 처리 방향 lock 필수.

### CR1-HIGH-3 — `{skill_prefix}` 가 systemd template 에서 slash 없이 합성

- **위치**: analysis_and_design.md §5.5 (line 290-305), §6.1 표
- **결함**: 현재 systemd template 본문:
  - `wikihub-vault@.service.template:19` — `ExecStart={agent_invocation} "{skill_prefix}ingest --vault %i"`
  - `lint.service.template:14` — `ExecStart={agent_invocation} "{skill_prefix}lint"`
  - 즉 `wh:ingest` 또는 `wh-ingest` 로 합성 — **leading slash 미포함**. ADR-0011 §"agent 호출 예" L:43-51 + 설계서 §6.1 의 Before/After 컬럼은 모두 `/wh:ingest` / `/wh-ingest` 로 slash 포함 표기. Hermes 의 slash-command dispatch (§2.2 line 70 "Every installed skill is automatically available as a slash command") 는 slash 가 trigger token. **현 template + 설계서 §5.5 의 `agent_invocation_for_wh_ingest` substitution 모델 둘 다 본 silent bug 를 carry**.
  - 설계서 §5.5 후반 inline 예시 (line 302): `ExecStart={agent_invocation_for_wh_ingest} "/wh-ingest --vault %i"` — **slash 포함**. 그러나 현 template 는 `{skill_prefix}` 가 slash 미포함. 즉 §5.5 의 두 모델 (placeholder 도입 vs per-skill key 도입) 사이에 slash 의 source 가 다름.
- **권장 해결책**:
  1. §5.5 가 template content 변경도 명시 — `{skill_prefix}ingest` → `/{skill_prefix}ingest` (slash 명시) 또는 placeholder 모델 채택 시 `{agent_invocation_for_wh_ingest}` + `"/wh-ingest ..."` 로 일관.
  2. §9.2 Step 3 종료 조건에 systemd template 5개 (`wikihub-vault@.service.template`, `lint.service.template`, 향후 `query.service.template`, `graphify.service.template` 등) 의 slash 합성 정합 검증 추가.

### CR1-HIGH-4 — VM 테스트 V3 의 PASS 기준이 schema (`wiki/sources/<vault>/log.md`) 와 mismatch

- **위치**: analysis_and_design.md §9.3 V3
- **결함**: V3 PASS 기준: "**`_state/<vault>/log.md`** 갱신". 그러나:
  - **ADR-0005** + **wiki-schema.md L:34**: log.md 정본 위치 = `wiki/sources/{vault_id}/log.md`.
  - **ingest.md L:152·191**: `wiki/sources/<vault_id>/log.md`.
  - `_state/<vault>/` 는 ADR-0007 의 JSON state 디렉토리 (pending_ingest.json, file_map.json 등). log.md 의 home 아님.
- **권장 해결책**: §9.3 V3 의 PASS 기준 표기를 `wiki/sources/<vault>/log.md` 로 교정. Step 3 가 본 spec 으로 grep 하는 자가 검증 도구 자동 변경 → silent mismatch 회피.

### CR1-HIGH-5 — `_step8_wh_setup_skill_meta` 의 `WIKIHUB_NONINTERACTIVE=1` + timeout 300s + chat transcript 미결의 누적 위험

- **위치**: analysis_and_design.md §5.6 (line 312), §8 M-3
- **결함**: 설계서 §5.6 가 `hermes -z "/wh:setup"` → `hermes chat --skills wh-setup --query "/wh-setup"` 변경. 그러나:
  - M-3 미결: `chat -q` 의 stdout 형식 (transcript or final-only) 가 불확실 — **transcript 면 logging volume 폭증**. 본 호출은 `WIKIHUB_NONINTERACTIVE=1` + `timeout 300` (line 1214) 으로 호출. transcript 가 (a) interactive prompt 를 포함하면 NONINTERACTIVE 모드에서 hang → 300s timeout 까지 block, (b) 대용량 transcript 가 install.log 의 tee buffer 를 채우면 install.sh 진행 차단.
  - 설계서 §9.3 V6 PASS 기준 ("exit 0 + skill dispatch") 가 본 risk 를 cover 안 함.
- **권장 해결책**: §5.6 에 `--quiet` 또는 `--final-only` 같은 chat flag 도입 의무를 surface — M-3 의 Step 3 VM 결과로 정본화. NONINTERACTIVE 모드에서 transcript hang 가능성을 V6 의 PASS 기준에 추가 ("stdout 크기 < X KB").

### CR1-HIGH-6 — `_step6_agent_skill` 의 `~/.hermes/config.yaml` 패치가 ADR-0023 safety guard 와 boundary 충돌

- **위치**: analysis_and_design.md §5.3 (line 241-247)
- **결함**: §5.3 — install.sh 가 `~/.hermes/config.yaml` 의 `skills.external_dirs` 에 atomic append. 그러나:
  - **ADR-0023 §safety guard 3개** L:44-47 은 `$WIKIHUB_HOME` 의 wipe scope 만 명시. `~/.hermes/` 는 wikihub 외부 path — wipe scope 가 아니라 **wikihub 가 사용자 home 의 다른 도구 config 를 mutate** 하는 신규 패턴.
  - ADR-0023 의 보안 모델 (메인테이너 GitHub + TLS + shasum) 은 `~/.hermes/config.yaml` 의 backup/rollback 정책 미명세. install.sh 의 atomic write 가 실패하면 (예: ENOSPC) Hermes 의 다른 skill 설정이 손상 가능.
  - `WIKIHUB_NONINTERACTIVE=1` 모드의 stderr 안내 후 진행 (§5.3 line 246) — wikihub 외부 파일을 silent mutate 하는 정책이 ADR-0023 의 "운영자 mental model 명시" 원칙과 충돌.
- **권장 해결책**: 신규 ADR-0032 (skill registration policy) 에 다음 명시:
  1. `~/.hermes/config.yaml` 의 patch 시 backup (`~/.hermes/config.yaml.wikihub-backup-<timestamp>`) 자동 생성.
  2. NONINTERACTIVE 모드의 default 를 "stderr 안내 후 진행" → "stderr 안내 + exit 1 (별도 flag `--accept-hermes-config-patch` 필수)" 로 강화 (M-8 의 결정 방향 사전 lock).
  3. install.sh `_rollback_if_failed` (ADR-0030) 가 `~/.hermes/config.yaml.wikihub-backup-*` 도 복원 대상에 포함.

---

## MED — backlog 처리 가능

### CR1-MED-1 — ADR-0032 의 범위가 1 ADR 에 묶일 만큼 동일 관심사인지 의심

- **위치**: analysis_and_design.md §7.1 (line 384)
- **결함**: ADR-0032 가 (a) external_dirs vs copy 선택, (b) SKILL.md format 정책, (c) skill source-of-truth 결정 3건 묶음. ADR-0030 의 "4 sub-decision 묶음" 패턴은 "update workflow safety" 라는 동일 관심사로 정당화 (§Considered Options 첫 줄). 본 ADR-0032 의 3 sub-decision 은:
  - (a) external_dirs vs copy = install/update 시점 메커니즘 (운영 도구 책임).
  - (b) SKILL.md schema = Hermes 와의 wire format.
  - (c) source-of-truth = wikihub 내부 정본 위치 (CR1-CRIT-2).
  - 셋의 관심사 분리도가 ADR-0030 의 4 sub-decision (update path 의 atomic safety) 대비 약함.
- **권장 해결책**: ADR-0032 = (a)+(b) 묶음 ("Hermes 와의 skill 등록 wire/registration 메커니즘"), ADR-0033 = (c) ("wikihub playbook 정본 위치 — `_system/commands/` vs `_system/skills/`") 로 분리. CR1-CRIT-2 의 ADR-0006 영향 항목과 정합.

### CR1-MED-2 — M-2 dispatch 결정성 임계치가 binary (100%/<100%)

- **위치**: analysis_and_design.md §8 M-2
- **결함**: "동일 prompt 10회 호출 → skill 진입 100% 확인. **<100% 시 옵션 (γ) wrapper 재검토**." Hermes 의 chat-mode 가 LLM-mediated dispatch 라면 stochastic — 100% 보장은 sample size 부족. 또한 <100% 즉시 (γ) wrapper 검토는 over-reaction (예: 9/10 도 ADR-0006 의 "LLM tool use 비결정성은 본 feature 범위 밖" 의 invariant 내일 수 있음).
- **권장 해결책**: 임계치 정합 결정 — 예: 95% pass + p99 latency 한계. sample size 도 10 → 30 또는 50. 또한 (γ) wrapper fallback 의 trigger 가 결정성 단독이 아니라 "결정성 + 운영자 SLA" 둘 다 충족이어야 step-back 명시.

### CR1-MED-3 — V1 PASS 조건이 Hermes 미설치 환경에서 unverifiable

- **위치**: analysis_and_design.md §9.3 V1·V7
- **결함**: V1 "install.sh 신규 install + Step 6 external_dirs 등록 — `~/.hermes/config.yaml` 에 wikihub skill path 등록됨". V7 "Hermes 미설치 detect — `_step6_agent_skill` 가 warn-only 진행". V1 PASS 는 Hermes 설치 가정 (없으면 `~/.hermes/config.yaml` 자체 미존재). V7 PASS 는 Hermes 미설치 가정. 둘이 동일 VM 시나리오에서 sequential 실행 안 됨 — VM 분리 또는 verify matrix 명시 필요.
- **권장 해결책**: §9.3 헤더에 "VM 환경 prerequisite 행렬 — V1·V2·V3·V4·V5·V6 = Hermes 설치 VM, V7 = Hermes 미설치 VM (또는 PATH 차단)" 명시.

### CR1-MED-4 — `oneshot_args` 의 `{skill}` placeholder 가 ADR-0031 §Decision E 의 example_version 검증 통과 의심

- **위치**: analysis_and_design.md §5.8 (line 336)
- **결함**: 설계서가 "ADR-0031 의 schema version (v1) 유지 — additive change only". 그러나 oneshot_args 값 (list 의 elements) 자체가 변경 — `["-z"]` → `["chat", "--skills", "{skill}", "--query"]`. ADR-0031 §Decision E 의 검증은 yaml `version` 필드 비교 (schema version) — `agent.*` 값 변경은 schema 변경 아님 (key 추가/제거 없음), so example_version 검증은 통과. 그러나 operational `wikihub.yaml` (`oneshot_args: ["-z"]` 잔존) 과 `.example` (`oneshot_args: ["chat", ...]` 신본) 의 drift 가 ADR-0031 §Decision C (drift fix) 의 catalog (4필드) 외라 강제 sync 안 됨 — CR1-HIGH-2 와 동일 root cause.
- **권장 해결책**: CR1-HIGH-2 의 해결책 일관 적용 — ADR-0031 catalog 의 `agent.*` 처리 결정. example_version 검증 자체는 별 이슈 없음 명시.

### CR1-MED-5 — §7.4 가 sparse-checkout fetch list 의 install.sh 위치 명세 부재

- **위치**: analysis_and_design.md §7.4 (line 397)
- **결함**: "install.sh 의 `_step2_clone` 의 sparse-checkout 명세에 `/_system/skills/` line append." 그러나 sparse-checkout 정본은 install.sh:290 `WIKIHUB_SPARSE_PATHS=(_system scripts install.sh wikihub.yaml.example README.md LICENSE)`. `_system` 가 이미 포함 → `_system/skills/` 자동 fetch. 즉 **§7.4 의 "추가 필요" 는 false — 이미 cover 됨**. 또한 `_step2_clone` 자체가 array 를 정의하는 게 아니라 `_apply_sparse_checkout` 가 사용. line reference 도 부재.
- **권장 해결책**: §7.4 를 "**검증 결과 — sparse-checkout 의 `_system` 전체 포함이라 `_system/skills/` 는 자동 cover. 별도 patch 불요**" 로 교체. §9.2 Step 3 종료 조건의 "sparse-checkout 에 `/_system/skills/` 추가" 항목 삭제 또는 "검증 only" 로 약화.

### CR1-MED-6 — README.md L:179 의 `wh:*` 표기 갱신 누락 surface

- **위치**: analysis_and_design.md §6.2 (line 361), §9.2 Step 3 종료 조건
- **결함**: §6.2 "운영자 mental model: README + commands 본문 + ADR 모두 `wh-` 표기로 일괄". 실제 README.md L:179 의 `wh:*` 표기 1건 — 명시 list 에 없음. §9.2 의 마지막 항목 "README.md install snippet 의 F5 후속 안내 → ✅ archive 표기로 갱신" 가 본 표기 변경을 cover 하는지 모호.
- **권장 해결책**: §9.2 에 "README.md L:179 의 `wh:*` → `wh-*` 표기 정합" 별도 항목 추가.

---

## LOW — 참고

### CR1-LOW-1 — M-7 의 grep 대상 명세 부재

- **위치**: §8 M-7
- **결함**: "_system/commands/ → _system/skills/ 이전 시 wiki/ 의 cross-link 영향 — grep 후 일괄 치환." `wiki/` 디렉토리 자체는 runtime 산출물 — repo 의 source path 가 아닐 가능성 (wiki/ 는 sparse-checkout 에 없음). 본 grep 의 대상은 `_system/`·`docs/`·`README.md`·`AGENTS.md` + features/active 가 더 정확.
- **권장 해결책**: M-7 의 검색 대상 path 를 명시 — `_system/` + `docs/adr/` + 루트 markdown 파일.

### CR1-LOW-2 — V5 의 "Hermes 재시작 없이" PASS 기준이 너무 약함

- **위치**: §9.3 V5
- **결함**: "Hermes 재시작 없이 skill 본문 갱신 인식 (또는 `hermes skills audit` 1회)". "또는" 분기 가 너무 broad — `audit` 가 매번 필요한 환경이면 update_mode 자동화 사슬에 추가 단계 필요.
- **권장 해결책**: V5 의 PASS 를 "재시작 불필요" 또는 "`audit` 1회 필요 — 그 경우 update_mode 의 어디서 audit 호출" 로 명시 binary 결정.

### CR1-LOW-3 — §10 Out of Scope 에 `_system/commands/` 디렉토리 완전 삭제 (5.7.B) v0.2.x 가 별도 feature 로 명시되나, 본 v1 에서 5.2.A (이전) 채택과 정합성

- **위치**: §10 (line 464), §5.2 (line 235), §5.7 (line 322)
- **결함**: §5.2.A "본 feature 에서 본문 그대로 skill 로 이전" + §10 "`_system/commands/` 디렉토리 완전 삭제 (5.7.B) — v0.2.x feature". §5.7.A 는 "stub Note 만 남김" 채택. 즉 v0.1.0 에서 commands/ 가 빈 stub + skills/ 가 본문 — **dual 위치 운영**. CR1-CRIT-2 의 ADR-0006 정본성 + 본 dual 위치가 maintainer onboarding 의 confusing surface (ADR-0006 본문은 commands/ 정본 가정 유지).
- **권장 해결책**: CR1-CRIT-2 의 해결책에 본 항목 함께 lock — dual 위치 운영의 명시적 정본 (skills/) + commands/ stub 의 redirect 표기 강화.

### CR1-LOW-4 — `_step8_wh_setup_skill_meta` 의 update 모드 guard 가 V6 와 비호환

- **위치**: §9.3 V6, install.sh:1202 (`[[ "$INSTALL_MODE" != "update" ]] && return 0`)
- **결함**: V6 "_step8_best_effort_wh_setup 의 `chat --skills wh-setup --query "/wh-setup"` — exit 0 + skill dispatch". 그러나 함수는 update mode 에서만 진입 — 신규 install (V1) 시점에는 본 함수 skip → V6 의 호출 자체가 안 일어남. V6 의 검증 timing 명시 필요.
- **권장 해결책**: V6 에 "install 후 2번째 install.sh 호출 (update path) 에서 검증" 명시.

---

## 추가 관찰

- **결정 정합 관점**: 본 설계서는 v0.1.0 acceptance blocker — F4 backlog #12 close 책임. 핵심 변경 (skill 등록 + `chat -q -s`) 의 방향은 타당. 결함의 본질은 (a) Hermes 실측 결과의 **partial certainty** (M-1·M-2·M-3·M-4 가 Step 3 VM 의존) 와 (b) **기존 ADR 정본성 (ADR-0006·0010·0011) 의 명시적 reassign 부재** 둘. 본 둘이 동시에 resolved 되어야 Step 3 진입 가능.

- **Step 2 v2 의 최소 lock 사항** (CRIT 3건):
  1. ADR-0011 의 supersede 의 trigger 조건 비대칭화 (보수적 `wh-` 채택 + colon 호환은 fallback Note).
  2. `_system/commands/` ↔ `_system/skills/` 정본 reassign 의 ADR 표면화 (ADR-0006 의 Partial supersede 또는 ADR-0032 분리).
  3. install.sh 함수명 정합 (`_step8_wh_setup_skill_meta`).

- **ADR-0030 와의 독립성**: ADR-0030 §"후속 영향" 의 "F5 hermes_adapter 와 독립 — install.sh 가 systemd render 직접 수행이므로 hermes 부재·`/wh:setup` skill 미등록 상태에서도 update path full functional" 는 본 설계 §7.3 가 정합 처리. update_mode 의 invariant 가 F5 의 skill dispatch 결정성 미달 시에도 보호됨 — 정합.

- **schema 변경 누적**: F2~F5 의 schema 변경 누적이 wikihub.yaml v1 의 키 추가 (없음, 값 변경만) + commands/ → skills/ migration (path 변경) — schema_version: 1 잔존 정합 (additive only). 단 CR1-HIGH-1 의 `oneshot_args` semantic 변경은 schema 가 아니라 contract 라 별도 lock 필요.

- **테스트 cover 누락 risk**: §9.3 의 V1~V7 중 **rollback 시 `~/.hermes/config.yaml.wikihub-backup-*` 복원** (CR1-HIGH-6 권장 처리) 시나리오 미cover. ADR-0030 의 trap rollback 과의 정합 검증 추가 권장.

- **R≥2 의 CR2 관점 expectation**: CR2 (SRE) 가 cover 할 영역 — Hermes 미설치 detect 의 신규 install vs update 차이 (CR1-LOW-4 와 인접), external_dirs append 의 race (Hermes daemon 동시 read), update_mode rollback 시 ~/.hermes/ 영향 (CR1-HIGH-6). 본 CR1 은 spec/ADR 정합 단독 — runtime operational risk 는 CR2 의 domain.
