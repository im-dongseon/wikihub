# F4 install_runtime — Analysis & Design

- **feat_id**: `install_runtime`
- **연계 plan**: `plan.md` v2 (2026-05-15)
- **버전**: v9
- **상태**: v6 approved 2026-05-14 — **v9 approved 2026-05-15** (Step 2 v9 사용자 검토 완료 — R11·R12·R13·R14 결함 47건 lock 처리, ADR-0024 writer 확장 옵션 c 채택, Step 3 v9 진입)

## Revision Log

| Version | Date | 변경 요지 |
|---|---|---|
| v1 | 2026-05-14 | 초안. 결정 7건 (A·B·C·D·E·F·G) + 산출물 spec + V<N> verification 7건 + 신규 ADR 5건 발의 (0015·0017·0021·0022 + ADR-0018 보류 결정) |
| v2 | 2026-05-14 | v1 surface 미흡 결함 6건 lock — (1) V8 starting fact hand-check 결과 반영 (gws = `googleworkspace/cli` GitHub 정식 CLI, install 방법 3개 surface), (2) install.sh Step 1 에 `EUID != 0` assert + sudo pre-check 추가, (3) ADR-0019 의 substitution 엔진을 Python helper 로 일원화 lock, (4) ADR-0019 본문에 instantiated template 재검토 트리거 (vault 5개 도달 또는 sync_interval 통일 운영 시) 명시, (5) ADR-0021 의 V12 fail mode 별 fallback lock (D2 회귀 시 ADR supersede 절차), (6) install.sh Step 8 안내 + README 의 3-경로 (repo · venv · instance.root) ASCII 도식 의무화 |
| v3 | 2026-05-14 | install.sh **호출 모델** 결함 (u7) — v2 까지의 가정 ("메인테이너가 repo clone 후 ./install.sh") 이 사용자 의도와 어긋남. 실제 = curl-pipe 한 줄 설치 (`curl -fsSL <URL>/install.sh \| bash`). install.sh 자체가 git clone 책임 + tag `latest` 추적. stdin 실행 영향 (prompt 는 `/dev/tty` 분기) + hosting URL 결정 — ADR-0023 발의. §4.1 install.sh spec 전면 재작성 (Step 0 신설, Step 2 갱신, Step 8 안내 갱신). ADR 총 8건 |
| v4 | 2026-05-14 | Step 2 design review (R5 feature-dev:code-reviewer + R6 general-purpose SRE) 결과 CRIT 7건 + HIGH 일부 lock. **R6 의 핵심 통찰** — v3 §4.2 systemd unit template 이 F1 archive §4.8.2 정본 spec 을 incomplete lift. **F1 surgical lift** 채용: service template 의 `Restart=on-failure + RestartSec + StartLimit*` 모두 제거 (oneshot 의 재시작은 timer 책임) → `SuccessExitStatus=0 75` 로 exit 75 success 분류 → CRIT-R6-1(exit 2 재시도)·CRIT-R6-2(StartLimit 후 stuck) 자연 해소. 추가 surgical lift: `OnUnitInactiveSec`(Active 아님), `OnBootSec=2min`(60s→2min), `TimeoutStartSec=15min`, `OnFailure=ops-alert.service`, `ops-alert.service` unit 정의 추가. CRIT 잔여: GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE 환경변수 추가 (ADR-0014 미이행 해소), Step 0 PIPE_MODE 감지 단순화 (무한 루프 방지), --update flag clean install alias 로 lock, {venv_path} 치환변수를 wikihub.yaml.example 에 등록, 첫 ingest 성공이 timer enable 전제로 ADR-0022 흐름 역전 (R6-3 fatal loop 차단). HIGH lock: §4.5 신설 (setup.md Step 6 spec 명문화), bootstrap_allowed 환원 책임 (/wh:setup yaml write), operations.gws_min_version yaml 등록, ADR-0023 본문에 supply chain 위협 모델 명시 (git clone --branch latest mutable tag + curl-pipe CDN cache). DoD §8 의 신규 ADR 표 5건 → 8건 갱신 |
| v5 | 2026-05-14 | Step 2 design review 2차 라운드 (R7 feature-dev:code-reviewer + R8 general-purpose SRE) — v4 의 fix-induced regression + 미해소 잔여 surface. **R8 의 핵심 finding**: v4 의 surgical lift 가 fatal loop 를 systemd 내부 → 알람 채널로 옮긴 것뿐 + last_failure.json producer 부재 + Hermes notify 이중 경로 미lift = **fatal 알림 채널 자체가 dead**. **신규 결정 [I] (ADR-0024 fatal 알림 contract)** — last_failure.json schema/writer/reader + dedup 정책 + Hermes notify 이중 경로 정본화. F4 산출물에 `scripts/vault-fetch.py` 수정 (fatal 시 last_failure.json 영속화) + `scripts/ops-alert.py` minimal spec (§4.6 신설) 추가. CRIT 추가 lock: §3.4 [D] 폐기된 spec 문구 교체 (NEW-1), setup.md 치환변수 목록 3건 등록 (NEW-2 — {venv_path}/{credentials_path}/{wikihub_home}), ops-alert 빈도 dedup 정책 (R8 CRIT-R8-2 = R7 NEW-7). HIGH lock: V10 검증 설명 교체 (NEW-4), exit 75 + cursor 미생성 분기 + V13 갱신 (NEW-5), §4.4 하위 번호 정리 (NEW-6), setup.md Step 4 enable 동작 변경 spec (NEW-8). ADR 9건, 결정 9건. |
| v9 | 2026-05-15 | **Step 2 v8 design review R13·R14 결함 20건 lock + 핵심 root cause (mount/vfs alert 정합성) 흡수.** R13 (feature-dev:code-reviewer) CRIT 2 + HIGH 2 + MED 3 + NIT 1 (8건). R14 (general-purpose SRE) CRIT 1 + HIGH 4 + MED 4 + LOW 2 + NIT 1 (12건). 공통 1건 (ls -la → stat). **blocking 8건 모두 §10 surgical patch 적용**. **architectural 추가 없음 — 옵션 c 채택**: mount alert 정합성 3건 (R14-CRIT-1 mount@ OnFailure dual-edge + R13-CRIT-1 vfs_refresh Q6 self-contradiction + R14-HIGH-4 Retryable + Requires silent abort) 를 ADR-0024 `last_failure` writer 확장으로 흡수 — `scripts/lib/state.py` 의 `save_last_failure` schema 에 `scope="mount"` 추가, `mount.py` 가 fatal 시 직접 호출. `mount-fail-recorder.service` 신규 unit 없음. ADR-0024 본문 minor 갱신 (mount scope) — supersede 아님. 핵심 변경: (1) §10.4.6 `assert_mount_alive` 의 `ls -la` → `stat` 교체 (R13-HIGH-2 + R14-HIGH-3, 메모리 폭발 차단). (2) §10.4.6 `vfs_refresh` 에 OAuth error 패턴 검사 + `VaultSyncFatal` (R13-CRIT-1 옵션 a). (3) §10.4.6 mount fatal escalation — `assert_mount_alive` 의 Retryable raise 가 N회 (default 6, 1시간) 누적 시 `VaultSyncFatal` + last_failure writer (R14-HIGH-4 + Q5 회귀 방지). (4) §10.4.2 `_yaml_get_vault_rc_ports` Python helper spec 추가 (R13-CRIT-2). (5) §10.4.2 GitHub Releases 가용성 fallback (3회 retry + 5min interval) (R14-HIGH-1). (6) §10.4.2 `ss -tlnH` user-namespace check 보강 (R14-HIGH-2). (7) §10.7 ADR-0025 Title 갱신 (R13-HIGH-1). (8) §10.4.4 substitution 2-pass 명시 (R13-MED-2). (9) §10.4.6 `retry_after_sec` 주석 + `import os` 제거 (R13-MED-1 + R13-NIT-1). (10) §10.8 DoD 에 V15-cost · V18 추가 (R13-MED-3). **새 미결 Q10 (R14 MED/LOW 흡수)**: vfs cache stale binary 정책 · gws schema runtime assert · V14/V15-cost 환경 가이드. **deferred to v0.2.x**: R14 NOTICE→DEBUG yaml override, vfs_refresh elapsed logging, V14 tc qdisc 환경, V15-cost 60s 임계 근거, patch 마커 normalize. ADR 12건 유지 (ADR-0024 본문 minor 갱신만, 신규 없음). Step 4 v9 code review R15·R16 대기. |
| v8 | 2026-05-15 | **Step 2 v7 design review R11·R12 결함 27건 lock.** R11 (feature-dev:code-reviewer) CRIT 3 + HIGH 4 + MED 3 + LOW 2 + NIT 1 (13건). R12 (general-purpose SRE) CRIT 2 + HIGH 5 + MED 4 + LOW 2 + NIT 1 (14건). 공통/중복 4건 (statvfs hung · mount sequencing race · mount silent dead · V15 timing). **blocking 11건 모두 §10 surgical patch 적용**. 핵심 변경: (1) §10.4.3 `_handle_removed` unlink 라인 제거 명시 — mount FS 위 unlink 가 Drive 원본 삭제 위험 차단 (R11-CRIT-3, 데이터 손실 직결). (2) §10.4.7 `assert_mount_alive` 실패 시 `VaultSyncRetryable` (exit 75) 처리로 reboot 직후 race ops-alert 오발화 차단 (R11-CRIT-2 + R12-HIGH-5). (3) §10.4.6 `assert_mount_alive` 를 `os.statvfs` → `subprocess.run(['ls','-la',...], timeout=5)` 교체 — hung FUSE block 차단 (R12-CRIT-2 + R11-HIGH-1). (4) §10.4.1 mount@.service 에 `OnFailure=ops-alert.service` 추가 + `--log-level NOTICE` token 노출 차단 (R12-CRIT-1 + R12-MED-3). (5) §10.4.2 install.sh 에 sha256 verify + rc port pre-check + rclone.conf chmod 0600 (R12-HIGH-3 + R12-MED-1 + R12-MED-2). (6) §10.4.3 step 2 에 `vfs_refresh` 실패 시 exit 75 사이클 abort 명시 (R11-HIGH-3, ADR-0026 가정 보장). (7) §10.4.3 `_resolve_mount_path` flat spec lock (v0.1.0 — `vault_mount / file_name`, 폴더 계층은 V13 검증) (R11-MED-2). (8) §10.4.4 yaml 을 v6 list 구조 (`- id: gdrive`) 로 정정 + `{rc_port_for_<vault_id>}` substitution binding 명시 + `rclone_max_version` (R11-HIGH-2 + R11-MED-1 + R12-LOW-2). (9) §10.4.5 setup.md 에 rclone.conf chmod 0600 명시. (10) §10.5 미결 Q5~Q9 추가 — Q5 mount permanently failed (R11-HIGH-4), Q6 rclone OAuth revoke (R12-HIGH-4), Q7 OCI free tier 디스크 (R12-HIGH-1), Q8 gws v0.x breaking (R12-MED-4), Q9 multi-vault 동시 부팅 (R12-LOW-1). (11) §10.6 V<N> 보강 — V14 hung mount 추가, V15 deterministic (vfs/refresh 응답 완료 후) + 비용 측정 (1k/10k 파일 케이스), V15 환경 명시 (R12-HIGH-2 + R11-LOW-1 + R12-NIT). (12) §10.7 ADR-0027 에 ADR-0006 cross-references 추가 (R11-MED-3). (13) §10.4.7 파일명 통일 — `wikihub-vault@.service.template` (R11-NIT-1). **deferred to v0.2.x**: R12-MED-4 (gws breaking 운영 매뉴얼), R12-LOW-1 (multi-vault contention 정밀화). ADR 12건 유지 (신규 없음 — 모든 결함이 spec patch 로 처리). Step 4 v8 code review R13·R14 대기. |
| v7 | 2026-05-15 | **Step 2 복귀 — Path C+ rclone mount 도입 architectural 보강.** v1~v6 본문 (§1~§9) 의 결정 [A]~[I] 모두 유지 (supersede 없음). 신규 결정 3건 추가: **[J] rclone mount 채택 — vault 자체 마운트** (ADR-0025), **[K] vfs refresh 정책 — 사이클 시작 시 recursive 1회** (ADR-0026, race window 차단), **[L] rclone vs gws 책임 분리 — Path C+ 정본** (ADR-0027). 결정 근거: 동일 디렉토리 `rclone_vs_gws_comparison.md` — rclone 은 Drive Changes API 를 backend command 로 노출하지 않음 (cursor 기반 변경 감지 부재), 따라서 변경 감지는 gws `drive changes list` 유지, mount 는 다운로드/실시간 UX 만 담당. 영향: `_system/systemd/wikihub-mount@.service.template` 신규, `scripts/lib/mount.py` 신규, `scripts/lib/sync.py` 다운로드 헬퍼 (`_download_to_vault`) → mount FS `open()` 으로 교체 (F3 sync.py 핵심 로직 ~90% 재사용), `install.sh` Step 5.5 (rclone install) 추가, `_system/commands/setup.md` Step 5.5 (rclone config) 추가, `wikihub-vault@.service.template` 에 `Requires=wikihub-mount@%i.service` 추가, `wikihub.yaml.example` 3 키 추가. ADR-0014 supersede 없음. v6 spec 의 변경 항목과 v7 신규 spec 은 모두 §10 (신설) 에 집약. v7 미결 4건 (Q1 Google native export 메커니즘 · Q2 rclone install 채널 · Q3 per-vault rc port · Q4 vfs_refresh fallback) Step 3 V<N> 으로 확정. V<N> 갱신: V12 mount.service 의존 추가, V13~V17 신규. ADR 12건 (v6 9건 + v7 3건). |
| v6 | 2026-05-14 | Step 4 code review 결과 R9 (feature-dev:code-reviewer) + R10 (general-purpose SRE) **총 29건** lock. **R9 = CRIT 2 + HIGH 5 + MED 3 + LOW 2 + NIT 1**, **R10 = CRIT 2 + HIGH 7 + MED 8 + LOW 3 + NIT 1**. 모든 CRIT/HIGH 처리 + MED 전건 + NIT 1 적용. **본 ver 에서 본문 결정 변경 없음** — 모든 fix 가 Step 3 구현 보강에 한정 (a&d v5 의 spec 은 그대로 정본). 적용 항목 요지: **(R10 CRIT-1)** `ops-alert.service` 에 `RemainAfterExit=no` + OnFailure 추가 금지 명문화. **(R10 CRIT-2)** 3개 service template 에 `ExecStartPre=/bin/mkdir -p {instance_root}` + setup.md Step 1 에 instance.root ensure 책임 명시. **(R10 HIGH-3)** `_LastFailureLock` context manager 신설 — `save_last_failure` + `mark_last_failure_alerted` 공유 lock 으로 lost-update race 차단. **(R10 MED-1)** install.sh 의 `_abs_path` 헬퍼 신설 (상대경로 + tilde literal normalize). **(R10 MED-3)** `wikihub.yaml.operations.instance_label` 추가 (webhook payload hostname leak 회피). **(R10 MED-4)** `--allow-non-ubuntu` flag + non-Ubuntu 환경 fail-fast (macOS dev box 의 `$HOME/wikihub` wipe 위험 차단). **(R10 MED-7)** install.sh 의 deps 파일을 `scripts/requirements.txt` 로 정합 (repo root requirements.txt 부재). **(R9 NIT)** `mark_alerted` 를 state.py 의 public helper `mark_last_failure_alerted` 로 추출 + ops-alert.py 의 private import 제거. ADR-0023 본문에 self-replace race window 운영 영향 명시 (R10 HIGH-4). 본 ver 까지 ADR 9건 유지 (신규 ADR 없음). 88 pytest 통과 + bash syntax OK. **deferred to v0.2.x**: R10 LOW-1 (`--require-shasum` opt-in), R10 LOW-2 (tar minimal image), R10 HIGH-2 의 영속 카운트 (운영 매뉴얼만 v0.1.0 lock). |

---

## 1. 배경 · 목적

F3 가 `scripts/vault-fetch.py` + `scripts/lib/*` 를 만들었지만 **OCI ARM Ubuntu 에서 자동으로 돌게 할 인프라**가 없다. 본 feature 는 그 인프라 (install.sh + systemd unit + wikihub.yaml.example + auth_gdrive.py) 를 한 묶음으로 만들고, 동시에 F3 가 잠정으로 남긴 ADR-0015 (gws version pinning) · ADR-0017 (gws stderr 패턴) 를 V<N> verification 으로 정본화한다.

**v0.1.0 의 acceptance invariant**: OS reboot 후 사람 개입 없이 sync 사이클이 자동 재기동. 본 invariant 가 모든 결정의 정렬 기준.

**호출 모델 (v3 lock)**: 운영자는 **한 줄 명령**으로 설치/업데이트한다 (rustup·nodejs 패턴):
```bash
curl -fsSL https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh | bash
```
install.sh 자체가 repo clone (또는 tarball 다운로드) + venv + gws + systemd + skill 등록 + linger 활성화 책임. tag `latest` 가 항상 최신 stable (메인테이너가 release 시 갱신). update 도 같은 명령 — install.sh 가 idempotent + git pull or re-fetch.

산출물 한 줄 요약:
- `install.sh` — repo root + curl-pipe 호출 가능. self-contained. OCI 서버 / dev box 어디서든 1회 명령으로 설치/업데이트
- `_system/systemd/` — unit template 정본 (single source of truth, F2 setup.md L24 lift)
- `wikihub.yaml.example` — F2 setup.md schema + F3 옵션 (root_folder_id·exclude_shared_with_me·max_file_size_mb·bootstrap_allowed) 모두 포함
- `scripts/auth_gdrive.py` — macOS dev box 용 1회성 OAuth 발급 (ADR-0003 정합, F3 미구현분)

---

## 2. 현행 진단

### 2.1 F1·F2·F3 가 이미 lock 한 사항 (변경 안 함)

| 항목 | 정본 위치 | F4 가 채워야 할 부분 |
|---|---|---|
| install.sh ↔ /wh:setup 책임 분할 | F2 `_system/commands/setup.md` §`install.sh와의 관계` + ADR-0010 | install.sh 의 실제 구현 (정본 fetch, OS deps, venv, gws, agent skill 초기 등록) |
| systemd unit 패턴 — Type=oneshot + timer | F1 archive §4.1 (Sequence diagram) | unit ini 의 정본 내용 (ExecStart·Type·Restart·timer interval) |
| systemd unit 이름 schema | F2 setup.md L48 — `{vault_id}-ingest.service`, `lint.service`, `ops-alert.service`, 조건부 `disk-watch.service` | 본 schema 의 구현 (vault 별 별도 파일 vs instantiated template) → **결정 [B]** |
| OAuth 토큰 검증 | F2 setup.md Step 1 + ADR-0003 | install.sh 자체는 토큰 발급 안 함. auth_gdrive.py 가 dev box 책임 |
| state JSON schema | F2 setup.md L37 (cursor·file_map·retry 초기 형식) + ADR-0007 | wikihub.yaml.example 의 vault 옵션 표현이 setup Step 1 검증과 호환 |
| gws CLI 채택 | ADR-0014 | install.sh 의 gws 설치 방법·pinned 버전 — **결정 [F]** |
| agent invocation 형식 | ADR-0012 + setup.md §Step 2.x ExecStart 조립 규약 | 본 spec 의 systemd unit 내 ExecStart 정확 표기 |
| reboot resilience | 명시 정본 **없음** (F1 §4.1 “timer 가 lifecycle 책임” 정도) | 본 feature 가 정본화 → **결정 [D]** + ADR-0021 |

### 2.2 결함·공백 (현행 상태에서 보이는 것)

1. **deploy.sh 가 repo 에 없음**. CLAUDE.md §3 Step 5 가 `deploy.sh` 언급하지만 실제 파일은 부재. F4 가 deploy.sh 를 만들지 vs install.sh 가 흡수할지 — **결정 [A]** + ADR-0018
2. F1 archive 의 unit 이름은 `gdrive-sync.service` (legacy 명명), F2 setup.md 는 `{vault_id}-ingest.service` (현재 정본). F2 가 정본이지만 F1 잔재 표현이 docs/ADR 일부에 남아 있을 수 있음 — Step 2 후반에 grep 후 동기화 정리
3. **venv 위치** 가 어디 정해진 적 없음 — **결정 [C]** + ADR-0020
4. **첫 ingest UX** — install.sh / /wh:setup / 자동 어디서 trigger 할지 미정 — **결정 [E]** + ADR-0022
5. **gws stderr 패턴** 의 실제 형식 미실증. F3 archive 의 lib/errors.py 가 추정 regex 만 — V4 후 ADR-0017 정본화
6. **systemd unit 의 instantiate 패턴 미결** — F2 가 “{vault_id}-ingest.service” 라는 표현으로 substitution 결과 vs instantiated template 둘 다 가능 — **결정 [B]** + ADR-0019

### 2.3 v2 추가 surface — v1 미명시 결함 6건

| # | Severity | 항목 | 본 v2 반영 위치 |
|---|---|---|---|
| u1 | **CRIT** | gws 설치 방법 미실증 (V8). v1 의 install.sh draft 가 `pip install gws==...` 가설 — gws CLI 의 실제 배포 채널과 무관할 수 있음 | §3.6 [F] + §4.1 Step 4 — V8 hand-check 결과 (`googleworkspace/cli` GitHub 정식 CLI) 로 starting draft 재작성 |
| u2 | HIGH | install.sh 가 `sudo` 와 user 모드를 섞으면 file ownership drift (root 가 만든 venv 를 user systemd 가 access 못 함) | §4.1 Step 1 — `EUID != 0` assert 추가. 메인테이너가 `sudo ./install.sh` 호출하면 즉시 exit 1 + 안내 |
| u3 | HIGH | ADR-0019 [B2] 의 placeholder substitution 엔진 미결정 (envsubst / sed / Python helper 의 trade-off) | §3.2 [B] ADR-0019 본문 — Python helper 로 일원화 lock. F2 setup.md 의 Step 2 가 이 helper 구현 책임 |
| u4 | MED | [B2] 의 재검토 트리거 미명시 — vault 수 늘면 instantiated template (B1) 이 자연스러워지는 시점 | §3.2 [B] ADR-0019 본문 — vault ≥ 5 또는 모든 vault sync_interval 통일 시 B1 재검토 lock |
| u5 | MED | V12 (reboot resilience) 의 dev box 사전 검증 불가 — macOS 에는 systemd 없음. fail 시 fallback 절차 미정 | §6 V12 행 + §3.4 [D] ADR-0021 본문 — V12 fail 시 D2 (system-level + service user) 로 fallback. 새 ADR 발의 절차 명시 |
| u6 | LOW | venv (`~/.local/share/wikihub/venv`) · repo (`~/wikihub`) · instance.root (`~/wikihub-instance`) 의 3-경로 분리가 운영자에게 혼란 위험 | §4.1 Step 8 안내 + README 의 ASCII 도식 의무화 |
| **u7** | **CRIT** (v3 surface) | install.sh **호출 모델** 미명시 — v1/v2 가 "메인테이너가 repo clone 후 ./install.sh" 가정. 실제 사용자 의도 = curl-pipe (`curl -fsSL .../install.sh \| bash`). install.sh 자체가 git clone 책임 + stdin 실행 (prompt 의 `/dev/tty` 우회 필수) + hosting URL 결정 (raw.githubusercontent.com 또는 release asset) | §3.8 [H] 신설 + ADR-0023 발의 + §4.1 Step 0 신설 (curl-pipe entry detection) + Step 2 (repo clone) 전면 재작성 |

---

## 3. 결정 종합 (9건)

각 결정마다 옵션 + 근거 + 추천 + ADR 매핑.

### 3.1 [A] install.sh ↔ deploy.sh 역할 분리 (ADR-0018)

**옵션**:
- **A1**: install.sh 단일 — deploy.sh 만들지 않음. 메인테이너가 dev box 에서 `git push` → OCI 서버에서 `git pull && install.sh` 흐름 (CLAUDE.md §3 Step 5 “git push → 서버에서 git pull + `deploy.sh` 실행” 의 deploy.sh 역할을 install.sh 가 흡수).
- **A2**: deploy.sh 별도 — install.sh 는 1회 bootstrap, deploy.sh 는 update (rsync · 권한 갱신 · systemctl restart).
- **A3**: deploy.sh 만 — install.sh 없이 deploy.sh 가 OS deps 까지 모두 처리.

**근거**:
- v0.1.0 의 메인테이너는 1명, 운영 서버 1대. update 절차는 git pull + restart 수준이라 별도 스크립트 가치 낮음.
- F2 setup.md 가 “install.sh 가 1회 bootstrap + 정본 update” 명문화 (L23) — 즉 update 까지 install.sh 흡수 가정.
- deploy.sh 가 v0.1.0 에 부재한 것 자체가 “install.sh 단일” 의 암묵적 선택.

**추천**: **A1 (install.sh 단일)**.
- CLAUDE.md §3 Step 5 의 “deploy.sh” 표현은 v0.1.0 에서 “install.sh” 로 lift 해서 읽도록 CLAUDE.md 도 한 줄 갱신 (또는 ADR-0018 에 매핑 명시).

→ **ADR-0018** (Status: Accepted, A1 채택).

---

### 3.2 [B] systemd unit 의 instantiate 패턴 (ADR-0019)

**옵션**:
- **B1**: instantiated template — `_system/systemd/wikihub-vault@.service` + `wikihub-vault@.timer`. /wh:setup 이 `systemctl --user enable wikihub-vault@gdrive.timer`. 단일 template 파일, 다중 vault.
- **B2**: per-vault file substitution — `_system/systemd/vault.service.template` + `_system/systemd/vault.timer.template`. /wh:setup 이 placeholder 치환 → `~/.config/systemd/user/gdrive-ingest.service` 파일을 vault 마다 작성. F2 setup.md 의 현재 표현 그대로.

**근거**:
- B1 장점: systemd 표준 패턴. unit template 한 개 유지보수. vault 추가 시 `enable` 만 호출.
- B1 단점: ExecStart 의 `%i` substitution 으로 vault_id 만 instance 화 가능. interval·local_path·options 같은 vault-specific 값은 환경변수 또는 별도 conf file 필요.
- B2 장점: vault 마다 interval · ExecStart · 환경변수 자유. F1 archive 의 vault 별 분리 모델과 자연.
- B2 단점: 파일 수 증가. unit template 의 정본 (drift 검증) 책임이 /wh:setup 에 들어감.

**추천**: **B2 (per-vault file substitution)**.
- F2 setup.md 의 unit 이름 표현과 정합. interval 이 vault 별로 다르므로 timer 의 `OnUnitActiveSec` 도 vault 별 substitution.
- vault 수가 v0.1.0~v0.2.x 에서 5개 미만 예상 — 파일 수 부담 미미.
- 기타 단일 unit (lint·ops-alert·disk-watch) 도 일관되게 substitution.

**v2 추가 lock (u3)** — substitution 엔진:
- `envsubst` (POSIX coreutils): shell variable 만 지원. yaml 구조 못 읽음 → 비채택.
- `sed`: 정규식 escape 부담 (instance.root·agent.binary 의 path 에 공백·특수문자 가능) → 비채택.
- **Python helper (`scripts/lib/systemd_render.py` 또는 /wh:setup 자체 내장)**: yaml 직접 load + `string.Template` substitution → **채택**.
- vault_id 는 `^[a-z][a-z0-9_]*$` 강제로 안전. 나머지 substitution 변수 (`{instance_root}`, `{venv_path}`, `{agent_invocation}` 등) 도 Python 측에서 escape 검증.

**v2 추가 lock (u4)** — B1 (instantiated template) 재검토 트리거:
- vault 수 ≥ 5 또는 모든 vault 의 `sync_interval_sec` 통일 운영으로 수렴할 때.
- 또는 systemd journald 에서 instance 별 filter 가 운영 디버깅에 필요해질 때 (`journalctl --user-unit "wikihub-vault@*.service"`).
- 그 시점에 ADR-0019 supersede + 새 ADR 발의. 마이그레이션 시 기존 vault 의 unit 파일 cleanup 도 정본화 필요.

→ **ADR-0019** (Status: Accepted, B2 + Python substitution + 재검토 트리거 lock).

---

### 3.3 [C] Python venv 위치 (ADR-0020)

**옵션**:
- **C1**: `~/.local/share/wikihub/venv` (XDG_DATA_HOME 표준).
- **C2**: `/opt/wikihub/venv` (system-level path).
- **C3**: `~/wikihub/venv` (사용자 home 직속).

**근거**: 본 결정은 [D] (reboot resilience 전략) 와 결합.
- user-level systemd unit + linger 채택 시 (= [D1]): venv 도 user-level path 가 자연 — XDG 표준 C1 추천.
- system-level unit 채택 시 (= [D2]): /opt/wikihub 가 자연 — C2.

**추천**: **C1 (`~/.local/share/wikihub/venv`)** — [D1] 결정과 결합.
- 메인테이너 user (예: `dongseon` 또는 `ubuntu`) 의 home 안에 모든 wikihub state 격리.
- repo 자체는 `~/wikihub/` 또는 메인테이너 자유 (install.sh 는 호출된 위치 기준).

→ **ADR-0020** (Status: Accepted, C1 채택, [D1] 와 결합).

---

### 3.4 [D] reboot resilience 전략 (ADR-0021) — **v0.1.0 acceptance**

**옵션**:
- **D1**: user-level unit (`~/.config/systemd/user/`) + `loginctl enable-linger <user>` + timer `Persistent=true`. 메인테이너 user 가 로그아웃해도 unit 계속 동작. reboot 후 systemd가 user manager 자동 기동.
- **D2**: system-level unit (`/etc/systemd/system/`) + dedicated `wikihub` 서비스 user (`useradd --system wikihub`). reboot 후 자동 기동 — linger 불필요.
- **D3**: 메인테이너 user 직접 system-level unit (소유자 user 명시) — D2 의 lite 버전, 별도 user 안 만듦.

**근거**:
- **D1 장점**: F1·F2 정합 (둘 다 `systemctl --user` 명시). 권한 격리 자연. install.sh 가 root 권한 없이 동작 가능.
- **D1 단점**: linger 활성화 안 잊어야 함 (V12 가 catch). user 가 삭제되면 unit 도 꺼짐.
- **D2 장점**: linger 의존 없음. dedicated user 로 권한 격리 강함.
- **D2 단점**: `sudo useradd` 필요 → install.sh 가 sudo 권한 필요. credentials path 등 권한 모델 복잡. F1·F2 spec 갱신 폭 큼.
- **D3 장점**: 단순. install.sh sudo 1회.
- **D3 단점**: root unit 으로 user 권한 (credentials 600 등) 정합 깨질 위험.

**추천**: **D1 (user-level + linger + Persistent=true)**.
- F1·F2 정합 가장 적음.
- timer `Persistent=true` 로 reboot 중 놓친 fire 부팅 직후 catch up.
- **v5 fix (R7 NEW-1)**: service `Restart=` 미설정 (ADR-0021 v4 surgical lift — oneshot 의 재시도는 timer 가 책임. F1 §4.8.2 정합). exit 75 는 `SuccessExitStatus=0 75` 로 success 분류 + 다음 timer 사이클이 자연 재시도. exit 2 는 `OnFailure=ops-alert.service` + 다음 timer 도 재시도 (운영자 개입 전까지). v3 까지의 `Restart=on-failure + StartLimit*` 패턴은 F1 정본과 충돌이라 폐기 — §4.2 template 본문 참조.
- install.sh 가 `loginctl enable-linger $USER` 실행 — 단 한 번 sudo 필요 (linger 활성화는 root 권한). 이 sudo 비용은 D1 도 피할 수 없음.

**v2 추가 lock (u5)** — V12 fail mode 별 fallback:
- V12 가 fail 하는 시나리오: (i) linger 활성화는 됐는데 reboot 후 user manager 자동 기동 안 됨, (ii) timer fire 됐지만 service 가 시작 못 함, (iii) OCI 의 host migration 이 user session 끊으면서 linger 무효화.
- fallback 결정: V12 fail 시 **D2 (system-level unit + service user) 로 회귀**. 본 ADR-0021 의 Status 를 `Superseded` 로 변경 + 새 ADR (예: ADR-0023) 발의 — `Supersedes: ADR-0021` 명시.
- D2 마이그레이션 절차 lock: (a) `useradd --system wikihub` (sudo), (b) `/etc/systemd/system/` 으로 unit template 이전, (c) `wikihub.yaml` 의 instance.root 및 venv 위치를 service user home 으로 이전, (d) credentials 파일의 owner 변경, (e) install.sh / /wh:setup 의 권한 모델 갱신.
- V12 acceptance 환경: **OCI ARM Ubuntu 인스턴스에서만 검증 가능** (macOS dev box 는 systemd 부재). 메인테이너의 검증 인스턴스가 dev box 와 분리됨을 사전 명시.

→ **ADR-0021** (Status: Accepted, D1 채택 + V12 fallback 절차 lock). V12 가 회귀 방지.

---

### 3.5 [E] 첫 ingest 진입점 (ADR-0022)

**옵션**:
- **E1**: install.sh 마지막에 prompt. yaml 이 example 상태인 시점이라 의미 약함 — credentials 도 아직 배치 안 됨.
- **E2**: /wh:setup 마지막에 prompt. yaml 편집 + credentials scp 완료 후 호출되는 단계라 first ingest trigger 시점으로 자연. setup.md L107 의 “다음 권장 액션” 안내를 prompt 로 격상.
- **E3**: 둘 다 prompt — install.sh 는 “나중에 /wh:setup 호출하세요” 안내, /wh:setup 이 실제 prompt.
- **E4**: 자동 — /wh:setup 이 첫 ingest 까지 자동 trigger (bootstrap_allowed=true 시).

**근거**:
- 운영 흐름 (F2 setup.md 정합): install.sh → 메인테이너가 yaml 편집 + credentials scp → /wh:setup → 첫 ingest.
- E1 은 시점이 너무 이름. E4 는 사용자 통제 약화.
- E2 가 가장 자연 + bootstrap_allowed flag 의 사용 시점과 일치.
- E3 는 E2 + install.sh 의 안내 메시지 (mute 가능).

**추천**: **E3 (둘 다 — install.sh 는 안내, /wh:setup 마지막 step 이 실제 prompt)**.
- install.sh 출력 마지막에 “이제 wikihub.yaml 편집 + credentials 배치 후 `/wh:setup` 호출하세요” 안내 (prompt 아님).
- /wh:setup Step 5 (보고) 다음에 **Step 6 신설** — “첫 ingest 를 지금 실행할까요? [Y/n]”. `Y` 시 vault 별 `vault-fetch.py --vault <id> --bootstrap` 1회 실행 + stdout JSON 보고 + bootstrap_allowed 자동 false 환원.
- 비대화형 모드: `--run-first-ingest` flag (force Y), `--skip-first-ingest` (force N), 환경변수 `WIKIHUB_FIRST_INGEST=yes/no` (CI · ansible 친화).

**v4 변경 (CRIT-R6-3 — fatal loop 차단)** — 흐름 순서 역전:

v3 까지의 의도는 `/wh:setup --enable` 이 (1) yaml 검증 → (2) systemd unit 동기화 → (3) `enable --now` 로 timer 활성화 → (4) Step 6 첫 ingest prompt. 그러나 (3)→(4) 순서면 timer 가 이미 enable 상태에서 첫 ingest 가 fatal 시 60초 뒤 systemd 의 다음 timer fire 가 같은 fatal 반복 → 무한 fatal loop.

**v4 의 새 순서** (Step 6 가 timer enable 의 전제조건):
1. yaml 검증 + state 디렉토리 + agent skill 메타 갱신 (Step 1·3).
2. systemd unit 파일 *작성* + `daemon-reload` (Step 2·4 — unit 파일은 disk 에 있음. 그러나 **enable 안 함**).
3. Step 6 첫 ingest prompt — `Y` 응답 시 `vault-fetch.py --vault <id> --bootstrap` 직접 호출 (timer 우회). 결과가 exit 0 (또는 75 with changes) 인 vault 만 다음 단계 진입.
4. **첫 ingest 성공한 vault 만** `systemctl --user enable --now <vault_id>-ingest.timer` 호출. 실패한 vault 는 unit 파일은 남기되 timer enable 보류 — 운영자가 진단 후 수동 enable.
5. lint.timer / ops-alert.service 는 항상 enable (vault 와 무관).

**책임 분할**:
- install.sh 는 yaml 편집/credentials 흐름의 책임이 없으므로 첫 ingest 결정도 책임 없음. 단순 안내만.
- /wh:setup 은 yaml + credentials 검증 + systemd unit + agent skill 메타까지 정합 보장 → 그 위에서 첫 ingest trigger 가 의미 있음. + **timer enable 의 게이트 책임** (R6-3 해소).

**bootstrap_allowed 환원 책임 (R5 §2.8 해소)**:
- `/wh:setup` Step 6 의 vault-fetch.py 가 exit 0 으로 종료 → `/wh:setup` 의 yaml writer 가 해당 vault 의 `bootstrap_allowed: true` → `false` 로 환원 + `wikihub.yaml` atomic write.
- yaml write 는 `/wh:setup` 의 새 책임 (ADR-0009 의 setup 책임 확장). Step 3 구현 시 `lib/config.py` 에 yaml writer helper 추가 또는 `/wh:setup` 자체 안에서 처리.
- 환원이 안 되면 다음 사이클의 vault-fetch.py 가 또 bootstrap 모드로 진입 — F3 의 sync 가 bootstrap 가드로 fatal 발생 (cursor 있는데 bootstrap_allowed=true + --bootstrap flag 없으면 정상 incremental 모드). 즉 환원 누락이 fatal 은 아니지만 위생.

→ **ADR-0022** (Status: Accepted, E3 + v4 순서 역전). F2 `_system/commands/setup.md` 갱신 필요 (§4.5 참조). V13 검증 항목에 순서 + bootstrap_allowed 환원 포함.

---

### 3.6 [F] gws version pinning starting value + 설치 채널 (ADR-0015 starting)

**v2 의 V8 hand-check 결과 (CRIT u1 해소)**:
- gws CLI = `googleworkspace/cli` (GitHub 정식 — Google Workspace 팀 maintained).
- 배포 채널 3개 확인:
  1. **GitHub Releases 의 pre-built binary** (`tar.gz` + shasum, OS·arch 별) — ARM64 Ubuntu 지원.
  2. **npm**: `npm install -g @googleworkspace/cli` — Node.js 의존 추가.
  3. **curl-based installer**: `curl -LsSf https://github.com/googleworkspace/cli/releases/download/v<ver>/gws-installer.sh | sh` — official installer script.

**version pinning 옵션**:
- **F1**: latest stable (Step 3 V6 시점의 GitHub Releases latest tag).
- **F2**: 특정 minor lock.
- **F3**: pinning 안 함 — latest 추적.

**설치 채널 옵션**:
- **CH1**: curl installer script — 단순 + idempotent (이미 설치된 버전 같으면 skip 가능 wrapper).
- **CH2**: GitHub Releases binary 직접 다운로드 + verify (shasum) → `/usr/local/bin/gws` 또는 `~/.local/bin/gws` 로 배치.
- **CH3**: npm — Node.js 의존 추가 → 의존 트리 비대화 + 본 feature 가 만드는 venv 와 별개 의존 (Python venv 만으로 충분한 흐름과 어긋남).

**근거**:
- gws 가 alpha 단계 (ADR-0014 명시) → API breaking 가능. F3 (pinning 안 함) 위험 큼.
- F2 (특정 minor lock) 는 v0.1.0 에서는 과도. V6 verification 후 결정.
- CH3 (npm) 는 v0.1.0 의 의존 최소화 원칙에 반함 — 비채택.
- CH1 (installer script) 는 빠르지만 third-party 신뢰. CH2 (직접 binary + shasum) 가 가장 안전 + idempotent.

**추천**:
- **version**: **F1 (V6 시점의 latest stable)**.
- **설치 채널**: **CH2 (GitHub Releases binary + shasum verify, `~/.local/bin/gws` 배치)** — user-level path 채택 ([C1] 정합).
- install.sh 가 `GWS_VERSION=<value>` env (default = `latest` → install.sh 가 GitHub API 로 latest tag 조회) 로 메인테이너 override 가능.

→ **ADR-0015** (Status: Proposed at Step 2, Accepted at Step 3 V6 후 — 정확한 버전 + 채택 채널 lock).

---

### 3.7 [G] gws stderr 패턴 starting regex (ADR-0017 starting)

**옵션**:
- **G1**: F3 archive 의 lib/errors.py 의 `GWS_API_ERROR_PATTERNS` 그대로 starting.
- **G2**: 비활성 (모두 fatal) — V4 결과 후 한 번에 정의.

**근거**:
- G1 의 매핑이 추정 regex 이지만 v0.1.0 의 starting safety 보장 (5xx·timeout retryable, 4xx fatal 분류) — 무작위 fatal 보다 안전.
- V4 결과는 starting 의 refine 만.

**추천**: **G1 (F3 archive 의 regex 그대로 starting)**.
- ADR-0017 의 starting status = `Proposed` (F3 가 잠정 발의), V4 후 정확한 매핑 표로 `Accepted`.
- F3 의 CRIT-R4-3 fix (scope 컬럼) 도 ADR-0017 본문에 포함되어야 함.

→ **ADR-0017** (Status: Proposed at Step 2, Accepted at Step 3 V4 후).

---

### 3.8 [H] install.sh 배포·호출 모델 (ADR-0023) — **v3 신규**

**옵션**:
- **H1**: curl-pipe (`curl -fsSL <URL>/install.sh | bash`). install.sh 가 raw GitHub URL 로 호스팅. install.sh 자체가 repo clone 책임. tag `latest` 가 최신 stable 추적.
- **H2**: 메인테이너 사전 clone (`git clone … && cd wikihub && ./install.sh`). install.sh 는 repo 안에 위치한 후 호출.
- **H3**: 별도 release artifact (tarball/installer binary) 다운로드 → 실행. GitHub Releases 의 `gws-installer.sh` 스타일.

**근거**:
- 사용자가 ASCII 도식 명령으로 명시 (`curl -fsSL URL/install | bash`) — H1 의도.
- rustup·nodejs·ohmyzsh 등 표준 OSS 설치 UX = H1.
- H1 의 단점: stdin 실행이라 대화형 prompt 가 `bash <(curl …)` 패턴에서 깨짐 → `/dev/tty` 분기 필요. 또한 raw URL 의 git pull 보안 (TLS · checksum) 신뢰가 GitHub 신뢰에 종속.
- H2 의 장점: 사전 inspection 가능. 단점: 운영자 step 수 증가 (clone → cd → install). 사용자 의도와 어긋남.
- H3 의 단점: release 마다 installer artifact 별도 build 필요. CI 비용. 가치 낮음.

**추천**: **H1 (curl-pipe)**.
- hosting URL: `https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh`.
- tag `latest` 가 항상 최신 stable 가리킴 — 메인테이너가 release 시 `git tag -f latest && git push --force origin latest`.
- install.sh 가 진입 직후 **execution context 감지** — `bash -c 'echo $0'` 또는 `[ -p /dev/stdin ]` 으로 curl-pipe 인지 local invocation 인지 판별 (모드별 동작 분기).
- 대화형 prompt 는 모두 `/dev/tty` 로 redirect (예: `read -r answer < /dev/tty`) — stdin 이 curl pipe 라도 사용자 응답 받음.
- 비대화 모드 (`WIKIHUB_NONINTERACTIVE=1` env 또는 `--skip-confirm` flag) 일 때만 prompt skip.
- **repo clone 정책 — clean install pattern (사용자 결정 lock)**: install.sh 가 `~/wikihub` 에 `git clone --branch latest --depth 1 https://github.com/im-dongseon/wikihub.git`. 기존 디렉토리 있으면 **`rm -rf` 후 재 clone**. git fetch / reset / pull 패턴 채택 안 함.
  - **장점**: idempotency 가장 단순. update 마다 깨끗한 상태 (변형 파일·orphan branch·detached HEAD 모두 회피). 운영 state 는 별도 경로 (`~/wikihub-instance`) 라 영향 없음.
  - **safety guard 필수** (rm -rf 위험 완화):
    1. `WIKIHUB_HOME` 가 시스템 path (`/`, `/usr`, `/etc`, `/opt`, `/home`, `$HOME` 자체, 빈 문자열) 면 즉시 exit 1.
    2. 기존 디렉토리가 있어도 **`.git` 서브디렉토리 존재만 wipe 허용** — wikihub repo 가 아닌 디렉토리는 wipe 거부 + 명시 안내.
    3. dev box 보호: 메인테이너가 자기 작업 디렉토리를 `WIKIHUB_HOME` 으로 잘못 지정한 케이스 — `.git` 존재해도 `origin` remote 가 `im-dongseon/wikihub.git` 인지 검증 후에만 wipe.
- self-update: install.sh 가 clone 후 **자기 자신을 새 위치의 install.sh 로 재실행** (`exec ~/wikihub/install.sh "$@"`) — 다음 단계는 repo 안의 정본 install.sh 가 진행. raw URL 의 install.sh 는 부트스트랩 책임만.

**보안 고려 (v4 R5 §2.9 + R6 lock — 위협 모델 명문화)**:

| 위협 | 영향 | v0.1.0 mitigation | v0.2.x 로 미루는 것 |
|---|---|---|---|
| **TLS MITM** | curl 응답·git clone 조작 | `--proto '=https' --tlsv1.2` 강제 + 시스템 CA 신뢰 | (없음 — TLS 만으로 충분) |
| **GitHub 계정 탈취** (메인테이너 GitHub 자격증명) | mass compromise — install.sh + tag `latest` 모두 attacker 통제. 다음 install 호출 시 자동 malicious clean install | **mitigation 없음**. 메인테이너 GitHub 의 2FA + 권한 최소화에 의존 | signed commit + GPG tag verification |
| **CDN cache stale** | `raw.githubusercontent.com` 의 CDN cache 로 메인테이너가 `latest` 갱신 후에도 운영자가 구버전 install.sh 받을 가능성 | GitHub raw 의 CDN TTL 은 ~5분 — v0.1.0 acceptable (운영자가 5분 후 재시도 안내) | mirror 또는 versioned URL |
| **mutable tag race** | `git clone --branch latest --depth 1` 가 mutable tag 를 한 번에 fetch — 직후 메인테이너가 force-push 하면 운영자는 직전 tag 의 commit 받음. 보안 결함 아님 (직전이 정상) 이지만 "어느 latest" 인지 비결정적 | `gws --version` 표시 + ADR-0015 의 yaml `gws_min_version` 으로 cross-check | tag 의 commit SHA fingerprint 보고 |
| **공급망 (gws binary)** | gws GitHub Releases 의 binary 가 변조 가능 | `gws-installer.sh.sha256` 또는 GitHub Release 자체의 shasum 검증 (Step 4) | GPG sig + reproducible build |

본 표는 ADR-0023 본문의 정본. v0.1.0 의 보안 모델은 **메인테이너 GitHub 계정 보안 + TLS + shasum (gws)** 의 3중. v0.2.x 에서 signed commit/tag · CodeSign · reproducible build 추가 계획.

→ **ADR-0023** (Status: Accepted, H1 채택). 본 결정 시 ADR-0018 (install.sh 단일 모델) 본문 보강 — “호출은 ADR-0023” 명시.

---

### 3.9 [I] fatal 알림 contract (ADR-0024) — **v5 신규**

**배경 (R8 finding)**: v4 의 surgical lift 가 `Restart=on-failure` 제거로 systemd 내부 fatal loop 는 해소했지만, fatal 알림 채널 자체가 **dead**.

증거:
- v4 §4.2 의 `OnFailure=ops-alert.service` 가 trigger 하는 `ops-alert.py` 의 **input `_state/<vault_id>/last_failure.json` producer 가 F3 코드에 부재**. F3 의 `scripts/vault-fetch.py` 와 `scripts/lib/*` 어디에도 last_failure 영속화 없음.
- F1 archive §4.6.6 의 **fatal 이중 경로** (Hermes 채널 `notify_on_fatal=true` + Hermes-독립 webhook `ops-alert.service`) 중 Hermes 채널이 v4 에 매핑 없음. F3 의 vault-fetch.py 도 Hermes 호출 안 함.
- v4 가 이 두 결함을 합치면 → fatal 발생 시 **알림 0건 도달** (systemd journal 만 남음).

**옵션**:
- **I1**: 알림 channel 전부 v0.2.x 로 미루기 (v0.1.0 은 journal 만). 운영자가 `journalctl --user -u "*-ingest.service"` 주기 점검.
- **I2**: ops-alert.service 만 작동 — last_failure.json producer 를 F4 가 vault-fetch.py 수정해서 추가 + ops-alert.py spec 명문화. Hermes 채널은 v0.2.x.
- **I3**: 이중 경로 둘 다 — last_failure.json producer + ops-alert.py + vault-fetch.py 가 fatal 시 Hermes notify 도 trigger.

**근거**:
- I1 은 v0.1.0 acceptance invariant (사람 개입 없는 자동 재기동) 와 충돌 — fatal 인지 못 하면 메인테이너 cursor·credentials 진단 시점 늦어짐.
- I3 는 시스템 복잡성 증가. Hermes 가 살아 있어야 통지 — Hermes 자체 fail 시 누락. 그래서 F1 이 이중 경로를 정본화한 것.
- I2 는 v0.1.0 minimum viable — webhook URL 미설정 시 no-op (조용히 journal 만), 설정 시 외부 webhook 통지. Hermes 채널 추가는 v0.2.x.

**추천**: **I2 (v0.1.0 minimum) + I3 마이그레이션 경로 lock**.

#### last_failure.json schema (state/<vault_id>/last_failure.json)

```json
{
  "vault_id": "gdrive",
  "exit_code": 2,
  "severity": "fatal",
  "scope": "vault",
  "reason": "401 invalid_grant: refresh_token revoked",
  "remediation": "auth_gdrive.py 재실행 + scp 재전송",
  "source_id": null,
  "first_failed_at": "2026-05-14T01:30:00+00:00",
  "last_failed_at": "2026-05-14T01:30:00+00:00",
  "failed_count": 1,
  "alerted_at": null
}
```

- `first_failed_at` — 첫 fatal 발생 시각 (이미 영속화돼 있으면 보존).
- `last_failed_at` — 매 fatal 발생 시 갱신.
- `failed_count` — 연속 fatal 카운트 (consecutive — success 1회로 리셋).
- `alerted_at` — ops-alert.py 가 webhook 발송 성공한 마지막 시각. **dedup 의 기준**.

#### writer 책임 — `scripts/vault-fetch.py` 수정 (F4 의 새 산출물)

vault-fetch.py 의 main exception 핸들러 (`VaultSyncFatal` catch 직후) 에 last_failure.json atomic write 추가. F3 의 `scripts/lib/state.py` 에 `save_last_failure()` helper 추가 — `_atomic_write_json` 패턴 (이미 fsync 포함 — F3 의 HIGH-R4-1 fix 정합).

```python
# scripts/lib/state.py 신규 함수 (F4 의 vault-fetch.py 수정과 함께)
def save_last_failure(state_dir: Path, payload: dict) -> None:
    """fatal 발생 시 영속화. ops-alert.service 의 input."""
    existing_path = state_dir / "last_failure.json"
    if existing_path.exists():
        existing = _read_json(existing_path)
        # 연속 fatal 누적 — alerted_at 보존, count 증가
        payload["first_failed_at"] = existing.get("first_failed_at", payload["first_failed_at"])
        payload["failed_count"] = int(existing.get("failed_count", 0)) + 1
        payload["alerted_at"] = existing.get("alerted_at")
    _atomic_write_json(existing_path, payload)


def clear_last_failure(state_dir: Path) -> None:
    """success 1회 시 호출 — 연속 fatal 카운트 리셋."""
    path = state_dir / "last_failure.json"
    path.unlink(missing_ok=True)
```

vault-fetch.py 의 흐름 갱신:
```python
# main() 의 except 블록
except VaultSyncFatal as e:
    save_last_failure(state_dir, {
        "vault_id": e.vault_id, "exit_code": 2, "severity": "fatal",
        "scope": "vault", "reason": e.reason, "remediation": e.remediation,
        "source_id": None,
        "first_failed_at": utc_now_iso(), "last_failed_at": utc_now_iso(),
        "failed_count": 1, "alerted_at": None,
    })
    return 2

# main() 의 success 분기 (sync() 가 정상 종료한 후)
clear_last_failure(state_dir)
return 0
```

`VaultSyncFileFatal` 도 별도 영속화 — 그러나 단일 파일 fatal 은 retry queue 가 더 적합하므로 last_failure.json 에는 기록 안 함 (F3 의 retry.json 이 정본 — ops-alert 가 retry.json 도 함께 수집).

#### reader 책임 — `ops-alert.service` 가 trigger 하는 `scripts/ops-alert.py`

본 spec 은 §4.6 에서 상세 (위 §4.6 신설 항목).

#### dedup 정책 (CRIT R8-R7 NEW-7 해소)

매 timer 사이클마다 fatal 반복 시 alarm fatigue 회피:

| 조건 | 동작 |
|---|---|
| `last_failure.json` 이 없음 | first fatal — webhook 즉시 발송 + alerted_at 기록 |
| `alerted_at` 가 null | first fatal 후 webhook 발송 실패 상태 — 즉시 재발송 시도 |
| `alerted_at` 기록 + `failed_count` 가 같음 | dedup hit — webhook 안 함 (journal 만) |
| `alerted_at` 기록 + `failed_count` 1 이상 증가 | resurfacing — webhook 발송 (operations 가 진단 안 한 상태라 alarm 의도) |
| `last_failed_at - alerted_at > 24h` | 매일 한 번 reminder — webhook 발송 |

**cool-down 윈도우**: dedup 의 기본은 "같은 fatal 이 연속 반복" 일 때 webhook 안 함. 운영자가 진단·수정 후 다음 사이클에 success → `clear_last_failure` 호출 → 다음 fatal 발생 시 다시 first fatal 로 인식.

#### Hermes 채널 — v0.2.x 마이그레이션 경로

ADR-0024 본문에 v0.2.x 의 진화 lock:
- F4 의 vault-fetch.py 수정에 `notify_via_hermes()` helper 추가 (현재는 no-op stub).
- v0.2.x 의 F5 (hermes_adapter) 가 `notify_on_fatal=true` 와 함께 Hermes Telegram 통지 활성화.
- ADR-0024 가 이 stub 책임을 v0.1.0 부터 lock — 단 함수 본문은 no-op (`logging.info("[STUB] notify_via_hermes called")`).

→ **ADR-0024** (Status: Accepted, I2 + I3 마이그레이션 경로 lock). F4 산출물에 vault-fetch.py 수정 + state.py helper + ops-alert.py 모두 포함.

---

## 4. 산출물 spec

### 4.1 `install.sh` — 호출 패턴 + CLI + 단계

**호출 패턴 (ADR-0023 [H1])**:
```bash
# 한 줄 설치 (운영 default)
curl -fsSL --proto '=https' --tlsv1.2 \
    https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh | bash

# 옵션 전달 (curl-pipe + arg)
curl -fsSL https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh | bash -s -- --skip-confirm

# 로컬 호출 (개발 또는 사전 inspection 후)
./install.sh [옵션]
```

**CLI**:
```
install.sh [--gws-version <ver>] [--skip-confirm] [--branch <ref>] [-h]
```

- `--gws-version`: gws pinned 버전 (default = `$GWS_VERSION` env, fallback = GitHub Releases latest).
- `--skip-confirm`: 모든 prompt 자동 Y (비대화 — CI/ansible). curl-pipe 모드에서 `/dev/tty` 미존재 시 자동 활성화.
- `--branch <ref>`: git checkout 대상 (default = `latest` tag). 메인테이너 또는 베타 테스트용.
- **v4 변경 (R5 §2.3)**: `--update` flag 제거. 모든 호출이 동일한 clean install pattern (`rm -rf ~/wikihub && git clone`) — update 와 신규 설치의 의미 구분 없음. 운영 state (`~/wikihub-instance`) 보존은 별도 경로라 영향 없음. 메인테이너 안내에서도 "동일 명령으로 재호출하면 latest 갱신" 으로 통일.
- 환경변수:
  - `WIKIHUB_FIRST_INGEST=yes/no` — 마지막 안내 단계 (실제 trigger 는 /wh:setup).
  - `WIKIHUB_NONINTERACTIVE=1` — `--skip-confirm` 동등.
  - `WIKIHUB_HOME` (default `~/wikihub`) — repo clone 위치 override.
  - `WIKIHUB_INSTANCE_ROOT` (default `~/wikihub-instance`) — 운영 state 위치 override.

**Step 0. 실행 컨텍스트 감지 + bootstrap (v4 — R5 §2.2 무한루프 방지)**

**v4 변경 (CRIT u8 — R5 §2.2)**: 감지를 env variable (`WIKIHUB_PIPE_MODE`) 에 의존하던 v3 패턴은 export 누락 시 새 process 가 다시 분기에 진입할 위험. v4 는 **`$BASH_SOURCE[0]` 단독** 으로 감지 — exec 후 새 process 의 `$BASH_SOURCE[0]` 가 file path 이므로 자연히 분기 미진입.

```bash
# 감지: $BASH_SOURCE[0] 가 file system 에 없으면 curl-pipe 모드.
# (bash <(curl ...) 또는 `curl ... | bash` 둘 다 BASH_SOURCE 가 빈 문자열 또는 /dev/stdin 가리킴)
if [ -z "${BASH_SOURCE[0]:-}" ] || [ ! -f "${BASH_SOURCE[0]}" ]; then
    # /dev/tty 가 사용 가능한지 (대화형 가능 여부)
    if [ ! -c /dev/tty ]; then
        export WIKIHUB_NONINTERACTIVE=1
        echo "INFO: /dev/tty 부재 → 비대화 모드 자동 활성화"
    fi

    # Step 2 의 git clone 을 먼저 수행 → 그 안의 install.sh 로 재실행
    # (raw URL 의 install.sh 는 bootstrap 책임만)
    bootstrap_clone_then_exec "$@"
    # bootstrap_clone_then_exec 가 'exec ~/wikihub/install.sh "$@"' 수행 — return 안 함.
    # 새 process 의 BASH_SOURCE[0]=~/wikihub/install.sh 는 file 이므로 본 분기 미진입.
fi
```

**무한 루프 방지 invariant**:
- 본 감지는 환경변수에 의존 안 함 → exec 가 어떤 env 도 inherit 해도 안전.
- safety: `bootstrap_clone_then_exec` 함수 내부에서 self-test (`[ -f "$WIKIHUB_HOME/install.sh" ]`) 후에만 exec — clone 실패 시 명시 에러.

**Step 1. 환경 검증** (fail-fast)
- **v2 추가 (u2)**: `EUID != 0` assert — 메인테이너가 `sudo ./install.sh` 호출하면 즉시 exit 1.
  ```bash
  if [ "$EUID" -eq 0 ]; then
      echo "ERROR: install.sh 는 일반 user 로 실행하세요. (현재 user: root)" >&2
      echo "       sudo 가 필요한 단계는 install.sh 내부에서 명시적으로 호출합니다." >&2
      exit 1
  fi
  ```
- **v2 추가 (u2)**: sudo pre-check — `--skip-confirm` 모드 시 silent hang 회피.
  ```bash
  if ! sudo -n true 2>/dev/null; then
      if [ -n "$SKIP_CONFIRM" ]; then
          echo "ERROR: --skip-confirm 모드인데 sudo 비대화 호출 실패. NOPASSWD 설정 필요." >&2
          exit 1
      fi
      echo "INFO: sudo 권한이 필요합니다 (linger 활성화 Step 7 에서 1회). 진행 시 password prompt 가 나타날 수 있습니다."
  fi
  ```
- OS 확인: `lsb_release -i` (Ubuntu 22.04+ / 24.04+ 만 v0.1.0 지원). 다른 OS 는 warning 후 계속 (V12 가 OCI 만 강제).
- arch 확인: `uname -m` (`aarch64` 가 default; `x86_64` 는 warning 후 계속).
- systemd 사용 가능 확인: `systemctl --user status` 가 응답.
- Python 3.11+ 또는 3.12+ 존재 확인. 없으면 `apt install python3-venv python3-pip`.

**Step 2. wikihub repo clean install (v3 — ADR-0023 lock, clean wipe + clone)**
```bash
WIKIHUB_HOME="${WIKIHUB_HOME:-$HOME/wikihub}"
BRANCH="${BRANCH:-latest}"  # ADR-0023: tag latest 가 정본
WIKIHUB_REPO_URL="https://github.com/im-dongseon/wikihub.git"

# ─── safety guard 1: WIKIHUB_HOME 이 시스템 path 면 즉시 거부 ───
case "$WIKIHUB_HOME" in
    ""|"/"|"/usr"|"/usr/local"|"/etc"|"/opt"|"/home"|"$HOME"|"$HOME/")
        echo "ERROR: WIKIHUB_HOME=$WIKIHUB_HOME 는 wipe 대상으로 안전하지 않음" >&2
        echo "       WIKIHUB_HOME env 로 다른 위치 지정 (default: ~/wikihub)" >&2
        exit 1
        ;;
esac
# 절대 경로로 normalize (relative path 의 함정 방지)
WIKIHUB_HOME="$(cd "$(dirname "$WIKIHUB_HOME")" 2>/dev/null && pwd)/$(basename "$WIKIHUB_HOME")" || true

# ─── 기존 디렉토리가 있으면 wikihub repo 인지 검증 후 wipe ───
if [ -e "$WIKIHUB_HOME" ]; then
    if [ ! -d "$WIKIHUB_HOME/.git" ]; then
        echo "ERROR: $WIKIHUB_HOME 가 존재하지만 git repo 가 아님." >&2
        echo "       wikihub 설치 위치가 아닐 가능성 — 수동 확인 후 재시도." >&2
        exit 1
    fi
    # safety guard 2: origin remote 가 wikihub 인지 검증 (dev box 작업 디렉토리 wipe 방지)
    existing_origin="$(cd "$WIKIHUB_HOME" && git config --get remote.origin.url 2>/dev/null || true)"
    case "$existing_origin" in
        *im-dongseon/wikihub*|*wikihub.git*)
            echo "INFO: 기존 wikihub repo 발견 → clean re-install 진행"
            ;;
        *)
            echo "ERROR: $WIKIHUB_HOME 의 origin=$existing_origin — wikihub repo 가 아님." >&2
            echo "       메인테이너의 작업 디렉토리를 잘못 지정했을 가능성. WIKIHUB_HOME 재확인." >&2
            exit 1
            ;;
    esac
    # safety guard 3: cwd 가 WIKIHUB_HOME 안이면 밖으로 이동 후 rm (busy 회피)
    [ "$(pwd)" = "$WIKIHUB_HOME" ] || [ "${PWD#"$WIKIHUB_HOME"/}" != "$PWD" ] && cd "$HOME"
    rm -rf "$WIKIHUB_HOME"
fi

# ─── 신규 clone (clean) ───
git clone --branch "$BRANCH" --depth 1 "$WIKIHUB_REPO_URL" "$WIKIHUB_HOME"
```

**동작 정리**:
- 매 install 호출이 **항상 새 clone** — `~/wikihub` 가 항상 latest tag 의 깨끗한 사본.
- update / re-install / 신규 설치가 모두 동일 흐름 — `--update` flag 의 의미 단순화 (현재는 안내 메시지에만 영향).
- `latest` tag 의 release 절차: 메인테이너가 stable commit 에서 `git tag -f latest && git push --force origin latest`.
- `--branch <ref>` 로 베타 (`main`) 또는 semver tag (`v0.1.0`) 사용 가능.

**손실되지 않는 것** (운영 state 는 별도 경로):
- `~/wikihub-instance/wikihub.yaml` · `.credentials/` · `_state/` · `vault-*/` · `wiki/` — 모두 wipe 영향 없음.
- `~/.local/share/wikihub/venv/` · `~/.local/bin/gws` — Step 3·4 가 idempotent 로 재확인.
- `~/.config/systemd/user/*.service` — /wh:setup 이 관리, install.sh 영향 없음.

**손실되는 것** (의도된 손실):
- `~/wikihub` 안의 메인테이너 수동 편집 — wikihub repo 는 read-only 정책 (CLAUDE.md). 손댄 적이 있으면 그것은 의도되지 않은 작업 → wipe 가 의도된 정책 적용.

**Step 3. venv 생성 (idempotent, v4 — R5 §2.1 lock)**
- 위치: `~/.local/share/wikihub/venv` (ADR-0020 [C1]).
- 존재 시: skip (`pip install -r requirements.txt --upgrade` 만 호출 — deps 갱신).
- 미존재 시: `python3 -m venv $VENV_PATH` + `pip install -r requirements.txt`.
- **v4 추가**: venv 경로를 `~/wikihub/.venv_path` 사이드카 파일에 기록 — `/wh:setup` 의 Python helper 가 systemd unit substitution 시 read.
  ```bash
  echo "$VENV_PATH" > "$WIKIHUB_HOME/.venv_path"
  ```
- `{venv_path}` 치환 변수는 `/wh:setup` 이 본 사이드카에서 read (wikihub.yaml 에 venv_path 키 추가 안 함 — yaml 은 운영자 편집 대상, install.sh 가 관리하는 path 는 분리).

**Step 4. gws 설치 (idempotent — v2 의 V8 hand-check 반영, CH2 채택)**
- 채택 채널: GitHub Releases 의 pre-built binary + shasum verify.
- 배치 위치: `~/.local/bin/gws` (PATH 에 포함됨을 install.sh 가 보장 — `~/.profile` 또는 `~/.bashrc` 확인 후 추가).
- starting draft:
  ```bash
  # 1. 버전 결정 (env 변수 override 가능)
  if [ -z "$GWS_VERSION" ] || [ "$GWS_VERSION" = "latest" ]; then
      GWS_VERSION=$(curl -fsSL https://api.github.com/repos/googleworkspace/cli/releases/latest \
          | grep '"tag_name"' | head -1 | sed -E 's/.*"v?([^"]+)".*/\1/')
  fi

  # 2. 이미 설치된 버전이면 skip
  if command -v gws &>/dev/null && gws --version 2>/dev/null | grep -q "$GWS_VERSION"; then
      echo "gws $GWS_VERSION already installed"
  else
      # 3. ARM64 binary 다운로드 + shasum verify + 배치
      ARCH=$(uname -m)
      OS=$(uname -s | tr '[:upper:]' '[:lower:]')
      ASSET="gws-${OS}-${ARCH}.tar.gz"  # V8 후속에서 정확한 asset 이름 확정
      URL="https://github.com/googleworkspace/cli/releases/download/v${GWS_VERSION}/${ASSET}"
      SUM_URL="${URL}.sha256"

      TMPDIR=$(mktemp -d)
      curl -fsSL "$URL"     -o "$TMPDIR/$ASSET"
      curl -fsSL "$SUM_URL" -o "$TMPDIR/$ASSET.sha256"

      ( cd "$TMPDIR" && shasum -a 256 -c "$ASSET.sha256" )
      tar -C "$TMPDIR" -xzf "$TMPDIR/$ASSET"
      install -m 0755 -D "$TMPDIR/gws" "$HOME/.local/bin/gws"
      rm -rf "$TMPDIR"
  fi

  # 4. PATH 확인
  if ! echo "$PATH" | tr ':' '\n' | grep -q "^$HOME/.local/bin\$"; then
      echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.profile"
      echo "INFO: ~/.profile 에 PATH 추가 — 새 shell 부터 적용"
  fi
  ```
- `gws --version` 확인 후 stdout 보고.
- **잔여 V8 사항**: GitHub Releases 의 정확한 ARM64 asset 이름 (예: `gws-linux-aarch64.tar.gz` vs `gws-linux-arm64.tar.gz` 표기 차이) — Step 3 진입 직전 hand-check.

**Step 5. wikihub.yaml.example → wikihub.yaml (없을 때만)**
- 위치: `$INSTANCE_ROOT/wikihub.yaml` (default `$INSTANCE_ROOT=~/wikihub-instance` 또는 yaml 안의 `instance.root`).
- 이미 존재 시 skip + “편집된 yaml 보존” 보고.

**Step 6. agent skill 초기 등록** (F2 setup.md §`install.sh와의 관계` 라인)
- `~/.claude/` 또는 agent 별 적합 위치에 wikihub skill 메타 작성.
- Hermes / codex / gemini 의 분기는 ADR-0012 매핑 따름.

**Step 7. linger 활성화 (D1)**
```bash
if ! loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=yes"; then
    if [ "$WIKIHUB_NONINTERACTIVE" = "1" ]; then
        sudo -n loginctl enable-linger "$USER"
    else
        # ADR-0023: curl-pipe 모드여도 sudo 는 /dev/tty 로 password prompt
        sudo loginctl enable-linger "$USER" < /dev/tty
    fi
fi
```
- sudo 필요. 비대화 모드면 `sudo -n` 으로 NOPASSWD 시도, 실패 시 명시적 안내. 대화 모드면 `/dev/tty` redirect 로 stdin 이 curl pipe 인 경우에도 password 입력 가능.

**Step 8. 안내** (E3 — 실제 trigger 는 /wh:setup. v2 의 u6 — 3-경로 도식 의무화)
```
wikihub 설치 완료. (curl-pipe 1줄 명령 또는 ./install.sh 모두 동일 결과)

[경로 구조]
  ~/wikihub/                            # repo (install.sh 가 git clone --branch latest)
  ~/.local/share/wikihub/venv/          # Python venv (install.sh 관리, 메인테이너 미관여)
  ~/.local/bin/gws                      # gws binary (install.sh 관리)
  ~/wikihub-instance/                   # 운영 state (instance.root) — 메인테이너 편집 대상
      ├── wikihub.yaml                  # 운영 정본 (편집 필수)
      ├── .credentials/                 # OAuth tokens (scp 배치 + chmod 600)
      ├── _state/<vault_id>/            # cursor·file_map·retry·last_sync (자동)
      ├── vault-<vault_id>/             # vault local mirror (자동)
      └── wiki/                         # 통합 wiki (자동)
  ~/.config/systemd/user/               # systemd unit (/wh:setup 관리)

다음 단계:
  1. ~/wikihub-instance/wikihub.yaml 편집 — vault 정의 + 옵션 채우기
  2. credentials 배치 — scripts/auth_gdrive.py (macOS dev box) 결과를 서버에 scp
     예: scp ~/wikihub-credentials/token_gdrive.json server:~/wikihub-instance/.credentials/
     배치 후: chmod 600 ~/wikihub-instance/.credentials/token_*.json
  3. /wh:setup 호출 — wikihub.yaml 검증 + systemd unit 동기화 + 첫 ingest prompt
     <agent_invocation> "/wh:setup --enable"

업데이트는 같은 명령 한 번 더:
  curl -fsSL https://raw.githubusercontent.com/im-dongseon/wikihub/latest/install.sh | bash

[update 동작 — clean install pattern (ADR-0023)]
  매 install 호출은 ~/wikihub 디렉토리를 wipe 후 latest tag 로 다시 clone.
  ~/wikihub-instance/ (운영 state) · ~/.local/share/wikihub/venv (venv) · systemd unit 은 영향 없음.
  ~/wikihub 안의 메인테이너 수동 편집은 손실됨 — repo 는 read-only 정책.
```

> 본 ASCII 도식은 README.md 의 install 절차 섹션에도 동일하게 포함 (u6 정합).

**exit code**:
- `0` 정상 종료.
- `1` 환경 결함 (Python 부재 등).
- `2` install 도중 결함 (venv 생성 실패 등).

---

### 4.2 `_system/systemd/` unit template (B2 — v4 의 F1 §4.8.2 surgical lift)

**v4 결정** (CRIT-R6-1·R6-2 해소): v3 의 `Restart=on-failure + RestartSec + StartLimit*` 패턴 전면 폐기. F1 archive §4.8.2 정본 lift — **oneshot 의 재시작 책임은 timer**. exit 75 는 `SuccessExitStatus` 로 success 분류 → 다음 timer 사이클에서 자연 재시도. exit 2 는 failure 로 분류 → `OnFailure=ops-alert.service` 가 ops-alert 경로 발동 + 다음 timer 사이클에서도 자연 재시도 (운영자 개입 전까지).

**파일 구조** (per-vault 별 substitution template):

`_system/systemd/vault-ingest.service.template`:
```ini
[Unit]
Description=WikiHub vault ingest — {vault_id}
After=network-online.target
Wants=network-online.target
OnFailure=ops-alert.service                # F1 §4.6.6 Hermes-독립 fatal 알림 경로

[Service]
Type=oneshot
WorkingDirectory={instance_root}
Environment=PATH={venv_path}/bin:/usr/bin:/bin
Environment=WIKIHUB_YAML={instance_root}/wikihub.yaml
Environment=GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE={credentials_path}   # ADR-0014 F4 책임
ExecStart={agent_invocation} "{skill_prefix}ingest --vault {vault_id}"
SuccessExitStatus=0 75                     # exit 75 (Retryable) 도 success 분류 — systemd 가 failure 로 기록 안 함
TimeoutStartSec=15min                      # F3 의 vault-fetch 자체 timeout 한도

# Restart= 미설정 (F1 §4.8.2 정본) — oneshot 의 재시도는 timer 가 책임.
# exit 75 는 다음 timer fire 에서 자연 재시도, exit 2 는 OnFailure 가 ops-alert 발동 + 다음 timer 도 시도.
# 운영자가 cursor·credentials 등 개입 전까지 fatal 사이클이 계속 반복될 수 있음 — ops-alert 가 통지 책임.
```

`_system/systemd/vault-ingest.timer.template`:
```ini
[Unit]
Description=WikiHub vault ingest timer — {vault_id}

[Timer]
Unit={vault_id}-ingest.service
OnBootSec=2min                             # F1 §4.8.2 lift (60s→2min — network-online + cloud-init settle 시간)
OnUnitInactiveSec={sync_interval_sec}s     # F1 §4.8.2 lift (Active→Inactive — timeout 회복 정합)
Persistent=true                            # reboot 중 놓친 fire 부팅 후 catch up. V12 acceptance
AccuracySec=1min                           # F1 §4.8.2 lift (전력 절감)

[Install]
WantedBy=timers.target
```

`_system/systemd/ops-alert.service` (Hermes-독립 fatal 알림 dispatcher — F1 §4.8.2 L1434 lift):
```ini
[Unit]
Description=WikiHub Hermes-independent fatal alert dispatcher

[Service]
Type=oneshot
WorkingDirectory={instance_root}
Environment=PATH={venv_path}/bin:/usr/bin:/bin
Environment=WIKIHUB_YAML={instance_root}/wikihub.yaml
ExecStart={venv_path}/bin/python {wikihub_home}/scripts/ops-alert.py
TimeoutStartSec=30s
```
- 트리거: 각 vault ingest service 의 `OnFailure=ops-alert.service`.
- 단독 활성화 안 함 — systemd 의 `OnFailure` 경로로만 호출. timer 없음. `[Install]` 없음.
- 스크립트 책임: `_state/*/last_failure.json` 수집 → `operations.fatal_webhook_url` POST. webhook 미설정 시 no-op.
- `scripts/ops-alert.py` 자체는 F4 산출물 (별도 §4.x 에서 spec — v0.1.0 minimal: webhook 또는 journal 기록만).

**핵심 결정 lock**:
- `Type=oneshot` — F1 archive §4.1 + §4.8.2 lock. systemd 가 overlap 방지 (`Type=oneshot` 의 active 상태는 service 종료까지 — 다음 timer fire 가 무시되어 race 없음).
- **`Restart=` 미설정** (v4 surgical lift) — F1 정본. v3 의 `Restart=on-failure + RestartSec=60s + StartLimitBurst=5` 는 잘못된 lift.
- `SuccessExitStatus=0 75` — exit 75 는 retryable 의도 → systemd 가 failure 로 기록 안 함 + journal 정상 항목으로 보존.
- exit 2 는 `OnFailure=ops-alert.service` 가 ops-alert 발동 + 다음 timer 사이클에서도 재시도. 운영자가 cursor·credentials 개입 전까지 사이클 반복. (이는 의도 — F3 의 `VaultSyncFatal` 가 cursor advance 안 함이라 같은 changes 가 또 처리됨 → 인적 개입 필수)
- `TimeoutStartSec=15min` — service 자체 timeout. F3 의 gws_timeout 300s × N + agent semantic phase 포함 한도.
- `Persistent=true` + `OnBootSec=2min` + `AccuracySec=1min` — reboot resilience + 전력 절감.
- service 의 `[Install]` 섹션 미작성 — timer 가 service 를 trigger 하므로 service 자체는 enable 안 함. `~/.config/systemd/user/` 에 파일만 존재.

**lint·disk-watch** unit 도 동일 패턴으로 별도 template (Step 3 에서 본 draft 와 함께 작성). lint 는 timer interval = `operations.lint_interval_hours`. disk-watch 는 F4 의 별도 §4.6 으로 후속 정의 (`operations.disk.*` 활성 시만).

---

### 4.3 `wikihub.yaml.example`

```yaml
version: 1

instance:
  root: ~/wikihub-instance
  timezone: Asia/Seoul

vaults:
  - id: gdrive
    type: gdrive_api
    enabled: false   # 운영 시작 시 true 로 변경
    sync_interval_sec: 600
    local_path: ~/wikihub-instance/vault-gdrive
    options:
      credentials_path: ~/wikihub-instance/.credentials/token_gdrive.json
      root_folder_id: ""              # Drive 의 vault root folder ID (선택)
      exclude_shared_with_me: true
      max_file_size_mb: 50
      bootstrap_allowed: false        # 첫 sync 시에만 true → /wh:setup 의 첫 ingest prompt 가 자동 환원

operations:
  lint_interval_hours: 24
  max_concurrent_vaults: serial
  retry:
    max_attempts: 5
    backoff_base_sec: 60
  disk: {}
  fatal_webhook_url: null
  fatal_webhook_timeout_sec: 10
  gws_min_version: ""              # v4: ADR-0014 F4 책임 — Step 3 V6 후 채움. /wh:setup 이 시작 시 `gws --version` 과 비교

agent:
  type: hermes
  binary: /usr/local/bin/hermes
  oneshot_args: ["-z"]
  skill_prefix: "wh:"
  timeout_sec: 600
  notify_on_fatal: true
```

**정합**:
- F2 setup.md Step 1 검증 항목 모두 포함.
- F3 의 vault options (`root_folder_id`, `exclude_shared_with_me`, `max_file_size_mb`, `bootstrap_allowed`) 모두 명시.
- 본 example 만 `.gitignore` 추적 — `wikihub.yaml` 자체는 untracked.

---

### 4.4 `_system/commands/setup.md` Step 6 spec (v4 신설 — R5 §2.7)



ADR-0022 가 결정한 흐름 (E3 + v4 순서 역전) 의 정본화. 기존 setup.md (Step 1~5) 끝에 Step 6 추가 + Step 4 (systemd 반영) 의 enable 동작을 본 Step 6 결과에 의존하도록 변경.

#### 4.4.1 Step 6 — 첫 ingest prompt + timer enable 게이트

**입력 조건**:
- Step 1~5 모두 통과 (yaml 검증 OK + state 디렉토리 OK + systemd unit 파일 작성 OK + daemon-reload OK + 보고 emit).
- enabled vault 중 `bootstrap_allowed: true` 인 vault 가 1개 이상.

**동작**:

1. **prompt 화면 출력** — vault 별로 한 번:
   ```
   vault 'gdrive' 의 첫 ingest 를 지금 실행하시겠습니까? [Y/n] (default Y, 60s timeout → Y)
   ```
   - 비대화 모드 (`--run-first-ingest` / `--skip-first-ingest` / `WIKIHUB_FIRST_INGEST=yes/no` / `/dev/tty` 부재 시 자동 비대화) 면 prompt skip + 사전 결정 사용.
2. **`Y` 응답**:
   - `vault-fetch.py --vault <id> --bootstrap` 직접 호출 (timer 우회 — 60초 backoff 없이 즉시 실행).
   - stdout JSON 보고 + exit code 캡처.
   - exit 0: 성공 → 다음 단계 (timer enable) 진입.
   - exit 75: Retryable — 사용자에게 “일시 결함 — timer 활성화 후 다음 사이클에서 재시도” 안내 + timer enable 은 진행 (다음 timer fire 가 자연 재시도).
   - exit 2: Fatal — “fatal 결함 — timer 활성화 보류. 진단 후 수동 enable 권장” 안내 + **timer enable 안 함**. 운영자가 cursor·credentials 등 진단 후 수동 `systemctl --user enable --now <vault_id>-ingest.timer`.
3. **`N` 응답**:
   - vault-fetch 호출 안 함.
   - timer enable 안 함. 운영자가 yaml 추가 편집 후 다시 `/wh:setup --enable` 호출.
4. **bootstrap_allowed 환원** (`Y` + exit 0 시에만):
   - `wikihub.yaml` 의 해당 vault `bootstrap_allowed: true` → `false` 로 atomic write.
   - yaml writer 는 `/wh:setup` 의 새 책임 (Step 3 구현 시 `scripts/lib/config_writer.py` 또는 `/wh:setup` 자체 helper).
5. **timer enable** (`Y` + exit 0/75 시):
   - `systemctl --user enable --now <vault_id>-ingest.timer`.
   - lint.timer + (조건부) disk-watch.timer 는 vault 와 독립적으로 항상 enable.

**boot 후 자동 재기동 invariant 유지** (V12):
- timer 가 enable 된 후에는 reboot 후에도 systemd user manager 가 자동 재기동 (ADR-0021 D1).
- 첫 ingest 가 fatal 로 timer enable 보류된 vault 도, 운영자가 수동 enable 한 후에는 동일 invariant 적용.

#### 4.4.2 비대화 모드 spec

| flag / env | 동작 |
|---|---|
| `--run-first-ingest` | 모든 vault 의 prompt 자동 `Y` |
| `--skip-first-ingest` | 모든 vault 의 prompt 자동 `N` (timer enable 보류) |
| `WIKIHUB_FIRST_INGEST=yes` | `--run-first-ingest` 와 동등 |
| `WIKIHUB_FIRST_INGEST=no` | `--skip-first-ingest` 와 동등 |
| 모두 미지정 + `/dev/tty` 부재 | default = `Y` (default 안전 — CI/ansible 친화) |

#### 4.4.3 setup.md 갱신 폭 (v5 — R7 NEW-2 + NEW-8 lock)

기존 setup.md L107 의 “다음 권장 액션” 안내 (수동 명령) 는 본 Step 6 의 prompt 가 흡수.

**(1) 치환 변수 목록 (setup.md §Step 2 L54~60) 에 v5 추가 3건**:

| 변수 | 출처 | 비고 |
|---|---|---|
| `{venv_path}` | `~/wikihub/.venv_path` 사이드카 파일 (install.sh Step 3 가 기록) | yaml 미저장 — install.sh 관리 영역 |
| `{credentials_path}` | `wikihub.yaml.vaults[id].options.credentials_path` | per-vault 별 substitution. `~` 는 Python `os.path.expanduser` 로 expand |
| `{wikihub_home}` | `WIKIHUB_HOME` env (default `~/wikihub`) | install.sh 가 실행 시 export. /wh:setup 의 Python helper 가 env 또는 `~/wikihub` fallback read |

**(2) Step 4 의 `--enable` 동작 변경 (R7 NEW-8 lock)**:

setup.md L103 의 현재 정본:
```
--enable 플래그 시: systemctl --user enable --now {vault_id}-ingest.timer lint.timer (...)
```

v5 변경 후:
```
--enable 플래그 시: daemon-reload + lint.timer/disk-watch.timer enable.
                vault-ingest.timer 는 Step 6 결과에 위임 (즉시 enable 안 함).
```

이 변경 누락 시 R6-3 (fatal loop) 재발. Step 3 구현자가 setup.md L103 만 보고 구현하면 흐름 역전 정합 깨짐.

**(3) `출력 산출물` 표에 행 추가**:

| 변경 대상 | 조건 |
|---|---|
| `wikihub.yaml` (bootstrap_allowed: true → false) | `Y` + (exit 0 또는 exit 75 with cursor) 시만 — ADR-0022 정본 정합 (R9 CRIT-2 fix). atomic write + fsync (state.py 의 `_atomic_write_json` 동일 패턴) |

**(4) `실패 처리` 표에 행 추가**:

| 실패 시점 | 동작 |
|---|---|
| Step 6 첫 ingest exit 2 | timer enable 보류 + 사용자 안내 + 보고에 “timer 비활성” 명시 + exit 0 (Step 6 자체는 정상 종료). ops-alert 채널은 별도 동작 |
| Step 6 첫 ingest exit 75 + cursor 존재 | timer enable + bootstrap_allowed 환원 + 다음 사이클 재시도 안내 + 보고 emit + exit 0 |
| **Step 6 첫 ingest exit 75 + cursor 미생성** (R7 NEW-5 lock) | timer enable **보류** (exit 2 동등 취급) — 다음 사이클이 bootstrap 가드 fatal loop 진입 회피. 사용자에게 “cursor 미생성 — 진단 후 수동 enable” 안내 |
| Step 6 yaml writer 실패 | bootstrap_allowed 환원 못 함. 안내 + timer enable 은 진행 + exit 0 (위생 결함이라 fatal 아님) |

---

### 4.5 `scripts/auth_gdrive.py`

**책임**: macOS dev box 에서 메인테이너가 1회 실행 → Google OAuth 발급 → JSON credentials 파일 출력.

```python
# 의사 구조
def main():
    # 1. Google Cloud Console 의 OAuth client (Web application 또는 Desktop) JSON 로드
    # 2. google-auth-oauthlib 의 InstalledAppFlow 로 사용자 브라우저 인증 trigger
    # 3. token 획득 → authorized_user JSON 구조로 저장
    #    형식: {"type": "authorized_user", "client_id": ..., "client_secret": ..., "refresh_token": ...}
    # 4. 출력 파일에 권한 600 설정
    # 5. 사용자에게 scp 안내 (`scp <file> server:~/wikihub-instance/.credentials/`)
```

**정합**: F3 의 `lib/credentials.py:assert_credentials` 가 정확히 이 형식을 검증함. 즉 auth_gdrive.py 의 출력 형식 = F3 의 입력 형식 = ADR-0003 정합 + ADR-0014 (gws 의 `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` 환경변수와 호환).

---

### 4.6 `scripts/ops-alert.py` — v0.1.0 minimal spec (v5 신설 — ADR-0024 reader 책임)

**책임**: systemd 의 `OnFailure=ops-alert.service` 가 trigger 한 시점에 모든 vault 의 `_state/<vault_id>/last_failure.json` 수집 + dedup 검사 + webhook 발송.

**진입점**:
```python
# scripts/ops-alert.py
def main() -> int:
    cfg = load_wikihub_yaml()
    failures = collect_last_failures(cfg.instance_root)  # _state/*/last_failure.json glob
    to_send = [f for f in failures if needs_alert(f)]  # dedup 정책 적용
    if not to_send:
        return 0  # journal 에만 — webhook skip
    if not cfg.operations.fatal_webhook_url:
        log.info("fatal_webhook_url 미설정 — webhook skip, journal 만")
        return 0
    sent_ok = post_webhook(cfg.operations.fatal_webhook_url,
                            payload_from(to_send),
                            timeout_sec=cfg.operations.fatal_webhook_timeout_sec)
    if sent_ok:
        for f in to_send:
            mark_alerted(state_dir_for(f), utc_now_iso())  # alerted_at 갱신
    return 0  # ops-alert 자체 실패는 silent (exit 0)
```

**핵심 결정**:
- exit code 항상 `0` — ops-alert.py 자체 실패도 fatal 아님. systemd 의 `OnFailure` 가 다시 ops-alert 를 trigger 하는 무한 recursion 회피.
- webhook 미설정 시 no-op (journal 로그만).
- dedup 정책은 `last_failure.json` 의 `alerted_at` 과 `failed_count` 비교 (§3.9 dedup 표).

**webhook payload 형식** (v0.1.0):
```json
{
  "wikihub_instance": "<hostname>",
  "alerts": [
    {
      "vault_id": "gdrive",
      "severity": "fatal",
      "scope": "vault",
      "reason": "...",
      "remediation": "...",
      "first_failed_at": "...",
      "last_failed_at": "...",
      "failed_count": 3
    }
  ]
}
```

webhook URL 타입은 user-agnostic — Telegram bot / ntfy / healthchecks.io / Discord webhook 모두 호환되도록 generic JSON POST. specific 타깃 어댑팅은 v0.2.x.

### 4.7 `scripts/vault-fetch.py` 수정 — last_failure writer (v5 신설 — ADR-0024 writer 책임)

F3 의 `scripts/vault-fetch.py` 의 main exception 핸들러 수정. F4 가 F3 산출물을 손대는 첫 사례 — ADR-0024 본문에 명시.

**변경 범위**:
- `scripts/lib/state.py` 에 `save_last_failure()` + `clear_last_failure()` helper 추가 (§3.9 코드 참조).
- `scripts/vault-fetch.py` 의 `except VaultSyncFatal` 직후 `save_last_failure` 호출 + success 분기 직후 `clear_last_failure` 호출.
- `scripts/lib/state.py` 의 `_atomic_write_json` 이미 fsync 포함 (F3 의 HIGH-R4-1 fix 정합) — 본 변경은 helper 만 추가.

**v0.1.0 stub — Hermes notify**:
```python
# scripts/lib/notify.py (신규 — F4 산출물)
def notify_via_hermes(vault_id: str, reason: str) -> None:
    """v0.1.0 은 no-op stub. v0.2.x 의 F5 (hermes_adapter) 가 활성화."""
    log.info("[STUB] notify_via_hermes: vault=%s reason=%s (v0.2.x 활성화 예정)",
             vault_id, reason)
```

vault-fetch.py 가 `notify_on_fatal=true` 인 경우 `save_last_failure` 직전에 `notify_via_hermes` 호출 (현재는 log 만).

**테스트**: F3 의 tests/test_state.py 에 `save_last_failure` + `clear_last_failure` 단위 테스트 추가 — atomic write 정합, 연속 fatal 카운트, success 후 reset.

---

## 5. F1·F2·F3 결정 lift 매트릭스

| 기존 결정 | F4 영향 |
|---|---|
| ADR-0003 OAuth 헤드리스 (Workspace + token-scp) | auth_gdrive.py 가 dev box 책임. install.sh 는 credentials path 자리만 명시 |
| ADR-0006 unified orchestration | systemd ExecStart 의 명령이 `<agent_invocation> "/wh:ingest --vault <id>"` 형식 |
| ADR-0007 all JSON state | install.sh 가 state 디렉토리는 만들지 않음 — /wh:setup 책임 |
| ADR-0010 install.sh ↔ /wh:setup 분리 | 본 feature 가 ADR-0010 의 install.sh 측 implementation |
| ADR-0011 skill namespace prefix | systemd ExecStart 의 prompt 가 `wh:` prefix (또는 fallback) |
| ADR-0012 agent invocation abstraction | wikihub.yaml.example 의 `agent.binary` + `oneshot_args` + skill_prefix |
| ADR-0014 gws CLI | install.sh Step 4 (gws 설치) + ADR-0015 starting |
| F3 archive `lib/errors.py` | ADR-0017 starting regex |

---

## 6. 미결 사항 / Step 3 verification points

| ID | 항목 | 방법 | 영향 |
|---|---|---|---|
| V4 | gws stderr 실패 패턴 (HTTP 4xx/5xx 실 형식) | dev box 또는 OCI 에서 의도적 403/401/5xx trigger 후 stderr 캡처 | ADR-0017 정본화 + F3 의 `lib/errors.py` regex refine |
| V6 | gws version pinning 값 | `gws --version` + changelog | ADR-0015 정본화 |
| V8 | gws 설치 방법 (pip / npm / brew / curl) | gws docs + 실 ARM Ubuntu 시도 | install.sh Step 4 의 명령 확정 |
| V10 | **(v5 교체 — R7 NEW-4)** systemd unit 동작 — `Restart=` 미설정의 oneshot 에서 exit code 별 흐름 | OCI 에서: (1) exit 75 후 `OnUnitInactiveSec` 경과 시 timer 자동 fire 확인, (2) `SuccessExitStatus=0 75` 로 exit 75 가 journal 에 success 기록 확인, (3) exit 2 시 `OnFailure=ops-alert.service` trigger 확인 + `last_failure.json` 영속화 확인 + ops-alert.py 실행 로그 확인 | v4 surgical lift + ADR-0024 정합 |
| V11 | install.sh idempotency (clean install pattern 정합) | (1) 두 번 호출 후 ~/wikihub 가 wipe + clone 정상 재구성, (2) ~/wikihub-instance · venv · systemd unit 무영향, (3) safety guard — WIKIHUB_HOME=/usr 같은 시스템 path · 비-wikihub git repo · 빈 디렉토리 모두 fail-fast, (4) origin remote 검증으로 dev box 작업 디렉토리 보호 | clean install (ADR-0023) idempotency 보장 |
| V12 | **reboot resilience — OS reboot 후 사람 개입 없이 timer fire + 첫 사이클 완료** | **OCI ARM Ubuntu 인스턴스 (macOS dev box 검증 불가)** 에서 `sudo reboot` 후 5분 내 timer fire + last_sync.json 진행 관찰. 검증 인스턴스가 dev box 와 분리됨을 메인테이너가 사전 확보 | **v0.1.0 acceptance**. fail 시 §3.4 [D] 의 fallback 절차 — D2 (system-level + service user) 로 회귀 + ADR-0021 supersede + 새 ADR 발의. 마이그레이션 부담 명시 (useradd / 권한 모델 갱신 / credentials owner 변경) |
| V13 | **(v5 보강 — R7 NEW-5)** 첫 ingest prompt + **순서 역전** 동작 — /wh:setup Step 6 의 prompt + bootstrap 자동 trigger + **첫 ingest 성공 시에만 timer enable** + bootstrap_allowed 환원 + exit 75 의 cursor 분기 | 실 dev box 에서 `/wh:setup --enable` 후 시나리오 6개: (1) `Y` + exit 0: timer enable + bootstrap_allowed false 환원 확인, (2) `Y` + exit 75 + cursor 존재 (partial success): timer enable + bootstrap_allowed 환원 확인, (3) `Y` + exit 75 + cursor 미생성 (완전 실패): timer enable **보류** + 사용자 안내 확인, (4) `Y` + exit 2: timer enable 보류 확인 + last_failure.json 영속화 확인, (5) `N`: vault-fetch + timer enable 모두 skip 확인, (6) 비대화 모드 (`/dev/tty` 부재): default Y 동작 확인 | ADR-0022 v5 정본화. **CRIT-R6-3 (fatal loop) 회귀 방지** + R7 NEW-5 (exit 75 cursor 분기) 회귀 방지 |

V4·V6 결과로 ADR-0015 / ADR-0017 정본 status. V12 acceptance 가 ADR-0021 의 lock-in.

---

## 7. 신규 ADR 발의 목록

| ID | Title | 본 단계 status | 정본화 시점 |
|---|---|---|---|
| ADR-0015 | gws pinned version + 설치 채널 (GitHub Releases binary + shasum, `~/.local/bin/gws`) | Proposed | Step 3 V6 후 Accepted |
| ADR-0017 | gws stderr → wikihub exit code 매핑 표 (scope 컬럼 포함) | Proposed | Step 3 V4 후 Accepted |
| ADR-0018 | wikihub 설치·갱신 흐름 — install.sh 단일 모델 (deploy.sh 미존재) | Accepted | 본 문서 v1 |
| ADR-0019 | systemd unit 의 per-vault file substitution (Python helper) — v0.2.x vault 5개 도달 시 instantiated template 재검토 | Accepted | 본 문서 v2 |
| ADR-0020 | Python venv 위치 — `~/.local/share/wikihub/venv` (XDG_DATA_HOME 기준) | Accepted | 본 문서 v1 |
| ADR-0021 | reboot resilience — user-level systemd unit + `loginctl enable-linger` + timer `Persistent=true` + V12 fail 시 D2 fallback 절차 | Accepted | 본 문서 v2, V12 회귀 방지 |
| ADR-0022 | 첫 ingest 진입점 — install.sh 안내 + `/wh:setup` Step 6 prompt (E3 모델) | Accepted | 본 문서 v1, V13 이 회귀 방지 |
| ADR-0023 | install.sh 배포·호출 모델 — curl-pipe (`curl -fsSL <raw URL> \| bash`) + tag `latest` + clean install pattern (`rm -rf ~/wikihub && git clone`) + safety guard 3개 (시스템 path / .git 검증 / origin remote 검증) | Accepted | 본 문서 v3, V11 이 회귀 방지 |
| **ADR-0024** | **fatal 알림 contract — last_failure.json schema (writer = vault-fetch.py 수정, reader = ops-alert.py) + dedup 정책 (alerted_at + failed_count 기준) + Hermes notify v0.2.x 마이그레이션 경로 (v0.1.0 은 notify_via_hermes stub)** | Accepted | 본 문서 v5, V10 이 회귀 방지 |

총 9건. 기존 F1·F2·F3 ADR 0001~0014 와 충돌 없음 (각각 보강 또는 새 결정 영역). ADR-0019·0021 은 v2 의 surface 결과를 본문에 lock 한 형태, ADR-0022 는 v4 에서 흐름 역전 추가 (supersede 아닌 개정), ADR-0023 은 v3 의 호출 모델 lock, **ADR-0024 는 v5 의 fatal 알림 채널 정본화 — F4 산출물에 vault-fetch.py 수정 (`scripts/lib/state.py` + `scripts/lib/notify.py`) + `scripts/ops-alert.py` 신규 모두 포함**.

---

## 8. Definition of Done

### Step 2 단계
- [ ] 본 문서 v5 사용자 검토 + 결정 [A]~[I] 합의 → 상단 `**상태**: approved YYYY-MM-DD` 마커
- [x] 멀티모델 design review 2 라운드 — R5/R6 (1차, v3 검토) + R7/R8 (2차, v4 검증) 완료 → `design_review_1.md`~`design_review_4.md`. CRIT 5건 + HIGH 4건 v5 lock 반영
- [ ] 신규 ADR **9건** 의 `docs/adr/` 파일 작성:
  - **Accepted at Step 2**: ADR-0018 (install single), ADR-0019 (per-vault unit + Python substitution), ADR-0020 (venv XDG), ADR-0021 (linger + V12 fallback), ADR-0022 (E3 + v4 흐름 역전), ADR-0023 (curl-pipe + clean install + supply chain), **ADR-0024 (fatal 알림 contract)**
  - **Proposed at Step 2 → Accepted at Step 3 V<N>**: ADR-0015 (gws version + CH2), ADR-0017 (gws stderr regex + scope)

### Feature 전체 (Step 5 완료 기준)
- 본 plan.md 의 “Definition of Done (feature 전체)” 7개 항목 그대로 lift.

---

## 9. 참조

- F1 archive: `features/archive/20260513_v030_initial_architecture/` (systemd Type=oneshot, sync 격리, user unit lock)
- F2 archive: `features/archive/20260513_wikihub_schema_v1/`
- F2 정본 spec: `_system/commands/setup.md` (install.sh ↔ /wh:setup 분할), `_system/commands/ingest.md`, `_system/wiki-schema.md`
- F3 archive: `features/archive/20260513_vault_gdrive_api/` (lib/errors.py starting regex, lib/credentials.py 의 JSON 형식)
- ADR 직접 의존: 0003·0006·0007·0010·0011·0012·0014

---

## 10. v7 — Path C+ 변경 spec (rclone mount + gws 책임 분리)

### 10.1 도입 — v6 본문과의 정합

v6 까지의 §1~§9 본문은 그대로 유효 (정본). v7 은 architectural 보강 — Drive 접근 메커니즘에 **rclone mount 를 추가**하고 gws 의 책임 영역을 **변경 감지 단독으로 축소**. v6 본문 중 다음 §은 v7 에서 부분 supersede / 보강:

| v6 § | v7 변경 성격 | 갱신 위치 |
|---|---|---|
| §1 배경·목적 | rclone 도입 motivation 보강 | §10.2 |
| §3.4 [D] reboot resilience (ADR-0021) | mount.service 의존 추가 — 본문 minor 갱신 (supersede 아님) | §10.6.1 (V12 갱신) |
| §4.1 install.sh | Step 5.5 (rclone install) 신설 | §10.4.2 |
| §4.2 systemd unit template | `wikihub-mount@.service.template` 신규 + `vault@.service.template` Requires/After 추가 | §10.4.1·§10.4.7 |
| §4.3 wikihub.yaml.example | `mount_path` / `rclone_remote_name` / `rclone_min_version` / `vfs_cache_max_size` / `vfs_refresh_mode` 추가 | §10.4.4 |
| §4.4 setup.md | Step 5.5 (rclone config) 신설 | §10.4.5 |
| §4.5 auth_gdrive.py | **변경 없음** (gws OAuth 유지) | — |
| §4.6 ops-alert.py | **변경 없음** | — |
| §4.7 vault-fetch.py last_failure writer | **변경 없음** (writer 책임은 그대로, mount 의존만 import) | — |
| §7 ADR 표 | ADR-0025·0026·0027 추가 (총 12건) | §10.7 |
| §8 DoD Step 2 | v7 DoD 추가 | §10.8 |

v6 의 §3.1~§3.3 · §3.5~§3.9 (결정 [A]~[I]) 는 **모두 유지** — supersede 없음. ADR-0014 (gws CLI 채택) 도 supersede 없음 (gws 는 변경 감지 정본으로 유지).

### 10.2 v7 의 architectural motivation

v6 까지의 design 에서 Drive 접근은 gws CLI 단독:
- `gws drive changes list` — 변경 감지 (cursor 기반, 정확)
- `gws drive files get/export` — 다운로드/export

v7 에서는 **사용자 요구사항 추가**: 운영자가 Google Drive 에 파일을 떨구면 OCI 서버의 vault 폴더에서 **실시간으로 접근** 가능해야 함 (SSH ls/cat). gws 단독으로는 이 UX 제공 불가 — 매 사이클 다운로드만 가능, 사이클 사이 시점에는 vault 폴더가 N-1 사이클 시점의 스냅샷.

**Path C+ 결정** (`rclone_vs_gws_comparison.md` §5·§7 참조):
- **rclone mount = vault 자체에 마운트** → 실시간 mount UX + 다운로드 패스 (vfs cache 활용)
- **gws drive changes list = 변경 감지 정본** (cursor 기반, ADR-0014 유지)
- **race window 차단** = 사이클 시작 시 `rclone rc vfs/refresh` 1회

**대안 기각 근거** (`rclone_vs_gws_comparison.md` §2·§3·§4):
- (B1) rclone 단독 (mount FS walk + file_map diff): 삭제 이벤트·권한 변경 감지 불가 + reboot 기간 catch up 불가 + source_id 노출 미보장
- (A) gws 단독 유지: 실시간 mount UX 미충족
- (C) UX 만 mount: 사용자 의도 (vault 자체 마운트) 와 어긋남

### 10.3 결정 종합 (3건 추가 — [J]·[K]·[L])

#### 10.3.1 [J] rclone mount 채택 — vault 자체 마운트 (ADR-0025)

**대안**:
- (J1) vault 별도 + 마운트 별도 디렉토리: `<instance_root>/google_drive/` 마운트 + `<instance_root>/vault/` 다운로드 → 두 디렉토리 동기화 부담
- (J2) **vault 자체에 직접 마운트**: `<instance_root>/vault/<vault_id>/` 가 곧 mount point → 다운로드 단계 자체 제거, 사용자 의도 1:1
- (J3) rclone mount 미사용 (gws 단독 유지): 사용자 요구사항 (실시간 UX) 미충족

**결정**: **(J2) vault 자체 마운트**

**이유**:
- 사용자 의도 (Drive ↔ vault 실시간) 와 1:1
- `sync.py` 의 다운로드 헬퍼 (`_download_to_vault`) 폐기 가능 → 코드 단순화
- vfs cache 가 다운로드 캐시 역할 흡수 (별도 캐시 정책 불필요)

**부정·제약**:
- mount 죽으면 vault 폴더 자체가 접근 불가 → 모든 read 실패 (장애 격리는 명확하지만 영향 범위 큼)
- vfs cache 크기 정책 = vault 디스크 사용량 정책 (운영 가시성 신규)

#### 10.3.2 [K] vfs refresh 정책 — 사이클 시작 시 recursive 1회 (ADR-0026)

**race window**: gws changes 가 "X 변경" 알린 시점부터 mount 가 vfs cache 를 invalidate 하기 전까지 → mount path 의 `open(X)` 가 OLD content 반환 위험.

**대안**:
- (K1) **사이클 시작 시 `rclone rc vfs/refresh recursive=true` 1회**: 단순·보수적. 큰 vault 시 비용
- (K2) per-file refresh: gws changes 응답의 source_id 별로 `rclone rc vfs/refresh file=<path>` 호출. 정밀하지만 mount path 계산 (Drive ID → path) 로직 신규
- (K3) `--dir-cache-time` 단축 (예: 1min) + `--vfs-read-wait`: refresh 호출 없음. 단 사이클 (10min) 대비 fresh 보장 안 됨

**결정**: **(K1) recursive refresh 1회** — v0.1.0 채택. V15 결과로 v0.2.x 에서 K2 마이그레이션 가능성 surface.

**이유**:
- v0.1.0 vault 규모 (수천 파일 추정) 에서 recursive refresh 비용 < 5s — acceptable
- per-file refresh 는 source_id → mount path 매핑 로직 신규 — Step 3 verification 부담 추가
- K3 는 fresh 보장 안 됨 — race window 잔존

**부정·제약**:
- 큰 vault (수만 파일) 에서 refresh 자체가 사이클 timeout 압박 가능 → V15 에서 측정
- recursive refresh 실패 시 fallback 없음 → fail-fast (다음 사이클 재시도, mount.service 가 Restart=always 로 mount 자체 복구)

#### 10.3.3 [L] rclone vs gws 책임 분리 — Path C+ 정본 (ADR-0027)

**책임 경계**:

| 영역 | rclone | gws |
|---|---|---|
| Drive ↔ 로컬 sync (실시간) | ✅ mount daemon | ❌ |
| 변경 감지 (cursor 기반) | ❌ (Drive Changes API 미노출 — `rclone_vs_gws_comparison.md` §2) | ✅ `changes list` |
| 삭제·권한·rename 이벤트 | ❌ | ✅ `changeType` |
| 파일 read (다운로드) | ✅ mount FS `open()` (vfs cache) | ❌ (v7 에서 폐기) |
| Google native export | Q1 미결 (§10.5) | Q1 미결 |
| OAuth | ✅ `rclone config` | ✅ `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` |
| systemd unit | `wikihub-mount@.service` (Type=simple, Restart=always) | `wikihub-vault@.service` (Type=oneshot, timer 기반) |

**장애 격리**:
- mount 죽음 → vault read 불가. `wikihub-vault@.service` 가 `assert_mount_alive()` 로 fail-fast (mount path stat 실패 감지). `OnFailure=ops-alert.service` 발화. 변경 감지 (gws) 호출 자체는 이뤄지지만 read 가 막혀 사이클 실패
- gws 결함 → 변경 감지 끊김. mount 는 살아있어 운영자 SSH UX 유지. `wikihub-vault@.service` 가 fail-fast → ops-alert

**이유**:
- 각 도구가 가장 잘하는 일만 — alpha 부담을 "gws changes list" 한 영역에만 격리
- F3 `sync.py` 핵심 로직 ~90% 재사용 (changes.list 호출은 그대로, 다운로드 헬퍼만 교체)
- ADR-0014 (gws CLI) supersede 없음 → ADR cascade 최소화

### 10.4 산출물 spec 변경

#### 10.4.1 신규 `_system/systemd/wikihub-mount@.service.template`

> **v8 patch**: `OnFailure=ops-alert.service` 추가 (R12-CRIT-1 — mount silent dead 차단), `--log-level INFO` → `NOTICE` (R12-MED-3 — token 노출 회피), `RemainAfterExit=no` 명시.

```ini
[Unit]
Description=WikiHub rclone mount — %i
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5
OnFailure=ops-alert.service                                # v8 (R12-CRIT-1) — StartLimitBurst 초과 fail 시 즉시 ops-alert 발화

[Service]
Type=simple
WorkingDirectory={instance_root}
Environment=PATH={venv_path}/bin:/usr/bin:/bin
Environment=RCLONE_CONFIG={rclone_config_path}
ExecStartPre=/bin/mkdir -p {instance_root}/vault/%i
ExecStart={rclone_bin} mount {remote_name_for_%i}: {instance_root}/vault/%i \
  --vfs-cache-mode full \
  --vfs-cache-max-size {vfs_cache_max_size} \
  --dir-cache-time 5m \
  --log-level NOTICE \                                     # v8 (R12-MED-3) — INFO 는 token 노출 위험, NOTICE 는 warn+error 만
  --rc \
  --rc-addr 127.0.0.1:{rc_port_for_%i}
ExecStop=/bin/fusermount3 -u {instance_root}/vault/%i
Restart=always
RestartSec=10s
RemainAfterExit=no                                         # v6 R10-CRIT-1 패턴 정합

[Install]
WantedBy=default.target
```

핵심 결정:
- `Type=simple` — daemon 상시 살아있어야 함
- **`Restart=always + RestartSec=10s`** — daemon 죽으면 자동 재기동. `StartLimitBurst=5` 로 5회/5min 초과 시 fail. **fail 시 `OnFailure=ops-alert.service` 가 ops-alert 발화** (v8 — vault@.service fail-fast 경로와 이중화: mount StartLimit 소진은 vault@ fire 사이클 (최대 10min) 을 기다리지 않고 즉시 통지)
- **`--rc --rc-addr 127.0.0.1:<port>`** — vault@.service 가 `rclone rc vfs/refresh` 호출하기 위한 endpoint. port 충돌 회피용 per-vault substitution (Q3 미결)
- **`--vfs-cache-mode full`** — 다운로드된 파일 영속 캐시 (사용자 메시지 §1 권장)
- **`--vfs-cache-max-size`** — 디스크 용량 정책 (`wikihub.yaml operations.vfs_cache_max_size` 정합. default 10G — Step 3 V8 검증). **OCI free tier 디스크 가이드는 Q7 미결**
- **`--dir-cache-time 5m`** — directory listing 캐시. 사이클 시작 시 `vfs/refresh` 가 무조건 invalidate 하므로 5m 으로 boundary 보수 설정
- **`--log-level NOTICE`** (v8) — rclone INFO log 가 OAuth token / URL 등을 평문 출력하는 경우가 있어 NOTICE 로 낮춤. trouble-shooting 시 운영자가 일시적으로 `RCLONE_LOG_LEVEL=DEBUG` env 로 override 후 token 노출 가능성 인지 (운영 매뉴얼)
- `[Install] WantedBy=default.target` — install.sh / Python helper 가 vault_id 별 instantiate 후 `systemctl --user enable wikihub-mount@<vid>.service`

ADR-0019 (per-vault Python substitution) 패턴 정합 — `wikihub-mount@.service.template` 도 동일 Python helper 가 instantiate.

**(v9 R14-CRIT-1 — last_failure writer 책임 분배, ADR-0024 본문 minor 갱신 정합)**:

mount alert 채널의 정합성을 보장하기 위해 **두 case 의 책임 분배**:

| Case | trigger 경로 | writer | reader |
|---|---|---|---|
| **(A) mount 가 일시 fail → Restart 사이클** | mount@ Restart=always 동작, OnFailure 미발화 | (없음 — daemon 복구 중) | (없음) |
| **(B) mount 가 hung/dead 지속 — Retryable 누적** | vault@ 사이클 중 `assert_mount_alive` 가 Retryable raise → 6회 누적 후 §10.4.6 의 `_raise_mount_failure` 가 Fatal escalate | **§10.4.6 `mount.py` 가 직접 `save_last_failure(scope="mount")` 호출** | ops-alert.service 가 last_failure.json 읽음 |
| **(C) mount@.service 자체 StartLimitBurst (5회/5min) 초과 → permanently failed** | mount@ `OnFailure=ops-alert.service` 발화 | **mount.py 미호출 (vault@ 가 못 돌아감)** — ops-alert.py 가 last_failure.json 부재 case 를 fallback diagnostic 으로 처리 | ops-alert.service (직접 trigger) |
| **(D) rclone OAuth revoke** | vault@ 사이클 중 `vfs_refresh` 가 OAuth 패턴 매칭 → Fatal | §10.4.6 `vfs_refresh` 가 직접 `save_last_failure(scope="mount")` 호출 | ops-alert.service via vault@.service OnFailure |

**(C) case 의 fallback diagnostic 처리** (ops-alert.py 책임 — §4.6 본문 v9 minor 갱신):
- `last_failure.json` 부재 시 (또는 `last_failed_at` 가 30분 이상 stale 시) `journalctl --user -u wikihub-mount@<vid>.service --since '30min ago' --no-pager` 의 tail (마지막 100줄) 을 webhook payload 의 `fallback_diagnostic` 필드로 첨부. webhook URL 미설정 시 stderr 로 진단 출력 (journalctl 가 운영자가 SSH 로 확인 가능한 영속 경로)

이로써 R14-CRIT-1 의 silent dead (OnFailure 발화 + webhook 0건) 차단.

#### 10.4.2 `install.sh` patch — Step 5.5 (rclone install + verify + rc port pre-check + conf perms)

> **v8 patch** (R12-HIGH-3 + R12-MED-1 + R12-MED-2): `rclone.org/install.sh | sudo bash` 의 supply chain 위협 회피 — GitHub Releases binary + **SHA256SUMS verify** 패턴으로 교체 (ADR-0023 의 wikihub install supply chain 위협 모델과 정합). 추가로 rc port 가용성 pre-check + `rclone.conf` 권한 0600 enforce 신설.

v6 §4.1 install.sh 본문의 Step 순서에 **Step 5.5** 신설 (Step 5 venv 생성 후, Step 6 systemd unit deploy 전):

```bash
# Step 5.5 — rclone install (sha256 verify) + rc port pre-check + conf perms (v8, ADR-0025)

# 5.5a — rclone binary 설치 (GitHub Releases + SHA256SUMS verify, v9 retry 보강)
_curl_with_retry() {
  # v9 R14-HIGH-1 — GitHub Releases 가용성 회귀 대응. 3회 retry @ 5min interval.
  # GitHub incident (status.github.com) 시 SHA verify 실패가 변조 의심으로 misleading 되는 것 차단.
  local url="$1" out="$2" attempts=3 wait_sec=300
  for ((i=1; i<=attempts; i++)); do
    if curl -fsSL --max-time 60 -o "$out" "$url"; then
      return 0
    fi
    _log "curl 실패 ($url) — ${i}/${attempts} 시도. ${wait_sec}s 후 재시도"
    sleep "$wait_sec"
  done
  _die "curl 3회 실패 ($url) — GitHub 가용성 또는 네트워크 점검. status.github.com 확인 후 install.sh 재실행"
}

_install_rclone() {
  local min_version="${1:-1.65.0}"
  if command -v rclone >/dev/null 2>&1; then
    local current_version
    current_version="$(rclone version | head -1 | awk '{print $2}' | sed 's/^v//')"
    if _version_ge "$current_version" "$min_version"; then
      _log "rclone $current_version 이상 — 설치 건너뜀"
      return 0
    fi
  fi
  local pinned="${RCLONE_PINNED_VERSION:-1.69.1}"   # ADR-0025 V16 후 정본 lock
  local arch
  case "$(uname -m)" in
    aarch64) arch="arm64" ;;
    x86_64)  arch="amd64" ;;
    *) _die "지원되지 않는 arch: $(uname -m)" ;;
  esac
  local archive="rclone-v${pinned}-linux-${arch}.zip"
  local base="https://github.com/rclone/rclone/releases/download/v${pinned}"
  _log "rclone v${pinned} 설치 (channel: GitHub Releases + SHA256SUMS verify, v9 retry)"
  _curl_with_retry "${base}/${archive}"  "/tmp/${archive}"      # v9 retry
  _curl_with_retry "${base}/SHA256SUMS"  "/tmp/SHA256SUMS"      # v9 retry
  ( cd /tmp && grep -E "  ${archive}\$" SHA256SUMS | sha256sum -c - ) \
    || _die "rclone SHA256 verify 실패 — supply chain 위협 가능, 설치 중단"
  unzip -q -o "/tmp/${archive}" -d /tmp/rclone-extract
  sudo install -m 755 "/tmp/rclone-extract/rclone-v${pinned}-linux-${arch}/rclone" /usr/local/bin/rclone
  rm -rf "/tmp/rclone-extract" "/tmp/${archive}" "/tmp/SHA256SUMS"
  _assert command -v rclone >/dev/null 2>&1 "rclone 설치 실패"
}
_install_rclone "${RCLONE_MIN_VERSION:-1.65.0}"

# 5.5b — rclone.conf 권한 강제 0600 (R12-MED-2 — secrets 노출 차단)
_enforce_rclone_conf_perms() {
  local conf="${RCLONE_CONFIG:-${HOME}/.config/rclone/rclone.conf}"
  if [[ -f "$conf" ]]; then
    chmod 0600 "$conf"
    _log "rclone.conf 권한 0600 enforce: $conf"
  else
    _log "rclone.conf 미존재 — setup.md Step 5.5 (rclone config) 안내 대상"
  fi
}
_enforce_rclone_conf_perms

# 5.5c — per-vault rc port 가용성 pre-check (R12-MED-1 + v9 R14-HIGH-2 + R13-CRIT-2)

# v9 R13-CRIT-2 — _yaml_get_vault_rc_ports helper 구현 spec (Python 인라인, PyYAML 사용)
_yaml_get_vault_rc_ports() {
  local yaml_file="$1"
  # venv 의 python3 는 이 시점에 활성. PyYAML 은 Step 5 venv 설치 시 포함 (scripts/requirements.txt).
  # 빈 출력 = 모든 vault 가 rclone_rc_port 미설정 (default 처리는 호출자 책임 — install.sh 가 default 5572 + 순번 산출).
  # yaml 파싱 오류 시 stderr 로 진단 + non-zero exit → 호출자가 stdout 비어있음으로 처리.
  python3 - "$yaml_file" <<'PYEOF' 2>&1
import sys, yaml
try:
    cfg = yaml.safe_load(open(sys.argv[1])) or {}
except Exception as e:
    print(f"yaml 파싱 실패: {e}", file=sys.stderr)
    sys.exit(2)
for v in cfg.get("vaults", []):
    port = (v.get("options") or {}).get("rclone_rc_port")
    if port is not None:
        print(port)
PYEOF
}

# v9 R14-HIGH-2 — ss user namespace false negative 보강
_check_rc_port_available() {
  local port="$1"
  # ss -tlnH 의 권한 — 비특권 사용자는 자기 user namespace 의 listen socket 만 봄.
  # systemd user unit 으로 mount@ 가 실행될 환경과 동일 사용자에서 install.sh 가 돌아야 정확.
  # EUID 0 (sudo install.sh) 인 경우 모든 namespace 보지만 운영 mode 와 mismatch — 경고.
  if [[ "${EUID}" -eq 0 ]]; then
    _log "WARN: install.sh 가 root 로 실행 중 — ss port check 가 user namespace mismatch. 운영자 의도 확인."
  fi
  # 추가 보강: lsof 가 있으면 cross-check (systemd unit 의 RuntimeUser 와 동일 user 에서 점유한 port 도 catch)
  if ss -tlnH "( sport = :${port} )" 2>/dev/null | grep -q ":${port}"; then
    _die "rclone rc port ${port} 이미 사용 중 (ss) — wikihub.yaml.vaults[*].options.rclone_rc_port 변경 후 재실행"
  fi
  if command -v lsof >/dev/null 2>&1; then
    if lsof -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null | grep -q .; then
      _die "rclone rc port ${port} 이미 사용 중 (lsof) — wikihub.yaml.vaults[*].options.rclone_rc_port 변경 후 재실행"
    fi
  fi
}

for port in $(_yaml_get_vault_rc_ports "${WIKIHUB_YAML}"); do
  _check_rc_port_available "${port}"
done
```

채널 결정 (Q2 v8 lock):
- **GitHub Releases binary + SHA256SUMS verify** — `rclone.org/install.sh | sudo bash` 는 supply chain 측면에서 weakest link (rclone.org domain 또는 그 CDN 변조 시 sudo 권한으로 임의 코드 실행). GitHub Releases 의 SHA256SUMS 본문 검증으로 mutable artifact 위험 차단. apt 보다 fresh + version pin 강제
- GPG signature 검증은 **v0.2.x deferred** — rclone 의 release signing 정책 변경 추적 부담. v0.1.0 은 SHA256 만으로 운영 위험 acceptable 판정
- supply chain 위협 모델: ADR-0023 (curl-pipe wikihub install) 과 정합 — install.sh 본문에 위협 모델 코멘트 명시

Step 6 (systemd unit deploy) 에서 `wikihub-mount@<vid>.service` 도 vault@.service 와 함께 enable.

#### 10.4.3 `scripts/lib/sync.py` patch — 다운로드 헬퍼 mount path open 교체

> **v8 patch**:
> - **(R11-CRIT-3)** `_handle_removed` 의 `(vault_local_path / entry).unlink()` 라인 **제거** — mount FS 위 unlink 는 rclone `--vfs-cache-mode full` 의 write-through 로 Drive 원본을 삭제할 위험. 데이터 손실 직결
> - **(R11-HIGH-3)** `vfs_refresh` 실패 시 사이클 흐름 step 2 에서 **exit 75 사이클 abort** 명시 — race window 차단 실패 시 stale read 를 허용하면 ADR-0026 가정 위반
> - **(R11-MED-2)** `_resolve_mount_path` v0.1.0 spec 을 **flat lock** — `vault_cfg.mount_path / change_record["file"]["name"]`. 폴더 계층은 V13 검증으로 확인 (Drive 폴더 ID → 폴더 이름 매핑은 v0.2.x deferred)
> - **(R11-CRIT-1)** Q1 (Google native export) lock 을 **Step 3 진입 즉시 V15a PoC 선행**으로 명시. 사이클 흐름은 Q1 lock 후 단일 경로 (옵션 1 잠정) 로 가정

**v6 (gws 단독)**:
```python
def _download_to_vault(vault_local_path, source_id, mime, ...):
    result = run_gws(['drive', 'files', 'get'],
                    params={'fileId': source_id, 'alt': 'media'},
                    binary_output=True, timeout_sec=...)
    if result.returncode != 0:
        wikihub_exit, severity, reason, scope = classify_gws_error(result.returncode, result.stderr)
        raise ...
    _atomic_write_bytes(vault_local_path, result.stdout_bytes)  # CRIT-2
```

**v7/v8 (mount path open)**:
```python
def _read_from_mount(mount_path: Path) -> bytes:
    if not mount_path.exists():
        raise VaultSyncFileFatal(
            source_id=...,
            reason=f"mount path 없음 — mount.service 가 죽었거나 file 이 vfs cache 에 미반영: {mount_path}",
            remediation="systemctl --user status wikihub-mount@<vault_id>.service",
        )
    return mount_path.read_bytes()


def _resolve_mount_path(change_record: dict, vault_cfg: VaultConfig) -> Path:
    """v0.1.0 flat lock (R11-MED-2): 폴더 계층 미반영.

    Drive 폴더 안에 있는 파일도 mount_path / name 으로 평가.
    V13 검증 케이스에 폴더 하위 파일 포함하여 미러 정합 확인.
    폴더 계층 반영은 v0.2.x — Drive parents ID → 폴더 이름 매핑 helper 추가 필요.
    """
    name = change_record["file"]["name"]
    return vault_cfg.mount_path / name
```

변경 폭:
- `gws files get` subprocess 호출 자체 폐기. mount FS read 가 vfs cache 또는 Drive fetch 를 자동 처리
- atomic-write 패턴 (CRIT-2 의 `_atomic_write_*`) 도 폐기 — mount FS read 는 그 자체로 atomic (rclone vfs 가 fresh copy 보장)
- mount path 계산: **v0.1.0 flat** — `vault_mount / file_name`. 폴더 계층은 v0.2.x deferred

**SIG-2 정합 (R11-CRIT-3 v8 lock)**:
v6 `_handle_removed` 의 `(vault_local_path / entry).unlink(missing_ok=True)` 라인 **제거**. 이유: v7 에서 `vault_local_path` 가 rclone mount point 이므로 unlink 는 Drive 원본 파일 삭제 위험. Drive 삭제 이벤트 처리 시 로컬 행동은 **wiki page 삭제 + file_map 갱신만**. `deleted_out` 로직은 그대로. vault binary 미러 일관성은 mount FS 가 read-through 로 자동 보장 (Drive 에서 삭제된 파일은 vfs/refresh 후 mount 에서도 사라짐).

**Google native export** (R11-CRIT-1 v8 sequencing):
Q1 미결 (§10.5). 후보:
- **옵션 1 (잠정 채택)**: rclone mount 의 자동 export (`--drive-export-formats markdown`) → vault 폴더에 `.md` 로 보임. `gws files export` 폐기
- 옵션 2: gws `files export` 유지

**Step 3 진입 즉시 V15a PoC 선행** — Q1 lock 후 본 §10.4.3 사이클 흐름 step 4 의 분기 구조 (single-path vs dual-path) 확정. PoC 실패 (옵션 1 의 markdown 품질 미흡) 시 옵션 2 로 회귀하며 `sync.py` 에 dual-path 분기 (mime == GWS_EXPORT_MIME 시 gws export, else mount read) 유지.

`sync.py` 사이클 흐름 (v8):
1. **`assert_mount_alive(vault_cfg.mount_path)`** — mount 살아있는지 fail-fast (§10.4.6 subprocess timeout helper)
2. **`vfs_refresh(rc_addr, recursive=True)`** — race window 차단 (ADR-0026). **실패 시 exit 75 (사이클 abort)** — race window 차단 실패 상태에서 stale read 진행은 ADR-0026 가정 위반 (R11-HIGH-3)
3. `gws drive changes list --params {pageToken: cursor}` — 변경 감지 (v6 유지)
4. 각 변경 file 별:
   - operation == "removed/trashed" → wiki page 삭제 + file_map 갱신. **vault local unlink 안 함** (R11-CRIT-3, Drive 원본 보호)
   - operation == "created/modified" → `_resolve_mount_path()` → `_read_from_mount()` → extraction → wiki page write (v6 의 extraction·frontmatter·file_map 갱신 흐름 그대로)
5. cursor 저장, last_sync 갱신 (v6 유지)

#### 10.4.4 `wikihub.yaml.example` patch

> **v8 patch**:
> - **(R11-HIGH-2)** vaults 를 **v6 §4.3 의 list 구조** (`- id: gdrive`) 로 정정. 직전 v7 작성 시 map 구조로 오기재 → `scripts/lib/config.py` 의 v6 list 파싱 로직과 불일치 (breaking change 위험)
> - **(R11-MED-1)** `{rc_port_for_<vault_id>}` substitution binding 을 본문에 명시 — yaml `vaults[*].options.rclone_rc_port` 에서 vault_id 별로 lookup
> - **(R12-LOW-2)** `rclone_max_version` 추가 — breaking change 방어

```yaml
vaults:
  - id: gdrive                                                      # v6 유지 (list 구조)
    enabled: true
    options:
      credentials_path: ~/.config/wikihub/gws-credentials.json     # v6 유지
      root_folder_id: "..."                                         # v6 유지
      max_file_size_mb: 50                                          # v6 유지
      bootstrap_allowed: false                                      # v6 유지
      mount_path: ~/.local/share/wikihub/vault/gdrive               # v7 신규 (default = instance_root/vault/<vault_id>)
      rclone_remote_name: gdrive                                    # v7 신규 (rclone config 의 remote 이름)
      rclone_rc_port: 5572                                          # v7 신규 (Q3 — per-vault rc port, default = 5572 + vault index)

operations:
  gws_min_version: 0.7.0                                            # v6 유지
  rclone_min_version: 1.65.0                                        # v7 신규 — install.sh _install_rclone 의 min
  rclone_max_version: 1.99.99                                       # v8 신규 (R12-LOW-2) — breaking change 방어. 초과 시 install.sh fail
  vfs_cache_max_size: 10G                                           # v7 신규 — OCI free tier 디스크 가이드는 Q7
  vfs_refresh_mode: recursive                                       # v7 신규 (recursive | per-file | none — K1·K2·K3)
  instance_label: hostname                                          # v6 유지
  fatal_webhook_url: ""                                             # v6 유지
```

**치환변수 binding** (Python substitution helper, ADR-0019):
- `{venv_path}` (v5 NEW-2 유지)
- `{credentials_path}` (v5 NEW-2 유지)
- `{wikihub_home}` (v5 NEW-2 유지)
- `{rclone_bin}` (v7 신규) — `/usr/local/bin/rclone` (install.sh §10.4.2 가 install location lock)
- `{rclone_config_path}` (v7 신규) — `${RCLONE_CONFIG:-${HOME}/.config/rclone/rclone.conf}`
- `{rc_port_for_<vault_id>}` (v8 명시) — yaml `vaults[*].options.rclone_rc_port` 에서 vault_id 별로 lookup. 예: vault_id=`gdrive` → yaml `vaults[0].options.rclone_rc_port: 5572` → 치환변수 key `{rc_port_for_gdrive}` = `5572`. mount@.service 의 `--rc-addr 127.0.0.1:{rc_port_for_%i}` 는 systemd `%i` 가 vault_id 와 동일 substitution
- `{remote_name_for_<vault_id>}` (v8 명시) — yaml `vaults[*].options.rclone_remote_name` 에서 vault_id 별로 lookup
- `{vfs_cache_max_size}` (v7 명시) — yaml `operations.vfs_cache_max_size`

**(v9 R13-MED-2 — Python substitution 순서: 2-pass)**:

Python substitution helper (ADR-0019) 는 vault_id 별로 template instantiate 시 **2-pass** 처리:

1. **Pass 1 — `%i` 전치환**: template 내 모든 `%i` 를 vault_id literal 로 치환. 예: `{rc_port_for_%i}` → `{rc_port_for_gdrive}`, `{remote_name_for_%i}` → `{remote_name_for_gdrive}`
2. **Pass 2 — `.format_map(subst_dict)` 로 brace 치환**: `subst_dict` 에 `rc_port_for_gdrive`, `remote_name_for_gdrive` 등 vault_id 가 합쳐진 key 가 등록되어 lookup

이유: systemd `%i` 는 systemd 가 runtime 에 instantiate 시 해석하는데, Python 의 `.format_map()` 은 systemd 와 다른 stage. 두 메커니즘이 같은 token 으로 보이지만 stage 가 분리됨 → Python helper 가 `%i` 를 먼저 명시 치환해야 `.format_map()` 가 정확한 key 를 lookup. ADR-0019 의 단일 pass 패턴을 per-vault 키 prefix 방식으로 확장.

instantiate 시점:
- install.sh / setup.md 가 systemd unit 을 `/etc/systemd/user/wikihub-mount@<vid>.service` 또는 `~/.config/systemd/user/wikihub-mount@<vid>.service` 로 deploy 할 때 Python helper 호출
- helper 가 vault_id 별로 substitution dict 산출 + 2-pass instantiate + 결과 파일 write
- systemd 가 unit 을 enable 후 시작 시점에 `%i` 가 unit 이름에서 추출돼 ExecStart 의 `%i` (이미 Python pass 1 으로 vault_id 치환됨) 와 정합

#### 10.4.5 `_system/commands/setup.md` patch — Step 5.5 (rclone config) 신설

v6 §4.4.3 의 setup.md 갱신 폭에 **Step 5.5 (rclone OAuth 발급)** 신설 — Step 5 (gws OAuth) 후, Step 6 (첫 ingest prompt + timer enable) 전:

```markdown
### Step 5.5 — rclone OAuth 발급 (vault 별 1회성, ADR-0025)

interactive mode (default):
1. `rclone config` 실행 안내
2. `n` (new remote) → name 입력 (`gdrive` 권장 — `wikihub.yaml.vaults.<id>.options.rclone_remote_name` 과 정합)
3. type 선택: `18` (drive)
4. client_id/secret: 빈칸 (rclone 기본 사용 — quota 부담 시 wikihub.yaml `vaults.<id>.options.rclone_client_id/secret` 명시 옵션 v0.2.x deferred)
5. scope: `1` (full access)
6. service_account_file: 빈칸
7. Edit advanced config: `n`
8. Use auto config: `y` → browser OAuth flow (gws 와 동일 Google 계정 권장 — token 만 분리)
9. Configure as Shared Drive: `n`
10. 완료 후 `~/.config/rclone/rclone.conf` 에 remote 등록 확인
11. **(v8, R12-MED-2) `chmod 0600 ~/.config/rclone/rclone.conf` 실행 — OAuth token 평문 저장이므로 다른 사용자 read 차단**

non-interactive mode (`--skip-rclone-config`):
- 사전에 `rclone.conf` 를 `~/.config/rclone/` 에 배치한 경우만. install.sh 가 conf 존재 + remote_name 정합 검증 + **권한 0600 enforce** (§10.4.2 의 `_enforce_rclone_conf_perms` 가 install.sh 실행 때 자동 처리, 본 step 은 setup.md 의 운영자 가이드 차원에서 한 번 더 명시)
- mount.service 가 `Environment=RCLONE_CONFIG=` 로 conf 경로 주입 — install.sh 가 path lock
```

ADR-0022 (첫 ingest 진입점) 와 정합 — Step 5.5 가 끝나야 Step 6 첫 ingest prompt 진입 가능.

**(v8 R12-MED-2 정합)** `rclone.conf` 의 권한 enforcement 책임 분배:
- **install.sh §10.4.2 5.5b** `_enforce_rclone_conf_perms` — 자동 `chmod 0600` (정본 enforce 경로)
- **setup.md Step 5.5 step 11** — 운영자가 수동 setup 한 직후 한 번 더 확인 (대화형 안내)
- **mount.service** — `Environment=RCLONE_CONFIG=` 만 주입 (권한 검증은 install.sh 책임, mount 단계 미수행)

#### 10.4.6 `scripts/lib/mount.py` 신규 — vfs/refresh + mount 검증 helper

> **v9 patch**:
> - **(R13-HIGH-2 + R14-HIGH-3)** `assert_mount_alive` 의 `ls -la` → `stat` 교체 — 대용량 vault stdout 메모리 폭발 차단, liveness check intent 유지
> - **(R13-NIT-1)** `import os` 제거 — `os.statvfs` 교체 후 orphan
> - **(R13-MED-1)** `retry_after_sec` 가 vault-fetch.py 미사용 진단 메타임을 주석으로 명시
> - **(R13-CRIT-1)** `vfs_refresh` 에 OAuth error 패턴 검사 추가 + `VaultSyncFatal` 분기 — Q6 alert 체인 정합 (단, V18 이 stderr 노출 여부 검증 후 패턴 refine — Step 3 verification)
> - **(R14-HIGH-4 + Q5 회귀 방지)** `assert_mount_alive` Retryable 누적 escalation — 동일 vault 의 Retryable 가 N회 (default 6, 1시간 ≈ 10min × 6) 연속 발생 시 `VaultSyncFatal` 로 escalate. ADR-0024 `last_failure` writer 가 mount scope 로 발화 → ops-alert. mount permanently failed 의 silent abort 차단
> - **ADR-0024 writer 확장 (옵션 c)**: `state.py` 의 `save_last_failure` schema 에 `scope="mount"` 추가. `mount.py` 가 fatal escalation 또는 OAuth Fatal 시 직접 호출. `mount-fail-recorder.service` 신규 unit 없음

```python
"""rclone mount lifecycle helpers (v7~v9, ADR-0024·0025·0026 정본)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .exceptions import VaultSyncFatal, VaultSyncRetryable
from .state import save_last_failure, utc_now_iso, load_last_failure


# v9 R13-CRIT-1 — rclone OAuth error 패턴 (V18 후 refine 예정)
_RCLONE_AUTH_PATTERNS = re.compile(
    r"(Token expired|invalid_grant|401 Unauthorized|oauth2.*invalid|"
    r"unauthorized_client|access_denied)",
    re.IGNORECASE,
)

# v9 R14-HIGH-4 — Retryable 누적 escalation 임계 (default 6 = 약 1시간 @ 10min cycle)
MOUNT_RETRYABLE_FATAL_THRESHOLD = 6


def assert_mount_alive(
    vault_id: str,
    mount_path: Path,
    state_dir: Path | None = None,
    timeout_sec: int = 5,
) -> None:
    """mount path 가 FUSE 응답 가능 상태인지 timeout 보장된 subprocess 로 검증 (v9 patch).

    v9 R13-HIGH-2 + R14-HIGH-3: `ls -la` 의 stdout 이 대용량 vault 에서 메모리 폭발 (~10MB/50k 파일).
    `stat <path>` 로 교체 — directory 자체의 stat syscall 만 발행, stdout ~200B 고정. liveness check
    intent 동일 (hung mount = timeout, dead mount = exit non-zero).

    v9 R14-HIGH-4 (Retryable 누적 escalation):
    - state_dir 제공 시: 직전 last_failure 의 failed_count 가 MOUNT_RETRYABLE_FATAL_THRESHOLD 이상
      이면 `VaultSyncFatal` 로 escalate (silent abort 차단, ADR-0021 invariant 정합)
    - state_dir=None: 기존 v8 동작 (Retryable only)

    실패 분류:
    - subprocess timeout (5s) → hung FUSE → VaultSyncRetryable (또는 누적 시 Fatal)
    - subprocess exit code != 0 → dead mount (ENOTCONN, ENOENT 등) → VaultSyncRetryable (또는 누적 시 Fatal)
    - subprocess exit code == 0 → mount 살아있음, 정상 return
    """
    try:
        result = subprocess.run(
            ["stat", str(mount_path)],   # v9 R13-HIGH-2 + R14-HIGH-3 — ls -la → stat
            capture_output=True, text=True, timeout=timeout_sec, check=False,
        )
        if result.returncode != 0:
            reason = (
                f"mount path stat 실패 (rc={result.returncode}) — mount.service 미준비/dead: "
                f"{mount_path}, stderr={result.stderr[:200]!r}"
            )
            _raise_mount_failure(vault_id, state_dir, reason)
    except subprocess.TimeoutExpired as e:
        reason = f"mount path stat timeout ({timeout_sec}s) — hung FUSE 가능: {mount_path}"
        _raise_mount_failure(vault_id, state_dir, reason)


def _raise_mount_failure(vault_id: str, state_dir: Path | None, reason: str) -> None:
    """v9 R14-HIGH-4 — Retryable vs Fatal 판단.

    state_dir 가 주어졌고 직전 last_failure 의 failed_count >= THRESHOLD 면 Fatal escalate.
    그 외엔 기존 Retryable (R11-CRIT-2 race 오발화 차단 정합).
    """
    if state_dir is not None:
        prev = load_last_failure(state_dir)
        if prev is not None and prev.get("scope") == "mount":
            prev_count = prev.get("failed_count", 0)
            if prev_count + 1 >= MOUNT_RETRYABLE_FATAL_THRESHOLD:
                # Fatal escalate — last_failure writer 가 ADR-0024 contract 로 발화
                save_last_failure(state_dir, {
                    "vault_id": vault_id,
                    "exit_code": 2,
                    "severity": "fatal",
                    "scope": "mount",           # v9 신규 scope (ADR-0024 본문 minor 갱신)
                    "reason": f"mount Retryable {prev_count + 1}회 연속 누적 — escalate: {reason}",
                    "remediation": (
                        f"systemctl --user status wikihub-mount@{vault_id}.service && "
                        f"systemctl --user reset-failed wikihub-mount@{vault_id}.service && "
                        f"systemctl --user restart wikihub-mount@{vault_id}.service"
                    ),
                    "source_id": None,
                    "first_failed_at": prev.get("first_failed_at", utc_now_iso()),
                    "last_failed_at": utc_now_iso(),
                    "failed_count": prev_count + 1,
                    "alerted_at": None,
                })
                raise VaultSyncFatal(
                    vault_id=vault_id,
                    reason=f"mount permanently failed ({prev_count + 1}회 누적): {reason}",
                    remediation="ops-alert 발화 — 운영자 개입 (Q5 참조)",
                )
    # 기존 Retryable 경로
    raise VaultSyncRetryable(
        vault_id=vault_id,
        retry_after_sec=120,    # v9 R13-MED-1: vault-fetch.py 미사용 진단 메타.
                                # 실제 retry 주기는 systemd OnUnitInactiveSec=600s. v0.2.x 사용 검토.
        reason=reason,
    )


def vfs_refresh(
    vault_id: str,
    rc_addr: str,
    state_dir: Path | None = None,
    recursive: bool = True,
    timeout_sec: int = 120,
) -> None:
    """rclone rc vfs/refresh — 사이클 시작 시 1회 호출 (ADR-0026 K1).

    v9 R13-CRIT-1 — OAuth error 패턴 검사 + VaultSyncFatal 분기 (Q6 alert 체인 정합):
    rclone stderr 에 인증 관련 패턴 매칭 시 `VaultSyncFatal` (mount scope) raise — ADR-0024
    writer 가 last_failure.json 에 영속화 → ops-alert 발화. V18 이 stderr 노출 여부 검증 후
    패턴 refine.

    그 외 실패 → VaultSyncRetryable. 호출자 (vault-fetch.py) 가 exit 75 사이클 abort 처리
    (R11-HIGH-3 — race window 차단 실패 시 stale read 금지).
    """
    payload = "true" if recursive else "false"
    result = subprocess.run(
        ["rclone", "rc", "--rc-addr", rc_addr, "vfs/refresh", f"recursive={payload}"],
        capture_output=True, text=True, timeout=timeout_sec, check=False,
    )
    if result.returncode != 0:
        stderr_snippet = result.stderr[:500]
        # v9 R13-CRIT-1 — OAuth error 패턴 → Fatal (Q6 정합)
        if _RCLONE_AUTH_PATTERNS.search(stderr_snippet):
            if state_dir is not None:
                save_last_failure(state_dir, {
                    "vault_id": vault_id,
                    "exit_code": 2,
                    "severity": "fatal",
                    "scope": "mount",   # v9 — ADR-0024 mount scope (OAuth revoke)
                    "reason": f"rclone OAuth revoked/expired: {stderr_snippet[:200]!r}",
                    "remediation": (
                        f"rclone config reconnect <remote_name> 후 "
                        f"systemctl --user restart wikihub-mount@{vault_id}.service"
                    ),
                    "source_id": None,
                    "first_failed_at": utc_now_iso(),
                    "last_failed_at": utc_now_iso(),
                    "failed_count": 1,
                    "alerted_at": None,
                })
            raise VaultSyncFatal(
                vault_id=vault_id,
                reason=f"rclone OAuth error (pattern matched): {stderr_snippet[:200]!r}",
                remediation="rclone config reconnect <remote_name>",
            )
        # 그 외 → Retryable (race window 차단 실패, 사이클 abort)
        raise VaultSyncRetryable(
            vault_id=vault_id,
            retry_after_sec=120,    # v9 R13-MED-1: 진단 메타
            reason=f"rclone rc vfs/refresh failed: rc={result.returncode}, "
                   f"stderr={stderr_snippet[:200]!r}",
        )
```

`vault-fetch.py` 사이클 시작에 두 호출 sequential — `assert_mount_alive(vault_id, mount_path, state_dir)` → `vfs_refresh(vault_id, rc_addr, state_dir)` → 기존 sync 로직. **v9 시그니처 변경**: `state_dir` 인자 추가 (`vault-fetch.py` 가 state_dir 이미 보유 — line 99~100). 둘 다 `VaultSyncFatal` 또는 `VaultSyncRetryable` raise 가능.

**v9 patch 핵심 의도**:
- **stat 교체** (R13-HIGH-2 + R14-HIGH-3): liveness check 에 파일 목록 불필요. `stat` 은 directory metadata 만 가져옴 → stdout 200B 고정, 대용량 vault 메모리 압박 0
- **OAuth Fatal 분기** (R13-CRIT-1): Q6 잠정 결정 ("vfs_refresh → VaultSyncFatal") 와 spec 코드 정합. ADR-0024 last_failure writer 가 mount scope 로 영속화. V18 이 stderr 노출 패턴을 PoC 후 regex refine
- **Retryable 누적 escalation** (R14-HIGH-4): mount 가 영구 fail 한 상태에서 사이클이 silent abort 로 계속되는 case 차단. 6 사이클 (1시간) 누적 시 Fatal escalate → ops-alert. ADR-0021 acceptance invariant ("사람 개입 없이 자동 재기동") 의 fail mode 가 timely surface
- **ADR-0024 본문 minor 갱신** (옵션 c): `last_failure` schema 에 `scope="mount"` 추가. supersede 아님 — 기존 schema 의 확장. mount-fail-recorder.service 같은 신규 unit 도입 회피

#### 10.4.7 `wikihub-vault@.service.template` patch — mount 의존 추가 + race 처리

> **v8 patch**:
> - **(R11-NIT-1)** 파일명 통일: v6 `vault-ingest.service.template` → **`wikihub-vault@.service.template`** rename (instantiated template `@` 패턴 명시, ADR-0019 Python substitution 정합)
> - **(R11-CRIT-2 + R12-HIGH-5)** mount 시작 race 처리: `assert_mount_alive` 실패 시 §10.4.6 의 `VaultSyncRetryable` (exit 75) 로 처리되므로 service 의 `SuccessExitStatus=0 75` 가 ops-alert 오발화를 차단. 본 §에서 race 시나리오와 systemd 동작을 명시

v6 §4.2 의 `vault-ingest.service.template` 을 **`wikihub-vault@.service.template`** 로 rename 후 patch:

```ini
[Unit]
Description=WikiHub vault ingest — %i
After=network-online.target wikihub-mount@%i.service          # v7 갱신 (mount 후 진입)
Wants=network-online.target
Requires=wikihub-mount@%i.service                              # v7 신규 — mount 죽으면 vault@ 도 stop
OnFailure=ops-alert.service                                    # v6 유지

[Service]
Type=oneshot
WorkingDirectory={instance_root}
Environment=PATH={venv_path}/bin:/usr/bin:/bin
Environment=WIKIHUB_YAML={instance_root}/wikihub.yaml
Environment=GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE={credentials_path}
Environment=RCLONE_RC_ADDR=127.0.0.1:{rc_port_for_%i}          # v7 신규 — mount.py 가 사용
ExecStartPre=/bin/mkdir -p {instance_root}                     # v6 유지 (R10 CRIT-2)
ExecStart={agent_invocation} "{skill_prefix}ingest --vault %i"
SuccessExitStatus=0 75
TimeoutStartSec=15min
```

`Requires=` 의미 — mount 가 죽으면 vault@ 도 자동 stop. timer fire 시점에 mount 가 active 아니면 systemd 가 mount@ 를 trigger (BindsTo 아님이라 vault@ 가 mount restart 를 wait — Step 3 V12 검증 시 정확한 sequencing 확인).

**(v8 R11-CRIT-2 + R12-HIGH-5) mount 시작 race 처리**:
mount@ 의 `Type=simple` 은 rclone 프로세스 시작 시점이 active — FUSE mount 가 실제로 준비된 시점이 아니다. reboot 직후 `OnBootSec=2min` 에 timer 가 fire 할 때 다음 race 가 발생 가능:
- mount@ 가 active (process up) 이지만 FUSE 가 아직 마운트 안 됨
- vault@ ExecStart 가 `assert_mount_alive()` 호출 → ls 가 ENOENT/EIO 또는 5s timeout
- §10.4.6 의 `assert_mount_alive` 가 `VaultSyncRetryable` (exit 75) 로 raise
- service 의 `SuccessExitStatus=0 75` 로 systemd 가 success 분류 → **`OnFailure=ops-alert.service` 미발화** (오발화 차단)
- 다음 timer 사이클 (10min 후) 에 mount@ 가 FUSE 준비 완료 → 정상 진입

**대안 (Step 3 시점에 V12 결과 따라 결정)**:
- (a) 현 spec — `assert_mount_alive` Retryable, ops-alert 오발화 차단 (v8 잠정)
- (b) mount@ 에 `Type=notify` + `ExecStartPost` 로 FUSE 준비 신호 emit. systemd 가 정확한 active 시점 인지 (구현 복잡)
- (c) `OnBootSec` 증가 (예: 5min). 가장 약체. 일반 sync_interval 도 늘어남

v0.1.0 은 (a) 채택. V12 검증 후 race 빈발 시 (b) 로 마이그레이션 — §10.5 Q5 에서 추적.

ADR-0021 (reboot resilience) 본문에 minor 갱신 — "mount.service 도 reboot 후 자동 진입, vault@ 가 mount@ 후에 fire, FUSE 미준비 race 는 assert_mount_alive Retryable 로 흡수" 명시. **mount permanently failed (StartLimitBurst 초과) case 는 §10.5 Q5 — v8 신규 미결**.

**(v9 R14-HIGH-4 — Retryable + Requires silent abort 처리, Q5 회귀 방지)**:

R14-HIGH-4 가 surface 한 문제: `assert_mount_alive` 가 Retryable (exit 75) 만 raise 하면 mount 가 영구 fail 한 상태에서도 매 사이클 silent abort 가 반복 — ADR-0021 acceptance invariant ("OS reboot 후 사람 개입 없이 sync 자동 재기동") 가 깨진 상태가 timely surface 되지 않음. 동시에 systemd 의 `Requires=wikihub-mount@%i.service` 는 mount 가 `failed` 상태일 때 vault@ 를 trigger 시 dependency-failed 로 cancel — 이 경우 `ExecStart` 가 실행조차 안 됨 → mount.py 의 Retryable escalation 도 trigger 안 됨.

v9 spec lock — **2-layer escalation**:

| layer | trigger | 처리 |
|---|---|---|
| **layer 1 (vault@ 가 fire 됨, mount 가 starting/active 이지만 hung)** | `assert_mount_alive` Retryable raise | §10.4.6 `_raise_mount_failure` 가 `state_dir` 의 `last_failure.json` 누적 카운트 ≥ 6 검사 → `VaultSyncFatal` escalate → `OnFailure=ops-alert.service` 발화 |
| **layer 2 (mount 가 failed — `Requires=` cancel 로 vault@ 가 trigger 자체 안 됨)** | mount@ `OnFailure=ops-alert.service` 가 직접 발화. vault@ `ExecStart` 미실행이라 mount.py 미호출 | ops-alert.py 가 §10.4.1 의 fallback diagnostic 경로 — `last_failure.json` 부재 시 `journalctl mount@<vid>.service` tail 을 webhook payload 에 첨부 |

이로써 어느 case 든 운영자가 timely 통지 받음. ADR-0021 acceptance invariant 의 fail mode (mount permanently failed) 가 silent 잔존 차단. Q5 (`§10.5`) 의 운영자 개입 절차 (`systemctl --user reset-failed wikihub-mount@<vid> && systemctl --user restart`) 는 ops-alert webhook 의 `remediation` 필드로 전달.

**vault@ 의 `Requires=` 정합성** — Requires 가 dependency-failed cancel 을 만들지만 이는 의도된 동작 (mount 없이 vault@ 가 돌면 mount path read 실패 보장). cancel 자체는 OK, 단 cancel 의 통지 경로 (layer 2) 가 정합해야 함 — v9 이 그 통지 경로를 명시.

### 10.5 미결 사항 / Step 3 verification (v7 + v8)

| ID | 항목 | Step 2 잠정 결정 | Step 3 확정 |
|---|---|---|---|
| Q1 (v7) | Google native (Docs/Sheets/Slides) export 메커니즘 | 옵션 1 잠정 — rclone `--drive-export-formats markdown` 의 mount 자동 export. `gws files export` 폐기. **v8 sequencing lock (R11-CRIT-1)**: Step 3 진입 즉시 V15a PoC 선행 → Q1 lock → §10.4.3 사이클 흐름 step 4 분기 구조 확정. PoC 실패 시 옵션 2 회귀 + sync.py dual-path 유지 | V15a |
| Q2 (v7) | rclone install 채널 | **v8 lock (R12-HIGH-3)** — GitHub Releases binary + SHA256SUMS verify (`rclone.org/install.sh` 폐기) | V16 — ARM Ubuntu clean instance 에서 SHA verify 통과 + min_version 검증 |
| Q3 (v7) | per-vault rc port 할당 정책 | 잠정 — `wikihub.yaml.vaults.[*].options.rclone_rc_port` 명시 (default 5572 + 순번). **v8 보강 (R12-MED-1)**: install.sh 가 ss 로 port 가용성 pre-check + 사용 중이면 fail-fast | V17 — 2개 vault 동시 mount + rc 응답 충돌 case 검증 |
| Q4 (v7) | vfs_refresh 실패 시 fallback | **v8 lock (R11-HIGH-3)** — `VaultSyncRetryable` (exit 75) → vault-fetch.py 가 사이클 abort. race window 차단 실패 상태에서 stale read 진행 금지 (ADR-0026 가정 보장) | V14·V15 결과 후 확정 |
| **Q5 (v8 → v9 갱신)** | **mount@ permanently failed + Retryable 누적 silent abort — 2-layer escalation 정합** (R11-HIGH-4 + R14-HIGH-4) | **v9 lock** — layer 1: vault@ 사이클 중 `assert_mount_alive` 가 Retryable 6회 누적 시 `mount.py` 의 `_raise_mount_failure` 가 Fatal escalate → ADR-0024 last_failure (scope="mount") writer 호출 → vault@ OnFailure → ops-alert. layer 2: mount@ 가 `Requires=` cancel 로 vault@ 미실행 시 mount@ `OnFailure` 가 직접 ops-alert 발화 + ops-alert.py 의 fallback diagnostic (journalctl tail) 첨부. 운영자 개입: `systemctl --user reset-failed wikihub-mount@<vid> && systemctl --user restart wikihub-mount@<vid>`. ops-alert webhook payload 의 `remediation` 필드로 전달. 자동 복구는 v0.2.x | V14 (layer 1 Retryable escalation 검증) + V19 신규 (layer 2 dependency-failed 통지) |
| **Q10 (v9)** | **vfs cache directory stale binary 정책** (R14 MED — `_handle_removed` unlink 제거 후 vfs cache 의 캐시된 binary 가 stale 잔존 가능성) | **v9 잠정** — rclone vfs cache 는 `--dir-cache-time 5m` 후 dir listing 갱신 시 자동 invalidate. 추가 검증으로 V15-cost (10k 파일) 후 vfs cache directory size 가 vfs_cache_max_size 한도 내인지 측정. cache LRU eviction 동작 확인 | V15-cost 보강 |
| **Q11 (v9)** | **gws v0.x breaking change runtime assert** (R14 MED-4 — Q8 의 운영 매뉴얼 보강) | **v9 잠정** — `lib/gws.py` 의 `run_gws` 응답 처리에 schema sanity check 추가 (예: `changes.list` 응답의 `nextPageToken` / `changes` 키 부재 시 `VaultSyncFatal`). v0.1.0 minimal — 핵심 key 부재만 detect. v0.2.x 에서 jsonschema 도입 | Step 3 보강 (V4 의 errors.py refine 시) |
| **Q12 (v9)** | **V14 hung mount 시뮬레이션 환경 — `tc qdisc` 권한** (R14 MED — OCI ARM free tier 에서 CAP_NET_ADMIN 가능 여부) | **v9 잠정** — OCI ARM free tier 는 sudo + tc 가능. dev box (macOS) 에서는 직접 시뮬레이션 불가 — `pfctl` 또는 docker container 우회. V14 verification 절차에 환경 분기 명시 | V14 실수행 환경 lock |
| **Q13 (v9)** | **V15-cost 60s 임계 근거** (R14 LOW — `TimeoutStartSec=15min` 대비 안전 여유 산정) | **v9 잠정** — 15min 의 4% (60s = 900s × 6.6%) 가 vfs/refresh share 한도. 60s 초과 시 K2 마이그레이션 검토 (per-file refresh 로 cycle latency 감소). 측정 환경 (vault 파일 수 · 네트워크 latency · CPU) 명시 매뉴얼 | V15-cost 측정 절차 |
| **Q6 (v8)** | **rclone OAuth revoke 감지 + ops-alert 경로** (R12-HIGH-4) | **v8 잠정** — `vfs_refresh` 또는 mount.service log 의 OAuth error (rclone exit 인증 관련 패턴: "Token expired", "invalid_grant", "401") 감지 시 `VaultSyncFatal` → ADR-0024 last_failure writer 가 발화. revoke 패턴 regex 는 V14 또는 별도 V<N> 으로 검증. v0.1.0 은 rclone stderr 의 raw 첫 500자 보존 (gws errors.py 패턴과 정합) | Step 3 V14 보강 또는 V18 신규 |
| **Q7 (v8)** | **OCI free tier (45GB) 디스크 가이드 — vfs cache + venv + Python deps + vault local + logs 합산이 안전한가** (R12-HIGH-1) | **v8 잠정** — `vfs_cache_max_size: 10G` (yaml default). 운영 매뉴얼에 안전 한도 (예: max 30G — Ubuntu OS 10G + venv·deps 5G + vault local 5G + vfs cache 10G) 명시. disk-watch (v6 §4.6 deferred) v0.2.x 와 정합 — disk fill alert 메커니즘 | V8 + 운영 매뉴얼 + disk-watch v0.2.x 통합 |
| **Q8 (v8)** | **gws v0.x breaking change silent stale** — gws 가 breaking change 후 changes API 응답 schema 변경 시 detection 부재 (R12-MED-4) | **v8 deferred to v0.2.x** — `lib/gws.py` 에 schema validation 추가 (response key 검증). v0.1.0 은 `wikihub.yaml.operations.gws_min_version` + `gws_max_version` 추가로 운영자 수동 추적 (`gws --version` 비교) | v0.2.x — schema validation feature |
| **Q9 (v8)** | **multi-vault 동시 부팅 시 vfs warming contention** (R12-LOW-1) | **v8 deferred to v0.2.x** — vault 1개 (default) 시 비관여. multi-vault 운영 시 `OnBootSec` 을 vault 순번별로 stagger (예: 2min, 3min, 4min) — Python substitution helper 가 처리. v0.1.0 단일 vault 가정 | v0.2.x — multi-vault 운영 feature |

### 10.6 V<N> 갱신 + 신규

#### 10.6.1 V12 갱신 (mount.service 의존)

**v6 V12**: "OS reboot 후 사람 개입 없이 sync 자동 재기동 + timer `Persistent=true` catch up"

**v7 갱신**: "OS reboot 후 사람 개입 없이 (1) `wikihub-mount@<vid>.service` 자동 진입 + mount path 정상 마운트, (2) `wikihub-vault@<vid>.timer` 자동 fire (`Persistent=true` catch up), (3) `assert_mount_alive` + `vfs_refresh` 통과 후 첫 사이클 정상 완료 + last_sync.json 진행"

#### 10.6.2 신규 V<N>

| ID | 항목 | 방법 | 영향 |
|---|---|---|---|
| V13 | rclone mount 가 vault 폴더에 정상 마운트 + SSH ls/cat 가능 | OCI ARM Ubuntu 22.04 LTS clean instance. `systemctl --user start wikihub-mount@gdrive` 후 `ls /vault/gdrive/` + 임의 파일 `cat` (size > 1KB 텍스트). **폴더 하위 파일도 포함** (§10.4.3 `_resolve_mount_path` flat lock 의 v0.1.0 한계 확인) | 사용자 입력 채널 충족 (Path C+ acceptance) |
| **V14** | mount.service Restart=always 자동 복구 + **hung mount 감지** | (a) 의도적 `kill -9 <rclone pid>` 후 30s 내 재기동 + vault 폴더 접근 복구. (b) **hung mount 시뮬레이션 — `tc qdisc add dev eth0 root netem delay 30s` 로 Drive API 지연 유발 후 `assert_mount_alive()` 가 5s 내 `VaultSyncRetryable` raise + exit 75 + ops-alert 미발화 확인** (v8 R11-HIGH-1). (c) 5회/5min 초과 시 fail + mount@ `OnFailure=ops-alert.service` 발화 확인 (R12-CRIT-1) | 장애 격리 + hung block 차단 |
| **V15** | **race window 차단 — `vfs/refresh` 응답 완료 후 mount read 가 fresh content** (v8 deterministic 기준) | **(v8 R11-LOW-1)** 결정론적 기준: Drive 에서 파일 X 의 content 수정 → wait 30s (Drive propagation 보수) → `rclone rc vfs/refresh recursive=true` 호출 + **응답 완료 wait** → mount read → content 가 fresh. 비교 baseline 으로 refresh 없이 read 시 stale content 도 확인. **(v8 R12-NIT)** 환경: OCI ARM Ubuntu 22.04, vault 1개, vfs cache full mode | **v7 핵심 — 정합성 정본 (ADR-0026 회귀 방지)** |
| **V15-cost (v8)** | **`vfs/refresh recursive=true` 의 비용 측정 — vault 규모별 latency** (R12-HIGH-2) | vault 파일 수 1k / 5k / 10k 케이스 각각에 대해 `time rclone rc vfs/refresh recursive=true` 측정 (3회 평균). 10k 파일에서 응답 < 60s 이면 vault@.service `TimeoutStartSec=15min` 안전 한도. 60s 초과 시 K2 (per-file refresh) 마이그레이션 가속 또는 yaml `vfs_refresh_mode: per-file` 옵션 활성화 검토 | ADR-0026 K1 채택 정당성 |
| V15a | Google native export 품질 — rclone vs gws | 동일 Docs/Sheets 파일을 두 경로로 export → markdown 변환 결과 비교 (frontmatter·heading·table 구조 보존도). **Step 3 진입 즉시 선행** (R11-CRIT-1 sequencing) | Q1 결정 lock |
| V16 | rclone version pinning + **SHA256SUMS verify** (v8) | ARM Ubuntu clean 에서 install.sh 실수행 → GitHub Releases 다운로드 + `sha256sum -c` pass + rclone 정상 동작 + `rclone version` 이 min_version~max_version 범위. **SHA verify 실패 시 install.sh fail-fast 도 확인** (artifact tamper 시뮬레이션 — `/tmp/<archive>` 의 1byte 변조 후 재시도) | install.sh 안정성 + supply chain (ADR-0025 회귀 방지, R12-HIGH-3) |
| V17 | per-vault rc port 충돌 case | (a) 2개 vault 동시 mount (`wikihub-mount@gdrive` + `wikihub-mount@gdrive2`) → 각 rc 응답 정상 + port 5572·5573 listen 확인. (b) **port 5572 가 다른 프로세스에 사용 중일 때 install.sh 의 `_check_rc_port_available` 가 fail-fast 확인** (v8 R12-MED-1) | rc port 정책 lock (Q3) |
| **V18 (v8)** | **rclone OAuth revoke 감지 — Q6 (R12-HIGH-4)** | Google Cloud Console 에서 rclone OAuth client 의 token revoke → 다음 사이클의 `vfs_refresh` 호출 → rclone stderr 에 인증 관련 패턴 출현 → vault-fetch.py 가 `VaultSyncFatal` raise → ADR-0024 last_failure writer 가 ops-alert 발화. revoke stderr 패턴 regex 본 검증에서 lock (errors.py 패턴 표 갱신) | Q6 lock (ADR-0024 통합) |

### 10.7 신규 ADR 발의 목록 (v7 추가)

v6 §7 의 ADR 9건 모두 유지 (supersede 없음). v7 추가 3건:

| ID | Title | 본 단계 status | 정본화 시점 |
|---|---|---|---|
| **ADR-0025** | **rclone mount 채택 — vault 자체에 마운트 + `--vfs-cache-mode full` + `--rc` 활성화 + 설치 채널 (GitHub Releases binary + SHA256SUMS verify + curl retry, v9 R13-HIGH-1 + R14-HIGH-1)** | Accepted (본 v7) | V13·V16 회귀 방지 |
| **ADR-0026** | **vfs refresh 정책 — 사이클 시작 시 `vfs/refresh recursive=true` 1회 (K1 채택, K2/K3 deferred to v0.2.x)** | Accepted (본 v7) | V15 회귀 방지 |
| **ADR-0027** | **rclone vs gws 책임 분리 — Path C+ 정본화 (rclone = mount/다운로드/UX, gws = changes API). ADR-0014 supersede 없음. Cross-references: ADR-0006 (unified orchestration) — `vault-fetch.py` 외부 인터페이스 무변경, subprocess 패턴 확장 (gws + rclone rc), ADR-0006 supersede 없음 (v8 R11-MED-3 명시)** | Accepted (본 v7) | F3 sync.py 재사용도 ~90% 회귀 방지 + ADR-0014·ADR-0006 supersede 부재 명문화 |
| **ADR-0024 (v9 본문 minor 갱신, supersede 아님)** | **fatal 알림 contract — last_failure.json schema 에 `scope="mount"` 추가** (v9 R14-CRIT-1 + R13-CRIT-1 + R14-HIGH-4 흡수). writer 확장: `mount.py` 의 `_raise_mount_failure` + `vfs_refresh` 가 OAuth Fatal 시 직접 호출. reader (ops-alert.py) 는 scope 분기 없음 — 동일 payload 형식. mount scope 의 fallback diagnostic 책임은 §10.4.1 본문 명시 (journalctl tail) | Accepted (v9 본문 갱신) | R14-CRIT-1 silent dead 차단 회귀 방지 |

**총 12건**. ADR-0014 (gws CLI) supersede 없음 — v2 의 reversal 결정이 v7 에서도 유효. ADR-0021 (reboot resilience) 본문은 mount.service 의존 추가로 minor 갱신 (supersede 아님).

### 10.8 Definition of Done — v7 단계

v6 §8 의 DoD 모두 유지. v7 추가:

**Step 2 v7 단계**:
- [ ] 본 문서 v7 사용자 검토 + 결정 [J]·[K]·[L] 합의 → 상단 `**상태**: v7 approved YYYY-MM-DD`
- [ ] 멀티모델 design review v7 라운드 — R11·R12 (mount unit · vfs refresh · 책임 분리 · sync.py 다운로드 헬퍼 교체) 완료 → `design_review_5.md`·`design_review_6.md`
- [ ] 신규 ADR 3건 (0025·0026·0027) `docs/adr/` 파일 작성

**Feature 전체 v7/v9 (Step 5 완료 기준, v9 갱신 — R13-MED-3 처리)**:
- [ ] **V13·V14·V15·V15-cost·V16·V17·V18·V19 모두 통과 + V12 갱신 통과** (v9: V15-cost · V18 추가, v9 신규 V19 = layer 2 dependency-failed 통지)
- [ ] V15a 결과로 Q1 (Google native export) 결정 lock
- [ ] V18 결과로 Q6 (rclone OAuth revoke 감지) 패턴 regex lock + §10.4.6 `_RCLONE_AUTH_PATTERNS` refine
- [ ] V15-cost 결과로 ADR-0026 K1 채택 정당성 lock (10k 파일 < 60s)
- [ ] ADR-0025·0026·0027 Status=`Accepted` + **ADR-0024 본문 v9 minor 갱신 (mount scope) 반영**
- [ ] Step 4 v9 멀티모델 code review (R15·R16) 결함 모두 처리 — CRIT·HIGH 0건
- [ ] HISTORY.md 항목 갱신 + ADR 참조 (0025·0026·0027 추가 + 0024 minor 갱신 명시) + archive 이동

---

## 11. V8 surgical fix — Python runtime 재설계 (2026-05-17 KST, ADR-0028)

V8 1차 실수행 (Multipass Ubuntu 22.04.5 LTS aarch64) 에서 surface 된 결함 5건 중 **#1 (python3-venv 미감지)** 과 **#2 (venv 부분 생성 idempotency)** 의 fix. 본 섹션은 결함 #3·#4·#5 의 fix 와는 분리 — 별도 surgical patch 로 진행.

### 11.1 결함과 fix 매핑

| # | 결함 | fix 위치 | fix 방식 |
|---|---|---|---|
| 1 | `python3-venv` 미감지 — Step 3 venv 생성 fail | `install.sh:_step1_env_check` (`install.sh:171~179`) | Python binary 검증 제거 (uv 가 자체 Python install). `unzip` 검증 + 자동 apt install 같이 추가 (결함 #5 동일 위치 fix) |
| 2 | venv 부분 생성 후 재실행 시 `bin/pip` 부재 | `install.sh:_step3_venv` (`install.sh:234~256`) | `uv venv --seed` 의 자체 idempotency 활용. `[ -d ]` 분기 제거 |

### 11.2 산출물 spec

| 파일 | 변경 |
|---|---|
| `docs/adr/0028-uv-python-runtime.md` | 신규 — uv 단독 + GitHub Releases binary + Python 3.12 pinned + UV_VERSION=0.11.14 |
| `docs/adr/README.md` | ADR-0028 행 추가 (Status: Proposed → V8 재검증 통과 후 Accepted) |
| `install.sh` env var section | `UV_VERSION="0.11.14"`, `PYTHON_VERSION="3.12"` 추가 |
| `install.sh:_step1_env_check` | `python3*` binary 검증 제거 + `unzip` 자동 install |
| `install.sh:_install_uv` (신규) | gws/rclone 패턴 일관 — GitHub Releases binary + SHA256 verify + tar 추출 + `$GWS_BIN_DIR/uv` install + PATH 추가 (현 셸 export 포함, V8 결함 #4b 회귀 방지) |
| `install.sh:_step3_venv` 재작성 | `_install_uv` → `uv python install $PYTHON_VERSION` → `uv venv --seed` → `uv pip install -r scripts/requirements.txt` |
| `features/20260514_install_runtime/progress.md` | V8 결함 표에 fix 진입 상태 표시 (결함 #1·#2) |

### 11.3 영향 받지 않는 산출물

- `scripts/requirements.txt` 본문 — pip 호환 그대로 (uv pip 가 동일 포맷 read)
- `scripts/lib/*.py` — Python 3.12 호환 검증은 V8 재검증 시 자연 surface (`uv pip install` 통과 = wheel 호환 OK)
- `_system/systemd/*.template` — `ExecStart=$VENV_PATH/bin/python` 패턴 그대로 (uv venv 결과물도 동일 layout)
- `wikihub.yaml.example` — uv/python 관련 키 추가 없음 (install.sh env var 로 충분, yaml 노출 불필요)

### 11.4 V8 재검증 DoD

- [ ] clean Ubuntu 22.04 ARM64 (`python3-venv` 미설치) 에서 `install.sh` Step 3 통과
- [ ] `uv --version` = `uv 0.11.14`
- [ ] `$VENV_PATH/bin/python --version` = `Python 3.12.x`
- [ ] `$VENV_PATH/bin/python -c "import pdfminer, pptx, markdownify, yaml"` 통과
- [ ] 두 번째 호출 (idempotency) — Step 3 통과 (`bin/pip` 부재 회귀 없음)
- [ ] 결함 #3·#4·#5 surface 또는 그 이후 Step 으로 진입

V8 재검증 통과 시 ADR-0028 Status `Proposed → Accepted` 전환.

---

## 12. V<N> Phase 2 진입 — Service Account 전환 (2026-05-17 KST, ADR-0029)

V8 acceptance gate 통과 후 V<N> Phase 2 (V13~V19) 진입 시점에 OAuth (ADR-0003) 모델의 운영 부담 surface. 본 §은 ADR-0003 → ADR-0029 (Service Account) 전환의 산출물 spec.

### 12.1 동기

| 항목 | ADR-0003 (기존) | ADR-0029 (신규) |
|---|---|---|
| 인증 mechanism | OAuth (user-token, refresh token) | Service Account (JSON key) |
| Workspace 마이그레이션 | 필수 (Personal Testing 모드 7일 refresh 만료 회피) | 불필요 (Personal Google 도 SA 사용 가능) |
| Token 발급 위치 | macOS dev box `flow.run_local_server()` 1회 + scp | Google Cloud Console JSON 다운로드 + scp |
| 권한 모델 | user-token = ownedByMe 전체 접근 | SA 가 명시 공유받은 폴더만 |
| revoke 감지 | OAuth token 재발급 (Google 계정 패스워드 변경 등) | Cloud Console SA 키 revoke (명시적) |
| V18 (revoke 감지) 검증 | Google 계정 패스워드 변경 시뮬레이션 (interactive) | Cloud Console SA 키 disable 1클릭 (automation 친화) |

### 12.2 산출물 spec

| 파일 | 변경 |
|---|---|
| `docs/adr/0029-service-account-auth.md` | 신규 — Status: Proposed → V<N> Phase 2 검증 후 Accepted |
| `docs/adr/0003-headless-oauth-strategy.md` | Status: Accepted → Superseded by ADR-0029. 본문 보존 (역사적 맥락) |
| `docs/adr/README.md` | 인덱스 갱신 — ADR-0003 Superseded + ADR-0029 추가 |
| `scripts/lib/credentials.py` | `assert_credentials` 의 `type` 검증 `authorized_user → service_account`. required: `private_key`, `client_email`. error 메시지 + remediation 갱신 |
| `scripts/lib/gws.py` | 변경 없음 (`env_extra` 로 `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` 그대로) |
| `scripts/auth_gdrive.py` | **제거** — OAuth flow 도구. SA 시 불필요 (Cloud Console UI 발급) |
| `_system/commands/setup.md` Step 5.5 | rclone OAuth interactive 11단계 → SA 사전 준비 5단계 (Cloud Console + 폴더 공유) + `rclone config create ... service_account_file=...` 1줄. Non-interactive 빠른 등록 권장. |
| `wikihub.yaml.example` | `credentials_path` 주석 — OAuth token → SA JSON key. `root_folder_id` 의미 변경 — SA 채택 후 명시 필수 |

### 12.3 V<N> Phase 2 진입 조건 (메인테이너 사전 작업)

본 SA 전환 commit 직후 메인테이너가 수행:

1. **Google Cloud project** — 기존 OAuth client 의 project 재사용 또는 신규 project 생성.
2. **Drive API 활성화** — Cloud Console → APIs & Services → Library → "Google Drive API" → Enable.
3. **SA 생성** — IAM & Admin → Service Accounts → "Create" → SA 이름 (예: `wikihub-vault`) + role 없음 (Drive 폴더 공유로 권한 부여).
4. **SA 키 발급** — Service Accounts → 본 SA → Keys → "Add Key" → "Create new key" → JSON → 다운로드 (e.g., `sa_gdrive.json`).
5. **SA 키 로컬 보관 (메인테이너 Mac)** — repo working tree 외부 격리:
   ```bash
   mkdir -p ~/.credentials/wikihub
   chmod 0700 ~/.credentials ~/.credentials/wikihub
   mv ~/Downloads/<project>-<hash>.json ~/.credentials/wikihub/sa_<project>.json
   chmod 0600 ~/.credentials/wikihub/sa_<project>.json
   ```
   **반드시 repo 외부 디렉토리에 둘 것.** `.gitignore` 패턴 (`gen-lang-client-*.json` 등) 은 안전망이지만 의존 금지. 메인테이너 가이드 §1 "Separation of Concerns" 정합 (Development zone 분리).
6. **Drive 폴더 준비** — Google Drive (Personal 또는 Workspace 무관) 에 vault 폴더 (예: `wikihub-test/`) + sample 파일 (`note.md`, `doc.gdoc`, `sheet.gsheet` 등). 폴더 ID 추출 (URL `https://drive.google.com/drive/folders/<ID>` 의 `<ID>`).
7. **SA 공유** — vault 폴더 UI → "Share" → SA 이메일 (`<sa>@<project>.iam.gserviceaccount.com`) **Editor** 부여.
8. **SA 키 scp (메인테이너 Mac → 운영 VM/서버)**:
   ```bash
   ssh <vm> 'mkdir -p ~/wikihub-instance/.credentials && chmod 0700 ~/wikihub-instance/.credentials'
   scp ~/.credentials/wikihub/sa_<project>.json <vm>:~/wikihub-instance/.credentials/sa_gdrive.json
   ssh <vm> 'chmod 0600 ~/wikihub-instance/.credentials/sa_gdrive.json'
   ```
   운영 측 파일명 `sa_gdrive.json` 는 yaml 의 `credentials_path` 와 정합. 메인테이너 로컬은 `sa_<project>.json` (여러 project 공존 가능), 운영 VM 은 `sa_<vault_id>.json` (vault 별 SA 1:1).
9. **wikihub.yaml 편집** (운영 VM) — `credentials_path: ~/wikihub-instance/.credentials/sa_gdrive.json` + `root_folder_id: <ID>` + `enabled: true` + `bootstrap_allowed: true`.

### 12.4 V<N> Phase 2 검증 범위 (SA 전환 후)

| ID | 항목 | SA 전환의 영향 |
|---|---|---|
| V4 | gws stderr 실패 패턴 (403/401/5xx) | SA 도 동일 stderr — `lib/errors.py` regex 변경 없음 예상 |
| V10 | systemd unit 동작 | 변경 없음 |
| V12 | reboot resilience | 변경 없음 (linger ✅ + mount/timer 자동 진입) |
| V13 | rclone mount + ls/cat | rclone SA 동작 검증 (`rclone lsd` + mount + `ls /vault/gdrive/`) |
| V14 | mount Restart=always + hung mount 감지 | 변경 없음 |
| V15 | race window 차단 (vfs/refresh) | 변경 없음 (gws changes API 정본) |
| V15-cost | vfs/refresh latency | 변경 없음 |
| V15a | Google native export 품질 (rclone vs gws) | SA 채택 후 두 도구 모두 동일 SA — export 결과 비교 fair. **2026-05-17 1차 surface**: rclone mount + `vfs-cache-mode full` 의 Google native silent fail (read=0). 진단 후 fix lock → §13 |
| V17 | per-vault rc port 충돌 | 변경 없음 |
| **V18** | **rclone OAuth revoke 감지** → "SA 키 revoke 감지" 로 의미 갱신 | Cloud Console SA 키 disable → rclone stderr 패턴 → `_RCLONE_AUTH_PATTERNS` 매칭. SA 의 revoke 패턴 별도 hand-check 필요 |
| V19 | layer 2 dependency-failed 통지 | 변경 없음 |

### 12.5 DoD (Phase 2 acceptance)

- [ ] ADR-0029 본문 + ADR-0003 Superseded 처리 commit
- [ ] credentials.py + setup.md Step 5.5 + wikihub.yaml.example surgical 갱신
- [ ] `scripts/auth_gdrive.py` 제거
- [ ] 메인테이너 사전 작업 8단계 완료 (Cloud Console + SA + Drive 공유 + scp)
- [ ] V13~V19 + V4·V10·V12·V15-cost·V15a·V17 검증 통과
- [ ] V18 의 SA revoke 패턴 확정 → `_RCLONE_AUTH_PATTERNS` regex refine (필요 시)
- [ ] ADR-0029 Status `Proposed → Accepted`

## §13 V15a fix lock — vfs-cache-mode minimal + drive-export-formats 명시 (2026-05-17)

### 13.1 결함 surface + 진단

V<N> Phase 2 1차 실수행 (Multipass `wikihub-test-clean` + SA `oci-hermes-sa@...` + Drive `wikihub-test` 폴더 + sample 4 파일) 에서 V15a 검증 시도 중:

- `cat $MOUNT/test.docx` → 0 bytes
- `rclone copy gdrive:test.docx /tmp/` → 6502 bytes 정상
- mount log error 없음 — **silent fail**

옵션 (b) `--vv` 진단 채택. 동일 mount path + 동일 SA + `--drive-export-formats docx,xlsx,pptx,md` 명시 + `--log-level DEBUG` 하에 `--vfs-cache-mode` 만 교체:

| vfs-cache-mode | test.docx | test.xlsx | test.pptx | V15_renamed.md |
|---|---|---|---|---|
| full (ADR-0025 v9 β3) | **0 ❌** | **0 ❌** | **0 ❌** | 25739 ✅ |
| minimal (β2) | 6502 ✅ | 5035 ✅ | 32119 ✅ | 25739 ✅ |
| off (β1) | 6502 ✅ | — | — | — |

`full` mode debug log 의 `test.docx` read 경로:
```
Lookup → Attr size=0 → Open → newRWFileHandle → Read len=131072 → _readAt n=0, err=EOF (즉시)
```
- `export` / `vnd.google` keyword 로그 **부재** — Google native export trigger 자체 없음.
- RWFileHandle path 가 lookup size=0 (Google native unknown) 을 신뢰하여 backend export 호출 없이 EOF.

### 13.2 Root cause + fix 결정

**Root cause (rclone v1.69.1)**: `--vfs-cache-mode full` 의 RWFileHandle 가 lookup size=0 short-circuit. `rclone copy` 의 별도 path (`backend.Copy` → 직접 `backend.Open`) 와 코드 분기.

**fix lock**:
- ADR-0025 의 `(β)` 결정 β3 → β2 변경 (cache mode `full` → `minimal`).
- `--drive-export-formats docx,xlsx,pptx,md` 명시 보강 (backend export call 시 적용).
- ADR-0025 본문 minor 갱신 + V15a 진단 근거 추가.

**trade-off (minimal vs full)**:
- minimal: 작은 read 매번 fetch (.md frontmatter, 작은 file metadata) — Drive API quota + latency 증가 (수십 ms). wikihub 의 read 패턴 (extraction.py 1회 변환 + Hermes 검색 frequent) 정합 — 영향 미미.
- minimal 도 큰 read (>= chunk size, default 128MiB) 는 캐시 → 큰 binary 파일 효과 유지.
- `vfs_cache_max_size` 정책은 큰 파일 한도로만 의미.

### 13.3 정본 변경 범위 (surgical)

| 파일 | 변경 |
|---|---|
| `_system/systemd/wikihub-mount@.service.template` | `--vfs-cache-mode full` → `minimal`. `--drive-export-formats docx,xlsx,pptx,md` 추가. 주석 갱신 (β2 + V15a). |
| `docs/adr/0025-rclone-mount-adoption.md` | (β) 결정 β3 → β2 + V15a 진단 근거 + Consequences 갱신 (vfs cache full silent fail 결함). Status `Accepted` 유지. |
| 본 §13 | V15a fix lock 기록 |

### 13.4 재검증 항목 (VM 에서 minimal mode 재기동 후)

- [ ] mount + ls 4 파일 정상 (size 표시는 변하지 않음 — Google native -1)
- [ ] cat test.docx / test.xlsx / test.pptx 각각 6502 / 5035 / 32119 bytes
- [ ] V15 (race window) — rename + vfs/refresh 후 mount 갱신 정합
- [ ] V15-cost — vfs/refresh latency 변화 측정 (minimal mode 에서 dir cache 만 활용 — 영향 작음 예상)

§12.4 의 V15a 행 + §12.5 의 DoD 의 V15a 항목은 본 §13 의 재검증 항목 통과로 처리.
