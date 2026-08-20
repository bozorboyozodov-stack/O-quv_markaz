from sqlalchemy import select

from database.db import async_session
from database.models import User, RoleEnum
from config import ADMIN_IDS, OWNER_ID


async def get_or_create_user(telegram_id: int, full_name: str, username: str) -> User:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user:
            return user

        role = RoleEnum.ADMIN if telegram_id in ADMIN_IDS else RoleEnum.STUDENT
        user = User(
            telegram_id=telegram_id,
            full_name=full_name or "",
            username=username or "",
            role=role,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def get_user(telegram_id: int) -> User | None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()


async def get_admin_telegram_ids() -> list[int]:
    """Barcha ADMIN rolidagi foydalanuvchilar (umumiy e'lonlar uchun kerak bo'lsa)."""
    async with async_session() as session:
        result = await session.execute(select(User.telegram_id).where(User.role == RoleEnum.ADMIN))
        return [row[0] for row in result.all()]


async def get_owner_telegram_id() -> int | None:
    """To'lov cheklarini tekshirish so'rovlari FAQAT shu (asosiy egasi)
    Telegram ID'ga boradi — boshqa adminlarga emas. config.OWNER_ID orqali
    sozlanadi (agar sozlanmagan bo'lsa, ADMIN_IDS ro'yxatidagi birinchisi)."""
    return OWNER_ID or None
