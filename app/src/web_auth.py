from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from src.config import settings
from src.models import User
from src.services import get_user


class WebAuthError(Exception):
    pass


def create_web_access_token(user: User) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": str(user.id),
        "login": user.login,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_web_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise WebAuthError("Некорректный токен") from exc


def extract_cookie_token(request: Request) -> str | None:
    raw_value = request.cookies.get(settings.cookie_name)
    if not raw_value:
        return None

    if raw_value.lower().startswith("bearer "):
        return raw_value[7:]

    return raw_value


def get_optional_web_user(request: Request, db: Session) -> User | None:
    token = extract_cookie_token(request)
    if token is None:
        return None

    try:
        payload = decode_web_access_token(token)
        user_id = int(payload.get("sub", 0))
        if user_id <= 0:
            return None
        return get_user(db, user_id)
    except Exception:
        return None


def require_web_user(request: Request, db: Session) -> User:
    user = get_optional_web_user(request, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
        )
    return user