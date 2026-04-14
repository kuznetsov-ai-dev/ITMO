import logging
import socket
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.config import settings
from src.db import get_db, ping_database
from src.dependencies import get_current_user
from src.init_data import init_database
from src.models import User
from src.schemas import (
    BalanceChangeIn,
    BalanceOperationResponse,
    BalanceResponse,
    ErrorResponse,
    LoginResponse,
    MLModelResponse,
    PredictionResponse,
    PredictionRunIn,
    PredictionRunResponse,
    TransactionResponse,
    UserProfileResponse,
    UserRegisterIn,
    UserResponse,
)
from src.services import (
    ConflictError,
    InsufficientFundsError,
    NotFoundError,
    ServiceError,
    ValidationError,
    create_user,
    deposit_balance,
    get_prediction_history,
    get_user,
    list_ml_models,
    list_transactions,
    run_prediction,
)

logger = logging.getLogger(__name__)


def check_service(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def error_payload(code: str, message: str, details=None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role.value,
        "balance": str(user.balance.amount if user.balance else Decimal("0.00")),
        "created_at": user.created_at,
    }


def serialize_model(model) -> dict:
    return {
        "id": model.id,
        "name": model.name,
        "description": model.description,
        "price": str(model.price),
        "is_active": model.is_active,
        "created_at": model.created_at,
    }


def serialize_transaction(tx) -> dict:
    return {
        "id": tx.id,
        "user_id": tx.user_id,
        "amount": str(tx.amount),
        "transaction_type": tx.transaction_type.value,
        "description": tx.description,
        "ml_request_id": tx.ml_request_id,
        "created_at": tx.created_at,
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
        "created_at": item.created_at,
        "finished_at": item.finished_at,
        "result_payload": item.result_payload,
    }


def build_service_error_response(exc: ServiceError) -> tuple[int, str]:
    if isinstance(exc, ConflictError):
        return status.HTTP_409_CONFLICT, "conflict"
    if isinstance(exc, NotFoundError):
        return status.HTTP_404_NOT_FOUND, "not_found"
    if isinstance(exc, InsufficientFundsError):
        return status.HTTP_400_BAD_REQUEST, "insufficient_funds"
    if isinstance(exc, ValidationError):
        return status.HTTP_400_BAD_REQUEST, "validation_error"
    return status.HTTP_400_BAD_REQUEST, "service_error"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(
    title=settings.app_name,
    version="4.0.0",
    description=(
        "REST API для ML-сервиса. "
        "Защищённые эндпоинты используют HTTP Basic Auth."
    ),
    lifespan=lifespan,
)


@app.exception_handler(ServiceError)
async def service_error_handler(_: Request, exc: ServiceError):
    status_code, code = build_service_error_response(exc)
    return JSONResponse(
        status_code=status_code,
        content=error_payload(code, str(exc)),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_payload(
            "request_validation_error",
            "Ошибка валидации входных данных",
            exc.errors(),
        ),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "Ошибка HTTP"
    code = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "request_validation_error",
    }.get(exc.status_code, "http_error")

    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content=error_payload(code, detail),
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(_: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_payload(
            "internal_server_error",
            "Внутренняя ошибка сервера",
        ),
    )


@app.get("/")
def home():
    return {
        "message": "Приложение работает",
        "app_name": settings.app_name,
        "docs": "/docs",
        "auth": "HTTP Basic Auth",
    }


@app.get("/health")
def health():
    db_ok = ping_database()
    rabbit_ok = check_service(settings.rabbitmq_host, settings.rabbitmq_port)

    payload = {
        "status": "ok" if db_ok and rabbit_ok else "error",
        "database": db_ok,
        "rabbitmq": rabbit_ok,
    }

    if db_ok and rabbit_ok:
        return payload

    return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)


@app.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["auth"],
    responses={
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def register_user(payload: UserRegisterIn, db: Session = Depends(get_db)):
    user = create_user(
        session=db,
        email=payload.email,
        password=payload.password,
    )
    return serialize_user(user)


@app.post(
    "/auth/login",
    response_model=LoginResponse,
    tags=["auth"],
    responses={401: {"model": ErrorResponse}},
)
def login(current_user: User = Depends(get_current_user)):
    return {
        "message": "Авторизация выполнена успешно",
        "user": serialize_user(current_user),
    }


@app.get(
    "/users/me",
    response_model=UserProfileResponse,
    tags=["users"],
    responses={401: {"model": ErrorResponse}},
)
def get_current_user_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    transactions = list_transactions(db, current_user.id)
    predictions = get_prediction_history(db, current_user.id)

    result = serialize_user(current_user)
    result["transaction_count"] = len(transactions)
    result["prediction_count"] = len(predictions)
    return result


@app.get(
    "/balance",
    response_model=BalanceResponse,
    tags=["balance"],
    responses={401: {"model": ErrorResponse}},
)
def get_balance(current_user: User = Depends(get_current_user)):
    return {"balance": str(current_user.balance.amount)}


@app.post(
    "/balance/deposit",
    response_model=BalanceOperationResponse,
    tags=["balance"],
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
    },
)
def deposit_balance_endpoint(
    payload: BalanceChangeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tx = deposit_balance(
        session=db,
        user_id=current_user.id,
        amount=payload.amount,
        description=payload.description,
    )
    updated_user = get_user(db, current_user.id)
    return {
        "balance": str(updated_user.balance.amount),
        "transaction": serialize_transaction(tx),
    }


@app.get(
    "/models",
    response_model=list[MLModelResponse],
    tags=["predict"],
    responses={401: {"model": ErrorResponse}},
)
def get_models(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    models = list_ml_models(db, only_active=True)
    return [serialize_model(model) for model in models]


@app.post(
    "/predict",
    response_model=PredictionRunResponse,
    tags=["predict"],
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def run_prediction_endpoint(
    payload: PredictionRunIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = run_prediction(
        session=db,
        user_id=current_user.id,
        model_id=payload.model_id,
        rows=payload.rows,
    )
    updated_user = get_user(db, current_user.id)

    return {
        "balance": str(updated_user.balance.amount),
        "prediction": serialize_prediction(result),
    }


@app.get(
    "/history/predictions",
    response_model=list[PredictionResponse],
    tags=["history"],
    responses={401: {"model": ErrorResponse}},
)
def user_predictions_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = get_prediction_history(db, current_user.id)
    return [serialize_prediction(item) for item in items]


@app.get(
    "/history/transactions",
    response_model=list[TransactionResponse],
    tags=["history"],
    responses={401: {"model": ErrorResponse}},
)
def user_transactions_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = list_transactions(db, current_user.id)
    return [serialize_transaction(item) for item in items]