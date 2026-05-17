# Backlog — v0.2.x 후속 작업

본 문서는 v0.1.0 의 각 feature 작업 도중 surface 한 항목 중 **v0.2.x 이후로 deferred** 결정된 것들의 인덱스. feature 단위 작업이 본 backlog 의 항목을 picking 해서 새 feature_id 로 시작한다.

## F4 install_runtime 산출 (2026-05-17 종료)

### 결함 surface — v0.1.0 범위 밖

| ID | 영역 | 항목 | 해결 방향 (제안) |
|---|---|---|---|
| #12 | agent integration | Hermes 의 `-z` 가 LLM prompt 직접 전달 — wikihub spec 의 `wh:<skill>` slash-command 자동 매핑 안 함. ADR-0002·0011·0012 의 hermes invocation 가정과 실 Hermes 동작 mismatch | F5 (hermes_adapter) — Hermes skill 정의 (SKILL.md) 또는 ADR-0012 옵션 β (wrapper script dispatcher) 채택. v0.1.0 운영 시작의 blocker |
| #A | install update | `BRANCH default=latest` 가 GitHub 부재 — release 전략 미정 | `update_mode` feature — main · tag 정합 결정 |
| #B | install update | Step 2 `rm -rf $WIKIHUB_HOME` 가 destructive — 메인테이너의 unstaged 작업 손실. 재실행이 "재설치" 아닌 "업데이트" 가 되어야 함 | `update_mode` feature — `--update` flag + `git fetch + reset --hard origin/$BRANCH` idempotent |
| #C | install update | update 중 `vault@` timer fire 시 vault-fetch.py ImportError race | `update_mode` feature — Step 2 진입 시 systemd stop/start orchestrate |
| #D | install update | update 후 service template 변경 시 자동 redeploy 미수행 — 메인테이너가 `/wh:setup` 별도 호출 의존 | `update_mode` feature — systemd unit auto-redeploy + mount stop/start orchestration |

### R15·R16 Could 8건 (Step 4 code review)

`features/archive/20260514_install_runtime/code_review_3.md` (R15 internal consistency) + `code_review_4.md` (R16 SRE reliability) 의 backlog 항목.

| ID | 영역 | 항목 |
|---|---|---|
| R15-M4 | regex evidence | `_RCLONE_AUTH_PATTERNS` 의 SA key rotation·GCP project disabled·IAM revoke 패턴 미커버 — 운영 evidence 누적 후 surgical 추가 |
| R15-L4 | parsing | install.sh `rclone version` 의 `awk '{print $2}'` future-proof — 형식 변경 대비 |
| R15-L5 | yaml validation | yaml 내 `rclone_rc_port` 중복 검증 — config.py 의 `_parse_vault` 갱신 (v0.1.0 단일 vault 가정에서 surface 안 됨) |
| R16-M3 | rc API schema | rclone `vfs/refresh` 응답의 unknown key warn — schema 변경 detect forensic |
| R16-M4 | concurrency | ops-alert.py 의 `socket.setdefaulttimeout` race — long-running mode 전환 시 제거 |
| R16-L1 | logging | mount.py `error_snippet[:200]!r` 가독성 — `!s` + newline strip |
| R16-L2 | log rotation | install.log 의 rotation 없음 — `update_mode` feature 와 함께 처리 |
| R16-L4 | filesystem | `vault-fetch.py` 의 `fcntl.flock` NFS 미보장 — v0.2.x distributed 시 namespace |

### V<N> Phase 2 acceptance gate 미수행 항목

| 항목 | 내용 | 비고 |
|---|---|---|
| V18 fallback diagnostic 검증 (R14-CRIT-1) | last_failure.json **부재** 케이스에서 ops-alert 의 mount@ journalctl tail 첨부 분기 정합 | V<N> 검증 시 stale last_failure 잔존으로 미진입 — 별도 verification |

## 다음 feature 제안 (v0.1.0 완성 path)

| feat_id | 목적 | 의존 |
|---|---|---|
| `hermes_adapter` (F5) | wikihub 의 `wh:*` skill 을 Hermes skill 시스템에 정합화. ADR-0011·0012 spec 보강 또는 wrapper dispatcher 채택. 결함 #12 lock | F4 archive |
| `update_mode` | install.sh `--update` flag + 결함 #A·#B·#C·#D 일괄 fix + log rotation (R16-L2) | F4 archive |
| `lint_authoring` (F2 잔여) | wiki 의 정합성 검증 자동화 (lint.service) | F2 spec |
| `wiki_query` (F6) | 메인테이너/사용자가 wiki 검색 / 그래프 탐색 (`wh:query`) | F5 (hermes_adapter) |

v0.1.0 acceptance = F4 (✅) + F5 + (선택) update_mode. v0.2.x 는 lint_authoring·wiki_query·multi-vault 등.
