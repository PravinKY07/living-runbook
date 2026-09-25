"""Seed the two demo users without printing passwords or hashes."""

import getpass
import os
import sys

from app.config import get_settings
from app.services.demo_seed import seed_demo_users
from app.services.user_store import SQLiteUserStore


def _read_password(environment_name: str, prompt: str) -> str:
    value = os.getenv(environment_name)
    if value:
        return value
    if not sys.stdin.isatty():
        raise SystemExit(
            f"Set {environment_name} in a private runtime environment before seeding."
        )
    return getpass.getpass(prompt)


def main() -> None:
    editor_password = _read_password(
        "DEMO_EDITOR_PASSWORD",
        "Choose the Editor demo password: ",
    )
    approver_password = _read_password(
        "DEMO_APPROVER_PASSWORD",
        "Choose the Approver demo password: ",
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
