"""Public Character HTTP adapter factory."""

from aiwebnovel.character.web.history_router import create_character_history_router
from aiwebnovel.character.web.router import create_character_router

__all__ = ["create_character_history_router", "create_character_router"]
