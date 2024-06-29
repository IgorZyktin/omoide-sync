"""Entry point."""

import logging

from omoide_sync import cfg
from omoide_sync import startup


def main():
    """Entry point."""
    config = cfg.get_config()
    startup.setup_logger(config)
    logger = logging.getLogger(__name__)

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
        logger.exception(msg)
        raise


if __name__ == '__main__':
    main()
