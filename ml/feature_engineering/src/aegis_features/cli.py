from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .config import (
    DEFAULT_MAX_INVALID_OBSERVATION_RATIO,
    DEFAULT_WINDOW_SECONDS,
    BuildConfig,
)
from .dataset import build_dataset, dataset_summary, validate_dataset
from .errors import FeatureEngineeringError
from .inspection import combine_inventories, inspect_run


def _print(document: dict[str, Any]) -> None:
    print(json.dumps(document, indent=2, sort_keys=True))


def _dataset_path(value: str, output_root: Path) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_dir() else output_root / value


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="aegis-features")
    root.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    root.add_argument("--output-root", type=Path, default=Path("data/features"))
    commands = root.add_subparsers(dest="command", required=True)

    inspect_parser = commands.add_parser("inspect", help="Inspect validated capture runs")
    inspect_parser.add_argument("--run", action="append", required=True, dest="runs")

    build_parser = commands.add_parser("build", help="Build a deterministic feature dataset")
    build_parser.add_argument("--run", action="append", required=True, dest="runs")
    build_parser.add_argument("--window-seconds", type=int, default=DEFAULT_WINDOW_SECONDS)
    build_parser.add_argument(
        "--max-invalid-observation-ratio",
        type=float,
        default=DEFAULT_MAX_INVALID_OBSERVATION_RATIO,
    )

    validate_parser = commands.add_parser("validate", help="Reopen and validate a dataset")
    validate_parser.add_argument("--dataset", required=True)

    summary_parser = commands.add_parser("summary", help="Print a compact dataset summary")
    summary_parser.add_argument("--dataset", required=True)
    return root


def run(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.command == "inspect":
        reports = [inspect_run(arguments.raw_root, run_id) for run_id in arguments.runs]
        return {"runs": reports, "combined_inventory": combine_inventories(reports)}
    if arguments.command == "build":
        config = BuildConfig(
            raw_root=arguments.raw_root,
            output_root=arguments.output_root,
            window_seconds=arguments.window_seconds,
            max_invalid_observation_ratio=arguments.max_invalid_observation_ratio,
        )
        result = build_dataset(arguments.runs, config)
        return {
            "dataset_id": result.dataset_id,
            "dataset_dir": str(result.dataset_dir),
            "service_window_rows": result.manifest["service_window_rows"],
            "metric_window_rows": result.manifest["metric_window_rows"],
            "quality_status": result.quality["status"],
            "build_duration_seconds": result.manifest["build_duration_seconds"],
        }
    dataset_dir = _dataset_path(arguments.dataset, arguments.output_root)
    if arguments.command == "validate":
        return validate_dataset(dataset_dir)
    return dataset_summary(dataset_dir)


def main(argv: Sequence[str] | None = None) -> int:
    argument_parser = parser()
    arguments = argument_parser.parse_args(argv)
    try:
        _print(run(arguments))
    except (FeatureEngineeringError, ValueError) as exc:
        argument_parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
