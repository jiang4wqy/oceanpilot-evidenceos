"""Local trusted accounts and opaque, revocable V2.1 browser sessions.

Account provisioning is an explicit administration operation. No account or
role is inferred from an HTTP header, route, merchant field, or browser state.
"""

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from oceanpilot.domain.dispute import DisputeError, require

ACCOUNT_ROLES = frozenset(
    {"MERCHANT", "OPERATOR", "RISK_OFFICER", "SUPERVISOR", "ADMIN", "DIRECTOR"}
)
SESSION_COOKIE = "oceanpilot_session"
PASSWORD_ITERATIONS = 600_000


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), PASSWORD_ITERATIONS
    )
    return f"pbkdf2-sha256:{PASSWORD_ITERATIONS}:{salt}:{derived.hex()}"


def _password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split(":")
        if algorithm != "pbkdf2-sha256" or int(iterations) != PASSWORD_ITERATIONS:
            return False
        result = _password_hash(password, salt).rsplit(":", 1)[1]
        return hmac.compare_digest(result, expected)
    except (ValueError, TypeError):
        return False


class SQLiteDisputeIdentity:
    def __init__(self, db_path: str | Path, *, clock=time.time) -> None:
        self.db_path = str(db_path)
        self.clock = clock
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS v21_users (
                    user_id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL, role TEXT NOT NULL,
                    merchant_id TEXT, merchant_ids TEXT NOT NULL,
                    password_hash TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v21_sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    created_at REAL NOT NULL, last_seen_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES v21_users(user_id)
                );
                CREATE INDEX IF NOT EXISTS v21_session_user ON v21_sessions(user_id);
                CREATE TABLE IF NOT EXISTS v21_login_attempts (
                    attempt_key TEXT PRIMARY KEY, failures INTEGER NOT NULL,
                    window_start REAL NOT NULL
                );
            """)
            connection.commit()
        # Unknown accounts do equivalent password work without exposing existence.
        self._dummy_hash = _password_hash("unusable-account-password", "00" * 16)

    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _public(row) -> dict:
        return {
            "id": row["user_id"],
            "user_id": row["user_id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
            "merchant_id": row["merchant_id"],
            "merchant_ids": json.loads(row["merchant_ids"]),
            "disabled": bool(row["disabled"]),
        }

    def create_user(
        self,
        *,
        username: str,
        password: str,
        display_name: str,
        role: str,
        merchant_id: str | None = None,
        merchant_ids: list[str] | None = None,
        user_id: str | None = None,
    ) -> dict:
        from uuid import uuid4

        require(role in ACCOUNT_ROLES, "INVALID_ROLE", "不支持此账号角色。", 422)
        require(
            isinstance(username, str) and 3 <= len(username.strip()) <= 80,
            "INVALID_USERNAME",
            "账号名称长度须为 3–80。",
            422,
        )
        require(
            isinstance(password, str) and 12 <= len(password) <= 128,
            "INVALID_PASSWORD",
            "密码长度须为 12–128。",
            422,
        )
        require(
            isinstance(display_name, str) and 1 <= len(display_name.strip()) <= 80,
            "INVALID_DISPLAY_NAME",
            "请填写使用者姓名。",
            422,
        )
        scope = sorted(set(merchant_ids or ([] if merchant_id is None else [merchant_id])))
        require(
            all(isinstance(item, str) and 0 < len(item) <= 100 for item in scope),
            "INVALID_SCOPE",
            "商户授权范围不合法。",
            422,
        )
        if role == "MERCHANT":
            require(
                isinstance(merchant_id, str) and scope == [merchant_id],
                "INVALID_SCOPE",
                "商户账号必须绑定且只能绑定本人商户。",
                422,
            )
        elif role != "DIRECTOR":
            require(bool(scope), "INVALID_SCOPE", "请明确该员工获授权的商户范围。", 422)
        identifier = user_id or str(uuid4())
        require(
            isinstance(identifier, str)
            and 0 < len(identifier) <= 100
            and not identifier.startswith(("oceanpilot-", "synthetic-")),
            "INVALID_USER_ID",
            "账号标识不合法或为系统保留标识。",
            422,
        )
        encoded = _password_hash(password)
        with closing(self._connect()) as connection:
            try:
                connection.execute(
                    "INSERT INTO v21_users VALUES (?,?,?,?,?,?,?,0,?)",
                    (
                        identifier,
                        username.strip().casefold(),
                        display_name.strip(),
                        role,
                        merchant_id if role == "MERCHANT" else None,
                        json.dumps(scope),
                        encoded,
                        self.clock(),
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise DisputeError("ACCOUNT_EXISTS", "该账号已存在。", 409) from exc
        return self.get_user(identifier)

    def get_user(self, user_id: str) -> dict | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM v21_users WHERE user_id=?", (user_id,)
            ).fetchone()
            return self._public(row) if row else None

    def list_users(self) -> list[dict]:
        with closing(self._connect()) as connection:
            return [
                self._public(row)
                for row in connection.execute("SELECT * FROM v21_users ORDER BY username")
            ]

    def set_disabled(self, user_id: str, disabled: bool) -> None:
        with closing(self._connect()) as connection:
            found = connection.execute(
                "UPDATE v21_users SET disabled=? WHERE user_id=?", (int(disabled), user_id)
            )
            require(found.rowcount == 1, "NOT_FOUND", "账号不存在。", 404)
            if disabled:
                connection.execute("DELETE FROM v21_sessions WHERE user_id=?", (user_id,))
            connection.commit()

    def _attempt_keys(self, username: str, remote: str):
        return ((_digest("user:" + username), 5), (_digest("remote:" + remote), 30))

    def login(self, username: str, password: str, *, remote: str = "local") -> tuple[str, dict]:
        require(
            isinstance(username, str)
            and len(username) <= 80
            and isinstance(password, str)
            and len(password) <= 128,
            "LOGIN_FAILED",
            "账号或密码不正确。",
            401,
        )
        username = username.strip().casefold()
        now = self.clock()
        keys = self._attempt_keys(username, remote)
        with closing(self._connect()) as connection:
            for key, limit in keys:
                row = connection.execute(
                    "SELECT * FROM v21_login_attempts WHERE attempt_key=?", (key,)
                ).fetchone()
                require(
                    row is None or now - row["window_start"] >= 300 or row["failures"] < limit,
                    "LOGIN_RATE_LIMIT",
                    "登录尝试过于频繁，请五分钟后重试。",
                    429,
                )
            account = connection.execute(
                "SELECT * FROM v21_users WHERE username=?", (username,)
            ).fetchone()
            valid = _password_matches(
                password, account["password_hash"] if account else self._dummy_hash
            )
            if not valid or account is None or account["disabled"]:
                for key, _ in keys:
                    connection.execute(
                        "INSERT INTO v21_login_attempts VALUES (?,1,?) ON CONFLICT(attempt_key) "
                        "DO UPDATE SET failures=CASE WHEN excluded.window_start-window_start>=300 "
                        "THEN 1 ELSE failures+1 END, "
                        "window_start=CASE WHEN excluded.window_start-window_start>=300 "
                        "THEN excluded.window_start ELSE window_start END",
                        (key, now),
                    )
                connection.commit()
                raise DisputeError("LOGIN_FAILED", "账号或密码不正确。", 401)
            connection.execute("DELETE FROM v21_login_attempts WHERE attempt_key=?", (keys[0][0],))
            token = secrets.token_urlsafe(32)
            connection.execute("DELETE FROM v21_sessions WHERE expires_at<=?", (now,))
            connection.execute(
                "INSERT INTO v21_sessions VALUES (?,?,?,?,?)",
                (_digest(token), account["user_id"], now, now, now + 8 * 3600),
            )
            connection.commit()
            return token, self._public(account)

    @staticmethod
    def csrf_token(token: str) -> str:
        return _digest("oceanpilot-csrf:" + token)

    def resolve(self, token: str | None) -> dict:
        require(
            isinstance(token, str) and 32 <= len(token) <= 128, "UNAUTHENTICATED", "请先登录。", 401
        )
        now = self.clock()
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT u.*, s.last_seen_at, s.expires_at FROM v21_sessions s "
                "JOIN v21_users u ON u.user_id=s.user_id WHERE s.token_hash=?",
                (_digest(token),),
            ).fetchone()
            require(
                row is not None
                and not row["disabled"]
                and row["expires_at"] > now
                and row["last_seen_at"] + 3600 > now,
                "SESSION_EXPIRED",
                "登录已失效，请重新登录。",
                401,
            )
            if now - row["last_seen_at"] >= 60:
                connection.execute(
                    "UPDATE v21_sessions SET last_seen_at=? WHERE token_hash=?",
                    (now, _digest(token)),
                )
                connection.commit()
            return self._public(row)

    def logout(self, token: str | None) -> None:
        if token:
            with closing(self._connect()) as connection:
                connection.execute("DELETE FROM v21_sessions WHERE token_hash=?", (_digest(token),))
                connection.commit()

    def authenticate(
        self, token: str | None, *, csrf: str | None = None, write: bool = False
    ) -> dict:
        user = self.resolve(token)
        if write:
            require(
                isinstance(csrf, str) and hmac.compare_digest(csrf, self.csrf_token(token)),
                "CSRF_REJECTED",
                "页面确认信息已失效，请重新打开当前页面。",
                403,
            )
        return {
            "role": user["role"],
            "actor_id": user["id"],
            "merchant_id": user["merchant_id"],
            "user": user,
        }
