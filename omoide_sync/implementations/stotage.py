"""Storage handler that can work with actual data.
"""
import logging
import os
import shutil
from abc import ABC
from pathlib import Path
from typing import Iterator

import yaml

from omoide_sync import cfg
from omoide_sync import const
from omoide_sync import exceptions
from omoide_sync import interfaces
from omoide_sync import models

LOG = logging.getLogger(__name__)


class _FileStorageBase(interfaces.AbsStorage, ABC):
    """Helper class."""

    def __init__(
        self,
        config: cfg.Config,
    ) -> None:
        """Initialize instance."""
        self.config = config

    def _find_matching_user(self, folder_name: str) -> models.User:
        """Scan through auth data."""
        for each in self.config.auth_data:
            # NOTE: here we could get collision between login and name
            if all(
                (
                    any(
                        (
                            each.get('name') == folder_name,
                            each.get('login') == folder_name,
                        )
                    ),
                    bool(each.get('password'))
                )
            ):
                return models.User(**each)

        msg = f'Not enough auth data for user {folder_name!r}'
        raise exceptions.UserRelatedException(msg)

    @staticmethod
    def _get_collection_setup(path: Path) -> models.Setup:
        """Load personal settings for this collection."""
        setup = models.Setup()

        for filename in const.SETUP_FILENAMES:
            try:
                with open(path / filename, encoding='utf-8') as f:
                    raw_setup = yaml.safe_load(f)
            except FileNotFoundError:
                pass
            else:
                setup = models.Setup(**raw_setup)
                break

        return setup

    def _process_file(
        self,
        user: models.User,
        path: Path,
        parent: models.Item,
    ) -> models.Item | None:
        """Return Item instance for given path."""
        index = path.name.rfind('.')
        ext = path.name[index:].lower()
        if ext in self.config.supported_formats:
            item = models.Item(
                uuid=None,
                name=path.name,
                owner=user,
                parent=parent,
                children=[],
                is_collection=False,
                uploaded=0,
                setup=parent.setup,
            )
            return item
        return None

    def _process_folder(
        self,
        user: models.User,
        path: Path,
        parent: models.Item | None,
    ) -> Iterator[models.Item]:
        """Scan folder and return it as a collection."""
        setup = self._get_collection_setup(path)

        collection = models.Item(
            uuid=None,
            name=path.name,
            owner=user,
            parent=parent,
            children=[],
            is_collection=True,
            uploaded=0,
            setup=setup,
        )

        for each in path.iterdir():
            if each.is_file() and not each.name.startswith('_'):
                item = self._process_file(user, each, collection)
                if item:
                    collection.children.append(item)

        for each in path.iterdir():
            if each.is_dir():
                yield from self._process_folder(
                    user=user,
                    path=each,
                    parent=collection,
                )

        yield collection

    @staticmethod
    def _get_item_path(item: models.Item) -> Path:
        """Return relative path to the item and its filename (if any)."""
        path = Path('.') / item.owner.login

        for parent in item.ancestors:
            path = path / parent.name

        return path / item.name


class FileStorage(_FileStorageBase):
    """File storage handler."""

    def get_root_item(self, user: models.User) -> models.Item | None:
        """Return root item for given user."""
        # NOTE - theoretically, we should request this from the API.
        #  But currently this functionality is not supported there.
        if user.root_item is None:
            return None

        return models.Item(
            uuid=user.root_item,
            owner=user,
            name=user.name,
            parent=None,
            children=[],
            is_collection=True,
            uploaded=0,
            setup=self._get_collection_setup(
                path=self.config.root_folder / user.name,
            )
        )

    def get_users(self) -> list[models.User]:
        """Return list of users."""
        users: list[models.User] = []

        for folder in self.config.root_folder.iterdir():
            if folder.is_file():
                continue

            user = self._find_matching_user(folder.name)
            users.append(user)

        return users

    def get_all_collections(
        self,
        user: models.User,
    ) -> Iterator[models.Item]:
        """Iterate on all collections."""
        path = self.config.root_folder / user.login

        for folder in path.iterdir():
            if folder.is_dir() and not folder.name.startswith('_'):
                yield from self._process_folder(user, folder, parent=None)

    def get_paths(self, item: models.Item) -> dict[str, str]:
        """Return path to data for every child item."""
        paths: dict[str, str] = {}

        for child in item.children:
            child_path = self.config.root_folder / self._get_item_path(child)
            paths[child.name] = str(child_path.absolute())

        return paths

    def prepare_termination(self, item: models.Item) -> None:
        """Create resources if need to."""
        move1 = item.setup.termination_strategy_item == const.TERMINATION_MOVE
        move2 = (item.setup.termination_strategy_collection
                    == const.TERMINATION_MOVE)

        if (move1 or move2) and item.setup.treat_as_collection:
            path = self._get_item_path(item)
            source_path = self.config.root_folder / path
            dest_path = self.config.trash_folder / path

            if self.config.dry_run:
                LOG.debug(
                    'Supposed to copy folder tree because '
                    'of collection %s from %s to %s',
                    item,
                    source_path,
                    dest_path,
                )
            else:
                LOG.debug(
                    'Copying folder tree because '
                    'of collection %s from %s to %s',
                    item,
                    source_path,
                    dest_path,
                )
                shutil.copytree(
                    source_path,
                    dest_path,
                    dirs_exist_ok=True,
                )

    def terminate_item(self, item: models.Item) -> None:
        """Finish item processing."""
        path = self._get_item_path(item)

        match item.setup.termination_strategy_item:
            case const.TERMINATION_MOVE:
                source_path = self.config.root_folder / path
                dest_path = self.config.trash_folder / path

                if self.config.dry_run:
                    LOG.debug(
                        'Supposed to move item %s from %s to %s',
                        item,
                        source_path,
                        dest_path,
                    )
                else:
                    LOG.debug(
                        'Moving item %s from %s to %s',
                        item,
                        source_path,
                        dest_path,
                    )
                    shutil.move(
                        source_path,
                        dest_path,
                    )

            case const.TERMINATION_DELETE:
                full_path = self.config.root_folder / path

                if self.config.dry_run:
                    LOG.debug('Supposed to delete %s at %s', item, full_path)
                else:
                    LOG.debug('Deleting %s at %s', item, full_path)
                    os.remove(full_path)

        return

    def terminate_collection(self, item: models.Item) -> None:
        """Finish collection processing."""
        path = self._get_item_path(item)

        match item.setup.termination_strategy_collection:
            case const.TERMINATION_MOVE:
                source_path = self.config.root_folder / path
                dest_path = self.config.trash_folder / path

                if self.config.dry_run:
                    LOG.debug(
                        'Supposed to move collection %s from %s to %s',
                        item,
                        source_path,
                        dest_path,
                    )
                else:
                    LOG.debug(
                        'Moving collection %s from %s to %s',
                        item,
                        source_path,
                        dest_path,
                    )
                    shutil.copytree(
                        source_path,
                        dest_path,
                        dirs_exist_ok=True,
                    )

                    shutil.rmtree(source_path)

            case const.TERMINATION_DELETE:
                full_path = self.config.root_folder / path

                filenames = set(
                    each.name
                    for each in full_path.iterdir()
                    if each.is_file()
                )

                unexpected_files = filenames - const.SETUP_FILENAMES
                must_be_deleted = (
                    item.setup.termination_strategy_item
                    == const.TERMINATION_DELETE
                )

                if unexpected_files and must_be_deleted:
                    msg = (
                        f'Cannot delete folder {path}, '
                        f'it has additional files inside: '
                        f'{sorted(unexpected_files)}'
                    )
                    raise exceptions.StorageRelatedException(msg)

                if self.config.dry_run:
                    LOG.debug(
                        'Supposed to delete collection %s at %s',
                        item,
                        full_path,
                    )
                else:
                    LOG.debug('Deleting collection %s at ', item, full_path)
                    shutil.rmtree(full_path)

        return
