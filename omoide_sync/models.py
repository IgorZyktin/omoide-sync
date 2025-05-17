"""Project models."""

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
import shutil
from typing import Literal
from typing import Optional
from typing import Union
from uuid import UUID

from loguru import logger
from omoide_client.api.info import api_get_myself_v1_info_whoami_get
from omoide_client.api.items import api_create_item_v1_items_post
from omoide_client.api.items import api_create_many_items_v1_items_bulk_post
from omoide_client.api.items import api_get_item_v1_items_item_uuid_get
from omoide_client.api.items import api_get_many_items_v1_items_get
from omoide_client.api.users import api_get_all_users_v1_users_get
from omoide_client.client import AuthenticatedClient
from omoide_client.models import ItemInput
import yaml

from omoide_sync import exceptions
from omoide_sync import utils

LOG = logger


@dataclass
class Setup:
    """Personal settings for collection."""

    no_collection: Literal['create', 'raise'] = 'raise'
    after_collection: Literal['move', 'delete', 'nothing'] = 'move'
    after_item: Literal['move', 'delete', 'nothing'] = 'move'
    ephemeral: bool = False
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_path(
        cls,
        path: Path,
        filename: str,
        parent_setup: Union['Setup', None] = None,
    ) -> 'Setup':
        """Create instance from given folder."""
        if parent_setup is None:
            setup = {}
        else:
            setup = asdict(parent_setup)

        try:
            with open(path / filename, encoding='utf-8') as fd:
                raw_setup = yaml.safe_load(fd)
        except FileNotFoundError:
            raw_setup = {}

        parent_tags = setup.pop('tags', [])
        raw_tags = raw_setup.pop('tags', [])
        setup.update(raw_setup)

        return cls(**setup, tags=list(set(parent_tags + raw_tags)))


CREATE = 'create'
RAISE = 'raise'
MOVE = 'move'
DELETE = 'delete'
NOTHING = 'nothing'


class Collection:
    """Folder abstraction."""

    def __init__(  # noqa: PLR0913
        self,
        uuid: UUID | None,
        owner: 'User',
        name: str,
        parent: Optional['Collection'],
        children: list['Collection'],
        path: Path,
        setup: 'Setup',
    ) -> None:
        """Initialize instance."""
        self.owner = owner
        self.name = name
        self.parent = parent
        self.children = children
        self.path = path
        self.setup = setup

        self._uuid = uuid
        self._initial_uuid = uuid
        self.uploaded = 0
        self.children_uploaded = 0

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f'<Item uuid={self._uuid}, {self.name}, '
            f'children={len(self.children)}, parent={self.parent}>'
        )

    def __str__(self) -> str:
        """Return string representation."""
        return f'<Item uuid={self.uuid}, {self.name}>'

    def increment_upload(self, value: int) -> None:
        """Increment upload value for us and our parent."""
        self.children_uploaded += value

        if self.parent is not None:
            self.parent.increment_upload(value)

    @property
    def uuid(self) -> UUID:
        """Return user UUID."""
        if self._uuid is None:
            msg = f'UUID for item {self.name} is not set yet'
            raise exceptions.ItemRelatedError(msg)
        return self._uuid

    @uuid.setter
    def uuid(self, new_uuid: str | UUID) -> None:
        """Set UUID."""
        if isinstance(new_uuid, str):
            new_uuid = UUID(new_uuid)
        self._uuid = new_uuid

    def _find_ourself_by_name_or_create(self) -> tuple[UUID, str]:
        """Find item by name and parent info."""
        if self.parent is None:
            msg = f'Cannot create root item {self.name!r}'
            raise exceptions.ItemRelatedError(msg)

        get_response = api_get_many_items_v1_items_get.sync(
            owner_uuid=self.owner.uuid,
            parent_uuid=self.parent.uuid,
            name=self.name,
            client=self.owner.client,
        )

        if get_response is None:
            msg = (
                f'Failed to get children of {self.parent.uuid} '
                f'with name {self.name!r}'
            )
            raise exceptions.ItemRelatedError(msg)

        if len(get_response.items) > 1:
            msg = (
                f'Got more than one child of {self.parent} '
                f'named {self.name!r}, '
                'you should explicitly specify UUID in folder name'
            )
            raise exceptions.ItemRelatedError(msg)

        if get_response.items:
            uuid = get_response.items[0].uuid
            name = get_response.items[0].name

        elif self.setup.init_collection == CREATE:
            if self.owner.source.config.dry_run:
                LOG.info(
                    'Will create child of {} with name {}',
                    self.parent,
                    self.name,
                )
                uuid = UUID('00000000-0000-0000-0000-000000000000')
                name = self.name
            else:
                LOG.info(
                    'Creating child of {} with name {}',
                    self.parent.uuid,
                    self.name,
                )
                create_response = api_create_item_v1_items_post.sync(
                    body=ItemInput(
                        parent_uuid=self.parent.uuid,
                        name=self.name,
                        is_collection=True,
                        tags=self.setup.tags,
                        permissions=[],
                    ),
                    client=self.owner.client,
                )

                if create_response is None:
                    msg = (
                        f'Failed to create child of {self.parent.uuid} '
                        f'with name {self.name!r}'
                    )
                    raise exceptions.ItemRelatedError(msg)

                uuid = create_response.item.uuid
                name = create_response.item.name

        else:
            msg = (
                f'Cannot find item by name {self.name!r} '
                f'and parent {self.parent.uuid}'
            )
            raise exceptions.ItemRelatedError(msg)

        return uuid, name

    def init(self) -> None:
        """Synchronize collection with API."""
        if self._uuid is not None:
            response = api_get_item_v1_items_item_uuid_get.sync(
                item_uuid=self.uuid,
                client=self.owner.client,
            )

            if response is None:
                msg = f'Item with UUID {self._uuid} does not exist'
                raise exceptions.ItemRelatedError(msg)

            remote_name = response.item.name
        else:
            remote_uuid, remote_name = self._find_ourself_by_name_or_create()
            self.uuid = remote_uuid

        if remote_name != self.name:
            msg = (
                f'Conflicting name for item, '
                f'folder says {self.name}, '
                f'but service says {remote_name}'
            )
            raise exceptions.ItemRelatedError(msg)

        LOG.debug('Got initial info on item {} {}', self.uuid, self.name)
        self.init_children()

    def init_children(self) -> None:
        """Read all underlying folders."""
        for each in self.path.iterdir():
            if each.is_file():
                continue

            if each.name.startswith(self.owner.source.config.skip_prefixes):
                LOG.warning('Skipping {}', each.name)
                continue

            uuid, name = utils.get_uuid_and_name(each)

            new_item = Collection(
                uuid=uuid,
                owner=self.owner,
                name=name,
                parent=self,
                children=[],
                path=each,
                setup=Setup.from_path(
                    each, self.owner.source.config.setup_filename, self.setup
                ),
            )

            self.children.append(new_item)

            new_item.init()

    def upload(self) -> None:
        """Upload content to API."""
        self._do_upload()

        for item in self.children:
            try:
                item.upload()
            except exceptions.ItemRelatedError:
                msg = (
                    f'Failed to synchronize item uuid={item.uuid}, {item.name}'
                )
                LOG.exception(msg)

        if self.setup.final_collection == MOVE:
            if self.owner.source.config.dry_run:
                LOG.info('Will move folder: {}', self.path.absolute())
            else:
                LOG.info('Moving folder: {}', self.path.absolute())

            self.owner.stats.moved_folders += 1
            if not self.owner.source.config.dry_run:
                utils.move(
                    source_path=self.owner.source.config.source_path,
                    archive_path=self.owner.source.config.archive_path,
                    target_path=self.path,
                )

        elif self.setup.final_collection == DELETE:
            if self.owner.source.config.dry_run:
                LOG.warning('Will delete folder: {}', self.path.absolute())
            else:
                LOG.warning('Deleting folder: {}', self.path.absolute())

            self.owner.stats.deleted_folders += 1
            if not self.owner.source.config.dry_run:
                shutil.rmtree(self.path)

    def _do_upload(self) -> None:  # noqa: PLR0912,C901
        """Upload content to API."""
        local_files = [
            file
            for file in self.path.iterdir()
            if all(
                (
                    file.is_file(),
                    file.name.endswith(
                        self.owner.source.config.supported_formats
                    ),
                    not file.name.startswith(
                        self.owner.source.config.skip_prefixes
                    ),
                )
            )
        ]

        if self.setup.limit != -1 and self.setup.limit < len(local_files):
            threshold = self.setup.limit + 1
            head = local_files[:threshold]
            tail = local_files[threshold:]
            local_files = head
            LOG.debug('Collection limit stops from uploading {}', tail)

        total_uploaded = self.owner.root_item.children_uploaded

        if self.setup.global_limit != -1 and self.setup.global_limit < (
            len(local_files) + total_uploaded
        ):
            threshold = self.setup.global_limit - total_uploaded

            if threshold <= 0:
                return

            head = local_files[:threshold]
            tail = local_files[threshold:]
            local_files = head
            LOG.debug('Global limit stops from uploading {}', tail)

        if not local_files:
            return

        if self.owner.source.config.dry_run:
            LOG.info('Will upload {} {}', self.uuid, self.name)
        else:
            LOG.info('Uploading {} {}', self.uuid, self.name)

        self.uploaded += len(local_files)
        self.increment_upload(len(local_files))

        if not self.owner.source.config.dry_run:
            self._do_upload_files(local_files)

        for file in local_files:
            self.owner.stats.uploaded_files += 1
            self.owner.stats.uploaded_bytes += file.stat().st_size

        if self.setup.final_item == MOVE:
            if self.owner.source.config.dry_run:
                LOG.info('Will move files: {}', [str(x) for x in local_files])
            else:
                LOG.info('Moving files: {}', [str(x) for x in local_files])

            for file in local_files:
                self.owner.stats.moved_files += 1
                self.owner.stats.moved_bytes += file.stat().st_size
                if not self.owner.source.config.dry_run:
                    utils.move(
                        source_path=self.owner.source.config.source_path,
                        archive_path=self.owner.source.config.archive_path,
                        target_path=file,
                    )

        elif self.setup.final_item == DELETE:
            if self.owner.source.config.dry_run:
                LOG.warning(
                    'Will delete files: {}', [str(x) for x in local_files]
                )
            else:
                LOG.warning(
                    'Deleting files: {}', [str(x) for x in local_files]
                )

            for file in local_files:
                self.owner.stats.deleted_files += 1
                self.owner.stats.deleted_bytes += file.stat().st_size
                if not self.owner.source.config.dry_run:
                    file.unlink()

    def _do_upload_files(self, files: list[Path]) -> None:
        """Create new items and upload content for them."""
        create_response = api_create_many_items_v1_items_bulk_post.sync(
            body=[
                ItemInput(
                    parent_uuid=self.uuid,
                    name='',
                    is_collection=False,
                    tags=self.setup.tags,
                    permissions=[],
                    # TODO - what about adding permissions in setup?
                )
                for _ in files
            ],
            client=self.owner.client,
        )

        if create_response is None:
            msg = f'Failed to upload files for {self}'
            raise exceptions.ItemRelatedError(msg)

        for remote, local in zip(create_response.items, files, strict=False):
            # TODO - save original filename
            # TODO - upload content
            _ = remote
            _ = local


class User:
    """User abstraction."""

    def __init__(  # noqa: PLR0913
        self,
        source,
        uuid: UUID | str | None,
        name: str,
        login: str,
        password: str,
        path: Path,
        setup: 'Setup',
    ) -> None:
        """Initialize instance."""
        self.source = source
        self.name = name
        self.login = login
        self.password = password
        self.path = path
        self.setup = setup

        self.collections: list[Collection] = []

        self._initial_uuid = uuid
        self._uuid: UUID | None = None
        self._root_item_uuid: UUID | None = None
        self._root_item: Collection | None = None
        self._client = None

    def __repr__(self) -> str:
        """Return string representation."""
        return f'<User uuid={self._uuid}, {self.name}>'

    @property
    def client(self) -> AuthenticatedClient:
        """Return current client."""
        if self._client is None:
            msg = f'Client for user {self.login} is not set yet'
            raise exceptions.UserRelatedError(msg)
        return self._client

    @client.setter
    def client(self, new_client: AuthenticatedClient) -> None:
        """Set current client."""
        self._client = new_client

    @property
    def uuid(self) -> UUID:
        """Return user UUID."""
        if self._uuid is None:
            msg = f'UUID for user {self.login} is not set yet'
            raise exceptions.UserRelatedError(msg)
        return self._uuid

    @uuid.setter
    def uuid(self, new_uuid: str | UUID) -> None:
        """Set UUID."""
        if isinstance(new_uuid, str):
            new_uuid = UUID(new_uuid)
        self._uuid = new_uuid

    @property
    def root_item_uuid(self) -> UUID:
        """Return root item UUID."""
        if self._root_item_uuid is None:
            msg = f'Root item UUID for user {self.login} is not set yet'
            raise exceptions.UserRelatedError(msg)
        return self._root_item_uuid

    @root_item_uuid.setter
    def root_item_uuid(self, new_uuid: str | UUID) -> None:
        """Set UUID."""
        if isinstance(new_uuid, str):
            new_uuid = UUID(new_uuid)
        self._root_item_uuid = new_uuid

    @property
    def root_item(self) -> Collection:
        """Return root item."""
        if self._root_item is None:
            msg = f'Root item for user {self.login} is not set yet'
            raise exceptions.UserRelatedError(msg)
        return self._root_item

    @root_item.setter
    def root_item(self, new_item: Collection) -> None:
        """Set UUID."""
        self._root_item = new_item

    def init(self) -> None:
        """Synchronize user with API."""
        me_response = api_get_myself_v1_info_whoami_get.sync(
            client=self.client
        )

        if (remote_uuid := me_response.uuid) is None:
            msg = f'{self} is not authorized'
            raise RuntimeError(msg)

        if self._initial_uuid is not None and str(self._initial_uuid) != str(
            remote_uuid
        ):
            msg = (
                f'Conflicting UUIDs for {self.login}, '
                f'folder says {self._initial_uuid}, '
                f'but service says {remote_uuid}'
            )
            raise exceptions.UserRelatedError(msg)

        if (remote_name := me_response.name) != self.name:
            msg = (
                f'Conflicting name for {self.login}, '
                f'folder says {self.name}, '
                f'but service says {remote_name}'
            )
            raise exceptions.UserRelatedError(msg)

        self.uuid = remote_uuid

        all_users = api_get_all_users_v1_users_get.sync(client=self.client)

        if all_users is None:
            msg = 'Failed to get users'
            raise RuntimeError(msg)

        for user in all_users.users:
            if UUID(user.uuid) == self.uuid:
                self.root_item_uuid = UUID(user.extras['root_item_uuid'])
                break
        else:
            msg = (
                f'Failed to find {self.login} '
                f'among other {len(all_users.users)} users'
            )
            raise exceptions.UserRelatedError(msg)

        LOG.debug('Got initial info on user {} {}', self.uuid, self.name)

        self.root_item = Collection(
            uuid=self.root_item_uuid,
            owner=self,
            name=self.name,
            parent=None,
            children=[],
            setup=self.setup,
            path=self.path,
        )
