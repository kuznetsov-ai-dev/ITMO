from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.domain_logic import predict_with_simple_model, validate_prediction_rows
from src.models import (
    BalanceTransaction,
    MLModel,
    PredictionRequest,
    TaskStatus,
    TransactionType,
    User,
    UserBalance,
    UserRole,
)
from src.security import make_password_hash
from src.models import utc_now


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


def get_model(session: Session, model_id: int) -> MLModel:
    stmt = select(MLModel).where(MLModel.id == model_id)
    model = session.execute(stmt).scalar_one_or_none()
    if model is None:
        raise NotFoundError(f"Модель {model_id} не найдена")
    return model


def create_user(
    session: Session,
    email: str,
    password: str,
    role: UserRole = UserRole.USER,
    start_balance: Decimal = Decimal("0.00"),
) -> User:
    existing = session.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"Пользователь с email {email} уже существует")

    if start_balance < 0:
        raise ValidationError("Начальный баланс не может быть отрицательным")

    try:
        user = User(
            email=email,
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


def list_ml_models(session: Session) -> list[MLModel]:
    stmt = select(MLModel).order_by(MLModel.id.asc())
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


def run_prediction(
    session: Session,
    user_id: int,
    model_id: int,
    rows: list[dict],
) -> PredictionRequest:
    user = get_user(session, user_id)
    model = get_model(session, model_id)

    if not model.is_active:
        raise ValidationError("Модель сейчас неактивна")

    if user.balance.amount < model.price:
        raise InsufficientFundsError("Недостаточно средств для запуска предикта")

    good_rows, errors = validate_prediction_rows(rows)
    answers = predict_with_simple_model(good_rows)

    try:
        request = PredictionRequest(
            user_id=user.id,
            model_id=model.id,
            status=TaskStatus.WORK,
            input_payload=rows,
            total_rows=len(rows),
            valid_rows=len(good_rows),
            invalid_rows=len(errors),
            charged_amount=model.price,
        )
        session.add(request)
        session.flush()

        user.balance.amount -= model.price

        session.add(
            BalanceTransaction(
                user_id=user.id,
                amount=model.price,
                transaction_type=TransactionType.CHARGE,
                description=f"charge for prediction #{request.id}",
                ml_request_id=request.id,
            )
        )

        request.result_payload = {
            "answers": answers,
            "errors": errors,
        }
        request.status = TaskStatus.DONE
        request.finished_at = utc_now()

        session.commit()
        session.refresh(request)
        return request

    except Exception:
        session.rollback()
        raise