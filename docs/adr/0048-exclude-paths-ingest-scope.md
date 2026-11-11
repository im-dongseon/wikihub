# ADR-0048: ingest 제외 범위 — vault 별 `options.exclude_paths`

- **Status**: Accepted
- **Date**: 2026-11-11
- **Feature**: issue #221
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

vault 전체를 ingest 대상으로 삼으면 보고서·임시 산출물처럼 wiki 통합이 불필요한 경로까지 source 페이지로 발행된다. 제외 범위를 vault 별로 선언하되, 발행 경로와 삭제 이벤트 분류의 정합을 유지해야 한다. listing 에서만 제외하면 file_map 에 남은 엔트리가 삭제로 분류되어 false-delete 가드에 걸린다.

## Considered Options

- **(α) vault 별 `options.exclude_paths` 선언**: 제외 prefix 를 vault 설정에 두고 ingest 단계에서 적용한다.
- **(β) 발행 위치 변경**: NAS 등 별도 저장소로 발행 경로를 옮긴다.
- **(γ) semantic 단계 마커**: source 노드에 제외 마커를 남겨 semantic 단계에서 건너뛴다.
- **(δ) 별도 vault 분리**: 제외 대상 전용 vault 를 구성한다.

## Decision

**채택**: (α) vault 별 `options.exclude_paths` 선언

**이유**:
- 제외는 ingest 제외 범위일 뿐 발행 경로를 바꾸지 않으므로 기존 발행·검증 흐름을 유지한다.
- listing 필터와 file_map 프루닝을 **함께** 수행해야 프루닝으로 인한 삭제 이벤트가 발생하지 않는다. listing 만 필터하면 file_map 잔여 엔트리가 deleted 로 분류되어 false-delete 가드에 걸린다.
- 파괴적 wiki source 삭제는 런타임 코드가 아니라 1회성 마이그레이션 스크립트(`scripts/migrate_exclude_paths.py`, dry-run 기본)가 담당한다. 런타임 경로는 결정적이고 반복 가능해야 한다.
- (β) 발행 위치 변경은 NAS 내구성과 `_publish_verify` 원격 md5 검증을 상실한다.
- (γ) semantic 단계 마커는 source 노드 비대 문제를 해결하지 못한다.
- (δ) 별도 vault 는 개념 부담이 크다.

## Consequences

- **긍정**: vault 별로 ingest 대상을 좁힐 수 있고, 기존 발행 경로·검증은 그대로 유지된다.
- **부정/제약**: `exclude_paths` 미설정 시 동작 변화는 없다. 프루닝 사이클은 `has_changes=false` 를 유지하고 `last_sync.json` 의 `file_map_count_before` 는 프루닝 후 값이다.
- **후속 영향**: 파괴적 정리는 1회성 마이그레이션 스크립트가 전담하며, 런타임 ingest 코드는 제외 판정과 프루닝만 수행한다.
- 프루닝 경고는 프루닝이 발생한 **1회 사이클에만** 출력된다(file_map 이 즉시 갱신되므로). 제외 콘텐츠의 실제 정리는 1회성 마이그레이션 로그(`unlinked_pages`·`stripped_ref_items`)로 추적한다.
