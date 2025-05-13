"""Filesystem related code."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from omoide_sync.models import Setup
from omoide_sync import cfg
from loguru import logger

LOG = logger

@dataclass
class Folder:
    """Folder abstraction."""

    path: Path
    setup: Setup
    children: list['Folder'] = field(default_factory=list)

    def output(self, depth: int = 0) -> None:
        """Show folder contents."""
        LOG.info('\t' * depth + str(self.path))

        for child in self.children:
            child.output(depth + 1)


def scan_folders(path: Path, parent: Folder | None = None) -> list[Folder]:
    """Extract folder info from filesystem."""
    config = cfg.get_config()
    setup = Setup.from_path(
        path,
        filename=config.setup_filename,
        parent_setup=parent.setup if parent else None,
    )

    folders: list[Folder] = []
    for folder_path in os.scandir(path):
        if not folder_path.is_dir():
            continue

        folder = Folder(
            path=Path(folder_path),
            setup=setup,
        )
        folders.append(folder)
        folder.children = scan_folders(Path(folder_path), folder)

    if parent:
        parent.children = folders

    return folders
