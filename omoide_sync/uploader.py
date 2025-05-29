"""Class that handles uploading files to a remote server."""

import os
import shutil
from uuid import UUID

from httpx import BasicAuth
from loguru import logger
from omoide_client.api.info import api_get_myself_v1_info_whoami_get
from omoide_client.api.items import api_create_many_items_v1_items_bulk_post
from omoide_client.api.items import api_get_item_v1_items_item_uuid_get
from omoide_client.api.items import api_get_many_items_v1_items_get
from omoide_client.api.items import (
    api_upload_item_v1_items_item_uuid_upload_put,
)
from omoide_client.models import BodyApiUploadItemV1ItemsItemUuidUploadPut
from omoide_client.types import File
from omoide_client.client import AuthenticatedClient
from omoide_client.models import ItemInput

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

        if not folder:
            return

        item_uuid = self.init_single_folder(parent_uuid, folder)

        if not folder.setup.ephemeral:
            self.upload_single_folder(item_uuid, folder)

        for child in folder.children:
            self.upload(item_uuid, child)

        if folder.setup.after_collection == 'move':
            destination = utils.move(
                data_folder_path=self.config.data_folder,
                archive_folder_path=self.config.archive_folder,
                target_path=folder.path,
            )
            LOG.debug('Moved {} -> {}', folder.path, destination)
        elif folder.setup.after_collection == 'delete':
            LOG.debug('Deleting folder {}', folder.path)
            shutil.rmtree(folder.path)

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
        files_to_upload = folder.files
        if self.config.limit > 0:
            files_left = self.config.limit - self.stats.uploaded_files
            files_to_upload = files_to_upload[:files_left]

        if not files_to_upload:
            return

        create_response = api_create_many_items_v1_items_bulk_post.sync(
            body=[
                ItemInput(
                    parent_uuid=parent_uuid,
                    name=file.name,
                    is_collection=False,
                    tags=folder.setup.tags,
                    permissions=[],  # TODO - what about adding permissions in setup?
                )
                for file in files_to_upload
            ],
            client=self.client,
        )

        if create_response is None:
            msg = (
                f'Failed to create items parent {parent_uuid}, folder {folder}'
            )
            raise exceptions.ItemRelatedError(msg)

        for remote, local in zip(
            create_response.items, files_to_upload, strict=False
        ):
            LOG.debug('Uploading file {} for parent {}', local, parent_uuid)

            with open(local, mode='rb') as fd:
                upload_response = (
                    api_upload_item_v1_items_item_uuid_upload_put.sync(
                        item_uuid=remote.uuid,
                        client=self.client,
                        body=BodyApiUploadItemV1ItemsItemUuidUploadPut(
                            file=File(
                                payload=fd,
                                file_name=local.name,
                                mime_type=get_mime_type(local.suffix.lower()),
                            )
                        ),
                    )
                )

                if upload_response is None:
                    LOG.error('Failed to upload {}', local)
                    continue

                self.stats.uploaded_files += 1
                self.stats.uploaded_bytes += local.stat().st_size

            if folder.setup.after_item == 'move':
                destination = utils.move(
                    data_folder_path=self.config.data_folder,
                    archive_folder_path=self.config.archive_folder,
                    target_path=local,
                )
                LOG.debug('Moved {} -> {}', local, destination)
            elif folder.setup.after_item == 'delete':
                LOG.debug('Deleting file {}', local)
                os.unlink(local)


def get_mime_type(suffix: str) -> str:
    """Return mime type of the file."""
    if suffix in ('.jpg', '.jpeg'):
        return 'image/jpeg'
    elif suffix:
        return f'image/{suffix.strip(".")}'
    return 'image'
