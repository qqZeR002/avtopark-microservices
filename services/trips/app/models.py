"""Таблицы сервиса поездок."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Машина и водитель живут в сервисе справочников, здесь только их номера
    # и копии данных, нужные для показа (госномер, ФИО)
    vehicle_id: Mapped[int] = mapped_column(index=True)
    vehicle_plate: Mapped[str] = mapped_column(String(20))
    driver_id: Mapped[int] = mapped_column(index=True)
    driver_name: Mapped[str] = mapped_column(String(150))

    purpose: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), default="active")  # active / finished
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    distance_km: Mapped[float | None] = mapped_column(Float)

    # Когда машину обслужили после этой поездки. Пусто = ещё не обслужена (БП-4)
    serviced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[str] = mapped_column(String(50))  # кто оформил выезд

    __table_args__ = (
        # БП-1 и БП-2 на уровне базы: у водителя и у машины не больше одной
        # открытой поездки, даже если два запроса пришли одновременно
        Index("one_active_trip_per_driver", "driver_id", unique=True,
              postgresql_where=text("status = 'active'")),
        Index("one_active_trip_per_vehicle", "vehicle_id", unique=True,
              postgresql_where=text("status = 'active'")),
    )


class OutboxEvent(Base):
    """Исходящие события, см. messaging.py."""
    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True)
    event_type: Mapped[str] = mapped_column(String(50))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
