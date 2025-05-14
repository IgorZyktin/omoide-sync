"""Filesystem related code."""

from dataclasses import dataclass
from dataclasses import field
import os
from pathlib import Path

from colorama import Fore
from loguru import logger
import python_utilz as pu

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

    def __bool__(self) -> bool:
        """Return true if we have something to upload."""
        return any((self.files, any(bool(child) for child in self.children)))

    def __len__(self) -> int:
        """Return our files + our children's files."""
        return len(self.files) + sum(len(child) for child in self.children)

    def output(self, depth: int = 0) -> None:
        """Show folder contents."""
        if not self:
            return

        prefix = '\t' * depth

        if self.files:
            files = f'{Fore.RED}{len(self.files)}{Fore.RESET}'
        else:
            files = '0'

        if files != '0':
            ending = f' (files={pu.sep_digits(files)})'
        else:
            ending = ''

        if depth:
            name = Fore.GREEN + self.path.name + Fore.RESET
        else:
            name = Fore.CYAN + self.path.name + Fore.RESET

        LOG.info(f'{prefix}{name}{ending}')

        for child in self.children:
            child.output(depth + 1)


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
