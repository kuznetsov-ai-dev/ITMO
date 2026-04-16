from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.db import get_db
from src.dependencies import get_current_user
from src.models import User
from src.schemas import ErrorResponse, PredictionResponse, TransactionResponse
from src.serializers import serialize_prediction, serialize_transaction
from src.services import get_prediction_history, list_transactions


router = APIRouter(prefix="/history", tags=["history"])


@router.get(
    "/predictions",
    response_model=list[PredictionResponse],
    responses={401: {"model": ErrorResponse}},
)
def user_predictions_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = get_prediction_history(db, current_user.id)
    return [serialize_prediction(item) for item in items]


@router.get(
    "/transactions",
    response_model=list[TransactionResponse],
    responses={401: {"model": ErrorResponse}},
)
def user_transactions_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = list_transactions(db, current_user.id)
    return [serialize_transaction(item) for item in items]