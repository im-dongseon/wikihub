# Code Review 2 — Production Safety SRE perspective (F3 Step 4)

- **Reviewer**: general-purpose subagent acting as SRE
- **Date**: 2026-05-13
- **Target**: F3 Step 3 implementation — scripts/* + tests/*

## Verdict

코드 골격은 단정하고 모듈 경계·exit-code 분류·atomic state I/O는 spec과 잘 정렬되어 있다. 그러나 **이 상태로 OCI 서버에 deploy하면 첫 binary 파일(.pptx/.docx/.pdf) sync 즉시 subprocess UnicodeDecodeError로 죽고 모든 후속 changes가 stuck 된다** — `lib/gws.py:run_gws`의 `text=True` 결정과 `lib/sync.py:_download_to_vault`의 stdout 캡처 모델이 Drive binary download 경로와 근본적으로 호환되지 않는다(아래 CRIT-1). 이 한 건이 v0.1.0 launch blocker. 그 외 directory-traversal 가능 path, file_map 부분 갱신 후 crash 시 cursor 손실, last_sync.json/stdout 사이 정합성 결함, log.md drift 정합성 등 5건의 significant 운영 리스크를 별도로 기록했다. **CRIT-1·CRIT-2 두 건 해결 + SIG-1·SIG-2 fix 후 launch 안전.**

## Critical operational gaps

#### CRIT-1. Binary download은 v0.1.0에서 작동하지 않음 — `lib/gws.py:73-80` + `lib/sync.py:269-277`

**Scenario**: 사용자 Drive에 `meetings/Q1.pptx`가 sync 대상으로 등장. agent가 `/wh:ingest --vault gdrive` 호출.

**Current code**:
```python
# lib/gws.py
proc = subprocess.run(cmd, capture_output=True, text=True, ...)
```
```python
# lib/sync.py _download_to_vault
result = _run(vault_id, ["drive", "files", "get"], {"fileId": fid, "alt": "media"}, env_extra=env_extra)
saved.write_text(result.stdout, encoding="utf-8") if mime.startswith("text/") else saved.write_bytes(
    result.stdout.encode("utf-8", errors="replace")
)
```

**Risk**: `subprocess.run(text=True)`는 stdout을 strict UTF-8로 decode한다 (재현: 임의의 `\x89` 시작 PNG/PPTX bytes를 stdout으로 emit하는 subprocess는 `UnicodeDecodeError` raise). gws가 `--alt media`로 binary PDF·PPTX·DOCX·XLSX를 stdout으로 emit하는 즉시 `run_gws` 안에서 `UnicodeDecodeError`가 raise되고 본 예외는 `VaultSyncRetryable`/`VaultSyncFatal` 어디에도 매핑되지 않아 `vault-fetch.py:101`의 generic `except Exception`이 잡아 exit 2(Fatal)로 끝난다. 더 위험: 다음 사이클도 같은 cursor에서 같은 파일을 다시 받으려 하므로 **vault는 영구 stuck**. 운영자는 systemd journal에서 `UnicodeDecodeError: codec can't decode byte 0x89` stack을 봐도 root cause("text=True"가 잘못)에 다다르기 어렵다. 또한 `errors="replace"` re-encoding이 동작하더라도 이미 strict decode 단계에서 죽었기 때문에 dead code다.

**Recommendation**:
1. `lib/gws.py`에 `binary: bool = False` 옵션 추가 → `subprocess.run(capture_output=True, text=False)`로 호출, `GwsResult.stdout: bytes` 반환(또는 별도 `stdout_bytes` 필드).
2. 더 안전한 옵션: gws에 `--output <path>` 강제(V2/V3 verification 후 확정 결정사항이지만 본 결정 안 되면 v0.1.0 시작도 위험). 의도적으로 v0.1.0이 binary 미지원(text/markdown export만)이라면 코드에 명시적 guard: `if mime in BINARY_MIMES: raise VaultSyncFatal(...)`로 빠른 실패.
3. 단기 minimal fix: `subprocess.run(..., text=False)`로 호출 후 stderr만 `.decode('utf-8', errors='replace')`. stdout은 JSON 호출은 `.decode()` 후 parse, binary 호출은 raw bytes 그대로 file write.

#### CRIT-2. wiki_path tmp 파일은 동일 디렉토리 충돌 + 권한 위반 + 실패 시 leak — `lib/sync.py:287-294`

**Scenario**: sync 중 `wiki/sources/gdrive/meetings/Q1.pptx.md`를 작성하는 동안 disk full 또는 SIGTERM.

**Current code**:
```python
def _write_wiki_source_page(*, instance_root, wiki_path_rel, frontmatter_dict, body):
    full = instance_root / wiki_path_rel
    full.parent.mkdir(parents=True, exist_ok=True)
    page_text = emit_page(frontmatter_dict, body)
    tmp = full.with_suffix(full.suffix + ".tmp")
    tmp.write_text(page_text, encoding="utf-8")
    tmp.replace(full)
```

**Risk**:
1. **Tmp 파일이 fixed name** (`Q1.pptx.md.tmp`) — `lib/state.py`의 `mkstemp(prefix=...)`와 달리 random suffix 없음. systemd Type=oneshot이 단일 writer 보장하지만 메인테이너가 manual로 vault-fetch.py를 돌리는 동안 systemd timer가 fire하면 (F3 design §OPS dev box 절차 권장됨) 두 writer가 같은 tmp 이름에 경합. 한 쪽이 부분 write 중인 파일을 다른 쪽이 `replace` → 손상된 페이지가 wiki에 commit됨.
2. **Disk full 또는 process kill mid-write 시 tmp leak**: `.tmp` 파일이 `wiki/sources/gdrive/meetings/`에 남는다 — wiki view tool들이 이 파일을 valid markdown으로 indexing할 수 있고 `/wh:lint`가 entry로 잡을 수도 있다.
3. **`tmp.write_text` 실패 시 try/except 없음** → tmp file 정리 안 됨 (`lib/state.py:_atomic_write_json`은 try/except로 보호하지만 sync.py는 빠뜨림).
4. **빈 suffix case**: 만약 미래에 wiki_path가 `wiki/sources/gdrive/no_ext_file`이면 `with_suffix("" + ".tmp")` = `no_ext_file.tmp` — OK. 단 현재는 `.md`로 끝나도록 보장하므로 즉시 위험은 아니지만 brittle.

**Recommendation**: `lib/state.py:_atomic_write_json` 의 `tempfile.mkstemp(prefix=".", suffix=".tmp", dir=full.parent)` 패턴을 통일 helper로 추출하고 (`atomic_write_text(path, text)`) sync.py에서도 사용. try/finally로 tmp leak 방지.

#### CRIT-3. Directory traversal — `lib/sync.py:199-206` + `_download_to_vault:244`

**Scenario**: 악의적 또는 사고로 Drive에 `name: "../../etc/passwd"` 같은 파일이 sync 범위에 들어옴 (Drive API는 파일명에 `/`를 허용한다 — 보통 UI는 차단하지만 API 직접 호출로 가능). 또는 합법적 사용자가 `name: "회의록 / 2026 Q1.pptx"`처럼 슬래시를 포함한 파일명을 만든다.

**Current code**:
```python
def _source_relpath(file_meta: dict) -> str:
    return str(file_meta.get("name", "")).lstrip("/")
# ...
saved = vault_local_path / name
wiki_path_rel = _compute_wiki_path(vault_id, source_relpath, mime)
```

**Risk**:
- `lstrip("/")`은 leading `/`만 제거. `../../etc/passwd`는 그대로 통과 → `saved = /opt/vault-gdrive/../../etc/passwd` = `/opt/etc/passwd`. wiki 측에서도 `wiki/sources/gdrive/../../etc/passwd.md` → `etc/passwd.md` 작성됨.
- 정상 사용자도 `name`에 `/`가 있으면 (Drive UI도 일부 경우 허용) wiki 디렉토리 트리에 의도하지 않은 mkdir.
- `saved.parent.mkdir(parents=True, exist_ok=True)` 후 `mkdir(0o755)` default — vault 외부 디렉토리 생성 권한이 있으면 sync user 권한에서 만들어버린다.
- 추가로 NUL byte (`\x00`)·newline 포함 시 `Path()` 자체는 받지만 일부 도구가 부정확하게 처리하여 후속 문제.

**Recommendation**:
1. `_source_relpath`에서 sanitize: `os.path.normpath` 후 결과가 `..`로 시작하거나 `/`로 시작하거나 NUL 포함이면 skip + stderr warning + file_map 미등록 (F3 design §OPS-D 권장사항이 코드에 미반영).
2. `saved`와 `full` 모두 resolve 후 `instance_root`/`vault_local_path`의 prefix인지 검증.

```python
def _safe_relpath(name: str) -> str | None:
    if not name or "\x00" in name or "\n" in name:
        return None
    cleaned = name.lstrip("/").replace("\\", "/")
    if cleaned.startswith("..") or "/../" in cleaned or cleaned in {"..", "."}:
        return None
    return cleaned
```

#### CRIT-4. 부분 사이클 crash 시 file_map 손실 (cursor advance 누락) — `lib/sync.py:359-422`

**Scenario**: changes 50건 중 30번째 파일 download 도중 `VaultSyncRetryable` (rate limit) 발생. 본 예외는 `_run`이 raise하여 `sync()`까지 propagate.

**Current code**:
```python
for ch in changes_synthetic:
    # ...
    saved_path, er, bytes_written = _download_to_vault(...)
    # ... write wiki page, mutate file_map in memory ...
save_file_map(state_dir, file_map)
save_cursor(state_dir, new_cursor, ...)
save_last_sync(state_dir, _result_to_dict(result))
```

**Risk**: 30번째 파일에서 raise되면 `save_file_map`·`save_cursor` 둘 다 호출 안 됨. 다음 사이클은 **이전 cursor**로 다시 50건을 받는다. 1~29번째 파일은 이미 vault에 다운로드되었고 wiki page도 작성됐으나 file_map은 미갱신 — 그 결과 다음 사이클에서 1~29번째 파일이 다시 `operation="created"`(in file_map이 없으므로)로 처리되어 wiki page를 덮어쓴다. 멱등하다고 볼 수도 있지만 **`created` 표기로 잘못된 ingest log + extracted_at·last_synced_at 갱신 + entity 추출 (F5) 재실행 등 cascading downside**가 있다.

또한 `_run`이 mid-loop에서 raise → vault에 부분 다운로드된 파일과 wiki에 부분 작성된 페이지가 **mismatched state**로 남는다. 본 design은 changes를 단일 transaction으로 처리하지만 transaction boundary는 (a) page write 후 file_map update를 묶고 (b) 매 page write 후 file_map을 incremental save하거나 (c) 처리 진행도를 별도 marker로 기록해야 안전하다.

**Recommendation**: 두 가지 중 택일.
- **Incremental persist**: 각 file 처리 후 `save_file_map` (atomic write 비용 vs 안전성 trade-off — v0.1.0 규모면 수십~수백번 atomic write도 ok).
- **Cursor not advanced until clean**: changes loop 안에서 retryable raise시 처리된 file_map은 commit하되 cursor는 advance 안 함 (= 다음 사이클이 동일 changes를 다시 처리하지만 file_map에 이미 들어있어 `modified`로 분류, idempotent).

현 코드는 cursor advance도 file_map advance도 둘 다 안 되는 worst-case. 최소한 cursor를 advance하지 않도록 try/except가 sync() level에 필요.

## Significant concerns

#### SIG-1. last_sync.json schema가 stdout JSON contract와 다르고 wiki_path 정합 결손 — `lib/sync.py:436` + `result_to_stdout_json:445`

**Scenario**: `/wh:setup`이나 operator가 last_sync.json을 읽어 마지막 sync 상태를 확인하려고 하는데 `changed`는 wiki_path를 포함하지만 `deleted`는 source_relpath string만 들어있다. stdout JSON contract와 last_sync.json schema가 묵시적으로 같다는 가정.

**Current code**: `save_last_sync(state_dir, _result_to_dict(result))`는 `SyncResult` dataclass의 `asdict`를 직접 저장. 결과:
```json
{"vault_id":..., "has_changes":..., "changed":[{...all 6 fields...}], "deleted":[...], "cursor_before":..., "cursor_after":..., "started_at":..., "finished_at":..., "duration_ms":...}
```
반면 stdout JSON contract는 cursor·started/finished 없음. design F1 §4.4.3 lift는 last_sync.json이 `cursor_before/after` 포함을 명시했으나 **schema가 어디에도 적혀있지 않다** (Q2 결정도 정책만 명시, 필드 목록 미정). 운영자가 last_sync.json을 코드 reference로 사용하면 코드 변경 시 silent breakage.

**Recommendation**: last_sync.json schema를 `_system/wiki-schema.md` 또는 별도 ADR에 명문화 + sync.py 코드에 schema 문자열 상수로 명시(`SCHEMA_VERSION = 1`). 또는 stdout JSON contract와 동일하게 통일.

#### SIG-2. `removed` change에서 file_map deletion 후 vault local의 binary는 미삭제 — `lib/sync.py:360-371`

**Scenario**: Drive에서 파일 삭제 → changes.list에 `removed=True` 항목 → file_map에서 entry 제거 + wiki page unlink. 그러나 vault 외부 `/opt/vault-gdrive/<name>` 원본 파일은 그대로 남는다.

**Current code**:
```python
if ch.get("removed"):
    # ...
    (instance_root / wp).unlink(missing_ok=True)
    del file_map["files"][entry]
    continue
```

**Risk**: vault 디렉토리에 orphan binary 누적 → disk full 위험 + GDPR/IRM 우려 (Drive에서 삭제됐는데 서버에 남아있음 = 의도와 불일치). spec(`wiki-schema.md` §책임 매트릭스의 sync "다운로드·갱신")은 명시적으로 vault 삭제를 sync 책임으로 적지 않았지만 **mirror semantic을 깬다**. ingest.md §Step 4의 "이미 script가 삭제 처리"가 wiki만 가리키는지 vault까지 가리키는지 모호.

**Recommendation**: vault 원본도 unlink하거나 (정합), 아니면 spec에 명시적 "vault는 보존, wiki만 삭제"를 적고 disk-watch가 cleanup 책임을 가지도록 명시. 현재 코드는 두 spec 사이에서 ambiguous.

#### SIG-3. PDF·PPTX·XLSX extraction의 메모리 비제한 + 도구별 무한 hang 가능성 — `lib/extraction.py:139-154` 등

**Scenario**: 200MB PDF, 100슬라이드 PPTX, 50시트 XLSX가 vault에 들어옴.

**Current code**: `pdfminer.extract_text(str(path))`는 파일 전체를 메모리에 올린다. `openpyxl.load_workbook(read_only=True, data_only=True)`는 read_only 덕에 streaming이지만 `data_only=True`는 cached values 의존(공식 안 caching된 sheet은 None만 반환 — silent data loss). `python-pptx` Presentation 객체도 메모리 전체 로드.

**Risk**: OCI ARM Ubuntu의 free tier는 보통 1GB RAM. 큰 PDF 하나에 OOM → systemd Type=oneshot이 SIGKILL → cursor 미갱신 → 다음 사이클도 같은 PDF 재시도 → infinite loop. extraction은 timeout도 없음.

**Recommendation**:
- 파일 크기 cap을 `wikihub.yaml.operations` 또는 default 50MB로 추가. 초과 시 `_failed("size-cap")`로 graceful skip.
- 또는 process-level memory cap(ulimit RLIMIT_AS) — F4 systemd unit 책임으로 위임 가능.
- 적어도 design 단계에서 V8 verification에 "큰 파일 메모리 사용량" 항목 추가하고 코드에 `# v0.1.0 size cap 없음 — operator가 root_folder_id로 격리` 코멘트 명시.

#### SIG-4. extraction tool import 실패 시 graceful이지만 동일 mime 모든 후속 파일도 같은 실패 반복 — `lib/extraction.py:50-53`

**Scenario**: `requirements.txt`가 OCI 서버에 partial install된 상태(예: pdfminer.six는 빠짐). 첫 PDF 처리에서 `ImportError` → `_failed`로 wiki page 작성. 50개 PDF 있으면 50번 `import` 시도 + 50번 같은 실패 메시지.

**Current code**: `def extract_pdf(path): try: from pdfminer.high_level import extract_text; import pdfminer ... except ImportError as e: return _failed(...)`

**Risk**: 운영 측면에서는 graceful이라 production 사고는 아니지만 (a) systemd journal에 같은 ImportError 50번 = noise, (b) F4 install.sh의 deps 검증 결함이 surface 안 됨(50개 silent fail 후 lint이 catch). 또한 `_safe_version("pdfminer_six")` (실제 import path `pdfminer`) — 모듈명 `_safe_version(tool.replace("-", "_"))` 변환은 `pdfminer.six` → `pdfminer_six`가 되어 import 실패해서 "unknown" 반환. tool_version 정합성 결함.

**Recommendation**:
- vault-fetch.py startup 시 1회 deps probe (모든 extraction libs를 import하고 결과 캐시). missing은 startup에서 stderr warning만 — extraction 시점에서는 cached miss 사용.
- `_safe_version("python-pptx")` 같은 호출에서 정확한 import path 매핑 dict 사용(`python-pptx → pptx`, `pdfminer.six → pdfminer`, `python-docx → docx`, `openpyxl → openpyxl`).

#### SIG-5. log.md 갱신은 agent 책임이지만 F3는 sync 사이클의 mtime drift 보호 미비 — `wiki-schema.md` 책임 매트릭스 vs `_write_wiki_source_page`

**Scenario**: ingest.md §Step 1은 pending_ingest가 가리키는 wiki_path의 source_mtime이 pending과 다르면 "source mtime drift detected" 로깅 후 최신 본문 신뢰. 그러나 F3 sync는 source_mtime을 file_map에 기록할 뿐 wiki 페이지 frontmatter의 `source.source_mtime` 값과 file_map 값이 다를 수 있는 race를 고려 안 함.

**Current code**: sync는 `_write_wiki_source_page`로 wiki 페이지를 atomic 덮어쓰기, file_map도 in-memory mutate 후 mass save. 한 changes_list 처리 도중 같은 파일이 두 번 등장(Drive가 동일 fileId의 connsecutive change 보고 가능 — 동일 cursor 범위에서 modify 2회)하면 두 번째 처리에서 wiki 페이지는 최신, file_map도 최신, but 첫 processing의 byte download는 vault에서 덮어써짐.

**Risk**: low(spec이 set semantics + 항상 최신 본문 신뢰)지만 v0.1.0에서 `for ch in changes_synthetic`의 중복 fileId 처리 미보호 — bytes_written 메트릭이 double-counted 등 minor inconsistency.

**Recommendation**: changes_synthetic loop 진입 전 fileId 기준 dedupe(가장 최신 modifiedTime 유지). 또는 v0.1.0 acceptable risk로 명문화.

## Observability deficits

#### OBS-1. stdout/stderr 분리 약속이 disabled vault 경로에서 사실상 위반 — `vault-fetch.py:62-66`

**Scenario**: 메인테이너가 vault를 임시로 disable. systemd timer fire.

**Current code**:
```python
if not vault_cfg.enabled:
    log.info("vault %s disabled — no-op", args.vault)
    print('{"vault_id": "%s", "has_changes": false, "changed": [], "deleted": [], "duration_ms": 0}'
          % args.vault)
```

**Risk**: `%s`로 vault_id를 raw string embedding — vault_id가 JSON-unsafe char(쌍따옴표·역슬래시)를 포함하면 stdout JSON 손상. (config.py가 `^[a-z][a-z0-9_]*$` regex 강제하므로 실질 위험은 낮지만, **JSON contract를 raw f-string으로 emit하는 패턴이 코드 다른 곳으로 번질 위험**. 정본은 `json.dumps`. 작은 일이지만 한 번 노출되면 다음 hand-edit으로 깨진다.)

또한 `print(... default file=sys.stdout)`는 OK이지만 `vault-fetch.py:88`은 `sys.stdout.write + flush` 명시 — 일관성 부족.

**Recommendation**: `print(json.dumps({"vault_id": args.vault, "has_changes": False, "changed": [], "deleted": [], "duration_ms": 0}))`로 통일.

#### OBS-2. sync 진행 로그가 거의 silent — `lib/sync.py` 전반

**Scenario**: 3am에 sync가 stuck. on-call이 systemd journal을 본다. 마지막 줄: `sync ok: vault=gdrive changed=0 deleted=0 duration_ms=42` 또는 아무 것도 없음.

**Current code**: `lib/sync.py`는 logging 호출 없음. `vault-fetch.py:_setup_logging`은 basicConfig만 set, 진행 상황(어떤 fileId 처리 중, 몇 page 받았는지)은 stderr에 안 나옴.

**Risk**: gws subprocess가 hang하거나 50개 파일 중 어디서 stuck했는지 모름. duration_ms는 emit되지만 그게 끝까지 도달 못 했으면 emit 안 됨.

**Recommendation**: `_run`에 `log.info("gws %s params=%s", args, params)` 1줄 (pageToken 등 민감 정보는 redact). 각 file download 시 `log.info("downloading %s (size=%d)", relpath, size)`. systemd journal로 자연 흐른다.

#### OBS-3. classify_gws_error의 reason 메시지가 sync에 도달했을 때 wiki/_lint나 ops-alert에 surface되지 않음

**Current code**: `_run`이 `VaultSyncRetryable(reason=reason)`으로 reason 첨부 → `vault-fetch.py`의 `log.warning("retryable: %s", e)`로 stderr 1줄 → systemd journal. 다음 사이클까지의 사용자는 systemd journal grep 필요.

**Recommendation**: retry 발생 시 `_state/<vault>/retry.json`의 queue에 enqueue되도록 sync flow에 통합. 현재 `state.enqueue_retry`는 정의됐지만 `sync()` 안에서 호출되지 않는다 — dead code. retry queue가 실제로는 채워지지 않으므로 ingest playbook의 retry 기반 진단이 불가능.

#### OBS-4. credentials.py가 0o600을 요구하지만 ACL/sticky/setgid bit는 미검증

**Current code**: `mode = path.stat().st_mode & 0o777; if mode != 0o600`

**Risk**: 누군가 `chmod g+x` 후 다시 `chmod 600` → 0o600이지만 `stat.S_ISGID`나 `S_ISUID`가 남아있으면 detect 못 함. 또한 POSIX ACL(`getfacl`)로 group이 추가됐어도 `st_mode`로 감지 못 함. v0.1.0 acceptable risk(아래 참조)지만 운영 관점에서 noteworthy.

## Acceptable for v0.1.0 (acknowledged risks)

- **CRIT-3의 보완**: 파일명 한글·non-ASCII 그대로 통과는 wiki-schema spec 의도(§A2). NUL/`\\`/CR/LF가 Drive 파일명에 들어올 가능성은 낮지만 sanitize는 추가 비용 거의 없음. CRIT-3는 fix 필수이나 한글·공백·기타 비-ASCII는 그대로 둠.
- **OBS-4 ACL bit 미검증**: v0.1.0은 메인테이너 단독 운영 가정. ACL/sticky 검증은 v0.2.x.
- **SIG-3 메모리 비제한**: F3 design §V8 verification 결과로 surface 후 ADR로 결정. v0.1.0은 root_folder_id로 격리하는 운영 정책으로 mitigate 가능.
- **OBS-3 retry queue 미사용**: F3 design은 retry queue를 미래 F5에서 채운다는 명시는 없으나 ingest.md의 retry 정책은 pending_ingest.json 기반(agent 책임)이라 vault-fetch.py가 retry.json을 안 채워도 ingest playbook은 동작. 단 `state.enqueue_retry`가 dead code인 점은 design intent 재확인 필요(미사용이라면 코드 삭제).
- **Test coverage gaps**: 아래 별도 절.
- **`exclude_shared_with_me` post-filter의 `ownedByMe` field 의존**: Drive API가 항상 반환한다는 가정은 V1 verification 결과에 의존. 누락 시 `_passes_trust_boundary`는 default `False`(필터 통과)로 동작 — fail-open. v0.1.0 acceptable이지만 V1 verification에서 fields request에 명시 포함되어 있음(line 139, 169) — defensive parsing은 OK.

## What's well-handled

- **`lib/state.py:_atomic_write_json`의 tmpfile+os.replace 패턴**: `mkstemp`로 unique name + same-dir + try/except로 leak 방지. textbook-quality. CRIT-2의 wiki page write도 이 패턴을 그대로 reuse해야 함.
- **classify_gws_error의 우선순위 ordering**: 403+quota retryable이 403+permission fatal보다 먼저 매칭 — correct(quota는 일시, permission은 영구).
- **stderr truncation to 500 chars**: noisy gws stderr를 systemd journal flood 안 함 + reason 필드 길이 bound.
- **vault-fetch.py:101의 generic `except Exception` → exit 2**: stack trace 누락 위험 없음(`log.exception`이 stderr에 traceback emit). 단 CRIT-1의 UnicodeDecodeError가 이 경로로 빠지는 게 문제.
- **frontmatter.py의 unicode preservation**: `allow_unicode=True` 명시 + 한글 테스트 케이스 존재.
- **config.py의 vault id regex enforcement**: setup.md spec과 정합(`^[a-z][a-z0-9_]*$`).
- **YAML loading은 `yaml.safe_load`** (RCE 위험 없음).
- **credentials.py 600 verification + JSON schema 검증**: file-level은 충분.

## V<N> assumption failure mode analysis

**V1 (`gws drive changes list` schema)**:
- 가정 빗나가면: stdout JSON parse 실패 → `_gws_json`에서 `VaultSyncFatal("JSON 파싱 실패")` raise → exit 2.
- **운영 측면**: 잘 surface된다(reason에 stdout 첫 500자 포함). 메인테이너가 1회 fix 후 진행 가능. **safe**.

**V2 (`files.export` 출력 방식)**:
- 가정 빗나가면: gws가 stdout이 아니라 `--output <path>` 강제이거나 다른 출력 모드. `result.stdout`이 빈 문자열 → `saved.write_text("")` → 0바이트 export 파일 + `extract_text`가 빈 body 반환 → wiki page에 빈 본문. **silent failure!** bytes_written=0이지만 changed[]에 들어가서 has_changes=True로 보인다. agent가 entity 추출 시도하지만 본문이 없어서 결과 없음.
- **운영 측면**: 매우 위험. 실패 시그널이 약함. systemd journal에서도 0바이트 통과는 noise처럼 보임. **V2는 verification 우선순위 최고. 미실증 상태로 production 절대 불가**.

**V3 (`files.get --alt media` binary download)**:
- 가정 빗나가면: 1순위로 CRIT-1처럼 UnicodeDecodeError로 crash(stderr stack trace로 surface). 2순위로 stdout이 empty + `--output` 강제 — V2와 같은 silent 0바이트. **CRIT-1 fix(binary mode)를 하지 않으면 V3 실패는 즉시 crash이지만 그건 차라리 visible**. CRIT-1 fix 후에는 V2와 같은 silent risk.

**V4 (stderr 패턴)**:
- 가정 빗나가면: 미매치 stderr는 Fatal(M1 default). 첫 quota 발생 시 retryable이 아니라 fatal → 운영 alert 1회 noise, vault stuck 안 함 (다음 사이클에서 재시도 가능 — 단 pending_ingest 미작성이라 agent도 재시도 안 함). **재시도 미스 = SLA 위반이지만 데이터 손실 없음. safe.**

**V5 (credentials JSON schema)**:
- 가정 빗나가면: gws가 token JSON을 인식 못 함 → exit code 2(auth) → fatal로 분류. setup.md의 light call에서 1차 surface. **safe**.

**V6 (gws version pinning)**:
- F4 책임. F3은 단지 `gws` PATH lookup. version mismatch로 args.parse 실패 시 exit 3(validation) → fatal. **safe**.

**V7 (root_folder_id changes API)**:
- 가정 빗나가면: changes API가 root_folder_id 필터 무시 → vault 외부 변경도 들어옴 → post-filter 없으면 무관 파일까지 sync. 현재 코드는 `_passes_trust_boundary`만 있고 root_folder_id post-filter는 **incremental sync에서 실종됨** (design §2.5는 "post-filter로 source_relpath가 root_folder_id 하위인지 확인 후 처리"라고 명시했지만 `lib/sync.py:359-380`에 해당 로직 없음). **이건 V7 assumption 결과 의존이 아니라 design 명시 사항 누락 — SIG-급 결함**. 사용자 Drive 전체가 vault에 sync될 위험.

**V8 (extraction 의존성)**:
- 가정 빗나가면: ImportError로 `_failed` 반환 → SIG-4 noise. **safe**.

**V9 (`files.list` pagination)**:
- 가정 빗나가면: nextPageToken 처리 잘못으로 무한 loop 또는 1 page만 처리. 무한 loop는 systemd unit의 TimeoutSec가 cap한다(F4 책임). 1 page만 처리면 vault 일부만 sync된 채 cursor 발급 → 누락 파일은 다음 changes에서 잡힘(modify 발생 시) 또는 영구 누락(static 파일). **bootstrap 무결성 위험. V9 verification 우선순위 높음**.

**추가 발견 — V7 spec 명시되었으나 코드 미반영**: design.md §2.5는 "incremental sync 시 root_folder_id post-filter로 source_relpath 확인" 명시. `lib/sync.py` 어디에도 이 검사 없음. 별도 SIG로 분류:

#### SIG-6 (V-derived). incremental sync의 root_folder_id post-filter 미구현 — `lib/sync.py:359-380`

**Scenario**: 메인테이너가 trust boundary로 `vaults[gdrive].options.root_folder_id = "<wikihub-folder>"` 설정. bootstrap은 `_files_list_iter`에서 `q: "'<id>' in parents"` 적용 ✓. 그러나 incremental은 changes API 호출만 — root_folder_id 무시.

**Risk**: bootstrap 후 사용자가 Drive에서 root_folder_id 바깥의 파일을 수정 → changes에 등장 → vault에 무단 sync → wiki에 untrusted content 흘러들어옴. trust boundary 우회.

**Recommendation**: changes loop에서 `file.parents`를 검사하여 `root_folder_id`가 ancestor에 포함되는지 확인. 또는 v0.1.0은 root_folder_id 미지원 명시 + spec 갱신.

## Test coverage gaps (runtime perspective)

테스트는 happy path와 명시적 error injection을 잘 다루지만 다음 production failure mode를 **테스트하지 않음**:

1. **binary subprocess output**: `test_gws.py`는 mock_binary가 text만 emit. PNG header(`\x89PNG`)를 emit하는 binary는 CRIT-1을 surface해야 함.
2. **disk full mid-write**: `_atomic_write_json`이 ENOSPC에 어떻게 반응하는지 미테스트. 단 tmpfile 정리는 `test_atomic_write_cleans_tmp_on_failure`가 부분적으로 cover.
3. **subprocess timeout**: `subprocess.TimeoutExpired` 시 child process가 zombie인지 미검증. Python 3.x `subprocess.run`은 timeout 시 `.kill()` 호출하지만 long-running gws의 자식 process tree까지 reap은 안 함. `start_new_session=True` + process group kill이 더 안전.
4. **path traversal**: `name="../etc/passwd"` 같은 file_meta는 미테스트. CRIT-3 trigger.
5. **concurrent vault-fetch.py invocations**: 단일 vault, 두 동시 호출. lockfile 없음 — state corruption 시연 가능 테스트.
6. **mid-loop exception**: 5개 changes 중 3번째에서 gws 실패. file_map과 cursor 상태가 어떻게 남는지 미테스트(CRIT-4).
7. **JSON contract 보존**: 정상 sync 결과 stdout이 정확히 1줄이고 valid JSON인지(다른 stdout pollution 없는지) 미테스트.
8. **약한 assertion**: `test_stderr_truncated_to_500: assert len(reason) <= 600` — 너무 lax. 600이면 truncation을 거의 검증 못 함(prefix `"gws unrecognized stderr: "`가 23 chars + 500 = 523). `<= 525` 정도가 적절.
9. **`enqueue_retry`는 단위 테스트만 — sync 흐름에서는 호출 안 됨**: 통합 측면에서 dead code임을 surface하는 테스트 없음.
10. **last_sync.json schema 정합성**: stdout JSON과 비교 검증 없음. SIG-1 surface 못 함.

---

## 우선순위 요약 (배포 전 처리 순서)

1. **CRIT-1**: gws binary mode (text=False) — launch blocker.
2. **CRIT-3**: path traversal sanitize — launch blocker (보안 + 데이터 무결성).
3. **CRIT-4**: cursor advance 조건부 — launch blocker (cursor 손실 시 운영 stuck).
4. **CRIT-2**: wiki page atomic write helper 통일 + try/finally — high priority.
5. **SIG-6**: root_folder_id incremental post-filter 또는 spec 갱신 — high priority(security boundary).
6. **SIG-1·SIG-2·SIG-3·SIG-4·SIG-5**: medium — 첫 production cycle 안에 후속 patch 가능.
7. **OBS-1~4**: 운영 가시성 향상 — F4 통합 시 함께 처리 가능.

테스트 보강은 위 fix와 함께 진행 권장(특히 binary mock_binary, path traversal, mid-loop exception 케이스).
