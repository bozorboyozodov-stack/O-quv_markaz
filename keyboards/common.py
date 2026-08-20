from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from database.models import RoleEnum


def student_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Kurslar"), KeyboardButton(text="🎓 Mening kurslarim")],
            [KeyboardButton(text="📊 Progressim"), KeyboardButton(text="💳 To'lovlarim")],
            [KeyboardButton(text="🏆 Sertifikatlarim")],
            [KeyboardButton(text="👤 Profil"), KeyboardButton(text="💬 Yordam")],
        ],
        resize_keyboard=True,
    )


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
            [KeyboardButton(text="➕ Kurs yaratish"), KeyboardButton(text="🎥 Dars qo'shish")],
            [KeyboardButton(text="👨‍🏫 O'qituvchi qo'shish"), KeyboardButton(text="👨‍🎓 O'quvchilar")],
            [KeyboardButton(text="💳 Kartalar")],
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
