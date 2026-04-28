import socket

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from src.config import settings
from src.db import ping_database


router = APIRouter(tags=["system"])


def check_service(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


@router.get("/api/info")
def api_info():
    return {
        "message": "Приложение работает",
        "app_name": settings.app_name,
        "docs": "/docs",
        "auth": "HTTP Basic Auth + cookie auth for web",
    }


@router.get("/health")
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

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )