# Design Review 1 — OAuth 통일 + gws 폐기 (rclone 단독)

- **Reviewer**: Claude (Opus 4.7, 1M context) — 컨텍스트 초기화 후 설계 정합 단독 리뷰
- **Date**: 2026-05-19
- **Scope**: plan.md + analysis_and_design.md + ADR-0035 + 5건 supersede ADR + README.md 인덱스
- **리뷰 관점**: 결정 논리 정합성 / cascade 일관성 / 누락 ADR 영향 / 미결 처리 / DoD / 장기 합리성

---

## 종합 평가 사전 요약

- **결정의 근본 논리 (SA 폐기 + gws 폐기 + lsjson 단일화)** 는 견고함. 2026-05-19 OCI 실증 (lsjson 의 ID·MimeType 노출 + Personal Drive SA storageQuotaExceeded) 가 두 결함을 정확히 짚고, ADR-0027 §L1 4개 기각 사유를 ADR-0035 §재평가 표에서 점 단위로 해체한 논리도 닫혀 있음.
- 단 **인접 ADR (ADR-0026 K1 cycle 순서, ADR-0024 v9 mount scope writer) 와의 정합 모순** 이 한 건 존재하고, **백로그 §I·§D 인용의 출처 불일치** (실제 `features/backlog.md` 에 §I·§D 라벨 부재), **state migration 책임의 분산** (ADR §Decision vs §Note vs DoD) 등 정합성 손상 항목이 surface 함.
- DoD 의 운영 검증 항목 일부가 §3.1 변경 매트릭스보다 약함 (특히 rename 정확성·false-delete 가드 발화 회귀 테스트 누락).

전반적으로 **결정 자체는 invariant — 단 cascade·인용·운영 detail 의 정밀화 필요**.

---

## 결함 목록 (등급 순)

### CRIT — 결정 자체 무효 위험

**없음.**

본 ADR 의 결정 (rclone 단독 + OAuth 단일 + lsjson + source_id 키 + cursor 폐기 + false-delete 가드) 6개 sub-decision 은 모두 2026-05-19 OCI 실증으로 뒷받침되고, ADR-0027 §L1 기각 사유 4개의 해체 논리가 등가 대체 가능 (deleted = listing 밖, renamed = ID stable, catch-up = full snapshot, cursor 정확성 = diff 정확성) 으로 닫혀 있음.

---

### HIGH — 정합성 손상 (수정 권고)

#### H1. ADR-0026 K1 cycle 순서와의 정합 모순 — supersede 또는 §Note 갱신 누락

**위치**: `docs/adr/0026-vfs-refresh-policy.md` §"vault-fetch.py 사이클 순서 (v9)" L52-58

**문제 진단**:

ADR-0026 §Decision L52-58 이 cycle 순서를 명시:

```
1. assert_mount_alive ...
2. vfs_refresh(vault_id, rc_addr, ...) — race window 차단
3. gws drive changes list --params {pageToken: cursor} — 변경 감지 (v6 유지)
4. 각 변경 file 별: _resolve_mount_path() → ...
5. cursor 저장, last_sync 갱신
```

본 ADR-0035 가 step 3 (gws changes list) 와 step 5 (cursor 저장) 를 폐기하지만 **ADR-0026 자체는 supersede 또는 §Note 갱신 대상에서 빠짐**. ADR-0026 §Status 는 `Accepted`, Superseded by `없음`. 결과 ADR-0026 §Decision 본문이 ADR-0035 와 직접 충돌 (cycle 의 step 3·5 가 폐기됐는데 ADR-0026 은 그대로).

추가로 ADR-0026 §Cross-references L98 가 ADR-0027 을 참조 — ADR-0027 supersede 후 dangling.

**파급 영향**:
- §"race window" 의 정의 자체가 변경됨: Before = "gws 알림 ↔ mount stale". After = "lsjson 결과의 mtime ↔ mount read content". race 가 여전히 존재하나 그 정의가 달라짐 — vfs_refresh 가 lsjson 호출 **이전** 인지 **이후** 인지 결정 필요.
- ADR-0035 §책임 매트릭스 (L100-108) 가 `rclone lsjson` 책임만 명시 + `vfs_refresh` 도 그대로 유지 가정인데, ADR-0026 의 cycle 순서가 폐기됨에 따라 vfs_refresh 호출 timing 의 정본이 사라짐.

**권장 수정**:

1. ADR-0035 §"Cross-references" 의 "무관·정합 유지" 명단에서 ADR-0026 을 **부분 갱신 대상** 으로 분리. 또는
2. ADR-0026 에 **`Note (2026-05-19, ADR-0035 cascade)`** 섹션 추가 — cycle 순서 step 3 (gws) → step 3' (lsjson) 으로 갱신, step 5 (cursor 저장) → step 5' (file_map 저장) 으로 갱신. race window 정의도 lsjson context 로 재서술. Status 는 `Accepted` 유지 (Decision 본문 minor 갱신 패턴, ADR-0024 v9 minor 와 동일).
3. analysis_and_design.md §6.2 "무관·정합 확인된 ADR" 의 ADR-0026 항목 (L409) 도 "그대로. lsjson 은 backend 직접 호출이라 vfs cache 무관" 으로 적었지만 **vfs_refresh 가 lsjson 호출 전/후에 호출되는지** 의 timing 의문은 미해소 — 본문 보강.

#### H2. 백로그 §D·§I 라벨 인용 출처 불일치

**위치**:
- `docs/adr/0035-rclone-only-unified-oauth.md` §Context L11 "백로그 §D·§I"
- `docs/adr/0035-rclone-only-unified-oauth.md` L15 "백로그 §D 근본 원인"
- `docs/adr/0035-rclone-only-unified-oauth.md` L26 "백로그 §I"
- `docs/adr/0035-rclone-only-unified-oauth.md` L210 "백로그 §D·§I"
- `plan.md` L5 "`features/backlog.md` §I"
- `plan.md` L9 "이슈 D"
- `analysis_and_design.md` L15 "**이슈 D** (백로그)"
- `analysis_and_design.md` L18 "**이슈 I** (백로그)"

**문제 진단**:

`features/backlog.md` 의 실제 구조에는 `§D`·`§I` 라벨이 **존재하지 않음**:

- `## F4 install_runtime 산출` 의 결함 표는 `#A`·`#B`·`#C`·`#D`·`#E`·`#F`·`#G`·`#12` 형식 (테이블 row identifier)
- `#D` 는 "install update — update 후 service template 자동 redeploy" 로 **이미 update_mode 로 closed** (2026-05-17)
- `§I` 라벨도 부재 — `#12` 가 "agent integration" 이고 `#G` 가 "rclone mount" 임

본 ADR·plan·analysis 의 "백로그 §D·§I" 인용은 backlog.md 와 매칭 안 됨. 실측 결함 (SA storageQuotaExceeded, changes feed 단절) 의 출처가 **backlog.md 가 아니라 별도 운영 진단 채널** 인 것으로 보이나 명시 부재.

**파급 영향**:
- 6개월 후 archive 리뷰 시 reader 가 backlog.md 의 §D·§I 를 찾지 못함 — 결정 근거 추적 실패.
- 본 ADR §Cross-references 의 "계기 백로그" 인용 자체가 dead link 와 등가.

**권장 수정**:

옵션 1 (선호): backlog.md 에 본 결함 surface 항목을 추가 — 예:

```markdown
### 결함 surface — v0.1.0 진입 직전 (2026-05-19 OCI)

| ID | 영역 | 항목 |
|---|---|---|
| §D | drive auth | SA write 시 storageQuotaExceeded (Personal Drive SA quota 미할당) — ADR-0029 §Decision L50 (Editor 공유) + §부정/제약 L79 가정 깨짐 |
| §I | changes feed | w2a → rclone(OAuth) 업로드가 gws(SA) changes.list 에 미감지 — 인증 주체 비대칭. closed by ADR-0035 |
```

옵션 2: 본 ADR·plan·analysis 의 모든 "백로그 §D·§I" 를 "2026-05-19 OCI 운영 진단" 또는 "본 feature 의 analysis_and_design.md §1.1" 로 교체. ADR §Cross-references 의 "계기 백로그" 라인 삭제.

#### H3. state migration 책임 분산 — ADR-0035 §Note 흡수 vs §Decision 본문 vs DoD 미정렬

**위치**:
- analysis_and_design.md §7.1 L432-440 (state migration 옵션 S1/S2/S3 + "ADR 추출: ADR-0035 §Note 에 흡수 가능")
- ADR-0035 §Decision §"운영 자산 영향" L140-141 (운영자 수동 rm 명시)
- ADR-0035 §Consequences §"부정/제약" L181 (운영자 수동 state migration)
- DoD §8.6 운영 검증 L522 "운영자가 수동으로 `rm ~/wikihub/_state/gdrive/{cursor,file_map}.json`"

**문제 진단**:

§7.1 가 "ADR-0035 §Note 에 흡수 가능" 으로 결정했고 §7.5 결정 표에서도 "ADR-0035 §Note 흡수 (별도 ADR 불요)" 로 lock 했음. 그러나 **ADR-0035 본문에는 별도 §Note 섹션이 없고**, §Decision §"운영 자산 영향" 에 단 2줄 (L140-141) 로 흩어져 있음 — "§Note 흡수" 의 의미가 "본문 §Decision 의 한 단락에 흡수" 인지 "별도 §Note 섹션 신설" 인지 모호.

또한 미결 §7.2 (false_delete_threshold default) 가 "§Decision 본문 포함" 으로 정해졌으나 ADR-0035 §"false-deleted 가드" L118-122 에 명시 — 정합. 단 ADR-0029 의 `Note (2026-05-19, ADR-0035 supersede)` 패턴과 비교하면 ADR-0035 본문의 정보 구조가 비균질.

**파급 영향**:
- ADR-0035 §Note 라는 섹션이 존재하지 않으면 후속 reader 가 §7.5 의 "§Note 흡수" 의미를 추적 못 함.
- state migration 절차가 명확한 한 곳에 lock 되지 않으면 운영 실수 (cursor.json 남기고 file_map.json 만 삭제 등) 가능.

**권장 수정**:

옵션 1 (선호): ADR-0035 본문에 **별도 §Operational Note 섹션 신설** — state migration 절차 + threshold default + first-run 거동 (모두 created 분류 + 24h 안정 관찰) 명시. §7.5 의 "§Note 흡수" 인용도 정합.

옵션 2: analysis_and_design.md §7.5 의 "ADR-0035 §Note 흡수" 표현을 "ADR-0035 §Decision §'운영 자산 영향' 본문 포함" 으로 수정 + DoD §8.6 의 운영 검증 절차를 ADR-0035 본문에서 cross-reference.

#### H4. ADR-0026 의 _RCLONE_AUTH_PATTERNS 의 mount scope 가 lsjson 경로로 확장 필요

**위치**:
- ADR-0035 §"인증 자료 단일화" L124-130 (rclone.conf 단일)
- ADR-0026 §Decision (vfs_refresh OAuth Fatal 분기)
- ADR-0024 v9 §"_RCLONE_AUTH_PATTERNS" (mount scope writer)

**문제 진단**:

After 모델에서 rclone 이 **두 경로** (mount + lsjson) 에서 OAuth 사용. mount 측의 OAuth revoke 는 ADR-0026 vfs_refresh + ADR-0024 v9 mount scope writer 로 fatal escalate. 그러나 **lsjson 측의 OAuth revoke·rate limit·403 분기 처리** 가 ADR-0035 본문에 미명시.

analysis_and_design.md §5.5 의 lsjson 인자 (L376-385) 와 §5.3 의 false-deleted 가드 (L340-358) 만 있음 — rclone lsjson 의 stderr exit code 매핑이 별도 ADR 또는 본 ADR §"rclone exit code 매핑 표" 로 lock 안 됨.

ADR-0017 §Decision 가 gws stderr → 5-bucket 매핑 표를 정본화했으나 supersede. 본 ADR §Decision 의 §책임 매트릭스 L101 "변경 감지 (메타데이터): rclone lsjson" 만 있고 매핑 표 부재. plan.md L84 "rclone exit code + stderr 패턴 (rclone 자체 매핑 표 신규)" 만 있음 — analysis 에선 §5 의 sub-section 으로 lock 안 됨.

**파급 영향**:
- 구현 시 `scripts/lib/rclone.py` 의 `run_rclone()` 의 exit code/stderr 분기가 ADR 정본 부재 상태로 임의 결정됨 → 운영 surface 시 retry/fatal 분류 부적합 위험.
- ADR-0017 의 scope 컬럼 (file vs vault) 개념이 lsjson 에서는 어떻게 적용되는지 미정 (lsjson 은 full listing 이라 file scope 무의미 가능).

**권장 수정**:

ADR-0035 §Decision 에 **§"rclone lsjson 에러 매핑" sub-section 신설** — 또는 analysis_and_design.md §5 에 §5.6 신설. starting regex:

| rclone exit | stderr pattern | severity | wikihub_exit | scope |
|---|---|---|---|---|
| 1 | `oauth2.*invalid`·`401`·`unauthorized` | fatal | 2 | vault |
| 1 | `403.*(quotaExceeded\|rateLimitExceeded)` | retryable | 75 | vault |
| 1 | `403.*(insufficientPermissions\|forbidden)` | fatal | 2 | vault (lsjson 은 full snapshot 이라 file scope 없음) |
| 1 | `5\d{2}` | retryable | 75 | vault |
| 1 | `timeout`·`connection`·`network` | retryable | 75 | vault |
| 2+ | argv 오류 | fatal | 2 | vault |
| 137·143 (timeout/kill) | — | retryable | 75 | vault |

운영 검증 (DoD §8.6) 에서 OAuth revoke 시 lsjson 측의 fatal escalate 가 vfs_refresh 측과 동일하게 ADR-0024 mount scope writer 로 흘러가는지 (또는 vault scope writer 인지) 명확화.

#### H5. DoD §8.6 의 rename 정확성 + false-delete 가드 회귀 테스트 누락

**위치**: analysis_and_design.md §8.6 운영 검증 L519-525

**문제 진단**:

§3.1 변경 매트릭스에서 신규 도입되는 핵심 invariant 2건:

1. **rename 추적 정확성** — file_map primary key 의 source_id 전환 (§4.2 L165-208) 의 핵심 가치. After 모델에서 Drive 의 파일 이름 변경 시 `renamed` 분류 + wiki_path unlink + 신규 path 로 갱신.
2. **false-delete 가드** — §5.3 L340-358 의 가드 발화 (delete_ratio > threshold → Retryable abort).

그러나 DoD §8.6 의 운영 검증은:
- L522 "수동 rm ..."
- L523 "timer 1회 fire → 모두 created"
- L524 "w2a 로 새 .md 파일 1건 업로드 → 다음 사이클에서 created 감지"
- L525 "정상 동작 24h 관찰"

→ **rename·false-delete 가드 발화 시나리오 자체가 DoD 에 없음**.

**파급 영향**:
- 운영 검증 통과 후에도 rename 시 (delete + create) 오분류 + false-delete 가드 미발화 결함이 surface 안 됨 → 첫 운영 사이클에서 wiki/sources/ 정합성 깨짐 가능.

**권장 수정**:

DoD §8.6 에 회귀 시나리오 2건 추가:

- [ ] Drive 에서 임의 파일 1건 rename → 다음 사이클에서 `renamed` 분류 + wiki_path 갱신 + 이전 wiki page unlink 확인
- [ ] Drive 에서 vault root 의 임의 폴더 1건 (전체 파일 수의 30% 이상) 임시 trash/unshare → 다음 사이클에서 VaultSyncRetryable + 임시 trash/unshare 복원 → 그 다음 사이클 정상 동작

§8.5 단위 테스트 (`tests/test_mount_diff.py`) 의 mock 케이스만으로는 운영 회귀 invariant 약함. 실 OCI 환경 회귀 1건 필수.

---

### MED — 개선 권고

#### M1. ADR-0027 의 cascade 잔존 — ADR-0024 v9 mount scope writer 의 ADR-0035 정합 명시

**위치**: ADR-0024 §"v9 추가 (2026-05-15) — mount scope writer 확장" L107-178

**문제 진단**:

ADR-0024 v9 §Context (L111) 가 "Path C+ (rclone mount + gws 책임 분리, ADR-0025·0026·0027 참조)" 를 인용. 본 ADR-0035 가 ADR-0027 을 supersede 함에 따라 ADR-0024 의 v9 추가 섹션의 인용이 부분적 dangling. 단 ADR-0024 의 mount scope writer 책임 (mount.py 의 `_raise_mount_failure` + `vfs_refresh` OAuth Fatal) 자체는 ADR-0035 에서도 유지 — supersede 대상은 아님.

analysis §6.2 (L408) 도 ADR-0024 를 "그대로" 분류 — 정합. 단 ADR-0024 v9 §Context 의 ADR-0027 인용은 dangling 검토 필요.

**권장 수정**:

옵션 1: ADR-0024 v9 §Context 의 ADR-0027 인용을 ADR-0035 로 교체 (또는 "ADR-0027 → ADR-0035 supersede" 명시).
옵션 2: 본 ADR-0035 §Cross-references 에 "ADR-0024 v9 mount scope writer — 정합 유지, ADR-0024 §Context 인용은 historical" 명시.

#### M2. ADR-0034 §Note (2026-05-19, feature `dir_layout_refactor`) 의 ADR-0029 정합

**위치**: ADR-0029 §"Note (2026-05-19, feature `dir_layout_refactor`)" L98-117

**문제 진단**:

ADR-0029 가 ADR-0035 로 supersede 됐는데, ADR-0029 본문 L98-117 의 "§Note (2026-05-19, feature `dir_layout_refactor`) — §Decision 본문 변경 (ADR-0034)" 섹션이 SA JSON 의 credentials_path 를 명시. 이 §Note 가 ADR-0035 에 의해 무효화됨 (credentials_path 자체 폐기). 

ADR-0029 의 ADR-0035 supersede §Note (L9-11) 가 본문 전체를 "역사적 맥락" 으로 표시하지만, L98-117 의 ADR-0034 정합 §Note 는 ADR-0034 를 살아있는 ADR 로 참조 — reader 가 헷갈릴 수 있음.

**권장 수정**:

ADR-0029 L98-117 §Note (ADR-0034) 에 한 줄 추가:

```
**ADR-0035 supersede 후 무효** — 본 §Note 의 credentials_path default 갱신은 ADR-0035 의 credentials_path 키 폐기로 의미 부재. 역사적 맥락 보존 위해 본문 유지.
```

#### M3. setup.md Step 6 진입 조건의 `bootstrap_allowed` 잔존

**위치**: `_system/commands/setup.md` Step 6 L217 "진입 조건: `--enable` 플래그 + Step 1~5 통과 + `bootstrap_allowed: true` vault 1개 이상"

**문제 진단**:

본 ADR-0035 §Decision 이 `bootstrap_allowed` yaml key 폐기를 명시 (analysis §4.3 L234 "bootstrap_allowed 폐기 — cursor 모델 자체 폐기" + ADR-0035 §state schema 갱신 L113 "cursor.json 폐기"). 그러나 setup.md Step 6 진입 조건과 setup.md L289 "Step 6 — `bootstrap_allowed` 환원" 표가 그대로 잔존.

이는 정본 코드 (Step 3 구현) 의 결함이지만 analysis_and_design.md §3.1 변경 매트릭스 L106 "`_system/commands/setup.md` Step 1 gws 단계 폐기" 만 명시 — **Step 6 의 bootstrap_allowed 진입 조건 갱신 항목 누락**.

**권장 수정**:

analysis §3.1 변경 매트릭스의 setup.md 항목에 "Step 6 진입 조건 — `bootstrap_allowed: true vault` → `enabled vault`" 추가. DoD §8.3 정본 문서 체크리스트에도 1항목 추가.

#### M4. install.sh `_step5_instance_dirs` 의 `~/.credentials/wikihub/` 폐기 누락

**위치**:
- ADR-0035 §"install.sh 단순화" L136 "Step 5.3 `_step5_instance_dirs` 의 `~/.credentials/wikihub/` 생성 폐기 (rclone.conf 만 필요 — `~/.config/rclone/`)"
- install.sh L646-670 `_step5_instance_dirs` 함수 (creds_dir="$HOME/.credentials/wikihub" 그대로)
- analysis §3.1 L109 "install.sh — gws 다운로드/설치 단계 제거 (`_step5_gws_install` 등)"

**문제 진단**:

ADR-0035 §Decision 본문은 `_step5_instance_dirs` 의 credentials dir 자체 폐기를 명시 — 단 analysis §3.1 변경 매트릭스 L109 는 `_step5_gws_install` 폐기만 명시 + `_step5_instance_dirs` 의 credentials dir 폐기를 누락 (raw text 만 보면 "등" 으로 약식 표현). 

DoD §8.2 인프라 L495 "install.sh 의 `_step5_gws_install` 및 INSTALLED_VERSIONS.json 의 gws 키 제거" 도 동일 — credentials dir 폐기 누락.

**파급 영향**:
- 운영자 base 0건 시점이라 큰 위험은 없으나 ADR §Decision 본문 vs 실 구현 backlog 가 어긋남 → 구현 추적 누락 가능.

**권장 수정**:

analysis §3.1 변경 매트릭스 install.sh 항목과 DoD §8.2 에 명시 추가:

- [ ] install.sh `_step5_instance_dirs` 의 `creds_dir="$HOME/.credentials/wikihub"` 분기 제거 (`rclone.conf` 권한 검증만 유지)
- [ ] ADR-0029 §"Note (2026-05-19)" 의 credentials_path default 변경 정합도 무효화 명시

#### M5. ADR-0035 §"OCI 실배포 검증" 의 24h 관찰 임계치 부재

**위치**: DoD §8.6 L525 "정상 동작 24h 관찰 — fatal 0건 + delete_ratio 0% 유지"

**문제 진단**:

24h 관찰의 정상 조건이 "fatal 0건 + delete_ratio 0%" 만 명시. 그러나 §5.3 false-deleted 가드의 default threshold 가 0.3 (30%) — 운영자 의도된 1건 삭제 시 delete_ratio = 1/N 이라도 0% 아님. "delete_ratio 0%" 가 의미하는 바가 모호 (운영자 삭제 행위 자체를 배제하는지, 가드 미발화만 보는지).

**권장 수정**:

DoD §8.6 L525 → "fatal 0건 + delete_ratio < false_delete_threshold (default 0.3) 유지 + listing_count 가 매 사이클 유사 범위 (±5%) 유지" 로 명시.

#### M6. 재검토 트리거의 우선순위 부재

**위치**: ADR-0035 §Consequences §"재검토 트리거" L197-202

**문제 진단**:

재검토 트리거 5개 (rclone client publishing 회귀 / rclone backend changes 추가 / vault 규모 N>>10k / Google native 추가 / rclone v2.x) 가 평면 나열. 우선순위·발화 임계치·재검토 deadline (예: "확인 시점 + 2주 내 ADR 갱신 검토") 부재. ADR-0027 의 재검토 트리거도 동일 형식이라 패턴 일관이긴 하나, 본 ADR 이 5건 supersede 의 정본이라는 점에서 더 정밀해야 함.

**권장 수정**:

각 트리거에 발화 임계치 + ADR 재검토 deadline 명시. 예:

- rclone 기본 client publishing → Testing 회귀: GCP Console 알림 또는 rclone 1.70+ release note — 발화 즉시 OAuth Production 검증 신청 ADR 발의
- vault 규모 N >> 10k: lsjson 응답 latency p95 > sync_interval_sec/3 — 측정 후 per-file refresh (ADR-0026 K2 hybrid) 또는 cursor 회귀 ADR 발의
- Google native 추가: 첫 .gdoc/.gsheet 파일 vault 진입 시 — 24h 내 mtime 안정성 측정 verification

---

### LOW — nit / 스타일

#### L1. analysis_and_design.md §6.1 ADR cascade 표의 ADR-0029 §Note 권장 표현

**위치**: analysis_and_design.md §6.1 L399 "ADR-0029 (SA 인증) | ... | 본문 유지 — §Note 에 2026-05-19 실증 (storageQuotaExceeded) 추가 권장"

**문제 진단**:

"추가 권장" 이라는 표현이 모호 — 강제인지 선택인지. 실제 ADR-0029 본문 L9-11 에 §Note 가 이미 작성됐으므로 사후적으로는 정합. 단 analysis 작성 시점엔 미완료를 시사.

**권장 수정**:

"§Note 추가 (ADR-0029 L9-11 lock)" 로 명시 — 또는 표 footer 에 "본 cascade 의 모든 §Note 갱신은 본 feature 의 Step 3 구현 범위" 추가.

#### L2. ADR-0035 §"file_map schema" 의 last_synced_at 의미

**위치**: ADR-0035 §state schema 갱신 L112 "value: `{source_relpath, source_mtime, wiki_path, bytes, last_synced_at}`"

**문제 진단**:

`last_synced_at` 의 의미가 ADR §Decision 본문에 미정의. After 모델에서 file_map 갱신은 매 사이클 발생 가능 (modified 시) — last_synced_at 이 "마지막 wiki write 시각" 인지 "마지막 lsjson 확인 시각" 인지 모호.

ADR-0007 (state JSON format) 참조 후에도 명확하지 않음. analysis §4.2 L185 의 file_map 예제에는 last_synced_at 값이 있지만 의미 정의 부재.

**권장 수정**:

ADR-0035 §state schema 에 1줄 추가: "last_synced_at: 해당 source_id 의 wiki page 가 마지막으로 write 된 시각 (modified 분류 시 갱신, unchanged 분류 시 보존)".

#### L3. plan.md L13 "rclone 의 OAuth client (기본값) 는 이미 Production 검증 통과" 출처 표시

**위치**: plan.md L13

**문제 진단**:

"Production 검증 통과" 의 출처가 명시 안 됨 — rclone GitHub readme 또는 docs 의 어느 부분인지. ADR-0035 §Consequences §"재검토 트리거" 의 "rclone 기본 client publishing status 정책 변경" 의 monitoring 대상이 무엇인지 추적 어려움.

**권장 수정**:

plan.md 또는 ADR-0035 §Cross-references 에 rclone 기본 client 의 publishing status 출처 (rclone docs 또는 GCP Console) URL 또는 간단한 인용 1줄 추가.

#### L4. ADR-0035 §"in-toto attestation" 등 v0.2.x supply chain 항목 명시 부재

**위치**: ADR-0035 §Consequences §"긍정" L173 "supply chain 위협 surface 1개 감소 — gws GitHub Releases artifact 폐기"

**문제 진단**:

ADR-0025 §Consequences §"부정/제약" 마지막 항목 (R16-H2) 에서 v0.2.x deferred 로 명시한 `RCLONE_PINNED_SHA256` env override 또는 in-toto attestation 정합 — 본 ADR 이 rclone artifact 하나로 통일하면서 supply chain 위협 surface 가 1개로 감소했으나, 단일 dependency 의 compromised 위험이 오히려 집중되는 trade-off 도 surface 권장.

**권장 수정**:

§Consequences §"부정/제약" 에 1줄 추가: "rclone single dependency — supply chain 위협 집중. ADR-0025 §부정/제약 (R16-H2) 의 v0.2.x deferred 항목 (in-toto / RCLONE_PINNED_SHA256) 우선순위 상향 검토".

#### L5. README.md 인덱스의 ADR-0035 행 의 "**Supersedes ADR-0014/0015/0017/0027/0029**" 표기 일관성

**위치**: `docs/adr/README.md` L92

**문제 진단**:

다른 행의 supersede 표기는 "— **Superseded by ADR-XXXX**" (소문자 by) 또는 "**Supersedes ADR-NNNN**" 패턴. 본 행은 "Supersedes ADR-0014/0015/0017/0027/0029" — `/` 구분자 사용. 다른 ADR 의 supersedes 표기는 단일 ADR 만 — multi-supersede 의 표기 컨벤션이 README 작명 규칙에 미명시.

**권장 수정**:

README.md 의 §"결정 변경 정책" 또는 §"인덱스" footer 에 multi-supersede 표기 컨벤션 추가:

```
ADR 1건이 여러 ADR 을 supersede 하는 경우 `Supersedes ADR-NNNN, ADR-MMMM` (콤마 + 공백 구분) 또는 `Supersedes ADR-NNNN/MMMM` (슬래시 구분) 중 일관성 채택. 본 컨벤션은 ADR-0035 (5건 supersede) 가 첫 사례.
```

또는 본 행을 `**Supersedes ADR-0014, ADR-0015, ADR-0017, ADR-0027, ADR-0029**` 로 표기 통일.

---

## 강점

1. **2026-05-19 OCI 실증의 정량 근거**: lsjson 의 ID·MimeType 필드 노출이 실제 출력 (analysis §2.4 L78-81) 으로 lock — gws changes API 등가 대체 가능성을 가설이 아니라 실증으로 입증. ADR-0027 §L1 4개 기각 사유 해체의 결합 논리도 §재평가 표 (ADR-0035 L88-97) 에서 점 단위로 닫혀 있음.
2. **Karpathy §2 Simplicity First 정합**: 두 도구 → 한 도구 + abstraction 신규 도입 없음 (plan.md L72). 단순화 방향이 명확하며 5건 supersede 가 ADR cascade 자체 단순화에도 기여.
3. **state schema 의 source_id primary key 전환의 정확성**: rename 추적의 정확성 + Drive `id` stability 의 invariant 가 명확. analysis §4.2 L202-209 의 4-way 분류 (created/modified/renamed/deleted) 가 잘 정의됨.
4. **false-deleted 가드의 보수성**: yaml override 가능 + listing 0건 별도 분기 + Retryable→Fatal escalate 체인이 ADR-0024 v9 기존 흐름과 정합.

---

## 종합 권고

**refine**.

CRIT 결함 없음 — 본 결정의 invariant (OAuth 통일 + gws 폐기 + lsjson 단일화) 는 견고. 단 HIGH 5건 (특히 H1 ADR-0026 정합 모순, H2 백로그 §D·§I 인용 출처 불일치, H4 lsjson 에러 매핑 표 부재) 는 cascade 정합성 손상 — Step 3 진입 전 반드시 surgical 갱신 필요.

권고 처리 순서:
1. **H1 ADR-0026 §Note 갱신** (cycle 순서·race window 재정의) — 본 ADR §Decision 의 책임 매트릭스가 vfs_refresh 의 timing 을 보존하려면 필수.
2. **H4 lsjson 에러 매핑 표 신설** (ADR-0035 §Decision 또는 analysis §5.6) — Step 3 구현의 임의성 회피.
3. **H2 백로그 §D·§I 출처 정합** — backlog.md 에 항목 추가 또는 인용 표현 교체.
4. **H3 §Operational Note 섹션 신설** + **H5 rename·false-delete 가드 회귀 시나리오** DoD 추가.
5. MED 6건 + LOW 5건은 Step 3 와 병행 또는 follow-up commit 가능.

위 refine 완료 후 Step 3 진입 권고. ADR-0035 의 결정 자체는 v0.1.0 의 architectural 정본으로 정합.
