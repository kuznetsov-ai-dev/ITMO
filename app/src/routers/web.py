from decimal import Decimal
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from src.config import settings
from src.db import get_db
from src.models import UserRole
from src.services import (
    AuthError,
    ValidationError,
    authenticate_user,
    create_prediction_task,
    create_user,
    deposit_balance,
    get_prediction_history,
    list_all_transactions,
    list_ml_models,
    list_transactions,
    list_users,
)
from src.web_auth import create_web_access_token, get_optional_web_user
from src.web_utils import parse_csv_rows, parse_features_json, parse_rows_json


router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory="templates")


def build_context(request: Request, current_user=None, **kwargs):
    context = {
        "request": request,
        "current_user": current_user,
        "app_name": settings.app_name,
        "message": request.query_params.get("message"),
        "error": request.query_params.get("error"),
    }
    context.update(kwargs)
    return context


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=302)


def redirect_with_message(url: str, message: str) -> RedirectResponse:
    return redirect(f"{url}?message={quote_plus(message)}")


def redirect_with_error(url: str, error: str) -> RedirectResponse:
    return redirect(f"{url}?error={quote_plus(error)}")


def require_web_user(request: Request, db: Session):
    current_user = get_optional_web_user(request, db)
    if current_user is None:
        return None
    return current_user


@router.get("/", response_class=HTMLResponse)
def home_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_optional_web_user(request, db)
    models = list_ml_models(db, only_active=True)
    return templates.TemplateResponse(
        "index.html",
        build_context(
            request,
            current_user=current_user,
            models=models,
        ),
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_optional_web_user(request, db)
    if current_user is not None:
        return redirect("/cabinet")

    return templates.TemplateResponse(
        "login.html",
        build_context(request, current_user=None),
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        user = authenticate_user(
            session=db,
            login_or_email=username,
            password=password,
        )
        token = create_web_access_token(user)
        response = redirect("/cabinet")
        response.set_cookie(
            key=settings.cookie_name,
            value=f"Bearer {token}",
            httponly=True,
            samesite="lax",
            max_age=settings.access_token_expire_minutes * 60,
        )
        return response
    except AuthError as exc:
        return templates.TemplateResponse(
            "login.html",
            build_context(
                request,
                current_user=None,
                form_data={"username": username},
                form_error=str(exc),
            ),
            status_code=401,
        )


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_optional_web_user(request, db)
    if current_user is not None:
        return redirect("/cabinet")

    return templates.TemplateResponse(
        "register.html",
        build_context(request, current_user=None),
    )


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    login: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        create_user(
            session=db,
            login=login,
            email=email,
            password=password,
        )
        return redirect_with_message("/login", "Регистрация выполнена. Теперь войдите в систему.")
    except Exception as exc:
        return templates.TemplateResponse(
            "register.html",
            build_context(
                request,
                current_user=None,
                form_data={
                    "login": login,
                    "email": email,
                },
                form_error=str(exc),
            ),
            status_code=400,
        )


@router.get("/logout")
def logout_page():
    response = redirect("/")
    response.delete_cookie(settings.cookie_name)
    return response


@router.get("/cabinet", response_class=HTMLResponse)
def cabinet_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_web_user(request, db)
    if current_user is None:
        return redirect_with_error("/login", "Сначала выполните вход")

    models = list_ml_models(db, only_active=True)
    predictions = get_prediction_history(db, current_user.id)[:5]
    transactions = list_transactions(db, current_user.id)[:5]

    return templates.TemplateResponse(
        "dashboard.html",
        build_context(
            request,
            current_user=current_user,
            models=models,
            predictions=predictions,
            transactions=transactions,
        ),
    )


@router.post("/cabinet/deposit")
def cabinet_deposit(
    request: Request,
    amount: Decimal = Form(...),
    db: Session = Depends(get_db),
):
    current_user = require_web_user(request, db)
    if current_user is None:
        return redirect_with_error("/login", "Сначала выполните вход")

    try:
        deposit_balance(
            session=db,
            user_id=current_user.id,
            amount=amount,
            description="web deposit",
        )
        return redirect_with_message("/cabinet", "Баланс успешно пополнен")
    except Exception as exc:
        return redirect_with_error("/cabinet", str(exc))


@router.get("/cabinet/predict", response_class=HTMLResponse)
def predict_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_web_user(request, db)
    if current_user is None:
        return redirect_with_error("/login", "Сначала выполните вход")

    models = list_ml_models(db, only_active=True)

    return templates.TemplateResponse(
        "predict.html",
        build_context(
            request,
            current_user=current_user,
            models=models,
        ),
    )


@router.post("/cabinet/predict", response_class=HTMLResponse)
async def predict_submit(
    request: Request,
    model: str = Form(...),
    raw_features: str = Form(default=""),
    raw_rows: str = Form(default=""),
    csv_file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    current_user = require_web_user(request, db)
    if current_user is None:
        return redirect_with_error("/login", "Сначала выполните вход")

    models = list_ml_models(db, only_active=True)

    try:
        sources_used = sum(
            [
                1 if raw_features.strip() else 0,
                1 if raw_rows.strip() else 0,
                1 if csv_file and csv_file.filename else 0,
            ]
        )
        if sources_used == 0:
            raise ValidationError("Нужно заполнить форму, либо JSON-список, либо загрузить CSV")
        if sources_used > 1:
            raise ValidationError("Используйте только один источник данных за раз")

        rows = None

        if csv_file and csv_file.filename:
            rows = parse_csv_rows(await csv_file.read())
        elif raw_rows.strip():
            rows = parse_rows_json(raw_rows)
        elif raw_features.strip():
            rows = parse_features_json(raw_features)

        task = create_prediction_task(
            session=db,
            user_id=current_user.id,
            model_name=model,
            rows=rows,
        )

        return redirect_with_message(
            "/cabinet/history",
            f"ML-задача создана: {task.task_id}",
        )

    except Exception as exc:
        return templates.TemplateResponse(
            "predict.html",
            build_context(
                request,
                current_user=current_user,
                models=models,
                form_error=str(exc),
                form_data={
                    "model": model,
                    "raw_features": raw_features,
                    "raw_rows": raw_rows,
                },
            ),
            status_code=400,
        )


@router.get("/cabinet/history", response_class=HTMLResponse)
def history_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_web_user(request, db)
    if current_user is None:
        return redirect_with_error("/login", "Сначала выполните вход")

    predictions = get_prediction_history(db, current_user.id)
    transactions = list_transactions(db, current_user.id)

    return templates.TemplateResponse(
        "history.html",
        build_context(
            request,
            current_user=current_user,
            predictions=predictions,
            transactions=transactions,
        ),
    )


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_web_user(request, db)
    if current_user is None:
        return redirect_with_error("/login", "Сначала выполните вход")

    if current_user.role != UserRole.ADMIN:
        return redirect_with_error("/cabinet", "Доступ только для администратора")

    users = list_users(db)
    transactions = list_all_transactions(db)[:50]

    return templates.TemplateResponse(
        "admin.html",
        build_context(
            request,
            current_user=current_user,
            users=users,
            transactions=transactions,
        ),
    )


@router.post("/admin/users/{user_id}/deposit")
def admin_deposit_page(
    user_id: int,
    request: Request,
    amount: Decimal = Form(...),
    db: Session = Depends(get_db),
):
    current_user = require_web_user(request, db)
    if current_user is None:
        return redirect_with_error("/login", "Сначала выполните вход")

    if current_user.role != UserRole.ADMIN:
        return redirect_with_error("/cabinet", "Доступ только для администратора")

    try:
        deposit_balance(
            session=db,
            user_id=user_id,
            amount=amount,
            description=f"admin deposit by {current_user.login}",
        )
        return redirect_with_message("/admin", f"Баланс пользователя {user_id} пополнен")
    except Exception as exc:
        return redirect_with_error("/admin", str(exc))