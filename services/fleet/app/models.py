"""Таблицы справочника: машины и водители."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# Категории транспортных средств
CATEGORIES = {
    "B": "легковые автомобили",
    "C": "грузовые автомобили",
    "D": "автобусы",
}


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)
    plate: Mapped[str] = mapped_column(String(20), unique=True)  # госномер
    model: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(1))
    active: Mapped[bool] = mapped_column(Boolean, default=True)  # False = списана
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150))
    license_number: Mapped[str] = mapped_column(String(30), unique=True)
    categories: Mapped[list[str]] = mapped_column(ARRAY(String(1)))  # категории в правах
    active: Mapped[bool] = mapped_column(Boolean, default=True)  # False = уволен
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
