# Code Review 1 — feature-dev:code-reviewer (F3 Step 4)

- **Reviewer**: feature-dev:code-reviewer subagent (Claude, context-fresh)
- **Date**: 2026-05-13
- **Target**: F3 Step 3 implementation — scripts/* + tests/*

## Summary

The implementation is structurally sound and correctly follows the module decomposition from the design. All five ADR-0007 state files are implemented with proper atomic write semantics. The F2 JSON contract fields in `result_to_stdout_json()` are correctly emitted. The ADR-0014 isolation constraint (no `google-*` in runtime) is correctly enforced. However, two confirmed bugs will cause data corruption or silent failure in production: (1) binary file content is received as a Python `str` via `text=True` in `subprocess.run` and then `.encode("utf-8", errors="replace")` written to disk — this will silently corrupt any non-UTF-8 binary file (.pptx, .docx, .pdf); (2) the disabled-vault early-exit path uses `print()` with `%` string interpolation, which is vulnerable to vault_id values that contain a `%` character, though the vault_id regex makes this a latent rather than immediate risk. Additionally, there is one confirmed dead-code ternary in `sync.py` and one missing field in the `build_source_frontmatter` call when extraction fails. Total: 2 High, 3 Important, 2 Low.

## Findings

### High confidence — must fix before approval

#### H1. scripts/lib/gws.py:73–80 + scripts/lib/sync.py:269–277 — Binary content corrupted by `text=True` + re-encoding

**Confidence**: 95

**Evidence**:

`gws.py:73–80`:
```python
proc = subprocess.run(
    cmd,
    capture_output=True,
    text=True,          # ← decodes stdout as UTF-8 by default
    timeout=timeout_sec,
    ...
)
```

`sync.py:275–277`:
```python
saved.write_text(result.stdout, encoding="utf-8") if mime.startswith("text/") else saved.write_bytes(
    result.stdout.encode("utf-8", errors="replace")
)
```

**Impact**: `run_gws` always uses `text=True`, so Python decodes the raw subprocess stdout bytes as UTF-8 before returning them as `result.stdout: str`. For binary files downloaded via `gws drive files get --alt media` (.pptx, .docx, .xlsx, .pdf), the raw binary content will fail UTF-8 decoding or produce a mangled string. The downstream `extract_pptx/extract_docx/extract_pdf` will then fail on the corrupted file, producing `[extraction failed: runtime: ...]` in every wiki source page for binary vault files.

**Suggested fix**: In `gws.py`, change `run_gws` to accept a `binary_output: bool = False` parameter. When `binary_output=True`, use `text=False` and capture `stdout: bytes`. Add a `stdout_bytes: bytes` field to `GwsResult`. In `sync.py`, call `run_gws(..., binary_output=True)` for the `files.get` path and write `result.stdout_bytes` directly with `saved.write_bytes(result.stdout_bytes)`.

---

#### H2. scripts/vault-fetch.py:64–65 — `print()` + `%`-format for stdout JSON (disabled vault path)

**Confidence**: 85

**Evidence**:
```python
print('{"vault_id": "%s", "has_changes": false, "changed": [], "deleted": [], "duration_ms": 0}'
      % args.vault)
```

**Impact**: 
1. `print()` bypasses `sys.stdout.flush()` that the normal path uses. On buffered stdout (subprocess capture), the output may not flush before `return 0`.
2. `%` string interpolation inconsistent with the rest of the codebase (which uses `json.dumps`). If vault_id ever contained a quote, would produce invalid JSON.

**Suggested fix**: Replace with `sys.stdout.write(json.dumps({"vault_id": args.vault, "has_changes": False, "changed": [], "deleted": [], "duration_ms": 0}, ensure_ascii=False) + "\n"); sys.stdout.flush()`. Add `import json` to `vault-fetch.py`.

---

### Important — should fix

#### I1. scripts/lib/sync.py:393 — Dead-code ternary

**Confidence**: 100

**Evidence**:
```python
extraction_tool=er.tool if er.extraction_status == "success" else er.tool,
```

Both branches identical. Intended logic was almost certainly `... else None`.

**Suggested fix**: `extraction_tool=er.tool if er.extraction_status == "success" else None,`

---

#### I2. scripts/lib/sync.py:209–227 — `_compute_wiki_path` `.txt` 처리 명세 불명

**Confidence**: 90

For `.txt` file `notes/readme.txt`, code produces `wiki/sources/gdrive/notes/readme.txt.md`. Wiki-schema.md §A2 텍스트 카테고리 spec 모호 — `.md` 중복 회피 노트는 `.md`만 명시. `.txt`는 `<relpath>.<ext>.md` (binary 패턴)인지 stripped `.md`인지 불명.

**Suggested fix**: Author confirmation + test 추가로 intent 고정.

---

#### I3. scripts/lib/sync.py:422 — cursor 저장 순서가 last_sync 보다 먼저 (partial-failure window)

**Confidence**: 80

```python
save_file_map(...)
save_cursor(...)  # cursor written first
...
save_last_sync(...)  # last_sync written after cursor
```

크래시가 두 호출 사이에 발생하면 cursor는 advance됐는데 last_sync는 이전 사이클 데이터. cursor가 trasaction commit marker라면 last_sync 다음에 와야.

**Suggested fix**: `save_cursor`를 `save_last_sync` 뒤로 이동.

---

### Low confidence / nits — optional

#### L1. scripts/lib/frontmatter.py:29 — `_StringDumper` 주석 부정확

`_StringDumper.add_representer`는 해당 클래스 scope. 주석의 "global" 표현 misleading.

---

#### L2. scripts/lib/extraction.py:27–32 — `_safe_version` import path 매칭

`tool="pdfminer.six"`인데 lookup은 `_safe_version("pdfminer")` — name mismatch latent confusion. `importlib.metadata.version("pdfminer.six")`로 canonical 가능.

---

#### L3. tests/ — `test_sync.py` 부재

Design에 listed됐던 `test_sync.py`가 7개 test 파일 중 없음. `_compute_wiki_path` branch별 unit + `result_to_stdout_json` field 검증이 absent. 핵심 orchestration 모듈인데 회귀 방지망 없음.

---

## What I checked but found OK

- **F2 JSON contract field match**: `result_to_stdout_json()` 모든 8개 필드 emit (vault_id, has_changes, changed[*] with source_relpath·wiki_path·operation·source_id·source_mtime·bytes_written, deleted[], duration_ms). 타입 정확.
- **ADR-0007 atomic write**: `_atomic_write_json` 같은 디렉토리 tmpfile + `os.replace`. 실패 시 cleanup. 5개 state 파일 모두 동일 패턴.
- **Initial state shapes vs setup.md §Step 1**: cursor·file_map·retry 모두 spec과 일치.
- **ADR-0014 isolation**: requirements.txt에 google-* 없음. auth_gdrive.py만 deferred import.
- **Exception classes spec**: keyword-only vault_id 정확. 모든 raise 사이트 vault_id 전달.
- **stdout/stderr separation**: logging은 stderr, 메인 path는 sys.stdout.write + flush. (H2 단일 예외)
- **`_passes_trust_boundary`**: `shared and not ownedByMe` 로직 정확.
- **`_compute_wiki_path` Google native**: virtual ext (.gdoc/.gsheet/.gslides) 추가 로직 정확.
- **Frontmatter YAML date string**: `_StringDumper`가 string forced. round-trip test로 검증.

## Open questions for author

1. **`.txt` wiki path intent** (`sync.py:226`): `notes/readme.txt` → `wiki/sources/gdrive/notes/readme.txt.md` 의도? `.md`로 strip? spec 명료화 필요.

2. **Binary download V3 plan**: `text=True` + binary re-encode 패턴이 H1. v0.1.0이 "binary는 ASCII-safe 가정"인지, `gws --output <path>` 사용 의도인지 확정 필요.

3. **`test_sync.py` 부재**: design listed였는데 의도적 deferral인지, follow-up tracked인지.

4. **`saved_path` 미사용** (`sync.py:381`): `_download_to_vault` 반환값 중 `saved_path` 호출자 미사용. signature 간소화 가능.
