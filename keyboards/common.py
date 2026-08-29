from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from database.models import RoleEnum


def student_main_menu(back_role: RoleEnum | None = None) -> ReplyKeyboardMarkup:
    """back_role — agar TEACHER/ADMIN vaqtincha "O'quvchi rejimi"ga o'tgan bo'lsa,
    o'z paneliga qaytish tugmasi shu yerda qo'shiladi (aks holda oddiy
    o'quvchida bunday tugma umuman ko'rinmaydi)."""
    keyboard = [
        [KeyboardButton(text="📚 Kurslar"), KeyboardButton(text="🎓 Mening kurslarim")],
        [KeyboardButton(text="📊 Progressim"), KeyboardButton(text="💳 To'lovlarim")],
        [KeyboardButton(text="🏆 Sertifikatlarim")],
        [KeyboardButton(text="👤 Profil"), KeyboardButton(text="💬 Yordam")],
    ]
    if back_role == RoleEnum.ADMIN:
        keyboard.append([KeyboardButton(text="🛠 Admin panelga qaytish")])
    elif back_role == RoleEnum.TEACHER:
        keyboard.append([KeyboardButton(text="👨‍🏫 O'qituvchi rejimi")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def teacher_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Kurslarim"), KeyboardButton(text="➕ Kurs yaratish")],
            [KeyboardButton(text="🎥 Dars qo'shish"), KeyboardButton(text="👨‍🎓 O'quvchilarim")],
            [KeyboardButton(text="💰 Daromadim")],
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="💳 Pul yechish")],
            [KeyboardButton(text="👨‍🎓 O'quvchi rejimi")],
        ],
        resize_keyboard=True,
    )


def admin_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Dashboard"), KeyboardButton(text="🟡 Moderatsiyadagi kurslar")],
            [KeyboardButton(text="🆕 Yangi kurslar")],
            [KeyboardButton(text="💰 Daromad"), KeyboardButton(text="💳 Balans")],
            [KeyboardButton(text="➕ Kurs yaratish"), KeyboardButton(text="🎥 Dars qo'shish")],
            [KeyboardButton(text="👨‍🏫 O'qituvchilar"), KeyboardButton(text="👨‍🎓 O'quvchilar")],
            [KeyboardButton(text="👑 Adminlar"), KeyboardButton(text="💳 Kartalar")],
            [KeyboardButton(text="👤 Admin lichkasi")],
            [KeyboardButton(text="👨‍🏫 O'qituvchi rejimi"), KeyboardButton(text="👨‍🎓 O'quvchi rejimi")],
        ],
        resize_keyboard=True,
    )


def menu_for_role(role: RoleEnum) -> ReplyKeyboardMarkup:
    if role == RoleEnum.ADMIN:
        return admin_main_menu()
    if role == RoleEnum.TEACHER:
        return teacher_main_menu()
    return student_main_menu()
