# Design Review 1 — migration_prompt_review (architectural/safety)

- **Reviewer**: subagent (general-purpose, architectural/safety perspective)
- **Date**: 2026-05-20

## 종합 평가

4 옵션 모두 동일 root cause (PTY-bearing subprocess 가 `[[ -t 0 ]]` 를 신뢰할 수 없게 만든다) 를 다루지만 **safety/idempotency 의 spectrum 이 극단 사이에서 진동**한다. (1)·(2) 는 "tty 신호 자체를 폐기" 진영, (3)·(4) 는 "tty 가 거짓일 때 default 의 의미만 뒤집어 회복" 진영. context.md 가 강조한 transformation 자체 속성 (idempotent / 부분 / backup) 을 함께 보면 prompt 의 정보가치는 이미 낮음 — 운영자 의도 보호는 prompt 의 timing 이 아니라 **명시적 opt-out surface** 에 옮기는 게 안전. 따라서 운영자 escape hatch 를 분리한 (2) 가 architectural 정합이 가장 깨끗하다. (3)·(4) 는 prompt UX 를 살리려는 절충안이지만 PTY/cron/Hermes 라는 4 환경 매트릭스에 대해 각각 다른 mental model 을 강제한다.

## 옵션별 평가

### (1) prompt 제거 + 항상 auto-proceed
- **Safety**: backup + idempotent transformation 이 이미 존재 → silent transformation 위험은 운영자가 `--yolo` 를 의도적으로 제거한 시나리오 한정. 그 시나리오에 대한 surface 가 0 — 의도 override 가 무력화된다.
- **Idempotency**: drift 미존재 시 no-op 이므로 동일. ★
- **Risk**: 운영자 yaml 편집이 정본 spec 과 의도적으로 divergent 한 경우, 매 호출마다 rollback. 운영자 mental model 에 "install.sh 는 yaml 도 own 한다" 가 silent 으로 incrust.

### (2) prompt 제거 + `WIKIHUB_SKIP_MIGRATION=1` opt-out
- **Safety**: (1) 의 safety profile + 운영자 의도 escape hatch. backup 도 그대로 유지. F5 ADR-0032 §sub-4 의 "noninteractive 동의 surface" 패턴과 정합 (`WIKIHUB_NONINTERACTIVE` 가 외부 자산 동의 포함하는 단일 toggle 정합).
- **Idempotency**: env 의 의미가 명시적 → CI/Hermes/cron 모두 동일 결과 결정. ★
- **Risk**: 운영자가 env 를 잊으면 (1) 과 동일 결과로 회귀 — 이건 risk 라기보다 **default 의 의식적 채택**. 새 env 변수 1개는 surface area 추가지만 `WIKIHUB_NONINTERACTIVE` 와 의미적으로 분리 (skip ≠ noninteractive) 하므로 over-engineering 아님.

### (3) prompt 유지 + default Y flip
- **Safety**: empty input → Y 라 Hermes/CI/pipe 모두 자동 진행. 단 운영자가 의식적 N 입력 외엔 prompt UX 가 사실상 noise (Y 가 default 라 운영자 학습 가치 ≒ 0).
- **Idempotency**: 환경별 (PTY/non-PTY) 분기 유지 → 4 환경 매트릭스 가운데 PTY-with-non-tty-controller (Hermes) 에서 prompt 가 보이지만 응답자가 없다 → 빈 입력 fast-path 의존. read 가 0 byte EOF 가 아닌 newline 만 받는 경우도 default Y 라 안전.
- **Risk**: **tty 거짓 양성 의존**. 운영자가 `bash install.sh < /dev/null` 또는 redirected input 으로 호출 시 빈 입력 → Y → 의도 미반영 진행. typo `n` (실수) 1회로 운영자 의도가 강제로 보존되는 reverse 시나리오도 위험. 운영자가 한번 `n` 를 잘못 누르면 `--yolo` 가 영구 미반영.

### (4) prompt 유지 + `read -t 5` + default Y
- **Safety**: (3) 와 동일 risk profile + 5초 reaction window.
- **Idempotency**: 5초 timing window 가 환경 부하 (loaded CI, slow PTY relay) 에 따라 비결정. 동일 install 이 환경에 따라 prompt 결과가 달라질 수 있음 → idempotency violation.
- **Risk**: install.sh 가 `--update` 흐름 (ADR-0030 의 trap rollback 포함) 안에서 5초 delay 누적 → systemd stop window (vault@.service 15min grace) 와 race 는 없지만 운영자 mental model 에 "install.sh 가 가끔 멈춘다" 가 incrust. `read -t` Bash 4+ 의존성 (OCI Ubuntu 22.04 는 OK 지만 macOS 메인테이너 box 의 default `/bin/bash` 는 3.2 — shebang `#!/usr/bin/env bash` 로 회피되지만 가정 추가).

## Strict Ranking

**(2) > (1) >> (3) > (4)**

- **(2)** — 운영자 의도 surface 와 환경 정합 모두 충족. simplicity + escape hatch.
- **(1)** — simplicity 극대화. 단 의도 override 시나리오 zero-surface 가 v0.2.x release window 에 운영자 컴플레인 surface 시 (3) 으로 reverse migration 필요 → 사전 차단이 합리.
- **(3)** — prompt 의 학습 가치 의도는 좋으나 default Y 가 그 가치를 무력화. tty 신호 거짓 양성 위험 잔존.
- **(4)** — 5초 delay 가 update path 의 매 호출 누적 + 비결정성 + Bash 4+ 가정. over-engineering.

## Hidden risk / 향후 변경 트리거

- **(1)/(2)**: graphify·rclone 외 추가 외부 도구 통합 시 yaml schema 가 더 자주 lift 됨 → 자동 migration 빈도 증가. backup retention 정책 (현재 hermes config 만 7일) 을 yaml backup 에도 확장 필요 (ADR-0032 §sub-4 패턴 차용). v0.2.x trigger.
- **(2)**: opt-out env 가 늘면 (`SKIP_MIGRATION`·`NONINTERACTIVE`·`SKIP_SYSTEMD` 등) toggle 매트릭스 폭증 → README + `install.sh -h` 의 env 목록 정본화 필요.
- **(3)/(4)**: Hermes 가 PTY 동작 변경 시 (e.g. tty 비할당 모드 도입) prompt 가 다시 잘 동작하나, 그게 발견될 무렵 (2) 도입 비용은 동일 — 즉 (3)/(4) 는 일시적 절충.
- **공통**: `_migrate_agent_schema` 가 "F5 form + `--yolo` 누락" 처럼 점진적으로 sub-rule 이 늘고 있음. v0.2.x 의 다른 lift 추가 시 본 함수가 multi-step migration 으로 성장 → backup-per-step 또는 marker (`_system/MIGRATIONS` ledger) 도입 트리거.

## 권장

**채택 = (2) prompt 제거 + `WIKIHUB_SKIP_MIGRATION=1` opt-out**.

부수 권장:
- **`WIKIHUB_DRY_RUN=1` 변형** 추가 검토 — drift 만 report 하고 transform skip (운영자가 backup 없이 변경 미리보기). v0.2.x 트리거로 등록하되 본 fix 와 atomic change (§8) 정합 위해 분리.
- **로그 가시화**: backup path + diff summary (skill_prefix wh:→wh-, `--yolo` insert at idx N) 를 stderr 한 줄로 출력. 운영자 사후 trace 보장.
- **README/`install.sh -h`** 에 `WIKIHUB_SKIP_MIGRATION` 명시 — ADR-0023 §safety guard 의 운영자 mental model layer 와 정합. README/ADR cross-link 는 별도 trivial change 로 분리.
- **Atomic Change (§8) 정합**: 본 fix 의 단일 목적 = "PTY 환경에서 migration 동작 정합화". (2) 의 env 추가가 이 목적의 일부 (escape hatch) 인지 별도 목적인지 논쟁 여지 있으나, README 갱신·log 가시화·DRY_RUN 도입은 모두 별도 feature 로 분리 권장. 본 PR 은 prompt 분기 제거 + env opt-out 2 점만 포함.
