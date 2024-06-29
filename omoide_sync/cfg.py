"""Global configuration."""

from pathlib import Path
from uuid import UUID

from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict
from typing_extensions import TypedDict


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
    trash_folder: Path
    dry_run: bool = False
    log_level: str = 'INFO'
    supported_formats: set[str] = {
        '.png',
        '.jpg',
        '.jpeg',
        '.webp',
    }
    wait_for_upload: int = 600
    wait_after_upload: int = 0
    wait_step_for_upload: int = 5
    wait_for_page_load: float = 1.0
    request_timeout: float = 5.0

    model_config = SettingsConfigDict(
        env_prefix='OMOIDE_SYNC__',
    )


def get_config() -> Config:
    """Return Config instance."""
    return Config()
