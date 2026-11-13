"""Форматы запросов и ответов сервиса обслуживания."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .timeutil import LocalDateTime


class ServiceStart(BaseModel):
    at: datetime | None = None  # время начала; если не указано - сейчас


class ServiceFinish(BaseModel):
    at: datetime | None = None
    comment: str | None = Field(default=None, max_length=300)


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    vehicle_id: int
    vehicle_plate: str
    status: str
    created_at: LocalDateTime
    started_at: LocalDateTime | None
    finished_at: LocalDateTime | None
    mechanic: str | None
    comment: str | None
