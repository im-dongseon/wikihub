# F4 code review R1 (feature-dev:code-reviewer — Step 4 first)

리뷰어: feature-dev:code-reviewer
대상: Step 3 구현 결과 (7 신규 + 5 수정)
정본: analysis_and_design.md v5 + ADR-0015~0024 (9건)

---

## 1. ADR 9건 ↔ 구현 매핑 검증

| ADR | 구현 위치 | 평가 |
|---|---|---|
| ADR-0015 (gws CH2 + latest F1) | `install.sh` Step 4, L216~261 | **부분** — CH2 채택, V8 hand-check 미완 라벨 명시. 단 pipe 파이프라인 `set -euo pipefail` 충돌(CRIT-1) |
| ADR-0017 (gws stderr regex) | F3 `lib/errors.py` (본 라운드 변경 없음) | **정합** — ADR Status `Proposed` 유지 |
| ADR-0018 (install.sh 단일) | `install.sh` 존재, `deploy.sh` 없음 | **정합** |
| ADR-0019 (per-vault + Python substitution) | `_system/systemd/*.template` + `setup.md` 치환변수 9건 | **부분** — `{lint_interval_hours}` timer template 부재(HIGH-1). `{wikihub_home}` export 책임 누락(MED-1) |
| ADR-0020 (venv `~/.local/share/wikihub/venv`) | `install.sh` L32, Step 3 L186~205 | **정합** — 사이드카 `.venv_path` 정합 |
| ADR-0021 (linger + V12 fallback) | `install.sh` Step 7 L308~323 | **정합** — idempotent skip + 비대화 NOPASSWD + 대화 `/dev/tty` |
| ADR-0022 (E3 + 흐름 역전) | `setup.md` Step 4 변경 + Step 6 신설 | **부분** — Step 6 exit 75 분기 spec 충돌(CRIT-2) |
| ADR-0023 (curl-pipe + clean install) | `install.sh` Step 0~2 | **부분** — top-level if 의 bootstrap 미호출 + args 소실(HIGH-2). normalize 생략(MED-2) |
| ADR-0024 (fatal contract) | `state.py` + `vault-fetch.py` + `ops-alert.py` + `notify.py` | **부분** — notify 순서 어긋남(HIGH-3), dedup spec 미이행(HIGH-4), `~` expand 누락(HIGH-5) |

---

## 2. 새 결함 surface

### [CRIT][NewBug] CRIT-1: Step 4 gws 버전 조회 파이프라인이 `set -euo pipefail` 와 충돌

**파일**: `install.sh:216~217`

```bash
GWS_VERSION="$(curl ... \
    | grep '"tag_name"' | head -1 | sed -E '...')"
```

`grep` 이 패턴 미발견 시 exit 1 → pipefail 로 스크립트 전체 즉시 종료. L218 의 빈 문자열 체크 도달 못 함.

**수정**: 파이프 체인 마지막에 `|| true` 추가.

### [CRIT][SpecMismatch] CRIT-2: setup.md Step 6 exit 75 분기 spec 내부 충돌

**파일**: `_system/commands/setup.md:Step 6` + `analysis_and_design.md §4.4.3` + `ADR-0022`

- ADR-0022 본문: "exit 75 + cursor 존재" 시 bootstrap_allowed 환원
- analysis_and_design.md §4.4.3 (4): "Y + exit 0 시에만" 환원

두 spec 내부 충돌. 정본은 ADR-0022 — setup.md 의 출력 산출물 표 `Y + exit 0 시만` 을 `Y + exit 0/75 with cursor` 로 통일 필요.

### [HIGH][NewBug] HIGH-1: `lint.service.template` + `lint.timer.template` 미존재

**파일**: `_system/systemd/` (lint unit 부재)

`setup.md` 의 "lint.timer 는 항상 enable" + `{lint_interval_hours}` 치환변수 등록 — 그러나 lint unit template 자체가 없음. `/wh:setup` Step 4 의 lint.timer enable 단계가 빌드 실패.

**수정**: lint.service.template + lint.timer.template 신규 작성.

### [HIGH][NewBug] HIGH-2: top-level if 의 `bootstrap_clone_then_exec` 미호출 + CLI args 소실

**파일**: `install.sh:71~79` + `main:372~374`

top-level if 블록이 NONINTERACTIVE 설정만 하고 bootstrap 호출 안 함 → 실제 호출은 `main` 안. 그런데 CLI 파싱이 이미 top-level (L36~47) 에서 완료 → `bootstrap_clone_then_exec "$@"` 의 `"$@"` 가 비어 있음.

운영자가 `curl ... | bash -s -- --gws-version 1.0.0` 으로 인자 전달 시 self-replace 후 인자 사라짐.

**수정**: CLI 파싱 전 원본 args 를 별도 배열에 보존 후 bootstrap 에 전달.

### [HIGH][NewBug] HIGH-3: `notify_via_hermes` 호출 순서가 spec 반대

**파일**: `scripts/vault-fetch.py:140~154`

spec (`analysis_and_design.md §4.7`): `notify_via_hermes` → `save_last_failure` 순서.
구현: `save_last_failure` → `notify_via_hermes` 순서.

v0.1.0 에서는 stub 이라 무영향 — 그러나 F5 활성화 시 Hermes notify 가 직전 last_failure 기준 dedup 받음 → 최신 failure 정보 누락.

**수정**: 호출 순서 교환.

### [HIGH][NewBug] HIGH-4: `needs_alert` dedup 로직 — `failed_count` 비교 누락

**파일**: `scripts/ops-alert.py:53~76`

ADR-0024 dedup 표: `alerted_at 있음 + failed_count 같음` → dedup hit.
구현: `failed_count` 미참조, `last_failed_at > alerted_at` 만 비교.

`save_last_failure` 가 매 fatal 마다 `last_failed_at = now` 갱신 → 매 timer cycle 마다 `last_failed_at > alerted_at` 영원히 True → **매 사이클마다 webhook 발송** → ADR-0024 핵심 목적 (alarm fatigue 회피) 미달.

**수정**:
1. `mark_alerted` 에서 `alerted_failed_count` 도 함께 기록.
2. `needs_alert` 에서 `alerted_failed_count` 비교 후 같으면 dedup hit.

### [HIGH][NewBug] HIGH-5: `config.py:187` 의 `instance_root` `~` 미expand → ops-alert.py 영구 no-op

**파일**: `scripts/lib/config.py:187`

```python
instance_root=Path(_require(instance, "root", ctx="instance")),
```

`wikihub.yaml.example` 의 `instance.root: ~/wikihub-instance` — `Path("~/wikihub-instance")` 는 literal. `expanduser()` 미호출.

결과: `ops-alert.py` 의 `collect_last_failures(cfg.instance_root)` 가 literal `~/wikihub-instance/_state` glob → 영원히 빈 리스트 → fatal 알림 0건 도달 (CRIT-R8-1 의 잔재).

**수정**: `config.py` 의 `instance_root` + `local_path` 둘 다 `.expanduser()` 추가.

### [MED][SpecMismatch] MED-1: WIKIHUB_HOME 절대경로 normalize 생략

**파일**: `install.sh:Step 2`

spec 의 `cd "$(dirname ...)" && pwd` normalize 단계 미구현. 상대경로 (`./wikihub`) 차단 안 됨.

### [MED][SpecMismatch] MED-2: `WIKIHUB_HOME` export 책임 미이행

**파일**: `install.sh` 전체

setup.md 가 "install.sh 가 실행 시 export" 명시. 그러나 `export WIKIHUB_HOME` 부재. self-replace exec 시 env 전달 안 됨.

### [MED][TestGap] MED-3: `_step4_gws` 의 `install` 실패 시 진단 부족

**파일**: `install.sh:L260`

`install -m 0755 "$tmpdir/gws" "$GWS_BIN_DIR/gws"` — `$tmpdir/gws` 부재 시 (asset 구조 다를 경우) `set -e` exit. 그러나 사용자에게 진단 정보 (어떤 파일이 tar 안에 있는지) 부족.

### [LOW][DocMismatch] LOW-1: install.sh:L11 의 spec 경로가 archive 가리킴

**파일**: `install.sh:11`

feature 아직 진행 중인데 `features/archive/` 가리킴. 단순 오타.

### [LOW][SpecMismatch] LOW-2: ADR-0015·0017 Status `Proposed`

V6·V4 verification 미완이라 의도된 상태. 단지 cross-reference 시 주의.

### [NIT][DocMismatch] NIT: `ops-alert.py` 의 private import

**파일**: `scripts/ops-alert.py:31`

```python
from lib.state import _atomic_write_json, _read_json, utc_now_iso
```

private (underscore prefix) 함수 직접 import. `mark_alerted` 를 `state.py` 의 public helper 로 옮기는 게 캡슐화 정합.

---

## 3. 결론

### 배포 차단 여부: **예** (CRIT 2건 + HIGH 5건)

**즉시 fix 필요**:

1. **CRIT-1** (`install.sh:217`): 파이프 체인에 `|| true` 추가. 가장 빠른 fix.
2. **CRIT-2** (`setup.md` Step 6): bootstrap_allowed 환원 조건 ADR-0022 정본 기준 통일.
3. **HIGH-1**: lint.service.template + lint.timer.template 신규 작성.
4. **HIGH-2**: CLI args 보존 + bootstrap 호출 흐름 수정.
5. **HIGH-3**: notify / save_last_failure 호출 순서 교환.
6. **HIGH-4**: needs_alert + mark_alerted 재구현 — alerted_failed_count 필드 추가.
7. **HIGH-5**: config.py 의 path 모두 `.expanduser()` 추가.

**다음 PR 까지 처리**:

- MED-1·2·3 + LOW/NIT.

**V8 hand-check** (별도 verification — 배포 전 필수):
- gws GitHub Releases 의 정확한 ARM64 asset 이름.
