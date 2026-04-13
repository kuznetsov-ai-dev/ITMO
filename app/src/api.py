import socket
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.config import settings
from src.db import get_db, ping_database
from src.init_data import init_database
from src.models import TaskStatus, UserRole
from src.services import (
    ConflictError,
    InsufficientFundsError,
    NotFoundError,
    ValidationError,
    charge_balance,
    create_user,
    deposit_balance,
    get_prediction_history,
    get_user,
    list_ml_models,
    list_transactions,
    run_prediction,
)


def check_service(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


class UserCreateIn(BaseModel):
    email: str
    password: str
    role: UserRole = UserRole.USER
    start_balance: Decimal = Decimal("0.00")


class BalanceChangeIn(BaseModel):
    amount: Decimal
    description: str | None = None


class PredictionRunIn(BaseModel):
    user_id: int
    model_id: int
    rows: list[dict[str, Any]]


def serialize_user(user) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role.value,
        "balance": str(user.balance.amount if user.balance else Decimal("0.00")),
        "created_at": user.created_at.isoformat(),
    }


def serialize_model(model) -> dict:
    return {
        "id": model.id,
        "name": model.name,
        "description": model.description,
        "price": str(model.price),
        "is_active": model.is_active,
        "created_at": model.created_at.isoformat(),
    }


def serialize_transaction(tx) -> dict:
    return {
        "id": tx.id,
        "user_id": tx.user_id,
        "amount": str(tx.amount),
        "transaction_type": tx.transaction_type.value,
        "description": tx.description,
        "ml_request_id": tx.ml_request_id,
        "created_at": tx.created_at.isoformat(),
    }


def serialize_prediction(item) -> dict:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "model_id": item.model_id,
        "model_name": item.ml_model.name if item.ml_model else None,
        "status": item.status.value,
        "charged_amount": str(item.charged_amount),
        "total_rows": item.total_rows,
        "valid_rows": item.valid_rows,
        "invalid_rows": item.invalid_rows,
        "created_at": item.created_at.isoformat(),
        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
        "result_payload": item.result_payload,
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.get("/")
def home():
    return {
        "message": "Приложение работает",
        "app_name": settings.app_name,
        "docs": "/docs",
    }


@app.get("/health")
def health():
    db_ok = ping_database()
    rabbit_ok = check_service(settings.rabbitmq_host, settings.rabbitmq_port)

    return {
        "status": "ok" if db_ok and rabbit_ok else "error",
        "database": db_ok,
        "rabbitmq": rabbit_ok,
    }


@app.get("/models")
def get_models(db: Session = Depends(get_db)):
    models = list_ml_models(db)
    return [serialize_model(model) for model in models]


@app.post("/users")
def create_user_endpoint(payload: UserCreateIn, db: Session = Depends(get_db)):
    try:
        user = create_user(
            session=db,
            email=payload.email,
            password=payload.password,
            role=payload.role,
            start_balance=payload.start_balance,
        )
        return serialize_user(user)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/users/{user_id}")
def get_user_endpoint(user_id: int, db: Session = Depends(get_db)):
    try:
        user = get_user(db, user_id)
        transactions = list_transactions(db, user_id)
        predictions = get_prediction_history(db, user_id)

        result = serialize_user(user)
        result["transaction_count"] = len(transactions)
        result["prediction_count"] = len(predictions)
        return result
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/users/{user_id}/balance/deposit")
def deposit_balance_endpoint(
    user_id: int,
    payload: BalanceChangeIn,
    db: Session = Depends(get_db),
):
    try:
        tx = deposit_balance(
            session=db,
            user_id=user_id,
            amount=payload.amount,
            description=payload.description,
        )
        return serialize_transaction(tx)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/users/{user_id}/balance/charge")
def charge_balance_endpoint(
    user_id: int,
    payload: BalanceChangeIn,
    db: Session = Depends(get_db),
):
    try:
        tx = charge_balance(
            session=db,
            user_id=user_id,
            amount=payload.amount,
            description=payload.description,
        )
        return serialize_transaction(tx)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InsufficientFundsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/users/{user_id}/transactions")
def user_transactions_endpoint(user_id: int, db: Session = Depends(get_db)):
    try:
        items = list_transactions(db, user_id)
        return [serialize_transaction(item) for item in items]
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/predictions/run")
def run_prediction_endpoint(payload: PredictionRunIn, db: Session = Depends(get_db)):
    try:
        result = run_prediction(
            session=db,
            user_id=payload.user_id,
            model_id=payload.model_id,
            rows=payload.rows,
        )
        return serialize_prediction(result)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InsufficientFundsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/users/{user_id}/predictions")
def user_predictions_endpoint(user_id: int, db: Session = Depends(get_db)):
    try:
        items = get_prediction_history(db, user_id)
        return [serialize_prediction(item) for item in items]
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc