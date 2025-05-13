"""Entry point."""

import sys

from loguru import logger
import typer

from omoide_sync import cfg
from omoide_sync import global_stats

LOG = logger
app = typer.Typer()


@app.command()
def sync(dry_run: bool | None = None) -> None:  # noqa: FBT001
    """Synchronize local storage with API."""
    config = cfg.get_config(dry_run=dry_run)
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

    # TODO - scan folders

    if config.dry_run:
        return

    # TODO - upload

    stats.output()


if __name__ == '__main__':
    app()
