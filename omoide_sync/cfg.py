"""Global configuration."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
from typing import Annotated
from typing import Literal

import nano_settings as ns

from omoide_sync import const


@dataclass(frozen=True)
class ConfigUser:
    """Initial user representation."""

    name: str
    login: str
    password: str

    def __repr__(self) -> str:
        """Return string representation."""
        class_name = type(self).__name__
        return f'{class_name}<{self.name}>'


@dataclass
class Config(ns.BaseConfig):
    """Global configuration."""

    api_url: str
    data_folder: Path
    archive_folder: Path
    users: Annotated[tuple[ConfigUser, ...], tuple] = ()

    supported_formats: Annotated[
        frozenset[str],
        frozenset,
        ns.Separated(),
    ] = frozenset(['png', 'jpg', 'jpeg', 'webp'])

    log_path: Path = Path('omoide_sync.log')
    log_rotation: str = '1 MB'
    setup_filename: str = 'setup.yaml'
    log_level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'EXCEPTION'] = (
        'DEBUG'
    )

    dry_run: bool = False

    skip_prefixes: Annotated[frozenset[str], frozenset, ns.Separated()] = (
        frozenset(['_'])
    )


USERNAME_TEMPLATE = re.compile(const.USERS_ENV_PREFIX + r'__USER_NAME_(\d+)')


def get_users() -> list[ConfigUser]:
    """Extract users from env."""
    users: list[ConfigUser] = []
    for key, value in os.environ.items():
        if reg := USERNAME_TEMPLATE.match(key):
            number = reg.group(1)
            login = os.environ.get(
                const.USERS_ENV_PREFIX + f'__USER_LOGIN_{number}'
            )

            if login is None:
                msg = f'Failed to get login for user {value!r}'
                sys.exit(msg)

            password = os.environ.get(
                const.USERS_ENV_PREFIX + f'__USER_PASSWORD_{number}'
            )

            if password is None:
                msg = f'Failed to get password for user {value!r}'
                sys.exit(msg)

            users.append(
                ConfigUser(
                    name=value,
                    login=login,
                    password=password,
                )
            )

    return users


def get_config(dry_run: bool | None) -> Config:
    """Return Config instance."""
    config = ns.from_env(Config, env_prefix=const.ENV_PREFIX)

    if dry_run is not None:
        config.dry_run = dry_run

    if not config.data_folder.exists():
        msg = f'Data folder does not exist: {config.data_folder.absolute()}'
        sys.exit(msg)

    if not config.archive_folder.exists():
        msg = (
            f'Archive folder does not exist: '
            f'{config.archive_folder.absolute()}'
        )
        sys.exit(msg)

    if not config.log_path.parent.exists():
        msg = (
            f'Logging folder does not exist: '
            f'{config.log_path.parent.absolute()}'
        )
        sys.exit(msg)

    config.users = tuple(get_users())

    return config
