"""Entry point."""

from httpx import BasicAuth
from loguru import logger
from omoide_client.client import AuthenticatedClient
import typer

from omoide_sync import cfg
from omoide_sync import exceptions
from omoide_sync import models

LOG = logger
app = typer.Typer()


@app.command()
def sync(config_file: str, *, dry_run: bool = False) -> None:
    """Synchronize local storage with API."""
    config = cfg.get_config(config_file=config_file, dry_run=dry_run)

    LOG.add(config.log_path, level=config.log_level, rotation='1 MB')
    LOG.info('Synchronizing {}', config.source_path.absolute())

    source = models.Source(config, setup=models.Setup(**config.raw_setup))
    source.init()

    try:
        for user in source.users:
            try:
                sync_one_user(config, user)
            except exceptions.UserRelatedError:
                msg = f'Failed to synchronize user {user.login}'
                LOG.exception(msg)
    except KeyboardInterrupt:
        LOG.warning('Stopped manually')
    else:
        LOG.info('Done synchronizing')

    global_stats = models.Stats()
    for user in source.users:
        global_stats += user.stats

    if not global_stats.uploaded_files:
        LOG.info('Uploaded nothing')
        return

    LOG.info('Uploaded files: {}, {} MiB', global_stats.uploaded_files, global_stats.uploaded_mib)

    if global_stats.deleted_files or global_stats.deleted_folders:
        LOG.info('Deleted folders: {}', global_stats.deleted_folders)
        LOG.info('Deleted files: {}, {} MiB', global_stats.deleted_files, global_stats.deleted_mib)

    if global_stats.moved_files or global_stats.moved_folders:
        LOG.info('Moved folders: {}', global_stats.moved_folders)
        LOG.info('Moved files: {}, {} MiB', global_stats.moved_files, global_stats.moved_mib)


def sync_one_user(config: cfg.Config, user: models.User) -> None:
    """Synchronize all items for specific user."""
    client = AuthenticatedClient(
        base_url=config.api_url,
        httpx_args={
            'auth': BasicAuth(username=user.login, password=user.password),
        },
        token='',
    )
    user.client = client
    user.init()

    LOG.info('Synchronizing user {} {}', user.uuid, user.name)

    user.root_item.init()
    user.root_item.upload()


if __name__ == '__main__':
    app()
