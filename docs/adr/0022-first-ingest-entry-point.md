# ADR-0022: 첫 ingest 진입점 + timer enable 게이트

- **Status**: Accepted
- **Date**: 2026-05-14
- **Feature**: features/20260514_install_runtime
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

install.sh → wikihub.yaml 편집 → credentials scp → `/wh:setup --enable` 의 운영 절차에서 **첫 ingest 의 실행 시점·trigger 책임** 결정 필요. 추가로 v4 의 SRE review (R6-3) 가 finding — 첫 ingest 가 timer enable 후 prompt 면 fatal 시 60초 뒤 systemd 자동 재시도 → fatal loop. 따라서 **timer enable 의 게이트 책임** 도 함께 결정.

## Considered Options

- **(α) E1**: install.sh 마지막에만 prompt — yaml 이 example 상태라 의미 약함.
- **(β) E2**: /wh:setup 마지막에만 prompt — yaml 편집 + credentials scp 완료 후 자연.
- **(γ) E3**: 둘 다 — install.sh 안내 + /wh:setup Step 6 prompt 가 실제 trigger.
- **(δ) E4**: 자동 — /wh:setup 이 첫 ingest 까지 자동 trigger (사용자 통제 없음).

> 옵션 상세는 [features/20260514_install_runtime/analysis_and_design.md §3.5](../../features/20260514_install_runtime/analysis_and_design.md) 참조.

## Decision

**채택**: (γ) E3 + **v4 흐름 역전** (첫 ingest 성공이 timer enable 의 전제).

**흐름 spec** (analysis_and_design.md §3.5 [E] + §4.4 정본):

1. `/wh:setup --enable` 호출 → Step 1~4 (yaml 검증 + state + agent skill + unit 파일 작성 + daemon-reload). **timer enable 안 함**.
2. Step 5 (보고) 후 **Step 6**: vault 별 prompt — "첫 ingest 를 지금 실행하시겠습니까? [Y/n]".
3. `Y` 응답 + `vault-fetch.py --vault <id> --bootstrap` 실행 후 exit code 분기:
   - exit 0: timer enable + bootstrap_allowed false 환원.
   - exit 75 + cursor 존재: timer enable + bootstrap_allowed false 환원 + 다음 사이클 재시도 안내.
   - exit 75 + cursor 미생성: timer enable **보류** + 사용자 안내 (fatal loop 회피).
   - exit 2: timer enable 보류 + last_failure.json 영속화 (ADR-0024 정합) + 사용자 안내.
4. `N` 응답: vault-fetch + timer enable 모두 skip.
5. lint.timer / disk-watch.timer 는 vault 와 독립적으로 항상 enable.

**비대화 모드**: `--run-first-ingest` / `--skip-first-ingest` flag, `WIKIHUB_FIRST_INGEST=yes/no` env, `/dev/tty` 부재 시 default `Y`.

**bootstrap_allowed 환원 책임**: `/wh:setup` 의 yaml writer (ADR-0009 setup 책임 확장). atomic write + fsync.

**이유**:
- E1 은 yaml 이 example 시점이라 의미 부재.
- E4 는 사용자 통제 약화.
- E2 는 install.sh 의 안내가 운영자 흐름에서 자연 — E3 가 두 진입점의 역할 명확.
- **흐름 역전 (R6-3 fix)**: timer enable 후 prompt 면 첫 ingest 가 fatal 시 systemd 가 60초 뒤 자동 재시도 → 매 사이클 fatal 반복 + ops-alert alarm fatigue. 첫 ingest 성공 후 enable 면 fatal vault 는 운영자 진단 + 수동 enable 흐름으로 분리.

## Consequences

- **긍정**: 첫 ingest 실패 시 timer enable 자동 차단 — alarm fatigue 회피. bootstrap_allowed 자동 환원으로 운영자 수동 yaml 편집 불필요.
- **부정/제약**: timer enable 보류된 vault 는 운영자가 수동 enable 필요. 운영자 인지 메커니즘 = `/wh:setup` 의 보고 stdout 만 (v0.1.0 단계).
- **후속 영향**:
  - F2 `_system/commands/setup.md` 갱신 필수 — Step 4 의 `--enable` 동작 변경 + Step 6 신설 + 출력 산출물 / 실패 처리 표 보강.
  - `/wh:setup` 이 wikihub.yaml 을 atomic write 하는 새 책임 — `scripts/lib/config.py` 에 writer helper 추가 필요.
  - V13 verification 이 회귀 방지 (시나리오 6개 — Y exit 0 / 75 with cursor / 75 without cursor / 2 / N / 비대화).
  - v0.2.x 에서 Hermes 채널 활성화 시 timer enable 보류 안내가 Telegram 으로 전달 (ADR-0024 의 notify_via_hermes 활성화).
