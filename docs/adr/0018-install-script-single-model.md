# ADR-0018: install.sh 단일 모델 (deploy.sh 미존재)

- **Status**: Accepted
- **Date**: 2026-05-14
- **Feature**: features/20260514_install_runtime
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

CLAUDE.md §3 Step 5 가 `deploy.sh` 를 언급하지만 repo 에 실제 파일 부재. wikihub v0.1.0 의 운영 갱신 절차 — 메인테이너 dev box 에서 `git push` → 운영 서버에서 update — 를 어떻게 구현할지 결정 필요.

F2 setup.md 가 이미 install.sh ↔ /wh:setup 책임 분할을 명문화 (ADR-0010) — install.sh 의 책임에 "정본 update" 가 포함. 즉 별도 deploy.sh 없이 install.sh 가 update 흐름 흡수 가능.

## Considered Options

- **(α) A1**: install.sh 단일 — deploy.sh 만들지 않음. update 도 install.sh 가 흡수.
- **(β) A2**: install.sh + deploy.sh 분리 — install.sh 1회 bootstrap, deploy.sh 가 update (rsync + restart).
- **(γ) A3**: deploy.sh 만 — install.sh 없이 deploy.sh 가 OS deps 까지 모두 처리.

> 옵션 상세는 [features/20260514_install_runtime/analysis_and_design.md §3.1](../../features/20260514_install_runtime/analysis_and_design.md) 참조.

## Decision

**채택**: (α) A1 — install.sh 단일.

**호출 흐름**: 메인테이너 dev box `git push` → 운영 서버 `curl -fsSL <URL>/install.sh | bash` (ADR-0023 의 curl-pipe 모델). update 도 동일 명령.

**이유**:
- v0.1.0 의 메인테이너 1명 + 운영 서버 1대 환경에서 별도 deploy.sh 가치 낮음. update 절차는 git pull 수준이라 install.sh 가 흡수 가능.
- F2 setup.md L23 "install.sh 가 1회 bootstrap + 정본 update" 명문화와 일치.
- A2 의 분리는 운영자 step 수 증가 (`install.sh` vs `deploy.sh` 구분 부담) — 1인 운영에서 가치 < 비용.
- A3 는 신규 설치와 update 의 의미 차이를 흐리며, install.sh 라는 표준 명명에서 벗어남.

**CLAUDE.md 의 "deploy.sh" 표현**: v0.1.0 에서는 install.sh 로 lift 해서 읽음. v0.2.x 에서 분리 필요 시 ADR supersede.

## Consequences

- **긍정**: 운영 절차 단일. 메인테이너 학습 비용 최소.
- **부정/제약**: update 의 incremental 갱신 (rsync delta) 불가 — 매 호출이 clean install (ADR-0023). 단 wikihub repo 가 작아서 network/disk 비용 미미.
- **후속 영향**:
  - 호출 모델은 ADR-0023 (curl-pipe + clean install + safety guard) 가 정본.
  - 운영 서버 다수화 (v0.2.x 의 multi-instance) 진입 시 본 ADR 재검토 — deploy.sh 또는 별도 orchestration 필요 가능성.
