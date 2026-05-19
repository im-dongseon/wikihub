# Design Review 2 — migration_prompt_review (operational/UX)

- **Reviewer**: subagent (general-purpose, operational/UX perspective)
- **Date**: 2026-05-20

## 종합 평가

v0.1.4 fix 의 `[[ -t 0 ]]` 가정은 "ADR-0023 default = pipe stdin" 만 본 partial view. Hermes 의 PTY 할당이 본 가정을 깬다는 사실은 v0.1.3 의 `--yolo` 누락 + v0.1.4 의 schema-drift 무력화와 동일한 **noninteractive 가정 미스매치** 패턴 — 매 release 마다 동일 root cause 가 다른 위치에서 surface 되고 있다. operational UX 관점에서 본 4 옵션 중 prompt 를 유지하는 (3)·(4) 는 그 패턴을 끊지 못한다. v0.1.0 미배포 + 운영자 base = Hermes 1대 + 메인테이너 1명이라는 현 컨텍스트에서 prompt 의 documentation 가치는 거의 0 이며 (관객 부재), Karpathy §2 정신 정합은 prompt 의 분기 자체 제거를 가리킨다.

## 3 운영 컨텍스트 분석

### (a) Hermes OCI PTY 환경

terminal tool subprocess 에 PTY slave 가 stdin 으로 붙음 → `[[ -t 0 ]]` true. Hermes 가 prompt 응답을 inject 할 hook 없음 (LLM 응답 stream 은 install.sh 의 stdin 과 무관). read 가 empty line 또는 EOF → default N → migration skip → systemd unit 에 `--yolo` 없는 ExecStart → tirith deny → vault/lint timer 매 사이클 실패. **본 환경이 실 운영 path 의 100%.** Hermes 가 `WIKIHUB_NONINTERACTIVE=1` 을 자동 inject 한다는 보장 없음 — env_passthrough 는 operator config 책임이라 install.sh 가 의존하면 안 됨.

### (b) curl|bash pipe 환경

stdin = pipe → `[[ -t 0 ]]` false → noninteractive 분기 자동 진행. v0.1.4 fix 가 본 시나리오만을 cover. ADR-0023 §Decision 의 default invocation 이므로 trade-off 무관.

### (c) operator manual tty 환경

`bash install.sh` 직접 호출 → tty stdin → prompt fire. **이 시나리오 자체가 현 시점 zero-traffic.** v0.1.0 미배포라 외부 운영자 부재 + 메인테이너는 macOS dev box (yaml 부재 → 즉시 return 0 으로 prompt 미도달). prompt 가 실제로 "운영자에게 보이는" 경로는 사실상 존재하지 않는다.

## 옵션별 평가

### (1) prompt 완전 제거 + 항상 auto-proceed

UX 단순도 최상. 3 컨텍스트 동일 동작 → 운영자 mental model 1개. backup 자동 생성이 의도 override safety net. v0.1.0 컨텍스트의 over-engineering 회피 정합. **문제는 외부 운영자 등장 후 — 운영자가 yaml 의 `--yolo` 를 의도적으로 제거해 운영하려 할 때 install.sh 가 매번 되돌림.** v0.2.x 의 외부 운영자 확보 시점에 본 결정 재검토 트리거 필요.

### (2) prompt 제거 + WIKIHUB_SKIP_MIGRATION env

(1) + escape hatch. 문제: **현 시점에 escape hatch 의 운영 가치 = 0** — `--yolo` 의도 제거 운영자가 존재하지 않음. CLAUDE.md §8 Atomic Change 관점에서 "migration prompt 동작 정합화" 라는 본 fix 의 단일 목적에 escape hatch 신설은 별도 feature 성격. v0.2.x 에서 운영자 사례 surface 되면 그때 환경 변수를 도입하는 것이 §2 Simplicity First + §8 Atomic 정합. **현 시점 채택은 over-engineering.**

### (3) prompt 유지 + default Y flip

`[[ -t 0 ]]` 가 Hermes PTY 에서 여전히 true 이지만 empty input → Y default → auto-proceed. 동작상 (1) 과 등가. 단, **운영자 관점에선 install.sh 가 prompt 를 던지는 듯한 출력만 남기고 답변 없이 진행 → log 가 "prompt 가 떴는데 누가 응답한 거지?" 의 혼란 surface.** Hermes log 에 부속 신호로 noise. typo 'n' risk 도 비현실적이지만 0 은 아님. documentation 가치는 prompt text 가 stderr/stdout 에 출력된다는 점에서 (1)·(2) 대비 약간의 surface advantage — 그러나 동일 정보를 `info "schema drift detected — auto migration"` 로도 충분.

### (4) prompt 유지 + read -t 5 timeout + default Y

매 install.sh 호출에 최대 5초 누적 delay. ADR-0030 의 update path 는 install.sh 빈번 재호출 모델 (운영자 force-push 후 OCI 측 `curl | bash` 1회 + 검증 cycle 마다 재호출) — 5초가 무시 가능하나 0 은 아님. `read -t` 의 PTY/non-PTY 모두 5초 wait → Hermes 환경에서 사용자 응답 없이 5초 마냥 기다리는 UX (Hermes 입장에선 subprocess 가 unresponsive). **over-engineering 의 가장 두드러진 사례** — 운영자 reaction window 보존이라는 가치가 현 시점 관객 부재로 정당화되지 않음.

## 운영자 의도 override 시나리오의 friction 비교

| 옵션 | `--yolo` 제거 의도 보존 path | friction |
|---|---|---|
| (1) | 매 install.sh 후 운영자가 yaml 수동 재편집 | 매 호출 후 1회 — 운영 부담 누적 |
| (2) | `export WIKIHUB_SKIP_MIGRATION=1` (shell rc 영속) | 1회 setup, 이후 0. **최저** |
| (3) | prompt 에 `n` 명시 입력 | Hermes PTY 에선 입력 hook 부재 → 불가능. manual tty 만 가능 |
| (4) | 5초 안에 `n` 입력 | Hermes 에서 불가능. manual tty 에서 time pressure 추가 |

(2) 가 ideal 이나 **현 시점 override 시나리오 자체가 가설**. v0.2.x 에 surface 후 도입이 §8 정합.

## v0.1.3~v0.1.4 install.sh 결함 패턴 분석

v0.1.3 첫 OCI 배포 — yaml 의 `--yolo` 미반영 결함 surface (F5 form 인데 `--yolo` 없는 yaml 의 migration trigger 부재). v0.1.4 fix — `_migrate_agent_schema` 에 `[[ -t 0 ]]` noninteractive 분기 추가. **그 fix 자체가 Hermes PTY 에서 다시 무력화.** 동일 root cause: install.sh 의 noninteractive 검출 layer 가 "운영 환경의 실 호출 경로 = Hermes terminal subprocess" 를 모델링 못함. v0.1.3 → v0.1.4 → v0.1.5 의 동일 패턴 반복 risk = `[[ -t 0 ]]` 같은 stdin-shape 휴리스틱을 다시 도입하면 또 다른 PTY-allocating caller 가 등장 시 동일 결함. **본 review 의 (1) 또는 (2) 채택만이 그 cycle 을 끊는다** — prompt 분기 자체를 제거함으로써 stdin shape 에 무의존. (3)·(4) 는 default flip 으로 동작상 cover 하지만 분기 자체가 잔존 → "어느 PTY-allocating caller 가 'n' 을 우발적으로 채워보내면?" 의 잠재 결함 존속.

## Strict Ranking

1. **(1) prompt 제거 + 항상 auto-proceed** — 현 컨텍스트 (v0.1.0 미배포 + 단일 운영자) 의 최저 friction. 분기 제거로 noninteractive 휴리스틱 cycle 종료. backup 이 의도 override safety net.
2. **(2) prompt 제거 + WIKIHUB_SKIP_MIGRATION** — (1) + escape hatch. 단일 운영자 base 형성 후 (v0.2.x) 채택 가치 있으나 현 시점 over-engineering.
3. **(3) prompt 유지 + default Y flip** — 동작은 (1) 과 등가지만 분기 잔존 + prompt-no-response log noise. 가치 대비 복잡도 손해.
4. **(4) prompt + 5s timeout** — 매 호출 5초 delay + Bash 4+ 의존 + Hermes 환경에서 가치 0. Most over-engineered.

## 권장

**1차 권장: 옵션 (1) — prompt 완전 제거 + 항상 auto-proceed.** v0.1.0 미배포 + Hermes 단일 운영자 + 메인테이너 1명 컨텍스트에서 prompt 의 가시화 가치는 0 에 수렴하고, `[[ -t 0 ]]` 가 catch-up cycle 의 root cause 임이 v0.1.3~v0.1.4 wave 로 입증됨. backup 생성 (`.wikihub-bak.<ts>`) 만으로 의도 override safety net 충분.

**부수 권장**:

- **info 메시지 강화**: `info "schema drift detected — auto migration (backup: $backup)"` 한 줄로 (3) 의 documentation 가치 대체. 운영자가 log 만 보고 "어떤 변환이 일어났는지" 추적 가능.
- **HISTORY.md 항목에 결정 근거 명시**: v0.1.5 entry 에 "prompt 제거 채택, escape hatch 미도입 — v0.2.x 외부 운영자 사례 surface 시 재검토" 명시. 결정 자체가 §8 Atomic 정합 + 미래 운영자 base 형성 시 회귀 검토 트리거.
- **재검토 트리거**: (a) 외부 운영자가 `--yolo` 의도 제거 시나리오 surface, (b) Hermes 외 다른 agent 등록 (codex/aider 등) 시 noninteractive 패턴 재평가. 둘 중 어느 하나 충족 시 옵션 (2) 의 escape hatch env 도입을 별도 feature 로 추출.
- **ADR 신규 여부**: 본 변경은 ADR-0032 §"Note (2026-05-19, feature `hermes_yolo_flag`)" 의 plumbing 정합 보강 — 별도 ADR 미신설 + `_migrate_agent_schema` 정책 변경은 ADR-0032 §Note 또는 ADR-0023 §"운영자 동의 surface" 본문에 1줄 추가로 처리.
