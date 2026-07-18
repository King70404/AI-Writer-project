"""Declarative metadata root populated only by explicit model registration."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base referenced by Alembic."""
