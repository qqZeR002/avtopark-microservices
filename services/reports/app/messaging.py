"""Обмен событиями между сервисами через RabbitMQ.

Отправка устроена через таблицу "исходящих событий" (outbox):
1. Сервис в одной транзакции меняет свои данные и кладёт событие в таблицу outbox.
2. Отдельный поток читает неотправленные события и публикует их в RabbitMQ.
Так событие не потеряется, даже если RabbitMQ в этот момент недоступен.

Файл одинаковый во всех сервисах, которые работают с событиями.
"""
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone

import pika
from sqlalchemy import select

log = logging.getLogger(__name__)
# Библиотека pika сама подробно пишет о каждой неудачной попытке связи; нам хватит одной строки
logging.getLogger("pika").setLevel(logging.CRITICAL)

RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@rabbitmq:5672/")
EXCHANGE = "autopark.events"


def _open_channel():
    connection = pika.BlockingConnection(pika.URLParameters(RABBIT_URL))
    channel = connection.channel()
    channel.exchange_declare(EXCHANGE, exchange_type="topic", durable=True)
    return connection, channel


def add_event(session, outbox_model, event_type: str, data: dict):
    """Кладёт событие в outbox. Вызывается внутри той же транзакции, что и изменение данных."""
    session.add(outbox_model(event_id=str(uuid.uuid4()), event_type=event_type, data=data))


def _publish_pending(session_factory, outbox_model, channel):
    with session_factory() as session:
        query = (
            select(outbox_model)
            .where(outbox_model.sent_at.is_(None))
            .order_by(outbox_model.id)
            .limit(50)
        )
        for event in session.scalars(query).all():
            body = {"event_id": event.event_id, "type": event.event_type, "data": event.data}
            channel.basic_publish(
                exchange=EXCHANGE,
                routing_key=event.event_type,
                body=json.dumps(body).encode(),
                properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
                mandatory=False,
            )
            event.sent_at = datetime.now(timezone.utc)
            session.commit()


def _publisher_loop(session_factory, outbox_model):
    while True:
        try:
            connection, channel = _open_channel()
            channel.confirm_delivery()  # ждём подтверждения от RabbitMQ
            log.info("Отправка событий запущена")
            while True:
                _publish_pending(session_factory, outbox_model, channel)
                connection.process_data_events(time_limit=1)
        except Exception as error:
            log.warning("Нет связи с RabbitMQ (%s), повтор через 3 с", error)
            time.sleep(3)


def _consumer_loop(queue: str, event_types: list[str], handler):
    def on_message(channel, method, properties, body):
        event = json.loads(body)
        try:
            handler(event["type"], event["data"])
            channel.basic_ack(method.delivery_tag)
        except Exception:
            # Вернём сообщение в очередь и попробуем позже
            log.exception("Ошибка обработки события %s", event.get("type"))
            time.sleep(2)
            channel.basic_nack(method.delivery_tag, requeue=True)

    while True:
        try:
            connection, channel = _open_channel()
            channel.queue_declare(queue, durable=True)
            for event_type in event_types:
                channel.queue_bind(queue, EXCHANGE, routing_key=event_type)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue, on_message)
            log.info("Очередь %s слушает события %s", queue, event_types)
            channel.start_consuming()
        except Exception as error:
            log.warning("Нет связи с RabbitMQ (%s), повтор через 3 с", error)
            time.sleep(3)


def start_publisher(session_factory, outbox_model):
    thread = threading.Thread(target=_publisher_loop, args=(session_factory, outbox_model), daemon=True)
    thread.start()


def start_consumer(queue: str, event_types: list[str], handler):
    """handler(event_type, data) должен спокойно переносить повторную доставку одного события."""
    thread = threading.Thread(target=_consumer_loop, args=(queue, event_types, handler), daemon=True)
    thread.start()
