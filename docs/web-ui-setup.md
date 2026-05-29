# WikiHub 웹 UI — hermes-webui + Cloudflare Tunnel 셋업 가이드

> 검토·도입 가이드 (issue #107). **외부 컴포넌트** — wikihub 가 설치/번들하지 않음. OCI 운영자가 별도 도입하는 운영 옵션.

Telegram 단일 인터페이스가 불편할 때, OCI 의 Hermes Agent 에 **브라우저로 접근**하는 웹 UI 를 추가한다. 회사·모바일·집 어디서든 HTTPS 로 hermes 세션·워크스페이스를 사용하는 것이 목표.

## 1. 도구 선택 — 왜 hermes-webui 인가

| | **hermes-webui** (nesquena) | AionUi (iOfficeAI) |
|---|---|---|
| 본질 | **Hermes Agent 전용** 셀프호스트 웹 UI | Electron 데스크톱 Cowork 플랫폼(+headless WebUI) |
| 스택 | Python 3.11+ / vanilla JS / SSE | Electron+React+Vite+Bun / SQLite |
| hermes 결합 | 같은 `~/.hermes/` state·세션 직접 래핑 | 13+ CLI 중 auto-detect (느슨) |
| 배포 | git/Docker(arm64)/`ctl.sh`, 127.0.0.1:8787 | 데스크톱 앱 중심, WebUI 부가 |
| 인증 | 비밀번호+HMAC 쿠키+WebAuthn/passkey | QR+비밀번호 |
| 규모/철학 | 경량·집중 (server-first 정합) | 27k★ 다목적(오피스 자동화·30+ 프로바이더) |
| 라이선스 | MIT | Apache 2.0 |

**채택: hermes-webui.** 래핑하는 Hermes Agent = `NousResearch/hermes-agent` (`hermes` 명령, `~/.hermes/`, `hermes-agent.nousresearch.com`) — wikihub 의 [ADR-0002](adr/0002-hermes-invocation-interface.md)·`.hermes/` gitignore·`hermes chat --skills` 와 동일. 운영 중인 그 hermes 를 그대로 비추므로 통합 리스크 최소. AionUi 는 "여러 에이전트 만능 데스크톱"이 필요할 때의 선택지로, Telegram 대체 목적엔 과함.

> **대상 = OCI hermes.** 로컬 Mac 의 hermes 는 대상 아님. hermes-webui 는 래핑 대상 agent 와 **같은 머신에 co-locate** 되어 그 머신의 `~/.hermes/` 를 읽으므로 **OCI 에 설치**해야 한다.

## 2. 동작 모델 — 한 줄 요약

```
[브라우저 (회사/모바일/집)] ──HTTPS──► [Cloudflare 엣지] ──outbound 443──► [cloudflared (OCI)]
                                                                              │ ingress
                                                                              ▼
                                                                  [hermes-webui 127.0.0.1:8787]
                                                                              │ reads
                                                                              ▼
                                                                  [~/.hermes/  ← Hermes Agent]
```

- **transport**: Cloudflare Tunnel. OCI 의 `cloudflared` 가 **outbound 443** 으로 CF 엣지에 상시 연결 → 브라우저는 `https://wiki.<domain>` 으로 접속. **OCI inbound 포트 개방 0**, 공인 IP 은닉.
- **회사 망 친화**: Tailscale 사용 불가 + SSH 번거로움 환경에서, 평범한 HTTPS outbound 만으로 도달.
- **인증**: hermes-webui 자체(비밀번호 + passkey) + (선택) Cloudflare Access 엣지 인증.
- **bind**: `127.0.0.1` 고정 — 터널이 로컬로 붙으므로 `0.0.0.0` 금지.

## 3. 사전 조건

| 항목 | 확인 |
|---|---|
| OCI 에 Hermes Agent 네이티브 설치·운영 중 | `command -v hermes` 절대 경로 |
| `~/.hermes/` state 존재 | `ls ~/.hermes/` (config.yaml, skills 등) |
| Cloudflare 계정 + 위임 가능 도메인 | 레지스트라에서 NS 를 Cloudflare 로 변경 가능 |
| Python 3.11+ | `python3 --version` |

## 4. 서버 측 (OCI) — hermes-webui 설치

### 4.1 설치 방식 — 네이티브 권장 (Docker 대비)

OCI 에 **이미 네이티브 hermes 가 도므로** 네이티브 webui 설치가 더 깔끔하다.

| | 네이티브 (start.sh + systemd --user) | Docker (단일 컨테이너) |
|---|---|---|
| hermes 연결 | bootstrap 이 **기존 OCI hermes auto-detect** 후 사용 | "agent in-process" → 컨테이너 안에 **또 다른 hermes** 구동 |
| `~/.hermes` | 동일 디렉터리 직접 공유 | host `~/.hermes` 마운트 → 네이티브 daemon 과 동시 read/write (cron jobs.json·memory·세션 DB lock 충돌 우려) |
| UID/GID | 무관 | 마운트 UID 정렬 필요 (OCI `ubuntu`=1000 이라 기본 OK) |
| wikihub systemd | `systemd --user` 패턴 동일 | 별도 런타임 추가 |

→ Telegram daemon + webui 가 **같은 hermes 를 공유하는 두 프런트엔드**가 되어 cron/memory/skill 중복 구동 없이 세션만 분리된다.

### 4.2 설치 + 데몬화

```bash
# OCI
git clone https://github.com/nesquena/hermes-webui.git ~/hermes-webui
cd ~/hermes-webui
python3 bootstrap.py --no-browser   # 기존 hermes auto-detect, venv 생성, /health 대기
```

`bootstrap.py` 는 기존 Hermes Agent 를 감지하고(없으면 공식 installer 시도), Python 환경·의존성을 구성한다. 동작 확인 후 `Ctrl+C`.

상시 구동 — `systemd --user` (`--foreground` 필수: 없으면 detach 되어 supervisor 가 무한 respawn):

```ini
# ~/.config/systemd/user/hermes-webui.service
[Unit]
Description=Hermes Web UI
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/hermes-webui
Environment=HERMES_WEBUI_HOST=127.0.0.1
Environment=HERMES_WEBUI_PORT=8787
ExecStart=/bin/bash %h/hermes-webui/start.sh --foreground
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now hermes-webui.service
loginctl enable-linger "$USER"   # 로그아웃 후에도 유지 (wikihub 운영 패턴 동일)
```

> `ctl.sh start|stop|restart|status|logs` 로도 관리 가능 (백그라운드 데몬, 로그 `~/.hermes/webui.log`). 단 systemd 와 병행하지 말 것.

### 4.3 환경변수

| var | 기본 | 용도 |
|---|---|---|
| `HERMES_WEBUI_HOST` | `127.0.0.1` | bind 주소 — **유지** (터널 뒤) |
| `HERMES_WEBUI_PORT` | `8787` | 포트 |
| `HERMES_WEBUI_PASSWORD` | — | 비밀번호 인증 활성화 — **반드시 설정** |
| `HERMES_WEBUI_AGENT_DIR` | auto-detect | hermes-agent 경로 |
| `HERMES_WEBUI_STATE_DIR` | `~/.hermes/webui` | 세션/state 경로 |
| `HERMES_WEBUI_CSP_CONNECT_EXTRA` | — | 리버스 프록시 origin (SSE 막힐 때 `https://wiki.<domain>`) |

### 4.4 워크스페이스 (선택)

파일 브라우저 root 를 wikihub `wiki/` 데이터 경로로 지정하면 entities/concepts/analyses 를 웹 트리에서 탐색할 수 있다.

## 5. Cloudflare Tunnel 설정

```
cloudflared(OCI, outbound 443) ──► Cloudflare 엣지 ──► 브라우저
        └─► http://127.0.0.1:8787 (ingress)
```

1. 보유 도메인을 Cloudflare 에 등록 (레지스트라에서 NS 위임).
2. OCI 에 `cloudflared` (arm64) 설치 → `cloudflared tunnel login` (브라우저 1회 인증).
3. `cloudflared tunnel create wikihub-webui` → credentials 생성.
4. `~/.cloudflared/config.yml`:
   ```yaml
   tunnel: wikihub-webui
   credentials-file: /home/ubuntu/.cloudflared/<UUID>.json
   ingress:
     - hostname: wiki.<domain>
       service: http://127.0.0.1:8787
     - service: http_status:404
   ```
5. `cloudflared tunnel route dns wikihub-webui wiki.<domain>` → DNS CNAME 자동 생성.
6. `sudo cloudflared service install` → systemd 상시 구동.

→ OCI inbound 0, TLS·hostname Cloudflare 제공. 회사 outbound 443 이면 접속.

## 6. Cloudflare Access (선택 — 엣지 인증, defense in depth)

Tunnel 위에 한 겹 더. **트래픽이 OCI 에 닿기 전 Cloudflare 엣지에서 인증** → webui 로그인 화면조차 외부 비노출.

- Zero Trust → Access → Applications → **Self-hosted** → `wiki.<domain>`.
- Policy: **Allow**, Include = `Emails: <your email>` (또는 도메인), 인증 **One-time PIN(email OTP)** — IdP 불필요, 무료 50명.
- 회사망/모바일 모두 HTTPS + 이메일 OTP 라 통과.
- 조합: 엣지(Access OTP) + webui(passkey) = 2계층. 원하면 webui passkey-only 로 단순화.

## 7. 보안 모델

| 항목 | 내용 |
|---|---|
| **인증** | `HERMES_WEBUI_PASSWORD`(필수) → 첫 로그인 후 Settings→System 에서 **passkey(WebAuthn)** 등록 → passkey 주 인증, 비밀번호 복구용 유지/제거 선택 |
| **세션** | HMAC-SHA256 서명 HttpOnly 쿠키, 24h TTL, 로그인 rate limiting(PBKDF2), 보안 헤더(`X-Frame-Options` 등) 기본 |
| **노출 표면** | OCI inbound 0 (cloudflared outbound only), 공인 IP 은닉, `127.0.0.1` bind 유지 |
| **엣지 인증** | (선택) Cloudflare Access OTP — OCI 도달 전 차단 |
| **mutation** | hermes-webui 는 `~/.hermes/webui/` 자기 영역만 write. hermes-agent 파일·`config.yaml` 미수정 |

## 8. 걷어내기 (uninstall)

**완전 가역. hermes/wikihub 무영향** — webui 는 자기 영역에만 쓰고 hermes-agent·`config.yaml` 을 건드리지 않는다. (공식 uninstall 스크립트는 없으므로 아래가 정본 절차.)

### 8.1 네이티브 설치 footprint

| 대상 | 경로 |
|---|---|
| 설치 디렉터리(repo + `.venv`) | `~/hermes-webui/` |
| webui state (세션·설정·passkey·첨부) | `~/.hermes/webui/` |
| 로그 / PID | `~/.hermes/webui.log` / `~/.hermes/webui.pid` |
| systemd 유닛 | `~/.config/systemd/user/hermes-webui.service` |

### 8.2 절차 (OCI)

```bash
# (a) 서비스 정지·비활성
systemctl --user disable --now hermes-webui.service
rm -f ~/.config/systemd/user/hermes-webui.service
systemctl --user daemon-reload
#   (ctl.sh 로 띄웠다면)  ~/hermes-webui/ctl.sh stop

# (b) 설치 디렉터리 제거
rm -rf ~/hermes-webui

# (c) state·로그 제거  ← 세션/passkey 보존하려면 생략
rm -rf ~/.hermes/webui
rm -f  ~/.hermes/webui.log ~/.hermes/webui.pid

# hermes-agent · wikihub config.yaml · skill · cron · 세션 → 전부 그대로
```
재설치 시 `~/.hermes/webui/` 만 남기면 세션·passkey·설정이 복원된다.

### 8.3 Cloudflare 측 정리 (dangling 주의)

```bash
sudo cloudflared service uninstall          # systemd 서비스 제거
cloudflared tunnel delete wikihub-webui     # 커넥터 정지 후 가능
rm -rf ~/.cloudflared                         # credentials + config.yml
```
대시보드 추가 정리:
- **DNS**: `wiki.<domain>` CNAME 삭제 (안 지우면 죽은 터널 가리키는 dangling CNAME).
- **Access**(설정 시): Zero Trust → Access → Applications 에서 app·policy 삭제.

## 9. 동작 검증 (DoD)

- [ ] hermes-webui 가 OCI 에서 기존 Hermes Agent 세션·메모리·scheduled job(`~/.hermes/cron/`) 을 그대로 노출
- [ ] Cloudflare Tunnel 경유로 회사·모바일·집 브라우저에서 HTTPS 접속 성공
- [ ] OCI inbound 포트 추가 개방 0 (tunnel outbound only)
- [ ] 인증(passkey/비밀번호, 선택 CF Access) 동작
- [ ] `wiki/` 워크스페이스 브라우징 + hermes 채팅 동작 확인

## 10. troubleshooting

| 증상 | 원인 / 확인 |
|---|---|
| 브라우저 접속 시 502/연결 안 됨 | `systemctl --user status hermes-webui` + `cloudflared` 서비스 상태 / ingress `service` 포트 8787 일치 확인 |
| 응답 스트리밍(SSE) 끊김 | CSP — `HERMES_WEBUI_CSP_CONNECT_EXTRA=https://wiki.<domain>` 설정 후 재시작 |
| 로그아웃 후 서비스 죽음 | `loginctl enable-linger "$USER"` 누락 |
| 무한 respawn | `start.sh` 에 `--foreground` 누락 |
| dead CNAME (터널 삭제 후) | Cloudflare 대시보드에서 `wiki.<domain>` CNAME 수동 삭제 (§8.3) |
| 워크스페이스 비어 보임 | (Docker 한정) 마운트 UID/GID 불일치 — 네이티브는 비해당 |

## 11. 관련 문서

- issue #107 — 도입 검토·결정 trace
- [ADR-0002](adr/0002-hermes-invocation-interface.md) — Hermes invocation interface (대상 hermes 동일성 근거)
- [ADR-0043](adr/0043-mcp-integration.md) — MCP integration (외부 read-only 접근, Phase 2 Cloudflare Tunnel 트리거)
- [docs/mcp-setup.md](mcp-setup.md) — MCP client 셋업 (LLM client 용 read-only 접근, 본 가이드와 상호보완)
- [docs/roadmap.md](roadmap.md) — Phase 2 "Cloudflare Tunnel integration"
- 외부: [nesquena/hermes-webui](https://github.com/nesquena/hermes-webui), [NousResearch/hermes-agent](https://github.com/nousresearch/hermes-agent)

> **후속(미정)**: 실제 도입 확정 시 ADR(외부 웹 인터페이스 정책) 작성 + roadmap Phase 2 상태 갱신 검토. 본 문서는 그 전 단계의 검토·셋업 가이드.
