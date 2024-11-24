"""Global configuration."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from omoide_sync import const


@dataclass
class RawUser:
    """Initial user representation."""

    name: str
    login: str
    password: str

    def __repr__(self) -> str:
        """Return string representation."""
        return f'RawUser<{self.login}>'


@dataclass
class Config:
    """Global configuration."""

    api_url: str
    root_path: Path
    trash_path: Path
    log_path: Path
    supported_formats: set[str]
    spacer: str
    dry_run: bool
    users: list[RawUser]


def get_config(config_file: str, dry_run: bool) -> Config:
    """Return Config instance."""
    config_path = Path(config_file)
    if not config_path.exists():
        msg = f'Config file does not exist: {config_path.absolute()}'
        raise RuntimeError(msg)

    with open(config_path, 'rb') as config_file:
        config_data = tomllib.load(config_file)

    if 'config' not in config_data:
        msg = f"There is no 'config' section in the config file: {config_path.absolute()}"
        raise RuntimeError(msg)

    root_path = Path(config_data['config']['root_folder'])
    if not root_path.exists():
        msg = f'Root folder does not exist: {root_path.absolute()}'
        raise RuntimeError(msg)

    trash_path = Path(config_data['config']['trash_folder'])
    if not trash_path.exists():
        msg = f'Trash folder does not exist: {trash_path.absolute()}'
        raise RuntimeError(msg)

    cred_path = Path(config_data['config']['cred_file'])
    if not cred_path.exists():
        msg = f'Credentials file does not exist: {cred_path.absolute()}'
        raise RuntimeError(msg)

    with open(cred_path, 'rb') as cred_file:
        cred_data = tomllib.load(cred_file)

    raw_users = cred_data.get('users')

    if not raw_users:
        msg = f'No users are mentioned in credentials file {cred_path.absolute()}'
        raise RuntimeError(msg)

    users: list[RawUser] = []
    for user_data in cred_data['users']:
        users.append(RawUser(**user_data))

    log_path = Path(config_data['config']['log_file'])
    if not log_path.parent.exists():
        msg = f'Logging folder does not exist: {log_path.parent.absolute()}'
        raise RuntimeError(msg)

    if not (api_url := config_data['config'].get('api_url')):
        msg = f'No API URL is mentioned in the config file: {config_path.absolute()}'
        raise RuntimeError(msg)

    if not (supported_formats := config_data['config'].get('supported_formats')):
        msg = f'No supported formats are mentioned in the config file: {config_path.absolute()}'
        raise RuntimeError(msg)

    spacer = config_data['config'].get('spacer', const.DEFAULT_SPACER)

    return Config(
        api_url=api_url,
        root_path=root_path,
        trash_path=trash_path,
        dry_run=dry_run,
        log_path=log_path,
        users=users,
        spacer=spacer,
        supported_formats=set(supported_formats),
    )
