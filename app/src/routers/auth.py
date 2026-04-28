from fastapi import APIRouter, Depends, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from src.config import settings
from src.db import get_db
from src.dependencies import get_current_user
from src.models import User
from src.schemas import (
    ErrorResponse,
    LoginResponse,
    UserRegisterIn,
    UserResponse,
    WebTokenResponse,
)
from src.serializers import serialize_user
from src.services import authenticate_user, create_user
from src.web_auth import create_web_access_token


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


@router.post(
    "/token",
    response_model=WebTokenResponse,
    responses={401: {"model": ErrorResponse}},
)
def issue_web_token(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = authenticate_user(
        session=db,
        login_or_email=form_data.username,
        password=form_data.password,
    )
    access_token = create_web_access_token(user)

    response.set_cookie(
        key=settings.cookie_name,
        value=f"Bearer {access_token}",
        httponly=True,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": serialize_user(user),
    }


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(settings.cookie_name)
    return {"message": "Выход выполнен"}