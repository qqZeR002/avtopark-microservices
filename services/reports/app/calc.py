"""Расчёт отчётов. Функции работают с обычными объектами, без базы и сети."""
from datetime import datetime, time, timedelta


def overlap_hours(start: datetime, end: datetime, period_start: datetime, period_end: datetime) -> float:
    """Сколько часов отрезка [start, end] попадает в период."""
    begin = max(start, period_start)
    finish = min(end, period_end)
    if finish <= begin:
        return 0.0
    return (finish - begin).total_seconds() / 3600


def hours_by_day(start: datetime, end: datetime, period_start: datetime, period_end: datetime, tz) -> dict:
    """Раскладывает отрезок по календарным дням: {"2026-11-09": 3.5, ...}.

    Поездка может начаться вечером и закончиться на следующий день,
    тогда часы делятся между двумя днями.
    """
    result = {}
    begin = max(start, period_start).astimezone(tz)
    finish = min(end, period_end).astimezone(tz)
    while begin < finish:
        next_midnight = datetime.combine(begin.date() + timedelta(days=1), time.min, tzinfo=tz)
        piece_end = min(next_midnight, finish)
        day = begin.date().isoformat()
        result[day] = result.get(day, 0.0) + (piece_end - begin).total_seconds() / 3600
        begin = piece_end
    return result


def vehicle_report(trips, services, period_start: datetime, period_end: datetime, now: datetime) -> list[dict]:
    """ФТ-11: использование машин за период."""
    rows = {}

    def row_for(vehicle_id, plate):
        return rows.setdefault(vehicle_id, {
            "vehicle_id": vehicle_id, "vehicle_plate": plate, "trips_count": 0,
            "distance_km": 0.0, "hours_on_trips": 0.0,
            "hours_waiting_service": 0.0, "hours_in_service": 0.0,
        })

    for trip in trips:
        # незакрытая поездка считается до текущего момента
        hours = overlap_hours(trip.started_at, trip.finished_at or now, period_start, period_end)
        if hours == 0:
            continue
        row = row_for(trip.vehicle_id, trip.vehicle_plate)
        row["trips_count"] += 1
        row["hours_on_trips"] += hours
        # пробег относим к периоду, в котором поездка завершилась
        if trip.finished_at and period_start <= trip.finished_at < period_end:
            row["distance_km"] += trip.distance_km or 0

    for service in services:
        waiting = overlap_hours(service.created_at, service.started_at or now, period_start, period_end)
        working = 0.0
        if service.started_at:
            working = overlap_hours(service.started_at, service.finished_at or now, period_start, period_end)
        if waiting == 0 and working == 0:
            continue
        row = row_for(service.vehicle_id, service.vehicle_plate)
        row["hours_waiting_service"] += waiting
        row["hours_in_service"] += working

    period_hours = (period_end - period_start).total_seconds() / 3600
    for row in rows.values():
        row["utilization_percent"] = round(row["hours_on_trips"] / period_hours * 100, 1)
        for key in ("distance_km", "hours_on_trips", "hours_waiting_service", "hours_in_service"):
            row[key] = round(row[key], 2)
    return sorted(rows.values(), key=lambda row: row["vehicle_plate"])


def driver_report(trips, period_start: datetime, period_end: datetime, now: datetime, tz) -> list[dict]:
    """ФТ-12: рабочее время водителей за период."""
    rows = {}
    for trip in trips:
        end = trip.finished_at or now
        hours = overlap_hours(trip.started_at, end, period_start, period_end)
        if hours == 0:
            continue
        row = rows.setdefault(trip.driver_id, {
            "driver_id": trip.driver_id, "driver_name": trip.driver_name,
            "trips_count": 0, "hours_worked": 0.0, "distance_km": 0.0, "hours_by_day": {},
        })
        row["trips_count"] += 1
        row["hours_worked"] += hours
        if trip.finished_at and period_start <= trip.finished_at < period_end:
            row["distance_km"] += trip.distance_km or 0
        for day, day_hours in hours_by_day(trip.started_at, end, period_start, period_end, tz).items():
            row["hours_by_day"][day] = row["hours_by_day"].get(day, 0.0) + day_hours

    for row in rows.values():
        row["hours_worked"] = round(row["hours_worked"], 2)
        row["distance_km"] = round(row["distance_km"], 2)
        row["hours_by_day"] = {day: round(value, 2) for day, value in sorted(row["hours_by_day"].items())}
    return sorted(rows.values(), key=lambda row: row["driver_name"])
