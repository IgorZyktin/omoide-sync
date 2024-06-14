"""HTTP client that interacts with the API.
"""
import http
import json
import logging
from uuid import UUID

import requests

from omoide_sync import cfg
from omoide_sync import exceptions
from omoide_sync import interfaces
from omoide_sync import models

LOG = logging.getLogger(__name__)


class SeleniumClient(interfaces.AbsClient):
    """API client."""

    def __init__(
        self,
        config: cfg.Config,
        storage: interfaces.AbsStorage,
    ) -> None:
        """Initialize instance."""
        self.config = config
        self.storage = storage
        self._item_cache_by_name: dict[str, models.Item] = {}
        self._item_cache_by_uuid: dict[UUID, models.Item] = {}

    def get_item(self, item: models.Item) -> models.Item | None:
        """Return Item from the API."""
        cached_by_name = self._item_cache_by_name.get(item.name)
        cached_by_uuid = self._item_cache_by_uuid.get(item.uuid)
        cached = cached_by_name or cached_by_uuid

        if cached:
            return cached

        if item.uuid:
            r = requests.get(
                f'{self.config.url}/api/items/{item.uuid}',
                headers={'Content-Type': 'application/json; charset=UTF-8'},
                auth=(
                    item.owner.login,
                    item.owner.password,
                ),
                timeout=3,
            )

        else:
            payload = json.dumps({
                'user_login': item.owner.login,
                'parent_name': item.parent.name if item.parent else None,
                'item_name': item.name,
            }, ensure_ascii=False)

            r = requests.get(
                f'{self.config.url}/api/items-by-name/',
                headers={'Content-Type': 'application/json; charset=UTF-8'},
                auth=(
                    item.owner.login,
                    item.owner.password,
                ),
                data=payload.encode('utf-8'),
                timeout=3,
            )

        if r.status_code == http.HTTPStatus.NOT_FOUND:
            return None

        if r.status_code != http.HTTPStatus.OK:
            if item.uuid:
                msg = f'Failed to get item {item.uuid}'
            else:
                msg = f'Failed to get item by name {item.name!r}'
            raise exceptions.NetworkRelatedException(msg)

        outer_item = r.json()
        item.uuid = UUID(outer_item['uuid'])
        self._item_cache_by_uuid[item.uuid] = item
        self._item_cache_by_name[item.name] = item

        return item

    def create_item(self, item: models.Item) -> models.Item:
        """Crete Item in the API."""
        cached_by_name = self._item_cache_by_name.get(item.name)
        cached_by_uuid = self._item_cache_by_uuid.get(item.uuid)
        cached = cached_by_name or cached_by_uuid

        if cached:
            return cached

        payload = json.dumps({
            'uuid': None,
            'parent_uuid': str(item.parent.uuid) if item.parent else None,
            'name': item.name,
            'is_collection': item.is_collection,
            'tags': item.setup.tags,
            'permissions': [],
        }, ensure_ascii=False)

        r = requests.post(
            f'{self.config.url}/api/items/',
            headers={'Content-Type': 'application/json; charset=UTF-8'},
            auth=(
                item.owner.login,
                item.owner.password,
            ),
            data=payload.encode('utf-8'),
            timeout=5,
        )

        if r.status_code not in (http.HTTPStatus.OK, http.HTTPStatus.CREATED):
            msg = f'Failed to create item {item.name}:{r.text!r}'
            raise exceptions.NetworkRelatedException(msg)

        outer_item = r.json()
        item.uuid = UUID(outer_item['uuid'])
        self._item_cache_by_uuid[item.uuid] = item
        self._item_cache_by_name[item.name] = item

        return item

    def upload(self, item: models.Item) -> models.Item:
        """Load item content in the API."""

        # TODO - actually load data

        return item
