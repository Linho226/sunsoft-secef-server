from sqlalchemy import inspect

from sunsoft_secef_server.storage.database import Database


def test_database_initialization(
    tmp_path,
) -> None:
    database_path = (
        tmp_path
        / "central-test.db"
    )

    database = Database(
        f"sqlite:///{database_path}"
    )

    try:
        database.initialize()

        inspector = inspect(
            database.engine
        )

        tables = set(
            inspector.get_table_names()
        )

        assert "agents" in tables
        assert "certification_requests" in tables
        assert "central_jobs" in tables

    finally:
        database.dispose()


def test_database_creates_parent_directory(
    tmp_path,
) -> None:
    database_path = (
        tmp_path
        / "nested"
        / "central.db"
    )

    database = Database(
        f"sqlite:///{database_path}"
    )

    try:
        database.initialize()

        assert database_path.exists()

    finally:
        database.dispose()