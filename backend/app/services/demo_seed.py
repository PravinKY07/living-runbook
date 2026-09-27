"""Controlled demo-user seeding for local development and demos."""

from app.services.user_store import SQLiteUserStore


def seed_demo_users(
    store: SQLiteUserStore,
    *,
    editor_email: str,
    editor_password: str,
    approver_email: str,
    approver_password: str,
) -> None:
    """Create or update the two demo users.

    ``create_user`` is an upsert, so an existing row has its role and password
    hash replaced. Re-running this resets the demo passwords to the values
    supplied in the environment.
    """
    store.create_user(editor_email, editor_password, "editor")
    store.create_user(approver_email, approver_password, "approver")
