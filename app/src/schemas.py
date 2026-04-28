import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


LOGIN_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorInfo


class UserRegisterIn(BaseModel):
    login: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)

    @field_validator("login")
    @classmethod
    def login_must_be_valid(cls, value: str) -> str:
        normalized = value.strip().lower()

        if not normalized:
            raise ValueError("Логин не может быть пустым")

        if "@" in normalized:
            raise ValueError("Логин не должен содержать символ @")

        if not LOGIN_PATTERN.fullmatch(normalized):
            raise ValueError(
                "Логин может содержать только буквы, цифры, точку, дефис и подчёркивание"
            )

        return normalized

    @field_validator("password")
    @classmethod
    def password_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Пароль не может состоять только из пробелов")
        return value


class UserResponse(BaseModel):
    id: int
    login: str
    email: EmailStr
    role: str
    balance: str
    created_at: datetime


class UserProfileResponse(UserResponse):
    transaction_count: int
    prediction_count: int


class LoginResponse(BaseModel):
    message: str
    user: UserResponse


class WebTokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class BalanceResponse(BaseModel):
    balance: str


class BalanceChangeIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    description: str | None = Field(default=None, max_length=255)


class TransactionResponse(BaseModel):
    id: int
    user_id: int
    amount: str
    transaction_type: str
    description: str | None = None
    ml_request_id: int | None = None
    task_id: str | None = None
    created_at: datetime


class BalanceOperationResponse(BaseModel):
    balance: str
    transaction: TransactionResponse


class MLModelResponse(BaseModel):
    id: int
    name: str
    description: str
    price: str
    is_active: bool
    created_at: datetime


class PredictRowIn(BaseModel):
    row_id: str | None = Field(default=None, max_length=100)
    features: dict[str, Any] = Field(default_factory=dict)

    @field_validator("row_id")
    @classmethod
    def normalize_row_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class PredictTaskIn(BaseModel):
    model: str = Field(min_length=1, max_length=150)
    features: dict[str, Any] | None = None
    rows: list[PredictRowIn] | None = None

    @field_validator("model")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Имя модели не может быть пустым")
        return normalized

    @model_validator(mode="after")
    def validate_input_payload(self):
        if self.features is not None and self.rows:
            raise ValueError("Передайте либо features, либо rows")

        if self.features is None and not self.rows:
            raise ValueError("Нужно передать либо features, либо rows")

        return self


class PredictTaskAcceptedResponse(BaseModel):
    task_id: str
    status: str
    total_rows: int


class PredictionResponse(BaseModel):
    id: int
    task_id: str
    user_id: int
    model_id: int
    model_name: str | None = None
    status: str
    worker_id: str | None = None
    charged_amount: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    created_at: datetime
    finished_at: datetime | None = None
    input_payload: dict[str, Any]
    result_payload: dict[str, Any] | None = None