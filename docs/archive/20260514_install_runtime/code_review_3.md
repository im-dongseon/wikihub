# Step 4 R15 — feature-dev:code-reviewer

**리뷰어**: claude (general-purpose subagent)
**범위**: F4 install_runtime feature 의 V<N> Phase 2 결함 9건 fix internal consistency
**일자**: 2026-05-17
**대상 커밋**: `feature/install_runtime` HEAD (`788d938`), main 대비 29 commits ahead
**리뷰 산출물**: 본 파일

본 라운드는 internal consistency 7개 측면만 검토 (SRE/운영 측면은 R16 담당). 검토 우선순위:

1. 결함 fix 9건 간 상호 충돌·regression
2. ADR vs 코드 정합 (ADR-0024·0025·0026·0027·0028·0029)
3. VaultSyncFatal.scope 정합 (mount.py 의 raise 사이트 + exceptions.py default + caller 호환성)
4. systemd unit template 의 substitution 정합 (`{...}` brace + `%i` 의 2-pass)
5. `_RCLONE_AUTH_PATTERNS` regex 커버리지 + false positive
6. 결함 fix 의 surgical 정도 (CLAUDE.md §2 Karpathy #3)
7. 새로 추가된 코드 (sync.py `_NATIVE_MIME_TO_EXT`, mount.py rc JSON 분기) 의 spec 자기 일관성

---

## CRIT (반드시 fix)

| # | 항목 | 위치 | 근거 |
|---|---|---|---|
| C1 | 결함 #9 fix 가 wiki-schema.md §A2 contract 위반 — Google native 의 wiki page 파일명이 `<relpath>.docx.gdoc.md` 패턴이 됨 (정합: `<relpath>.gdoc.md`) | `scripts/lib/sync.py:288-340` (`_source_relpath` + `_compute_wiki_path` 상호작용) | `_source_relpath` 가 mimeType 기반으로 `.docx`/`.xlsx`/`.pptx` 를 raw_name 에 prepend (line 301-303), 그 후 `_compute_wiki_path` 가 `mime in GWS_EXPORT_MIME` 분기에서 `.gdoc`/`.gsheet`/`.gslides` 를 추가로 suffix (line 332-336). 결과: Google Doc → `wiki/sources/gdrive/test.docx.gdoc.md` (실제 정본은 `test.gdoc.md`). `[[link]]` 도 `[[gdrive/test.docx.gdoc]]` 로 `wiki-schema.md:124,130` spec 위반. V<N> Phase 2 검증은 `bytes_written` 만 확인 → 미surface. **fix 권장**: ① `_source_relpath` 는 native 일 때 raw_name 변환 안 함 + `_download_to_vault` 의 `saved` 계산 시점에서만 native ext 추가, 또는 ② `_compute_wiki_path` 가 native 일 때 source_relpath 의 `.docx` suffix 를 strip 후 `.gdoc.md` 적용 (둘 다 surgical) |

## HIGH (fix 권장)

| # | 항목 | 위치 | 근거 |
|---|---|---|---|
| H1 | ADR-0026 본문 spec 과 mount.py 구현 divergent — ADR 은 `["rclone", "rc", "--rc-addr", rc_addr, ...]`, 코드는 `--url http://{rc_addr}` (결함 #1 fix) | `docs/adr/0026-vfs-refresh-policy.md:37,96` vs `scripts/lib/mount.py:200` | 결함 #1 fix (`113aa66`) 가 `--rc-addr` → `--url` 로 변경했으나 ADR-0026 본문은 갱신 안 됨. ADR 이 결정의 정본 (CLAUDE.md §7 — "결정의 정본은 ADR 파일") 이라 V<N> 향후 검증·refactor 시 ADR 기준으로 회귀할 위험. **fix**: ADR-0026 §"vfs_refresh helper" 의 코드 블록을 `--url` 로 갱신 + Cross-references 의 `--rc-addr` 문구 명확화 (server-side flag 와 client-side flag 분리) |
| H2 | extraction.py 의 module-level `extract_text` 가 동일 모듈 `extract_pdf` 내부 import 와 name 충돌 (shadow) | `scripts/lib/extraction.py:146,162` | `extract_pdf()` 내부에서 `from pdfminer.high_level import extract_text` 가 local scope 에서 module-level `extract_text` 함수를 shadow. 실제 동작은 안전 (local scope) 하지만 동일 모듈 내 두 동일 이름 함수가 공존하여 future maintainer 혼동 + IDE refactor 시 cross-rename 위험. **fix**: pdfminer 의 import 를 `from pdfminer.high_level import extract_text as _pdfminer_extract_text` alias 로 분리 (1줄 변경) |
| H3 | extraction.py docstring (`extract` 함수) 가 결함 #9 fix 후 outdated — "Google native 는 본 함수가 처리 안 함" 명시이지만 실제로 `LOCAL_EXTRACTION_DISPATCH` 에 native MIME 매핑 (line 201-203) | `scripts/lib/extraction.py:218` | docstring "Google native 는 본 함수가 처리 안 함 (sync.py 가 gws export 후 ``extract_text`` 호출)" 은 v6 (gws-only) 잔재. 결함 #9 fix 이후엔 `extract(saved, mime)` 가 native MIME 도 dispatch (line 455). **fix**: 문서 갱신 — "Google native 는 rclone mount 의 binary export 후 본 함수가 LOCAL_EXTRACTION_DISPATCH 로 매핑" |
| H4 | `_handle_removed` 의 `vault_local_path` 인자가 dead code — 본문에서 미사용 | `scripts/lib/sync.py:523-546` | v9 R11-CRIT-3 fix 가 `(vault_local_path / entry).unlink()` 라인을 제거하면서 호출자 시그니처는 surgical 보존 (caller 호환성). 결과적으로 `vault_local_path` 매개변수가 무용 — docstring/comment 만 참조. Karpathy #3 surgical 정신 위배 (변경 라인이 사용자 요청에 직결). **fix**: caller (sync.py:648) 와 함께 매개변수 제거 (2 라인 변경, 호출자 1개) |

## MED (선택)

| # | 항목 | 위치 | 근거 |
|---|---|---|---|
| M1 | `_NATIVE_MIME_TO_EXT` 가 `--drive-export-formats docx,xlsx,pptx,md` 순서에 silent coupled — 운영자가 mount template 의 export-formats 순서를 바꾸면 sync.py 가 mismatch | `scripts/lib/sync.py:309-313` vs `_system/systemd/wikihub-mount@.service.template:19` | sync.py 는 `application/vnd.google-apps.document → .docx` hardcode. mount template 가 `--drive-export-formats md,docx,...` 로 바뀌면 mount 는 `.md` 로 export 하지만 sync.py 는 `.docx` 찾음 → mount path miss. **fix**: ① `_NATIVE_MIME_TO_EXT` 를 yaml config (`operations.drive_export_priority`) 로 외부화, 또는 ② mount template 의 export-formats 가 본 dict 와 정합 필수임을 주석으로 명시 (코드 변경 없음). 현재 코드 주석 (line 308) 이 절반 — 역방향 (yaml → template) 의존성은 미명시 |
| M2 | mount.py 의 rc JSON 파싱 `rc_response.get("result", {}).get("", "")` 가 `result` 가 dict 가 아닐 때 AttributeError | `scripts/lib/mount.py:213` | rclone rc API 의 spec 은 `result` 가 dict 라 정상 case 는 OK 지만, error response 또는 future 버전에서 `result: []` 또는 `result: null` 반환 시 `.get("", "")` 가 AttributeError → except 분기 없음 → `try/except json.JSONDecodeError` 가 catch 안 함 → `_RCLONE_AUTH_PATTERNS` 매칭 path 미진입 → unhandled. **fix**: line 213 을 `result_val = rc_response.get("result"); if isinstance(result_val, dict): backend_msg = result_val.get("", "")` 패턴으로 (2 라인 변경) |
| M3 | mount.py 의 rc JSON 파싱이 recursive refresh 의 sub-path error 를 누락 — `result.""` 가 OK 라도 깊은 경로 fail 가능 | `scripts/lib/mount.py:213-219` | rclone `vfs/refresh recursive=true` 의 응답은 `{"result": {"": "OK", "subdir/file.docx": "couldn't list..."}}` 패턴 가능. 현재 코드는 root path (`""`) 만 검사 → sub-path 의 OAuth/SA error 시 silent pass + 다음 사이클 stale read. **fix**: result dict 의 모든 value 를 join 후 regex 검색 (1줄 변경: `error_full = result.stderr or " ".join(str(v) for v in result_val.values())`) |
| M4 | `_RCLONE_AUTH_PATTERNS` 가 SA 키 rotation (만료된 키 인지) · GCP project disabled · IAM revoke 패턴 미커버 | `scripts/lib/mount.py:44-53` | 현재 패턴: OAuth (`Token expired`, `invalid_grant`, `401 Unauthorized`, `oauth2.*invalid`, `unauthorized_client`, `access_denied`) + SA 6건 (`private key should be`, `asn1: structure error`, `service account.*disabled`, `key.*disabled`, `invalid_credentials`, `no such file or directory.*sa_`). 미커버: SA 키 자체 expire (`key has expired`), GCP project disable (`project ... is disabled`), Drive API quota exceeded permanent (`403.*billing`), IAM bind 제거 (`caller does not have permission`). **fix**: 본 패턴들은 V<N> Phase 2 SA 시뮬에서 surface 안 됨 → V18+ 시뮬 시점에 evidence 확보 후 surgical 추가 (현재 fix 안 해도 운영 시점 surface 가능) |
| M5 | `_RCLONE_AUTH_PATTERNS` 의 `no such file or directory.*sa_` 가 false positive 위험 — Drive 폴더에 우연히 `sa_` 로 시작하는 파일 (예: `sa_report.docx`) 가 missing 시 매칭 가능 | `scripts/lib/mount.py:50` | 패턴 의도: credentials 파일 사라짐 (`sa_<vault_id>.json`). 그러나 regex 는 `sa_` literal 만 검사 → Drive 의 정상 파일명에도 매칭. 정상 사이클에서 rclone 이 missing 파일에 대해 stderr 에 `no such file or directory` 를 emit 하는 케이스는 한정적이지만 false positive surface 가능. **fix**: 패턴을 `no such file or directory.*\.credentials/sa_` 또는 `sa_[a-z0-9_]+\.json` 으로 narrow |
| M6 | `_compute_wiki_path` 가 native mime 이면서 source_relpath 가 이미 `.gdoc` suffix 끝나는 경우는 ext 추가 skip 하지만, 결함 #9 fix 후엔 절대 발생 안 함 (source_relpath 가 항상 `.docx`/`.xlsx`/`.pptx` 로 끝) — dead branch | `scripts/lib/sync.py:334` | line 334 의 `if virt and not source_relpath.endswith(virt)` 분기에서 `source_relpath.endswith(virt)` 가 True 인 path 는 결함 #9 fix 후 도달 불가 (`.docx` 가 `.gdoc` 로 끝나는 경우 없음). dead code 자체는 무해 하지만 C1 fix 시점에 함께 정리 권장 |
| M7 | install.sh 의 `_install_uv` 의 trap RETURN 이 `_step3_venv` 의 venv idempotency 검증 분기 중간에 `return 0` 시 cleanup 가능 — trap 의 `tmpdir` 변수 scope 가 함수 scope 이라 안전하나 trap 동작 자체는 옅음 | `install.sh:235-278` | `_install_uv` 의 `trap 'rm -rf "$tmpdir"' RETURN` 는 함수 return 시점에 trap 실행. 그러나 line 236 `if command -v uv ...` 분기에서 `return 0` 시 `tmpdir` 변수 미정의 (`mktemp -d` 이전) → `rm -rf ""` 위험 (실제 동작: `rm -rf` 인자 없음 → no-op 일 수 있지만 shell 마다 다름). **fix**: trap 등록을 mktemp 이후로 이동 (1 라인 reorder), 또는 `tmpdir=""` 초기화 후 trap |

## LOW (참고)

| # | 항목 | 위치 | 근거 |
|---|---|---|---|
| L1 | `_NATIVE_MIME_TO_EXT` 가 사용 위치 (line 301) 보다 정의 위치 (line 309) 가 뒤 — Python 은 runtime resolution 으로 동작하지만 정의 후 사용 컨벤션 위배 | `scripts/lib/sync.py:301,309` | 모듈 import 시점엔 `_source_relpath` 함수 body 가 평가 안 됨 → 안전. 그러나 reader 의 reading flow 가 어색. **fix**: `_NATIVE_MIME_TO_EXT` 정의를 line 288 (`_source_relpath` 정의 직전) 으로 이동 |
| L2 | `mount.py` 의 docstring (line 7-11) 의 사이클 흐름 예시가 `mount.assert_mount_alive(...)` + `mount.vfs_refresh(...)` 로 표시되지만 vault-fetch.py 의 실제 호출은 `assert_mount_alive(...)` (line 118) + `vfs_refresh(...)` (line 120) — module prefix 없음 | `scripts/lib/mount.py:9-10` | 단순 문서/코드 표기 불일치. 동작 영향 없음. **fix**: docstring 의 `mount.` 접두사 제거 |
| L3 | `wikihub-vault@.service.template` 의 `Restart=` 미설정 주석 (line 36) 이 ADR-0021 v4 surgical lift 참조 — ADR 본문 갱신 후엔 v5 일 가능성 (lift 후 추가 변경 있을 시) | `_system/systemd/wikihub-vault@.service.template:36` | ADR-0021 본문에 v 표기 없음 → 주석의 "ADR-0021 v4" 가 무엇을 의미하는지 불명 (F1 §4.8.2 v4 인지, ADR-0021 v4 인지). reader 가 헷갈림. **fix**: "F1 §4.8.2 + ADR-0021 D1 surgical lift" 로 명확화 |
| L4 | `_install_rclone` 의 `current` 변수 quote escape 가 not strict — `current` 가 빈 문자열일 때 `[[ -n "$current" && "$current" == "$pinned" ]]` 는 안전하지만 `awk '{print $2}'` 가 multi-token line 에서 부정확 | `install.sh:452` | rclone v1.69.1 의 `rclone version` 첫 줄은 `rclone v1.69.1` (2 토큰) — `$2` 가 `v1.69.1` 로 안전. 그러나 future 버전 출력 format 변경 시 break 가능. R16 영역과 겹쳐 본 라운드 내 fix 불요 |
| L5 | install.sh 의 `_step45_rclone` 가 `_check_rc_port_available` 호출 시 yaml 부재 케이스를 skip 으로 정합 처리 (line 508-510). 그러나 두 번째 호출 (yaml 존재) 시 다른 vault 의 port 와 충돌 케이스 (서로 yaml entry 가 동시에 같은 port) 검증 부재 — yaml 내 중복은 미검증 | `install.sh:498-510` | port 가용성 (외부 process 사용 중) 만 검증, yaml 내 중복은 미검증. config.py 의 `_parse_vault` 에서도 port 중복 검증 부재. v0.1.0 단일 vault 가정으로 surface 안 됨. R16 영역 가까움 |

## 통과 항목 (정합 확인)

### 결함 fix 9건 간 상호 충돌·regression

- **결함 #1 (mount.py `--rc-addr` → `--url`) ↔ #6 (rc JSON parsing)**: 둘 다 `vfs_refresh` 내부 변경. `--url` 가 client-side flag 라 RCLONE_RC_ADDR env (server) 와 분리 — rc API 자체는 정상 응답 → JSON parsing 진입 → backend error 추출 → regex 매칭 정합. ✅
- **결함 #6 (rc JSON parsing) ↔ #7 (VaultSyncFatal.scope)**: mount.py 가 raise 하는 `VaultSyncFatal(scope="mount")` (line 250) 가 vault-fetch.py 의 `getattr(e, "scope", "vault")` (line 174) 에서 보존. last_failure.json 의 scope="mount" → ops-alert 의 fallback diagnostic 분기 정합. ✅
- **결함 #2 (SA override) ↔ #8 (camelCase)**: 둘 다 sync.py 내부 변경. 호출 순서: `sync()` 진입 → SA override (line 574-581) → `_bootstrap_token` 호출 (line 624) → `getStartPageToken` camelCase (line 165). 두 fix 가 직렬 — 충돌 없음. ✅
- **결함 #3·#4·#5 (systemd template)**: ExecStartPre fusermount + PATH /usr/local/bin + timer inline comment 제거. 세 fix 가 같은 commit (`6d644c4`) 에 묶임 + 영향 영역 분리 (mount@ ExecStartPre, 4 unit PATH env, 2 timer 주석 위치). 상호 직교. ✅
- **결함 #9 (Google native source_relpath) ↔ V15a fix (β3 → β2)**: V15a 진단으로 β2 채택 → mount 가 binary export → 결함 #9 가 sync.py 측 mount lookup miss fix. 두 fix 가 chain (mount 가 .docx 로 export → sync.py 가 .docx 로 lookup) — 정합. ✅ **단 wiki page 파일명 contract 위반 (C1) 은 별개**.
- **결함 #10 (install.sh main guard)**: 본 fix 는 `BASH_SOURCE[0] == ${0}` 분기로 source 시 main 미실행 (`44a8b35`). 다른 fix 와 영역 분리 — 충돌 없음. ✅

### ADR vs 코드 정합

- **ADR-0024 v9 (mount scope)** — last_failure schema `scope` enum 에 `"mount"` 추가, writer 책임 mount.py 추가. 코드: `exceptions.py:36` 의 `scope: str = "vault"` default + mount.py 의 `scope="mount"` 명시 (line 138, 250) + vault-fetch.py 의 `getattr(e, "scope", "vault")` (line 174). ✅
- **ADR-0024 v9 fallback diagnostic** — ops-alert.py `collect_mount_fallback_failures` (line 91-136) 가 ADR §"Reader fallback diagnostic" spec 정합 (systemctl is-failed + journalctl tail). ✅
- **ADR-0025 β2** — mount template `--vfs-cache-mode minimal` (line 17) + `--drive-export-formats docx,xlsx,pptx,md` (line 19) 정합. V15a 진단 후 본 ADR 본문 갱신 (`e4a65a2`). ✅
- **ADR-0025 γ3 (GitHub Releases + SHA256SUMS + curl retry)** — install.sh `_install_rclone` (line 446-482) 가 spec 정합. `_curl_with_retry` 3회 @ 5min interval (line 396-407), `sha256sum -c` 검증, `/usr/local/bin` 배치. ✅
- **ADR-0025 δ2 (rc endpoint)** — mount template `--rc --rc-addr 127.0.0.1:{rc_port_for_%i}` (line 22-23) + yaml `rclone_rc_port` 정합. ✅
- **ADR-0026 K1 (recursive refresh)** — vault-fetch.py `vfs_refresh_mode == "recursive"` 분기 (line 119-124) + mount.py `vfs_refresh(recursive=True)` (line 168). ✅
- **ADR-0027 책임 분배 매트릭스** — sync.py 의 mount FS read (line 433/443/458) + gws drive changes API (line 165, 197, 224) 분리. extraction.py 의 Google native dispatch (line 201-203) 가 ADR Q1 lock 정합. ✅
- **ADR-0028 uv 단독** — install.sh `_install_uv` (line 235-278) + Python 3.12 pinned + `UV_VERSION=0.11.14` (line 38-39) + venv idempotency 검증 (line 289-299). ✅
- **ADR-0029 SA 채택** — credentials.py `assert_credentials` 가 `type == "service_account"` (line 48) + `private_key`·`client_email` (line 54) 검증. wikihub.yaml.example 의 `credentials_path: sa_gdrive.json` 정합. ✅
- **ADR-0029 SA Drive API 호환** — sync.py 의 `exclude_swm` 자동 override (line 574-581) — Drive API `sharedWithMe=false` query 의 SA 호환 회피. ✅

### VaultSyncFatal.scope 정합

- `exceptions.py:32` 의 default `scope: str = "vault"` — caller 가 keyword 안 줘도 안전.
- `mount.py` 의 2개 raise 사이트 모두 `scope="mount"` 명시 (line 138, 250). ✅
- `sync.py` 의 raise 사이트 6건 (`_run` 의 GwsBinaryMissing/non-zero, `_gws_json` 의 decode fail, `_bootstrap_token` 의 응답 미상, `sync()` 의 bootstrap guard 2건, `_download_to_vault` invariant) 모두 scope 미명시 → default "vault" 적용. ✅
- `config.py` 의 raise 사이트 다수 — `vault_id="__config__"` + default scope="vault". ops-alert 의 fallback diagnostic 분기는 scope 만 의존, vault_id 는 무관 → __config__ payload 도 정상 처리. ✅
- `vault-fetch.py:174` 의 `getattr(e, "scope", "vault")` — VaultSyncFatal 외 일반 Exception 도 본 except 분기 도달 가능성은 없음 (다른 except 가 catch) — fallback default 도 정합. ✅

### systemd unit template substitution 정합

- `wikihub-mount@.service.template` 의 brace: `{instance_root}`·`{venv_path}`·`{rclone_config_path}`·`{rclone_bin}`·`{remote_name_for_%i}`·`{vfs_cache_max_size}`·`{rc_port_for_%i}` + systemd `%i` 11회 — setup.md §2 의 2-pass 정합 (Pass 1: `%i → vault_id`, Pass 2: `format_map`). ✅
- `wikihub-vault@.service.template` 의 brace: `{instance_root}`·`{venv_path}`·`{credentials_path}`·`{agent_invocation}`·`{skill_prefix}`·`{rc_port_for_%i}` — 정합. ✅
- `wikihub-vault@.timer.template` 의 brace: `{sync_interval_sec}` + `%i` — 정합.
- `lint.service.template` + `lint.timer.template` — `%i` 미사용, 1-pass format_map 가능. ✅
- `ops-alert.service` — `%i` 미사용 + `{instance_root}`·`{venv_path}`·`{wikihub_home}` brace. ✅
- 결함 #4 fix (PATH `/usr/local/bin` 추가) 가 4 unit template 모두 동일하게 반영 — 일관성 정합. ✅
- 결함 #5 fix (timer inline comment 제거) — 2 timer template 의 `[Timer]` 섹션 위로 주석 이동. systemd parser 정합. ✅

### `_RCLONE_AUTH_PATTERNS` regex 정합

- V18 SA 시뮬에서 매칭한 패턴 (`private key should be a PEM`, `asn1: structure error`) 본문 포함. ✅
- OAuth 시대 패턴 (`Token expired`, `invalid_grant`, `401 Unauthorized`, `oauth2.*invalid`, `unauthorized_client`, `access_denied`) — ADR-0024 v9 spec 정본 그대로. ✅
- regex flag `re.IGNORECASE` — rclone stderr 대소문자 변동 흡수. ✅

### 결함 fix 의 surgical 정도 (Karpathy #3)

- 결함 #1: mount.py 의 `--rc-addr` → `--url` (1줄). 인접 라인 미수정. ✅
- 결함 #3·#4·#5: systemd template 3건만 변경. mount/vault 의 Python 코드 무변경. ✅
- 결함 #6: mount.py 의 `vfs_refresh` 함수 내부 JSON 파싱 분기 + `_RCLONE_AUTH_PATTERNS` regex 본문만 변경. assert_mount_alive 등 인접 함수 무변경. ✅
- 결함 #7: exceptions.py `scope` 필드 1개 추가 + mount.py 의 2 raise 사이트에 `scope="mount"` + vault-fetch.py 의 1 라인. surgical lift 정합. ✅
- 결함 #2: sync.py 의 `sync()` 함수 내 SA override 7줄 추가. credentials.py 무변경. ✅
- 결함 #8: sync.py 의 `_bootstrap_token` 1줄 변경 (subcommand 이름만). ✅
- 결함 #9: sync.py 의 `_source_relpath` + `_download_to_vault` is_native 분기 + extraction.py LOCAL_EXTRACTION_DISPATCH 의 native MIME entry 3건. 본 fix 가 가장 크지만 모두 결함 #9 spec 의 직접 대응. ✅ (단 wiki path 영향은 C1 별도)
- 결함 #10: install.sh main guard 라인 1개 추가. ✅
- V15a fix: mount template 1줄 (`--vfs-cache-mode full` → `minimal`) + ADR-0025 본문. ✅

### 새 코드의 spec 자기 일관성

- mount.py 의 `rc_error_msg` 분기 (line 209-219) — exit 0 + JSON parsable + result."" 가 "OK" 아닌 경우만 backend error 로 분류. Unreachable branch 없음. ✅
- sync.py 의 `_NATIVE_MIME_TO_EXT` (line 309-313) — 3 native MIME 만 매핑. `_virtual_ext_for_native` (line 316-321) 와 1:1 대응. ✅ (정의 위치는 L1)
- sync.py 의 `is_native` 분기 (line 429, 436-455) — `bytes_written == 0` 가드 (line 445) + extract dispatch. off-by-one 없음. ✅

---

## 종합 의견

V<N> Phase 2 의 결함 9건 fix 는 **internal consistency 측면에서 1건의 CRIT 외에는 대체로 정합**. CRIT-C1 은 결함 #9 fix 의 surface 안 된 sub-effect — V15a 검증이 `bytes_written` 만 봤고 wiki page 파일명을 확인 안 한 결과로 누락. 본 결함을 fix 안 하면 wiki-schema.md §A2 의 wikilink contract (`[[gdrive/notes/idea.gdoc]]`) 가 깨져 query/lint 단계 (F5) 에서 link resolution 실패 가능.

ADR-0026 본문 갱신 누락 (H1) 도 결정의 정본 정책 (CLAUDE.md §7) 정합 측면에서 fix 권장 — ADR 이 정본이라 갱신 안 하면 V<N> 재시도 시 mount.py 의 `--url` 가 "결함" 으로 잘못 분류될 위험.

나머지 fix 8건 은 surgical 정도·ADR 정합·scope 정합 모두 통과. systemd template substitution 의 2-pass 처리도 정합. `_RCLONE_AUTH_PATTERNS` regex 는 V18 evidence 기반 — 향후 surface 시 패턴 추가 운영 (M4·M5 는 미surface 영역).

본 라운드 CRIT 1건 + HIGH 4건 fix 후 Step 4 acceptance gate 통과 가능. MED·LOW 는 v0.2.x 또는 후속 surgical feature 로 이관 가능.

권장 후속:
1. **C1 즉시 fix** (1-2 라인 surgical): `_compute_wiki_path` 에서 native 인 경우 source_relpath 의 export ext suffix strip 후 virtual_ext 적용.
2. **H1 ADR-0026 본문 갱신**: 코드 블록 + Cross-references 의 `--rc-addr` 문구 명확화.
3. **H2·H3·H4 surgical cleanup** (3-5 라인): name shadow alias, docstring 갱신, dead parameter 제거.
4. **R16 (general-purpose SRE) 라운드** 진입 — 운영 측면 (systemd lifecycle race, port conflict, sudo NOPASSWD edge, journal log volume) 검토.
