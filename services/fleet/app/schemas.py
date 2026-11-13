"""Форматы запросов и ответов сервиса справочников."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal["B", "C", "D"]


class VehicleCreate(BaseModel):
    plate: str = Field(min_length=3, max_length=20)
    model: str = Field(min_length=1, max_length=100)
    category: Category

    @field_validator("plate")
    @classmethod
    def normalize_plate(cls, value: str) -> str:
        # "1234 ab-7" и "1234 AB-7" - один и тот же номер
        return " ".join(value.upper().split())


class VehicleUpdate(BaseModel):
    model: str | None = Field(default=None, min_length=1, max_length=100)
    active: bool | None = None


class VehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plate: str
    model: str
    category: str
    active: bool


class DriverCreate(BaseModel):
    full_name: str = Field(min_length=3, max_length=150)
    license_number: str = Field(min_length=3, max_length=30)
    categories: list[Category] = Field(min_length=1)

    @field_validator("categories")
    @classmethod
    def remove_duplicates(cls, value: list[str]) -> list[str]:
        return sorted(set(value))


class DriverUpdate(BaseModel):
    categories: list[Category] | None = Field(default=None, min_length=1)
    active: bool | None = None


class DriverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    license_number: str
    categories: list[str]
    active: bool
