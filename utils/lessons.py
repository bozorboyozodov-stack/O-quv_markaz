from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Module, Lesson, LessonProgress, Enrollment


async def get_ordered_lessons(session: AsyncSession, course_id: int) -> list[Lesson]:
    """Kursning barcha darslarini modul tartibi bo'yicha, so'ng dars tartibi
    bo'yicha qaytaradi (1-modul/1-dars, 1-modul/2-dars, 2-modul/1-dars, ...)."""
    result = await session.execute(
        select(Module).where(Module.course_id == course_id).order_by(Module.order_index)
    )
    modules = result.scalars().all()

    lessons: list[Lesson] = []
    for module in modules:
        result = await session.execute(
            select(Lesson).where(Lesson.module_id == module.id).order_by(Lesson.order_index)
        )
        lessons.extend(result.scalars().all())
    return lessons


async def get_completed_lesson_ids(session: AsyncSession, student_id: int, lesson_ids: list[int]) -> set[int]:
    if not lesson_ids:
        return set()
    result = await session.execute(
        select(LessonProgress.lesson_id).where(
            LessonProgress.student_id == student_id,
            LessonProgress.lesson_id.in_(lesson_ids),
            LessonProgress.is_completed == True,  # noqa: E712
        )
    )
    return {row[0] for row in result.all()}


async def mark_lesson_completed(session: AsyncSession, student_id: int, lesson_id: int) -> None:
    result = await session.execute(
        select(LessonProgress).where(
            LessonProgress.student_id == student_id,
            LessonProgress.lesson_id == lesson_id,
        )
    )
    progress = result.scalar_one_or_none()
    if progress:
        if not progress.is_completed:
            from datetime import datetime, timezone
            progress.is_completed = True
            progress.completed_at = datetime.now(timezone.utc)
    else:
        from datetime import datetime, timezone
        session.add(LessonProgress(
            student_id=student_id,
            lesson_id=lesson_id,
            is_completed=True,
            completed_at=datetime.now(timezone.utc),
        ))
    await session.commit()


async def recalculate_enrollment_progress(session: AsyncSession, student_id: int, course_id: int) -> int:
    """Enrollment.progress_percent ni qayta hisoblab, saqlaydi. Foizni qaytaradi."""
    lessons = await get_ordered_lessons(session, course_id)
    total = len(lessons)
    if total == 0:
        percent = 0
    else:
        completed = await get_completed_lesson_ids(session, student_id, [l.id for l in lessons])
        percent = round(len(completed) * 100 / total)

    result = await session.execute(
        select(Enrollment).where(Enrollment.student_id == student_id, Enrollment.course_id == course_id)
    )
    enrollment = result.scalar_one_or_none()
    if enrollment:
        enrollment.progress_percent = percent
        await session.commit()
    return percent
