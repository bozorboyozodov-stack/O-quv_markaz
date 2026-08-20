from sqlalchemy import select

from database.db import async_session
from database.models import BotSetting


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
