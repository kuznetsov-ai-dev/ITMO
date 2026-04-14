import os
import sys
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import src.api as api_module
from src.api import app
from src.db import get_db
from src.models import Base
from src.services import create_ml_model


@pytest.fixture()
def client(monkeypatch):
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
            name="simple-model",
            description="test model",
            price=Decimal("25.00"),
            is_active=True,
        )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(api_module, "init_database", lambda: None)
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_register_and_login(client: TestClient):
    response = client.post(
        "/auth/register",
        json={
            "email": "user@mail.com",
            "password": "123456",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "user@mail.com"
    assert body["role"] == "user"
    assert body["balance"] == "0.00"

    login_response = client.post(
        "/auth/login",
        auth=("user@mail.com", "123456"),
    )
    assert login_response.status_code == 200
    assert login_response.json()["user"]["email"] == "user@mail.com"


def test_get_balance_and_deposit(client: TestClient):
    client.post(
        "/auth/register",
        json={
            "email": "money@mail.com",
            "password": "123456",
        },
    )

    deposit_response = client.post(
        "/balance/deposit",
        auth=("money@mail.com", "123456"),
        json={
            "amount": "50.00",
            "description": "top up",
        },
    )
    assert deposit_response.status_code == 200
    assert deposit_response.json()["balance"] == "50.00"

    balance_response = client.get(
        "/balance",
        auth=("money@mail.com", "123456"),
    )
    assert balance_response.status_code == 200
    assert balance_response.json()["balance"] == "50.00"


def test_run_prediction_and_get_history(client: TestClient):
    client.post(
        "/auth/register",
        json={
            "email": "predict@mail.com",
            "password": "123456",
        },
    )

    client.post(
        "/balance/deposit",
        auth=("predict@mail.com", "123456"),
        json={"amount": "100.00"},
    )

    models_response = client.get(
        "/models",
        auth=("predict@mail.com", "123456"),
    )
    assert models_response.status_code == 200
    model_id = models_response.json()[0]["id"]

    predict_response = client.post(
        "/predict",
        auth=("predict@mail.com", "123456"),
        json={
            "model_id": model_id,
            "rows": [
                {"value": 5},
                {"value": 12},
                {"name": "bad row"},
            ],
        },
    )
    assert predict_response.status_code == 200
    predict_body = predict_response.json()
    assert predict_body["balance"] == "75.00"
    assert predict_body["prediction"]["status"] == "done"
    assert predict_body["prediction"]["invalid_rows"] == 1

    tx_history = client.get(
        "/history/transactions",
        auth=("predict@mail.com", "123456"),
    )
    assert tx_history.status_code == 200
    assert len(tx_history.json()) == 2

    prediction_history = client.get(
        "/history/predictions",
        auth=("predict@mail.com", "123456"),
    )
    assert prediction_history.status_code == 200
    assert len(prediction_history.json()) == 1


def test_predict_without_money_returns_business_error(client: TestClient):
    client.post(
        "/auth/register",
        json={
            "email": "poor@mail.com",
            "password": "123456",
        },
    )

    models_response = client.get(
        "/models",
        auth=("poor@mail.com", "123456"),
    )
    model_id = models_response.json()[0]["id"]

    response = client.post(
        "/predict",
        auth=("poor@mail.com", "123456"),
        json={
            "model_id": model_id,
            "rows": [{"value": 10}],
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "insufficient_funds"


def test_request_without_auth_returns_401(client: TestClient):
    response = client.get("/balance")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_register_duplicate_user_returns_409(client: TestClient):
    first_response = client.post(
        "/auth/register",
        json={
            "email": "dup@mail.com",
            "password": "123456",
        },
    )
    assert first_response.status_code == 201

    second_response = client.post(
        "/auth/register",
        json={
            "email": "dup@mail.com",
            "password": "123456",
        },
    )
    assert second_response.status_code == 409
    body = second_response.json()
    assert body["error"]["code"] == "conflict"


def test_predict_with_all_invalid_rows_returns_400(client: TestClient):
    client.post(
        "/auth/register",
        json={
            "email": "invalidrows@mail.com",
            "password": "123456",
        },
    )

    client.post(
        "/balance/deposit",
        auth=("invalidrows@mail.com", "123456"),
        json={"amount": "100.00"},
    )

    models_response = client.get(
        "/models",
        auth=("invalidrows@mail.com", "123456"),
    )
    assert models_response.status_code == 200
    model_id = models_response.json()[0]["id"]

    response = client.post(
        "/predict",
        auth=("invalidrows@mail.com", "123456"),
        json={
            "model_id": model_id,
            "rows": [
                {"name": "bad row"},
                {"value": "text"},
            ],
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"