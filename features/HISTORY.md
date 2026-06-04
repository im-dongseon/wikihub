# Feature 배포 이력

<!-- append-only — 최신 항목이 파일 끝에 위치 -->

---

## [2026-05-19] oauth_unify_rclone_only

- **목적**: v0.1.0 진입 직전 OCI 검증에서 surface 한 두 결함 closed — (1) Personal Drive 에서 SA write 불가 (`403 storageQuotaExceeded`, ADR-0029 §Decision 가정 깨짐), (2) rclone(OAuth) ↔ gws(SA) 인증 주체 비대칭으로 changes feed 단절 (w2a 업로드 미감지).
- **로직**: 두 도구 → 한 도구로 단순화 + 인증 자료 단일화. `rclone lsjson <remote>: --recursive` (Drive API files.list backend 호출) 이 반환하는 `ID`·`MimeType`·`ModTime` 필드 + `file_map` (primary key = source_id/Drive fileId) diff 로 gws `drive changes list` 등가 대체. cursor 모델 폐기 (full snapshot diff), SA JSON 폐기 (rclone.conf 단일 인증). `mount_diff.compute_diff` 가 4-way 분류 (created/modified/renamed/deleted) + false-deleted 가드 (listing 0건 또는 delete_ratio > threshold 시 Retryable abort) 책임.
- **생성 ADR**: ADR-0035 (Supersedes ADR-0014, ADR-0015, ADR-0017, ADR-0027, ADR-0029)
- **트레이드오프**:
  - lsjson cost — 매 사이클 full snapshot. v0.1.0 vault 규모 (N~수천) 에선 무영향. 큰 vault (N >> 10k) 에서 재검토 필요.
  - rclone single dependency — supply chain 위협 집중 (ADR-0025 §부정/제약 R16-H2 의 in-toto / RCLONE_PINNED_SHA256 우선순위 상향 검토 트리거).
  - Google native (`.gdoc`/`.gsheet`/`.gslides`) export 의 mtime 안정성 미실증 — vault 에 미존재. native 파일 도입 시 검증 필요 (재검토 트리거).
  - 운영자 수동 state migration 1회 (`rm cursor.json file_map.json`) — 자동화 미제공 (v0.1.0 미배포 시점 가정).
- **결론**: ADR cascade 5건 → 1건 단순화. 코드 ~30% 감소 (gws/errors 모듈 폐기, sync.py 재작성). pytest 56 pass / 1 skip. 설계·코드 멀티 리뷰 (refine) 반영 완료. v0.1.0 의 Drive 접근 architectural 정본 lock.
- **참조**: features/archive/20260519_oauth_unify_rclone_only/

---

## [2026-05-19] wh_skills_env_cleanup

- **목적**: `_system/skills/wh-*.frontmatter.yaml` 5개의 `required_environment_variables: [WIKIHUB_HOME, WIKIHUB_INSTANCE_ROOT]` 선언 제거 — Hermes 의 secret-on-load 메커니즘 (API key/token 용) 과 path 상수 (install.sh shell rc + systemd `Environment=` 으로 이미 주입) 의 layer 불일치 해소. macOS 메인테이너 세션에서 false `🔑 Skill Setup Required` prompt 트리거 + Hermes secret-store 에 path 상수 등록되는 부작용 제거.
- **로직**: 5개 yaml 파일 (`wh-setup`, `wh-ingest`, `wh-query`, `wh-lint`, `wh-graphify`) 에서 동일 패턴 (`metadata.config.wikihub_home_required: true` + `required_environment_variables` 블록, 각 5 라인) 제거. 코드 path / playbook / ADR 변경 없음. env 의존성 보증은 ADR-0023 (install.sh shell rc) + systemd unit `Environment=` directive 가 그대로 유지.
- **트레이드오프**: frontmatter 의 self-documenting 효과 일부 손실 — env 의존성은 `description` 본문 및 `_system/commands/*.md` playbook 의 entry condition 으로만 표현. 운영자 수동 invoke 시 env 부재면 Python `KeyError` 로 fail-loud (기존과 동일).
- **결론**: 5 파일 -25 라인. macOS 메인테이너 세션 prompt 노이즈 제거 + Hermes secret-store 의미적 정확성 회복. 운영 동작 불변.
- **참조**: features/archive/20260519_wh_skills_env_cleanup/

---

## [2026-05-19] rclone_remote_path

- **목적**: v0.1.1 OCI 실증 결함 closed — (1) `rclone_remote_name: gdrive` 단일 필드로는 mount 와 lsjson 의 sub-path scope 표현 불가 — mount=`gdrive:wikihub` 로 운영하려 해도 lsjson 은 `gdrive:` (Drive 전체) 조회로 scope 불일치. (2) ADR-0035 가 SA + root_folder_id trust boundary 모델 폐기했으나 yaml.example 에 `root_folder_id` 가 dead config 로 잔존. (3) `gdrive:wikihub` 같은 sub-path mount source 사전 부재 시 mount fail 우려.
- **로직**: yaml schema 에 `rclone_remote_path: string = ""` 신설 — mount + lsjson 공통 sub-path scope (빈 문자열이면 remote 루트). `lsjson(remote, *, path="")` 인자 확장 + sync.py 가 yaml options 의 rclone_remote_path 전달. systemd mount template `ExecStartPre=-{rclone_bin} mkdir {remote}:{path}` 추가 — source path 부재 시 멱등 자동 생성. `_cross_vault_subs` 가 `remote_path_for_<vid>` placeholder 추가. ADR-0027/0031 의 root_folder_id 언급은 historical (ADR-0027 supersede 후 본문 미수정 정책 + ADR-0031 catalog 영향 없음).
- **생성 ADR**: 없음 (ADR-0035 §Note 추가 — schema 보강 결정은 ADR-0035 의 §Decision β2/ε2 본의 정합 보강).
- **트레이드오프**: 새 yaml 필드 1건 추가 — v0.1.0 미배포 시점이라 마이그레이션 0. 기존 운영자가 yaml 에 필드 미명시 시 빈 문자열 default 로 기존 `gdrive:` 동작 유지 (backward-compat).
- **결론**: yaml schema 1 필드 추가 + 1 필드 제거 (root_folder_id), 코드 ~10줄, systemd template +2줄, 문서 정리. pytest 57 pass / 1 skip (신규 path-인자 spy 테스트 1건 추가).
- **참조**: features/archive/20260519_rclone_remote_path/

---

## [2026-05-19] hermes_yolo_flag

- **목적**: v0.1.2 OCI 실증 결함 closed — install.sh post-install `hermes chat --skills wh-setup --quiet --query "/wh-setup"` 호출이 Hermes 의 보안 승인 layer (tirith) 에 의해 `Choice [o/s/D]: ✗ Denied` 로 중단. `/wh-setup` playbook 의 inline python 호출 (`python3 -c`, `cat | python3`) 이 위험 명령으로 분류돼 prompt → noninteractive context (install.sh + systemd timer) 에서 응답 불가. systemd timer 가 호출하는 wh-ingest / wh-lint / wh-graphify 도 동일 결함.
- **로직**: agent 의 oneshot 호출 cmdline 에 `--yolo` (Hermes noninteractive auto-approve) 표준 형태로 포함. 4 layer 동시 갱신 — (1) `wikihub.yaml.example:57` `agent.oneshot_args` default, (2) `install.sh:718` F5 migration default literal (update path 자동 갱신), (3) `install.sh:1486-1487` `_step8_wh_setup_skill_meta` 의 직접 호출 cmdline, (4) `scripts/_helpers/render_systemd_units.py:158-159` fail-fast 안내 메시지. systemd unit render dry-run 검증 — vault@/lint ExecStart 둘 다 `--yolo` 포함 확인.
- **생성 ADR**: 없음 (ADR-0032 §Note 추가 — `--yolo` plumbing 결정 기록. §sub-3 cmdline schema 본문 미수정 — 운영자 yaml override 가능 형태 그대로).
- **트레이드오프**: `--yolo` 는 tirith 의 prompt 를 자동 승인 → noninteractive 환경에선 효과적 동일 (prompt 응답 불가로 deny 만 발생했음). interactive manual hermes 호출은 운영자가 yaml override 또는 직접 cmdline 사용 시 trust 모델 본인 책임.
- **결론**: 4 파일 미만 small change. pytest 57 pass / 1 skip 유지. systemd render 결과에 `--yolo` 정확히 주입됨. install.sh 자동 호출 + systemd timer fire 둘 다 tirith 차단 회피.
- **참조**: features/archive/20260519_hermes_yolo_flag/

---

## [2026-05-19] graphify_integration

- **목적**: `_system/commands/graphify.md` (F2 작성 시 4항목 — PyPI 패키지명·MIN_GRAPHIFY_VERSION·CLI 시그니처·ignore 정책 — 잠정) 이 가정한 graphify CLI 가 graphify.net 공식 도구 (PyPI `graphifyy`, MIT) 임을 2026-05-19 검토로 확정. install.sh 가 실제 설치 안 함 결함 closed — wh-lint Step 9 chain 호출 시 `command -v graphify` false → exit 2 Fatal → ops-alert 매 사이클 발화 (v0.1.0 미배포라 surface 안 됐던 잠재 결함). 또한 graphify Pass 3 (Claude/OpenAI subagent semantic extraction) 의 LLM 호출이 wikihub 운영에 새 API key 자료 + 비용 모델 + non-deterministic output 이라는 3가지 새 제약 surface.
- **로직**: ADR-0036 신설 (Accepted) — 6개 결정 (PyPI pin, API key path, hook skip, ignore 정책, non-deterministic 가정, 비용 모델). install.sh `_install_graphify` 함수 신설 (`$VENV_PATH/bin/pip install "graphifyy>=0.8.0,<1.0.0"`) + `_write_installed_versions_sidecar` 의 graphify key 추가 + `_step5_instance_dirs` 의 `~/.config/wikihub/{dir 700, env 600}` ensure + `_step8_guide` 의 API key 안내 + cost 환기. `wikihub.yaml.example` 의 `operations.*` 에 `graphify_min_version`/`graphify_max_version`/`graphify_api_key_env_name` 추가. `_system/systemd/lint.service.template` 에 `EnvironmentFile=-%h/.config/wikihub/env` (lenient `-` prefix). `_system/commands/graphify.md` 의 잠정 4항목 확정 + L83 deterministic 가정 §Note. `_system/commands/setup.md` Step 1 검증에 graphify env file + wiki/.graphifyignore ensure 추가. `_system/templates/wiki/.graphifyignore` template 신설 (`_lint/`, `_state/` 제외). ADR-0005/0023 §Note 추가 (도구 확정 + 설치 책임 layer 분리). systemd render dry-run — `EnvironmentFile=-%h/.config/wikihub/env` 정확 출력 확인. pytest 57 pass / 1 skip.
- **생성 ADR**: ADR-0036
- **트레이드오프**: PyPI 의존성 신규 추가 (`graphifyy`) — rclone 의 SHA256 verify 와 다른 supply chain layer (pip hashes). hash pin enforce 는 v0.2.x 검토 트리거. 보안 자료 layer 가 2개로 분리 (rclone.conf OAuth + `~/.config/wikihub/env` LLM key) — 단일 layer 통합 검토는 v0.2.x. graphify Pass 3 운영자 별도 API 비용 발생 — token-budget / backend 통제 schema 부재 (v0.1.0 은 wh-lint timer 주기로만 통제).
- **결론**: 잠정 → 확정 + 신규 plumbing. install.sh + yaml + systemd + 4개 docs (graphify.md, setup.md, 2개 ADR §Note) + ADR 신규 + 신규 template. VERSION 동일 (0.1.3) 유지 — hermes_yolo_flag (v0.1.3 bump) 와 같은 release window 의 통합 cleanup 으로 처리.
- **후속 cleanup (2026-05-19, 같은 release window 흡수)**: 3 playbook 의 graphify 사용 패턴 검토 (서브에이전트 2건 design review 통합) 후 3건 채택 — (a) `.graphifyignore` 의 `**/log.md` 추가 (vault 별 ingest log 의 entity-noise 차단), (b) `ingest.md` 산출물 표에 `graphify-out/` 미관여 명시 (책임 경계 1줄), (c) `lint.md` Step 9 의 graphify 결과 self-check (`N/M < 0.5` ratio 가 Pass 3 silent partial failure 의심 가드, ops-alert 트리거). #2 (lint churn §Note) + #4 (query Leiden v0.2.x §Note) 는 ADR-0036 §D4 / context.md echo 위험으로 drop (Karpathy §2 Simplicity First 정합). 별도 feature ID 미발급 — design review evidence 는 features/archive/20260519_graphify_usage_review/ 보존.
- **추가 cleanup — systemd timer `OnActiveSec` (같은 release window 흡수, ADR-0036 무관)**: Hermes OCI 운영 중 surface 한 결함 — `install.sh --update` 후 `daemon-reload` + timer 재시작 시 `next_elapse=0` 으로 영원히 대기 → 운영자/Hermes 가 매번 수동 trigger 필요했음. 근본 원인: timer template (vault@ + lint) 가 `OnBootSec` (boot 기준, system uptime 길면 이미 과거) + `OnUnitInactiveSec` (service prior run 없으면 기준점 부재) 두 조건만 보유 → timer 재시작 on running system 시나리오 미커버. `Persistent=true` 는 `OnCalendar=` 전용이라 본 unit 들에서 no-op (dead config). Fix — 두 template 에 `OnActiveSec=Ns` 추가 (timer active 기준 monotonic) + `Persistent=true` 제거. ADR 무신설 (ADR-0030 의 install.sh `--update` auto-recovery 의도 정합 보강). systemd render dry-run — vault@/lint 모두 `OnActiveSec` 정확 출력 + `Persistent=` 제거 확인.
- **추가 cleanup — install.sh `_migrate_agent_schema` in-place `--yolo` 삽입 (v0.1.3 self-fix)**: v0.1.3 첫 OCI 배포 직후 Hermes 가 surface — render 후 unit ExecStart 에 `--yolo` 미반영. 근본 원인: migration 의 trigger 조건이 `{skill}` placeholder **부재** 시만 overwrite — v0.1.0~v0.1.2 시점에 이미 F5 form 으로 작성된 yaml (`oneshot_args: [chat, --skills, {skill}, --quiet, --query]`) 은 `{skill}` 존재라 migration skip → 기존 `--yolo` 없는 형태 그대로 render. Fix — `_migrate_agent_schema` detection 분기에 "F5 form 인데 `--yolo` 누락" 케이스 추가 + PYEOF block 에 in-place 삽입 로직 (`--query` 앞에 `--yolo` insert, 운영자 override 의 다른 인자 보존). v0.1.0~v0.1.2 → v0.1.3+ upgrade path 자동 정합화. `Persistent=true` 제거 (위 OnActiveSec 항목) 와 함께 v0.1.3 amend 반영.

---

## [2026-05-20] install_robustness (v0.1.4)

- **목적**: v0.1.3 의 두 fix (in-place `--yolo` migration + `OnActiveSec` 추가) 가 default 호출 경로에서 무력화되는 결함 closed — Hermes OCI 운영 중 surface.
  1. `_migrate_agent_schema` 의 prompt 가 `curl | bash` (ADR-0023 default invocation) 의 pipe stdin 에서 즉시 EOF → 자동 N → migration 거부 → yaml 의 `--yolo` 미삽입 → 매 install.sh 호출마다 systemd unit 의 `--yolo` 누락.
  2. `_step8_systemd_render` 가 daemon-reload 만 하고 timer restart 안 함 → fresh / `--force-fresh` 경로에서 이미 enable+start 상태인 timer 가 새 template 적용 안 됨 → OnActiveSec=5min 도 stale "active since" 기준이라 이미 과거 → lint NEXT="-" 영원히 대기.
- **로직**: install.sh 2곳 fix.
  - `install.sh:745` (`_migrate_agent_schema`) — `[[ -t 0 ]] && [[ -z "${WIKIHUB_NONINTERACTIVE:-}" ]]` 조건 추가. stdin 이 tty 가 아니면 (pipe / cron / Hermes subprocess) 자동 진행. backup (`.wikihub-bak.<ts>`) 생성은 그대로 보존.
  - `install.sh:1542` (`_step8_systemd_render`) — daemon-reload 직후 `systemctl --user try-restart 'wikihub-mount@*.service' 'wikihub-vault@*.timer' wikihub-lint.timer` 호출. `try-restart` 는 inactive unit 에 no-op 이라 update path 의 stop/start 시퀀스와 충돌 없음. 이미 running 인 timer 만 restart → "active since" fresh → OnActiveSec=5min 정상 trigger.
- **생성 ADR**: 없음 (ADR-0030 `--update` auto-recovery + ADR-0023 install distribution 의 default invocation 정합 보강).
- **트레이드오프**: 자동 migration 진행이 운영자 의도와 다를 risk — 보수적 transformation (schema lift + flag insert) + backup 생성으로 mitigation. `WIKIHUB_NONINTERACTIVE` env 미설정 + tty 검출이 명시 거부 경로.
- **결론**: 2 곳 변경 (install.sh) + VERSION 0.1.3 → 0.1.4. pytest 57 pass 유지. v0.1.3 immutability 회복 — force-push 1회로 종료, 본 변경은 새 commit + v0.1.4 tag 로 정합.
- **참조**: features/archive/20260519_install_robustness/

---

## [2026-05-20] graphify_backend_flexibility (v0.1.4 wave — 2번째 entry)

- **목적**: ADR-0036 §D2 (2026-05-19) 의 default `ANTHROPIC_API_KEY` backend lock 이 OCI 운영자 비용 모델에 misaligned — 별도 Anthropic API key 발급 의사 없음 + Hermes 측에 OpenCode-go (`https://opencode.ai/zen/go/v1`) API key 이미 설정 (운영 모델 = `minimax-m2.5`, 초기 `deepseek-v4-pro` 였으나 reasoning hang 결함으로 변경, 2026-05-20). backend 선택 layer 보강 + lint Step 9 의 graphify hang 가드 추가.
- **로직**: graphify CLI source 검증 (`graphifyy 0.8.13/llm.py:64-71, 287`) — `ollama` backend 가 실제로는 "OpenAI-compatible endpoint generic client" 임을 확인 (`OLLAMA_BASE_URL` 으로 base_url override + `OpenAI()` SDK 사용). yaml schema 변경: `graphify_api_key_env_name` 폐기 + `operations.graphify_backend` 신설 (catalog `""` auto-detect | claude | claude-cli | openai | gemini | kimi | deepseek | ollama | bedrock). install.sh `_step5_instance_dirs` 의 env template 에 backend 별 예시 5종 (Anthropic / OpenAI / OpenCode-go via ollama / Ollama local / claude-cli) 표기. lint.md Step 9 가 yaml graphify_backend 읽어 `--backend $value` 명시 전달 + `timeout 300 graphify ...` wrapper (exit 124 시 report 에 timeout 기록 + lint 본체 계속, ADR-0036 §D6 정합 보강). setup.md Step 1 의 env file 검증 단순화 (graphify_api_key_env_name 의존 제거) + Hermes `terminal.env_passthrough` 안내 1줄.
- **생성 ADR**: 없음 (ADR-0036 §Note 추가 — §D2 본문 미수정, schema 정본은 §Note + 본 feature 의 analysis_and_design).
- **트레이드오프**: yaml 1 field 교체 (`graphify_api_key_env_name` → `graphify_backend`) — v0.1.0 미배포 시점이라 마이그레이션 0 (단 OCI 가 v0.1.3 으로 1회 배포 후라 운영자 yaml 의 `graphify_api_key_env_name` 키 잔존 시 install.sh 무관심 — graphify 호출 흐름에 영향 없음, dead config 로 자연 무시). operator-side Hermes `terminal.env_passthrough` 설정 책임 추가 — wikihub spec 차원 자동화 안 함 (Hermes config 는 wikihub 외부 영역).
- **결론**: yaml + install.sh template + 2 playbook + ADR §Note. v0.1.3 → v0.1.4 wave 2번째 entry (install_robustness 후속). pytest 57 pass 유지 (코드 변경은 yaml 읽는 부분 외 없음).
- **참조**: features/archive/20260520_graphify_backend_flexibility/

---

## [2026-05-20] migration_prompt_simplify (v0.1.5)

- **목적**: v0.1.3 → v0.1.4 의 동일 root cause cycle 종료 — `install.sh:_migrate_agent_schema` 의 `[[ -t 0 ]]` 기반 noninteractive 검출이 Hermes terminal tool 의 PTY 할당으로 거짓 양성 → prompt fire → empty input → default N → migration 거부 → yaml `--yolo` 미반영 → systemd unit `--yolo` 누락 → 운영자 매번 수동 patch.
- **로직**: 서브에이전트 2건 design review (architectural/safety + operational/UX) 후 옵션 (1) 채택 — prompt 분기 자체 제거 + info log 1줄 (`schema drift detected — auto migration`). transformation 의 backup 자동 생성 (`.wikihub-bak.<utc_iso>`) 이 운영자 의도 override safety net 으로 유지. macOS dev box 는 `$WIKIHUB_HOME/wikihub.yaml` 부재 → 함수 즉시 return 0, 영향 없음.
- **생성 ADR**: 없음 (ADR-0032 §Note 추가 — prompt 제거 결정 + 미래 재검토 트리거 기록).
- **트레이드오프**: 외부 운영자가 의도적으로 `--yolo` 없는 yaml 운영하려 할 시 매 install.sh 가 덮어씌움 — 현 시점 운영자 base = Hermes 1대 + 메인테이너 1명, 이 시나리오 가설. v0.2.x 외부 운영자 사례 surface 시 escape hatch (예: `WIKIHUB_SKIP_MIGRATION=1` env) 별도 feature 로 추출 — 재검토 트리거 ADR-0032 §Note 명시.
- **결론**: install.sh `_migrate_agent_schema` 의 prompt 블록 10줄 → info log 1줄. v0.1.4 → v0.1.5 patch bump. pytest 57 pass 유지.
- **참조**: features/archive/20260520_migration_prompt_review/ (context + 2 design reviews + plan)

---

## [2026-05-20] lint_fallback_toggles (v0.1.5 wave — 2번째 entry)

- **목적**: Hermes OCI lint timeout 진단 — root cause = DeepSeek API 응답 느림 (네트워크 대기, CPU 10.6초). 운영자(Hermes) 수동 SIGINT 로 lint 중단. lint chain 의 graphify (Step 9) 호출 + lint 본체 모순 점검 (Step 6) 의 LLM cost 통제 토글 부재 — quick fix 로 yaml schema 보강.
- **로직**: yaml 3 변경 — (a) `agent.timeout_sec` default 600 → 1200 (Hermes 가 이미 TimeoutStartSec=1200 으로 manual patch 실증), (b) `operations.graphify_enabled` (default true; false 시 lint Step 9 skip + report 1줄), (c) `operations.lint_contradiction_check` (default true; false 시 lint Step 6 skip — 가장 무거운 LLM 호출). lint.md Step 6/Step 9 진입에 yaml toggle read + skip 분기. setup.md maintainer catalog 갱신.
- **생성 ADR**: 없음 (ADR-0036 §Note 추가 — graphify_enabled toggle + v0.1.6 분리 트리거 명시).
- **트레이드오프**: `graphify_enabled: false` 시 lint Step 3 의 wiki 순회 fallback 으로 lint 본체 정상 동작 — graph.json 갱신만 stale (다음 cycle 까지). `lint_contradiction_check: false` 시 wiki 의 모순·stale 정보 자동 detect 안 됨 — 메인테이너 수동 `--apply` 호출 시 1회 점검 보완 권장.
- **결론**: yaml 3 field 변경 + lint.md 2 분기 + setup.md catalog + ADR-0036 §Note. v0.1.5 wave 2번째 commit (migration_prompt_simplify `152d751` 와 함께 push 예정). graphify 별도 systemd unit 분리는 v0.1.6 별도 feature.
- **참조**: features/archive/20260520_lint_fallback_toggles/

---

## [2026-05-20] agent_model_per_skill (v0.1.5 amend — 같은 release window)

- **목적**: Hermes OCI 진단 — (1) reasoning 모델 (deepseek-v4-pro/flash) 이 작은 max_tokens 에서 content="" → agent hang, (2) MiniMax M2.5 등 일부 모델이 한국어 응답에 한자 섞어 출력. wh-lint 만 model 분리 + 출력 언어 정책 lift.
- **로직**: yaml `agent.models` map 신설 (default 빈 dict; per-skill model override). `scripts/_helpers/render_systemd_units.py:_per_skill_invocation` 갱신 — `--model <id>` 명시 inject (--query 앞에, hermes_yolo_flag 의 `--yolo` 패턴 동일). yaml.example 예시 `wh-lint: minimax-m2.5`. `_system/commands/lint.md` 상단에 "출력 언어 정책" section — 한자 → 한글 변환, 고유명사 예외, 영어 약어 그대로. 적용 범위: Step 3·4·5·6 의 LLM 호출 공통. ADR-0032 §Note 추가 (per-skill model + 출력 언어 정책 결정 정본).
- **생성 ADR**: 없음 (ADR-0032 §Note 추가).
- **트레이드오프**: per-skill override 사용 시 운영자가 yaml 의 `agent.models` map 을 명시 관리 필요. 빈 dict default 라 backward-compat. 출력 언어 정책은 lint 만 적용 — 다른 wh-* skill (ingest/query/graphify) 의 동일 결함 surface 시 점진 lift 권장.
- **결론**: yaml 1 map + render helper 14줄 + lint.md 1 section + ADR §Note + setup.md catalog 1줄. v0.1.5 amend (force-push 4번째). render dry-run 검증 — lint.service 만 `--model minimax-m2.5` inject, 다른 wh-* unit 미영향 확인. pytest 57 pass.
  - **wh-ingest 추가** (2026-05-20 후속): `agent.models` 에 `wh-ingest: deepseek-v4-pro` 추가 — per-source LLM 호출 (entity/concept 추출) 의 reasoning 정확도 활용. 운영자 판단 — max_tokens hang risk 인지 (Hermes 실증) 후 운영 모델 선택. surface 시 `qwen3.6-plus` 로 fallback 권장 (non-reasoning + 한국어 안정).
  - **ingest.md 출력 언어 정책 추가** (2026-05-20 후속): `_system/commands/ingest.md` 상단에 lint.md 와 동일 패턴 "출력 언어 정책" section — Step 4 (entity/concept 추출) 의 LLM 응답에서 한자 → 한글 변환 지시. deepseek-v4-pro / minimax 등 모델의 동음이의 한자 출력 결함 대비.

---

## [2026-05-20] alert_pipeline_overhaul (v0.1.5 wave — architectural)

- **목적**: ADR-0024 (fatal alert contract) 의 dispatch + trigger layer 두 한계 — (a) single-channel (webhook URL 만), (b) attempts-based trigger 만 (age-based monitor 부재) — wikihub spec 차원 통합. Hermes OCI 패치 (Telegram 발송 + 30분 cron pending-check) 정본화.
- **로직**: ADR-0037 (alert pipeline architecture) 신설 (Accepted, ADR-0024 complement).
  1. **Telegram channel** (ADR-0037 §D1): `scripts/ops-alert.py` 에 `send_telegram` + `format_telegram_message` 추가. `main()` dispatch 가 webhook + Telegram 병행 — 한쪽이라도 성공 시 `alerted_at` 갱신. env: `TELEGRAM_ALERT_BOT_TOKEN` + `TELEGRAM_ALERT_CHAT_ID`. `_system/systemd/ops-alert.service` 에 `EnvironmentFile=-%h/.config/wikihub/env` 추가.
  2. **wikihub-pending-monitor systemd unit** (ADR-0037 §D2): `_system/systemd/wikihub-pending-monitor.{service,timer}.template` 신설. timer `OnBootSec=10min / OnActiveSec=10min / OnUnitInactiveSec=30min`. service oneshot, `ExecStart=python scripts/pending_monitor.py`. `OnFailure` 미설정 — 항상 exit 0 + ops-alert recursion 회피.
  3. **`scripts/pending_monitor.py` 신설**: enabled vault 순회 → `pending_ingest.json` mtime age 검사 → age > `operations.pending_alert_age_sec` (default 3600s) → `last_failure.json` 갱신 (scope="ingest_pending") + `systemctl --user start ops-alert.service` 호출.
  4. **yaml schema**: `operations.pending_alert_age_sec` (default 3600). `OperationsConfig` dataclass + `_parse_operations` 갱신.
  5. **install.sh**: `_step5_instance_dirs` 의 env template 에 `TELEGRAM_ALERT_*` 예시 + bot 생성 안내. `_systemd_stop_before_update` + `_systemd_start_after_update` + `_step8_systemd_render` try-restart + reset-failed list 에 pending-monitor 추가. `_step8_guide` 에 운영 진단 + Telegram 검증 명령.
  6. **setup.md catalog**: `pending_alert_age_sec` 추가.
  7. **ADR**: ADR-0037 신설 (Accepted, ADR-0024 complement) + ADR-0024 §Note 1줄 (cross-reference) + docs/adr/README.md index 갱신.
- **생성 ADR**: ADR-0037 (alert pipeline architecture)
- **트레이드오프**: Telegram bot token / chat_id 가 secret — `~/.config/wikihub/env` + Hermes `terminal.env_passthrough` 운영자 책임. pending_monitor → ops-alert.service 호출 recursion risk — 둘 다 항상 exit 0 + StartLimitBurst mitigation. wikihub-pending-monitor.service 가 systemd unit 1개 추가 — render 부담 acceptable.
- **결론**: 새 systemd unit 2개 + 새 script 1개 + ADR 신설 + ops-alert.py Telegram 통합 + yaml schema 1 field + install.sh 다중 갱신. render dry-run 8 units 출력 확인 (기존 6 + pending-monitor 2). pytest 57 pass + ops-alert/pending_monitor import 검증.
- **버전**: v0.1.5 유지 (user 명시 "버전은 0.1.5 사용"). v0.1.5 wave 의 architectural 보강 — main fast-forward push + v0.1.5 tag re-point (force-update) + latest force-update.
- **참조**: features/archive/20260520_alert_pipeline_overhaul/
  - **lint default interval 24h → 3h** (2026-05-20 후속): `wikihub.yaml.example` 의 `operations.lint_interval_hours: 24 → 3` 갱신 — 더 빠른 wiki 위생 사이클. lint.timer.template / setup.md / lint.md / ADR-0036 §Note 동기화. graphify chain (graphify_enabled=true) 의 cost 가 8배 증가하나 `graphify_enabled: false` toggle 로 운영자 통제 가능. ADR-0036 §D6 cost upper bound 가정 변경 — default 값만 갱신, 본문 미수정.
- **참조**: features/archive/20260520_agent_model_per_skill/




- **참조**: features/archive/20260519_graphify_integration/ + features/archive/20260519_graphify_usage_review/

---

## [2026-05-22] v016_operational_default_align (v0.1.6)

- **목적**: 운영자가 v0.1.5 배포 이후 자기 환경 (`~/wikihub/wikihub.yaml` + `~/.hermes/config.yaml` + `~/.config/wikihub/env` + systemd unit) 에 누적 적용한 운영 결정 ↔ wikihub repo 정본 default 의 4건 mismatch 해소. 새 운영자 / fork 가 운영자의 검증된 결정을 install 직후 자동 전수받도록 정본화.
- **로직**: 4건 정본 변경 + 부속 갱신.
  1. **`wikihub.yaml.example` `agent.models.wh-lint`**: `minimax-m2.5` → `deepseek-v4-flash`. 운영자 검증 latency (2.6~6.4s/call, 260521 §B 측정) + wh-ingest (`-pro`) 와 DeepSeek 패밀리·opencode-go backend 일관성. 한자→한글 보호는 lint.md "출력 언어 정책" 섹션이 v0.1.5 에서 이미 model-agnostic layer 로 강화돼 minimax 한정 안전 가정 해제.
  2. **`wikihub.yaml.example` `vaults[].sync_interval_sec`**: `600` → `3600` (1h). mechanical phase IO·log.md noise 절감 (lsjson + log append 빈도 6배 감소). has_changes=false 경로 LLM cost 는 0 이지만 idle cycle 의 IO 부담 완화.
  3. **`install.sh` `_step5_instance_dirs` env template**: graphify backend 예시 6번째 항목 `gemini` 추가 (`GEMINI_API_KEY` + `GEMINI_BASE_URL` + `GEMINI_MODEL`, non-reasoning flash-lite 계열 권장 — 260521 §F 실증). yaml.example `graphify_backend` catalog 의 `gemini` 와 비대칭 해소.
  4. **`install.sh` `_step8_guide` + `_system/commands/setup.md` Step 1**: hermes `~/.hermes/config.yaml` 의 `delegation.model: minimax-m2.5` 권장 안내 추가. 자동 patch 미수행 (Hermes 는 wikihub 외 사용처 존재 가능 — 의도 침범 회피). setup.md Step 1 의 warn 출력에 정합 체크 1줄 추가 (정보 출력만).
  5. **부속**: ADR-0032 §Note 추가 (wh-lint default 갱신 사유 + 운영 정본 trail). README v0.1.0 → v0.1.6 (badge + 개발 상태 1줄 + 로드맵 표 v0.1.x 누적 row 추가). `_system/VERSION` 0.1.5 → 0.1.6.
- **트레이드오프**:
  - wh-lint default `deepseek-v4-flash` 의 DeepSeek 한자 섞임 빈도가 minimax-m2.5 와 동등하다는 정량 검증은 운영자 실 운영 trail (한자 issue 미보고) 외에 없음 — lint.md output policy 의 후처리 보호 layer 가 의존 layer.
  - sync_interval 1h → 변경 detect 지연 ~1h. 더 짧게 원하면 운영자 override.
  - hermes config 자동 patch 회피 → 새 운영자가 안내 미숙독 시 subagent 가 hermes default 모델 fallback → 한자/비용/latency 불일치. setup.md warn 으로 surface.
  - README ADR-0035·0036·0037 일괄 align (Mermaid gws/SA 잔존·F3·F4 description·graphify URL) 은 본 feature scope 초과로 별도 feature 분리 (v0.1.7 후보).
- **결론**: yaml.example 2줄 + install.sh 2블록 + setup.md 1줄 + ADR §Note + README 버전·로드맵·개발 상태 + HISTORY + VERSION. Step 4 (Review) 생략 — 외부 인터페이스 미변경 (스키마 동일, default 값만 변경, 가이드 추가). render dry-run 검증 — wh-lint.service 의 ExecStart 에 `--model deepseek-v4-flash` 정합 + vault@.timer 의 `OnUnitInactiveSec=3600s` 정합. v0.1.5 → v0.1.6 patch 승격 + 운영 server `install.sh --update`.
  - **graphify.md Step 2 정본 fix** (2026-05-22 후속, v0.1.6 유지): `_system/commands/graphify.md` Step 2 의 `graphify CLI` 호출에 `--backend $backend` flag + `timeout 300` 명시 lift — lint.md Step 9 의 backend-aware 호출 코드와 동일 패턴으로 정합. 이전 graphify.md Step 2 는 backend flag 부재로 graphify CLI auto-detect 의존 → 다중 backend env (예: ANTHROPIC_API_KEY + OLLAMA_API_KEY 공존) 시 우선순위 충돌 risk. fix 로 yaml `operations.graphify_backend` 명시값이 수동 `/wh-graphify` 호출에도 적용. v0.1.6 tag 재설정 (force-update) + latest 재설정.
- **참조**: features/archive/20260522_v016_operational_default_align/

---

## [2026-05-22] yaml_schema_drift_migration (v0.1.7)

- **목적**: v0.1.6 배포 직후 OCI 운영 server `install.sh --update` 실행 시 운영자의 manual systemd unit edit 4건 (lint·ingest `--model` × 2 + lint `TimeoutStartSec` + vault@.timer `OnUnitInactiveSec`) 손실 사건 surface. 진단: 운영자의 `~/wikihub/wikihub.yaml` 이 v0.1.0 era schema 동결 + v0.1.5+ 신설 field 부재 → render 의 default fallback (TimeoutStartSec=600, `--model` flag 미주입, OnUnitInactiveSec=600s) → 운영자 manual edit overwrite. install.sh 가 schema drift 보호 layer 신설.
- **로직**: `install.sh` `_migrate_agent_schema` 확장 — 기존 Group A (ADR-0033 skill_prefix + ADR-0032 oneshot_args) 외에 두 그룹 신설.
  1. **Group B — 자동 추가 (안전 default, 부재 시만)**: `agent.timeout_sec: 1200`, `agent.models: {wh-lint: deepseek-v4-flash, wh-ingest: deepseek-v4-pro}`, `operations.pending_alert_age_sec: 3600`, `operations.lint_contradiction_check: true`, `operations.graphify_enabled: true`, `operations.graphify_backend: ""`, `operations.graphify_min_version: "0.8.0"`, `operations.graphify_max_version: "0.99.99"`. yaml.example schema 와의 single source of truth 보장.
  2. **Group C — 자동 삭제 (ADR-0035 폐기 field cleanup)**: `vaults[].options.{bootstrap_allowed, credentials_path, root_folder_id, cursor_path}` 잔존 시 삭제. schema noise 제거.
  3. **정책**: PTY-safe (prompt 0 — v0.1.5 §Note 2026-05-20 일관성) + idempotent (재실행 no-op) + 값 변경 자동 회피 (운영자 trust — `sync_interval_sec: 600` 같은 값은 그대로). backup `.wikihub-bak.<utc_iso>` 매 migration 시 생성. ruamel.yaml round-trip 으로 주석 보존.
  4. **drift detect**: Python single-shot 으로 3-group flag 수집 + 변경 발생 시 info log 로 어떤 drift 감지됐는지 출력 (운영자 surface).
  5. **ADR 갱신**: ADR-0031 §Note (install.sh 의 yaml mutation 책임 boundary — value vs schema 분리), ADR-0032 §Note (`_migrate_agent_schema` 확장 범위 정본화).
- **트레이드오프**:
  - 값 변경 자동 회피 → 운영자가 새 default 적용 원하면 yaml 직접 편집 + install.sh 재실행 필요 (자동성 일부 희생, 운영자 trust 보호)
  - yaml.example 의 신설 field 가 추가될 때마다 본 함수의 catalog 동기 갱신 필요 (추가 maintenance cost) — 단순 add 만이라 부담 작음
  - PTY-safe 정책 유지 (prompt 0) → 값 변경 prompt 옵션 없음. `WIKIHUB_INTERACTIVE_MIGRATE=1` opt-in 은 v0.1.8+ 후보 (M3 미결 사항)
- **결론**: install.sh `_migrate_agent_schema` 약 120줄 추가 (기존 ~80줄 → 약 200줄) + ADR-0031·ADR-0032 §Note + README 버전·로드맵 + VERSION 0.1.6→0.1.7 + HISTORY 항목. 자가 검증: fixture (v0.1.0 era yaml) 1차 migration → 신설 field 8건 자동 추가 + 폐기 field 2건 자동 삭제 + 운영자 의도 값 (sync_interval_sec=600, lint_interval_hours=24) 보존 + 주석 보존 확인. 2차 migration idempotent (diff 0). Step 4 (Review) — 멀티 reviewer 권장 수행이었으나 user 진행 압축 지시로 self-verification 으로 대체. v0.1.6 → v0.1.7 patch 승격 + 운영 server `install.sh --update` 흐름이 즉시 운영 yaml 자동 보강 효과.
- **참조**: features/archive/20260522_yaml_schema_drift_migration/

---

## [2026-05-24] graphify_profile_namespace (v0.1.7 follow-up)

- **목적**: OCI 운영 (2026-05-22~24) 에서 두 가지 문제 surface — (1) `~/.config/wikihub/env` 의 `OLLAMA_BASE_URL`/`OLLAMA_API_KEY`/`OLLAMA_MODEL` 이 systemd `EnvironmentFile=` 경유로 Hermes parent 에 주입 → Hermes 가 자기 LLM backend 로 인식 → `model.default` (deepseek-v4-flash) 오버라이드, (2) graphify CLI v8 의 실제 명령어 (`graphify extract <wiki> --backend X --model Y --max-concurrency N --out DIR`) 와 `_system/commands/graphify.md` Step 2 의 호출 패턴 (`graphify <wiki> --update $backend_flag`) 어긋남 (drift 가 v7 era 유지). 부차 요구: opencode / openrouter / local Ollama 등 multi-profile 동시 보유 + yaml 한 줄 swap.
- **로직**: env namespace 격리 + graphify v8 CLI sync + 자동 migration 의 3-layer 통합.
  1. **env namespace**: `~/.config/wikihub/env` 의 표준 컨벤션 키 (`OLLAMA_*`/`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`GEMINI_*`) → wikihub-private `WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL>` namespace. graphify subprocess 호출 시점에 `env <BACKEND_ENV>=<value> graphify ...` 로 explicit 주입 — Hermes parent 에는 backend env 가 보이지 않음.
  2. **yaml profile selector**: `operations.graphify_profile: <name>` (default `ollama_gemma`) 신설. env 의 어떤 keyset 을 활성으로 쓸지 yaml 한 줄로 결정. multi-profile 동시 보유 + 전환은 yaml 1줄 수정.
  3. **graphify.md Step 2 전면 재작성**: profile resolve + 정규식 검증 (`^[a-z][a-z0-9_]*$`) + endpoint pattern 자동 분기 (loopback hostname → `OLLAMA_HOST` / 외부 → `OLLAMA_BASE_URL`) + concurrency 휴리스틱 (`*cloud*` model 또는 외부 endpoint → 4, 진짜 local → 1) + 6 backend case dispatch (gemini/kimi/claude/openai/deepseek/ollama) + 2-mode dispatch (수동 `--rebuild` → graph.json 삭제 → extract / 그 외 → extract — graphify internal cache 가 자동 incremental). Step 3 결과 검증에 `jq 'keys'` fail 시 partial graph.json 삭제 + exit 1 보호.
  4. **install.sh `_migrate_graphify_env` 신규**: 기존 env 파일의 legacy 키 자동 삭제 + Telegram 값 + 운영자 custom profile 보존 + `ollama_gemma` default inject. PTY-safe + idempotent + backup (`.wikihub-bak.<utc_iso>`, 30일 retention).
  5. **install.sh `_migrate_agent_schema` 확장**: `_op_defaults` 에 `graphify_profile: "ollama_gemma"` 추가 + invalid profile 값 install-time non-fatal warn (W_ flag, 값 mutation 안 함). flag separator `,` → newline (profile 값에 `,` 박힌 case robust).
  6. **부속**: lint.md Step 9 의 v7 패턴 설명 block (`backend_flag` + `timeout 300` + `--update`) → 1줄 reference (graphify.md 단일 책임, ADR-0006 + ADR-0038). setup.md Step 1 의 Hermes `terminal.env_passthrough` 안내 정리 (namespace 격리 후 불필요). lint.service.template + install.sh `_step5_instance_dirs`/`_step8_guide` 의 stale legacy env 예시 cleanup. `docs/graphify-backend-test-reference.md` (이전 Downloads) 프로젝트로 이전 + §6 Alternative profile cookbook (6 profile examples).
- **생성 ADR**: ADR-0038 (graphify env namespace isolation — namespace 격리 + Profile bundle + auto-migration + Hermes trust 가정 + ADR-0036 §D2 partial supersede)
- **트레이드오프**:
  - 운영자 코멘트 drop — `_migrate_graphify_env` 가 canonical template 으로 rewrite → 운영자가 적어둔 inline 메모 소실 (backup 에서만 참조 가능). install.sh info 로 surface.
  - endpoint pattern 분기 fragility — LAN Ollama (`http://192.168.x.x:11434`) / Docker network 의 native API 노출 시 silent misroute 가능. v0.2.x 의 `WIKIHUB_GRAPHIFY_<P>_OLLAMA_MODE=native|compat` env override 도입 deferred.
  - backend/profile prefix mismatch silent misconfig — `backend: claude` + `profile: ollama_gemma` 같은 mixed config 시 graphify.md 가 ANTHROPIC_API_KEY 로 dispatch + ollama_gemma 의 ENDPOINT 무시. consistency warn 추가 안 함 (advanced mixed case 존중).
  - `check-update` gate deferred — OCI 검증 (2026-05-24) 결과 3 시나리오 모두 exit=0 + stdout 무음 → gate 활용 불가. graphify 본가의 notification 채널 spec 명확화 시 v0.2.x 재방문.
- **결론**: install.sh `_migrate_graphify_env` 약 110줄 신설 + `_migrate_agent_schema` 확장 + `_step5_instance_dirs` env template 단순화 (40줄 → 12줄) + `_step8_guide` 안내 정리. graphify.md Step 2 162줄 변경 (전면 재작성), lint.md Step 9 15줄 변경 (1줄 reference), setup.md Step 1 4줄 변경, lint.service.template 4줄 변경. ADR-0038 신설 (~75줄), ADR-0036 §Note 2026-05-24 추가 (~95줄 — 결정 A~F + Rollback procedure + Gap window 분석), `docs/graphify-backend-test-reference.md` (이전 Downloads) 프로젝트로 이전 + §6 cookbook (~100줄). README v0.1.7 follow-up 1줄 + HISTORY 본 항목 + VERSION 미변경 (0.1.7 유지). Step 2 + Step 4 모두 멀티 reviewer 수행 — Step 2 design review 1/2 (C1~C3, A4~A7, D8~D10 + U1~U3 결정 추출) → 본 patch 흡수. Step 4 code review 1/2 (C1 IPv6 `[::1]` glob escape + C2 `${1:-}` set -u + H1 `while read || [[ -n ]]` last-line + R2-M1~M3 stale 코멘트 + R2-M5 bash 가정 명시 + R1-M1 flag separator newline) 모두 즉시 fix 흡수. bash syntax 검증 (`bash -n install.sh` pass) + Critical/High fix 의 동작 검증 (IPv6 MATCH, set -u 안전, last-line 잡힘). 운영 server `install.sh --update` 1회로 legacy env 자동 migration + yaml `graphify_profile` 자동 추가. Hermes bleed 즉시 차단 효과.
- **참조**: features/archive/20260524_graphify_profile_namespace/

---

## [2026-05-25] legacy_migration_cleanup (v0.1.8)

- **목적**: v0.1.0~v0.1.6 era 의 1회성 migration 코드 5건 (#M~#Q) 일괄 정리. 운영자 base 가 v0.1.7 정착 후 영구 no-op state 인 코드를 install.sh + scripts 에서 제거하여 가독성·유지보수성 개선. v0.1.8 의 첫 atomic feature (multi-feature v0.1.8 release 의 일부).
- **로직**: install.sh 5 항목 + `scripts/migrate_layout.sh` 파일 전체 삭제 + Step 4 review 흡수 (`scripts/_helpers/hermes_config_migrate.py` orphan 동반 삭제) — (a) `_migrate_graphify_env` 함수 + main flow 호출 (#M, ADR-0038 의 v0.1.7 follow-up 1회성), (b) `_migrate_agent_schema` Group A — `wh:`→`wh-` (`A_skill_prefix`) + oneshot legacy (`A_oneshot_legacy`) + `--yolo` 누락 (`A_yolo_missing`) (#N, ADR-0033/0032 의 v0.1.0~v0.1.3 era), (c) `_migrate_agent_schema` Group C — vaults legacy options 4 키 (`bootstrap_allowed` / `credentials_path` / `root_folder_id` / `cursor_path`) cleanup (#O, ADR-0035 의 v0.1.4/v0.1.5 era), (d) `WIKIHUB_HOME` silent bug detect block (#P, ADR-0034 의 pre-v0.1.0 transition), (e) `scripts/migrate_layout.sh` 313줄 9-phase state machine 파일 + `scripts/_helpers/hermes_config_migrate.py` orphan helper (#Q + Step 4 review H1-b 흡수, ADR-0034 transition helper chain). 보존 — `_migrate_agent_schema` 함수 본체 (Group B v0.1.5+ field auto-add + A4 W_graphify_profile_invalid warn) + `_step5_instance_dirs` env template (fresh install 영구 가치). ADR-0036 §Note 2026-05-24 의 §Rollback procedure + §배포 Gap window 분석 두 절 동시 삭제 (둘 다 `_migrate_graphify_env` referent — dead text). README §Migration 절 historical note 로 단순화 + _system/wiki-schema.md directory tree 정리 + ADR-0032 §sub-3 dead block 정리 + install.sh:1143 caller 주석 갱신.
- **생성 ADR**: 없음 (refactoring). 단 ADR-0034 §"후속 영향" + ADR-0036 §Note §Cross-references + ADR-0038 §"후속 영향" 에 cleanup 완료 cross-link 1줄씩 추가. ADR-0038 §"후속 영향" 추가로 line 74 `Rollback procedure` bullet 삭제 (dead link) + line 73 TELEGRAM_ALERT_* parenthetical stale 갱신.
- **트레이드오프**:
  - pre-v0.1.7 yaml/env 운영자 base 등장 시 (외부 backup 복원, 새 OCI 인스턴스에 옛 자료 이식 등) 본 cleanup 후의 install.sh 는 schema 자동 보강 불가 — 운영자 수동 yaml/env 갱신 필요. 단일 OCI server (메인테이너 자신) 환경 + v0.1.7 정착 가정으로 risk 무시 가능.
  - ADR 본문 (v0.1.0~v0.1.6 era 결정 기록) 은 그대로 — history record 보존. cleanup 은 §"후속 영향" 절에만 명시.
- **결론**: install.sh ~195줄 감소 + `scripts/migrate_layout.sh` 313줄 + `scripts/_helpers/hermes_config_migrate.py` 191줄 파일 삭제 = **약 700줄 감소** (전체 diff stat: 12 files, 42 insertions / 757 deletions). VERSION 0.1.7 → 0.1.8. canary tag 검증 cycle (`docs/agent_dev_guide.md §Step 5 "배포 채널 — canary tag 활용"`) 의 첫 dogfooding — canary 부여 → OCI 검증 → 통과 시 latest promote. v0.1.8 release 진입의 첫 atomic feature. bash syntax 검증 (`bash -n install.sh` pass) + 4 PYEOF Python heredoc ast.parse 통과 + `_migrate_agent_schema` 의 Group B (v0.1.5+ field 자동 추가) + A4 (W_invalid warn) 보존 동작 확인. Step 4 (Review) 멀티 reviewer 수행 — code_review_1 (H1 README §Migration dead reference + M1 wiki-schema tree + M2 caller 주석 stale) + code_review_2 (H1 hermes_config_migrate.py orphan + H2 install.sh:1143 stale + M1 줄수 313 정정 + M2/M3 ADR refs) 모두 흡수. OCI batch 검증은 추후 운영자가 일괄 진행.
- **참조**: features/archive/20260525_legacy_migration_cleanup/

---

## [2026-05-25] canary_channel (v0.1.8 docs)

- **목적**: release 전 OCI 사전 검증 trace 위한 `canary` lightweight tag 운영 절차를 README + agent_dev_guide 에 정본화. v0.1.7 era 까지 latest tag 직행 배포의 risk surface 후 도입.
- **로직**: README §"호출" 의 curl 예시에 `--branch canary` 추가 + §"배포 채널 (tag 운영)" 표 신설 (latest/canary/vX.Y.Z 의미 분리). `docs/agent_dev_guide.md` §Step 5 (Deployment) 끝에 "배포 채널 — canary tag 활용" 절 추가 — 검증 → tag promote → main merge 흐름 5-step 명시.
- **생성 ADR**: 없음 (docs).
- **트레이드오프**: 없음.
- **결론**: docs 단독 commit (79b7a4e). 후속 `branch_strategy_formalize` 의 5-액션 git workflow 메소드론 정립의 base. 첫 dogfooding = `legacy_migration_cleanup` (위 항목).
- **참조**: commit 79b7a4e (archive 없음 — docs 단독).

---

## [2026-05-25] branch_strategy_formalize (v0.1.8)

- **목적**: v0.1.7~v0.1.8 진행 중 main 직접 push + revert 사고 (`4f5f206` + `4b90fc0`) 의 root cause = "버전 단위 통합 지점 미명시 → feature commit 이 곧장 main 으로 흘러감". `main → v0.X.Y → feature` 3-layer branch model + 5-액션 squash workflow 메소드론 정본화. 본 feature 가 본 메소드론의 첫 자기적용.
- **로직**: `CLAUDE.md` §3 Step 5 (Deploy) 와 §6 (Git Worktree) 에 5 액션 표 신설 + `docs/agent_dev_guide.md` §Step 5 본문 갱신. install.sh `F8` fetch 책임에 `--force` 추가 (git 2.20+ 부터 lightweight tag (canary) fetch force 없이는 clobber 거부 — canary force-update 후 운영자 update 시 stale local tag 잔존 risk 차단).
- **생성 ADR**: 없음 (governance 메소드론). 본 메소드론이 v0.1.8 의 모든 후속 feature (wikihub_monitor / lint_operations_improvements / update_path_fixes / install_update_hardening) 의 squash 흐름 base.
- **트레이드오프**: feature 별 worktree 분기 부담 — 단일 에이전트 작업 시 worktree 미사용 허용 (CLAUDE.md §6 의 worktree 필수 조건 = 멀티 패널/서브에이전트). main 직접 commit 금지 → release batch 까지 cumulative trace 가 길어짐 (v0.1.8 = 10 commit).
- **결론**: CLAUDE.md / docs/agent_dev_guide.md / install.sh 3 파일. canary force-update 정합 + 5-액션 squash workflow 운영. v0.1.8 의 모든 후속 feature 가 본 메소드론 첫 dogfooding.
- **참조**: features/archive/20260525_branch_strategy_formalize/

---

## [2026-05-25] wikihub_monitor (v0.1.8)

- **목적**: 운영 OCI 의 12hr 윈도우 종합 진단 보고서 자동 발송 — 운영자가 ssh 없이 매일 09:00 / 21:00 KST 에 Telegram + vault 안 보고서 파일로 ingest/lint cycle 통계 + 결함 surface 받음. 기존 ops-alert.service (fatal trigger) + pending_monitor (age-based stuck detect) 의 보완 layer (정상 cycle 운영 진단).
- **로직**: `scripts/wikihub_monitor.py` 신설 (Python, ~400줄) — systemd journal 정적 파싱 (`journalctl --user -u wikihub-vault@* --since "12 hours ago"` + lint) → success/fail 통계 + error excerpt 추출 + Telegram 발송 (`TELEGRAM_MONITOR_BOT_TOKEN` / `TELEGRAM_MONITOR_CHAT_ID`, ops-alert 와 동일 채널) + 보고서 파일 저장 (`$WIKIHUB_HOME/vault/<vid>/<subpath>/YYYYMMDD__HH_mm.md`, KST). `_system/systemd/wikihub-monitor.{service,timer}.template` 신설 (OnCalendar=`*-*-* 09,21:00:00 Asia/Seoul`, Type=oneshot). yaml `operations.monitor_enabled` / `monitor_report_vault` / `monitor_report_subpath` 3 fields 신설. install.sh systemd unit list 에 wikihub-monitor 추가. D1 정정 (Hermes 스킬 → Python 직접 — `wikihub_monitor` 의 deterministic 통계 작업은 LLM 부적합).
- **생성 ADR**: 없음 (operational layer 확장 — ADR-0037 의 pending_monitor 패턴 follow-up).
- **트레이드오프**: 추가 systemd unit 2건 (service + timer) — render dry-run 검증으로 부담 acceptable. Telegram channel 이 ops-alert 와 동일 → 정상 cycle 보고서 + critical alert 가 한 channel 에 섞임 (운영자 prefix 로 분리 인지). vault 안 보고서 파일 = vault 의 LLM derivative 추가 — graphify wiki 와 다른 카테고리 (운영 메타) 라 카테고리 cross-contamination 없음.
- **결론**: scripts/wikihub_monitor.py 신설 + systemd unit 2건 + yaml 3 fields + install.sh systemd 통합. multipass 검증 — 보고서 파일 정합 + Telegram 발송 정합. 사용자 정책 (test 인스턴스 = mount only) 정합 — monitor.timer enable 안 함 default.
- **참조**: features/archive/20260525_wikihub_monitor/

---

## [2026-05-25] lint_operations_improvements (v0.1.8)

- **목적**: wh-lint cycle 의 운영 안정성 3건 통합 — (I1) timeout 종료 결함 + wh-ingest timeout 정책 검토, (I2) lint report 의 case-variant (`MiniMax` / `minimax`) + cross-category duplicates (entity `Docker` + concept `Docker`) 정책 결정 + 자동 처리, (I3) wh-lint `--apply` 자동 실행 패턴.
- **로직**: 
  1. **ADR-0039 신설 (alias frontmatter)**: entity/concept page frontmatter 에 `aliases: [...]` 필드 신설. case-variant + cross-category 의 LLM 인식 layer — 운영자 manual edit 없이도 lint LLM 이 alias 합쳐서 인지 → 재생성 무한 loop + product noun case 손상 차단.
  2. **`--apply` flag 폐기**: wh-lint 매 cycle (3h timer + 메인테이너 수동 호출) 진단 + 적용 default. wikihub `wiki/` 가 sources (vault, immutable) 의 LLM derivative 라 원본 변경 0 — 자동 적용 risk 무시 가능.
  3. **graphify timeout yaml expose**: `operations.graphify_timeout_sec` 신설 (default 900s = 15분). v0.1.5~v0.1.7 era hard-coded `timeout 720` 을 yaml 으로 격상. 운영자 backend 별 조정 가능.
- **생성 ADR**: ADR-0039 (entity/concept alias frontmatter).
- **트레이드오프**: alias frontmatter 가 entity/concept 페이지의 schema 확장 — 기존 wiki 의 alias 미존재 페이지는 lint cycle 자동 보강 (graphify 가 detect → next lint cycle 에서 page 갱신). `--apply` 폐기 → 운영자가 staging review 안 함 (자동 적용). wikihub 의 자기상태 (`wiki/` = sources derivative) 가정 정합 — risk null.
- **결론**: ADR-0039 신설 + lint.md spec 갱신 (`--apply` 분기 폐기 + alias section) + wikihub.yaml.example operations 1 field + install.sh `_migrate_agent_schema` 자동 추가. multipass 검증 — lint cycle 자동 적용 + alias 동작 정합.
- **참조**: features/archive/20260525_lint_operations_improvements/

---

## [2026-05-25] update_path_fixes (v0.1.8)

- **목적**: multipass `wikihub-test` 의 v0.1.0 → v0.1.8 큰 jump test 에서 surface 한 2 결함 fix. R1 = wh-lint Step 9 의 `<agent_invocation> "/wh-graphify"` 가 silent skip (LLM hallucination — fake `proc_xxx` 응답). R2 = `_migrate_agent_schema` 가 큰 jump 시 yaml 신설 fields 자동 추가 안 됨 (특히 `--yolo` 부재 → hermes dangerous command Denied stuck).
- **로직**: 
  1. **D3 (B) — wh-graphify hermes skill 폐기 + systemd 격상**: Layer 1 LLM wrapper (`wh-graphify` hermes skill) 는 deterministic bash 작업의 over-engineering. `scripts/wikihub_graphify.sh` (bash, backend dispatch 6 case + N/M partial failure 가드) + `wikihub-graphify.service` (Type=oneshot, timer 없음, lint Step 9 trigger) 격상. lint Step 9 가 변경 감지 분기 (Step 3/4.5/5/7 archive 0건이면 skip) → `systemctl --user start wikihub-graphify.service` (fire-and-forget) — cost gate 보존 (변경 없을 때 graphify 실행 안 함). Layer 2 semantic extraction LLM (graphify CLI 내부 ollama_cloud) 유지.
  2. **R2 — `_migrate_agent_schema` yaml.example single-source sync**: 신설 fields 자동 추가 일반화 (yaml.example 의 operations/agent top key 순회 → 운영 yaml 에 부재 키 자동 추가, 운영자 명시 값 보존). `A_yolo_missing` 복원 (oneshot_args 에 `--yolo` 없으면 자동 insert).
- **생성 ADR**: 없음. ADR-0036 §"후속 영향" + ADR-0038 §"후속 영향" 에 cross-link 1줄씩.
- **트레이드오프**: wh-graphify hermes skill 5건 → 4건 (skill 폐기 정합). yaml.example sync 가 set semantics 한계 — `if k not in target` 가 자연 부재 vs 명시 삭제 구분 불가 (운영자가 의도적으로 삭제한 field 도 자동 복원 가능). 단 v0.1.8 의 신설 fields scope 에선 risk 무시 가능.
- **결론**: scripts/wikihub_graphify.sh 신설 (~150줄) + wikihub-graphify.service.template 신설 + lint.md Step 9 spec 변경 + graphify.md spec 격하 (skill 폐기 명시) + install.sh `_migrate_agent_schema` 일반화. multipass 검증 — full cycle (ingest → lint → graphify.service trigger) 정합. release transition 정합 (cecf651 squash + a9f971e docs cleanup).
- **참조**: features/archive/20260525_update_path_fixes/

---

## [2026-05-26] install_update_hardening (v0.1.8)

- **목적**: v0.1.8 canary 검증 (multipass `wikihub-test`) 의 `install.sh --version canary` 가 3회 fix evolution 거쳐 회피 없이 통과. 운영 OCI 첫 update / fresh install 시점에 동일 surface 가능 → release 전 흡수.
- **로직**: install.sh update flow 5 결함 fix.
  1. `.gitignore` 에 `_system/INSTALLED_VERSIONS.json` 추가 (install.sh runtime artifact 가 untracked → update guard L1439 `git status --porcelain` 차단됐던 결함).
  2. `git reset --hard refs/tags/<ref>` 직후 `WIKIHUB_INSTALL_SELF_RESTARTED` guard + `exec "$0" "$@"` self-restart 추가 (bash mid-execution 의 module-level array stale → new source 와 mismatch 됐던 anti-pattern).
  3. `_install_graphify` 진입 직후 `export PATH=$VENV_PATH/bin:$PATH` 추가 (L578 comment 와 실제 동작 불일치 — `command -v graphify` PATH detect fail 됐던 결함).
  4. self-restart 직전 `exec 200>&-` 추가 (lockfix — exec 자식 process 가 부모 fd 200 inherited → `_acquire_install_lock` flock fail).
  5. self-restart 의 `$@` → `${ORIGINAL_ARGS[@]}` (argsfix — `_step2_update()` 함수 scope 에서 `$@` empty → `--version canary` 손실 → latest fallback downgrade).
- **생성 ADR**: 없음. ADR-0030 §"후속 영향" + ADR-0036 §"후속 영향" 에 cross-link 1줄씩.
- **트레이드오프**: self-update anti-pattern fix 의 chicken-and-egg 본질적 한계 — fix 가 deploy 되어도 첫 호출은 부모 process 의 이전 source 동작이 결정. 정합 동작은 다음 호출부터. 운영자 release transition 시 1회 transient fail (rollback) 가능 — 즉시 재호출로 정합화.
- **결론**: install.sh + .gitignore + README + ADR-0030/0036 cross-link. multipass 검증 — 회피 없이 install.sh 통과 + idempotent re-run 정합. canary force-update 4회 거쳐 정합 단일 squash commit (a748d19) 으로 통합.
- **참조**: features/archive/20260526_install_update_hardening/

---

## [2026-05-26] v018-fix (v0.1.9)

- **목적**: v0.1.8 lesson-driven fixes + OCI 운영 중 발견된 sync passthrough 결함 fix.
- **로직**:
  1. **fix(sync)**: `_read_from_mount()` else 브랜치에서 binary MIME(`application/octet-stream`)으로 식별된 text 파일(.md, .txt, .json 등)을 확장자로 판별하여 UTF-8 직접 디코딩 후 passthrough 처리. 디코딩 실패 시에만 extract()로 fallback.
  2. **fix(config)**: `config.py` `lint_interval_hours` 기본값 24→3 (yaml.example 정합)
  3. **fix(review)**: `test_config.py` fixture 24→3, install.sh 들여쓰기 수정
  4. **docs**: v0.1.8 lesson report + OPS 검증 체크리스트 + 멀티모델 리뷰 (MiniMax M2.5, Kimi K2.6, Qwen3.6 plus)
- **생성 ADR**: 없음.
- **트레이드오프**: passthrough는 확장자 heuristic + UTF-8 only (기존 `is_text_mime` 브랜치와 동일한 encoding 정책). 비UTF-8 legacy encoding 파일은 extract() fallback 후 실패 가능. OCI 운영 검증 완료.
- **결론**: 7 commits, 8 files changed (+559 -5). v0.1.9 version bump.
- **참조**: features/archive/20260526_v018_fix/

---

## [2026-05-26] monitor_services_remove (v0.1.9)

- **목적**: v0.1.5 (ADR-0037 §D2) `wikihub-pending-monitor` + v0.1.8 `wikihub-monitor` 폐기. 운영 6주차 시점 두 unit 의 추가 surface 가 ops-alert (ADR-0024) 가 못 잡는 결함을 실제로 잡았다는 evidence 부재 — Karpathy §2 Simplicity 정공법.
- **로직**:
  1. **systemd unit 4종 삭제** — `_system/systemd/wikihub-monitor.{service,timer}.template` + `wikihub-pending-monitor.{service,timer}.template`.
  2. **scripts 3 파일 폐기** — `scripts/wikihub_monitor.py` (470L), `scripts/pending_monitor.py` (110L), `scripts/lib/telegram.py` (80L).
  3. **telegram inline 회수** — `send_telegram` + `format_telegram_alert_message` → `scripts/ops-alert.py` (단일 caller, `parse_mode="HTML"` 고정, 옵션화 제거).
  4. **yaml.example 4 필드 제거** — `pending_alert_age_sec`, `monitor_enabled`, `monitor_report_vault`, `monitor_report_subpath`. `OperationsConfig` dataclass 동일 4 필드 + `_parse_operations` 4 라인 삭제.
  5. **install.sh upgrade migration** — legacy monitor unit stop+disable. `render_systemd_units.py` legacy_singletons catalog 에 monitor 4 unit 추가 (operator 의 `~/.config/systemd/user/` 의 orphan unit 자동 삭제).
  6. **ADR-0037 §Note + ADR-0024 cross-ref + ADR-0032 catalog 정리** — `pending_alert_age_sec` Group B 자동 추가 catalog 자연 제거.
- **생성 ADR**: ADR-0040 (Supersedes ADR-0037)
- **트레이드오프**: pending_ingest age 기반 surface 부재로 회귀 — operator 가 vault sync 실패를 ADR-0024 attempts 기반 alert (50min) 까지 기다림. `TELEGRAM_MONITOR_*` env key 명명이 fatal alert layer 만 남아 의미 부정확 → operator env 마이그레이션 부담 회피 위해 키 이름 유지 (install.sh 주석으로 historical 명시). 12hr 보고서 부재 → operator 가 journalctl 명령으로 자기 운용.
- **결론**: 7 파일 삭제 + 12 파일 수정 (+161 -124). 멀티모델 리뷰 2회 (code_review_1 runtime correctness + code_review_2 consistency) + v2 fix (3 Critical + 5 Medium 결함 surface 후 모두 반영). multipass wikihub-test 검증 통과 — `render ok: removed_stale=6` 정합 (vault@ 2 + monitor 2 + pending-monitor 2).
- **참조**: features/archive/20260526_monitor_services_remove/

---

## [2026-05-26] systemd_prefix_realign (v0.1.9)

- **목적**: commit `2ed01f8` (v0.1.9 release window 의 systemd unit rename — `wikihub-vault@` → `wh-ingest@`, `lint.*` → `wh-lint.*`) 의 명분 (Hermes skill 이름과 통일) 보다 systemd namespace 일관성 (`wikihub-*` 단일) 이 운영자 mental model 에 더 유익. Hermes skill prefix `wh-` (ADR-0033 lock) 와 systemd unit prefix 는 두 다른 abstraction layer — 같은 prefix 강제 의미 부족.
- **로직**:
  1. **systemd template 4 rename** — `wh-ingest@.{service,timer}.template` → `wikihub-ingest@.{service,timer}.template`, `wh-lint.{service,timer}.template` → `wikihub-lint.{service,timer}.template`. 효과적 rename: `wikihub-vault@` (pre-2ed01f8) → `wikihub-ingest@` (semantic) + `lint.*` (no prefix) → `wikihub-lint.*` (namespace).
  2. **Hermes skill `wh-*` 보존** — ADR-0033 lock 정합. ExecStart 의 `hermes chat --skills wh-ingest --quiet --yolo --query "/wh-ingest --vault %i"` 형태 보존. systemd unit layer (`wikihub-*`) ↔ Hermes skill layer (`wh-*`) 명확 분리.
  3. **install.sh upgrade migration 확장** — pre-2ed01f8 era (`wikihub-vault@*` + `lint.*` 잔존) + 2ed01f8 canary era (`wh-ingest@*` + `wh-lint.*` 잔존) 둘 다 stop + disable cleanup.
  4. **renderer 보강** — `_do_render` 의 per-vault regex 를 `wikihub-(?:mount|ingest)@` 패턴으로 갱신 + 별도 unconditional delete 블록 (`wikihub-vault@*` + `wh-ingest@*` template 자체 폐기). `legacy_singletons` 에 `wh-lint.{service,timer}` 추가.
  5. **commands docs + wiki-schema + README + ADR-0040 narrative + ADR-0033 §Note cross-ref** — systemd unit 참조 일괄 갱신, Hermes skill 호출 (`/wh-lint`, `--skills wh-ingest` 등) 보존.
- **생성 ADR**: ADR-0041 (commit `2ed01f8` 정정, ADR 결정 변경 없음 — 직전 implementation-level rename 의 첫 ADR 격상)
- **트레이드오프**: commit `2ed01f8` 의 GLM 5.1 + Mimo 2.5 Pro 멀티모델 리뷰가 `wh-*` 방향 승인 → 직후 maintainer 검토 결과 반전. 리뷰 가치 손상 0 (당시 결정 시점의 정확한 평가) 이나 메소드론 churn cost 인식. legacy_singletons catalog 누적 (pre-2ed01f8 + 2ed01f8 canary + monitor 4 unit = 다층 cleanup) 부담.
- **결론**: 4 template rename + install.sh 21 위치 unit 참조 갱신 + renderer regex + commands docs + ADR-0040 narrative + ADR-0033 §Note. Step 4 review 메인테이너 판단 생략 (mechanical rename + 정적 검증 + 직전 monitor_services_remove 리뷰의 graphify layer 정합 흡수). multipass wikihub-test 검증 통과 — rendered unit 7 종 모두 `wikihub-*` prefix + Hermes skill 호출 정합.
- **참조**: features/archive/20260526_systemd_prefix_realign/

---

## [2026-05-26] graphify_path_absolute (v0.1.9)

- **목적**: OCI 운영 중 발견 — wh-lint cycle 이 stale `$WIKIHUB_HOME/wiki/graphify-out/graph.json` (934 nodes, 826 edges, 2026-05-24 생성, 4.6MB) 을 읽고 0 edges 회귀 보고. 근본 원인 — wh-lint skill (LLM) 의 CWD context 가 wiki/ 로 implicit drift → 상대 경로 `graphify-out/graph.json` 이 `$WIKIHUB_HOME/wiki/graphify-out/` 으로 잘못 resolution.
- **로직**:
  1. **`_system/commands/lint.md` 5 위치 절대 경로** — `graphify-out/graph.json` → `$WIKIHUB_HOME/graphify-out/graph.json`. CWD-independent resolution.
  2. **Step 3 schema 호환** — graphify v0.7 (`edges`) → v0.8+ (`links`) migration: `d.get('links', d.get('edges', []))` 패턴 명시.
  3. **Step 7 stale cleanup** — `wiki/graphify-out/` 존재 감지 시 → `graphify-out/.archived/wiki-graphify-out-<utc>/` 자동 archive 이동 (recoverable, `rm -rf` 금지).
  4. **Step 8 report 보고 형식** — stale cleanup 항목 추가.
  5. **`.graphifyignore` 에 `graphify-out/` 추가** — defense-in-depth (graphify CLI 의 잘못된 `--out` 호출 시 자기 출력 재scan 차단).
  6. **`docs/references/graph-path-resolution.md` 신설 (185L)** — 운영자 진단 가이드 + 정합 경로 catalog + Recovery 절차 + 회귀 차단 4-layer + graphify schema 호환 노트.
- **생성 ADR**: 없음. ADR-0036 §"후속 영향" cross-ref 1줄 add (implementation hardening — 결정 변경 없음).
- **트레이드오프**: Step 7 stale cleanup 가 매 lint cycle 마다 `find $WIKIHUB_HOME/wiki/graphify-out/` 검사 1회 추가 — minimal cost. `.archived/` 누적 retention policy 부재 (v0.2.x 검토 backlog).
- **결론**: lint.md 5 위치 + .graphifyignore template + ADR-0036 §Note + docs/references/graph-path-resolution.md 신설. multipass 검증 통과. Step 4 review 메인테이너 판단 생략 (OCI 실증 trail + 직전 ADR-0036/0040/0041 review 의 graphify layer 정합 흡수).
- **참조**: features/archive/20260526_graphify_path_absolute/

---

## [2026-05-27] graphifyignore_migration (v0.1.9)

- **목적**: graphify_path_absolute (v0.1.9 squash) 의 multipass canary 검증에서 surface 한 결함 — 운영자 `~/wikihub/wiki/.graphifyignore` 가 update 시 자동 갱신 안 됨. `cp -n` (template 배치) 는 fresh install 만 효과, 기존 instance 의 file 은 무변경 → defense-in-depth layer 3 (`graphify-out/` ignore) 가 기존 instance 에 미적용.
- **로직**: `install.sh _migrate_graphifyignore` 신규 — wiki/.graphifyignore 가 존재하면 `^graphify-out/?$` regex 부재 시만 idempotent append. 운영자 customization 보존 (다른 형태 `/graphify-out`, `**/graphify-out/` 미touch). `_step5_instance_dirs` 끝에 hook 추가 — 매 install (update + fresh) 시점 작동. setup.md Step 1 §wiki/.graphifyignore catalog 갱신 + ADR-0036 §"후속 영향" cross-ref.
- **생성 ADR**: 없음. ADR-0036 §"후속 영향" cross-ref 1줄 add.
- **트레이드오프**: regex `^graphify-out/?$` 의 매칭 범위 보수적 — 운영자가 `# graphify-out/` comment-out 형태로 작성한 경우 매칭 안 함 → migration 가 append (중복 가능). 운영자가 의도적 comment-out 했다면 본 line 의 추가는 redundant 이나 idempotent 정합 깨지지 않음.
- **결론**: install.sh 1 fn + setup.md 1 bullet + ADR-0036 §Note 1줄. multipass 검증 통과 — 첫 실행 시 `wiki/.graphifyignore migration: graphify-out/ append (graphify_path_absolute layer 3 회복)` 출력 + 재실행 시 no-op (idempotent).
- **참조**: features/archive/20260527_graphifyignore_migration/ (예정)

## [2026-05-30] v0.1.10 release (통합 기록)

> 다수 feature 묶음 release — 개별 항목은 각 feature 의 `features/archive/...` + ADR 참조. 본 항목은 release 시점 §3.5 backfill (issue #114 — 당시 누락분 소급).

- **목적**: v0.1.9 → v0.1.10 누적 release. 외부 read-only 접근(MCP) + wiki 링크 alias resolve + install/update 경로 hardening + release helper.
- **로직 (주요 묶음)**:
  - **MCP server** (ADR-0043) — `scripts/wikihub_mcp.py` read-only (4 resource + 5 tool), stdio + SSH spawn, `docs/mcp-setup.md`.
  - **alias-aware link resolver** (ADR-0042, issue #37) — lint Step 1.5 alias index.
  - **install/update hardening** — self-restart current_version 보존(#86), per-vault flock(#61), reboot timer enable(#34), mount fallback diagnostic env scrub fix(#29), graphify partial-failure alert(#42).
  - **systemd TimeoutStartSec yaml-driven**(#104), **sidecar cwd fix**(#108), **sidecar uv 탐지**(#109).
  - **deployment helpers** — `scripts/promote_canary.sh` + `release.sh`.
  - **docs** — README 사용자 중심 재작성(#103) + changelog/roadmap 신설 + web-ui-setup(#107 검토) + docs/reviews·reports → features/archive 이관.
- **생성 ADR**: ADR-0042 (alias resolver), ADR-0043 (MCP integration).
- **트레이드오프**: MCP Phase 1 은 stdio+SSH 한정 (SSE/HTTP·write tool 은 Phase 2 deferred). release.sh 는 첫 실사용에서 branch+tag 동일명 push 모호성 발견(#112, v0.1.11 fix).
- **결론**: main merge `fb50872` + annotated tag `v0.1.10` + `latest` (2026-05-30). 운영자 `install.sh --branch latest`. 자세한 사용자 관점 요약은 `docs/changelog.md` v0.1.10 entry.
- **참조**: `docs/changelog.md` [v0.1.10], `docs/adr/0042`·`0043`, features/archive/20260529_mcp_integration/ 등.
|

## [2026-06-05] v0.1.11 release (통합 기록)

> NAS vault 첫 지원 release — SFTP 기반 vault type 확장.

- **목적**: v0.1.10 → v0.1.11 누적 release. Google Drive 외 NAS (SFTP) vault type 지원 + release 프로세스 hardening.
- **로직 (주요 묶음)**:
  - **NAS vault type** (ADR-0044, #117/#125) — `SUPPORTED_VAULT_TYPES` + type별 필수 옵션 검증 + rclone rc port skip + mount 템플릿 분기 (#130) + path 기반 diff (#129) + SFTP remote 생성 (#126).
  - **NAS vault 호환성** — vfs_refresh/OAuth 검사 조건 분기 (#119/#127).
  - **NAS vault 저장 계층** — 저장 위치·권한·백업 구조 ADR-0044 정본화 (#123/#131).
  - **release 프로세스 hardening** — preflight 체크 (#114) + push refspec 명시적 분리 (#112).
- **생성 ADR**: ADR-0044 (NAS vault storage layer).
- **트레이드오프**: NAS vault는 SFTP 기반으로 rclone 의존성 유지. Google Drive vault와 동일한 mount/vfs 계층 사용하나, `vfs/refresh` 및 OAuth 검사는 NAS에서 불필요하여 조건 분기. 향후 NFS/SMB backend는 별도 ADR 필요.
- **결론**: main merge `dbf4dda` + annotated tag `v0.1.11` + `latest` (2026-06-05). 운영자 `install.sh --branch latest`. 자세한 사용자 관점 요약은 `docs/changelog.md` v0.1.11 entry.
- **참조**: `docs/changelog.md` [v0.1.11], `docs/adr/0044`, features/archive/*.