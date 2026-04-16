from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.db import get_db
from src.dependencies import get_current_user
from src.models import User
from src.schemas import ErrorResponse, UserProfileResponse
from src.serializers import serialize_user
from src.services import get_prediction_history, list_transactions


router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserProfileResponse,
    responses={401: {"model": ErrorResponse}},
)
def get_current_user_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    transactions = list_transactions(db, current_user.id)
    predictions = get_prediction_history(db, current_user.id)

    result = serialize_user(current_user)
    result["transaction_count"] = len(transactions)
    result["prediction_count"] = len(predictions)
    return result