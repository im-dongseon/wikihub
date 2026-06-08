# Plan — wh_skills_env_cleanup

- **작업 분류**: 운영 (skill frontmatter 메타 정리)
- **적용 단계 선언**:
  - Step 1 (Plan): 수행 (본 문서)
  - Step 2 (Analysis & Design): 수행 — 결정 단순하나 ADR-0009 정합 검토 명시
  - Step 3 (Implementation): 수행 — 5개 yaml 파일 동일 패턴 edit
  - **Step 4 (Review): 생략** — 사유: 단일 디렉토리(`_system/skills/`) 내 5파일·총 25줄 이하 cleanup, 외부 인터페이스(스키마/명령어 의미론) 미변경. CLAUDE.md §3 Step 4 생략 조건 3항목 모두 충족.
  - Step 5 (Deployment): 수행 — `_system/` 변경이므로 install.sh 다음 갱신 시 OCI 로 전파. HISTORY.md 항목 추가.
- **예상 영향 범위**:
  - `_system/skills/wh-{setup,ingest,query,lint,graphify}.frontmatter.yaml` — frontmatter 의 `metadata.config.wikihub_home_required` + `required_environment_variables` 블록 제거.
  - ADR 변경 없음 (ADR-0009 에 frontmatter 관련 결정 부재).
  - 코드 영향 없음 (Hermes 가 frontmatter 의 해당 블록 부재 시 secure prompt 트리거 안 함, skill 동작 자체 불변).
- **메소드론 적용 여부**: 적용. trivial 후보지만 5파일 동시 변경 + `_system/` 영속 자산 변경이므로 절차 적용.

## 배경 (한 문장)

`required_environment_variables` 프론트매터는 Hermes 의 secret-on-load (API key/token) 용 메커니즘인데, WIKIHUB_HOME/WIKIHUB_INSTANCE_ROOT 는 install.sh 의 shell rc + systemd unit `Environment=` directive 로 이미 process env 에 주입되는 **path 상수** — secret 아님. 잘못된 layer 선언으로 macOS 메인테이너 세션에서 false prompt + Hermes secret-store 에 path 상수 등록되는 부작용 발생.

자세한 진단·근거는 `analysis_and_design.md` 참조.
