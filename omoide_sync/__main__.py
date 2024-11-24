"""Entry point."""

from httpx import BasicAuth
from loguru import logger
from omoide_client import AuthenticatedClient

from omoide_sync import cfg
from omoide_sync import exceptions
from omoide_sync import models

LOG = logger


def main() -> None:
    """Entry point."""
    config = cfg.get_config()
    LOG.add(config.log_file, rotation='1 MB')

    root = models.Root(config)
    root.sync()

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
    main()
