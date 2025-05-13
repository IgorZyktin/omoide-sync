"""Entry point."""

import sys

from loguru import logger
import typer

from omoide_sync import cfg
from omoide_sync import filesystem
from omoide_sync import stats as global_stats

LOG = logger
app = typer.Typer()


@app.command()
def sync(
    dry_run: bool | None = None,  # noqa: FBT001
    limit: int | None = None,
) -> None:
    """Synchronize local storage with API."""
    config = cfg.get_config(dry_run=dry_run, limit=limit)
    stats = global_stats.get_stats()

    LOG.add(
        config.log_path,
        level=config.log_level,
        rotation=config.log_rotation,
    )

    if not config.users:
        LOG.info('No users to sync')
        sys.exit(1)

    LOG.info('Synchronizing {}', config.data_folder.absolute())

    folders = filesystem.scan_folders(config.data_folder.absolute())

    if config.show_folder_structure:
        LOG.info('Got structure:')
        for folder in folders:
            folder.output()

    if config.dry_run:
        return

    # TODO - upload

    stats.output()


if __name__ == '__main__':
    app()
