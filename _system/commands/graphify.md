# graphify

> **v0.1.8 update_path_fixes 정정 (2026-05-26)**: graphify 가 hermes skill 이 아닌 systemd service 로 격상.
>
> | 항목 | 정본 위치 |
> |---|---|
> | graphify CLI 호출 코드 | `scripts/wikihub_graphify.sh` (ADR-0036 §D6 single-source) |
> | systemd unit | `_system/systemd/wikihub-graphify.service.template` (timer 없음 — lint Step 9 가 trigger) |
> | 메인테이너 manual 호출 | `systemctl --user start wikihub-graphify.service` |
> | 자동 trigger | `_system/commands/lint.md` Step 9 (변경 감지 시만, cost gate) |
>
> **hermes skill `wh-graphify` 폐기 이유**:
> - Layer 1 LLM wrapper (deterministic bash 작업의 LLM wrapping) = over-engineering
> - semantic extraction 의 LLM 호출은 graphify CLI 내부 (Layer 2, ollama_cloud 등) 유지 — 정합

## 호출 흐름

```
wikihub-lint.timer (3h 주기) → wh-lint hermes skill (deepseek-v4-flash)
   ├─ Step 1~8: lint cycle 본체 (LLM 작업)
   └─ Step 9: 변경 감지 분기 (cost gate)
       ├─ 변경 없음 → skip + report.md "graph rebuild skipped (no changes)"
       └─ 변경 있음 → systemctl --user start wikihub-graphify.service
                          ↓
                  wikihub-graphify.service (systemd oneshot)
                       └─ scripts/wikihub_graphify.sh (bash, 정본)
                              ├─ yaml read (backend, profile, timeout)
                              ├─ env profile bundle resolve (ADR-0038)
                              ├─ graphify CLI extract (backend dispatch — 6 case)
                              │      └─ semantic extraction LLM 호출 (Layer 2)
                              └─ 결과 검증 + partial failure 가드 (N/M ratio)
```

## 사전 조건

- `graphify` CLI 실행 가능 — install.sh `_install_graphify` 가 `$VENV_PATH/bin/pip install "graphifyy>=0.8.0,<1.0.0"` 으로 venv 에 설치 (PyPI 패키지 `graphifyy`, ADR-0036). **fresh/update 경로 모두 install.sh `_step45_rclone` 에서 자동 설치** (v0.1.0 업데이트 시에도 graphify 자동 추가, Issue #43).
- `wiki/` 디렉토리 존재 (페이지 0개여도 OK — 빈 그래프 생성)
- `instance.root`/`graphify-out/` 쓰기 권한
- `~/.config/wikihub/env` 의 active profile bundle 채워짐 (ADR-0038 v0.1.7 follow-up — namespace 격리). yaml `operations.graphify_profile` 이 가리키는 env keyset (`WIKIHUB_GRAPHIFY_<PROFILE_UPPER>_<ENDPOINT|API_KEY|MODEL>`) 가 호출 시점에 backend-native env (OLLAMA_HOST/ANTHROPIC_API_KEY 등) 로 explicit 변환 주입 — 추가 profile cookbook → `docs/graphify-backend-test-reference.md` §6

## backend / profile / timeout

| yaml field | 정본 default | 의미 |
|---|---|---|
| `operations.graphify_enabled` | `true` | false 시 lint Step 9 가 graphify trigger 안 함 (운영자 cost / API key 부재 대응) |
| `operations.graphify_backend` | `""` (auto-detect 또는 명시) | `ollama` / `openai` / `claude` / `gemini` / `deepseek` / `kimi` 중 하나 |
| `operations.graphify_profile` | `ollama_gemma` | env namespace prefix (lowercase, ^[a-z][a-z0-9_]*$) — ADR-0038 |
| `operations.graphify_profiles.<profile>.timeout_sec` | (미설정) | **(v0.1.10)** profile-specific timeout. 지정 시 `graphify_timeout_sec` 보다 우선. Issue #36. |
| `operations.graphify_timeout_sec` | `900` (15분) | graphify CLI wrapper timeout — ADR-0036 §"후속 영향". profile-specific 미설정 시 fallback. |
| `operations.graphify_partial_failure_threshold` | `0.5` | N/M ratio threshold (Pass 3 silent partial failure 가드) |
| `operations.graphify_min_version` / `graphify_max_version` | `0.8.0` / `0.99.99` | graphify CLI 버전 범위 |

## 운영 흐름

- **timer 자동**: lint cycle 의 Step 9 가 trigger 책임. lint cycle 자체가 wikihub-lint.timer (3h 주기) 로 fire — graphify chain 은 변경 시만 fire (cost gate).
- **메인테이너 수동**: `systemctl --user start wikihub-graphify.service` — lint Step 9 분기와 동일한 systemd 경로. graph.json 이 손상되지 않은 일반 갱신용.
- **강제 rebuild** (`--rebuild`): systemd ExecStart 는 인자 전달 불가. 직접 script 호출 필요:
  ```bash
  cd "$WIKIHUB_HOME"
  source ~/.config/wikihub/env                    # ADR-0038 profile bundle (WIKIHUB_GRAPHIFY_<PROFILE>_*)
  scripts/wikihub_graphify.sh --rebuild
  ```
  `WIKIHUB_HOME`, `WIKIHUB_YAML`, `WIKIHUB_SRC`, `PATH` 가 설정된 shell 에서 실행. 위 `source ~/.config/wikihub/env` 로 두 env 를 직접 설정하지 않아도 systemd 의 EnvironmentFile 과 동일한 profile bundle env 가 로드됨. graph.json 손상·stale 데이터 강제 재생성 시 사용.

## 산출물

- `$WIKIHUB_HOME/graphify-out/graph.json` — NetworkX node-link format, 모든 entity/concept/source 의 graph
- `$WIKIHUB_HOME/graphify-out/.graphify_analysis.json` — communities + metadata
- `$WIKIHUB_HOME/graphify-out/manifest.json` — graphify CLI metadata
- `wikihub-graphify.service` 의 journal — `journalctl --user -u wikihub-graphify.service --since "1 day ago"`

## 실패 처리

| 실패 시점 | 동작 |
|---|---|
| graphify CLI 미설치 (exit 2) | OnFailure=ops-alert 발화 — install.sh 재실행 안내 |
| profile bundle 부재 (env model var unset, exit 2) | OnFailure=ops-alert 발화 — `~/.config/wikihub/env` 확인 |
| graphify extract timeout (exit 124) | SuccessExitStatus 정합 (75 분류 안 됨, 124 fail — ops-alert) |
| graph.json invalid JSON (partial write) | scripts/wikihub_graphify.sh 가 자동 삭제 + exit 1 (force clean) |
| N/M ratio < threshold | journal WARNING surface — ops-alert trigger 는 BL 등록 (현행 stderr warn 만) |

## 관련 ADR

- **ADR-0036** (graphify CLI integration) — PyPI graphifyy install + env 정책 + Pass 3 가정. §"후속 영향" 의 v0.1.8 update_path_fixes (B 채택) — systemd service 격상 명시
- **ADR-0038** (graphify env namespace isolation) — `WIKIHUB_GRAPHIFY_<PROFILE>_*` namespace. §"후속 영향" 의 wh-graphify skill 폐기 후 env namespace 정합 유지 명시
- **ADR-0032** (Hermes skill registration policy) — `_WIKIHUB_SKILLS` 4 skills (graphify 폐기) §"후속 영향"
