# Design Review 4 — F5 hermes_adapter (CR3-2: SRE closure)

- **리뷰 대상**: analysis_and_design.md v2 (R2 closure 검증, 761줄)
- **리뷰어**: CR3-2 (운영 신뢰성 / SRE closure / 외부 자산 mutate + failure-mode + cross-feature)
- **선행 리뷰**: CR2 design_review_2.md (CRIT 2 / HIGH 8 / MED 8 / 관찰 4)
- **리뷰 일자**: 2026-05-18
- **종합 판단**:
  - **Closure 평가**: CR2 CRIT 2 = CLOSED 2 / 0 / 0. HIGH 8 = CLOSED 6 / PARTIAL 2 / NOT_CLOSED 0. MED 8 = CLOSED 3 / DEFERRED-ACK 5 / NOT_CLOSED 0. 관찰 4 = CLOSED 4 / 0 / 0.
  - **신규 결함 (v2 도입)**: CRIT 0 / HIGH 2 / MED 4 / LOW 3.
  - **최종 판단**: **Step 3 진입 가능 (조건부)** — v3 revision 불필요. 신규 HIGH 2건은 Step 3 구현 시 산출물 (install.sh / render_systemd_units.py / ADR-0024·0030 갱신) 에 반영 가능. v2 의 §9.2 DoD 보강 2건과 §7.1 ADR-0024 / ADR-0030 의 Note 본문 의무 명시화만 추가하면 lock 가능.

---

## R2-CR2 closure 검증

### CR2-CRIT-1 (Hermes 미설치 silent dead 사슬) → **CLOSED**

권장 (a) 채택 — v2 §5.3.1 의 `SKIP_SYSTEMD_RENDER=1` flag + `_step8_systemd_render` / `_step8_5_systemd_enable_only` 둘 다 skip + install.sh exit 0 + §9.3 V7 의 5개 sub-criteria (warn / flag / 2 step skip / `systemctl list-unit-files | grep wikihub` empty / exit 0). vault@.timer / lint.timer 자체가 미생성 → 매 fire 의 exit 127 발생 경로 자체 차단. ADR-0024 의 last_failure.json producer 책임 보존 (uninstalled state 는 alerting matter 가 아니라 install-time 안내 matter — §7.1 의 ADR-0024 Note 가 명시). (a) 채택 적절 — (b) fail-fast 보다 surgical, (c) ExecStartPre wrapper 보다 ADR-0024 supersede 회피. **잔존 risk 1건**: 운영자가 `SKIP_SYSTEMD_RENDER=1` 이후 hermes 설치만 하고 install.sh 재호출 안 한 케이스의 운영자 안내가 stderr 1회뿐 — README install snippet 의 prerequisite 와 §9.2 DoD CR2-LOW-4 항목으로 cover (별도 결함 아님).

### CR2-CRIT-2 (`~/.hermes/config.yaml` race + rollback) → **CLOSED**

권장 (a)+(c) 조합 채택 — v2 §5.3.2 의 6 step 절차 (flock LOCK_EX|NB → PRE_HASH → backup → ruamel + os.replace → POST_HASH 변경 시 install.log record → flock release) + 5초 retry × 12회 (60s) + retention 7일 (5.3.2 step 3). (b) trap rollback handler 는 v0.2.x deferred — surgical 결정. **잔존 risk 1건**: flock 이 advisory 라 Hermes daemon 이 동일 lock 안 쓰면 wikihub-internal protection 한정 (CR2 권장의 (a) 명시 한계 그대로). 본 한계는 v2 §5.3.2 의 절차 자체에는 surface 안 됨 — 신규 결함 §B-MED-2 로 surface (아래).

### CR2-HIGH-1 (external_dirs merge 의미론) → **CLOSED**

v2 §5.3.3 의 Python 의사코드 + realpath + append + marker comment (CommentedSeq) + idempotent 3-branch 분기 ((1) realpath 매치 = no-op, (2) marker 부재 + wikihub path 부재 = first install / append+marker, (3) marker 부재 + wikihub path 존재 = operator 재등록 케이스 / 보존). CR2 권장의 3개 요건 (realpath / append / marker) 모두 cover. **잔존 risk 0건** — 단 marker comment 가 ruamel.yaml round-trip 의 CommentedSeq 에 의존이라 ruamel 의 comment preservation 특성을 Step 3 VM 실측에서 확인 필요 (M-1 의 frontmatter schema 검증과 별개의 round-trip 검증 항목) — 신규 결함 §B-MED-1 로 surface.

### CR2-HIGH-2 (`--accept-hermes-config-patch` 통합) → **CLOSED**

v2 §5.3.4 의 (a) 채택 — `WIKIHUB_NONINTERACTIVE=1` 단일 toggle 이 외부 자산 동의 포함, `--accept-hermes-config-patch` flag 신설 회피. install.log 명시 record + README NONINTERACTIVE 설명 갱신 약속 (§9.2 DoD CR2-LOW-4 의 README prerequisite 와 정합). surface 단순 + 기존 동의 모델 일관성 보존. **잔존 risk 0건**.

### CR2-HIGH-3 (transcript log volume) → **CLOSED**

v2 §5.4.4 의 `--quiet` flag oneshot_args default 포함 + V3 PASS 기준 "stdout 크기 < 10 KB" 정량 lock. 단 M-3 이 `--quiet` 효과 정확도를 Step 3 VM 실측 의존 유지 — v2 가 부분 lock 명시 (CR2 권장 (a) 의 default 포함 부분만 v0.1.0 채택, (b) wrapper grep-filter 와 (c) journald.conf 안내는 미채택). (a) 만으로 충분한지는 V3 결과 의존 — 결과가 미달이면 `(c)` 의 SystemMaxUse 안내 README 추가가 Step 3 backport. **잔존 risk 1건**: V3 sample 단일 fire 의 10 KB 가 매시간 5 skill × 일 24h × 30 days 누적 시 ~36 MB / month — journald.conf SystemMaxUse default (10% of /var) 와 정합 분석이 v2 에 없음. journal volume 의 30일 누적 관점 mitigation surface 안 됨 — 신규 결함 §B-MED-3 으로 surface.

### CR2-HIGH-4 (Restart= + exit code contract) → **PARTIAL**

v2 §8.2 M-9 신규 (Step 3 VM 의존) + §9.3 V8 의 측정 항목. 그러나 v0.1.0 acceptance 진입 시점에 M-9 가 미해결로 leave — 본 항목이 acceptable 한가의 정책 surface 가 v2 에 명시 없음. ADR-0024 의 fatal 알림 contract 측면에서: Hermes 가 transient (429/503/timeout) 를 systemd failure 로 emit 하면 매 timer fire 마다 OnFailure=ops-alert.service → fatal alert spam. V8 의 PASS 기준이 "exit code 측정" 으로 정량 측정만 — 측정 후 어떤 default policy 로 v0.1.0 release 할지 decision criterion 부재 (예: yaml.agent.retryable_exit_codes default = `[]` vs `[75]` vs `[1]`). CR2 권장의 (b) yaml-driven retryable_exit_codes 는 schema 확장이라 v2 §5.4 의 schema 갱신에 포함 안 됨 (additive only 정합이지만 default 결정 의무가 §9.2 DoD 에 없음). **ADR-0024 정합 측면**: §7.1 의 ADR-0024 Note 본문은 "Hermes 미설치 시 unit 미생성" 만 — Hermes 가 설치된 상태의 transient fail 의 alert spam 정책은 ADR-0024 본문 갱신 의무 없음. 본 정합은 "v0.1.0 은 Hermes 의 exit code 가 transient 든 permanent 든 모두 fatal alert 1회 발화 + ops-alert.py 의 dedup 6h 가 spam 방지" 라는 implicit assumption. v2 에 본 assumption surface 가 없어 PARTIAL — 신규 결함 §B-HIGH-1 로 surface.

### CR2-HIGH-5 (TimeoutStartSec=15min) → **PARTIAL**

v2 §5.4.4 `--quiet` mitigation 으로 transcript-induced timeout 위험 부분 cover. v2 에 별도 처리 명시 없음 (review prompt 의 "§M-9 의 exit code 외 별도 처리 없는데 충분?" 질문에 직접 해당). CR2 권장의 "render-time substitution + yaml.agent.timeout_sec 와 sync" 가 v2 §5.4.2 yaml 의 `timeout_sec: 600` 만 — systemd template L:21 TimeoutStartSec=15min 의 render-time 갱신은 미명시. 즉 yaml 의 timeout_sec=600 은 best-effort wh-setup 호출 (`_step8_wh_setup_skill_meta`) 의 bash `timeout` 인자로 사용되나, systemd unit 의 TimeoutStartSec 와는 미동기. 운영자가 yaml.agent.timeout_sec 를 600 → 1200 으로 늘려도 systemd TimeoutStartSec 는 15min 하드코딩 — 사용자 의도 무효화. **PARTIAL**: V3 의 large vault 시나리오 측정 결과 1회 fire 가 15min 초과 가능성 (특히 100 files 첫 ingest) 이 ADR-0006 의 LLM 비결정성 + transcript multi-turn 시 가능 — 신규 결함 §B-HIGH-2 로 surface.

### CR2-HIGH-6 (placeholder fail-fast) → **CLOSED**

v2 §5.5.1 의 명시적 raise SystemExit + has_placeholder 검증 + §5.5.4 의 `systemd-analyze --user verify` post-render 호출. CR2 권장의 fail-fast 2단계 (Python detect + systemd verify) 둘 다 채택. **잔존 risk 1건**: verify 자체가 실패 시 install.sh 의 처리 정책 v2 에 명시 없음 — review prompt §B-4 ("verify 자체가 fail 일 때 install.sh 가 어떻게? unit 파일은 이미 atomic write 됨 → revert? 운영자 안내?") 미커버. 신규 결함 §B-MED-4 로 surface.

### CR2-HIGH-7 (update_mode rollback yaml schema) → **CLOSED**

v2 §5.5.5 의 schema version 검증 (placeholder 부재 시 명시 fail-fast + 안내 메시지) + §7.3 의 ADR-0030 §부정/제약 Note 추가 약속 + backup (`wikihub.yaml.wikihub-bak.<ts>`) 복원 source 명시. CR2 권장의 (a)+(b) 채택, (c) update_mode rollback handler 가 yaml schema rollback 책임은 v0.2.x deferred (재검토 트리거 항목으로 ADR-0030 추가 약속). **잔존 risk 1건**: 자동 rollback 부재로 운영자 수동 복원 절차 의존 — ADR-0030 의 자동 trap rollback 과 비대칭. 본 비대칭은 v2 §7.3 가 surface 하나, §9.2 DoD 에 README troubleshooting 섹션 추가 의무 없음 — 신규 결함 §B-LOW-1 로 surface.

### CR2-HIGH-8 (sparse-checkout cross-feature 검증) → **CLOSED**

v2 §7.4 의 정정 — v1 의 잘못된 "추가 필요" 분석을 "이미 cover (`_system` 전체 fetch)" 로 교체 + 신규 frontmatter source 5건 + `_generated/` git untracked 명시. install.sh:290 `WIKIHUB_SPARSE_PATHS` array 의 `_system` 가 directory 전체 fetch 라 sub-dir 자동 cover. **잔존 risk 0건** — `--no-cone` 모드의 매칭 의미는 sparse-checkout dir-prefix 매칭이라 검증 정확 (`_system` 으로 시작하는 모든 path).

---

### MED closure 정도 (v2 §8.3 v0.2.x 이양 list cover 검증)

| CR2-MED-N | v2 처리 상태 | 평가 |
|---|---|---|
| CR2-MED-1 (binary version 검증) | §8.3 의 5번째 항목 (hermes_min_version 도입은 versioning stability 확보 후 v0.2.x) | **DEFERRED-ACK** — surface 적절 |
| CR2-MED-2 (audit 자동 호출 부작용) | §9.3 V5a/V5b 분리 + §5.3.5 의 audit 1회 호출 정책 (M-5 의존) | **CLOSED** — sub-decision 분리 채택 |
| CR2-MED-3 (skill disable detect) | §8.3 의 3번째 항목 (per-skill enable/disable 정책 v0.2.x) | **DEFERRED-ACK** — Hermes side disable detect 는 v0.2.x |
| CR2-MED-4 (silent dispatch fail detect) | §8.3 의 4번째 항목 (staleness alert v0.2.x — last_ingest.json + ops-alert 확장) | **DEFERRED-ACK** — adequate surface |
| CR2-MED-5 (~/.hermes 권한 정책) | v2 §5.3.2 의 backup 절차는 `cp` 만 — chmod 정책 명시 없음 | **NOT_CLOSED** — 신규 결함 §B-MED-1' (아래 §B-LOW-2 로 강등) |
| CR2-MED-6 (alias 처리) | v2 §5.4.2 의 yaml example 의 `/usr/local/bin/hermes` 절대경로 명시 + §9.2 DoD CR2-LOW-4 의 README prerequisite (절대경로 권고) | **CLOSED** — README 안내로 surface |
| CR2-MED-7 (per-skill enable) | §8.3 의 3번째 항목 (per-skill enable/disable 정책 v0.2.x) | **DEFERRED-ACK** |
| CR2-MED-8 (stale skill 자동 정리) | v2 의 §5.3.3 marker comment + `_generated/` git untracked 패턴이 자동 정리 — git pull 시 frontmatter source 제거되면 다음 install.sh 의 materialization 에서 `_generated/wh-old/` 제거 안 함 (idempotent 가 새 list 추가만, 삭제 미수행) | **PARTIAL** — 신규 결함 §B-MED-5 로 surface |

종합: MED-5 는 chmod 미명시 (낮은 위험, v2 §5.3.2 의 `os.replace` 가 source mode 보존하는지 검증 항목 추가만 필요 — LOW 강등). MED-8 의 stale `_generated/` 처리는 install.sh 의 5건 materialization 절차에 "기존 `_generated/wh-*` 중 frontmatter source 없는 항목 cleanup" step 미명시 — Step 3 구현 시 보강. 나머지 MED 6건은 v2 §8.3 의 v0.2.x 이양 list 가 cover 또는 surface 처리.

---

### 관찰 closure

#### 관찰-1 (ADR-0024 notify stub) → **CLOSED**

v2 §10 Out-of-Scope 의 명시 — "ADR-0024 의 `notify_via_hermes()` stub 채움 (Telegram 통지) — v0.2.x 별도 feature". §8.3 의 v0.2.x 이양 list 와 cross-link 정합. CR2 권장의 surface 완전 채택. **잔존 risk 0건**.

#### 관찰-2 ((α)/(γ) 재평가) → **CLOSED**

v2 §4.5 의 (α) 유지 채택 + 4개 근거 lock — (1) vault-fetch.py 가 이미 agent subprocess (`vault-fetch.py` 헤더 인용), (2) (γ) 가 ADR-0006 orchestration role architectural reassign 으로 v0.1.0 범위 폭발, (3) CR2-CRIT-1 의 알림 dead 사슬은 install.sh prerequisite gate 로 차단 → vault-fetch.py pivot 불요, (4) (γ) 부분 도입은 v0.2.x `hermes_wrapper` 로 push + trigger 조건 명시 (exit code 미보장 또는 다른 agent 매핑). **vault-fetch.py 가 이미 agent subprocess 라는 논거 검증**: ADR-0006 §Decision 의 unified orchestration 은 "agent = orchestrator + scripts = procedure subprocess" — F5 의 `hermes chat --skills wh-ingest --query "/wh-ingest --vault X"` 호출 시 Hermes 가 SKILL.md 의 procedure 를 LLM 으로 read + tool call (예: vault-fetch.py) — 즉 vault-fetch.py 는 Hermes 의 subprocess. ADR-0006 정합 OK. **단 CR2-HIGH-4 와의 정합**: vault-fetch.py 가 Hermes subprocess 면 exit code emit 책임은 Hermes 가 wrap — CR2-HIGH-4 의 PARTIAL 잔존. v2 §4.5 의 (α) 유지 결정 자체는 architectural 측면에서 정합하나, exit code contract 의 risk 가 v0.1.0 acceptance 의 "operational acceptable" 임을 §9.2 DoD 가 명시화 필요 — §B-HIGH-1 와 연계.

#### 관찰-3 (wiki/ cross-link) → **CLOSED**

v2 의 5.2.B 채택 (commands/ 정본 유지) 으로 wiki/ 콘텐츠의 `/wh:<cmd>` 또는 `_system/commands/<cmd>.md` 참조 영향 = path 변경 0 + slash prefix `wh:` → `wh-` 만. v2 §7.2 의 치환 대상 list 가 `_system/wiki-schema.md` + `_system/commands/*.md` + README + AGENTS + docs/adr/ 명시. wiki/ 운영자 콘텐츠는 운영자 vault 영역으로 wikihub repo 외부 — CR2 권장의 release notes 안내가 §10 Out-of-Scope 에는 없으나 5.2.B 채택으로 cross-link 자체가 path-level 영향 0 라 release notes 의무가 약화. **잔존 risk 0건**.

#### 관찰-4 (V4 멱등성 LLM 비결정성) → **CLOSED**

v2 §9.3 V4 의 PASS 기준 "source_mtime drift 0 + log.md 항목 추가 0 (ingest skip)" 명시화. CR2 권장의 LLM 비결정성 흡수 — ingest skip 시점의 deterministic invariant (mtime + log row count) 만 검증. plan.md §핵심운영invariant ("playbook 내부의 LLM tool use 비결정성은 본 feature 범위 밖") 정합. **잔존 risk 0건**.

---

## v2 도입 신규 결함

### HIGH-1 (B-HIGH-1) — v0.1.0 release 시점의 Hermes exit code default policy 미결정

- **위치**: v2 §8.2 M-9 + §9.3 V8 + §7.1 ADR-0024 Note + §9.2 DoD
- **결함**: V8 의 PASS 기준 = "exit code 측정" 만 — 측정 후 v0.1.0 default policy 가 (a) yaml.agent.retryable_exit_codes 신설 (b) systemd template 의 `SuccessExitStatus` 갱신 (c) ADR-0024 dedup window 단축 (d) 측정값 무시 + default 유지 중 어느 것인지 v2 의 decision criterion 부재. M-9 의 v0.1.0 release-time resolution path 없음 — V8 PASS 가 무엇이든 release 가능. CR2-HIGH-4 의 transient alert spam risk 정책 surface 안 됨.
- **권장**: §9.2 DoD 에 "V8 측정 결과 기반 v0.1.0 release-time decision matrix" 추가 — 예: "transient (429/503) 이 0/1/75 중 어느 것이든 1회는 fatal alert 발화 (ops-alert.py dedup 6h 가 spam 방지) + retryable_exit_codes 도입은 v0.2.x". 본 lock 이 v2 의 (α) 유지 정합 보장. ADR-0024 §7.1 Note 본문에 "Hermes transient fail 의 alert dedup 의존성" 명시 추가.

### HIGH-2 (B-HIGH-2) — systemd TimeoutStartSec 와 yaml.agent.timeout_sec sync 부재

- **위치**: v2 §5.4.2 yaml schema + §5.4.4 `--quiet` mitigation + 기존 template L:21 TimeoutStartSec=15min
- **결함**: yaml.agent.timeout_sec=600 은 best-effort wh-setup 호출의 bash `timeout` 인자만 사용 (§5.6 의 "bash `timeout 300` → `timeout {agent.timeout_sec}` (yaml-driven)"). systemd unit 의 TimeoutStartSec 와는 미동기 — render_systemd_units.py 에 timeout_start_sec placeholder 없음. CR2-HIGH-5 의 "render-time substitution 도입" 권장이 v2 에 채택 안 됨. large vault (100+ files) 첫 ingest 의 transcript multi-turn 시 15min 초과 → SIGTERM exit 143 → systemd failure → ops-alert spam. `--quiet` mitigation 은 stdout 크기만 cover, wallclock 미커버.
- **권장**: §5.5.2 의 substitution dict 에 `timeout_start_sec = agent.timeout_sec` 추가 + systemd template L:21 의 `TimeoutStartSec=15min` 를 `TimeoutStartSec={timeout_start_sec}s` placeholder 화. yaml.agent.timeout_sec 의 default 를 900 (15min, 기존 호환) 으로 lock. V3 large vault 측정 결과 미달 시 운영자가 yaml 만 조정해도 systemd 자동 동기.

### MED-1 (B-MED-1) — ruamel.yaml CommentedSeq 의 marker comment 복원성 미검증

- **위치**: v2 §5.3.3 의 marker comment ("managed by wikihub install.sh — remove to disable auto-discovery")
- **결함**: ruamel.yaml round-trip 의 comment preservation 은 CommentedSeq 의 item-level comment 가 yaml load → modify → dump 후에도 보존된다는 가정. 그러나 Hermes 가 동일 config.yaml 을 자체 modify 시 ruamel.yaml 안 쓰면 comment 손실 → 다음 install.sh 호출 시 marker 부재로 분기 판단 잘못 (3-branch 의 (3) 보존 분기로 잘못 진입 vs (2) re-append). M-1 의 frontmatter schema 검증과 별개로 본 round-trip 검증 항목 V1 PASS 기준에 없음.
- **권장**: V1 PASS 기준에 "marker comment 가 ruamel.yaml round-trip 후 wikihub path 의 item-level 에 정확히 보존" 검증 항목 추가. 보존 안 되면 marker 를 별도 key (`_wikihub_managed_paths: [<path>]`) 로 분리 검토 — schema 추가는 별 리스크 (Hermes 가 unknown key 무시 가정).

### MED-2 (B-MED-2) — flock advisory 의 wikihub-internal 한정 surface 미명시

- **위치**: v2 §5.3.2 flock 절차 (CR2-CRIT-2 closure)
- **결함**: `~/.hermes/config.yaml.lock` advisory lock 은 Hermes daemon 이 동일 lock 안 쓰면 (Hermes 가 자체 file locking 사용 시 호환 안 됨) wikihub-internal protection 한정. CR2 권장의 (a) 가 본 한계 명시 권고했으나 v2 §5.3.2 절차 본문에 surface 없음 — 운영자 mental model 에 "install.sh 동시 호출 (운영자 실수로 2개 터미널) 만 cover" 명시 부족.
- **권장**: §5.3.2 step 1 의 flock 절차에 명시적 Note — "본 lock 은 wikihub install.sh 의 동시 호출 방지 한정. Hermes daemon 의 동시 write 와의 race 는 backup + PRE/POST hash 비교의 사후 detect 의존". install.log 의 변경 record 가 사후 trace 도구임을 surface.

### MED-3 (B-MED-3) — journal volume 누적 30일 mitigation 미surface

- **위치**: v2 §5.4.4 transcript volume mitigation + V3 PASS 1회 fire < 10 KB
- **결함**: 1 fire 당 10 KB × 5 skill × 24h × 30 days ≈ 36 MB / month. journald.conf SystemMaxUse default (10% of /var, 보통 수 GB) 와 정합 OK 측면, BUT large vault (100+ files) 의 첫 ingest 시 transcript 가 10 KB 초과 가능 + 운영자가 sync_interval_sec 단축 시 누적 폭증. CR2-HIGH-3 권장의 (c) "journald.conf SystemMaxUse per-identifier 안내 README" 가 v2 에 미채택.
- **권장**: README troubleshooting 섹션에 "wikihub journal volume — sync_interval_sec × vault 수 × 5 skill × transcript 평균 크기 계산식 + SystemMaxUse 조정 안내" 추가 (§9.2 DoD CR2-LOW-4 의 README prerequisite 와 합산). 또는 §10 Out-of-Scope 에 "journal log rotation 정책 v0.2.x" 명시.

### MED-4 (B-MED-4) — systemd-analyze verify 실패 시 install.sh 처리 정책 미명시

- **위치**: v2 §5.5.4 systemd-analyze verify (CR2-HIGH-6 closure 의 2단계 fail-fast 중 두 번째)
- **결함**: verify 실패 시 install.sh 가 어떻게? unit 파일은 이미 atomic write 완료된 상태 (`/etc/systemd/system/...` 또는 `~/.config/systemd/user/...`) → revert? install.sh fail-fast exit 1? 운영자 안내? v2 §5.5.4 본문에 명시 없음. update_mode 의 trap rollback 흐름과 정합도 미surface.
- **권장**: §5.5.4 에 다음 절차 명시:
  1. verify 실패 시 install.sh 가 `_step8_systemd_render` 직전 backup (있으면) 복원 또는 unit 파일 제거.
  2. install.sh exit 1 + 운영자에게 yaml schema 점검 안내 (placeholder 누락 등 detect 메시지 포함).
  3. update_mode 의 `_rollback_if_failed` trap 와 정합 — verify 실패가 trap trigger 인 ERR 발화 → 자동 rollback path 정합.

### MED-5 (B-MED-5) — stale `_generated/wh-*` 자동 정리 미명시

- **위치**: v2 §5.3.6 Materialization 절차 + §5.7 "5건 materialization" 가정
- **결함**: install.sh 가 매 호출 시 idempotent 재생성하나 — frontmatter source 5건이 4건으로 줄거나 (v0.2.x 에서 skill 통합) name 변경 시 (예: `wh-ingest` → `wh-knowledge-ingest`) `_generated/wh-old/` 가 stale 잔존. external_dirs 가 dir 단위 참조라 Hermes 가 stale skill 인식 — `hermes skills list` 에 잔존. CR2-MED-8 의 partial closure.
- **권장**: §5.3.6 materialization step 4 신설 — "frontmatter source 가 정의한 5건 외 `_generated/wh-*/` 디렉토리 제거 (cleanup step)". V1 PASS 기준에 "이전 install 의 stale wh-old/ 가 다음 install.sh 호출 후 제거됨" 추가.

### LOW-1 (B-LOW-1) — rollback 자동/수동 비대칭 운영 안내 README 미명시

- **위치**: v2 §5.5.5 rollback compat + §7.3 update_mode 정합
- **결함**: F5 의 yaml schema migration 의 rollback 은 수동 (`wikihub.yaml.wikihub-bak.<ts>` 운영자 복원). update_mode 의 자동 trap rollback (ADR-0030 sub-3) 와 비대칭. §9.2 DoD 에 README troubleshooting 추가 의무 없음. 운영자가 update_mode rollback 후 systemd unit 이 broken 상태로 render 됨을 처음 경험 시 mental model 부족.
- **권장**: §9.2 DoD 에 "README troubleshooting 섹션 — update_mode rollback 후 systemd render 실패 시 `wikihub.yaml.wikihub-bak.<ts>` 복원 절차 안내" 추가.

### LOW-2 (B-LOW-2) — ~/.hermes/config.yaml 권한 정책 surface 부족

- **위치**: v2 §5.3.2 backup 절차 (`cp`)
- **결함**: `cp` 가 mode 보존하나 `os.replace` 가 source file mode 보존 보장 미검증 (Python 3 docs 상 replace 는 dest 파일 metadata 일부 보존 + dest 가 새 파일이면 source mode 채택, 그러나 atomic write tmp 파일 mode 가 umask 의존). CR2-MED-5 의 partial closure. Hermes config 에 LLM API key 같은 secret 가 있다면 (Hermes config schema v0.1.0 시점 미검증) 권한 약화 risk.
- **권장**: §5.3.2 step 4 의 ruamel + `os.replace` 직후 명시적 `os.chmod(path, original_mode)` 호출 — `pre_mode = os.stat(path).st_mode` 캡처 후 복원. V1 PASS 기준에 "PRE/POST mode 동일" 추가.

### LOW-3 (B-LOW-3) — SKIP_SYSTEMD_RENDER env 의 subshell scope 미명시

- **위치**: v2 §5.3.1 + §5.6 의 신규 flag
- **결함**: `SKIP_SYSTEMD_RENDER=1` 가 bash env var 인지 install.sh 의 shell-local var 인지 v2 본문 미명시. install.sh 가 단일 process 내 모든 step 실행 (subshell 사용 안 함) 가정이면 shell-local 충분. 그러나 `_step8_systemd_render` 가 subshell 또는 별도 함수에서 호출 시 var inherit 정합 필요. install.sh 의 기존 패턴 (예: `INSTALL_MODE`, `WIKIHUB_NONINTERACTIVE`) 정합 검증 미surface.
- **권장**: §5.3.1 에 명시 — "flag 는 install.sh 의 shell-local var (기존 `INSTALL_MODE` 와 동일 패턴, subshell 미사용 가정). subshell 에서 access 필요 시 `export` 추가". Step 3 구현 시 install.sh 코드 site 확인.

---

## 추가 관찰

### 관찰-1 (CR3-2) — V10 (flock contention) 재현성 시나리오 구체화 필요

v2 §9.3 V10 PASS 기준: "install.sh 2개 instance 동시 실행 — 1개는 5.3.2 의 5초 retry × 12 안에 lock 획득, 다른 1개는 wait 후 idempotent skip". 그러나 시뮬레이션 방법 명시 부족 (review prompt §B-9). 재현 절차:
1. 별도 shell 1: `flock -n /home/u/.hermes/config.yaml.lock sleep 60 &`
2. 별도 shell 2: install.sh 실행 → 5.3.2 flock NB acquire 시도 → busy → 5초 retry
3. 60s 후 shell 1 lock release → shell 2 12회 retry 중 어느 시점에 acquire
4. shell 2 의 idempotent (5.3.3 의 (1) realpath 매치 = no-op) 분기 진입 확인

V10 본문에 위 4-step 절차 명시 권장 — 재현성 보장.

### 관찰-2 (CR3-2) — §9.3 V<N> 10건의 SRE 결정 cover matrix

| v2 SRE 결정 | cover V<N> | 평가 |
|---|---|---|
| §5.3.1 SKIP_SYSTEMD_RENDER | V7 | OK |
| §5.3.2 flock + backup + hash | V1 (backup 생성) + V10 (flock contention) | OK |
| §5.3.3 realpath + marker | V1 (marker comment 등록) | PARTIAL — round-trip 보존 검증 (B-MED-1) |
| §5.3.4 NONINTERACTIVE 통일 | (직접 V<N> 없음 — install.log record 검증만) | PARTIAL — V1 PASS 에 install.log 명시 record 검증 추가 권장 |
| §5.3.5 hermes skills list 검증 | V2 | OK |
| §5.3.6 materialization | V1 (5건 SKILL.md 생성) | PARTIAL — stale cleanup (B-MED-5) |
| §5.4.3 _migrate_agent_schema | (직접 V<N> 없음 — V9 rollback 의 backup source 만) | PARTIAL — V6 update path 에서 schema migration trigger 검증 추가 권장 |
| §5.4.4 --quiet flag | V3 (stdout < 10 KB) | OK |
| §5.5.4 systemd-analyze verify | (직접 V<N> 없음 — fail-fast 만) | PARTIAL — verify 실패 시 처리 (B-MED-4) |
| §5.5.5 rollback compat | V9 | OK |

결론: 6/10 OK + 4/10 PARTIAL. PARTIAL 4건이 §B-MED-1/4/5 + V1·V6 PASS 기준 보강으로 해결 가능 (Step 3 구현 시 backport).

### 관찰-3 (CR3-2) — §7.1 ADR Note 본문 의무 §9.2 DoD 정합

v2 §9.2 DoD 의 ADR list:
- ADR-0024 Note (Hermes 미설치 시 unit 미생성) — 본문 명시 OK
- ADR-0030 §부정/제약 Note (yaml schema migration rollback) — 본문 명시 OK
- ADR-0031 §Decision Note (agent.* catalog 미포함 + F5 별도 migration) — 본문 명시 OK

ADR-0024 본문 검증 (위 grep 결과 line 88, 105): "v0.2.x 의 F5 (hermes_adapter) 가 stub 본문을 Telegram 통지로 채움" + "F5 (hermes_adapter) 진입 시 `notify_via_hermes` stub 활성화 — 본 ADR supersede 가 아닌 stub 본문 갱신". v2 §10 Out-of-Scope 의 "ADR-0024 의 notify stub 채움 v0.2.x" 정합 — ADR-0024 본문 변경 의무는 **추가 1건** 필요: ADR-0024 의 "F5 진입 시 stub 활성화" 가정을 "F5 는 invocation 정합 한정, notify stub 채움은 별도 v0.2.x feature" 로 갱신. 본 변경이 v2 §9.2 DoD 의 ADR-0024 Note 본문 1줄 추가로 cover — Step 3 구현 시 명시.

### 관찰-4 (CR3-2) — `_migrate_agent_schema` operator override 처리 미surface

§5.4.3 의 `_migrate_agent_schema()` 가 1회성 schema lift. 그러나 운영자가 schema patch 후 yaml 을 다시 `wh:` 로 손편집하면 — install.sh 가 다음 호출에 재patch (interactive 면 confirm 받지만 NONINTERACTIVE 모드 자동 patch). operator intent override 위반. §5.3.3 의 marker comment 패턴 (3-branch 분기) 이 본 migration 에 미적용. **권장**: §5.4.3 step 4 신설 — yaml 의 `agent.skill_prefix` 옆에 marker comment ("migrated by wikihub F5 — remove to retain operator override") 또는 별도 wikihub-meta 키 (`_wikihub_agent_schema_version: f5`) 도입. 다음 호출 시 marker 있으면 재patch, 부재면 운영자 의도 보존. 본 결함은 LOW 강등 (운영자의 일반 케이스가 schema 손편집 안 함 가정 — 단 surface 권장).

---

## CR3-2 종합

v2 가 R2-CR2 의 CRIT 2 + 핵심 HIGH 6 + MED 3 + 관찰 4 를 surgical 하게 일괄 closure. CR2-HIGH-4 (exit code contract) 와 CR2-HIGH-5 (TimeoutStartSec) 는 PARTIAL — Step 3 VM 실측 의존이라 v0.1.0 acceptance 진입 시점에 미해결 leave 자체는 acceptable 하나, release-time decision criterion + render-time substitution 의 v2 §9.2 DoD 보강 2건이 필요. v2 의 surgical 결정 (vault-fetch.py pivot 회피, (γ) wrapper push, marker comment 패턴) 은 CLAUDE.md §2 Simplicity First 정합. 신규 결함 HIGH 2건 + MED 4건은 Step 3 구현 시 install.sh + render_systemd_units.py + ADR Note 본문 + README 보강으로 backport 가능 — v3 design revision 불필요.

**lock 권장**: v2 의 §9.2 DoD 에 다음 4 항목 추가 후 Step 3 진입.

1. (B-HIGH-1) V8 측정 결과 기반 v0.1.0 release-time decision matrix 명시 (yaml schema 확장 회피 + ops-alert dedup 의존).
2. (B-HIGH-2) `render_systemd_units.py` substitution dict 에 `timeout_start_sec` 추가 + template L:21 의 placeholder 화.
3. (B-MED-4) §5.5.4 의 systemd-analyze verify 실패 처리 절차 (revert + exit 1 + update_mode trap 정합).
4. (B-MED-5) §5.3.6 의 stale `_generated/wh-*` cleanup step 명시.

나머지 MED/LOW 6건은 Step 3 구현 시 surgical 보완 가능 — v3 revision 불필요.
