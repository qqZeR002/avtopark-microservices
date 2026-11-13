"""Форматы запросов и ответов сервиса поездок."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .timeutil import LocalDateTime


class TripStart(BaseModel):
    vehicle_id: int
    driver_id: int
    purpose: str = Field(min_length=1, max_length=200)
    at: datetime | None = None  # время выезда; если не указано - сейчас


class TripFinish(BaseModel):
    distance_km: float = Field(gt=0, le=10000)  # БП-9
    at: datetime | None = None  # время возвращения


class TripOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vehicle_id: int
    vehicle_plate: str
    driver_id: int
    driver_name: str
    purpose: str
    status: str
    started_at: LocalDateTime
    finished_at: LocalDateTime | None
    distance_km: float | None
    serviced_at: LocalDateTime | None
    created_by: str
