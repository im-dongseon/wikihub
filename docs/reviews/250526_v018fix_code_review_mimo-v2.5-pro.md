# Code Review: systemd rename wh-ingest@ / wh-lint — Mimo 2.5 Pro

**Date:** 2026-05-26
**Branch:** feature/v018-fix
**Commit:** 2ed01f8
**Model:** opencode-go/mimo-v2.5-pro

---

## Assessment: **Changes Requested**

## Issues Found

### 🔴 C1 — `scripts/wikihub_monitor.py:478,481` (HIGH)
`collect_journal()` uses `journalctl -u` with old unit names. After rename, units are `wh-ingest@{vid}.service` / `wh-lint.service`. Monitor produces empty reports. **Runtime breakage.**

### 🟡 C2 — `scripts/pending_monitor.py:73` (MED)
Remediation message: `journalctl -u wikihub-vault@%s.service` → should be `wh-ingest@%s.service`.

### 🟡 C3 — `_system/commands/setup.md:153,170,171,177,305` (MED)
`lint.timer`, `lint.service`, `gdrive-ingest.timer` references — should be `wh-lint.*`.

### 🟡 C4 — `_system/commands/lint.md:36,238,279` (MED)
`lint.service`, `lint.timer` references — should be `wh-lint.*`.

### 🔵 C5 — `_system/commands/graphify.md:20` (LOW)
`lint.timer (3h 주기)` → should be `wh-lint.timer`.

### 🔵 C6 — `render_systemd_units.py:336-337` (LOW)
Dead `pass` branch after lint special-case removal.

## Verified Correct
- Template renames + internal SyslogIdentifier/Unit= correct
- install.sh upgrade migration sequence safe (old stop → disable → render → new start)
- render_systemd_units.py stale cleanup regex covers all patterns
- Legacy lint cleanup (`wikihub-lint.*`) correct
- Banner list-timers pattern `*wh-*` correct
- `_systemd_analyze_verify` glob catches `wh-*.service/.timer`
