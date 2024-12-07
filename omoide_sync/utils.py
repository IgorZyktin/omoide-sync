"""Utility functions."""

from pathlib import Path
import re
import shutil
from uuid import UUID

TEMPLATE = re.compile(r'^\s?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?\s?(.+)')


def get_uuid_and_name(path: Path) -> tuple[UUID | None, str]:
    """Return UUID or none and a name."""
    reg = TEMPLATE.match(path.name)

    if reg is None:
        return None, path.name

    uuid = reg.group(1)
    name = reg.group(2)

    if uuid is not None:  # noqa: PLR2004
        return UUID(uuid), name

    return None, name


def move(source_path: Path, archive_path: Path, target_path: Path) -> None:
    """Move folder or file."""
    relative_path = target_path.relative_to(source_path)
    destination_path = archive_path / relative_path

    if target_path.is_dir():
        shutil.copytree(
            target_path,
            destination_path,
            dirs_exist_ok=True,
        )
        shutil.rmtree(target_path)

    else:
        new_folder = destination_path.parent
        new_folder.mkdir(parents=True)
        shutil.move(
            target_path,
            destination_path,
        )