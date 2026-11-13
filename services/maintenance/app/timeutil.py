"""Работа со временем.

В базе время хранится в UTC. Сотрудники вводят и видят время автопарка
(часовой пояс задаётся переменной BUSINESS_TZ).
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import PlainSerializer

BUSINESS_TZ = ZoneInfo(os.getenv("BUSINESS_TZ", "Europe/Minsk"))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_utc(moment: datetime | None) -> datetime:
    """Время из запроса -> UTC. Если время не указано, берём текущее.

    Время без часового пояса считаем временем автопарка.
    """
    if moment is None:
        return now_utc()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BUSINESS_TZ)
    return moment.astimezone(timezone.utc)


def to_local(moment: datetime) -> datetime:
    return moment.astimezone(BUSINESS_TZ)


def is_future(moment: datetime) -> bool:
    """Минута запаса нужна на случай небольшой разницы часов."""
    return moment > now_utc() + timedelta(minutes=1)


def format_local(moment: datetime) -> str:
    return to_local(moment).strftime("%d.%m.%Y %H:%M")


# Тип для ответов API: время показываем в поясе автопарка
LocalDateTime = Annotated[
    datetime,
    PlainSerializer(lambda value: to_local(value).isoformat(timespec="seconds"), return_type=str),
]
