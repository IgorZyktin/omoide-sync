"""Custom exceptions for the project.
"""


class OmoideSyncException(Exception):
    """General base class for all exceptions."""


class UserRelatedException(OmoideSyncException):
    """Got problem with user."""


class StorageRelatedException(OmoideSyncException):
    """Got problem with storage."""


class NetworkRelatedException(OmoideSyncException):
    """Got problem with network or remote APIs."""
