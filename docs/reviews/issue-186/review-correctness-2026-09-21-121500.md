# Review 1 — Correctness (issue #186)

- **Date**: 2026-09-21
- **Subagent**: `review-correctness` (`mode: subagent`) — 정상 호출
- **Actual model**: `ollama-cloud/kimi-k3`
- **Initial verdict**: NEEDS CHANGES

## Findings and disposition (모두 실측 판정)

| # | Severity | Finding | 판정 | 조치 |
|---|---|---|---|---|
| 1 | high | `$HOME` 을 python `-c` source 에 interpolation → HOME 에 quote 가 있으면 SyntaxError → 빈 target 등록 | **타당** (재현: `HOME=/tmp/it's` → SyntaxError) | 경로를 argv 로 전달 + 빈 값이면 `return 2` |
| 2 | mid | noop 분기에서 marker 재부착이 없어, 첫 실행에 marker 부착이 실패하면 영구히 누락 | 타당 | noop 경로에서 marker 확인 후 재부착 |
| 3 | mid | PATH guard 는 install-time `$VENV_PATH` bake, export 는 `$WIKIHUB_VENV` → 값이 갈리면 불일치 | 타당 | guard·export 모두 `\$WIKIHUB_VENV` (source-time 평가) |
| 4 | mid | `_ensure_session_env_file` 이 항상 0 반환 + `\|\| true` → `mv` 실패 시에도 미존재 파일을 등록 | 타당 | 실패 시 `return 1`, caller 가 성공 시에만 등록 |
| 5 | mid | 파일은 symlink spelling, 등록은 realpath — 동작은 정상이나 미문서 | 타당 (비결함) | 문서에 명시하지 않음 — 실익 없음 |
| 6 | mid | 신규 함수 테스트 부재 | 타당 | `tests/test_session_env.sh` 신규 (21 케이스) |
| 7 | minor | `column=60` cosmetic | 기각 | ruamel 이 알아서 정렬, 실해 없음 |
| 8 | minor | `lint.md` `WIKIHUB_VENV` unset 시 exit 127 | 채택 안 함 | fail-loud 가 의도 — 조용한 오대상보다 안전 (이슈 §6d 부합) |
| 9 | minor | stray sweep 이 신규 marker key 미처리 | 기각 (범위 밖) | marker 는 shell_init_files 용. stray 정리는 skills.external_dirs 전용 — 별개 계약 |

## Confirmed correct (리뷰가 명시)

- **비밀 분리 완전** — 4개 non-secret export 만, `~/.config/wikihub/env` 미접촉, dir 700/file 644, PID-suffix tmp + atomic mv
- **heredoc escape 정확** — `\$PATH` source-time 평가, install-time 상수 bake
- **off-by-one 없음** — `len(sif)-1` after append 정확
- **lock discipline** 기존 패처와 대칭 (fd 201, dispatch 전 해제)

## 판정 근거 (직접 실측)

```
$ HOME=/tmp/xxx/it's python3 -c "...expanduser('$HOME/...')"
SyntaxError: unterminated string literal    ← finding 1 재현
```

수정 후 동일 조건에서 등록 성공 (tests/test_session_env.sh 21 passed).

## Verification after fixes

```
bash tests/test_session_env.sh                      → 21 passed, 0 failed
python3 -m pytest tests/test_config.py -q           → 15 passed
bash -n install.sh                                  → OK
```

핵심 목표 실측 (session-env.sh source):

```
python3 = <venv>/bin/python3
extraction_status = success | chars = 27018
```
