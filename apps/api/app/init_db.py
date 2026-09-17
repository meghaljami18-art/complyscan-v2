"""Explicit one-off table bootstrap; run in release tooling, never at ASGI import."""
from __future__ import annotations

from .config import get_settings
from .repository import Base, SQLAlchemyRepository


def main() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is required")
    repository = SQLAlchemyRepository(settings.database_url)
    Base.metadata.create_all(repository.engine)


if __name__ == "__main__":
    main()
