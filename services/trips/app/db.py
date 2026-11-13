"""Подключение к базе данных сервиса. У каждого сервиса база своя."""
import logging
import os
import time

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

log = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """Выдаёт сессию на время одного запроса."""
    with SessionLocal() as session:
        yield session


def create_tables():
    """Создаёт таблицы при старте. База может подниматься дольше сервиса, поэтому ждём."""
    for attempt in range(30):
        try:
            Base.metadata.create_all(engine)
            return
        except OperationalError:
            log.warning("База ещё не готова, попытка %s", attempt + 1)
            time.sleep(2)
    raise RuntimeError("Не удалось подключиться к базе данных")
