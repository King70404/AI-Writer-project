"""Public HTTP adapters for current novel-structure resources."""

from aiwebnovel.novel_structure.web.content_router import create_chapter_content_router
from aiwebnovel.novel_structure.web.router import create_novel_structure_router

__all__ = ["create_chapter_content_router", "create_novel_structure_router"]
