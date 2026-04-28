import os
from dataclasses import dataclass
from urllib.parse import quote_plus


def to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "itmo-ml-service")
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8080"))

    db_host: str = os.getenv("DB_HOST", "database")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_name: str = os.getenv("DB_NAME", "itmo_db")
    db_user: str = os.getenv("DB_USER", "itmo_user")
    db_password: str = os.getenv("DB_PASSWORD", "itmo_pass")
    db_echo: bool = to_bool(os.getenv("DB_ECHO"), default=False)

    rabbitmq_host: str = os.getenv("RABBITMQ_HOST", "rabbitmq")
    rabbitmq_port: int = int(os.getenv("RABBITMQ_PORT", "5672"))
    rabbitmq_user: str = os.getenv("RABBITMQ_USER", "itmo_rabbit")
    rabbitmq_password: str = os.getenv("RABBITMQ_PASSWORD", "itmo_rabbit_pass")
    rabbitmq_queue: str = os.getenv("RABBITMQ_QUEUE", "ml_task_queue")

    cookie_name: str = os.getenv("COOKIE_NAME", "ITMO_AUTH")
    secret_key: str = os.getenv("SECRET_KEY", "CHANGE_ME_SUPER_SECRET")
    access_token_expire_minutes: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")
    )
    jwt_algorithm: str = "HS256"

    @property
    def database_url(self) -> str:
        explicit_url = os.getenv("DATABASE_URL")
        if explicit_url:
            return explicit_url

        user = quote_plus(self.db_user)
        password = quote_plus(self.db_password)
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()