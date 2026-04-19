import os
import sys
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import src.api as api_module
import src.services as services_module
from src.api import app
from src.db import get_db
from src.models import BalanceTransaction, Base, TransactionType
from src.services import create_ml_model, get_prediction_by_task_id, process_prediction_task


@pytest.fixture()
def client_and_session_factory(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as session:
        create_ml_model(
            session=session,
            name="simple-quality-model",
            description="quality model",
            price=Decimal("25.00"),
            is_active=True,
        )
        create_ml_model(
            session=session,
            name="simple-fast-model",
            description="fast model",
            price=Decimal("15.00"),
            is_active=True,
        )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(api_module, "init_database", lambda: None)
    monkeypatch.setattr(services_module, "publish_task_message", lambda task_message: None)
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client, TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def register_user(client, login: str, email: str, password: str = "123456"):
    response = client.post(
        "/auth/register",
        json={
            "login": login,
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 201


def deposit_money(client, login: str, password: str, amount: str):
    response = client.post(
        "/balance/deposit",
        auth=(login, password),
        json={"amount": amount},
    )
    assert response.status_code == 200


def test_predict_rejects_task_when_balance_is_not_enough_before_queue(
    client_and_session_factory,
    monkeypatch,
):
    client, _ = client_and_session_factory
    register_user(client, "poor_user", "poor_user@mail.com")

    publish_calls = []

    monkeypatch.setattr(
        services_module,
        "publish_task_message",
        lambda task_message: publish_calls.append(task_message),
    )

    response = client.post(
        "/predict",
        auth=("poor_user", "123456"),
        json={
            "model": "simple-quality-model",
            "features": {"value": 12},
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "insufficient_funds"
    assert publish_calls == []


def test_predict_creates_charge_transaction_before_queue(client_and_session_factory):
    client, SessionLocal = client_and_session_factory

    register_user(client, "charged_user", "charged_user@mail.com")
    deposit_money(client, "charged_user", "123456", "100.00")

    response = client.post(
        "/predict",
        auth=("charged_user", "123456"),
        json={
            "model": "simple-quality-model",
            "features": {"value": 12},
        },
    )

    assert response.status_code == 202
    task_id = response.json()["task_id"]

    balance_response = client.get("/balance", auth=("charged_user", "123456"))
    assert balance_response.status_code == 200
    assert balance_response.json()["balance"] == "75.00"

    with SessionLocal() as session:
        task = get_prediction_by_task_id(session, task_id)
        txs = list(
            session.execute(
                select(BalanceTransaction).where(
                    BalanceTransaction.ml_request_id == task.id
                )
            ).scalars()
        )

        assert len(txs) == 1
        assert txs[0].transaction_type == TransactionType.CHARGE
        assert txs[0].amount == Decimal("25.00")
        assert task.charged_amount == Decimal("25.00")


def test_worker_processes_real_model(client_and_session_factory):
    client, SessionLocal = client_and_session_factory

    register_user(client, "model_user", "model_user@mail.com")
    deposit_money(client, "model_user", "123456", "100.00")

    create_response = client.post(
        "/predict",
        auth=("model_user", "123456"),
        json={
            "model": "simple-quality-model",
            "features": {"value": 12},
        },
    )

    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]

    with SessionLocal() as session:
        process_prediction_task(
            session=session,
            task_id=task_id,
            worker_id="worker-1",
        )

    status_response = client.get(
        f"/predict/{task_id}",
        auth=("model_user", "123456"),
    )
    assert status_response.status_code == 200

    body = status_response.json()
    assert body["status"] == "done"
    assert body["worker_id"] == "worker-1"
    assert body["charged_amount"] == "25.00"
    assert body["result_payload"]["status"] == "success"
    assert body["result_payload"]["prediction"] == "хорошо"
    assert body["result_payload"]["threshold"] == 10.0

    balance_response = client.get("/balance", auth=("model_user", "123456"))
    assert balance_response.status_code == 200
    assert balance_response.json()["balance"] == "75.00"


def test_worker_refunds_money_when_task_finishes_with_error(client_and_session_factory):
    client, SessionLocal = client_and_session_factory

    register_user(client, "refund_user", "refund_user@mail.com")
    deposit_money(client, "refund_user", "123456", "100.00")

    create_response = client.post(
        "/predict",
        auth=("refund_user", "123456"),
        json={
            "model": "simple-quality-model",
            "features": {"x1": 1.2},
        },
    )

    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]

    with SessionLocal() as session:
        process_prediction_task(
            session=session,
            task_id=task_id,
            worker_id="worker-2",
        )

    status_response = client.get(
        f"/predict/{task_id}",
        auth=("refund_user", "123456"),
    )
    assert status_response.status_code == 200

    body = status_response.json()
    assert body["status"] == "error"
    assert body["worker_id"] == "worker-2"
    assert body["charged_amount"] == "25.00"
    assert body["result_payload"]["status"] == "error"

    balance_response = client.get("/balance", auth=("refund_user", "123456"))
    assert balance_response.status_code == 200
    assert balance_response.json()["balance"] == "100.00"

    with SessionLocal() as session:
        task = get_prediction_by_task_id(session, task_id)
        txs = list(
            session.execute(
                select(BalanceTransaction).where(
                    BalanceTransaction.ml_request_id == task.id
                )
            ).scalars()
        )

        tx_types = sorted(tx.transaction_type.value for tx in txs)
        assert tx_types == ["charge", "deposit"]


def test_predict_with_empty_features_returns_422(client_and_session_factory):
    client, _ = client_and_session_factory

    register_user(client, "empty_features_user", "empty_features_user@mail.com")
    deposit_money(client, "empty_features_user", "123456", "100.00")

    response = client.post(
        "/predict",
        auth=("empty_features_user", "123456"),
        json={
            "model": "simple-quality-model",
            "features": {},
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"