from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class UserRecord:
    """A user record used inside the backend only."""

    id: int
    email: str
    role: str
    password_hash: str = field(repr=False)
