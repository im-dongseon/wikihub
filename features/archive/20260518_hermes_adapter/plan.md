# Feature Plan — hermes_adapter

- **feat_id**: `hermes_adapter`
- **시작일 (KST)**: 2026-05-18
- **버전**: v1
- **locked**: 2026-05-18 (Step 2 진입)
- **선행 feature**: F4 `install_runtime` (archive), `update_mode` (archive, squash `0a83135`), `install_scope_reduction` (archive, squash `92ecf7f`)
- **목적**: wikihub spec (ADR-0002·0011·0012) 의 호출 모델 가정 — `hermes -z "/wh:ingest --vault X"` 식 slash-command 자동 dispatch — 과 실제 Hermes 동작 (`-z` 가 prompt 를 LLM 에 그대로 전달) 의 mismatch 를 해소. v0.1.0 acceptance 의 마지막 blocker (F4 backlog 결함 #12).

> **핵심 운영 invariant**: sync→ingest 자동화 사슬이 결정적 (deterministic). vault@.service 가 timer fire 할 때마다 `wh:ingest` 가 동일한 입력 → 동일한 동작 보장. agent 의 자연어 해석에 맡기지 않음.

---

## 작업 분류

**기능 추가** + **외부 인터페이스 정합** (agent ↔ wikihub 호출 의미론 lock).

---

## 적용 단계 선언

| 단계 | 수행 | 사유 |
|---|---|---|
| Step 1 Plan | ✅ | 본 문서 |
| Step 2 Analysis & Design | ✅ **필수** | 옵션 (α) Hermes skill 등록 vs (β) wrapper dispatcher (ADR-0012 옵션 β) 결정. Hermes skill 시스템 실측 결과가 결정 입력. ADR 1~2건 신설 예상 (skill 등록 정책 또는 ADR-0012 미검증 항목 closure) |
| Step 3 Implementation | ✅ | 선택된 옵션의 산출물 (skill 파일 또는 wrapper script) + `install.sh` 의 vault@.service ExecStart 정합 + `scripts/_helpers/render_systemd_units.py` (옵션 β 채택 시) substitution 정합 |
| Step 4 Code Review | ✅ **R≥2 필수** | update_mode·install_scope_reduction 와 동일 기준 — 외부 인터페이스 의미론 변경 + 운영 자동화 사슬 직접 영향. 멀티모델 리뷰 (CR1 spec + CR2 SRE) |
| Step 5 Deployment | ⏸ **deferred** | v0.1.0 acceptance 전체 (F4 + update_mode + install_scope_reduction + F5) 의 일괄 release 시점에 합산. F5 단독 deploy 아님. HISTORY.md 항목 추가는 v0.1.0 release feature 에서 묶음 처리 |

---

## 예상 영향 범위

| 영역 | 변경 성격 | 예상 크기 |
|---|---|---|
| `_system/commands/{ingest,lint,query,graphify,setup}.md` | skill 등록 메타 추가 (옵션 α) 또는 wrapper dispatch 호환 명세 (옵션 β) | 5개 파일, 각 +10~30줄 |
| `_system/skills/wh-*.md` 또는 `scripts/agent_run.sh` | **신규** — 옵션 결정 후 산출물 위치 확정 | 신규 1~5개 파일 |
| `install.sh` | skill registration step 신규 (Hermes skill dir 에 copy) 또는 wrapper 경로 yaml 기록 | +10~50줄 |
| `scripts/_helpers/render_systemd_units.py` | ExecStart 의 prompt 합성 — wrapper 채택 시 substitution contract 변경 가능 | +0~30줄 |
| `wikihub.yaml.example` | `agent.skill_dir` 또는 `agent.dispatcher_path` 키 추가 가능 | +1~5줄 |
| `docs/adr/0031-*.md` 또는 ADR-0002·0011·0012 의 Note | **신규 ADR** (skill 등록 정책) 또는 미검증 항목 closure Note | 신규 1건 또는 Note 2~3건 |
| `README.md` | install snippet 의 F5 후속 안내 보강 | +5~15줄 |

총 영향 파일 8~14개 예상. update_mode (16 files, +3860/-136) 대비 ⅓~½ 규모 예상.

---

## 핵심 미결 사항 (Step 2 에서 결정)

1. **Hermes skill 시스템 실측** — SKILL.md 형식, 등록 디렉토리 (`~/.hermes/skills/`?), `wh:` colon prefix 호환성, `-z` 와 skill match 의 실제 우선순위. 실측 환경: multipass VM (`update_mode` 검증과 동일).
2. **옵션 (α) vs (β) 선택** — 1번 실측 결과가 입력값.
   - (α) Hermes skill 등록 (SKILL.md): agent 의 skill 시스템 의존, 표준 path
   - (β) wrapper dispatcher (`scripts/agent_run.sh`): agent 비의존, indirection 1단계 추가
3. **`wh:` colon prefix fallback (ADR-0011)** — Hermes 가 colon 을 namespace separator 로 받는지 실측. 비호환 시 `wh-` 자동 치환 trigger 조건 정본화.
4. **systemd unit ExecStart 정합** — wrapper 채택 시 prompt quoting (`/wh:ingest --vault gdrive`) 의 shell escape 정합. F4 의 `_step8_systemd_render` + `render_systemd_units.py` substitution contract 와 호환.
5. **`/wh:setup` 의 skill 메타 갱신 책임** — install_scope_reduction 에서 `/wh:setup` 책임이 skill 메타 + yaml validate + first ingest prompt 로 축소됨. F5 가 skill 등록 자동화 시 `/wh:setup` 의 역할 재조정 필요할 수 있음.

---

## 메소드론 적용 여부

✅ **전체 적용** — trivial 변경 아님. 외부 인터페이스 변경 + ADR 신설 + 운영 자동화 사슬 직접 영향. Step 4 R≥2 필수.

---

## 진입 조건

- ✅ F4 `install_runtime` archive
- ✅ `update_mode` archive
- ✅ `install_scope_reduction` archive
- ✅ 현재 main HEAD = `c328548`
- ⏸ Hermes 실측 가능 환경 (multipass VM 의 Hermes 설치 또는 메인테이너 로컬) — Step 2 진입 시 준비

---

## 다음 액션

1. 사용자 lock: `"plan lock 하고 Step 2 진입해"` → Hermes 실측 → analysis_and_design.md v1
2. 또는 Hermes 실측 환경 부재 시: 옵션 (α)·(β) 의 spec 비교 우선 + 실측은 Step 3 진입 직전에 검증
