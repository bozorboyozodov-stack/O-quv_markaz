from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message

from database.models import RoleEnum
from utils.roles import get_or_create_user, get_user, get_admin_telegram_ids
from keyboards.common import menu_for_role

router = Router()

_ROLE_WELCOME = {
    RoleEnum.ADMIN: "🛠 Siz <b>admin</b> sifatida kirdingiz — platformani shu yerdan boshqarasiz.",
    RoleEnum.TEACHER: "👨‍🏫 Siz <b>o'qituvchi</b> sifatida kirdingiz — kurslaringizni shu yerdan boshqarasiz.",
    RoleEnum.STUDENT: "",
}


async def _notify_admins_new_subscriber(message: Message, user) -> None:
    """Yangi obunachi DB'ga qo'shilganda barcha adminlarga xabar beradi."""
    name = message.from_user.full_name or "—"
    username = f"@{message.from_user.username}" if message.from_user.username else "—"
    text = (
        "🆕 <b>Yangi obunachi qo'shildi</b>\n"
        f"{name} ({username})\n"
        f"🆔 <code>{message.from_user.id}</code>"
    )
    admin_ids = await get_admin_telegram_ids()
    for admin_id in admin_ids:
        if admin_id == message.from_user.id:
            continue
        try:
            await message.bot.send_message(admin_id, text)
        except Exception:
            pass  # admin botni bloklagan yoki hali /start bosmagan bo'lishi mumkin


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user, created = await get_or_create_user(
        telegram_id=message.from_user.id,
        full_name=message.from_user.full_name,
        username=message.from_user.username or "",
    )

    if created:
        await _notify_admins_new_subscriber(message, user)

    first_name = message.from_user.first_name or "do'stim"
    role_line = _ROLE_WELCOME.get(user.role, "")

    text = (
        f"✨ <b>Online Academy</b>'ga xush kelibsiz, {first_name}!\n\n"
        "Ushbu bot orqali saytga chiqmasdan:\n\n"
        "📚 Kursni tanlab, xarid qilasiz\n"
        "🎥 Video darslarni tomosha qilasiz\n"
        "📊 O'z progressingizni kuzatasiz\n"
        "🏆 Kursni tugatib, sertifikat olasiz\n"
    )
    if role_line:
        text += f"\n{role_line}\n"
    text += "\n👇 Quyidagi menyudan boshlang."

    await message.answer(text, reply_markup=menu_for_role(user.role))


@router.message(F.text == "👨‍🎓 O'quvchi rejimi")
async def switch_to_student_view(message: Message) -> None:
    """Teacher/Admin bir zumda o'quvchi menyusini ham ko'rishi uchun (test qulayligi).

    Foydalanuvchining asl roli (TEACHER/ADMIN) aniqlanadi va shu rolga qaytish
    tugmasi menyuga qo'shiladi — aks holda bu yerdan chiqib ketgandan keyin
    o'z paneliga qaytib bo'lmay qolardi."""
    from keyboards.common import student_main_menu

    user = await get_user(message.from_user.id)
    back_role = user.role if user and user.role in (RoleEnum.TEACHER, RoleEnum.ADMIN) else None

    await message.answer(
        "👨‍🎓 O'quvchi menyusiga o'tdingiz:",
        reply_markup=student_main_menu(back_role=back_role),
    )


@router.message(F.text == "👨‍🏫 O'qituvchi rejimi")
async def switch_to_teacher_view(message: Message) -> None:
    """Admin kurs/dars(video) qo'shish kabi o'qituvchi funksiyalaridan
    to'g'ridan-to'g'ri foydalanishi uchun (handlers/teacher.py o'qituvchi
    funksiyalarini ADMIN roliga ham ruxsat beradi), shuningdek haqiqiy
    TEACHER foydalanuvchi "O'quvchi rejimi"dan qaytganda ham shu tugma orqali
    o'z paneliga qaytadi.
    Asosiy admin menyusiga qaytish uchun /start yoki /admin yuboring."""
    from keyboards.common import teacher_main_menu
    await message.answer(
        "👨‍🏫 O'qituvchi menyusiga qaytdingiz.\n"
        "Bu yerdan kurs yaratishingiz va darslarga video qo'shishingiz mumkin.\n\n"
        "Admin panelga qaytish uchun /admin yuboring.",
        reply_markup=teacher_main_menu(),
    )


@router.message(F.text == "🛠 Admin panelga qaytish")
async def switch_back_to_admin_view(message: Message) -> None:
    """Admin "O'quvchi rejimi"dan asosiy admin paneliga shu tugma orqali qaytadi
    (oldin faqat /admin buyrug'i orqali qaytish mumkin edi va tugma yo'q edi)."""
    from keyboards.common import admin_main_menu

    user = await get_user(message.from_user.id)
    if not user or user.role != RoleEnum.ADMIN:
        await message.answer("Bu bo'lim faqat adminlar uchun.")
        return

    await message.answer("🛠 Admin panelga qaytdingiz.", reply_markup=admin_main_menu())
