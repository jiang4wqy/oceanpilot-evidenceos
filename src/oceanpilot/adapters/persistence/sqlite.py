import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from oceanpilot.adapters.persistence.schema import REQUIRED_TABLES, SCHEMA_SQL
from oceanpilot.application.errors import DatabaseUnavailable


def connect_sqlite(path: Path) -> sqlite3.Connection:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            str(path),
            timeout=5.0,
            isolation_level=None,
            autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        foreign_keys_row = connection.execute("PRAGMA foreign_keys").fetchone()
        journal_mode_row = connection.execute("PRAGMA journal_mode").fetchone()
        if (
            foreign_keys_row is None
            or foreign_keys_row[0] != 1
            or journal_mode_row is None
            or journal_mode_row[0] != "delete"
        ):
            connection.close()
            raise DatabaseUnavailable()
        return connection
    except sqlite3.Error:
        if connection is not None:
            connection.close()
        raise DatabaseUnavailable() from None


def initialize_schema(path: Path) -> None:
    connection: sqlite3.Connection | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = connect_sqlite(path)
        connection.executescript(f"BEGIN IMMEDIATE;\n{SCHEMA_SQL}\nCOMMIT;")
        table_names = frozenset(
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_schema
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        )
        if table_names != REQUIRED_TABLES:
            raise DatabaseUnavailable()
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise DatabaseUnavailable()
    except (OSError, sqlite3.Error, DatabaseUnavailable):
        raise DatabaseUnavailable() from None
    finally:
        if connection is not None:
            connection.close()


@contextmanager
def immediate_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise


class SqliteCaseStoreSession:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def healthcheck(self) -> None:
        try:
            table_names = frozenset(
                row["name"]
                for row in self._connection.execute(
                    """
                    SELECT name
                    FROM sqlite_schema
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                )
            )
            if not REQUIRED_TABLES.issubset(table_names):
                raise DatabaseUnavailable()
            self._connection.execute("SELECT case_id FROM cases LIMIT 0")
            if (
                self._connection.execute("PRAGMA foreign_key_check").fetchone()
                is not None
            ):
                raise DatabaseUnavailable()
        except sqlite3.Error:
            raise DatabaseUnavailable() from None


class SqliteCaseStoreFactory:
    def __init__(self, path: Path) -> None:
        self._path = path

    @contextmanager
    def __call__(self) -> Iterator[SqliteCaseStoreSession]:
        connection = connect_sqlite(self._path)
        try:
            yield SqliteCaseStoreSession(connection)
        finally:
            connection.close()
