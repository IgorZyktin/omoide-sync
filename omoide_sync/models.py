"""Project models."""

from collections.abc import Iterator
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
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


class Stats:
    """Upload statistics."""


class Collection:
    """Folder abstraction."""

    def __init__(
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
        return f'<Item({self.name}, children={len(self.children)}, parent={self.parent.name}>'

    def __str__(self) -> str:
        """Return string representation."""
        return f'<{self.uuid} {self.name}>'

    @property
    def uuid(self) -> UUID:
        """Return user UUID."""
        if self._uuid is None:
            msg = f'UUID for item {self.name} is not set yet'
            raise exceptions.UserRelatedError(msg)
        return self._uuid

    @uuid.setter
    def uuid(self, new_uuid: str | UUID) -> None:
        """Set UUID."""
        if isinstance(new_uuid, str):
            new_uuid = UUID(new_uuid)
        self._uuid = new_uuid

    def init(self) -> None:
        """Synchronize collection with API."""
        if self._uuid is not None:
            response = api_get_item_v1_items_item_uuid_get.sync(
                item_uuid=self.uuid,
                client=self.owner.client,
            )
            remote_item = response.item
        else:
            response = api_get_many_items_v1_items_get.sync(
                owner_uuid=self.owner.uuid,
                parent_uuid=self.parent.uuid,
                client=self.owner.client,
                limit=100,
            )
            print('-' * 20)
            print(*response.items, sep='\n')
            matching = [item for item in response.items if item.name == self.name]

            if not matching:
                msg = f'Cannot find item by name {self.name!r} and parent {self.parent.uuid}'
                raise exceptions.ItemRelatedError(msg)

            if len(matching) > 1:
                msg = f'Got more than child named {matching[0].name!r}'
                raise exceptions.ItemRelatedError(msg)

            remote_item = matching[0]
            self.uuid = remote_item.uuid

        if remote_item.name != self.name:
            msg = (
                f'Conflicting name for item, '
                f'folder says {self.name}, '
                f'but service says {remote_item.name}'
            )
            raise exceptions.ItemRelatedError(msg)

        self.init_children()

    def init_children(self) -> None:
        """Read all underlying folders."""
        for each in self.path.iterdir():
            if each.is_file():
                continue

            uuid, name = utils.split_name(each, self.owner.root.config.spacer)

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
        LOG.info('Uploading {} {}', self.uuid, self.name)


class User:
    """User abstraction."""

    def __init__(
        self,
        root: 'Source',
        uuid: UUID | str | None,
        name: str,
        login: str,
        password: str,
        path: Path,
        setup: 'Setup',
    ) -> None:
        """Initialize instance."""
        self.root = root
        self.name = name
        self.login = login
        self.password = password
        self.path = path
        self.setup = setup

        self.collections: list[Collection] = []

        self._initial_uuid = uuid
        self._uuid = None
        self._root_item_uuid = None
        self._root_item = None
        self._client = None

    def __repr__(self) -> str:
        """Return string representation."""
        return f'User<{self.name}>'

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

        self.sync_collections()

    def sync_collections(self) -> None:
        """Read all underlying folders."""
        self.root_item = Collection(
            uuid=self.root_item_uuid,
            owner=self,
            name=self.name,
            parent=None,
            children=[],
            setup=self.setup,
            path=self.path,
        )

        for each in self.path.iterdir():
            if each.is_file():
                continue

            uuid, name = utils.split_name(each, self.root.config.spacer)

            new_item = Collection(
                uuid=uuid,
                owner=self,
                name=name,
                parent=self.root_item,
                children=[],
                setup=self.setup,
                path=each,
            )

            self.collections.append(new_item)
            self.root_item.children.append(new_item)

    def iter_collections(self) -> Iterator[Collection]:
        """Iterate on all collections, including nested."""
        for collection in self.collections:
            yield from collection.iter_children()


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
            uuid, name = utils.split_name(each, self.config.spacer)

            for raw_user in self.config.users:
                if raw_user.name == name:
                    new_user = User(
                        root=self,
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
    treat_as_collection: bool = True
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


# @dataclass
# class Item:
#     """Item representation."""
#
#     uuid: UUID | None
#     owner: User
#     name: str
#     parent: Optional['Item']
#     children: list['Item']
#     is_collection: bool
#     uploaded: int
#     setup: Setup
#
#
#     @property
#     def uploaded_enough(self) -> bool:
#         """Return True if we're reached the upload limit."""
#         enough = all(
#             (
#                 self.setup.upload_limit > 0,
#                 self.uploaded >= self.setup.upload_limit,
#             )
#         )
#
#         if enough:
#             return True
#
#         if self.parent:
#             return self.parent.uploaded_enough
#
#         return False
#
#     @property
#     def ancestors(self) -> list['Item']:
#         """Return all parent items."""
#         ancestors: list[Item] = []
#         parent = self.parent
#
#         while parent:
#             ancestors.append(parent)
#             parent = parent.parent
#
#         return list(reversed(ancestors))
#
#     @property
#     def real_parent(self) -> Optional['Item']:
#         """Return first parent that is treated as a collection."""
#         parent = self.parent
#
#         while parent:
#             if parent.setup.treat_as_collection:
#                 return parent
#
#             parent = parent.parent
#
#         return parent
