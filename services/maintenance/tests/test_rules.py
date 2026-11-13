"""Тесты правил обслуживания. Запуск: cd services/maintenance && python -m pytest"""
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app import rules

MINSK = ZoneInfo("Europe/Minsk")


def local(day, hour, minute=0):
    """Ноябрь 2026: 2-е число - понедельник, 7-е - суббота, 8-е - воскресенье."""
    return datetime(2026, 11, day, hour, minute, tzinfo=MINSK)


@pytest.mark.parametrize("moment, expected", [
    (local(2, 8, 0), True),     # понедельник, ровно открытие
    (local(2, 12, 30), True),   # понедельник, середина дня
    (local(6, 17, 0), True),    # пятница, ровно закрытие
    (local(2, 7, 59), False),   # за минуту до открытия
    (local(2, 17, 1), False),   # через минуту после закрытия
    (local(7, 10, 0), False),   # суббота
    (local(8, 10, 0), False),   # воскресенье
])
def test_working_time(moment, expected):  # БП-5
    assert rules.is_working_time(moment) is expected


def test_working_time_uses_fleet_timezone():
    # 06:30 по UTC - это 09:30 в Минске, сервис открыт
    utc_moment = datetime(2026, 11, 2, 6, 30, tzinfo=ZoneInfo("UTC"))
    assert rules.is_working_time(utc_moment)


def order(status="waiting", started_at=None):
    return SimpleNamespace(status=status, created_at=local(2, 12, 30), started_at=started_at)


def test_start_in_working_time_is_allowed():
    assert rules.check_service_start(order(), local(3, 9)) is None


def test_start_on_weekend_is_refused():  # БП-5
    assert "будни" in rules.check_service_start(order(), local(7, 10))


def test_start_before_vehicle_returned_is_refused():  # БП-8
    assert "раньше" in rules.check_service_start(order(), local(2, 10))


def test_start_twice_is_refused():
    assert rules.check_service_start(order(status="in_progress"), local(3, 9)) is not None


def test_finish_requires_started_service():
    assert rules.check_service_finish(order(status="waiting"), local(3, 9)) is not None


def test_finish_must_be_after_start_and_in_working_time():
    started = order(status="in_progress", started_at=local(3, 9))
    assert rules.check_service_finish(started, local(3, 8, 30)) is not None
    assert "будни" in rules.check_service_finish(started, local(3, 18))
    assert rules.check_service_finish(started, local(3, 10)) is None


def test_service_can_finish_next_working_day():
    started = order(status="in_progress", started_at=local(6, 16))  # пятница
    assert rules.check_service_finish(started, local(9, 9)) is None  # понедельник
