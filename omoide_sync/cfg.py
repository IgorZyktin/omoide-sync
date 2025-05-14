"""Global configuration."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
from typing import Annotated
from typing import Literal
from typing import TypeAlias

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


LogLevel: TypeAlias = Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'EXCEPTION']


@dataclass
class Config(ns.BaseConfig):
    """Global configuration."""

    api_url: str
    data_folder: Path
    archive_folder: Path
    users: Annotated[tuple[ConfigUser, ...], tuple] = ()

    supported_formats: Annotated[
        tuple[str, ...],
        tuple,
        ns.Separated(),
    ] = ('.png', '.jpg', '.jpeg', '.webp')

    log_path: Path = Path('omoide_sync.log')
    log_rotation: str = '1 MB'
    setup_filename: str = 'setup.yaml'
    log_level: Annotated[LogLevel, str.upper] = 'DEBUG'

    show_folder_structure: bool = True
    dry_run: bool = False
    limit: int = -1

    skip_prefixes: Annotated[tuple[str, ...], tuple, ns.Separated()] = (
        '_',
        '.',
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


def build_config(dry_run: bool | None, limit: int | None) -> Config:
    """Return Config instance."""
    config = ns.from_env(Config, env_prefix=const.ENV_PREFIX)

    if dry_run is not None:
        config.dry_run = dry_run

    if limit is not None:
        config.limit = limit

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


_CONFIG: Config | None = None


def get_config(
    dry_run: bool | None = None,
    limit: int | None = None,
) -> Config:
    """Return global statistics singleton."""
    global _CONFIG  # noqa: PLW0603
    if _CONFIG is None:
        _CONFIG = build_config(dry_run=dry_run, limit=limit)
    return _CONFIG
