"""User abstraction."""

from uuid import UUID

from omoide_client import AuthenticatedClient

from omoide_sync import exceptions


class User:
    """User abstraction."""

    def __init__(
        self,
        uuid: UUID | None,
        name: str,
        login: str,
        password: str,
        root_item_uuid: UUID | None = None,
    ) -> None:
        """Initialize instance."""
        self.uuid = uuid
        self.name = name
        self.login = login
        self.password = password
        self.root_item_uuid = root_item_uuid
        self._client = None

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

    def sync(self) -> None:
        """Synchronize user with API."""
