"""Sertifikat tizimi.

Hujjatdagi oqim: "...videolarni ko'radi → progressi saqlanadi → sertifikat oladi."

Ya'ni: o'quvchi kursning barcha darslarini tugatib, progress 100% bo'lganda,
tizim AVTOMATIK ravishda (bitta marta) sertifikat yaratadi va PDF holida
yuboradi. O'quvchi keyinchalik "🏆 Sertifikatlarim" bo'limidan uni istagancha
qayta yuklab olishi mumkin.
"""

import io
import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Certificate, Course, User

# reportlab faqat shu modul ichida kerak — boshqa joyларда PDF generatsiyasi yo'q.
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth


def _generate_code() -> str:
    """Masalan: CB-7F3K9QZP2X — taxminlab topib bo'lmaydigan, qisqa kod."""
    alphabet = string.ascii_uppercase + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(10))
    return f"CB-{random_part}"


async def get_certificate(session: AsyncSession, student_id: int, course_id: int) -> Certificate | None:
    result = await session.execute(
        select(Certificate).where(Certificate.student_id == student_id, Certificate.course_id == course_id)
    )
    return result.scalar_one_or_none()


async def issue_certificate_if_completed(
    session: AsyncSession, student_id: int, course_id: int, progress_percent: int,
) -> Certificate | None:
    """Progress 100% bo'lsa va hali sertifikat berilmagan bo'lsa — yaratadi.

    Idempotent: kurs uchun bir o'quvchiga faqat bitta marta beriladi (qayta
    100%'ga "tegib o'tsa" ham eski sertifikat qaytariladi, yangisi yaratilmaydi).
    Progress 100% bo'lmasa — None qaytaradi (hali sertifikat yo'q).
    """
    existing = await get_certificate(session, student_id, course_id)
    if existing:
        return existing

    if progress_percent < 100:
        return None

    certificate = Certificate(student_id=student_id, course_id=course_id, code=_generate_code())
    session.add(certificate)
    await session.commit()
    await session.refresh(certificate)
    return certificate


def render_certificate_pdf(certificate: Certificate, student: User, course: Course, teacher: User | None) -> bytes:
    """Sertifikatni A4 landscape PDF sifatida chizadi va bayt sifatida qaytaradi
    (fayl diskka yozilmaydi — to'g'ridan-to'g'ri Telegram'ga yuboriladi)."""
    buffer = io.BytesIO()
    page_size = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=page_size)
    width, height = page_size

    navy = HexColor("#1B2A4A")
    gold = HexColor("#C6A15B")
    gray = HexColor("#5B6472")

    # Tashqi va ichki ramka
    c.setStrokeColor(gold)
    c.setLineWidth(3)
    c.rect(1.2 * cm, 1.2 * cm, width - 2.4 * cm, height - 2.4 * cm)
    c.setLineWidth(0.8)
    c.rect(1.5 * cm, 1.5 * cm, width - 3.0 * cm, height - 3.0 * cm)

    center_x = width / 2

    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(center_x, height - 3.0 * cm, "ONLINE ACADEMY")

    c.setFillColor(gold)
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(center_x, height - 4.4 * cm, "SERTIFIKAT")

    c.setFillColor(gray)
    c.setFont("Helvetica", 13)
    c.drawCentredString(center_x, height - 5.4 * cm, "Ushbu sertifikat quyidagi shaxsga topshiriladi:")

    student_name = student.full_name or f"Foydalanuvchi #{student.telegram_id}"
    c.setFillColor(navy)
    font_size = 30
    while stringWidth(student_name, "Helvetica-Bold", font_size) > width - 6 * cm and font_size > 16:
        font_size -= 1
    c.setFont("Helvetica-Bold", font_size)
    c.drawCentredString(center_x, height - 6.6 * cm, student_name)

    # Ism ostidagi bezak chiziq
    c.setStrokeColor(gold)
    c.setLineWidth(1)
    line_half = min(6 * cm, stringWidth(student_name, "Helvetica-Bold", font_size) / 2 + 1 * cm)
    c.line(center_x - line_half, height - 7.1 * cm, center_x + line_half, height - 7.1 * cm)

    c.setFillColor(gray)
    c.setFont("Helvetica", 13)
    c.drawCentredString(center_x, height - 8.1 * cm, "quyidagi kursni muvaffaqiyatli yakunlagani uchun:")

    c.setFillColor(navy)
    font_size = 22
    while stringWidth(course.title, "Helvetica-Bold", font_size) > width - 6 * cm and font_size > 14:
        font_size -= 1
    c.setFont("Helvetica-Bold", font_size)
    c.drawCentredString(center_x, height - 9.3 * cm, course.title)

    issued_date = certificate.issued_at or datetime.now(timezone.utc)
    date_str = issued_date.strftime("%d.%m.%Y")

    c.setFillColor(gray)
    c.setFont("Helvetica", 10)
    bottom_y = 2.6 * cm
    c.drawString(2.3 * cm, bottom_y + 0.9 * cm, "Sana:")
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(2.3 * cm, bottom_y, date_str)

    if teacher and teacher.full_name:
        c.setFillColor(gray)
        c.setFont("Helvetica", 10)
        c.drawCentredString(center_x, bottom_y + 0.9 * cm, "O'qituvchi:")
        c.setFillColor(navy)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(center_x, bottom_y, teacher.full_name)

    c.setFillColor(gray)
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 2.3 * cm, bottom_y + 0.9 * cm, "Tasdiqlash kodi:")
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(width - 2.3 * cm, bottom_y, certificate.code)

    c.showPage()
    c.save()
    return buffer.getvalue()
