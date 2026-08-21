"""
Admin panel — "💰 Daromad" bo'limi uchun yordamchi.

Bu yerda hisoblanadigan summalar — barcha tasdiqlangan (PAID) to'lovlarning
YALPI (gross) summasi, ya'ni o'qituvchi ulushi + admin ulushi qo'shilgan
holda — talabalardan jami qancha pul tushgani.
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Payment, PaymentStatus


async def get_income_summary(session: AsyncSession) -> dict:
    """Qaytaradi: today, week, month, all_time — har biri shu davr ichida
    tasdiqlangan to'lovlar summasi (so'mda)."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())  # dushanbadan
    month_start = today_start.replace(day=1)

    async def _sum_since(dt: datetime) -> int:
        result = await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == PaymentStatus.PAID,
                func.coalesce(Payment.reviewed_at, Payment.created_at) >= dt,
            )
        )
        return result.scalar_one()

    all_time = (await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == PaymentStatus.PAID)
    )).scalar_one()

    return {
        "today": await _sum_since(today_start),
        "week": await _sum_since(week_start),
        "month": await _sum_since(month_start),
        "all_time": all_time,
    }
