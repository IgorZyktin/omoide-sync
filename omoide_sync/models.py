"""Project models."""

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
import shutil
from typing import Any
from typing import Literal
from typing import Optional
from typing import Self
from uuid import UUID

from loguru import logger
from omoide_client.api.info import api_get_myself_v1_info_whoami_get
from omoide_client.api.items import api_get_item_v1_items_item_uuid_get
from omoide_client.api.items import api_get_many_items_v1_items_get
from omoide_client.api.users import api_get_all_users_v1_users_get
from omoide_client.client import AuthenticatedClient
import yaml

from omoide_sync import cfg
from omoide_sync import exceptions
from omoide_sync import utils

LOG = logger

MOVE = 'move'
DELETE = 'delete'
NOTHING = 'nothing'


@dataclass
class Stats:
    """Global statistic."""

    uploaded_files: int = 0
    uploaded_bytes: int = 0

    moved_files: int = 0
    moved_bytes: int = 0
    moved_folders: int = 0

    deleted_files: int = 0
    deleted_bytes: int = 0
    deleted_folders: int = 0

    @property
    def uploaded_mib(self) -> str:
        """Return human-readable uploaded size."""
        return f'{self.uploaded_bytes / 1024 / 1024:0.2f}'

    @property
    def moved_mib(self) -> str:
        """Return human-readable moved size."""
        return f'{self.moved_bytes / 1024 / 1024:0.2f}'

    @property
    def deleted_mib(self) -> str:
        """Return human-readable deleted size."""
        return f'{self.deleted_bytes / 1024 / 1024:0.2f}'

    def __add__(self, other: 'Stats') -> 'Stats':
        """Summarize two stats."""
        return Stats(
            uploaded_files=self.uploaded_files + other.uploaded_files,
            uploaded_bytes=self.uploaded_bytes + other.uploaded_bytes,
            moved_files=self.moved_files + other.moved_files,
            moved_bytes=self.moved_bytes + other.moved_bytes,
            moved_folders=self.moved_folders + other.moved_folders,
            deleted_files=self.deleted_files + other.deleted_files,
            deleted_bytes=self.deleted_bytes + other.deleted_bytes,
            deleted_folders=self.deleted_folders + other.deleted_folders,
        )


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

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f'<Item uuid={self._uuid}, {self.name}, '
            f'children={len(self.children)}, parent={self.parent.name}>'
        )

    def __str__(self) -> str:
        """Return string representation."""
        return f'<Item uuid={self.uuid}, {self.name}>'

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

    def _find_ourself_by_name(self) -> tuple[UUID, str]:
        """Find item by name and parent info."""
        response = api_get_many_items_v1_items_get.sync(
            owner_uuid=self.owner.uuid,
            parent_uuid=self.parent.uuid,
            name=self.name,
            client=self.owner.client,
        )

        if not response.items:
            msg = f'Cannot find item by name {self.name!r} and parent {self.parent.uuid}'
            raise exceptions.ItemRelatedError(msg)

        if len(response.items) > 1:
            msg = (
                f'Got more than one child of {self.parent} named {self.name!r}, '
                'you should explicitly specify UUID in folder name'
            )
            raise exceptions.ItemRelatedError(msg)

        return response.items[0].uuid, response.items[0].name

    def init(self) -> None:
        """Synchronize collection with API."""
        # TODO - what if item does not exist yet?
        if self._uuid is not None:
            response = api_get_item_v1_items_item_uuid_get.sync(
                item_uuid=self.uuid,
                client=self.owner.client,
            )
            remote_name = response.item.name
        else:
            remote_uuid, remote_name = self._find_ourself_by_name()
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

            uuid, name = utils.get_uuid_and_name(each)

            new_item = Collection(
                uuid=uuid,
                owner=self.owner,
                name=name,
                parent=self,
                children=[],
                path=each,
                setup=self.setup,
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
                msg = f'Failed to synchronize item uuid={item.uuid}, {item.name}'
                LOG.exception(msg)

        if self.setup.final_collection == MOVE:
            if self.owner.source.config.dry_run:
                LOG.info('Will move folder: {}', self.path.absolute())
            else:
                LOG.info('Moving folder: {}', self.path.absolute())

            self.owner.stats.moved_folders += 1
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

    def _do_upload(self) -> None:
        """Upload content to API."""
        local_files = [
            file
            for file in self.path.iterdir()
            if all(
                (
                    file.is_file(),
                    file.name.endswith(self.owner.source.config.supported_formats),
                    not file.name.startswith(self.owner.source.config.skip_prefixes),
                )
            )
        ]

        if not local_files:
            return

        if self.owner.source.config.dry_run:
            LOG.info('Will upload {} {}', self.uuid, self.name)
        else:
            LOG.info('Uploading {} {}', self.uuid, self.name)

        # TODO - actually upload
        for file in local_files:
            self.owner.stats.uploaded_files += 1
            self.owner.stats.uploaded_bytes += file.stat().st_size

        # TODO - consider limits

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
                LOG.warning('Will delete files: {}', [str(x) for x in local_files])
            else:
                LOG.warning('Deleting files: {}', [str(x) for x in local_files])

            for file in local_files:
                self.owner.stats.deleted_files += 1
                self.owner.stats.deleted_bytes += file.stat().st_size
                if not self.owner.source.config.dry_run:
                    file.unlink()


class User:
    """User abstraction."""

    def __init__(  # noqa: PLR0913
        self,
        source: 'Source',
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
        self.stats = Stats()

        self.collections: list[Collection] = []

        self._initial_uuid = uuid
        self._uuid = None
        self._root_item_uuid = None
        self._root_item = None
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
        me_response = api_get_myself_v1_info_whoami_get.sync(client=self.client)

        if (remote_uuid := me_response.uuid) is None:
            msg = f'{self} is not authorized'
            raise RuntimeError(msg)

        if self._initial_uuid is not None and str(self._initial_uuid) != str(remote_uuid):
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
            msg = f'Failed to find {self.login} among other {len(all_users.users)} users'
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


class Source:
    """Source folder abstraction."""

    def __init__(self, config: cfg.Config, setup: 'Setup'):
        """Initialize instance."""
        self.config = config
        self.setup = setup
        self.users: list[User] = []

    def init(self) -> None:
        """Synchronize root with filesystem."""
        LOG.debug('Initializing source: {}', self.config.source_path)

        for each in self.config.source_path.iterdir():
            if each.is_file():
                continue

            setup = Setup.from_path(each, self.config.setup_filename)
            uuid, name = utils.get_uuid_and_name(each)

            for raw_user in self.config.users:
                if raw_user.name == name:
                    new_user = User(
                        source=self,
                        uuid=uuid,
                        name=name,
                        login=raw_user.login,
                        password=raw_user.password,
                        path=each,
                        setup=Setup(**{**self.setup.model_dump(), **setup.model_dump()}),
                    )
                    LOG.debug('Adding raw user {}', name)
                    self.users.append(new_user)
                    break
            else:
                LOG.warning('There are no credentials for user named {}, skipping', name)


@dataclass
class Setup:
    """Personal settings for collection."""

    final_collection: Literal['move', 'delete', 'nothing'] = 'move'
    final_item: Literal['move', 'delete', 'nothing'] = 'move'
    ephemeral: bool = False
    tags: list[str] = field(default_factory=list)
    limit: int = -1

    @classmethod
    def from_path(cls, path: Path, filename: str) -> Self:
        """Create instance from given folder."""
        setup = cls().model_dump()

        try:
            with open(path / filename, encoding='utf-8') as f:
                raw_setup = yaml.safe_load(f)
        except FileNotFoundError:
            pass
        else:
            setup.update(raw_setup)

        return cls(**setup)

    def model_dump(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
