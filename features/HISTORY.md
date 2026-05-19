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
