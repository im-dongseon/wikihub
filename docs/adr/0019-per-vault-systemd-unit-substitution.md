# ADR-0019: per-vault systemd unit (file substitution + Python helper)

- **Status**: Accepted
- **Date**: 2026-05-14
- **Feature**: features/20260514_install_runtime
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

F2 setup.md 가 systemd unit 이름을 `{vault_id}-ingest.service` 로 명시 (L48) 했지만, 다중 vault 의 unit 관리 패턴은 두 옵션 — (B1) systemd instantiated template (`wikihub-vault@.service`) 또는 (B2) per-vault 별 separate file substitution. v0.1.0 의 단순성 vs v0.2.x 의 확장성 trade-off 결정 필요.

또한 unit template 의 placeholder 치환 엔진 (envsubst / sed / Python helper) 결정 부재 — substitution 시 escape 부담 vs 안전성.

## Considered Options

**Unit 패턴**:
- **(α) B1**: instantiated template — `wikihub-vault@.service` + `.timer`. 단일 template, 다중 vault.
- **(β) B2**: per-vault file substitution — `_system/systemd/vault-ingest.{service,timer}.template` 가 정본, /wh:setup 이 vault 마다 substitution 결과를 `~/.config/systemd/user/` 에 작성.

**Substitution 엔진**:
- **(i) envsubst** (POSIX coreutils) — shell variable 만.
- **(ii) sed** — 정규식 escape 부담.
- **(iii) Python helper** — yaml 직접 load + `string.Template` substitution.

> 옵션 상세는 [features/20260514_install_runtime/analysis_and_design.md §3.2](../../features/20260514_install_runtime/analysis_and_design.md) 참조.

## Decision

**채택**: (β) B2 (per-vault file substitution) + (iii) Python helper.

**Substitution 변수 목록** (F2 setup.md L54~60 + v5 추가 3건):
- `{vault_id}` / `{sync_interval_sec}` / `{lint_interval_hours}` / `{instance_root}` / `{agent_invocation}` / `{skill_prefix}` (F2 기존)
- `{venv_path}` — `~/wikihub/.venv_path` 사이드카 파일 (install.sh Step 3 가 기록)
- `{credentials_path}` — `wikihub.yaml.vaults[id].options.credentials_path` (per-vault)
- `{wikihub_home}` — `WIKIHUB_HOME` env (default `~/wikihub`)

**결과 파일명**: `{vault_id}-ingest.service`, `{vault_id}-ingest.timer` (F2 setup.md 정합).

**이유**:
- B2 가 vault 별 `OnUnitActiveSec` (sync_interval), 환경변수 (credentials_path) 등 서로 다른 값을 자연 substitution.
- B1 (instantiated) 은 timer 의 OnUnitActiveSec 통일 강제 — v0.1.0 의 vault 별 다른 interval 가정과 어긋남.
- envsubst / sed 는 instance.root·agent.binary 의 공백·특수문자 escape 부담. Python helper 가 yaml load + str.Template 으로 안전.
- vault_id 정규식 `^[a-z][a-z0-9_]*$` 강제로 substitution injection 방지.

## Consequences

- **긍정**: vault 별 자유로운 interval·credentials 매핑. F2 setup.md 정본 정합. Python substitution 의 escape 안전.
- **부정/제약**: vault 추가 시 `.service` + `.timer` 두 파일 생성 — 5 vault 면 10 파일. 메인테이너가 수동 편집 시 `/wh:setup` 호출이 덮어쓰기 (yaml = 정본 — 의도된 동작).
- **후속 영향 / 재검토 트리거**:
  - **vault ≥ 5 또는 모든 vault 의 `sync_interval_sec` 통일 운영 또는 journald instance filter (`journalctl --user-unit "wikihub-vault@*.service"`) 가 운영 디버깅에 필요해질 때** — B1 (instantiated) 재검토. 그 시점에 본 ADR supersede + 마이그레이션 절차 정본화.
  - v0.2.x 에서 vault type 추가 (NAS / Notion / Slack) 시 본 ADR 재검토.
