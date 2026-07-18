"""Framework-independent errors for shared domain primitives."""

from typing import ClassVar


class DomainError(Exception):
    """Base class for expected domain failures with a safe public summary."""

    code: ClassVar[str] = "domain_error"
    message: ClassVar[str] = "The domain operation could not be completed."

    def __init__(self) -> None:
        super().__init__(self.message)


class InvalidDomainIdentifier(DomainError):
    """Raised when an identifier cannot be constructed or parsed safely."""

    code = "invalid_domain_identifier"
    message = "The domain identifier is invalid."


class InvalidRevisionNumber(DomainError):
    """Raised when a revision number is outside its valid domain."""

    code = "invalid_revision_number"
    message = "The revision number is invalid."


class InvalidConcurrencyVersion(DomainError):
    """Raised when a concurrency version is outside its valid domain."""

    code = "invalid_concurrency_version"
    message = "The concurrency version is invalid."


class ConcurrencyConflict(DomainError):
    """Report a safe optimistic-concurrency mismatch without resolving it."""

    code = "concurrency_conflict"
    message = "The expected concurrency version does not match the current version."

    def __init__(self, *, expected_version: int, actual_version: int) -> None:
        if (
            isinstance(expected_version, bool)
            or not isinstance(expected_version, int)
            or expected_version < 1
            or isinstance(actual_version, bool)
            or not isinstance(actual_version, int)
            or actual_version < 1
        ):
            raise InvalidConcurrencyVersion
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__()
