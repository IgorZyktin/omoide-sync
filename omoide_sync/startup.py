"""Code that prepares application for run."""

from omoide_sync import cfg
from omoide_sync import implementations
from omoide_sync import interfaces


def get_client(config: cfg.Config) -> interfaces.AbsClient:
    """Return working API client instance."""
    return implementations.SeleniumClient(config=config)


def get_storage_handler(config: cfg.Config) -> interfaces.AbsStorage:
    """Return working storage handler instance."""
    return implementations.FileStorage(config=config)


def get_logic(
    config: cfg.Config,
    client: interfaces.AbsClient,
    storage: interfaces.AbsStorage,
) -> interfaces.AbsLogic:
    """Return working service logic instance."""
    return implementations.Logic(
        config=config,
        client=client,
        storage=storage,
    )
