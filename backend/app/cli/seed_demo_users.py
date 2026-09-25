"""Seed the two demo users without printing passwords or hashes."""

import os

from app.config import get_settings
from app.services.demo_seed import seed_demo_users
from app.services.user_store import SQLiteUserStore


def main() -> None:
    editor_password = os.getenv("DEMO_EDITOR_PASSWORD")
    approver_password = os.getenv("DEMO_APPROVER_PASSWORD")

    if not editor_password or not approver_password:
        raise SystemExit(
            "Set DEMO_EDITOR_PASSWORD and DEMO_APPROVER_PASSWORD before seeding."
        )

    settings = get_settings()
    store = SQLiteUserStore(settings.database_path)
    seed_demo_users(
        store,
        editor_email="editor@example.test",
        editor_password=editor_password,
        approver_email="approver@example.test",
        approver_password=approver_password,
    )
    print("Demo users seeded.")


if __name__ == "__main__":
    main()
