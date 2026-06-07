# Wikihub — v0.1.9: feature/v018-fix Lessons Learned Report

**날짜**: 2026-05-26 KST
**버전**: v0.1.9 (feature/v018-fix)
**기반**: v0.1.8 업데이트 보고서 (§G 교훈)
**수행자**: Hermes Agent (deepseek-v4-pro)

---

## 개요

v0.1.7→v0.1.8 업데이트 과정에서 수집된 5개 교훈(§G)을 바탕으로 코드베이스 검토 및 수정 작업을 `feature/v018-fix` 브랜치에서 순차적으로 진행.

---

## 작업 내역

### Lesson 1 — 업데이트 경로 결함 (install.sh in-memory 배열)

| 항목 | 내용 |
|------|------|
| 상태 | **수정 불필요** |
| 사유 | v0.1.8에 도입된 self-restart 메커니즘(exec 재호출)이 이미 문제를 해결함. git reset 후 새 install.sh를 exec하므로 in-memory 배열이 항상 최신 파일 시스템 상태를 반영 |

### Lesson 2 — lint_interval_hours 기본값 불일치

| 항목 | 내용 |
|------|------|
| 상태 | **수정 완료** |
| 대상 | `scripts/lib/config.py:153` |
| 변경 | `int(ocfg.get("lint_interval_hours", 24))` → `... 3` |
| 사유 | yaml.example과 render_systemd_units.py는 3h로 일관되었으나, config.py만 v0.1.0 시대의 24h 기본값이 잔존. yaml.example/template과 불일치 해소 |
| 커밋 | `d0a6746` |

### Lesson 3 — agent.models auto-injection

| 항목 | 내용 |
|------|------|
| 상태 | **수정 불필요** |
| 사유 | render_systemd_units.py의 `--model` 주입 로직 정상. `agent.models`에 없는 skill은 `--model` arg 없이 Hermes 기본 모델 사용. 보고서의 "silent change"는 render layer가 아닌 migration layer(`_migrate_agent_schema`)의 정상 동작 |

### Lesson 4 — graphify skill 잔여 참조

| 항목 | 내용 |
|------|------|
| 상태 | **수정 완료** |
| 대상 | `install.sh:1261` |
| 변경 | 설치 후 안내문에서 `wh-graphify·` 참조 제거 (systemd unit으로 이관 완료, 더 이상 Hermes skill 아님) |
| 커밋 | `135f961` |

### Lesson 5 — gws_min_version 잔존

| 항목 | 내용 |
|------|------|
| 상태 | **수정 불필요** |
| 사유 | ADR-0035 구현 시 이미 코드베이스(wikihub.yaml.example, config.py, migration)에서 정리 완료. 보고서의 `gws_min_version: 0.22.5`는 OCI 서버 운영 wikihub.yaml에만 존재 (소스 관리 밖). 남은 참조는 모두 ADR-0035 관련 주석/docs로 유지 필요 |

---

## 최종 git 내역

```
28492eb docs(lesson-report): add v018-fix lessons learned report with OPS verification checklist
135f961 fix(lesson-4): remove stale wh-graphify reference from install.sh guidance text
d0a6746 fix(lesson-2): align config.py lint_interval_hours default (24→3) with yaml.example
```

---

## 브랜치

- **브랜치**: `feature/v018-fix`
- **기준**: `origin/v0.1.9`
- **커밋**: 3개
- **미처리 이슈**: 없음 (Lesson 1/3/5는 검토 결과 수정 불필요)

---

## 참고

- ADR-0035: gws_min_version 폐기
- 원본 보고서: `250525_wikihub_v018_update_report.md`

---

## 운영서버(OCI) 확인 사항

v0.1.8 업데이트 후 아래 항목들을 운영서버에서 확인 필요:

### S-1. systemd unit 상태 확인

```bash
systemctl --user list-timers
systemctl --user status mount@gdrive.service
systemctl --user status lint.service
systemctl --user status vault@gdrive.service
systemctl --user status wikihub-graphify.service
systemctl --user status wikihub-monitor.service
```

| unit | 확인 사항 |
|------|----------|
| mount@gdrive.service | active (running) 유지 |
| lint.timer | enabled, OnUnitInactiveSec=3h (복원값 유지) |
| vault@gdrive.timer | enabled, OnUnitInactiveSec=3600s |
| pending-monitor.timer | enabled, 30min |
| wikihub-monitor.timer | enabled, 09:00/21:00 KST |
| wikihub-graphify.service | static, lint Step 9에서 정상 trigger |

### S-2. lint timer 간격 확인

v0.1.8 설치 후 3h로 복원했으나, yaml.example 동기화로 재설정될 가능성 있음.

```bash
systemctl --user show lint.timer | grep OnUnitInactiveSec
```

기대값: `OnUnitInactiveSec=3h`

### S-3. vault@gdrive.service model 확인

```bash
systemctl --user show vault@gdrive.service -p ExecStart | grep -o -- '--model [^ ]*'
```

기대값: `--model deepseek-v4-flash` (복원값, yaml.example의 pro 아님)

### S-4. agent.models 주입 확인 (Lesson 3)

lint.service에 `--model` arg가 자동 주입되었는지 확인:

```bash
systemctl --user show lint.service -p ExecStart | grep -o -- '--model [^ ]*'
```

- `--model deepseek-v4-flash` 있음 → yaml.example 동기화에 따른 정상 주입
- 없음 → yaml.example에 `agent.models.wh-lint` 누락 가능성

### S-5. wikihub.yaml 잔존 필드 확인 (Lesson 5)

```bash
grep -n 'gws_min_version\|bootstrap_allowed' ~/wikihub/wikihub.yaml
```

- `gws_min_version: 0.22.5` 있음 → ADR-0035 폐기 필드. 차기 정리 시 수동 제거 권장
- `bootstrap_allowed` 있음 → 마찬가지로 제거 대상

### S-6. yq 설치 확인

```bash
yq --version
```

기대: `yq 4.44.3` (v0.1.8 신규 의존성)

### S-7. graphify 동작 확인 (Lesson 4)

```bash
# graphify 수동 트리거 (lint가 trigger하기 전에)
systemctl --user start wikihub-graphify.service
journalctl --user -u wikihub-graphify.service --no-pager -n 20
```

정상 실행 및 타임아웃(900s) 내 완료 확인

### S-8. 업데이트 경로 재현 테스트 (Lesson 1)

대상: OCI 서버에서 v0.1.8 → v0.1.9 (실제 또는 dry-run)

```bash
# 현재 버전 확인
git -C ~/wikihub describe --tags

# v0.1.8의 self-restart 경로 확인 (재현 테스트)
# 가상 시나리오: wh-xxx skill 추가/제거 시 in-memory 배열 결함 재발 여부
```

핵심 검증 포인트:
- self-restart(exec)가 in-memory bash 배열을 최신화하는지
- `WIKIHUB_SKILLS` 배열에 추가/제거된 skill이 올바르게 반영되는지
- `_step6_agent_skill` / `_materialize_skills` 단계 통과

