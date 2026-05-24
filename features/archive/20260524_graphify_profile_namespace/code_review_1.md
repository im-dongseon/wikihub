# Code Review 1 — Correctness & Edge Cases

- **Reviewer**: Claude subagent (Opus 4.7, 1M context, 컨텍스트 초기화)
- **Date**: 2026-05-24
- **Scope**: install.sh `_migrate_graphify_env` / `_migrate_agent_schema` 확장 + `_system/commands/graphify.md` Step 2~3 + `_system/commands/lint.md` Step 9 + `_system/commands/setup.md` Step 1 + `docs/adr/0038-*` + `docs/adr/0036-*` §Note + `wikihub.yaml.example`
- **Focus**: bash semantics + edge cases + security
- **방법**: 정적 reading + 실제 bash 실행 검증 (case glob 매칭, set -u, heredoc 재확장)

---

## Critical 결함

### C1. `graphify.md:71,88` — IPv6 loopback `[::1]` case glob 미매치 (silent NOMATCH → OLLAMA_BASE_URL 오분기)

**위치**: `_system/commands/graphify.md` 71 (endpoint 분기) + 88 (concurrency 분기). 양쪽 동일 패턴 `http://[::1]:*`.

**문제**: bash `case` 의 `[::1]` 은 **POSIX character class collation 문법** (`[:class:]`) 로 parse 됨. 실제 매칭 결과:

```bash
$ case "http://[::1]:11434" in http://[::1]:*) echo MATCH ;; *) echo NOMATCH ;; esac
NOMATCH
$ case "http://[::1]:11434" in http://\[::1\]:*) echo MATCH ;; *) echo NOMATCH ;; esac
MATCH
$ case "http://[::1]:11434" in "http://[::1]:"*) echo MATCH ;; *) echo NOMATCH ;; esac
MATCH
```

→ 운영자가 IPv6 loopback (`http://[::1]:11434`) 으로 endpoint 를 설정하면:
1. endpoint 분기 (line 71) 가 `OLLAMA_BASE_URL` (compat) 로 fallthrough — 의도 (native) 와 정반대
2. concurrency 분기 (line 88) 도 `*` fallthrough → 4 (cloud) — 의도 (1, 진짜 local) 와 정반대

ADR-0038 §Decision 1 + ADR-0036 §Note 결정 B 의 명시된 의도 ("loopback hostname → native") 와 실 동작 불일치 — silent misroute.

**근거**: 실제 `/bin/bash` 5.x 에서 검증 (위 transcript). design review 2 §H1 이 hostname-anchored 분기를 명시했으나 IPv6 bracket escape 는 빠짐.

**제안**: 두 case 문 모두 escape 적용.

```bash
case "$endpoint" in
    http://localhost:*|http://127.0.0.1:*|http://\[::1\]:*) ollama_env_name="OLLAMA_HOST" ;;
    *) ollama_env_name="OLLAMA_BASE_URL" ;;
esac
```

ADR-0036 §Note + ADR-0038 본문의 사례 표기 (`http://[::1]:*`) 는 documentation level — escape 없는 표기는 사람이 읽기 좋으나, 실 코드에는 `\[::1\]` 명시 필요.

### C2. `graphify.md:100` — `$1` 가 set -u 환경에서 unbound variable fatal

**위치**: `_system/commands/graphify.md:100` `if [[ "$1" == "--rebuild" ]]`

**문제**: 운영자가 `<agent_invocation> "/wh-graphify"` (인자 없음) 호출 시 `$1` 가 unset. install.sh strict-mode (`set -euo pipefail`, line 20) 와 동일 모드를 Hermes terminal subprocess 가 활성하면:

```bash
$ bash -c 'set -u; if [[ "$1" == "--rebuild" ]]; then :; fi'
bash: $1: unbound variable
```

graphify.md 자체에 `set -u` 선언이 없어 Hermes terminal 의 default shell 환경이 strict 면 fatal. graphify.md:53 의 주석 "set -u 안전" 은 indirection (`${!var:-}`) 에만 적용되어 있고 `$1` 는 누락.

**근거**: install.sh `set -euo pipefail` 가 본 patch 의 strict-mode 가정. design review 2 §H2 가 indirection 만 cover (line 58~60), positional param 은 미언급.

**제안**: `${1:-}` 로 safe default.

```bash
if [[ "${1:-}" == "--rebuild" ]]; then
    rm -f "$WIKIHUB_HOME/graphify-out/graph.json"
fi
```

C2 가 Hermes terminal shell 의 strict-mode 여부에 dependent — 실 환경이 strict 가 아니면 silent OK 이나 design review 2 §정합확인 의 "bash-ism 가정" trust 와 set -u 안전 명시가 동시에 깨지는 부정합. 안전 fix 가 1글자 (`:-`) — 즉시 반영 권장.

---

## High 결함

### H1. `install.sh:937,969` — `while read` last-line-no-newline 누락 → 운영자 ollama_gemma 값 silent reset

**위치**: `install.sh _migrate_graphify_env` 의 두 `while IFS= read -r line; do ... done < "$wh_env_file"` (line 937~947 detect + line 969~984 capture).

**문제**: 운영자가 env 파일 마지막 줄에 trailing newline 을 안 붙여 두고 그 줄이 `WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_MODEL=foo` 라고 가정. `read` 는 EOF 무 newline 시 마지막 줄을 buffer 에 채우되 exit code 1 → `while` loop 가 body 실행 안 하고 종료. 결과:

```bash
$ printf "x=1\ny=2" > /tmp/test; while IFS= read -r l; do echo "[$l]"; done < /tmp/test
[x=1]                       # y=2 누락
```

1. **detect 단계**: `has_model=0` → drift 감지 (over-report. migration 실행되긴 함.)
2. **capture 단계**: `og_model=""` (운영자 값 못 잡음) → `: "${og_model:=gemma4:31b-cloud}"` 가 default 채움 → **운영자가 의도한 model 값이 default 로 silent 덮어쓰임**.

ADR-0031 §Note + ADR-0038 §Decision 5 의 "value mutation 회피" 원칙 위반. operator 의 model 선택이 install.sh 1회 실행으로 무음 reset.

**근거**: bash POSIX `read` semantics. 실제 검증 transcript:

```bash
$ printf "MODEL=foo" > /tmp/env; while IFS= read -r l; do echo "[$l]"; done < /tmp/env
# (출력 없음) → loop body 0회
```

운영자가 `vi` / `nvim` 으로 편집하면 자동 newline 추가되나 `echo -n` / `printf` 또는 일부 GUI editor 는 newline 누락 가능. install.sh 가 매 호출 atomic write (`cat <<EOF ... EOF`) 로 trailing newline 추가하므로 *2회차 이후 안전*. 단 OCI 운영의 첫 migration 에서 fragile.

**제안**: while loop 의 표준 idiom 적용 — 마지막 줄을 buffer 에서 명시적 처리.

```bash
while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
        ...
    esac
done < "$wh_env_file"
```

`|| [[ -n "$line" ]]` 추가가 last-line-no-newline 케이스 cover. 양쪽 loop (detect + capture) 모두 동일 패턴 적용 필요.

---

## Medium 결함

### M1. `_migrate_agent_schema` W_ flag — profile 값에 `,` 포함 시 CSV split 깨짐

**위치**: `install.sh:791` (Python: `f"W_graphify_profile_invalid:{_profile}"`) + `install.sh:812` (bash: `IFS=',' read -ra _flags <<< "$drift_flags"`).

**문제**: 운영자가 yaml 에 `graphify_profile: "foo,bar"` (정규식 fail) 박은 경우, Python 이 `W_graphify_profile_invalid:foo,bar` 를 emit → bash 가 `,` 로 split → 2 토큰 (`W_graphify_profile_invalid:foo` + `bar`). 두 번째 토큰은 case `*` fallthrough 로 silent ignored — warn 의도가 일부만 surface. (`:` 자체는 bash CSV 와 무관 — `:` 가 IFS 가 아니므로 split 안 됨 → `${f#W_graphify_profile_invalid:}` 추출 정상 동작).

**근거**: YAML 문법상 `,` 는 quoted string 내부 합법 (`graphify_profile: "foo,bar"` 는 valid YAML scalar). install-time validation 의 surface 가 partial. 실 빈도 낮음 (profile 명에 `,` 박는 운영자 reasonable 가정 아님) — Medium 으로 분류.

**제안**: drift_flags 의 separator 를 `,` 가 아닌 newline 으로 교체.

```python
# Python
print("\n".join(flags))
```

```bash
# bash
while IFS= read -r f; do
    case "$f" in
        ...
    esac
done <<< "$drift_flags"
```

newline 은 환경변수 / yaml string 에 박힐 가능성 매우 낮아 robust. 또는 W_ 값을 base64 encode (overkill).

### M2. `_migrate_graphify_env` detect 단계의 `WIKIHUB_GRAPHIFY_*=*` 패턴이 ollama_gemma 외 namespace 도 cover — 그러나 detect 의 has_endpoint/api_key/model flag 는 ollama_gemma 전용

**위치**: `install.sh:980` (capture 단계의 `WIKIHUB_GRAPHIFY_*=*) custom_lines+=...`).

**문제**: detect 단계 (line 937~947) 는 `WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_<KEY>` 만 explicit case 분기 — 그 외 namespace (`WIKIHUB_GRAPHIFY_OPENCODE_MINIMAX_*` 등) 는 detect case 의 default `*` 로 흘러 silent. detect 단계가 의도된 한정 동작 (ollama_gemma drift 만 check). 그러나 capture 단계의 `WIKIHUB_GRAPHIFY_*=*) custom_lines+=...` 보다 **case 분기 순서가 앞에 있으므로** OLLAMA_GEMMA 의 명시 case 가 먼저 match → 분기 OK. 정합 확인 (no issue).

→ **재분석**: case 의 ollama_gemma 명시 case 3개 (line 974, 976, 978) 가 `WIKIHUB_GRAPHIFY_*=*` (line 980) 보다 위 — bash case "first match wins" semantics 정합. 운영자 custom profile 만 default 흡수. 정합 OK.

**제안**: 없음 (false positive 회피 — 정합 확인 섹션 이동).

→ 본 finding 은 정합 확인으로 이동 (아래 "정합 확인" 참조).

### M3. `_migrate_graphify_env` — `_migrate_agent_schema` 가 yaml backup 만들지만 env backup 과 timestamp 가 분리

**위치**: `install.sh:833` (yaml backup) + `install.sh:961` (env backup). 둘 다 `date -u +%Y%m%dT%H%M%SZ` — 같은 명령 두 번 호출 → 1초 이내면 동일 timestamp 일 가능성 높지만 install.sh 가 무거운 step 사이에 둘 다 호출되므로 second drift 가능.

**문제**: ADR-0036 §Note 의 Rollback procedure (line 310 `cp ~/.config/wikihub/env.wikihub-bak.<utc_iso> ~/.config/wikihub/env` + line 314 `cp ~/wikihub/wikihub.yaml.wikihub-bak.<utc_iso> ~/wikihub/wikihub.yaml`) 는 *같은* `<utc_iso>` 로 일관성 가정. 운영자가 yaml backup 보고 그 timestamp 로 env backup 도 찾으면 file not found.

**근거**: install.sh 의 sequential 실행 흐름에서 `_migrate_agent_schema` 와 `_migrate_graphify_env` 사이에 다른 step (`_step6_agent_skill` 등) 가 있는지 확인하면 — 실 호출 (line 1911 → 1912 → 1913): `_step5_instance_dirs` → `_migrate_graphify_env` → `_step6_agent_skill` (내부 `_migrate_agent_schema`). 두 backup 사이에 venv Python invocation + ruamel yaml dump + git/hermes 조작이 들어가 수십초 ~ 수분 drift 가능.

**제안**: install.sh main flow 초입 (line 1900 근처) 에서 `local _migration_utc="$(date -u +%Y%m%dT%H%M%SZ)"` 한 번 캐시 + export → 두 마이그레이션 함수가 동일 timestamp 사용. 또는 ADR-0036 §Rollback procedure 의 `<utc_iso>` 가 *서로 다를 수 있음* 명시.

### M4. `graphify.md:108` `case "$backend" in ollama)` — backend value 의 leading/trailing whitespace robust 부재

**위치**: graphify.md Step 2 backend dispatch case.

**문제**: `backend="$(yq '.operations.graphify_backend // "ollama"' "$WIKIHUB_HOME/wikihub.yaml")"` — yq 의 결과가 명시적 trim 안 됨. yaml 의 `graphify_backend: ollama ` (trailing space) 또는 quote 누락된 값은 yq 가 그대로 emit → bash case `ollama)` 미매치 → default `*)` 분기 → exit 2.

**근거**: yq (mikefarah) 는 default scalar emit 시 trim 됨 — 단 quoted string 내부 space 보존. 운영자 실수 (`graphify_backend: " ollama"`) 면 silent fail. 실 빈도 낮음.

**제안**: trim 명시 — `backend="$(yq '.operations.graphify_backend // "ollama"' "$WIKIHUB_HOME/wikihub.yaml" | tr -d '[:space:]')"`. 또는 case 패턴 자체에 `*ollama*` 같은 substring 으로 lax — 후자는 false positive 위험 (cloudburst 사례 L3 와 동일 문제).

---

## Low / 권장 개선

### L1. `_migrate_graphify_env` info 로그 인용 부호 inconsistency

`install.sh:954` info 메시지의 "(OLLAMA_*/ANTHROPIC_API_KEY/OPENAI_API_KEY/GEMINI_*)" 가 8 종 legacy 키 중 6 종만 명시 (`OLLAMA_BASE_URL/API_KEY/MODEL` 을 `OLLAMA_*` 로 묶음 — OK. `GEMINI_API_KEY/BASE_URL/MODEL` 을 `GEMINI_*` 로 묶음 — OK. 단 메시지에 `OPENAI_API_KEY` 만 있고 detection 에는 `OPENAI_API_KEY` 만 있음 — 정합). 정합 확인 (no issue).

→ 본 finding 은 정합 확인 섹션으로 이동.

### L2. `graphify.md:84` `case "$model" in *cloud*)` — substring fragility

design review 1 §L3 명시. 본 review 에서 추가 finding 없음. deferred 결정 정합.

### L3. `_migrate_agent_schema` `B_graphify_profile` 만 ADR-0038 prefix, `W_graphify_profile_invalid` 도 ADR-0038 prefix — 일관성 OK

`install.sh:826,827`. design review 1 §L4 의 우려 (prefix consistency) 가 본 patch 에서 ADR-0038 로 통일 — 정합 확인.

→ 본 finding 은 정합 확인 섹션으로 이동.

### L4. heredoc 의 `\`operations.graphify_profile\`` backtick escape

`install.sh:1001` `# yaml \`operations.graphify_profile\` ...`. unquoted EOF heredoc 내부 backtick 은 command substitution → escape 필요. 본 patch 가 정확히 escape 적용 — 정합 OK.

→ 본 finding 은 정합 확인 섹션으로 이동.

---

## 정합 확인 (no issue)

- **install.sh:20 `set -euo pipefail`**: `_migrate_graphify_env` 전체 local 변수 (`og_endpoint=""` 등 line 968) 가 선제 초기화 → `: "${og_endpoint:=default}"` 가 set -u 하 안전. **OK**.
- **install.sh:962 `cp -p "$wh_env_file" "$backup"`**: `-p` 가 mode 보존 → backup 도 0600 (env 파일 이미 0600 보장, line 711). chmod 추가 호출 불필요. **OK**.
- **install.sh:1028 `mv "$tmp" "$wh_env_file"`**: 동일 디렉토리 (`$wh_config_dir`) 내 tmp → atomic rename. mode 는 source ($tmp) 의 umask 결정 — install.sh 의 default umask 가 0022 일 경우 0644 가 잠깐 노출. 직후 `chmod 600` (line 1029) 가 close — race window 가 atomic mv 직후 chmod 직전 마이크로초 단위. fork/exec 외부 reader 가 그 사이 open 할 확률 negligible. **운영 OK** (mode race window 의 보안 impact minimal — 운영자 home + 0700 config dir 보호 layer).
- **install.sh:1032 `find ... -delete 2>/dev/null || true`**: 디렉토리 부재 / 매치 0건 / permission denied 모두 swallow. `set -e` 환경에서도 `|| true` 가 보장. **OK**.
- **install.sh:994~1006 heredoc unquoted EOF 의 `${og_endpoint}` 변수 expansion**: 의도된 동작 (default 값 또는 운영자 보존 값 inject). 단일 expansion pass — value 내부 `$(...)` / backtick 있어도 재실행 안 됨 (검증 transcript). **보안 OK**.
- **install.sh:1004 `${og_endpoint}` 의 special char 처리**: value 가 운영자가 직접 작성한 URL — 표준 URL 문법에 `\`/`$`/`"` 거의 없음. 단 escape 안 되면 dollar-substitution 가능 (예: `og_endpoint='$HOME/x'` 면 heredoc 이 `$HOME` 확장). 그러나 그런 값이 env 에 박힐 시나리오 unrealistic. **OK** (defense-in-depth 로 `<<'EOF'` quoted heredoc + 별도 echo 도 가능하나 over-engineering).
- **install.sh:935~947 detect 단계 case 순서**: ollama_gemma 3 키 explicit case 가 generic `WIKIHUB_GRAPHIFY_*=*` 앞에 — bash case "first match wins" 정합. **OK**.
- **install.sh:786~791 W_ flag generation**: profile 값에 `:` 박혀도 `${f#W_graphify_profile_invalid:}` extract 정상 (`${f#prefix}` 는 가장 짧은 left match — `W_graphify_profile_invalid:` prefix 만 제거, 그 뒤의 `:` 는 value 일부로 보존). **OK**.
- **`_migrate_agent_schema` Python `import re as _re`**: lazy import 패턴, 다른 import 와 분리 — 운영 정합 OK. drift detection block 내부 1회 실행. **OK**.
- **W_ flag migration block 미변경**: design 의도 — warn only, value 자동 수정 안 함 (ADR-0031 §Note value mutation 회피). bash info-log loop 의 W_ case label 과 정합. **OK**.
- **graphify.md:43~62 profile resolve**: yq fallback (`// ""` + `// "ollama"`) + 정규식 fail-fast + `${!var:-}` indirection + model unset fatal — design review 2 §H2 + §정합확인 의 모든 요구 cover. **OK** (C2 의 `$1` 만 별도).
- **graphify.md:69~74 backend=ollama guard**: ENDPOINT-less profile (claude_direct 등) 의 endpoint indirection 안전 — design review 2 §H2 충족. **OK**.
- **graphify.md:155 `timeout 720`**: design review 2 §M2 (yaml expose deferred) 정합. partial graph.json 보호는 Step 3 의 `jq 'keys'` + delete + exit 1 로 cover. **OK**.
- **graphify.md:167~171 Step 3 partial 보호**: `jq 'keys' ... 2>/dev/null || { rm + exit 1; }` — A5 정합. **OK**.
- **lint.md:183 graphify dispatch 1줄 reference**: C3 정합 — backend dispatch single source 가 graphify.md Step 2 로 통일. v7 패턴 설명 block 제거 정합. **OK**.
- **setup.md:110 terminal.env_passthrough 안내 정리**: ADR-0038 정합 — namespace 격리 후 안내 불필요 명시. **OK**.
- **wikihub.yaml.example:57~58**: `graphify_backend: ollama` + `graphify_profile: ollama_gemma` — install.sh `_migrate_agent_schema` 의 default `graphify_profile: "ollama_gemma"` (line 893) 정합. **graphify_backend default 는 `""` (install.sh) vs `ollama` (yaml.example) 비대칭** — design §5b 가 명시 (fresh install 만 yaml.example default 갱신, 기존 운영 yaml 은 `""` 유지 = value mutation 회피). graphify.md:45 `yq '.operations.graphify_backend // "ollama"'` 가 fallback 으로 보전. **운영 OK** (design 의도 일치).
- **docs/adr/0038**: §Decision 1~5 + Consequences 정합. graphify.md / install.sh / setup.md 의 cross-link 정합. **OK**.
- **docs/adr/0036 §Note 2026-05-24**: 결정 A~F + Rollback procedure + Gap window 분석 정합. ADR-0038 분리 명시 (line 246). **OK**.
- **info / ok / warn helper 가용성**: install.sh:30~32 정의 → `_migrate_graphify_env` (line 930~) 가 호출 가능 (정의가 함수 앞쪽). **OK**.
- **idempotency 2회 호출**: 1회차 migration 후 fresh write 가 `WIKIHUB_GRAPHIFY_OLLAMA_GEMMA_*` 3 키 + trailing newline 보장 → 2회차 detect 가 `has_legacy=0, has_endpoint=1, has_api_key=1, has_model=1` → early return (line 949). **OK**. (단 H1 의 last-line-no-newline 케이스 1회차에 한정).
- **idempotency `_migrate_agent_schema`**: `graphify_profile` 추가 후 2회차 detect (`"graphify_profile" not in operations` False) → flags 미추가 → drift 0 → early return. **OK**.

---

## 우선순위 정리

| 우선순위 | finding | 조치 timing |
|---|---|---|
| **Critical** | C1 IPv6 `[::1]` case glob escape | **본 patch 즉시 fix** — 1글자 escape, runtime silent misroute risk |
| **Critical** | C2 `$1` set -u 안전 | **본 patch 즉시 fix** — `${1:-}` 1 token 변경 |
| **High** | H1 while read last-line newline | **본 patch fix 권장** — `|| [[ -n "$line" ]]` 추가, value mutation 위반 차단 |
| Medium | M1 W_ flag CSV split (`,` in profile) / M3 backup timestamp drift / M4 backend trim | 본 patch 흡수 권장 (각 1~3 줄) |
| Low | L2 `*cloud*` substring (design review 1 §L3 deferred 정합) | 운영 데이터 surface 후 v0.2.x |

**결론**: C1 + C2 + H1 본 patch fix 필수. design review 1/2 가 cover 한 architecture / `[::1]` 사례 표기를 따라가다 escape 문법 한 곳에서 silent break. 그 외 정합성 (env namespace + auto-migration + graphify v8 CLI + ADR cross-link) 은 sound. Step 3 implementation 의 핵심 의도는 잘 반영됨 — 본 review 가 finding 한 3건 모두 surface 영향 작거나 fix 가 trivial.
