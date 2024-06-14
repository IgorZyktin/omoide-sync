"""HTTP client that interacts with the API.
"""
import abc

from omoide_sync import models


class AbsClient(abc.ABC):
    """Abstract API client."""

    @abc.abstractmethod
    def get_item(self, item: models.Item) -> models.Item | None:
        """Return Item from the API."""

    @abc.abstractmethod
    def create_item(self, item: models.Item) -> models.Item:
        """Crete Item in the API."""

    @abc.abstractmethod
    def upload(self, item: models.Item) -> models.Item:
        """Crete Item in the API."""
