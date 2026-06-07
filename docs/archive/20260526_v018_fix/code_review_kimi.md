# Code Review: feature/v018-fix (Kimi K2.6)

**리뷰 모델**: Kimi K2.6 (opencode-go/kimi-k2.6)
**날짜**: 2026-05-26 KST
**기준**: `origin/v0.1.9` → `feature/v018-fix`
**커밋**: 3개 (3 files, +181 -2 lines)

---

## Commit 1 — `d0a6746`: `scripts/lib/config.py:153` lint_interval_hours default 24→3

| 기준 | 평가 | 비고 |
|------|------|------|
| **Correctness** | ✅ | wikihub.yaml.example:35과 render_systemd_units.py:220이 모두 3으로 확인. v0.1.0 시대의 stale default fix |
| **Side effects** | ✅ Low risk | `.get("lint_interval_hours", 3)` — key가 **없는** config만 영향. 운영 yaml의 명시값은 미변경 |
| **Completeness** | ⚠ Minor | `tests/test_config.py:36,48` fixture가 여전히 `lint_interval_hours: 24` + `assert == 24`. 테스트는 통과하나 fixture가 현재 canonical default를 반영하지 않음. fixture를 3으로 갱신 권장 |
| **Style** | ✅ | 1줄 literal 변경, 코드 스타일 문제 없음 |

---

## Commit 2 — `135f961`: `install.sh:1261` remove stale wh-graphify guidance text

| 기준 | 평가 | 비고 |
|------|------|------|
| **Correctness** | ✅ | wh-graphify가 Hermes skill → systemd unit(wikihub-graphify.service)으로 이관 완료. 안내문에서 제거 정확 |
| **Side effects** | ✅ None | 안내문만 변경. 기능/설치 경로 영향 없음 |
| **Style** | ⚠ Nit | `wh-graphify·` 제거로 인해 `model.default` 앞에 **leading space 증가** (공백 1→2). 의도치 않은 정렬 불일치. 필요시 단락 재정렬 가능 |

```diff
   wh-ingest·wh-lint 메인 모델은 wikihub agent.models 가 systemd `--model` 으로 lock — hermes
-  model.default 와 무관. Telegram 대화·미명시 skill (wh-query·wh-graphify·wh-setup) 의
+   model.default 와 무관. Telegram 대화·미명시 skill (wh-query·wh-setup) 의
   model.default 는 운영자 일반 선호로 결정.
```

---

## Commit 3 — `28492eb`: new report `250526_wikihub_v018fix_report.md`

| 기준 | 평가 | 비고 |
|------|------|------|
| **Docs accuracy** | ⚠ Minor | §"최종 git 내역"에 2개 커밋만 표시, report 커밋(28492eb) 미포함. §"브랜치"도 `커밋: 2개`. 3개로 수정 필요 |
| **Completeness** | ✅ | v0.1.8 보고서 5개 교훈 모두 명확한 상태(수정 완료/수정 불필요)와 사유로 정리 |
| **OPS checklist** | ⚠ Minor | S-3/S-4가 `grep ExecStart \| grep -- --model` 사용. systemd show 출력에서 ExecStart가 line-wrap될 경우 두 번째 grep이 fail 가능. `systemctl --user show <unit> -p ExecStart \| grep -o -- --model` 또는 `grep -a` 방어적 fallback 권장 |
| **Style** | ✅ | 명확한 마크다운 구조 |

---

## 종합 평가

| 항목 | 점수 | 조치 |
|------|------|------|
| Correctness | ✅ 모든 커밋 정확 | 없음 |
| Side effects | ✅ 운영 위험 없음 | 없음 |
| Completeness | ⚠ test_config.py fixture; report 커밋 수 불일치 | **권장**: test_config.py fixture 3으로 갱신, report 커밋 수 3개로 정정 |
| Style | ⚠ install.sh leading space drift, grep 명령어 보안 | 선택: 안내문 재정렬, grep -o/-a 추가 |
| Docs accuracy | ⚠ report 커밋 누락, grep 명령어 | 보고서 보강 |

**Bottom line**: 기능 변경은 모두 정확하고 merge 안전. 발견된 gap은 문서/테스트 위생 수준으로 배포를 막지 않음.
