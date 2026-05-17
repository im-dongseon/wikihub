# F3 코드 리뷰 R4 (SRE 독립 검토)

- **Reviewer**: general-purpose SRE (R4) — claude-opus-4-7, fresh context
- **Date**: 2026-05-14
- **Target**: `feature/vault_gdrive_api` HEAD + working tree (5 modified + 1 new)
- **독립성 선언**: `code_review_1.md` / `code_review_2.md` 의 결론을 답습하지 않고 working tree 를 직접 읽어 SRE 운영 관점(24/7 daemon, OCI ARM, retry/idempotency, observability, 보안 경계)으로 재검토. 선행 리뷰가 식별한 28개 항목은 *결과적 회귀* 만 확인하고, 본 리뷰는 **수정 도중 새로 생긴 결함** 과 **선행 리뷰 미발견 SRE 결함** 에 집중한다.

## 요약

수정 라운드가 R1·R2 의 큰 줄기(binary mode, atomic write, traversal, file_map 즉시 commit, cursor 순서, root_folder_id post-filter)는 진지하게 해결했다. **그러나 fix-induced regression 4건**이 있고, 그중 2건은 OCI 서버 첫 사이클부터 실데이터 손상 또는 vault 영구 stuck 을 일으킨다. 추가로 선행 리뷰가 짚지 못한 **timeout silent-skip / fsync 누락 / per-file fatal stuck / 동시 invocation lock 부재** 등 SRE 단골 결함이 잔존한다. 다음 4건은 **배포 차단**.

---

## 1. 차단 이슈 (CRIT — 배포 차단)

### CRIT-R4-1 [Security / Reliability] `_download_to_vault` 가 raw `file_meta["name"]` 으로 path 합성 — CRIT-3 fix 우회 (`scripts/lib/sync.py:303-319`)

**무엇이**: 호출자 sync 루프(`sync.py:521`)는 `_sanitize_relpath` 로 traversal 차단 후 `source_relpath` 만 사용한다. 그러나 `_download_to_vault` 내부(`sync.py:304`)는 다시 `name = file_meta.get("name", fid)` 로 **sanitized 되지 않은 raw** name 을 꺼내 `saved = vault_local_path / name` (`sync.py:319`) 으로 합성한다.

**왜 위험한가**: `_sanitize_relpath` 는 `raw.lstrip("/").strip()` 후 검증한다. 즉 Drive 가 `name="/foo/bar"` 를 반환하면 caller 는 `source_relpath="foo/bar"` 로 받아들여 통과시키지만, callee 는 그대로 `"/foo/bar"` 를 사용한다. POSIX semantics 상 `vault_local_path / "/foo/bar"` = `PosixPath("/foo/bar")` — **vault 경계 밖 절대 경로로 write**. (재현 검증 완료, 본 리뷰 검토 중 `python3` 실행)

```python
>>> Path("/opt/vault-gdrive") / "/abs/escape"
PosixPath('/abs/escape')
```

**Drive 가 그런 name 을 줄 수 있나**: Drive API 는 `name` 에 임의 문자열 허용. UI 가 차단해도 API 직접 호출(다른 클라이언트, 또는 악의적 sharing)로 `/`-시작 name 진입 가능. 또한 *현재* sanitize 가 leading slash 를 `lstrip` 만 하고 backslash·NUL·`..` 는 None 반환하는 비대칭 — leading slash 인 입력은 *통과되지만* vault 측에서는 절대경로화된다.

**왜 선행 리뷰가 놓쳤나**: R1·R2 의 CRIT-3 권고는 "_source_relpath sanitize" 와 "wiki_path resolve 검증" 까지였고, vault local path 의 callee 측 재합성은 시야 밖. 본 라운드 fix 는 caller 만 손봤다.

**어떻게 고칠까**:

1. `_download_to_vault` signature 에 `source_relpath: str` 추가하고 callee 안에서 raw `name` 사용 금지. 호출자(line 534)는 이미 sanitized 값을 들고 있으므로 그대로 전달.
2. Defense-in-depth: 함수 진입 시 `Path(source_relpath).is_absolute()` 면 `VaultSyncFatal` raise — invariant 위반은 fail-loud.
3. `saved.resolve().relative_to(vault_local_path.resolve())` 로 escape 차단 (sanitize 이중 방어).

**또 한 군데**: `_handle_removed` 의 `vault_local_path / entry` (`sync.py:411`) 는 `entry` 가 file_map key (이전 사이클의 sanitized 결과)이므로 우연히 안전하지만, 동일한 defensive resolve 검증을 두는 게 좋다.

---

### CRIT-R4-2 [Reliability] `subprocess.TimeoutExpired` 가 per-file silent skip → 다음 사이클에 동일 파일을 영원히 안 받음 (`scripts/lib/sync.py:99-116` + `scripts/lib/gws.py:71` docstring 거짓)

**무엇이**: `gws.py:70` docstring 은 "TimeoutExpired 는 호출자가 catch → VaultSyncRetryable 매핑" 이라고 명시한다. 그러나 실제 `sync.py:_run` 의 try/except 는 `GwsBinaryMissing` 만 잡는다(`sync.py:101`). `subprocess.TimeoutExpired` 는 어디서도 wikihub 예외로 변환되지 않는다.

**경로 1 — per-file 호출 (drive files get/export)**: `_download_to_vault` 안에서 timeout 발생 → 호출 chain 으로 raise → sync 루프의 `except Exception as e: noqa: BLE001` (`sync.py:594`) 가 catch → `log.exception` + skip. **retry queue 에 enqueue 되지 않음**. cursor 는 정상 진행되어 새 token 으로 advance.

**결과**: timeout 한 번 발생한 파일은 다음 사이클에 changes.list 에 *다시 나타나지 않는다* (Drive 의 modify 없으면). 즉 **영구 미반영 + 운영자 가시화 없음** — `error_count` 만 +1 되고 stdout JSON 에는 안 들어감 (R4 보강 필요 별건이지만 핵심은 retry queue 누락).

**경로 2 — vault-level 호출 (`_changes_list_iter`, `_files_list_iter`, `_bootstrap_token`)**: timeout 이 sync 루프 진입 전 발생 → `vault-fetch.py:109` 의 generic `except Exception` → exit 2 (Fatal). **systemd 의 `Restart=on-failure` 가 75 (Retryable) 만 trigger 한다면 timeout 으로 OCI ↔ Google 일시 네트워크 끊김 시 vault 가 stuck**. 사용자의 ADR-0014 의도(timeout=transient=retryable) 와 정면 모순.

**왜 선행 리뷰가 놓쳤나**: 둘 다 binary_output / sanitize 의 정적 결함에 집중. timeout propagation chain 추적은 안 함. R2 는 OBS-3 에서 "retry queue 가 dead code" 만 지적했지 timeout 매핑 부재는 안 짚음.

**어떻게 고칠까**:

```python
def _run(...) -> GwsResult:
    try:
        result = run_gws(...)
    except GwsBinaryMissing as e:
        raise VaultSyncFatal(...) from e
    except subprocess.TimeoutExpired as e:
        raise VaultSyncRetryable(
            vault_id=vault_id, retry_after_sec=60,
            reason=f"gws timeout after {e.timeout}s: args={args[:3]}"
        ) from e
    if result.returncode != 0:
        ...
```

추가: `subprocess.run` 에 `start_new_session=True` 또는 `process_group=0` (Python 3.11+) 권장 — timeout 발생 시 gws 가 띄운 자식 process 까지 함께 reap 되도록. 현재는 zombie 가능.

---

### CRIT-R4-3 [Reliability] per-file `VaultSyncFatal` (예: 한 파일의 403 insufficientPermissions) 이 vault 전체 cycle 을 영구 stuck (`scripts/lib/sync.py:591-593` + `scripts/lib/errors.py:33-39`)

**무엇이**: `errors.py:GWS_API_ERROR_PATTERNS` 는 `403 ... (insufficientPermissions|forbidden)` 를 `fatal` 로 분류한다. 사용자 Drive 안에 ACL 제한이 있는 한 파일(또는 sharedDrive 의 위임된 회원 파일)이 changes.list 에 나타나면 → `_run` 이 `VaultSyncFatal` raise → sync 루프의 `except VaultSyncFatal: raise` (`sync.py:592`) 가 그대로 propagate → `save_cursor` 가 호출되지 않음 → **다음 사이클도 동일 changes 받고 동일 파일에서 또 fatal → 영구 stuck**.

운영 시나리오:
- 신입 동료가 vault 내 폴더에 `restricted=True` 파일 1개 업로드. Drive UI 는 owner 에게는 보이는데 OAuth scope 가 ACL 거부 → 403.
- gws 가 `drive files get` 호출 시 403 → wikihub 가 fatal 로 분류 → vault 전체 stuck.
- 운영자 개입 없이는 풀리지 않음. Hermes 가 fatal 알림은 받지만 *어떤 파일* 인지 모름(stdout JSON 도 발신 안 됨, 사이클 도중 raise 이므로).

**왜 fix 회귀인가**: 선행 라운드의 CRIT-4 fix 는 "cursor 를 *clean* 사이클 끝에만 advance" 패턴을 채택했다. 이 자체는 옳다. 그러나 *per-file* fatal 과 *vault-wide* fatal 을 동일 클래스로 raise 하면 cursor block 이 데이터 파괴 방지가 아니라 **vault stuck 무기** 가 된다.

**선행 리뷰**: R1 은 fatal 분류 자체를 검토 안 함. R2 SIG-4 는 import 실패만 다룸. 본 issue 미식별.

**어떻게 고칠까** (옵션 단계):

1. **최소**: per-file `VaultSyncFatal` 도 retry queue 에 enqueue + 사이클 *계속* (cursor advance 하되 file_map 미반영) — 운영자가 retry.json 으로 가시화. 단점: 사용자 모르게 파일이 빠진 상태로 cursor 가 advance.
2. **권장**: `VaultSyncFatal` 을 두 종류로 분리 — `VaultSyncFatalVault` (전체 stop, 예: auth invalid) vs `VaultSyncFatalFile` (per-file skip + retry log). `errors.py` 의 매핑에 scope 컬럼 추가:

   | 패턴 | severity | scope |
   |---|---|---|
   | 401 | fatal | vault |
   | 403 insufficientPermissions | fatal | **file** |
   | gws auth error (rc=2) | fatal | vault |
   | gws unknown stderr | fatal | **file** |

3. **빠른 hotfix**: sync 루프에서 `except VaultSyncFatal as e: log.error(...); enqueue_retry(...); error_count += 1; continue` — file_map 미반영 + retry queue 에 영구 등록 후 사이클 진행. 단 vault-wide auth invalidate 시 50개 파일 모두 같은 fatal 로 retry queue 폭주 — 트리거 임계값(같은 reason 5회) 두는 게 필요.

**무엇을 결정해야 하나**: spec(`analysis_and_design.md` §2.3) 의 retry 분류표에 file-scope vs vault-scope 컬럼 추가가 ADR-0017 사이드 결정으로 필요. 본 결정 전 production 진입 위험.

---

### CRIT-R4-4 [TestGap / Reliability] CRIT-1 (binary download) 회귀 방지 테스트가 mock 한계로 검증 불가 (`tests/test_sync.py:326-339`)

**무엇이**: `test_sync_incremental_with_text_file` 의 `fake_run_gws` 는 `["drive", "files", "get"]` 에 대해 `binary_output` 인자와 무관하게 `GwsResult(returncode=0, stdout="# hello\n\nbody\n", stderr="", duration_ms=5)` 를 반환한다. `stdout_bytes` 는 default `b""`.

**왜 위험한가**: CRIT-1 fix(binary_output 분기) 는 다음 회귀에 무방비.
- 누가 sync.py 의 `binary_output=True` 인자를 다시 제거해도 텍스트 파일 테스트는 통과(`is_text_mime=True` 경로 사용).
- 진짜 binary MIME(`application/pdf`, `application/vnd.openxmlformats-...`) 으로 sync 를 돌리는 테스트가 **하나도 없다**. mock 이 binary_output 분기를 simulate 하지 않으므로 회귀 시 `saved.write_bytes(b"")` 가 0 byte 파일 작성 → extraction failed 로 silent passthrough.
- R1·R2 가 CRIT-1 을 H1·CRIT-1 로 핵심 결함으로 지정했는데, 그 회귀 방지 테스트가 사실상 placeholder.

**어떻게 고칠까**:

```python
def test_sync_incremental_binary_pptx(tmp_path, monkeypatch):
    """CRIT-1 회귀 방지 — .pptx 의 raw bytes 가 손상 없이 vault 에 저장되는지."""
    pptx_bytes = b"PK\x03\x04" + b"\x00" * 100 + b"\xff\xfe non-utf8"  # ZIP 헤더 + non-UTF8
    def fake(args, params=None, *, timeout_sec=300, env_extra=None,
             binary=None, binary_output=False):
        if args[:3] == ["drive", "changes", "list"]:
            return GwsResult(0, json.dumps({...}), "", 10)
        if args[:3] == ["drive", "files", "get"]:
            assert binary_output is True, "binary file 다운로드는 binary_output=True 필수 (CRIT-1)"
            return GwsResult(0, "", "", 5, stdout_bytes=pptx_bytes)
        raise AssertionError(...)
    ...
    saved = vault_local / "deck.pptx"
    assert saved.read_bytes() == pptx_bytes  # 손상 없음
```

추가로 timeout / 403 fatal 경로 테스트도 부재(CRIT-R4-2, CRIT-R4-3 미커버).

---

## 2. HIGH (배포 전 반드시 fix)

### HIGH-R4-1 [Reliability / Durability] atomic write 가 fsync 누락 — power-fail 시 zero/partial 파일 가능 (`scripts/lib/sync.py:369-390`, `scripts/lib/state.py:22-40`)

`_atomic_write_wiki_page` 와 `_atomic_write_json` 모두 `os.replace` 만 사용. fsync 없음. POSIX 보장은 "rename 의 directory entry 가 atomic" 일 뿐, **tmp 데이터의 disk durability 는 별개**. OCI ARM Ubuntu 가 unexpected reboot (free tier 의 maintenance reboot 빈번) 시:

- rename 만 fsync 완료 → 파일이 존재하지만 content 가 0 byte 또는 직전 garbage.
- file_map.json 이 zero-length 가 되면 다음 sync 의 `_read_json` 이 `json.JSONDecodeError` raise → fatal exit.

**fix**:
```python
with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
    f.write(content)
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp_name, full_path)
# (선택) dir fsync — strict durability
dir_fd = os.open(str(full_path.parent), os.O_RDONLY)
try:
    os.fsync(dir_fd)
finally:
    os.close(dir_fd)
```

비용: write 당 ~수 ms. v0.1.0 처리량(파일 수십~수백) 에서 무시할만함. state I/O 에는 더더욱 중요.

선행 리뷰 둘 다 atomic write 를 "textbook quality" 로 칭찬했는데 fsync 누락은 textbook 누락.

---

### HIGH-R4-2 [Concurrency] 같은 vault 에 대한 동시 vault-fetch.py 실행 보호 없음 (`scripts/vault-fetch.py` 전체)

**시나리오**: systemd timer 가 600s 간격으로 fire 인데 이전 실행이 큰 PDF extraction 으로 600s+ 점유. 또는 운영자가 dev box 에서 동일 vault 로 수동 `vault-fetch.py --vault gdrive` 호출하는 사이 timer fire.

**위험**:
- 두 process 가 같은 `state_dir` 의 `file_map.json` 을 동시에 mutate. atomic write 는 race condition 보호 안 함 — read-modify-write 사이 다른 process 가 write 했어도 detect 불가 → **잃어버린 update**.
- 두 process 가 같은 vault local path 에 같은 파일을 write — `os.replace` 가 한쪽을 silently 덮어쓰지만, 둘이 *다른* bytes 였다면(modify race) 어느 게 vault 에 남을지 미정의.
- retry.json 의 `next_id` 가 두 process 사이 동기화 없으니 같은 id 중복 발급 가능.

`scripts/lib/state.py:enqueue_retry` 의 docstring 은 "단일 writer 가정으로 lock 불필요" 라 적혀있는데, **그 가정이 어디에도 강제되지 않는다**. F4 systemd unit 이 `RemainAfterExit=no` + 충분히 긴 `TimeoutSec` 로 운영하는 게 아니라면 race window 가 실재.

**fix**: vault-fetch.py 진입 시 `state_dir/.lock` 에 `fcntl.flock(LOCK_EX | LOCK_NB)` — 이미 잡혀있으면 `VaultSyncRetryable("concurrent run")` exit 75.

```python
import fcntl
lock_path = state_dir / ".lock"
with open(lock_path, "w") as lock_fd:
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise VaultSyncRetryable(vault_id=..., retry_after_sec=120,
                                  reason="concurrent vault-fetch in progress")
    # ... sync ...
```

---

### HIGH-R4-3 [Reliability] Google native export 의 0-byte silent failure (`scripts/lib/sync.py:322-338`)

R2 가 V2 assumption failure 로 짚었던 문제가 그대로 잔존. `result.stdout` 이 빈 문자열이어도 `saved.write_text("")` → `bytes_written=0` → `extract_text` 가 빈 본문 반환 → wiki page 가 frontmatter + 빈 본문으로 commit. operation 은 `created` 또는 `modified` 로 changed[] 에 정상 등재. 운영자가 hermes 알림으로 "5건 changed" 받지만 그중 5건 모두 빈 페이지일 수 있다.

선행 라운드 fix 는 binary_output 분기에 집중하면서 V2 silent-fail 가드는 추가 안 함.

**fix** (최소):
```python
if not result.stdout.strip() and mime in GWS_EXPORT_MIME:
    log.warning("gws export empty stdout: vault=%s id=%s mime=%s", vault_id, fid, mime)
    return ExtractionResult(
        body_text=f"[extraction failed: gws export returned empty stdout for {mime}]",
        tool="gws-export", tool_version="n/a",
        extraction_status="failed",
        reason="empty export",
    ), 0
```

V2 verification (Step 3 미실증) 이 확정될 때까지 이 가드가 안전 보루.

---

### HIGH-R4-4 [Reliability] `max_file_size_mb` 가드가 **binary export 결과 size 점검 안 함** + Drive native 는 size=0 이므로 무시 (`scripts/lib/sync.py:307-317`)

**현 코드**:
```python
size_bytes = int(file_meta.get("size", 0) or 0)
if max_file_size_mb and size_bytes and size_bytes > max_file_size_mb * 1024 * 1024:
    ... skip
```

**문제**:
1. `size_bytes` 가 0(Drive native gdoc/gslides/gsheet)이면 가드 미동작 — export 결과가 100MB 인 슬라이드도 통과해서 메모리 OOM. spec(SIG-3) 의 의도는 "Drive native 도 cap" 일 가능성이 큰데 코드 주석은 "binary 만 적용" 으로 의도적 trade-off.
2. binary download 시 `subprocess.run` 이 stdout 을 **whole** in-memory buffer 로 받는다 (`capture_output=True`). 500MB PDF 면 wikihub 프로세스가 500MB+ 메모리 점유. OCI free tier(1GB RAM) → OOM kill → cursor 미갱신 → 다음 사이클도 같은 파일 재시도 → infinite OOM loop.
3. `max_file_size_mb` 가 download *전* 가드인 점은 좋은데 streaming download (`gws --output <path>`) 옵션이 있다면 메모리 압박 자체를 회피 가능. 현재 `gws.py` 는 `--output` 사용 안 함.

**fix priorities**:
- 즉시: binary download 후 `len(result.stdout_bytes) > max_file_size_mb * 1024 * 1024` 사후 점검 추가(이미 메모리 점유했지만 disk write 는 막음).
- 중기: `gws drive files get --output <tmp_path>` 사용으로 streaming. V3 verification 결과 따라 결정.
- spec: Drive native cap 정책 결정 (현 주석은 의도적 면제처럼 보이는데 design 에 명문 없음).

---

### HIGH-R4-5 [Observability] `tool_version` 이 extraction 실패 시 `er.tool_version` 그대로 frontmatter 에 emit (`scripts/lib/sync.py:548-549`)

```python
extraction_tool=er.tool if er.extraction_status == "success" else None,
extraction_tool_version=er.tool_version,
```

I1 fix 로 `extraction_tool` 은 실패 시 None 으로 잘 만들었지만 `extraction_tool_version` 은 항상 전달. `build_source_frontmatter` 내부는 `if extraction_tool:` 분기로 둘 다 묶어 처리하므로 결과적 행동은 OK — 하지만 코드 가독성 결함 + 미래 refactor 시 (예: tool_version 만 별도 emit) inconsistency 가 침투. 또한 `er.tool_version` 이 `"unknown"` 인 경우와 `"n/a"` 인 경우의 의미 분리가 없음.

**fix**: 둘을 conditional 로 묶기:
```python
extraction_tool=er.tool if er.extraction_status == "success" else None,
extraction_tool_version=(er.tool_version if er.extraction_status == "success" else None),
```

---

## 3. MED (다음 PR 까지는)

### MED-R4-1 [Observability] per-file `error_count` 가 stdout JSON / last_sync 에 안 나감 (`scripts/lib/sync.py:489-622`)

`error_count` 와 `skipped_count` 는 logging.info 에 1회 emit 되고 끝. SyncResult 에 없음 → stdout JSON 에 없음 → hermes 가 텔레메트리화 불가. on-call 이 systemd journal grep 해야 vault 의 정상 사이클인지 (50건 처리됐는데 49건 skipped + 1건 error 인 사이클인지) 알 수 있다.

**fix**: `SyncResult` 에 `error_count: int`, `skipped_count: int` 추가 → stdout JSON 에 emit → last_sync.json schema(SIG-1) 에도 포함. 향후 Prometheus exporter 가 잡기 쉬움.

---

### MED-R4-2 [Observability] sync start/finish 로그가 `bootstrap=True/False` 만 emit, **root_folder_id 와 cursor_before/after 도 emit 권장** (`scripts/lib/sync.py:438, 619`)

현 start 로그(`sync.py:438`)는 root_folder_id 를 emit 하지만 cursor_before 은 line 484 별도 로그. finish 로그(`sync.py:619`)에는 cursor 정보 없음. on-call 디버깅 시 "이 사이클이 어느 cursor 에서 시작해 어디로 advance 했나" 가 핵심 — log 한 줄에 통합 권장.

```python
log.info(
    "sync done: vault=%s bootstrap=%s cursor_before=%s... cursor_after=%s... "
    "changed=%d deleted=%d skipped=%d errors=%d duration_ms=%d",
    vault_id, bootstrap_flag,
    cursor_before[:12] if cursor_before else "(none)",
    new_cursor[:12] if new_cursor else "(none)",
    len(changed), len(deleted), skipped_count, error_count, duration_ms,
)
```

또한 finish 로그의 `cursor_after` 는 `new_cursor` 변수에서 가져와야 진짜 advance 됐는지 검증 가능.

---

### MED-R4-3 [Reliability] retry queue `next_retry_at` 이 항상 now — `e.retry_after_sec` 무시 (`scripts/lib/sync.py:586`)

`VaultSyncRetryable(retry_after_sec=60)` 으로 raise 됐어도 enqueue 시 `next_retry_at=utc_now_iso()` 으로 즉시 재시도 가능 표시. quota exceeded 같은 retryable 은 60+s backoff 이 핵심인데, retry consumer (F5 agent) 가 이 필드를 신뢰하면 즉시 재시도 → 또 quota 실패 → infinite ping.

**fix**:
```python
from datetime import datetime, timezone, timedelta
next_retry_at = (datetime.now(timezone.utc) + timedelta(seconds=e.retry_after_sec)).isoformat(timespec="seconds")
```

---

### MED-R4-4 [Reliability] `operation="modified"` 하드코딩 → retry 시 의미 손실 (`scripts/lib/sync.py:584`)

per-file retryable enqueue 시 `operation="modified"` 고정. 처음 시도가 `created` (file_map 에 없던 새 파일) 였으면 retry 도 created 여야 의미가 맞다. file_map 에 entry 있는지 확인 후 분류해야 함. retry consumer 가 operation 으로 분기하는 로직(F5)이 있다면 잘못된 path 선택.

**fix**:
```python
op = "modified" if sr in file_map["files"] else "created"
enqueue_retry(retry_obj, source_relpath=sr, ..., operation=op, ...)
```

---

### MED-R4-5 [SpecMismatch] `_handle_removed` 가 `file_map` 미등록 파일의 **vault local file 은 cleanup 안 함** (`scripts/lib/sync.py:401-413`)

```python
entry = next((p for p, v in file_map["files"].items() if v.get("source_id") == file_id), None)
if not entry:
    log.info("removed (untracked): file_id=%s", file_id)
    return
```

`removed` change 인데 file_map 에 entry 없는 경우:
- 이전 사이클에서 file_map 갱신 직전 crash → orphan vault file 존재 가능.
- Drive 가 동일 fileId 의 created 후 즉시 removed 를 한 사이클에 emit → 이번 사이클에서 created 가 file_map 에 등록되기 전 removed 처리.

이 경우 `vault_local_path` 에 orphan binary 가 남는다. 미러 semantics 위반.

**중요도**: low-medium — Drive change ordering 보장이 있다면 거의 없는 시나리오지만 OCI 운영 6개월 누적 시 orphan 1-2건은 기대.

**fix**: untracked 라도 alternate identification (file_id 가 들어있을 수 있는 파일을 vault 안에서 찾는) 또는 별도 GC pass 로 disk-watch (F4) 책임으로 명시. spec 명문화 필요.

---

### MED-R4-6 [Security] credentials_path 가 fatal reason 메시지에 그대로 노출 (`scripts/lib/credentials.py:33`)

`f"credentials file 권한 위반: {oct(mode)} (요구: 0o600)"` — 경로 직접 노출 안 함(체크 OK). 그러나:
```python
remediation=f"chmod 600 {path}"
```
remediation 에 절대 경로 노출. systemd journal 은 root 만 읽지만 hermes 가 fatal reason+remediation 을 Telegram 으로 전송하는 경로(F1 §4.6.6)면 채팅에 `/opt/wikihub/.credentials/token_gdrive.json` 절대경로가 흘러간다. Telegram message log 는 보존 정책에 따라 외부 노출 위험.

**fix**: remediation 에서 경로 redact (`...token_*.json`) 또는 vault_id 만 emit.

또한 `ensure_env_var` (`credentials.py:62-68`) 는 `dict[str, str]` 으로 env var 를 만들지만, 만약 gws subprocess 가 fail 했을 때 stderr 가 env 를 dump 하는 어떤 디버그 모드라면 credentials_path 가 stderr 에 surface 가능. mitigation 으로 `classify_gws_error` 의 reason 에서 path-like 패턴 redact 권장.

---

### MED-R4-7 [Reliability] `subprocess.run` 에 `start_new_session=True` 미설정 → timeout 시 zombie children (`scripts/lib/gws.py:83-90`)

gws CLI 가 내부적으로 google API 호출 helper 또는 ssh 등 자식 process 띄울 수 있는데, `subprocess.run(timeout=N)` 은 직접 자식만 SIGKILL. process group 단위 kill 이 없으면 grand-child 가 살아남아 zombie / 자원 점유.

**fix**:
```python
proc = subprocess.run(
    cmd,
    capture_output=True,
    text=not binary_output,
    timeout=timeout_sec,
    env=env,
    check=False,
    start_new_session=True,  # 새 process group
)
```

timeout 시 `os.killpg(proc.pid, signal.SIGKILL)` 처리는 `run` 이 자동으로 안 함 — 더 안전한 방법은 `Popen` + manual timeout. v0.1.0 에서는 `start_new_session=True` 만이라도 추가하고 zombie 누적 시 v0.2.x 에서 Popen 마이그.

---

### MED-R4-8 [Reliability / Resource] `subprocess.run(capture_output=True)` 는 stdout 전체를 메모리 buffer — 큰 binary 시 OOM (`scripts/lib/gws.py:83-90`)

HIGH-R4-4 의 부수효과지만 별도 항목. v0.1.0 에서 `gws drive files get --alt media` 가 500MB PDF 를 stdout 으로 emit 하면 `subprocess.PIPE` buffer 가 메모리 전체 차지. `--output <path>` 옵션이 gws 에 있다면 streaming 으로 우회 가능 (V3 verification 의제).

**spec 액션**: V3 verification 의 "binary download streaming 가능 여부" 항목을 명시화하고, 가능하면 `binary_output=True` 대신 `output_path` 패턴 도입.

---

## 4. LOW / NIT

### LOW-R4-1 [Code Quality] `tests/test_sync.py` 의 mock 이 `binary` 인자를 `binary=None` 으로 받아 real signature(`binary: str = "gws"`)와 불일치 (`tests/test_sync.py:268-269`)

```python
def fake_run_gws(args, params=None, *, timeout_sec=300, env_extra=None, binary=None,
                 binary_output=False):
```

Real `run_gws` 의 default 는 `"gws"`. mock 이 None 을 default 로 받으면 caller 가 `binary="gws"` 를 명시 전달했을 때만 일치, 미전달 시 mock 입장에서 None 로 보이므로 binary 인자 검증 테스트는 작성 불가. 큰 결함은 아니지만 mock 정합성 결함.

**fix**: `binary="gws"` 로 default 통일.

---

### LOW-R4-2 [Code Quality] `_safe_version` 의 `PackageNotFoundError` import 가 unused (`scripts/lib/extraction.py:34`)

```python
from importlib.metadata import version, PackageNotFoundError  # type: ignore
return str(version(distribution_name))
```

`PackageNotFoundError` 는 `except Exception:` 으로 통째 잡히므로 import 가 dead. `from importlib.metadata import version` 만 남기는 게 깨끗.

---

### LOW-R4-3 [Code Quality] `_handle_removed` 가 untracked file 에도 `save_file_map` 호출 (`scripts/lib/sync.py:505-506`)

```python
_handle_removed(...)  # 내부에서 entry 없으면 early return
save_file_map(state_dir, file_map)  # 항상 호출 — untracked 면 변경 없는 disk write
```

성능 영향 micro 지만 fsync(HIGH-R4-1 fix 후) 가 들어가면 무의미한 disk fsync 가 매 untracked removal 마다 추가. _handle_removed 가 True/False 반환하도록 변경하거나 caller 가 변경 여부 추적.

---

### LOW-R4-4 [Observability] `log.info("removed: %s", entry)` — vault_id 누락 (`scripts/lib/sync.py:413`)

멀티 vault 환경(F4 이후) 에서 systemd journal 의 log entry 만 보고는 어느 vault 의 removal 인지 모름. 모든 sync log 에 `vault=%s` prefix 통일 권장.

---

### LOW-R4-5 [Code Quality] `_changes_list_iter` 의 `new_start` truncation logic 가독성 떨어짐 (`scripts/lib/sync.py:209`)

```python
log.info("changes.list 사이클 완료: %d changes (new start_token=%s)",
         len(changes), new_start[:16] + "..." if len(new_start) > 16 else new_start)
```

Python 연산자 우선순위로 `new_start[:16] + "..."` 와 `new_start` 둘 다 ternary 의 branch — 의도 맞음. 다만 `(new_start[:16] + "...") if len(new_start) > 16 else new_start` 로 괄호 추가가 명확.

---

### NIT-R4-1 [Code Quality] `gws.py:78-79` 의 env 처리 — `env=None` 일 때 child 가 부모 env 를 그대로 상속 (`scripts/lib/gws.py:76-79`)

```python
env: dict[str, str] | None = None
if env_extra:
    env = os.environ.copy()
    env.update(env_extra)
```

`env_extra` 없으면 `env=None` → subprocess.run 이 부모 env 사용. 이 자체는 OK. 단 isolation 관점에서 `PATH` 또는 `LD_LIBRARY_PATH` 등을 명시 controlling 하지 않으면 systemd unit 의 `Environment=` 설정 외 다른 env (운영자가 임시 export 한 것) 가 gws 에 leak 가능. F4 install.sh / systemd unit 책임으로 미루지만 design intent 코멘트 필요.

---

## 5. SRE 관점 강점 (잘 적용된 부분 — 균형감)

- **CRIT-R1·R2 trace-driven fix**: 28개 선행 지적 중 결정적 결함(binary mode, file_map 즉시 commit, sanitize, cursor 순서)을 직접 다루고 코드 주석으로 매핑 추적. 운영 시점 회귀 진단에 유용.
- **`_atomic_write_wiki_page` 와 `_atomic_write_json` 의 tempfile 패턴 통일**: same-dir tmpfile + os.replace + try/except cleanup — fsync 만 빠뜨렸을 뿐 패턴 자체는 textbook (HIGH-R4-1 보강 후 production grade).
- **`_passes_trust_boundary` 의 `ownedByMe` short-circuit**: "내가 만들고 남에게 공유한" 케이스는 trust → exclude 안 함 — 사용자 의도 반영.
- **`classify_gws_error` 의 retryable 우선 매칭**: 403+quota 를 403+permission 보다 먼저 검사 — 일시·영구 분류가 의도대로 동작.
- **logging 의 stderr 강제**: stdout JSON contract 보호. R1 H2 fix 로 disabled vault 경로도 json.dumps + flush.
- **systemd Restart=on-failure 와 exit 75 매핑**: EX_TEMPFAIL convention 준수.
- **cursor truncation in log**: `cursor_before[:16]` — sensitive token 부분만 emit, 전체 노출 회피 (logging hygiene).
- **GwsResult.stdout_bytes 신규 필드**: dataclass 가 backward-compat 유지하면서 binary path 분기 가능하게 함. 향후 ulimit/Popen 마이그 여지를 남김.

---

## 6. 종합 권고

| 항목 | 권고 |
|---|---|
| **배포 차단** | CRIT-R4-1 (raw name path), CRIT-R4-2 (timeout silent skip), CRIT-R4-3 (per-file fatal stuck), CRIT-R4-4 (binary 테스트 무력화) 4건 fix 전 production 진입 금지 |
| **배포 전 fix** | HIGH-R4-1 (fsync), HIGH-R4-2 (file lock), HIGH-R4-3 (empty export guard), HIGH-R4-4 (memory cap), HIGH-R4-5 (tool_version consistency) |
| **첫 사이클 안 fix** | MED-R4-1~8 — 운영 가시성·retry 정확성·spec 명확화 |
| **v0.2.x 미루기 가능** | LOW/NIT 전체 |
| **Spec 의제** | ADR-0017 (gws stderr 매핑) 에 *scope* (file vs vault) 컬럼 추가 결정 필요 — CRIT-R4-3 의 정본 결정 |
| **테스트 보강 필수** | binary mock 강화(`stdout_bytes`), timeout 시뮬, per-file fatal 시뮬, concurrent invocation lock 시뮬, fsync 회귀(power-fail 시뮬은 어렵지만 atomic write helper 자체의 fsync 호출 검증 가능) |
| **V<N> verification 우선순위** | V3 (binary streaming) 와 V2 (export 출력 형식) 를 launch 전 실호출 확정 — 그 결과에 따라 HIGH-R4-3/4 의 final fix 형태 결정 |

**배포 차단 4건 + HIGH 5건은 launch blocker.** 그 외 MED 항목은 sysmtemd timer 가 24/7 도는 환경에서 첫 7일 안에 surface 될 가능성이 높으므로 v0.1.0 첫 패치(v0.1.1)에 묶어 처리 권장. F4(systemd unit / install.sh) 통합 시 retry queue consumer / fatal webhook 연결이 들어오면 MED-R4-1·MED-R4-3 의 메트릭 정합성이 진가를 발휘한다.

**선행 리뷰 두 건과의 비교**: R1 은 코드 정합성 위주, R2 는 *failure mode* 와 V<N> assumption 매핑 위주. R4(본 리뷰)는 **fix-induced regression** 과 **24/7 daemon 운영 특화 결함(timeout chain, concurrency, fsync, per-file vs vault fatal 분리)** 을 추가 surface. 세 라운드를 합치면 CRIT 총 7건(R1·R2: H1·CRIT-1~4 5건 + R4: CRIT-R4-1~4 4건 — 일부 중첩), HIGH 약 10건 — 본 PR 은 다음 라운드 fix 후 재리뷰 후 deploy 가 정석.
