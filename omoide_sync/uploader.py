"""Class that handles uploading files to a remote server."""

from uuid import UUID

from httpx import BasicAuth
from loguru import logger
from omoide_client.api.info import api_get_myself_v1_info_whoami_get
from omoide_client.api.items import api_get_item_v1_items_item_uuid_get
from omoide_client.api.items import api_get_many_items_v1_items_get
from omoide_client.client import AuthenticatedClient

from omoide_sync import cfg
from omoide_sync import exceptions
from omoide_sync import filesystem
from omoide_sync import stats as global_stats
from omoide_sync import utils
from omoide_sync.filesystem import Folder

LOG = logger


class Uploader:
    """Class that handles uploading files to a remote server."""

    def __init__(
        self,
        config: cfg.Config,
        user: cfg.ConfigUser,
        folder: filesystem.Folder,
        stats: global_stats.Stats,
    ) -> None:
        """Initialize instance."""
        self.config = config
        self.user = user
        self.folder = folder
        self.stats = stats
        self._client = None
        self._api_user_uuid: UUID | None = None

    @property
    def client(self) -> AuthenticatedClient:
        """Return client instance."""
        if self._client is None:
            msg = 'Client is not yet initialized'
            raise exceptions.ConfigRelatedError(msg)
        return self._client

    @property
    def api_user_uuid(self) -> UUID:
        """Return UUID of the owner."""
        me_response = api_get_myself_v1_info_whoami_get.sync(
            client=self.client
        )

        if me_response is None:
            msg = 'Failed to perform request to get user'
            raise exceptions.NetworkRelatedError(msg)

        if (remote_uuid := me_response.uuid) is None:
            msg = f'{self.user.name} is not authorized'
            raise exceptions.ConfigRelatedError(msg)

        return UUID(remote_uuid)

    def init_client(self) -> None:
        """Initialize API client."""
        self._client = AuthenticatedClient(
            base_url=self.config.api_url,
            httpx_args={
                'auth': BasicAuth(
                    username=self.user.login,
                    password=self.user.password,
                ),
            },
            token='',
        )

    def upload(
        self, parent_uuid: UUID | None = None, folder: Folder | None = None
    ) -> None:
        """Upload our folder and all of its children."""
        if folder is None:
            folder = self.folder

        item_uuid = self.init_single_folder(parent_uuid, folder)

        if not folder.setup.ephemeral:
            self.upload_single_folder(item_uuid, folder)

        for child in folder.children:
            self.upload(item_uuid, child)

    def init_single_folder(
        self, parent_uuid: UUID | None, folder: Folder
    ) -> UUID:
        """Upload given folder."""
        LOG.info('Uploading {}', folder)
        item_uuid, name = utils.get_uuid_and_name(folder.path)

        if item_uuid is None:
            response = api_get_many_items_v1_items_get.sync(
                owner_uuid=self.api_user_uuid,
                parent_uuid=parent_uuid,
                name=name,
                client=self.client,
            )

            if not response:
                exists = False
            elif len(response.items) > 1:
                msg = f'Got more than one item for name {name}'
                raise exceptions.ConfigRelatedError(msg)
            elif response.items:
                exists = True
                item_uuid = response.items[0].uuid
            else:
                exists = False

        else:
            response = api_get_item_v1_items_item_uuid_get.sync(
                item_uuid=item_uuid,
                client=self.client,
            )
            if response is None:
                exists = False
            else:
                exists = True
                item_uuid = response.item.uuid

        if not exists and folder.setup.no_collection == 'raise':
            msg = f'Item {item_uuid} does not exist'
            raise exceptions.ConfigRelatedError(msg)
        elif not exists:
            LOG.info('Creating collection {} is {}', name, item_uuid)
            # TODO - create item

        LOG.info('Target item for {} is {}', name, item_uuid)
        return item_uuid

    def upload_single_folder(self, parent_uuid: UUID, folder: Folder) -> None:
        """Upload all files in given folder."""
        for file in folder.files:
            LOG.debug('Uploading file {} for parent {}', file, parent_uuid)
            # TODO - actually upload
            # TODO - move after upload
