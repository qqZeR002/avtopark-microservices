"""Бизнес-правила выпуска машины и закрытия поездки.

Функции ничего не знают про базу и сеть: получают данные и возвращают
текст причины отказа или None, если всё в порядке. Поэтому их легко тестировать.
"""
from datetime import datetime

from .timeutil import format_local, is_future


def check_trip_start(vehicle: dict, driver: dict, last_vehicle_trip, last_driver_trip,
                     moment: datetime) -> str | None:
    """vehicle и driver - данные из сервиса справочников,
    last_*_trip - последняя поездка машины / водителя (или None)."""

    # БП-9
    if is_future(moment):
        return "Время выезда не может быть в будущем"

    # БП-7
    if not vehicle["active"]:
        return f"Машина {vehicle['plate']} списана"
    if not driver["active"]:
        return f"Водитель {driver['full_name']} уволен"

    # БП-6
    if vehicle["category"] not in driver["categories"]:
        return (f"У водителя {driver['full_name']} нет категории {vehicle['category']}, "
                f"нужной для машины {vehicle['plate']}")

    # БП-1
    if last_driver_trip is not None:
        if last_driver_trip.status == "active":
            return (f"Водитель {driver['full_name']} сейчас в поездке "
                    f"на машине {last_driver_trip.vehicle_plate}")
        if moment < last_driver_trip.finished_at:
            return ("Время выезда раньше, чем водитель вернулся из прошлой поездки "
                    f"({format_local(last_driver_trip.finished_at)})")

    if last_vehicle_trip is not None:
        # БП-2
        if last_vehicle_trip.status == "active":
            return f"Машина {vehicle['plate']} сейчас в поездке"
        # БП-4
        if last_vehicle_trip.serviced_at is None:
            return f"Машина {vehicle['plate']} не прошла обслуживание после прошлой поездки"
        # БП-8
        if moment < last_vehicle_trip.serviced_at:
            return ("Время выезда раньше, чем закончилось обслуживание машины "
                    f"({format_local(last_vehicle_trip.serviced_at)})")

    return None


def check_trip_finish(trip, moment: datetime) -> str | None:
    if trip.status != "active":
        return "Поездка уже закрыта"
    if is_future(moment):
        return "Время возвращения не может быть в будущем"
    if moment <= trip.started_at:
        return f"Время возвращения должно быть позже выезда ({format_local(trip.started_at)})"
    return None
