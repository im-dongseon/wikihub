# Analysis & Design — dir_layout_refactor

- **feat_id**: `dir_layout_refactor`
- **plan**: [plan.md](./plan.md) (Step 1 lock — δ-2 XDG src 채택, 2026-05-19)
- **버전**: v3 (R3 closure review 반영 — narrow patch: ADR-0029 진단 정정 + 잔존 항목 명시)
- **approved**: 2026-05-19 (Step 3 진입)
- **R2 산출**: [design_review_1.md](./design_review_1.md) (CR1 spec, CRIT 5 / HIGH 8), [design_review_2.md](./design_review_2.md) (CR2 SRE, CRIT 5 / HIGH 7)
- **R3 산출**: [design_review_3.md](./design_review_3.md) (CR3-1 spec closure), [design_review_4.md](./design_review_4.md) (CR3-2 SRE closure)
- **선행 ADR**: ADR-0010 (operational tooling split), ADR-0020 (Python venv XDG), ADR-0023 (install.sh curl-pipe + safety guard), ADR-0029 (Service Account auth + credentials path), ADR-0030 (update workflow orchestration), ADR-0031 (yaml template materialization), ADR-0032 (Hermes skill registration)
- **현재 main HEAD**: `eb4b6ed` (F5 hermes_adapter archive — v0.1.0 acceptance 달성)

> **핵심 운영 invariant** (plan.md 에서 lock): 운영자 일상 자산 (`~/wikihub/wiki/`·`~/wikihub/_state/`·`~/wikihub/wikihub.yaml`) 가 `--force-fresh` 또는 update_mode 의 어떤 단계에서도 손실되지 않음. 시스템 코드 (`~/.local/share/wikihub/src/`) 만 git fetch+reset / wipe 대상.

---

## 1. 배경 및 목적

### 1.1 현행 모델의 mental model 결함

v0.1.0 acceptance 달성 직후 운영자 surface 의문 (2026-05-19):

> 실제 사용하는건 instance 인데 이게 왜 `wikihub` 가 아니지?

현 layout 의 naming 은 **code-first**:
- `WIKIHUB_HOME = ~/wikihub/` (repo, 시스템 코드)
- `WIKIHUB_INSTANCE_ROOT = ~/wikihub-instance/` (운영 데이터)

OSS 일반 convention (`~/<tool>/` = tool's repo, e.g. `rustup`·`nodenv`) 따른 결과. 그러나 wikihub 는 "tool" 보다 **데이터 + 자동화 시스템** 의 결합체이므로:

- 운영자 일상 자산 = wiki 페이지·yaml·state (현 `wikihub-instance/`)
- 시스템 코드 = install.sh·_system/·scripts/ (현 `wikihub/`)
- 사용자 mental model 의 "wikihub" = 운영 자산. 시스템은 그것을 돌리는 엔진.

본 feature 가 layout 을 invert — `~/wikihub/` 가 운영 자산이 되고, 시스템 코드는 `~/.local/share/wikihub/src/` (XDG 표준) 로 이동.

### 1.2 본 feature 의 목적

운영자 mental model 의 자연화 + 1 home directory 정리 + multi-machine 자연 지원 + `--force-fresh` 의 운영 자산 wipe 위험 근본 차단.

선행 feature 의 정본성 보존:
- ADR-0006 (agent orchestration), ADR-0010 (dev/ops split — XDG 로 더 명시화), ADR-0020 (venv XDG — 완벽 정합), ADR-0030 (update workflow — src dir 만 reset), ADR-0031 (yaml materialization — yaml 위치 변경만), ADR-0032 (Hermes external_dirs — path 갱신)

### 1.3 v0.1.0 release 전 architectural refactor

**정정**: v0.1.0 acceptance 는 달성됐으나 **deployment 미배포** — 운영자 base 0 건. 본 feature 가 v0.1.0 release tag 전 마지막 architectural refactor. backwards-incompat 변경 (env 명명 swap, layout invert) 의 비용 = 0 (운영자 base 부재). v0.1.0 release 후의 migration 안내는 단순화 — 신규 install 의 기본 layout 으로 적용. release 후 새 운영자에게는 v0.1.0 이 유일한 history.

본 feature 의 migration helper 는 **메인테이너 자체의 dev box 환경** (~/wikihub-instance/ 가 존재할 수 있음) + 미래의 v0.2.x release 시점 대비. v0.1.0 release 시점 운영자에게는 default install 만 진행.

---

## 2. Step 1 lock 의 결정 사항

δ-2 XDG src 채택 (plan.md §Step 1 lock):

- **운영 dir**: `~/wikihub/` (사용자 일상 자산)
- **시스템 코드**: `~/.local/share/wikihub/src/` (XDG, ADR-0020 venv 와 동일 root)

```
~/wikihub/                                    # 운영 자산 (data-first)
├── wikihub.yaml                              # 운영 정본
├── wiki/                                     # ★ wiki 콘텐츠
│   ├── index.md
│   ├── _lint/  analyses/  concepts/  entities/
│   └── sources/<vault>/
├── vault/<vault>/                            # FUSE mount (rclone)
├── _state/<vault>/{cursor,file_map,last_sync,pending_ingest}.json
└── (선택) .credentials/                       # ADR-0029 (또는 ~/.credentials/wikihub/ 권장 — 5.5 미결)

~/.local/share/wikihub/                       # XDG data dir (ADR-0020 venv 정합)
├── src/                                      # 시스템 코드 (current ~/wikihub/ content)
│   ├── .git/
│   ├── _system/  scripts/  install.sh  ...
│   ├── INSTALLED_VERSIONS.json
│   └── .venv_path
└── venv/                                     # 현행 유지 (ADR-0020)

~/.config/systemd/user/                       # 현행 유지 (ADR-0021)
~/.config/rclone/rclone.conf                  # 현행 유지
~/.hermes/                                    # 외부 도구 (ADR-0032 external_dirs)
~/.credentials/wikihub/                       # 현행 유지 (ADR-0029, repo 외부)
```

---

## 3. 현행 진단

### 3.1 install.sh 의 WIKIHUB_HOME 기본값 (L:43~ 추정)

```bash
: "${WIKIHUB_HOME:=$HOME/wikihub}"
: "${WIKIHUB_INSTANCE_ROOT:=$HOME/wikihub-instance}"
```

→ code-first 가정. 본 feature 가 둘 다 갱신 (또는 env 명명 변경).

### 3.2 install.sh self-replace (L:1640~)

```bash
# curl-pipe → fresh clone → exec ~/wikihub/install.sh "$@"
```

→ self-replace target 이 `~/wikihub/install.sh`. δ-2 후에는 `~/.local/share/wikihub/src/install.sh` 로 변경.

### 3.3 ADR-0023 safety guard 3개

```bash
1. WIKIHUB_HOME 이 system path (/·/usr·/etc·/opt·/home·$HOME·empty) 면 exit 1
2. .git 서브디렉토리 존재 시에만 wipe 허용
3. git remote.origin.url 이 im-dongseon/wikihub 일 때만 wipe
```

→ δ-2 후 wipe 대상은 `~/.local/share/wikihub/src/` — 같은 safety guard 적용 가능 (system path 차단·.git·origin 검증). 그러나 본 위치는 시스템 dir 라 system path 차단 list 갱신 필요 (`/usr` 등 외에 `$HOME/.local` prefix detect 시 운영자 confirm — 강화).

### 3.4 ADR-0030 update_mode 의 git fetch+reset target

```bash
_step2_update() {
    cd "$WIKIHUB_HOME"
    git fetch ...
    git reset --hard ...
}
```

→ `WIKIHUB_HOME` semantic 이 src dir 로 정의 변경되면 자연 정합. 단 env 이름 변경 옵션 (B/C) 채택 시 변수 rename 동반.

### 3.5 ADR-0031 wikihub.yaml.example 의 `instance.root`

```yaml
instance:
  root: ~/wikihub-instance
```

→ `~/wikihub/` 으로 변경. derived 4필드 patching 정합.

### 3.6 ADR-0029 SA credentials path (v3 — CR3-NEW-CRIT-1 정정)

**진단 (실재 상태)**:

- **ADR-0029 §Decision line 52 본문**: `배포: scp → OCI ~/wikihub-instance/.credentials/sa_<vault_id>.json → chmod 0600. wikihub.yaml 의 credentials_path 가 본 파일 지정.` → **instance 내부** 가 ADR-0029 의 정본 default.
- **CLAUDE.md** (메인테이너 가이드, 이전 conversation context): `SA JSON kept in ~/.credentials/wikihub/sa_<project>.json (outside repo working tree)` → **외부** 가 보안 권장.
- 두 문서 mismatch — ADR-0029 본문 vs CLAUDE.md 권장. v0.1.0 운영 시점에 surface 됐어야 할 invariant 결함.

**본 feature 의 책임 추가** (v3 정정):

v0.1.0 release 전 layout refactor 가 자연스러운 ADR-0029 path 정합 기회. 결정:

- **§Decision 본문 갱신** — ADR-0029 line 52 의 default 를 외부 (`~/.credentials/wikihub/sa_<vault_id>.json`) 로 lock. CLAUDE.md 정합. 운영 자산 dir (`~/wikihub/`) 내부 보안 비밀 미배치 — 격리 강화.
- wikihub.yaml.example 의 `credentials_path` default 동시 갱신.
- 본 변경은 v0.1.0 운영자 base 의 yaml 운영본 (instance 내부 path) 와 mismatch — migration helper (5.3) 가 운영자 yaml 의 `credentials_path` value detect → 안내 (자동 mv 안 함, 운영자가 보안 자산 위치 명시 인지 필요).

→ §7.1 ADR-0029 row 처리 격상: "Note 추가" → "**§Decision 본문 변경**" (CR3-NEW-CRIT-1 closure).

### 3.7 render_systemd_units.py 의 path helper

```python
def _wikihub_home() -> Path:
    return Path(os.environ.get("WIKIHUB_HOME", str(Path.home() / "wikihub"))).resolve()

def _instance_root_default() -> Path:
    return Path(os.environ.get("WIKIHUB_INSTANCE_ROOT", str(Path.home() / "wikihub-instance"))).resolve()
```

→ env 명명 + default 갱신. systemd unit template 의 모든 path substitution 정합.

### 3.8 ADR-0032 의 external_dirs path

```yaml
# ~/.hermes/config.yaml
skills:
  external_dirs:
    - /home/user/wikihub/_system/skills/_generated     # 현행
```

→ 변경 후:
```yaml
    - /home/user/.local/share/wikihub/src/_system/skills/_generated
```

`_step6_agent_skill _patch_hermes_external_dirs` 의 realpath 비교 + marker comment 갱신 — 운영자가 마이그레이션 시 기존 entry 제거 + 신규 entry 추가.

---

## 4. 옵션 분석 (잔존 미결 5건)

### 4.1 미결 #1 — env 명명 (A/B/C)

**(A) 신규 `WIKIHUB_SRC` 도입, 기존 변수는 의미 swap**:
- `WIKIHUB_HOME` 의미 = 운영 자산 (변경)
- `WIKIHUB_INSTANCE_ROOT` deprecated (호환성 유지: env 존재 시 warning + alias 처리)
- 신규 `WIKIHUB_SRC` = 시스템 코드 dir
- 장점: 외부 인터페이스 단순. yaml.example 의 `instance.root` 만 갱신
- 단점: `WIKIHUB_HOME` semantic 변경이 운영자 혼동 (이전 의미 = repo, 이후 = 운영)

**(B) 변수 swap 완전 — `WIKIHUB_HOME` ↔ `WIKIHUB_SRC`**:
- `WIKIHUB_HOME` = 운영 자산
- `WIKIHUB_INSTANCE_ROOT` 폐기 (강제 — env 사용 시 fail-fast + 안내)
- 신규 `WIKIHUB_SRC` = 시스템 코드 dir
- 장점: 깔끔한 의미. 이전 의미 잔존 없음
- 단점: backwards-incompat. v0.1.0 운영자가 env 명시 사용 시 break

**(C) 둘 다 deprecated + 새 env (`WIKIHUB_DATA` + `WIKIHUB_SRC`)**:
- `WIKIHUB_HOME`·`WIKIHUB_INSTANCE_ROOT` deprecated
- 신규 명명: `WIKIHUB_DATA` (운영) + `WIKIHUB_SRC` (시스템)
- 장점: 의미 가장 명확 ("DATA" 라는 단어 자체)
- 단점: 변경 폭 최대. v0.1.0 운영자가 두 변수 다 rename 필요

**권장**: **(B) 변수 swap** — v0.1.0 release 전 architectural refactor 이라 backwards-incompat 수용 가능. `WIKIHUB_HOME` 의 의미가 "내 wikihub 자산" 으로 자연화. README 의 install snippet + ADR 갱신 안내로 운영자 mental model 일관.

> 단점 완화: v0.1.x 운영자가 `WIKIHUB_INSTANCE_ROOT` env 사용 중인지 install.sh 가 detect → "v0.1.0 release 전 migration: `WIKIHUB_INSTANCE_ROOT` 폐기, `WIKIHUB_HOME` 으로 통일됨" 명시 + 자동 mapping (5.3 migration 의 일부).

### 4.2 미결 #2 — migration 자동화 (A/B/C)

**(A) install.sh 자동 detect + 명시 confirm 후 자동 이전**:
- detect 조건: `$HOME/wikihub-instance` 존재 + `$HOME/wikihub` 가 wikihub repo (origin 검증 통과)
- 자동 이전:
  1. `~/wikihub/` (repo) → `~/.local/share/wikihub/src/` (mv)
  2. `~/wikihub-instance/` → `~/wikihub/` (mv)
- 운영자 명시 confirm (5초 wait) 또는 NONINTERACTIVE=1 자동 동의
- 장점: 운영자 부담 최소. 동일 명령 (curl-pipe) 으로 install + migrate
- 단점: install.sh 의 복잡도 증가 (~50줄 신규). 실패 시 partial state 위험

**(B) install.sh 가 detect 후 안내만 출력**:
- 운영자가 직접 mv 명령 실행
- 장점: install.sh 단순 유지
- 단점: 운영자 step 증가. 실수 가능성 (path typo 등)

**(C) 별도 `scripts/migrate_layout.sh` helper**:
- install.sh 가 legacy detect → helper 호출 prompt (또는 자동 호출)
- helper 는 명시적 mv 절차 + rollback (실패 시 원상 복귀)
- 장점: install.sh 책임 분리. helper 단독 실행 가능 (운영자 신중한 검증 가능)
- 단점: 파일 1개 증가 + cross-call 복잡도

**권장**: **(C) `scripts/migrate_layout.sh` 신규 helper** — install.sh 의 책임 분리 (curl-pipe 의 1줄 명령 정합 유지) + helper 단독 실행 가능 (운영자 신중함). install.sh 가 legacy detect 시 helper 호출 prompt + NONINTERACTIVE 자동 동의.

### 4.3 미결 #3 — curl-pipe self-replace destination

(layout lock + env 명명 결정 후 명확):

```bash
# curl-pipe 의 단계
curl https://.../install.sh | bash
  └→ /tmp/install.sh (curl 의 stdout buffer)
      └→ Step 0: bash -c "curl-pipe detect"
      └→ Step 1: ensure ~/.local/share/wikihub/src 존재
      └→ Step 2: git clone --branch <ref> --depth 1 https://github.com/im-dongseon/wikihub.git ~/.local/share/wikihub/src
      └→ Step 3: exec ~/.local/share/wikihub/src/install.sh "$@"     # self-replace
```

destination 변경 외 의미론 동일. ADR-0023 §Decision 의 self-replace race window (R10 HIGH-4) 분석 그대로 정합.

### 4.4 미결 #4 — multi-instance 시나리오

기존 패턴 유지 + 강화:

```bash
# 단일 instance (default)
WIKIHUB_HOME=~/wikihub WIKIHUB_SRC=~/.local/share/wikihub/src curl ... | bash

# multi-instance (prod·staging 동시)
WIKIHUB_HOME=/var/wikihub-prod WIKIHUB_SRC=/var/wikihub-src/prod curl ... | bash
WIKIHUB_HOME=/var/wikihub-staging WIKIHUB_SRC=/var/wikihub-src/staging curl ... | bash
```

- src dir 도 운영자 명시 분리 가능 (`WIKIHUB_SRC` env override)
- default 는 single-instance 가정 → `~/wikihub/` + `~/.local/share/wikihub/src/`
- systemd user units 의 SyslogIdentifier 가 instance 구분 필요 — 현행 `wikihub-vault-%i` (vault_id) 만 — multi-instance 시점에 instance label 도입 검토 (v0.2.x)

### 4.5 미결 #5 — `.credentials/` 위치

**(A) `~/wikihub/.credentials/`** — 운영 자산의 일부 (data-first 정합)
**(B) `~/.credentials/wikihub/`** — repo 외부 유지 (현 보안 결정, CLAUDE.md)

권장: **(B) 유지** — 보안 격리 (외부 자산 mutate 패턴, ADR-0029 정합). data-first naming 은 운영 자산 시각화 목적이지 보안 보호 영역까지 inversion 의도 아님. SA JSON 같은 비밀은 별도 보안 디렉토리에 격리가 표준.

→ wikihub.yaml.example 의 `credentials_path` default = `~/.credentials/wikihub/sa_<vault>.json` (변경 없음, 현행 권장 유지).

---

## 5. 설계

### 5.1 env 명명 (v2 — (B) 변수 swap + silent bug detect)

| env | Before | After |
|---|---|---|
| `WIKIHUB_HOME` | repo dir (`~/wikihub`) | **운영 자산 dir (`~/wikihub`)** — semantic swap |
| `WIKIHUB_INSTANCE_ROOT` | 운영 자산 dir (`~/wikihub-instance`) | **폐기** (detect 시 fail-fast + migration 안내) |
| `WIKIHUB_SRC` (신규) | — | **시스템 코드 dir (`~/.local/share/wikihub/src`)** |

env override 패턴 (multi-instance 등) 그대로 가능 — `WIKIHUB_HOME=/var/wikihub-prod WIKIHUB_SRC=/var/wikihub-src/prod`.

#### 5.1.1 `WIKIHUB_HOME` semantic swap silent bug detect (CR1-CRIT-3, CR2-HIGH-3 — v2)

v0.1.x 운영자가 `WIKIHUB_HOME` env 를 명시 설정한 경우 (예: shell rc 의 `export WIKIHUB_HOME=$HOME/wikihub` 등) 의미 변경 후 silent bug — 이전 의미 (repo) 로 사용한 path 가 신 의미 (운영) 로 해석됨.

**detect 분기** (`install.sh _step0_env_semantic_check`, 신규):

```bash
# detect 시그널: WIKIHUB_HOME 가 명시 설정됐고 + 그 path 에 .git 존재 + origin = im-dongseon/wikihub
# = "v0.1.x 의미로 WIKIHUB_HOME 설정된 운영자" 확정
if [[ -n "${WIKIHUB_HOME_EXPLICIT:-${WIKIHUB_HOME+set}}" ]] && \
   [[ -d "$WIKIHUB_HOME/.git" ]] && \
   (cd "$WIKIHUB_HOME" 2>/dev/null && git config --get remote.origin.url 2>/dev/null | grep -q "im-dongseon/wikihub"); then
    err "WIKIHUB_HOME=$WIKIHUB_HOME 가 v0.1.x 의미 (repo) 로 설정됨."
    err "v0.1.0 부터 WIKIHUB_HOME 의 의미가 운영 자산 dir 로 변경됨 (data-first)."
    err "마이그레이션:"
    err "  1. unset WIKIHUB_HOME  또는  export WIKIHUB_HOME=<운영 자산 dir, 예: \$HOME/wikihub>"
    err "  2. export WIKIHUB_SRC=<시스템 코드 dir, 예: \$HOME/.local/share/wikihub/src>"
    err "  3. scripts/migrate_layout.sh 호출 (legacy detect 자동 진입 가능)"
    exit 1
fi
```

NONINTERACTIVE 모드 자동 detect 도 동일 — silent 진행 안 함 (운영자 명시 환경 변경 요구). detect 가 false-positive 시 운영자가 env unset 후 재시도.

#### 5.1.2 `WIKIHUB_SRC` 명명 검토 (CR1-HIGH-N)

대안: `WIKIHUB_REPO` (의미: git repo, 명확). 단 본 feature 채택 = `WIKIHUB_SRC`:
- "src" = source code (시스템 소스). data 와 대비 명확
- XDG `XDG_DATA_HOME` 의미와 충돌 없음 (XDG 는 system-wide 표준, wikihub 의 SRC 는 local)
- v0.1.0 release 전 architectural refactor 이라 후속 rename 비용 낮음

명명 자체는 v2 lock — 본 ADR-0034 (신설) 의 sub-decision 으로 결정 정본화.

### 5.2 install.sh 변경 (v2 — entry step 순서 명시 + safety guard ADR §Decision 갱신)

#### 5.2.1 install.sh 진입 단계 순서 정본 (CR2-CRIT-4)

curl-pipe 또는 직접 호출 시 install.sh 의 entry path. **Step 0a/0b/0c 의 순서 정본**:

```
Step 0a — env semantic check (5.1.1)
  ├─ WIKIHUB_INSTANCE_ROOT env 설정 시 fail-fast (5.3.3)
  └─ WIKIHUB_HOME 가 v0.1.x semantic (repo) 인지 detect → fail-fast + 안내

Step 0b — legacy layout detect (5.3.2)
  ├─ $HOME/wikihub/.git 존재 + $HOME/wikihub-instance 존재 + origin 검증
  └─ TRUE → migrate_layout.sh 호출 prompt → exec helper / FALSE → 정상 진행

Step 0c — curl-pipe 모드 detect
  ├─ BASH_SOURCE[0] 부재 → curl-pipe fresh bootstrap
  │   ├─ ensure $WIKIHUB_SRC parent exists ($HOME/.local/share/wikihub/)
  │   ├─ git clone --branch <ref> --depth 1 ... "$WIKIHUB_SRC"
  │   └─ exec "$WIKIHUB_SRC/install.sh" "$@"     # self-replace
  └─ BASH_SOURCE[0] = "$WIKIHUB_SRC/install.sh" → 정상 main() 진입

Step 1 ~ Step N (기존 패턴)
```

Step 0a 가 0b 보다 먼저인 이유: env-level mismatch 가 더 fundamental — legacy detect 진입 전 env 가 정합돼야 helper 호출 시 변수 의미가 일관됨.

#### 5.2.2 default 정의 (L:43~ 부근)

```bash
: "${WIKIHUB_HOME:=$HOME/wikihub}"                  # 의미 변경: 운영 자산
: "${WIKIHUB_SRC:=$HOME/.local/share/wikihub/src}"  # 신규
# WIKIHUB_INSTANCE_ROOT 사용 시 fail-fast (Step 0a)
```

#### 5.2.3 self-replace + curl-pipe (Step 0c)

```bash
git clone --branch <ref> --depth 1 --filter=blob:none --sparse \
    https://github.com/im-dongseon/wikihub.git "$WIKIHUB_SRC"
cd "$WIKIHUB_SRC" && git sparse-checkout set _system scripts install.sh wikihub.yaml.example README.md LICENSE
exec "$WIKIHUB_SRC/install.sh" "$@"
```

(sparse-checkout list 는 install_scope_reduction (ADR-0031 §Decision A) 정합 — 변경 없음)

#### 5.2.4 _step2_update — cwd 변경

```bash
cd "$WIKIHUB_SRC" && git fetch ... && git reset --hard ...
```

unstaged guard, in-flight grace, rollback trap 모두 cwd 가 src dir 라 자연 정합 (ADR-0030 §sub-1·2·3·4 변경 없음).

#### 5.2.5 safety guard 4번째 추가 — ADR-0023 §Decision 갱신 (CR1-CRIT-2)

ADR-0023 §Decision 본문의 "safety guard 3개" 명세는 본 feature 의 4번째 guard 추가로 **§Decision 본문 갱신** 필요 (Note 만 불충분). 신 safety guard list:

```bash
# wipe target = $WIKIHUB_SRC (변경)
# 1. system path 차단 — $WIKIHUB_SRC ∈ {/, /usr, /etc, /opt, /home, $HOME, ""} → exit 1
# 2. $WIKIHUB_SRC/.git 디렉토리 존재 검증
# 3. git remote.origin.url = im-dongseon/wikihub 검증
# 4. (신규) $WIKIHUB_SRC 의 prefix 가 $HOME/.local/share/wikihub/ 외 path 인 경우 NONINTERACTIVE=1 거부 + 명시 confirm 요구
#    — 운영자가 의도적 다른 위치 사용 (e.g. /var/lib/wikihub-src) 시에만 통과
```

(4) 의 의도: XDG path 외 wipe 는 default 가 아닌 명시 의도 — 운영자가 multi-instance 또는 특수 운영 환경에서만 사용. silent wipe 차단.

ADR-0023 §Decision §safety guard 항목 본 4건으로 갱신. ADR-0023 §Decision 의 "self-replace destination" 도 갱신 (`$WIKIHUB_HOME` → `$WIKIHUB_SRC`).

`--force-fresh` 의 wipe target = `$WIKIHUB_SRC` 만. `$WIKIHUB_HOME` (운영 자산) 은 wipe scope 외 — 별도 backup 불요, 운영자 데이터 절대 안전.

#### 5.2.6 systemd unit Environment matrix (CR2-CRIT-5)

systemd unit template 의 `Environment=` directive 가 path 포함. 매트릭스:

| Unit | Directive | Before | After |
|---|---|---|---|
| wikihub-vault@.service | `Environment=WIKIHUB_YAML=` | `{instance_root}/wikihub.yaml` | `{wikihub_home}/wikihub.yaml` |
| wikihub-vault@.service | `Environment=GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=` | `{credentials_path}` (yaml derive) | **변경 없음** (yaml.options.credentials_path 가 절대경로) |
| wikihub-vault@.service | `Environment=PATH=` | `{venv_path}/bin:...` | **변경 없음** (ADR-0020 venv 위치 보존) |
| wikihub-vault@.service | `WorkingDirectory=` | `{instance_root}` | `{wikihub_home}` |
| wikihub-vault@.service | `ExecStartPre=/bin/mkdir -p` | `{instance_root}` | `{wikihub_home}` |
| wikihub-vault@.service | `ExecStart={agent_invocation_for_wh_ingest}` | `... "/wh-ingest --vault %i"` | **변경 없음** (path 무관) |
| lint.service | `Environment=WIKIHUB_YAML=` | `{instance_root}/wikihub.yaml` | `{wikihub_home}/wikihub.yaml` |
| lint.service | `WorkingDirectory=`·`ExecStartPre=mkdir` | `{instance_root}` | `{wikihub_home}` |
| wikihub-mount@.service | `ExecStartPre=mkdir`·`ExecStart=rclone mount ... {instance_root}/vault/%i` | `{instance_root}` | `{wikihub_home}` |
| ops-alert.service | `ExecStartPre=mkdir`·`ExecStart=python {wikihub_home}/scripts/ops-alert.py` | `{wikihub_home}` (이전 의미 = repo) | **분리**: `WorkingDirectory={wikihub_home}` (운영) + `ExecStart={venv_path}/bin/python {wikihub_src}/scripts/ops-alert.py` (시스템 코드) |

→ `{wikihub_home}` substitution key 의 의미 변경 (이전 repo → 이후 운영). `{wikihub_src}` 신규. `{instance_root}` deprecated (alias of `{wikihub_home}` 로 호환 또는 완전 제거).

render_systemd_units.py 의 모든 substitution key 영향 (5.4 표 정합).

#### 5.2.6 venv path 정합 (ADR-0020 그대로)

`~/.local/share/wikihub/venv/` 변경 없음. `.venv_path` sidecar 는 `$WIKIHUB_SRC/.venv_path` 로 이동 (run-time 생성).

#### 5.2.7 INSTALLED_VERSIONS.json 위치

`$WIKIHUB_SRC/_system/INSTALLED_VERSIONS.json` (현 `~/wikihub/_system/INSTALLED_VERSIONS.json` 의 정합 mv).

### 5.3 migration 자동화 (v2 — SRE-grade detail 보강, CR2-CRIT-1·2·3 + HIGH 다수)

#### 5.3.1 `scripts/migrate_layout.sh` — phase marker state machine + mv-only backup + rollback trap

```bash
#!/usr/bin/env bash
# wikihub v0.1.x → v0.2.x layout migration helper.
# - phase marker state machine (재호출 시 resume)
# - mv-only (cp 없음, ENOSPC 회피)
# - rollback trap (ADR-0030 패턴)
# - rclone FUSE unmount + busy 처리
# - flock advisory (helper 단독 호출 race 차단)

set -euo pipefail

LEGACY_REPO="${LEGACY_WIKIHUB_REPO:-$HOME/wikihub}"
LEGACY_INSTANCE="${LEGACY_WIKIHUB_INSTANCE:-$HOME/wikihub-instance}"
NEW_HOME="${WIKIHUB_HOME:-$HOME/wikihub}"
NEW_SRC="${WIKIHUB_SRC:-$HOME/.local/share/wikihub/src}"
PHASE_FILE="$HOME/.local/state/wikihub/migrate_layout.phase"   # state machine marker
LOCK_FILE="$HOME/.local/state/wikihub/migrate_layout.lock"

mkdir -p "$(dirname "$PHASE_FILE")"

# ─── flock advisory ────────────────────────────────────────────────
exec 200>"$LOCK_FILE"
flock -nx 200 || { echo "ERROR: 다른 migration 인스턴스 실행 중" >&2; exit 2; }

# ─── phase marker ──────────────────────────────────────────────────
# values: pre-stop | stopped | unmounted | mv-src-done | mv-home-done | hermes-patched | render-done | start-done | DONE
get_phase() { [[ -f "$PHASE_FILE" ]] && cat "$PHASE_FILE" || echo "pre-stop"; }
set_phase() { echo "$1" > "$PHASE_FILE"; }

# ─── rollback trap (ADR-0030 패턴) ─────────────────────────────────
PRE_PHASE=""
_rollback_if_failed() {
    local exit_code=$?
    [[ $exit_code -eq 0 ]] && return 0
    local current; current=$(get_phase)
    case "$current" in
        pre-stop|stopped|unmounted)
            # mv 전 — systemd 재시작 만
            _systemd_start_legacy
            ;;
        mv-src-done)
            # src mv 후 home mv 전 — src 만 reverse
            [[ -d "$NEW_SRC" && ! -d "$LEGACY_REPO/.git" ]] && mv "$NEW_SRC" "$LEGACY_REPO"
            _systemd_start_legacy
            ;;
        mv-home-done)
            # 양쪽 mv 후 — 양쪽 reverse
            [[ -d "$NEW_HOME/wikihub.yaml" || -d "$NEW_HOME/wiki" ]] && mv "$NEW_HOME" "$LEGACY_INSTANCE"
            [[ -d "$NEW_SRC/.git" ]] && mv "$NEW_SRC" "$LEGACY_REPO"
            _systemd_start_legacy
            ;;
        hermes-patched|render-done)
            # hermes config + systemd render 까지 진행 — 운영자 수동 복구 필요
            err "migration 후반 단계 실패. ~/.hermes/config.yaml.wikihub-bak.* 수동 검토 권장"
            err "phase: $current (${PHASE_FILE} 보존)"
            ;;
    esac
    err "migration failed at phase: $current"
    exit "$exit_code"
}
trap '_rollback_if_failed' ERR EXIT INT TERM HUP

# ─── Step 1. systemd stop (CR2-CRIT-1 — in-flight grace, ADR-0030 §sub-1) ─────
_systemd_stop_legacy() {
    local phase; phase=$(get_phase)
    [[ "$phase" != "pre-stop" ]] && return 0   # idempotent resume
    info "Step 1: systemd stop sequence (15min in-flight grace)"
    # vault@*.timer 먼저 (새 fire 차단)
    systemctl --user stop 'wikihub-vault@*.timer' 2>/dev/null || true
    systemctl --user stop 'wikihub-lint.timer' 2>/dev/null || true
    # vault@*.service grace (mid-sync 자연 종료 대기, max 15min)
    timeout 900 systemctl --user stop 'wikihub-vault@*.service' 2>/dev/null || true
    systemctl --user stop 'wikihub-lint.service' 2>/dev/null || true
    # mount@ 마지막 (file_map 보호)
    systemctl --user stop 'wikihub-mount@*.service' 2>/dev/null || true
    systemctl --user reset-failed 'wikihub-*' 2>/dev/null || true
    set_phase "stopped"
}

# ─── Step 2. rclone FUSE unmount (CR2-CRIT-1) ──────────────────────
_unmount_vaults() {
    local phase; phase=$(get_phase)
    [[ "$phase" != "stopped" ]] && return 0
    info "Step 2: rclone FUSE unmount"
    for mp in "$LEGACY_INSTANCE"/vault/*/; do
        [[ -d "$mp" ]] || continue
        # mount 인지 확인 (mount | grep)
        if mount | grep -q " on $mp type fuse"; then
            # busy 시 retry × 6 (10s × 6 = 1min)
            local i=0
            while (( i < 6 )); do
                if fusermount3 -u "$mp" 2>/dev/null; then
                    break
                fi
                sleep 10; i=$((i+1))
            done
            if (( i == 6 )); then
                # 강제 lazy unmount fallback
                fusermount3 -uz "$mp" || true
            fi
        fi
    done
    set_phase "unmounted"
}

# ─── Step 3. mv src (LEGACY_REPO → NEW_SRC, CR2-CRIT-2: mv-only) ──
_mv_src() {
    local phase; phase=$(get_phase)
    [[ "$phase" != "unmounted" ]] && return 0
    info "Step 3: $LEGACY_REPO → $NEW_SRC"
    mkdir -p "$(dirname "$NEW_SRC")"
    # mv (atomic, ENOSPC 없음 — same filesystem 가정. cross-fs 시 cp+rm 자동)
    mv "$LEGACY_REPO" "$NEW_SRC"
    set_phase "mv-src-done"
}

# ─── Step 4. mv home (LEGACY_INSTANCE → NEW_HOME) ─────────────────
_mv_home() {
    local phase; phase=$(get_phase)
    [[ "$phase" != "mv-src-done" ]] && return 0
    info "Step 4: $LEGACY_INSTANCE → $NEW_HOME"
    # NEW_HOME 가 이미 존재하면 fail-fast (운영자 직접 처리 필요)
    if [[ -e "$NEW_HOME" ]]; then
        err "$NEW_HOME 가 이미 존재 — 수동 정합 필요. 진행 중단"
        return 1
    fi
    mv "$LEGACY_INSTANCE" "$NEW_HOME"
    set_phase "mv-home-done"
}

# ─── Step 5. Hermes config 갱신 (CR2-HIGH-8) ──────────────────────
_patch_hermes_external_dirs_migration() {
    local phase; phase=$(get_phase)
    [[ "$phase" != "mv-home-done" ]] && return 0
    info "Step 5: ~/.hermes/config.yaml 의 external_dirs 갱신"
    # install.sh 의 _patch_hermes_external_dirs reuse — flock + backup + sha256 PRE/POST
    # 단 본 migration 의 추가 책임: stale entry (= $LEGACY_REPO/_system/skills/_generated) 제거 + 신규 (= $NEW_SRC/_system/skills/_generated) 추가
    # marker comment 검사: stale entry 옆에 wikihub-managed marker 있으면 제거. operator-managed entry 는 보존
    "$VENV_PATH/bin/python3" "$NEW_SRC/scripts/_helpers/hermes_config_migrate.py" \
        --remove-stale "$LEGACY_REPO/_system/skills/_generated" \
        --add-new "$NEW_SRC/_system/skills/_generated"
    set_phase "hermes-patched"
}

# ─── Step 6. systemd unit render (신 path) ─────────────────────────
_render_systemd_new() {
    local phase; phase=$(get_phase)
    [[ "$phase" != "hermes-patched" ]] && return 0
    info "Step 6: systemd unit render (신 path)"
    export WIKIHUB_HOME="$NEW_HOME"
    export WIKIHUB_SRC="$NEW_SRC"
    "$VENV_PATH/bin/python3" "$NEW_SRC/scripts/_helpers/render_systemd_units.py" \
        --yaml "$NEW_HOME/wikihub.yaml" \
        --render --out "$HOME/.config/systemd/user/"
    systemctl --user daemon-reload
    set_phase "render-done"
}

# ─── Step 7. systemd start (재개) ──────────────────────────────────
_systemd_start_new() {
    local phase; phase=$(get_phase)
    [[ "$phase" != "render-done" ]] && return 0
    info "Step 7: systemd start (신 path)"
    # mount@ 먼저 — FUSE-ready 대기 후 vault@ start
    systemctl --user start 'wikihub-mount@*.service' 2>/dev/null || true
    sleep 5
    systemctl --user start 'wikihub-vault@*.timer' 2>/dev/null || true
    systemctl --user start 'wikihub-lint.timer' 2>/dev/null || true
    set_phase "start-done"
}

# ─── main ───────────────────────────────────────────────────────────
detect_legacy() {
    [[ -d "$LEGACY_REPO/.git" && -d "$LEGACY_INSTANCE" ]] \
        && (cd "$LEGACY_REPO" && git config --get remote.origin.url 2>/dev/null | grep -q "im-dongseon/wikihub")
}

main() {
    if ! detect_legacy; then
        info "v0.1.x layout 미detect — migration 불필요"
        set_phase "DONE"
        return 0
    fi
    PRE_PHASE=$(get_phase)
    info "phase resume from: $PRE_PHASE"
    _systemd_stop_legacy
    _unmount_vaults
    _mv_src
    _mv_home
    _patch_hermes_external_dirs_migration
    _render_systemd_new
    _systemd_start_new
    set_phase "DONE"
    trap - ERR EXIT INT TERM HUP   # rollback trap 해제 (success)
    ok "migration complete — phase: DONE"
}

main "$@"
```

#### 5.3.2 install.sh 의 legacy detect (Step 0b)

```bash
_step0_legacy_detect() {
    if [[ -d "$HOME/wikihub-instance" ]] && [[ -d "$HOME/wikihub/.git" ]] && \
       (cd "$HOME/wikihub" && git config --get remote.origin.url 2>/dev/null | grep -q "im-dongseon/wikihub"); then
        warn "v0.1.x layout detect — ~/wikihub (repo) + ~/wikihub-instance (data)"
        warn "v0.1.0 layout: ~/wikihub (data) + ~/.local/share/wikihub/src (repo)"
        if [[ -n "${WIKIHUB_NONINTERACTIVE:-}" ]] || _prompt_yn "migration helper 실행?"; then
            local helper="$HOME/wikihub/scripts/migrate_layout.sh"
            if [[ -f "$helper" ]]; then
                exec bash "$helper"
            else
                err "migrate_layout.sh 부재 — git pull 후 재시도 권장"
                exit 1
            fi
        else
            info "migration 거부 — 운영자 직접 호출 후 재시도"
            exit 0
        fi
    fi
}
```

#### 5.3.3 WIKIHUB_INSTANCE_ROOT env detect (Step 0a)

```bash
_step0_env_semantic_check() {
    if [[ -n "${WIKIHUB_INSTANCE_ROOT:-}" ]]; then
        err "WIKIHUB_INSTANCE_ROOT env 는 v0.1.0 부터 폐기. WIKIHUB_HOME 으로 통일."
        err "  마이그레이션: unset WIKIHUB_INSTANCE_ROOT && export WIKIHUB_HOME=<이전 INSTANCE_ROOT 값>"
        err "  ※ WIKIHUB_HOME 의 의미가 v0.1.0 release 전 변경 — 운영 자산 dir (이전 repo)"
        exit 1
    fi
    # 5.1.1 의 WIKIHUB_HOME semantic swap silent bug detect 도 본 step 에서 진행
    # ...
}
```

#### 5.3.4 helper 의 idempotency (CR1-CRIT-4 / CR2-CRIT-3)

phase marker state machine 으로 보장. 운영자가 중간 실패 후 재호출 시:
- `$PHASE_FILE` 의 phase value read
- 해당 phase 부터 resume
- 이미 완료된 step 은 idempotent skip

phase values: `pre-stop` → `stopped` → `unmounted` → `mv-src-done` → `mv-home-done` → `hermes-patched` → `render-done` → `start-done` → `DONE`

#### 5.3.5 backup 모델 — mv-only (CR2-CRIT-2)

ENOSPC 회피 위해 `cp -r` 모델 폐기. mv-only 사용:
- mv 는 atomic (same filesystem) + disk 사용 0
- cross-fs 시 mv 가 자동 cp+rm — 그래도 cp -r 후 별도 backup 보유보다 안전 (단 cross-fs 운영자는 매우 드묾)
- rollback 은 reverse mv 만 (rollback trap 의 phase-aware 분기, 5.3.1 의 _rollback_if_failed)
- 운영자 명시 backup 원할 시 helper 호출 전 직접 `cp -r` 권고 — README 안내

#### 5.3.6 rclone FUSE unmount (CR2-CRIT-1)

mv 전 vault 의 FUSE mount unmount 필수 — busy detect + retry + lazy fallback (5.3.1 의 `_unmount_vaults`).

#### 5.3.7 in-flight grace 정합 (CR2-CRIT-1 + CR1-CRIT-5)

ADR-0030 §sub-1 의 stop sequence 정본 따름:
- timer 먼저 stop (새 fire 차단)
- service grace (timeout 900 = 15min, mid-sync 자연 종료)
- mount@ 마지막 (file_map 보호)
- reset-failed 호출 (StartLimitBurst counter 초기화)

### 5.4 render_systemd_units.py 변경 (v2 — substitution key matrix)

#### 5.4.1 path helper 함수

```python
def _wikihub_src() -> Path:   # 신규 — 시스템 코드 dir (XDG)
    return Path(os.environ.get("WIKIHUB_SRC", str(Path.home() / ".local/share/wikihub/src"))).resolve()

def _wikihub_home() -> Path:  # 의미 변경 — 운영 자산 dir
    return Path(os.environ.get("WIKIHUB_HOME", str(Path.home() / "wikihub"))).resolve()

# _instance_root_default() 완전 제거 (또는 alias of _wikihub_home())
```

#### 5.4.2 substitution key matrix (v2 — 명시)

| key | Before semantic | After semantic | unit template 사용처 |
|---|---|---|---|
| `{wikihub_home}` | repo dir (시스템 코드) | **운영 자산 dir** | WorkingDirectory, ExecStartPre mkdir, Environment WIKIHUB_YAML |
| `{wikihub_src}` (신규) | — | **시스템 코드 dir** | ExecStart 의 Python scripts path |
| `{instance_root}` | 운영 자산 dir | **deprecated alias of {wikihub_home}** | 호환 — 신 template 은 사용 안 함 |
| `{venv_path}` | venv path | 변경 없음 (ADR-0020) | Environment PATH, ExecStart prefix |
| `{credentials_path}` | yaml derive | 변경 없음 (절대경로) | Environment |
| `{rclone_bin}`·`{rclone_config_path}` | system path | 변경 없음 | mount@ ExecStart |
| `{agent_invocation_for_wh_<skill>}` | agent invocation (5건) | 변경 없음 (ADR-0032/0033) | vault@·lint ExecStart |
| `{skill_prefix}` | wh- (ADR-0033) | 변경 없음 | (현 미사용 — slash 합성으로 변경됨, F5) |
| `{timeout_start_sec}` | yaml.agent.timeout_sec | 변경 없음 (F5) | TimeoutStartSec |
| `{remote_name_for_<vid>}`·`{rc_port_for_<vid>}` | yaml.vaults[*].options | 변경 없음 | mount@ ExecStart |
| `{sync_interval_sec}` | yaml.vaults[*] | 변경 없음 | vault@.timer OnUnitInactiveSec |
| `{lint_interval_hours}` | yaml.operations | 변경 없음 | lint.timer OnCalendar |

#### 5.4.3 systemd unit template 변경

```diff
# wikihub-vault@.service.template
-WorkingDirectory={instance_root}
+WorkingDirectory={wikihub_home}
-ExecStartPre=/bin/mkdir -p {instance_root}
+ExecStartPre=/bin/mkdir -p {wikihub_home}
-Environment=WIKIHUB_YAML={instance_root}/wikihub.yaml
+Environment=WIKIHUB_YAML={wikihub_home}/wikihub.yaml

# wikihub-mount@.service.template
-ExecStartPre=-/bin/fusermount3 -uz {instance_root}/vault/%i
+ExecStartPre=-/bin/fusermount3 -uz {wikihub_home}/vault/%i
-ExecStartPre=/bin/mkdir -p {instance_root}/vault/%i
+ExecStartPre=/bin/mkdir -p {wikihub_home}/vault/%i
-ExecStart={rclone_bin} mount {remote_name_for_%i}: {instance_root}/vault/%i ...
+ExecStart={rclone_bin} mount {remote_name_for_%i}: {wikihub_home}/vault/%i ...

# lint.service.template — 동일 패턴

# ops-alert.service — 시스템 코드 path 분리 (5.2.6 매트릭스)
-ExecStart={venv_path}/bin/python {wikihub_home}/scripts/ops-alert.py
+ExecStart={venv_path}/bin/python {wikihub_src}/scripts/ops-alert.py
```

#### 5.4.4 alias 호환 (transition 안전망)

`_SafeDict` 의 `__missing__` 에 `instance_root` 가 들어오면 `wikihub_home` 으로 fallback 처리 — 운영자가 직접 template 편집한 경우 (`{instance_root}` 잔존) 의 silent break 방지:

```python
class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        if key == "instance_root":
            # transition alias (v0.2.x) — deprecation warning
            sys.stderr.write(f"WARN: {{instance_root}} deprecated, use {{wikihub_home}}\n")
            return self["wikihub_home"]
        raise KeyError(key)
```

v0.3.x 에서 본 alias 제거 검토.

### 5.5 wikihub.yaml.example 갱신

```yaml
instance:
  root: ~/wikihub                       # 변경 (이전 ~/wikihub-instance)
  ...

vaults:
  - id: gdrive
    local_path: ~/wikihub/vault/gdrive  # instance.root 의 subdir
    options:
      credentials_path: ~/.credentials/wikihub/sa_gdrive.json   # 보안 격리 유지 (5.5 미결 → (B) 채택)
```

### 5.6 `_system/wiki-schema.md` 디렉토리 트리 갱신

(현재 `_system/`·`wikihub.yaml.example`·`README.md`·`AGENTS.md` 등 다수 path 표기 변경)

### 5.7 ADR Notes (cross-feature 정합)

- ADR-0010 — operational tooling split 의 path 구체화 (XDG src) Note
- ADR-0020 — venv XDG 와 src XDG 통합 정합 Note
- ADR-0023 — self-replace destination 변경 + safety guard 4번째 추가 Note
- ADR-0029 — credentials_path default 정책 유지 명시
- ADR-0030 — git fetch+reset target 이 $WIKIHUB_SRC Note
- ADR-0031 — instance.root default 변경 Note
- ADR-0032 — external_dirs path 변경 (migration 시 자동 갱신) Note
- 신규 ADR-0034 (선택) — XDG layout 결정 정본화 — 위 6 ADR 의 cross-cutting 결정이라 신규 ADR 권장

### 5.8 README.md 갱신

- install snippet 의 path 안내 (단일 `~/wikihub/` 만 visible)
- 디렉토리 구조 다이어그램 갱신
- v0.1.x → v0.2.x migration 안내 (운영자 명시 step)
- `WIKIHUB_HOME` semantic 변경 명시 (이전 의미 보존, deprecation 안내)

---

## 6. 개정 전/후 비교

### 6.1 env 변수

| 변수 | Before (v0.1.0 acceptance) | After (v0.1.0 release 후, ADR-0034) |
|---|---|---|
| `WIKIHUB_HOME` | repo dir | **운영 자산 dir** |
| `WIKIHUB_INSTANCE_ROOT` | 운영 자산 dir | **폐기 — fail-fast + 안내** |
| `WIKIHUB_SRC` | — | **신규: 시스템 코드 dir** |

### 6.2 디렉토리 위치

| 자산 | Before | After |
|---|---|---|
| repo (.git, install.sh, _system, scripts) | `~/wikihub/` | `~/.local/share/wikihub/src/` |
| wikihub.yaml | `~/wikihub-instance/wikihub.yaml` | `~/wikihub/wikihub.yaml` |
| wiki/ | `~/wikihub-instance/wiki/` | `~/wikihub/wiki/` |
| vault/ (mount) | `~/wikihub-instance/vault/` | `~/wikihub/vault/` |
| _state/ | `~/wikihub-instance/_state/` | `~/wikihub/_state/` |
| .credentials/sa_*.json | `~/.credentials/wikihub/sa_*.json` (권장) | **변경 없음** |
| venv | `~/.local/share/wikihub/venv/` | **변경 없음** (ADR-0020) |
| systemd user units | `~/.config/systemd/user/` | **변경 없음** |
| Hermes external_dirs | `~/wikihub/_system/skills/_generated/` | `~/.local/share/wikihub/src/_system/skills/_generated/` |

### 6.3 호출 예 (curl-pipe)

| 시나리오 | Before | After |
|---|---|---|
| fresh install | `curl ... \| bash` → `~/wikihub/` clone | `curl ... \| bash` → `~/.local/share/wikihub/src/` clone + `~/wikihub/` 생성 |
| update | 동일 명령 → `~/wikihub/` 의 git fetch+reset | 동일 명령 → `~/.local/share/wikihub/src/` 의 git fetch+reset |
| `--force-fresh` | `~/wikihub/` wipe + clone (운영 자산 `~/wikihub-instance/` 외부라 안전) | `~/.local/share/wikihub/src/` wipe + clone (운영 자산 `~/wikihub/` 별도 dir 라 절대 안전) |
| migration (v0.1.0 dev box → v0.1.0 release 후) | — | `scripts/migrate_layout.sh` 또는 install.sh 의 legacy detect 분기 |

---

## 7. 연계 룰/스킬 정합성 검토

### 7.1 ADR 영향 매트릭스 (v2 — CR1-CRIT-1·2 + HIGH-1·2·3 반영)

| ADR | 영향 | 처리 (v2) |
|---|---|---|
| **ADR-0006** | unified orchestration | 영향 없음 |
| **ADR-0010** | operational tooling split | **§Decision 갱신** (Note 만 불충분 — Dev/Ops Zone 분리의 정본 영역) — install.sh = src dir (`$WIKIHUB_SRC`) 책임, `/wh-setup` = data dir (`$WIKIHUB_HOME`) 책임. dir 분리의 path semantics 변경 명시 |
| **ADR-0020** | Python venv XDG | **§Decision 갱신** — venv 위치 그대로 (`~/.local/share/wikihub/venv/`). 추가 명세: **src 도 동일 XDG root 공유** (`~/.local/share/wikihub/src/`). XDG_DATA_HOME 정합. ADR-0034 (신설) 의 sub-decision 중 하나로 cross-reference |
| **ADR-0023** | install.sh curl-pipe + safety guard | **§Decision 본문 변경** (Note 만 불충분 — CR1-CRIT-2) — (a) self-replace destination = `$WIKIHUB_SRC/install.sh`. (b) wipe target = `$WIKIHUB_SRC` (운영 자산 `$WIKIHUB_HOME` wipe scope 외). (c) **safety guard 4번째 추가** — `$WIKIHUB_SRC` 의 prefix 가 `$HOME/.local/share/wikihub/` 외이면 NONINTERACTIVE 거부 + 명시 confirm |
| **ADR-0029** | Service Account credentials path | **§Decision 본문 변경** (v3 — CR3-NEW-CRIT-1 정정). ADR-0029 line 52 의 default path `~/wikihub-instance/.credentials/sa_<vid>.json` (instance 내부) → `~/.credentials/wikihub/sa_<vid>.json` (외부, CLAUDE.md 보안 권장 정합). 운영 자산 dir 내부 비밀 미배치 — 격리 강화. wikihub.yaml.example 의 default 동시 갱신. v0.1.x 운영자의 instance 내부 credentials 잔존 시 helper 가 안내 (자동 mv 안 함 — 운영자 보안 자산 위치 명시 인지) |
| **ADR-0030** | update workflow orchestration | **§Decision 갱신** — `_step2_update` cwd = `$WIKIHUB_SRC`. 4 sub-decision 모두 cwd 변경만 정합 — sub-1 stop sequence·sub-2 unstaged guard·sub-3 rollback trap·sub-4 ref resolution chain 의 모든 git 명령이 `$WIKIHUB_SRC` 에서 실행 |
| **ADR-0031** | yaml template materialization | **§Decision 갱신** — `instance.root` default = `~/wikihub` (변경). derived 4필드 patching catalog (§Decision B) 의 값 표현 변경: `instance.root` → `$WIKIHUB_HOME`, `vaults[*].local_path` → `$WIKIHUB_HOME/vault/<vid>`, `vaults[*].options.mount_path` → 동일. schema version 본 변경에 따라 v1 → v1 (key 변경 없음, 값 의미 변경 — schema version bump 불요 §Decision E 정합) |
| **ADR-0032** | Hermes skill registration policy | **§Decision 갱신** + Note — external_dirs path = `$WIKIHUB_SRC/_system/skills/_generated`. 4 sub-decision 중 sub-3 (marker comment + realpath 비교) 가 migration helper 에도 적용 — stale wikihub entry 자동 식별 + 제거. 운영자가 마커 부재로 등록한 다른 wikihub-related path 는 보존 (warn-only) |
| **ADR-0033** | skill prefix `wh-` lock | 영향 없음 |
| **ADR-0034 (신규 — 권장 lock)** | XDG layout 결정 정본화 (4 sub-decision) | **신설** — 본 feature 의 architectural decisions 정본:<br/>**sub-1**: data-first naming (`~/wikihub/` = 운영 자산, `~/.local/share/wikihub/src/` = 시스템)<br/>**sub-2**: env (B) 변수 swap (`WIKIHUB_HOME` semantic 변경, `WIKIHUB_INSTANCE_ROOT` 폐기, `WIKIHUB_SRC` 신규)<br/>**sub-3**: migration 자동화 (C) — `scripts/migrate_layout.sh` helper + install.sh Step 0a/0b/0c entry 순서<br/>**sub-4**: backup 모델 — mv-only + phase marker state machine + rollback trap (cp-based backup 폐기, ENOSPC 회피) |

본 feature 의 ADR 영향:
- §Decision 갱신 6건 (ADR-0010·0020·0023·0030·0031·0032)
- Note 추가 1건 (ADR-0029)
- 신설 1건 (ADR-0034)
- 영향 없음 2건 (ADR-0006·0033)

update_mode 동급 분량 (ADR 7건 변경).

### 7.2 hermes_adapter (F5) 정합

ADR-0032 의 `external_dirs` 가 `$WIKIHUB_SRC/_system/skills/_generated/` 로 path 변경. migration helper 가 ~/.hermes/config.yaml 의 stale entry 제거 + 신규 entry 추가. install.sh `_step6_agent_skill _patch_hermes_external_dirs` 는 realpath 비교 + marker comment 정합 — path 만 변경되면 자동 재인식.

### 7.3 update_mode (ADR-0030) 정합

`_step2_update` 의 cwd 가 `$WIKIHUB_HOME` (이전) → `$WIKIHUB_SRC` (이후). git fetch+reset 가 src dir 한정. rollback trap 의 PRE_UPDATE_REF 도 src dir 기반. update_mode 의 fresh path 도 `$WIKIHUB_SRC` 에 clone.

### 7.4 install_scope_reduction (ADR-0031) 정합

`/wh-setup` Step 0 의 yaml materialize 대상 = `$WIKIHUB_HOME/wikihub.yaml` (운영 자산 dir). derived 4필드:
- `instance.root` → `$WIKIHUB_HOME` (자기참조 변경 — 운영자가 yaml 편집 시 명시 가능)
- `vaults[*].local_path` → `$WIKIHUB_HOME/vault/<vault_id>`
- `vaults[*].rclone_remote_name` (변경 없음)
- `vaults[*].options.mount_path` → `$WIKIHUB_HOME/vault/<vault_id>`

derive 식 변경만 — patching 로직 자체는 그대로.

---

## 8. 미결 사항 (Step 2 v1 후)

### 8.1 v1 에서 권장 lock 된 항목 (사용자 확인 필요)

| ID | 결정 | 비고 |
|---|---|---|
| #1 env 명명 | (B) 변수 swap — `WIKIHUB_HOME` 의미 변경 + `WIKIHUB_SRC` 신규 + `WIKIHUB_INSTANCE_ROOT` 폐기 | backwards-incompat (v0.1.0 release 전 architectural refactor 이라 수용) |
| #2 migration 자동화 | (C) 별도 `scripts/migrate_layout.sh` helper + install.sh 의 legacy detect 분기 | 책임 분리 + 운영자 신중함 |
| #3 self-replace destination | `$WIKIHUB_SRC/install.sh` | 자명 |
| #4 multi-instance | 현행 env override 패턴 유지 + `WIKIHUB_SRC` 도 명시 분리 가능 | 변경 없음 |
| #5 `.credentials/` 위치 | (B) `~/.credentials/wikihub/` 외부 유지 | ADR-0029 보안 결정 보존 |

### 8.2 Step 3 VM 실측 의존 (3건)

| ID | 항목 | 검증 |
|---|---|---|
| M-1 | systemd user unit 의 path substitution 정합 (`{wikihub_src}` 추가) | V1 — render_systemd_units.py + 새 template substitution 검증 |
| M-2 | migration helper 의 in-flight grace + rollback 정합 (update_mode 패턴 reuse) | V3 — 운영 중 instance 의 migration 시뮬레이션. systemd stop → mv → render → start |
| M-3 | Hermes external_dirs path 갱신의 운영자 자산 보존 (~/.hermes/config.yaml 의 stale entry 제거 시 운영자 다른 skill 등록 entry 손상 X) | V4 — config.yaml 의 다른 external_dirs entry 보존 검증 |

### 8.3 ADR-0034 신설 vs 7건 Note 분산

옵션:
- **(가) 각 ADR Note 분산** — 변경 최소. 단 cross-cutting 결정이라 추후 trace 시 분산
- **(나) ADR-0034 신설** (XDG layout 정본화) — Note 는 cross-reference 만, 결정 정본은 ADR-0034 본문

Step 2 v2 에서 lock 권장 — 본 v1 은 둘 다 명시.

---

## 9. Definition of Done

### 9.1 Step 2 종료 조건

- [x] 본 v1 의 multi-model design review (R≥2) — CR1 spec + CR2 SRE
- [ ] 잔존 미결 5건 중 v1 권장안 의 사용자 lock (특히 #1 env 명명 backwards-incompat 수용 여부)
- [ ] ADR-0034 신설 여부 lock
- [ ] 사용자 승인 (`approved: 2026-XX-XX` 마커)

### 9.2 Step 3 종료 조건 (구현)

**산출물 — repo tracked**:
- [ ] `install.sh` — env default 변경 + self-replace destination + safety guard 4번째 + legacy detect + helper 호출 분기 (~80~150줄)
- [ ] `scripts/migrate_layout.sh` (신규) — systemd stop + backup + mv + render + start (~100~150줄)
- [ ] `wikihub.yaml.example` — `instance.root` default 변경
- [ ] `_system/wiki-schema.md` — 디렉토리 트리 갱신 (대폭)
- [ ] `_system/commands/setup.md` — ADR-0031 derived 필드 정합
- [ ] `scripts/_helpers/render_systemd_units.py` — `_wikihub_src()` 신규 + path substitution 확장
- [ ] systemd unit template — `{wikihub_src}` substitution + path 정합 (~5건)
- [ ] `README.md` — install snippet + 디렉토리 구조 + migration 안내 (대폭)
- [ ] `.gitignore` — path 영향 검토 (현 `.venv_path` 등 sidecar)

**ADR — repo tracked**:
- [ ] ADR-0010·0020·0023·0029·0030·0031·0032 Note 갱신 (7건)
- [ ] (선택) ADR-0034 (XDG layout 결정 정본) 신설

**version bump**:
- [ ] `_system/VERSION` v0.1.0 유지 (v0.1.0 release 전 internal refactor — bump 불필요)

### 9.3 VM 테스트 (Step 3 자가 검증)

| V<N> | 환경 | 검증 항목 | PASS 기준 |
|---|---|---|---|
| V1 | VM-A (fresh, Hermes 설치) | curl-pipe install — `~/.local/share/wikihub/src/` clone + `~/wikihub/` 생성 | (1) `~/wikihub/wikihub.yaml` materialize. (2) `~/.local/share/wikihub/src/.git/` 존재. (3) `~/.local/share/wikihub/src/install.sh` exists. (4) systemd unit render. (5) Hermes external_dirs 패치 = `~/.local/share/wikihub/src/_system/skills/_generated/` realpath |
| V2 | VM-A | update_mode — `~/.local/share/wikihub/src/` 의 git fetch+reset | `~/wikihub/` 의 운영 자산 변경 없음. src 만 reset |
| V3 | VM-B (legacy v0.1.x layout — `~/wikihub/` repo + `~/wikihub-instance/` data) | migration helper 호출 | (1) systemd stop. (2) `~/wikihub-instance.pre-migration.<ts>` backup. (3) `~/wikihub/` → `~/.local/share/wikihub/src/` mv. (4) `~/wikihub-instance/` → `~/wikihub/` mv. (5) ~/.hermes/config.yaml external_dirs 갱신. (6) systemd render + start 재개. (7) vault@.service fire 성공 |
| V4 | VM-A | --force-fresh 의 wipe scope | (1) `~/.local/share/wikihub/src/` wipe + 신규 clone. (2) `~/wikihub/` (운영 자산) **변경 없음**. 운영자 데이터 보존 |
| V5 | VM-A | WIKIHUB_INSTANCE_ROOT env 사용 시 fail-fast | install.sh exit 1 + 안내 ("v0.1.0 부터 폐기, WIKIHUB_HOME 으로 통일") |
| V6 | VM-A | multi-instance — `WIKIHUB_HOME=/tmp/wikihub-test WIKIHUB_SRC=/tmp/wikihub-src` | (1) /tmp/wikihub-src 에 clone. (2) /tmp/wikihub-test 에 운영 자산. (3) `~/wikihub/` 영향 0 |
| V7 | VM-A | Hermes external_dirs migration | ~/.hermes/config.yaml 의 기존 stale entry (`~/wikihub/_system/...`) 제거 + 신규 entry 추가. **다른 도구 (codex 등) 의 entry + operator-managed entry (marker 부재) 는 보존** |
| **V8 (신규, v2)** | VM-B (legacy) | helper partial failure resume | migration 중간 단계 (예: mv-src-done) 에서 의도적 kill -9 → 재호출 시 phase marker resume → 정상 완료. phase: pre-stop / stopped / unmounted / mv-src-done / mv-home-done / hermes-patched / render-done / start-done / DONE 매트릭스 검증 |
| **V9 (신규, v2)** | VM-B (legacy) | rclone FUSE busy unmount | mid-sync 중 helper 호출 — fusermount3 -u retry × 6 (60s) 후 lazy fallback (`fusermount3 -uz`). 운영 자산 보존 |
| **V10 (신규, v2)** | VM-B (legacy) | mv ENOSPC simulation | LEGACY_INSTANCE 가 큰 데이터 (disk 80%+) — mv-only 모델 정합 검증. cp-r 폐기로 ENOSPC 발생 안 함 |
| **V11 (신규, v2)** | VM-A | systemd Environment matrix 정합 | rendered unit 의 Environment line grep — `WIKIHUB_YAML={wikihub_home}/wikihub.yaml` (운영 dir), `ExecStart={venv_path}/bin/python {wikihub_src}/scripts/...` (시스템 dir) 정합 |

### 9.4 Step 4 R≥2 code review

- CR1 spec — ADR 정합 + env 명명 backwards-incompat 영향 + migration 흐름 + safety guard 4번째
- CR2 SRE — migration in-flight grace + Hermes config 갱신 시 다른 도구 영향 + multi-instance race + `_system/VERSION` v0.1.0 보존의 update_mode detect 시그널 영향

---

## 10. Out of Scope (본 feature 범위 밖)

- v0.1.x 운영자 base 의 자동 OTA migration (운영 시점 명시 호출 요구 — 본 feature 는 helper 제공만)
- `WIKIHUB_HOME=$HOME` 같은 edge case (운영자 명시 + safety guard 차단)
- Windows / non-XDG OS 호환성 — Linux only (ADR-0020 정합)
- credentials_path 의 secret management 도입 (vault·1Password 등) — v0.2.x 별도 feature
- systemd user unit 의 instance label substitution (multi-instance 운영자 식별) — v0.2.x

---

## 변경 이력

- **v1** (2026-05-19): 초안. δ-2 XDG src layout 전제. 잔존 미결 5건 옵션 비교 + 권장 (#1 B / #2 C / #3 자명 / #4 현행 유지 / #5 (B) ADR-0029 보존). ADR 7건 영향 + 1건 신규 후보.

- **v2** (2026-05-19): R2 design review (CR1 spec / CR2 SRE) 반영.
  - **CRIT 10건 해결**:
    - CR1-CRIT-1 — §3.6 ADR-0029 진단 정정 (yaml.example default 가 v0.1.0 의 잘못된 값, ADR-0029 §Decision 본문은 외부 유지)
    - CR1-CRIT-2 — §5.2.5·§7.1 ADR-0023 처리 격상 (Note → **§Decision 본문 변경**) + safety guard 4번째 lock
    - CR1-CRIT-3 + CR2-HIGH-3 — §5.1.1 `WIKIHUB_HOME` semantic swap silent bug detect (`_step0_env_semantic_check`)
    - CR1-CRIT-4 + CR2-CRIT-3 — §5.3.4 helper idempotency phase marker state machine
    - CR1-CRIT-5 + CR2-CRIT-1 — §5.3.7 systemd in-flight grace + §5.3.6 rclone FUSE unmount retry (busy 처리)
    - CR2-CRIT-2 — §5.3.5 backup mv-only 모델 (cp -r 폐기, ENOSPC 회피) + 5.3.1 의 reverse-mv rollback
    - CR2-CRIT-4 — §5.2.1 install.sh entry order 정본 (Step 0a/0b/0c)
    - CR2-CRIT-5 — §5.2.6 + §5.4.2 systemd unit Environment= directive matrix 명시
  - **핵심 HIGH 해결**:
    - ADR-0034 신설 lock (4 sub-decision 묶음)
    - §5.3.1 의 rollback trap (ADR-0030 패턴 적용) + flock advisory
    - §5.4.4 `instance_root` deprecated alias (transition 안전망)
    - §7.1 의 ADR §Decision 갱신 6건 + Note 1건 + 신설 1건 매트릭스 명시
    - §9.3 V8/V9/V10/V11 신규 (partial failure / busy unmount / ENOSPC / Environment matrix 정합)
  - **잔존 미결 (Step 3 backport)**: CR1-MED 6건 + LOW 5건 + CR2-MED 6건 + LOW 3건 — 모두 Step 3 구현 시 backport 가능 항목

- **v3** (2026-05-19): R3 closure review (CR3-1 spec / CR3-2 SRE) narrow patch.
  - **CR3-NEW-CRIT-1 fix** — §3.6 ADR-0029 진단 reverse direction 정정. v2 §3.6 가 "ADR-0029 본문 default = 외부" 라 적었으나 실제 line 52 = instance 내부. v3 가 본 mismatch 정확 surface 후 본 feature 가 ADR-0029 §Decision 본문을 외부로 변경 (CLAUDE.md 보안 권장 정합). §7.1 ADR-0029 row 처리 "Note 추가" → "§Decision 본문 변경" 격상
  - **잔존 (Step 3 backport)** — CR3-1 신규 1 HIGH-1 (Step 0a fail-fast 시 helper 호출 path 안내) · HIGH-2 (phase value validation) · 3 MED · 1 LOW (변경이력 표현 정확도). CR3-2 신규 3 HIGH (V11 측정 명령·phase file multi-instance·alias warning log volume) · 3 MED (INSTALLED_VERSIONS.json bump·hermes backup retention·ops-alert template diff) · 2 LOW (helper 의 `$VENV_PATH` 미정의·`_systemd_start_legacy` 미정의)
  - **CR3 종합 판단**: CR3-1 v3 patch 후 Step 3 진입. CR3-2 v2 그대로 Step 3 진입 가능 — 신규 결함 모두 Step 3 backport.
