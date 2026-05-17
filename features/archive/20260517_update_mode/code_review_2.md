# Code Review #2 — update_mode (SRE operational safety)

- **Reviewer**: Claude Opus 4.7 (subagent, SRE angle)
- **Date**: 2026-05-17
- **Branch**: feature/update_mode (HEAD ac80f38)

## Summary

The implementation matches `analysis_and_design.md` v3 spec at the structural level — flock, mode detect, rollback trap, stop/start sequences, render_systemd_units.py contract — all present. However, **one CRIT-class trap-clobber bug** (`_step4_gws` overwrites the rollback EXIT trap), one **HIGH-class fresh-install ref-resolution gap** (tag `latest` never reachable on first install), one **HIGH stale-tag silent restore** path, and several MED/LOW operational footguns surface. The rollback machinery itself (state-machine on `PRE_UPDATE_REF == HEAD`) is well thought out; the issues are at the boundaries between rollback scope and reusable helper functions whose trap-management collides.

## Findings

### CRIT-1: `_step4_gws` overwrites the rollback EXIT trap mid-update
**File/Line**: `install.sh:440`, `:467` (interaction with `:877`)
**Issue**: In `_step2_update` the rollback trap is registered as `trap '_rollback_if_failed' ERR EXIT INT` (line 877). Subsequently `_step4_gws` (called from `main` at line 1186) installs gws via the path that requires download — and at line 440 unconditionally does `trap 'rm -rf "$tmpdir"' EXIT`, **clobbering the EXIT half of the rollback trap**. At line 467 it then does `trap - EXIT` — clearing EXIT to nothing — but the rollback handler is *not restored*.

After Step 4 completes successfully in update mode, ERR/INT remain bound to `_rollback_if_failed`, but EXIT does not. Two consequences:
1. Bare `exit N` invocations after Step 4 (e.g. an explicit `exit` from a deeper helper that doesn't trigger ERR because the parent uses `if ! cmd`, `cmd || …`, etc.) will not fire rollback.
2. Receipt of SIGTERM (not handled here at all — only INT is trapped) → bash exits → no EXIT trap → no rollback. Even SIGHUP path is broken the same way.

**Evidence**: Compare line 561 (`_install_rclone`) and line 328 (`_install_uv`) — both use `trap … RETURN` (function-local) and `trap - RETURN`, which is correct. Only `_step4_gws` uses EXIT.

**Suggested fix**: Convert line 440 to `trap 'rm -rf "$tmpdir"' RETURN` and line 467 to `trap - RETURN` to match the sibling helpers. RETURN is function-scoped and cannot collide with the rollback trap.

---

### HIGH-1: `_resolve_ref` cannot reach tag `latest` on fresh install — operator gets `origin/main` instead
**File/Line**: `install.sh:819-861` (with `:296` fresh-path entry)
**Issue**: `_step2_clone` is invoked after `rm -rf "$WIKIHUB_HOME"`. It then calls `_resolve_ref` (line 296). But `_resolve_ref` paths 3 and 4 use `git -C "$WIKIHUB_HOME" rev-parse refs/tags/latest` and `git -C "$WIKIHUB_HOME" for-each-ref …` — `$WIKIHUB_HOME` does not exist (just wiped, or never created). Both commands fail silently (errors masked by `>/dev/null 2>&1` or `|| true`). Path 5 fallback to `origin/main` HEAD is therefore the unconditional fresh-install outcome whenever `--version`/`--branch` is absent.

This contradicts the design intent that the default fresh install pins to the `latest` tag (ADR-0010 §Decision). Operators running `curl … | bash` on a brand-new VM silently get the bleeding edge of `main` instead of the pinned release tag.

**Evidence**: `_resolve_ref` has no `ls-remote` path — there is no way to know what `latest` resolves to remotely before cloning. The warn message on path 5 says "no 'latest' tag" but the real reason is "no local repo to inspect tags from yet."

**Suggested fix**: Either (a) `_step2_clone` does a `git ls-remote --tags "$WIKIHUB_REPO_URL" latest` probe before falling back to main, or (b) accept that fresh + no `--version` always uses `origin/main` and document it loudly in `_step8_guide` + ADR-0030. The current banner ("[no 'latest' tag — using origin/main HEAD]") is misleading and silently wrong for the standard install path.

---

### HIGH-2: Stale `latest` tag silently restored when `git fetch` fails
**File/Line**: `install.sh:914-916` → `:846-849`
**Issue**: Update path does:
```bash
if ! git -C "$WIKIHUB_HOME" fetch origin --tags 2>&1; then
    warn "git fetch 실패 — local cache fallback 시도"
fi
target_ref="$(_resolve_ref)"
```
Then `_resolve_ref` path 3 — *not* path 4 — succeeds because `refs/tags/latest` exists locally from a prior fetch. `git reset --hard refs/tags/latest` resets to a possibly-month-old stale `latest` (a force-pushed mutable ref). No warn is issued because the network-offline warn is in path 4, which is never reached. Operator sees "update transition: v0.1.2 → v0.1.2" and assumes idempotent no-op, when in reality they have unknown drift behind a stale `latest`.

Also: `2>&1` on the `fetch` line dumps stderr into stdout (and via tee, into the log) — this is non-fatal but defeats grep-by-severity in postmortem.

**Suggested fix**: When fetch fails, set a flag and either (a) skip path 3 entirely (treat local `latest` as untrusted after fetch failure), or (b) issue an explicit warn citing the stale-tag risk before proceeding. Drop the `2>&1` so stderr remains stderr.

---

### HIGH-3: SIGTERM (and SIGHUP) bypass rollback entirely
**File/Line**: `install.sh:877`
**Issue**: `trap '_rollback_if_failed' ERR EXIT INT` — only INT is trapped. SIGTERM (sent by systemd shutdown, OOM killer, `kill <pid>`) and SIGHUP (ssh disconnect without linger, terminal close) both terminate bash without firing the rollback. With curl-pipe running over flaky ssh, an SSH disconnect mid-update will leave the system in a partial state and skip rollback.

Combined with the install lock being held on `$WIKIHUB_INSTANCE_ROOT/install.lock` and released only on fd close, this also strands the lock — but the lock is correctly released by kernel on process death (HIGH-3 not affecting CRIT-1 of lock safety). The rollback itself, though, never runs.

**Evidence**: Spec design doc §3 Step 2 only lists `ERR EXIT INT` as well — so this is design + impl aligned, but operationally insufficient.

**Suggested fix**: Add `TERM HUP` to the trap signal list: `trap '_rollback_if_failed' ERR EXIT INT TERM HUP`. Verify behavior under ssh disconnect (V-script extension).

---

### HIGH-4: `_step10_verify` returns 2 → set -e fires ERR trap → rollback runs even though git tree is target ref
**File/Line**: `install.sh:1133-1140`, interaction with `_rollback_if_failed:978-986`
**Issue**: `_step10_verify` returns 2 if any enabled vault's mount@ isn't active (line 1138). The caller (main, line 1198) lets it propagate; `set -e` triggers ERR. Rollback fires with `current_ref != PRE_UPDATE_REF` branch → forces `git reset --hard $PRE_UPDATE_REF`, re-renders, restarts.

But the verify failure may be a transient state (mount@ slow to come up beyond 120s, or vault failing on first sync but recoverable). The rollback re-renders units back to old version and restarts old vault@ → operator now has the *old* binary on a vault that may already have begun writing state with the new schema. **This violates invariant #1 (re-call = consistent sync, not destructive)** when the new vault@ has already touched user state.

**Evidence**: `_step10_verify` checks `is-active` only — does not verify the *failure* is fatal (could just be slow). Yet failure triggers a full git rollback.

**Suggested fix**: Either (a) `_step10_verify` retries with longer timeout / fewer error semantics (treat as warn, exit 0), or (b) verify failure does not rollback git — only logs an alert. Current behavior is "any verify hiccup → silent downgrade with state divergence risk."

---

### HIGH-5: `_systemd_stop_before_update` misses inactive-but-loaded vaults — incomplete stop sequence
**File/Line**: `install.sh:1015-1016`
**Issue**: `systemctl --user list-units --no-legend 'wikihub-mount@*.service'` without `--all` only lists *currently active* units. If a vault's mount@ has hit StartLimitBurst and is in `failed` state, OR if mount is `loaded inactive` (not started yet because timer hasn't fired), this listing returns empty for it. Consequence: the corresponding `wikihub-vault@<vid>.timer` is **not stopped**, and may fire during the update window before `_systemd_stop_before_update` finishes (race with the `_step8_systemd_render` write).

This is a real F1 invariant breach (#2 in design's invariant list: "vault@ timer fire and update race blocked").

**Evidence**: List of `running_vaults` drives every loop in the stop sequence. A vault enabled in yaml but with mount@ currently inactive is invisible.

**Suggested fix**: Either drive the stop loops from `_enabled_vaults_yaml` (desired state from yaml, the canonical answer), or use `list-units --all --state=loaded` to capture all loaded units. The current approach mixes "what is active now" with "what should be controlled" — these diverge.

---

### MED-1: rollback handler does not re-acquire the install lock; concurrent operator action during rollback can race
**File/Line**: `install.sh:951-987`
**Issue**: When the rollback handler runs after a long stop (e.g., 15min grace × N vaults + git reset), an operator on the same host could have manually invoked `systemctl --user start wikihub-vault@x.service` after seeing the timer stopped. The rollback's `_systemd_start_after_update` will then race with the operator's invocation, possibly attempting `start` on an already-starting service.

The flock is held throughout `_step2_update` and rollback (rollback runs in the same shell), so concurrent *install.sh* is blocked. But this protects only against concurrent install.sh, not concurrent operator systemctl actions. Lower likelihood, real-world possible.

**Evidence**: Lock is fd-200-based; rollback runs inside the original shell so lock is still held — correct. The race is operator vs script, not script vs script.

**Suggested fix**: Out-of-scope for v0.1.0; document in ADR-0030 Notes as "operator should not interleave systemctl actions during install.sh window."

---

### MED-2: `render_systemd_units.py` leaves `.tmp` files on Python crash; install.sh does not clean them
**File/Line**: `scripts/_helpers/render_systemd_units.py:237-247`; install.sh `_step8_systemd_render:1087-1102`
**Issue**: `_atomic_write_if_changed` writes to `<output>.tmp` then `os.replace`. On Python SIGKILL/OOM between `write_text` and `os.replace`, the `.tmp` lingers. The stale-cleanup pass (line 358) globs `wikihub-*@*` and matches the regex `^wikihub-(?:mount|vault)@([^.]+)\.(service|timer)$` — which **does not match `.tmp` files**. They accumulate indefinitely in `~/.config/systemd/user/`.

**Evidence**: regex anchors `\.(service|timer)$` — `.service.tmp` fails the `$`.

**Suggested fix**: At the start of `_do_render`, glob `out_dir.glob("*.tmp")` and remove. Or relax the cleanup regex to match `.service.tmp` / `.timer.tmp` suffixes too.

---

### MED-3: `expanduser` on `credentials_path` does not expand `$HOME`/env vars
**File/Line**: `scripts/_helpers/render_systemd_units.py:188`
**Issue**: If operator writes `credentials_path: $HOME/.credentials/sa.json` in wikihub.yaml (a natural mistake given the env-style conventions elsewhere), `os.path.expanduser` does NOT expand `$HOME`. The literal `$HOME/...` is then written into the systemd unit's `Environment=GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=$HOME/...`. systemd does not expand environment variables on the RHS of `Environment=` directives → vault-fetch.py receives the literal path → file-not-found at runtime → fatal exit.

**Evidence**: only `~` and `~user` are handled by `expanduser`. `os.path.expandvars` is not called.

**Suggested fix**: Use `os.path.expandvars(os.path.expanduser(...))`, or validate at schema-check time that path is absolute and contains no `$`.

---

### MED-4: `git fetch` failure stderr swallowed in update path; "[network offline]" warn is unreachable
**File/Line**: `install.sh:914`
**Issue**: `if ! git -C "$WIKIHUB_HOME" fetch origin --tags 2>&1; then` — `2>&1` redirects stderr to stdout. Combined with the tee at line 103, you do still see the message in the log, but it's mixed with progress output and grep-by-severity (e.g., `grep ERROR install.log`) won't find git's error. Worse, since path 3 (`latest` tag) succeeds locally after fetch failure (HIGH-2), the "[network offline — using local semver max tag]" warn never fires — operator has no signal that something is wrong.

**Evidence**: Lines 854 and 859 are the only place network-offline status is communicated. They're in path 4 and 5 only, which are skipped after a successful local `refs/tags/latest` lookup.

**Suggested fix**: Drop `2>&1`. Capture fetch failure into a flag and emit the warn at `_resolve_ref` start when the flag is set, regardless of which path succeeds.

---

### MED-5: `_step4_gws` non-Ubuntu path missing `timeout` and GNU-only commands
**File/Line**: `install.sh:1026`, `:341`, `:461`, `:97`
**Issue**: With `ALLOW_NON_UBUNTU=1` on macOS dev box, the following will fail or behave wrong:
- Line 1026: `timeout 900 systemctl …` — BSD lacks `timeout` (only `gtimeout` via coreutils brew). On macOS without coreutils, this returns "command not found" → `|| warn ...` absorbs, but no actual grace timeout is applied.
- Line 341: `find … -executable -printf` — BSD `find` has neither flag → returns error → `uv_bin` empty → exits 2.
- Line 461: `find … -printf` — same issue, falls through to ls fallback (defensive code present).
- Line 97: `xargs -r` — BSD `xargs` lacks `-r`. Empty input invokes `rm -f` (no args) → no error but minor wart.

ALLOW_NON_UBUNTU is gated as "intentional non-Ubuntu" so the macOS user opts in, but several of these (find -executable) hard-fail on the install path. Comment-level note in `_step1_env_check` warns of risk but the specific incompatibilities aren't enumerated.

**Suggested fix**: Either (a) constrain `ALLOW_NON_UBUNTU` to truly Linux-on-non-Ubuntu (gate on `uname -s == Linux`), or (b) replace `find -executable -printf` with `find -type f -name uv` + `[ -x ... ]` test (POSIX), and document `timeout` requirement.

---

### MED-6: `agent_binary` from operator yaml executed as absolute path with `-x` check only — minor injection surface
**File/Line**: `install.sh:1109-1118`
**Issue**: `agent_binary` is read from `wikihub.yaml.agent.binary` via Python yaml safe_load. The check is `[[ -z "$agent_binary" || ! -x "$agent_binary" ]]` — i.e., the script will execute any executable file the operator names. If the wikihub.yaml is operator-edited (intended), this is "trust the operator" model and acceptable. But if a future feature ever allows wikihub.yaml to be partially derived from less-trusted sources (e.g., a setup helper that merges sample config from a downloaded URL), this becomes an arbitrary-code-execution sink.

Also `WIKIHUB_NONINTERACTIVE=1 timeout 300 "$agent_binary" -z "/wh:setup"` — the `-z` flag is hard-coded as a Hermes idiom; if `agent_binary` is not actually Hermes-compatible (operator typo), it gets executed with `-z` as argv which most binaries reject. Failure absorbed by `|| warn`. Not a security issue but a UX one.

**Suggested fix**: Out-of-scope for v0.1.0; document that wikihub.yaml is a trusted file (chmod 600 it like .credentials). Long-term, allowlist known `agent.binary` values.

---

### MED-7: Dead variable `venv_was_recreated` in `_step3_venv`
**File/Line**: `install.sh:371`, `:382`
**Issue**: Commit ac80f38 removed the pip-skip optimization that consumed `venv_was_recreated`. The variable is still assigned but never read. Cosmetic dead code; harmless but signals incomplete refactor.

**Suggested fix**: Remove the variable.

---

### MED-8: Persistent timer + immediate fire after restart can flood
**File/Line**: `_system/systemd/wikihub-vault@.timer.template:13` (Persistent=true) interacting with `_systemd_start_after_update`
**Issue**: With `Persistent=true` + `OnUnitInactiveSec={sync_interval_sec}s`, after the stop sequence keeps vault@ inactive for the duration of the update (could be 5+ minutes including 15min grace), on `start wikihub-vault@<v>.timer` the timer immediately fires because the inactive interval has elapsed. For N vaults this means N simultaneous vault-fetch invocations right after update — exactly when system state is most fragile.

V14 (idempotency) reportedly passed, so this isn't catastrophic, but worth noting: the burst could overlap with `_step10_verify` window, with `is-active` showing transient `activating` state and verify timing out.

**Evidence**: spec design §3 Step 2c-d notes 15min grace for in-flight stop, but doesn't address the catch-up burst on start.

**Suggested fix**: Either accept (V1 passed) or add a `RandomizedDelaySec={sync_interval_sec/4}s` to the timer template to spread the catch-up fire.

---

### LOW-1: Log rotation `mv "$log" "${log}.YYYYMMDD_HHMMSS_$$"` race in `ls -1t | tail -n +8`
**File/Line**: `install.sh:96-97`
**Issue**: `mv` with PID suffix avoids same-second collision between two install.sh PIDs. But the prune step `ls -1t "${log}".*_* 2>/dev/null | tail -n +8 | xargs -r rm -f` uses mtime ordering. If two PIDs rotate within the same second, both files get the same mtime; `ls -1t` arbitrary-orders them. Cap of 7 retained is still respected, but *which* of the two same-second files is kept is non-deterministic. Edge case; unlikely operationally.

**Suggested fix**: None needed — keep cap, accept arbitrary tie-break.

---

### LOW-2: `--branch` flag accepts hostile values via operator
**File/Line**: `install.sh:114`, `:296`, `:305`
**Issue**: `--branch "$2"; shift 2` — if operator types `--branch '--upload-pack=evil'`, the value flows into `git clone --branch "$clone_ref"`. After strip rules at line 302-303, neither `origin/` nor `refs/tags/` prefix applies, so `clone_ref="--upload-pack=evil"`. Git's `clone --branch --upload-pack=...` would interpret `--upload-pack` as a separate option only if it's positional — `--branch=VALUE` form prevents this. The current code uses `--branch "$clone_ref"` (space-separated), which IS susceptible: bash passes argv `[--branch, --upload-pack=evil, repo, target]`. Git's `clone` argparse sees `--branch` needs an arg, takes `--upload-pack=evil` as its arg, treats it as a ref name → "fatal: Remote branch --upload-pack=evil not found." So Git refuses, no execution. **Confirmed safe** in current Git, but fragile.

**Suggested fix**: Validate `--branch`/`--version` values reject leading `-`: `case "$2" in -*) err "ref cannot start with -"; exit 1 ;; esac`.

---

### LOW-3: `_step10_verify` checks mount@ only, not vault@.timer
**File/Line**: `install.sh:1130-1141`
**Issue**: Verify only checks mount@ services. vault@.timer activation (line 1061) failure is `|| warn` (line 1062), and timer absence is not checked. Operator could pass verify but have no timers running → silent no-sync.

**Suggested fix**: Add `systemctl --user is-active "wikihub-vault@${v}.timer"` to verify loop.

---

### LOW-4: PyYAML duplicate-key silent acceptance
**File/Line**: `scripts/_helpers/render_systemd_units.py:75`
**Issue**: `yaml.safe_load` uses last value for duplicate keys without warning. Operator yaml with two `vaults:` blocks (paste error) silently drops the first. Schema validator checks duplicate vault *ids* within a list but not duplicate top-level keys.

**Suggested fix**: Use a custom yaml loader that raises on duplicate keys; or document the caveat.

---

### LOW-5: `_install_uv` does not have `--quiet` either — verbose pip install on every call
**File/Line**: `install.sh:366`, `:392`
**Issue**: Per ac80f38 commit, `--quiet` was removed from pip install. Every invocation prints full uv install + pip install output. Acceptable but bloats install.log over time (rotation at 10MB triggers more often). Cosmetic.

**Suggested fix**: None — explicit choice per commit message.

---

### LOW-6: `_verify_version_tag_integrity` runs `git describe --tags --exact-match` which fails noisily off-tag
**File/Line**: `install.sh:808`
**Issue**: `git describe --tags --exact-match HEAD` exits non-zero when HEAD isn't exactly on a tag (e.g., 1 commit ahead of v0.1.0). Wrapped in `2>/dev/null || true` so silent. OK. Just noting `tag_exact` becomes empty in that case → the `if [[ -n "$version_str" && -n "$tag_exact" ]]` correctly skips warn. No issue.

---

## Verdict

**Fix CRIT-1 and HIGH-1, HIGH-3 before lock. HIGH-2, HIGH-4, HIGH-5 strongly recommended before lock. MED/LOW acceptable as backlog.**

- **CRIT-1** is a latent footgun for exactly the kind of partial-failure scenario rollback exists to handle — a trivial one-line fix.
- **HIGH-1** breaks the documented "default fresh = pinned latest" mental model. Either fix or update docs.
- **HIGH-3** (TERM/HUP) is a real operational gap — ssh-disconnect mid-update is plausible.
- **HIGH-2** + **HIGH-4** + **HIGH-5** are correctness bugs but require deeper design discussion; fix or document as known.

VM tests V1·V2·V13·V14 passed but **none of these tests would have surfaced CRIT-1** (gws was pre-installed in those test VMs) or HIGH-1 (V8 not run = `latest` tag fallback chain not exercised) or HIGH-3 (no SIGTERM/HUP test). V3·V11·V12·V15 unexecuted have non-trivial risk especially V11 (forced pip fail → rollback) which would hit CRIT-1 directly.

## Notes

- The state-machine in `_rollback_if_failed` (PRE_UPDATE_REF vs current HEAD) is genuinely well-designed — kudos for the 3-branch structure (SIGINT / pre-reset / post-reset).
- The render_systemd_units.py contract (§6.1) is clean; the substitution conflict detection (overlap of instance vs cross-vault keys) is good defense.
- `_acquire_install_lock` semantics are correct (fd 200 OFD, explicit close before exec, kernel auto-release on kill -9).
- Recommend a V15-extended VM test scenario: SSH disconnect (close terminal without disown) at three points: (a) during 15min grace stop, (b) during `git reset --hard`, (c) during `_step8_systemd_render`. This will surface HIGH-3 immediately.
- Recommend V11 be run before lock — it's the direct CRIT-1 trigger if Step 11 is moved before Step 4 (or if pip install fails after Step 4 succeeds).
- The 4 fix commits in the recent history (gitignore, refspec, origin/ prefix, pip skip) all surfaced in single-vault clean-tree VM runs. Real-world scenarios (dirty tree mid-update, stale credentials, mount in failed state during update entry) likely yield more.
