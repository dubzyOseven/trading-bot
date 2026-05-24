from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Create all tables on startup (use Alembic for production migrations)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_trades_position_id_column)


def _ensure_trades_position_id_column(connection) -> None:
    from sqlalchemy import inspect, text

    if "trades" not in inspect(connection).get_table_names():
        return
    columns = {c["name"] for c in inspect(connection).get_columns("trades")}
    if "position_id" in columns:
        return
    connection.execute(text("ALTER TABLE trades ADD COLUMN position_id VARCHAR(64)"))
    connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_trades_position_id ON trades (position_id)")
    )


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
