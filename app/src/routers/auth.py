from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.db import get_db
from src.dependencies import get_current_user
from src.models import User
from src.schemas import ErrorResponse, LoginResponse, UserRegisterIn, UserResponse
from src.serializers import serialize_user
from src.services import create_user


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def register_user(payload: UserRegisterIn, db: Session = Depends(get_db)):
    user = create_user(
        session=db,
        login=payload.login,
        email=payload.email,
        password=payload.password,
    )
    return serialize_user(user)


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={401: {"model": ErrorResponse}},
)
def login(current_user: User = Depends(get_current_user)):
    return {
        "message": "Авторизация выполнена успешно",
        "user": serialize_user(current_user),
    }