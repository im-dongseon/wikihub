# Design Review 3 — F5 hermes_adapter (CR3-1: spec closure)

- **리뷰 대상**: analysis_and_design.md v2 (R2 closure 검증)
- **리뷰어**: CR3-1 (spec / ADR 정합 closure)
- **선행 리뷰**: CR1 design_review_1.md (spec), CR2 design_review_2.md (SRE)
- **리뷰 일자**: 2026-05-18
- **종합 판단**:
  - **Closure 평가**: R2-CR1 의 CRIT 3건 CLOSED, HIGH 6건 CLOSED, MED 6건 CLOSED (단 MED-1 은 부분 CLOSED — ADR-0032 의 (a)+(b) 묶음 분리는 미수행, (c) source-of-truth 만 ADR-0033 으로 분리).
  - **신규 결함 (v2 도입)**: CRIT-N 1, HIGH-N 3, MED-N 4, LOW-N 2.
  - **최종 판단**: **v3 revision 필요** — 신규 CRIT (§5.6 중복 헤더 + `_step8_5_systemd_enable_only` 함수명 drift — CR1-CRIT-3 의 재발) 차단. 잔여 HIGH·MED 도 Step 3 진입 전 closure 권장.

---

## R2-CR1 closure 검증

### CR1-CRIT-1 → **CLOSED**
v2 §5.4.1 보수적 `wh-` 선결정 + §7.1 ADR-0011 Status → Superseded by ADR-0033 + 신규 ADR-0033 (`wh-` lock). §5 전체가 `wh-` 일괄 전제와 정합. CR1 권장 (1)(보수적 supersede + colon 호환은 fallback Note) 그대로 채택. closure 적절. 잔존 risk: ADR-0033 본문에 "VM 실측 후 Note 추가" 가 §9.3 V2/V3 의 dispatch 동작 측정과 명시 link 필요 (DoD 미세 보강 — LOW-N1 참조).

### CR1-CRIT-2 → **CLOSED**
v2 §5.2.B 채택 (`_system/commands/` 정본 유지, `_system/skills/_generated/wh-<cmd>/SKILL.md` 가 install-time materialized artifact). §7.1 ADR-0006 행 "영향 없음" 명시 정합 — ADR-0006/0010 정본성 보존. wiki-schema.md L:20·L:315 path 표기 변경 0. CR1 권장 (b) (안전 fallback — 5.2.B/C 재검토) 정확히 채택. closure 적절.

### CR1-CRIT-3 → **CLOSED**
v2 §5.6 함수명 `_step8_wh_setup_skill_meta` 로 교정 (§3.2 도 L:99 에서 일관) + §9.2 DoD 갱신. install.sh L:1201 실제 함수명과 일치 확인 완료. CR1 권장 정확히 채택. closure 적절. **단**, v2 가 새로 도입한 `_step8_5_systemd_enable_only` 함수명이 또 다른 drift (→ 아래 신규 CRIT-N1 참조).

### CR1-HIGH-1 → **CLOSED**
v2 §5.4.2 ADR-0012 처리를 "Note 추가" → "**§Decision 갱신 (Status 유지, content 변경 — placeholder substitution semantics 추가)**" 로 격상. §7.1 ADR-0012 행 동일 명시. CR1 권장 (1) 채택. closure 적절. 다른 agent (codex/gemini) 의 placeholder convention 은 v0.2.x 로 push 명시.

### CR1-HIGH-2 → **CLOSED**
v2 §5.4.3 `_migrate_agent_schema()` 신규 — F5 의 1회성 schema lift (skill_prefix·oneshot_args drift fix + interactive/non-interactive 분기 + backup). ADR-0031 catalog 의 "agent.* 미관여" 정책과 정합 (ADR-0031 강제 추가 안 함). CR1 권장 (2) 채택. closure 적절.

### CR1-HIGH-3 → **CLOSED**
v2 §5.5.3 systemd template 의 ExecStart 가 명시적 slash 포함 (`"/wh-ingest --vault %i"`) + per-skill substitution key (`{agent_invocation_for_wh_ingest}`) 일관. §6.1 비교 표도 정합. CR1 권장 (1) 채택. closure 적절.

### CR1-HIGH-4 → **CLOSED**
v2 §9.3 V3 PASS 기준 `wiki/sources/<vault>/log.md` 로 교정 (`_state/<vault>/` 표기 제거). wiki-schema.md L:34 / ingest.md L:152·L:191 과 정합. CR1 권장 정확히 채택. closure 적절.

### CR1-HIGH-5 → **CLOSED**
v2 §5.4.4 `--quiet` flag yaml.agent.oneshot_args default 포함 + §9.3 V3 PASS 기준 "stdout 크기 < 10 KB" 정량. M-3 부분 lock + Step 3 VM 의 효과 정량 측정 명시. CR1 권장 정확히 채택. closure 적절. (단, CR2-LOW-5 의 `_step8_wh_setup_skill_meta` 의 bash `timeout 300` 와 yaml.agent.timeout_sec=600 불일치 — 본 v2 §5.6 표에서 yaml-driven 으로 바뀌나 LOW 처리 잔존 — HIGH-N3 참조).

### CR1-HIGH-6 → **CLOSED**
v2 §5.3.2 flock + backup + atomic write + retention 명시 + §7.1 ADR-0023 §safety guard Note 확장 + §5.3.4 NONINTERACTIVE 동의 모델 통일. CR1 권장 (1)(2)(3) 모두 반영. closure 적절. (다만 ADR-0023 의 safety guard 3개가 `$WIKIHUB_HOME` 의 wipe scope 만 명시 — 외부 자산 mutate 의 별도 invariant 추가는 ADR-0023 본문 수정 의무 명시화 필요 — MED-N1 참조).

### CR1-MED-1 → **PARTIAL**
v2 §7.1 ADR-0033 신규 (`wh-` lock, supersedes ADR-0011) 로 prefix lock 만 분리. ADR-0032 는 여전히 (a) external_dirs vs copy + (b) SKILL.md format + (c) source-of-truth 3 sub-decision 묶음 잔존. CR1 권장의 분리안 (ADR-0032 = (a)+(b), ADR-0033 = (c)) 와 다르게 ADR-0033 이 **prefix lock 으로 reassign** 됨 — 즉 source-of-truth(c) 는 ADR-0032 본문에 묶여 있을 가능성. ADR-0032 본문 작성이 미수행 (Step 3 산출물). 잔존 risk: ADR-0032 의 sub-decision boundary 가 ADR-0030 의 4 sub-decision 패턴 정당화 수준에 도달하는지 ADR 작성 시점에 재검토 필요. closure는 부분적.

### CR1-MED-2 → **CLOSED**
v2 §8.1 M-2 lock — "95%+ pass, sample 30, p50/p95 latency 기록", §9.3 V3' PASS 기준 ≥ 28/30 (≥93%) 명시. CR1 권장의 "95% pass + p99 latency 한계 + sample 30" 와 정합 (다만 p99 → p95 로 약화 — 실측 의미상 동일 수준 — closure 인정).

### CR1-MED-3 → **CLOSED**
v2 §9.3 헤더 "VM 환경 행렬 — VM-A (Hermes 설치) → V1~V6, V8 / VM-B (Hermes 미설치) → V7" 명시. CR1 권장 정확히 채택. closure 적절.

### CR1-MED-4 → **CLOSED**
v2 §5.8 명시 — "schema version (v1) 유지 — additive change only. `version` 키 bump 불요 (§Decision E 의 example_version 검증 통과 — schema 의 key 추가/제거 없음, 값만 변경)". CR1 권장의 "별 이슈 없음 명시" 채택. closure 적절. (`oneshot_args` semantic 변경 자체는 contract migration 으로 CR1-HIGH-1 에서 별도 처리.)

### CR1-MED-5 → **CLOSED**
v2 §7.4 정정 — "sparse-checkout 영향 없음 — `_system` 의 자동 cover. 운영-time materialized `_system/skills/_generated/` 는 git untracked" + §9.2 DoD 에서 sparse-checkout 추가 항목 제거. CR1 권장 정확히 채택. closure 적절.

### CR1-MED-6 → **CLOSED**
v2 §7.2 치환 대상 파일 list 에 `README.md L:179` 명시 추가 + §9.2 DoD `README.md L:179 (F5 archive) + install snippet prerequisite` 항목 잔존. README.md L:179 의 실제 `wh:*` 표기는 F5 진행 상태 표기 부분 — `wh:*` → `wh-*` 표기 정합 필요한 사항. closure 적절. (단 README 실 라인 확인 결과 L:179 의 `wh:*` 가 v0.1.0 의 5 명령 namespace 안내 — 표기 변경 의도와 일치.)

---

## v2 도입 신규 결함

### CRIT-N1 — §5.6 헤더 중복 + v1 stale block 미제거
- **위치**: analysis_and_design.md L:497 `### 5.6 install.sh 변경 (v2 — CR1-CRIT-3 함수명 fix)` + L:510 `### 5.6 install.sh 변경`
- **결함**: v2 의 §5.6 (L:497~509) 가 새 표 (4행 — _step6_agent_skill, _step8_wh_setup_skill_meta, _migrate_agent_schema, SKIP_SYSTEMD_RENDER) 추가했으나, v1 의 §5.6 stale block (L:510~516, 3행 표 — Step 6, Step 8, 신규 import) 이 **미제거 상태로 잔존**. 즉 §5.6 헤더가 2번 등장, 두 표가 모순 (L:515 가 다시 `_step8_best_effort_wh_setup` + `wh:setup` 표기 — CR1-CRIT-3 가 fix 한 함수명이 되살아남). Step 3 implementer 가 어느 표를 정본으로 읽는지 ambiguous → CR1-CRIT-3 의 정확히 같은 silent drift 패턴 재발.
- **권장**: L:510~516 의 v1 stale block 삭제. §5.6 단일 헤더로 통합.

### CRIT-N2 — `_step8_5_systemd_enable_only` 함수가 install.sh 정본에 미존재
- **위치**: analysis_and_design.md §5.3.1 (L:287) "후속 step (_step8_systemd_render, _step8_5_systemd_enable_only) **skip flag** (`SKIP_SYSTEMD_RENDER=1`) 세팅", §5.6 (L:504), §9.3 V7 PASS 기준 (L:710)
- **결함**: install.sh 정본 (main HEAD `c328548`) 에 `_step8_5_systemd_enable_only` 함수 **부재** (grep 결과 0건). 실제 install.sh 의 systemd enable 경로는 `_systemd_start_after_update` (L:1139) — update 모드에서만 호출, fresh 에선 별도 enable 없이 `_step8_guide` 가 운영자 enable 안내. CR1-CRIT-3 의 함수명 drift 패턴 정확히 재발 — Step 3 implementer 가 skip 분기를 install.sh 의 어디에 삽입할지 정본 없음.
- **권장**: §5.3.1·§5.6·§9.3 의 `_step8_5_systemd_enable_only` 를 install.sh 정본 함수명 (`_systemd_start_after_update` 또는 신규 함수명 명시) 으로 교정 + fresh/update 분기 skip 정책 명시 (fresh 는 enable 자체가 운영자 책임이므로 SKIP 의미가 약함).

### HIGH-N1 — `_migrate_agent_schema()` 의 idempotent 보장 미명세
- **위치**: §5.4.3 (L:403-410)
- **결함**: "F5 의 1회성 schema lift" 라고 명시했으나 2번째 호출 (예: update_mode 의 install.sh 재실행) 시 동작 미명세. 이미 `wh-` + `{skill}` placeholder 로 migration 된 yaml 을 다시 처리하면 (a) interactive 모드는 patch 대상 없어 silent skip 인가? (b) backup 파일이 매번 새로 생성되어 누적되는가? §5.3.2 의 `~/.hermes/config.yaml.wikihub-bak.*` 는 7일 retention 명시, `wikihub.yaml.wikihub-bak.*` 는 retention 미명세. installed_scope_reduction (ADR-0031) 의 4필드 catalog 와의 책임 boundary 도 "별도" 라고 명시했지만, install.sh 매 호출 시 두 path 모두 yaml 을 mutate 가능 — 호출 순서 (ADR-0031 의 `/wh:setup` Step 0 vs `_migrate_agent_schema`) 명세 부재.
- **권장**: §5.4.3 에 idempotent guard 추가 — `agent.skill_prefix == "wh-"` AND `oneshot_args` 가 `{skill}` 포함 시 patch skip + backup 생성도 skip. 호출 순서: `_step6_agent_skill` 내에서 `_migrate_agent_schema()` 호출 (install.sh 시점) → `/wh:setup` Step 0 의 catalog drift fix 와 별도 trigger.

### HIGH-N2 — ADR-0011 superseded 후 cross-reference 갱신 의무 누락
- **위치**: §7.1 ADR-0011 행 + §9.2 DoD ADR 항목
- **결함**: §7.1 ADR-0011 Status 변경 + §9.2 DoD "ADR-0011 Status → Superseded by ADR-0033" 만 명시. 그러나 ADR-0011 의 cross-reference 갱신 의무 누락:
  - **ADR-0012 §스키마 정의 (L:39)**: `skill_prefix: "wh:"           # ADR-0011` — 주석이 ADR-0011 (superseded) 참조. ADR-0033 으로 갱신 또는 ADR-0011 후 ADR-0033 link 추가 의무.
  - **ADR-0012 §이유 (L:100)**: "agent-agnostic 원칙 정합 (ADR-0011 연장)" — 동일.
  - **ADR-0010 §매트릭스 (L:159-163)**: "ADR-0011 fallback 과 연동" + `wh:` 시도 → `wh-` 폴백 — v2 의 `wh-` 단일 default 로 fallback 시도 자체 불필요. 본 절 갱신 누락.
  - **wiki-schema.md L:340·L:347**: `skill_prefix: "wh:"           # ADR-0011` + "ADR-0011: `wh:` (default), `wh-` (fallback)". §7.2 의 "L:319-324 표기 갱신" 만 명시 — L:340·L:347 갱신 누락.
  - **docs/adr/README.md L:69**: ADR-0011 entry 의 Status `Accepted` → `Superseded by ADR-0033`.
- **권장**: §7.2 치환 대상에 위 5개 location 추가 + §9.2 DoD 의 "ADR-0011 Status 변경" 을 "ADR-0011 본문 (Status + Note) + 위 5개 cross-ref 갱신" 으로 확장.

### HIGH-N3 — `_step8_wh_setup_skill_meta` 의 bash `timeout 300` ↔ yaml.timeout_sec 동기화 명세 incomplete
- **위치**: §5.6 L:502 "bash `timeout 300` → `timeout {agent.timeout_sec}` (yaml-driven)"
- **결함**: 변경 의도는 명시했으나 실제 yaml 값 read 메커니즘 미명세. install.sh 의 기존 read 패턴은 `python3 -c "import yaml; ..."` (L:1208-1210) — `timeout_sec` 도 동일 방식인가? `agent.timeout_sec` 미설정 (운영자 yaml 의 schema migration 안 됐을 때) 시 default 600 fallback? CR2-LOW-5 는 "600 으로 sync" 만 명시, v2 는 "yaml-driven" 으로 격상 — 구현 ambiguity 가 HIGH 로 격상. 또한 `timeout` shell utility 가 인자로 fractional sec 받는지 (e.g. yaml 이 `600.5` 면) edge case.
- **권장**: §5.6 에 read 절차 + default + 검증 명시 — "python3 yaml read → integer 검증 → default 600 → bash `timeout ${timeout_sec}s`". 또는 `_migrate_agent_schema()` 의 책임에 `timeout_sec` 항목 추가 (현재는 skill_prefix + oneshot_args 2건만).

### MED-N1 — ADR-0023 §safety guard scope 확장의 본문 의무 명시 부재
- **위치**: §7.1 ADR-0023 행 "§safety guard 확장 Note" + §9.2 DoD ADR 항목 "ADR-0023 §safety guard Note 확장"
- **결함**: v2 가 ADR-0023 의 safety guard 3개 (L:44-47 — `$WIKIHUB_HOME` wipe scope 한정) 를 외부 자산 `~/.hermes/config.yaml` mutate 의 backup + flock + 동의 surface 로 확장한다고 명시. 그러나 ADR-0023 §safety guard 3개의 invariant (예: "wipe 는 wikihub 외부 mutate 안 함") 가 외부 자산 mutate 확장으로 어떻게 강화/완화되는지 정확한 ADR 본문 변경 의도 미명세. 단순히 "Note 추가" 만으로 외부 자산 mutate 책임이 ADR-0023 의 scope 에 들어오는 것이 architectural change 인지 supplementary note 인지 모호.
- **권장**: ADR-0023 본문 변경 의도를 §7.1 에 구체화 — "safety guard 3개 invariant 유지 + 신규 invariant 4 추가 (외부 자산 mutate 는 backup + flock + 동의 + log 기록)" 또는 "별도 ADR-0034 (외부 자산 mutate 정책) 분리" 둘 중 결정.

### MED-N2 — ADR-0033 의 본문 의무 + supersede 양방향 link 의무 명시 부재
- **위치**: §7.1 ADR-0033 행 + §9.2 DoD
- **결함**: ADR-0033 신설 명시되나, 본문에 반드시 포함되어야 할 항목 미명세:
  - `Supersedes: ADR-0011` 헤더 마커.
  - ADR-0011 본문에 `Superseded by: ADR-0033` 마커 갱신.
  - ADR-0011 의 Notes 섹션에 supersede 사유 ("Hermes docs 의 skill name colon 미문서화 — `wh-` 보수적 lock") 1줄 추가.
  - docs/adr/README.md 의 ADR 인덱스 갱신 (Status `Accepted` → `Superseded by ADR-0033`).
  - docs/adr/template.md 의 Considered Options 패턴 정합 (ADR-0033 의 옵션 = `wh:` lock vs `wh-` lock vs both-allowed).
- **권장**: §9.2 DoD 의 "ADR-0033 신규" 행을 위 5개 sub-item 으로 확장. CLAUDE.md §7 의 "결정 변경 시 기존 ADR Status 를 Superseded 로 바꾸고 신규 ADR 에 Supersedes 명시" 정합.

### MED-N3 — `SKIP_SYSTEMD_RENDER` flag 의 scope 명세 부재
- **위치**: §5.3.1 (L:287) + §5.6 (L:504)
- **결함**: flag 변수의 scope/persistence 미명세. (a) bash environment variable? install.sh process-local? sub-shell propagation? (b) 다른 step (특히 `_step10_verify` L:1095-) 이 flag 인식하는가? (c) install.sh 재호출 시 flag reset? (d) flag set 시 trap rollback (ADR-0030) 와의 정합 — render skip 됐는데 rollback trigger 시 PRE_UPDATE_REF 의 systemd unit 잔존 처리.
- **권장**: §5.3.1 에 flag scope 명시 — "install.sh process-local bash variable, sub-function 모두 read. `_step8_systemd_render` + `_step8_wh_setup_skill_meta` + `_systemd_start_after_update` + `_step10_verify` 모두 flag 인식 (early return)". rollback 시 동작도 1줄 명시.

### MED-N4 — `_system/skills/_generated/` 의 partial materialize 실패 정책 미명세
- **위치**: §5.1 (L:222-226) + §5.2 (L:273-275) + §5.3.6 (L:351-358)
- **결함**: install.sh 가 5건 SKILL.md materialize 중 3건째에서 실패 (예: ENOSPC, frontmatter yaml parse error) 시 처리 정책 미명세. (a) partial 상태 의 `_generated/` 잔존 → external_dirs 가 인식 가능한 일부 skill 만 노출 → silent partial functionality? (b) install.sh 종료 코드? (c) atomic write 가 file-level — 5건 batch 의 atomicity 부재. `.gitignore` 의 `_system/skills/_generated/` 등재는 OK 하나 update_mode 의 trap rollback 시 `_generated/` 잔존이 stale 상태로 남을 가능성.
- **권장**: §5.3.6 에 실패 정책 추가 — "5건 중 1건 실패 시 install.sh fail-fast + `_generated/` 전체 cleanup (`rm -rf`) → 운영자가 install.sh 재호출. partial state 잔존 안 함". 또는 staging dir (`_generated.tmp`) materialize 후 atomic rename (`os.rename _generated.tmp _generated`).

### LOW-N1 — V3' (dispatch 결정성) PASS 기준의 statistical confidence 미명세
- **위치**: §9.3 V3' (L:705)
- **결함**: "sample 30 중 ≥28건 (≥93%)". 30 sample 의 통계적 신뢰구간 (Wilson score 등) 미명세 — 28/30 의 95% CI 가 0.78~0.99 일 수 있어 "95%+ pass" 의 underlying probability 추정에 약함. CR1-MED-2 의 결정 (95%+) 와 실제 측정 기준 (≥93%) 의 numerical gap.
- **권장**: V3' PASS 를 "30 sample 중 ≥29건 (96.7%)" 또는 "100 sample 중 ≥95건 (95%)" 로 sample size 증대 또는 threshold 정합. ADR-0033 의 Note 항목에 본 결정 근거 1줄 추가.

### LOW-N2 — §5.2 의 `_generated/` 관계도와 §5.3.6 의 절차가 unicode arrow 표기 불일치
- **위치**: §5.2 L:262-269 관계도 + §5.3.6 L:353-358
- **결함**: §5.2 관계도가 ASCII art (`└→`) + §5.3.6 절차는 numbered list. 동일 정보 (frontmatter source + commands body → _generated/ artifact) 가 2 표기 — 가독성. v2 closure 영향 0, cosmetic only.
- **권장**: §5.2 관계도 유지 + §5.3.6 의 1~4 step 을 관계도 참조로 단축.

---

## v2 의 spec 일관성 검증

### §3 unchanged 진단 정합성
§3.1 (`_step6_agent_skill` stub L:701-706) — 실제 install.sh 와 일치. §3.2 (`_step8_best_effort_wh_setup`) — v1 표기 잔존이 §5.6 stale block (L:510~516) 과 함께 fix 의무. §3 본문은 §5.6 의 정본 함수명 (`_step8_wh_setup_skill_meta`) 으로 교정 완료 (L:99). 5.2.B 채택 후에도 §3 진단 유효 — `_system/skills/` 존재 X (`_generated/` 는 runtime 산출물이라 진단 시점 X).

### §6.1 ExecStart Before/After 정합
4건 (vault@.service, lint.service, lint.service --apply, `_step8_wh_setup_skill_meta`) 모두 `wh-` + slash + `chat --skills --quiet --query` 일관. `_step8_wh_setup_skill_meta` 행 (L:554) 은 `chat --skills wh-setup --quiet --query` — 5.6 표 (L:502) 의 `--quiet` 포함과 정합. closure OK.

### §7.1 ADR 영향 표 11개 정합
§5 결정 항목과 cross-reference 결과:
- ADR-0002·0006·0010·0011·0012·0023·0024·0030·0031 — §5 결정과 정합.
- ADR-0032 — 본문 미작성 (Step 3 산출물) — MED-1 PARTIAL.
- ADR-0033 — 본문 미작성 + supersede 양방향 link 의무 (MED-N2).

§7.1 자체는 closure 가 well-formed 하나, ADR 본문 작성 시점 (Step 3) 에 위 sub-item 들이 누락되지 않도록 DoD 강화 필요.

---

## 추가 관찰

- **R3 narrow scope 정합**: 본 R3 는 closure 검증 + v2 도입 신규 결함 surface 한정. R2-CR2 의 SRE 결함 closure 는 CR3-2 (별도 reviewer) 의 책임 — 본 R3 는 CR2 항목 (CR2-CRIT-1, CR2-CRIT-2, CR2-HIGH-1~8 등) 의 closure 평가 미수행. spec/ADR scope 만 cover.
- **CRIT 가 다시 등장한 패턴 주의**: CR1-CRIT-3 (함수명 drift) closure 후 v2 가 새로 도입한 CRIT-N1 (§5.6 헤더 중복) + CRIT-N2 (`_step8_5_systemd_enable_only` 함수명 drift) — 동일 root cause (정본 코드 grep 검증 부족). v3 작성 시 install.sh / docs/adr/*.md 의 함수명·ADR-ID grep 검증을 명시 step 으로 추가 권장.
- **Step 3 진입 가능성**: 본 R3 의 신규 CRIT 2건 fix 후 v3 lock 가능. v3 는 narrow patch (§5.6 중복 제거 + 함수명 교정 + DoD ADR sub-item 확장) 정도 — 200줄 미만 추가 변경 예상. v3 의 CR3 재검토 (closure-of-closure) 는 trivial scope 면 생략 가능.
- **Multi-model 정합**: CR1 (spec) 의 6 CRIT/HIGH/MED 의 closure 가 v2 에 적절히 반영. CR2 (SRE) 의 closure 는 CR3-2 의 domain. 두 R3 reviewer 의 결과 cross-check 후 final v3 lock 권장.
- **CLAUDE.md §2 Simplicity First 정합**: v2 의 5.2.B 채택은 architectural drift 최소화 (commands/ 정본 보존) — 정합. 단 ADR-0032 의 (a)+(b)+(c) 묶음 (MED-1 PARTIAL) 은 본 원칙 측면에서 (c) 분리 후 잔여 2 sub-decision 의 atomic boundary 재평가 권장.
