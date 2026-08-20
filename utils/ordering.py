"""Modul va darslar tartibini (order_index) o'zgartirish uchun umumiy yordamchi.

Ham `Module` (kurs ichida), ham `Lesson` (modul ichida) uchun ishlatiladi —
ikkalasida ham `id` va `order_index` maydonlari bor, shuning uchun bitta
generic funksiya yetarli.
"""

from sqlalchemy.ext.asyncio import AsyncSession


async def move_item(session: AsyncSession, ordered_items: list, item_id: int, direction: str) -> bool:
    """`ordered_items` — order_index bo'yicha saralangan ro'yxat (Module yoki
    Lesson obyektlari). `item_id` elementni bir pog'ona yuqoriga ("up") yoki
    pastga ("down") suradi — qo'shni elementning order_index'i bilan almashadi.

    Element allaqachon chetda (birinchi/oxirgi) bo'lsa — hech narsa qilmay
    False qaytaradi. Muvaffaqiyatli surilsa — commit qilib True qaytaradi.
    """
    idx = next((i for i, it in enumerate(ordered_items) if it.id == item_id), None)
    if idx is None:
        return False

    if direction == "up":
        if idx == 0:
            return False
        other_idx = idx - 1
    elif direction == "down":
        if idx == len(ordered_items) - 1:
            return False
        other_idx = idx + 1
    else:
        raise ValueError("direction must be 'up' or 'down'")

    current, neighbor = ordered_items[idx], ordered_items[other_idx]
    current.order_index, neighbor.order_index = neighbor.order_index, current.order_index
    await session.commit()
    return True
