from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.db import get_db
from src.dependencies import get_current_admin_user
from src.models import User
from src.schemas import (
    BalanceChangeIn,
    BalanceOperationResponse,
    ErrorResponse,
    TransactionResponse,
    UserResponse,
)
from src.serializers import serialize_transaction, serialize_user
from src.services import deposit_balance, get_user, list_all_transactions, list_users


router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get(
    "/users",
    response_model=list[UserResponse],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
    },
)
def admin_list_users(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
):
    return [serialize_user(item) for item in list_users(db)]


@router.get(
    "/transactions",
    response_model=list[TransactionResponse],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
    },
)
def admin_list_transactions(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
):
    return [serialize_transaction(item) for item in list_all_transactions(db)]


@router.post(
    "/users/{user_id}/deposit",
    response_model=BalanceOperationResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
    },
)
def admin_deposit_for_user(
    user_id: int,
    payload: BalanceChangeIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
):
    tx = deposit_balance(
        session=db,
        user_id=user_id,
        amount=payload.amount,
        description=payload.description or "admin deposit",
    )
    updated_user = get_user(db, user_id)

    return {
        "balance": str(updated_user.balance.amount),
        "transaction": serialize_transaction(tx),
    }