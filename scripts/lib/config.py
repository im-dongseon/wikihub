"""wikihub.yaml load + 스키마 검증 (B1, F2 setup.md §Step 1 정합).

Schema 위반 시 VaultSyncFatal — vault_id를 알 수 없으므로 '__config__' 사용.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .exceptions import VaultSyncFatal

_log = logging.getLogger(__name__)

VAULT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
SUPPORTED_VAULT_TYPES = frozenset({"gdrive_api", "directory", "nas"})


@dataclass
class VaultConfig:
    id: str
    type: str
    enabled: bool
    sync_interval_sec: int
    local_path: Path
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentConfig:
    type: str
    binary: str
    oneshot_args: list[str]
    skill_prefix: str
    timeout_sec: int
    notify_on_fatal: bool
    profile: str | None = None  # optional Hermes profile name (issue #153)


@dataclass
class OperationsConfig:
    lint_interval_hours: int
    max_concurrent_vaults: str
    retry_max_attempts: int
    retry_backoff_base_sec: int
    disk: dict[str, Any]
    fatal_webhook_url: str | None
    fatal_webhook_timeout_sec: int
    instance_label: str | None  # R10 MED-3: webhook payload identifier (hostname leak 회피)
    # v9 신규 (ADR-0025·0026 — rclone install + vfs cache 정책)
    rclone_min_version: str = "1.65.0"
    rclone_max_version: str = "1.99.99"
    vfs_cache_max_size: str = "10G"
    vfs_refresh_mode: str = "recursive"  # recursive | per-file | none — K1·K2·K3
    # lint_operations_improvements (v0.1.8) — graphify timeout yaml expose
    graphify_timeout_sec: int = 900    # graphify subprocess wrapper timeout (15분 = 900s default, D4)


@dataclass
class Config:
    instance_root: Path
    timezone: str
    vaults: dict[str, VaultConfig]
    operations: OperationsConfig
    agent: AgentConfig
    version: int = 1


def _require(d: dict[str, Any], key: str, *, ctx: str) -> Any:
    if key not in d:
        raise VaultSyncFatal(
            vault_id="__config__",
            reason=f"{ctx}: 필수 키 누락 '{key}'",
            remediation=f"wikihub.yaml 의 {ctx}.{key} 필드를 채우세요.",
        )
    return d[key]


def _validate_vault_id(vid: str) -> None:
    if not VAULT_ID_PATTERN.match(vid):
        raise VaultSyncFatal(
            vault_id="__config__",
            reason=f"vault id 형식 위반: '{vid}' (정규식 {VAULT_ID_PATTERN.pattern})",
            remediation="vault id 는 소문자 + 숫자 + 언더스코어만 허용. 첫 글자는 소문자.",
        )


def _parse_vault(vid: str, vcfg: dict[str, Any]) -> VaultConfig:
    _validate_vault_id(vid)
    vtype = _require(vcfg, "type", ctx=f"vaults.{vid}")
    if vtype not in SUPPORTED_VAULT_TYPES:
        raise VaultSyncFatal(
            vault_id=vid,
            reason=f"지원하지 않는 vault type '{vtype}'",
            remediation=f"type 은 다음 중 하나여야 함: {sorted(SUPPORTED_VAULT_TYPES)}",
        )
    interval = int(_require(vcfg, "sync_interval_sec", ctx=f"vaults.{vid}"))
    if interval < 60:
        raise VaultSyncFatal(
            vault_id=vid,
            reason=f"sync_interval_sec={interval} 너무 짧음 (>=60)",
            remediation="60 이상 정수로 설정",
        )
    local_path = Path(_require(vcfg, "local_path", ctx=f"vaults.{vid}")).expanduser()
    options = dict(vcfg.get("options", {}))

    # ADR-0031 §Decision B (HIGH-A1): mount_path 는 maintainer-controlled.
    # default (Path C+) 는 mount_path == local_path 지만, advanced 운영자가 bind-mount /
    # ramdisk / multi-vault layout 분리 등으로 명시 분리할 수 있음. fail 아닌 soft warn 만.
    mount_path_raw = options.get("mount_path")
    if mount_path_raw is not None:
        mount_path = Path(str(mount_path_raw)).expanduser()
        if mount_path != local_path:
            _log.warning(
                "vault '%s': mount_path (%s) != local_path (%s) — default 패턴 아님. "
                "bind-mount/ramdisk/multi-vault layout 의도가 아니면 yaml 정합 확인 권장.",
                vid, mount_path, local_path,
            )

    # NAS vault 필수 옵션 검증 및 기본값 (features/20260602_nas_vault §2.1)
    if vtype == "nas":
        _require(options, "sftp_host", ctx=f"vaults.{vid}.options")
        _require(options, "sftp_user", ctx=f"vaults.{vid}.options")
        _require(options, "rclone_remote_path", ctx=f"vaults.{vid}.options")
        options.setdefault("sftp_port", 22)
        options.setdefault("ssh_key_path", "~/.ssh/id_ed25519")
        # rclone_remote_name 기본값: nas_{vault_id}
        options.setdefault("rclone_remote_name", f"nas_{vid}")

    return VaultConfig(
        id=vid,
        type=vtype,
        enabled=bool(vcfg.get("enabled", True)),
        sync_interval_sec=interval,
        local_path=local_path,
        options=options,
    )


def _parse_agent(acfg: dict[str, Any]) -> AgentConfig:
    return AgentConfig(
        type=str(_require(acfg, "type", ctx="agent")),
        binary=str(_require(acfg, "binary", ctx="agent")),
        oneshot_args=list(acfg.get("oneshot_args", [])),
        skill_prefix=str(acfg.get("skill_prefix", "wh:")),
        timeout_sec=int(acfg.get("timeout_sec", 600)),
        notify_on_fatal=bool(acfg.get("notify_on_fatal", True)),
        profile=acfg.get("profile"),  # optional, None if unset (issue #153)
    )


def _parse_operations(ocfg: dict[str, Any]) -> OperationsConfig:
    return OperationsConfig(
        lint_interval_hours=int(ocfg.get("lint_interval_hours", 3)),
        max_concurrent_vaults=str(ocfg.get("max_concurrent_vaults", "serial")),
        retry_max_attempts=int(ocfg.get("retry", {}).get("max_attempts", 5)),
        retry_backoff_base_sec=int(ocfg.get("retry", {}).get("backoff_base_sec", 60)),
        disk=dict(ocfg.get("disk", {})),
        fatal_webhook_url=ocfg.get("fatal_webhook_url"),
        fatal_webhook_timeout_sec=int(ocfg.get("fatal_webhook_timeout_sec", 10)),
        instance_label=ocfg.get("instance_label"),
        # v9 신규 (ADR-0025·0026)
        rclone_min_version=str(ocfg.get("rclone_min_version", "1.65.0")),
        rclone_max_version=str(ocfg.get("rclone_max_version", "1.99.99")),
        vfs_cache_max_size=str(ocfg.get("vfs_cache_max_size", "10G")),
        vfs_refresh_mode=str(ocfg.get("vfs_refresh_mode", "recursive")),
        # lint_operations_improvements (v0.1.8)
        graphify_timeout_sec=int(ocfg.get("graphify_timeout_sec", 900)),
    )


def load_wikihub_yaml(path: Path | None = None) -> Config:
    """wikihub.yaml 로드 + 스키마 검증.

    default path: /opt/wikihub/wikihub.yaml.
    환경변수 ``WIKIHUB_YAML`` 로 override 가능 (dev box 용).
    """
    if path is None:
        env_path = os.environ.get("WIKIHUB_YAML")
        path = Path(env_path) if env_path else Path("/opt/wikihub/wikihub.yaml")
    if not path.exists():
        raise VaultSyncFatal(
            vault_id="__config__",
            reason=f"wikihub.yaml 없음: {path}",
            remediation=(
                "/wh:setup 을 호출하여 wikihub.yaml 을 생성하세요 — "
                "ADR-0031 §Decision A 정합 (`.example` template → derived 값 patching → atomic write). "
                "install.sh 직후 첫 /wh:setup 호출이 yaml 의 시작 책임."
            ),
        )
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise VaultSyncFatal(
            vault_id="__config__",
            reason=f"wikihub.yaml YAML 파싱 실패: {e}",
            remediation="yaml 문법 오류 수정",
        ) from e
    if not isinstance(data, dict):
        raise VaultSyncFatal(
            vault_id="__config__",
            reason="wikihub.yaml 루트가 mapping 이 아님",
            remediation="key:value 구조로 작성",
        )
    version = int(data.get("version", 1))
    if version != 1:
        raise VaultSyncFatal(
            vault_id="__config__",
            reason=f"지원하지 않는 wikihub.yaml version={version}",
            remediation="version: 1 만 지원 (v0.1.0)",
        )
    instance = _require(data, "instance", ctx="root")
    vaults_raw = _require(data, "vaults", ctx="root")
    if not isinstance(vaults_raw, list) or not vaults_raw:
        raise VaultSyncFatal(
            vault_id="__config__",
            reason="vaults 가 비어 있거나 list 가 아님",
            remediation="최소 1개 vault 정의 필요",
        )
    vaults: dict[str, VaultConfig] = {}
    for vcfg in vaults_raw:
        vid = _require(vcfg, "id", ctx="vaults[*]")
        if vid in vaults:
            raise VaultSyncFatal(
                vault_id=vid,
                reason=f"중복된 vault id '{vid}'",
                remediation="vault id 는 unique 해야 함",
            )
        vaults[vid] = _parse_vault(vid, vcfg)
    # vault 간 rclone_rc_port 중복 검증 (ADR-0025: rc port unique per vault)
    seen_ports: dict[str | int, str] = {}
    for vcfg in vaults_raw:
        vid = _require(vcfg, "id", ctx="vaults[*]")
        # NAS vault 는 rclone rc 미사용 — port 검증 skip (Issue #117)
        if str(vcfg.get("type", "")).strip() == "nas":
            continue
        opts = dict(vcfg.get("options", {}))
        port = opts.get("rclone_rc_port")
        if port is not None:
            if port in seen_ports:
                raise VaultSyncFatal(
                    vault_id=vid,
                    reason=f"rclone_rc_port={port} 중복 (vault '{seen_ports[port]}' 가 이미 사용 중)",
                    remediation="각 vault 의 rclone_rc_port 는 고유해야 합니다. 중복 port 제거 또는 변경.",
                )
            seen_ports[port] = vid
    return Config(
        version=version,
        instance_root=Path(_require(instance, "root", ctx="instance")).expanduser(),
        timezone=str(instance.get("timezone", "Asia/Seoul")),
        vaults=vaults,
        operations=_parse_operations(dict(data.get("operations", {}))),
        agent=_parse_agent(dict(_require(data, "agent", ctx="root"))),
    )
