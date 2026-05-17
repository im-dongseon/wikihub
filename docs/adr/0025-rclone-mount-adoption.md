# ADR-0025: rclone mount 채택 — vault 자체 mount + vfs cache minimal + GitHub Releases binary

- **Status**: Accepted
- **Date**: 2026-05-15 (v9 정본화), 2026-05-17 minor 갱신 (V15a 진단 → β3 → β2)
- **Feature**: features/20260514_install_runtime (v9)
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

F4 v1~v6 까지의 design 은 Google Drive 접근을 **gws CLI 단독**으로 처리. 그러나 사용자 요구사항이 추가됨:

> 운영자가 Google Drive 에 파일을 떨구면 OCI 서버의 vault 폴더에서 **실시간으로 접근** 가능해야 함 (SSH `ls`/`cat`).

gws 단독 design 으로는 이 UX 가 불가능 — 매 sync 사이클의 다운로드만 가능, 사이클 사이 시점에는 vault 폴더가 N-1 사이클 시점의 스냅샷.

추가로 gws 의 alpha (v0.x) 의존성 부담을 격리하고 싶다는 요구. 다만 gws 의 changes API (cursor 기반 변경 감지) 는 정확성 측면에서 유지 가치 있음 — rclone 은 Drive Changes API 를 backend command 로 노출하지 않음 (`rclone backend changes` 부재).

본 ADR 은 **rclone mount 도입 + 책임 영역 lock**. 변경 감지는 gws 유지 (ADR-0014), 다운로드/UX 는 rclone — Path C+ 정본화 (ADR-0027 참조).

## Considered Options

**(α) mount 위치**:
- (J1) vault 별도 + 마운트 별도 디렉토리: `<instance_root>/google_drive/` 마운트 + `<instance_root>/vault/` 다운로드 → 두 디렉토리 동기화 부담
- **(J2) vault 자체에 직접 마운트**: `<instance_root>/vault/<vault_id>/` 가 곧 mount point → 다운로드 단계 제거, 사용자 의도 1:1
- (J3) rclone mount 미사용 (gws 단독 유지): 사용자 요구사항 (실시간 UX) 미충족

**(β) vfs cache 모드**:
- (β1) `--vfs-cache-mode off`: 매 read 마다 Drive fetch — latency 부담
- **(β2) `--vfs-cache-mode minimal`**: stream read path + 큰 read 만 캐시. Google native 호환 (V15a 진단으로 lock, 2026-05-17)
- (β3) `--vfs-cache-mode full`: 다운로드된 파일 영속 캐시. **결함 — Google native (Docs/Sheets/Slides) read=0 silent fail** (V15a 진단). RWFileHandle path 가 lookup size=0 을 신뢰하여 backend export 호출 없이 EOF.

**(γ) 설치 채널**:
- (γ1) `apt`: 종종 outdated, version pin 어려움
- (γ2) `rclone.org/install.sh | sudo bash`: curl-pipe + sudo root 권한, supply chain 위협 surface 큼 (R12-HIGH-3)
- **(γ3) GitHub Releases binary + SHA256SUMS verify + curl retry**: SHA256 본문 검증으로 mutable artifact 위협 차단. 3회 retry @ 5min interval (R14-HIGH-1 — GitHub 가용성 회귀 대응)

**(δ) rc endpoint**:
- (δ1) 미활성화: vfs/refresh 호출 불가 → ADR-0026 K1 (race window 차단) 동작 안 함
- **(δ2) `--rc --rc-addr 127.0.0.1:<port>`**: per-vault port 로 vfs/refresh 호출 가능

> 옵션 상세는 [features/20260514_install_runtime/analysis_and_design.md §10.3.1 + §10.4.1 + §10.4.2](../../features/20260514_install_runtime/analysis_and_design.md) + [rclone_vs_gws_comparison.md](../../features/20260514_install_runtime/rclone_vs_gws_comparison.md) 참조.

## Decision

**채택**: (α=J2) + (β=β2) + (γ=γ3) + (δ=δ2) (v9 정본 β3 → V15a 진단으로 β2 변경, 2026-05-17)

### mount 위치 — vault 자체

`<instance_root>/vault/<vault_id>/` 가 곧 rclone mount point. 다운로드 단계 폐기, vfs cache 가 캐시 역할 흡수.

### `wikihub-mount@.service.template` (v9 정본)

```ini
[Unit]
Description=WikiHub rclone mount — %i
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5
OnFailure=ops-alert.service                                # v9 R12-CRIT-1

[Service]
Type=simple
WorkingDirectory={instance_root}
Environment=PATH={venv_path}/bin:/usr/bin:/bin
Environment=RCLONE_CONFIG={rclone_config_path}
ExecStartPre=/bin/mkdir -p {instance_root}/vault/%i
ExecStart={rclone_bin} mount {remote_name_for_%i}: {instance_root}/vault/%i \
  --vfs-cache-mode minimal \                               # 2026-05-17 V15a 진단 (β3 → β2)
  --vfs-cache-max-size {vfs_cache_max_size} \
  --drive-export-formats docx,xlsx,pptx,md \               # Google native → markdown 우선
  --dir-cache-time 5m \
  --log-level NOTICE \                                     # v9 R12-MED-3 (token 노출 회피)
  --rc \
  --rc-addr 127.0.0.1:{rc_port_for_%i}
ExecStop=/bin/fusermount3 -u {instance_root}/vault/%i
Restart=always
RestartSec=10s
RemainAfterExit=no

[Install]
WantedBy=default.target
```

### 설치 채널 — GitHub Releases binary + SHA256SUMS verify + curl retry (v9)

`install.sh` Step 5.5a:
- `rclone.org/install.sh | sudo bash` 폐기 (supply chain 위협)
- GitHub Releases (`https://github.com/rclone/rclone/releases/download/v<version>/`) 에서 binary + SHA256SUMS 다운로드
- `sha256sum -c` 본문 검증 (artifact tamper 시 fail-fast)
- `_curl_with_retry` 3회 @ 5min interval — GitHub 가용성 회귀 대응
- version pin: `RCLONE_PINNED_VERSION` (default v1.69.1, V16 검증 후 lock)

### `rclone.conf` 권한 (v9 R12-MED-2)

`install.sh` Step 5.5b — `_enforce_rclone_conf_perms` 가 `chmod 0600 ~/.config/rclone/rclone.conf`. setup.md Step 5.5 의 운영자 가이드도 명시.

### per-vault rc port (v9 R12-MED-1)

`install.sh` Step 5.5c — `_yaml_get_vault_rc_ports` + `_check_rc_port_available` (ss + lsof cross-check + EUID 경고). yaml `vaults[*].options.rclone_rc_port` 가 정본 (default 5572 + 순번).

**이유**:
- (J2): 사용자 의도 (Drive ↔ vault 실시간) 와 1:1. 다운로드 단계 폐기로 `sync.py` 의 `_download_to_vault` 헬퍼 폐기 (~90% 재사용 + 다운로드만 mount path `open()` 교체)
- (β2): V15a 진단 (2026-05-17, Multipass ARM Ubuntu 22.04 + rclone v1.69.1 + SA + sample 4 file) 으로 β3 의 Google native silent fail (read=0) root cause 식별. β2 는 stream read path 라 backend export 자동 트리거 + 큰 파일 캐시 효과 유지 → wikihub 의 read 패턴 (extraction.py 1회 변환 + Hermes 검색 frequent) 에 정합. 작은 read 매번 fetch 의 latency 부담은 .md frontmatter 정도라 영향 미미. **`--drive-export-formats docx,xlsx,pptx,md` 명시** 보강 (backend export call 시 적용).
- (γ3): rclone.org install.sh 의 sudo + curl-pipe 위협 (ADR-0023 와 동일 패턴이지만 sudo 추가) 회피. SHA256 본문 검증으로 supply chain 위협 차단. GitHub 가용성 회귀는 retry 로 흡수
- (δ2): ADR-0026 (vfs refresh 정책) 의 K1 채택은 `rclone rc vfs/refresh` 호출 필수 → rc endpoint 활성화 필수

## Consequences

- **긍정**:
  - 사용자 요구사항 (Drive ↔ vault 실시간 동기화 + SSH ls/cat) 충족
  - F3 `sync.py` 핵심 로직 ~90% 재사용 (다운로드 헬퍼만 교체)
  - vfs cache 가 다운로드 캐시 역할 — 별도 캐시 정책 불필요
  - GitHub Releases + SHA verify 로 supply chain 위협 격리
  - rclone v1.x stable 의 maturity 활용 — gws alpha 부담을 changes API 영역에만 격리

- **부정/제약**:
  - mount daemon (rclone) 이 상시 살아있어야 함 → systemd unit 1개 추가 (`wikihub-mount@`)
  - vfs cache minimal 모드 — 작은 read 매번 fetch (Drive API quota 소모 + latency). `vfs_cache_max_size` 는 큰 파일 한도로만 의미 (β2 정합). Q7 (OCI free tier 디스크 가이드) 는 큰 파일 캐시 영역만 대상.
  - mount permanently failed case 의 fatal escalation 필요 → ADR-0024 v9 minor 갱신 (mount scope) + ADR-0026 race window 차단 + 2-layer escalation (analysis_and_design.md §10.4.7)
  - rclone OAuth 추가 발급 필요 (gws OAuth 와 분리) — setup.md Step 5.5 신규 (ADR-0029 SA 전환 후 SA JSON key 공유)
  - mount 시작 race (Type=simple active ≠ FUSE ready) — `assert_mount_alive` Retryable (exit 75) 로 흡수, ops-alert 오발화 차단
  - **rclone v1.69.1 + vfs-cache-mode full 의 Google native silent fail 결함** (V15a) — β2 채택으로 회피. rclone v1.70+ 에서 full mode 의 RWFileHandle 가 Google native 의 backend export 를 트리거하도록 회귀 fix 되는지 추적 (Cross-references)
  - **Supply chain release-time compromise 미차단** (R16-H2, V<N> R16 SRE 리뷰, 2026-05-17): SHA256SUMS 본문 검증 (γ3) 은 transport-time tamper 만 차단 — GitHub Releases artifact 가 release 시점에 attacker 통제 하 publish 시 (compromised maintainer · supply chain attack) SHA verify 통과. v0.1.0 은 binary signing (`gpg --verify`) / sigstore / reproducible build 미적용. v0.2.x deferred — `RCLONE_PINNED_SHA256` env override 또는 in-toto attestation 도입 검토.

- **후속 영향**:
  - V13 (mount 정상 마운트 + ls/cat) 통과 시 본 ADR 정합성 회귀 방지
  - V14 (Restart=always + hung mount 감지) 통과 시 mount lifecycle 안정성 보장
  - V15a (Google native read via mount) 통과 — β2 + drive-export-formats 명시로 재검증 필수
  - V16 (rclone version pin + SHA verify) 통과 시 supply chain 정합
  - 재검토 트리거:
    - rclone 이 Drive Changes API 를 backend command 로 노출 (`rclone backend changes` 추가) → ADR-0027 의 책임 분리 재검토 (rclone 단일화 가능)
    - rclone v1.x → v2.x major upgrade 시 breaking change 검토
    - rclone v1.70+ 에서 full mode 의 Google native silent fail 회귀 fix → β2 → β3 재검토 (cache 효과 극대화)

## Cross-references

- ADR-0014 (gws CLI 채택) — supersede 없음. 변경 감지 정본은 gws 유지
- ADR-0023 (install.sh curl-pipe) — supply chain 위협 모델 정합
- ADR-0024 (fatal alert contract) — v9 minor 갱신 (mount scope writer)
- ADR-0026 (vfs refresh 정책) — race window 차단 위해 `--rc` 활성화 필수
- ADR-0027 (rclone vs gws 책임 분리) — Path C+ 정본화의 architectural 결정. 본 ADR 은 그 안의 mount 산출물 spec lock
- features/20260514_install_runtime/rclone_vs_gws_comparison.md — Path C+ 결정 근거
- features/20260514_install_runtime/analysis_and_design.md §10.3.1·§10.4.1·§10.4.2 — spec 정본
