"""HTTP client that interacts with the API."""

from abc import ABC
import datetime
import http
import json
import logging
import time
from typing import Any
from uuid import UUID

import requests
from selenium import webdriver
import selenium.common.exceptions
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver

from omoide_sync import cfg
from omoide_sync import exceptions
from omoide_sync import interfaces
from omoide_sync import models

LOG = logging.getLogger(__name__)


class _SeleniumClientBase(interfaces.AbsClient, ABC):
    """API client."""

    def __init__(self, config: cfg.Config) -> None:
        """Initialize instance."""
        self.config = config
        self._item_cache: dict[UUID, models.Item] = {}
        self._driver: WebDriver | None = None

    @property
    def driver(self) -> WebDriver:
        """Return driver instance."""
        if self._driver is None:
            msg = 'Selenium driver is not initialized'
            raise exceptions.ConfigRelatedError(msg)
        return self._driver

    def _make_auth_url(self, item: models.Item) -> str:
        """Make url that will allow us to login."""
        if self.config.url.startswith('https://'):
            prefix = 'https://'
            url_end = self.config.url[8:]
        else:
            # noinspection HttpUrlsUsage
            prefix = 'http://'
            url_end = self.config.url[7:]

        return f'{prefix}{item.owner.login}:{item.owner.password}@{url_end}'

    def _wait_for_upload(self, item: models.Item, timeout: int) -> None:
        """Wait for uploading to complete."""
        deadline = datetime.datetime.now(
            tz=datetime.timezone.utc
        ) + datetime.timedelta(seconds=timeout)

        while datetime.datetime.now(tz=datetime.timezone.utc) < deadline:
            try:
                self.driver.find_element(
                    'xpath',
                    '//span[text()="Ready for new batch"]',
                )
            except selenium.common.exceptions.NoSuchElementException:
                LOG.info('Still waiting %s to upload', item)
                time.sleep(self.config.wait_step_for_upload)
            else:
                LOG.info('Done uploading %s', item)
                return

        msg = f'Failed to upload {item} even after {deadline} seconds'
        raise exceptions.NetworkRelatedError(msg)

    def _common_request_args(self, item: models.Item) -> dict[str, Any]:
        """Return common arguments for all requests."""
        return {
            'headers': {
                'Content-Type': 'application/json; charset=UTF-8',
            },
            'auth': (
                item.owner.login,
                item.owner.password,
            ),
            'timeout': self.config.request_timeout,
        }


class SeleniumClient(_SeleniumClientBase):
    """API client."""

    def start(self) -> None:
        """Prepare for work."""
        options = Options()
        options.add_argument('--headless=new')
        driver = webdriver.Remote(
            command_executor=self.config.driver,
            options=options,
        )
        self._driver = driver

    def stop(self) -> None:
        """Finish work."""
        self.driver.close()
        self.driver.quit()

    def get_item(self, item: models.Item) -> models.Item | None:
        """Return Item from the API."""
        if item.uuid:
            if cached := self._item_cache.get(item.uuid):
                return cached

        payload = json.dumps(
            {
                'name': item.name,
            },
            ensure_ascii=False,
        )

        if item.uuid:
            r = requests.get(  # noqa: S113
                f'{self.config.url}/api/items/{item.uuid}',
                **self._common_request_args(item),
            )

        else:
            r = requests.get(  # noqa: S113
                f'{self.config.url}/api/items/by-name',
                data=payload.encode('utf-8'),
                **self._common_request_args(item),
            )

        if r.status_code == http.HTTPStatus.NOT_FOUND:
            return None

        if r.status_code != http.HTTPStatus.OK:
            if item.uuid:
                msg = (
                    f'Failed to get item {item}: ' f'{r.status_code} {r.text}'
                )
            else:
                msg = (
                    f'Failed to get item by name {item}: '
                    f'{r.status_code} {r.text}, payload {payload}'
                )
            raise exceptions.NetworkRelatedError(msg)

        item.uuid = UUID(r.json()['uuid'])
        self._item_cache[item.uuid] = item

        return item

    def create_item(self, item: models.Item) -> models.Item:
        """Crete Item in the API."""
        if not item.setup.treat_as_collection:
            msg = (
                f'Item {item} is not treated as a collection '
                f'and is not supposed to be created on the backend'
            )
            raise exceptions.ConfigRelatedError(msg)

        if item.uuid:
            if cached := self._item_cache.get(item.uuid):
                return cached

        parent_uuid: str | None
        if item.real_parent is None:
            parent_uuid = str(item.owner.root_item)
        else:
            parent_uuid = (
                str(item.real_parent.uuid) if item.real_parent.uuid else None
            )

        payload = json.dumps(
            {
                'uuid': None,
                'parent_uuid': parent_uuid,
                'name': item.name,
                'is_collection': item.is_collection,
                'tags': item.setup.tags,
                'permissions': [],
            },
            ensure_ascii=False,
        )

        r = requests.post(  # noqa: S113
            f'{self.config.url}/api/items',
            data=payload.encode('utf-8'),
            **self._common_request_args(item),
        )

        if r.status_code not in (http.HTTPStatus.OK, http.HTTPStatus.CREATED):
            msg = (
                f'Failed to create item {item}: '
                f'{r.status_code} {r.text!r}, payload: {payload}'
            )
            raise exceptions.NetworkRelatedError(msg)

        item.uuid = UUID(r.json()['uuid'])
        self._item_cache[item.uuid] = item

        return item

    def upload(self, item: models.Item, paths: dict[str, str]) -> None:
        """Crete Item in the API."""
        # logging in
        auth_url = self._make_auth_url(item)
        self.driver.get(f'{auth_url}/login')

        if item.setup.treat_as_collection:
            upload_url = f'{self.config.url}/upload/{item.uuid}'
            LOG.info(
                'Uploading children of %(item)s using url '
                '%(url)s with %(total)s items',
                {
                    'item': item,
                    'parent': item.real_parent,
                    'url': upload_url,
                    'total': len(item.children),
                },
            )
        elif item.real_parent and item.real_parent.uuid:
            upload_url = f'{self.config.url}/upload/{item.real_parent.uuid}'
            LOG.info(
                'Uploading children of %(item)s '
                'as a proxy for %(parent)s '
                'using url %(url)s with %(total)s items',
                {
                    'item': item,
                    'parent': item.real_parent,
                    'url': upload_url,
                    'total': len(item.children),
                },
            )
        else:
            LOG.error(
                'Failed to find parent to upload: item %(item_uuid)s, '
                'real parent is %(parent)s',
                {
                    'item': item,
                    'parent': item.real_parent,
                },
            )
            msg = f'Item {item} has no real parent: {item.real_parent}'
            raise exceptions.OmoideSyncError(msg)

        self.driver.get(upload_url)

        js_code = 'arguments[0].scrollIntoView();'

        # turning on simplified upload
        time.sleep(self.config.wait_for_page_load)
        auto_checkbox = self.driver.find_element(
            by='id',
            value='auto-continue',
        )
        self.driver.execute_script(js_code, auto_checkbox)

        time.sleep(self.config.wait_for_page_load)
        auto_checkbox.click()

        # adding files
        time.sleep(self.config.wait_for_page_load)
        upload_input = self.driver.find_element(by='id', value='upload-input')
        self.driver.execute_script(js_code, upload_input)
        all_files = '\n'.join(paths[each.name] for each in item.children)

        time.sleep(self.config.wait_for_page_load)
        # TODO - here we're supposed to add personal tags for items,
        #  but for now it's not yet implemented
        upload_input.send_keys(all_files)
        self._wait_for_upload(item, timeout=self.config.wait_for_upload)

        if self.config.wait_after_upload:
            time.sleep(self.config.wait_after_upload)
