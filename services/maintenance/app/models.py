"""Таблицы сервиса обслуживания."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class ServiceOrder(Base):
    """Заявка на обслуживание машины после поездки."""
    __tablename__ = "service_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(unique=True)  # одна заявка на одну поездку
    vehicle_id: Mapped[int] = mapped_column(index=True)
    vehicle_plate: Mapped[str] = mapped_column(String(20))

    status: Mapped[str] = mapped_column(String(15), default="waiting")  # waiting / in_progress / done
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # когда машина вернулась
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mechanic: Mapped[str | None] = mapped_column(String(50))
    comment: Mapped[str | None] = mapped_column(String(300))


class OutboxEvent(Base):
    """Исходящие события, см. messaging.py."""
    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True)
    event_type: Mapped[str] = mapped_column(String(50))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
