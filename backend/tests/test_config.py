from pathlib import Path

from app.config import BACKEND_ROOT, Settings


def test_relative_database_path_is_independent_of_shell_directory():
    settings = Settings(_env_file=None, database_path="./data/example.db")

    assert Path(settings.database_path) == (BACKEND_ROOT / "data" / "example.db").resolve()


def test_absolute_database_path_is_preserved(tmp_path):
    absolute_path = tmp_path / "runbooks.db"

    settings = Settings(_env_file=None, database_path=str(absolute_path))

    assert Path(settings.database_path) == absolute_path
