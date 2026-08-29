import asyncio

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func

import config
from database.db import async_session
from database.models import (
    User, RoleEnum, Course, CourseStatus, Module, Lesson, Payment, PaymentStatus,
    Withdrawal, WithdrawalStatus, Enrollment,
)
from states.teacher_states import CreateCourse, AddLesson, EditModule, EditLesson, RequestWithdrawal
from utils.ordering import move_item
from utils.format import fmt_money, DIVIDER, COURSE_STATUS_LABEL, WITHDRAWAL_STATUS_LABEL
from utils.withdrawals import get_teacher_balance
from utils.roles import get_owner_telegram_id

router = Router()


async def _require_teacher(message: Message) -> User | None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
    if not user or user.role not in (RoleEnum.TEACHER, RoleEnum.ADMIN):
        await message.answer("Bu bo'lim faqat o'qituvchilar uchun.")
        return None
    return user


@router.message(F.text == "📚 Kurslarim")
async def my_courses(message: Message) -> None:
    user = await _require_teacher(message)
    if not user:
        return

    async with async_session() as session:
        result = await session.execute(select(Course).where(Course.teacher_id == user.id))
        courses = result.scalars().all()

        if not courses:
            await message.answer("📭 Sizda hali kurslar yo'q.\n\n👉 '➕ Kurs yaratish' tugmasini bosing.")
            return

        lines = [f"📚 <b>Kurslarim</b> ({len(courses)} ta)", DIVIDER]
        rows = []
        for c in courses:
            result = await session.execute(select(Lesson).join(Module).where(Module.course_id == c.id))
            lesson_count = len(result.scalars().all())
            lines.append(
                f"🎓 <b>{c.title}</b>\n"
                f"{fmt_money(c.price)} · {COURSE_STATUS_LABEL[c.status]} · 🎥 {lesson_count} ta dars\n"
            )
            rows.append([InlineKeyboardButton(text=f"📂 {c.title} — boshqarish", callback_data=f"tcourse:{c.id}")])

    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.message(F.text == "➕ Kurs yaratish")
async def start_create_course(message: Message, state: FSMContext) -> None:
    user = await _require_teacher(message)
    if not user:
        return
    await state.set_state(CreateCourse.title)
    await message.answer("✨ <b>Yangi kurs yaratish</b>\n\n1️⃣ Kurs nomini yuboring:")


@router.message(CreateCourse.title)
async def cc_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text)
    await state.set_state(CreateCourse.description)
    await message.answer("2️⃣ Kurs tavsifini yuboring:")


@router.message(CreateCourse.description)
async def cc_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text)
    await state.set_state(CreateCourse.price)
    await message.answer("3️⃣ Narxini so'mda kiriting (faqat raqam, masalan: 299000):")


@router.message(CreateCourse.price)
async def cc_price(message: Message, state: FSMContext) -> None:
    if not message.text.isdigit():
        await message.answer("⚠️ Iltimos faqat raqam kiriting. Masalan: 299000")
        return
    await state.update_data(price=int(message.text))
    await state.set_state(CreateCourse.category)
    await message.answer("4️⃣ Kategoriyasini kiriting (masalan: Til kurslari):")


@router.message(CreateCourse.category)
async def cc_category(message: Message, state: FSMContext) -> None:
    data = await state.update_data(category=message.text)
    await state.clear()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        teacher = result.scalar_one_or_none()

        # Admin o'zi yaratgan kursni moderatsiyasiz to'g'ridan-to'g'ri
        # tasdiqlangan holatda ochadi (o'zini-o'zi tekshirishning hojati yo'q).
        # Oddiy o'qituvchi yaratgan kurs hamon 🟡 moderatsiyaga boradi.
        is_admin = teacher.role == RoleEnum.ADMIN
        status = CourseStatus.APPROVED if is_admin else CourseStatus.PENDING

        course = Course(
            teacher_id=teacher.id,
            title=data["title"],
            description=data["description"],
            price=data["price"],
            category=data["category"],
            status=status,
        )
        session.add(course)
        await session.commit()

    if is_admin:
        await message.answer(
            f"✅ <b>{course.title}</b> kursi yaratildi va darhol ✅ <b>tasdiqlangan</b> holatda katalogga qo'shildi.\n\n"
            f"💰 {fmt_money(course.price)} · 📂 {course.category}\n\n"
            "Endi '🎥 Dars qo'shish' orqali modul va darslarni qo'shishingiz mumkin."
        )
    else:
        await message.answer(
            f"✅ <b>{course.title}</b> kursi yaratildi va 🟡 <b>moderatsiyaga</b> yuborildi.\n\n"
            f"💰 {fmt_money(course.price)} · 📂 {course.category}\n\n"
            "Admin tasdiqlagach, kurs katalogda ko'rinadi. Shu orada '🎥 Dars qo'shish' "
            "orqali modul va darslarni tayyorlab qo'yishingiz mumkin."
        )


@router.message(F.text == "💰 Daromadim")
async def teacher_income(message: Message) -> None:
    user = await _require_teacher(message)
    if not user:
        return

    async with async_session() as session:
        result = await session.execute(
            select(Payment).where(Payment.teacher_id == user.id, Payment.status == PaymentStatus.PAID)
        )
        payments = result.scalars().all()
        balance = await get_teacher_balance(session, user.id)

    total_sales = sum(p.amount for p in payments)

    text = (
        f"💰 <b>Daromadim</b>\n"
        f"{DIVIDER}\n"
        f"🧾 Sotilgan kurslar: {len(payments)} ta\n"
        f"💵 Jami savdo: {fmt_money(total_sales)}\n"
        f"👨‍🏫 Sizning ulushingiz (50%): <b>{fmt_money(balance['total_earned'])}</b>\n"
        f"{DIVIDER}\n"
        f"💳 Yechib olingan: {fmt_money(balance['approved_total'])}\n"
        f"💰 Balans (yechib olish mumkin): <b>{fmt_money(balance['available'])}</b>\n"
        f"{DIVIDER}\n"
        f"👉 '💳 Pul yechish' bo'limidan so'rov yuborishingiz mumkin."
    )
    await message.answer(text)


@router.message(F.text == "👨‍🎓 O'quvchilarim")
async def teacher_students(message: Message) -> None:
    user = await _require_teacher(message)
    if not user:
        return

    async with async_session() as session:
        result = await session.execute(select(Course).where(Course.teacher_id == user.id))
        courses = result.scalars().all()

        if not courses:
            await message.answer("📭 Sizda hali kurslar yo'q, shuning uchun o'quvchilar ham yo'q.")
            return

        course_ids = [c.id for c in courses]
        result = await session.execute(
            select(func.count()).select_from(Enrollment).where(Enrollment.course_id.in_(course_ids))
        )
        total_students = result.scalar_one()

        lines = [f"👨‍🎓 <b>O'quvchilarim</b> ({total_students} ta)", DIVIDER]
        rows = []
        for c in courses:
            result = await session.execute(
                select(func.count()).select_from(Enrollment).where(Enrollment.course_id == c.id)
            )
            count = result.scalar_one()
            lines.append(f"🎓 <b>{c.title}</b> — {count} ta o'quvchi")
            if count:
                rows.append([InlineKeyboardButton(
                    text=f"👥 {c.title} — ko'rish", callback_data=f"tstudents:{c.id}",
                )])

    await message.answer(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
    )


@router.callback_query(F.data.startswith("tstudents:"))
async def teacher_students_list(callback: CallbackQuery) -> None:
    course_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        teacher = result.scalar_one_or_none()
        course = await session.get(Course, course_id)
        if not teacher or not course or course.teacher_id != teacher.id:
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return

        result = await session.execute(
            select(Enrollment, User)
            .join(User, Enrollment.student_id == User.id)
            .where(Enrollment.course_id == course_id)
            .order_by(Enrollment.created_at.desc())
        )
        rows = result.all()

    if not rows:
        await callback.answer("Hali o'quvchi yo'q", show_alert=True)
        return

    lines = [f"👥 <b>{course.title}</b> — o'quvchilar ({len(rows)} ta)", DIVIDER]
    for enrollment, student in rows[:50]:
        lines.append(
            f"👤 {student.full_name or '—'} (@{student.username or '—'})\n"
            f"🆔 <code>{student.telegram_id}</code> · 📊 Progress: {enrollment.progress_percent}%"
        )
    if len(rows) > 50:
        lines.append(f"\n… va yana {len(rows) - 50} ta o'quvchi.")

    await callback.message.answer("\n\n".join(lines))
    await callback.answer()


@router.message(F.text == "📊 Statistika")
async def teacher_statistics(message: Message) -> None:
    user = await _require_teacher(message)
    if not user:
        return

    async with async_session() as session:
        result = await session.execute(select(Course).where(Course.teacher_id == user.id))
        courses = result.scalars().all()
        course_ids = [c.id for c in courses]

        approved = sum(1 for c in courses if c.status == CourseStatus.APPROVED)
        pending = sum(1 for c in courses if c.status == CourseStatus.PENDING)
        hidden = sum(1 for c in courses if c.status == CourseStatus.HIDDEN)
        rejected = sum(1 for c in courses if c.status == CourseStatus.REJECTED)

        lesson_count = 0
        total_students = 0
        if course_ids:
            result = await session.execute(
                select(func.count()).select_from(Lesson).join(Module).where(Module.course_id.in_(course_ids))
            )
            lesson_count = result.scalar_one()

            result = await session.execute(
                select(func.count(func.distinct(Enrollment.student_id))).where(
                    Enrollment.course_id.in_(course_ids)
                )
            )
            total_students = result.scalar_one()

        result = await session.execute(
            select(Payment).where(Payment.teacher_id == user.id, Payment.status == PaymentStatus.PAID)
        )
        payments = result.scalars().all()
        balance = await get_teacher_balance(session, user.id)

        # Eng ko'p sotilgan kurs
        sales_by_course: dict[int, int] = {}
        for p in payments:
            sales_by_course[p.course_id] = sales_by_course.get(p.course_id, 0) + 1
        top_course = None
        if sales_by_course:
            top_course_id = max(sales_by_course, key=sales_by_course.get)
            top_course = next((c for c in courses if c.id == top_course_id), None)

    total_sales = sum(p.amount for p in payments)

    lines = [
        "📊 <b>Statistika</b>",
        DIVIDER,
        f"📚 Fan: {user.subject or '— (kiritilmagan, admin bilan bog\u2018laning)'}",
        f"📚 Kurslar: {len(courses)} ta",
        f"　✅ Faol: {approved} · 🟡 Moderatsiyada: {pending} · 🙈 Yashirin: {hidden} · ❌ Rad etilgan: {rejected}",
        f"🎥 Jami darslar: {lesson_count} ta",
        f"👨‍🎓 Jami o'quvchilar: {total_students} ta",
        DIVIDER,
        f"🧾 Sotuvlar: {len(payments)} ta",
        f"💵 Jami savdo: {fmt_money(total_sales)}",
        f"👨‍🏫 Ulushingiz (50%): {fmt_money(balance['total_earned'])}",
        f"💰 Mavjud balans: {fmt_money(balance['available'])}",
    ]
    if top_course:
        lines += [DIVIDER, f"🏆 Eng ko'p sotilgan kurs: {top_course.title} ({sales_by_course[top_course.id]} ta)"]

    await message.answer("\n".join(lines))


# ============================================================
# 💳 Pul yechish — o'qituvchi balansidan yechib olish so'rovi
#
# Oqim: balans tekshiriladi → summa so'raladi (balansdan oshmasligi kerak)
# → karta raqami so'raladi → Withdrawal(PENDING) yaratiladi → admin (OWNER_ID)
# ga xabar boradi, tugmalar bilan: ✅ Tasdiqlash / ❌ Rad etish.
# ============================================================
@router.message(F.text == "💳 Pul yechish")
async def start_withdrawal(message: Message, state: FSMContext) -> None:
    user = await _require_teacher(message)
    if not user:
        return

    async with async_session() as session:
        balance = await get_teacher_balance(session, user.id)

    if balance["available"] <= 0:
        await message.answer(
            "📭 Hozircha yechib olish uchun mavjud balansingiz yo'q.\n\n"
            f"💰 Balans: <b>{fmt_money(balance['available'])}</b>"
        )
        return

    await state.set_state(RequestWithdrawal.waiting_amount)
    await state.update_data(available=balance["available"])
    await message.answer(
        f"💳 <b>Pul yechish</b>\n"
        f"{DIVIDER}\n"
        f"💰 Mavjud balans: <b>{fmt_money(balance['available'])}</b>\n"
        f"{DIVIDER}\n"
        "Yechib olmoqchi bo'lgan summani so'mda kiriting (faqat raqam, masalan: 500000):"
    )


@router.message(RequestWithdrawal.waiting_amount)
async def withdrawal_amount(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip().replace(" ", "")
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ Iltimos faqat musbat raqam kiriting. Masalan: 500000")
        return

    amount = int(text)
    data = await state.get_data()
    available = data.get("available", 0)

    if amount > available:
        await message.answer(
            f"⚠️ Bu summa balansingizdan katta.\n\n"
            f"💰 Mavjud balans: <b>{fmt_money(available)}</b>\n\n"
            "Iltimos, balansdan oshmaydigan summa kiriting:"
        )
        return

    await state.update_data(amount=amount)
    await state.set_state(RequestWithdrawal.waiting_card)
    await message.answer("💳 Endi karta raqamingizni kiriting (masalan: 8600 1234 5678 9012):")


@router.message(RequestWithdrawal.waiting_card)
async def withdrawal_card(message: Message, state: FSMContext) -> None:
    card_number = (message.text or "").strip()
    if len(card_number) < 8:
        await message.answer("⚠️ Iltimos to'g'ri karta raqamini kiriting.")
        return

    data = await state.get_data()
    amount = data.get("amount")
    await state.clear()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Xatolik yuz berdi. Iltimos /start bosing.")
            return
        # Balansni yana bir bor tekshiramiz (race condition'dan himoya)
        balance = await get_teacher_balance(session, user.id)
        if amount > balance["available"]:
            await message.answer(
                "⚠️ Balansingiz o'zgardi va bu summa endi mavjud emas.\n\n"
                f"💰 Joriy balans: <b>{fmt_money(balance['available'])}</b>\n\n"
                "Iltimos, '💳 Pul yechish' bo'limidan qaytadan urinib ko'ring."
            )
            return

        withdrawal = Withdrawal(teacher_id=user.id, amount=amount, card_number=card_number)
        session.add(withdrawal)
        await session.commit()
        await session.refresh(withdrawal)

        owner_id = await get_owner_telegram_id()
        teacher_name = user.full_name or "—"
        teacher_username = f"@{user.username}" if user.username else "—"

    await message.answer(
        f"✅ So'rovingiz qabul qilindi.\n\n"
        f"💰 Summa: <b>{fmt_money(amount)}</b>\n"
        f"💳 Karta: <code>{card_number}</code>\n\n"
        "Admin tekshirib chiqqach, sizga xabar beriladi ⏳"
    )

    caption = (
        f"💳 <b>Yangi pul yechish so'rovi</b>\n"
        f"{DIVIDER}\n"
        f"👨‍🏫 O'qituvchi: {teacher_name} ({teacher_username})\n"
        f"🆔 Telegram ID: <code>{user.telegram_id}</code>\n\n"
        f"{teacher_name} ({teacher_username}) <b>{fmt_money(amount)}</b> pul yechib olmoqchi.\n\n"
        f"💳 Karta raqami: <code>{card_number}</code>\n"
        f"{DIVIDER}\n"
        f"🔢 So'rov ID: {withdrawal.id}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"wd_ok:{withdrawal.id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"wd_no:{withdrawal.id}"),
    ]])
    if owner_id:
        try:
            await message.bot.send_message(owner_id, caption, reply_markup=kb)
        except Exception:
            pass


# ============================================================
# 🎥 Dars qo'shish — "kino bot" uslubidagi video yuklash oqimi
#
# Oqim: kursni tanlash → modulni tanlash (yoki yangi modul yaratish)
# → dars nomini yozish → video yuborish → bot videoni yashirin STORAGE
# kanalga ko'chiradi (copy_message) va o'sha kanaldagi xabar ID'sini
# saqlaydi. O'quvchiga hech qachon asl faylga to'g'ridan-to'g'ri link
# berilmaydi — faqat sotib olgan/enroll qilingan o'quvchiga bot orqali
# nusxa (copy_message) yuboriladi.
# ============================================================

def _teacher_courses_kb(courses: list[Course]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"🎓 {c.title}", callback_data=f"lc:{c.id}")] for c in courses]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == "🎥 Dars qo'shish")
async def add_lesson_start(message: Message, state: FSMContext) -> None:
    user = await _require_teacher(message)
    if not user:
        return

    async with async_session() as session:
        result = await session.execute(select(Course).where(Course.teacher_id == user.id))
        courses = result.scalars().all()

    if not courses:
        await message.answer("📭 Avval ➕ Kurs yaratish orqali kurs oching, keyin dars qo'shishingiz mumkin.")
        return

    await state.clear()
    await message.answer("🎥 <b>Dars qo'shish</b>\n\nQaysi kursga dars qo'shmoqchisiz?", reply_markup=_teacher_courses_kb(courses))


def _modules_kb(modules: list[Module], course_id: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"📚 {m.title}", callback_data=f"lm:{m.id}")] for m in modules]
    rows.append([InlineKeyboardButton(text="➕ Yangi modul", callback_data=f"lm_new:{course_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _check_course_owner(session, course_id: int, telegram_id: int) -> Course | None:
    course = await session.get(Course, course_id)
    if not course:
        return None
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user or (course.teacher_id != user.id and user.role != RoleEnum.ADMIN):
        return None
    return course


@router.callback_query(F.data.startswith("lc:"))
async def choose_course_for_lesson(callback: CallbackQuery, state: FSMContext) -> None:
    course_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        course = await _check_course_owner(session, course_id, callback.from_user.id)
        if not course:
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return
        result = await session.execute(
            select(Module).where(Module.course_id == course_id).order_by(Module.order_index)
        )
        modules = result.scalars().all()

    await state.update_data(course_id=course_id)
    await callback.message.edit_text(
        f"🎓 {course.title}\n\nQaysi modulga dars qo'shamiz?",
        reply_markup=_modules_kb(modules, course_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lm_new:"))
async def new_module_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    course_id = int(callback.data.split(":")[1])
    await state.update_data(course_id=course_id)
    await state.set_state(AddLesson.waiting_module_title)
    await callback.message.edit_text("📚 Yangi modul nomini yuboring (masalan: \"2-modul: Grammar\"):")
    await callback.answer()


@router.message(AddLesson.waiting_module_title)
async def create_module(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    course_id = data["course_id"]

    async with async_session() as session:
        course = await _check_course_owner(session, course_id, message.from_user.id)
        if not course:
            await message.answer("Ruxsat yo'q")
            await state.clear()
            return
        result = await session.execute(select(Module).where(Module.course_id == course_id))
        count = len(result.scalars().all())
        module = Module(course_id=course_id, title=message.text, order_index=count + 1)
        session.add(module)
        await session.commit()
        await session.refresh(module)

    await state.update_data(module_id=module.id)
    await state.set_state(AddLesson.waiting_lesson_title)
    await message.answer(f"✅ \"{module.title}\" moduli yaratildi.\n\n1️⃣ Dars nomini yuboring:")


@router.callback_query(F.data.startswith("lm:"))
async def choose_module_for_lesson(callback: CallbackQuery, state: FSMContext) -> None:
    module_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        module = await session.get(Module, module_id)
        if not module:
            await callback.answer("Modul topilmadi", show_alert=True)
            return
        course = await _check_course_owner(session, module.course_id, callback.from_user.id)
        if not course:
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return

    await state.update_data(module_id=module.id, course_id=module.course_id)
    await state.set_state(AddLesson.waiting_lesson_title)
    await callback.message.edit_text(f"📚 {module.title}\n\n1️⃣ Dars nomini yuboring:")
    await callback.answer()


@router.message(AddLesson.waiting_lesson_title)
async def lesson_title_received(message: Message, state: FSMContext) -> None:
    await state.update_data(lesson_title=message.text)
    await state.set_state(AddLesson.waiting_video)
    await message.answer("2️⃣ Endi shu darsning video faylini yuboring (video sifatida, fayl emas):")


@router.message(AddLesson.waiting_video, F.video)
async def lesson_video_received(message: Message, state: FSMContext, bot: Bot) -> None:
    if not config.STORAGE_CHANNEL_ID:
        await message.answer(
            "⚠️ STORAGE_CHANNEL_ID sozlanmagan. Adminga murojaat qiling: bot xususiy "
            "kanalga admin qilib qo'shilishi va .env ga STORAGE_CHANNEL_ID yozilishi kerak."
        )
        await state.clear()
        return

    data = await state.get_data()
    module_id = data.get("module_id")
    lesson_title = data.get("lesson_title", "Dars")

    # "Kino bot" uslubidagi soxta progress-bar — foydalanuvchiga tanish, tushunarli tajriba beradi.
    progress_msg = await message.answer("⏳ Video yuklanmoqda...\n[□□□□□□□□□□] 0%")
    bars = [
        (20, "■■□□□□□□□□"), (40, "■■■■□□□□□□"), (60, "■■■■■■□□□□"),
        (80, "■■■■■■■■□□"), (100, "■■■■■■■■■■"),
    ]
    for percent, bar in bars:
        await asyncio.sleep(0.35)
        try:
            await progress_msg.edit_text(f"⏳ Video yuklanmoqda...\n[{bar}] {percent}%")
        except Exception:
            pass

    # Videoni yashirin storage kanalga ko'chiramiz — asl fayl hech qachon
    # to'g'ridan-to'g'ri o'quvchiga (yoki uning linkiga) berilmaydi.
    try:
        copied = await bot.copy_message(
            chat_id=config.STORAGE_CHANNEL_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except Exception as e:
        await state.clear()
        await progress_msg.edit_text(
            "❌ <b>Video yuklashda xatolik yuz berdi.</b>\n\n"
            f"<code>{e}</code>\n\n"
            "Tekshiring:\n"
            "1️⃣ Bot STORAGE kanaliga <b>admin</b> qilib qo'shilganmi?\n"
            "2️⃣ Kanalga xabar yuborish (post) huquqi berilganmi?\n"
            "3️⃣ .env/Railow'dagi <code>STORAGE_CHANNEL_ID</code> to'g'ri (masalan -100 bilan boshlanadigan)mi?\n\n"
            "Tuzatgach, '🎥 Dars qo'shish' orqali qaytadan urinib ko'ring."
        )
        return

    async with async_session() as session:
        result = await session.execute(select(Lesson).where(Lesson.module_id == module_id))
        count = len(result.scalars().all())
        lesson = Lesson(
            module_id=module_id,
            title=lesson_title,
            order_index=count + 1,
            video_chat_id=config.STORAGE_CHANNEL_ID,
            video_message_id=copied.message_id,
        )
        session.add(lesson)
        await session.commit()
        await session.refresh(lesson)

    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎥 Yana dars qo'shish", callback_data=f"lm:{module_id}"),
        InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"ldel:{lesson.id}"),
    ]])
    await progress_msg.edit_text(
        f"✅ <b>Video muvaffaqiyatli yuklandi!</b>\n\n🎬 {lesson.title}",
        reply_markup=kb,
    )


@router.message(AddLesson.waiting_video)
async def lesson_video_wrong_type(message: Message) -> None:
    await message.answer("Iltimos, videoni 🎥 <b>video</b> sifatida yuboring (fayl/hujjat sifatida emas).")


@router.callback_query(F.data.startswith("ldel:"))
async def delete_lesson(callback: CallbackQuery) -> None:
    lesson_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        if not lesson:
            await callback.answer("Dars topilmadi", show_alert=True)
            return
        module = await session.get(Module, lesson.module_id)
        course = await _check_course_owner(session, module.course_id, callback.from_user.id)
        if not course:
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return
        await session.delete(lesson)
        await session.commit()

    await callback.message.edit_text("🗑 Dars o'chirildi.\n\n(Video storage kanalida qoladi, lekin kursga bog'liq emas)")
    await callback.answer()


# ============================================================
# 📂 Kursni boshqarish — modul/darslarni ko'rish, TAHRIRLASH va o'chirish
# ============================================================

@router.callback_query(F.data.startswith("tcourse:"))
async def manage_course(callback: CallbackQuery) -> None:
    course_id = int(callback.data.split(":")[1])
    await _render_course_management(callback, course_id)


async def _render_course_management(callback: CallbackQuery, course_id: int) -> None:
    async with async_session() as session:
        course = await _check_course_owner(session, course_id, callback.from_user.id)
        if not course:
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return
        result = await session.execute(
            select(Module).where(Module.course_id == course_id).order_by(Module.order_index)
        )
        modules = result.scalars().all()

    rows = []
    total = len(modules)
    for idx, m in enumerate(modules):
        row = [InlineKeyboardButton(text=f"📚 {m.title}", callback_data=f"tmodule:{m.id}")]
        if idx > 0:
            row.append(InlineKeyboardButton(text="⬆️", callback_data=f"tmod_up:{m.id}"))
        if idx < total - 1:
            row.append(InlineKeyboardButton(text="⬇️", callback_data=f"tmod_down:{m.id}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(text="➕ Yangi modul", callback_data=f"lm_new:{course_id}")])

    await callback.message.edit_text(
        f"📂 <b>{course.title}</b>\n"
        f"{DIVIDER}\n"
        "Modulni tanlang (tahrirlash/darslarni ko'rish uchun).\n"
        "⬆️/⬇️ — modullar tartibini o'zgartirish:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tmod_up:"))
async def move_module_up(callback: CallbackQuery) -> None:
    await _move_module(callback, "up")


@router.callback_query(F.data.startswith("tmod_down:"))
async def move_module_down(callback: CallbackQuery) -> None:
    await _move_module(callback, "down")


async def _move_module(callback: CallbackQuery, direction: str) -> None:
    module_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        module = await session.get(Module, module_id)
        course = await _check_course_owner(session, module.course_id, callback.from_user.id) if module else None
        if not course:
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return
        result = await session.execute(
            select(Module).where(Module.course_id == course.id).order_by(Module.order_index)
        )
        modules = result.scalars().all()
        moved = await move_item(session, modules, module_id, direction)
        course_id = course.id

    if not moved:
        await callback.answer("Bu allaqachon chetda 🙂")
        return

    await callback.answer("↕️ Tartib yangilandi")
    await _render_course_management(callback, course_id)


@router.callback_query(F.data.startswith("tmodule:"))
async def manage_module(callback: CallbackQuery) -> None:
    module_id = int(callback.data.split(":")[1])
    await _render_module_management(callback, module_id)


async def _render_module_management(callback: CallbackQuery, module_id: int) -> None:
    async with async_session() as session:
        module = await session.get(Module, module_id)
        if not module:
            await callback.answer("Modul topilmadi", show_alert=True)
            return
        course = await _check_course_owner(session, module.course_id, callback.from_user.id)
        if not course:
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return
        result = await session.execute(
            select(Lesson).where(Lesson.module_id == module_id).order_by(Lesson.order_index)
        )
        lessons = result.scalars().all()

    rows = [[
        InlineKeyboardButton(text="✏️ Modul nomi", callback_data=f"tmod_edit:{module_id}"),
        InlineKeyboardButton(text="🗑 Modulni o'chirish", callback_data=f"tmod_del:{module_id}"),
    ]]
    total = len(lessons)
    for idx, l in enumerate(lessons):
        video_mark = "🎥" if l.has_video else "⚠️ video yo'q"
        row = [InlineKeyboardButton(text=f"{video_mark} {l.title}", callback_data=f"tlesson:{l.id}")]
        if idx > 0:
            row.append(InlineKeyboardButton(text="⬆️", callback_data=f"tles_up:{l.id}"))
        if idx < total - 1:
            row.append(InlineKeyboardButton(text="⬇️", callback_data=f"tles_down:{l.id}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(text="➕ Dars qo'shish", callback_data=f"lm:{module_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"tcourse:{module.course_id}")])

    text = f"📚 <b>{module.title}</b>\n{DIVIDER}\n"
    text += "Darsni tahrirlash uchun tanlang. ⬆️/⬇️ — darslar tartibini o'zgartirish:" if lessons else "Bu modulda hali darslar yo'q."

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data.startswith("tles_up:"))
async def move_lesson_up(callback: CallbackQuery) -> None:
    await _move_lesson(callback, "up")


@router.callback_query(F.data.startswith("tles_down:"))
async def move_lesson_down(callback: CallbackQuery) -> None:
    await _move_lesson(callback, "down")


async def _move_lesson(callback: CallbackQuery, direction: str) -> None:
    lesson_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        module = await session.get(Module, lesson.module_id) if lesson else None
        course = await _check_course_owner(session, module.course_id, callback.from_user.id) if module else None
        if not course:
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return
        result = await session.execute(
            select(Lesson).where(Lesson.module_id == module.id).order_by(Lesson.order_index)
        )
        lessons = result.scalars().all()
        moved = await move_item(session, lessons, lesson_id, direction)
        module_id = module.id

    if not moved:
        await callback.answer("Bu allaqachon chetda 🙂")
        return

    await callback.answer("↕️ Tartib yangilandi")
    await _render_module_management(callback, module_id)


@router.callback_query(F.data.startswith("tmod_edit:"))
async def start_edit_module_title(callback: CallbackQuery, state: FSMContext) -> None:
    module_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        module = await session.get(Module, module_id)
        course = await _check_course_owner(session, module.course_id, callback.from_user.id) if module else None
        if not course:
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return

    await state.update_data(module_id=module_id)
    await state.set_state(EditModule.waiting_title)
    await callback.message.edit_text(f"✏️ \"{module.title}\" moduli uchun yangi nom yuboring:")
    await callback.answer()


@router.message(EditModule.waiting_title)
async def save_module_title(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    module_id = data["module_id"]
    async with async_session() as session:
        module = await session.get(Module, module_id)
        course = await _check_course_owner(session, module.course_id, message.from_user.id) if module else None
        if not course:
            await message.answer("Ruxsat yo'q")
            await state.clear()
            return
        module.title = message.text
        await session.commit()

    await state.clear()
    await message.answer(f"✅ Modul nomi \"{message.text}\" ga o'zgartirildi.")


@router.callback_query(F.data.startswith("tmod_del:"))
async def confirm_delete_module(callback: CallbackQuery) -> None:
    module_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        module = await session.get(Module, module_id)
        course = await _check_course_owner(session, module.course_id, callback.from_user.id) if module else None
        if not course:
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return
        result = await session.execute(select(Lesson).where(Lesson.module_id == module_id))
        lesson_count = len(result.scalars().all())

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha, o'chirish", callback_data=f"tmod_del_yes:{module_id}"),
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"tmodule:{module_id}"),
    ]])
    await callback.message.edit_text(
        f"⚠️ \"{module.title}\" modulini o'chirmoqchimisiz?\n\n"
        f"Bu moduldagi {lesson_count} ta dars ham birga o'chib ketadi. Bu qaytarilmaydi.",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tmod_del_yes:"))
async def delete_module(callback: CallbackQuery) -> None:
    module_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        module = await session.get(Module, module_id)
        course = await _check_course_owner(session, module.course_id, callback.from_user.id) if module else None
        if not course:
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return
        course_id = module.course_id
        await session.delete(module)  # cascade: shu moduldagi darslar ham o'chadi
        await session.commit()

    await callback.message.edit_text("🗑 Modul va undagi darslar o'chirildi.")
    await callback.answer()


@router.callback_query(F.data.startswith("tlesson:"))
async def manage_lesson(callback: CallbackQuery) -> None:
    lesson_id = int(callback.data.split(":")[1])
    await _render_lesson_management(callback, lesson_id)


async def _render_lesson_management(callback: CallbackQuery, lesson_id: int) -> None:
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        if not lesson:
            await callback.answer("Dars topilmadi", show_alert=True)
            return
        module = await session.get(Module, lesson.module_id)
        course = await _check_course_owner(session, module.course_id, callback.from_user.id)
        if not course:
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Nomini o'zgartirish", callback_data=f"tles_edit_title:{lesson_id}")],
        [InlineKeyboardButton(text="🎥 Videoni almashtirish", callback_data=f"tles_edit_video:{lesson_id}")],
        [InlineKeyboardButton(
            text=("🚫 Preview'ni bekor qilish" if lesson.is_preview else "🎁 Bepul preview qilish"),
            callback_data=f"tles_preview:{lesson_id}",
        )],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"ldel:{lesson_id}")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"tmodule:{module.id}")],
    ])
    video_status = "🎥 Video yuklangan" if lesson.has_video else "⚠️ Video yo'q"
    preview_status = "\n🎁 Bu dars — BEPUL PREVIEW (hamma ko'ra oladi)" if lesson.is_preview else ""
    await callback.message.edit_text(
        f"🎬 <b>{lesson.title}</b>\n{DIVIDER}\n{video_status}{preview_status}", reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tles_preview:"))
async def toggle_lesson_preview(callback: CallbackQuery) -> None:
    lesson_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        if not lesson:
            await callback.answer("Dars topilmadi", show_alert=True)
            return
        module = await session.get(Module, lesson.module_id)
        course = await _check_course_owner(session, module.course_id, callback.from_user.id)
        if not course:
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return
        lesson.is_preview = not lesson.is_preview
        await session.commit()
        new_state = lesson.is_preview

    await callback.answer("🎁 Preview yoqildi" if new_state else "🚫 Preview o'chirildi")
    # Kartani yangilash uchun manage_lesson ekranini qayta chizamiz.
    await _render_lesson_management(callback, lesson_id)


@router.callback_query(F.data.startswith("tles_edit_title:"))
async def start_edit_lesson_title(callback: CallbackQuery, state: FSMContext) -> None:
    lesson_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        module = await session.get(Module, lesson.module_id) if lesson else None
        course = await _check_course_owner(session, module.course_id, callback.from_user.id) if module else None
        if not course:
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return

    await state.update_data(lesson_id=lesson_id)
    await state.set_state(EditLesson.waiting_title)
    await callback.message.edit_text(f"✏️ \"{lesson.title}\" darsi uchun yangi nom yuboring:")
    await callback.answer()


@router.message(EditLesson.waiting_title)
async def save_lesson_title(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lesson_id = data["lesson_id"]
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        module = await session.get(Module, lesson.module_id) if lesson else None
        course = await _check_course_owner(session, module.course_id, message.from_user.id) if module else None
        if not course:
            await message.answer("Ruxsat yo'q")
            await state.clear()
            return
        lesson.title = message.text
        await session.commit()

    await state.clear()
    await message.answer(f"✅ Dars nomi \"{message.text}\" ga o'zgartirildi.")


@router.callback_query(F.data.startswith("tles_edit_video:"))
async def start_edit_lesson_video(callback: CallbackQuery, state: FSMContext) -> None:
    lesson_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        module = await session.get(Module, lesson.module_id) if lesson else None
        course = await _check_course_owner(session, module.course_id, callback.from_user.id) if module else None
        if not course:
            await callback.answer("Ruxsat yo'q", show_alert=True)
            return

    await state.update_data(lesson_id=lesson_id)
    await state.set_state(EditLesson.waiting_video)
    await callback.message.edit_text(f"🎥 \"{lesson.title}\" darsi uchun yangi video faylni yuboring:")
    await callback.answer()


@router.message(EditLesson.waiting_video, F.video)
async def save_lesson_video(message: Message, state: FSMContext, bot: Bot) -> None:
    if not config.STORAGE_CHANNEL_ID:
        await message.answer("⚠️ STORAGE_CHANNEL_ID sozlanmagan. Adminga murojaat qiling.")
        await state.clear()
        return

    data = await state.get_data()
    lesson_id = data["lesson_id"]

    progress_msg = await message.answer("⏳ Yangi video yuklanmoqda...\n[■■■■■■■■■■] 100%")

    try:
        copied = await bot.copy_message(
            chat_id=config.STORAGE_CHANNEL_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except Exception as e:
        await state.clear()
        await progress_msg.edit_text(
            "❌ <b>Video yuklashda xatolik yuz berdi.</b>\n\n"
            f"<code>{e}</code>\n\n"
            "Bot STORAGE kanaliga admin qilib qo'shilganmi va "
            "<code>STORAGE_CHANNEL_ID</code> to'g'ri sozlanganmi — tekshiring."
        )
        return

    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        module = await session.get(Module, lesson.module_id) if lesson else None
        course = await _check_course_owner(session, module.course_id, message.from_user.id) if module else None
        if not course:
            await progress_msg.edit_text("Ruxsat yo'q")
            await state.clear()
            return
        lesson.video_chat_id = config.STORAGE_CHANNEL_ID
        lesson.video_message_id = copied.message_id
        await session.commit()
        title = lesson.title

    await state.clear()
    await progress_msg.edit_text(f"✅ \"{title}\" darsining videosi yangilandi.")


@router.message(EditLesson.waiting_video)
async def edit_video_wrong_type(message: Message) -> None:
    await message.answer("Iltimos, videoni 🎥 <b>video</b> sifatida yuboring.")
