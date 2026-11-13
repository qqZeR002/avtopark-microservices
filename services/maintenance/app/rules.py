"""Бизнес-правила обслуживания.

Главное правило БП-5: обслуживание проводится только в будни с 8:00 до 17:00.
Функции возвращают текст причины отказа или None, если всё в порядке.
"""
from datetime import datetime, time

from .timeutil import format_local, is_future, to_local

WORK_START = time(8, 0)
WORK_END = time(17, 0)


def is_working_time(moment: datetime) -> bool:
    local = to_local(moment)
    is_weekday = local.weekday() < 5  # 0 = понедельник, 5 и 6 = выходные
    return is_weekday and WORK_START <= local.time() <= WORK_END


def _check_moment(moment: datetime) -> str | None:
    if is_future(moment):
        return "Время не может быть в будущем"
    if not is_working_time(moment):
        return (f"Обслуживание проводится только в будни с 8:00 до 17:00, "
                f"а указано {format_local(moment)}")
    return None


def check_service_start(order, moment: datetime) -> str | None:
    if order.status != "waiting":
        return "Обслуживание по этой заявке уже начато или завершено"
    problem = _check_moment(moment)
    if problem:
        return problem
    # БП-8
    if moment < order.created_at:
        return (f"Обслуживание не может начаться раньше возвращения машины "
                f"({format_local(order.created_at)})")
    return None


def check_service_finish(order, moment: datetime) -> str | None:
    if order.status != "in_progress":
        return "Завершить можно только начатое обслуживание"
    problem = _check_moment(moment)
    if problem:
        return problem
    if moment <= order.started_at:
        return (f"Окончание должно быть позже начала обслуживания "
                f"({format_local(order.started_at)})")
    return None
