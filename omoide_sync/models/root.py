"""Root folder abstraction."""
from omoide_sync import cfg
from omoide_sync.models.models import User


class Root:

    def __init__(self, config: cfg.Config):
        """Initialize instance."""
        self.config = config
        self.users: list[User] = []

    def sync(self) -> None:
        """Synchronize root with filesystem."""
