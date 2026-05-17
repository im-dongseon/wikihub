<!-- Thanks to: Andrej Karpathy, Louis Wang -->

<div align="center">

# WikiHub v0.1.0

서버에서 다중 소스를 통합 관리하는 LLM 위키 허브

**Server-first LLM wiki hub aggregating multiple source backends.**

[![Status](https://img.shields.io/badge/Status-Design%20Phase-orange)](features/20260513_v030_initial_architecture/analysis_and_design.md)
[![Version](https://img.shields.io/badge/Version-0.1.0--alpha-blue)](AGENTS.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

> **개발 상태**: 본 리포는 설계 단계입니다. 메소드론과 첫 feature의 분석·설계가 진행 중이며, 운영 가능한 구현체는 아직 없습니다. 운영 사용은 [WikiCurate v0.2.6](https://github.com/im-dongseon/wikicurate)을 참조하십시오.

---

## 목차

- [WikiHub란?](#wikihub란)
- [타깃 아키텍처](#타깃-아키텍처)
- [개발 방법론](#개발-방법론)
- [디렉토리 구조](#디렉토리-구조)
- [로드맵](#로드맵)
- [참고 자료](#참고-자료)
- [라이선스](#라이선스)

---

## WikiHub란?

`WikiHub`는 여러 외부 소스 백엔드(Google Drive, NAS 등)를 단일 LLM 위키로 통합 관리하는 server-first 시스템입니다.

### 왜 필요한가?

- 지식의 원본이 여러 곳에 흩어져 있는 환경(개인 클라우드, NAS, 메모 앱)에서 **단일 위키로 종합 분석**이 어려운 문제 해결
- 서버에서 24/7 동작하면서 **Telegram 같은 대화형 인터페이스로 자연어 질의·관리**
- 사용자는 평소대로 Google Drive 등에 파일을 떨구기만 하고, 위키는 자동으로 갱신·정리됨

---

## 타깃 아키텍처

```mermaid
flowchart TD
    GDrive["Google Drive"]
    Mount["rclone mount daemon<br/>(wikihub-mount@.service, Type=simple)<br/>vfs-cache full + dir-cache 5m + --rc"]
    Vault["wikihub-instance/vault/&lt;vault_id&gt;/<br/>(실시간 mount FS — SSH ls/cat 가능)"]
    Sync["vault-fetch.py<br/>(wikihub-vault@.service, Type=oneshot)<br/>systemd timer, 10분 주기"]
    Hermes["Hermes daemon<br/>Telegram polling +<br/>/ingest /lint /query /graphify"]
    Wiki["wikihub/wiki/<br/>(통합 위키)"]
    ADR["docs/adr/<br/>(결정 기록)"]

    GDrive -->|"FUSE read-through"| Mount
    Mount -->|"실시간 동기화"| Vault
    GDrive -->|"changes.list (cursor, gws CLI)"| Sync
    Sync -->|"assert_mount_alive + vfs/refresh"| Mount
    Vault -->|"mount FS open()"| Sync
    Sync -->|"변동 발생 시 trigger"| Hermes
    Hermes --> Wiki
    Hermes --> ADR
```

**v9 (ADR-0025·0026·0027 — Path C+ 책임 분리)**:
- **rclone mount** = Drive ↔ vault 실시간 동기화 + 파일 read 패스 (vfs cache 영속). SSH 에서 `ls/cat` 으로 Drive 파일 즉시 접근
- **gws CLI** = `drive changes list` 로 cursor 기반 변경 감지 (정확한 삭제·rename·권한 이벤트)
- **vault-fetch.py 사이클**: 시작 시 `assert_mount_alive` (stat) + `vfs/refresh recursive=true` 로 race window 차단 → `gws changes list` → mount FS `open()` → extraction → wiki page write

**rclone OAuth 1회성 발급** (vault 별, install.sh 후 setup.md §Step 5.5):
```
rclone config        # 안내 따라 OAuth flow + remote name = wikihub.yaml.vaults.<id>.options.rclone_remote_name
chmod 0600 ~/.config/rclone/rclone.conf
```
gws OAuth (macOS dev box 의 `scripts/auth_gdrive.py`) 와 token 분리 — 같은 Google 계정 권장.

상세 설계는 [`features/20260513_v030_initial_architecture/analysis_and_design.md`](features/20260513_v030_initial_architecture/analysis_and_design.md) + Path C+ 결정은 [`docs/adr/0025-rclone-mount-adoption.md`](docs/adr/0025-rclone-mount-adoption.md) · [`docs/adr/0027-rclone-gws-responsibility-split.md`](docs/adr/0027-rclone-gws-responsibility-split.md) 참조.

---

## 개발 방법론

WikiHub는 5단계 Feature-based Workflow를 따릅니다. 상세 가이드: [`AGENTS.md`](AGENTS.md), [`docs/agent_dev_guide.md`](docs/agent_dev_guide.md).

```mermaid
flowchart TD
    Plan["Step 1: Plan"]
    AD["Step 2: Analysis & Design"]
    Impl["Step 3: Implementation"]
    Review["Step 4: Review<br/>(조건부)"]
    Deploy["Step 5: Deployment<br/>(조건부)"]
    Archive["Feature 종료 처리<br/>(archive 이동, 필수)"]

    Plan --> AD --> Impl --> Review --> Deploy --> Archive
```

### 핵심 컨벤션

- **결정 정본은 ADR**: 모든 아키텍처 결정은 [`docs/adr/NNNN-{slug}.md`](docs/adr/) 단일 파일에. 다른 문서는 `ADR-NNNN` 식별자로 참조.
- **라이프사이클 분리**: `docs/`는 영속 기록(가이드·개념·ADR), `features/`는 워크스페이스(active → archive).
- **조건부 단계**: 검토와 배포는 plan.md에서 미리 생략 선언 가능(기준: 변경 크기·성격·영향 범위).
- **코딩 행동 원칙**: [Karpathy Guidelines](docs/karpathy-guidelines.md) 4원칙(Think Before Coding / Simplicity First / Surgical Changes / Goal-Driven Execution)을 메소드론과 매핑해 적용. 자세히는 `AGENTS.md §2`.

---

## 디렉토리 구조

현재 상태 (v0.1.0 부트스트랩):

```
wikihub/
├── AGENTS.md                  # 메인테이너 가이드 (CLAUDE.md / GEMINI.md 심볼릭)
├── docs/                      # 영속 기록 (영구 보존, supersede로만 변경)
│   ├── adr/                   #   결정 기록 (Architecture Decision Records)
│   ├── agent_dev_guide.md     #   개발 방법론 상세
│   ├── karpathy-guidelines.md #   코딩 행동 가이드
│   └── llm_wiki.md            #   LLM 위키 패턴 개념 설명
└── features/                  # 워크스페이스 (라이프사이클 있음)
    ├── HISTORY.md             #   배포 이력 (append-only)
    ├── [active feat_id]/      #   진행 중 feature
    └── archive/               #   완료 feature (종료 처리 시 이동)
```

향후 추가될 디렉토리 (구현 단계에서):

```
wikihub/
├── _system/                   # 정본 룰 + 명령어 플레이북 (deploy.sh로만 주입)
├── scripts/                   # gdrive-sync.py, watcher 등 인프라
├── deploy.sh                  # systemd 배포
└── wikihub.yaml.example       # vault 등록 설정 예시

별도 위치 (운영 시):
/opt/vault-gdrive/             # Drive API로 미러링되는 외부 vault
/opt/vault-nas/                # 향후 추가 가능
```

---

## 로드맵

v0.1.0 feature 진행 상황 (2026-05-17 기준):

| Feature | 범위 | 상태 |
|---|---|---|
| **F1: `v030_initial_architecture`** | 메소드론 + 초기 architecture 정본화 | ✅ archive |
| **F2: `wikihub_schema_v1`** | `_system/wiki-schema.md` + `_system/commands/*` 구현 | ✅ archive |
| **F3: `vault_gdrive_api`** | `scripts/sync.py` + Drive API + cursor/file_map 영속화 | ✅ archive |
| **F4: `install_runtime`** | `install.sh` + systemd unit (mount@/vault@/timer/ops-alert/lint) + rclone mount + vfs/refresh + SA 인증 (ADR-0029) | ✅ archive (2026-05-17) |
| **F5: `hermes_adapter`** | Hermes 호출 어댑터 — wikihub `wh:*` skill ↔ Hermes skill 시스템 정합화. F4 surface 의 결함 #12 lock | ⏸ 진행 예정 |
| `update_mode` | `install.sh --update` flag + Step 2 idempotent + systemd auto-redeploy. F4 의 결함 #A·#B·#C·#D 일괄 fix | ⏸ 진행 예정 |
| **F6: `vault_directory`** (v0.2.x) | NAS / 로컬 디렉토리 vault type, inotifywait 통합 | 후속 |

v0.1.0 acceptance = F4 (✅) + F5 + (선택) update_mode. v0.1.0 일괄 deployment 는 F5 완료 후 진행.

자세한 backlog (R15·R16 Could 8건 + 결함 surface) 는 [`features/backlog.md`](features/backlog.md) 참조.

---

## 참고 자료

### 핵심 개념
- **[LLM Wiki Pattern (Karpathy)](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)** — AI 에이전트가 지식을 축적·구조화하는 설계 패턴 (`docs/llm_wiki.md`에 사본)
- **[Karpathy Coding Guidelines](https://x.com/karpathy/status/2015883857489522876)** — LLM 코딩 행동 원칙 (`docs/karpathy-guidelines.md`에 사본)
- **[Architecture Decision Records (Nygard)](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)** — 본 리포의 ADR 컨벤션 출처

### 선행 시스템
- **[WikiCurate v0.2.6](https://github.com/im-dongseon/wikicurate)** — macOS 로컬 단일 vault 모델의 안정화 구현

### 예정 도구
- **[graphify](https://github.com/safishamsi/graphify)** — 위키 페이지 간 지식 그래프
- **[Hermes](#)** — Telegram 연동 에이전트 (외부 컴포넌트)

---

## 라이선스

[MIT License](LICENSE)

---

<div align="center">

Developed by **WikiHub Team**.

</div>
