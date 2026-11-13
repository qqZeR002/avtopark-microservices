"""Сервис обслуживания: заявки после поездок и работа механика (ФТ-8 - ФТ-10)."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import rules
from .db import SessionLocal, create_tables, get_db
from .messaging import add_event, start_consumer, start_publisher
from .models import OutboxEvent, ServiceOrder
from .schemas import OrderOut, ServiceFinish, ServiceStart
from .timeutil import now_utc, to_utc

logging.basicConfig(level=logging.INFO)


def handle_event(event_type: str, data: dict):
    """Поездка закрыта - создаём заявку на обслуживание машины (БП-3)."""
    with SessionLocal() as db:
        already_exists = db.scalar(select(ServiceOrder).where(ServiceOrder.trip_id == data["trip_id"]))
        if already_exists:
            return  # событие пришло повторно
        db.add(ServiceOrder(
            trip_id=data["trip_id"],
            vehicle_id=data["vehicle_id"],
            vehicle_plate=data["vehicle_plate"],
            created_at=datetime.fromisoformat(data["finished_at"]),
        ))
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    start_publisher(SessionLocal, OutboxEvent)
    start_consumer("maintenance.trip-finished", ["trip.finished"], handle_event)
    yield


app = FastAPI(title="Автопарк: обслуживание", lifespan=lifespan)


def order_event_data(order: ServiceOrder) -> dict:
    return {
        "order_id": order.id,
        "trip_id": order.trip_id,
        "vehicle_id": order.vehicle_id,
        "vehicle_plate": order.vehicle_plate,
        "created_at": order.created_at.isoformat(),
        "started_at": order.started_at.isoformat() if order.started_at else None,
        "finished_at": order.finished_at.isoformat() if order.finished_at else None,
    }


def find_order(db: Session, order_id: int) -> ServiceOrder:
    order = db.get(ServiceOrder, order_id, with_for_update=True)
    if order is None:
        raise HTTPException(404, "Заявка не найдена")
    return order


@app.get("/health")
def health():
    return {"status": "ok", "service": "maintenance"}


@app.get("/working-hours")
def working_hours():
    return {
        "days": "понедельник - пятница",
        "from": rules.WORK_START.strftime("%H:%M"),
        "to": rules.WORK_END.strftime("%H:%M"),
        "open_now": rules.is_working_time(now_utc()),
    }


@app.get("/orders", response_model=list[OrderOut])
def list_orders(status: str | None = None, vehicle_id: int | None = None,
                db: Session = Depends(get_db)):
    query = select(ServiceOrder).order_by(ServiceOrder.created_at.desc())
    if status:
        query = query.where(ServiceOrder.status == status)
    if vehicle_id:
        query = query.where(ServiceOrder.vehicle_id == vehicle_id)
    return db.scalars(query).all()


@app.post("/orders/{order_id}/start", response_model=OrderOut)
def start_service(order_id: int, body: ServiceStart, x_user: str = Header(default="unknown"),
                  db: Session = Depends(get_db)):
    order = find_order(db, order_id)
    moment = to_utc(body.at)
    problem = rules.check_service_start(order, moment)
    if problem:
        raise HTTPException(409, problem)

    order.status = "in_progress"
    order.started_at = moment
    order.mechanic = x_user
    add_event(db, OutboxEvent, "maintenance.started", order_event_data(order))
    db.commit()
    return order


@app.post("/orders/{order_id}/finish", response_model=OrderOut)
def finish_service(order_id: int, body: ServiceFinish, db: Session = Depends(get_db)):
    order = find_order(db, order_id)
    moment = to_utc(body.at)
    problem = rules.check_service_finish(order, moment)
    if problem:
        raise HTTPException(409, problem)

    order.status = "done"
    order.finished_at = moment
    order.comment = body.comment
    # По этому событию сервис поездок снимет блокировку с машины
    add_event(db, OutboxEvent, "maintenance.completed", order_event_data(order))
    db.commit()
    return order
