from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message

from database.models import RoleEnum
from utils.roles import get_or_create_user
from keyboards.common import menu_for_role

router = Router()

_ROLE_WELCOME = {
    RoleEnum.ADMIN: "🛠 Siz <b>admin</b> sifatida kirdingiz — platformani shu yerdan boshqarasiz.",
    RoleEnum.TEACHER: "👨‍🏫 Siz <b>o'qituvchi</b> sifatida kirdingiz — kurslaringizni shu yerdan boshqarasiz.",
    RoleEnum.STUDENT: "",
}


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        full_name=message.from_user.full_name,
        username=message.from_user.username or "",
    )

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
    """Teacher/Admin bir zumda o'quvchi menyusini ham ko'rishi uchun (test qulayligi)."""
    from keyboards.common import student_main_menu
    await message.answer("👨‍🎓 O'quvchi menyusiga o'tdingiz:", reply_markup=student_main_menu())
