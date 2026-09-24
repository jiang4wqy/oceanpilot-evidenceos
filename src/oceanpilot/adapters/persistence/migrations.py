"""Alembic/SQLAlchemy migration marker for the shared PostgreSQL backend."""

from __future__ import annotations

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from oceanpilot.adapters.persistence.database import backend, database_url

REVISION = "20260924_distribution_v1"


def upgrade_database() -> None:
    """Apply the distributable schema baseline once before store migrations."""
    if backend() != "postgresql":
        return
    # Use a dedicated SQLAlchemy pool: compatibility connections install a
    # sqlite-like row factory on their raw psycopg connection.
    selected_engine = create_engine(database_url(), pool_pre_ping=True, future=True)
    with selected_engine.begin() as connection:
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        if "alembic_version" not in inspect(connection).get_table_names():
            operations.create_table(
                "alembic_version",
                sa.Column("version_num", sa.String(64), primary_key=True, nullable=False),
            )
            connection.execute(
                sa.text("INSERT INTO alembic_version(version_num) VALUES (:revision)"),
                {"revision": REVISION},
            )
            return
        current = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
        if current != REVISION:
            raise RuntimeError("unsupported OceanPilot database revision")
