import os
import sys
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from src.init_data import seed_demo_data
from src.models import Base, MLModel, TaskStatus, TransactionType, User, UserRole
from src.services import (
    InsufficientFundsError,
    charge_balance,
    create_ml_model,
    create_user,
    deposit_balance,
    get_prediction_history,
    get_user,
    list_transactions,
    run_prediction,
)


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as test_session:
        yield test_session

    engine.dispose()


def test_create_and_load_user_with_balance_and_history(session):
    user = create_user(
        session=session,
        email="user@mail.com",
        password="123",
        role=UserRole.USER,
        start_balance=Decimal("100.00"),
    )

    loaded_user = get_user(session, user.id)
    transactions = list_transactions(session, user.id)

    assert loaded_user.email == "user@mail.com"
    assert loaded_user.role == UserRole.USER
    assert loaded_user.balance.amount == Decimal("100.00")
    assert len(transactions) == 1
    assert transactions[0].transaction_type == TransactionType.DEPOSIT
    assert transactions[0].amount == Decimal("100.00")


def test_deposit_and_charge_balance(session):
    user = create_user(
        session=session,
        email="money@mail.com",
        password="123",
        start_balance=Decimal("100.00"),
    )

    deposit_balance(session, user.id, Decimal("50.00"), "top up")
    charge_balance(session, user.id, Decimal("70.00"), "manual spend")

    loaded_user = get_user(session, user.id)
    transactions = list_transactions(session, user.id)

    assert loaded_user.balance.amount == Decimal("80.00")
    assert len(transactions) == 3
    assert transactions[0].transaction_type == TransactionType.CHARGE
    assert transactions[1].transaction_type == TransactionType.DEPOSIT


def test_charge_balance_without_money_raises_error(session):
    user = create_user(
        session=session,
        email="poor@mail.com",
        password="123",
        start_balance=Decimal("10.00"),
    )

    with pytest.raises(InsufficientFundsError):
        charge_balance(session, user.id, Decimal("50.00"), "too much")


def test_prediction_history_sorted_by_date_and_contains_related_model(session):
    user = create_user(
        session=session,
        email="predict@mail.com",
        password="123",
        start_balance=Decimal("100.00"),
    )

    model = create_ml_model(
        session=session,
        name="simple-model",
        description="test model",
        price=Decimal("25.00"),
        is_active=True,
    )

    first_request = run_prediction(
        session=session,
        user_id=user.id,
        model_id=model.id,
        rows=[{"value": 5}, {"value": 12}],
    )

    second_request = run_prediction(
        session=session,
        user_id=user.id,
        model_id=model.id,
        rows=[{"value": 20}, {"name": "bad row"}],
    )

    history = get_prediction_history(session, user.id)
    loaded_user = get_user(session, user.id)
    transactions = list_transactions(session, user.id)

    assert len(history) == 2
    assert history[0].id == second_request.id
    assert history[1].id == first_request.id
    assert history[0].ml_model.name == "simple-model"
    assert history[0].charged_amount == Decimal("25.00")
    assert history[0].status == TaskStatus.DONE
    assert history[0].result_payload["errors"][0]["field_name"] == "value"
    assert loaded_user.balance.amount == Decimal("50.00")
    assert len(transactions) == 3


def test_seed_demo_data_is_idempotent(session):
    seed_demo_data(session)
    seed_demo_data(session)

    user_count = session.scalar(select(func.count()).select_from(User))
    model_count = session.scalar(select(func.count()).select_from(MLModel))

    demo_user = session.execute(
        select(User).where(User.email == "demo.user@mail.com")
    ).scalar_one()

    demo_admin = session.execute(
        select(User).where(User.email == "demo.admin@mail.com")
    ).scalar_one()

    assert user_count == 2
    assert model_count == 2
    assert demo_user.role == UserRole.USER
    assert demo_admin.role == UserRole.ADMIN