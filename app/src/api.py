import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.config import settings
from src.init_data import init_database
from src.routers.admin import router as admin_router
from src.routers.auth import router as auth_router
from src.routers.balance import router as balance_router
from src.routers.history import router as history_router
from src.routers.predict import router as predict_router
from src.routers.system import router as system_router
from src.routers.users import router as users_router
from src.routers.web import router as web_router
from src.services import (
    ConflictError,
    InsufficientFundsError,
    NotFoundError,
    ServiceError,
    ValidationError,
)


logger = logging.getLogger(__name__)


def error_payload(code: str, message: str, details=None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
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
    version="6.0.0",
    description=(
        "REST API и Web-интерфейс для ML-сервиса. "
        "REST использует HTTP Basic Auth. "
        "Web-интерфейс использует cookie/JWT."
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


app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(system_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(balance_router)
app.include_router(predict_router)
app.include_router(history_router)
app.include_router(admin_router)
app.include_router(web_router)