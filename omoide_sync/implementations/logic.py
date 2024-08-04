"""Service logic."""

from loguru import logger as LOG

from omoide_sync import cfg
from omoide_sync import interfaces
from omoide_sync import models


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
        raw_users = self.storage.get_raw_users()

        LOG.info('Got users {}', [user.name for user in raw_users])

        try:
            self.client.start()

            for raw_user in raw_users:
                user = self.client.get_user(raw_user)
                LOG.debug('Working with user {} {}', user.uuid, user.name)
                self.process_single_user(user)
        finally:
            self.client.stop()

    def process_single_user(self, user: models.User) -> None:
        """Upload data for given user."""
        for item in self.storage.get_all_collections(user):
            if not self.client.get_item(item):
                self.create_chain(item)

            LOG.debug('Processing collection {}', item)

            if item.uploaded_enough:
                continue

            if not item.children:
                continue

            paths = self.storage.get_paths(item)
            self.client.upload(item, paths)
            self.storage.prepare_termination(item)

            item.uploaded += len(item.children)
            if item.real_parent:
                item.real_parent.uploaded += item.uploaded + 1

            for sub_item in item.children:
                self.storage.terminate_item(sub_item)

            self.storage.terminate_collection(item)

    def create_chain(self, item: models.Item) -> None:
        """Create whole chain of items."""
        if item.setup.treat_as_collection:
            names: list[str] = [item.owner.name]
            for ancestor in item.ancestors:
                if ancestor.setup.treat_as_collection:
                    if self.client.get_item(ancestor):
                        # already exist
                        names.append(f'{ancestor.name}')
                    else:
                        # newly created
                        names.append(f'!!!{ancestor.name}!!!')
                        with LOG.catch(Exception, reraise=True):
                            self.client.create_item(ancestor)
                else:
                    # not a collection
                    names.append(f'???{ancestor.name}???')

            if not self.client.get_item(item):
                with LOG.catch(Exception, reraise=True):
                    self.client.create_item(item)
                    names.append(f'!!!{item.name}!!!')
                    LOG.info('Created collection {}', ' -> '.join(names))
