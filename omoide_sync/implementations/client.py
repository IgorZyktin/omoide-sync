"""HTTP client that interacts with the API.
"""
import datetime
import http
import json
import logging
import time
from uuid import UUID

import requests
import selenium.common.exceptions
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver

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
        self._driver: WebDriver | None = None

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

    @property
    def driver(self) -> WebDriver:
        """Return driver instance."""
        if self._driver is None:
            msg = 'Selenium driver is not initialized'
            raise exceptions.ConfigRelatedException(msg)
        return self._driver

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
                'name': item.name,
            }, ensure_ascii=False)

            r = requests.get(
                f'{self.config.url}/api/items-by-name',
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
                msg = (
                    f'Failed to get item {item.uuid}: '
                    f'{r.status_code} {r.text}'
                )
            else:
                msg = (
                    f'Failed to get item by name {item.name!r}: '
                    f'{r.status_code} {r.text}'
                )
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

        if item.parent is None:
            parent_uuid = str(item.owner.root_item)
        else:
            parent_uuid = str(item.parent.uuid) if item.parent.uuid else None

        payload = json.dumps({
            'uuid': None,
            'parent_uuid': parent_uuid,
            'name': item.name,
            'is_collection': item.is_collection,
            'tags': item.setup.tags,
            'permissions': [],
        }, ensure_ascii=False)

        r = requests.post(
            f'{self.config.url}/api/items',
            headers={'Content-Type': 'application/json; charset=UTF-8'},
            auth=(
                item.owner.login,
                item.owner.password,
            ),
            data=payload.encode('utf-8'),
            timeout=5,
        )

        if r.status_code not in (http.HTTPStatus.OK, http.HTTPStatus.CREATED):
            msg = (
                f'Failed to create item {item.name}: '
                f'{r.status_code} {r.text!r}, payload: {payload}'
            )
            raise exceptions.NetworkRelatedException(msg)

        outer_item = r.json()
        item.uuid = UUID(outer_item['uuid'])
        self._item_cache_by_uuid[item.uuid] = item
        self._item_cache_by_name[item.name] = item

        return item

    def upload(self, item: models.Item, paths: dict[str, str]) -> models.Item:
        """Crete Item in the API."""
        self.driver.get(f'{self.config.url}/upload/{item.uuid}')

        js_code = "arguments[0].scrollIntoView();"

        # turning on simplified upload
        time.sleep(1)
        auto_checkbox = self.driver.find_element(
            by='id',
            value='auto-continue',
        )
        self.driver.execute_script(js_code, auto_checkbox)
        time.sleep(1)
        auto_checkbox.click()

        # adding files
        time.sleep(1)
        upload_input = self.driver.find_element(by='id', value='upload-input')
        self.driver.execute_script(js_code, upload_input)
        all_files = '\n'.join(paths[each.name] for each in item.children)
        time.sleep(1)
        upload_input.send_keys(all_files)

        self._wait_for_upload(timeout=1000)
        self._wait_for_processing()

        return item

    def _wait_for_upload(self, timeout: int) -> None:
        """Wait for uploading to complete."""
        deadline = datetime.datetime.now() + datetime.timedelta(
            seconds=timeout)

        while datetime.datetime.now() < deadline:
            try:
                self.driver.find_element(
                    'xpath',
                    '//span[text()="Ready for new batch"]',
                )
            except selenium.common.exceptions.NoSuchElementException:
                LOG.info('Still waiting...')
                time.sleep(5)
            else:
                return

        msg = f'Failed to upload even after {deadline} seconds'
        raise RuntimeError(msg)

    @staticmethod
    def _wait_for_processing() -> None:
        """Waif for files to be processed."""
        # NOTE - not really progressive...
        time.sleep(600)
