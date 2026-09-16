# Review 1 — Correctness (issue #182)

- **Date**: 2026-09-16
- **Subagent**: `review-correctness` (`mode: subagent`)
- **Actual model**: `ollama-cloud/glm-5.2` (`agent=review-correctness mode=subagent modelID=glm-5.2`)
- **Primary**: `ollama-cloud/deepseek-v4-flash`
- **Scope**: `git diff HEAD -- install.sh wikihub.yaml.example docs/agent_dev_guide.md`

## Verdict: SOUND — no blockers, no data-destruction path

## Confirmed correct
- **realpath fix** (`install.sh:1257`) — contains-check `/.local/share/wikihub/` + endswith `/_system/skills/_generated` is right; matches the canonical realpath target in `_patch_hermes_external_dirs`.
- **`del data["skills"]` trace** (`:1275-1276`) — `skills` aliases `data["skills"]`; sibling keys survive; the delete only fires when it was the sole key.
- **canonical==stray guard** (`:1196`) — returns before any cp/mutation on all three resolution paths. No path mutates when equal.
- **bash pattern match** (`:889`) — `$_profile` quoted so metacharacters are literal; glob anchors correct.
- **`profile_args` array** (`:1330-1347`) — empty-array expansion safe under `set -u` on bash 5.x; display uses `"${profile_args[*]:-}"`.
- **marker detection** (`:1236-1247`) — `ext.ca.items.get(idx)` is the correct ruamel CommentedSeq idiom.
- **always returns 0** (`:1312`) — call site guarded by prior `|| return 2`.

## Findings
1. **[MINOR] `:1200` — no 7-day backup cleanup (asymmetry vs `:1183`)** — stray backup lives in a different dir than `hermes_dir`, so the existing `find` misses it.
2. **[NIT] `:1339-1351`** — silent audit-failure path (pre-existing behavior).
3. **[NIT] `:1335,1347`** — "5건" label stale; `WIKIHUB_SKILLS` has 6 entries (pre-existing, out of scope).
4. **[NIT]** no regression tests for new bash functions.

## 최PM 처리
- `:1200` 백업 cleanup 비대칭 → stray 백업용 `find -mtime +7` 추가로 해소.
- nit 2·3 은 기존 코드이며 본 diff 범위 밖 (surgical change 원칙) → 미변경.
- nit 4 회귀 테스트 → 아래 독립 검증으로 대체 (격리 케이스 6건 실증).
