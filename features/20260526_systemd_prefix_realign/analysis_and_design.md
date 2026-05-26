# Analysis & Design — systemd_prefix_realign

approved: 2026-05-26

---

## 배경 및 목적

`feature/v018-fix` 의 commit `2ed01f8` (2026-05-26) 가 systemd unit 의 prefix 를 Hermes skill 이름과 통일하기 위해 rename:

- `wikihub-vault@` (template) → `wh-ingest@`
- `lint.{service,timer}` (no prefix) → `wh-lint.{service,timer}`

당시 commit 의 rationale: "rename unit files wh-ingest@ / wh-lint for consistency with skill names" + GLM/Mimo 멀티모델 리뷰 통과.

**문제 — 직후 발견 (2026-05-26, 운영자 직관 검토)**:
- `wikihub-mount@`, `wikihub-graphify`, `ops-alert` 등 다른 unit 은 `wikihub-*` 또는 prefix 없음. `wh-*` 만 두 unit 에 적용 → **systemd namespace 일관성 손상**.
- Hermes skill `wh-*` (ADR-0033 lock) 와 systemd unit 은 두 다른 abstraction layer — 같은 prefix 강제 의미 부족 (skill 호출과 systemd ExecStart 의 호출 chain 관계만 존재, 그 외 직접 매핑 없음).
- 결과: 직전 rename 결정의 명분 (skill name 통일) 보다 namespace 정합 (`wikihub-*` 단일 systemd namespace) 이 운영자 mental model 에 더 유익.

## 현행 진단

| # | 결함 | 근거 |
|---|---|---|
| 1 | `_system/systemd/wh-{ingest@,lint}.{service,timer}.template` (4 파일) 이 `wikihub-*` namespace 정합 위반 | `ls _system/systemd/` 결과 `wikihub-mount@`, `wikihub-graphify`, `ops-alert` 와 prefix 불일치 |
| 2 | `install.sh` 의 21 systemd unit invocation 이 `wh-*` 사용 | grep `wh-ingest\|wh-lint install.sh` |
| 3 | `_system/commands/*.md` 19 refs | grep 결과 setup 8 + lint 9 + graphify 2 |
| 4 | `_system/wiki-schema.md` 30 refs (inventory + namespace catalog) | grep 결과 |
| 5 | `scripts/_helpers/render_systemd_units.py` 5 refs (glob/regex/legacy cleanup) | grep 결과 |
| 6 | `README.md` 5 refs | grep 결과 |
| 7 | `docs/adr/0040-monitor-services-remove.md` 1 ref (직전 작성 narrative) | grep 결과 |
| 8 | v0.1.9 canary 운영자가 이미 `wh-*` unit 으로 운영 중일 가능성 — upgrade migration block 부재 시 orphan unit 잔존 | install.sh 검토 |

## 개정 범위

### Rename (4 template)

| Before | After |
|---|---|
| `_system/systemd/wh-ingest@.service.template` | `_system/systemd/wikihub-ingest@.service.template` |
| `_system/systemd/wh-ingest@.timer.template` | `_system/systemd/wikihub-ingest@.timer.template` |
| `_system/systemd/wh-lint.service.template` | `_system/systemd/wikihub-lint.service.template` |
| `_system/systemd/wh-lint.timer.template` | `_system/systemd/wikihub-lint.timer.template` |

### Modify

| 파일 | 변경 성격 |
|---|---|
| `install.sh` | 21 unit invocation rename. **skill name (`hermes chat --skills wh-ingest`, `--skills wh-lint` 등) 은 그대로**. upgrade migration block 확장 — `wh-ingest@*` + `wh-lint.{service,timer}` stop + disable. |
| `_system/commands/setup.md` (8 refs) | systemd unit name 만 갱신 — Hermes skill name 언급 (예: "wh-lint hermes skill") 은 그대로 |
| `_system/commands/lint.md` (9 refs) | 동상 |
| `_system/commands/graphify.md` (2 refs) | 동상 |
| `_system/wiki-schema.md` (30 refs) | inventory tree + namespace catalog 갱신. skill / unit 둘 다 언급되는 부분은 layer 분리 명시. |
| `scripts/_helpers/render_systemd_units.py` (5 refs) | glob 패턴 (`wh-*` → `wikihub-*` 또는 alternation 추가) + regex (`wikihub-(?:mount\|vault\|ingest)\|wh-ingest`) + legacy_singletons catalog 확장 (canary cleanup). |
| `README.md` (5 refs) | systemd unit 예시만 |
| `docs/adr/0040-monitor-services-remove.md` (1 ref) | `wh-lint.service` → `wikihub-lint.service` (직전 monitor remove 의 carry-over 표 narrative) |
| `wikihub.yaml.example` | 주석에 systemd unit 언급 있으면 — 검토 후 갱신 |

### 신규 ADR-0041

- **Decision**: systemd unit `wikihub-*` namespace, Hermes skill `wh-*` namespace 두 abstraction layer 의 prefix 분리 정합.
- **Supersedes**: 없음 (ADR-0033 본문 X — skill prefix 결정 자체는 보존. commit 2ed01f8 의 rename 은 ADR 없는 implementation level 결정이라 §"Supersedes" 표기 부적합).
- **Context**: 직전 v0.1.9 rename (`wikihub-vault@` → `wh-ingest@`, `lint.*` → `wh-lint.*`) 가 skill prefix 와 통일 의도 → namespace 일관성 손상 → 본 ADR 이 prefix 분리 정공법 채택.

### 차이점 — Hermes skill 명 보존

다음 형태의 reference 는 **변경 없음**:

| Reference | 의미 | Action |
|---|---|---|
| `hermes chat --skills wh-ingest` (install.sh `_step8_wh_setup_skill_meta` 등) | Hermes skill 호출 cmdline | 보존 |
| `_system/skills/wh-ingest.frontmatter.yaml` (파일명) | Hermes skill metadata | 보존 |
| `wh-ingest hermes skill` (commands docs 의 텍스트) | skill 의 식별자 | 보존 |
| `/wh-ingest`, `/wh-lint`, `/wh-setup`, `/wh-query` (메인테이너 invocation) | skill slash command | 보존 |

다음 형태는 **rename**:

| Reference | 의미 | After |
|---|---|---|
| `wh-ingest@<vid>.{service,timer}` | systemd unit | `wikihub-ingest@<vid>.{service,timer}` |
| `wh-lint.{service,timer}` | systemd unit | `wikihub-lint.{service,timer}` |
| `systemctl --user start wh-lint.timer` 등 | systemctl 명령 | `systemctl --user start wikihub-lint.timer` |

## 개정 전/후 비교

### Before (commit 2ed01f8 이후, 현재 HEAD)

```
_system/systemd/:
  ops-alert.service
  wh-ingest@.{service,timer}.template       ← 본 rename 대상
  wh-lint.{service,timer}.template          ← 본 rename 대상
  wikihub-graphify.service.template
  wikihub-mount@.service.template

systemd namespace:
  wh-*          ← 2 unit (ingest, lint)
  wikihub-*     ← 2 unit (mount, graphify)
  (prefix 없음) ← 1 unit (ops-alert — install.sh 가 별도 처리)

Hermes skill namespace (ADR-0033):
  wh-*          ← 4 skill (wh-ingest, wh-lint, wh-query, wh-setup)
```

### After

```
_system/systemd/:
  ops-alert.service
  wikihub-graphify.service.template
  wikihub-ingest@.{service,timer}.template  ← rename 결과
  wikihub-lint.{service,timer}.template     ← rename 결과
  wikihub-mount@.service.template

systemd namespace:
  wikihub-*     ← 4 unit (mount, ingest, lint, graphify) — **일관성 회복**
  (prefix 없음) ← 1 unit (ops-alert — final dispatcher, OnFailure target)

Hermes skill namespace (ADR-0033 unchanged):
  wh-*          ← 4 skill (wh-ingest, wh-lint, wh-query, wh-setup)
```

## Upgrade Migration

v0.1.9 canary 운영자 대응. 직전 v0.1.9 rename (2ed01f8) 의 upgrade migration block (install.sh:1629-1633) 은 `wikihub-vault@*` + `wikihub-lint.{service,timer}` 를 stop+disable. 본 rename 의 migration 은:

- **stop**: `wh-ingest@*.{service,timer}` + `wh-lint.{service,timer}` 모두 (canary 운영자 시나리오)
- **disable**: `wh-ingest@*.timer` + `wh-lint.timer` (`.service` 는 enable 대상 외)
- **render cleanup**: `legacy_singletons` 에 `wh-lint.{service,timer}` 추가 + `_do_render` 의 stale unit glob 에 `wh-ingest@*.{service,timer}` 매칭 추가

install.sh `_systemd_stop_before_update` 의 monitor migration block (1629-1633) 패턴 차용.

## DoD

- [ ] **D1 — Template rename**: 4 파일 `git mv` 완료. `ls _system/systemd/` 결과에 `wh-*` 0건.
- [ ] **D2 — install.sh systemd refs**: 21 unit invocation rename. `grep -E 'wh-ingest@|wh-lint\.' install.sh` 결과 = upgrade migration block + legacy_singletons 만 (모두 의도된 legacy).
- [ ] **D3 — Hermes skill name 보존**: `grep '\-\-skills wh-' install.sh` 결과 변경 없음 (skill cmdline reference 보존). `_system/skills/wh-*.frontmatter.yaml` 파일명 변경 없음.
- [ ] **D4 — commands docs**: setup.md / lint.md / graphify.md 의 systemd unit ref 갱신, skill name ref 보존. `wh-lint hermes skill` 같은 phrase 는 그대로.
- [ ] **D5 — wiki-schema.md**: inventory tree + namespace catalog 갱신.
- [ ] **D6 — renderer**: legacy_singletons 에 `wh-lint.{service,timer}` 추가. `_do_render` stale glob 패턴이 `wh-ingest@<vid>.{service,timer}` cleanup 가능하도록 보강.
- [ ] **D7 — README.md**: systemd unit 예시 갱신.
- [ ] **D8 — ADR-0041 신설**: Accepted + Status / Context / Decision / Consequences / Cross-references 완비. docs/adr/README.md index 추가.
- [ ] **D9 — ADR-0040 narrative**: `wh-lint.service` ref → `wikihub-lint.service` 1줄 갱신.
- [ ] **D10 — Verify**: render dry-run 출력에 `wikihub-ingest@<vid>` / `wikihub-lint.*` 정확 출력. pytest pass. grep `wh-ingest@\|wh-lint\.` 0건 (upgrade migration/legacy_singletons 제외). Hermes skill grep `wh-ingest\|wh-lint\|wh-query\|wh-setup` 변경 0건.

## 미결 사항

없음. Step 4 review 는 사용자 결정 (2026-05-26) 으로 생략 — plan.md §"적용 단계" 의 Step 4 row 참조.

## 참조

- [plan.md](plan.md)
- commit 2ed01f8 (`fix(systemd): rename unit files wh-ingest@ / wh-lint for consistency with skill names`)
- [docs/reviews/250526_v018fix_code_review_glm-5.1.md](../../docs/reviews/250526_v018fix_code_review_glm-5.1.md)
- [docs/reviews/250526_v018fix_code_review_mimo-v2.5-pro.md](../../docs/reviews/250526_v018fix_code_review_mimo-v2.5-pro.md)
- [docs/adr/0033-skill-prefix-hyphen-lock.md](../../docs/adr/0033-skill-prefix-hyphen-lock.md)
