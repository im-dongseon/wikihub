# WikiHub MCP server — 외부 client 셋업 가이드 (Phase 1)

> ADR-0043 정합. read-only MCP server + stdio + SSH spawn. v0.1.10 / Phase 1.

회사 노트북 · 개인 IDE · Claude Desktop 등 **MCP-호환 client** 에서 OCI VM 의 wikihub 데이터를 read-only 로 query 한다. daemon 없이 sshd + Python venv 만 재사용.

## 1. 동작 모델 — 한 줄 요약

```
[client (Claude Desktop)] ── ssh subprocess ──► [OCI VM] ── stdio ──► [wikihub_mcp.py]
                              (per-session)        (sshd)             (read-only, LLM 0)
```

- **transport**: stdio + 외부 client 가 `ssh <host> '<python> <wikihub_mcp.py>'` 명령으로 원격 subprocess 를 띄움. stdin/stdout 가 그대로 MCP JSON-RPC pipe.
- **daemon**: 없음. 매 MCP session 마다 ssh + python subprocess 한 번 spawn → session 종료 시 close. systemd unit, reverse proxy, TLS cert 전부 불필요.
- **인증**: SSH key. 별도 Bearer token 없음.
- **scope**: read-only — `wiki/` 디렉토리 read 만. mutation 0. OAuth credential 접근 0.

## 2. 서버 측 (OCI VM) 셋업

### 2.1 사전 조건

| 항목 | 확인 |
|---|---|
| wikihub install 완료 | `cat ~/wikihub/wikihub.yaml` 정상 |
| venv | `~/.local/share/wikihub/venv/bin/python` 존재 |
| `mcp` dependency | `<venv>/bin/python -c 'import mcp'` 성공 (PR2 머지 후 install.sh 재호출로 자동 install) |
| `wikihub_mcp.py` | `~/.local/share/wikihub/src/scripts/wikihub_mcp.py` 존재 |
| sshd | 운영자가 평소 SSH 접근하는 상태 |

### 2.2 SSH key 등록 (client 측 pub key → server `authorized_keys`)

client 노트북에서 생성된 SSH key 의 **public** key 를 OCI VM 의 `~/.ssh/authorized_keys` 에 1줄 추가한다.

```bash
# server 에서
mkdir -p ~/.ssh && chmod 700 ~/.ssh
cat /path/to/client_id_ed25519.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

client 마다 별도 key — 노트북 분실 시 그 key 만 제거.

### 2.3 OCI 측 포트 설정 검토

회사 망의 outbound 정책에 따라 4 가지 layer 확인 필요. **운영자가 평소 SSH 가능한 환경이면 2.3.1 (기본) 만 확인.**

#### 2.3.1 기본 — outbound 22 OK 케이스 (가장 흔함)

운영자가 평소 노트북에서 `ssh ubuntu@<oci-public-ip>` 정상 동작하면 추가 설정 0. 다음 4 layer 모두 22 통과 보장:
- **OCI Security List / NSG** — 기본 generated rule 에 ingress 22 (TCP, 0.0.0.0/0) 가 보통 포함됨.
- **OCI Cloud Shell vs Console firewall** — 무관 (운영자 SSH 동작 시점에 이미 통과).
- **OS firewall (Ubuntu 24.04 `ufw`)** — OCI Ubuntu 기본 이미지는 `ufw` 비활성. `sudo ufw status` 가 `inactive` 면 무관.
- **`iptables`** — OCI ARM Ubuntu 이미지는 InstancePrincipals / OCI Compute Agent 가 추가 rule 넣을 수 있음. `sudo iptables -L INPUT -n -v` 로 22 ACCEPT 확인 (또는 운영자 SSH 가 동작하면 OK).

→ **추가 작업 없음.** client 측 (§3) 만 셋업.

#### 2.3.2 outbound 22 막힘 + 443 만 허용 (대기업 흔함)

회사 노트북에서 `ssh ubuntu@<oci-public-ip>` 가 timeout/refused 이고 outbound 443 만 허용된다면, **OCI sshd 에 Port 443 추가 listen** 으로 해결.

**자가 진단** (어느 케이스인지 모를 때) — client 에서 OCI 의 port 도달 가능 여부 확인:
```bash
# client
nc -vz <oci-public-ip> 22    # 성공이면 §2.3.1 (기본), 실패면 다음
nc -vz <oci-public-ip> 443   # 성공이면 §2.3.2, 둘 다 실패면 §2.3.3/§2.3.4
```

**Step A. sshd_config 갱신**:
```bash
# server
sudo nano /etc/ssh/sshd_config
# 또는 sed shortcut (단, 기존 `#Port 22` 가 commented 형식일 때만 동작):
sudo sed -i '/^#Port 22/a Port 443' /etc/ssh/sshd_config
# Port 22 가 이미 uncommented 면 위 sed 는 silent no-op — nano 로 직접 추가 권장
sudo grep -E '^Port' /etc/ssh/sshd_config   # 결과에 "Port 22" 와 "Port 443" 둘 다 보여야 함
sudo sshd -t   # syntax check
sudo systemctl reload ssh
```

**Step B. OCI Security List ingress 443**:

OCI Console → Networking → Virtual Cloud Networks → 해당 VCN → Security Lists → 기본 Security List (또는 NSG) → **Add Ingress Rules**:
- Source CIDR: `0.0.0.0/0` (또는 회사 망 NAT IP 대역 narrow)
- IP Protocol: TCP
- Destination Port Range: `443`

```bash
# CLI 로도 가능 — oci network security-list update --add-ingress-rule ...
```

**Step C. OS firewall**:
```bash
# server
sudo ufw status   # inactive 면 무관
# active 이면:
sudo ufw allow 443/tcp
```

**Step D. 충돌 확인** — OCI VM 의 443 을 다른 service (Caddy / nginx) 가 안 쓰는지 확인:
```bash
sudo ss -tlnp | grep ':443'
```
사용 중이면 sshd 의 Port 가 다른 값 (예: 2222) 으로 + 회사 망 outbound 가 그 port 허용 여부 확인.

**Step E. client 측 검증** — `ssh -p 443 ubuntu@<oci-ip>` 로 SSH 가능 확인.

#### 2.3.3 모든 outbound proxy 강제 경유

회사 망의 모든 outbound TCP 가 proxy (`proxy.company.com:8080` 같은 형식) 거쳐야 한다면 client 측 `~/.ssh/config` 의 `ProxyCommand` 사용. 자세한 사항은 §3.3.

서버 측 추가 작업은 §2.3.2 와 동일 (Port 443 listen + Security List rule).

#### 2.3.4 OCI VM 도달 불가 — Phase 2 필요

회사 망에서 OCI VM 의 어떤 port 에도 outbound 도달 불가하면 SSH tunnel 자체가 불가능 → **Phase 2 (Cloudflare Tunnel 또는 비슷한 outbound-only reverse tunnel) 필요**. ADR-0043 §재검토 트리거 참조. 본 가이드 Phase 1 scope 외.

### 2.4 sshd hardening 권고 (optional)

별도 MCP 전용 user 분리 (선택 — 보안 분리도 ↑):

```bash
# server
sudo adduser --disabled-password --gecos "" mcp-readonly
sudo usermod -aG ubuntu mcp-readonly  # 또는 별도 group
sudo -u mcp-readonly mkdir -m 700 -p ~mcp-readonly/.ssh
sudo cp ~ubuntu/.ssh/authorized_keys ~mcp-readonly/.ssh/authorized_keys
sudo chown mcp-readonly:mcp-readonly ~mcp-readonly/.ssh/authorized_keys
sudo chmod 600 ~mcp-readonly/.ssh/authorized_keys
```

이후 client `~/.ssh/config` 의 `User` 를 `mcp-readonly` 로. **wikihub VM 의 wiki/ 가 group/world readable 한지** 확인 후 적용 (read-only 운영 정합).

## 3. 클라이언트 측 (회사 노트북) 셋업

### 3.1 SSH key + `~/.ssh/config`

```bash
# client (회사 노트북 — macOS)
ssh-keygen -t ed25519 -f ~/.ssh/wikihub_id_ed25519 -N ""
cat ~/.ssh/wikihub_id_ed25519.pub
# 이 출력값을 §2.2 단계에서 server `~/.ssh/authorized_keys` 에 추가
```

`~/.ssh/config` 에 host alias 추가:
```
Host wikihub-oci
    HostName 1.2.3.4              # OCI VM public IP (또는 도메인)
    User ubuntu                   # §2.4 의 mcp-readonly 적용 시 그것
    Port 22                       # §2.3.2 적용 시 443
    IdentityFile ~/.ssh/wikihub_id_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30        # NAT timeout 방지
    ServerAliveCountMax 3
```

검증:
```bash
ssh wikihub-oci 'echo hello && hostname'
# 출력: hello / wikihub-test  (또는 hostname 그대로)
```

### 3.2 Claude Desktop config

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) 또는
`%APPDATA%\Claude\claude_desktop_config.json` (Windows).

> **Windows 전제**: OpenSSH Client optional feature 설치 필요 — Settings → Apps → Optional Features → "OpenSSH Client". `where ssh` 로 `C:\Windows\System32\OpenSSH\ssh.exe` 출력 확인.

```json
{
  "mcpServers": {
    "wikihub": {
      "command": "ssh",
      "args": [
        "wikihub-oci",
        "/home/ubuntu/.local/share/wikihub/venv/bin/python",
        "/home/ubuntu/.local/share/wikihub/src/scripts/wikihub_mcp.py"
      ]
    }
  }
}
```

`mcp-readonly` user 적용 시 path 의 `ubuntu` → `mcp-readonly` 또는 절대 path 그대로 (read 권한이면 OK).

Claude Desktop 재시작 → 새 chat 의 tool 아이콘에서 `wikihub` server 의 5 tool (`list_entities` / `list_concepts` / `read_page` / `grep_wiki` / `search_by_alias`) 노출 확인.

### 3.3 회사 망 fallback — ProxyCommand

§2.3.3 (corporate proxy 강제 경유) 케이스 — `~/.ssh/config` 에 `ProxyCommand` 추가:

```
Host wikihub-oci
    HostName 1.2.3.4
    Port 443
    User ubuntu
    IdentityFile ~/.ssh/wikihub_id_ed25519
    # HTTP CONNECT proxy 경유
    ProxyCommand /usr/local/bin/corkscrew proxy.company.com 8080 %h %p
    # 또는 nc/ncat:
    # ProxyCommand nc -X connect -x proxy.company.com:8080 %h %p
```

`corkscrew` 는 `brew install corkscrew` (macOS) 로 설치. `nc -X connect` 도 BSD/macOS 기본 가능.

### 3.4 다른 MCP-호환 client (Cline / Continue.dev 등)

각 client 의 server registration UI 또는 config 파일에 동일한 `command="ssh"` + args 형식으로 등록. 일부 client 는 stdio 외 SSE 도 지원 — Phase 1 은 stdio 만 호환.

## 4. 동작 검증

### 4.1 server 측 직접 실행 (smoke test)

```bash
# server
~/.local/share/wikihub/venv/bin/python ~/.local/share/wikihub/src/scripts/wikihub_mcp.py
# stdin 대기 — 그대로 Ctrl+C
```

### 4.2 client 측 ssh + 직접 실행

`WIKIHUB_HOME` 을 default 외 위치로 override 한 경우 명시 export 필요 (비인터랙티브 ssh 는 `~/.bashrc` 의 env 일부 미import 가능).

```bash
# client
ssh wikihub-oci 'WIKIHUB_HOME=$HOME/wikihub /home/ubuntu/.local/share/wikihub/venv/bin/python -c "import importlib.util; spec=importlib.util.spec_from_file_location(\"wikihub_mcp\", \"/home/ubuntu/.local/share/wikihub/src/scripts/wikihub_mcp.py\"); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print(m._list_vault_ids())"'
# 출력: ['gdrive']  (또는 yaml 의 vault id 목록)
```

### 4.3 Claude Desktop 호출 예시

new chat 에서:
> "wikihub MCP 의 entities 목록 알려줘"
> → tool 사용 (list_entities) → 결과
>
> "wikihub 에서 'mini-max' 관련 entity 찾아"
> → tool 사용 (search_by_alias) → ADR-0042 resolver 가 `MiniMax` 페이지로 매칭

## 5. 보안 모델 / 제한사항

| 항목 | Phase 1 |
|---|---|
| **인증** | SSH key 만 |
| **권한** | server 의 SSH user (보통 `ubuntu`) 의 filesystem 권한. wiki/ read 만 사용 |
| **mutation** | **0** — `wikihub_mcp.py` 가 file write/append/rename/unlink 호출 없음 |
| **OAuth credential** (rclone.conf) | MCP server 가 직접 read 안 함. SSH user 권한 차원에서 접근 가능하나 호출 0 |
| **path traversal** | `_safe_under(Path.resolve(), base.resolve())` 가드로 `wiki/` 바깥 read 차단 |
| **rate limit** | 없음 (per-session spawn 이라 burst 영향 SSH 본인) |
| **audit log** | sshd 로그 (`/var/log/auth.log`) — MCP 자체 access log 별도 없음 |

**알려진 제한** (ADR-0043 §재검토 트리거):
- 다중 client 시 SSH key 관리 부담 — Phase 2 (Bearer token + SSE) 도입 검토
- IDE plugin 등 SSH 호출 불가 client 미지원 — Phase 2 SSE/HTTP 필요
- write tool (lint trigger 등) 부재 — 별도 ADR + 인증 강화 필요

## 6. troubleshooting

| 증상 | 원인 / 확인 |
|---|---|
| Claude Desktop 의 tool 아이콘에 wikihub 안 보임 | `claude_desktop_config.json` json syntax (trailing comma 등) / Claude Desktop 완전 재시작 / `claude_desktop_config.json` 위치 (macOS vs Windows) |
| ssh 직접 호출은 OK 인데 Claude Desktop 만 fail | Claude Desktop 의 PATH 에 `ssh` 없을 가능성 (rare on macOS) → `args` 의 `ssh` 를 절대 path (`/usr/bin/ssh`) 로 |
| `Connection timed out` | server outbound port (회사 망) — §2.3.2 (Port 443) 적용 검토 |
| `Permission denied (publickey)` | client `~/.ssh/wikihub_id_ed25519` 권한 (`chmod 600`) / server `~/.ssh/authorized_keys` 권한 (`chmod 600`) / pub key copy 누락 |
| `import mcp` ModuleNotFoundError | install.sh 재호출 또는 `uv pip install --require-hashes --python ~/.local/share/wikihub/venv/bin/python -r ~/.local/share/wikihub/src/scripts/requirements.txt` 수동 실행 (uv 는 system `~/.local/bin/uv`) |
| `vault_id 'xxx' 미존재` | `wikihub.yaml.vaults[*].id` 와 client 가 요청한 vault_id 가 다름 — `list_vault_ids` 출력 확인 |
| `path 미존재 또는 scope 외 path` | sources name 에 `../` 가 포함됐거나 실재 파일 부재. wiki 디렉토리 내 path 만 |

server 측 로그:
```bash
# server — wikihub_mcp.py 는 stderr 로만 log (stdio MCP 라 stdout 은 protocol 전용)
journalctl --user -t wikihub-mcp 2>&1   # 없음 — daemon 아님
# 대신 ssh session 의 server 측 출력은 client 의 ssh stderr 로 갱신됨
```

## 7. Phase 2 forward pointer

다음 시나리오 surface 시 Phase 2 도입 (ADR-0043 §재검토 트리거):

| 트리거 | Phase 2 옵션 |
|---|---|
| 회사 망 outbound 22 / 443 둘 다 막힘 | **Cloudflare Tunnel** — outbound-only reverse tunnel. wikihub VM 이 CF 에 outbound connection 유지 + 회사 client 는 `https://wikihub.<domain>` HTTPS 호출. Cloudflare Access (Zero Trust) 로 SSO/token 인증 추가 |
| 다중 client (3+ 명) | SSE/HTTP + Bearer token + reverse proxy (Caddy/nginx) + Let's Encrypt cert. systemd unit `wikihub-mcp.service` (ADR-0041 prefix 정합) |
| write tool 필요 | 별도 ADR + 인증 강화 (Bearer token + audit log + permission scope) |
| IDE plugin 호환 (SSH spawn 불가) | SSE/HTTP transport |

## 8. 관련 문서

- ADR-0043 — MCP integration 정책 (`docs/adr/0043-mcp-integration.md`)
- ADR-0042 — alias-aware link resolver (`read_page` / `search_by_alias` 의 alias 매칭 base)
- ADR-0034 — data-first layout (`WIKIHUB_HOME` env 의미)
- `_system/commands/wh-query.md` — Hermes LLM-mediated query skill (MCP server 와 layer 분리)
- `features/20260529_mcp_integration/` — feature workspace (plan + analysis_and_design)
