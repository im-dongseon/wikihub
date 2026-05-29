# ADR-0043: wikihub MCP integration — read-only server + stdio + SSH transport

- **Status**: Accepted
- **Date**: 2026-05-29
- **Feature**: `features/20260529_mcp_integration/` (issue #95)
- **Supersedes**: 없음
- **Superseded by**: 없음

## Context

외부 (회사 노트북 / 개인 IDE / Claude Desktop 등) MCP-호환 client 가 wikihub VM 의 wiki 데이터 (`wiki/entities`, `wiki/concepts`, `wiki/sources/<vault>`, `wiki/analyses`) 를 표준 protocol 로 탐색하고자 한다. 현재는 Hermes / claude-code 같은 CLI agent 가 VM 에 직접 SSH 후 `/wh-query` slash command 를 invoke 해야 데이터 접근 가능 — non-CLI client 는 활용 불가.

핵심 제약:
- **단일 source of truth** — `wiki/` markdown 정본 유지. MCP 는 read-only layer.
- **layer 분리** — LLM-mediated playbook (`/wh-query`) 와 deterministic primitive (MCP server) 책임 분담.
- **회사 망 환경 다양성** — Tailscale / mesh VPN 사용 불가 환경 흔함. outbound 22 또는 443 만 허용 케이스 빈번.
- **운영자 1 명 + client 1~2 대** — SaaS-scale 다중 client 시나리오 아님.

## Considered Options

### Role
- **(α) MCP server**: wikihub 가 외부 client 에 데이터 노출.
- **(β) MCP client**: wikihub 가 외부 MCP server 의 tool 통합. wikihub 의 deterministic bash + LLM 분리 패턴과 fit 제한.
- (γ) 양쪽 — α 안정화 후 검토.

### Transport (server role 가정)
- **(A) stdio + SSH spawn**: client 가 `ssh wikihub-oci '...mcp.py'` 으로 원격 stdio. daemon 0 — sshd 재사용.
- **(B) SSE/HTTP daemon + Bearer token**: systemd unit `wikihub-mcp.service` + reverse proxy (Caddy/nginx) + Let's Encrypt cert + token rotation. 운영 overhead 큼.
- **(C) Cloudflare Tunnel + SSE**: outbound-only tunnel — 회사 망 친화. CF 계정 + 도메인 + `cloudflared` daemon 의존.

### Scope
- **(X) read-only**: resources + 조회 tool 만. mutation 0. OAuth credential 접근 0.
- **(Y) read + safe-write**: lint trigger / pending_ingest 조회 등 일부 mutation.
- **(Z) full**: 4 skill 모두 tool 화 (ingest/lint/query/setup).

## Decision

**채택**: (α) MCP server + (A) stdio + SSH spawn + (X) read-only.

### 정본 결정 사항

1. **Role**: MCP server. wikihub VM 측 entry `scripts/wikihub_mcp.py`.
2. **Transport**: stdio. Client 가 `ssh <host> '<venv>/bin/python <src>/scripts/wikihub_mcp.py'` 으로 원격 spawn. daemon 0, systemd unit 0 (Phase 1).
3. **Auth**: SSH key. 별도 token layer 없음.
4. **Scope**: read-only.
   - **Resources (4 base + 1 dynamic)**: `wikihub://entities`, `wikihub://concepts`, `wikihub://sources/<vault_id>`, `wikihub://analyses`, `wikihub://page/<cat>/<name>`
   - **Tools (5)**: `list_entities(filter?)`, `list_concepts(filter?)`, `read_page(category, name)`, `grep_wiki(pattern, category?)`, `search_by_alias(name)`
5. **Layer 분리**: MCP server 는 deterministic primitive (file read · grep · frontmatter parse · alias index lookup) 만. semantic synthesis 는 client 측 LLM 책임. `wikihub_mcp.py` 안에서 LLM 호출 0 (recursive LLM 회피).
6. **ADR-0042 재사용**: alias-aware resolver (`Dict[lowercase_alias, canonical_filename]`) 알고리즘을 `wikihub_mcp.py` 안에서 동일 구현 — lazy build (호출 시점 1회 + per-process cache). lint cycle 의 in-memory index 와는 별 process 라 독립.
7. **Dependency**: Python `mcp` SDK (wikihub venv 에 추가, install.sh `_step3_venv` pip install 단계 통합). install.sh:472 의 `uv pip install --require-hashes -r scripts/requirements.txt` (hash-locked) 정합 — PR2 에서 `mcp` 의 정확한 버전 (예: `mcp==X.Y.Z`) pin + `uv pip compile --generate-hashes` 재실행으로 `scripts/requirements.txt` 갱신 필수. unhashed install 금지.
8. **read-only invariant (코드 audit)**:
   - `open(..., "w"/"a"/"x")` 금지
   - `pathlib.Path.write_text` / `write_bytes` / `rename` / `unlink` / `mkdir` 금지
   - subprocess 사용 시 read 명령만 (`grep`, `cat`) — 단 Phase 1 은 Python 직접 처리로 subprocess 회피 (audit surface 축소)

### Hermes skill 과의 관계

| 동일점 | 차이점 |
|---|---|
| 둘 다 `wiki/` 자원을 read-only 활용 | MCP = deterministic primitive (LLM 0) / Hermes `/wh-query` = LLM-mediated synthesis |
| ADR-0006 single-entry-point 정합 — 둘 다 wiki 데이터의 "조회" 책임 분담 | client 가 다름 — MCP = LLM 호환 외부 client / Hermes = CLI agent + 자체 LLM session |

write 책임은 Hermes 의 다른 skill (`/wh-lint`, `/wh-ingest`) 만 — MCP server 와 책임 충돌 없음.

### Phase 1 / Phase 2 분리

- **Phase 1 (본 ADR scope)**: stdio + SSH + read-only.
- **Phase 2 (deferred — §재검토 트리거)**:
  - SSE/HTTP daemon — 회사 망 outbound 22 막힌 환경 + corporate proxy 통과 불가 시
  - Cloudflare Tunnel — outbound-only reverse tunnel, 다중 client 시
  - write tool 추가 — 별도 ADR + 인증 강화 (Bearer token + audit log) 필수

## Consequences

- **긍정**:
  - 외부 MCP client (Claude Desktop / Cline / IDE plugin) 에서 wikihub query 가능 — wiki UX 큰 개선
  - 운영 overhead 0 (Phase 1) — sshd 재사용, daemon 없음, TLS cert 없음
  - 보안 sane — SSH key 가 인증, mutation 권한 0, OAuth credential 노출 0
  - layer 분리 — Hermes skill 과 책임 충돌 없음, recursive LLM 호출 차단

- **부정/제약**:
  - **회사 망 outbound 22 막힘 시 fallback 필요** — OCI sshd `Port 443` 추가 listen + Security List ingress rule 추가 필요 (PR3 `docs/mcp-setup.md` 자세 명시). 모든 outbound proxy 경유 환경은 SSH ProxyCommand (corkscrew/proxytunnel) 또는 Phase 2 (CF Tunnel)
  - **다중 client 시나리오 미지원** (Phase 1) — 운영자 1~2 명 + SSH key 관리 가능 범위
  - **IDE plugin 등 SSH 호출 불가 client 미지원** (Phase 1) — Phase 2 의 SSE/HTTP 필요
  - **알고리즘 정본 중복** — ADR-0042 의 alias index 알고리즘이 `_system/commands/lint.md` Step 1.5 (markdown playbook — Hermes LLM 이 실행) 와 `wikihub_mcp.py` (Python — 최초 실제 impl) 양쪽 정본. 향후 `scripts/lib/alias.py` 로 추출 시 lint.md 가 helper 호출로 전환될지 (deterministic Python 의존) 또는 markdown playbook 정본을 유지할지 (Hermes-agnostic 유지) 결정 필요
  - **per-spawn 비용** — 매 MCP session 마다 ssh + python interpreter spawn 비용 (~수백 ms). long-running daemon 대비 latency 높지만 운영 1~2 client 수준에서 무시 가능

- **후속 영향**:
  - **재검토 트리거**:
    - 회사 망 outbound 22 / 443 모두 막힌 환경 surface → Phase 2 (CF Tunnel) 도입
    - 다중 client (3+ 명) 시나리오 → Phase 2 (SSE/HTTP + Bearer token + Cloudflare Access)
    - IDE plugin 호환 요구 → Phase 2
    - write tool 필요 surface → 별도 ADR + 인증 강화 ADR 발의
    - alias index 코드 중복이 maintenance 부담 surface → `scripts/lib/alias.py` 공통화

## Cross-references

- ADR-0006 (unified orchestration) — MCP 가 추가 entry point. 단 read-only + Hermes skill 과 책임 분리 명시로 단일 source of truth 유지.
- ADR-0033 (skill prefix `wh-` lock) — MCP server 의 tool 명명 (`list_entities` 등) 은 skill 이 아니라 protocol-level 식별자. `wh-` prefix 무관.
- ADR-0041 (systemd prefix `wikihub-` 일관화) — Phase 2 의 SSE daemon 도입 시 `wikihub-mcp.service` 명명 정합.
- ADR-0042 (alias-aware resolver) — `read_page` / `search_by_alias` 에서 알고리즘 재사용.
- 표준: https://modelcontextprotocol.io (MCP spec), Python SDK https://github.com/modelcontextprotocol/python-sdk
