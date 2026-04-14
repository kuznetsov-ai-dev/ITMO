from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from src.db import get_db
from src.models import User
from src.services import AuthError, authenticate_user


basic_auth = HTTPBasic(auto_error=False)


def get_current_user(
    credentials: HTTPBasicCredentials | None = Depends(basic_auth),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
            headers={"WWW-Authenticate": "Basic"},
        )

    try:
        return authenticate_user(
            session=db,
            email=credentials.username,
            password=credentials.password,
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Basic"},
        ) from exc