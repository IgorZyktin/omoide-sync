"""Storage handler that can work with actual data."""

from abc import ABC
from collections.abc import Iterator
import os
from pathlib import Path
import shutil

from loguru import logger as LOG
import yaml

from omoide_sync import cfg
from omoide_sync import const
from omoide_sync import exceptions
from omoide_sync import interfaces
from omoide_sync import models


class _FileStorageBase(interfaces.AbsStorage, ABC):
    """Helper class."""

    def __init__(
        self,
        config: cfg.Config,
    ) -> None:
        """Initialize instance."""
        self.config = config

    def _find_matching_user(self, folder_name: str) -> models.RawUser:
        """Scan through auth data."""
        for each in self.config.auth_data:
            if all(
                (
                    bool(each.get('name')),
                    bool(each.get('password')),
                    each.get('login') == folder_name,
                )
            ):
                return models.RawUser(**each)

        msg = f'Not enough auth data for user {folder_name!r}'
        raise exceptions.UserRelatedError(msg)

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
        parent: models.Collection,
    ) -> models.Collection | None:
        """Return Item instance for given path."""
        index = path.name.rfind('.')
        ext = path.name[index:].lower()
        if ext in self.config.supported_formats:
            item = models.Collection(
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
        parent: models.Collection | None,
    ) -> Iterator[models.Collection]:
        """Scan folder and return it as a collection."""
        setup = self._get_collection_setup(path)

        collection = models.Collection(
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

        collection.children.sort(key=lambda _item: _item.name)

        folders = [each for each in path.iterdir() if each.is_dir()]
        folders.sort(key=lambda _folder: _folder.name)

        for each in folders:
            yield from self._process_folder(
                user=user,
                path=each,
                parent=collection,
            )

        yield collection

    @staticmethod
    def _get_item_path(item: models.Collection) -> Path:
        """Return relative path to the item and its filename (if any)."""
        path = Path('.') / item.owner.login

        for parent in item.ancestors:
            path = path / parent.name

        return path / item.name


class FileStorage(_FileStorageBase):
    """File storage handler."""

    def get_raw_users(self) -> list[models.RawUser]:
        """Return list of users."""
        users: list[models.RawUser] = []

        for folder in self.config.root_folder.iterdir():
            if folder.is_file():
                continue

            user = self._find_matching_user(folder.name)
            users.append(user)

        return users

    def get_all_collections(
        self,
        user: models.User,
    ) -> Iterator[models.Collection]:
        """Iterate on all collections."""
        path = self.config.root_folder / user.login

        folders = list(path.iterdir())
        folders.sort(key=lambda _folder: _folder.name)

        for folder in folders:
            if folder.is_dir() and not folder.name.startswith('_'):
                yield from self._process_folder(user, folder, parent=None)

    def get_paths(self, item: models.Collection) -> dict[str, str]:
        """Return path to data for every child item."""
        paths: dict[str, str] = {}

        for child in item.children:
            child_path = self.config.root_folder / self._get_item_path(child)
            paths[child.name] = str(child_path.absolute())

        return paths

    def prepare_termination(self, item: models.Collection) -> None:
        """Create resources if need to."""
        move1 = item.setup.termination_strategy_item == const.TERMINATION_MOVE
        move2 = item.setup.termination_strategy_collection == const.TERMINATION_MOVE

        if (move1 or move2) and item.setup.treat_as_collection:
            path = self._get_item_path(item)
            source_path = self.config.root_folder / path
            dest_path = self.config.trash_folder / path

            if self.config.dry_run:
                LOG.debug(
                    'Supposed to copy folder tree because ' 'of collection {} from {} to {}',
                    item,
                    source_path,
                    dest_path,
                )
            else:
                LOG.debug(
                    'Copying folder tree because ' 'of collection {} from {} to {}',
                    item,
                    source_path,
                    dest_path,
                )
                shutil.copytree(
                    source_path,
                    dest_path,
                    dirs_exist_ok=True,
                )

    def terminate_item(self, item: models.Collection) -> None:
        """Finish item processing."""
        path = self._get_item_path(item)

        match item.setup.termination_strategy_item:
            case const.TERMINATION_MOVE:
                source_path = self.config.root_folder / path
                dest_path = self.config.trash_folder / path

                if self.config.dry_run:
                    LOG.debug(
                        'Supposed to move item {} from {} to {}',
                        item,
                        source_path,
                        dest_path,
                    )
                else:
                    LOG.debug(
                        'Moving item {} from {} to {}',
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
                    LOG.debug('Supposed to delete {} at {}', item, full_path)
                else:
                    LOG.debug('Deleting {} at {}', item, full_path)
                    os.remove(full_path)

    def terminate_collection(self, item: models.Collection) -> None:
        """Finish collection processing."""
        path = self._get_item_path(item)

        match item.setup.termination_strategy_collection:
            case const.TERMINATION_MOVE:
                source_path = self.config.root_folder / path
                dest_path = self.config.trash_folder / path

                if self.config.dry_run:
                    LOG.debug(
                        'Supposed to move collection {} from {} to {}',
                        item,
                        source_path,
                        dest_path,
                    )
                else:
                    LOG.debug(
                        'Moving collection {} from {} to {}',
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

                filenames = {each.name for each in full_path.iterdir() if each.is_file()}

                unexpected_files = filenames - const.SETUP_FILENAMES
                must_be_deleted = item.setup.termination_strategy_item == const.TERMINATION_DELETE

                if unexpected_files and must_be_deleted:
                    msg = (
                        f'Cannot delete folder {path}, '
                        f'it has additional files inside: '
                        f'{sorted(unexpected_files)}'
                    )
                    raise exceptions.StorageRelatedError(msg)

                if self.config.dry_run:
                    LOG.debug(
                        'Supposed to delete collection {} at {}',
                        item,
                        full_path,
                    )
                else:
                    LOG.debug(
                        'Deleting collection {} at {}',
                        item,
                        full_path,
                    )
                    shutil.rmtree(full_path)
