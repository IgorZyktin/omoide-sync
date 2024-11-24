"""Entry point."""

from loguru import logger

from omoide_sync import cfg
from omoide_sync import startup

LOG = logger


def main() -> None:
    """Entry point."""
    config = cfg.get_config()
    LOG.add(config.log_file, rotation='1 MB')

    try:
        storage = startup.get_storage_handler(config)
        client = startup.get_client(config)
        logic = startup.get_logic(config, client, storage)
    except Exception:
        msg = 'Failed to initialize application'
        logger.exception(msg)
        raise

    try:
        logic.execute()
    except Exception:
        msg = 'Failed to synchronize'
        LOG.exception(msg)
        raise


if __name__ == '__main__':
    main()
