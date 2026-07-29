"""Safe framework-independent failures owned by the Character domain."""

from aiwebnovel.character.identifiers import CharacterId
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.project.identifiers import ProjectId


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


class CharacterRepositoryError(CharacterDomainError):
    """Base class for safe Character persistence-boundary failures."""

    code = "character_repository_error"
    message = "The Character persistence operation could not be completed."


class CharacterAlreadyExists(CharacterRepositoryError):
    """Raised when create would reuse a stable Character identity."""

    code = "character_already_exists"
    message = "The Character already exists."

    def __init__(self, character_id: CharacterId) -> None:
        if type(character_id) is not CharacterId:
            raise InvalidCharacterState
        self.character_id = character_id
        super().__init__()


class CharacterProjectNotFound(CharacterRepositoryError):
    """Raised when persistence cannot find the required owning Project."""

    code = "character_project_not_found"
    message = "The owning Project was not found."

    def __init__(self, project_id: ProjectId) -> None:
        if type(project_id) is not ProjectId:
            raise InvalidCharacterState
        self.project_id = project_id
        super().__init__()


class CharacterNotFound(CharacterRepositoryError):
    """Raised when a requested Character cannot be found for a write."""

    code = "character_not_found"
    message = "The Character was not found."

    def __init__(self, character_id: CharacterId) -> None:
        if type(character_id) is not CharacterId:
            raise InvalidCharacterState
        self.character_id = character_id
        super().__init__()


class CharacterDataCorruption(CharacterRepositoryError):
    """Raised when stored rows cannot form one valid current aggregate."""

    code = "character_data_corruption"
    message = "The stored Character state is inconsistent."
