import json
import uuid
from decimal import Decimal

import pika
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from src.config import settings
from src.domain_logic import run_model_prediction, validate_task_features
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
        .options(
            selectinload(PredictionRequest.ml_model),
            selectinload(PredictionRequest.user).selectinload(User.balance),
            selectinload(PredictionRequest.transactions),
        )
    )
    item = session.execute(stmt).scalar_one_or_none()

    if item is None:
        raise NotFoundError(f"Задача {task_id} не найдена")

    return item


def build_error_result(
    task_id: str,
    worker_id: str | None,
    errors: list[dict[str, str]],
) -> dict:
    return {
        "task_id": task_id,
        "worker_id": worker_id,
        "status": "error",
        "errors": errors,
    }


def add_request_refund(
    session: Session,
    request: PredictionRequest,
    description: str,
) -> None:
    if request.charged_amount <= 0:
        return

    request.user.balance.amount += request.charged_amount

    refund_tx = BalanceTransaction(
        user_id=request.user_id,
        amount=request.charged_amount,
        transaction_type=TransactionType.DEPOSIT,
        description=description,
        ml_request_id=request.id,
    )
    session.add(refund_tx)



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


def build_task_message(features: dict[str, float], model_name: str) -> dict:
    task_id = str(uuid.uuid4())
    timestamp = utc_now().replace(tzinfo=None, microsecond=0).isoformat()

    return {
        "task_id": task_id,
        "features": features,
        "model": model_name,
        "timestamp": timestamp,
    }


def publish_task_message(task_message: dict) -> None:
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
    features: dict[str, float],
) -> PredictionRequest:
    user = get_user(session, user_id)
    model = get_model_by_name(session, model_name)

    if not model.is_active:
        raise ValidationError("Модель сейчас неактивна")

    if not features:
        raise ValidationError("features не должен быть пустым")

    charged_amount = model.price if model.price > 0 else Decimal("0.00")

    if charged_amount > 0 and user.balance.amount < charged_amount:
        raise InsufficientFundsError("На балансе недостаточно средств")

    task_message = build_task_message(features=features, model_name=model.name)

    try:
        request = PredictionRequest(
            task_id=task_message["task_id"],
            user_id=user.id,
            model_id=model.id,
            status=TaskStatus.NEW,
            input_payload=task_message,
            result_payload=None,
            total_rows=1,
            valid_rows=0,
            invalid_rows=0,
            charged_amount=charged_amount,
            worker_id=None,
        )
        session.add(request)
        session.flush()

        if charged_amount > 0:
            user.balance.amount -= charged_amount
            charge_tx = BalanceTransaction(
                user_id=user.id,
                amount=charged_amount,
                transaction_type=TransactionType.CHARGE,
                description=f"charge for prediction task {request.task_id}",
                ml_request_id=request.id,
            )
            session.add(charge_tx)

        session.commit()
        session.refresh(request)

    except Exception:
        session.rollback()
        raise

    try:
        publish_task_message(task_message)
    except Exception as exc:
        try:
            request = get_prediction_by_task_id(session, task_message["task_id"])
            request.status = TaskStatus.ERROR
            request.result_payload = build_error_result(
                task_id=request.task_id,
                worker_id=None,
                errors=[
                    {
                        "field_name": "rabbitmq",
                        "text": str(exc),
                    }
                ],
            )
            request.finished_at = utc_now()

            add_request_refund(
                session=session,
                request=request,
                description=f"refund for failed queue publish {request.task_id}",
            )

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

    if request.status in {TaskStatus.DONE, TaskStatus.ERROR}:
        return request

    try:
        request.status = TaskStatus.WORK
        request.worker_id = worker_id
        session.add(request)
        session.commit()
        session.refresh(request)

        payload = request.input_payload or {}
        features = payload.get("features")
        payload_model_name = payload.get("model")

        normalized_features, errors = validate_task_features(features)

        if payload_model_name != request.ml_model.name:
            errors.append(
                {
                    "field_name": "model",
                    "text": "имя модели в сообщении не совпадает с моделью задачи",
                }
            )

        prediction_payload = None
        if not errors:
            prediction_payload, model_errors = run_model_prediction(
                model_name=request.ml_model.name,
                features=normalized_features,
            )
            errors.extend(model_errors)

        if errors:
            request.status = TaskStatus.ERROR
            request.total_rows = 1
            request.valid_rows = 0
            request.invalid_rows = len(errors)
            request.result_payload = build_error_result(
                task_id=request.task_id,
                worker_id=worker_id,
                errors=errors,
            )
            request.finished_at = utc_now()

            add_request_refund(
                session=session,
                request=request,
                description=f"refund for failed task {request.task_id}",
            )
        else:
            request.status = TaskStatus.DONE
            request.total_rows = 1
            request.valid_rows = 1
            request.invalid_rows = 0
            request.result_payload = {
                "task_id": request.task_id,
                "worker_id": worker_id,
                "status": "success",
                **prediction_payload,
            }
            request.finished_at = utc_now()

        session.add(request)
        session.commit()
        session.refresh(request)
        return get_prediction_by_task_id(session, task_id)

    except Exception as exc:
        session.rollback()

        request = get_prediction_by_task_id(session, task_id)

        if request.status != TaskStatus.ERROR:
            request.status = TaskStatus.ERROR
            request.worker_id = worker_id
            request.total_rows = 1
            request.valid_rows = 0
            request.invalid_rows = 1
            request.result_payload = build_error_result(
                task_id=task_id,
                worker_id=worker_id,
                errors=[
                    {
                        "field_name": "internal",
                        "text": str(exc),
                    }
                ],
            )
            request.finished_at = utc_now()

            add_request_refund(
                session=session,
                request=request,
                description=f"refund for crashed task {request.task_id}",
            )

            session.add(request)
            session.commit()
            session.refresh(request)

        return request