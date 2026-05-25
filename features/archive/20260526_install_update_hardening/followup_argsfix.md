# install_update_hardening — followup_argsfix

본 feature 의 76b15b2 검증 중 surface 한 sub-결함 fix.

## Surface 경위

multipass `wikihub-test` 에서 두 번째 `install.sh --version canary` 호출 (disk = 76b15b2) — self-restart + fd close 정합 동작 ✓ (자식 process Step 1 통과 trace 확인) → 그러나 자식이 `--version` 인자 없이 시작 → `_resolve_ref` 가 `refs/tags/latest` 로 fallback → eb766ef (v0.1.7) → downgrade detect → rollback.

trace:
```
INFO  install.sh self-restart with refreshed source (post-reset)
─── install.sh start: 2026-05-25T16:13:09Z ───
OK    Step 1 환경 검증 완료
INFO  current version: v0.1.8 (HEAD 76b15b2)
...
INFO  git reset --hard refs/tags/latest    ← 자식이 --version canary 미수신
ERROR unexpected downgrade detected: v0.1.8 → v0.1.7
```

## 근본 원인

self-restart block 이 `_step2_update()` 함수 (L1420) 의 scope 안. bash 에서 함수 안의 `$@` = 그 함수의 인자. `_step2_update` 는 L1814 에서 인자 없이 호출 → 함수 안 `$@` = empty → `exec "$WIKIHUB_SRC/install.sh" "$@"` 의 인자 전파 0.

`bootstrap_clone_then_exec` L169 는 함수 scope 인데도 정합인 이유: top-level L124 의 `ORIGINAL_ARGS=("$@")` 캡처 (script 시작 시 모든 인자 보존) + 함수 안에서 `${ORIGINAL_ARGS[@]}` 참조.

## Fix

```diff
-        exec "$WIKIHUB_SRC/install.sh" "$@"
+        exec "$WIKIHUB_SRC/install.sh" "${ORIGINAL_ARGS[@]}"
```

## DoD

- [ ] install.sh self-restart 의 `$@` → `${ORIGINAL_ARGS[@]}` 변경
- [ ] multipass 회피 없이 통과 + 자식 process 가 `--version canary` 정합 수신
- [ ] v0.1.8 squash + canary force-update
