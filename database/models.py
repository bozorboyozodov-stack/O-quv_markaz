import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger, String, Integer, Text, ForeignKey, DateTime,
    Enum as SAEnum, Numeric, func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RoleEnum(str, enum.Enum):
    STUDENT = "STUDENT"
    TEACHER = "TEACHER"
    ADMIN = "ADMIN"


class CourseStatus(str, enum.Enum):
    PENDING = "PENDING"        # 🟡 Moderatsiyada
    APPROVED = "APPROVED"      # ✅ Tasdiqlangan, katalogda ko'rinadi
    HIDDEN = "HIDDEN"          # Admin tomonidan yashirilgan
    REJECTED = "REJECTED"


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"


class WithdrawalStatus(str, enum.Enum):
    PENDING = "PENDING"      # Admin javobini kutmoqda
    APPROVED = "APPROVED"    # Admin tasdiqladi
    REJECTED = "REJECTED"    # Admin rad etdi (sababi bilan)


# ------------------------------------------------------------------
# users — hujjatdagi 15-bo'lim: users, teachers, students bitta jadvalga
# role maydoni orqali birlashtirilgan (soddalashtirish uchun; keyinchalik
# teacher_profile / student_profile alohida jadvallarga bo'linishi mumkin)
# ------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    username: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    role: Mapped[RoleEnum] = mapped_column(SAEnum(RoleEnum), default=RoleEnum.STUDENT)
    # Faqat TEACHER uchun mazmunli: o'qituvchi qaysi fan(lar)dan dars berishi
    # (masalan: "Matematika", "Ingliz tili"). Admin o'qituvchini qo'shayotganda
    # kiritadi, o'qituvchilar ro'yxatida shu maydon ko'rsatiladi.
    subject: Mapped[str] = mapped_column(String(255), default="")
    is_blocked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    courses: Mapped[list["Course"]] = relationship(back_populates="teacher")
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="student")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[int] = mapped_column(Integer, default=0)  # so'mda, butun son
    category: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[CourseStatus] = mapped_column(SAEnum(CourseStatus), default=CourseStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    teacher: Mapped["User"] = relationship(back_populates="courses")
    modules: Mapped[list["Module"]] = relationship(back_populates="course", cascade="all, delete-orphan")
    enrollments: Mapped[list["Enrollment"]] = relationship(back_populates="course")


class Module(Base):
    __tablename__ = "course_modules"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    title: Mapped[str] = mapped_column(String(255))
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    course: Mapped["Course"] = relationship(back_populates="modules")
    lessons: Mapped[list["Lesson"]] = relationship(back_populates="module", cascade="all, delete-orphan")


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("course_modules.id"))
    title: Mapped[str] = mapped_column(String(255))
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    # Video "kino bot" uslubida saqlanadi: video yashirin/xususiy STORAGE
    # kanalga yuboriladi (bot admin bo'lgan), va shu kanaldagi xabar ID'si
    # saqlanadi. O'quvchiga hech qachon to'g'ridan-to'g'ri fayl linki
    # berilmaydi — faqat copy_message orqali nusxa yuboriladi (14-bo'lim:
    # "Video protection").
    video_chat_id: Mapped[int] = mapped_column(BigInteger, default=0)
    video_message_id: Mapped[int] = mapped_column(Integer, default=0)
    # 🎁 Preview dars: sotib olmagan foydalanuvchi ham bepul ko'ra oladi
    # (hujjatning 7-bo'limi: "8. Preview dars"). Har bir o'qituvchi xohlagan
    # darsini(larini) preview qilib qo'yishi mumkin — odatda 1-darsni.
    is_preview: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    module: Mapped["Module"] = relationship(back_populates="lessons")

    @property
    def has_video(self) -> bool:
        return bool(self.video_chat_id and self.video_message_id)


class Enrollment(Base):
    """O'quvchining kursga yozilishi (to'lov qilingandan keyin)."""
    __tablename__ = "enrollments"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student: Mapped["User"] = relationship(back_populates="enrollments")
    course: Mapped["Course"] = relationship(back_populates="enrollments")


class Payment(Base):
    """Qo'lda (karta orqali) to'lov + admin tasdiqlash oqimi.

    Oqim:
    PENDING (chek kutilmoqda) → RECEIPT_SENT (o'quvchi chek yubordi, admin
    tekshiryapti) → PAID (admin tasdiqladi, kurs ochildi) yoki FAILED
    (admin rad etdi).
    """
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    card_id: Mapped[int | None] = mapped_column(ForeignKey("payment_cards.id"), nullable=True)
    amount: Mapped[int] = mapped_column(Integer)  # so'mda
    status: Mapped[PaymentStatus] = mapped_column(SAEnum(PaymentStatus), default=PaymentStatus.PENDING)
    receipt_file_id: Mapped[str] = mapped_column(String(255), default="")  # o'quvchi yuborgan chek rasmi
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # qaysi admin
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaymentCard(Base):
    """Admin qo'shadigan to'lov kartalari. Bir nechtasi bo'lishi mumkin
    (masalan turli banklar) — o'quvchi sotib olishda qaysi biriga
    to'lashni tanlaydi (agar 1 tadan ko'p faol karta bo'lsa)."""
    __tablename__ = "payment_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(100))  # masalan: "Uzcard — asosiy"
    card_number: Mapped[str] = mapped_column(String(64))
    owner_name: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BotSetting(Base):
    """Oddiy key-value sozlamalar (masalan: to'lov uchun karta raqami).
    Kelajakda promocode/notification sozlamalari ham shu yerga qo'shilishi mumkin."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), default="")


class LessonProgress(Base):
    """Hujjatning 5-bo'limi: 'video boshlandi → progress saqlanadi → video tugadi →
    dars completed bo'ladi'. Har bir (student, lesson) juftligi uchun bitta yozuv."""
    __tablename__ = "progress"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"))
    is_completed: Mapped[bool] = mapped_column(default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Withdrawal(Base):
    """Hujjatning 10-bo'limi: 'Pul yechish tizimi'.

    O'qituvchi balansidan (50% ulushidan) pul yechib olish so'rovi.
    Oqim:
    PENDING (admin javobini kutmoqda) → APPROVED (admin tasdiqladi, o'qituvchiga
    xabar boradi) yoki REJECTED (admin sababi bilan rad etadi, o'qituvchiga
    sabab bilan xabar boradi).

    Balans hisobi: teacher_share (barcha PAID to'lovlarning 50% ulushi) minus
    hali ko'rib chiqilmagan (PENDING) va allaqachon tasdiqlangan (APPROVED)
    so'rovlar yig'indisi — shu orqali o'qituvchi balansidan ko'p pul so'ray
    olmaydi, hatto bir nechta so'rovni ketma-ket yuborsa ham."""
    __tablename__ = "withdrawals"

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[int] = mapped_column(Integer)  # so'mda
    card_number: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[WithdrawalStatus] = mapped_column(SAEnum(WithdrawalStatus), default=WithdrawalStatus.PENDING)
    reject_reason: Mapped[str] = mapped_column(Text, default="")
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Certificate(Base):
    """Hujjatning 15-bo'limi ('certificates' jadvali) va profil bo'limidagi
    '🏆 Sertifikatlari' maydoniga asos.

    O'quvchi bitta kursning barcha darslarini tugatib, progress 100% bo'lganda
    (bir marta, avtomatik) yaratiladi. `code` — PDF ichida ko'rsatiladigan va
    kimdir haqiqiyligini tekshirmoqchi bo'lsa ishlatiladigan noyob kod."""
    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
