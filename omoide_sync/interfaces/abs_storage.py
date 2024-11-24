"""Storage handler that can work with actual data."""

import abc
from collections.abc import Iterator

from omoide_sync.models import models


class AbsStorage(abc.ABC):
    """Abstract storage handler."""

    @abc.abstractmethod
    def get_raw_users(self) -> list[models.RawUser]:
        """Return list of users."""

    @abc.abstractmethod
    def get_all_collections(
        self,
        user: models.User,
    ) -> Iterator[models.Item]:
        """Iterate on all items."""

    @abc.abstractmethod
    def get_paths(self, item: models.Item) -> dict[str, str]:
        """Return path to data for every child item."""

    @abc.abstractmethod
    def prepare_termination(self, item: models.Item) -> None:
        """Create resources if need to."""

    @abc.abstractmethod
    def terminate_item(self, item: models.Item) -> None:
        """Finish item processing."""

    @abc.abstractmethod
    def terminate_collection(self, item: models.Item) -> None:
        """Finish collection processing."""
