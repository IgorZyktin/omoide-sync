"""Entry point."""

import sys

from loguru import logger
import python_utilz as pu
import typer

from omoide_sync import cfg
from omoide_sync import filesystem
from omoide_sync import stats as global_stats

LOG = logger
app = typer.Typer()


@app.command()
def sync() -> None:
    """Synchronize local storage with API."""
    config = cfg.get_config()
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

    total = sum(len(folder) for folder in folders)
    if config.show_folder_structure and total:
        LOG.info('Got structure with {} files:', pu.sep_digits(total))
        for folder in folders:
            folder.output()

    if config.dry_run:
        return

    # TODO - upload

    stats.output()


if __name__ == '__main__':
    app()
