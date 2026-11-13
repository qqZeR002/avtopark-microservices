"""Сервис справочников: машины и водители по категориям (ФТ-1 - ФТ-4)."""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import create_tables, get_db
from .models import CATEGORIES, Driver, Vehicle
from .schemas import DriverCreate, DriverOut, DriverUpdate, VehicleCreate, VehicleOut, VehicleUpdate

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(title="Автопарк: справочники", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "service": "fleet"}


@app.get("/categories")
def list_categories():
    return CATEGORIES


# ---------- Машины ----------

@app.get("/vehicles", response_model=list[VehicleOut])
def list_vehicles(category: str | None = None, db: Session = Depends(get_db)):
    query = select(Vehicle).order_by(Vehicle.id)
    if category:
        query = query.where(Vehicle.category == category.upper())
    return db.scalars(query).all()


@app.get("/vehicles/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(404, "Машина не найдена")
    return vehicle


@app.post("/vehicles", response_model=VehicleOut, status_code=201)
def create_vehicle(body: VehicleCreate, db: Session = Depends(get_db)):
    vehicle = Vehicle(plate=body.plate, model=body.model, category=body.category)
    db.add(vehicle)
    try:
        db.commit()
    except IntegrityError:
        # БП-10: госномер уникален
        db.rollback()
        raise HTTPException(409, f"Машина с номером {body.plate} уже есть в справочнике")
    return vehicle


@app.patch("/vehicles/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(vehicle_id: int, body: VehicleUpdate, db: Session = Depends(get_db)):
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(404, "Машина не найдена")
    if body.model is not None:
        vehicle.model = body.model
    if body.active is not None:
        vehicle.active = body.active
    db.commit()
    return vehicle


# ---------- Водители ----------

@app.get("/drivers", response_model=list[DriverOut])
def list_drivers(category: str | None = None, db: Session = Depends(get_db)):
    query = select(Driver).order_by(Driver.id)
    if category:
        query = query.where(Driver.categories.any(category.upper()))
    return db.scalars(query).all()


@app.get("/drivers/{driver_id}", response_model=DriverOut)
def get_driver(driver_id: int, db: Session = Depends(get_db)):
    driver = db.get(Driver, driver_id)
    if driver is None:
        raise HTTPException(404, "Водитель не найден")
    return driver


@app.post("/drivers", response_model=DriverOut, status_code=201)
def create_driver(body: DriverCreate, db: Session = Depends(get_db)):
    driver = Driver(
        full_name=body.full_name.strip(),
        license_number=body.license_number.strip().upper(),
        categories=body.categories,
    )
    db.add(driver)
    try:
        db.commit()
    except IntegrityError:
        # БП-10: номер удостоверения уникален
        db.rollback()
        raise HTTPException(409, "Водитель с таким номером удостоверения уже есть")
    return driver


@app.patch("/drivers/{driver_id}", response_model=DriverOut)
def update_driver(driver_id: int, body: DriverUpdate, db: Session = Depends(get_db)):
    driver = db.get(Driver, driver_id)
    if driver is None:
        raise HTTPException(404, "Водитель не найден")
    if body.categories is not None:
        driver.categories = sorted(set(body.categories))
    if body.active is not None:
        driver.active = body.active
    db.commit()
    return driver
