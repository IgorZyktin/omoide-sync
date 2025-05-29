"""Project models."""

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Literal
from typing import Union

import yaml
from loguru import logger

LOG = logger


@dataclass
class Setup:
    """Personal settings for collection."""

    no_collection: Literal['create', 'raise'] = 'raise'
    after_collection: Literal['move', 'delete', 'nothing'] = 'move'
    after_item: Literal['move', 'delete', 'nothing'] = 'move'
    ephemeral: bool = False
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_path(
        cls,
        path: Path,
        filename: str,
        parent_setup: Union['Setup', None] = None,
    ) -> 'Setup':
        """Create instance from given folder."""
        if parent_setup is None:
            setup = {}
        else:
            setup = asdict(parent_setup)

        try:
            with open(path / filename, encoding='utf-8') as fd:
                raw_setup = yaml.safe_load(fd)
        except FileNotFoundError:
            raw_setup = {}

        parent_tags = setup.pop('tags', [])
        raw_tags = raw_setup.pop('tags', [])
        setup.update(raw_setup)

        return cls(**setup, tags=list(set(parent_tags + raw_tags)))
