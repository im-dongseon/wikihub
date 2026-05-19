# Plan — rclone_remote_path

- **작업 분류**: 기능 (yaml schema 보강 + dead config 제거 + systemd template 변경)
- **적용 단계 선언**:
  - Step 1 (Plan): 본 문서
  - Step 2 (Analysis & Design): 수행 — yaml schema·코드·systemd·문서 동시 변경 + ADR-0035 §Note 추가 필요
  - Step 3 (Implementation): 수행
  - **Step 4 (Review): 생략** — 변경은 다중 파일이나 단일 vault scope 명시 동기화. 외부 인터페이스 변화(yaml schema): `root_folder_id` 폐기 + `rclone_remote_path` 신설 — 단 v0.1.0 미운영 (운영자 base 없음). self-review 로 대체. 사유 plan.md 명시로 추적성 확보.
  - Step 5 (Deployment): 수행 — `_system/` + scripts 변경. HISTORY 항목 추가.
- **예상 영향 범위**:
  - `wikihub.yaml.example` — schema 갱신
  - `scripts/lib/rclone.py` — `lsjson(path=...)` 인자
  - `scripts/lib/sync.py` — remote_path 전달
  - `scripts/lib/mount_diff.py` — root_folder_id 주석 정리
  - `scripts/_helpers/render_systemd_units.py` — `remote_path_for_<vid>` 추가
  - `_system/systemd/wikihub-mount@.service.template` — ExecStartPre mkdir + ExecStart spec
  - `_system/commands/setup.md` — derived fields catalog
  - `_system/wiki-schema.md` — trust boundary 표
  - `docs/adr/0035-rclone-only-unified-oauth.md` — §Note 추가
  - `docs/adr/0027`, `docs/adr/0031` — root_folder_id 언급 정리 (역사 보존 + 갱신 Note)
  - tests — lsjson signature change 반영
- **메소드론 적용 여부**: 적용. 멀티파일 schema·인터페이스 변경.

## OCI 실증 결함 (한 문장 요약)

`rclone_remote_name` 단일 필드로는 `mount` 와 `lsjson` 모두 `<remote>:` (Drive 루트) scope 만 표현 가능 — user 가 OCI 에서 `gdrive:wikihub` sub-path mount 운영하려면 schema 보강 필요. 추가로 ADR-0035 가 SA 폐기 + mount root 자체를 trust boundary 로 격상했는데 SA 시절 trust boundary narrow 용 `root_folder_id` 필드가 yaml.example 에 dead config 로 잔존 — 폐기.
