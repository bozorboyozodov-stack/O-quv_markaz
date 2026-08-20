from aiogram.fsm.state import State, StatesGroup


class CreateCourse(StatesGroup):
    title = State()
    description = State()
    price = State()
    category = State()


class PromoteTeacher(StatesGroup):
    waiting_telegram_id = State()


class AddCard(StatesGroup):
    waiting_label = State()
    waiting_card_number = State()
    waiting_card_owner = State()


class BuyCourse(StatesGroup):
    waiting_receipt = State()


class AddLesson(StatesGroup):
    waiting_module_title = State()   # yangi modul yaratilayotganda
    waiting_lesson_title = State()
    waiting_video = State()


class EditModule(StatesGroup):
    waiting_title = State()


class EditLesson(StatesGroup):
    waiting_title = State()
    waiting_video = State()
