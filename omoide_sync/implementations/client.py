"""HTTP client that interacts with the API."""

import datetime
import http
import json
import time
from abc import ABC
from typing import Any
from uuid import UUID

import requests
import selenium.common.exceptions
from loguru import logger as LOG
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver

from omoide_sync import cfg
from omoide_sync import exceptions
from omoide_sync import interfaces
from omoide_sync import models

API_USERS_ENDPOINT = '/api/v1/users'
API_ITEMS_ENDPOINT = '/api/v1/items'


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
                LOG.info('Still waiting {} to upload', item)
                time.sleep(self.config.wait_step_for_upload)
            else:
                LOG.info('Done uploading {}', item)
                return

            try:
                elem = self.driver.find_element(
                    'xpath',
                    '//div[@class="notification om-alert"]',
                )
            except selenium.common.exceptions.NoSuchElementException:
                pass
            else:
                LOG.error(
                    'Got error in element {}',
                    elem.get_attribute('innerHTML'),
                )
                return

        msg = f'Failed to upload {item} even after {deadline} seconds'
        raise exceptions.NetworkRelatedError(msg)

    def _common_request_args(
        self,
        login: str,
        password: str,
    ) -> dict[str, Any]:
        """Return common arguments for all requests."""
        return {
            'headers': {
                'Content-Type': 'application/json; charset=UTF-8',
            },
            'auth': (
                login,
                password,
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

    def get_user(self, raw_user: models.RawUser) -> models.User:
        """Return User from the API."""
        url = self.config.url.rstrip('/') + API_USERS_ENDPOINT

        r = requests.get(  # noqa: S113
            url,
            **self._common_request_args(
                login=raw_user.login,
                password=raw_user.password,
            ),
        )

        r.raise_for_status()
        body = r.json()

        if not body or not body.get('users'):
            msg = f'User {raw_user.name} does not exist'
            raise exceptions.NetworkRelatedError(msg)

        try:
            user_dict = body['users'][0]
            user = models.User(
                uuid=UUID(user_dict['uuid']),
                name=user_dict['name'],
                login=raw_user.login,
                password=raw_user.password,
                root_item=user_dict['extras']['root_item_uuid'],
            )
        except Exception:
            LOG.exception('Failed to parse API response '
                          'after requesting user info, got body {}', body)
            raise exceptions.NetworkRelatedError(
                'Failed to parse API response after requesting user info')

        return user

    def get_item(self, item: models.Item) -> models.Item | None:
        """Return Item from the API."""
        LOG.info('Getting item {} for {}', item, item.owner)

        if item.uuid and (cached := self._item_cache.get(item.uuid)):
            return cached

        url = self.config.url.rstrip('/') + API_ITEMS_ENDPOINT

        if item.uuid:
            r = requests.get(  # noqa: S113
                f'{url}/{item.uuid}',
                **self._common_request_args(
                    login=item.owner.login,
                    password=item.owner.password,
                ),
            )
            cardinality = 'one'

        else:
            r = requests.get(  # noqa: S113
                url,
                params={
                    'name': item.name,
                    'owner_uuid': str(item.owner.uuid),
                },
                **self._common_request_args(
                    login=item.owner.login,
                    password=item.owner.password,
                ),
            )
            cardinality = 'many'

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
                    f'{r.status_code} {r.text}'
                )
            raise exceptions.NetworkRelatedError(msg)

        response = r.json()
        LOG.info('Got response {}', response)

        if cardinality == 'one':
            item.uuid = UUID(r.json()['item']['uuid'])
        else:
            items = r.json()['items']

            if not items:
                return None

            if len(items) > 1:
                msg = f'Got more than one item: {items}'
                raise exceptions.NetworkRelatedError(msg)

            item.uuid = items[0]['uuid']

        self._item_cache[item.uuid] = item

        return item

    def create_item(self, item: models.Item) -> models.Item:
        """Crete Item in the API."""
        LOG.info('Creating item {} for {}', item, item.owner)

        if not item.setup.treat_as_collection:
            msg = (
                f'Item {item} is not treated as a collection '
                f'and is not supposed to be created on the backend'
            )
            raise exceptions.ConfigRelatedError(msg)

        if item.uuid and (cached := self._item_cache.get(item.uuid)):
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
                'parent_uuid': parent_uuid,
                'name': item.name,
                'is_collection': item.is_collection,
                'tags': item.setup.tags,
                'permissions': [],
            },
            ensure_ascii=False,
        )

        url = self.config.url.rstrip('/') + API_ITEMS_ENDPOINT

        r = requests.post(  # noqa: S113
            url=url,
            data=payload.encode('utf-8'),
            **self._common_request_args(
                login=item.owner.login,
                password=item.owner.password,
            ),
        )

        if r.status_code not in (http.HTTPStatus.OK, http.HTTPStatus.CREATED):
            msg = (
                f'Failed to create item {item}: '
                f'{r.status_code} {r.text!r}, payload: {payload}'
            )
            raise exceptions.NetworkRelatedError(msg)

        item.uuid = UUID(r.json()['item']['uuid'])
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
                f'Uploading children of {item} using url '
                f'{upload_url} with {len(item.children)} items'
            )
        elif item.real_parent and item.real_parent.uuid:
            upload_url = f'{self.config.url}/upload/{item.real_parent.uuid}'
            LOG.info(
                f'Uploading children of {item} '
                f'as a proxy for {item.real_parent} '
                f'using url {upload_url} with {len(item.children)} items'
            )
        else:
            LOG.error(
                f'Failed to find parent to upload: item {item}, '
                f'real parent is {item.real_parent}',
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
