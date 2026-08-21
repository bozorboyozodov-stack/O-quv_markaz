"""
Qo'lda (karta) to'lovni admin tasdiqlagandan/rad etgandan keyingi umumiy logika.

Muhim tamoyil (hujjatning 14-bo'limi — "Payment protection"): kurs FAQAT shu
yerdagi approve_payment() orqali ochiladi — ya'ni faqat ADMIN roli tasdiqlagan
holatda. O'quvchining o'zi "to'ladim" deb yozishi kursni ochmaydi.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Payment, PaymentStatus, Enrollment, User, Course
from utils.format import fmt_money
from utils.roles import get_admin_telegram_ids


async def approve_payment(session: AsyncSession, payment: Payment, admin: User) -> bool:
    """To'lovni PAID qiladi va kursni ochadi (Enrollment yaratadi). Idempotent."""
    if payment.status == PaymentStatus.PAID:
        return True
    if payment.status != PaymentStatus.PENDING:
        return False

    payment.status = PaymentStatus.PAID
    payment.reviewed_by_id = admin.id
    payment.reviewed_at = datetime.now(timezone.utc)

    result = await session.execute(
        select(Enrollment).where(
            Enrollment.student_id == payment.student_id,
            Enrollment.course_id == payment.course_id,
        )
    )
    if not result.scalar_one_or_none():
        session.add(Enrollment(student_id=payment.student_id, course_id=payment.course_id))

    await session.commit()
    return True


async def reject_payment(session: AsyncSession, payment: Payment, admin: User) -> bool:
    if payment.status != PaymentStatus.PENDING:
        return False
    payment.status = PaymentStatus.FAILED
    payment.reviewed_by_id = admin.id
    payment.reviewed_at = datetime.now(timezone.utc)
    await session.commit()
    return True


async def notify_student_approved(bot, session: AsyncSession, payment: Payment) -> None:
    student = await session.get(User, payment.student_id)
    course = await session.get(Course, payment.course_id)
    if not (student and course):
        return
    try:
        await bot.send_message(
            student.telegram_id,
            "✅ Adminlar tomonidan to'lovingiz tasdiqlandi va "
            f"<b>{course.title}</b> nomli kurs sotib olindi.\n\n"
            "👉 '🎓 Mening kurslarim' bo'limidan darslarni boshlang.",
        )
    except Exception:
        pass  # foydalanuvchi botni bloklagan bo'lishi mumkin


async def notify_student_rejected(bot, session: AsyncSession, payment: Payment) -> None:
    student = await session.get(User, payment.student_id)
    course = await session.get(Course, payment.course_id)
    if not (student and course):
        return
    try:
        await bot.send_message(
            student.telegram_id,
            f"❌ <b>{course.title}</b> kursi uchun to'lovingiz rad etildi.\n\n"
            "Sababi: chek noto'g'ri yoki tasdiqlanmadi. Qayta urinib ko'ring "
            "yoki 💬 Yordam bo'limi orqali admin bilan bog'laning.",
        )
    except Exception:
        pass


async def notify_admins_course_sold(bot, session: AsyncSession, payment: Payment) -> None:
    """Kurs sotib olinib, admin tasdiqlagach — barcha adminlarga xabar beradi:
    ism(@username) (kurs nomi) kursini (miqdor) so'mga sotib oldi."""
    student = await session.get(User, payment.student_id)
    course = await session.get(Course, payment.course_id)
    if not (student and course):
        return

    name = student.full_name or "—"
    username = f"@{student.username}" if student.username else "—"
    text = (
        "💰 <b>Yangi sotuv</b>\n"
        f"{name} ({username}) <b>{course.title}</b> kursini "
        f"{fmt_money(payment.amount)}ga sotib oldi."
    )
    admin_ids = await get_admin_telegram_ids()
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass


async def notify_teacher_course_sold(bot, session: AsyncSession, payment: Payment) -> None:
    """O'z yuklagan kursi sotilganda o'qituvchiga xabar beradi."""
    teacher = await session.get(User, payment.teacher_id)
    course = await session.get(Course, payment.course_id)
    student = await session.get(User, payment.student_id)
    if not (teacher and course and student):
        return

    name = student.full_name or "—"
    username = f"@{student.username}" if student.username else "—"
    try:
        await bot.send_message(
            teacher.telegram_id,
            "🎉 <b>Kursingiz sotildi!</b>\n"
            f"{name} ({username}) <b>{course.title}</b> kursini "
            f"{fmt_money(payment.amount)}ga sotib oldi.",
        )
    except Exception:
        pass  # o'qituvchi botni bloklagan bo'lishi mumkin
