from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db import SessionLocal, engine
from src.models import Base, BalanceTransaction, MLModel, TransactionType, User, UserBalance, UserRole
from src.services import create_ml_model, create_user, get_user


def ensure_user(
    session: Session,
    email: str,
    password: str,
    role: UserRole,
    start_balance: Decimal,
) -> User:
    normalized_email = email.strip().lower()

    existing = session.execute(
        select(User).where(User.email == normalized_email)
    ).scalar_one_or_none()

    if existing is None:
        return create_user(
            session=session,
            email=normalized_email,
            password=password,
            role=role,
            start_balance=start_balance,
        )

    changed = False

    if existing.role != role:
        existing.role = role
        changed = True

    if existing.balance is None:
        session.add(
            UserBalance(
                user_id=existing.id,
                amount=start_balance,
            )
        )
        if start_balance > 0:
            session.add(
                BalanceTransaction(
                    user_id=existing.id,
                    amount=start_balance,
                    transaction_type=TransactionType.DEPOSIT,
                    description="initial balance from seed",
                )
            )
        changed = True

    if changed:
        session.commit()

    return get_user(session, existing.id)


def ensure_model(
    session: Session,
    name: str,
    description: str,
    price: Decimal,
    is_active: bool = True,
) -> MLModel:
    existing = session.execute(
        select(MLModel).where(MLModel.name == name)
    ).scalar_one_or_none()

    if existing is None:
        return create_ml_model(
            session=session,
            name=name,
            description=description,
            price=price,
            is_active=is_active,
        )

    existing.description = description
    existing.price = price
    existing.is_active = is_active
    session.commit()
    session.refresh(existing)
    return existing


def seed_demo_data(session: Session) -> None:
    ensure_user(
        session=session,
        email="demo.user@mail.com",
        password="user123",
        role=UserRole.USER,
        start_balance=Decimal("100.00"),
    )

    ensure_user(
        session=session,
        email="demo.admin@mail.com",
        password="admin123",
        role=UserRole.ADMIN,
        start_balance=Decimal("500.00"),
    )

    ensure_model(
        session=session,
        name="simple-quality-model",
        description="Базовая учебная модель для проверки value >= 10",
        price=Decimal("25.00"),
        is_active=True,
    )

    ensure_model(
        session=session,
        name="simple-fast-model",
        description="Упрощённая модель для демонстрации списка доступных моделей",
        price=Decimal("15.00"),
        is_active=True,
    )


def init_database() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_demo_data(session)


if __name__ == "__main__":
    init_database()