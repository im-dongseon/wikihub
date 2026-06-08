# Code Review: feature/v018-fix

**리뷰 모델**: MiniMax M2.5 (opencode-go/minimax-m2.5)
**날짜**: 2026-05-26 KST
**기준**: `origin/v0.1.9` → `feature/v018-fix`

---

## Commit 1 — `d0a6746`: lint_interval_hours 기본값 24→3

**파일**: `scripts/lib/config.py:153`

| 기준 | 평가 |
|------|------|
| Correctness | ✅ config.py 기본값이 render_systemd_units.py:220 및 wikihub.yaml.example:35(둘 다 3)와 일치함 |
| Side effects | ✅ yaml에 명시값이 있으면 영향 없음. 새 설치에만 기본값 적용 |
| Consistency | ✅ 코드 스타일 일치 |

**⚠ Completeness — 테스트 미반영**: `tests/test_config.py:36,48`에 `lint_interval_hours: 24` 픽스처가 잔존. 단, 픽스처는 명시값(24)을 쓰므로 기본값 변경과 무관. 테스트는 통과하나, 의도적 검증 목적에 따라 3으로 갱신 검토 가능.

---

## Commit 2 — `135f961`: wh-graphify 참조 제거

**파일**: `install.sh:1261`

| 기준 | 평가 |
|------|------|
| Correctness | ✅ `wh-graphify·` 제거 정확. graphify skill은 systemd unit(wikihub-graphify.service)으로 이전 완료 |
| Side effects | ✅ 없음 |

---

## Commit 3 — `28492eb`: lessons learned report

**파일**: `250526_wikihub_v018fix_report.md`

| 기준 | 평가 |
|------|------|
| Docs accuracy | ⚠ 최종 git 내역에 2개 커밋만 표시되었으나, report 커밋(28492eb) 포함 총 3개 |
| OPS checklist | ✅ S-1~S-8 구체적이고 실용적 |
| OPS checklist | ⚠ S-3/S-4의 `--model` 확인 bash grep은 ExecStart에 line-wrapping 있을 경우 단일 grep fail 가능 → `-o -- --model` 또는 `grep -a` 고려 |

---

## 종합 평가

| 기준 | 평가 |
|------|------|
| Correctness | ✅ 2건 수정 모두 정확 |
| Completeness | ⚠ test_config.py 픽스처 값 검토 가능 |
| Side effects | ✅ 없음 |
| Consistency | ✅ |
| Docs | ⚠ report 커밋 수 명시, grep 명령어 보강 |

**종합**: Merge 준비 완료. 발견된 경미 사항은 report 문서 보강으로 해소 가능.
