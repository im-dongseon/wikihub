#!/usr/bin/env python3
"""WikiHub systemd unit template renderer.

정본 contract: features/20260517_update_mode/analysis_and_design.md §6.1 (ADR-0030).

install.sh + update_mode 가 본 helper 를 호출해서 _system/systemd/*.template →
~/.config/systemd/user/wikihub-*.service|.timer 로 render.

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
            data = yaml.safe_load(f)
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
_WIKIHUB_SKILLS = ("wh-ingest", "wh-lint", "wh-query", "wh-graphify", "wh-setup")


def _per_skill_invocation(cfg: dict, skill_name: str) -> str:
    """ADR-0032 §sub-2 / ADR-0033: per-unit `{skill}` placeholder substitution.

    `oneshot_args` 에 `{skill}` placeholder 가 반드시 있어야 함 (fail-fast).
    F5 schema: `oneshot_args: ["chat", "--skills", "{skill}", "--quiet", "--query"]`.
    F5 이전 (e.g. update_mode rollback) 의 `oneshot_args: ["-z"]` 는 placeholder 부재 → fail.
    """
    agent = cfg.get("agent") or {}
    binary = agent.get("binary", "")
    oneshot_args = agent.get("oneshot_args") or []
    has_placeholder = any("{skill}" in str(a) for a in oneshot_args)
    if not has_placeholder:
        print(
            f"ERROR: agent.oneshot_args 에 '{{skill}}' placeholder 누락 — "
            f"F5 schema (ADR-0032) 요구. 현재 oneshot_args={oneshot_args!r}. "
            f"yaml 의 oneshot_args 를 `[\"chat\", \"--skills\", \"{{skill}}\", \"--quiet\", \"--query\"]` 로 갱신 필요 "
            f"(또는 F5 이전 ref 로 rollback 시 `[\"-z\"]` 로 다운그레이드).",
            file=sys.stderr,
        )
        sys.exit(EXIT_OPERATIONAL)
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
        "lint_interval_hours": str(ops.get("lint_interval_hours", 24)),
        "agent_invocation": agent_invocation,
        "skill_prefix": agent.get("skill_prefix", "wh-"),
        # F5 — yaml.agent.timeout_sec ↔ systemd TimeoutStartSec sync (R3-CR3-2 B-HIGH-2)
        "timeout_start_sec": str(agent.get("timeout_sec", 600)),
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
    return {
        f"remote_name_for_{vid}": str(opts.get("rclone_remote_name", vid)),
        f"rc_port_for_{vid}": str(opts.get("rclone_rc_port", 5572)),
    }


def _current_vault_subs(vault: dict) -> dict[str, str]:
    """Current-vault scalar keys (suffix 없음) — 본 vault 의 render 결과에만 적용.

    template 에 `{credentials_path}` · `{sync_interval_sec}` 형태로 등장 — vault 마다 다른
    값. per-vault render 마다 별도 dict 산출 후 instance-wide subs 와 merge.
    """
    opts = vault.get("options") or {}
    expanded_creds = os.path.expanduser(str(opts.get("credentials_path", "")))
    return {
        "credentials_path": expanded_creds,
        "sync_interval_sec": str(vault.get("sync_interval_sec", 600)),
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
      lint.timer.template (singleton)                   → lint.timer (wikihub-lint.timer 로 prefix)
      ops-alert.service (file, no template suffix)      → ops-alert.service
    """
    name = template_path.name
    if name.endswith(".template"):
        name = name[:-len(".template")]
    if vault_id is not None:
        # per-vault: `@.service` → `@<vid>.service`
        name = name.replace("@.", f"@{vault_id}.", 1)
    # singleton 의 wikihub- prefix 정합 (lint.timer → wikihub-lint.timer)
    if not name.startswith("wikihub-") and name not in ("ops-alert.service",):
        # convention: lint.*, ops-alert.service 는 그대로. 다른 singleton 은 wikihub- prefix.
        if name.startswith("lint."):
            name = "wikihub-" + name
    return name


def _do_render(cfg: dict, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
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
                # per-vault render: base + current vault scalar keys (credentials_path 등)
                current_subs = _current_vault_subs(v)
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

    # enabled=false 또는 제거된 vault 의 stale unit 정리
    # — wikihub-mount@<vid>.service, wikihub-vault@<vid>.service, wikihub-vault@<vid>.timer.
    removed = 0
    for p in sorted(out_dir.glob("wikihub-*@*")):
        m = re.match(r"^wikihub-(?:mount|vault)@([^.]+)\.(service|timer)$", p.name)
        if not m:
            continue
        vid = m.group(1)
        if vid not in enabled_ids:
            try:
                p.unlink()
                removed += 1
            except OSError as e:
                print(f"WARN: stale unit 삭제 실패 {p}: {e}", file=sys.stderr)

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

    services = sorted(out_dir.glob("wikihub-*.service")) + sorted(out_dir.glob("wikihub-*.timer"))
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
                # fallback to local_path
                mp = v.get("local_path", "")
            if not mp:
                print(f"ERROR: vault {vault_id} 의 mount_path 미정의", file=sys.stderr)
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
