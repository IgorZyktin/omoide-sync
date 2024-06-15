"""Project models."""
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Optional
from uuid import UUID


@dataclass
class User:
    """User representation."""
    name: str
    login: str
    password: str
    root_item: UUID


@dataclass
class Setup:
    """Personal settings for a collection."""
    termination_strategy_collection: str = 'move'
    termination_strategy_item: str = 'move'
    treat_as_collection: bool = True
    tags: list[str] = field(default_factory=list)
    upload_limit: int = -1

    def model_dump(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class Item:
    """Item representation."""
    uuid: UUID | None
    owner: User
    name: str
    parent: Optional['Item']
    children: list['Item']
    is_collection: bool
    uploaded: int
    setup: Setup

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f'<Item({self.name}, '
            f'children={len(self.children)}, '
            f'parent={self.parent}>'
        )

    def __str__(self) -> str:
        """Return string representation."""
        return f'<{self.uuid} {self.name}>'

    @property
    def uploaded_enough(self) -> bool:
        """Return True if we're reached the upload limit."""
        enough = all(
            (
                self.setup.upload_limit > 0,
                self.uploaded >= self.setup.upload_limit
            )
        )

        if enough:
            return True

        if self.parent:
            return self.parent.uploaded_enough

        return False

    @property
    def ancestors(self) -> list['Item']:
        """Return all parent items."""
        ancestors: list[Item] = []
        parent = self.parent

        while parent:
            ancestors.append(parent)
            parent = parent.parent

        return list(reversed(ancestors))

    @property
    def real_parent(self) -> Optional['Item']:
        """Return first parent that is treated as a collection."""
        parent = self.parent

        while parent:
            if parent.setup.treat_as_collection:
                return parent

            parent = parent.parent

        return parent
