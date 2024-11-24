"""Utility functions."""

from pathlib import Path
from uuid import UUID


def split_name(path: Path, spacer: str) -> tuple[UUID | None, str]:
    """Try to extract UUID from path."""
    parts = path.name.split(spacer, maxsplit=1)

    if len(parts) == 2:
        return UUID(parts[0]), parts[1]

    return None, path.name
