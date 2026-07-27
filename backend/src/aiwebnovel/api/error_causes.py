"""Safe exception classification helpers for HTTP persistence boundaries."""


def has_database_driver_cause(exc: BaseException) -> bool:
    """Return whether an error directly wraps the configured database driver."""
    cause = exc.__cause__
    return cause is not None and type(cause).__module__.startswith("sqlalchemy.")


__all__ = ["has_database_driver_cause"]
