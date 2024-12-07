"""Utility functions."""

from pathlib import Path
import re
from uuid import UUID

TEMPLATE = re.compile(r'^\s?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?\s?(.+)')


def get_uuid_and_name(path: Path) -> tuple[UUID | None, str]:
    """Return UUID or none and a name."""
    reg = TEMPLATE.match(path.name)

    uuid = reg.group(1)
    name = reg.group(2)

    if uuid is not None:  # noqa: PLR2004
        return UUID(uuid), name

    return None, name
