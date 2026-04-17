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
from src.services import create_ml_model, process_prediction_task


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
            price=Decimal("0.00"),
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


def test_register_and_login_by_login(client_and_session_factory):
    client, _ = client_and_session_factory

    response = client.post(
        "/auth/register",
        json={
            "login": "user_login",
            "email": "user@mail.com",
            "password": "123456",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["login"] == "user_login"
    assert body["email"] == "user@mail.com"

    login_response = client.post(
        "/auth/login",
        auth=("user_login", "123456"),
    )
    assert login_response.status_code == 200


def test_predict_creates_task_and_returns_task_id(client_and_session_factory):
    client, _ = client_and_session_factory

    client.post(
        "/auth/register",
        json={
            "login": "predict_user",
            "email": "predict@mail.com",
            "password": "123456",
        },
    )

    response = client.post(
        "/predict",
        auth=("predict_user", "123456"),
        json={
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


def test_worker_processes_task_and_status_endpoint_returns_done(client_and_session_factory):
    client, SessionLocal = client_and_session_factory

    client.post(
        "/auth/register",
        json={
            "login": "worker_user",
            "email": "worker@mail.com",
            "password": "123456",
        },
    )

    create_response = client.post(
        "/predict",
        auth=("worker_user", "123456"),
        json={
            "model": "demo_model",
            "features": {
                "x1": 1.2,
                "x2": 5.7,
            },
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
        auth=("worker_user", "123456"),
    )
    assert status_response.status_code == 200
    body = status_response.json()

    assert body["task_id"] == task_id
    assert body["status"] == "done"
    assert body["worker_id"] == "worker-1"
    assert body["result_payload"]["prediction"] == 6.9
    assert body["result_payload"]["status"] == "success"


def test_predict_with_unknown_model_returns_404(client_and_session_factory):
    client, _ = client_and_session_factory

    client.post(
        "/auth/register",
        json={
            "login": "bad_model_user",
            "email": "badmodel@mail.com",
            "password": "123456",
        },
    )

    response = client.post(
        "/predict",
        auth=("bad_model_user", "123456"),
        json={
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

    client.post(
        "/auth/register",
        json={
            "login": "owner_user",
            "email": "owner_user@mail.com",
            "password": "123456",
        },
    )

    client.post(
        "/auth/register",
        json={
            "login": "other_user",
            "email": "other_user@mail.com",
            "password": "123456",
        },
    )

    create_response = client.post(
        "/predict",
        auth=("owner_user", "123456"),
        json={
            "model": "demo_model",
            "features": {
                "x1": 1.2,
                "x2": 5.7,
            },
        },
    )
    task_id = create_response.json()["task_id"]

    with SessionLocal() as session:
        process_prediction_task(
            session=session,
            task_id=task_id,
            worker_id="worker-1",
        )

    response = client.get(
        f"/predict/{task_id}",
        auth=("other_user", "123456"),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"