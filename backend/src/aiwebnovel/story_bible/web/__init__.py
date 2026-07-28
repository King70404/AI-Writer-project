"""Public HTTP adapter for current Story Bible application use cases."""

from aiwebnovel.story_bible.web.history_router import (
    create_story_bible_history_router,
)
from aiwebnovel.story_bible.web.router import create_story_bible_router

__all__ = ["create_story_bible_history_router", "create_story_bible_router"]
