"""Custom exceptions for the project."""


class OmoideSyncError(Exception):
    """General base class for all exceptions."""


class ConfigRelatedError(OmoideSyncError):
    """Got problem with config."""


class UserRelatedError(OmoideSyncError):
    """Got problem with user."""


class StorageRelatedError(OmoideSyncError):
    """Got problem with storage."""


class NetworkRelatedError(OmoideSyncError):
    """Got problem with network or remote APIs."""
