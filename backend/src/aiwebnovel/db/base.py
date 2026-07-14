"""Declarative metadata root for future authorized database models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Empty SQLAlchemy declarative base referenced by Alembic."""
