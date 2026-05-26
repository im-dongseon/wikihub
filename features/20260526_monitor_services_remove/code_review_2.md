# Code Review 2 — monitor_services_remove (consistency + methodology)

**Date:** 2026-05-26
**Reviewer:** Claude subagent (Sonnet)
**Branch:** feature/v018-fix
**Scope:** post-Step 3 diff for monitor_services_remove feature (3 deletions of templates, 2 scripts, 1 lib + ADR-0037 supersede + ADR-0040 신설 + install.sh upgrade migration + carry-over edits)

---

## Assessment: Changes Requested

3 critical inconsistencies (operator-visible stale references that contradict the new code), plus several medium items (carry-over claim partial mismatch, doc/index stale fragments, residual orphan field auto-add path). The actual deletion + carry-over surgical edits are sound, but the surrounding documentation/cross-reference layer still trails the change. Recommended fix scope is small (≤ 10 lines across 3 files for the critical items).

## Issues Found

### 🔴 Critical 1 — `_system/systemd/ops-alert.service:17-18` (stale ADR + stale env name)

The systemd unit template still references the **old** ADR-0037 §D1 and the **old** `TELEGRAM_ALERT_BOT_TOKEN` / `TELEGRAM_ALERT_CHAT_ID` env names:

```
# ADR-0037 §D1 (v0.1.5) — Telegram alert channel env. lenient `-` prefix: 파일 부재/빈 값 OK.
# 운영자가 ~/.config/wikihub/env 에 TELEGRAM_ALERT_BOT_TOKEN + TELEGRAM_ALERT_CHAT_ID 채움.
```

But the actual reader `scripts/ops-alert.py:258-259` reads `TELEGRAM_MONITOR_BOT_TOKEN` / `TELEGRAM_MONITOR_CHAT_ID`, and `install.sh:744-750` writes the env template with `TELEGRAM_MONITOR_*`. ADR-0040 §carry-over table row 5 explicitly says the MONITOR rename is preserved.

**Impact**: Operator who reads `systemctl --user cat ops-alert.service` to debug alerts will be told to populate env keys that the dispatcher never reads — silent breakage of the entire Telegram channel.

**Fix**: 2-line update to reference ADR-0040 §D1 (carry-over of ADR-0037 §D1) and use the `TELEGRAM_MONITOR_*` names:

```
# ADR-0040 §D1 (carry-over of ADR-0037 §D1) — Telegram alert channel env. lenient `-` prefix: 파일 부재/빈 값 OK.
# 운영자가 ~/.config/wikihub/env 에 TELEGRAM_MONITOR_BOT_TOKEN + TELEGRAM_MONITOR_CHAT_ID 채움 (MONITOR prefix 는 historical — install.sh 의 env template 주석 참조).
```

This was missed in D2 (install.sh) and D4 (ops-alert.py inline) scopes — the unit template was not in the §"개정 범위" inventory table of analysis_and_design.md (rows 6-21 covered install.sh / wikihub.yaml.example / config.py / commands docs / ADR but not the systemd unit template itself).

### 🔴 Critical 2 — `README.md:160` (operator-facing wikihub-monitor entry retained)

README.md still has a dedicated bullet about `wikihub-monitor` feature including `monitor_enabled` yaml field reference:

```
- **wikihub-monitor** (v0.1.8): 매일 09:00 / 21:00 KST 에 12hr 윈도우 운영 보고서 자동 발송. … 비활성화: yaml `operations.monitor_enabled: false`.
```

This is the **public-facing** project intro. After ADR-0040, the feature is gone — operator reading this will look for a yaml field that no longer exists, then look for `wikihub-monitor.service` which fails to render, then file a support issue.

**Impact**: External operator confusion + contradicts ADR-0040 §Consequences which lists `monitor_enabled` as a removed field.

**Fix**: Delete L160 entirely; optionally also update L19 ("v0.1.x 운영 정본화 진행 중...") which still lists "wikihub-monitor (v0.1.8)" as a v0.1.x milestone (the README §개발 상태 line is historical-ish — lower severity, can stay or get a 1-line addendum).

This was missed in D5 (commands docs) scope — D5 covered `_system/commands/*.md` but not top-level `README.md`. The analysis_and_design.md §개정 범위 should have caught this in the initial grep but did not.

### 🔴 Critical 3 — `features/HISTORY.md` lines 132-140, 249-253 (stale `wikihub-monitor` / `pending-monitor` entries retained)

HISTORY.md still has the original `alert_pipeline_overhaul` (v0.1.5) and `wikihub_monitor` (v0.1.8) entries describing the *now-deleted* services in present-tense / as-if-active. The feature methodology (§3 Step 5) says HISTORY.md is append-only — those entries are historical record of *past releases* and should stay as-is.

**However**: when monitor_services_remove gets squashed at Step 5, a *new* HISTORY.md entry MUST be appended with `생성 ADR: ADR-0040` (per §3 Step 5 HISTORY.md format). The current diff does not include this entry yet (Step 5 not yet performed — but the DoD D6 says "신규 ADR-0040 신설" and D8 says verify, neither explicitly mentions HISTORY.md append). This is also missing from `analysis_and_design.md §DoD D1-D9`.

**Impact**: Step 5 risk — if the maintainer squashes without remembering to append HISTORY.md, the supersede chain becomes opaque (ADR-0040 exists but HISTORY skips the polish event).

**Fix**: Add an explicit D10 to analysis_and_design.md DoD: "HISTORY.md entry append at squash time, format per CLAUDE.md §3 Step 5". Or, the maintainer commits to remembering this at Step 5 — but the documentation gap stays.

(Strictly the Step 5 entry happens at squash time, so this is more of a **methodology completeness flag** than a current diff defect — bumping to 🔴 because forgetting it is a known recurring slippage pattern in this codebase per `features/backlog.md` notes.)

### 🟡 Medium 1 — `docs/adr/0040-monitor-services-remove.md:89` (version label "기존 v0.1.9 instance" is wrong)

ADR-0040 §"후속 영향" says:
```
- install.sh upgrade migration block 추가 — 기존 v0.1.9 instance 의 `wikihub-monitor.timer` + `wikihub-pending-monitor.timer` 를 stop + disable (orphan 회피).
```

But monitor units lived in **v0.1.8** (commit `f739c35`, `chore(release): v0.1.8`). The "기존 v0.1.9 instance" phrasing is technically incorrect — there is no deployed v0.1.9 with monitor units (v0.1.9 was bumped at `eb93253` and immediately gets the monitor removal in the same release window per `plan.md` "같은 release window 흡수"). The upgrade target is v0.1.8 (or possibly an early v0.1.9 canary that includes the monitors). install.sh:1630 comment "post-v0.1.9, monitor_services_remove" is also semantically ambiguous.

**Fix**: Change ADR-0040:89 to "기존 v0.1.8 instance (또는 monitor unit 이 enable 된 v0.1.9 canary instance) 의 ...". Optionally update install.sh:1630 to "upgrade migration (v0.1.9, monitor_services_remove): ...".

### 🟡 Medium 2 — `docs/adr/0032-hermes-skill-registration-policy.md:264, 299` (ADR-0032 still lists `pending_alert_age_sec` as Group B auto-add)

ADR-0032 §Note 2026-05-22 (yaml schema drift migration) lists `operations.pending_alert_age_sec: 3600` as a Group B auto-add field and references "ADR-0037 — `pending_alert_age_sec` (Group B 자료)" in Cross-references.

After ADR-0040, that field is gone. ADR-0032 was historically describing an event sequence, so it's acceptable to leave the historical claim — but a reader cross-referencing the migration catalog will be confused.

The actual `install.sh:_migrate_agent_schema` reads `wikihub.yaml.example` as the single source of truth (lines 871-917), so the field is *naturally* no longer auto-added — code is correct. But the ADR-0032 documentation now contradicts the live code's behavior.

**Fix**: Append a 1-line note to ADR-0032 §Note (after L266 or in Cross-references): "2026-05-26 (ADR-0040): `pending_alert_age_sec` 폐기 — Group B 자동 추가 catalog 에서 자연 제거 (`wikihub.yaml.example` single source of truth 정합)."

### 🟡 Medium 3 — ADR-0040 carry-over table omits §D2 (the deletion itself) and re-numbers oddly

ADR-0040:59-66 carry-over table lists §D1 / §D3 / §D4 / §D5 + 2 follow-ups, but skips §D2 entirely. §D2 of ADR-0037 (wikihub-pending-monitor systemd unit) IS the central thing being polished — a reader expects to see it in the table with status "폐기 — pending_monitor.py + systemd unit template + ops-alert.service trigger 호출 모두 제거". The reasoning is already in §Decision + Context, so it's not strictly missing — but for table completeness and reader scan affordance, an explicit row helps.

**Fix**: Add row 2 to the table:
```
| §D2: wikihub-pending-monitor systemd unit (architectural) | **폐기** — `_system/systemd/wikihub-pending-monitor.{service,timer}.template` + `scripts/pending_monitor.py` 제거. age-based surface 회복은 §재검토 트리거 항목으로 deferred. |
```

(Low criticality because the deletion is the whole point of the ADR and is covered elsewhere — flagging as Medium because the table claims "next decisions" comprehensively.)

### 🟡 Medium 4 — `features/backlog.md:118` (BL-N5 references deleted timer names)

```
| BL-N5 | systemd | timer enable catalog 정비 — lint.timer / pending-monitor.timer / monitor.timer 모두 install.sh 가 start 만, explicit enable 없음. reboot 후 자동 start 미보장 | code_review_2 M1 | medium (reboot 후 silent break) |
```

The backlog item still references `pending-monitor.timer` + `monitor.timer` which no longer exist. The underlying concern (reboot resilience for `wh-lint.timer`) is still valid for the surviving timer. Backlog is owned by feature workflow but is not gated by per-feature methodology — still, leaving stale references in an active backlog reduces its operational value.

**Fix**: Update BL-N5 to "wh-lint.timer / wh-ingest@*.timer ..." or close the entry if the surviving scope is no longer a concern.

### 🟡 Medium 5 — analysis_and_design.md §DoD D2 wording vs actual state

D2 says "monitor / pending-monitor / pending_monitor / wikihub_monitor 참조 0건 (`grep -c` 검증)". Actual `grep -c` on `install.sh` returns **4** hits (lines 1630-1633 of the upgrade migration block + line 747 comment). These are intentional carry-over per ADR-0040 §"후속 영향" L89, but the DoD wording does not anticipate the migration block.

**Fix**: D2 should read "monitor 참조 = upgrade migration block (`install.sh:1630-1633`) + env template historical comment (`install.sh:747`) 만 유지 — 그 외 0건". This is a documentation-of-intent issue, not a code issue.

### 🔵 Low 1 — design `analysis_and_design.md §Before` listing nonexistent `lint.py`

The before/after block at L75 lists `scripts/lint.py` which does not exist (lint runs as a hermes skill via `wh-lint.frontmatter.yaml` + `_system/commands/lint.md`; no Python script). Design doc inaccuracy, no code impact.

### 🔵 Low 2 — plan.md feat_id vs methodology recommendation

`plan.md` says "ADR 번호 — 기존 ADR-0037 → 0038 → 0039 까지 존재. **신규 = ADR-0040**." This matches `docs/adr/README.md`. No issue.

But plan.md L47 originally tentatively named the new ADR as **ADR-0038**: "신규 ADR-0038 (가칭)". The final ADR file is `0040-monitor-services-remove.md`. The plan was updated implicitly during Step 2 but the placeholder ADR-0038 reference in plan.md L47 is a minor stale artifact. (Plan files are append-only per `features/` lifecycle, but in-place clarification is acceptable per CLAUDE.md §3 Step 1 wording — minor only.)

### 🔵 Low 3 — orphan operator yaml fields not auto-cleaned

`scripts/lib/config.py` no longer parses `pending_alert_age_sec` / `monitor_enabled` / `monitor_report_*` (correctly), but existing operator `~/wikihub/wikihub.yaml` files will retain these fields as orphans. `_migrate_agent_schema` Group C auto-deletion only handles ADR-0035 fields (vault credentials_path etc), not these 4. ADR-0040 §"후속 영향" doesn't mention this. Acceptable as orphan-tolerant (yaml.safe_load ignores unknown keys), but could surface as operator confusion later.

**Fix (optional)**: Either add a Group C cleanup entry in `_migrate_agent_schema` for the 4 deleted fields, or add a note to ADR-0040 §"후속 영향" explicitly stating orphan tolerance.

## Verified Correct

- **D1 (Deletion count)**: `git status -s | grep '^D' | wc -l` = 7. Matches analysis_and_design.md DoD claim of "template 4 + script 2 + lib 1 = 총 7 파일 삭제". ✓
- **D3 (yaml + config)**: `wikihub.yaml.example:43-50` shows operations block with `fatal_webhook_*`, `instance_label`, `graphify_*`, `rclone_*`, `vfs_*` — no monitor fields. `scripts/lib/config.py:46-65` `OperationsConfig` dataclass and `:147-162` `_parse_operations` also clean. ✓
- **D4 (ops-alert.py inline)**: `scripts/ops-alert.py:185-228` contains `send_telegram` + `format_telegram_alert_message` with `parse_mode="HTML"` hardcoded (no option). Import block lines 31-36 references only `lib.config` + `lib.state` (no `lib.telegram`). ✓
- **D5 (commands docs)**: `_system/commands/setup.md:153, 167-179, 307` — wh-lint.timer + wh-ingest@gdrive references, no monitor. `lint.md:36, 172, 222, 279` — `wikihub_monitor 보고서 read` removed, D1 정정 정신 reference removed. `graphify.md:14, 19, 54` — D1 정정 reference removed, wh-lint.timer rename complete. ✓
- **D6 (ADR)**: ADR-0040 Status=Accepted + Supersedes=ADR-0037, ADR-0037 Status=Superseded + Superseded by=ADR-0040, ADR-0024:212 1-line addendum, README.md:94+97 index entries. All correct. ✓
- **D7 (Phase B absorption)**: `render_systemd_units.py:320-334` dead `pass` block removed (clean function signature). Legacy singleton cleanup expanded to include monitor units (lines 430-446). ✓
- **D8 partial (grep verify)**: After excluding ADR-0037/0040 + ADR-0032 historical + ADR-0031 historical + render_systemd_units.py cleanup catalog, the only live references to monitor strings are install.sh upgrade migration + install.sh env template comment + Critical 1 + Critical 2 + Critical 3 issues above.
- **systemd unit template inventory** (`ls _system/systemd/`): ops-alert.service + wh-ingest@.{service,timer}.template + wh-lint.{service,timer}.template + wikihub-graphify.service.template + wikihub-mount@.service.template = 7 files (matches `_system/wiki-schema.md:54-59` inventory). ✓
- **No stale lib.telegram imports**: `grep 'lib.telegram\|from lib.telegram'` across scripts/ = 0 hits. ✓
- **No stale wikihub_monitor.py / pending_monitor.py refs in live code**: `grep` across scripts/ install.sh _system/ = 0 hits in non-historical context. ✓
- **upgrade migration matches ADR-0040 §"후속 영향" L89**: install.sh:1630-1633 stop + disable both timers, both services. Pattern consistent. ✓
- **Karpathy §2 Simplicity adherence**: 7-file deletion, ~660 LOC removed (per ADR-0040 §Consequences L73), 4 yaml fields removed, 2 dataclass fields + 2 parse lines removed. No new abstractions introduced. ✓
- **Karpathy §3 Surgical Changes**: Phase A + Phase B touch same files (setup.md / lint.md / graphify.md) but the two purposes are explicitly separated in analysis_and_design.md §"작업 시퀀싱" L186 — methodology acknowledges and accepts. ✓
- **§Atomic Change violation acknowledged**: 3 scopes piled on feature/v018-fix (v0.1.9 bump + rename + monitor removal) — known and accepted per the review prompt. No additional issues from this stack-up in the current diff (test fixtures clean, no scope confusion in DoD).

## DoD Check (analysis_and_design.md §"Definition of Done")

- [x] **D1 — Deletion**: 7 files deleted (template 4 + script 2 + lib 1). `git status -s | grep '^D' | wc -l` = 7. ✓
- [x] **D2 — install.sh**: monitor refs = 4 (upgrade migration block) + 1 (env template comment) = intentional carry-over. ⚠️ DoD wording inaccurate (Medium 5).
- [x] **D3 — yaml + config**: 4 yaml.example fields removed (L43-48 of pre-edit), 4 OperationsConfig fields removed (L60-65 of pre-edit), 4 `_parse_operations` lines removed. ✓
- [x] **D4 — ops-alert.py inline**: `send_telegram` + `format_telegram_alert_message` inlined, `parse_mode="HTML"` hardcoded (line 196), `lib.telegram` import absent. ✓
- [x] **D5 — commands docs**: setup.md / lint.md / graphify.md cleaned of `wikihub_monitor` D1 정정 references + monitor enable list. ✓ (But README.md not covered — see Critical 2.)
- [x] **D6 — ADR**: ADR-0040 신설 (Accepted, Supersedes ADR-0037), ADR-0037 Status updated, ADR-0024 §Note 1-line add, README.md index 2-line update. ✓ (But §D2 missing from carry-over table — Medium 3.)
- [x] **D7 — Phase B 흡수**: `render_systemd_units.py:336-337` dead pass removed + legacy_singletons catalog expanded. ✓
- [ ] **D8 — Verify**: `render_systemd_units.py` dry-run not executed in this review (no test env), but legacy_singletons catalog visually verifies orphan cleanup intent. `pytest` not executed (no pytest in repo's mise python — recommend maintainer runs locally). grep verify performed manually — all monitor refs accounted for (3 Critical issues identified).
- [ ] **D9 — Code Review**: This is review #2 (Claude subagent). Review #1 + #2 needed per analysis_and_design.md D9. Status: pending second reviewer.

**Recommended additional DoD item**:
- [ ] **D10 — HISTORY.md append (Step 5 only)**: At squash time, append v0.1.9 release entry with `생성 ADR: ADR-0040` per CLAUDE.md §3 Step 5 format. (See Critical 3.)
