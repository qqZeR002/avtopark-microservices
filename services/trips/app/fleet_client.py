"""Обращения к сервису справочников по HTTP."""
import os

import httpx
from fastapi import HTTPException

FLEET_URL = os.getenv("FLEET_URL", "http://fleet:8000")


def _fetch(path: str, not_found_message: str) -> dict:
    try:
        response = httpx.get(f"{FLEET_URL}{path}", timeout=5)
    except httpx.HTTPError:
        # Риск Р6: без проверки категории выпускать машину нельзя
        raise HTTPException(503, "Справочник машин и водителей недоступен, выпуск невозможен")
    if response.status_code == 404:
        raise HTTPException(404, not_found_message)
    if response.status_code != 200:
        raise HTTPException(503, "Справочник машин и водителей ответил с ошибкой")
    return response.json()


def get_vehicle(vehicle_id: int) -> dict:
    return _fetch(f"/vehicles/{vehicle_id}", "Машина не найдена")


def get_driver(driver_id: int) -> dict:
    return _fetch(f"/drivers/{driver_id}", "Водитель не найден")
