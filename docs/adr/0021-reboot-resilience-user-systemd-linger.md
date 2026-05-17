# ADR-0021: reboot resilience — user-level systemd + loginctl enable-linger

- **Status**: Accepted
- **Date**: 2026-05-14
- **Feature**: features/20260514_install_runtime
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

wikihub 의 **v0.1.0 acceptance invariant**: OS reboot 후 사람 개입 없이 sync 사이클 자동 재기동. OCI ARM Ubuntu 의 maintenance reboot · unexpected power-off · host migration 모두 cover 해야 함.

systemd 의 운영 모델 선택지: (i) user-level unit + `loginctl enable-linger`, (ii) system-level unit + dedicated service user, (iii) system-level + 메인테이너 user. 각각 권한 모델 · sudo 비용 · F1/F2 정합 trade-off.

## Considered Options

- **(α) D1**: user-level unit (`~/.config/systemd/user/`) + `loginctl enable-linger <user>` + timer `Persistent=true`.
- **(β) D2**: system-level unit (`/etc/systemd/system/`) + `useradd --system wikihub`.
- **(γ) D3**: system-level unit + 메인테이너 user 직접 (별도 user 없음).

> 옵션 상세는 [features/20260514_install_runtime/analysis_and_design.md §3.4](../../features/20260514_install_runtime/analysis_and_design.md) 참조.

## Decision

**채택**: (α) D1 — user-level systemd + linger + Persistent=true.

**서비스·timer spec** (F1 archive §4.8.2 surgical lift — analysis_and_design.md §4.2 참조):
- service: `Type=oneshot`, `Restart=` 미설정, `SuccessExitStatus=0 75`, `TimeoutStartSec=15min`, `OnFailure=ops-alert.service` (ADR-0024 정합).
- timer: `OnBootSec=2min`, `OnUnitInactiveSec={sync_interval_sec}s`, `Persistent=true`, `AccuracySec=1min`.
- install.sh 가 `sudo loginctl enable-linger $USER` 1회 호출 (idempotent skip 검증 후).

**이유**:
- F1 archive §4.1.2·§4.8.2 의 `systemctl --user` 명시와 정합 — F4 가 F1 spec 의 implementation.
- D2 의 dedicated service user 는 install.sh 의 sudo 노출 증가 (useradd, /etc/systemd/system/ write, credentials owner 변경) — v0.1.0 의 1인 운영에서 비용 > 가치.
- D3 는 system-level + 메인테이너 user 조합으로 권한 모델 모호.
- linger 활성화는 sudo 1회 필요 — 다른 옵션도 sudo 비용 회피 불가 (D2 는 더 많은 sudo).

## Consequences

- **긍정**: F1·F2 정합. 권한 격리 자연 (메인테이너 user 의 home 내 모든 state). install.sh 가 root 없이 venv·gws·unit·credentials 모두 관리. timer `Persistent=true` 가 reboot 중 놓친 fire 부팅 후 catch up.
- **부정/제약**:
  - linger 활성화 누락 시 user manager 가 logout 시점에 종료 → V12 의 acceptance 깨짐. V12 가 검증.
  - sudo 1회 필요 (`loginctl enable-linger`). `--skip-confirm` 모드면 NOPASSWD 요구.
  - exit 2 (Fatal) 후 매 timer 사이클에서 같은 fatal 재시도 — ops-alert.service (ADR-0024) 가 통지 + dedup.
- **후속 영향 / V12 fail 시 fallback 절차 (D2 회귀)**:
  1. `useradd --system wikihub` (sudo).
  2. `/etc/systemd/system/` 으로 unit template 이전.
  3. `wikihub.yaml` 의 instance.root + venv 위치를 service user home 으로 이전 (ADR-0020 supersede).
  4. credentials 파일 owner 변경 + chmod 600 유지 (F3 `assert_credentials` 정합).
  5. `/wh:setup` 호출 방식 변경: `sudo -u wikihub <agent> "/wh:setup"`.
  6. ADR-0021 Status → Superseded + 신규 ADR (예: ADR-XXXX `Supersedes: ADR-0021`) 발의.
  - V12 검증 환경: **OCI ARM Ubuntu 인스턴스 (macOS dev box 검증 불가 — systemd 부재)**.
