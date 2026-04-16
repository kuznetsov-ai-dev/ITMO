from decimal import Decimal

from sqlalchemy import or_, select
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


def run_prediction(
    session: Session,
    user_id: int,
    model_id: int,
    rows: list[dict],
) -> PredictionRequest:
    if not rows:
        raise ValidationError("Нужно передать хотя бы одну строку для предсказания")

    user = get_user(session, user_id)
    model = get_model(session, model_id)

    if not model.is_active:
        raise ValidationError("Модель сейчас неактивна")

    if user.balance.amount < model.price:
        raise InsufficientFundsError("Недостаточно средств для запуска предикта")

    good_rows, errors = validate_prediction_rows(rows)

    if not good_rows:
        raise ValidationError("Все строки невалидны, предсказание не выполнено")

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