# Code Review 2 — update_path_fixes (independent reviewer, 운영 안전성 + 실측 가능성)

작성일: 2026-05-26 (KST)
리뷰어: Claude (독립 세션, prior 컨텍스트 0)
대상: design v2 (approved 2026-05-25) + 변경 파일 11건 + 신설 2건 (`wikihub-graphify.service.template` / `wikihub_graphify.sh`)
검토 관점: 운영 안전성 + 실측 가능성 (DoD §4 multipass 시나리오 검증)

---

## 종합 평가

본 fix 는 multipass v0.1.0 → v0.1.8 큰 jump test 가 surface 한 2 결함 (R1: lint Step 9 silent skip / R2: schema drift 미반영) 의 hotfix. design v2 의 D3=B (wh-graphify hermes skill 폐기 + systemd 격상) + D4 (yaml.example sync 일반화) 는 방향 자체 정합 — 코드 구현도 design 본문 trace 정합. 단 **두 핵심 운영 안전성 결함이 surface**:

| ID | 결함 | 본 review 평가 |
|---|---|---|
| **C1** | `wikihub-graphify.service` 의 `OnFailure=ops-alert.service` 가 graphify failure 를 **silent skip** — ops-alert.py 의 `collect_last_failures` 는 `_state/<vault_id>/last_failure.json` 만 scan, graphify 가 작성 안 함 + `collect_mount_fallback_failures` 도 `wikihub-mount@.service` 만 검사 → graphify exit 2 시 ops-alert 가 "no last_failure to alert" log + exit 0. | **C — silent fail loop** |
| **C2** | `install.sh:1685` 의 `try-restart` 가 `wikihub-graphify.service` 포함 — oneshot + timer 부재 unit 의 try-restart 는 semantic 불일치. `try-restart` 는 "active 면 restart, inactive 면 no-op". oneshot 의 active 상태는 ExecStart 종료 직후 inactive (Type=oneshot + RemainAfterExit=no default) — try-restart 가 항상 no-op. 의도 0 — install path 의 graphify race re-fire 안전망 부재. | **C — 의도/구현 mismatch** |

**핵심 진단**:

- design v2 §2.1 의 "bootstrap fail (exit 2) 시만 ops-alert 발화" 가정이 ops-alert.py 의 실제 동작 (last_failure.json scan-only) 과 mismatch — `wikihub-graphify.service` 의 OnFailure 가 trigger 돼도 ops-alert 가 surface 안 함. `wikihub-monitor.service` 와 동일 결함 (design v2 §1.1 §2.1.1 의 "wikihub_monitor 의 패턴 정합" 명시 — 정확히 같은 결함 inheritance).
- `try-restart` 의 wikihub-graphify.service 포함은 reviewer 의 운영 시나리오 검토에서 install path 의 race re-fire (예: lint cycle 가 graphify 호출 중 install.sh --update 가 진입 시 graphify subprocess 재시작) 의도 인지 — 그러나 systemd semantic 상 oneshot 의 active 가 일시적이라 try-restart 가 의도 동작 안 함.
- `graphify_partial_failure_threshold` field 가 `wikihub.yaml.example` 부재 — `wikihub_graphify.sh:140` 에서만 `yq` default `0.5` 로 처리. R2 fix 의 yaml.example sync 가 본 field 자동 추가 안 함 — 운영자 yaml 에 명시 path 부재. 운영자가 threshold override 의도 시 yaml field 자체가 schema 미문서 — 운영 가시성 약화 (M2).
- 운영자 manual 호출 UX 안전성 (Q1) — `systemctl --user start wikihub-graphify.service` 후 fire-and-forget 의 결과 surface 가 `journalctl --user -u wikihub-graphify.service` 의 운영자 manual grep 의존. monitor 보고서 통합 (Q2) 별도 feature 로 분리됐으나 BL 등록 surface 안 됨.
- R1 fix 의 lint Step 9 변경 감지 분기 (lint.md:231) 의 LLM 트래킹 정확도 의존 — wh-lint hermes skill LLM 의 자체 응답 정확도 가 cost gate 정합 (LLM 이 보수적 "변경 있음" 판단 시 cost 폭증) — design 본문 §2.2 / lint.md Step 9 spec 미명시.

**release 권고**: v0.1.8 hotfix 통합 정합 (design v2 D1=v0.1.8 통합 + D2=단일 feature). 단 본 review 의 C1/C2 흡수 후 release 권장. C1/C2 모두 본 fix scope 안 (graphify systemd unit + install.sh systemd sequence).

---

## C — Critical (반드시 흡수)

### C1. `wikihub-graphify.service` OnFailure → ops-alert.service 의 silent skip 결함 — graphify failure 가 운영자 surface 안 됨

**위치**:
- `_system/systemd/wikihub-graphify.service.template:5-6` (`OnFailure=ops-alert.service`)
- `scripts/ops-alert.py:144-163` (`collect_last_failures` — `_state/<vault_id>/last_failure.json` glob only)
- `scripts/ops-alert.py:96-141` (`collect_mount_fallback_failures` — `wikihub-mount@<vid>.service` 만 검사)

**시나리오 재현**:

1. lint cycle 변경 감지 시 `systemctl --user start wikihub-graphify.service` (lint.md Step 9 분기 3).
2. `wikihub_graphify.sh` 가 다음 중 하나로 exit 2 (`OnFailure` trigger):
   - graphify CLI 미설치 (line 20-23, `pip install graphifyy` 실패 잔존)
   - `WIKIHUB_HOME` / `WIKIHUB_YAML` unset (line 16-17 — systemd env 정합이라 fail 가능성 낮으나 manual 호출 case)
   - `graphify_profile` 정규식 위반 (line 31-34)
   - `model` env unset (line 45-48)
   - unknown `graphify_backend` (line 118-121)
3. systemd 가 `OnFailure=ops-alert.service` trigger → ops-alert.py 호출.
4. ops-alert.py:202 의 `collect_last_failures` 는 `instance_root/_state/<vault_id>/last_failure.json` glob → graphify 가 작성 안 함 → 빈 list.
5. ops-alert.py:206-208 의 fallback 도 `vault_ids` 의 `wikihub-mount@<vid>.service` 만 검사 → graphify 미포함 → 빈 list.
6. ops-alert.py:210-212: `"no last_failure to alert (mount@ status 도 normal)"` log + exit 0.

→ **graphify exit 2 가 ops-alert journal 1줄 (no-op log) + Telegram 0건 + webhook 0건**. 운영자가 `journalctl --user -u wikihub-graphify.service` manual grep 안 하면 cost gate 의 graphify failure 영구 invisible.

**평가**:

design v2 §2.1.1 (analysis_and_design.md:131) 명시 "OnFailure=ops-alert.service — wikihub_monitor / lint-apply 패턴 정합 (bootstrap fail (exit 2) 만 surface)" — **wikihub_monitor 의 동일 결함 inheritance**. design 의 가정 자체가 ops-alert.py 의 실제 동작 검증 안 됨 (ops-alert.py 의 collect_* 함수 의 scope: vault_id namespace 만).

본 결함은 **wikihub_monitor 가 같은 결함 보유** — `_system/systemd/wikihub-monitor.service.template:6` 도 동일 `OnFailure=ops-alert.service`. 그러나 wikihub_monitor 의 결함은 design v2 가 명시 인지 (analysis_and_design.md:131 "wikihub_monitor 의 패턴 정합") — 본 fix 가 같은 결함 재생산 + 본 review 의 자유 결함 surface 책임.

**권고**:

(a) **단기**: design v2 의 OnFailure 의미 재정의 — "wikihub-graphify.service 의 OnFailure=ops-alert.service 는 nominal 정합이나 ops-alert.py 의 last_failure.json scope 외라 silent — 운영자가 `journalctl --user -u wikihub-graphify.service` manual grep 책임" 을 명시. backlog 신설 (BL- 발급).

(b) **중기**: `scripts/wikihub_graphify.sh` 가 exit 2 직전 `$WIKIHUB_HOME/_state/_graphify/last_failure.json` 작성 — ops-alert.py:144 의 glob scope 안에 들어오게 namespace 확장 (지금은 `<vault_id>/last_failure.json` 만). state_root 의 scope 확장은 ops-alert.py 변경 필요 (별도 feature scope).

(c) **장기**: ops-alert.py 의 collect_* 함수가 vault_id namespace 외 (graphify / monitor / lint 등 wikihub global service) 도 cover 하는 일반화 — wikihub_monitor backlog 항목과 통합 (Q2).

### C2. `install.sh:1685` 의 `try-restart` 가 `wikihub-graphify.service` 포함 — oneshot + timer 부재 unit 의 try-restart semantic 불일치

**위치**: `install.sh:1684-1685` (Step 8 systemd render 후)

**인용**:
```bash
systemctl --user try-restart 'wikihub-mount@*.service' \
    'wikihub-vault@*.timer' wikihub-lint.timer wikihub-pending-monitor.timer wikihub-monitor.timer wikihub-graphify.service 2>/dev/null || true
```

**문제**:

systemd `try-restart` semantic:
- "If the unit is **active**, restart it. Otherwise, no-op."
- `wikihub-graphify.service` 는 `Type=oneshot` + `RemainAfterExit=` 미지정 (default `no`, template line 25 의 코멘트만 `# Restart= 미설정` — RemainAfterExit 명시 없음).
- oneshot + `RemainAfterExit=no` (default) → ExecStart 종료 즉시 unit 상태 = `inactive (dead)`.
- → **try-restart 가 install.sh:1685 호출 시점에 항상 no-op** (graphify CLI 가 install.sh 와 동시 실행 가능성 0 — install.sh 의 stop sequence:1584 가 이미 stop 처리).

**의도 vs 구현 mismatch**:

design v2 의 DoD §4 항목 "install.sh systemd 3 위치 (stop / try-restart) — wikihub-graphify.service 추가 (timer 없음 — start 흐름 없음)" — try-restart 추가는 **install.sh 의 다른 timer (lint / monitor 등) 의 try-restart 패턴 정합** 의도. 그러나 timer 의 try-restart 는 의미 있음 (timer 가 long-running, active state 보유) ↔ oneshot service 는 active state 보유 안 함 (Type=oneshot + RemainAfterExit=no).

**비교**:
- `wikihub-monitor.timer` try-restart: timer 의 `OnCalendar=` reload 의도 — 정합.
- `wikihub-graphify.service` try-restart: **의미 0** — graphify 가 active 일 가능성 0 (oneshot 의 inactive 상태). 만약 active 라도 (race window, lint cycle 호출 직후) graphify 중간 kill → graph.json 손상 → wikihub_graphify.sh:131-135 의 invalid JSON detect path 의존.

**평가**:

본 try-restart 추가는 design v2 의 systemd 3 위치 lock 의도 — "stop / try-restart / start 3 sequence 정합" 이나 **start 흐름 부재** (graphify 는 timer 없음, install.sh:1635-1639 에 start 추가 안 됨, 정합). 그렇다면 try-restart 도 부재 권장 — install.sh:1685 의 try-restart 목록에서 `wikihub-graphify.service` 제거.

만약 의도가 "install.sh --update 가 graphify 실행 중 진입 → graphify subprocess 재시작" 이면 `try-restart` 가 아닌 `restart` (active 강제 restart) 여야 함 — 그러나 lint Step 9 의 fire-and-forget 정합 + cost gate 정합 의도 외 (재실행은 다음 lint cycle 의 변경 감지에 위임).

**권고**:

`install.sh:1685` 의 try-restart 목록에서 `wikihub-graphify.service` 제거. install.sh 의 stop:1584 + stop-and-disable:1604 는 정합 유지 (oneshot 의 stop 도 active 라면 SIGTERM, inactive 라면 no-op — 정합).

---

## H — High (강력 권고)

### H1. `_migrate_agent_schema` 의 yaml.example sync 가 ruamel.yaml `default_v` deep-copy 안 함 — 운영자 yaml 의 nested dict 변경이 yaml.example 의 default 와 reference 공유 risk

**위치**: `install.sh:884-886` (ruamel.yaml 의 `target_top[k] = default_v` 직접 assignment)

**인용**:
```python
for top in ("operations", "agent"):
    example_top = example.get(top, {}) or {}
    target_top = data.setdefault(top, {})
    if isinstance(example_top, dict) and isinstance(target_top, dict):
        for k, default_v in example_top.items():
            if k not in target_top:
                target_top[k] = default_v
```

**문제**:

`default_v` 가 ruamel.yaml 의 `CommentedMap` / `CommentedSeq` (e.g. `agent.models` dict-of-string, `operations.retry` nested dict) 인 경우, **`target_top[k] = default_v` 는 reference assignment**. 즉 `data["operations"]["retry"]` 와 `example["operations"]["retry"]` 가 같은 객체 share. 후속 `yaml.dump(data, ...)` 가 정상 작동하나, **dump 직전 `example` 의 데이터를 inadvertent 수정 시 data 도 영향** — 본 PYEOF 내에서 직접적 risk 0 (example 후속 수정 없음).

그러나 ruamel.yaml 의 round-trip 시 **commented metadata 가 example 의 source 위치 (path 정보) 와 연동** — 운영자 yaml backup `.wikihub-bak.<utc_iso>` 의 diff 확인 시, 본 fix 가 sync 한 field 의 comment 가 yaml.example 의 comment 그대로 복사. 이는 디자인 의도 (yaml.example 정본화) 정합이나 운영자 yaml 의 comment style 과 mismatch 가능 (운영자가 자신의 yaml 에 comment 작성 중이면 자동 sync 한 field 만 example 의 comment 가짐).

**평가**:

R2 fix 의 design 의도 (analysis_and_design.md §2.4.2) 는 "schema authority = yaml.example" 의 정합 — comment 도 sync 가 의도. 그러나 본 review 의 운영 안전성 관점:

- (i) **commented field** (e.g. `operations.graphify_backend` 의 인라인 comment 약 200자) 가 자동 sync 시 운영자 yaml 의 길이 갑자기 증가 — yaml diff review 부담.
- (ii) **dict reference share** 의 indirect risk — install.sh PYEOF 내부 수정 안 하나, ruamel.yaml 의 round-trip 내부 mutation (e.g. flow vs block style 정규화) 시 example 도 영향.

**권고**:

`copy.deepcopy(default_v)` 적용 — `target_top[k] = copy.deepcopy(default_v)`. 1줄 보강. reference share risk 차단 + 운영자 backup diff 의 deterministic 보장 + commented metadata 의 정상 copy.

### H2. `graphify_partial_failure_threshold` field 가 `wikihub.yaml.example` 부재 — R2 fix yaml.example sync 가 본 field 운영자 yaml 에 자동 추가 안 함

**위치**:
- `scripts/wikihub_graphify.sh:140` (yq default `0.5`)
- `_system/commands/graphify.md:50` (도큐먼트 — yaml.example 에 명시되어야 한다고 안내)
- `wikihub.yaml.example` (operations 블록 — `graphify_partial_failure_threshold` 부재, grep 확인)

**문제**:

design v2 §2.1.2 + graphify.md 도큐먼트 (line 50) 명시 "operations.graphify_partial_failure_threshold default 0.5" — 운영자 override 가능 명시. 그러나 yaml.example 에 본 field 미정의 → R2 fix 의 yaml.example sync 가 자동 추가 안 함 → **운영자가 yaml 에 본 field 명시 path 부재** (운영자가 yaml.example 참조 시 본 field 비명시).

본 reviewer 가 wikihub_graphify.sh:140 의 `yq '.operations.graphify_partial_failure_threshold // 0.5'` default fallback 정합 — 운영자 yaml 부재 시 0.5 사용. 그러나:

- 운영자가 threshold override 의도 시 yaml.example 에 본 field 자체가 없으므로 정합 path 부재.
- design v2 §2.1.2 의 wikihub_graphify.sh 의 partial failure guard spec 이 yaml 정본화 미완 — schema authority (yaml.example) 단일성 위반.

**평가**:

본 fix scope 안 — yaml.example 에 1줄 추가 (default 0.5 + 인라인 comment) 만으로 정합. lint_operations_improvements (`2c4b42d`) 의 `graphify_timeout_sec` yaml expose 패턴 정합 — 본 fix 도 동일 패턴 적용 권장.

**권고**:

`wikihub.yaml.example` 의 operations 블록에 1줄 추가:
```yaml
graphify_partial_failure_threshold: 0.5   # graphify N/M ratio (graph nodes / wiki md docs) 의 partial failure 의심 임계치 (ADR-0036 §재검토 트리거 — Pass 3 silent partial failure 가드). 운영자 wiki 규모 작거나 entity stub 누적 적은 초기엔 false positive 우려 — 0.3 등으로 lower 가능.
```

R2 fix 의 yaml.example sync 가 자동으로 운영자 yaml 에 본 field 추가 — 정합 완성.

### H3. lint.md Step 9 의 "변경 감지" 분기 정확성이 wh-lint LLM 자체 응답에 의존 — 보수적 default policy 미명시

**위치**: `_system/commands/lint.md:231` (변경 감지 분기 spec)

**인용**:
```
2. **lint cycle 변경 없음** (다음 모두 0건: Step 3 자동 stub 생성 / Step 4.5 duplicate 처리 / Step 5 index.md 변경 / Step 7 archive 이동) → skip + `_lint/report.md` 에 1줄 `graph rebuild skipped (no changes)` ← **cost gate (사용자 핵심 의도, v0.1.8 신설)**
```

**문제**:

wh-lint hermes skill 의 LLM (deepseek-v4-flash) 이 Step 3 / 4.5 / 5 / 7 의 4 분기 카운트를 LLM 응답 안에 정확히 트래킹해야 함. LLM 응답 정확도 의존 — design v2 §2.2 의 검토 6 항 "wh-lint LLM 이 이를 정확히 트래킹 가능한지" surface:

- **case A (LLM 보수적 default `변경 있음`)**: 매 cycle graphify trigger → cost gate 무력화. graphify CLI 의 cloud LLM 호출 cost (gemma4:31b-cloud 등) 매 3h cycle 발생 — 사용자 핵심 의도 위반.
- **case B (LLM 보수적 default `변경 없음`)**: graphify 영구 stale → wiki 의 entity/concept 추가가 graph.json 에 반영 안 됨 → 후속 /wh-query 정확도 저하 + lint Step 3 의 graph 기반 점검 (line 63) 의 graph stale 의존.

design 본문 + lint.md Step 9 spec 모두 LLM 의 default 분기 결정 lock 안 함 — **운영자가 cost vs graph freshness 의 trade-off 결정 path 부재**.

**평가**:

LLM 응답 정확도는 deepseek-v4-flash 모델 특성 의존 — 본 fix 의 design scope 안에서 결정 가능. 권장 default = **변경 있음 보수적** (graph staleness 회피 우선) + 운영자 yaml toggle 제공:
```yaml
operations.graphify_cost_gate_strict: false  # true 면 LLM 이 4 분기 모두 0 confirmation 시만 skip. false (default) 면 LLM 의 보수적 변경 있음 채택 — graph freshness 우선.
```

또는 alternative: lint.service 의 ExecStart 후처리 가 4 분기를 deterministic 카운트 (LLM 의존 회피) — `_lint/report.md` 의 마크다운 섹션 (e.g. `## 신규 stub 생성: N건`) 을 grep 으로 추출 + 0건 체크. design v2 §2.2 검토 6 의 "LLM 의 자체 응답 정확도 의존" 의 결론 lock — backlog 후속 검토.

**권고**:

(a) **lint.md Step 9 spec 보강**: LLM 보수적 default `변경 있음` 명시 — graphify cost > graph staleness cost (사용자 핵심 의도 정합 — graphify_enabled toggle 자체가 cost gate 1차 보호, 변경 감지 cost gate 는 2차 보호).

(b) **Q3 backlog 등록**: deterministic 카운트 (LLM 의존 회피) 별도 feature 로 — `_lint/report.md` 의 grep 패턴 명세 + lint.service ExecStart 후처리 wrapper 신설.

### H4. `wikihub-graphify.service` 의 timer 부재 운영자 가시성 부족 — install.sh ok 메시지 / README 의 명시 부족

**위치**:
- `install.sh:1145-1146` (Step 6 ok 메시지 — 4 skills 명시)
- `install.sh:1635-1639` (start sequence — graphify 부재 정합)
- `README.md:159` (4 skill + graphify systemd 1행 — diff 확인)

**문제**:

`wikihub-graphify.service` 는 timer 없음 + lint Step 9 가 trigger — 운영자가 본 unit 의 존재 + cost gate 운영 모델을 이해하는 path:

- (i) `_system/wiki-schema.md:55-56` directory tree 의 1줄 (`wikihub-graphify.service.template ... timer 없음, lint Step 9 가 trigger`).
- (ii) `_system/commands/graphify.md:55-56` 의 운영 흐름 섹션 (timer 자동 + 메인테이너 수동).
- (iii) `README.md:159` 의 1행 (v0.1.8 update_path_fixes: ... lint Step 9 가 변경 시만 trigger).

→ 위 3 위치 명시는 정합. 단:

- **install.sh:1635-1639** 의 start sequence 가 lint.timer / pending-monitor.timer / monitor.timer 만 명시 — graphify 부재가 운영자에게 invisible. install ok 메시지에 1줄 안내 권장 (예: "wikihub-graphify.service 는 timer 없음 — lint Step 9 가 변경 감지 시 trigger").
- **`systemctl --user start wikihub-graphify.service` UX** (Q1) — 너무 길다는 backlog 등록은 design v2 §3 Q1 명시 (정합). 운영자 manual grep 의존이 graphify failure surface (C1 결함과 결합) 의 second-order risk.

**평가**:

본 결함은 H 수준 surface — 운영자 가시성 + manual UX 안전성. C1 의 silent fail loop 결함과 결합 시 graphify 결과의 운영자 surface path = `journalctl --user -u wikihub-graphify.service` manual grep 만. 운영자가 본 unit 의 존재 인지 못하면 결과도 invisible.

**권고**:

(a) **install.sh:1639 직후 1줄 info 추가**:
```bash
info "  wikihub-graphify.service 는 timer 없음 — lint cycle (3h) 의 Step 9 가 변경 감지 시 trigger (cost gate). manual: systemctl --user start wikihub-graphify.service"
```

(b) **Q1 backlog 발급**: alias 신설 — `~/.local/bin/wikihub-graphify` symlink → `systemctl --user start wikihub-graphify.service`. install.sh 의 _step45_rclone 패턴 정합.

---

## M — Medium (보강 권장)

### M1. `install.sh` PYEOF 안 list element insert 가 ruamel.yaml metadata 와 충돌 가능성 — A_yolo_missing 복원 path

**위치**: `install.sh:890-894` (PYEOF 안 oneshot_args insert 패턴)

**인용**:
```python
agent = data.get("agent") or {}
agent_args = agent.get("oneshot_args")
if isinstance(agent_args, list) and "--query" in agent_args and "--yolo" not in agent_args:
    idx = agent_args.index("--query")
    agent_args.insert(idx, "--yolo")
```

**문제**:

ruamel.yaml 의 `CommentedSeq` (list-like) 의 `.insert(idx, value)` 동작은 documented 정합 — list element 의 insertion 은 안전. 단:

- (i) **inline comment**: 운영자 yaml 에 `oneshot_args: [chat, "--skills", "{skill}", --quiet, --query]  # F5 schema` 같은 trailing comment 가 있으면 `--yolo` insert 후 comment 위치 보존 vs 손실 동작이 ruamel.yaml 의 spec 의존.
- (ii) **block vs flow style**: 운영자 yaml 의 oneshot_args 가 multi-line block (- chat\n  - "--skills"\n ...) vs single-line flow (`["chat", ...]`) 의 둘 다 ruamel 처리 정합이나 insert 후 style 정규화 risk.

실제 multipass v0.1.0 yaml 의 oneshot_args 형식 (`["chat", "--skills", "{skill}", "--quiet", "--query"]`) 은 single-line flow — design v2 §2.4.3 의 `A_yolo_missing` 복원 path 정합. 운영자 manual edit (block style) case 는 design 의 jagged corner 외.

**평가**:

본 결함은 medium 수준 — ruamel.yaml 의 list insert 자체는 safe 하나 yaml.example sync 와 분리된 별도 처리 (line 890-894) 가 jagged corner 의 LLM 안전망. 본 fix 의 multipass v0.1.0 yaml 시나리오 cover 정합 — 단 운영자 manual edit yaml (rare case) 의 edge case backlog 등록 권장.

**권고**:

design v2 §2.4.3 의 "A_yolo_missing 복원" 의 인라인 comment / block style 대응 1줄 추가 — "운영자 manual edit yaml 의 trailing comment 보존은 ruamel.yaml round-trip 기본 동작 의존. block style ↔ flow style 정규화 자동" (정보성 명시 — fix 대상 외).

### M2. `graphify_partial_failure_threshold` 의 운영자 yaml 갱신 path 부재 → 운영자가 backup 로 revert 가능 명시 design v2 §2.4.2 의 한계

**위치**: design v2 §2.4.2 "set semantics 한계" + `install.sh:910-912` info 메시지

**인용** (analysis_and_design.md:372):
```
**set semantics 한계** (Reviewer 2 H1 흡수): `if k not in target_top` 는 운영자의 "자연 부재" 와 "명시 삭제" 구분 불가. 운영자 명시 삭제 의도가 본 fix 로 자동 복원되어 의도 손상 가능. 본 fix 의 scope 는 "자연 부재 (큰 jump)" 만 cover — 명시 삭제는 별도 backlog.
```

**문제**:

design v2 의 한계 명시 정합. 단 운영자 surface path 의 weakness:

- (i) **info log 의 generic `B_sync:{key}`** (install.sh:845) — 운영자가 어떤 field 가 어떤 default 로 sync 됐는지 yaml diff 또는 backup 비교 필요. design v2 §2.4.2 명시 "info log message: `B_sync:{key}` generic 만 출력" — 운영자 친화도 낮음.
- (ii) backup path (`$yaml.wikihub-bak.<utc_iso>`) 의 manual diff (`diff $yaml $backup`) 가 운영자 책임 — install.sh:910-912 의 안내 명시 부족.

**평가**:

본 결함은 medium 수준 — backup 자체는 정합 (line 853-855). 운영자 actionable 안내 보강이 design 본문 + 운영 안전성 강화.

**권고**:

`install.sh:845` 의 info 메시지 보강 — `B_sync:{key}` generic 외 default 값 1줄 추가:
```bash
B_sync:*)
    local field="${f#B_sync:}"
    local default_v
    default_v="$(yq ".${field} // \"<unknown>\"" "$WIKIHUB_SRC/wikihub.yaml.example")"
    info "  - [yaml.example sync] ${field} 부재 → ${default_v} 자동 추가 (운영자 명시 값 보존)"
    ;;
```

또는 design v2 §2.4.2 의 "set semantics 한계" 보강 — 운영자 diff path 명시.

### M3. `install.sh:864-907` 의 ruamel.yaml PYEOF 안 example 부재 check 부재 — drift detect (Group 1 PYEOF) 는 line 781-784 fail-fast 있으나 mutation PYEOF 는 부재

**위치**:
- `install.sh:781-784` (drift detect PYEOF 안 `isfile(example_path)` check)
- `install.sh:864-907` (mutation PYEOF — example_path read but isfile check 부재)

**인용**:
```python
# install.sh:864-907 — mutation PYEOF
with open(path, encoding="utf-8") as f:
    data = yaml.load(f)
with open(example_path, encoding="utf-8") as f:
    example = yaml.load(f)
```

**문제**:

drift detect PYEOF (line 781-784) 는 isfile check + sys.exit(2) 명시 — `WIKIHUB_SRC` env unset / sparse-checkout fail / yaml.example 삭제 시 fail-fast 정합. 그러나 mutation PYEOF (line 864-907) 는 `open(example_path)` 직접 호출 — file 부재 시 `FileNotFoundError` exception → install.sh 의 trap 에서 fail rollback 정합 (정합 path 이나 운영자 친화도 낮음 — generic Python traceback 만 surface).

drift detect 가 통과한 경우 mutation 까지 진입 정합 (sequential) — 단 drift detect (가벼운 read) 와 mutation (ruamel round-trip) 사이 race window 0 (single install.sh process) — file 부재 risk 0 in nominal path.

**평가**:

본 결함은 medium 수준 — nominal path 안전 + edge case 에서 fail-fast 보강 가치만.

**권고**:

`install.sh:870` 직후 isfile check 1줄 추가:
```python
if not os.path.isfile(example_path):
    print(f"ERROR: yaml.example 부재 — {example_path} (drift detect 통과 후 mutation 진입 직전 삭제됨?)", file=sys.stderr)
    sys.exit(2)
```

drift detect PYEOF 패턴 정합.

### M4. multipass 실측 가능성 — DoD §4 의 3 시나리오 verification criteria 의 quantitative spec 부족

**위치**: design v2 §4 DoD (analysis_and_design.md:427-429)

**인용**:
```
- [ ] multipass 실측: v0.1.0 yaml → `_migrate_agent_schema` 후 `--yolo` + 신설 field 모두 자동 추가
- [ ] multipass 실측: lint cycle 변경 시 `systemctl start wikihub-graphify.service` trigger → `graphify-out/graph.json` 생성 + journal surface
- [ ] multipass 실측: lint cycle 변경 없을 때 graphify trigger 안 함 (cost gate)
```

**문제**:

3 시나리오 의 verification criteria 가 binary (생성 / 안 생성):

- (i) **시나리오 1**: `_migrate_agent_schema` 후 검증 — yaml 의 `--yolo` element + 모든 yaml.example field 의 자동 추가 검증. 단 backup 의 diff 가 expected vs actual 일치 검증 path 부재 — `diff <(yq '.' new.yaml) <(yq '.' wikihub.yaml.example)` 의 차이 확인 권장.
- (ii) **시나리오 2**: graph.json 생성 확인 — graphify 의 LLM 호출 latency (cloud LLM 15분 limit) 의 timing flexibility 부재. design v1 reviewer 1 의 M4 가 이미 surface — design v2 §4 의 binary 검증 spec 미보강.
- (iii) **시나리오 3**: graphify trigger 안 함 검증 — `_lint/report.md` 의 1줄 `graph rebuild skipped (no changes)` grep + `journalctl --user -u wikihub-graphify.service --since "lint cycle 시점"` 의 absence 확인 양쪽 필요. design 본문 미명시.

**평가**:

design review 1 의 M4 (analysis_and_design.md design v1 단계 검토) 와 같은 결함 — design v2 가 흡수했으나 verification spec 자체는 binary 유지. 본 fix 의 multipass test 의 actionable spec 보강 가치.

**권고**:

DoD §4 의 3 시나리오 각각 verification command 1줄 추가 권장 (의사 코드):

```bash
# 시나리오 1
diff <(yq '.operations' ~/wikihub/wikihub.yaml | sort) <(yq '.operations' wikihub.yaml.example | sort) | grep "^>" | wc -l  # expected 0 (sync 후 모든 field present)

# 시나리오 2
systemctl --user is-active wikihub-graphify.service  # transient: active during run, inactive after
test -f ~/wikihub/graphify-out/graph.json && jq '.nodes | length' ~/wikihub/graphify-out/graph.json  # expected > 0
journalctl --user -u wikihub-graphify.service --since "5 min ago" | grep "graph rebuilt"  # expected match

# 시나리오 3
grep "graph rebuild skipped (no changes)" ~/wikihub/wiki/_lint/report.md  # expected match
journalctl --user -u wikihub-graphify.service --since "lint cycle start" | wc -l  # expected 0 (no trigger)
```

---

## L — Low (선택)

### L1. design v2 의 `wikihub_graphify.sh` line count estimate (60줄) vs actual (150줄) — design line estimate underestimate

design v2 §1.4 "scripts/wikihub_graphify.sh +60 / -0" — 실 코드 151줄 (file end at line 151). 2.5x underestimate.

원인: design v2 §2.1.2 의 spec 본문 (analysis_and_design.md:133-269) 의 코드 예시가 약 130줄 (이미 actual 와 근접) — line estimate 만 mismatch. design line estimate 의 정확성 약화 (design review 1 의 M2 와 같은 패턴).

권고: design v2 의 net line 계산 (`net -87`) 도 mismatch — actual 는 graphify.md 격하 (180줄 → 80줄, net -100) + wikihub_graphify.sh 신설 (+150) + 기타 ≈ net +90 정도. design 본문의 line estimate trace 가 Step 3 implementation review 의 정합 trace 가치 — 본 fix scope 외, design 본문 추후 정정 권장.

### L2. graphify CLI install path — `_install_graphify` 가 v0.1.0 → v0.1.8 jump 시 자동 trigger 검증

`install.sh:560-585` 의 `_install_graphify` 는 update path (`_step45_rclone:685`) 안에서 자동 호출 — v0.1.5 (`a35ddd7`) 부터 도입. v0.1.0 era 운영자가 multipass jump 시 venv 의 graphify CLI 부재 → install.sh --update 시 자동 설치 — 정합.

단 design 본문 (analysis_and_design.md §1.4) 미명시 — 본 fix 의 가정 (graphify CLI = install.sh 책임). README / 운영자 가시성 강화 1줄 권장.

### L3. wikihub_graphify.sh 의 `concurrency` 변수 unset risk — set -u + nested case

`wikihub_graphify.sh:60-70` 의 concurrency 결정:
```bash
concurrency=4
case "$model" in
    *cloud*) concurrency=4 ;;
    *)
        case "$endpoint" in
            http://localhost:*|http://127.0.0.1:*|http://\[::1\]:*) concurrency=1 ;;
            *)                                                       concurrency=4 ;;
        esac
        ;;
esac
```

→ concurrency 가 항상 초기 `concurrency=4` 로 set — `set -u` (line 14) 정합. 단 ollama case 외 (openai/claude/gemini/deepseek/kimi) 의 dispatch (line 88-117) 는 hard-coded `--max-concurrency 4` — concurrency 변수 미사용. design intent 가 ollama 만 endpoint-aware concurrency 인지 (graphify.md spec 정합) — 본 fix scope 안 정합.

### L4. lint.md Step 9 spec 의 `_lint/report.md` "graphify chain triggered" 1줄 vs report.md 의 actual content 정합 검증

`_system/commands/lint.md:236` 명시:
```
+ `_lint/report.md` 에 1줄 `graphify chain triggered — see journalctl --user -u wikihub-graphify.service`
```

본 1줄이 wh-lint hermes skill 의 LLM 응답 안에 정확히 작성되는지 = wh-lint LLM 의 spec following 의존. design v2 §2.2 의 미결 — 다만 LLM 의 spec following 정확도는 deepseek-v4-flash 모델 특성 의존 + wh-lint 의 system prompt 안에 lint.md 가 preload 됨 (ADR-0032 §sub-2). lint.md 자체가 spec source → LLM 의 spec following 신뢰 가능 (단 보장 안 됨).

backlog 등록 권장 — wh-lint LLM 의 report.md 작성 spec following 정확도 multipass 실측 + 결함 surface 시 wh-lint 의 lint.md system prompt 의 explicit instruction 강화.

### L5. `_system/skills/wh-graphify.frontmatter.yaml` 삭제 vs `_system/_generated/wh-graphify/SKILL.md` cleanup

design v2 DoD §4 명시 "`_system/skills/wh-graphify.frontmatter.yaml` 삭제" — git status 확인 완료 (deleted). 그러나 install.sh 의 Step 6 (`_step6_agent_skill`) 가 `_system/skills/_generated/wh-graphify/SKILL.md` 의 cleanup 책임 명시 부재 — update path 운영자가 v0.1.7 era 의 `_generated/wh-graphify/SKILL.md` 잔존 시 hermes 가 인식 가능성. 운영자 yaml 의 graphify_enabled / agent.binary 등 변경 시 stale skill 잔존 risk.

권고: install.sh `_step6_agent_skill` 안 `_system/_generated/wh-graphify/` 디렉토리 정리 1줄 추가 (rm -rf) — design v2 §1.4 의 install.sh `_step6_agent_skill` 변경 +5/-5 line 안에 흡수 권장.

---

## 통과 관점

다음 design 결정 + 코드 구현 정합 + 본 review 통과:

1. **D3=B (wh-graphify hermes skill 폐기 + systemd 격상)** — Layer 1 LLM wrapper over-engineering 제거 의도 정합 (wikihub_monitor 의 D1 정정 정신).
2. **`scripts/wikihub_graphify.sh` 의 backend dispatch 6 case** — graphify.md v0.1.7 spec 정합 + ADR-0038 namespace 격리 정합 + ollama endpoint-aware concurrency 정합.
3. **`scripts/wikihub_graphify.sh` 의 결과 검증 (Step 4)** — graph.json 존재 / invalid JSON detect / partial failure ratio guard — graphify.md Step 3 spec 정합 (단 H2 의 yaml field 명시 보강).
4. **`wikihub-graphify.service.template` 의 `Type=oneshot` + `SuccessExitStatus=0 75` + `TimeoutStartSec=1200`** — graphify_timeout_sec (900s) + 300s margin 의도 정합 (LLM cloud latency cover).
5. **lint.md Step 9 의 fire-and-forget spec** — `systemctl --user start wikihub-graphify.service` 의 비동기 정합 + lint exit code 의 graphify 결과 무관 정합 (graph 보조 자원 정합, ADR-0036 §D6).
6. **`install.sh` `_WIKIHUB_SKILLS` 4 skills 정정** + `_step6_agent_skill:1145` "4건 materialized" 메시지 정정 — D3=B 의 정합.
7. **`install.sh` `_migrate_agent_schema` 의 yaml.example sync 일반화** — schema authority 의 single source of truth 보존 (ADR-0031 §"후속 영향" 정합).
8. **`A_yolo_missing` 복원 narrowing** — legacy_migration_cleanup 의 부분 inversion (design v2 §2.4.3 명시) + jagged corner 처리 정합.
9. **`WIKIHUB_SRC` env guard (drift detect PYEOF)** — design v2 §2.4.2 Reviewer 2 M1 흡수 정합 (단 mutation PYEOF M3 보강).
10. **ADR cross-link 4건 갱신** (ADR-0036 / 0038 / 0031 / 0032) — design v2 §2.5 catalog 정합. ADR 본문 (예: ADR-0036 §"후속 영향" 의 v0.1.8 update_path_fixes 1줄) 정합 보존.
11. **README §"동작" 5 skill → 4 skill + graphify systemd service 1행** — diff 확인 (README.md:159).
12. **`_system/wiki-schema.md` directory tree 정합** — wh-graphify skill 제외 + wikihub-graphify.service.template 포함 + wikihub_graphify.sh 추가.

---

## 범위 외 (본 feature scope 외 — 후속 처리 권장)

1. **ops-alert.py 의 `collect_*` 함수 scope 일반화** (C1 권고 (c)) — vault_id namespace 외 (graphify / monitor / lint 등 wikihub global service) 도 cover. wikihub_monitor 의 같은 결함과 통합 처리 — 별도 feature 권장 (e.g. `ops-alert-scope-generalize`).
2. **deterministic 변경 카운트 (LLM 의존 회피)** (H3 권고 (b)) — `_lint/report.md` grep 패턴 + lint.service ExecStart 후처리 wrapper. 별도 feature scope.
3. **`~/.local/bin/wikihub-graphify` alias symlink** (H4 권고 (b), Q1) — install.sh 의 _step45_rclone 패턴 정합. 별도 feature.
4. **wh-lint LLM 의 spec following 정확도 multipass 실측 + system prompt 강화** (L4) — graphify chain trigger 1줄의 정확성 실 검증. 별도 feature.
5. **PyPI 의 supply chain hash pin** (`_install_graphify` 의 `pip install graphifyy>=0.8.0,<1.0.0`) — ADR-0036 §재검토 트리거 정합. v0.2.x.
6. **운영자 yaml 의 explicit field 삭제 의도 보존** — set semantics 한계 (design v2 §2.4.2) — 운영자 명시 `null` vs 자연 부재 구분 path. 별도 feature.

---

## 권장 흐름

1. **본 review 의 C1/C2 흡수 → design v2.1 또는 plan.md 보강**:
   - C1: design v2 §2.1.1 의 "OnFailure 의미 재정의" + backlog 신설 (BL-).
   - C2: `install.sh:1685` 의 try-restart 목록에서 `wikihub-graphify.service` 제거 (1줄 변경).
2. **H1/H2/H3/H4 흡수 권장** (단 release 미차단):
   - H1: `install.sh:884-886` 의 `copy.deepcopy` 1줄 보강.
   - H2: `wikihub.yaml.example` 의 `graphify_partial_failure_threshold` field 추가 (1줄).
   - H3: lint.md Step 9 spec 의 보수적 default 명시 (1줄).
   - H4: install.sh:1639 직후 info 메시지 1줄.
3. **M1~M4 backlog 등록 권장** — design v2 §3 미결 항목 확장.
4. **L1~L5 선택적 흡수**.
5. **multipass 실측 (DoD §4)** — M4 의 verification command 1줄씩 actionable spec 보강 후 진행.
6. **R1 + R2 결합 정합 검증**:
   - R1 (wh-graphify skill 폐기 + systemd 격상) 의 graphify chain trigger path 정합.
   - R2 (yaml.example sync) 가 wh-graphify skill 폐기와 무관하게 작동 — yaml.example 의 graphify_backend / graphify_profile / graphify_timeout_sec 등 field 가 v0.1.8 spec 정합 유지 (wikihub.yaml.example 의 line 60-64 확인 완료, 정합).
7. **canary cycle** — v0.1.8 force-update + multipass 실측 + 운영 12h 관찰 → v0.1.8 release.
