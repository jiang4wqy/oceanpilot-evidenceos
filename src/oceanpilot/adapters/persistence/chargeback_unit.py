"""Borrow a Chargeback transaction without changing Foundation transactions."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from oceanpilot.adapters.persistence.sqlite import immediate_transaction


class BorrowedConnection:
    """Adapters can reuse their normal methods inside a command's transaction."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def __getattr__(self, name: str):
        return getattr(self.connection, name)

    def close(self) -> None:
        # The owning command commits/rolls back and closes the real connection.
        pass


@contextmanager
def chargeback_transaction(connection) -> Iterator[None]:
    if isinstance(connection, BorrowedConnection):
        if not connection.connection.in_transaction:
            raise RuntimeError("borrowed connection requires an owning transaction")
        yield
    else:
        with immediate_transaction(connection):
            yield
