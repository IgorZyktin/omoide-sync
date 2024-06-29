"""Service logic."""

import abc

from omoide_sync import models


class AbsLogic(abc.ABC):
    """Abstract service logic."""

    @abc.abstractmethod
    def execute(self) -> None:
        """Start processing."""

    @abc.abstractmethod
    def process_single_user(self, user: models.User) -> None:
        """Upload data for given user."""

    @abc.abstractmethod
    def create_chain(self, item: models.Item) -> None:
        """Create whole chain of items."""
