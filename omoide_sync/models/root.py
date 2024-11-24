"""Root folder abstraction."""

from loguru import logger

from omoide_sync import cfg
from omoide_sync import utils
from omoide_sync import models

LOG = logger


class Root:
    def __init__(self, config: cfg.Config):
        """Initialize instance."""
        self.config = config
        self.users: list[models.User] = []

    def sync(self) -> None:
        """Synchronize root with filesystem."""
        for each in self.config.root_path.iterdir():
            if each.is_file():
                continue

            uuid, name = utils.split_name(each, self.config.spacer)

            for raw_user in self.config.users:
                if raw_user.name == name:
                    new_user = models.User(
                        uuid=uuid,
                        name=name,
                        login=raw_user.login,
                        password=raw_user.password,
                    )
                    self.users.append(new_user)
                    break
            else:
                LOG.warning('There are no credentials for user named {}, skipping', name)
