"""Сервис поездок: выпуск машин и приём их обратно (ФТ-5 - ФТ-7)."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import fleet_client, rules
from .db import SessionLocal, create_tables, get_db
from .messaging import add_event, start_consumer, start_publisher
from .models import OutboxEvent, Trip
from .schemas import TripFinish, TripOut, TripStart
from .timeutil import to_utc

logging.basicConfig(level=logging.INFO)


def handle_event(event_type: str, data: dict):
    """Машину обслужили - запоминаем это, теперь её снова можно выпускать (БП-4)."""
    with SessionLocal() as db:
        trip = db.get(Trip, data["trip_id"])
        if trip is not None and trip.serviced_at is None:
            trip.serviced_at = datetime.fromisoformat(data["finished_at"])
            db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    start_publisher(SessionLocal, OutboxEvent)
    start_consumer("trips.maintenance-completed", ["maintenance.completed"], handle_event)
    yield


app = FastAPI(title="Автопарк: поездки", lifespan=lifespan)


def trip_event_data(trip: Trip) -> dict:
    return {
        "trip_id": trip.id,
        "vehicle_id": trip.vehicle_id,
        "vehicle_plate": trip.vehicle_plate,
        "driver_id": trip.driver_id,
        "driver_name": trip.driver_name,
        "started_at": trip.started_at.isoformat(),
        "finished_at": trip.finished_at.isoformat() if trip.finished_at else None,
        "distance_km": trip.distance_km,
    }


def last_trip(db: Session, column, value) -> Trip | None:
    query = select(Trip).where(column == value).order_by(Trip.started_at.desc()).limit(1)
    return db.scalar(query)


@app.get("/health")
def health():
    return {"status": "ok", "service": "trips"}


@app.get("/trips", response_model=list[TripOut])
def list_trips(status: str | None = None, vehicle_id: int | None = None,
               driver_id: int | None = None, db: Session = Depends(get_db)):
    query = select(Trip).order_by(Trip.started_at.desc())
    if status:
        query = query.where(Trip.status == status)
    if vehicle_id:
        query = query.where(Trip.vehicle_id == vehicle_id)
    if driver_id:
        query = query.where(Trip.driver_id == driver_id)
    return db.scalars(query).all()


@app.get("/status")
def current_status(db: Session = Depends(get_db)):
    """Кто сейчас занят: машины в поездке или без обслуживания, водители в поездке."""
    vehicles, drivers = {}, {}
    for trip in db.scalars(select(Trip).where(Trip.status == "active")):
        vehicles[trip.vehicle_id] = "on_trip"
        drivers[trip.driver_id] = "on_trip"
    not_serviced = select(Trip).where(Trip.status == "finished", Trip.serviced_at.is_(None))
    for trip in db.scalars(not_serviced):
        vehicles.setdefault(trip.vehicle_id, "needs_service")
    return {"vehicles": vehicles, "drivers": drivers}


@app.post("/trips", response_model=TripOut, status_code=201)
def start_trip(body: TripStart, x_user: str = Header(default="unknown"),
               db: Session = Depends(get_db)):
    moment = to_utc(body.at)
    vehicle = fleet_client.get_vehicle(body.vehicle_id)
    driver = fleet_client.get_driver(body.driver_id)

    problem = rules.check_trip_start(
        vehicle, driver,
        last_vehicle_trip=last_trip(db, Trip.vehicle_id, body.vehicle_id),
        last_driver_trip=last_trip(db, Trip.driver_id, body.driver_id),
        moment=moment,
    )
    if problem:
        raise HTTPException(409, problem)

    trip = Trip(
        vehicle_id=vehicle["id"], vehicle_plate=vehicle["plate"],
        driver_id=driver["id"], driver_name=driver["full_name"],
        purpose=body.purpose, started_at=moment, created_by=x_user,
    )
    db.add(trip)
    try:
        db.flush()  # получаем номер поездки
        add_event(db, OutboxEvent, "trip.started", trip_event_data(trip))
        db.commit()
    except IntegrityError:
        # Сработал уникальный индекс: параллельный запрос успел раньше
        db.rollback()
        raise HTTPException(409, "Машина или водитель только что были назначены в другую поездку")
    return trip


@app.post("/trips/{trip_id}/finish", response_model=TripOut)
def finish_trip(trip_id: int, body: TripFinish, db: Session = Depends(get_db)):
    trip = db.get(Trip, trip_id, with_for_update=True)
    if trip is None:
        raise HTTPException(404, "Поездка не найдена")

    moment = to_utc(body.at)
    problem = rules.check_trip_finish(trip, moment)
    if problem:
        raise HTTPException(409, problem)

    trip.status = "finished"
    trip.finished_at = moment
    trip.distance_km = body.distance_km
    # БП-3: по этому событию сервис обслуживания создаст заявку.
    # Поездка и событие сохраняются одной транзакцией.
    add_event(db, OutboxEvent, "trip.finished", trip_event_data(trip))
    db.commit()
    return trip
