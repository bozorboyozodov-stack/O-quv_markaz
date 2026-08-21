from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from sqlalchemy import select

import config
from database.db import async_session
from database.models import (
    Course, CourseStatus, User, Enrollment, Payment, PaymentStatus, PaymentCard, Module, Lesson, Certificate,
)
from states.teacher_states import BuyCourse
from utils.roles import get_owner_telegram_id
from utils.format import fmt_money, fmt_date, DIVIDER, PAYMENT_STATUS_LABEL
from utils.lessons import (
    get_ordered_lessons, get_completed_lesson_ids, mark_lesson_completed, recalculate_enrollment_progress,
)
from utils.certificates import issue_certificate_if_completed, render_certificate_pdf
from utils.settings import get_setting, resolve_contact_url, SUPPORT_CONTACT_KEY

router = Router()


def course_list_kb(courses: list[Course]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"🎓 {c.title} — {fmt_money(c.price)}", callback_data=f"course:{c.id}")]
        for c in courses
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == "📚 Kurslar")
async def show_catalog(message: Message) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(Course).where(Course.status == CourseStatus.APPROVED).order_by(Course.created_at.desc())
        )
        courses = result.scalars().all()

    if not courses:
        await message.answer("📭 Hozircha tasdiqlangan kurslar yo'q. Tez orada qo'shiladi 🙌")
        return

    await message.answer(
        f"📚 <b>Kurslar katalogi</b>\n\n"
        f"Jami <b>{len(courses)}</b> ta faol kurs mavjud. Batafsil ma'lumot uchun kursni tanlang:",
        reply_markup=course_list_kb(courses),
    )


@router.callback_query(F.data.startswith("course:"))
async def show_course_detail(callback: CallbackQuery) -> None:
    course_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        course = await session.get(Course, course_id)
        if not course:
            await callback.answer("Kurs topilmadi", show_alert=True)
            return
        teacher = await session.get(User, course.teacher_id)

        result = await session.execute(select(Module).where(Module.course_id == course_id))
        module_count = len(result.scalars().all())

        result = await session.execute(select(Lesson).join(Module).where(Module.course_id == course_id))
        all_lessons = result.scalars().all()
        lesson_count = len(all_lessons)

        result = await session.execute(
            select(Lesson).join(Module).where(Module.course_id == course_id, Lesson.is_preview == True)  # noqa: E712
        )
        preview_lessons = [l for l in result.scalars().all() if l.has_video]

        result = await session.execute(
            select(Enrollment).where(Enrollment.course_id == course_id)
        )
        student_count = len(result.scalars().all())

    text = (
        f"🎓 <b>{course.title}</b>\n"
        f"{DIVIDER}\n"
        f"👨‍🏫 O'qituvchi: {teacher.full_name if teacher else '—'}\n"
        f"📚 {module_count} ta modul · 🎥 {lesson_count} ta dars\n"
        f"👨‍🎓 {student_count} ta o'quvchi\n"
        f"{DIVIDER}\n"
        f"{course.description or 'Tavsif hali qo\u2019shilmagan.'}\n"
        f"{DIVIDER}\n"
        f"💰 <b>{fmt_money(course.price)}</b>"
    )
    rows = []
    for l in preview_lessons:
        rows.append([InlineKeyboardButton(text=f"🎁 Bepul: {l.title}", callback_data=f"preview:{l.id}")])
    rows.append([InlineKeyboardButton(text="🛒 KURSNI SOTIB OLISH", callback_data=f"buy:{course.id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Katalogga qaytish", callback_data="back_to_catalog")])

    await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data == "back_to_catalog")
async def back_to_catalog(callback: CallbackQuery) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(Course).where(Course.status == CourseStatus.APPROVED).order_by(Course.created_at.desc())
        )
        courses = result.scalars().all()

    if not courses:
        await callback.message.edit_text("📭 Hozircha tasdiqlangan kurslar yo'q.")
        await callback.answer()
        return

    await callback.message.edit_text(
        f"📚 <b>Kurslar katalogi</b>\n\n"
        f"Jami <b>{len(courses)}</b> ta faol kurs mavjud. Batafsil ma'lumot uchun kursni tanlang:",
        reply_markup=course_list_kb(courses),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("preview:"))
async def watch_preview_lesson(callback: CallbackQuery, bot: Bot) -> None:
    """Preview darslarni HAR KIM ko'ra oladi — sotib olish/enrollment shart emas."""
    lesson_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        if not lesson or not lesson.is_preview or not lesson.has_video:
            await callback.answer("Bu dars bepul preview emas", show_alert=True)
            return

    await callback.answer("🎬 Video yuborilmoqda...")
    # protect_content=True — video boshqa chatga forward qilinmaydi va
    # galereyaga/qurilmaga saqlab bo'lmaydi (Telegramning o'z himoyasi).
    await bot.copy_message(
        chat_id=callback.from_user.id,
        from_chat_id=lesson.video_chat_id,
        message_id=lesson.video_message_id,
        protect_content=True,
    )
    await callback.message.answer(
        "☝️ Bu — bepul <b>preview</b> dars. To'liq kursni ko'rish uchun 🛒 sotib oling."
    )


@router.callback_query(F.data.startswith("buy:"))
async def buy_course(callback: CallbackQuery, state: FSMContext) -> None:
    course_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        result = await session.execute(select(PaymentCard).where(PaymentCard.is_active == True))  # noqa: E712
        active_cards = result.scalars().all()

        if not active_cards:
            await callback.answer(
                "To'lov usuli hali sozlanmagan. Iltimos, admin bilan bog'laning.",
                show_alert=True,
            )
            return

        course = await session.get(Course, course_id)
        if not course or course.status != CourseStatus.APPROVED:
            await callback.answer("Kurs topilmadi", show_alert=True)
            return

        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        student = result.scalar_one_or_none()
        if not student:
            await callback.answer("Iltimos avval /start bosing.", show_alert=True)
            return

        result = await session.execute(
            select(Enrollment).where(Enrollment.student_id == student.id, Enrollment.course_id == course.id)
        )
        if result.scalar_one_or_none():
            await callback.answer("Siz bu kursga allaqachon yozilgansiz ✅", show_alert=True)
            return

        result = await session.execute(
            select(Payment).where(
                Payment.student_id == student.id,
                Payment.course_id == course.id,
                Payment.status == PaymentStatus.PENDING,
            )
        )
        payment = result.scalar_one_or_none()
        if not payment:
            payment = Payment(
                student_id=student.id,
                teacher_id=course.teacher_id,
                course_id=course.id,
                amount=course.price,
            )
            session.add(payment)
            await session.commit()
            await session.refresh(payment)

    await callback.answer()

    if len(active_cards) == 1:
        await _start_receipt_wait(callback.message, state, payment, course, active_cards[0])
        return

    # Bir nechta faol karta bor — o'quvchi qaysi biriga to'lashni tanlaydi.
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 {c.label}", callback_data=f"pickcard:{payment.id}:{c.id}")]
        for c in active_cards
    ])
    await callback.message.answer(
        f"🎓 <b>{course.title}</b> — {fmt_money(course.price)}\n\n"
        "Qaysi karta orqali to'lamoqchisiz?",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("pickcard:"))
async def pick_card(callback: CallbackQuery, state: FSMContext) -> None:
    _, payment_id_s, card_id_s = callback.data.split(":")
    payment_id, card_id = int(payment_id_s), int(card_id_s)

    async with async_session() as session:
        payment = await session.get(Payment, payment_id)
        card = await session.get(PaymentCard, card_id)
        if not payment or payment.status != PaymentStatus.PENDING:
            await callback.answer("Bu to'lov so'rovi endi amal qilmaydi.", show_alert=True)
            return
        if not card or not card.is_active:
            await callback.answer("Bu karta endi mavjud emas, boshqasini tanlang.", show_alert=True)
            return

        payment.card_id = card.id
        await session.commit()
        course = await session.get(Course, payment.course_id)

    await callback.answer()
    await _start_receipt_wait(callback.message, state, payment, course, card)


async def _start_receipt_wait(message: Message, state: FSMContext, payment: Payment, course: Course,
                               card: PaymentCard) -> None:
    await state.update_data(payment_id=payment.id)
    await state.set_state(BuyCourse.waiting_receipt)

    owner_line = f"\n👤 Karta egasi: {card.owner_name}" if card.owner_name else ""
    await message.answer(
        f"💳 <b>To'lovni yakunlash</b>\n"
        f"{DIVIDER}\n"
        f"🎓 Kurs: {course.title}\n"
        f"💰 Summa: <b>{fmt_money(course.price)}</b>\n"
        f"{DIVIDER}\n"
        f"Quyidagi kartaga aynan shu summani o'tkazing:\n\n"
        f"💳 {card.label}\n<code>{card.card_number}</code>{owner_line}\n\n"
        f"✅ To'lovni amalga oshirgach, <b>chek skrinshotini shu yerga rasm qilib yuboring</b>.\n"
        f"Admin tekshirib chiqib, kursni ochadi — odatda bir necha daqiqa ichida."
    )


@router.message(BuyCourse.waiting_receipt, F.photo)
async def receive_receipt(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    payment_id = data.get("payment_id")
    await state.clear()

    async with async_session() as session:
        payment = await session.get(Payment, payment_id) if payment_id else None
        if not payment or payment.status != PaymentStatus.PENDING:
            await message.answer("Bu to'lov so'rovi endi amal qilmaydi. Qaytadan '📚 Kurslar' dan urinib ko'ring.")
            return

        payment.receipt_file_id = message.photo[-1].file_id
        await session.commit()

        student = await session.get(User, payment.student_id)
        course = await session.get(Course, payment.course_id)
        card = await session.get(PaymentCard, payment.card_id) if payment.card_id else None
        owner_id = await get_owner_telegram_id()

    card_line = f"💳 Karta: {card.label}\n" if card else ""
    caption = (
        f"🧾 <b>Yangi chek — tekshirish kerak</b>\n"
        f"{DIVIDER}\n"
        f"👤 O'quvchi: {student.full_name or '—'} (@{student.username or '—'})\n"
        f"🆔 Telegram ID: <code>{student.telegram_id}</code>\n"
        f"🎓 Kurs: {course.title}\n"
        f"💰 Summa: <b>{fmt_money(course.price)}</b>\n"
        f"{card_line}"
        f"{DIVIDER}\n"
        f"🔢 To'lov ID: {payment.id}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pay_ok:{payment.id}"),
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"pay_no:{payment.id}"),
    ]])
    if owner_id:
        try:
            await message.bot.send_photo(owner_id, payment.receipt_file_id, caption=caption, reply_markup=kb)
        except Exception:
            pass

    await message.answer(
        "✅ Chek qabul qilindi.\nAdmin tekshirib chiqqach, kurs avtomatik ochiladi — biroz kuting ⏳"
    )


@router.message(BuyCourse.waiting_receipt)
async def receive_receipt_wrong_type(message: Message) -> None:
    await message.answer("Iltimos, to'lov chekining <b>rasmini (screenshot)</b> yuboring.")


@router.message(F.text == "🎓 Mening kurslarim")
async def my_courses(message: Message) -> None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Iltimos avval /start bosing.")
            return

        result = await session.execute(select(Enrollment).where(Enrollment.student_id == user.id))
        enrollments = result.scalars().all()

        if not enrollments:
            await message.answer("📭 Siz hali birorta kursga yozilmagansiz.\n\n👉 '📚 Kurslar' bo'limidan tanlang!")
            return

        rows = []
        for e in enrollments:
            course = await session.get(Course, e.course_id)
            done = "🏆" if e.progress_percent >= 100 else "🎓"
            rows.append([InlineKeyboardButton(
                text=f"{done} {course.title} — {e.progress_percent}%",
                callback_data=f"mycourse:{course.id}",
            )])

    await message.answer(
        f"🎓 <b>Mening kurslarim</b>\n\nDavom ettirish uchun kursni tanlang ({len(enrollments)} ta):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


def _lesson_status_emoji(lesson_id: int, completed_ids: set[int], is_next: bool) -> str:
    if lesson_id in completed_ids:
        return "✅"
    if is_next:
        return "▶️"
    return "🔒"


@router.callback_query(F.data.startswith("mycourse:"))
async def show_course_lessons(callback: CallbackQuery) -> None:
    course_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()

        result = await session.execute(
            select(Enrollment).where(Enrollment.student_id == user.id, Enrollment.course_id == course_id)
        )
        enrollment = result.scalar_one_or_none()
        if not user or not enrollment:
            await callback.answer("Siz bu kursga yozilmagansiz", show_alert=True)
            return

        course = await session.get(Course, course_id)
        lessons = await get_ordered_lessons(session, course_id)
        completed_ids = await get_completed_lesson_ids(session, user.id, [l.id for l in lessons])

    if not lessons:
        await callback.message.edit_text(f"🎓 <b>{course.title}</b>\n\nHozircha darslar qo'shilmagan.")
        await callback.answer()
        return

    # Ketma-ket ochilish: birinchi tugallanmagan dars — "▶️" (ochiq), undan
    # keyingilari "🔒" (hali qulflangan). Tugallangan darslarni qayta ko'rish mumkin.
    next_found = False
    rows = []
    lines = [f"🎓 <b>{course.title}</b>", DIVIDER]
    for lesson in lessons:
        is_next = (lesson.id not in completed_ids) and not next_found
        if is_next:
            next_found = True
        emoji = _lesson_status_emoji(lesson.id, completed_ids, is_next)
        lines.append(f"{emoji} {lesson.title}")
        if emoji in ("✅", "▶️") and lesson.has_video:
            rows.append([InlineKeyboardButton(text=f"{emoji} {lesson.title}", callback_data=f"watch:{lesson.id}")])

    percent = round(len(completed_ids) * 100 / len(lessons))
    filled = percent // 10
    bar = "🟩" * filled + "⬜️" * (10 - filled)
    lines.append(f"\n{bar} <b>{percent}%</b>")

    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data.startswith("watch:"))
async def watch_lesson(callback: CallbackQuery, bot: Bot) -> None:
    lesson_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        if not lesson or not lesson.has_video:
            await callback.answer("Video topilmadi", show_alert=True)
            return

        module = await session.get(Module, lesson.module_id)
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()

        result = await session.execute(
            select(Enrollment).where(Enrollment.student_id == user.id, Enrollment.course_id == module.course_id)
        )
        enrollment = result.scalar_one_or_none()
        if not enrollment:
            await callback.answer("Bu kursni sotib olmagansiz", show_alert=True)
            return

        # Ketma-ket ochilish tekshiruvi: dars faqat tugallangan yoki "navbatdagi" bo'lsa ochiladi.
        lessons = await get_ordered_lessons(session, module.course_id)
        completed_ids = await get_completed_lesson_ids(session, user.id, [l.id for l in lessons])
        next_found = False
        allowed = False
        for l in lessons:
            is_next = (l.id not in completed_ids) and not next_found
            if is_next:
                next_found = True
            if l.id == lesson.id and (l.id in completed_ids or is_next):
                allowed = True
                break
        if not allowed:
            await callback.answer("Avval oldingi darslarni tugating 🔒", show_alert=True)
            return

    await callback.answer("🎬 Video yuborilmoqda...")
    # Video hech qachon to'g'ridan-to'g'ri fayl/link sifatida berilmaydi —
    # faqat storage kanaldan bevosita o'quvchiga copy_message orqali yuboriladi.
    # protect_content=True — video boshqa chatga forward qilinmaydi va
    # galereyaga/qurilmaga saqlab bo'lmaydi (Telegramning o'z himoyasi).
    await bot.copy_message(
        chat_id=callback.from_user.id,
        from_chat_id=lesson.video_chat_id,
        message_id=lesson.video_message_id,
        protect_content=True,
    )

    if lesson.id in completed_ids:
        # Qayta ko'rilyapti — allaqachon tugallangan, qayta so'ramaymiz.
        await callback.message.answer("🔁 Bu darsni qayta ko'ryapsiz. Progress allaqachon hisoblangan.")
        return

    # MUHIM: Bot API videoni "necha foiz ko'rilgani"ni bermaydi (texnik
    # cheklov — Telegram player'dan botga signal kelmaydi). Shu sababli
    # eng yaqin va halol yechim — video yuborilgach darhol "tugallandi"
    # deb belgilamaslik, balki o'quvchining o'zidan tasdiq so'rash.
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Darsni ko'rib bo'ldim", callback_data=f"complete:{lesson.id}"),
    ]])
    await callback.message.answer(
        "Darsni ko'rib bo'lgach, quyidagi tugmani bosing — shunda progress yangilanadi "
        "va keyingi dars ochiladi 👇",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("complete:"))
async def confirm_lesson_completed(callback: CallbackQuery, bot: Bot) -> None:
    lesson_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        if not lesson:
            await callback.answer("Dars topilmadi", show_alert=True)
            return
        module = await session.get(Module, lesson.module_id)

        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()

        result = await session.execute(
            select(Enrollment).where(Enrollment.student_id == user.id, Enrollment.course_id == module.course_id)
        )
        if not result.scalar_one_or_none():
            await callback.answer("Bu kursni sotib olmagansiz", show_alert=True)
            return

        await mark_lesson_completed(session, user.id, lesson.id)
        percent = await recalculate_enrollment_progress(session, user.id, module.course_id)

        # Keyingi darsni topib, tezkor o'tish tugmasini beramiz.
        lessons = await get_ordered_lessons(session, module.course_id)
        completed_ids = await get_completed_lesson_ids(session, user.id, [l.id for l in lessons])
        next_lesson = next((l for l in lessons if l.id not in completed_ids), None)

        # 🏆 Kurs 100% tugagan bo'lsa — sertifikat AVTOMATIK beriladi (bir marta).
        new_certificate = None
        if percent >= 100:
            new_certificate = await issue_certificate_if_completed(session, user.id, module.course_id, percent)
            course = await session.get(Course, module.course_id)

    filled = percent // 10
    bar = "🟩" * filled + "⬜️" * (10 - filled)

    rows = []
    if next_lesson:
        rows.append([InlineKeyboardButton(text=f"▶️ Keyingi dars: {next_lesson.title}", callback_data=f"watch:{next_lesson.id}")])
    else:
        rows.append([InlineKeyboardButton(text="🏆 Kurs tugadi!", callback_data="noop")])

    await callback.message.edit_text(
        f"✅ Dars tugallandi!\n\n{bar} <b>{percent}%</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()

    if new_certificate:
        await _send_certificate_pdf(bot, callback.from_user.id, new_certificate, congrats=True)


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    await callback.answer("🎉 Tabriklaymiz, kursni tugatdingiz!", show_alert=True)


async def _send_certificate_pdf(bot: Bot, chat_id: int, certificate: Certificate, congrats: bool = False) -> None:
    async with async_session() as session:
        student = await session.get(User, certificate.student_id)
        course = await session.get(Course, certificate.course_id)
        teacher = await session.get(User, course.teacher_id) if course else None
        if not (student and course):
            return
        pdf_bytes = render_certificate_pdf(certificate, student, course, teacher)

    filename = f"sertifikat_{certificate.code}.pdf"
    caption = (
        f"🏆 <b>Tabriklaymiz!</b>\n\n"
        f"Siz <b>{course.title}</b> kursini 100% tugatdingiz.\n"
        f"Sertifikat kodi: <code>{certificate.code}</code>"
        if congrats else
        f"🏆 <b>{course.title}</b>\nSertifikat kodi: <code>{certificate.code}</code>"
    )
    await bot.send_document(
        chat_id,
        BufferedInputFile(pdf_bytes, filename=filename),
        caption=caption,
    )


@router.message(F.text == "📊 Progressim")
async def my_progress(message: Message) -> None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Iltimos avval /start bosing.")
            return

        result = await session.execute(select(Enrollment).where(Enrollment.student_id == user.id))
        enrollments = result.scalars().all()

        if not enrollments:
            await message.answer("📭 Siz hali birorta kursga yozilmagansiz.\n\n👉 '📚 Kurslar' bo'limidan tanlang!")
            return

        lines = ["📊 <b>Progressim</b>", DIVIDER]
        for e in enrollments:
            course = await session.get(Course, e.course_id)
            filled = e.progress_percent // 10
            bar = "🟩" * filled + "⬜️" * (10 - filled)
            lines.append(f"\n🎓 <b>{course.title}</b>\n{bar} {e.progress_percent}%")

    await message.answer("\n".join(lines))


@router.message(F.text == "💳 To'lovlarim")
async def my_payments(message: Message) -> None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Iltimos avval /start bosing.")
            return

        result = await session.execute(
            select(Payment).where(Payment.student_id == user.id).order_by(Payment.created_at.desc())
        )
        payments = result.scalars().all()

    if not payments:
        await message.answer("📭 Hali to'lovlar tarixi yo'q.")
        return

    lines = ["💳 <b>To'lovlarim</b>", DIVIDER]
    async with async_session() as session:
        for p in payments:
            course = await session.get(Course, p.course_id)
            lines.append(
                f"🎓 {course.title if course else '—'}\n"
                f"{fmt_money(p.amount)} · {fmt_date(p.created_at)} · {PAYMENT_STATUS_LABEL[p.status]}\n"
            )
    await message.answer("\n".join(lines))


@router.message(F.text == "🏆 Sertifikatlarim")
async def my_certificates(message: Message) -> None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Iltimos avval /start bosing.")
            return

        result = await session.execute(
            select(Certificate).where(Certificate.student_id == user.id).order_by(Certificate.issued_at.desc())
        )
        certificates = result.scalars().all()

        if not certificates:
            await message.answer(
                "📭 Hali sertifikatingiz yo'q.\n\nBiror kursni 100% tugatsangiz, "
                "sertifikat avtomatik shu yerda paydo bo'ladi 🏆"
            )
            return

        rows = []
        for cert in certificates:
            course = await session.get(Course, cert.course_id)
            rows.append([InlineKeyboardButton(
                text=f"📄 {course.title if course else '—'}",
                callback_data=f"certdl:{cert.id}",
            )])

    await message.answer(
        f"🏆 <b>Sertifikatlarim</b>\n\nYuklab olish uchun tanlang ({len(certificates)} ta):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("certdl:"))
async def download_certificate(callback: CallbackQuery, bot: Bot) -> None:
    cert_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        certificate = await session.get(Certificate, cert_id)
        if not certificate:
            await callback.answer("Sertifikat topilmadi", show_alert=True)
            return

        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if not user or certificate.student_id != user.id:
            await callback.answer("Bu sertifikat sizga tegishli emas", show_alert=True)
            return

    await callback.answer("📄 Sertifikat tayyorlanmoqda...")
    await _send_certificate_pdf(bot, callback.from_user.id, certificate, congrats=False)


@router.message(F.text == "👤 Profil")
async def my_profile(message: Message) -> None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("Iltimos avval /start bosing.")
            return

        enrollment_count = len((await session.execute(
            select(Enrollment).where(Enrollment.student_id == user.id)
        )).scalars().all())
        cert_count = len((await session.execute(
            select(Certificate).where(Certificate.student_id == user.id)
        )).scalars().all())

    role_label = {"STUDENT": "👨‍🎓 O'quvchi", "TEACHER": "👨‍🏫 O'qituvchi", "ADMIN": "🛠 Admin"}
    text = (
        f"👤 <b>Profil</b>\n"
        f"{DIVIDER}\n"
        f"Ism: <b>{user.full_name or '—'}</b>\n"
        f"Username: @{user.username or '—'}\n"
        f"Telegram ID: <code>{user.telegram_id}</code>\n"
        f"Rol: {role_label.get(user.role.value, user.role.value)}\n"
        f"Ro'yxatdan o'tgan: {fmt_date(user.created_at)}\n"
        f"{DIVIDER}\n"
        f"🎓 Kurslari: {enrollment_count} ta\n"
        f"🏆 Sertifikatlari: {cert_count} ta"
    )
    await message.answer(text)


@router.message(F.text == "💬 Yordam")
async def help_message(message: Message) -> None:
    contact_value = await get_setting(SUPPORT_CONTACT_KEY, default=f"@{config.SUPPORT_USERNAME}")
    contact_url = resolve_contact_url(contact_value) or f"https://t.me/{config.SUPPORT_USERNAME}"

    text = (
        "💬 <b>Yordam</b>\n\n"
        "Savol yoki muammo bo'lsa, bemalol yozing:\n"
        f"👉 {contact_value}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✍️ Adminga yozish", url=contact_url),
    ]])
    await message.answer(text, reply_markup=kb)
