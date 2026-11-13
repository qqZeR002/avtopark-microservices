"""Тесты правил выпуска машины. Запуск: cd services/trips && python -m pytest"""
from datetime import datetime, timezone
from types import SimpleNamespace

from app import rules

VEHICLE = {"id": 1, "plate": "1234 AB-7", "category": "C", "active": True}
DRIVER = {"id": 1, "full_name": "Иванов И. И.", "categories": ["B", "C"], "active": True}


def moment(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc)


def trip(status="finished", finished_at=None, serviced_at=None):
    return SimpleNamespace(status=status, vehicle_plate="1234 AB-7", started_at=moment(2, 6),
                           finished_at=finished_at, serviced_at=serviced_at)


def start(vehicle=VEHICLE, driver=DRIVER, last_vehicle_trip=None, last_driver_trip=None, at=None):
    return rules.check_trip_start(vehicle, driver, last_vehicle_trip, last_driver_trip, at or moment(3, 9))


def test_first_trip_is_allowed():
    assert start() is None


def test_driver_on_active_trip_cannot_take_second_car():  # БП-1
    assert "сейчас в поездке" in start(last_driver_trip=trip(status="active"))


def test_vehicle_on_active_trip_is_refused():  # БП-2
    assert "сейчас в поездке" in start(last_vehicle_trip=trip(status="active"))


def test_vehicle_without_service_is_refused():  # БП-4
    last = trip(finished_at=moment(2, 10), serviced_at=None)
    assert "не прошла обслуживание" in start(last_vehicle_trip=last)


def test_serviced_vehicle_is_allowed():  # БП-4
    last = trip(finished_at=moment(2, 10), serviced_at=moment(2, 12))
    assert start(last_vehicle_trip=last) is None


def test_trip_cannot_start_before_service_ended():  # БП-8
    last = trip(finished_at=moment(2, 10), serviced_at=moment(3, 10))
    assert "раньше" in start(last_vehicle_trip=last, at=moment(3, 9))


def test_driver_without_category_is_refused():  # БП-6
    driver = {**DRIVER, "categories": ["B"]}
    assert "нет категории C" in start(driver=driver)


def test_inactive_vehicle_and_driver_are_refused():  # БП-7
    assert "списана" in start(vehicle={**VEHICLE, "active": False})
    assert "уволен" in start(driver={**DRIVER, "active": False})


def test_future_time_is_refused():  # БП-9
    assert "будущем" in start(at=datetime(2099, 1, 1, tzinfo=timezone.utc))


def test_finish_must_be_after_start():  # БП-8
    active = trip(status="active")
    assert rules.check_trip_finish(active, moment(2, 5)) is not None
    assert rules.check_trip_finish(active, moment(2, 8)) is None


def test_finished_trip_cannot_be_finished_again():
    assert "уже закрыта" in rules.check_trip_finish(trip(finished_at=moment(2, 10)), moment(2, 11))
