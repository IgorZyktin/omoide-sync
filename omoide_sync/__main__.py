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
def sync(config_file: str, dry_run: bool = False) -> None:
    """Synchronize local storage with API."""
    config = cfg.get_config(config_file=config_file, dry_run=dry_run)

    LOG.add(config.log_path, rotation='1 MB')
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

    try:
        user.root_item.init()
        user.root_item.upload()
    except exceptions.ItemRelatedError as exc:
        msg = f'Failed to synchronize collection: {exc}'
        LOG.error(msg)


if __name__ == '__main__':
    app()
