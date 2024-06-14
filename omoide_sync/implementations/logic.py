"""Service logic.
"""
import logging

from omoide_sync import cfg
from omoide_sync import interfaces
from omoide_sync import models

LOG = logging.getLogger(__name__)


class Logic(interfaces.AbsLogic):
    """Service logic."""

    def __init__(
        self,
        config: cfg.Config,
        client: interfaces.AbsClient,
        storage: interfaces.AbsStorage,
    ) -> None:
        """Initialize instance."""
        self.config = config
        self.client = client
        self.storage = storage

    def execute(self) -> None:
        """Start processing."""
        users = self.storage.get_users()

        try:
            self.client.start()

            for user in users:
                LOG.debug('Working with user %s', user.name)
                self.process_single_user(user)
        finally:
            self.client.stop()

    def process_single_user(self, user: models.User) -> None:
        """Upload data for given user."""
        for item in self.storage.get_all_collections(user):
            LOG.debug('Processing collection %s', item)

            if item.uploaded_enough:
                continue

            if not self.client.get_item(item):
                self.create_chain(item)

            paths = self.storage.get_paths(item)
            self.client.upload(item, paths)
            self.storage.prepare_termination(item)

            for sub_item in item.children:
                self.storage.terminate_item(sub_item)

            if item.real_parent:
                item.real_parent.uploaded += 1

            self.storage.terminate_collection(item)

    def create_chain(self, item: models.Item) -> None:
        """Create whole chain of items."""
        if item.setup.treat_as_collection:
            names: list[str] = [item.owner.name]
            for ancestor in item.ancestors:
                if ancestor.setup.treat_as_collection:
                    names.append(ancestor.name)
                    if not self.client.get_item(ancestor):
                        self.client.create_item(ancestor)
                else:
                    names.append(f'!{ancestor.name}!')

            names.append(item.name)

            LOG.info(
                'Created collection %s %s',
                ' -> '.join(names),
                item.setup.tags,
            )

            self.client.create_item(item)
