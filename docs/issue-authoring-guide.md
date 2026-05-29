# GitHub 이슈 작성 가이드 (에이전트 공통) v0.1.0

이 문서는 에이전트(이 Claude 세션, 다른 Claude 세션, Hermes 등)가 wikihub repo 에 GitHub 이슈를 등록할 때 따르는 **제목·라벨·본문 형식의 정본**이다. 백로그 항목, 코드 리뷰 발견, 운영 결함 등을 이슈로 옮길 때 일관된 형식을 보장한다.

> 위치 근거: 본 가이드는 영속 메인테이너 가이드이므로 `docs/` 에 둔다 (AGENTS.md §1 — Development Zone, 영속 기록). 변경은 supersede 로 추적.

## 1. 제목 규칙

형식: **`[<AGENT-ID>] <사람이 읽는 한글 요약>`**

- **`<AGENT-ID>`** — 이슈를 만든 에이전트 식별 태그. 에이전트마다 고유하게 둬서 작성 주체를 추적한다.
  - 이 Claude 세션 = `CLAUDE-A`
  - 다른 Claude 세션 = `CLAUDE-B`, `CLAUDE-C` …
  - Hermes = `HERMES`
- **요약** — 제목만 보고 이해되는 한글 한 줄.
  - ❌ 내부 코드(`R15-M4`, `BL-N12`, `CR2-MED-1` 등)를 제목에 넣지 않는다. 소스(backlog / review)가 사라지면 아무것도 가리키지 못하는 opaque 토큰이 된다.
  - ✅ `[CLAUDE-A] rclone 인증 에러 패턴 커버리지 확장 (project disabled / 권한 revoke)`

## 2. 라벨

모든 에이전트 작성 이슈는 **`agent` + `priority: *`** 2개를 단다.

| 라벨 | 색 | 의미 | 적용 |
|---|---|---|---|
| `agent` | `#bfdadc` | 에이전트가 작성·관리하는 이슈 | 항상 |
| `priority: high` | `#b60205` (red) | 운영 사고 / silent failure 직결 | 택1 |
| `priority: medium` | `#fbca04` (amber) | hardening / spec drift / 중요 개선 | 택1 |
| `priority: low` | `#0e8a16` (green) | 정리 / 미세 개선 / 추후 검토 | 택1 |

색은 **중요도 gradient** (red → amber → green).

**우선순위 매핑 기준** (순서대로 적용):
1. 소스에 명시된 우선순위가 있으면 그대로 사용.
2. 없으면 소스 리뷰 severity 에서 derive (리뷰의 `M`=medium, `L`=low 태그 등).
3. CRIT / C 급 근거(silent alert 유실, 데이터 정합 파손 등)는 `high` 로 격상.

라벨 부재 시 1 회 생성:
```bash
gh label create "priority: high"   --color b60205 --description "운영 사고/silent failure 직결"
gh label create "priority: medium" --color fbca04 --description "hardening / spec drift / 중요 개선"
gh label create "priority: low"    --color 0e8a16 --description "정리 / 미세 개선 / 추후 검토"
```

## 3. 본문 섹션 템플릿

```markdown
> **메타** — 출처: <feature / 리뷰 파일> · 영역: <area> · 우선순위: <high|medium|low>

## 배경
<어느 작업·리뷰에서 surface 됐고 왜 미뤄졌는지>

## 현행 동작 / 문제
<지금 코드가 어떻게 동작하며 무엇이 결함·누락인지 — file:line 앵커 포함>

## 영향 / 리스크
<무엇이 저하·파손되는지, 우선순위 근거>

## 제안 해결 방향
<해결 방향 + 리뷰 권고 종합>

## 영향 범위 / 대상 파일
<수정 대상 파일 경로>

## 수용 기준 (DoD)
- [ ] <검증 가능한 완료 조건>

## 참조
- 소스: <archive 리뷰 파일 경로 (라인)>
- 코드: <file:line>
- ADR: <ADR-NNNN> (있을 때)
- 관련: <관련 이슈 #N>
```

**Umbrella 이슈** (작은 관련 항목 묶음 1개 이슈): 위 템플릿에 **`## 하위 항목`** 표(각 sub-item 요약 · 소스 라인 · 체크박스)를 추가하고, 개별 섹션은 그룹 공통 수준으로 축약한다.

## 4. 작성 원칙

- **한글**로 작성 (repo 정합).
- **추측 금지** — 본문 작성 전 cited 소스(리뷰 파일 라인)와 코드 앵커를 직접 read 해서 실제 근거로 채운다. backlog 문구를 그대로 복사하지 말고 **현재 코드·아키텍처와 정합 정정**한다 (예: 폐기된 메커니즘을 거론하는 항목은 해당 ADR 기준으로 무효 명시).
- **코드 앵커** — `file:line` 형식으로 실재 위치를 인용 (예: `scripts/lib/mount.py:38`).
- **내부 코드 토큰 제외** — `R15-M4` 같은 backlog / review ID 는 제목은 물론 메타에서도 standalone 으로 쓰지 않는다. 추적은 `## 참조` 의 파일 + 라인 locator 로 한다.
- **버전 결부 문구 금지** — "v0.2.x deferred", "v0.3 에서" 등 명확한 버전 계획이 없는 표현 대신 **"추후 검토 사항"** 으로 reframe 한다.

## 5. gh 명령 패턴

긴 마크다운은 임시 파일에 쓰고 `--body-file` 로 생성한다.
```bash
gh issue create \
  --title "[CLAUDE-A] <한글 요약>" \
  --body-file /tmp/issue-body.md \
  --label agent \
  --label "priority: medium"
```
검증: `gh issue view <N> --json title,labels,body` 로 라벨·본문 렌더 확인.

## 6. 예시 (품질 기준)

**제목**: `[CLAUDE-A] rclone 인증 에러 패턴 커버리지 확장 (project disabled / 권한 revoke / billing)`
**라벨**: `agent`, `priority: medium`

```markdown
> **메타** — 출처: install_runtime feature · `code_review_3.md` (Step 4 코드 리뷰) · 영역: regex evidence · 우선순위: medium

## 배경
F4 `install_runtime` Step 4 코드 리뷰에서 surface. rclone 인증 실패 감지용 정규식이 OAuth 계열만 커버하고 일부 인증 실패를 누락 — 운영 evidence 누적 후 surgical 추가하기로 추후 검토 사항으로 분류.

## 현행 동작 / 문제
`scripts/lib/mount.py:38` `_RCLONE_AUTH_PATTERNS` 는 현재 OAuth 계열만 매칭한다 (`Token expired` / `invalid_grant` / `401 Unauthorized` / `oauth2.*invalid` / `unauthorized_client` / `access_denied` / `invalid_credentials`). GCP project disabled / 권한·IAM revoke / billing 영구 거부는 미커버 → 인증 에러로 분류되지 않고 generic error 로 흐른다.

> **ADR 정합 정정**: 원 리뷰가 거론한 "SA 키 rotation" 패턴은 ADR-0035(rclone-only — SA 폐기)로 무효. 실제 scope 는 OAuth 시대에도 발생 가능한 위 3종으로 한정.

## 영향 / 리스크
미분류 시 `vfs_refresh` 의 OAuth-error 분기를 못 타 `VaultSyncFatal`(scope=mount) escalation · last_failure 영속화 · ops-alert 발화가 누락 → 운영자가 인증 단절을 즉시 인지 못 함. 빈도는 낮으나 진단 신호 약화라 medium.

## 제안 해결 방향
추측성 패턴을 넣지 말고, 실제 운영·시뮬에서 위 실패의 rclone stderr 원문 evidence 를 확보한 뒤 해당 문자열만 `_RCLONE_AUTH_PATTERNS` 에 narrow 하게 surgical 추가.

## 영향 범위 / 대상 파일
- `scripts/lib/mount.py` — `_RCLONE_AUTH_PATTERNS` (L38–45)

## 수용 기준 (DoD)
- [ ] project disabled / 권한 revoke / billing 영구거부 메시지가 인증 fatal 로 분류됨
- [ ] 기존 OAuth 패턴 regression 없음 (false positive 미발생)

## 참조
- 소스: `features/archive/20260514_install_runtime/code_review_3.md` (L43)
- 코드: `scripts/lib/mount.py:38`
- ADR: ADR-0035 (rclone-only 인증 모델), ADR-0024 (last_failure / ops-alert)
```

## 7. 생성 전 체크리스트

- [ ] 제목 = `[<AGENT-ID>] <한글 요약>`, 내부 코드 토큰 없음
- [ ] 라벨 = `agent` + `priority: high|medium|low`
- [ ] 본문 8 섹션 작성 (또는 umbrella + `## 하위 항목`)
- [ ] 코드 앵커·소스 라인 실측 확인 (추측 아님)
- [ ] 버전 결부 문구 없음 ("추후 검토 사항"으로)
- [ ] DoD 가 검증 가능
