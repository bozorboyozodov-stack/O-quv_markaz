"""
Butun bot bo'ylab bir xil, premium ko'rinish uchun umumiy formatlash
yordamchilari. Har bir handler shu yerdan foydalanadi — shunda pul
summasi, status belgilari va ajratuvchi chiziqlar hamma joyda bir xil
ko'rinadi.
"""

from database.models import CourseStatus, PaymentStatus

DIVIDER = "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈"

COURSE_STATUS_LABEL = {
    CourseStatus.PENDING: "🟡 Moderatsiyada",
    CourseStatus.APPROVED: "✅ Faol",
    CourseStatus.HIDDEN: "🙈 Yashirilgan",
    CourseStatus.REJECTED: "❌ Rad etilgan",
}

PAYMENT_STATUS_LABEL = {
    PaymentStatus.PENDING: "🟡 Kutilmoqda",
    PaymentStatus.PAID: "✅ To'langan",
    PaymentStatus.FAILED: "❌ Bekor qilingan",
}


def fmt_money(amount: int) -> str:
    """1234567 -> '1 234 567 so'm'"""
    return f"{amount:,}".replace(",", " ") + " so'm"


def fmt_date(dt) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y")
