# Analysis & Design — wikihub MCP integration (Phase 1)

| 항목 | 값 |
|---|---|
| feat_id | `mcp_integration` |
| Date | 2026-05-29 |
| Issue | #95 |
| ADR | ADR-0043 (신규) |
| Step | 2 (Analysis & Design) |
| Scope | Phase 1 — read-only, stdio + SSH |

## 1. 문제 정의

외부 (회사 노트북 / 개인 IDE / Claude Desktop 등) MCP-호환 client 가 wikihub VM 의 wiki 데이터를 표준 protocol 로 read-only 탐색할 수 있어야 한다. 현재는 Hermes / claude-code 같은 CLI agent 가 wikihub VM 에 직접 SSH 후 `/wh-query` slash command 를 invoke 해야 데이터 접근 가능 — non-CLI client 는 활용 불가.

핵심 invariants:
1. **single source of truth** — wiki/ markdown 디렉토리가 정본. MCP server 는 그 위에 read-only layer.
2. **layer 분리** — LLM-mediated playbook (Hermes skill `/wh-query`) 와 deterministic primitive (MCP server) 는 책임 분담. semantic synthesis 는 client LLM 책임 (recursive LLM 호출 회피).
3. **mutation 0** — Phase 1 은 wiki/ + \_state/ 어디에도 write 없음. OAuth credential file (`~/.config/rclone/rclone.conf`) 접근 없음.

## 2. 결정 (ADR-0043 정본화)

### 2.1 Role · Transport · Auth

| 항목 | 결정 | 기각 옵션 |
|---|---|---|
| Role | **MCP server** | MCP client (외부 server 통합) — wikihub deterministic bash + LLM 분리 패턴 과 fit 제한 |
| Transport (Phase 1) | **stdio** | SSE/HTTP — daemon + TLS + token 운영 overhead |
| 외부 접근 | **client 가 `ssh wikihub-oci '...'` 으로 원격 spawn** | local stdio (외부 접근 불가) / VPN (회사 정책 다양) |
| Auth | **SSH key** | Bearer token (별도 관리 부담) |

### 2.2 Scope

**read-only**. Resources 4 + Tools 5. mutation 0. (정확한 signature → §4)

### 2.3 Hermes skill 과의 관계

- **MCP server** (`scripts/wikihub_mcp.py`) = deterministic primitive (file read · glob · grep · frontmatter parse · alias index lookup)
- **Hermes skill `/wh-query`** = LLM-mediated semantic synthesis (의미 검색 · cross-ref 추론 · analyses 자동 저장)
- 두 entry point 모두 wiki/ 자원을 **read-only 로 활용**. write 책임은 Hermes 의 다른 skill (`/wh-lint`, `/wh-ingest`) 만.
- MCP server 의 LLM-recursive 회피 — `wikihub_mcp.py` 안에서 LLM 호출 0. client 의 LLM 이 search 결과로 synthesis.

### 2.4 ADR-0042 alias index 재사용

ADR-0042 의 inverted index (`Dict[lowercase_alias, canonical_filename]`) 알고리즘을 `scripts/wikihub_mcp.py` 안에서 동일하게 구현 — `read_page(name)` 또는 `search_by_alias(name)` 호출 시 build (lazy, per-process cache). lint cycle 의 in-memory index 와 별개 (다른 process).

## 3. File structure

```
scripts/
  wikihub_mcp.py             # 신규 — MCP server entry point
  lib/
    (기존 — 재사용)
docs/
  mcp-setup.md               # 신규 — client 셋업 가이드 (PR3)
  adr/
    0043-mcp-integration.md  # 신규 (PR1)
features/20260529_mcp_integration/
  plan.md
  analysis_and_design.md
scripts/requirements.txt        # hash-locked (install.sh `--require-hashes`).
  # PR2 에서 `mcp==<X.Y.Z>` (정확한 버전 pin) 추가 + `uv pip compile --generate-hashes` 재실행으로 갱신.
```

## 4. MCP Interface 정본

### 4.1 Resources (4 base + 1 dynamic)

| URI 패턴 | 응답 | 비고 |
|---|---|---|
| `wikihub://entities` | entities 디렉토리 page 목록 (file stem + frontmatter aliases[] preview + 1줄 summary) | static list |
| `wikihub://concepts` | concepts 동일 | static list |
| `wikihub://sources/<vault_id>` | `wiki/sources/<vid>/` 의 source page 목록 + 마지막 sync timestamp | vault_id 는 `wikihub.yaml.vaults[*].id` |
| `wikihub://analyses` | analyses 목록 | static list |
| `wikihub://page/<category>/<name>` | 단일 page 의 frontmatter + body. ADR-0042 resolver 적용 (alias form 도 canonical 로 resolve). sources 케이스의 `<name>` 은 `<vault_id>/<path>` 형식 — multi-slash URI 그대로 (escape 없음). 예: `wikihub://page/sources/gdrive/meetings/2026-Q1.pptx` | dynamic |

### 4.2 Tools (5)

```python
list_entities(filter: str = "") -> list[dict]
    """entities 디렉토리 page enumeration. filter 가 비어있지 않으면 name/aliases 에 substring 포함 page 만.
    응답: [{name, aliases, summary}, ...]"""

list_concepts(filter: str = "") -> list[dict]
    """concepts 동일."""

read_page(category: Literal["entities", "concepts", "sources", "analyses"], name: str) -> dict
    """category + name 으로 page 내용 read.
    entities/concepts 의 경우 ADR-0042 resolver 적용 — alias form `mini-max` 입력해도 canonical `MiniMax` 페이지로 resolve.
    sources 는 vault-prefix 필수 — name = '<vault_id>/<path>' 형식.
    응답: {canonical_name, category, frontmatter: dict, body: str, resolved_via: 'exact'|'alias'}"""

grep_wiki(pattern: str, category: str = "") -> list[dict]
    """wiki/ 전체 또는 특정 category 의 markdown 파일에서 regex 검색.
    응답: [{path, line, snippet}, ...]. snippet 은 매치 라인 ±2 line context.
    Skip 대상: `wiki/.archived/`, `wiki/_lint/`. 검색 범위: 본문 + frontmatter (full text)."""

search_by_alias(name: str) -> list[dict]
    """ADR-0042 alias index lookup.
    응답: [{category, canonical_name, matched_alias}, ...]. 매칭 0건 빈 list."""
```

### 4.3 Read-only invariants

`wikihub_mcp.py` 코드 audit 기준:
- `open(..., "r")` 또는 `open(..., "rb")` 만 사용. `"w"` / `"a"` / `"x"` 모드 금지
- `pathlib.Path.write_text` / `write_bytes` / `rename` / `unlink` / `mkdir` 금지
- `subprocess.run` 호출 시 read 명령만 (`grep`, `cat`, `git log`) — 쓰는 명령 (`sed -i`, `tee`) 없음. 단 Phase 1 은 가능한 Python 직접 처리 (subprocess 회피 — code review surface 축소).

## 5. 운영 모델

### 5.1 spawn 흐름

```
Claude Desktop (client)
  ↓ subprocess spawn (per session)
ssh wikihub-oci 'python wikihub_mcp.py'
  ↓ stdio pipe (SSH 통해)
wikihub VM (server)
  ↓ MCP protocol over stdio
wikihub_mcp.py
  ↓ wiki/ filesystem read
응답
```

- per-session spawn — Claude Desktop 이 MCP server 세션 시작 시 ssh subprocess 1개 spawn. 세션 종료 시 close.
- 동시 다중 client 시 ssh subprocess N 개 — 각자 독립 `wikihub_mcp.py` process. wiki/ filesystem read 만이라 race 없음.
- daemon 없음 (Phase 1).

### 5.2 install.sh 통합

- Phase 1: wikihub venv 에 `mcp` Python SDK 추가만 (`_step3_venv` 의 pip install 단계). `wikihub_mcp.py` 는 git checkout 시 함께 deploy. systemd unit 0.
- Phase 2 (deferred): SSE daemon 필요 시 `wikihub-mcp.service` + EnvironmentFile (Bearer token) + reverse proxy 통합.

### 5.3 회사 망 접근 fallback (PR3 가이드 명시)

| 회사 망 상태 | 해결 |
|---|---|
| outbound 22 OK | 기본 설정 |
| outbound 22 막힘 + 443 OK | OCI sshd `Port 443` 추가 listen |
| 모든 outbound proxy 경유 | SSH ProxyCommand (corkscrew/proxytunnel) |
| OCI VM 도달 불가 | Phase 2 — Cloudflare Tunnel |

## 6. 영향·연계

| 정본 | 영향 |
|---|---|
| `_system/commands/wh-query.md` | 변경 없음. Hermes skill 그대로 유지 (LLM 추론 entry point) |
| `_system/wiki-schema.md` | 변경 없음. MCP 가 read-only consumer |
| `wiki/` markdown 본문 | 변경 없음 |
| `pyproject.toml` 또는 `requirements.txt` | `mcp` SDK dependency 추가 (PR2) |
| ADR-0042 (alias resolver) | 알고리즘 재사용. 정본 중복 — lint.md Step 1.5 (markdown playbook, Hermes LLM 실행) ↔ `wikihub_mcp.py` (Python 최초 impl). 향후 `scripts/lib/alias.py` 추출 시 lint.md 가 helper 호출로 전환 (deterministic 의존) 또는 markdown playbook 정본 유지 (Hermes-agnostic) 결정 필요 — O1 |

## 7. 미결 사항

| ID | 항목 | 처리 |
|---|---|---|
| O1 | alias index 정본 중복 (lint.md markdown playbook ↔ wikihub_mcp.py Python impl) → 공통 helper 분리 시 정본 결정 | Phase 1 후 별도 issue. 결정: scripts/lib/alias.py 추출 + lint.md 가 helper 호출 (deterministic 의존) vs playbook 정본 유지 |
| O2 | MCP error 응답 schema — read_page name 부재 시 ToolError vs 빈 dict | Phase 1 impl 시 결정 (정공법: MCP SDK 의 `RuntimeError` raise → SDK 가 protocol error 변환) |
| O3 | grep_wiki 의 binary 파일 skip 정책 | impl 시 결정 (`.md` 만 grep) |
| O4 | vault_id 미존재 시 응답 — `wikihub://sources/<vault_id>` 또는 `read_page(category="sources", name="<vault_id>/<path>")` 에서 vault_id 가 `wikihub.yaml.vaults[*].id` 와 일치 안 함 | impl 시 결정 (정공법: ToolError raise, "vault_id `<vid>` 미존재, 가용 vault: [...]" 메시지) |
| O5 | frontmatter parser 선택 — `pyyaml.safe_load` (read-only, dependency 최소) vs `ruamel-yaml` (현재 `scripts/lib/yaml_writer.py` 가 사용) | impl: pyyaml — read-only 이고 round-trip 보존 불필요 |

## 8. DoD

- [ ] PR1: ADR-0043 Accepted + 본 design 문서 + plan.md commit. Self-review MED 0
- [ ] PR2: `scripts/wikihub_mcp.py` impl + dependency. local stdio 테스트 (5 tool · 4 resource 응답) + read-only audit
- [ ] PR3: `docs/mcp-setup.md` (Claude Desktop config + SSH config + 회사 망 fallback)
- [ ] release 시 HISTORY.md append (Step 5)

## 9. 참조

- 이슈: #95
- ADR: ADR-0042 (resolver), ADR-0006 (unified orchestration), ADR-0033 (skill prefix), ADR-0043 (신규)
- 표준: https://modelcontextprotocol.io, https://github.com/modelcontextprotocol/python-sdk
