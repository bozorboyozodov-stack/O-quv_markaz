"""
Hujjatning 10-bo'limi — "Pul yechish tizimi".

Muhim tamoyil: o'qituvchi balansidagi puldan ko'p yecha olmasligi kerak.
Balans = (barcha PAID to'lovlardan 50% ulush) - (PENDING + APPROVED
so'rovlar yig'indisi). PENDING so'rovlar ham hisobga olinadi — shunda
o'qituvchi bir nechta so'rovni ketma-ket yuborib, balansidan ko'p pul
"band" qilib qo'ya olmaydi.
"""
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Payment, PaymentStatus, Withdrawal, WithdrawalStatus, User


async def get_teacher_balance(session: AsyncSession, teacher_id: int) -> dict:
    """Qaytaradi: total_earned (50% ulush), reserved (PENDING+APPROVED so'rovlar),
    available (yechib olish mumkin bo'lgan qoldiq), approved_total (haqiqatda
    tasdiqlanib to'langan)."""
    total_sales = (await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.teacher_id == teacher_id, Payment.status == PaymentStatus.PAID
        )
    )).scalar_one()
    total_earned = round(total_sales * 0.5)

    reserved = (await session.execute(
        select(func.coalesce(func.sum(Withdrawal.amount), 0)).where(
            Withdrawal.teacher_id == teacher_id,
            Withdrawal.status.in_([WithdrawalStatus.PENDING, WithdrawalStatus.APPROVED]),
        )
    )).scalar_one()

    approved_total = (await session.execute(
        select(func.coalesce(func.sum(Withdrawal.amount), 0)).where(
            Withdrawal.teacher_id == teacher_id, Withdrawal.status == WithdrawalStatus.APPROVED
        )
    )).scalar_one()

    return {
        "total_earned": total_earned,
        "reserved": reserved,
        "available": max(total_earned - reserved, 0),
        "approved_total": approved_total,
    }


async def get_admin_balance(session: AsyncSession) -> dict:
    """Admin hisobidagi pul (masalan: kurs 299 000 so'mga sotilsa, o'qituvchiga
    50% beriladi, qolgan 50% adminda qoladi).

    Qaytaradi:
    - total_paid: barcha tasdiqlangan (PAID) to'lovlarning yalpi summasi
    - teacher_share_total: shundan o'qituvchilarga tegishli ulush (jami)
    - admin_share: adminning sof ulushi (total_paid - teacher_share_total) —
      har doim adminda qoladigan foyda
    - withdrawn_to_teachers: o'qituvchilarga allaqachon to'langan (APPROVED
      pul yechish so'rovlari) summasi
    - cash_on_hand: hozirda admin hisobida (jismoniy) turgan pul — ya'ni
      tushgan pulning o'qituvchilarga hali to'lanmagan qismi ham shu yerda
      turibdi (total_paid - withdrawn_to_teachers)
    """
    total_paid = (await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == PaymentStatus.PAID)
    )).scalar_one()

    teacher_ids = (await session.execute(
        select(Payment.teacher_id).where(Payment.status == PaymentStatus.PAID).distinct()
    )).scalars().all()

    teacher_share_total = 0
    for teacher_id in teacher_ids:
        balance = await get_teacher_balance(session, teacher_id)
        teacher_share_total += balance["total_earned"]

    withdrawn_to_teachers = (await session.execute(
        select(func.coalesce(func.sum(Withdrawal.amount), 0)).where(
            Withdrawal.status == WithdrawalStatus.APPROVED
        )
    )).scalar_one()

    return {
        "total_paid": total_paid,
        "teacher_share_total": teacher_share_total,
        "admin_share": total_paid - teacher_share_total,
        "withdrawn_to_teachers": withdrawn_to_teachers,
        "cash_on_hand": total_paid - withdrawn_to_teachers,
    }


async def approve_withdrawal(session: AsyncSession, withdrawal: Withdrawal, admin: User) -> bool:
    if withdrawal.status != WithdrawalStatus.PENDING:
        return False
    withdrawal.status = WithdrawalStatus.APPROVED
    withdrawal.reviewed_by_id = admin.id
    withdrawal.reviewed_at = datetime.now(timezone.utc)
    await session.commit()
    return True


async def reject_withdrawal(session: AsyncSession, withdrawal: Withdrawal, admin: User, reason: str) -> bool:
    if withdrawal.status != WithdrawalStatus.PENDING:
        return False
    withdrawal.status = WithdrawalStatus.REJECTED
    withdrawal.reject_reason = reason
    withdrawal.reviewed_by_id = admin.id
    withdrawal.reviewed_at = datetime.now(timezone.utc)
    await session.commit()
    return True


async def notify_teacher_withdrawal_approved(bot, session: AsyncSession, withdrawal: Withdrawal) -> None:
    from utils.format import fmt_money

    teacher = await session.get(User, withdrawal.teacher_id)
    if not teacher:
        return
    try:
        await bot.send_message(
            teacher.telegram_id,
            f"✅ Sizning <b>{fmt_money(withdrawal.amount)}</b> pul yechib olish haqidagi "
            "arizangiz tasdiqlandi.\n\n"
            f"💳 Ko'rsatgan kartangizga (<code>{withdrawal.card_number}</code>) tez orada "
            "o'tkazma amalga oshiriladi.",
        )
    except Exception:
        pass  # foydalanuvchi botni bloklagan bo'lishi mumkin


async def notify_teacher_withdrawal_rejected(bot, session: AsyncSession, withdrawal: Withdrawal) -> None:
    from utils.format import fmt_money

    teacher = await session.get(User, withdrawal.teacher_id)
    if not teacher:
        return
    try:
        await bot.send_message(
            teacher.telegram_id,
            f"❌ Sizning <b>{fmt_money(withdrawal.amount)}</b> sum pul yechib olish haqidagi "
            "arizangiz tasdiqlanmadi.\n\n"
            f"Sababi: {withdrawal.reject_reason or '—'}",
        )
    except Exception:
        pass
