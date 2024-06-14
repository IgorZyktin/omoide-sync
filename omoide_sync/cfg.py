"""Global configuration.
"""
from pathlib import Path
from uuid import UUID

from typing_extensions import TypedDict

from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class RawUser(TypedDict):
    """Initial user representation."""
    name: str
    login: str
    root_item: UUID
    password: str


class Config(BaseSettings):
    """Global configuration."""
    url: str
    driver: str
    auth_data: list[RawUser]
    root_folder: Path
    trash_folder: Path | None = None
    dry_run: bool = False
    log_level: str = 'INFO'
    supported_formats: set[str] = {
        '.png',
        '.jpg',
        '.jpeg',
        '.webp',
    }

    model_config = SettingsConfigDict(
        env_prefix='OMOIDE_SYNC__',
    )


def get_config() -> Config:
    """Return Config instance."""
    return Config()
