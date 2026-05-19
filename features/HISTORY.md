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

- **목적**: ADR-0036 §D2 (2026-05-19) 의 default `ANTHROPIC_API_KEY` backend lock 이 OCI 운영자 비용 모델에 misaligned — 별도 Anthropic API key 발급 의사 없음 + Hermes 측에 OpenCode-go (`https://opencode.ai/zen/go/v1`) 의 `deepseek-v4-pro` API key 이미 설정. backend 선택 layer 보강 + lint Step 9 의 graphify hang 가드 추가.
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


- **참조**: features/archive/20260519_graphify_integration/ + features/archive/20260519_graphify_usage_review/
