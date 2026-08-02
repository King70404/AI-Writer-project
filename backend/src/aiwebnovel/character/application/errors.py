"""Safe Character failures that exist only at the application boundary."""

from aiwebnovel.character.identifiers import CharacterId
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber


class CharacterRevisionNotFound(DomainError):
    code = "character_revision_not_found"
    message = "The Character revision was not found."

    def __init__(self, character_id: CharacterId, revision_number: RevisionNumber) -> None:
        if type(character_id) is not CharacterId or type(revision_number) is not RevisionNumber:
            raise TypeError("character_id and revision_number must be exact domain values")
        self.character_id = character_id
        self.revision_number = revision_number
        super().__init__()


__all__ = ["CharacterRevisionNotFound"]
