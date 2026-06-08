# Plan — v016_operational_default_align

- **시작일**: 2026-05-22 KST
- **버전 목표**: v0.1.5 → v0.1.6 (patch 승격)
- **연계 백로그**: `~/Google Drive/내 드라이브/wikihub/backlog/260520_wikihub_backlog.md` (§V·§M), `260521_wikihub_backlog.md` (§C2·§F)
- **운영 정본 확보 경로**: user 가 share 한 hermes 모델 설정 + ExecStart + wh-ingest 16:40 KST cycle (deepseek-v4-pro, 8.477s mechanical-only)

---

## 1. 작업 분류

**운영 + 문서** — 4건의 정본 default·가이드 align (운영자 실 운영 결정 ↔ wikihub repo 정본 mismatch 해소).

- 기능 추가 ✗
- 리팩토링 ✗
- 버그 ✗
- 문서 ✓ (가이드·README·ADR §Note)
- **운영 ✓** (yaml default 값 변경 + install.sh env template + setup.md 안내)

## 2. 적용 단계 선언

| Step | 수행 | 사유 |
|---|---|---|
| Step 1 Plan | ✓ | 본 문서 |
| Step 2 Analysis & Design | ✓ | 4건 통합 설계 + 트레이드오프 + Karpathy Surgical Changes 경계 |
| Step 3 Implementation | ✓ | yaml.example, install.sh, setup.md, ADR-0032 §Note, README, HISTORY, VERSION |
| Step 4 Review | **생략** | 변경 50줄 이하 + 단일 정합 (default 값 + 가이드) + 외부 인터페이스 (스키마·명령어 의미론·API) 미변경 (값만 변경) |
| Step 5 Deployment | ✓ | `_system/` + install.sh + VERSION 승격 — git push + 운영 server `install.sh --update` 흐름 |

## 3. 예상 영향 범위

### 정본 변경 (4건)

| # | 파일 | 변경 |
|---|---|---|
| 1 | `wikihub.yaml.example:20` | `sync_interval_sec` 600 → 3600 (1h) + 코멘트 |
| 2 | `install.sh:700-718` `_step5_instance_dirs` env template | `GEMINI` backend 예시 1블록 추가 |
| 3 | `install.sh:1119+` `_step8_guide` + `_system/commands/setup.md` | hermes `delegation.model = minimax-m2.5` 권장 안내 |
| 4 | `wikihub.yaml.example:69` | `agent.models.wh-lint` minimax-m2.5 → deepseek-v4-flash + 코멘트 갱신 |

### 부속 변경

| 파일 | 변경 |
|---|---|
| `docs/adr/0032-hermes-skill-registration-policy.md` | §Note 추가 (wh-lint default 변경 + 운영 정본 align 사유) |
| `_system/VERSION` | 0.1.5 → 0.1.6 |
| `features/HISTORY.md` | v0.1.6 항목 append |
| `README.md` | 버전 badge + 로드맵 표 v0.1.x 항목 (본 feature scope 한정) |

### README 갱신 scope 결정 (Karpathy Surgical Changes 적용)

User 가 "readme 도 업데이트 해" 라고 했으나 README 가 v0.1.0 기준이라 stale 변경 누적이 큼:

| 후보 변경 | 본 feature scope? | 사유 |
|---|---|---|
| Title + badge: v0.1.0 → v0.1.6 | **✓ 포함** | 본 feature 의 VERSION 승격과 직결 |
| 로드맵 표: v0.1.x 항목 (v0.1.1~v0.1.6 누적) 추가 | **✓ 포함** | v0.1.0 acceptance 표 stale — v0.1.x 정본화 항목 1줄 안내 |
| 개발 상태 한 줄 (line 19) 갱신 | **✓ 포함** | 버전 align |
| Mermaid diagram gws CLI / SA 잔존 (line 49-67) → rclone-only 갱신 | **✗ 분리** | ADR-0035 일괄 반영 별도 feature 가치. 본 feature 의 default align scope 초과 |
| `~/.credentials/wikihub/` SA 자료 (line 102) → `~/.config/rclone/` rclone.conf | **✗ 분리** | 동일 사유 |
| F3·F4 description (line 219-220) ADR-0035 align | **✗ 분리** | 동일 사유 |
| graphify URL (line 244) PyPI graphifyy align | **✗ 분리** | ADR-0036 정본화 별도 feature 가치 |

→ 본 feature 의 README scope = **버전 + 로드맵 + 개발 상태 한 줄** (3 포인트). ADR-0035 일괄 README align 은 별도 feature (v0.1.7 후보) 로 분리.

## 4. 메소드론 적용 여부

본 절차 (Step 1~3, 5) 적용. trivial 변경 아님 — 4건 통합 + ADR §Note + README 갱신 + VERSION 승격 묶음.

## 5. 다음 단계

`"바로 진행"` 또는 `"확정할게요"` 응답 후 Step 2 (analysis_and_design.md) 시작. analysis 에서 다룰 핵심:

- 4건의 결정 정합성 (예: wh-lint default 변경의 한자→한글 정책 보호 layer 검증)
- 운영자가 이미 적용한 결정 → 정본 default 변경 시 새 운영자 영향 분석
- README scope 의 surgical changes 경계 재확인
- DoD: render dry-run 통과 + ADR §Note 인용 정합 + HISTORY 항목 형식 정합
