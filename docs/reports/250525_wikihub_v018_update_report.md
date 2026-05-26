# Wikihub Backlog — 250525: v0.1.8 Update Report

**날짜**: 2026-05-25 KST
**버전**: v0.1.7 → v0.1.8
**관련 ADR**: ADR-0030, ADR-0038, ADR-0037, ADR-0031
**수행자**: Hermes Agent (deepseek-v4-flash)

---

## §A. 개요

v0.1.8(`4d85cca`) 업데이트 적용. 주요 변경:
- **wh-graphify skill 폐기** → 독립 systemd unit(`wikihub-graphify.service`)으로 격상
- **wikihub-monitor 신설**: 12hr 운영 보고서 timer (09:00/21:00 KST)
- **update_path_fixes**: graphify Hermes skill 제거, yaml.example sync 일반화
- **install_update_hardening**: install.sh self-restart 메커니즘 도입 (v0.1.7→v0.1.8 업데이트 경로 보완)
- **lint_operations_improvements**: lint cycle 자동 적용, alias frontmatter, graphify timeout yaml expose
- **branch_strategy_formalize**: main→v0.X.Y→feature git workflow 정립
- **legacy_migration_cleanup**: v0.1.0~v0.1.6 era 1회성 migration 코드 정리
- **lint/ingest 시간 간격 기본값 정합**: lint 3h, ingest 1h (yaml.example sync)
- **신규 의존성**: yq 4.44.3

---

## §B. 설치 전 설정 (v0.1.7)

### B-1. wikihub.yaml

```yaml
version: 1
instance:
  root: /home/ubuntu/wikihub
  timezone: Asia/Seoul
vaults:
  - id: gdrive
    type: gdrive_api
    enabled: true
    sync_interval_sec: 3600
    local_path: /home/ubuntu/wikihub/vault/gdrive
    options:
      exclude_shared_with_me: true
      max_file_size_mb: 50
      mount_path: ~/wikihub/vault/gdrive
      rclone_remote_name: gdrive
      rclone_rc_port: 5572
      rclone_remote_path: wikihub
      bootstrap_allowed: false          # ← ADR-0035 폐기 필드 (후속 migration에서 제거)
operations:
  lint_interval_hours: 1
  max_concurrent_vaults: serial
  retry:
    max_attempts: 5
    backoff_base_sec: 60
  disk: {}
  fatal_webhook_url:
  fatal_webhook_timeout_sec: 10
  instance_label: wikihub
  gws_min_version: 0.22.5              # ← ADR-0035 폐기 필드 (잔존)
  rclone_min_version: 1.65.0
  rclone_max_version: 1.99.99
  vfs_cache_max_size: 10G
  vfs_refresh_mode: recursive
  graphify_backend: ollama
  graphify_profile: ollama_gemma
agent:
  type: hermes
  binary: /home/ubuntu/.local/bin/hermes
  oneshot_args: [chat, --skills, '{skill}', --quiet, --yolo, --query]
  skill_prefix: wh-
  timeout_sec: 600
  notify_on_fatal: true
  # agent.models 블록 부재 (v0.1.5+ migration에서 추가됨)
```

### B-2. systemd units

| unit | 주요 설정 | 비고 |
|------|----------|------|
| lint.service | `--yolo`, TimeoutStartSec=600sec, **model 미지정** | 기본 모델 사용 |
| lint.timer | **OnUnitInactiveSec=3h** | 사용자 수동 설정 |
| vault@gdrive.service | `--yolo --model deepseek-v4-flash`, RCLONE_RC_ADDR, TimeoutStartSec=600sec | |
| vault@gdrive.timer | OnUnitInactiveSec=3600s (1h) | |
| mount@gdrive.service | vfs-cache-mode minimal, 10G, export-formats docx,xlsx,pptx,md, dir-cache-time 5m | 변경 없음 |
| pending-monitor.service | TimeoutStartSec=60sec | |
| pending-monitor.timer | OnUnitInactiveSec=30min | |

### B-3. systemd 상태

| unit | 활성화 | 상태 |
|------|--------|------|
| mount@gdrive.service | enabled | active (running) |
| lint.timer | enabled | active (waiting) |
| vault@gdrive.timer | enabled | active (waiting) |
| pending-monitor.timer | enabled | active (waiting) |

### B-4. env 파일

```bash
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_ENDPOINT=http://127.0.0.1:11434
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_API_KEY=***
WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_MODEL=gemma4:31b-cloud
TELEGRAM_ALERT_BOT_TOKEN=***
TELEGRAM_ALERT_CHAT_ID=29696627
TELEGRAM_MONITOR_BOT_TOKEN=***
TELEGRAM_MONITOR_CHAT_ID=29696627
```

### B-5. 의존성 버전

- rclone 1.69.1
- graphify 0.8.17
- uv 0.11.14

---

## §C. 설치 과정

### C-1. 1차 시도 실패 (v0.1.7 install.sh)

**증상**: v0.1.7의 install.sh가 `git reset --hard refs/tags/latest`로 v0.1.8 checkout 후 `_step6_agent_skill`에서 실패:

```
ERROR frontmatter source 부재: .../_system/skills/wh-graphify.frontmatter.yaml
ERROR update 실패 (exit 2) — rollback
```

**원인**: v0.1.7의 `WIKIHUB_SKILLS=(wh-ingest wh-lint wh-query wh-graphify wh-setup)` — 5개 skill. v0.1.8은 `wh-graphify` 제거된 4개. git reset으로 v0.1.8 파일로 교체됐으나 bash는 기존 in-memory 배열 유지 → `wh-graphify.frontmatter.yaml` 조회 실패. v0.1.8에 도입된 self-restart 메커니즘이 v0.1.7에는 없어 업데이트 경로가 깨짐.

**대처**: 수동 checkout v0.1.8 후 install.sh 재실행:

```bash
git -C "$WIKIHUB_SRC" reset --hard v0.1.8
bash "$WIKIHUB_SRC/install.sh"
```

### C-2. 2차 시도 성공 (v0.1.8 install.sh)

install.sh self-restart → systemd reorchestrate → schema migration → skill materialize(4건) → /wh-setup 완료 → mount start → systemd verify OK

---

## §D. 설치 후 설정 변경 (v0.1.7 → v0.1.8)

### D-1. wikihub.yaml schema migration (자동 적용)

설치 전 필드 → 설치 후 자동 추가된 필드 (`monitor_*`, `graphify_timeout_*`):

| 필드 | 값 | 출처 |
|------|----|------|
| `monitor_enabled` | `true` | yaml.example sync |
| `monitor_report_vault` | `(빈 값)` | yaml.example sync |
| `monitor_report_subpath` | `project/wikihub/report` | yaml.example sync |
| `graphify_timeout_sec` | `900` | yaml.example sync |
| `graphify_partial_failure_threshold` | `0.5` | yaml.example sync |
| `pending_alert_age_sec` | `3600` | (이전 migration에서 이미 존재) |
| `lint_contradiction_check` | `true` | (이전 migration에서 이미 존재) |
| `graphify_enabled` | `true` | (이전 migration에서 이미 존재) |
| `graphify_min_version` | `0.8.0` | (이전 migration에서 이미 존재) |
| `graphify_max_version` | `0.99.99` | (이전 migration에서 이미 존재) |
| `agent.models.wh-lint` | `deepseek-v4-flash` | (이전 migration에서 이미 존재) |
| `agent.models.wh-ingest` | `deepseek-v4-pro` | ← 복원 대상 |

**제거된 필드**: `vaults[0].options.bootstrap_allowed` (ADR-0035 cleanup)

**잔존 deprecated 필드**: `gws_min_version: 0.22.5` (아직 cleanup 안 됨)

### D-2. systemd unit 변경

| unit | 설치 전 | 설치 후 (초기) | 복원 후 |
|------|--------|--------------|--------|
| **lint.service** | `--yolo` (model 미지정) | `--yolo --model deepseek-v4-flash` | 유지 |
| **lint.timer** | **OnUnitInactiveSec=3h** (수동 설정) | **OnUnitInactiveSec=1h** (template 기본값) | **→ 3h 복원** |
| **vault@gdrive.service** | `--model deepseek-v4-flash` | `--model deepseek-v4-pro` (yaml models 반영) | **→ deepseek-v4-flash 복원** |
| vault@gdrive.timer | OnUnitInactiveSec=3600s | 동일 | 유지 |
| mount@gdrive.service | vfs-cache-mode minimal, 10G | 동일 | 유지 |
| pending-monitor.service/.timer | 30min | 동일 | 유지 |

**신규 unit**:

| unit | 설명 | 초기 상태 | 현재 상태 |
|------|------|----------|----------|
| wikihub-graphify.service | graphify 독립 systemd unit (Hermes skill 폐기) | static | static (timer 없음) |
| wikihub-monitor.service | 12hr 운영 보고서 생성 | static | static |
| wikihub-monitor.timer | 09:00/21:00 KST | **disabled** | **→ enabled** |

### D-3. 의존성 변경

| 항목 | 설치 전 | 설치 후 |
|------|--------|--------|
| yq | 없음 | **4.44.3** (신규) |

---

## §E. 복원 작업

### E-1. lint timer 간격 복원 (3h)

```yaml
# wikihub.yaml
operations:
  lint_interval_hours: 1  →  3
```

render_systemd_units.py 재실행 → lint.timer OnUnitInactiveSec=3h 재생성.

### E-2. ingest model 복원 (deepseek-v4-flash)

```yaml
# wikihub.yaml
agent:
  models:
    wh-ingest: deepseek-v4-pro  →  deepseek-v4-flash
```

render_systemd_units.py 재실행 → vault@gdrive.service `--model deepseek-v4-flash` 재생성.

### E-3. monitor timer 활성화

```bash
systemctl --user enable --now wikihub-monitor.timer
```

---

## §F. 최종 systemd 상태

| unit | 상태 | 비고 |
|------|------|------|
| mount@gdrive.service | **active (running)** | 변경 없음 |
| lint.timer | enabled, waiting | 3h 간격, 복원 완료 |
| vault@gdrive.timer | enabled, waiting | 1h 간격 |
| pending-monitor.timer | enabled, waiting | 30min 간격 |
| monitor.timer | **enabled, waiting** | 신규, 09:00/21:00 KST |
| graphify.service | static | lint Step 9이 trigger |

---

## §G. 교훈

1. **v0.1.7→v0.1.8 업데이트 경로 결함**: v0.1.7 install.sh가 wh-graphify skill을 in-memory 배열로 보유한 상태에서 v0.1.8로 git reset → frontmutter 파일 부재로 실패. v0.1.8의 self-restart 메커니즘이 이 문제를 해결했으나, v0.1.7에는 해당 패치가 없어 수동 checkout이 필요했음.
2. **install.sh 기본값 재설정 주의**: lint timer 기본값 3h가 template에 반영되었으나, yaml `lint_interval_hours: 1`이 우선하여 1h로 렌더링됨. yaml 값을 source of truth로 삼아야 함.
3. **agent.models 자동 주입**: wikihub.yaml `agent.models`의 per-skill model override가 systemd unit의 `--model` 인자로 자동 렌더링됨. 이전에 lint.service는 model 미지정(default 모델 사용)이었으나 이제 yaml 값이 우선.
4. **graphify skill 폐기**: wh-graphify가 Hermes skill에서 systemd unit으로 이관. 향후 설치 시 `wh-graphify` 관련 참조가 없음.
5. **gws_min_version 잔존**: `gws_min_version: 0.22.5`가 wikihub.yaml에 아직 남아있음. ADR-0035 폐기 대상이나 마이그레이션에서 제거되지 않음. 차기 정리 시 참조.
