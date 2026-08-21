from sqlalchemy import select

from database.db import async_session
from database.models import BotSetting

SUPPORT_CONTACT_KEY = "support_contact"


async def get_setting(key: str, default: str = "") -> str:
    async with async_session() as session:
        setting = await session.get(BotSetting, key)
        return setting.value if setting else default


async def set_setting(key: str, value: str) -> None:
    async with async_session() as session:
        setting = await session.get(BotSetting, key)
        if setting:
            setting.value = value
        else:
            session.add(BotSetting(key=key, value=value))
        await session.commit()


def resolve_contact_url(value: str) -> str | None:
    """Admin kiritgan qiymatni (username yoki guruh/kanal linki) bosiladigan
    URL'ga aylantiradi.

    Qabul qilinadigan formatlar:
    - @username yoki username           -> https://t.me/username
    - t.me/username yoki telegram.me/…  -> https://t.me/username
    - https://t.me/... (guruh/kanal/username linki, shu jumladan
      https://t.me/+xxxxx taklif linklari) -> o'zgarishsiz qaytadi
    """
    value = (value or "").strip()
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("t.me/") or value.startswith("telegram.me/"):
        return "https://" + value
    username = value.lstrip("@")
    if not username:
        return None
    return f"https://t.me/{username}"
