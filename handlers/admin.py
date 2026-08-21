from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func

from database.db import async_session
from database.models import User, RoleEnum, Course, CourseStatus, Payment, PaymentStatus, PaymentCard, Withdrawal, WithdrawalStatus, Enrollment
from states.teacher_states import PromoteTeacher, AddCard, RejectWithdrawal
from utils.payments import approve_payment, reject_payment, notify_student_approved, notify_student_rejected
from utils.withdrawals import approve_withdrawal, reject_withdrawal, notify_teacher_withdrawal_approved, notify_teacher_withdrawal_rejected, get_admin_balance
from utils.income import get_income_summary
from utils.format import fmt_money, fmt_date, DIVIDER
from config import ADMIN_IDS

router = Router()


async def _require_admin(message: Message) -> User | None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
    if not user or user.role != RoleEnum.ADMIN:
        await message.answer("Bu bo'lim faqat adminlar uchun.")
        return None
    return user


@router.message(Command("admin"))
async def open_admin_panel(message: Message) -> None:
    """To'g'ridan-to'g'ri admin panelga kirish uchun tezkor buyruq.

    ADMIN_IDS'ga qo'shilgan bo'lsangiz, DB'dagi eski rolni ham avtomatik
    ADMIN'ga ko'taradi (masalan, avval oddiy o'quvchi sifatida start bosgan
    bo'lsangiz)."""
    from keyboards.common import admin_main_menu

    telegram_id = message.from_user.id

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()

        if not user:
            await message.answer("Avval /start bosing, keyin qaytadan /admin yuboring.")
            return

        if telegram_id in ADMIN_IDS and user.role != RoleEnum.ADMIN:
            user.role = RoleEnum.ADMIN
            await session.commit()

        is_admin = user.role == RoleEnum.ADMIN

    if not is_admin:
        await message.answer(
            "⛔️ Sizda admin huquqi yo'q.\n\n"
            f"🆔 Sizning Telegram ID'ingiz: <code>{telegram_id}</code>\n\n"
            "Admin bo'lish uchun bu ID'ni Railway (yoki serveringiz) muhit "
            "o'zgaruvchilarida <code>ADMIN_IDS</code> qiymatiga qo'shing, "
            "botni qayta ishga tushiring va yana /admin yuboring."
        )
        return

    await message.answer("🛠 <b>Admin panel</b>", reply_markup=admin_main_menu())


@router.message(F.text == "📊 Dashboard")
async def dashboard(message: Message) -> None:
    if not await _require_admin(message):
        return

    async with async_session() as session:
        students = (await session.execute(
            select(func.count()).select_from(User).where(User.role == RoleEnum.STUDENT)
        )).scalar_one()
        teachers = (await session.execute(
            select(func.count()).select_from(User).where(User.role == RoleEnum.TEACHER)
        )).scalar_one()
        courses = (await session.execute(select(func.count()).select_from(Course))).scalar_one()
        pending = (await session.execute(
            select(func.count()).select_from(Course).where(Course.status == CourseStatus.PENDING)
        )).scalar_one()
        paid_sum = (await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == PaymentStatus.PAID)
        )).scalar_one()
        pending_receipts = (await session.execute(
            select(func.count()).select_from(Payment).where(
                Payment.status == PaymentStatus.PENDING, Payment.receipt_file_id != ""
            )
        )).scalar_one()

    text = (
        "📊 <b>Dashboard</b>\n"
        f"{DIVIDER}\n"
        f"👨‍🎓 O'quvchilar: {students}\n"
        f"👨‍🏫 O'qituvchilar: {teachers}\n"
        f"📚 Kurslar: {courses}\n"
        f"🟡 Moderatsiyada: {pending}\n"
        f"{DIVIDER}\n"
        f"💰 Jami tasdiqlangan to'lovlar: <b>{fmt_money(paid_sum)}</b>\n"
        f"🧾 Tekshirish kutilayotgan cheklar: {pending_receipts}"
    )
    await message.answer(text)


@router.message(F.text == "💰 Daromad")
async def income_overview(message: Message) -> None:
    if not await _require_admin(message):
        return

    async with async_session() as session:
        income = await get_income_summary(session)

    text = (
        "💰 <b>Daromad</b>\n"
        f"{DIVIDER}\n"
        f"📅 Bugun: <b>{fmt_money(income['today'])}</b>\n"
        f"🗓 Shu hafta: <b>{fmt_money(income['week'])}</b>\n"
        f"📆 Shu oy: <b>{fmt_money(income['month'])}</b>\n"
        f"{DIVIDER}\n"
        f"🏦 Umumiy (barcha vaqt): <b>{fmt_money(income['all_time'])}</b>\n\n"
        "<i>Bu — barcha tasdiqlangan to'lovlarning yalpi summasi "
        "(o'qituvchilar ulushi + admin ulushi qo'shilgan holda).</i>"
    )
    await message.answer(text)


@router.message(F.text == "💳 Balans")
async def admin_balance_overview(message: Message) -> None:
    if not await _require_admin(message):
        return

    async with async_session() as session:
        balance = await get_admin_balance(session)

    text = (
        "💳 <b>Balans</b>\n"
        f"{DIVIDER}\n"
        f"💰 Jami tushgan pul: <b>{fmt_money(balance['total_paid'])}</b>\n"
        f"👨‍🏫 O'qituvchilar ulushi (jami): {fmt_money(balance['teacher_share_total'])}\n"
        f"✅ O'qituvchilarga to'langan: {fmt_money(balance['withdrawn_to_teachers'])}\n"
        f"{DIVIDER}\n"
        f"💵 Sizning sof ulushingiz: <b>{fmt_money(balance['admin_share'])}</b>\n"
        f"🏦 Hozir hisobingizda turgan pul: <b>{fmt_money(balance['cash_on_hand'])}</b>\n\n"
        "<i>Hozir hisobingizda turgan pul = jami tushgan pul − o'qituvchilarga "
        "allaqachon to'langan pul. Bu summaga o'qituvchilarning hali yechilmagan "
        "ulushi ham kiradi — ular yechib olishganda bu son kamayadi.</i>"
    )
    await message.answer(text)


def _moderation_kb(course_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve:{course_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject:{course_id}"),
    ]])


@router.message(F.text == "🟡 Moderatsiyadagi kurslar")
async def pending_courses(message: Message) -> None:
    if not await _require_admin(message):
        return

    async with async_session() as session:
        result = await session.execute(select(Course).where(Course.status == CourseStatus.PENDING))
        courses = result.scalars().all()

    if not courses:
        await message.answer("✅ Moderatsiyada kurs yo'q.")
        return

    await message.answer(f"🟡 <b>Moderatsiyadagi kurslar</b> ({len(courses)} ta):")
    for c in courses:
        text = f"🎓 <b>{c.title}</b>\n{fmt_money(c.price)} · 📂 {c.category or '—'}"
        await message.answer(text, reply_markup=_moderation_kb(c.id))


@router.callback_query(F.data.startswith("approve:"))
async def approve_course(callback: CallbackQuery) -> None:
    course_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        course = await session.get(Course, course_id)
        if course:
            course.status = CourseStatus.APPROVED
            await session.commit()
    old_text = callback.message.text or callback.message.caption or ""
    new_text = old_text + "\n\n✅ Tasdiqlandi"
    if callback.message.caption is not None:
        await callback.message.edit_caption(caption=new_text)
    else:
        await callback.message.edit_text(new_text)
    await callback.answer("Kurs tasdiqlandi va katalogda ko'rinadi")


@router.callback_query(F.data.startswith("reject:"))
async def reject_course(callback: CallbackQuery) -> None:
    course_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        course = await session.get(Course, course_id)
        if course:
            course.status = CourseStatus.REJECTED
            await session.commit()
    old_text = callback.message.text or callback.message.caption or ""
    new_text = old_text + "\n\n❌ Rad etildi"
    if callback.message.caption is not None:
        await callback.message.edit_caption(caption=new_text)
    else:
        await callback.message.edit_text(new_text)
    await callback.answer("Kurs rad etildi")


@router.message(F.text == "👨‍🏫 O'qituvchi qo'shish")
async def start_promote(message: Message, state: FSMContext) -> None:
    if not await _require_admin(message):
        return
    await state.set_state(PromoteTeacher.waiting_telegram_id)
    await message.answer(
        "👨‍🏫 <b>O'qituvchi qo'shish</b>\n\n"
        "O'qituvchi qilmoqchi bo'lgan foydalanuvchining Telegram ID sini yuboring.\n"
        "<i>(Foydalanuvchi botga kamida bir marta /start bosgan bo'lishi kerak)</i>"
    )


@router.message(PromoteTeacher.waiting_telegram_id)
async def finish_promote(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not message.text.isdigit():
        await message.answer("⚠️ Telegram ID faqat raqamlardan iborat bo'lishi kerak.")
        return

    target_id = int(message.text)
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("❌ Bu ID bilan foydalanuvchi topilmadi.")
            return
        user.role = RoleEnum.TEACHER
        await session.commit()

    await message.answer(f"✅ <b>{user.full_name or target_id}</b> endi o'qituvchi (TEACHER) huquqiga ega.")


@router.message(F.text == "👨‍🎓 O'quvchilar")
async def list_students(message: Message) -> None:
    if not await _require_admin(message):
        return
    async with async_session() as session:
        result = await session.execute(select(User).where(User.role == RoleEnum.STUDENT))
        students = result.scalars().all()

        if not students:
            await message.answer("📭 Hali o'quvchilar yo'q.")
            return

        student_ids = [s.id for s in students]
        result = await session.execute(
            select(Enrollment.student_id, func.count()).where(
                Enrollment.student_id.in_(student_ids)
            ).group_by(Enrollment.student_id)
        )
        course_counts = dict(result.all())

    lines = [f"👨‍🎓 <b>O'quvchilar</b> ({len(students)} ta, birinchi 30 tasi)", DIVIDER]
    rows = []
    for s in students[:30]:
        count = course_counts.get(s.id, 0)
        lines.append(
            f"{s.full_name or '—'} (@{s.username or '—'}) — <code>{s.telegram_id}</code>\n"
            f"📚 Sotib olgan kurslari: {count} ta"
        )
        rows.append([InlineKeyboardButton(
            text=f"🔍 {s.full_name or s.telegram_id} — kurslarini ko'rish",
            callback_data=f"astudent:{s.id}",
        )])

    await message.answer("\n".join(lines))
    if rows:
        await message.answer(
            "Batafsil ko'rish uchun tugmani bosing 👇",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data.startswith("astudent:"))
async def student_courses_detail(callback: CallbackQuery) -> None:
    if not await _require_admin_user(callback):
        return

    student_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        student = await session.get(User, student_id)
        if not student:
            await callback.answer("O'quvchi topilmadi", show_alert=True)
            return

        result = await session.execute(
            select(Enrollment, Course)
            .join(Course, Enrollment.course_id == Course.id)
            .where(Enrollment.student_id == student_id)
            .order_by(Enrollment.created_at.desc())
        )
        rows = result.all()

    if not rows:
        await callback.message.answer(
            f"👤 <b>{student.full_name or '—'}</b> (@{student.username or '—'})\n\n"
            "📭 Hali birorta kurs sotib olmagan."
        )
        await callback.answer()
        return

    lines = [
        f"👤 <b>{student.full_name or '—'}</b> (@{student.username or '—'})\n"
        f"🆔 <code>{student.telegram_id}</code>\n"
        f"📚 Sotib olgan kurslari: {len(rows)} ta",
        DIVIDER,
    ]
    for enrollment, course in rows:
        lines.append(
            f"🎓 <b>{course.title}</b>\n"
            f"💰 {fmt_money(course.price)} · 📊 Progress: {enrollment.progress_percent}%\n"
            f"📅 Sotib olgan sana: {fmt_date(enrollment.created_at)}"
        )

    await callback.message.answer("\n\n".join(lines))
    await callback.answer()


# ------------------------------------------------------------------
# To'lov: kartalarni boshqarish (bir nechta karta qo'llab-quvvatlanadi)
# ------------------------------------------------------------------
def _card_row_kb(card: PaymentCard) -> InlineKeyboardMarkup:
    toggle_text = "⏸ Faolsizlantirish" if card.is_active else "▶️ Faollashtirish"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=toggle_text, callback_data=f"card_toggle:{card.id}"),
        InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"card_del:{card.id}"),
    ]])


def _card_text(card: PaymentCard) -> str:
    status = "✅ Faol" if card.is_active else "⏸ Faolsiz"
    owner_line = f"\n👤 {card.owner_name}" if card.owner_name else ""
    return f"💳 <b>{card.label}</b>\n<code>{card.card_number}</code>{owner_line}\n{status}"


@router.message(F.text == "💳 Kartalar")
async def list_cards(message: Message) -> None:
    if not await _require_admin(message):
        return

    async with async_session() as session:
        result = await session.execute(select(PaymentCard).order_by(PaymentCard.created_at))
        cards = result.scalars().all()

    if not cards:
        await message.answer("📭 Hali karta qo'shilmagan.")
    else:
        await message.answer(f"💳 <b>To'lov kartalari</b> ({len(cards)} ta)")
        for card in cards:
            await message.answer(_card_text(card), reply_markup=_card_row_kb(card))

    await message.answer(
        "Yangi karta qo'shish uchun tugmani bosing 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="➕ Yangi karta qo'shish", callback_data="card_add"),
        ]]),
    )


@router.callback_query(F.data == "card_add")
async def start_add_card(callback: CallbackQuery, state: FSMContext) -> None:
    admin = await _require_admin_user(callback)
    if not admin:
        return
    await state.set_state(AddCard.waiting_label)
    await callback.message.answer(
        "➕ <b>Yangi karta qo'shish</b>\n\n"
        "1️⃣ Karta uchun nom kiriting (masalan: \"Uzcard — asosiy\" yoki \"Humo — Ali aka\"):"
    )
    await callback.answer()


@router.message(AddCard.waiting_label)
async def add_card_label(message: Message, state: FSMContext) -> None:
    await state.update_data(label=message.text.strip())
    await state.set_state(AddCard.waiting_card_number)
    await message.answer("2️⃣ Karta raqamini kiriting (masalan: 8600 1234 5678 9012):")


@router.message(AddCard.waiting_card_number)
async def add_card_number(message: Message, state: FSMContext) -> None:
    await state.update_data(card_number=message.text.strip())
    await state.set_state(AddCard.waiting_card_owner)
    await message.answer("3️⃣ Karta egasining F.I.Sh. sini kiriting (yoki o'tkazib yuborish uchun /skip):")


async def _finish_add_card(message: Message, state: FSMContext, owner_name: str) -> None:
    data = await state.get_data()
    await state.clear()
    async with async_session() as session:
        card = PaymentCard(
            label=data["label"], card_number=data["card_number"], owner_name=owner_name, is_active=True,
        )
        session.add(card)
        await session.commit()
        await session.refresh(card)
    await message.answer("✅ Karta qo'shildi:\n\n" + _card_text(card), reply_markup=_card_row_kb(card))


@router.message(AddCard.waiting_card_owner, F.text == "/skip")
async def add_card_owner_skip(message: Message, state: FSMContext) -> None:
    await _finish_add_card(message, state, "")


@router.message(AddCard.waiting_card_owner)
async def add_card_owner(message: Message, state: FSMContext) -> None:
    await _finish_add_card(message, state, message.text.strip())


@router.callback_query(F.data.startswith("card_toggle:"))
async def toggle_card(callback: CallbackQuery) -> None:
    admin = await _require_admin_user(callback)
    if not admin:
        return
    card_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        card = await session.get(PaymentCard, card_id)
        if not card:
            await callback.answer("Karta topilmadi", show_alert=True)
            return
        card.is_active = not card.is_active
        await session.commit()
        await callback.message.edit_text(_card_text(card), reply_markup=_card_row_kb(card))
    await callback.answer("Yangilandi ✅")


@router.callback_query(F.data.startswith("card_del:"))
async def delete_card(callback: CallbackQuery) -> None:
    admin = await _require_admin_user(callback)
    if not admin:
        return
    card_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        card = await session.get(PaymentCard, card_id)
        if card:
            await session.delete(card)
            await session.commit()
    await callback.message.edit_text("🗑 Karta o'chirildi.")
    await callback.answer("O'chirildi")


# ------------------------------------------------------------------
# To'lov: chekni tasdiqlash / rad etish
# ------------------------------------------------------------------
async def _require_admin_user(callback: CallbackQuery) -> User | None:
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()
    if not user or user.role != RoleEnum.ADMIN:
        await callback.answer("Bu amal faqat adminlar uchun.", show_alert=True)
        return None
    return user


@router.callback_query(F.data.startswith("pay_ok:"))
async def confirm_payment(callback: CallbackQuery) -> None:
    admin = await _require_admin_user(callback)
    if not admin:
        return

    payment_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        payment = await session.get(Payment, payment_id)
        if not payment:
            await callback.answer("To'lov topilmadi", show_alert=True)
            return
        if payment.status != PaymentStatus.PENDING:
            await callback.answer("Bu to'lov allaqachon ko'rib chiqilgan.", show_alert=True)
            return

        await approve_payment(session, payment, admin)
        await notify_student_approved(callback.bot, session, payment)

    caption = (callback.message.caption or callback.message.text or "") + "\n\n✅ TASDIQLANDI"
    try:
        await callback.message.edit_caption(caption=caption)
    except Exception:
        await callback.message.edit_text(caption)
    await callback.answer("Tasdiqlandi, o'quvchiga xabar yuborildi ✅")


@router.callback_query(F.data.startswith("pay_no:"))
async def cancel_payment(callback: CallbackQuery) -> None:
    admin = await _require_admin_user(callback)
    if not admin:
        return

    payment_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        payment = await session.get(Payment, payment_id)
        if not payment:
            await callback.answer("To'lov topilmadi", show_alert=True)
            return
        if payment.status != PaymentStatus.PENDING:
            await callback.answer("Bu to'lov allaqachon ko'rib chiqilgan.", show_alert=True)
            return

        await reject_payment(session, payment, admin)
        await notify_student_rejected(callback.bot, session, payment)

    caption = (callback.message.caption or callback.message.text or "") + "\n\n❌ BEKOR QILINDI"
    try:
        await callback.message.edit_caption(caption=caption)
    except Exception:
        await callback.message.edit_text(caption)
    await callback.answer("Bekor qilindi, o'quvchiga xabar yuborildi")


# ------------------------------------------------------------------
# 💳 Pul yechish so'rovlarini tasdiqlash / rad etish
# ------------------------------------------------------------------
@router.callback_query(F.data.startswith("wd_ok:"))
async def confirm_withdrawal(callback: CallbackQuery) -> None:
    admin = await _require_admin_user(callback)
    if not admin:
        return

    withdrawal_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        withdrawal = await session.get(Withdrawal, withdrawal_id)
        if not withdrawal:
            await callback.answer("So'rov topilmadi", show_alert=True)
            return
        if withdrawal.status != WithdrawalStatus.PENDING:
            await callback.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
            return

        await approve_withdrawal(session, withdrawal, admin)
        await notify_teacher_withdrawal_approved(callback.bot, session, withdrawal)

    old_text = callback.message.text or callback.message.caption or ""
    new_text = old_text + "\n\n✅ TASDIQLANDI"
    try:
        await callback.message.edit_text(new_text)
    except Exception:
        await callback.message.edit_caption(caption=new_text)
    await callback.answer("Tasdiqlandi, o'qituvchiga xabar yuborildi ✅")


@router.callback_query(F.data.startswith("wd_no:"))
async def start_reject_withdrawal(callback: CallbackQuery, state: FSMContext) -> None:
    admin = await _require_admin_user(callback)
    if not admin:
        return

    withdrawal_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        withdrawal = await session.get(Withdrawal, withdrawal_id)
        if not withdrawal:
            await callback.answer("So'rov topilmadi", show_alert=True)
            return
        if withdrawal.status != WithdrawalStatus.PENDING:
            await callback.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
            return

    await state.set_state(RejectWithdrawal.waiting_reason)
    await state.update_data(withdrawal_id=withdrawal_id, chat_id=callback.message.chat.id,
                             message_id=callback.message.message_id)
    await callback.message.answer(
        f"❌ <b>Rad etish sababi</b>\n\n"
        f"🔢 So'rov ID: {withdrawal_id}\n\n"
        "Sababini yozib yuboring — bu matn o'qituvchiga aynan shu ko'rinishda ko'rsatiladi:"
    )
    await callback.answer()


@router.message(RejectWithdrawal.waiting_reason)
async def finish_reject_withdrawal(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()

    withdrawal_id = data.get("withdrawal_id")
    reason = (message.text or "").strip()
    if not reason:
        await message.answer("⚠️ Iltimos sababni matn ko'rinishida yuboring.")
        await state.set_state(RejectWithdrawal.waiting_reason)
        await state.update_data(**data)
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        admin = result.scalar_one_or_none()
        withdrawal = await session.get(Withdrawal, withdrawal_id) if withdrawal_id else None
        if not withdrawal or not admin:
            await message.answer("So'rov topilmadi yoki allaqachon ko'rib chiqilgan.")
            return
        if withdrawal.status != WithdrawalStatus.PENDING:
            await message.answer("Bu so'rov allaqachon ko'rib chiqilgan.")
            return

        await reject_withdrawal(session, withdrawal, admin, reason)
        await notify_teacher_withdrawal_rejected(message.bot, session, withdrawal)

    chat_id = data.get("chat_id")
    message_id = data.get("message_id")
    if chat_id and message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text=f"💳 So'rov #{withdrawal_id}\n\n❌ RAD ETILDI\nSababi: {reason}",
            )
        except Exception:
            pass

    await message.answer(f"✅ Rad etildi va o'qituvchiga sabab bilan xabar yuborildi.\n\nSababi: {reason}")
