#!/usr/bin/env python3
"""Сквозная проверка критериев приёмки из REQUIREMENTS.md (раздел 10).

Скрипт работает с запущенной системой через шлюз, как обычный пользователь.
Нужен только Python 3, дополнительные библиотеки не требуются.

    python3 scripts/check_requirements.py                # КП-1 ... КП-12
    python3 scripts/check_requirements.py --with-outage  # ещё и КП-13: остановка сервиса обслуживания

Все даты в сценарии - прошедшая неделя (2-6 ноября 2026), поэтому результат
не зависит от того, в какой день и час скрипт запущен.
"""
import json
import os
import random
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")
PASSWORDS = {
    "admin": os.getenv("ADMIN_PASSWORD", "admin_demo"),
    "dispatcher": os.getenv("DISPATCHER_PASSWORD", "dispatcher_demo"),
    "mechanic": os.getenv("MECHANIC_PASSWORD", "mechanic_demo"),
    "manager": os.getenv("MANAGER_PASSWORD", "manager_demo"),
}

tokens = {}
failed = []


def call(role, method, path, body=None):
    """Запрос к шлюзу от имени роли. Возвращает (код ответа, данные)."""
    headers = {"Content-Type": "application/json"}
    if role:
        headers["Authorization"] = "Bearer " + tokens[role]
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE_URL + "/api/" + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def check(code, title, condition, details=""):
    mark = "OK  " if condition else "FAIL"
    print(f"  [{mark}] {code}: {title}" + (f"  ->  {details}" if details else ""))
    if not condition:
        failed.append(code)


def refused(code, title, response, status=409, text=""):
    """Проверяет, что система отказала и объяснила причину."""
    actual_status, data = response
    reason = str(data.get("detail", ""))
    check(code, title, actual_status == status and text.lower() in reason.lower(), f"{actual_status}: {reason}")


def wait_for(description, get_value, seconds=30):
    """Сервисы обмениваются событиями не мгновенно, поэтому результат ждём."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        value = get_value()
        if value:
            return value
        time.sleep(0.5)
    print(f"  [FAIL] не дождались: {description}")
    failed.append(description)
    return None


def find_order(trip_id):
    orders = call("mechanic", "GET", "maintenance/orders")[1]
    return next((order for order in orders if order["trip_id"] == trip_id), None)


def trip_is_serviced(trip_id, vehicle_id):
    trips = call("dispatcher", "GET", f"trips/trips?vehicle_id={vehicle_id}")[1]
    return any(trip["id"] == trip_id and trip["serviced_at"] for trip in trips)


def service(order_id, start_at, finish_at):
    call("mechanic", "POST", f"maintenance/orders/{order_id}/start", {"at": start_at})
    return call("mechanic", "POST", f"maintenance/orders/{order_id}/finish", {"at": finish_at})


def main():
    with_outage = "--with-outage" in sys.argv
    tag = random.randint(1000, 9999)  # чтобы номера не повторялись при повторном запуске

    print("Вход под четырьмя ролями")
    for role, password in PASSWORDS.items():
        status, data = call(None, "POST", "login", {"login": role, "password": password})
        if status != 200:
            sys.exit(f"Не удалось войти как {role}: {data}. Система запущена?")
        tokens[role] = data["token"]
    refused("ФТ-13", "неверный пароль не принимается",
            call(None, "POST", "login", {"login": "admin", "password": "wrong"}), status=401)

    print("\nСправочники (администратор)")
    def add_vehicle(number, model, category):
        status, data = call("admin", "POST", "fleet/vehicles",
                            {"plate": f"{tag} AB-{number}", "model": model, "category": category})
        assert status == 201, data
        return data

    def add_driver(number, name, categories):
        status, data = call("admin", "POST", "fleet/drivers",
                            {"full_name": name, "license_number": f"BY{tag}{number}", "categories": categories})
        assert status == 201, data
        return data

    car = add_vehicle(1, "Skoda Octavia", "B")
    truck = add_vehicle(2, "МАЗ-5340", "C")
    old_car = add_vehicle(3, "Lada Granta", "B")
    ivanov = add_driver(1, f"Иванов И. И. ({tag})", ["B"])
    petrov = add_driver(2, f"Петров П. П. ({tag})", ["B", "C"])
    sidorov = add_driver(3, f"Сидоров С. С. ({tag})", ["B"])
    check("ФТ-1/2", "машины и водители добавлены", True, f"{car['plate']}, {truck['plate']}, 3 водителя")
    refused("БП-10", "повторный госномер не принимается",
            call("admin", "POST", "fleet/vehicles", {"plate": car["plate"], "model": "Копия", "category": "B"}))
    status, data = call("dispatcher", "GET", "fleet/vehicles?category=C")
    check("ФТ-4", "фильтр по категории", all(v["category"] == "C" for v in data) and len(data) >= 1)

    print("\nПрава доступа")
    refused("КП-10", "диспетчер не может добавить машину",
            call("dispatcher", "POST", "fleet/vehicles", {"plate": "X", "model": "X", "category": "B"}), status=403)
    refused("КП-10", "механик не может открыть поездку",
            call("mechanic", "POST", "trips/trips", {"vehicle_id": car["id"], "driver_id": ivanov["id"], "purpose": "x"}),
            status=403)
    refused("КП-10", "диспетчер не видит отчёты",
            call("dispatcher", "GET", "reports/vehicles?from=2026-11-02&to=2026-11-08"), status=403)
    refused("КП-10", "без входа запросы не принимаются", call(None, "GET", "fleet/vehicles"), status=401)

    print("\nПоездки (диспетчер)")
    def start_trip(vehicle, driver, at, purpose="Доставка документов"):
        return call("dispatcher", "POST", "trips/trips",
                    {"vehicle_id": vehicle["id"], "driver_id": driver["id"], "purpose": purpose, "at": at})

    status, trip1 = start_trip(car, ivanov, "2026-11-02T09:00")
    check("КП-1", "свободная машина выпущена со свободным водителем", status == 201, f"поездка №{trip1.get('id')}")
    refused("КП-2", "водитель не может вести вторую машину",
            start_trip(old_car, ivanov, "2026-11-02T09:30"), text="сейчас в поездке")
    refused("КП-3", "машина не может быть в двух поездках",
            start_trip(car, petrov, "2026-11-02T09:30"), text="сейчас в поездке")
    refused("КП-4", "водителю категории B не дают грузовик",
            start_trip(truck, sidorov, "2026-11-02T09:30"), text="нет категории")
    refused("БП-8", "поездка не может закончиться раньше, чем началась",
            call("dispatcher", "POST", f"trips/trips/{trip1['id']}/finish", {"distance_km": 10, "at": "2026-11-02T08:00"}))
    refused("БП-9", "нельзя оформить выезд из будущего",
            start_trip(old_car, sidorov, "2099-01-01T09:00"), text="будущем")

    status, data = call("dispatcher", "POST", f"trips/trips/{trip1['id']}/finish",
                        {"distance_km": 120, "at": "2026-11-02T12:30"})
    check("ФТ-6", "поездка закрыта", status == 200 and data["status"] == "finished")
    order1 = wait_for("заявка на обслуживание", lambda: find_order(trip1["id"]))
    check("КП-5", "заявка на обслуживание создана автоматически", bool(order1),
          f"заявка №{order1['id']}, состояние {order1['status']}" if order1 else "")
    refused("КП-6", "необслуженную машину выпускать нельзя",
            start_trip(car, ivanov, "2026-11-02T13:00"), text="не прошла обслуживание")

    print("\nОбслуживание (механик)")
    refused("КП-7", "вечером (19:00) сервис не работает",
            call("mechanic", "POST", f"maintenance/orders/{order1['id']}/start", {"at": "2026-11-02T19:00"}), text="будни")
    refused("КП-7", "в субботу сервис не работает",
            call("mechanic", "POST", f"maintenance/orders/{order1['id']}/start", {"at": "2026-11-07T10:00"}), text="будни")
    refused("БП-8", "обслуживание не может начаться раньше возвращения машины",
            call("mechanic", "POST", f"maintenance/orders/{order1['id']}/start", {"at": "2026-11-02T10:00"}), text="раньше")
    status, data = call("mechanic", "POST", f"maintenance/orders/{order1['id']}/start", {"at": "2026-11-03T08:30"})
    check("КП-8", "обслуживание начато во вторник в 8:30", status == 200 and data["status"] == "in_progress")
    refused("КП-6", "машину на обслуживании тоже нельзя выпустить",
            start_trip(car, ivanov, "2026-11-03T09:00"), text="не прошла обслуживание")
    refused("КП-7", "закончить в 17:30 нельзя",
            call("mechanic", "POST", f"maintenance/orders/{order1['id']}/finish", {"at": "2026-11-03T17:30"}), text="будни")
    status, data = call("mechanic", "POST", f"maintenance/orders/{order1['id']}/finish", {"at": "2026-11-03T10:00"})
    check("КП-8", "обслуживание завершено в 10:00", status == 200 and data["status"] == "done")

    print("\nПовторный выпуск")
    wait_for("сервис поездок узнал об обслуживании", lambda: trip_is_serviced(trip1["id"], car["id"]))
    refused("БП-8", "выезд не может быть раньше конца обслуживания",
            start_trip(car, ivanov, "2026-11-03T09:00"), text="раньше")
    status, trip2 = start_trip(car, ivanov, "2026-11-03T11:00")
    check("КП-9", "обслуженная машина снова выпущена", status == 201, f"поездка №{trip2.get('id')}")
    call("dispatcher", "POST", f"trips/trips/{trip2['id']}/finish", {"distance_km": 80, "at": "2026-11-03T15:00"})
    order2 = wait_for("вторая заявка", lambda: find_order(trip2["id"]))
    service(order2["id"], "2026-11-04T09:00", "2026-11-04T09:45")

    print("\nСписанная машина")
    call("admin", "PATCH", f"fleet/vehicles/{old_car['id']}", {"active": False})
    refused("КП-12", "списанную машину нельзя выпустить",
            start_trip(old_car, sidorov, "2026-11-04T09:00"), text="списана")

    print("\nОдновременные запросы")
    # Пять диспетчеров в один момент назначают одного водителя на пять разных машин
    cars = [add_vehicle(10 + i, "Renault Logan", "B") for i in range(5)]
    results = []
    threads = [threading.Thread(target=lambda c=c: results.append(start_trip(c, sidorov, "2026-11-04T10:00")[0]))
               for c in cars]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    check("НФТ-4", "из пяти одновременных выпусков одного водителя прошёл ровно один",
          results.count(201) == 1 and results.count(409) == 4, f"коды ответов: {sorted(results)}")

    print("\nНочная поездка на грузовике" + (" и отказ сервиса обслуживания" if with_outage else ""))
    status, trip3 = start_trip(truck, petrov, "2026-11-04T22:00", "Перевозка груза")
    assert status == 201, trip3
    if with_outage:
        subprocess.run(["docker", "compose", "stop", "maintenance"], check=True, capture_output=True)
        health = call(None, "GET", "health")[1]
        check("КП-13", "сервис обслуживания остановлен", health["maintenance"] != "ok", f"health: {health}")
    status, data = call("dispatcher", "POST", f"trips/trips/{trip3['id']}/finish",
                        {"distance_km": 150, "at": "2026-11-05T02:00"})
    check("КП-13" if with_outage else "ФТ-6", "поездка закрыта" + (" при остановленном сервисе" if with_outage else ""),
          status == 200)
    if with_outage:
        subprocess.run(["docker", "compose", "start", "maintenance"], check=True, capture_output=True)
        order3 = wait_for("заявка после возвращения сервиса", lambda: (
            call("mechanic", "GET", "maintenance/orders")[0] == 200 and find_order(trip3["id"])), seconds=90)
        check("КП-13", "после запуска сервис получил пропущенное событие и создал заявку", bool(order3))

    print("\nОтчёты (руководитель), период 02.11-08.11.2026")
    def vehicle_row():
        rows = call("manager", "GET", "reports/vehicles?from=2026-11-02&to=2026-11-08")[1].get("rows", [])
        row = next((r for r in rows if r["vehicle_id"] == car["id"]), None)
        # ждём, пока до отчётов дойдут все события
        return row if row and row["hours_in_service"] == 2.25 else None

    row = wait_for("данные в отчёте по машинам", vehicle_row)
    expected = {"trips_count": 2, "distance_km": 200.0, "hours_on_trips": 7.5,
                "hours_waiting_service": 38.0, "hours_in_service": 2.25, "utilization_percent": 4.5}
    check("КП-11", "отчёт по машине: 2 поездки, 200 км, 7.5 ч в пути, 38 ч ожидания, 2.25 ч в сервисе",
          bool(row) and all(row[key] == value for key, value in expected.items()), str(row))

    def driver_rows():
        rows = call("manager", "GET", "reports/drivers?from=2026-11-02&to=2026-11-08")[1].get("rows", [])
        found = {r["driver_id"]: r for r in rows}
        # ждём, пока до отчётов дойдёт закрытие ночной поездки
        ready = ivanov["id"] in found and found.get(petrov["id"], {}).get("hours_worked") == 4.0
        return found if ready else None

    rows = wait_for("данные в отчёте по водителям", driver_rows) or {}
    row = rows.get(ivanov["id"], {})
    check("КП-11", "Иванов: 7.5 ч за рулём, по дням 3.5 и 4.0",
          row.get("hours_worked") == 7.5 and row.get("hours_by_day") == {"2026-11-02": 3.5, "2026-11-03": 4.0}
          and row.get("distance_km") == 200.0, str(row.get("hours_by_day")))
    row = rows.get(petrov["id"], {})
    check("КП-11", "Петров: ночная поездка разделена между двумя днями по 2 ч",
          row.get("hours_by_day") == {"2026-11-04": 2.0, "2026-11-05": 2.0}, str(row.get("hours_by_day")))
    rows = call("manager", "GET", "reports/drivers?from=2026-11-05&to=2026-11-05")[1]["rows"]
    row = next((r for r in rows if r["driver_id"] == petrov["id"]), {})
    check("КП-11", "отчёт за один день считает только часы этого дня",
          row.get("hours_worked") == 2.0 and row.get("distance_km") == 150.0, str(row.get("hours_worked")))

    print()
    if failed:
        print(f"ИТОГ: есть ошибки ({len(failed)}): {', '.join(failed)}")
        sys.exit(1)
    print("ИТОГ: все проверки пройдены")


if __name__ == "__main__":
    main()
