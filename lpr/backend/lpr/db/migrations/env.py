from alembic import context
from sqlalchemy import create_engine

from lpr.db.models import Base

target_metadata = Base.metadata
config = context.config


def run_migrations_online() -> None:
    conn = config.attributes.get("connection")
    if conn is None:
        url = config.get_main_option("sqlalchemy.url")
        eng = create_engine(url)
        with eng.connect() as c:
            context.configure(connection=c, target_metadata=target_metadata, render_as_batch=True)
            with context.begin_transaction():
                context.run_migrations()
        return
    context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
