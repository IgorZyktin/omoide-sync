"""Global statistics."""

from dataclasses import dataclass

from loguru import logger
import python_utilz as pu

LOG = logger


@dataclass
class Stats:
    """Global statistics."""

    uploaded_files: int = 0
    uploaded_bytes: int = 0

    moved_folders: int = 0
    moved_files: int = 0
    moved_bytes: int = 0

    deleted_folders: int = 0
    deleted_files: int = 0
    deleted_bytes: int = 0

    def __bool__(self) -> bool:
        """Return true if we did something."""
        return bool(
            self.uploaded_files or self.moved_files or self.deleted_files
        )

    def output(self) -> None:
        """Show statistics of uploaded files."""
        if not self:
            return

        if self.uploaded_files:
            LOG.info(
                'Uploaded files: {}, {}',
                pu.sep_digits(self.uploaded_files),
                pu.human_readable_size(self.uploaded_bytes),
            )

        if self.moved_folders:
            LOG.info('Moved folders: {}', pu.sep_digits(self.moved_folders))

        if self.moved_files:
            LOG.info(
                'Moved files: {}, {}',
                pu.sep_digits(self.moved_files),
                pu.human_readable_size(self.moved_bytes),
            )

        if self.deleted_folders:
            LOG.info('Deleted folders: {}', self.deleted_folders)

        if self.deleted_files:
            LOG.info(
                'Deleted files: {}, {}',
                self.deleted_files,
                pu.human_readable_size(self.deleted_bytes),
            )


_STATS: Stats | None = None


def get_stats() -> Stats:
    """Return global statistics singleton."""
    global _STATS
    if _STATS is None:
        _STATS = Stats()
    return _STATS
