# Feature Plan — dir_layout_refactor

- **feat_id**: `dir_layout_refactor`
- **시작일 (KST)**: 2026-05-19
- **버전**: v1
- **locked**: 2026-05-19 (Step 1 종료, Step 2 진입 가능)
- **선행 feature**: F5 `hermes_adapter` (archive, squash `eb4b6ed` — v0.1.0 acceptance 달성)
- **목적**: wikihub 의 home 디렉토리 layout 의 mental model 재정의. 현행 (`~/wikihub/` = repo, `~/wikihub-instance/` = 운영 데이터) 의 **code-first naming** 을 **data-first naming** 으로 invert — 사용자가 일상적으로 보는 자산 (wiki 콘텐츠 + yaml + state) 이 `~/wikihub/` 가 되고, 시스템 코드 (repo) 는 XDG 표준 위치 (`~/.local/share/wikihub/src/`) 로 이동.

> **핵심 운영 invariant**: 운영자의 일상 자산 (`~/wikihub/wiki/`) 가 `--force-fresh` 또는 update_mode 의 어떤 단계에서도 손실되지 않음. `~/.local/share/wikihub/src/` 만 git fetch+reset / wipe 대상.

---

## 작업 분류

**리팩토링** (외부 인터페이스 변경) + **운영자 mental model 재정의**.

architectural change — install.sh 의 self-replace pattern + WIKIHUB_HOME 의미론 + ADR 4건 갱신. update_mode (ADR-0030) 동급 분량 예상.

---

## 적용 단계 선언

| 단계 | 수행 | 사유 |
|---|---|---|
| Step 1 Plan | ✅ | 본 문서 |
| Step 2 Analysis & Design | ✅ **필수** | (δ-1/-2/-3) 옵션 분기 결정 (현 권장 δ-2 XDG src) + ADR 영향 + migration 시나리오 4개 + curl-pipe self-replace 정합 |
| Step 3 Implementation | ✅ | install.sh self-replace + WIKIHUB_HOME default + safety guard 재정의 + migration 자동 detect + ADR Notes 다수 |
| Step 4 Code Review | ✅ **R≥2 필수** | 외부 인터페이스 의미론 변경 (운영자 mental model + multi-machine deployment 영향) + ADR-0020·0023·0030 cross-feature invariant |
| Step 5 Deployment | ⏸ **deferred** | v0.2.0 release 시점 — v0.1.0 운영 시작 후 surface 한 결함 정리와 함께 묶음 release. 운영자에게 명시 migration guide 제공 |

---

## 예상 영향 범위

| 영역 | 변경 성격 | 예상 크기 |
|---|---|---|
| `install.sh` | self-replace target 변경 + clone destination 변경 + safety guard 재정의 + migration detect | +80~150줄 |
| `wikihub.yaml.example` | `instance.root` default — placeholder 또는 명시 변경 | +1~5줄 |
| `_system/wiki-schema.md` | 디렉토리 트리 안내 갱신 (대폭) | +30~60줄 |
| `_system/commands/setup.md` | ADR-0031 §Decision B catalog 의 `instance.root` derive 정합 | +5~15줄 |
| `scripts/_helpers/render_systemd_units.py` | `_wikihub_home()` + `_instance_root_default()` semantic 변경 | +10~30줄 |
| `README.md` | install snippet 대폭 갱신 + 디렉토리 구조 갱신 + migration 안내 | +30~50줄 |
| `docs/adr/0010-*` Note | operational tooling split — XDG src 분리 명시 | +20줄 |
| `docs/adr/0020-*` Note | venv XDG 와 src XDG 통합 정합 | +15줄 |
| `docs/adr/0023-*` Note | self-replace destination 변경 + safety guard scope 재정의 | +30줄 |
| `docs/adr/0030-*` Note | update_mode 의 git fetch+reset target 정합 (XDG src) | +20줄 |
| `docs/adr/0031-*` Note | yaml.instance.root default 변경 — operator override 패턴 유지 | +15줄 |
| `docs/adr/0034-*` (신규) | 후보 — XDG src layout 결정 정본화 (선택, 옵션 lock 시점에 결정) | +60~100줄 (신규 시) |
| `.gitignore` | path 변경 영향 검토 (현 `.venv_path` 등 sidecar 위치) | +1~5줄 |
| 신규 migration helper | 기존 운영자의 `~/wikihub/` (repo) + `~/wikihub-instance/` (운영) 자동 detect → 안전 이전 안내 | 신규 script 1건 또는 install.sh 내 함수 |

총 영향 파일 11~14개. update_mode (16 files, +3860/-136) 와 유사 분량.

---

## Step 1 lock 결정

1. **layout 옵션 — δ-2 XDG 채택 (2026-05-19 lock)**:
   - 운영 dir = `~/wikihub/` (사용자 일상 자산 — wiki, yaml, state)
   - 시스템 코드 = `~/.local/share/wikihub/src/` (XDG, ADR-0020 venv 와 정합)
   - 선정 근거: data-first mental model + ADR-0020 정합 + multi-instance 자연 지원 + `--force-fresh` 가 src 만 wipe (운영 자산 절대 안전)
   - 기각: (δ-1) hidden `.system/` — `--force-fresh` 시 운영 자산 wipe 위험 + IDE visibility 어색. (δ-3) sibling `~/wikihub-src/` — home cluttering 해소 부분적
   - Step 2 분석은 본 layout 채택을 전제로 진행

## 핵심 미결 사항 (Step 2 에서 결정)

1. **WIKIHUB_HOME semantic 재정의**:
   - **option A**: `WIKIHUB_HOME` = 운영 자산 dir (사용자 의도). 신규 env `WIKIHUB_SRC` 도입
   - **option B**: 변수명 자체 변경 — `WIKIHUB_INSTANCE_ROOT` → `WIKIHUB_HOME`, `WIKIHUB_HOME` → `WIKIHUB_SRC`. 의미 명확, 그러나 backwards-incompat
   - **option C**: 둘 다 deprecated 후 새 env 도입 — `WIKIHUB_DATA` + `WIKIHUB_SRC`
2. **migration 자동화 수준**:
   - **option A**: install.sh 가 기존 `~/wikihub/` (repo) detect → 명시 confirm 후 자동 이전 (`~/wikihub/` → `~/.local/share/wikihub/src/` mv, `~/wikihub-instance/` → `~/wikihub/` mv)
   - **option B**: 운영자 manual migration. install.sh 가 detect 후 안내만 출력
   - **option C**: 별도 `scripts/migrate_layout.sh` helper — install.sh 가 호출 prompt
3. **curl-pipe self-replace destination**:
   - 신규 self-replace 가 `~/.local/share/wikihub/src/install.sh` 호출
   - 신규 install.sh 가 운영 dir (`~/wikihub/`) 생성 + initial yaml materialize
4. **multi-instance 시나리오 (운영자 명시 사용)**:
   - default `WIKIHUB_HOME=~/wikihub` 외에 `WIKIHUB_HOME=/var/wikihub-prod` 같이 env override 지원 유지
   - `WIKIHUB_SRC` 는 default 공유 또는 per-instance — Step 2 결정
5. **`~/wikihub/.credentials/` vs `~/.credentials/wikihub/`**:
   - ADR-0029 의 SA JSON 위치 — repo 외부 권장 (현 `~/.credentials/wikihub/`). data-first 후에도 같은 정책 유지
   - 운영 데이터의 일부지만 보안 격리 위해 외부 유지가 권장 — Step 2 명시

---

## 메소드론 적용 여부

✅ **전체 적용** — trivial 변경 아님. install.sh self-replace + WIKIHUB_HOME semantic 변경 + ADR 4건 영향 + migration scenarios. Step 4 R≥2 필수.

---

## 진입 조건

- ✅ F5 archive (squash `eb4b6ed`) — v0.1.0 acceptance 달성
- ✅ 현 main HEAD = `eb4b6ed`
- ⏸ multipass VM 검증 환경 (wikihub-fresh 보존 또는 신규)
- ⏸ Hermes 인스턴스 + provider 설정 (V3 dispatch 검증 필요 시)

---

## 다음 액션

1. **사용자 lock**: `"plan lock 하고 Step 2 진입해"` → analysis_and_design.md v1 작성
2. **사용자 옵션 재확인**: δ-1/-2/-3 중 최종 채택 — 현 권장 δ-2 유지 여부
3. 또는 plan 검토 피드백 후 v2 재작성
