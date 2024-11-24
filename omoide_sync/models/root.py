"""Root folder abstraction."""
from omoide_sync import cfg


class Root:

    def __init__(self, config: cfg.Config):
        """Initialize instance."""
        self.config = config
