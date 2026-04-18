import json
import uuid
from decimal import Decimal
from typing import Any

import pika
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from src.config import settings
from src.domain_logic import predict_demo_model, validate_task_features
from src.models import (
    BalanceTransaction,
    MLModel,
    PredictionRequest,
    TaskStatus,
    TransactionType,
    User,
    UserBalance,
    UserRole,
    utc_now,
)
from src.security import make_password_hash, verify_password


class ServiceError(Exception):
    pass


class NotFoundError(ServiceError):
    pass


class ConflictError(ServiceError):
    pass


class InsufficientFundsError(ServiceError):
    pass


class ValidationError(ServiceError):
    pass


class AuthError(ServiceError):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_login(login: str) -> str:
    return login.strip().lower()


def normalize_prediction_rows(
    features: dict[str, Any] | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if features is not None and rows:
        raise ValidationError("Передайте либо features, либо rows")

    normalized_rows: list[dict[str, Any]] = []

    if rows:
        for index, raw_row in enumerate(rows, start=1):
            if not isinstance(raw_row, dict):
                normalized_rows.append(
                    {
                        "row_id": f"row-{index}",
                        "features": raw_row,
                    }
                )
                continue

            row_id = raw_row.get("row_id")
            if row_id is None or not str(row_id).strip():
                row_id = f"row-{index}"

            normalized_rows.append(
                {
                    "row_id": str(row_id).strip(),
                    "features": raw_row.get("features"),
                }
            )
    elif features is not None:
        if not isinstance(features, dict):
            raise ValidationError("features должен быть объектом")

        if not features:
            raise ValidationError("features не должен быть пустым")

        normalized_rows.append(
            {
                "row_id": "row-1",
                "features": features,
            }
        )
    else:
        raise ValidationError("Нужно передать либо features, либо rows")

    return normalized_rows


def get_user(session: Session, user_id: int) -> User:
    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.balance))
    )
    user = session.execute(stmt).scalar_one_or_none()
    if user is None:
        raise NotFoundError(f"Пользователь {user_id} не найден")
    return user


def get_user_by_email(session: Session, email: str) -> User | None:
    normalized_email = normalize_email(email)
    stmt = (
        select(User)
        .where(User.email == normalized_email)
        .options(selectinload(User.balance))
    )
    return session.execute(stmt).scalar_one_or_none()


def get_user_by_login(session: Session, login: str) -> User | None:
    normalized_login = normalize_login(login)
    stmt = (
        select(User)
        .where(User.login == normalized_login)
        .options(selectinload(User.balance))
    )
    return session.execute(stmt).scalar_one_or_none()


def get_user_by_login_or_email(session: Session, login_or_email: str) -> User | None:
    normalized_value = login_or_email.strip().lower()

    if not normalized_value:
        return None

    stmt = (
        select(User)
        .where(
            or_(
                User.login == normalized_value,
                User.email == normalized_value,
            )
        )
        .options(selectinload(User.balance))
    )
    return session.execute(stmt).scalar_one_or_none()


def authenticate_user(session: Session, login_or_email: str, password: str) -> User:
    user = get_user_by_login_or_email(session, login_or_email)
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("Неверный логин/email или пароль")
    return user


def get_model(session: Session, model_id: int) -> MLModel:
    stmt = select(MLModel).where(MLModel.id == model_id)
    model = session.execute(stmt).scalar_one_or_none()
    if model is None:
        raise NotFoundError(f"Модель {model_id} не найдена")
    return model


def get_model_by_name(session: Session, model_name: str) -> MLModel:
    normalized_name = model_name.strip()

    stmt = select(MLModel).where(MLModel.name == normalized_name)
    model = session.execute(stmt).scalar_one_or_none()

    if model is None:
        raise NotFoundError(f"Модель {normalized_name} не найдена")

    return model


def get_prediction_by_task_id(session: Session, task_id: str) -> PredictionRequest:
    stmt = (
        select(PredictionRequest)
        .where(PredictionRequest.task_id == task_id)
        .options(selectinload(PredictionRequest.ml_model))
    )
    item = session.execute(stmt).scalar_one_or_none()

    if item is None:
        raise NotFoundError(f"Задача {task_id} не найдена")

    return item


def create_user(
    session: Session,
    login: str,
    email: str,
    password: str,
    role: UserRole = UserRole.USER,
    start_balance: Decimal = Decimal("0.00"),
) -> User:
    normalized_login = normalize_login(login)
    normalized_email = normalize_email(email)

    if not normalized_login:
        raise ValidationError("Логин не может быть пустым")

    if "@" in normalized_login:
        raise ValidationError("Логин не должен содержать символ @")

    if not normalized_email:
        raise ValidationError("Email не может быть пустым")

    if not password or not password.strip():
        raise ValidationError("Пароль не может быть пустым")

    existing_by_login = get_user_by_login(session, normalized_login)
    if existing_by_login is not None:
        raise ConflictError(f"Пользователь с логином {normalized_login} уже существует")

    existing_by_email = get_user_by_email(session, normalized_email)
    if existing_by_email is not None:
        raise ConflictError(f"Пользователь с email {normalized_email} уже существует")

    if start_balance < 0:
        raise ValidationError("Начальный баланс не может быть отрицательным")

    try:
        user = User(
            login=normalized_login,
            email=normalized_email,
            password_hash=make_password_hash(password),
            role=role,
        )
        session.add(user)
        session.flush()

        balance = UserBalance(
            user_id=user.id,
            amount=Decimal("0.00"),
        )
        session.add(balance)

        if start_balance > 0:
            balance.amount = start_balance
            session.add(
                BalanceTransaction(
                    user_id=user.id,
                    amount=start_balance,
                    transaction_type=TransactionType.DEPOSIT,
                    description="initial balance",
                )
            )

        session.commit()
        return get_user(session, user.id)

    except Exception:
        session.rollback()
        raise


def create_ml_model(
    session: Session,
    name: str,
    description: str,
    price: Decimal,
    is_active: bool = True,
) -> MLModel:
    existing = session.execute(
        select(MLModel).where(MLModel.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"Модель с именем {name} уже существует")

    if price < 0:
        raise ValidationError("Цена модели не может быть отрицательной")

    try:
        model = MLModel(
            name=name,
            description=description,
            price=price,
            is_active=is_active,
        )
        session.add(model)
        session.commit()
        session.refresh(model)
        return model
    except Exception:
        session.rollback()
        raise


def list_ml_models(session: Session, only_active: bool = False) -> list[MLModel]:
    stmt = select(MLModel)

    if only_active:
        stmt = stmt.where(MLModel.is_active.is_(True))

    stmt = stmt.order_by(MLModel.id.asc())
    return list(session.execute(stmt).scalars().all())


def list_users(session: Session) -> list[User]:
    stmt = (
        select(User)
        .options(selectinload(User.balance))
        .order_by(User.id.asc())
    )
    return list(session.execute(stmt).scalars().all())


def list_all_transactions(session: Session) -> list[BalanceTransaction]:
    stmt = (
        select(BalanceTransaction)
        .options(selectinload(BalanceTransaction.ml_request))
        .order_by(
            BalanceTransaction.created_at.desc(),
            BalanceTransaction.id.desc(),
        )
    )
    return list(session.execute(stmt).scalars().all())

def deposit_balance(
    session: Session,
    user_id: int,
    amount: Decimal,
    description: str | None = None,
) -> BalanceTransaction:
    if amount <= 0:
        raise ValidationError("Сумма пополнения должна быть больше нуля")

    user = get_user(session, user_id)

    try:
        user.balance.amount += amount
        tx = BalanceTransaction(
            user_id=user.id,
            amount=amount,
            transaction_type=TransactionType.DEPOSIT,
            description=description or "manual deposit",
        )
        session.add(tx)
        session.commit()
        session.refresh(tx)
        return tx
    except Exception:
        session.rollback()
        raise


def charge_balance(
    session: Session,
    user_id: int,
    amount: Decimal,
    description: str | None = None,
    ml_request_id: int | None = None,
) -> BalanceTransaction:
    if amount <= 0:
        raise ValidationError("Сумма списания должна быть больше нуля")

    user = get_user(session, user_id)

    if user.balance.amount < amount:
        raise InsufficientFundsError("На балансе недостаточно средств")

    try:
        user.balance.amount -= amount
        tx = BalanceTransaction(
            user_id=user.id,
            amount=amount,
            transaction_type=TransactionType.CHARGE,
            description=description or "manual charge",
            ml_request_id=ml_request_id,
        )
        session.add(tx)
        session.commit()
        session.refresh(tx)
        return tx
    except Exception:
        session.rollback()
        raise


def list_transactions(session: Session, user_id: int) -> list[BalanceTransaction]:
    get_user(session, user_id)

    stmt = (
        select(BalanceTransaction)
        .where(BalanceTransaction.user_id == user_id)
        .options(selectinload(BalanceTransaction.ml_request))
        .order_by(
            BalanceTransaction.created_at.desc(),
            BalanceTransaction.id.desc(),
        )
    )
    return list(session.execute(stmt).scalars().all())


def get_prediction_history(session: Session, user_id: int) -> list[PredictionRequest]:
    get_user(session, user_id)

    stmt = (
        select(PredictionRequest)
        .where(PredictionRequest.user_id == user_id)
        .options(selectinload(PredictionRequest.ml_model))
        .order_by(
            PredictionRequest.created_at.desc(),
            PredictionRequest.id.desc(),
        )
    )
    return list(session.execute(stmt).scalars().all())


def build_task_message(rows: list[dict[str, Any]], model_name: str) -> dict[str, Any]:
    task_id = str(uuid.uuid4())
    timestamp = utc_now().replace(tzinfo=None, microsecond=0).isoformat()

    payload: dict[str, Any] = {
        "task_id": task_id,
        "rows": rows,
        "model": model_name,
        "timestamp": timestamp,
        "total_rows": len(rows),
    }

    if len(rows) == 1:
        payload["features"] = rows[0].get("features")

    return payload


def publish_task_message(task_message: dict[str, Any]) -> None:
    credentials = pika.PlainCredentials(
        username=settings.rabbitmq_user,
        password=settings.rabbitmq_password,
    )

    connection_params = pika.ConnectionParameters(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        virtual_host="/",
        credentials=credentials,
        heartbeat=30,
        blocked_connection_timeout=5,
    )

    connection = pika.BlockingConnection(connection_params)

    try:
        channel = connection.channel()
        channel.queue_declare(queue=settings.rabbitmq_queue, durable=True)

        channel.basic_publish(
            exchange="",
            routing_key=settings.rabbitmq_queue,
            body=json.dumps(task_message, ensure_ascii=False).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
        )
    finally:
        connection.close()


def create_prediction_task(
    session: Session,
    user_id: int,
    model_name: str,
    features: dict[str, Any] | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> PredictionRequest:
    user = get_user(session, user_id)
    model = get_model_by_name(session, model_name)

    if not model.is_active:
        raise ValidationError("Модель сейчас неактивна")

    if user.balance.amount <= 0:
        raise InsufficientFundsError("Баланс должен быть больше нуля")

    if user.balance.amount < model.price:
        raise InsufficientFundsError("На балансе недостаточно средств для выполнения запроса")

    normalized_rows = normalize_prediction_rows(features=features, rows=rows)
    if not normalized_rows:
        raise ValidationError("Не переданы данные для обработки")

    task_message = build_task_message(rows=normalized_rows, model_name=model.name)

    try:
        request = PredictionRequest(
            task_id=task_message["task_id"],
            user_id=user.id,
            model_id=model.id,
            status=TaskStatus.NEW,
            input_payload=task_message,
            result_payload=None,
            total_rows=len(normalized_rows),
            valid_rows=0,
            invalid_rows=0,
            charged_amount=Decimal("0.00"),
            worker_id=None,
        )
        session.add(request)
        session.commit()
        session.refresh(request)
    except Exception:
        session.rollback()
        raise

    try:
        publish_task_message(task_message)
    except Exception as exc:
        try:
            request.status = TaskStatus.ERROR
            request.result_payload = {
                "task_id": request.task_id,
                "worker_id": None,
                "status": "error",
                "accepted_rows": [],
                "rejected_rows": [],
                "summary": {
                    "total_rows": request.total_rows,
                    "valid_rows": 0,
                    "invalid_rows": 0,
                },
                "errors": [
                    {
                        "field_name": "rabbitmq",
                        "text": str(exc),
                    }
                ],
            }
            request.finished_at = utc_now()
            session.add(request)
            session.commit()
        except Exception:
            session.rollback()

        raise ServiceError("Не удалось поставить задачу в очередь RabbitMQ")

    return get_prediction_by_task_id(session, request.task_id)


def process_prediction_task(
    session: Session,
    task_id: str,
    worker_id: str,
) -> PredictionRequest:
    request = get_prediction_by_task_id(session, task_id)

    if request.status == TaskStatus.DONE:
        return request

    try:
        request.status = TaskStatus.WORK
        request.worker_id = worker_id
        session.add(request)
        session.commit()
        session.refresh(request)

        payload = request.input_payload or {}
        raw_rows = payload.get("rows")
        if raw_rows is None and payload.get("features") is not None:
            raw_rows = [
                {
                    "row_id": "row-1",
                    "features": payload.get("features"),
                }
            ]

        global_errors: list[dict[str, str]] = []
        if not isinstance(raw_rows, list) or not raw_rows:
            raw_rows = []
            global_errors.append(
                {
                    "field_name": "rows",
                    "text": "Не переданы данные для обработки",
                }
            )

        payload_model_name = payload.get("model")
        if payload_model_name != request.ml_model.name:
            global_errors.append(
                {
                    "field_name": "model",
                    "text": "имя модели в сообщении не совпадает с моделью задачи",
                }
            )

        valid_results: list[dict[str, Any]] = []
        rejected_rows: list[dict[str, Any]] = []

        for index, raw_row in enumerate(raw_rows, start=1):
            if not isinstance(raw_row, dict):
                rejected_rows.append(
                    {
                        "row_id": f"row-{index}",
                        "errors": [
                            {
                                "field_name": "row",
                                "text": "строка должна быть объектом",
                            }
                        ],
                        "input": raw_row,
                    }
                )
                continue

            row_id = str(raw_row.get("row_id") or f"row-{index}").strip() or f"row-{index}"
            normalized_features, errors = validate_task_features(raw_row.get("features"))

            if errors:
                rejected_rows.append(
                    {
                        "row_id": row_id,
                        "errors": errors,
                        "input": raw_row.get("features"),
                    }
                )
                continue

            valid_results.append(
                {
                    "row_id": row_id,
                    "features": normalized_features,
                    "prediction": predict_demo_model(normalized_features),
                }
            )

        total_rows = len(raw_rows)
        summary = {
            "total_rows": total_rows,
            "valid_rows": len(valid_results),
            "invalid_rows": len(rejected_rows),
        }

        if global_errors or not valid_results:
            request.status = TaskStatus.ERROR
            request.total_rows = total_rows
            request.valid_rows = 0
            request.invalid_rows = len(rejected_rows) if total_rows else 1
            request.result_payload = {
                "task_id": request.task_id,
                "worker_id": worker_id,
                "status": "error",
                "accepted_rows": [],
                "rejected_rows": rejected_rows,
                "summary": {
                    "total_rows": total_rows,
                    "valid_rows": 0,
                    "invalid_rows": len(rejected_rows) if total_rows else 1,
                },
                "errors": global_errors,
            }
            request.finished_at = utc_now()
            session.add(request)
            session.commit()
            session.refresh(request)
            return get_prediction_by_task_id(session, task_id)

        user = get_user(session, request.user_id)
        if user.balance.amount <= 0:
            global_errors.append(
                {
                    "field_name": "balance",
                    "text": "Баланс стал нулевым или отрицательным до завершения обработки",
                }
            )
        elif user.balance.amount < request.ml_model.price:
            global_errors.append(
                {
                    "field_name": "balance",
                    "text": "Во время обработки на балансе оказалось недостаточно средств",
                }
            )

        if global_errors:
            request.status = TaskStatus.ERROR
            request.total_rows = total_rows
            request.valid_rows = len(valid_results)
            request.invalid_rows = len(rejected_rows)
            request.result_payload = {
                "task_id": request.task_id,
                "worker_id": worker_id,
                "status": "error",
                "accepted_rows": valid_results,
                "rejected_rows": rejected_rows,
                "summary": summary,
                "errors": global_errors,
            }
            request.finished_at = utc_now()
            session.add(request)
            session.commit()
            session.refresh(request)
            return get_prediction_by_task_id(session, task_id)

        request.status = TaskStatus.DONE
        request.total_rows = total_rows
        request.valid_rows = len(valid_results)
        request.invalid_rows = len(rejected_rows)
        request.result_payload = {
            "task_id": request.task_id,
            "worker_id": worker_id,
            "status": "success",
            "accepted_rows": valid_results,
            "rejected_rows": rejected_rows,
            "summary": summary,
        }
        request.finished_at = utc_now()

        if request.charged_amount == 0 and request.ml_model.price > 0:
            user.balance.amount -= request.ml_model.price
            request.charged_amount = request.ml_model.price
            session.add(
                BalanceTransaction(
                    user_id=request.user_id,
                    amount=request.ml_model.price,
                    transaction_type=TransactionType.CHARGE,
                    description=f"ML request {request.task_id}",
                    ml_request_id=request.id,
                )
            )

        session.add(request)
        session.commit()
        session.refresh(request)
        return get_prediction_by_task_id(session, task_id)

    except Exception as exc:
        session.rollback()

        request = get_prediction_by_task_id(session, task_id)
        request.status = TaskStatus.ERROR
        request.worker_id = worker_id
        request.total_rows = request.total_rows or 1
        request.valid_rows = 0
        request.invalid_rows = max(request.invalid_rows, 1)
        request.result_payload = {
            "task_id": task_id,
            "worker_id": worker_id,
            "status": "error",
            "accepted_rows": [],
            "rejected_rows": [],
            "summary": {
                "total_rows": request.total_rows,
                "valid_rows": 0,
                "invalid_rows": request.invalid_rows,
            },
            "errors": [
                {
                    "field_name": "internal",
                    "text": str(exc),
                }
            ],
        }
        request.finished_at = utc_now()

        session.add(request)
        session.commit()
        session.refresh(request)
        return request