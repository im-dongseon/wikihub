# Design Review 2 — F5 hermes_adapter (CR2: SRE)

- **리뷰 대상**: analysis_and_design.md v1 (472줄)
- **리뷰어**: CR2 (운영 신뢰성 / SRE / 시스템 통합 / race / failure mode)
- **리뷰 일자**: 2026-05-18
- **종합 판단**: **Accept with revisions** — 핵심 옵션 (α) 의 방향성은 타당하나, 외부 자산(`~/.hermes/config.yaml`) 변경의 운영자 동의·atomicity·rollback 모델과 Hermes 미설치/실패 모드의 알림 경로가 정본화 부족. CRIT 2건·HIGH 8건의 surfacing 필요.

---

## CRIT — 진입 차단

### CR2-CRIT-1 — Hermes 미설치 시 systemd timer 가 silent dead 사슬 진입

- **위치**: §5.6 `_step6_agent_skill()` warn-only + §9.3 V7 PASS 기준
- **결함**: §5.6 은 "Hermes 미설치면 `_step6_agent_skill` 가 warn-only" 명시 + V7 의 PASS 기준이 "warn-only 진행 (fail-fast 아님)". 그러나 후속 step(_step8_systemd_render·_step8_5_systemd_enable_only)이 그대로 진행 → vault@.timer / lint.timer 가 enable·activate 됨. 매 timer fire 마다 `hermes: command not found` (exit 127) 가 발생. ADR-0024 의 `last_failure.json` producer 는 `VaultSyncFatal` 분기에서만 호출되는데 (vault-fetch.py 도달 전 ExecStart 자체 fail), `last_failure.json` 미생성 + ops-alert.py 의 fallback diagnostic (journalctl mount tail) 도 mount scope 한정 → **fatal 알림 0건 도달**, journal 만 누적. 알림 사슬 전체 dead.
- **권장 해결책**: 다음 중 하나로 정본화 후 §5.6·§9.3 갱신:
  - (a) Hermes 미설치 시 `_step8_systemd_render` 도 skip + `_step8_5_systemd_enable_only` 도 skip — install.sh 종료 코드는 success 유지하되 운영자가 hermes 설치 후 재실행 path 안내. README 의 install snippet 에 hermes 사전 설치 prerequisite 추가.
  - (b) Hermes 미설치 시 install.sh 자체 fail-fast (curl-pipe 운영자 첫 경험 측면에서 권장). `WIKIHUB_NONINTERACTIVE=1` 도 동일.
  - (c) systemd 는 enable 하되 `_state/<vault_id>/last_failure.json` 의 producer 책임을 ExecStartPre 의 hermes-existence 검증 wrapper 로 확장 — vault-fetch.py 호출 전에 hermes binary 부재를 fatal 로 기록. 단 ADR-0024 §writer-책임 갱신 필요.
- 권장: (a) — surgical + ADR-0024 영향 0. v1 의 V7 PASS 기준을 "warn + systemd render/enable skip + 운영자 안내 stderr 출력" 으로 갱신.

### CR2-CRIT-2 — `~/.hermes/config.yaml` 동시 쓰기 race + rollback 부재

- **위치**: §5.3 atomic append (ruamel.yaml round-trip + os.replace)
- **결함**: `~/.hermes/config.yaml` 은 **wikihub 외부 운영자 자산**. 운영자가 동시에 `hermes chat` / `hermes skills install <other>` 실행 중이면 (Hermes 도 동일 파일 쓸 수 있음) ruamel.yaml read → modify → `os.replace` 사이에 외부 write 가 끼면 last-writer-wins 로 외부 변경 손실. install.sh 의 atomic write 는 **wikihub repo 내부** 의 yaml (wikihub.yaml) 정합 패턴이지, 외부 도구가 공유하는 파일에는 부적합. 더 큰 문제: install.sh 가 fail 한 경우 (예: external_dirs 추가 직후 다음 step 에서 abort), config.yaml 의 변경은 **rolled back 되지 않음** — ADR-0030 update_mode 의 trap rollback 은 wikihub repo HEAD 기반이라 `~/.hermes/config.yaml` 까지 미커버.
- **권장 해결책**:
  - (a) `flock(2)` 또는 `~/.hermes/config.yaml.lock` advisory lock — install.sh 가 lock 획득 후 read-modify-write. Hermes 자체가 동일 lock 을 쓰지 않으면 protection 부분적이지만, wikihub 의 install.sh 의 중복 호출 (update_mode rollback 시 재실행) 만큼은 안전.
  - (b) install.sh 에 `_step6_agent_skill` 진입 전 PRE_HERMES_CONFIG_HASH 캡처 + `trap` 에 hermes config rollback handler 추가 (install.sh 전체 fail 시 sha256 비교 후 backup 복원). ADR-0030 sub-3 의 rollback 책임 확장.
  - (c) Backup 보존 — write 전 `cp ~/.hermes/config.yaml ~/.hermes/config.yaml.wikihub-bak.<ts>` (7일 retention). 운영자가 수동 rollback 가능. install.sh 가 stderr 로 backup path 출력.
- 최소 권장: (a) + (c) 조합. (b) 는 trap 복잡도 증가라 v0.2.x deferred 도 가능.

---

## HIGH — Step 2 v2 에서 반영 권장

### CR2-HIGH-1 — external_dirs append 의 merge 의미론 미정의

- **위치**: §5.3 step 2~3 "기존 config 의 `skills.external_dirs` 에 `$WIKIHUB_HOME/_system/skills` 가 포함됐는지 확인. 미포함 시 atomic append"
- **결함**: "포함됐는지 확인" 의 비교 방법이 미명세. (1) 정규화된 절대경로 비교? `~/wikihub/_system/skills` 와 `/home/user/wikihub/_system/skills` 는 동일? (2) 운영자가 다른 도구 (codex/aider/Cline) 의 skill dir 을 이미 등록했다면, wikihub 가 list 의 어느 위치에 insert? prepend (wikihub priority) vs append? (3) 운영자가 손으로 wikihub path 를 제거했다가 install.sh 재실행하면 wikihub 가 다시 추가 — 운영자 의도 무효화 (idempotent 가 아님 — destructive idempotent).
- **권장 해결책**: §5.3 에 정본 명시:
  - 비교: `os.path.realpath()` 정규화 후 string 비교.
  - 위치: append (운영자 선등록 dir 의 priority 보존).
  - 운영자 제거 의도 보호: 첫 등록 시 wikihub path 옆에 marker comment (`# managed by wikihub install.sh — remove to disable auto-discovery`). 재실행 시 marker 존재 path 만 갱신, marker 없는 wikihub path 가 외부에 있으면 append 하지 않고 stderr 경고.
- ADR-0032 (placeholder) 의 핵심 결정 항목으로 승격.

### CR2-HIGH-2 — `--accept-hermes-config-patch` flag 의 기존 동의 모델과 불일치

- **위치**: §M-8 + §5.3 step 4
- **결함**: install.sh 의 기존 동의 모델은 `WIKIHUB_NONINTERACTIVE=1` 단일 toggle + `SKIP_CONFIRM` (L:47, 281). M-8 의 `--accept-hermes-config-patch` 가 추가되면 동의 surface 가 N+1 flag 로 분기 → curl-pipe 시 운영자가 flag 추가를 누락하면 `WIKIHUB_NONINTERACTIVE=1` 인데도 hermes config 패치는 silent skip 또는 fail. 일관성 깨짐.
- **권장 해결책**: 둘 중 하나로 통일:
  - (a) `WIKIHUB_NONINTERACTIVE=1` 단일 toggle 이 hermes config 동의도 포함 (단, install.log 에 명시 record). README 의 NONINTERACTIVE 설명에 "외부 자산 변경 동의 포함" 명시.
  - (b) per-resource 동의 flag 모델 채택 — `WIKIHUB_CONSENT_HERMES_CONFIG=1` env 또는 `--accept-hermes-config-patch`. 단, 동시에 다른 외부 자산 (예: ~/.config/systemd/user/ 도 외부) 의 동의도 명시. 현재는 systemd user dir 은 묵시적 동의 — 일관성 위해 그것도 명시 추가.
- 권장: (a) — surface 단순. 다만 stderr 안내 + install.log 에 patch 적용 명시 record 필수.

### CR2-HIGH-3 — `--query` transcript 의 log volume 폭증 + retention 미검증

- **위치**: §M-3 + §6.1 ExecStart 형식
- **결함**: F4 의 logging 가정은 `hermes -z` 의 "single prompt in, final response text out" (§2.1) — final answer only. `hermes chat --query` 는 transcript (tool output 포함, §2.1). systemd journal 의 vault@gdrive.service 1회 fire 당 log volume 이 10~100배 증가 가능. R16-L2 의 install.log retention (7일/10MB) 은 install.sh 의 stdout/stderr 한정이라 영향 없으나, **systemd journal 의 vault-fetch-* SyslogIdentifier** retention 은 OS 기본값 (journald.conf 의 SystemMaxUse) 의존 — wikihub 가 명시 강제 없음. v0.1.0 에서 매일 sync_interval_sec=3600 (시간당 1회) × 5 skill × verbose transcript 면 journal 이 며칠 안에 SystemMaxUse 도달.
- **권장 해결책**:
  - (a) Hermes 의 `--quiet` / `-Q` / `--no-tool-output` flag 존재 확인 (M-3 의 VM 실측 항목 명시 추가). 존재하면 yaml.agent.oneshot_args 에 default 포함.
  - (b) 부재하면 wikihub 가 ExecStart 를 wrapper 로 감싸 stdout 의 tool-output 줄을 grep-filter (transcript 의 final answer 만 journal 에 잔존). 단 (γ) wrapper 옵션 의 부분 도입 — v0.1.0 범위 영향.
  - (c) 운영자 안내 — `systemd-journald.conf` 의 vault 관련 SyslogIdentifier 에 `SystemMaxUse` per-identifier 설정. README 의 troubleshooting 섹션 추가.
- 최소 요건: M-3 의 VM 실측 항목에 (a) 검증 명시 + V3 의 PASS 기준에 "log volume 1회 fire 당 X KB 이하" 정량 기준 추가.

### CR2-HIGH-4 — Restart= 미설정 + LLM API transient fail 의 retry 모델 미정의

- **위치**: §5.5 ExecStart inline + (참조) `wikihub-vault@.service.template` L:36-39
- **결함**: 현 systemd template L:36 명시: "Restart= 미설정 (oneshot 의 재시작은 timer 책임). exit 75 (Retryable) 는 SuccessExitStatus 로 success 분류 → 다음 timer fire 가 자연 재시도." 이 모델은 vault-fetch.py 가 75 를 명시 emit 할 때 성립. **F5 후**: ExecStart 가 `hermes chat --query` → vault-fetch.py 미경유 → exit code 는 Hermes 가 직접 emit. LLM API rate limit (429), 503, timeout 같은 transient fail 의 Hermes exit code 가 75 로 매핑되리란 보장 X — Hermes 가 1 또는 다른 코드 emit 시 systemd 가 failure 로 분류 → OnFailure=ops-alert.service 발화. transient 가 매번 fatal alert.
- **권장 해결책**:
  - (a) Hermes 의 exit code contract 실측 추가 — M-3 옆에 M-9 (Hermes exit code mapping) 신설. transient (network/LLM 503) 와 permanent (skill not found, prompt malformed) 의 코드 차이 확인.
  - (b) 결과에 따라 wikihub.yaml.agent 에 `retryable_exit_codes: [75, 124, ...]` 추가. systemd template 의 `SuccessExitStatus=0 75` 를 yaml-driven render 로 변경 (render_systemd_units.py).
  - (c) 더 robust 한 해법: vault-fetch.py 가 Hermes 의 subprocess parent 로 유지 (wrapper 옵션 γ 부분 도입) — exit code 의미론 통제 + last_failure.json producer 책임 보존.
- v1 의 ADR-0006 정합 옵션 (α) 채택은 (c) 의 vault-fetch.py 우회를 의미 — 이게 ADR-0024 의 fatal 알림 contract 와 직접 충돌. **재검토 필요**.

### CR2-HIGH-5 — TimeoutStartSec=15min 의 LLM transcript 시간 영향 미평가

- **위치**: §B.11 (review prompt) + template L:21
- **결함**: 기존 `hermes -z` 의 LLM 응답 시간 baseline 으로 15min grace 가 설정됨. `chat --query` 는 transcript (tool call multi-turn 가능) — ingest skill 이 vault 의 큰 파일 100건 처리 시 LLM 이 tool call 반복 → 15min 초과 가능. SIGTERM → exit 143 → systemd failure → ops-alert + transient.
- **권장 해결책**: M-3 의 VM 실측 항목에 "large vault (예: 100 files) 의 ingest 1회 wallclock 측정" 추가. 결과 기반 yaml.agent.timeout_sec (이미 §5.4 에서 600 default) 의 default 조정 + systemd TimeoutStartSec 의 render-time substitution 도입 (현재는 template 하드코딩). render_systemd_units.py 에 `timeout_start_sec` placeholder 추가 + yaml.agent.timeout_sec 와 sync.

### CR2-HIGH-6 — placeholder substitution 실패의 fail-fast 보장 미명시

- **위치**: §5.5 `_per_unit_invocation` + substitution dict
- **결함**: §5.5 의 Python 코드 `[str(a).format(skill=skill_name) for a in oneshot_args]` — yaml.agent.oneshot_args 에 `{skill}` placeholder 가 누락된 경우 (운영자가 손으로 yaml 편집 후 placeholder 빠뜨림) `.format(skill=...)` 는 placeholder 없으면 그대로 passthrough → "chat --skills --query" 의 `--skills` 다음 인자 부재로 systemd ExecStart 가 invalid → service 시작 시점에 systemd 가 fail (203/EXEC 또는 invalid argument). install.sh 의 _step8_systemd_render 단계에서 detect 안 됨.
- **권장 해결책**: render_systemd_units.py 에 명시적 검증:
  ```python
  if "{skill}" not in " ".join(oneshot_args):
      raise SystemExit("agent.oneshot_args missing '{skill}' placeholder")
  ```
  + render 직후 (`_step8_systemd_render` 종료 시) `systemd-analyze verify` 호출로 unit 문법 검증. 둘 다 fail-fast.

### CR2-HIGH-7 — update_mode rollback 시 신/구 yaml schema 정합 invariant 깰 가능

- **위치**: §7.3 update_mode 정합 + ADR-0030 §sub-3
- **결함**: ADR-0030 sub-3 rollback 시 `git reset --hard $PRE_UPDATE_REF` + `_step8_systemd_render` 재호출. PRE_UPDATE_REF 가 F5 이전 ref 면 wikihub.yaml.example 의 `oneshot_args: ["-z"]` schema 시점. 단 wikihub.yaml (운영자 정본) 은 `_systemd_render` 가 읽는 파일이고 `instance.root` 외부라 rollback 영향 없음 — 운영자 yaml 은 F5 후 schema (`{skill}` placeholder) 유지 + render 코드는 F5 이전 (substitution dict 에 `agent_invocation_for_<skill>` 없음) → KeyError 또는 unresolved placeholder. systemd unit 이 broken 상태로 render 됨.
- **권장 해결책**:
  - (a) §7.3 에 명시 — "운영자 yaml 의 schema migration 은 install.sh _step3_yaml 의 책임. rollback 시 yaml 자체도 PRE_UPDATE_REF 의 schema 로 다운그레이드해야 정합" + ADR-0030 §부정/제약 에 cross-feature 영향 surface.
  - (b) render_systemd_units.py 에 yaml schema version 검증 (ADR-0031 의 example_version 검증과 동일 패턴) — F5 placeholder 부재 시 명시 fail + "현 install.sh 가 신 schema 요구 — yaml 마이그레이션 필요" stderr.
  - (c) update_mode 의 rollback handler 가 `wikihub.yaml` 의 schema version 도 rollback 책임 — 단 운영자 직접 편집 항목 (instance.root, vaults[*].source 등) 보존 필수. 복잡도 높음 — 권장은 (a)+(b).

### CR2-HIGH-8 — sparse-checkout fetch list 갱신의 cross-feature 검증 누락

- **위치**: §7.4 + §9.2 DoD `install.sh _step2_clone()` sparse-checkout 에 `/_system/skills/` 추가
- **결함**: 현 install.sh L:290 `WIKIHUB_SPARSE_PATHS=(_system scripts install.sh wikihub.yaml.example README.md LICENSE)` — `_system` 이 이미 포함됐으니 `_system/skills/` 도 함께 fetch (sparse-checkout 이 dir 단위면 모두 포함). 단 `--no-cone` 모드 (L:296) 의 패턴 매칭이 hierarchical 인지 정확히 확인 필요. 더 큰 문제: §9.2 DoD 가 sparse-checkout list 에 `/_system/skills/` 명시 추가를 요구 — 현 array 가 `_system` directory 전체를 fetch 한다면 redundant. 만약 redundant 가 아니면 (sparse 가 sub-dir 자동 확장 안 되면) install_scope_reduction 의 F4 archive 시점부터 `_system/skills/` 가 미존재였으므로 영향 X, 그러나 본 feature 가 신설 → fetch 대상 명시 추가가 실제로 필요한지 검증 누락.
- **권장 해결책**: §7.4 갱신 — sparse-checkout `--no-cone` 의 매칭 의미 명시 + WIKIHUB_SPARSE_PATHS 의 현재 array 가 `_system/skills/` 를 cover 하는지 결정. cover 한다면 §9.2 DoD 의 sparse-checkout list 추가 항목 삭제 (redundant). cover 안 한다면 명시 추가. V1 의 PASS 기준에 "git clone 후 `_system/skills/wh-ingest/SKILL.md` 가 존재" 추가.

---

## MED — backlog 처리 가능

### CR2-MED-1 — Hermes binary version 검증 미존재

- **위치**: §5.3 step 1 "Hermes 존재 검사"
- **결함**: 존재만 확인하고 version 검증 없음. Hermes 1.x 의 `chat --skills` 가 다른 syntax 일 가능성 (M-2 와 별개의 syntax 변경). gws_min_version (ADR-0015) 와 동일 패턴의 hermes_min_version 부재.
- **권장 해결책**: ADR-0032 에 `agent.hermes_min_version` 키 도입 검토 — 단 hermes versioning 의 stability 가 v0.1.0 시점 미검증이라 v0.2.x deferred 가능. 본 v1 에서는 §5.3 에 "version 검증은 v0.2.x — 현재는 `hermes skills list` 의 exit code 가 0 인지로 binary 기능 확인" 명시만.

### CR2-MED-2 — `hermes skills audit` 자동 호출의 부작용 미평가

- **위치**: §M-5 + V5 PASS 기준 "재시작 없이 또는 `hermes skills audit` 1회"
- **결함**: V5 PASS 기준이 미결 M-5 의 결과 의존 → V5 자체가 비결정 (review prompt §G.22 지적). `hermes skills audit` 의 부작용 (예: 다른 skill 의 cache 무효화, audit log 의 비대화) 검증 없음. install.sh 가 매번 audit 호출하면 운영자의 외부 skill workflow 에 영향 가능.
- **권장 해결책**: V5 PASS 기준 분리 — V5a (재시작 없이 인식) + V5b (audit 1회 후 인식). 둘 다 측정 후 결과 기반으로 install.sh 의 audit 호출 정책 결정. ADR-0032 의 sub-decision 항목으로 승격.

### CR2-MED-3 — skill disable 상태의 detect/re-enable 미명세

- **위치**: §B.8 (review prompt) — §5.3 검증 단계 (`hermes skills list | grep ^wh-`)
- **결함**: `grep ^wh-` 가 disabled skill 도 매치 (Hermes 의 list 출력에 disabled 가 prefix 로 표시되는지 미확인). 운영자가 `hermes skills config disable wh-ingest` 후 install.sh 재실행 시 wikihub 가 disable 상태를 모르고 OK 처리 → vault@.service fire 시 skill not dispatched → silent fail (LLM 이 자연어 응답).
- **권장 해결책**: §5.3 step 5 신설 — `hermes skills inspect wh-<cmd> --json` 으로 state=enabled 검증. disabled detect 시 (a) 운영자 의도 존중 + 경고만 (b) install.sh 가 enable 강제 (운영자 의도 무효) 중 정본 정책 결정. 권장 (a) — 운영자 control 우선.

### CR2-MED-4 — silent dispatch fail 의 detect 메커니즘 부재

- **위치**: §9.3 V3 PASS 기준 "skill dispatch 진입 + `_state/<vault>/log.md` 갱신"
- **결함**: Hermes 가 skill dispatch 안 하고 자연어로 적당히 응답한 경우 — exit 0 + stdout 에 response text 있음 → systemd success → log.md 갱신 안 됨 → V3 fail 로 detect 가능하나, **운영 시점** 의 detect 메커니즘 없음. log.md 미갱신이 매 timer 마다 silent — 운영자가 며칠 후 wiki 가 stale 한 걸 직접 발견.
- **권장 해결책**: vault-fetch.py 의 last_failure.json 갱신 패턴을 확장 — `_state/<vault_id>/last_ingest.json` 추가 (timer fire 마다 갱신 시각 + source_mtime). ops-alert.py 가 `now - last_ingest.timestamp > 2 × sync_interval_sec` 면 staleness fatal alert. ADR-0024 의 fallback diagnostic 확장. v0.2.x deferred 가능하나 v1 의 §10 Out-of-Scope 에 명시 등재.

### CR2-MED-5 — ~/.hermes 권한 정책 surface 부재

- **위치**: §B.4 (review prompt) + §5.3
- **결함**: §5.3 이 `~/.hermes/config.yaml` 변경을 명시하나 권한 (chmod 0600) 정책 surface 없음. wikihub 의 .credentials/ (L:675 chmod 700, L:687-688 chmod 600 enforce) 와 정합성 미평가. Hermes config 에 LLM API key 같은 secret 이 있다면 (Hermes 의 config schema 미확인) 권한 위반이 보안 결함.
- **권장 해결책**: §5.3 에 "Hermes config 권한 정책은 운영자/Hermes 책임" 명시 + install.sh 가 변경 후 권한이 기존 mode 보다 약해지지 않음을 보장 (`os.replace` 가 source file 의 mode 를 보존하는지 확인). 약해질 가능성 있으면 변경 후 `os.chmod(path, original_mode)` 명시 복원.

### CR2-MED-6 — agent.binary 가 alias/wrapper 인 경우 처리

- **위치**: §B.19 (review prompt) + §5.4 yaml schema
- **결함**: 운영자가 `hermes` 를 docker wrapper 또는 shell alias 로 운영하는 경우 — `which hermes` 가 wrapper path 반환. systemd 의 PATH (template L:15 `Environment=PATH=...`) 에 wrapper 가 없으면 ExecStart fail. agent.binary 가 절대경로 (`/usr/local/bin/hermes`) 권고는 §5.4 example 에 있으나 alias 케이스 명시 없음.
- **권장 해결책**: §5.3 의 Hermes 존재 검사에 "binary 가 alias/function 인지 detect → absolute path 권고 stderr". README install 의 prerequisite 에 "hermes 는 절대경로 binary 로 설치 권장 (alias/wrapper 미지원)" 명시.

### CR2-MED-7 — per-skill enable/disable 정책 부재

- **위치**: §B.20 (review prompt) + §5.5 + §9.2 DoD
- **결함**: 5 skill 전체를 일괄 활성화 가정. 운영자가 query/graphify 미사용이면 — vault@.timer 와 lint.timer 만 enable, query/graphify 는 timer 없음 (현재 systemd template 에 query/graphify timer 없음). 그러나 §9.2 DoD 가 "5건 등록" 강제 → 미사용 skill 도 등록됨. external_dirs 에 path 추가만 하면 5건 자동 노출이라 의도된 동작, 단 wikihub 가 운영자의 partial 사용 케이스를 모름.
- **권장 해결책**: v1 에서 surface 만 — §10 Out-of-Scope 에 "per-skill enable/disable 정책 (v0.2.x — Hermes 의 skills config disable 과의 정합)" 명시. v0.1.0 은 5 skill 일괄 등록 + 운영자가 Hermes 측에서 disable 가능 (CR2-MED-3 의 detect 정책과 연계).

### CR2-MED-8 — stale skill 의 자동 정리 미정의

- **위치**: §E.17 (review prompt) + §5.3
- **결함**: v0.1.0 → v0.2.x 업데이트 시 skill name 변경 (예: `wh-ingest` → `wh-knowledge-ingest`) 또는 skill 제거 시 — external_dirs 가 dir 단위 참조라 Hermes 는 dir 내용 기반 인식 → stale skill 잔존은 _system/skills/ 의 git pull 결과에 따라 자동 정리 가능 (구버전 skill 디렉토리가 git pull 로 삭제되면 Hermes 도 자동 unregister). 단 운영자가 `external_dirs` 외 `~/.hermes/skills/` 로 copy 한 경우 (§5.3 의 대안, 기각됐지만) stale 가능. 또 Hermes 의 internal cache 가 잔존하는지 미확인.
- **권장 해결책**: §5.3 에 "skill 정리는 git pull + external_dirs 자동 반영 가정. Hermes internal cache 의 stale 가능성은 M-5 의 audit 정책과 연계 — v0.2.x feature 에서 lifecycle 정본화" 명시.

---

## LOW — 참고

### CR2-LOW-1 — VM 테스트 자동화의 Hermes 설치 의존

- **위치**: §9.3 + §G.21 (review prompt)
- **결함**: multipass Ubuntu 22.04 에 Hermes 설치 자동화가 본 feature 의 prerequisite. install 자동화 스크립트 부재 시 Step 3 자가 검증이 manual 단계 — 재현성 약함.
- **권장**: Step 3 진입 전 `scripts/test/install_hermes_on_vm.sh` helper 1건 추가 (out-of-scope 면 features/backlog.md 에 등재). 본 feature 의 Step 3 산출물에 surface.

### CR2-LOW-2 — V7 (Hermes 미설치 detect) 검증 메커니즘 명시 부족

- **위치**: §9.3 V7
- **결함**: PATH 조작 (`PATH=/tmp install.sh`) 또는 임시 hermes 제거 (`mv /usr/local/bin/hermes /tmp/`) 중 어느 방법인지 명시 없음.
- **권장**: V7 의 검증 절차 명시 — "PATH 에서 hermes 제거 후 install.sh 실행 → _step6_agent_skill 의 warn 발생 + (CR2-CRIT-1 권장 해결 적용 후) systemd render/enable skip 확인".

### CR2-LOW-3 — install.log 에 hermes config 변경 명시 record 누락

- **위치**: §5.3
- **결함**: install.log (R16-L2) 에 install.sh stdout/stderr mirror. `_step6_agent_skill` 의 hermes config 변경이 명시 record 안 되면 사후 trace 시 wikihub 가 외부 자산을 변경한 시각을 운영자가 모름.
- **권장**: §5.3 step 3 (atomic append) 직후 `info "hermes config patched: $HERMES_CONFIG_PATH (backup: $BACKUP_PATH)"` 출력. install.log 에 자동 mirror.

### CR2-LOW-4 — README install snippet 의 prerequisite surface 부족

- **위치**: §9.2 DoD "README install snippet 의 F5 후속 안내 → archive 표기로 갱신"
- **결함**: F5 archive 표기 갱신만 명시. CR2-CRIT-1·HIGH-2·MED-6 의 prerequisite (hermes 사전 설치 + NONINTERACTIVE 의 외부 자산 동의 포함 + alias 미지원) 가 README install snippet 에 surface 안 됨.
- **권장**: §9.2 DoD 갱신 — "README 의 install snippet prerequisite 섹션 신설 (hermes 사전 설치 + 절대경로 권고 + ~/.hermes/config.yaml 변경 동의)".

### CR2-LOW-5 — `_step8_best_effort_wh_setup` 의 timeout 300s 와 agent.timeout_sec=600 불일치

- **위치**: install.sh L:1214 `timeout 300` + §5.4 yaml `timeout_sec: 600`
- **결함**: best-effort wh-setup 호출의 bash `timeout 300` 와 yaml.agent.timeout_sec=600 불일치. F5 가 best-effort 호출을 `chat --skills wh-setup --query "/wh-setup"` 로 바꾸면 transcript 로 인해 300s 초과 가능 (CR2-HIGH-5 와 동일 원인).
- **권장**: §5.6 의 `_step8_best_effort_wh_setup` 변경 항목에 "bash `timeout` 인자를 yaml.agent.timeout_sec 와 sync (예: 600)" 추가.

---

## 추가 관찰

### 관찰-1 — ADR-0024 의 v0.2.x notify_via_hermes stub 가 F5 와 연결

ADR-0024 (`notify.py` 의 `notify_via_hermes()` stub) 가 "v0.2.x 의 F5 (hermes_adapter) 가 stub 본문을 Telegram 통지로 채움" 명시. 본 feature v1 은 stub 채우기 책임 surface 안 됨. plan.md §작업분류 + §예상 영향 범위 에도 없음. ADR-0024 의 v0.2.x 약속이 stale 인지 (즉 F5 가 invocation 정합 한정이고 notify 는 별도 v0.2.x feature) 확인 필요. 권장: §10 Out-of-Scope 에 "Hermes 채널의 fatal notify (Telegram 통지) — 별도 v0.2.x feature, ADR-0024 의 stub 채움" 명시 등재로 cross-feature 의도 명확화.

### 관찰-2 — option (α) 의 ADR-0006 정합성 주장 vs 실 운영 결과 차이

§4.1 의 "장점" 항목에 ADR-0006 정합 명시. 그러나 ADR-0006 (agent = orchestrator) 의 운영 시 의미는 "agent 가 procedure 의 LLM 해석 + tool call". CR2-HIGH-4 가 surface 한 exit code contract 의 vault-fetch.py 우회는 ADR-0024 의 last_failure.json producer 책임 dead 의미. 즉 ADR-0006 정합을 얻으면서 ADR-0024 정합을 잃음. 옵션 (γ) wrapper 의 v0.1.0 부분 도입 (vault-fetch.py 가 hermes subprocess parent 로 유지 + skill 의 procedure 본문은 (α) 그대로) 의 hybrid 가 두 ADR 모두 정합 가능. v2 에서 (α) vs (γ) 재평가 권장.

### 관찰-3 — `_system/commands/` stub 처리 (옵션 5.7.A) 와 wiki/ cross-link 정합

§5.7.A 가 stub Note + skill 참조 만 남김. §M-7 이 cross-link 영향 surface 하나 검증 절차 명시 없음. wiki/index.md + `_system/wiki-schema.md` L:319-324 외에 `wiki/` 사용자 콘텐츠 (운영자가 추가한 페이지) 의 `/wh:<cmd>` 또는 `_system/commands/<cmd>.md` 참조는 grep 만으로 surface 안 됨 (운영자 vault 외부). v1 에 "wiki 운영자 콘텐츠의 stale link 는 운영자 책임 — release notes 에 cross-link migration 안내" 명시 권장.

### 관찰-4 — V4 (멱등성) 의 source_mtime drift 기준이 LLM 비결정성 흡수 못함

§9.3 V4 "동일 결과 — log 의 source_mtime drift 없음". source_mtime 은 vault 파일의 mtime 으로 결정적. 그러나 ingest 의 LLM 해석 (entity extraction, link suggestion) 은 비결정적 — V4 의 "동일 결과" 가 source_mtime 동일성만 의미하는지 LLM 출력 stability 도 포함하는지 모호. plan.md §핵심운영invariant ("playbook 내부의 LLM tool use 비결정성은 본 feature 범위 밖") 와 정합되게 V4 PASS 기준을 "source_mtime drift 없음 + log.md 항목 추가 없음 (mtime 변화 없으면 ingest skip)" 으로 명시화 권장.

---

## CR2 종합

옵션 (α) 의 방향성은 ADR-0006 + Hermes 표준 path 측면에서 합리적. 그러나 SRE 측면의 3개 축에서 정본화 부족:

1. **외부 자산 변경의 동의·atomicity·rollback 모델** (CRIT-2, HIGH-1·2, MED-5, LOW-3) — `~/.hermes/config.yaml` 은 wikihub 가 처음 다루는 외부 운영자 자산. wikihub.yaml 의 내부 atomic write 패턴을 그대로 가져오면 부족.
2. **Hermes 외부 의존성의 failure mode 와 알림 사슬 정합** (CRIT-1, HIGH-3·4·5, MED-1·2·3·4) — ADR-0024 의 last_failure.json producer 가 vault-fetch.py 의존인데 (α) 가 vault-fetch.py 를 우회. v0.1.0 acceptance 의 알림 사슬이 dead 될 가능성. (γ) 부분 도입 재평가 필요.
3. **cross-feature invariant** (HIGH-6·7·8, MED-7·8, 관찰-1) — update_mode rollback + install_scope_reduction sparse-checkout + ADR-0024 의 v0.2.x notify stub 와의 정합이 v1 에서 isolated check.

Step 2 v2 에서 CRIT 2건 + HIGH 8건 surface 후 재검토. v2 의 변화가 ADR 영향 (특히 ADR-0024 갱신 또는 ADR-0032 의 sub-decision 확장) 을 surface 하면 ADR 추출도 비례 증가 예상.
