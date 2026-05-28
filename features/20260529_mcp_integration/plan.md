# Plan — wikihub MCP integration (Phase 1: stdio + SSH)

- **feat_id**: `mcp_integration`
- **Date**: 2026-05-29
- **Issue**: #95
- **Status**: Step 2 진입 — analysis_and_design.md 작성

## 의도

외부 (회사 노트북 / 개인 IDE / Claude Desktop 등) 에서 **MCP-호환 client** 가 wikihub 의 wiki 데이터 (entities · concepts · sources · analyses) 를 **read-only query** 로 탐색할 수 있도록 wikihub VM 측에 MCP server (`scripts/wikihub_mcp.py`) 를 신설한다.

## Scope

### Phase 1 (본 feature)
- Role: **MCP server**
- Transport: **stdio** + **client 가 SSH 로 원격 spawn** (`ssh wikihub-oci '...wikihub_mcp.py'`)
- Capability: **read-only**
  - 4 resources — `wikihub://entities|concepts|sources/<vid>|analyses` + `wikihub://page/<cat>/<name>`
  - 5 tools — `list_entities`, `list_concepts`, `read_page`, `grep_wiki`, `search_by_alias`
- Auth: SSH key (별도 token layer 없음)
- Dependency: Python `mcp` SDK (wikihub venv)
- LLM-mediated semantic synthesis 는 **client 측 LLM 책임** (MCP server 는 deterministic primitive 만)
- ADR-0042 alias index 재사용

### Phase 2 (deferred — 본 feature 외)
- SSE/HTTP transport — Cloudflare Tunnel 또는 직접 nginx/Caddy + Bearer token + Let's Encrypt
- 회사 망 outbound 22 막힌 환경에서 필요
- 다중 client / IDE plugin 지원 시
- ADR-0043 §재검토 트리거에 명시

## 작업 흐름 (단계적 3 PR)

| PR | scope | 파일 |
|---|---|---|
| **PR1 (design)** | ADR-0043 + feature workspace | `docs/adr/0043-mcp-integration.md`, `features/20260529_mcp_integration/plan.md`, `features/20260529_mcp_integration/analysis_and_design.md`, `docs/adr/README.md` |
| **PR2 (impl)** | MCP server 구현 + dependency | `scripts/wikihub_mcp.py`, `pyproject.toml`/`requirements.txt`, install.sh _step3_venv 통합 검토 |
| **PR3 (docs)** | client 셋업 가이드 | `docs/mcp-setup.md` |

각 PR 의 self-review MED 0 까지 + agent label + v0.1.10 milestone.

## 결정된 정책 사항 (ADR-0043 정본화)

1. **stdio + SSH** (Phase 1) — daemon 없음, sshd 재사용, SSH key 인증
2. **read-only** — wiki/ + \_state/ 어디에도 write 없음. OAuth credential 노출 0
3. **LLM-mediated playbook (Hermes skill) 와 layer 분리** — MCP server 는 deterministic primitive (file read / grep / alias lookup). Hermes skill `/wh-query` 가 LLM mediation 책임. 두 entry point 가 같은 wiki 자원을 read 함 (단일 source of truth 유지)
4. **ADR-0042 alias index 재사용** — `read_page` / `search_by_alias` 가 inverted index 활용. lint cycle 의 in-memory index 와 별개로 MCP server 측 lazy build (호출 시점 1회 + cache)
5. **scope 확장 정책** — write tool 추가는 **별도 ADR + 인증 강화 필요**. Phase 1 read-only 가 향후 mutation 도입의 기준선

## DoD (issue #95 정합)

- [ ] ADR-0043 Accepted + analysis_and_design.md (Phase 1 scope lock)
- [ ] `scripts/wikihub_mcp.py` — local stdio 호출로 5 tool + 4 resource 응답 정합
- [ ] `docs/mcp-setup.md` — Claude Desktop config + `~/.ssh/config` + 회사 망 fallback (Port 443, ProxyCommand, CF Tunnel) 명시
- [ ] read-only audit — wiki/ 또는 \_state/ write 0건
- [ ] Phase 2 deferred 항목이 ADR-0043 §재검토 트리거에 명시
- [ ] PR1 → PR2 → PR3 순서로 머지

## 참조

- 이슈: #95
- ADR: ADR-0006 (unified orchestration), ADR-0033 (skill prefix), ADR-0042 (alias-aware resolver), ADR-0043 (본 feature 신규)
- 표준: MCP spec (modelcontextprotocol.io), Python SDK `mcp`
