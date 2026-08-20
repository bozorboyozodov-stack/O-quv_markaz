import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

# (chat_id, message_id) yoki callback.id -> oxirgi ko'rilgan vaqt.
# Chegaralangan hajmda saqlanadi (eski yozuvlar avtomatik chiqarib tashlanadi).
_SEEN: "OrderedDict[str, float]" = OrderedDict()
_MAX_ITEMS = 2000
_TTL_SECONDS = 15.0


def _seen_recently(key: str) -> bool:
    now = time.monotonic()

    # Eskirgan yozuvlarni tozalash
    while _SEEN and next(iter(_SEEN.values())) < now - _TTL_SECONDS:
        _SEEN.popitem(last=False)

    if key in _SEEN:
        return True

    _SEEN[key] = now
    if len(_SEEN) > _MAX_ITEMS:
        _SEEN.popitem(last=False)
    return False


class DedupMiddleware(BaseMiddleware):
    """Telegramdan bir xil update (masalan, tarmoq sekinligi tufayli qayta
    yuborilgan bitta xabar) ikki marta kelib qolsa, uni ikkinchi marta
    qayta ishlamaslik uchun himoya. Har bir xabar/callback uchun bir marta
    javob berilishini kafolatlaydi."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        key = None
        if isinstance(event, Message):
            key = f"msg:{event.chat.id}:{event.message_id}"
        elif isinstance(event, CallbackQuery):
            key = f"cb:{event.id}"

        if key and _seen_recently(key):
            return None

        return await handler(event, data)
