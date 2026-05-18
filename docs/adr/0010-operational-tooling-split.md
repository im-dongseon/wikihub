# ADR-0010: 운영 도구 책임 분할 — install.sh + `/wh:setup` (deploy.sh 폐기, git 의존 없음)

- **Status**: Accepted
- **Date**: 2026-05-13 / 2026-05-18 (Note: yaml.example 복사 책임 ADR-0031 으로 이관)
- **Feature**: features/20260513_wikihub_schema_v1
- **Supersedes**: 없음 (F1 §4.8.6 deploy.sh 설계를 retract하지만 F1은 ADR가 아닌 archive 문서)
- **Superseded by**: 없음 (부분 supplement: ADR-0031 — yaml writer 책임만 reassign, 도구 split 결정은 유지)

> **Note (2026-05-18, feature `install_scope_reduction`)**: 본 ADR §"도구별 책임 매트릭스" line 38 (install.sh 가 `wikihub.yaml.example` 복사) + §"wikihub.yaml lifecycle" 단계 2 (line 49) + §"install.sh의 동작" step 7 (line 80) 의 **yaml.example 복사 책임은 ADR-0031 에 의해 `/wh:setup` Step 0 단독으로 이전됨**.
>
> 본 ADR 의 큰 결정 (`install.sh + /wh:setup` 2-도구 split, deploy.sh 폐기, git 의존 없음) 은 **유지**. yaml writer 책임만 reassign — install.sh 는 yaml 한 글자도 안 만짐. `/wh:setup` 의 Step 0 가 `wikihub.yaml.example` 을 template 으로 read → derived 5필드 patching → atomic write `$WIKIHUB_INSTANCE_ROOT/wikihub.yaml`.
>
> 본 Note 는 supersede 아님 — ADR-0031 의 `Partially supersedes: ADR-0010 §lifecycle step 2 + §step 7` 와 짝. 이 sub-decision 만 reassign + 큰 책임 split 결정은 활성.

## Context

F1 (`20260513_v030_initial_architecture`)의 §4.8.6은 dev box → OCI 정본 파일 sync용 `deploy.sh`를 F4 산출물로 정의했다(6단계 + 자동 롤백 + 수동 복원).

F2 Step 2에서 운영 도구 정리 도중 다음 단순화 surface됨:

- `deploy.sh`의 책임(정본 파일 push)은 **git pull로 자연 대체 가능** — git이 정본 sync의 표준 메커니즘이고 backup·rollback도 `git revert`로 1급 지원
- 그러나 운영 시 git 의존을 두지 않는 게 더 단순한 사용자 경험 (curl 1회 호출로 설치+업데이트)
- agent-측 설정(skill 등록, systemd unit 동기화, 검증)은 별도 명령(`/wh:setup`)이 책임
- `wikihub.yaml`은 정본이지만 lifecycle 명시 부재 — 누가 만들고 누가 편집하는지 흐림

이 시점에 운영 도구 4종(install.sh, /wh:setup, deploy.sh, git)과 wikihub.yaml의 책임을 재정의 필요.

## Considered Options

운영 도구 구성:

- **(α) F1 모델**: deploy.sh + install.sh + /wh:setup + git pull. 도구 4개
- **(β) git-pull 기반**: deploy.sh 폐기, install.sh + /wh:setup + git pull. 도구 3개
- **(γ) install.sh 중심**: deploy.sh 폐기, git 의존 없음, install.sh(install + update) + /wh:setup. 도구 2개

## Decision

**채택**: (γ) install.sh + /wh:setup, deploy.sh 폐기, git 의존 없음

### 도구별 책임 매트릭스 (정본)

| 도구 | 호출 빈도 | 호출 방법 | 책임 |
|---|---|---|---|
| **install.sh** | 1회 (신규 설치) + 반복 (업데이트) | `curl ...install.sh \| bash` | OS bootstrap (디렉토리·venv·deps) + agent 종류 입력 + `wikihub.yaml.example` 복사 + agent skill 등록 + 정본 파일(`_system/`·`scripts/`) **`https://github.com/im-dongseon/wikihub.git` 에서 fetch/갱신** (메인테이너 git 명령 호출 없음 — install.sh 내부에서 git clone 또는 tarball 다운로드 dispatch) |
| **/wh:setup** | 반복 (yaml/template 변경 시) | `agent -z "/wh:setup"` | 검증(yaml·OAuth·디렉토리·_state/) + systemd unit 생성·갱신 (F4 template + yaml 값 instance화) + skill 메타 갱신 + daemon-reload + (옵션) enable |
| **wikihub.yaml** | 정본 | 메인테이너 수기 편집 (`$EDITOR`) | vault·credentials_path·sync_interval_sec·lint_interval_hours 등 운영 값의 single source of truth |
| ~~deploy.sh~~ | 폐기 | — | install.sh + /wh:setup이 흡수 |
| ~~git pull~~ | 폐기 | — | install.sh가 정본 fetch 책임 (git 의존 제거) |

### wikihub.yaml lifecycle

| 단계 | 누가 | 무엇을 | 결과 |
|---|---|---|---|
| 1 | F4 | `wikihub.yaml.example` 작성 (정본 schema) | 정본 파일에 포함, install.sh 배포 대상 |
| 2 | install.sh | `wikihub.yaml.example` → `/opt/wikihub/wikihub.yaml` 복사 (이미 있으면 skip — never overwrite) | placeholder 상태 |
| 3 | 메인테이너 (외부) | OAuth pickle 발급(macOS) → scp(OCI) | `/opt/wikihub/.credentials/token_*.pickle` |
| 4 | 메인테이너 | `$EDITOR /opt/wikihub/wikihub.yaml` — vault id, type, paths, intervals 등 입력 | 운영 가능 상태 |
| 5 | `/wh:setup` | yaml 검증 + 디렉토리 ensure + systemd unit 생성·갱신 + skill 메타 갱신 | systemd timer 활성 가능 |
| 6 | 메인테이너 또는 `/wh:setup --enable` | `systemctl --user enable --now ...` | 운영 시작 |

### install.sh의 동작 (개략 — F4 구체화)

**Source repository**: `https://github.com/im-dongseon/wikihub.git` (정본 source of truth)

**버전 기준**: git tag `latest` (이동 태그, 항상 현재 stable release 가리킴). 특정 버전 install·rollback은 `v0.1.0` 같은 명시 tag.

```bash
# 신규 설치 또는 업데이트 (default = tag latest)
curl -fsSL https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh | bash

# 또는 특정 버전 (install·rollback)
curl -fsSL https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh | bash -s -- --version v0.1.0
```

install.sh가 수행:
1. 기존 설치 detect (`/opt/wikihub/_system/VERSION` 존재 → 업데이트 모드, 미존재 → 신규 모드)
2. 사용자 prompt — 설치 경로(default `/opt/wikihub`), agent 종류(default `hermes` — ADR-0012 매핑으로 `binary`·`oneshot_args` default 자동 채움)
3. Python venv + 의존성 라이브러리 (신규 모드에서만, 업데이트는 deps 변경 시 install)
4. 정본 파일(`_system/`·`scripts/`) fetch — **메인테이너 git 명령 호출 없이** install.sh 내부에서 처리:
   - **기본 ref = tag `latest`** (또는 `--version <tag>` 지정 시 해당 tag)
   - git이 OCI 서버에 있으면: `git clone --depth 1 --branch <ref> https://github.com/im-dongseon/wikihub.git` (임시 디렉토리) → 필요 경로만 복사
   - git이 없으면: GitHub tarball URL(`https://github.com/im-dongseon/wikihub/archive/refs/tags/<ref>.tar.gz`) → curl + tar
   - 구체 dispatch는 F4 install.sh 구현 책임. **소스 URL·ref는 항상 위 GitHub repo + tag**
5. 다운로드 후 `_system/VERSION` 파일을 읽어 update 상황 보고 (예: "v0.1.0 → v0.1.1 업데이트")
6. user 파일 보존: `wikihub.yaml`·`.credentials/`·`_state/`·`wiki/`·`logs/` 절대 덮어쓰지 않음
7. `wikihub.yaml.example` → `wikihub.yaml` 복사 (신규 모드, 없을 때만)
8. agent에 wh: skill 등록 (agent별 메커니즘 dispatch). `wikihub.yaml.agent.invocation` 매핑(ADR-0012)도 본 단계에서 설정
9. 안내 출력 — "yaml 편집 후 `agent -z '/wh:setup'` 실행"

**`latest` tag 관리** (메인테이너 release 절차 — F4가 명문화):
- 새 stable release 시: 버전 tag 생성(`v0.1.1`) + `latest` tag를 해당 commit으로 이동(`git tag -f latest <commit> && git push -f origin latest`)
- `latest`는 항상 force-update. 버전 tag는 immutable

### 운영 절차 비교

| 시나리오 | F1 모델 | 본 결정 |
|---|---|---|
| 신규 설치 | (메인테이너가 git clone) → install.sh → deploy.sh → yaml 편집 → /wh:setup | `curl ...install.sh \| bash` → yaml 편집 → `/wh:setup` |
| 정본 파일 업데이트 | dev box `git push` → OCI `git pull` → deploy.sh 또는 /wh:setup | `curl ...install.sh \| bash` (재실행) → (필요 시) `/wh:setup` |
| yaml 변경 | `$EDITOR yaml` → /wh:setup | 동일 |
| 운영 도구 수 | 4 | 2 |
| git 의존 | 메인테이너 OCI 서버에 git 필요 | 불필요 (curl만) |

**이유**:

- **사용자 경험 단순화**: `curl ...install.sh | bash` 1회 호출로 설치+업데이트. git·deploy.sh 학습 부담 0
- **운영 도구 절감**: 4개 → 2개
- **OCI 서버 의존 최소화**: bash + curl만 있으면 충분. git 미설치 환경에서도 동작
- **install/update 일관성**: 같은 install.sh가 양면 책임 → 절차 통일 → 메인테이너 mental load 감소
- **(α) 기각**: deploy.sh의 6단계는 git + /wh:setup으로 자연 분산 — 별도 도구 중복
- **(β) 기각**: git pull은 멘탈 모델 추가 (git 사용법 + clone 위치). curl 한 줄이 더 단순. backup·rollback은 install.sh가 release tag 기반으로 처리 (이전 버전 재설치)

## Consequences

- **긍정**:
  - 운영 도구 2개 (install.sh + /wh:setup) — 단순
  - 신규 설치·업데이트가 동일 curl 1줄 — 학습 부담 0
  - OCI 서버에 git 불필요
  - install.sh의 release tag 인자로 특정 버전 install·rollback 가능
  - wikihub.yaml lifecycle 6단계로 명시화 — 메인테이너 절차 추적 가능

- **부정/제약**:
  - **install.sh 복잡도 증가**: install + update + version detect + agent dispatch + agent별 skill 등록 dispatch — 다른 OS 도구의 책임을 흡수
  - **release 관리 부담**: install.sh가 release tag·tarball을 신뢰. GitHub release 발급 절차 필수 (F4가 정의)
  - **버전 관리 명시**: `_system/VERSION` 파일이 정본 (v0.2.6 패턴 lift). install.sh가 비교
  - **rollback 정밀도**: install.sh가 user 파일은 안 만지지만 정본 파일은 통째 교체 — 부분 rollback 어려움 (대안: 이전 tag로 재설치)

- **후속 영향**:
  - **F2 추가**: `_system/VERSION` 파일 (단일 라인: `0.1.0`) — v0.2.6 패턴 lift
  - **F2 `_system/commands/setup.md`**: 슬림화 — install.sh로 이관된 venv·deps·partial mode 항목 제거
  - **F4 산출물 재정의**:
    - 신규: `install.sh` (root, executable)
    - 신규: `wikihub.yaml.example` (root)
    - 신규: `_system/systemd/*.{service,timer}` template (placeholder 포함)
    - 폐기: `deploy.sh`
  - **F1 archive 영향**: F1 §4.8.6 deploy.sh 인터페이스는 영속 archive 기록으로 남되 본 ADR이 supersede 명시
  - **재검토 트리거**: install.sh의 release fetch가 부적합한 환경(인터넷 격리 등) 등장 시 git-pull 모델 fallback ADR 발의

### install.sh precondition (O1 — F4 정본)

install.sh가 실행 가능한 OS·도구 minimum:
- OS: Ubuntu 22.04+ (ARM 또는 x86_64). 다른 Linux distro는 best-effort
- Python: `python3.11+`
- 필수 도구: `curl`, `bash`, `tar`
- 선택 도구: `git` (있으면 git clone, 없으면 tarball)

precondition 미충족 시 install.sh는 fail-fast + remediation 안내 (예: `apt install python3.11 curl tar`).

### install.sh skill 등록 dispatch (B5 — F4 정본, agent별 분기)

| agent type | 등록 명령 (잠정) | 검증 상태 |
|---|---|---|
| `hermes` | `hermes skill add --name <prefix><cmd> --playbook /opt/wikihub/_system/commands/<cmd>.md` | v0.1.0 default, F4 검증 |
| `codex` | TBD — F4가 codex-cli 문서 확인 후 본 표 갱신 | 미검증 |
| `gemini` | TBD | 미검증 |
| `copilot` | TBD | 미검증 |
| `custom` | 메인테이너가 `wikihub.yaml.agent.skill_register_cmd` 직접 명시 (v0.1.0 미지원, future) | n/a |

**등록 실패 detection** (ADR-0011 fallback과 연동):
- 시도 1: skill_prefix = `wh:`로 등록
- exit code != 0 OR stderr에 `invalid name`·`colon`·`namespace` keyword 포함 → 시도 2
- 시도 2: skill_prefix = `wh-`로 등록 + `wikihub.yaml.agent.skill_prefix = "wh-"` 기록
- 두 번 모두 실패 → install.sh stderr 경고 + `agent.skill_prefix: null` 기록 → 메인테이너에게 "/wh:setup 후 수기 register 안내"

**idempotency**: install.sh를 update 모드로 재호출 시 skill은 덮어쓰기 (agent별 etag·hash 비교는 F4가 결정 — 기본은 force-update).

### schema migration (O5 — F4 정본)

- `wikihub.yaml.version` 키가 정본 (`version: 1`). install.sh가 update 모드에서 yaml의 version과 fetch된 `_system/`의 `VERSION` 호환성 확인
- v1 → v2 같은 incompatible 변경 시: install.sh가 schema migration guide URL 안내 + fail-fast (메인테이너가 yaml 수기 마이그레이션 후 재실행)
- 동일 major version 내 키 추가는 install.sh가 기본값으로 yaml에 append (메인테이너 review 권장 안내)
- v0.1.0 → v0.1.x는 동일 schema 가정. v1.0 진입 시 migration 정책 정식 확정

## Note (2026-05-18, feature `hermes_adapter` F5)

본 ADR 의 §"도구별 책임 매트릭스" 의 install.sh Step 6 책임 (`hermes skill add --name <prefix><cmd> --playbook /opt/wikihub/_system/commands/<cmd>.md`) 명세화:

- **install.sh `_step6_agent_skill`** 책임 — Hermes 의 SKILL.md materialization (frontmatter + `_system/commands/<cmd>.md` 본문 결합) + `~/.hermes/config.yaml` 의 `skills.external_dirs` 패치 + 등록 검증. ADR-0032 정본.
- **playbook path 정본** — `_system/commands/<cmd>.md` 유지 (ADR-0006 정합, F5 의 5.2.B 채택). `_system/skills/_generated/wh-<cmd>/SKILL.md` 는 install-time build artifact (git untracked).
- **Hermes 미설치 시** — `_step6_agent_skill` 가 detect → `SKIP_SYSTEMD_RENDER` flag → systemd unit render/enable 둘 다 skip. install.sh exit 0. 운영자가 Hermes 설치 후 재호출 권장 (CR2-CRIT-1 해결).

## Note (2026-05-19, feature `dir_layout_refactor`) — §Decision 갱신 (ADR-0034)

Dev/Ops Zone 분리의 path 구체화:

- **install.sh** = `$WIKIHUB_SRC` (XDG `~/.local/share/wikihub/src/`) 책임 — git clone target, 모든 시스템 코드 (install.sh, _system/, scripts/, _system/skills/_generated/).
- **`/wh-setup`** = `$WIKIHUB_HOME` (`~/wikihub/`) 책임 — 운영 자산 dir. yaml materialize + state + wiki/vault.

이전 model 의 `WIKIHUB_HOME` (repo 의미) + `WIKIHUB_INSTANCE_ROOT` (운영 의미) 가 ADR-0034 로 변수 swap. 본 ADR-0010 의 책임 분리 원칙 보존 + path 변경만 정합.
