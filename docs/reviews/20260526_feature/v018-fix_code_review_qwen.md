# Code Review: v0.1.9 fix — text file passthrough for binary MIME

**Date**: 2026-05-26
**Reviewer**: Qwen (opencode)
**Branch**: vs origin/v0.1.9
**Scope**: Primary — `scripts/lib/sync.py` `_read_from_mount()` text passthrough fix; also all other commits in branch

---

## 1. Primary Fix: `scripts/lib/sync.py` — text passthrough for extension-matched files

### File: `scripts/lib/sync.py`

#### 1.1 `_text_extensions` defined inline inside the `else` block (line 226)

**Rating**: 🟡 Warning

**Location**: `scripts/lib/sync.py:226`

The tuple `_text_extensions` is defined inside the `else` branch (the non-text-mime, non-native path) on every invocation. This is a minor style/perf issue — the tuple is recreated each call. It should be a module-level constant, like `GWS_EXPORT_MIME` or `LOCAL_EXTRACTION_MIME` patterns already used elsewhere in this file.

**Suggestion**: Move to module level:
```python
_TEXT_EXTENSIONS = (".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".conf", ".log", ".xml", ".html")
```

---

#### 1.2 Extension check uses `source_relpath` not `saved` / `mount_relpath`

**Rating**: 🟢 Suggestion

**Location**: `scripts/lib/sync.py:227`

```python
if source_relpath.lower().endswith(_text_extensions):
```

`source_relpath` is the original path parameter. However, earlier in the function (lines 156-159), `mount_relpath` is derived from `source_relpath` with a native extension appended for Google native MIME types. Since this code path is in the `else` branch (i.e., `not is_text_mime` and `not is_native`), Google native MIMEs are already excluded, so `source_relpath == mount_relpath` here. The logic is correct, but using `mount_relpath` or `saved.name` would be more consistent with the local variable naming and would make the intent clearer to future readers.

---

#### 1.3 No size cap check before decoding

**Rating**: 🔴 Critical

**Location**: `scripts/lib/sync.py:216-229`

The size cap check at lines 218-225 runs **before** the extension check. However, the check uses `bytes_written` which is set from `data = saved.read_bytes()` at line 216. If the file passes the size check, the code then tries `data.decode("utf-8")` at line 229. This is fine — `data` is already fully read into memory.

**However**, there is a subtle issue: for very large files that pass the size check (e.g., a 50MB `.log` file when `max_file_size_mb=100`), the entire file is decoded into a single Python string. This is a memory concern but not a correctness bug — the size cap already bounds it. Marking as 🟢 since the cap provides protection.

---

#### 1.4 `UnicodeDecodeError` fallback to `extract(saved, mime)` is correct

**Rating**: 🟢 Suggestion (positive)

**Location**: `scripts/lib/sync.py:236-237`

When a file has a text extension but contains non-UTF-8 binary data (e.g., a `.txt` file that is actually a binary blob, or a file encoded in EUC-KR/CP949), the `UnicodeDecodeError` is caught and falls back to the binary `extract()` dispatch. This is the correct behavior — it handles the "binary file with text extension" edge case gracefully.

**Caveat**: `extract(saved, mime)` will likely return `failed` for most binary MIME types that don't have a handler in `LOCAL_EXTRACTION_DISPATCH` (e.g., `application/octet-stream`). This is acceptable — the file will be marked as extraction-failed rather than crashing.

---

#### 1.5 Only UTF-8 is attempted — no encoding detection

**Rating**: 🟡 Warning

**Location**: `scripts/lib/sync.py:229`

The code only attempts `data.decode("utf-8")`. Files with text extensions that are encoded in other formats (EUC-KR, CP949, ISO-8859-1, etc.) will hit `UnicodeDecodeError` and fall back to `extract()`, which will likely fail for non-supported binary MIMEs.

**Context**: This is consistent with the existing `is_text_mime` path at line 190 (`saved.read_text(encoding="utf-8")`), which also hardcodes UTF-8. So this is not a regression — it's consistent with existing behavior.

**Suggestion**: If the system needs to support Korean/legacy-encoded text files, consider adding `chardet` or `charset_normalizer` as a fallback. This is out of scope for this fix but worth noting as a future enhancement.

---

#### 1.6 `.endswith()` with tuple — correct but watch for false positives

**Rating**: 🟢 Suggestion

**Location**: `scripts/lib/sync.py:227`

`str.endswith(tuple)` checks the **suffix** of the entire string. This means:
- `"file.md"` → matches ✅
- `"file.MD"` → matches ✅ (`.lower()` applied)
- `"file.md.bak"` → does NOT match ✅ (correct — it's a `.bak` file)
- `"README"` → does NOT match ✅ (no extension)

This is correct behavior. No issue here.

---

#### 1.7 Missing test coverage for the new passthrough path

**Rating**: 🔴 Critical

**Location**: `tests/test_sync.py` — **no new tests added**

The diff shows **zero changes** to `tests/test_sync.py`. The new passthrough logic has three distinct paths:
1. Text extension match + valid UTF-8 → passthrough success
2. Text extension match + invalid UTF-8 → fallback to `extract()`
3. No text extension match → `extract()` as before

None of these are covered by existing tests. `_read_from_mount()` is an internal function tested indirectly through `sync.sync()`, but the existing tests only use `.md` files with `text/markdown` MIME, which takes the `is_text_mime` branch (line 189), **not** the new `else` branch.

**Recommendation**: Add at least one test that exercises the new branch:
- A `.csv` file with `text/csv` or `application/octet-stream` MIME → should passthrough
- A `.txt` file with binary content → should fall back to extract

---

#### 1.8 Empty file edge case

**Rating**: 🟢 Suggestion

If `data` is empty (`b""`), `data.decode("utf-8")` returns `""` successfully. The `ExtractionResult` will have `body_text=""` and `extraction_status="success"`. This is acceptable — an empty text file is valid.

Note that the `is_native` branch (line 204) has an explicit empty-file guard, but the `else` branch does not. This is fine because empty text files are semantically valid, whereas empty native exports indicate a problem.

---

## 2. Other Changes in Branch

### 2.1 `scripts/lib/config.py:153` — `lint_interval_hours` default 24 → 3

**Rating**: 🟢 Suggestion

**Location**: `scripts/lib/config.py:153`

Changes the default lint interval from 24 hours to 3 hours. This is an operational tuning change. The test fixture in `tests/test_config.py` is updated accordingly (lines 36, 48), so tests remain consistent.

**No issues** — straightforward config default change with matching test update.

---

### 2.2 `install.sh:1261` — Documentation typo fix (`wh-graphify·wh-query` → `wh-query·wh-setup`)

**Rating**: 🟢 Suggestion (positive)

**Location**: `install.sh:1261`

Removes `wh-graphify` from the list of Telegram skill defaults. This is a documentation correction to match the actual skill set. No functional impact.

---

### 2.3 Report and review documents added

**Rating**: 🟢 Informational

- `docs/reports/250525_wikihub_v018_update_report.md` (244 lines)
- `docs/reports/250526_wikihub_v018fix_report.md` (182 lines)
- `docs/reviews/250526_v018fix_code_review.md` (56 lines)
- `docs/reviews/250526_v018fix_code_review_kimi.md` (59 lines)

These are documentation/review artifacts. No code impact.

---

## 3. Summary of Findings

| # | File | Line | Rating | Description |
|---|------|------|--------|-------------|
| 1 | `scripts/lib/sync.py` | 226 | 🟡 Warning | `_text_extensions` tuple defined inline — should be module-level constant |
| 2 | `scripts/lib/sync.py` | 227 | 🟢 Suggestion | Use `mount_relpath` instead of `source_relpath` for consistency |
| 3 | `scripts/lib/sync.py` | 229 | 🟡 Warning | Only UTF-8 attempted; legacy-encoded text files will fail (consistent with existing behavior) |
| 4 | `tests/test_sync.py` | — | 🔴 Critical | **No test coverage** for the new passthrough branch (3 distinct paths untested) |

---

## 4. Verdict

### ❌ Request Changes

**Primary reason**: Missing test coverage for the new passthrough logic in `_read_from_mount()`. The fix introduces three new code paths (text-extension passthrough, UnicodeDecodeError fallback, and the existing extract path) — none are exercised by existing tests. The existing `test_sync.py` tests only cover the `is_text_mime` branch via `text/markdown` MIME, which bypasses the new code entirely.

**Required before merge**:
1. Add at least 2 tests to `tests/test_sync.py` that exercise:
   - A file with a text extension (e.g., `.csv`) and non-text MIME → passthrough success
   - A file with a text extension containing binary/non-UTF-8 data → fallback to extract

**Optional (can be deferred)**:
- Move `_text_extensions` to module-level constant
- Add encoding detection fallback for legacy text encodings (out of scope)

The core logic of the fix is **correct** — the extension-based heuristic with UTF-8 decode + UnicodeDecodeError fallback is a sound approach for the stated problem (binary MIME files with text extensions being incorrectly routed to binary extractors). The only blocker is test coverage.
