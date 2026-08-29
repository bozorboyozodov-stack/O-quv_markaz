from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import DATABASE_URL
from database.models import Base

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def _run_light_migrations(conn) -> None:
    """create_all() faqat YANGI jadvallarni yaratadi, mavjud jadvalga yangi
    ustun qo'shmaydi. Shu sabab avval deploy qilingan bazalarda ham
    ishlashi uchun yetishmayotgan ustunlarni qo'lda tekshirib qo'shamiz.
    Har ikkala dialektda (SQLite va PostgreSQL) ishlaydi."""
    dialect = conn.dialect.name

    if dialect == "sqlite":
        result = await conn.execute(text("PRAGMA table_info(users)"))
        existing_cols = {row[1] for row in result.fetchall()}
    else:
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"
        ))
        existing_cols = {row[0] for row in result.fetchall()}

    if existing_cols and "subject" not in existing_cols:
        await conn.execute(text("ALTER TABLE users ADD COLUMN subject VARCHAR(255) DEFAULT ''"))


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _run_light_migrations(conn)
