from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserRecord:
    """A user record safe to return to the application layer."""

    id: int
    email: str
    role: str
    password_hash: str
