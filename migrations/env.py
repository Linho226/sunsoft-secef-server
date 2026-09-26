from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from sunsoft_secef_server.config import get_settings
from sunsoft_secef_server.storage.models import Base


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


settings = get_settings()

config.set_main_option(
    "sqlalchemy.url",
    settings.database_url,
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Ex?cute les migrations sans connexion active."""

    url = config.get_main_option(
        "sqlalchemy.url"
    )

    is_sqlite = url.startswith("sqlite:")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        render_as_batch=is_sqlite,
        dialect_opts={
            "paramstyle": "named",
        },
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Ex?cute les migrations avec connexion DB."""

    connectable = engine_from_config(
        config.get_section(
            config.config_ini_section,
            {}
        ),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        is_sqlite = (
            connection.dialect.name == "sqlite"
        )

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=is_sqlite,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
