import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator


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


class PredictionRunIn(BaseModel):
    model_id: int = Field(gt=0)
    rows: list[dict[str, Any]] = Field(min_length=1)


class PredictionResponse(BaseModel):
    id: int
    user_id: int
    model_id: int
    model_name: str | None = None
    status: str
    charged_amount: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    created_at: datetime
    finished_at: datetime | None = None
    result_payload: dict[str, Any] | None = None


class PredictionRunResponse(BaseModel):
    balance: str
    prediction: PredictionResponse