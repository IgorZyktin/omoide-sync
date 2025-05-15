"""Class that handles uploading files to a remote server."""

from httpx import BasicAuth
from omoide_client.client import AuthenticatedClient

from omoide_sync import filesystem, cfg, exceptions
from omoide_sync import stats as global_stats


class Uploader:
    """Class that handles uploading files to a remote server."""

    def __init__(
        self,
        config: cfg.Config,
        user: cfg.ConfigUser,
        folder: filesystem.Folder,
        stats: global_stats.Stats,
    ) -> None:
        """Initialize instance."""
        self.config = config
        self.user = user
        self.folder = folder
        self.stats = stats
        self._client = None

    def client(self) -> AuthenticatedClient:
        """Return client instance."""
        if self._client is None:
            msg = 'Client is not yet initialized'
            raise exceptions.ConfigRelatedError(msg)
        return self._client

    def init_client(self) -> None:
        """Initialize API client."""
        self._client = AuthenticatedClient(
            base_url=self.config.api_url,
            httpx_args={
                'auth': BasicAuth(
                    username=self.user.login,
                    password=self.user.password,
                ),
            },
            token='',
        )

    def upload(self) -> None:
        """Upload our folder and all children."""
        # TODO
