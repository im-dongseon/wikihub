# ADR-0044: NAS vault 저장 계층 — SFTP backend 지원

- **Status**: Accepted
- **Date**: 2026-06-03
- **Feature**: features/20260602_nas_vault
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

wikihub에 Synology NAS를 Tailscale 기반 read-only 소스 미러로 추가한다. 기존 Drive vault의 rclone mount + lsjson diff 아키텍처를 재사용하되, SFTP backend 특성(path 기반, ID 부재, OAuth 불요, Tailscale 도달성 의존)으로 인한 분기만 추가한다.

### 배경

- NAS vault는 Drive vault와 backend가 다른 최초의 vault type 확장
- SFTP backend는 ID가 공백 → 기존 ID 기반 diff 로직 사용 불가
- OAuth 불요 → vfs_refresh, OAuth 검사 스킵 필요
- Tailscale 경유 → 도달성 게이트 필요

## Considered Options

### (α) 기존 템플릿 분기 (채택)
- `render_systemd_units.py`에서 vault_type에 따라 mount 옵션 분기
- 단일 템플릿 유지, 관리 효율성

### (β) 별도 systemd drop-in
- NAS vault 전용 drop-in 생성
- 격리된 관리, 별도 파일 필요

### 채택 사유
- 변경 사항이 옵션 추가/제거 수준 (완전한 오버라이드 아님)
- 기존 템플릿 구조 유지
- 단일 소스 관리

## Decision

### 6건의 설계 결정

| # | 결정 | 근거 |
|---|------|------|
| ① | vault type 신규 추가 (`nas`) | `config.py`에서 `SUPPORTED_VAULT_TYPES`에 추가 |
| ② | mount: `--vfs-cache-mode full` + `--read-only` + `--drive-export-formats` 제거 | read-only 환경에서 Google native 변환 불요 |
| ③ | OAuth 패턴 스킵 | `vault-fetch.py`에서 `vault_cfg.type == "nas"` 시 `vfs_refresh()` 호출 skip |
| ④ | rename = ID 부재 → delete+add 폴백 (path 기반 diff) | `mount_diff.py`에서 `_compute_diff_path_based()` 함수 추가 |
| ⑤ | systemd 도달성 게이트 = SFTP 포트 TCP 체크 | `ExecStartPre`에서 `/dev/tcp` 사용 |
| ⑥ | rc/vfs-refresh 생략 | NAS vault는 `--rc`, `--rc-addr` 옵션 미포함 |

### 핵심 구현 파일

| 파일 | 변경 내용 |
|------|-----------|
| `scripts/lib/config.py` | `SUPPORTED_VAULT_TYPES`에 `nas` 추가, 필수 옵션 검증 |
| `scripts/vault-fetch.py` | vault_type == "nas" 시 vfs_refresh skip |
| `scripts/lib/mount_diff.py` | `vault_type` 파라미터 추가, `_compute_diff_path_based()` 함수 |
| `scripts/lib/sync.py` | `vault_type=vault_cfg.type` 전달 |
| `_system/systemd/wikihub-mount@.service.template` | vault_type별 분기 (after_target, mount_options, restart_policy) |
| `scripts/_helpers/render_systemd_units.py` | vault_type에 따라 mount 옵션 분기 |

## Consequences

### 핵심 리스크

| 리스크 | 설명 | 완화 |
|--------|------|------|
| ④ path 기반 diff로 rename 감지 불가 | SFTP backend는 ID가 없으므로 rename 감지 불가 | delete + new path created로 분해 |
| ⑤ Tailscale 도달성 게이트 | TCP 체크 실패 시 mount 실패 → ingest 중단 | `Restart=on-failure`로 자가 복구 |

### 추가 고려사항

- **timeout**: mount TimeoutStartSec 미정의 (NAS vault 90s 근접) → 별도 이슈 필요
- **테스트**: NAS path-based diff 테스트 0건 → 별도 이슈 필요
- **downstream**: created entry source_id="" → downstream 빈 키 처리 필요

### Cross-references

| ADR | 관계 | 설명 |
|-----|------|------|
| ADR-0025 | 참조 | rclone mount 채택 — 동일 아키텍처 재사용 |
| ADR-0026 | 수정 | vfs refresh 정책 — NAS vault는 미적용 |
| ADR-0035 | 참조 | rclone 단독화 + lsjson diff — path 기반 확장 |

### 관련 이슈

- #117: vault type schema + config 파싱 ✅
- #118: install.sh rclone SFTP remote 생성 ✅
- #119: vfs_refresh + OAuth 검사 skip ✅
- #120: mount_diff.py path 기반 diff ✅
- #121: sync.py vault_type 전달 ✅
- #122: systemd unit NAS vault 지원 ✅ (이슈 128로 해결)
- #123: ADR 작성 (본 이슈)
- #128: mount 템플릿 분기 (systemd) ✅
