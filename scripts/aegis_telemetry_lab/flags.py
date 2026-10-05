from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import LabError


def read_flag_document(path: Path) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabError(f"Cannot read feature flags from {path}: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("flags"), dict):
        raise LabError(f"Invalid feature flag document: {path}")
    return document


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, document: dict[str, object]) -> None:
    content = (json.dumps(document, indent=2, sort_keys=False) + "\n").encode("utf-8")
    _atomic_write_bytes(path, content)


def patch_variants(path: Path, changes: dict[str, str]) -> None:
    document = read_flag_document(path)
    flags = document["flags"]
    assert isinstance(flags, dict)
    for flag_name, variant in changes.items():
        flag = flags.get(flag_name)
        if not isinstance(flag, dict):
            raise LabError(f"Cannot patch missing feature flag {flag_name!r}.")
        variants = flag.get("variants")
        if not isinstance(variants, dict) or variant not in variants:
            raise LabError(f"Feature flag {flag_name!r} has no variant {variant!r}.")
        flag["defaultVariant"] = variant
    atomic_write_json(path, document)


def current_variant(path: Path, flag_name: str) -> str:
    document = read_flag_document(path)
    flags = document["flags"]
    assert isinstance(flags, dict)
    flag = flags.get(flag_name)
    if not isinstance(flag, dict) or not isinstance(flag.get("defaultVariant"), str):
        raise LabError(f"Cannot read current variant for feature flag {flag_name!r}.")
    return flag["defaultVariant"]


@contextmanager
def temporary_patch(path: Path, changes: dict[str, str]) -> Iterator[None]:
    try:
        original = path.read_bytes()
    except OSError as exc:
        raise LabError(f"Cannot back up feature flag file {path}: {exc}") from exc
    patch_variants(path, changes)
    try:
        yield
    finally:
        _atomic_write_bytes(path, original)
