"""Code that prepares application for run.
"""
import logging

from omoide_sync import cfg
from omoide_sync import const
from omoide_sync import implementations
from omoide_sync import interfaces


def setup_logger(config: cfg.Config) -> None:
    """Apply logging settings."""
    log_file_path = config.root_folder / const.LOG_FILENAME
    logging.basicConfig(
        encoding='utf-8',
        level=logging.getLevelName(config.log_level.upper()),
        format='%(asctime)s - %(levelname)7s - %(name)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file_path, encoding='utf-8'),
            logging.StreamHandler()
        ],
    )


def get_client(
    config: cfg.Config,
    storage: interfaces.AbsStorage,
) -> interfaces.AbsClient:
    """Return working API client instance."""
    return implementations.SeleniumClient(
        config=config,
        storage=storage,
    )


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
