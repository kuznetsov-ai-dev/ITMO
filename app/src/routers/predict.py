from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.db import get_db
from src.dependencies import get_current_user
from src.models import User
from src.schemas import (
    ErrorResponse,
    MLModelResponse,
    PredictionRunIn,
    PredictionRunResponse,
)
from src.serializers import serialize_model, serialize_prediction
from src.services import get_user, list_ml_models, run_prediction


router = APIRouter(tags=["predict"])


@router.get(
    "/models",
    response_model=list[MLModelResponse],
    responses={401: {"model": ErrorResponse}},
)
def get_models(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    models = list_ml_models(db, only_active=True)
    return [serialize_model(model) for model in models]


@router.post(
    "/predict",
    response_model=PredictionRunResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def run_prediction_endpoint(
    payload: PredictionRunIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = run_prediction(
        session=db,
        user_id=current_user.id,
        model_id=payload.model_id,
        rows=payload.rows,
    )
    updated_user = get_user(db, current_user.id)

    return {
        "balance": str(updated_user.balance.amount),
        "prediction": serialize_prediction(result),
    }