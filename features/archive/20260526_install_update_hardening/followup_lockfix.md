# install_update_hardening — followup_lockfix

본 feature 의 c17f13c 검증 중 surface 한 sub-결함 fix.

## Surface 경위

multipass `wikihub-test` 에서 `install.sh --version canary` 회피 없이 호출 → trace:

```
INFO  install.sh self-restart with refreshed source (post-reset)
─── install.sh start: 2026-05-25T16:10:43Z ───
ERROR 다른 install.sh 가 진행 중 (lock: /home/ubuntu/wikihub/install.lock)
```

self-restart 는 동작 (trace 명시) — 새 process 가 `_acquire_install_lock` 에서 fail. **부모 process 의 fd 200 (install.lock flock target) 이 exec 자식 process 에 자연 상속** → 새 process 가 fresh lock 시도 시 자기 자신의 inherited fd 가 already-held lock 으로 보임.

## Fix

`bootstrap_clone_then_exec` L161 의 동일 패턴 적용:

```diff
 if [[ -z "${WIKIHUB_INSTALL_SELF_RESTARTED:-}" ]]; then
     info "install.sh self-restart with refreshed source (post-reset)"
     export WIKIHUB_INSTALL_SELF_RESTARTED=1
+    exec 200>&- 2>/dev/null || true
     exec "$WIKIHUB_SRC/install.sh" "$@"
 fi
```

`exec 200>&-` — fd 200 명시 close. exec 후 새 process 가 fresh lock 잡음.

## 검증

multipass `install.sh --version canary` 회피 없이 호출 — 통과 확인 후 본 followup squash.

## DoD

- [ ] install.sh self-restart 직전 fd 200 close 추가
- [ ] multipass 회피 없이 통과 확인
- [ ] v0.1.8 squash + canary force-update

## Step 적용

- Step 1 (Plan): 본 문서로 대체 — trivial scope, sub-결함 fix
- Step 2~3 (Analysis & Design + Implementation): 본 문서 + diff
- Step 4 (Review): 생략 (1 line fix + 외부 인터페이스 미변경)
- Step 5 (Deploy): squash + canary
