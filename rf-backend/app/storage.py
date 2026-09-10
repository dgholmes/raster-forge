"""Storage layout and path safety.

    storage/datasets/{dataset-uuid}/
        source/    original.tif       (never modified)
        working/   clean.tif          (only when NoData normalisation ran)
        output/
            tiles/ {z}/{x}/{y}.png
            {slug}_tiles.zip
        metadata/  metadata.json
        logs/      job-{job-uuid}.log

Every path is the storage root joined with a UUID and a *fixed* subdirectory
name. No user-supplied string — not the slug, not the uploaded filename —
ever becomes a path segment. `safe_join` is the guard for the one place
user input does reach a path: the tile route's {z}/{x}/{y}.
"""
from __future__ import annotations

import re
import shutil
import uuid as _uuid
from pathlib import Path

from flask import current_app

__all__ = [
    "PathTraversal",
    "dataset_root",
    "source_dir",
    "working_dir",
    "output_dir",
    "tiles_dir",
    "metadata_dir",
    "logs_dir",
    "safe_join",
    "dir_size_bytes",
    "free_disk_bytes",
    "storage_root",
    "delete_dataset_tree",
    "is_valid_uuid",
]

_UUID_RE = re.compile(r"^[0-9a-fA-F-]{32,36}$")


class PathTraversal(ValueError):
    """A resolved path escaped its permitted root."""


def storage_root() -> Path:
    root = Path(current_app.config["STORAGE_ROOT"])
    root.mkdir(parents=True, exist_ok=True)
    return root


def is_valid_uuid(value: str) -> bool:
    """Dataset ids come from the database, but they also arrive in URLs."""
    if not isinstance(value, str) or not _UUID_RE.match(value):
        return False
    try:
        _uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def dataset_root(dataset_id: str, create: bool = True) -> Path:
    if not is_valid_uuid(dataset_id):
        raise PathTraversal(f"Not a valid dataset id: {dataset_id!r}")
    p = storage_root() / "datasets" / dataset_id
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def _sub(dataset_id: str, *names: str, create: bool = True) -> Path:
    p = dataset_root(dataset_id, create=create).joinpath(*names)
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def source_dir(dataset_id: str, create: bool = True) -> Path:
    return _sub(dataset_id, "source", create=create)


def working_dir(dataset_id: str, create: bool = True) -> Path:
    return _sub(dataset_id, "working", create=create)


def output_dir(dataset_id: str, create: bool = True) -> Path:
    return _sub(dataset_id, "output", create=create)


def tiles_dir(dataset_id: str, create: bool = True) -> Path:
    return _sub(dataset_id, "output", "tiles", create=create)


def metadata_dir(dataset_id: str, create: bool = True) -> Path:
    return _sub(dataset_id, "metadata", create=create)


def logs_dir(dataset_id: str, create: bool = True) -> Path:
    return _sub(dataset_id, "logs", create=create)


def safe_join(root: Path, *parts: str) -> Path:
    """Join `parts` under `root`, refusing anything that escapes it.

    Rejects absolute components and '..' *before* joining, then verifies the
    fully resolved result is still inside the resolved root — which also
    catches escapes through a symlink.
    """
    root = Path(root).resolve()
    cleaned: list[str] = []
    for part in parts:
        if part is None:
            raise PathTraversal("Empty path component")
        text = str(part).replace("\\", "/").strip()
        if not text or text == ".":
            continue
        if text.startswith("/") or (len(text) > 1 and text[1] == ":"):
            raise PathTraversal(f"Absolute path component rejected: {part!r}")
        for segment in text.split("/"):
            if segment in ("", "."):
                continue
            if segment == ".." or "\x00" in segment:
                raise PathTraversal(f"Illegal path component: {segment!r}")
            cleaned.append(segment)

    if not cleaned:
        raise PathTraversal("No usable path components")

    candidate = root.joinpath(*cleaned)
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise PathTraversal(f"Could not resolve path: {exc}") from exc

    if not resolved.is_relative_to(root):
        raise PathTraversal(f"Path escapes its root: {candidate}")
    return resolved


def dir_size_bytes(path: Path) -> int:
    total = 0
    p = Path(path)
    if not p.exists():
        return 0
    for child in p.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def free_disk_bytes(path: Path) -> int:
    """Free bytes on the volume holding `path` (nearest existing ancestor)."""
    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return 0


def delete_dataset_tree(dataset_id: str) -> None:
    """Remove a dataset's entire directory. Validates the id first so a
    malformed value can never widen the delete."""
    root = dataset_root(dataset_id, create=False)
    base = (storage_root() / "datasets").resolve()
    resolved = root.resolve()
    if not resolved.is_relative_to(base) or resolved == base:
        raise PathTraversal(f"Refusing to delete {resolved}")
    shutil.rmtree(resolved, ignore_errors=True)
