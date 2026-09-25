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
    """Create the two demo users if they do not already exist."""
    store.create_user(editor_email, editor_password, "editor")
    store.create_user(approver_email, approver_password, "approver")
