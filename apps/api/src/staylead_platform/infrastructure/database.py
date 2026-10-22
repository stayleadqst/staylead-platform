"""Lazy SQLAlchemy engine factory; never connects or creates schema during import/startup."""

from sqlalchemy import Engine, create_engine


def create_database_engine(database_url: str) -> Engine:
    """Create an engine handle without opening a connection or creating database objects."""
    return create_engine(database_url, pool_pre_ping=True)
