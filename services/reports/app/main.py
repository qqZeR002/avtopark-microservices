"""Сервис отчётов: использование машин и рабочее время водителей (ФТ-11, ФТ-12)."""
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import calc
from .db import SessionLocal, create_tables, get_db
from .messaging import start_consumer
from .models import ServiceFact, TripFact
from .timeutil import BUSINESS_TZ, now_utc

logging.basicConfig(level=logging.INFO)


def parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def handle_event(event_type: str, data: dict):
    """Записываем факт из события. Повторное событие просто перезапишет те же данные."""
    with SessionLocal() as db:
        if event_type.startswith("trip."):
            fact = db.get(TripFact, data["trip_id"]) or TripFact(trip_id=data["trip_id"])
            fact.vehicle_id = data["vehicle_id"]
            fact.vehicle_plate = data["vehicle_plate"]
            fact.driver_id = data["driver_id"]
            fact.driver_name = data["driver_name"]
            fact.started_at = parse_time(data["started_at"])
            if data["finished_at"]:
                fact.finished_at = parse_time(data["finished_at"])
                fact.distance_km = data["distance_km"]
        else:
            fact = db.get(ServiceFact, data["order_id"]) or ServiceFact(order_id=data["order_id"])
            fact.vehicle_id = data["vehicle_id"]
            fact.vehicle_plate = data["vehicle_plate"]
            fact.created_at = parse_time(data["created_at"])
            fact.started_at = parse_time(data["started_at"])
            if data["finished_at"]:
                fact.finished_at = parse_time(data["finished_at"])
        db.add(fact)
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    start_consumer("reports.all-events", ["trip.*", "maintenance.*"], handle_event)
    yield


app = FastAPI(title="Автопарк: отчёты", lifespan=lifespan)


def period_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """Период задаётся датами включительно, по времени автопарка."""
    if date_to < date_from:
        raise HTTPException(400, "Конец периода раньше начала")
    start = datetime.combine(date_from, time.min, tzinfo=BUSINESS_TZ)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=BUSINESS_TZ)
    return start, end


@app.get("/health")
def health():
    return {"status": "ok", "service": "reports"}


@app.get("/vehicles")
def vehicles_report(date_from: date = Query(alias="from"), date_to: date = Query(alias="to"),
                    db: Session = Depends(get_db)):
    start, end = period_bounds(date_from, date_to)
    trips = db.scalars(select(TripFact)).all()
    services = db.scalars(select(ServiceFact)).all()
    return {
        "from": date_from, "to": date_to,
        "rows": calc.vehicle_report(trips, services, start, end, now_utc()),
    }


@app.get("/drivers")
def drivers_report(date_from: date = Query(alias="from"), date_to: date = Query(alias="to"),
                   db: Session = Depends(get_db)):
    start, end = period_bounds(date_from, date_to)
    trips = db.scalars(select(TripFact)).all()
    return {
        "from": date_from, "to": date_to,
        "rows": calc.driver_report(trips, start, end, now_utc(), BUSINESS_TZ),
    }
