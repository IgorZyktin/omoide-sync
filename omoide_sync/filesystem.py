"""Filesystem related code."""

from dataclasses import dataclass
from dataclasses import field
import os
from pathlib import Path

from colorama import Fore
from loguru import logger

from omoide_sync import cfg
from omoide_sync.models import Setup

LOG = logger


@dataclass
class Folder:
    """Folder abstraction."""

    path: Path
    setup: Setup
    children: list['Folder'] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)

    def output(self, depth: int = 0, position: str | None = None) -> None:
        """Show folder contents."""
        suffix = ''
        if depth:
            if position == 'one-of':
                suffix = '├───'
            elif position == 'last':
                suffix = '└───'

        prefix = '\t' * (depth - 1)

        if self.children:
            folders = f'{Fore.RED}{len(self.children)}{Fore.RESET}'
        else:
            folders = '0'

        if self.files:
            files = f'{Fore.RED}{len(self.files)}{Fore.RESET}'
        else:
            files = '0'

        if folders != '0' or files != '0':
            ending = f' (folders={folders}, files={files})'
        else:
            ending = ''

        LOG.info(
            f'{prefix}{suffix}{Fore.GREEN}{self.path.name}{Fore.RESET}{ending}'
        )

        total = len(self.children)
        for i, child in enumerate(self.children, start=1):
            if total > 1 and i < total:
                position = 'one-of'
            else:
                position = 'last'

            child.output(depth + 1, position)


def scan_folders(path: Path, parent: Folder | None = None) -> list[Folder]:
    """Extract folder info from filesystem."""
    config = cfg.get_config()

    if parent is None:
        setup = Setup.from_path(
            path,
            filename=config.setup_filename,
            parent_setup=parent.setup if parent else None,
        )
    else:
        setup = parent.setup

    folders: list[Folder] = []

    for folder_path in os.scandir(path):
        if not folder_path.is_dir():
            continue

        if folder_path.name.startswith(config.skip_prefixes):
            continue

        folder = Folder(
            path=Path(folder_path),
            setup=Setup.from_path(
                Path(folder_path),
                filename=config.setup_filename,
                parent_setup=setup,
            ),
        )
        folders.append(folder)
        folder.children = scan_folders(Path(folder_path), folder)
        folder.files = [
            Path(each)
            for each in os.scandir(folder_path)
            if each.is_file()
            and each.name.lower().endswith(config.supported_formats)
        ]

    if parent:
        parent.children = folders

    return folders
