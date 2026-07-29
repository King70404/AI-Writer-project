"""Safe framework-independent failures owned by the Character domain."""

from aiwebnovel.domain.errors import DomainError


class CharacterDomainError(DomainError):
    """Base class for expected Character domain failures."""

    code = "character_domain_error"
    message = "The Character domain operation could not be completed."


class InvalidCharacterName(CharacterDomainError):
    """Raised when a Character name violates its value rules."""

    code = "invalid_character_name"
    message = "The Character name is invalid."


class InvalidCharacterRole(CharacterDomainError):
    """Raised when a Character role violates its value rules."""

    code = "invalid_character_role"
    message = "The Character role is invalid."


class InvalidCharacterProfile(CharacterDomainError):
    """Raised when a Character profile violates its value rules."""

    code = "invalid_character_profile"
    message = "The Character profile is invalid."


class InvalidCharacterState(CharacterDomainError):
    """Raised when Character objects cannot form one valid state."""

    code = "invalid_character_state"
    message = "The Character state is invalid."
