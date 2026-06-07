# F4 design review R11 (feature-dev:code-reviewer — Step 2 v7)

리뷰어: feature-dev:code-reviewer
대상: v7 §10 신규 (rclone mount + gws 책임 분리) + v6 §1~§9 정합성
정본: analysis_and_design.md v7 + rclone_vs_gws_comparison.md + plan.md v2
독립성 선언: R5·R7·R9 (선행 라운드) 의 발견 답습 회피, v7 신규 spec 에만 집중

## 결함 요약
- CRIT: 3건
- HIGH: 4건
- MED: 3건
- LOW: 2건
- NIT: 1건

---

## CRIT

### CRIT-R11-1: Q1 (Google native export 메커니즘) 이 Step 3 미결로 미루기에는 sync.py 구현 진입 자체를 blocker 함

**위치**: §10.4.3 (line 1288–1292), §10.5 Q1

**현행**: §10.4.3 의 sync.py 사이클 흐름 step 4는 "각 변경 file 별: `_resolve_mount_path()` → `_read_from_mount()` → extraction → wiki page write" 로 명시. Q1 (Google native 처리 메커니즘) 은 미결.

**문제**: 두 옵션은 `sync.py` 의 if-분기 구조 자체를 달리 만든다. 옵션 1 (rclone `--drive-export-formats markdown` 자동 export) 이면 Google native 파일도 `_read_from_mount()` 단일 경로로 처리된다. 옵션 2 (gws `files export` 유지) 이면 Google native 에 대해 gws subprocess 를 추가로 호출하는 dual-path 가 남는다. v6 `sync.py` 의 `_download_to_vault` 는 `mime in GWS_EXPORT_MIME` 분기에서 `gws drive files export` 를 별도로 호출한다 (lines 379–408). v7 spec 이 이 분기를 "폐기 가능" 이라고 하지만 Q1 이 확정되지 않으면 폐기 여부 자체가 미정이다. 더 심각한 것은 옵션 1 의 품질이 V15a 검증 후에만 확정되는데, V15a 는 Step 3 진입 후로 미뤄져 있다 — 검증 실패 시 구현 롤백 리스크가 있다.

**제안**: Q1 을 Step 3 전에 lock 하거나, §10.5 에 "Step 3 구현 최초 단계에서 V15a PoC 먼저 수행 → Q1 확정 → 나머지 구현 진행" 의 sequencing 을 명시해야 한다. §10.4.3 의 사이클 흐름도 Q1 lock 후 update 대상.

**근거**: plan.md v2 §DoD — "Step 2 v7 단계: 결정 [J]·[K]·[L] 합의". Q1 은 [J] 결정의 구현을 결정적으로 달라지게 만드는 미결 사항이며, Step 2 DoD 에 "Q1 처리 순서 명시" 가 빠져 있다.

---

### CRIT-R11-2: `Requires=wikihub-mount@%i.service` + `Persistent=true` timer 의 race — reboot 직후 timer 가 mount 준비 전에 fire 하면 vault@ 가 즉시 실패하고 ops-alert 가 오발화

**위치**: §10.4.7 (line 1399–1426), §10.6.1 V12 갱신

**현행**: `vault@.service` 에 `Requires=wikihub-mount@%i.service` + `After=wikihub-mount@%i.service` 추가. `vault@.timer` 는 `Persistent=true` + `OnBootSec=2min`. `mount@.service` 는 `Type=simple` — 프로세스 시작된 시점이 active.

**문제**: `Type=simple` 의 active 상태는 rclone 프로세스 시작 시점이지 FUSE mount 완료 시점이 아니다. reboot 후 `OnBootSec=2min` 에 timer 가 fire 할 때 mount@ 가 active 상태여도 FUSE mount 가 아직 준비 중일 수 있다. 이 경우 `assert_mount_alive()` 의 `os.statvfs` 가 `ENOENT` / `EIO` 로 fail → vault@ exit non-zero → `OnFailure=ops-alert.service` 오발화. §10.4.7 은 "Step 3 V12 검증 시 정확한 sequencing 확인" 으로만 처리하지만, V12 는 pass/fail 검증이지 설계 결정이 아니다. 검증에서 발견되면 설계를 바꿔야 하므로 spec 수준에서 해법을 제시해야 한다.

**제안**: 다음 중 하나를 §10.4.7 에 명시해야 한다. (a) `assert_mount_alive` 실패 시 `VaultSyncFatal` 대신 exit 75 (Retryable) 로 처리하여 ops-alert 오발화 차단 — 이것이 가장 파급이 작다. (b) mount@ 에 FUSE 준비 완료 신호를 emit 하는 `ExecStartPost` polling + `Type=notify` 전환. (c) `OnBootSec` 을 늘려 여유 확보 (최약체).

**근거**: ADR-0021 은 mount 의존 추가 이전 작성 — mount 시작 race 를 다루지 않는다. §10.1 이 "minor 갱신" 으로 분류했지만 이 race 는 reboot resilience 의 accept invariant 를 위협한다.

---

### CRIT-R11-3: `_handle_removed` 의 `(vault_local_path / entry).unlink()` 가 mount FS 위에서 Drive 파일 삭제 위험 — 데이터 손실

**위치**: §10.4.3 (line 1283–1299), `scripts/lib/sync.py` lines 486–501

**현행**: v6 `_handle_removed` (SIG-2) 는 deleted 이벤트 시 `(vault_local_path / entry).unlink(missing_ok=True)` 로 vault local binary 를 삭제한다. v7 에서 `vault_local_path` 는 rclone mount point 자체 (`<instance_root>/vault/<vault_id>/`).

**문제**: mount FS 위에서의 `unlink()` 는 rclone 의 `--vfs-cache-mode full` 설정에서 **write-through** 동작으로 Drive 원본 파일까지 삭제할 수 있다. v6 에서는 로컬 다운로드 미러를 지우는 안전한 연산이었지만, v7 에서는 Drive 파일 자체를 삭제하는 위험한 연산이 된다. §10.4.3 이 "~90% 재사용" 이라고 하지만 이 90% 안에 데이터 손실 시나리오가 포함된다. §10.4.3 에는 `_handle_removed` 의 변경에 대한 언급이 전혀 없다.

**제안**: §10.4.3 에 다음을 명시해야 한다. `_handle_removed` 의 `(vault_local_path / entry).unlink()` 라인을 **제거** — mount FS 에서는 Drive 원본 삭제 위험. Drive 삭제 이벤트 처리 시 로컬 행동은 wiki page 삭제 + file_map 갱신만. `deleted_out` 로직은 그대로 유지하되 vault_local_path unlink 라인만 제거. 이 변경을 "SIG-2 mount 기반 적용" 으로 §10.4.3 에 명시.

**근거**: v6 `sync.py` SIG-2 docstring — "removed 시 vault binary 도 삭제 — 미러 일관성". v7 mount 기반에서 vault binary = Drive 원본이므로 이 로직은 의미 역전.

---

## HIGH

### HIGH-R11-1: `os.statvfs` 가 hung/slow FUSE mount 를 감지하지 못하고 indefinite block — `assert_mount_alive` 의 fail-fast 보장이 깨짐

**위치**: §10.4.6 (line 1366–1376)

**현행**: `assert_mount_alive` 는 `os.statvfs(str(mount_path))` 로 mount 상태 확인. `OSError` 발생 시 `VaultSyncFatal` 로 raise.

**문제**: dead mount 는 `ENOTCONN` / `ENOENT` 로 `OSError` 를 즉시 raise 한다. 그러나 FUSE mount 가 **hung** 상태 (프로세스는 살아있지만 Drive 네트워크 응답 대기 또는 vfs cache lock 대기) 인 경우 `os.statvfs` 는 timeout 없이 **block** 한다. `vault@.service` 의 `TimeoutStartSec=15min` 전체를 소비할 수 있다. §10.4.6 의 docstring은 "fail-fast 검증" 이라고 하지만 hung 상태에서는 fail-fast 가 아니다.

**제안**: §10.4.6 spec 에 다음 중 하나를 명시. (a) `subprocess.run(['ls', '-la', str(mount_path)], timeout=5)` 로 교체 — timeout 보장. (b) `threading` 으로 `statvfs` 를 wrapping 해서 timeout. 최소한 이 한계를 spec 에 인지된 제약으로 문서화하고 V13/V14 에 hung mount 케이스를 추가해야 한다.

**근거**: FUSE `EIO` (Input/output error) 는 mount 가 살아있지만 Drive 응답 실패인 경우로, 이 상태에서 `statvfs` 가 block 하는 것이 실제 FUSE 동작이다.

---

### HIGH-R11-2: `wikihub.yaml.example` v7 patch 가 vaults 를 map 구조로 표기 — v6 §4.3 의 list 구조와 불일치

**위치**: §10.4.4 (line 1303–1322), v6 §4.3 (line 774–818)

**현행**: v6 §4.3 의 `wikihub.yaml.example` 은 vaults 를 list 구조 (`- id: gdrive`) 로 정의. §10.4.4 의 v7 patch 는 vaults 를 map 구조 (`vaults: gdrive: ...`) 로 표기.

**문제**: list 구조와 map 구조는 `scripts/lib/config.py` 의 파싱 로직이 다르다. list 파싱은 `vaults[*].id` 로 식별, map 파싱은 `vaults.<key>` 로 식별. plan.md v2 에서 `config.py` 변경은 "vault.mount_path 옵션 파싱 추가" 만 기재 — 구조 전환에 대한 언급이 없다. 만약 §10.4.4 의 map 구조가 의도된 변경이라면 `config.py` 파싱 로직 전면 수정이 필요한 breaking change 이며, `sync.py` 의 `vault_cfg.id` / `vault_cfg.options` 파싱도 영향받는다. 만약 오기라면 §10.4.4 의 yaml 을 v6 list 구조로 정정해야 한다.

**제안**: §10.4.4 의 yaml 예시를 v6 §4.3 과 동일한 list 구조로 수정하거나, map 구조로 전환한다면 이를 명시적 breaking change 로 선언하고 `config.py` 전면 수정을 §10.4 영향 목록에 추가.

---

### HIGH-R11-3: `vfs_refresh` 실패 시 `VaultSyncRetryable` 은 race window 차단이 실패한 채 사이클이 계속될 수 있음 — ADR-0026 의 핵심 가정 위반

**위치**: §10.4.6 (line 1378–1394), §10.4.3 사이클 흐름 step 2

**현행**: `vfs_refresh` 실패 시 `VaultSyncRetryable` 로 raise. docstring — "다음 사이클 재시도".

**문제**: `VaultSyncRetryable` 의 처리가 per-file 루프 내에서는 `enqueue_retry + continue` 이지만, 사이클 시작 직후의 `vfs_refresh` 실패 시 호출자 (`vault-fetch.py`) 가 이것을 exit 75 (사이클 중단) 로 처리하는지, 아니면 계속하는지 §10.4.3 의 사이클 흐름 spec 에 명시되지 않았다. ADR-0026 K1 의 채택 이유가 "race window 차단" 이므로, refresh 실패 시 stale cache 상태로 gws changes → `_read_from_mount` 로 진행하면 ADR-0026 의 보장이 사라진다.

**제안**: §10.4.3 의 사이클 흐름 step 2 에 "vfs_refresh 실패 → exit 75 사이클 중단 (race window 차단 실패 시 오염된 read 허용 안 함)" 을 명시. `vfs_refresh` 의 `VaultSyncRetryable` 은 적절하지만 호출자가 이를 사이클 전체 abort 로 처리하는 책임을 명시해야 한다.

---

### HIGH-R11-4: ADR-0021 "본문 minor 갱신" 이 mount permanently failed 라는 신규 fail mode 를 커버하지 못함

**위치**: §10.1 (line 1090), §10.4.7 (line 1424–1426), §10.7 (line 1466)

**현행**: §10.1 — "§3.4 [D] reboot resilience (ADR-0021): mount.service 의존 추가 — 본문 minor 갱신 (supersede 아님)". ADR-0021 의 V12 fail 시 fallback 절차는 D2 (system-level + service user) 회귀만 다룬다.

**문제**: v7 에서 mount@ 가 StartLimitBurst=5 를 초과해서 permanently failed 되면 timer 가 계속 fire 하지만 vault@ 는 계속 실패 → ADR-0021 의 acceptance invariant ("OS reboot 후 사람 개입 없이 sync 사이클 자동 재기동") 이 깨진다. 이 fail mode 가 ADR-0021 에 없고 §10.7 의 minor 갱신 항목에도 없다. ADR-0021 의 Consequences 와 fallback 절차는 mount 의존이 없는 전제로 작성됐다.

CLAUDE.md §7 — "결정 변경 시 기존 ADR Status 를 Superseded 로 바꾸고 신규 ADR". mount 의존 추가가 reboot resilience 의 fail mode 를 추가한다면 이는 ADR 의 핵심 Consequences 변경이다.

**제안**: §10.5 미결에 "Q5: mount@ permanently failed 케이스에서 ADR-0021 의 acceptance invariant 어떻게 복구하는가" 를 추가하고, §10.7 에 ADR-0021 에 대한 addendum ADR 발의 여부를 결정 항목으로 명시. 최소한 mount@ StartLimitBurst 초과 시 운영자 복구 절차를 ADR-0021 본문 갱신에 포함시켜야 한다.

---

## MED

### MED-R11-1: `{rc_port_for_%i}` 치환변수의 yaml 바인딩 방법이 spec 에 없음

**위치**: §10.4.1 (line 1208), §10.4.4 (line 1314, 1325), §10.4.7 (line 1417)

**현행**: `mount@.service` 의 `--rc-addr 127.0.0.1:{rc_port_for_%i}` 와 `vault@.service` 의 `RCLONE_RC_ADDR=127.0.0.1:{rc_port_for_%i}` 에서 `{rc_port_for_%i}` 치환변수 사용. yaml 에는 `rclone_rc_port: 5572` 가 per-vault 옵션.

**문제**: ADR-0019 (Python substitution) 는 `{vault_id}` 기반 치환을 정의하지만, `{rc_port_for_%i}` 는 systemd 런타임 대입 `%i` 와 Python 대입 `{...}` 가 혼재한다. Python helper 가 template 을 instantiate 할 때 `{rc_port_for_%i}` 를 key 로 처리하면 실제로는 `{rc_port_for_gdrive}` 를 lookup 해야 한다. 이 key 가 yaml 의 어느 경로에서 어떻게 결정되는지 spec 이 없다.

**제안**: §10.4.4 의 치환변수 목록에 `{rc_port_for_<vault_id>}` (예: `{rc_port_for_gdrive}`) 가 `wikihub.yaml.vaults.<vault_id>.options.rclone_rc_port` 에서 읽힌다는 것을 명시. ADR-0019 의 substitution 패턴과의 정합성 검토 결과도 포함.

---

### MED-R11-2: `_resolve_mount_path()` 신규 함수의 spec 이 한 줄 언급뿐 — flat 가정 vs 폴더 계층 불일치 위험

**위치**: §10.4.3 (line 1286–1287)

**현행**: "mount path 계산: gws changes 응답의 `parents` + `name` → `<instance_root>/vault/<vault_id>/<full_path>`. helper `_resolve_mount_path(change_record, vault_cfg)` 신규" 한 줄.

**문제**: `parents` 는 Drive folder ID 목록이며, mount 경로를 계산하려면 ID → 폴더 이름 매핑이 필요하다. v0.1.0 이 flat 구조 (Drive 'name' 만 사용) 라고 해도, mount FS 는 Drive 폴더 계층대로 경로를 만들 수 있다. `_resolve_mount_path` 가 `vault_mount / file_name` 만 반환하는 flat 계산이라면 폴더 하위에 있는 파일은 경로 불일치로 읽기 실패.

**제안**: §10.4.3 에 `_resolve_mount_path` 의 v0.1.0 spec 을 명시. 입력: change_record. 반환: `vault_cfg.mount_path / change_record["file"]["name"]` (flat, v0.1.0). 제약: Drive 폴더 계층이 있는 경우 mount 경로 불일치 위험 → V13 검증 케이스에 폴더 포함 파일 추가.

---

### MED-R11-3: ADR-0027 이 ADR-0006 (unified orchestration) 과의 관계를 명문화하지 않음

**위치**: §10.7 (line 1463–1464)

**현행**: ADR-0027 spec — "ADR-0014 supersede 없음" 만 명시. ADR-0006 과의 관계 없음.

**문제**: `rclone_vs_gws_comparison.md` §5 의 ADR cascade 표는 "ADR-0006: 영향 없음" 이라고 하지만 ADR-0027 spec 자체에 이 관계가 빠져 있다. v7 에서 `vault-fetch.py` 내부에 `rclone rc vfs/refresh` subprocess + mount FS open 이 추가되어 외부 의존성이 늘어나지만 ADR-0006 의 외부 인터페이스는 변경 없다는 것이 v7 의 주장 — 이것이 ADR-0027 에 명시되어야 한다.

**제안**: §10.7 의 ADR-0027 spec 에 `Cross-references: ADR-0006 (unified orchestration) — vault-fetch.py 외부 인터페이스 무변경, subprocess 패턴 확장. ADR-0006 supersede 없음` 을 추가.

---

## LOW

### LOW-R11-1: V15 의 "Drive 수정 직후 5s 내 사이클 trigger" 가 timing-dependent flaky 조건

**위치**: §10.6.2 V15 (line 1447–1451), plan.md v2 V15 (line 103)

**현행**: V15 성공 기준 — "Drive 에서 파일 X 의 content 수정 직후 5s 내 사이클 trigger → mount read content 가 새 content"

**문제**: "5s 내" 는 Drive API propagation latency, vfs/refresh 응답 시간, OCI 서버 부하에 의존한다. 환경에 따라 pass/fail 이 달라지는 flaky 조건이다.

**제안**: V15 의 성공 기준을 "vfs/refresh API 응답 완료 후 첫 read 가 fresh content" 로 변경. 결정론적 기준 ("refresh 완료 이후") 이 시간 기준보다 재현 가능하다.

---

### LOW-R11-2: mount@ 에 `OnFailure` 미설정 — StartLimitBurst 초과 시 통지 지연이 최대 sync_interval (10분)

**위치**: §10.4.1 (line 1219)

**현행**: "StartLimitBurst=5 로 5회/5min 초과 시 fail. OnFailure 미설정 — vault@ 측에서 ops-alert 발화"

**문제**: mount@ 가 permanently failed 된 시점과 다음 vault@ fire 사이에 최대 10분 gap 이 있다. mount@ 에 `OnFailure` 를 추가하면 즉각 통지 가능. 현재 spec 은 이 선택을 명시적 trade-off 로 기록하지 않았다.

**제안**: spec 에 이 trade-off 를 명시 (`mount@ OnFailure 미설정 = 최대 sync_interval 지연 통지, 의도된 trade-off`) 하거나, mount@ 에도 `OnFailure=ops-alert.service` 추가를 검토.

---

## NIT

### NIT-R11-1: `wikihub-vault@.service.template` vs `vault-ingest.service.template` 파일명 불일치

**위치**: §10.4.7 (line 1401), v6 §4.2 (line 702)

**현행**: §10.4.7 본문 — "v6 §4.2 의 `vault-ingest.service.template` 에 patch". 헤더 — "`wikihub-vault@.service.template` patch". v6 §4.2 파일명은 `vault-ingest.service.template` (instantiated @ 없음).

**문제**: v6 파일을 rename 해서 @ 패턴으로 전환한 것인지, 신규 파일인지 명확하지 않다. ADR-0019 B2 (Python substitution) 와의 관계도 불명확.

**제안**: §10.4.7 에 "v6 의 `vault-ingest.service.template` 을 `wikihub-vault@.service.template` 으로 rename (이유: instantiated template 패턴 명시)" 또는 "신규 파일 추가, v6 파일 폐기" 중 어느 것인지 명시.

---

## 결론

### 결함 우선순위 및 처리 절차 권고

CRIT-R11-3 은 v6 `sync.py` 가 그대로 재사용될 경우 Drive 원본 파일 삭제 위험으로 **데이터 손실 직결**이다. CRIT-R11-1 은 Google native export 경로가 미정인 채 구현에 진입하면 **구현 범위 자체가 미확정**이다. CRIT-R11-2 는 reboot 직후 race 로 **V12 acceptance invariant 를 spec 결함으로 위협**한다. HIGH-R11-2 는 yaml 구조 불일치로 config.py 파싱 로직이 불확정이다.

처리 순서:
1. CRIT-R11-3 — `_handle_removed` 의 vault_local_path unlink 제거를 §10.4.3 에 명시
2. CRIT-R11-1 — Q1 처리 sequencing (V15a PoC first) 을 §10.5 에 명시
3. HIGH-R11-2 — yaml 구조 (list vs map) 불일치 수정
4. CRIT-R11-2 — `assert_mount_alive` 실패 시 exit 75 처리 (또는 mount 준비 완료 신호 메커니즘) 를 §10.4.7 에 명시
5. HIGH-R11-3 — `vfs_refresh` 실패 시 사이클 abort 를 §10.4.3 step 2 에 명시
6. HIGH-R11-4 — ADR-0021 minor 갱신 범위에 mount permanently failed fail mode 추가
7. HIGH-R11-1, MED, LOW, NIT — Step 3 전 또는 Step 3 초반 처리

### v7 approval 가능 여부

**현 상태에서 approval 불가.**

CRIT-R11-3 은 spec 이 현재 상태로 Step 3 에 진입하면 데이터 손실 경로가 열린다. CRIT-R11-1 은 Google native export 분기 구조가 미결인 채 구현이 불확정이다. CRIT-R11-2 는 V12 acceptance 를 위협하는 설계 결함이다.

**CRIT-R11-1·R11-2·R11-3 + HIGH-R11-2·R11-3 처리 후 approval 가능 조건**: 해당 5건은 모두 §10 내 텍스트 수정으로 처리 가능하다. HIGH-R11-4 (ADR-0021 minor 갱신 범위) 는 사용자가 "minor 갱신으로 충분하다 + mount permanently failed 케이스를 §10.5 Q5 로 추가한다" 고 명시하면 Step 3 V12 검증으로 위임 가능 — 이 경우 HIGH-R11-4 는 approval blocking 이 아니다.

---

관련 파일:
- `/Users/1004790/workspace/wikihub/features/20260514_install_runtime/analysis_and_design.md`
- `/Users/1004790/workspace/wikihub/features/20260514_install_runtime/rclone_vs_gws_comparison.md`
- `/Users/1004790/workspace/wikihub/features/20260514_install_runtime/plan.md`
- `/Users/1004790/workspace/wikihub/scripts/lib/sync.py`
- `/Users/1004790/workspace/wikihub/docs/adr/0021-reboot-resilience-user-systemd-linger.md`
- `/Users/1004790/workspace/wikihub/docs/adr/0014-drive-access-mechanism-revisited.md`
- `/Users/1004790/workspace/wikihub/docs/adr/0006-ingest-orchestration-model.md`
