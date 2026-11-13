"""Тесты расчёта отчётов. Запуск: cd services/reports && python -m pytest"""
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app import calc

MINSK = ZoneInfo("Europe/Minsk")


def local(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=MINSK)


WEEK_START = local(2, 0)
WEEK_END = local(9, 0)
NOW = local(13, 12)


def trip(started_at, finished_at, distance_km=100, vehicle_id=1, driver_id=1):
    return SimpleNamespace(vehicle_id=vehicle_id, vehicle_plate=f"car-{vehicle_id}",
                           driver_id=driver_id, driver_name=f"driver-{driver_id}",
                           started_at=started_at, finished_at=finished_at, distance_km=distance_km)


def service(created_at, started_at, finished_at, vehicle_id=1):
    return SimpleNamespace(vehicle_id=vehicle_id, vehicle_plate=f"car-{vehicle_id}",
                           created_at=created_at, started_at=started_at, finished_at=finished_at)


def test_overlap_hours():
    assert calc.overlap_hours(local(2, 9), local(2, 12, 30), WEEK_START, WEEK_END) == 3.5
    # отрезок начался до периода - считаем только часть внутри
    assert calc.overlap_hours(local(1, 22), local(2, 2), WEEK_START, WEEK_END) == 2.0
    # отрезок целиком вне периода
    assert calc.overlap_hours(local(10, 9), local(10, 12), WEEK_START, WEEK_END) == 0.0


def test_hours_by_day_splits_night_trip():
    result = calc.hours_by_day(local(4, 22), local(5, 2), WEEK_START, WEEK_END, MINSK)
    assert result == {"2026-11-04": 2.0, "2026-11-05": 2.0}


def test_vehicle_report():
    trips = [trip(local(2, 9), local(2, 12, 30), 120), trip(local(3, 11), local(3, 15), 80)]
    services = [service(local(2, 12, 30), local(3, 8, 30), local(3, 10))]
    rows = calc.vehicle_report(trips, services, WEEK_START, WEEK_END, NOW)
    assert rows == [{
        "vehicle_id": 1, "vehicle_plate": "car-1", "trips_count": 2, "distance_km": 200.0,
        "hours_on_trips": 7.5, "hours_waiting_service": 20.0, "hours_in_service": 1.5,
        "utilization_percent": 4.5,
    }]


def test_vehicle_report_ignores_trips_outside_period():
    rows = calc.vehicle_report([trip(local(10, 9), local(10, 12))], [], WEEK_START, WEEK_END, NOW)
    assert rows == []


def test_unfinished_trip_counts_until_now():
    now = local(3, 12)
    rows = calc.driver_report([trip(local(3, 9), None, None)], WEEK_START, WEEK_END, now, MINSK)
    assert rows[0]["hours_worked"] == 3.0
    assert rows[0]["distance_km"] == 0.0


def test_driver_report_groups_by_driver():
    trips = [
        trip(local(2, 9), local(2, 12, 30), 120, driver_id=1),
        trip(local(3, 11), local(3, 15), 80, driver_id=1),
        trip(local(4, 22), local(5, 2), 150, vehicle_id=2, driver_id=2),
    ]
    rows = calc.driver_report(trips, WEEK_START, WEEK_END, NOW, MINSK)
    assert [row["driver_name"] for row in rows] == ["driver-1", "driver-2"]
    assert rows[0]["trips_count"] == 2
    assert rows[0]["hours_worked"] == 7.5
    assert rows[0]["hours_by_day"] == {"2026-11-02": 3.5, "2026-11-03": 4.0}
    assert rows[1]["hours_by_day"] == {"2026-11-04": 2.0, "2026-11-05": 2.0}
