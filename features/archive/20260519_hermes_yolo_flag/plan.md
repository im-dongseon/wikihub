# Plan — hermes_yolo_flag

- **작업 분류**: 운영 (install.sh + yaml schema agent.oneshot_args 단순 plumbing)
- **적용 단계 선언**:
  - Step 1 (Plan): 본 문서
  - Step 2 (Analysis & Design): 수행 (간소)
  - Step 3 (Implementation): 수행 — 4파일 미만 small change
  - **Step 4 (Review): 생략** — 단일 의도 (Hermes `--yolo` flag 통일 주입), 외부 인터페이스 의미 변경 없음 (수정된 oneshot_args 는 v0.1.2 yaml.example 의 form 에서 단일 인자 추가)
  - Step 5 (Deployment): 수행 — `_system/` 미변경이나 systemd unit render 결과 변경 + install.sh 변경 → v0.1.3 patch bump + HISTORY 항목
- **예상 영향 범위**:
  - `wikihub.yaml.example` — `agent.oneshot_args` 에 `"--yolo"` 추가
  - `install.sh` — (1) F5 migration code 의 default oneshot_args literal 갱신, (2) `_step8_wh_setup_skill_meta` 의 직접 호출 cmdline 에 `--yolo` 추가
  - `scripts/_helpers/render_systemd_units.py` — fail-fast hint message 의 oneshot_args 권장 form 갱신 (역할: 운영자 디버깅 안내)
- **메소드론 적용 여부**: 적용. 의미적으로는 trivial 한 toggle 이나 yaml schema (agent.oneshot_args) 표준 form 변경 + install.sh 자동 호출 동작 변경 → ADR-0032 sub-3 (agent invocation) 후행 정합 보강 필요.

## 배경 (한 문장)

Hermes 0.x 의 보안 승인 layer (tirith) 가 `hermes chat` 안에서 발생하는 inline python / shell 호출을 차단 — `wh-setup` playbook 의 yaml 검증·상태 확인이 Python 인라인 스크립트로 동작하기 때문에 install.sh 의 post-install `hermes chat --skills wh-setup --quiet --query "/wh-setup"` 가 `Choice [o/s/D]: ✗ Denied` 로 중단. `--yolo` flag 가 Hermes 의 non-interactive auto-approve 모드 — install.sh 자동 실행 + systemd timer 호출 모두 동일하게 필요.
