from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import LabError


@dataclass(frozen=True)
class Timings:
    warmup_seconds: int
    capture_seconds: int
    fault_propagation_seconds: int
    collector_flush_seconds: int


@dataclass(frozen=True)
class LabConfig:
    repo_root: Path
    otel_demo_version: str
    git_ref: str
    expected_commit: str
    repository_url: str
    compose_project: str
    timings: Timings
    frontend_proxy_port: int
    envoy_admin_port: int

    @property
    def infrastructure_dir(self) -> Path:
        return self.repo_root / "infrastructure" / "telemetry-lab"

    @property
    def demo_dir(self) -> Path:
        return self.repo_root / ".runtime" / "opentelemetry-demo"

    @property
    def runtime_dir(self) -> Path:
        return self.repo_root / ".runtime" / "telemetry-lab"

    @property
    def runtime_flag_dir(self) -> Path:
        return self.runtime_dir / "flagd"

    @property
    def runtime_flag_file(self) -> Path:
        return self.runtime_flag_dir / "demo.flagd.json"

    @property
    def idle_capture_dir(self) -> Path:
        return self.runtime_dir / "idle-capture"

    @property
    def raw_data_dir(self) -> Path:
        return self.repo_root / "data" / "raw"

    @property
    def scenarios_file(self) -> Path:
        return self.infrastructure_dir / "scenarios.json"

    @property
    def collector_config(self) -> Path:
        return self.infrastructure_dir / "collector" / "aegis-capture-config.yml"

    @property
    def compose_overlay(self) -> Path:
        return self.infrastructure_dir / "compose.capture.yml"

    @property
    def upstream_flag_file(self) -> Path:
        return self.demo_dir / "src" / "flagd" / "demo.flagd.json"

    @property
    def upstream_compose_file(self) -> Path:
        return self.demo_dir / "compose.yaml"

    @property
    def upstream_env_file(self) -> Path:
        return self.demo_dir / ".env"


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _require(mapping: dict[str, Any], key: str, expected_type: type) -> Any:
    value = mapping.get(key)
    if not isinstance(value, expected_type):
        raise LabError(f"Invalid lab configuration: {key!r} must be {expected_type.__name__}.")
    return value


def load_config(repo_root: Path | None = None) -> LabConfig:
    root = (repo_root or default_repo_root()).resolve()
    path = root / "infrastructure" / "telemetry-lab" / "lab.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabError(f"Cannot read telemetry lab configuration {path}: {exc}") from exc

    defaults = _require(document, "defaults", dict)
    ports = _require(document, "ports", dict)
    timings = Timings(
        warmup_seconds=int(_require(defaults, "warmup_seconds", int)),
        capture_seconds=int(_require(defaults, "capture_seconds", int)),
        fault_propagation_seconds=int(
            _require(defaults, "fault_propagation_seconds", int)
        ),
        collector_flush_seconds=int(_require(defaults, "collector_flush_seconds", int)),
    )
    return LabConfig(
        repo_root=root,
        otel_demo_version=_require(document, "otel_demo_version", str),
        git_ref=_require(document, "git_ref", str),
        expected_commit=_require(document, "expected_commit", str),
        repository_url=_require(document, "repository_url", str),
        compose_project=_require(document, "compose_project", str),
        timings=timings,
        frontend_proxy_port=int(_require(ports, "frontend_proxy", int)),
        envoy_admin_port=int(_require(ports, "envoy_admin", int)),
    )
