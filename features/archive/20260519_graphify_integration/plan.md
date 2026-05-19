# Plan — graphify_integration

- **작업 분류**: 기능 (외부 도구 통합 + 신규 ADR + 인프라/스크립트/문서 동시 변경)
- **적용 단계 선언**:
  - Step 1 (Plan): 본 문서
  - Step 2 (Analysis & Design): 수행 — `analysis_and_design.md` + ADR-0036 신설
  - Step 3 (Implementation): 수행 — install.sh + yaml + systemd + render helper + commands docs + ignore template
  - **Step 4 (Review): 생략** — 단일 의도 (graphify CLI integration plumbing). 외부 인터페이스 변경 있음 (`operations.graphify_*`, env file path) 이나 v0.1.0 미배포 단계 — 운영자 base 없음. self-review.
  - Step 5 (Deployment): 수행 — `_system/` + install.sh + scripts 동시 변경. v0.1.3 → v0.1.4. HISTORY 항목 추가.
- **예상 영향 범위**:
  - `install.sh` — `_install_graphify` 함수 + `_step5_instance_dirs` 의 `~/.config/wikihub/{,env}` ensure + `_write_installed_versions_sidecar` 의 graphify key + `_step8_guide` 안내 (API key 운영자 입력)
  - `wikihub.yaml.example` — `operations.graphify_min_version` / `graphify_max_version` / `graphify_api_key_env_name` 신설
  - `_system/systemd/lint.service.template` — `EnvironmentFile=-%h/.config/wikihub/env` (lenient prefix)
  - `_system/commands/graphify.md` — 잠정 4항목 확정 (PyPI 패키지명, MIN_GRAPHIFY_VERSION, CLI 형태 `<path> --update`, `.graphifyignore` 정책, deterministic 가정 §Note)
  - `_system/commands/setup.md` — Step 0 entry condition + maintainer field catalog + 운영 비용 환기
  - `scripts/_helpers/render_systemd_units.py` — graphify version validation + lint template 의 EnvironmentFile placeholder 처리 필요 시
  - `wiki/.graphifyignore` (template) — install.sh 또는 wh-setup 의 wiki/ ensure 단계가 배치
  - `docs/adr/0036-graphify-cli-integration.md` (신규)
  - `docs/adr/0005-wiki-index-vs-graphify.md` (§Note 추가 — 잠정 → 확정 갱신)
  - `docs/adr/0023-install-script-distribution-curl-pipe.md` (§Note 추가 — graphify install.sh 책임 명시)
  - `docs/adr/README.md` — index 갱신
  - `features/HISTORY.md` — 항목 append
  - `_system/VERSION` — 0.1.3 → 0.1.4
- **메소드론 적용 여부**: 적용. 외부 도구 + LLM 비용 모델 + 보안 자료 (API key) 도입 → ADR 신설 정합.

## 배경 (한 문장)

graphify.net 의 graphify CLI 가 wikihub 의 `_system/commands/graphify.md` 가 처음부터 가정한 그 도구 (출력 디렉토리·파일 이름·CLI 시그니처 정확 일치) 임을 2026-05-19 검토로 확정. install.sh 가 실제로 설치 안 함 → wh-lint Step 9 chain 호출 시 `command -v graphify` false → 매 사이클 Fatal + ops-alert 발화 결함. 또한 graphify Pass 3 의 LLM 호출 (Anthropic/OpenAI API) 이 wikihub 운영에 새 비용 모델 + 보안 자료 (API key) 도입 → ADR 신설 필요.
