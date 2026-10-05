from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path

from .config import LabConfig
from .errors import LabError
from .flags import current_variant
from .scenarios import Scenario, validate_against_upstream
from .validation import validate_jsonl


class CommandRunner:
    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                list(command),
                cwd=cwd,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            raise LabError(f"Could not run {command[0]!r}: {exc}") from exc
        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip()
            raise LabError(
                f"Command failed ({result.returncode}): {' '.join(command)}"
                + (f"\n{details}" if details else "")
            )
        return result


class DemoEnvironment:
    def __init__(self, config: LabConfig, runner: CommandRunner | None = None) -> None:
        self.config = config
        self.runner = runner or CommandRunner()

    def _require_executable(self, name: str) -> None:
        if shutil.which(name) is None:
            raise LabError(f"Required executable {name!r} was not found on PATH.")

    def check_cli_tools(self) -> None:
        self._require_executable("git")
        self._require_executable("docker")
        self.runner.run(["docker", "compose", "version"], cwd=self.config.repo_root)

    def check_docker_daemon(self) -> None:
        try:
            self.runner.run(["docker", "info"], cwd=self.config.repo_root)
        except LabError as exc:
            raise LabError(
                "Docker is installed, but the Docker daemon is not reachable. "
                "Start Docker Desktop and retry."
            ) from exc

    def _git(self, *arguments: str) -> str:
        return self.runner.run(
            ["git", *arguments], cwd=self.config.demo_dir
        ).stdout.strip()

    def setup(self) -> str:
        self.check_cli_tools()
        demo_dir = self.config.demo_dir
        demo_dir.parent.mkdir(parents=True, exist_ok=True)
        if not demo_dir.exists():
            self.runner.run(
                [
                    "git",
                    "clone",
                    "--filter=blob:none",
                    "--no-checkout",
                    self.config.repository_url,
                    str(demo_dir),
                ],
                cwd=self.config.repo_root,
            )
        if not (demo_dir / ".git").is_dir():
            raise LabError(
                f"Runtime path exists but is not an OpenTelemetry Demo Git clone: {demo_dir}"
            )

        origin = self._git("remote", "get-url", "origin")
        accepted_origins = {
            self.config.repository_url,
            self.config.repository_url.removesuffix(".git"),
        }
        if origin.removesuffix(".git") not in {
            value.removesuffix(".git") for value in accepted_origins
        }:
            raise LabError(f"Unexpected origin for runtime clone: {origin}")
        dirty = self._git("status", "--porcelain")
        if dirty:
            raise LabError(
                "The runtime OpenTelemetry Demo clone has local changes. "
                "The lab will not overwrite them; clean the runtime clone or use clean --runtime."
            )

        self._git(
            "fetch",
            "--force",
            "--depth",
            "1",
            "origin",
            f"refs/tags/{self.config.git_ref}:refs/tags/{self.config.git_ref}",
        )
        tag_commit = self._git("rev-parse", f"{self.config.git_ref}^{{commit}}")
        if tag_commit != self.config.expected_commit:
            raise LabError(
                f"Upstream tag {self.config.git_ref} resolved to {tag_commit}, "
                f"expected {self.config.expected_commit}."
            )
        self._git("checkout", "--detach", "--force", self.config.expected_commit)
        commit = self.verify_checkout()

        self.config.runtime_flag_dir.mkdir(parents=True, exist_ok=True)
        self.config.idle_capture_dir.mkdir(parents=True, exist_ok=True)
        self.config.raw_data_dir.mkdir(parents=True, exist_ok=True)
        if not self.config.runtime_flag_file.exists():
            shutil.copy2(self.config.upstream_flag_file, self.config.runtime_flag_file)
        return commit

    def verify_checkout(self) -> str:
        commit = self._git("rev-parse", "HEAD")
        if commit != self.config.expected_commit:
            raise LabError(
                f"OpenTelemetry Demo checkout is {commit}; expected {self.config.expected_commit}."
            )
        tags = set(self._git("tag", "--points-at", "HEAD").splitlines())
        if self.config.git_ref not in tags:
            raise LabError(
                f"OpenTelemetry Demo commit is not tagged {self.config.git_ref}."
            )
        return commit

    def verify_scenarios(self, scenarios: dict[str, Scenario]) -> None:
        try:
            upstream = json.loads(self.config.upstream_flag_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LabError(f"Cannot read pinned upstream feature flags: {exc}") from exc
        validate_against_upstream(scenarios, upstream)

    def reset_runtime_flag_file(self) -> None:
        self.config.runtime_flag_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.config.upstream_flag_file, self.config.runtime_flag_file)

    def _compose_environment(self, capture_dir: Path) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(
            {
                "AEGIS_CAPTURE_DIR": str(capture_dir.resolve()),
                "AEGIS_FLAGD_DIR": str(self.config.runtime_flag_dir.resolve()),
                "OTEL_COLLECTOR_CONFIG_EXTRAS": str(self.config.collector_config.resolve()),
                "DEMO_VERSION": self.config.otel_demo_version,
                "IMAGE_VERSION": self.config.otel_demo_version,
                "ENVOY_PORT": str(self.config.frontend_proxy_port),
                "ENVOY_ADMIN_PORT": str(self.config.envoy_admin_port),
                "LOCUST_AUTOSTART": "true",
            }
        )
        return environment

    def _compose_command(self, *arguments: str) -> list[str]:
        return [
            "docker",
            "compose",
            "--project-name",
            self.config.compose_project,
            "--env-file",
            str(self.config.upstream_env_file),
            "--file",
            str(self.config.upstream_compose_file),
            "--file",
            str(self.config.compose_overlay),
            *arguments,
        ]

    def compose(self, *arguments: str, capture_dir: Path | None = None) -> str:
        directory = capture_dir or self.config.idle_capture_dir
        directory.mkdir(parents=True, exist_ok=True)
        result = self.runner.run(
            self._compose_command(*arguments),
            cwd=self.config.demo_dir,
            env=self._compose_environment(directory),
        )
        return result.stdout.strip()

    def clear_idle_capture(self) -> None:
        self.config.idle_capture_dir.mkdir(parents=True, exist_ok=True)
        for filename in ("metrics.jsonl", "logs.jsonl", "traces.jsonl"):
            (self.config.idle_capture_dir / filename).unlink(missing_ok=True)

    def start(self) -> None:
        self.setup()
        self.check_docker_daemon()
        self.clear_idle_capture()
        self.compose(
            "up",
            "--detach",
            "--pull",
            "always",
            "--no-build",
            "--wait",
            "--wait-timeout",
            "600",
        )
        # A running file exporter keeps an open handle if its host file is
        # removed. Always recreate the collector after clearing idle output so
        # its writers attach to fresh, visible files on every start.
        self.recreate_collector(self.config.idle_capture_dir)

    def running_services(self) -> set[str]:
        output = self.compose("ps", "--services", "--status", "running")
        return {line.strip() for line in output.splitlines() if line.strip()}

    def is_started(self) -> bool:
        running = self.running_services()
        return {"otel-collector", "flagd", "load-generator", "frontend-proxy"} <= running

    def has_running_project_containers(self) -> bool:
        result = self.runner.run(
            [
                "docker",
                "ps",
                "--filter",
                f"label=com.docker.compose.project={self.config.compose_project}",
                "--format",
                "{{.ID}}",
            ],
            cwd=self.config.repo_root,
        )
        return bool(result.stdout.strip())

    def ensure_started(self) -> None:
        try:
            started = self.is_started()
        except LabError:
            started = False
        if not started:
            self.start()

    def status(self) -> str:
        self.check_docker_daemon()
        return self.compose("ps", "--all")

    def stop(self) -> None:
        self.check_docker_daemon()
        self.compose("down", "--remove-orphans")

    def recreate_collector(self, capture_dir: Path) -> None:
        capture_dir.mkdir(parents=True, exist_ok=True)
        self.compose(
            "up",
            "--detach",
            "--no-deps",
            "--force-recreate",
            "otel-collector",
            capture_dir=capture_dir,
        )

    def stop_collector(self, capture_dir: Path) -> None:
        self.compose("stop", "--timeout", "20", "otel-collector", capture_dir=capture_dir)

    def restore_idle_collector(self) -> None:
        self.clear_idle_capture()
        self.recreate_collector(self.config.idle_capture_dir)

    def _flagd_ofrep_port(self) -> int:
        output = self.compose("port", "flagd", "8016")
        first_line = next((line for line in output.splitlines() if line.strip()), "")
        if not first_line or ":" not in first_line:
            raise LabError("Could not determine flagd OFREP host port.")
        try:
            return int(first_line.rsplit(":", 1)[1])
        except ValueError as exc:
            raise LabError(f"Unexpected flagd port mapping: {first_line}") from exc

    def verify_flag(self, flag_name: str, expected_variant: str, timeout: int = 20) -> None:
        actual_file_variant = current_variant(self.config.runtime_flag_file, flag_name)
        if actual_file_variant != expected_variant:
            raise LabError(
                f"Feature flag file has {flag_name}={actual_file_variant}, "
                f"expected {expected_variant}."
            )

        port = self._flagd_ofrep_port()
        url = f"http://127.0.0.1:{port}/ofrep/v1/evaluate/flags/{flag_name}"
        payload = json.dumps({"context": {"targetingKey": "aegis-validation"}}).encode()
        deadline = time.monotonic() + timeout
        last_error = "no response"
        while time.monotonic() < deadline:
            request = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    result = json.loads(response.read().decode("utf-8"))
                if result.get("variant") == expected_variant:
                    return
                last_error = f"flagd returned variant {result.get('variant')!r}"
            except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
                last_error = str(exc)
            time.sleep(1)
        raise LabError(
            f"flagd did not confirm {flag_name}={expected_variant} within {timeout}s: {last_error}"
        )

    def verify_traffic(self, timeout: int = 60) -> tuple[str, ...]:
        frontend_url = f"http://127.0.0.1:{self.config.frontend_proxy_port}/"
        deadline = time.monotonic() + timeout
        last_error = "no trace batches observed"
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(frontend_url, timeout=5) as response:
                    if response.status >= 400:
                        last_error = f"frontend returned HTTP {response.status}"
                        time.sleep(2)
                        continue
                traces = validate_jsonl(
                    self.config.idle_capture_dir / "traces.jsonl", "resourceSpans"
                )
                if {"frontend", "load-generator"} & set(traces.services):
                    return traces.services
                last_error = "traces did not include frontend or load-generator service identity"
            except (LabError, OSError, urllib.error.URLError) as exc:
                last_error = str(exc)
            time.sleep(2)
        raise LabError(
            "The built-in load generator did not produce verifiable frontend traffic: " + last_error
        )
