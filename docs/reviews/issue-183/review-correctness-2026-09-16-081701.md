# Review 1 — Correctness (issue #183)

- **Date**: 2026-09-16
- **Subagent**: `review-correctness` (`mode: subagent`)
- **Actual model**: `ollama-cloud/glm-5.2` (from `--print-logs`: `agent=review-correctness mode=subagent modelID=glm-5.2`)
- **Primary**: `ollama-cloud/deepseek-v4-flash`
- **Scope**: `git diff HEAD -- _system/systemd/wikihub-lint.service.template _system/systemd/wikihub-ingest@.service.template _system/commands/ingest.md`

## Verdict: PASS — no [high]/[mid] findings

## Confirmed by reviewer
- **Substitution key valid**: `render_systemd_units.py:271` puts `wikihub_src` into `_instance_wide_subs` (via `base_subs`), applied to all unit templates. `_wikihub_src()` (`:90-95`) always returns a non-empty default, so `{wikihub_src}` never renders empty; unresolved placeholder would KeyError via `_SafeDict`. Same key already used in `wikihub-graphify.service.template:15`.
- **Comments accurate**: `lint.md:161` does call `$WIKIHUB_SRC/scripts/_helpers/detect_alias_duplicates.py`; the empty-var claim holds since systemd `Environment=` does not shell-expand.
- **ingest.md rule matches reality**: 2-space indent confirmed in `_system/wiki-schema.md:195-197` and ADR-0039.
- No logic errors, nothing missing, no edge-case regression.

## [low] nits (non-blocking)
1. `wikihub-lint.service.template:14-16` / `wikihub-ingest@.service.template:17-18` — comment added where the graphify mirror has none (minor deviation from exact mirroring).
2. `wikihub-lint.service.template:17-19` — comment insertion shifts the `ADR-0038` block away from `EnvironmentFile=` (binding preserved, cosmetic).
3. `ingest.md:177` — 6-space sibling indent is consistent.

## 최PM 처리
- nit 1·2 는 주석 줄 순서 정리(env 줄을 주석 뒤로 이동)로 해소 — 두 template 모두 적용.
- nit 3 은 조치 불필요 (reviewer 도 consistent 로 판정).

## 최PM 독립 검증 (subagent 자체 보고 불신)
- 렌더 실측: `render_systemd_units.py --render` → `render ok: written=7` , `wikihub-lint.service:14` / `wikihub-ingest@nas.service:17` 에 `Environment=WIKIHUB_SRC=<src>` 주입 확인.
- DoD: `grep -c 'Environment=WIKIHUB_SRC'` → 각 1.
- helper 실행: `env WIKIHUB_SRC=<src> bash -c '[ -f ... ] && echo OK'` → OK.
