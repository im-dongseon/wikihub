# Feature 배포 이력

<!-- append-only — 최신 항목이 파일 끝에 위치 -->

---

## [2026-05-19] oauth_unify_rclone_only

- **목적**: v0.1.0 진입 직전 OCI 검증에서 surface 한 두 결함 closed — (1) Personal Drive 에서 SA write 불가 (`403 storageQuotaExceeded`, ADR-0029 §Decision 가정 깨짐), (2) rclone(OAuth) ↔ gws(SA) 인증 주체 비대칭으로 changes feed 단절 (w2a 업로드 미감지).
- **로직**: 두 도구 → 한 도구로 단순화 + 인증 자료 단일화. `rclone lsjson <remote>: --recursive` (Drive API files.list backend 호출) 이 반환하는 `ID`·`MimeType`·`ModTime` 필드 + `file_map` (primary key = source_id/Drive fileId) diff 로 gws `drive changes list` 등가 대체. cursor 모델 폐기 (full snapshot diff), SA JSON 폐기 (rclone.conf 단일 인증). `mount_diff.compute_diff` 가 4-way 분류 (created/modified/renamed/deleted) + false-deleted 가드 (listing 0건 또는 delete_ratio > threshold 시 Retryable abort) 책임.
- **생성 ADR**: ADR-0035 (Supersedes ADR-0014, ADR-0015, ADR-0017, ADR-0027, ADR-0029)
- **트레이드오프**:
  - lsjson cost — 매 사이클 full snapshot. v0.1.0 vault 규모 (N~수천) 에선 무영향. 큰 vault (N >> 10k) 에서 재검토 필요.
  - rclone single dependency — supply chain 위협 집중 (ADR-0025 §부정/제약 R16-H2 의 in-toto / RCLONE_PINNED_SHA256 우선순위 상향 검토 트리거).
  - Google native (`.gdoc`/`.gsheet`/`.gslides`) export 의 mtime 안정성 미실증 — vault 에 미존재. native 파일 도입 시 검증 필요 (재검토 트리거).
  - 운영자 수동 state migration 1회 (`rm cursor.json file_map.json`) — 자동화 미제공 (v0.1.0 미배포 시점 가정).
- **결론**: ADR cascade 5건 → 1건 단순화. 코드 ~30% 감소 (gws/errors 모듈 폐기, sync.py 재작성). pytest 56 pass / 1 skip. 설계·코드 멀티 리뷰 (refine) 반영 완료. v0.1.0 의 Drive 접근 architectural 정본 lock.
- **참조**: features/archive/20260519_oauth_unify_rclone_only/
