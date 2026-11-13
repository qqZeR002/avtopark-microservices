"""Таблицы сервиса отчётов.

Сервис не ходит в чужие базы: он слушает события и складывает у себя
только то, что нужно для отчётов.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class TripFact(Base):
    __tablename__ = "trip_facts"

    trip_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    vehicle_id: Mapped[int] = mapped_column(index=True)
    vehicle_plate: Mapped[str] = mapped_column(String(20))
    driver_id: Mapped[int] = mapped_column(index=True)
    driver_name: Mapped[str] = mapped_column(String(150))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    distance_km: Mapped[float | None] = mapped_column(Float)


class ServiceFact(Base):
    __tablename__ = "service_facts"

    order_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    vehicle_id: Mapped[int] = mapped_column(index=True)
    vehicle_plate: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # машина вернулась
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
