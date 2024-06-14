"""Storage handler that can work with actual data.
"""
import abc
from typing import Iterator

from omoide_sync import models


class AbsStorage(abc.ABC):
    """Abstract storage handler."""

    @abc.abstractmethod
    def get_root_item(self, user: models.User) -> models.Item | None:
        """Return root item for given user."""

    @abc.abstractmethod
    def get_users(self) -> list[models.User]:
        """Return list of users."""

    @abc.abstractmethod
    def get_all_collections(
        self,
        user: models.User,
    ) -> Iterator[models.Item]:
        """Iterate on all items."""

    @abc.abstractmethod
    def terminate_item(self, item: models.Item) -> None:
        """Finish item processing."""

    @abc.abstractmethod
    def terminate_collection(self, item: models.Item) -> None:
        """Finish collection processing."""