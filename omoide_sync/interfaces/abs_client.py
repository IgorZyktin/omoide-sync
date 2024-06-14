"""HTTP client that interacts with the API.
"""
import abc

from omoide_sync import models


class AbsClient(abc.ABC):
    """Abstract API client."""

    @abc.abstractmethod
    def start(self) -> None:
        """Prepare for work."""

    @abc.abstractmethod
    def stop(self) -> None:
        """Finish work."""

    @abc.abstractmethod
    def get_item(self, item: models.Item) -> models.Item | None:
        """Return Item from the API."""

    @abc.abstractmethod
    def create_item(self, item: models.Item) -> models.Item:
        """Crete Item in the API."""

    @abc.abstractmethod
    def upload(self, item: models.Item, paths: dict[str, str]) -> models.Item:
        """Crete Item in the API."""
