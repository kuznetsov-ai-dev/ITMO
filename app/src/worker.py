import json
import logging
import os
import time

import pika

from src.config import settings
from src.db import SessionLocal
from src.services import process_prediction_task


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

logger = logging.getLogger(__name__)

WORKER_ID = os.getenv("WORKER_ID", "worker-unknown")


def build_connection_params() -> pika.ConnectionParameters:
    return pika.ConnectionParameters(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        virtual_host="/",
        credentials=pika.PlainCredentials(
            username=settings.rabbitmq_user,
            password=settings.rabbitmq_password,
        ),
        heartbeat=30,
        blocked_connection_timeout=5,
    )


def callback(ch, method, properties, body):
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        logger.exception("%s: не удалось распарсить сообщение", WORKER_ID)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    task_id = payload.get("task_id")
    if not task_id:
        logger.error("%s: в сообщении нет task_id", WORKER_ID)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    logger.info("%s: получена задача %s", WORKER_ID, task_id)

    try:
        time.sleep(2)

        with SessionLocal() as session:
            result = process_prediction_task(
                session=session,
                task_id=task_id,
                worker_id=WORKER_ID,
            )

        logger.info(
            "%s: задача %s завершена со статусом %s",
            WORKER_ID,
            task_id,
            result.status.value,
        )
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception:
        logger.exception("%s: ошибка обработки задачи %s", WORKER_ID, task_id)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def run_worker() -> None:
    while True:
        connection = None

        try:
            connection = pika.BlockingConnection(build_connection_params())
            channel = connection.channel()

            channel.queue_declare(queue=settings.rabbitmq_queue, durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=settings.rabbitmq_queue,
                on_message_callback=callback,
                auto_ack=False,
            )

            logger.info("%s: ожидание сообщений в очереди %s", WORKER_ID, settings.rabbitmq_queue)
            channel.start_consuming()

        except KeyboardInterrupt:
            logger.info("%s: остановка воркера", WORKER_ID)
            break
        except Exception:
            logger.exception("%s: потеряно соединение с RabbitMQ, повтор через 5 секунд", WORKER_ID)
            time.sleep(5)
        finally:
            if connection is not None and connection.is_open:
                connection.close()


if __name__ == "__main__":
    run_worker()