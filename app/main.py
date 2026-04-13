import os
import socket
from fastapi import FastAPI
import uvicorn


# простое приложение
app = FastAPI()


# доступность сервиса по хосту и порту
def check_service(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


# главная страница
@app.get("/")
def home():
    return {
        "message": "Приложение работает",
        "app_name": os.getenv("APP_NAME", "itmo-app")
    }


# healthcheck для docker
@app.get("/health")
def health():
    db_host = os.getenv("DB_HOST", "database")
    db_port = int(os.getenv("DB_PORT", "5432"))

    rabbit_host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    rabbit_port = int(os.getenv("RABBITMQ_PORT", "5672"))

    return {
        "status": "ok",
        "database": check_service(db_host, db_port),
        "rabbitmq": check_service(rabbit_host, rabbit_port)
    }


# запуск приложения
if __name__ == "__main__":
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8080"))
    uvicorn.run(app, host=host, port=port)