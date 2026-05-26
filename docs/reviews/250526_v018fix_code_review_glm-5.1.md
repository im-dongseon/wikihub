# Code Review: systemd rename wh-ingest@ / wh-lint — GLM 5.1

**Date:** 2026-05-26
**Branch:** feature/v018-fix
**Commit:** 2ed01f8
**Model:** opencode-go/glm-5.1

---

## Assessment: **Changes Requested**

## Issues Found

### 🔴 Critical 1 — `scripts/wikihub_monitor.py:478,481`
`collect_journal()` calls use `wikihub-vault@{vid}.service` and `wikihub-lint.service`. After upgrade, systemd unit names will be `wh-ingest@{vid}.service` and `wh-lint.service` — journal lookups will break.

### 🔴 Critical 2 — `scripts/pending_monitor.py:73`
Remediation message references `journalctl --user -u wikihub-vault@%s.service`. Must be updated to `wh-ingest@%s.service`.

### 🟡 Medium — `_system/commands/setup.md`
Lines 153, 170-171, 177 reference old unit names (`lint.timer`, `lint.service`, `gdrive-ingest.timer`). These are operator-facing docs in `_system/` and should reflect new names.

### 👍 Correct Items
- All 4 template renames + internal references correct
- install.sh upgrade migration logic well-structured (legacy stop → new start)
- render_systemd_units.py `_output_filename`, stale cleanup regex, verify globs correct
- README.md, graphify template comment updated
- Remaining old-name references in install.sh/renderer are intentional (upgrade cleanup)
