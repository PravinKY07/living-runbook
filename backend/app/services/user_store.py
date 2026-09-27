"""SQLite-backed user storage for the MVP."""

import sqlite3
from pathlib import Path
from threading import RLock

from app.models.user import UserRecord
from app.security.passwords import hash_password


class SQLiteUserStore:
    """Small synchronous store used by the MVP authentication flow."""

    def __init__(self, database_path: str) -> None:
        self._database_path = database_path
        self._lock = RLock()
        self._connection: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        with self._lock:
            if self._connection is None:
                if self._database_path != ":memory:":
                    Path(self._database_path).parent.mkdir(parents=True, exist_ok=True)
                self._connection = sqlite3.connect(
                    self._database_path,
                    check_same_thread=False,
                )
                self._connection.row_factory = sqlite3.Row
            return self._connection

    def initialize(self) -> None:
        """Create the users table if it does not exist."""
        with self._lock:
            connection = self._connect()
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL,
                    password_hash TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def create_user(self, email: str, password: str, role: str) -> UserRecord:
        """Create a user with an Argon2-hashed password."""
        normalized_email = email.strip().lower()
        with self._lock:
            self.initialize()
            connection = self._connect()
            connection.execute(
                """
                INSERT INTO users (email, role, password_hash)
                VALUES (?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    role = excluded.role,
                    password_hash = excluded.password_hash
                """,
                (normalized_email, role, hash_password(password)),
            )
            connection.commit()
            user = self.get_by_email(normalized_email)
            if user is None:
                raise RuntimeError("User could not be created")
            return user

    def get_by_email(self, email: str) -> UserRecord | None:
        """Find a user by normalized email address."""
        with self._lock:
            self.initialize()
            row = self._connect().execute(
                "SELECT id, email, role, password_hash FROM users WHERE email = ?",
                (email.strip().lower(),),
            ).fetchone()
            return self._to_record(row) if row else None

    def get_by_id(self, user_id: int) -> UserRecord | None:
        """Find a user by database ID."""
        with self._lock:
            self.initialize()
            row = self._connect().execute(
                "SELECT id, email, role, password_hash FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            return self._to_record(row) if row else None

    @staticmethod
    def _to_record(row: sqlite3.Row) -> UserRecord:
        return UserRecord(
            id=row["id"],
            email=row["email"],
            role=row["role"],
            password_hash=row["password_hash"],
        )
