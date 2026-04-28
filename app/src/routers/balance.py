from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.db import get_db
from src.dependencies import get_current_user
from src.models import User
from src.schemas import (
    BalanceChangeIn,
    BalanceOperationResponse,
    BalanceResponse,
    ErrorResponse,
)
from src.serializers import serialize_transaction
from src.services import deposit_balance, get_user


router = APIRouter(prefix="/balance", tags=["balance"])


@router.get(
    "",
    response_model=BalanceResponse,
    responses={401: {"model": ErrorResponse}},
)
def get_balance(current_user: User = Depends(get_current_user)):
    return {"balance": str(current_user.balance.amount)}


@router.post(
    "/deposit",
    response_model=BalanceOperationResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
    },
)
def deposit_balance_endpoint(
    payload: BalanceChangeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tx = deposit_balance(
        session=db,
        user_id=current_user.id,
        amount=payload.amount,
        description=payload.description,
    )
    updated_user = get_user(db, current_user.id)
    return {
        "balance": str(updated_user.balance.amount),
        "transaction": serialize_transaction(tx),
    }