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
import src.services as services_module
from src.api import app
from src.db import get_db
from src.models import Base
from src.services import create_ml_model, get_user, list_transactions, process_prediction_task


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
            name="demo_model",
            description="test async model",
            price=Decimal("10.00"),
            is_active=True,
        )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(api_module, "init_database", lambda: None)
    monkeypatch.setattr(
        services_module,
        "publish_task_message",
        lambda task_message: None,
    )
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client, TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def register_user(
    client: TestClient,
    login: str,
    email: str,
    password: str = "123456",
):
    response = client.post(
        "/auth/register",
        json={
            "login": login,
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 201
    return response.json()


def deposit_balance(
    client: TestClient,
    login: str,
    password: str = "123456",
    amount: str = "100.00",
    description: str = "test deposit",
):
    response = client.post(
        "/balance/deposit",
        auth=(login, password),
        json={
            "amount": amount,
            "description": description,
        },
    )
    assert response.status_code == 200
    return response.json()


def get_balance(
    client: TestClient,
    login: str,
    password: str = "123456",
):
    response = client.get(
        "/balance",
        auth=(login, password),
    )
    assert response.status_code == 200
    return response.json()


def create_prediction(
    client: TestClient,
    login: str,
    payload: dict,
    password: str = "123456",
):
    response = client.post(
        "/predict",
        auth=(login, password),
        json=payload,
    )
    return response


def process_task(SessionLocal, task_id: str, worker_id: str = "worker-1"):
    with SessionLocal() as session:
        return process_prediction_task(
            session=session,
            task_id=task_id,
            worker_id=worker_id,
        )

def test_register_and_login_by_login(client_and_session_factory):
    client, _ = client_and_session_factory

    body = register_user(
        client=client,
        login="user_login",
        email="user@mail.com",
    )
    assert body["login"] == "user_login"
    assert body["email"] == "user@mail.com"
    assert body["balance"] == "0.00"

    login_response = client.post(
        "/auth/login",
        auth=("user_login", "123456"),
    )
    assert login_response.status_code == 200
    assert login_response.json()["user"]["login"] == "user_login"


def test_repeat_login_works_twice(client_and_session_factory):
    client, _ = client_and_session_factory

    register_user(
        client=client,
        login="repeat_user",
        email="repeat@mail.com",
    )

    first_login = client.post(
        "/auth/login",
        auth=("repeat_user", "123456"),
    )
    second_login = client.post(
        "/auth/login",
        auth=("repeat_user", "123456"),
    )

    assert first_login.status_code == 200
    assert second_login.status_code == 200
    assert first_login.json()["message"] == "Авторизация выполнена успешно"
    assert second_login.json()["message"] == "Авторизация выполнена успешно"


def test_login_with_wrong_password_returns_401(client_and_session_factory):
    client, _ = client_and_session_factory

    register_user(
        client=client,
        login="wrong_pass_user",
        email="wrongpass@mail.com",
    )

    response = client.post(
        "/auth/login",
        auth=("wrong_pass_user", "bad_password"),
    )

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert "Неверный логин/email или пароль" in body["error"]["message"]


def test_balance_is_zero_then_deposit_updates_it(client_and_session_factory):
    client, _ = client_and_session_factory

    register_user(
        client=client,
        login="balance_user",
        email="balance@mail.com",
    )

    initial_balance = get_balance(client, "balance_user")
    assert initial_balance["balance"] == "0.00"

    deposit_response = deposit_balance(
        client=client,
        login="balance_user",
        amount="55.50",
    )
    assert deposit_response["balance"] == "55.50"
    assert deposit_response["transaction"]["transaction_type"] == "deposit"

    updated_balance = get_balance(client, "balance_user")
    assert updated_balance["balance"] == "55.50"


def test_predict_creates_task_and_returns_task_id(client_and_session_factory):
    client, _ = client_and_session_factory

    register_user(
        client=client,
        login="predict_user",
        email="predict@mail.com",
    )
    deposit_balance(client=client, login="predict_user")

    response = create_prediction(
        client=client,
        login="predict_user",
        payload={
            "model": "demo_model",
            "features": {
                "x1": 1.2,
                "x2": 5.7,
            },
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert "task_id" in body
    assert body["status"] == "new"
    assert body["total_rows"] == 1


def test_worker_processes_task_and_status_endpoint_returns_done(client_and_session_factory):
    client, SessionLocal = client_and_session_factory

    register_user(
        client=client,
        login="worker_user",
        email="worker@mail.com",
    )
    deposit_balance(client=client, login="worker_user", amount="100.00")

    create_response = create_prediction(
        client=client,
        login="worker_user",
        payload={
            "model": "demo_model",
            "features": {
                "x1": 1.2,
                "x2": 5.7,
            },
        },
    )

    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]

    process_task(SessionLocal, task_id, worker_id="worker-1")

    status_response = client.get(
        f"/predict/{task_id}",
        auth=("worker_user", "123456"),
    )
    assert status_response.status_code == 200
    body = status_response.json()

    assert body["task_id"] == task_id
    assert body["status"] == "done"
    assert body["worker_id"] == "worker-1"
    assert body["charged_amount"] == "10.00"
    assert body["valid_rows"] == 1
    assert body["invalid_rows"] == 0
    assert body["result_payload"]["status"] == "success"
    assert body["result_payload"]["accepted_rows"][0]["prediction"] == 6.9
    assert body["result_payload"]["accepted_rows"][0]["row_id"] == "row-1"
    assert body["result_payload"]["rejected_rows"] == []


def test_successful_ml_request_charges_balance(client_and_session_factory):
    client, SessionLocal = client_and_session_factory

    register_user(
        client=client,
        login="charge_user",
        email="charge@mail.com",
    )
    deposit_balance(client=client, login="charge_user", amount="30.00")

    before = get_balance(client, "charge_user")
    assert before["balance"] == "30.00"

    create_response = create_prediction(
        client=client,
        login="charge_user",
        payload={
            "model": "demo_model",
            "features": {
                "x1": 2,
                "x2": 3,
            },
        },
    )
    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]

    process_task(SessionLocal, task_id)

    after = get_balance(client, "charge_user")
    assert after["balance"] == "20.00"


def test_predict_with_insufficient_funds_returns_400(client_and_session_factory):
    client, _ = client_and_session_factory

    register_user(
        client=client,
        login="poor_user",
        email="poor@mail.com",
    )
    deposit_balance(client=client, login="poor_user", amount="5.00")

    response = create_prediction(
        client=client,
        login="poor_user",
        payload={
            "model": "demo_model",
            "features": {
                "x1": 1.0,
                "x2": 2.0,
            },
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "insufficient_funds"
    assert "недостаточно средств" in body["error"]["message"].lower()


def test_invalid_ml_request_is_processed_as_error_and_balance_not_charged(client_and_session_factory):
    client, SessionLocal = client_and_session_factory

    register_user(
        client=client,
        login="invalid_ml_user",
        email="invalidml@mail.com",
    )
    deposit_balance(client=client, login="invalid_ml_user", amount="40.00")

    create_response = create_prediction(
        client=client,
        login="invalid_ml_user",
        payload={
            "model": "demo_model",
            "features": {
                "x1": "bad",
                "x2": "oops",
            },
        },
    )
    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]

    process_task(SessionLocal, task_id)

    status_response = client.get(
        f"/predict/{task_id}",
        auth=("invalid_ml_user", "123456"),
    )
    assert status_response.status_code == 200
    body = status_response.json()

    assert body["status"] == "error"
    assert body["charged_amount"] == "0.00"
    assert body["valid_rows"] == 0
    assert body["invalid_rows"] == 1

    balance_response = get_balance(client, "invalid_ml_user")
    assert balance_response["balance"] == "40.00"


def test_partial_validation_keeps_successful_rows_and_charges_once(client_and_session_factory):
    client, SessionLocal = client_and_session_factory

    register_user(
        client=client,
        login="partial_user",
        email="partial@mail.com",
    )
    deposit_balance(client=client, login="partial_user", amount="50.00")

    create_response = create_prediction(
        client=client,
        login="partial_user",
        payload={
            "model": "demo_model",
            "rows": [
                {
                    "row_id": "good-1",
                    "features": {"x1": 1.5, "x2": 2.5},
                },
                {
                    "row_id": "bad-1",
                    "features": {"x1": "bad", "x2": 10},
                },
            ],
        },
    )
    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]

    process_task(SessionLocal, task_id)

    status_response = client.get(
        f"/predict/{task_id}",
        auth=("partial_user", "123456"),
    )
    assert status_response.status_code == 200
    body = status_response.json()

    assert body["status"] == "done"
    assert body["charged_amount"] == "10.00"
    assert body["valid_rows"] == 1
    assert body["invalid_rows"] == 1
    assert len(body["result_payload"]["accepted_rows"]) == 1
    assert len(body["result_payload"]["rejected_rows"]) == 1
    assert body["result_payload"]["accepted_rows"][0]["row_id"] == "good-1"
    assert body["result_payload"]["rejected_rows"][0]["row_id"] == "bad-1"

    balance_response = get_balance(client, "partial_user")
    assert balance_response["balance"] == "40.00"


def test_predict_with_unknown_model_returns_404(client_and_session_factory):
    client, _ = client_and_session_factory

    register_user(
        client=client,
        login="bad_model_user",
        email="badmodel@mail.com",
    )

    response = create_prediction(
        client=client,
        login="bad_model_user",
        payload={
            "model": "unknown_model",
            "features": {
                "x1": 1.0,
            },
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_request_without_auth_returns_401(client_and_session_factory):
    client, _ = client_and_session_factory

    response = client.get("/models")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_other_user_cannot_access_foreign_task(client_and_session_factory):
    client, SessionLocal = client_and_session_factory

    register_user(
        client=client,
        login="owner_user",
        email="owner_user@mail.com",
    )
    register_user(
        client=client,
        login="other_user",
        email="other_user@mail.com",
    )
    deposit_balance(client=client, login="owner_user")

    create_response = create_prediction(
        client=client,
        login="owner_user",
        payload={
            "model": "demo_model",
            "features": {
                "x1": 1.2,
                "x2": 5.7,
            },
        },
    )
    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]

    process_task(SessionLocal, task_id)

    response = client.get(
        f"/predict/{task_id}",
        auth=("other_user", "123456"),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_transaction_history_contains_deposit_and_charge(client_and_session_factory):
    client, SessionLocal = client_and_session_factory

    register_user(
        client=client,
        login="history_tx_user",
        email="historytx@mail.com",
    )
    deposit_balance(
        client=client,
        login="history_tx_user",
        amount="25.00",
        description="history deposit",
    )

    create_response = create_prediction(
        client=client,
        login="history_tx_user",
        payload={
            "model": "demo_model",
            "features": {
                "x1": 4,
                "x2": 1,
            },
        },
    )
    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]

    process_task(SessionLocal, task_id)

    response = client.get(
        "/history/transactions",
        auth=("history_tx_user", "123456"),
    )
    assert response.status_code == 200
    items = response.json()

    assert len(items) >= 2
    transaction_types = {item["transaction_type"] for item in items}
    assert "deposit" in transaction_types
    assert "charge" in transaction_types

    charge_items = [item for item in items if item["transaction_type"] == "charge"]
    assert len(charge_items) >= 1
    assert charge_items[0]["task_id"] == task_id


def test_prediction_history_contains_created_task(client_and_session_factory):
    client, SessionLocal = client_and_session_factory

    register_user(
        client=client,
        login="history_pred_user",
        email="historypred@mail.com",
    )
    deposit_balance(client=client, login="history_pred_user", amount="20.00")

    create_response = create_prediction(
        client=client,
        login="history_pred_user",
        payload={
            "model": "demo_model",
            "features": {
                "x1": 3,
                "x2": 4,
            },
        },
    )
    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]

    process_task(SessionLocal, task_id)

    response = client.get(
        "/history/predictions",
        auth=("history_pred_user", "123456"),
    )
    assert response.status_code == 200
    items = response.json()

    assert len(items) >= 1
    assert items[0]["task_id"] == task_id
    assert items[0]["status"] == "done"
    assert items[0]["charged_amount"] == "10.00"


def test_invalid_request_payload_returns_422(client_and_session_factory):
    client, _ = client_and_session_factory

    register_user(
        client=client,
        login="payload_user",
        email="payload@mail.com",
    )
    deposit_balance(client=client, login="payload_user", amount="20.00")

    response = create_prediction(
        client=client,
        login="payload_user",
        payload={
            "model": "demo_model",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "request_validation_error"


def test_failed_ml_processing_does_not_create_charge_transaction(client_and_session_factory):
    client, SessionLocal = client_and_session_factory

    register_user(
        client=client,
        login="no_charge_user",
        email="nocharge@mail.com",
    )
    deposit_balance(client=client, login="no_charge_user", amount="40.00")

    create_response = create_prediction(
        client=client,
        login="no_charge_user",
        payload={
            "model": "demo_model",
            "features": {
                "x1": "bad",
            },
        },
    )
    assert create_response.status_code == 202
    task_id = create_response.json()["task_id"]

    process_task(SessionLocal, task_id)

    with SessionLocal() as session:
        user = get_user(session, 1)
        transactions = list_transactions(session, user.id)

    charge_transactions = [
        tx for tx in transactions
        if tx.transaction_type.value == "charge"
    ]
    assert charge_transactions == []