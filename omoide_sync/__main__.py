"""Entry point."""

import typer
from httpx import BasicAuth
from loguru import logger
from omoide_client import AuthenticatedClient

from omoide_sync import cfg
from omoide_sync import const
from omoide_sync import exceptions
from omoide_sync import models

LOG = logger
app = typer.Typer()


@app.command()
def sync(config_file: str, *, dry_run: bool = False) -> None:
    """Synchronize all."""
    config = cfg.get_config(config_file=config_file, dry_run=dry_run)
    LOG.add(config.log_path, rotation='1 MB')
    LOG.info('Will synchronize contents of {}', config.root_path.absolute())

    root = models.Root(config)
    root.sync()


def main() -> None:
    """Entry point."""
    config = cfg.get_config()

    for user in root.users:
        try:
            sync_one_user(config, user)
        except exceptions.UserRelatedError:
            msg = f'Failed to synchronize user {user.login}'
            LOG.exception(msg)
            continue


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
    user.sync()

    # for collection in user.get_collections():
    #     collection.upload()


if __name__ == '__main__':
    app()
