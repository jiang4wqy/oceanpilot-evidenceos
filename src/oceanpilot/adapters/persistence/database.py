"""Database selection and a small DB-API compatibility boundary.

The historic stores intentionally keep their reviewed SQL and transaction
boundaries.  SQLite continues to use the standard library driver.  PostgreSQL
connections are created through SQLAlchemy and expose the subset of the
sqlite3 API used by those stores.  This keeps database selection in the
composition boundary instead of leaking it into the application/domain code.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3 as _sqlite
from collections.abc import Iterator, Mapping, Sequence
from functools import lru_cache
from typing import Any

import psycopg
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

_POSTGRES_SELECTED = (
    os.getenv("OCEANPILOT_DATABASE_BACKEND", "sqlite").strip().lower() == "postgresql"
)
Error = psycopg.Error if _POSTGRES_SELECTED else _sqlite.Error
IntegrityError = psycopg.IntegrityError if _POSTGRES_SELECTED else _sqlite.IntegrityError
OperationalError = psycopg.OperationalError if _POSTGRES_SELECTED else _sqlite.OperationalError
DatabaseError = psycopg.DatabaseError if _POSTGRES_SELECTED else _sqlite.DatabaseError
DataError = psycopg.DataError if _POSTGRES_SELECTED else _sqlite.DataError
ProgrammingError = psycopg.ProgrammingError if _POSTGRES_SELECTED else _sqlite.ProgrammingError
InterfaceError = psycopg.InterfaceError if _POSTGRES_SELECTED else _sqlite.InterfaceError
InternalError = psycopg.InternalError if _POSTGRES_SELECTED else _sqlite.InternalError
NotSupportedError = psycopg.NotSupportedError if _POSTGRES_SELECTED else _sqlite.NotSupportedError
LEGACY_TRANSACTION_CONTROL = getattr(_sqlite, "LEGACY_TRANSACTION_CONTROL", -1)
Row = _sqlite.Row
Connection = Any

_QMARK = re.compile(r"\?")
_NAMED = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")
_INSERT_IGNORE = re.compile(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+", re.I)
_INSERT_REPLACE = re.compile(r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\s+", re.I)


def backend() -> str:
    value = os.getenv("OCEANPILOT_DATABASE_BACKEND", "sqlite").strip().lower()
    if value not in {"sqlite", "postgresql"}:
        raise ValueError("OCEANPILOT_DATABASE_BACKEND must be 'sqlite' or 'postgresql'")
    return value


def database_url() -> str:
    value = os.getenv("OCEANPILOT_DATABASE_URL", "").strip()
    if backend() == "postgresql":
        if not value.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("OCEANPILOT_DATABASE_URL must be a PostgreSQL URL")
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


@lru_cache(maxsize=4)
def _engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, future=True)


def engine() -> Engine:
    return _engine(database_url())


class PostgresRow(Mapping[str, Any], Sequence[Any]):
    def __init__(self, names: Sequence[str], values: Sequence[Any]) -> None:
        self._names = tuple(names)
        self._values = tuple(
            json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            if isinstance(value, (dict, list))
            else value
            for value in values
        )
        self._mapping = dict(zip(self._names, self._values, strict=False))

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._values[key]
        return self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._names)

    def __len__(self) -> int:
        return len(self._values)

    def keys(self):
        return self._mapping.keys()


def _row_factory(cursor):
    names = [column.name for column in (cursor.description or ())]
    return lambda values: PostgresRow(names, values)


def _qmarks(sql: str) -> str:
    result: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(sql):
        char = sql[index]
        if quote:
            result.append(char)
            if char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    result.append(sql[index + 1])
                    index += 1
                else:
                    quote = None
        elif char in {"'", '"'}:
            quote = char
            result.append(char)
        elif char == "?":
            result.append("%s")
        else:
            result.append(char)
        index += 1
    return "".join(result)


def _translate_json(sql: str) -> str:
    expression = r"([A-Za-z0-9_.:%]+)"
    path = r"([A-Za-z0-9_.]+)"
    sql = re.sub(
        rf"json_each\({expression},\s*'\$\.{path}'\)\s+([A-Za-z][A-Za-z0-9_]*)",
        lambda match: (
            f"jsonb_array_elements(({match.group(1)})::jsonb #> "
            f"'{{{match.group(2).replace('.', ',')}}}') AS {match.group(3)}(value)"
        ),
        sql,
        flags=re.I,
    )
    sql = re.sub(
        rf"json_each\({expression}\)",
        lambda match: f"jsonb_array_elements_text(({match.group(1)})::jsonb) AS jitems(value)",
        sql,
        flags=re.I,
    )
    sql = re.sub(
        rf"json_type\({expression},\s*'\$\.{path}'\)",
        lambda match: (
            f"jsonb_typeof(({match.group(1)})::jsonb #> '{{{match.group(2).replace('.', ',')}}}')"
        ),
        sql,
        flags=re.I,
    )
    sql = re.sub(
        rf"json_extract\({expression},\s*'\$\.{path}'\)",
        lambda match: f"(({match.group(1)})::jsonb #>> '{{{match.group(2).replace('.', ',')}}}')",
        sql,
        flags=re.I,
    )
    sql = re.sub(r"\bjson_object\(", "jsonb_build_object(", sql, flags=re.I)
    return sql


def _translate(sql: str) -> str:
    # SQLite permits this circular declaration before the referenced table
    # exists; PostgreSQL does not. The application enforces the same invariant
    # when committing a diagnosis, so omit only this creation-order constraint.
    if re.search(r"CREATE TABLE IF NOT EXISTS cases\s*\(", sql, re.I):
        sql = re.sub(
            r",\s*FOREIGN KEY \(case_id, current_diagnosis_id\).*?DEFERRABLE INITIALLY DEFERRED",
            "",
            sql,
            flags=re.I | re.S,
        )
    sql = re.sub(r"\bBEGIN\s+IMMEDIATE\b", "BEGIN", sql, flags=re.I)
    sql = re.sub(r"\bAUTOINCREMENT\b", "", sql, flags=re.I)
    sql = re.sub(r"INTEGER\s+PRIMARY\s+KEY\s*(?=,|\n|\))", "BIGSERIAL PRIMARY KEY", sql, flags=re.I)
    sql = re.sub(r"\bBLOB\b", "BYTEA", sql, flags=re.I)
    sql = re.sub(r"\browid\b", "ctid", sql, flags=re.I)
    sql = re.sub(r"\bCASE\s+WHEN\s+1\s+THEN\b", "CASE WHEN TRUE THEN", sql, flags=re.I)
    sql = re.sub(r"\bWHERE\s+1\b", "WHERE TRUE", sql, flags=re.I)
    sql = re.sub(r"\bWHERE\s+0\b", "WHERE FALSE", sql, flags=re.I)
    sql = re.sub(r"\bAND\s+1\b", "AND TRUE", sql, flags=re.I)
    sql = re.sub(r"\bAND\s+0\b", "AND FALSE", sql, flags=re.I)
    sql = re.sub(r"\bOR\s+1\b", "OR TRUE", sql, flags=re.I)
    sql = re.sub(r"\bOR\s+0\b", "OR FALSE", sql, flags=re.I)
    sql = re.sub(r"\binstr\(([^,]+),\s*([^\)]+)\)", r"strpos(\1, \2)", sql, flags=re.I)
    sql = re.sub(
        r"julianday\((json_extract\([A-Za-z0-9_.:%]+,\s*'\$\.[A-Za-z0-9_.]+'\))\)",
        r"(EXTRACT(EPOCH FROM (\1)::timestamptz)/86400)",
        sql,
        flags=re.I,
    )
    sql = re.sub(
        r"julianday\(([^,()]+),\s*'\+1 day'\)",
        r"(EXTRACT(EPOCH FROM ((\1)::timestamptz + interval '1 day'))/86400)",
        sql,
        flags=re.I,
    )
    sql = re.sub(
        r"julianday\(([^()]+)\)",
        r"(EXTRACT(EPOCH FROM (\1)::timestamptz)/86400)",
        sql,
        flags=re.I,
    )
    if re.search(r"\bFROM\s+sqlite_schema\b", sql, re.I):
        sql = re.sub(
            r"SELECT\s+name\s+FROM\s+sqlite_schema.*",
            (
                "SELECT table_name AS name FROM information_schema.tables "
                "WHERE table_schema=current_schema()"
            ),
            sql,
            flags=re.I | re.S,
        )
    sql = _translate_json(sql)
    if _INSERT_IGNORE.match(sql):
        sql = _INSERT_IGNORE.sub("INSERT INTO ", sql)
        sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    elif _INSERT_REPLACE.match(sql):
        raise ValueError("INSERT OR REPLACE is not portable; use ON CONFLICT explicitly")
    sql = _NAMED.sub(r"%(\1)s", sql)
    if "%(" not in sql:
        sql = _qmarks(sql)
    return sql


class PostgresCursor:
    def __init__(self, cursor) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return None

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)


class PostgresConnection:
    def __init__(self, database_key: str) -> None:
        self._database_key = database_key
        raw = _engine(database_url()).raw_connection()
        self._raw = raw
        self._connection = getattr(raw, "driver_connection", raw)
        self._connection.autocommit = True
        self._connection.row_factory = _row_factory
        self.row_factory = PostgresRow

    @property
    def in_transaction(self) -> bool:
        return False

    def _pragma(self, sql: str):
        normalized = sql.strip().lower()
        cursor = self._connection.cursor()
        if normalized.startswith("pragma table_info("):
            table = normalized.removeprefix("pragma table_info(").rstrip(") ;")
            cursor.execute(
                "SELECT column_name AS name FROM information_schema.columns "
                "WHERE table_schema=current_schema() AND table_name=%s ORDER BY ordinal_position",
                (table,),
            )
            return PostgresCursor(cursor)
        if normalized.startswith("pragma user_version="):
            version = int(normalized.split("=", 1)[1])
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS oceanpilot_schema_meta "
                "(database_key TEXT PRIMARY KEY, user_version INTEGER NOT NULL)"
            )
            cursor.execute(
                "INSERT INTO oceanpilot_schema_meta VALUES (%s,%s) "
                "ON CONFLICT(database_key) DO UPDATE SET user_version=excluded.user_version",
                (self._database_key, version),
            )
            return PostgresCursor(cursor)
        if normalized == "pragma user_version":
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS oceanpilot_schema_meta "
                "(database_key TEXT PRIMARY KEY, user_version INTEGER NOT NULL)"
            )
            cursor.execute(
                "SELECT COALESCE((SELECT user_version FROM oceanpilot_schema_meta "
                "WHERE database_key=%s),0) AS user_version",
                (self._database_key,),
            )
            return PostgresCursor(cursor)
        if normalized == "pragma foreign_key_check":
            cursor.execute("SELECT NULL AS result WHERE FALSE")
            return PostgresCursor(cursor)
        if normalized == "pragma quick_check":
            cursor.execute("SELECT 'ok' AS result")
            return PostgresCursor(cursor)
        if normalized == "pragma foreign_keys":
            cursor.execute("SELECT 1 AS foreign_keys")
            return PostgresCursor(cursor)
        if normalized == "pragma journal_mode":
            cursor.execute("SELECT 'delete' AS journal_mode")
            return PostgresCursor(cursor)
        cursor.execute("SELECT NULL AS ignored WHERE FALSE")
        return PostgresCursor(cursor)

    def execute(self, sql: str, parameters=()):
        if sql.lstrip().lower().startswith("pragma "):
            return self._pragma(sql)
        cursor = self._connection.cursor()
        cursor.execute(_translate(sql), parameters)
        return PostgresCursor(cursor)

    def executemany(self, sql: str, parameters):
        cursor = self._connection.cursor()
        cursor.executemany(_translate(sql), parameters)
        return PostgresCursor(cursor)

    def executescript(self, script: str):
        cursor = None
        for statement in script.split(";"):
            if statement.strip():
                cursor = self.execute(statement)
        return cursor

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()


def connect(database, *args, **kwargs):
    if backend() == "postgresql":
        return PostgresConnection(str(database))
    return _sqlite.connect(database, *args, **kwargs)
