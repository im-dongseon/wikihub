#!/usr/bin/env python3
"""WikiHub systemd unit template renderer.

정본 contract: features/20260517_update_mode/analysis_and_design.md §6.1 (ADR-0030).

install.sh + update_mode 가 본 helper 를 호출해서 _system/systemd/*.template →
~/.config/systemd/user/wikihub-*|wh-*.service|.timer 로 render.

modes (mutually exclusive):
    --render --out DIR         : template → DIR 에 render (idempotent atomic write)
    --list-enabled             : enabled vault id 목록 (1줄 1개) stdout
    --get-mount-path VAULT_ID  : 해당 vault 의 options.mount_path stdout
    --validate                 : yaml schema validate only

options:
    --yaml PATH                : yaml 경로. default `$WIKIHUB_HOME/wikihub.yaml`
                                 (env 미설정 시 ~/wikihub/wikihub.yaml — ADR-0034)

exit codes:
    0 — success
    1 — semantic failure (vault not found, validation fail)
    2 — operational failure (yaml malformed, template missing, write deny, disk full)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML 미설치. venv 활성화 후 재시도.", file=sys.stderr)
    sys.exit(2)


# ── exit codes ─────────────────────────────────────────────────────────
EXIT_OK = 0
EXIT_SEMANTIC = 1
EXIT_OPERATIONAL = 2


# ── duplicate-key 검출 SafeLoader (CR2-LOW-4, issue #32) ──────────────
# PyYAML `safe_load` 는 duplicate key (top-level 및 nested mapping 모두) 를
# silent 로 마지막 값 채택. operator yaml 의 `vaults:` 블록을 paste-실수로
# 두 번 두거나 `options:` 안에 같은 key 를 두 번 쓰면 첫 번째 값이 silent
# drop 되어 운영 결과가 의도와 어긋남. 본 loader 가 duplicate key 를
# ConstructorError 로 raise → `yaml.YAMLError` 분기 (EXIT_OPERATIONAL).
# 검출 범위는 top-level 뿐 아니라 모든 nested mapping — fail-fast 안전 방향.
class _DuplicateKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping_no_duplicates(loader, node, deep=False):
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_DuplicateKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_no_duplicates,
)


# ── per-vault vs singleton template 분류 ──────────────────────────────
# per-vault: `@.` 패턴 (e.g. wikihub-mount@.service.template) — vault 마다 render.
# singleton: 그 외 — 1회 render.
_PER_VAULT_PATTERN = re.compile(r"@\.[^/]+\.template$")
_VAULT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")   # ADR-0019 정합


# ── path 산출 ──────────────────────────────────────────────────────────
def _wikihub_home() -> Path:
    """운영 자산 dir (ADR-0034 v0.1.0 layout — data-first). 이전 WIKIHUB_INSTANCE_ROOT 의미."""
    return Path(os.environ.get("WIKIHUB_HOME", str(Path.home() / "wikihub"))).resolve()


def _wikihub_src() -> Path:
    """시스템 코드 dir (ADR-0034 — XDG, ADR-0020 venv 와 동일 root). 이전 WIKIHUB_HOME 의미."""
    return Path(os.environ.get(
        "WIKIHUB_SRC",
        str(Path.home() / ".local" / "share" / "wikihub" / "src"),
    )).resolve()


def _systemd_templates_dir() -> Path:
    return _wikihub_src() / "_system" / "systemd"


# ── yaml 로딩·검증 ─────────────────────────────────────────────────────
def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        print(f"ERROR: yaml 부재: {path}", file=sys.stderr)
        sys.exit(EXIT_OPERATIONAL)
    try:
        with path.open("r", encoding="utf-8") as f:
            # CR2-LOW-4 (issue #32): duplicate-key 검출 loader.
            data = yaml.load(f, Loader=_DuplicateKeySafeLoader)
    except yaml.YAMLError as e:
        print(f"ERROR: yaml malformed ({path}): {e}", file=sys.stderr)
        sys.exit(EXIT_OPERATIONAL)
    if not isinstance(data, dict):
        print(f"ERROR: yaml top-level 이 dict 아님: {path}", file=sys.stderr)
        sys.exit(EXIT_OPERATIONAL)
    return data


def _validate_schema(cfg: dict) -> list[str]:
    """minimal schema check — 본 helper 가 substitution 에 필요한 필드만 검증."""
    errors: list[str] = []
    if "instance" not in cfg or not isinstance(cfg["instance"], dict):
        errors.append("instance: dict 필요")
    elif "root" not in cfg["instance"]:
        errors.append("instance.root 누락")

    if "vaults" not in cfg or not isinstance(cfg["vaults"], list):
        errors.append("vaults: list 필요")
    else:
        seen_ids: set[str] = set()
        seen_ports: dict[int, str] = {}
        for i, v in enumerate(cfg["vaults"]):
            if not isinstance(v, dict):
                errors.append(f"vaults[{i}]: dict 필요")
                continue
            vid = v.get("id", "")
            if not _VAULT_ID_RE.match(vid):
                errors.append(f"vaults[{i}].id 형식 위반: {vid!r} (정규식 {_VAULT_ID_RE.pattern})")
            if vid in seen_ids:
                errors.append(f"vaults[{i}].id 중복: {vid}")
            seen_ids.add(vid)
            # NAS vault 는 rclone rc 미사용 — port 검증 skip (Issue #117)
            if str(v.get("type", "")).strip() == "nas":
                continue
            opts = v.get("options") or {}
            port = opts.get("rclone_rc_port")
            if port is not None:
                if port in seen_ports:
                    errors.append(f"vaults[{i}].options.rclone_rc_port={port} 중복 (직전: {seen_ports[port]})")
                else:
                    seen_ports[port] = vid

    if "operations" in cfg and not isinstance(cfg["operations"], dict):
        errors.append("operations: dict 필요")
    if "agent" in cfg and not isinstance(cfg["agent"], dict):
        errors.append("agent: dict 필요")
    return errors


# ── substitution 값 산출 ───────────────────────────────────────────────
def _read_venv_path() -> str:
    """`.venv_path` sidecar — install.sh 가 시스템 코드 dir 에 기록 (ADR-0034)."""
    sidecar = _wikihub_src() / ".venv_path"
    if sidecar.is_file():
        return sidecar.read_text(encoding="utf-8").strip()
    return str(Path.home() / ".local" / "share" / "wikihub" / "venv")


def _instance_root(cfg: dict) -> Path:
    """yaml.instance.root — 운영 자산 dir (ADR-0031). default = _wikihub_home() (ADR-0034)."""
    raw = cfg.get("instance", {}).get("root", str(_wikihub_home()))
    return Path(os.path.expanduser(raw)).resolve()


# ── F5 (ADR-0032·0033): wikihub skill 5건 — per-skill substitution ────
_WIKIHUB_SKILLS = ("wh-ingest", "wh-lint", "wh-query", "wh-setup", "wq")
# v0.1.8 update_path_fixes (B): wh-graphify hermes skill 폐기 — wikihub-graphify.service systemd 격상.
# graphify 호출 정본 = scripts/wikihub_graphify.sh (ADR-0036 §D6 single-source).


def _per_skill_invocation(cfg: dict, skill_name: str) -> str:
    """ADR-0032 §sub-2 / ADR-0033: per-unit `{skill}` placeholder substitution.

    `oneshot_args` 에 `{skill}` placeholder 가 반드시 있어야 함 (fail-fast).
    F5 schema (+ 2026-05-19 §Note ADR-0032): `oneshot_args: ["chat", "--skills", "{skill}", "--quiet", "--yolo", "--query"]`.
    F5 이전 (e.g. update_mode rollback) 의 `oneshot_args: ["-z"]` 는 placeholder 부재 → fail.
    """
    agent = cfg.get("agent") or {}
    binary = agent.get("binary", "")
    oneshot_args = list(agent.get("oneshot_args") or [])
    has_placeholder = any("{skill}" in str(a) for a in oneshot_args)
    if not has_placeholder:
        print(
            f"ERROR: agent.oneshot_args 에 '{{skill}}' placeholder 누락 — "
            f"F5 schema (ADR-0032) 요구. 현재 oneshot_args={oneshot_args!r}. "
            f"yaml 의 oneshot_args 를 `[\"chat\", \"--skills\", \"{{skill}}\", \"--quiet\", \"--yolo\", \"--query\"]` 로 갱신 필요 "
            f"(또는 F5 이전 ref 로 rollback 시 `[\"-z\"]` 로 다운그레이드).",
            file=sys.stderr,
        )
        sys.exit(EXIT_OPERATIONAL)

    # ADR-0032 §Note (v0.1.5, 2026-05-20) — per-skill model override.
    # yaml.agent.models[<skill>] 명시 시 oneshot_args 에 `--model <id>` inject (--query 앞에).
    # 빈 dict / 미명시 skill → hermes config.yaml.model.default 사용 (backward-compat).
    models = agent.get("models") or {}
    skill_model = models.get(skill_name)
    if skill_model:
        new_args: list = []
        inserted = False
        for arg in oneshot_args:
            if str(arg) == "--query" and not inserted:
                new_args.extend(["--model", str(skill_model)])
                inserted = True
            new_args.append(arg)
        if not inserted:
            new_args.extend(["--model", str(skill_model)])
        oneshot_args = new_args

    resolved = [str(a).format(skill=skill_name) for a in oneshot_args]
    return " ".join([binary] + resolved).strip()


def _instance_wide_subs(cfg: dict) -> dict[str, str]:
    """Pass 2 — instance-wide substitution keys."""
    instance_root = _instance_root(cfg)
    venv_path = _read_venv_path()
    wikihub_home = _wikihub_home()
    wikihub_src = _wikihub_src()

    ops = cfg.get("operations") or {}
    agent = cfg.get("agent") or {}

    agent_binary = agent.get("binary", "")
    oneshot_args = agent.get("oneshot_args") or []
    # F4 호환 legacy invocation (agent_invocation 단일 key) — placeholder 미해석. F5 후
    # systemd unit template 은 per-skill key (agent_invocation_for_wh_*) 사용.
    agent_invocation_parts = [agent_binary] + [str(a) for a in oneshot_args]
    agent_invocation = " ".join(agent_invocation_parts).strip()

    rclone_config_path = str(Path.home() / ".config" / "rclone" / "rclone.conf")
    rclone_bin = os.environ.get("RCLONE_BIN", "/usr/local/bin/rclone")

    subs: dict[str, str] = {
        # ADR-0034 (v0.1.0 layout — data-first):
        # - wikihub_home = 운영 자산 dir (이전 WIKIHUB_INSTANCE_ROOT 의미)
        # - wikihub_src  = 시스템 코드 dir (XDG)
        # - instance_root = deprecated alias of wikihub_home (transition 호환)
        "wikihub_home": str(wikihub_home),
        "wikihub_src": str(wikihub_src),
        "instance_root": str(instance_root),   # deprecated alias (5.4.4 transition 안전망)
        "venv_path": venv_path,
        "rclone_config_path": rclone_config_path,
        "rclone_bin": rclone_bin,
        "vfs_cache_max_size": str(ops.get("vfs_cache_max_size", "10G")),
        "lint_interval_hours": str(ops.get("lint_interval_hours", 3)),   # v0.1.6 default (was 24 — v0.1.0 era stale)
        "agent_invocation": agent_invocation,
        "skill_prefix": agent.get("skill_prefix", "wh-"),
        # F5 — yaml.agent.timeout_sec ↔ systemd TimeoutStartSec sync (R3-CR3-2 B-HIGH-2)
        # Issue #104: lint/ingest 각각 yaml override 지원. 우선순위:
        # operations.lint_timeout_start_sec → agent.timeout_sec → 600
        # operations.ingest_timeout_start_sec → agent.timeout_sec → 600
        "lint_timeout_start_sec": str(ops.get("lint_timeout_start_sec") or agent.get("timeout_sec", 600)),
        "ingest_timeout_start_sec": str(ops.get("ingest_timeout_start_sec") or agent.get("timeout_sec", 600)),
    }

    # F5 — per-skill agent_invocation_for_<skill> keys (ADR-0032·0033)
    for skill in _WIKIHUB_SKILLS:
        key = f"agent_invocation_for_{skill.replace('-', '_')}"
        subs[key] = _per_skill_invocation(cfg, skill)

    return subs


def _cross_vault_subs(vault: dict) -> dict[str, str]:
    """Cross-vault keys (`_for_<vid>` suffix) — `%i` 변환 후 lookup 되는 dynamic keys.

    template 에 `{remote_name_for_%i}` · `{rc_port_for_%i}` 형태로 나타남. `%i` 가 vault_id
    로 치환된 후 dict lookup → render 시점에 모든 enabled vault 의 값을 집합으로 보유.
    """
    vid = vault["id"]
    opts = vault.get("options") or {}
    vault_type = str(vault.get("type", "gdrive_api")).strip()
    
    # vault_type에 따라 분기
    if vault_type == "nas":
        # NAS vault: rc 미사용, Tailscale 경유, read-only mount
        return {
            f"remote_name_for_{vid}": str(opts.get("rclone_remote_name", vid)),
            f"remote_path_for_{vid}": str(opts.get("rclone_remote_path") or ""),
            f"rc_port_for_{vid}": str(opts.get("rclone_rc_port", 5572)),  # NAS는 미사용하지만 템플릿 호환
        }
    else:
        # Drive vault: 기존 동작
        return {
            f"remote_name_for_{vid}": str(opts.get("rclone_remote_name", vid)),
            f"remote_path_for_{vid}": str(opts.get("rclone_remote_path") or ""),
            f"rc_port_for_{vid}": str(opts.get("rclone_rc_port", 5572)),
        }


def _current_vault_subs(vault: dict, vfs_cache_max_size: str) -> dict[str, str]:
    """Current-vault scalar keys (suffix 없음) — 본 vault 의 render 결과에만 적용.

    ADR-0035: `credentials_path` 폐기 (rclone.conf 단일 인증). `sync_interval_sec` 만 유지.
    vault_type에 따라 mount 옵션 분기.

    vfs_cache_max_size: instance-wide 설정값. mount_options 내에 미리 치환하여
    반환 (format_map 1-pass에서 `{mount_options}` 내부 placeholder가
    미치환되는 문제 해결 — issue #141).
    """
    vault_type = str(vault.get("type", "gdrive_api")).strip()
    opts = vault.get("options") or {}
    
    if vault_type == "nas":
        # NAS vault: Tailscale 경유, read-only, rc 미사용
        sftp_host = str(opts.get("sftp_host", ""))
        sftp_port = str(opts.get("sftp_port", 22))
        
        # TCP 체크 ExecStartPre (Tailscale 연결 대기)
        tcp_check_pre = (
            f"ExecStartPre=/bin/bash -c 'for i in $(seq 1 30); do "
            f"echo >/dev/tcp/{sftp_host}/{sftp_port} 2>/dev/null && break; "
            f"sleep 2; done'"
        )
        
        # mount 옵션: --vfs-cache-mode full, --dir-cache-time, --log-level
        # vfs_cache_max_size 는 호출부에서 전달받아 직접 치환 (issue #141)
        # --read-only 제거 — NAS vault 는 ingest/sync 과정에서 write 필요 (issue #142)
        mount_options = (
            "--vfs-cache-mode full \\\n"
            f"  --vfs-cache-max-size {vfs_cache_max_size} \\\n"
            "  --dir-cache-time 5m \\\n"
            "  --log-level NOTICE"
        )
        
        return {
            "sync_interval_sec": str(vault.get("sync_interval_sec", 3600)),
            "after_target": "network-online.target tailscaled.service",
            "tcp_check_pre": tcp_check_pre,
            "mount_options": mount_options,
            "restart_policy": "on-failure",
            "template_comments": (
                "NAS vault mount template\\n"
                "- After: network-online.target + tailscaled.service\\n"
                "- ExecStartPre: TCP 체크 (SFTP 포트 도달성)\\n"
                "- mount_options: vfs-cache-mode full\\n"
                "- Restart: on-failure (Tailscale 지연 시 자가 복구)"
            ),
        }
    else:
        # Drive vault: 기존 동작
        # vfs_cache_max_size 는 호출부에서 전달받아 직접 치환 (issue #141)
        mount_options = (
            "--vfs-cache-mode minimal \\\n"
            f"  --vfs-cache-max-size {vfs_cache_max_size} \\\n"
            "  --drive-export-formats docx,xlsx,pptx,md \\\n"
            "  --dir-cache-time 5m \\\n"
            "  --log-level NOTICE \\\n"
            "  --rc \\\n"
            "  --rc-addr 127.0.0.1:{rc_port_for_%i}"
        )
        
        return {
            "sync_interval_sec": str(vault.get("sync_interval_sec", 3600)),
            "after_target": "network-online.target",
            "tcp_check_pre": "",
            "mount_options": mount_options,
            "restart_policy": "always",
            "template_comments": (
                "Drive vault mount template\\n"
                "- After: network-online.target\\n"
                "- mount_options: vfs-cache-mode minimal, rc 활성화\\n"
                "- Restart: always"
            ),
        }


# ── safe substitution ──────────────────────────────────────────────────
class _SafeDict(dict):
    """Missing key → KeyError 명시. str.format_map 사용."""
    def __missing__(self, key: str) -> str:
        raise KeyError(key)


def _render_template(
    template_text: str,
    subs: dict[str, str],
    vault_id: str | None,
) -> str:
    """2-pass: %i 치환 후 {placeholder} 치환.

    %i → vault_id (per-vault template) 또는 미치환 (singleton).
    그 후 `str.format_map(_SafeDict(subs))` 로 {key} 치환.
    """
    text = template_text
    if vault_id is not None:
        # systemd 의 %i 와 우리의 {key_for_%i} 패턴 동시 치환.
        # {key_for_%i} → {key_for_<vid>} 로 먼저 (subs key 가 _for_<vid> 로 색인됨).
        text = text.replace("%i", vault_id)
    # str.format_map 의 {} escape: literal `{` 가 template 에 있으면 `{{` 처리 필요 — wikihub
    # template 은 systemd 가 `{` 안 사용. 안전 가정.
    try:
        return text.format_map(_SafeDict(subs))
    except KeyError as e:
        raise KeyError(f"substitution key 누락: {{{e.args[0]}}}")


# ── render 책임 ────────────────────────────────────────────────────────
def _atomic_write_if_changed(out: Path, new_content: str) -> bool:
    """동일 byte 면 mtime 보존 + skip. 다르면 .tmp + rename atomic.

    Returns: True if write occurred, False if skipped (byte-equal).
    """
    if out.is_file():
        try:
            if out.read_text(encoding="utf-8") == new_content:
                return False
        except OSError:
            pass
    tmp = out.with_suffix(out.suffix + ".tmp")
    try:
        tmp.write_text(new_content, encoding="utf-8")
        os.replace(str(tmp), str(out))
    except OSError as e:
        print(f"ERROR: write fail {out}: {e}", file=sys.stderr)
        try:
            tmp.unlink()
        except OSError:
            pass
        sys.exit(EXIT_OPERATIONAL)
    return True


def _enabled_vaults(cfg: dict) -> list[dict]:
    return [v for v in (cfg.get("vaults") or []) if v.get("enabled", False)]


def _output_filename(template_path: Path, vault_id: str | None) -> str:
    """template stem + vault_id → systemd unit filename.

    examples:
      wikihub-mount@.service.template + vault_id=gdrive → wikihub-mount@gdrive.service
      wikihub-lint.timer.template (singleton)           → wikihub-lint.timer
      ops-alert.service (file, no template suffix)      → ops-alert.service
    """
    name = template_path.name
    if name.endswith(".template"):
        name = name[:-len(".template")]
    if vault_id is not None:
        # per-vault: `@.service` → `@<vid>.service`
        name = name.replace("@.", f"@{vault_id}.", 1)
    return name


def _do_render(cfg: dict, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)

    # startup cleanup: 이전 run crash 로 인한 잔존 .tmp 파일 제거
    for stale_tmp in out_dir.glob("*.tmp"):
        try:
            stale_tmp.unlink()
        except OSError:
            pass

    tpl_dir = _systemd_templates_dir()
    if not tpl_dir.is_dir():
        print(f"ERROR: template dir 부재: {tpl_dir}", file=sys.stderr)
        return EXIT_OPERATIONAL

    instance_subs = _instance_wide_subs(cfg)
    enabled = _enabled_vaults(cfg)
    enabled_ids = {v["id"] for v in enabled}

    # template glob — *.template + non-template singleton (ops-alert.service)
    templates: list[Path] = sorted(tpl_dir.glob("*.template"))
    singletons_without_suffix: list[Path] = [
        p for p in tpl_dir.iterdir()
        if p.is_file() and p.suffix in (".service", ".timer") and not p.name.endswith(".template")
    ]

    written_count = 0
    skipped_count = 0
    intended_outputs: set[str] = set()

    # cross-vault subs (`_for_<vid>` suffix) — 모든 enabled vault 합집합
    all_cross_vault_subs: dict[str, str] = {}
    for v in enabled:
        all_cross_vault_subs.update(_cross_vault_subs(v))

    # duplicate key check (cross-vault vs instance-wide)
    overlap = set(instance_subs) & set(all_cross_vault_subs)
    if overlap:
        print(f"ERROR: substitution key 충돌 (instance vs cross-vault): {sorted(overlap)}", file=sys.stderr)
        return EXIT_OPERATIONAL

    base_subs = {**instance_subs, **all_cross_vault_subs}

    for tpl in templates + singletons_without_suffix:
        per_vault = bool(_PER_VAULT_PATTERN.search(tpl.name))
        try:
            body = tpl.read_text(encoding="utf-8")
        except OSError as e:
            print(f"ERROR: template read fail {tpl}: {e}", file=sys.stderr)
            return EXIT_OPERATIONAL
        if per_vault:
            for v in enabled:
                # per-vault render: base + current vault scalar keys (sync_interval_sec 등)
                current_subs = _current_vault_subs(v, base_subs.get("vfs_cache_max_size", "10G"))
                # current_subs 의 key 가 base_subs 와 충돌하면 안 됨
                conflict = set(current_subs) & set(base_subs)
                if conflict:
                    print(f"ERROR: current-vault key 충돌: {sorted(conflict)}", file=sys.stderr)
                    return EXIT_OPERATIONAL
                full_subs = {**base_subs, **current_subs}
                try:
                    rendered = _render_template(body, full_subs, v["id"])
                except KeyError as e:
                    print(f"ERROR: render fail ({tpl.name} for vault {v['id']}): {e}", file=sys.stderr)
                    return EXIT_OPERATIONAL
                out_name = _output_filename(tpl, v["id"])
                out_path = out_dir / out_name
                if _atomic_write_if_changed(out_path, rendered):
                    written_count += 1
                else:
                    skipped_count += 1
                intended_outputs.add(out_name)
        else:
            try:
                rendered = _render_template(body, base_subs, None)
            except KeyError as e:
                print(f"ERROR: render fail ({tpl.name}): {e}", file=sys.stderr)
                return EXIT_OPERATIONAL
            out_name = _output_filename(tpl, None)
            out_path = out_dir / out_name
            if _atomic_write_if_changed(out_path, rendered):
                written_count += 1
            else:
                skipped_count += 1
            intended_outputs.add(out_name)

    # enabled=false 또는 제거된 vault 의 stale unit 정리 (per-vault).
    # operational: wikihub-mount@<vid>, wikihub-ingest@<vid>.
    removed = 0
    for p in sorted(out_dir.glob("wikihub-*@*")):
        m = re.match(r"^wikihub-(?:mount|ingest)@([^.]+)\.(service|timer)$", p.name)
        if not m:
            continue
        vid = m.group(1)
        if vid not in enabled_ids:
            try:
                p.unlink()
                removed += 1
            except OSError as e:
                print(f"WARN: stale unit 삭제 실패 {p}: {e}", file=sys.stderr)
    # upgrade cleanup — fully deprecated template names (unit 자체가 더 이상 render 안 됨).
    # operational vid 인지 무관하게 unconditional delete.
    #   - wikihub-vault@<vid>.{service,timer}  ← pre-2ed01f8 (v0.1.9 rename 이전)
    #   - wh-ingest@<vid>.{service,timer}      ← 2ed01f8 ~ ADR-0041 canary era
    for p in sorted(out_dir.glob("wikihub-vault@*")) + sorted(out_dir.glob("wh-ingest@*")):
        if not re.match(r".+@.+\.(service|timer)$", p.name):
            continue
        try:
            p.unlink()
            removed += 1
        except OSError as e:
            print(f"WARN: deprecated unit 삭제 실패 {p}: {e}", file=sys.stderr)
    # upgrade cleanup — singleton legacy names.
    #   - wh-lint.{service,timer}              ← 2ed01f8 ~ ADR-0041 canary era
    #   - wikihub-monitor.{service,timer}      ← ADR-0040 폐기 (monitor_services_remove)
    #   - wikihub-pending-monitor.{service,timer}  ← ADR-0040 폐기
    legacy_singletons = (
        "wh-lint.service",
        "wh-lint.timer",
        "wikihub-monitor.service",
        "wikihub-monitor.timer",
        "wikihub-pending-monitor.service",
        "wikihub-pending-monitor.timer",
    )
    for old_name in legacy_singletons:
        old_p = out_dir / old_name
        if old_p.is_file():
            try:
                old_p.unlink()
                removed += 1
            except OSError as e:
                print(f"WARN: legacy unit 삭제 실패 {old_p}: {e}", file=sys.stderr)

    print(
        f"render ok: written={written_count} skipped={skipped_count} "
        f"removed_stale={removed} enabled_vaults={sorted(enabled_ids)}",
        file=sys.stderr,
    )

    # F5 — systemd-analyze verify (CR2-HIGH-6 / R3-CR3-2 B-MED-4)
    _systemd_analyze_verify(out_dir)
    return EXIT_OK


def _systemd_analyze_verify(out_dir: Path) -> None:
    """ADR-0032 §sub-4 / R3-CR3-2 B-MED-4: render 후 unit 문법 검증.

    fail 시 EXIT_OPERATIONAL — install.sh trap (ADR-0030) 가 _rollback_if_failed 발동.
    """
    import shutil
    import subprocess

    sa = shutil.which("systemd-analyze")
    if sa is None:
        print(
            "WARN: systemd-analyze 미설치 — unit 문법 검증 skip "
            "(non-Linux 또는 minimal container 환경 추정)",
            file=sys.stderr,
        )
        return

    services = sorted(out_dir.glob("wikihub-*.service")) + sorted(out_dir.glob("wikihub-*.timer")) \
        + sorted(out_dir.glob("wh-*.service")) + sorted(out_dir.glob("wh-*.timer"))
    if not services:
        return
    try:
        result = subprocess.run(
            [sa, "--user", "verify", *[str(p) for p in services]],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"WARN: systemd-analyze verify 실행 실패: {e}", file=sys.stderr)
        return
    if result.returncode != 0:
        print(
            f"ERROR: systemd-analyze verify 실패 — rendered unit 문법 결함. "
            f"render_systemd_units.py 로직 또는 yaml schema 의심.\n"
            f"stderr:\n{result.stderr}",
            file=sys.stderr,
        )
        sys.exit(EXIT_OPERATIONAL)
    if result.stderr.strip():
        # warning level (returncode==0 with stderr) — surface only.
        print(f"INFO: systemd-analyze verify stderr (warn only):\n{result.stderr}", file=sys.stderr)


# ── mode dispatchers ──────────────────────────────────────────────────
def _do_list_enabled(cfg: dict) -> int:
    for v in _enabled_vaults(cfg):
        print(v["id"])
    return EXIT_OK


def _do_get_mount_path(cfg: dict, vault_id: str) -> int:
    for v in (cfg.get("vaults") or []):
        if v.get("id") == vault_id:
            mp = (v.get("options") or {}).get("mount_path", "")
            if not mp:
                # CR1-LOW-4 (issue #32): fallback to vault top-level local_path (ADR-0019 alias).
                mp = v.get("local_path", "")
            if not mp:
                # CR1-LOW-4 — 진단 hint: 두 필드 모두 부재 명시.
                print(
                    f"ERROR: vault {vault_id} 의 options.mount_path / local_path 둘 다 미정의",
                    file=sys.stderr,
                )
                return EXIT_SEMANTIC
            print(mp)
            return EXIT_OK
    print(f"ERROR: vault {vault_id} 미발견", file=sys.stderr)
    return EXIT_SEMANTIC


def _do_validate(cfg: dict) -> int:
    errors = _validate_schema(cfg)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_SEMANTIC
    print("yaml schema ok", file=sys.stderr)
    return EXIT_OK


# ── main ──────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WikiHub systemd unit renderer (ADR-0030 §6.1)",
    )
    parser.add_argument("--yaml", type=Path, default=None, help="wikihub.yaml 경로")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--render", action="store_true", help="template → DIR 에 render")
    g.add_argument("--list-enabled", action="store_true", help="enabled vault id stdout")
    g.add_argument("--get-mount-path", metavar="VAULT_ID", help="해당 vault 의 mount_path stdout")
    g.add_argument("--validate", action="store_true", help="yaml schema validate only")
    parser.add_argument("--out", type=Path, help="render 출력 디렉토리 (--render 필수)")
    args = parser.parse_args(argv)

    yaml_path = args.yaml or (_wikihub_home() / "wikihub.yaml")
    cfg = _load_yaml(yaml_path)

    # render mode 가 아닌 다른 mode 도 schema 가 깨지면 unsafe — minimal validation 만 silent.
    if args.render:
        errors = _validate_schema(cfg)
        if errors:
            for e in errors:
                print(f"ERROR: {e}", file=sys.stderr)
            return EXIT_OPERATIONAL
        if not args.out:
            print("ERROR: --render 는 --out DIR 필수", file=sys.stderr)
            return EXIT_OPERATIONAL
        return _do_render(cfg, args.out.expanduser().resolve())

    if args.list_enabled:
        return _do_list_enabled(cfg)
    if args.get_mount_path:
        return _do_get_mount_path(cfg, args.get_mount_path)
    if args.validate:
        return _do_validate(cfg)

    parser.print_help(sys.stderr)
    return EXIT_OPERATIONAL


if __name__ == "__main__":
    sys.exit(main())
