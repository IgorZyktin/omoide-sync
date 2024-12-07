"""Global configuration."""

from dataclasses import dataclass
from pathlib import Path
import sys
import tomllib
from typing import Any
from typing import Literal


@dataclass(frozen=True)
class RawUser:
    """Initial user representation."""

    name: str
    login: str
    password: str

    def __repr__(self) -> str:
        """Return string representation."""
        return f'RawUser<{self.name}>'


@dataclass(frozen=True)
class Config:
    """Global configuration."""

    api_url: str
    source_path: Path
    archive_path: Path
    log_level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'EXCEPTION']
    log_path: Path
    setup_filename: str
    supported_formats: tuple[str, ...]
    skip_prefixes: tuple[str, ...]
    dry_run: bool
    users: list[RawUser]
    raw_setup: dict[str, Any]


def get_config(config_file: str, *, dry_run: bool) -> Config:  # noqa: C901
    """Return Config instance."""
    config_path = Path(config_file)

    if not config_path.exists():
        msg = f'Config file does not exist: {config_path.absolute()}'
        sys.exit(msg)

    with open(config_path, 'rb') as file:
        config_data = tomllib.load(file)

    if 'config' not in config_data:
        msg = f"There is no 'config' section in the config file: {config_path.absolute()}"
        sys.exit(msg)

    source_path = Path(config_data['config']['source_folder'])
    if not source_path.exists():
        msg = f'Source folder does not exist: {source_path.absolute()}'
        sys.exit(msg)

    archive_path = Path(config_data['config']['archive_folder'])
    if not archive_path.exists():
        msg = f'Archive folder does not exist: {archive_path.absolute()}'
        sys.exit(msg)

    cred_path = Path(config_data['config']['cred_file'])
    if not cred_path.exists():
        msg = f'Credentials file does not exist: {cred_path.absolute()}'
        sys.exit(msg)

    with open(cred_path, 'rb') as cred_file:
        cred_data = tomllib.load(cred_file)

    raw_users = cred_data.get('users')

    if not raw_users:
        msg = f'No users in credentials file: {cred_path.absolute()}'
        sys.exit(msg)

    users: list[RawUser] = []
    for user_data in cred_data['users']:
        users.append(RawUser(**user_data))

    log_path = Path(config_data['config']['log_file'])
    if not log_path.parent.exists():
        msg = f'Logging folder does not exist: {log_path.parent.absolute()}'
        sys.exit(msg)

    if not (api_url := config_data['config'].get('api_url')):
        msg = f'No API URL is mentioned in the config file: {config_path.absolute()}'
        sys.exit(msg)

    if not (setup_filename := config_data['config'].get('setup_filename')):
        msg = f'No setup filename is mentioned in the config file: {config_path.absolute()}'
        sys.exit(msg)

    if not (supported_formats := config_data['config'].get('supported_formats')):
        msg = f'No supported formats are mentioned in the config file: {config_path.absolute()}'
        sys.exit(msg)

    return Config(
        api_url=api_url,
        source_path=source_path,
        archive_path=archive_path,
        setup_filename=setup_filename,
        log_path=log_path,
        log_level=config_data['config'].get('log_level', 'INFO'),
        dry_run=dry_run,
        users=users,
        supported_formats=tuple(set(supported_formats)),
        skip_prefixes=tuple(config_data['config'].get('skip_prefixes', ('_',))),
        raw_setup=config_data.get('root', {}),
    )
