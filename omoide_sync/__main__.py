"""Entry point."""

import sys

from loguru import logger
import python_utilz as pu
import typer

from omoide_sync import cfg
from omoide_sync import exceptions
from omoide_sync import filesystem
from omoide_sync import uploader
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

    for user_folder in folders:
        user_name = user_folder.path.name
        chosen_user: cfg.ConfigUser | None = None
        for user in config.users:
            if user.name == user_name:
                chosen_user = user
                break

        if chosen_user is None:
            LOG.error('Will skip user {}, got no credentials', user_name)
            continue

        user_uploader = uploader.Uploader(
            config=config,
            user=chosen_user,
            folder=user_folder,
            stats=stats,
        )

        try:
            user_uploader.init_client()
            user_uploader.upload()
        except exceptions.OmoideSyncError:
            LOG.exception('Failed to sync {}', user_folder.path.name)
            continue

    stats.output()


if __name__ == '__main__':
    app()
