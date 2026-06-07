# Code Review 1 — update_path_fixes (v0.1.8, D3=B)

리뷰어: Claude (독립 컨텍스트, 이전 conversation 미참조)
일자: 2026-05-26
대상: `analysis_and_design.md` v2 (approved) + git diff HEAD (modified 11 + 신규 2 + 삭제 1)

---

## 종합 평가

설계 v2 가 정의한 D3=(B) 결정 (graphify hermes skill 폐기 + systemd service 격상) 의 라인 단위 정합 — **대체로 충실 구현**. (B) 채택의 architectural intent (Layer 1 LLM wrapper 폐기 + cost gate 보존 + Hermes parent leak 정합 유지) 가 실제 코드에 일관. 단 **C 1건 (timeout exit 124 unhandled)**, **H 1건 (wiki-schema.md stale `/wh-graphify` 4 위치)**, M 3건, L 2건 surface.

DoD 16개 항목 매트릭스: 14 PASS / 1 FAIL (`wikihub.yaml.example` 의 `graphify_partial_failure_threshold` 누락 — yaml.example sync 일반화의 single-source 원칙 위반) / 1 PARTIAL (wiki-schema.md tree만 갱신 — 본문 §책임 매트릭스·frontmatter 예시는 미정정).

배포 가능 판정: **C1 + H1 fix 후 가능**. 나머지는 backlog 또는 본 cycle merge 후 follow-up.

---

## C — Critical (배포 차단 후보)

### C1. `wikihub-graphify.service` 의 `timeout 124` 미흡수 → 매 timeout 마다 ops-alert 발화

**위치**: `_system/systemd/wikihub-graphify.service.template:5,20` + `scripts/wikihub_graphify.sh:81-122`

**결함**:
- service template 주석: `# runtime fail (exit 75/124) 은 SuccessExitStatus 정합`
- 실제 directive: `SuccessExitStatus=0 75` — **124 누락**
- `wikihub_graphify.sh` 의 backend dispatch 가 `timeout "$timeout_sec" env ... graphify ...` — timeout 발생 시 `timeout` 명령은 124 exit. `set -euo pipefail` 이라 그대로 propagate.
- 결과: graphify backend hang / cloud LLM latency 누적 시 정상 운영 경로인데 systemd 가 fail 분류 → `OnFailure=ops-alert.service` 발화 → Telegram alarm.

**대비 패턴**: ADR-0036 §"추가 보강 — lint Step 9 의 timeout wrapper" 가 "exit 124 시 report 에 `graph rebuild timeout` + lint 계속" 을 명시. lint.service.template / wikihub-vault@.service.template 등은 `0 75` 만 쓰지만 **자기 Python wrapper 가 timeout 을 잡아 75 로 변환**. wikihub_graphify.sh 는 bash + `timeout` shell builtin 사용이라 124 propagate. **systemd 양식이 75 만 보면 124 는 fail**.

**fix 옵션** (택1):
- A. service template: `SuccessExitStatus=0 75 124` (timeout 도 success 분류 — 12hr 후 또는 다음 lint cycle 자연 재시도)
- B. `wikihub_graphify.sh` 의 dispatch case 마다 timeout 124 → 75 변환 trap (set +e + $? 검사 + exit 75 명시)

설계 §2.1.1 의 SuccessExitStatus 코멘트와 일치시키려면 A 가 minimal change. 단 ops-alert 가 timeout 도 surface 받기 원하면 B 가 더 의도적.

권장: A (1줄). 차후 운영자가 timeout 빈발 감지 필요 시 lint Step 9 가 report.md 에 timeout fact 를 surface (별도 BL).

---

## H — High

### H1. `_system/wiki-schema.md` 의 stale `/wh-graphify` 본문 4 위치 — directory tree 만 정정, 본문 미정정

**위치**: `_system/wiki-schema.md:196, 234, 301, 343`

```
196: referenced_by:  # /wh-lint·/wh-graphify가 갱신 — 수동 편집 금지
234: referenced_by: []  # /wh-graphify가 갱신
301: | `graphify-out/*` | 미접근 | /wh-graphify가 빌드 |
343: | `/wh-graphify` | 지식 그래프 빌드 (수동 또는 /wh-lint 마지막 단계 자동) | `commands/graphify.md` |
```

**결함**: wh-graphify hermes skill 폐기 후에도 frontmatter 예시 + §책임 매트릭스 + §명령어 매트릭스 가 `/wh-graphify` 호출 패턴을 정본 spec 으로 명시. 운영자/메인테이너가 wiki-schema.md 를 정본 가이드로 참조하므로 정합 fail.

설계 §1.4 의 wiki-schema.md 갱신 범위 = "directory tree — wh-graphify SKILL.md 제외 + wikihub-graphify.service.template 포함" — 본문 §책임/명령어 매트릭스는 scope 외였으나 (B) 채택으로 graphify 가 더 이상 hermes skill = `/wh-graphify` invocation 이 아니므로 본문 정정도 필수.

**fix**: 4 위치 모두 `/wh-graphify` → `wikihub-graphify.service` 또는 `scripts/wikihub_graphify.sh` 로 표현 정정. 매트릭스 행 1줄 (`/wh-graphify | 지식 그래프 빌드` 행) → `wikihub-graphify.service | 지식 그래프 빌드 (systemd oneshot, lint Step 9 trigger) | commands/graphify.md` 형태.

---

## M — Medium

### M1. `wikihub.yaml.example` 에 `graphify_partial_failure_threshold` 부재 — yaml.example sync 일반화의 single-source 위반

**위치**: `wikihub.yaml.example` (grep 결과 미존재) + `_system/commands/graphify.md:50` + `scripts/wikihub_graphify.sh:140`

**결함**: 
- graphify.md §"backend / profile / timeout" 표가 `operations.graphify_partial_failure_threshold` 를 정본 yaml field 로 명시 (default 0.5).
- `wikihub_graphify.sh:140` 은 `yq '.operations.graphify_partial_failure_threshold // 0.5'` 로 runtime read.
- 그러나 `wikihub.yaml.example` 에 해당 키가 부재 → §2.4.2 의 yaml.example sync 메커니즘 (R2 fix) 이 이 field 를 자동 보강 못 함 → 운영자 yaml 에 미존재.
- runtime 은 default 0.5 로 동작하므로 functional fail 은 아님. 단 R2 fix 의 architectural intent ("yaml.example = schema mutation single source of truth") 미실현.

**fix**: `wikihub.yaml.example` 의 operations 섹션에 `graphify_partial_failure_threshold: 0.5` + 주석 1줄 추가.

### M2. wikihub_graphify.sh `--rebuild` 인자가 systemd 호출 path 에서 사용 불가

**위치**: `scripts/wikihub_graphify.sh:74` + `_system/systemd/wikihub-graphify.service.template:19`

**결함**: 
- service template `ExecStart={wikihub_src}/scripts/wikihub_graphify.sh` — 인자 없음.
- script 의 `--rebuild` 분기 (`if [[ "${1:-}" == "--rebuild" ]]`) 는 직접 호출 시만 동작.
- graphify.md:56 가 메인테이너 manual 호출을 `systemctl --user start wikihub-graphify.service` 로 안내 — 이 경로로는 `--rebuild` 전달 불가.
- 직접 `scripts/wikihub_graphify.sh --rebuild` 호출은 가능하지만 `WIKIHUB_HOME / WIKIHUB_YAML` env 수동 set 필요 + systemd EnvironmentFile 미적용 → profile bundle env 누락 위험.

**fix 옵션**:
- A. `systemd-run --user --unit=wikihub-graphify-rebuild --collect ... wikihub-graphify.service --rebuild` 같은 ad-hoc 활성 — 복잡
- B. yaml `operations.graphify_force_rebuild: false` toggle + script 가 yaml 에서 읽기 — 운영자가 1회 fire 후 reset 필요 (UX 부담)
- C. 현 상태 유지 + graphify.md 의 manual rebuild 안내를 `WIKIHUB_HOME=... WIKIHUB_YAML=... EnvironmentFile=~/.config/wikihub/env source... ./scripts/wikihub_graphify.sh --rebuild` 처럼 명시 (BL 등록)

권장: C + graphify.md §"운영 흐름" 의 메인테이너 manual 안내를 보강. 또는 backlog Q1 (alias 신설) 과 묶음.

### M3. `_migrate_agent_schema` 의 `B_sync:*` flag 가 운영자에게 너무 generic — 어느 신설 field 가 추가됐는지 surface 안 됨

**위치**: `install.sh:776-832` + `install.sh:843-845`

**결함**: 
- Python detect 가 `flags.append(f"B_sync:{top}.{k}")` — flag string 안에 field path 가 박혀 있음 (good).
- bash side `case "$f" in B_sync:*) info "  - [yaml.example sync] ${f#B_sync:} 부재 → ..."` — flag 의 `${f#B_sync:}` 가 `operations.foo` 형태 한 줄 출력. 
- 하지만 ruamel write (864-908) 는 어떤 key 가 실제로 추가됐는지 stdout 출력 안 함 → backup 파일 diff 가 유일 검증 수단.
- 큰 jump (v0.1.0 → v0.1.8) 시 신설 key 다수면 info log 많아지나 multi-line 처리는 OK. 다만 ruamel write 가 detect 와 별도 loop 라 detect 의 set 과 실제 write 의 set 이 분기될 위험 (예: detect 후 운영자 race 편집).

**fix**: ruamel write Python heredoc 에 `print` 추가 — `print(f"  applied B_sync: {top}.{k}", file=sys.stderr)` 패턴으로 실제 mutation surface. 또는 detect/write Python heredoc 통합 (현재 2개 분리된 PYEOF block 을 1개로) — DRY + race window 축소.

권장: detect/write heredoc 통합 (단일 source). minimal change.

---

## L — Low / Nit

### L1. `wikihub_graphify.sh:143` 의 awk ratio 계산 — 두 번 호출 (분기 + warning 메시지)

```bash
if awk "BEGIN {exit !($N / $M < $threshold)}"; then
    echo "WARNING: graphify partial failure 의심: N=$N, M=$M, ratio=$(awk "BEGIN {print $N/$M}")" >&2
```

ratio 변수 사전 계산 후 재사용 — 1줄 단축.

### L2. install.sh:1254 의 운영자 안내 text 가 `wh-graphify` 를 미명시 skill 군에 포함

```
Telegram 대화·미명시 skill (wh-query·wh-graphify·wh-setup) 의 model.default 는 ...
```

(B) 채택으로 `wh-graphify` skill 미존재. `wh-query·wh-setup` 만 또는 `wh-graphify` 삭제. text-only nit.

---

## 통과 관점 (PASS)

| DoD 항목 | 상태 | 근거 |
|---|---|---|
| `_system/skills/wh-graphify.frontmatter.yaml` 삭제 | PASS | git status: deleted |
| `_system/commands/graphify.md` spec 격하 (~50줄) | PASS | 80 lines, bash reference + ADR cross-link |
| `_system/systemd/wikihub-graphify.service.template` 신설 | PASS | Type=oneshot + OnFailure=ops-alert + TimeoutStartSec=1200 + Restart 미설정 + Install 미설정 (timer 없음 정합) |
| `scripts/wikihub_graphify.sh` 신설 + chmod +x | PASS | 6.0KB rwxr-xr-x. set -euo pipefail. 6 backend case (ollama/openai/claude/gemini/deepseek/kimi). |
| graphify.md v0.1.7 Step 2 6 backend case 정합 | PASS | wikihub_graphify.sh 의 dispatch case 가 6개 모두 — env var 와 API key 정합 (OPENAI/ANTHROPIC/GEMINI/DEEPSEEK/MOONSHOT) |
| ADR-0038 profile bundle resolve | PASS | regex 검증 `^[a-z][a-z0-9_]*$` + 3 env var indirect expansion (`${!model_var:-}`) + model 부재 시 fail-fast exit 2 |
| ollama endpoint 분기 + IPv6 escape | PASS | `http://\[::1\]:*` — bash case 의 POSIX char class 충돌 회피 escape. localhost / 127.0.0.1 / [::1] 3 패턴 |
| concurrency 휴리스틱 | PASS | default 4 + `*cloud*` model 4 + 로컬 endpoint 1 + 외부 4 (graphify v8 --help "default 4; set 1 for local LLMs" 정합) |
| lint Step 9 변경 감지 분기 + systemctl --user start fire-and-forget | PASS | lint.md:217-244 — 3 case 분기 (yaml toggle / 변경 없음 / 변경 있음) + fire-and-forget 명시 + cost gate 보존 |
| `_WIKIHUB_SKILLS` 4 skills (render_systemd_units.py + install.sh 동기) | PASS | render:141 + install.sh:756 둘 다 `wh-ingest, wh-lint, wh-query, wh-setup` |
| install.sh systemd 3 위치 (stop / reset-failed / try-restart) wikihub-graphify.service 포함 | PASS | line 1584 (stop), 1604 (reset-failed), 1685 (try-restart) — try-restart 가 inactive 시 no-op 정합 |
| install.sh `_migrate_agent_schema` yaml.example sync 일반화 | PASS | 776-833 detect (Python heredoc) + 864-908 write (ruamel) + WIKIHUB_SRC env guard (782-784) |
| Group A_yolo_missing 복원 | PASS | 815-817 detect + 890-894 insert. legacy_migration_cleanup 의 narrowing rationale (skill_prefix·oneshot_legacy 는 미복원) 정합 |
| ADR 4건 §"후속 영향" 각 1줄 cross-link | PASS | 0031:232, 0032:80, 0036:129, 0038:75 — 모두 D3=B 명시 + v0.1.8 update_path_fixes feature 명 + 정본 위치 cross-link |
| README.md §"동작" 4 skill 정정 | PASS | line 159 — 4 skill (wh-ingest·wh-lint·wh-query·wh-setup) + graphify systemd 격상 명시 |

---

## 범위 외 (본 review scope 외 / 별도 BL 권장)

- **R-out-1**: ADR-0036 §재검토 트리거 의 "Pass 3 silent partial failure" → ops-alert trigger path. 현재 stderr WARNING 만 — wikihub-monitor 가 journal grep 으로 surface 하므로 1차 mitigation. ops-alert 자동 발화는 미결 사항 Q3 그대로 BL.
- **R-out-2**: graphify_partial_failure_threshold 가 yaml.example 부재 → M1 으로 처리. partial failure ratio 가 정확히 운영 의미인지 (예: stub 만 100% 인 wiki 의 ratio 정의) 는 ADR-0036 의 §재검토 트리거.
- **R-out-3**: `B_sync:*` flag 의 set semantics 한계 (운영자 명시 삭제 vs 자연 부재 구분 불가) — 설계 §2.4.2 가 명시한 known limitation. 본 fix scope 외.
- **R-out-4**: wikihub-graphify.service 가 `[Install]` 미작성이라 `systemctl --user enable` 불가 — 의도 (timer 없음). 단 운영자가 실수로 enable 시도 시 silent fail 안 함 — systemd 가 `[Install]` 부재 명시 에러 → 운영자 surface 가능.
- **R-out-5**: lint Step 9 의 trigger 가 hermes LLM body 안에서 `bash` tool 호출로 일어남 (LLM-driven). hallucination 위험 → wikihub_monitor 의 journal scan 으로 사후 검증. 본 fix 의 (B) 채택 자체가 이 LLM 의존 인식 위에서 결정 (Layer 1 폐기는 sub-skill spawn 자동화 가설 mismatch).

---

## 결론

**1 cycle 후 merge 권장 — C1 (SuccessExitStatus 0 75 124 보강) + H1 (wiki-schema.md 본문 4 위치 정정) 만 본 cycle 안 fix**. M1·M3 는 본 cycle 흡수 시 net +5 line, M2 는 BL Q1 통합 권장.

전체 net diff: +163 / -350 (실제) vs 설계 +170 / -257 — graphify.md 격하가 설계보다 더 큰 감축. (B) 채택의 architectural intent (Layer 1 폐기 = over-engineering 제거) 와 일관.
