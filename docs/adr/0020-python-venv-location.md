# ADR-0020: Python venv 위치 — `~/.local/share/wikihub/venv`

- **Status**: Accepted
- **Date**: 2026-05-14
- **Feature**: features/20260514_install_runtime
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

wikihub 의 Python 런타임 환경 (vault-fetch.py 의존성 — gws SDK 호환, pdfminer.six, python-pptx, python-docx, openpyxl, PyYAML) 을 격리하기 위해 venv 필요. venv 위치 미정 시 install.sh 가 임의 결정 → 운영 일관성 저해.

ADR-0021 의 reboot resilience 전략 (user-level systemd + linger) 과 결합 필요 — system-level 채택 시 `/opt/wikihub/venv` 가 자연, user-level 시 `~` 가 자연.

## Considered Options

- **(α) C1**: `~/.local/share/wikihub/venv` (XDG_DATA_HOME 표준).
- **(β) C2**: `/opt/wikihub/venv` (system-level path).
- **(γ) C3**: `~/wikihub/venv` (사용자 home 직속).

> 옵션 상세는 [features/20260514_install_runtime/analysis_and_design.md §3.3](../../features/20260514_install_runtime/analysis_and_design.md) 참조.

## Decision

**채택**: (α) C1 — `~/.local/share/wikihub/venv`.

**경로 책임 분할**:
- repo (`~/wikihub`) — git 관리 (ADR-0023 의 clean install 대상).
- venv (`~/.local/share/wikihub/venv`) — install.sh 관리 (사용자 미관여).
- gws binary (`~/.local/bin/gws`) — install.sh 관리 (ADR-0015).
- 운영 state (`~/wikihub-instance`) — 메인테이너 편집 영역.

**이유**:
- ADR-0021 의 D1 (user-level systemd + linger) 채택과 정합 — venv 도 user-level path.
- XDG_DATA_HOME 표준 준수 — 메인테이너 dev box (macOS) 와 운영 서버 (Linux) 둘 다 호환.
- C2 (system-level) 는 install.sh 의 sudo 노출 면적 증가 — D2 fallback 시점에만 채택.
- C3 (`~/wikihub/venv`) 는 venv 가 repo 안에 있어 ADR-0023 의 clean install 시 매번 wipe → 재구성 비용.

**venv path 사이드카**: install.sh Step 3 가 `~/wikihub/.venv_path` 에 절대 경로 기록. /wh:setup 의 Python helper 가 systemd unit substitution 시 read.

## Consequences

- **긍정**: XDG 표준 + 메인테이너 user 의 home 안에 격리. repo wipe 와 무관.
- **부정/제약**: ADR-0021 의 D2 (system-level + service user) 로 fallback 시 venv 위치도 이전 (`/opt/wikihub/venv`) 필요 → 마이그레이션 절차 ADR-0021 본문에 명시.
- **후속 영향**:
  - install.sh 의 deps 갱신은 매 호출 `pip install -r requirements.txt --upgrade` — venv 자체는 idempotent skip.
  - venv 손상 시 운영자 수동 복구 절차: `rm -rf ~/.local/share/wikihub/venv && install.sh` 재호출.

## Note (2026-05-19, feature `dir_layout_refactor`) — §Decision 갱신 (ADR-0034)

XDG `~/.local/share/wikihub/` root 공유:

| dir | 책임 | ADR |
|---|---|---|
| `~/.local/share/wikihub/venv/` | Python venv (uv 관리) | ADR-0020 (현행) |
| `~/.local/share/wikihub/src/` | 시스템 코드 (git clone) | ADR-0034 (신규) |

venv 위치 변경 없음. `WIKIHUB_SRC` env 가 src 부분만 override 가능 — venv 도 동일 root override 시 운영자 명시 설정.
