from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.db import get_db
from src.dependencies import get_current_user
from src.models import User
from src.schemas import (
    ErrorResponse,
    MLModelResponse,
    PredictTaskAcceptedResponse,
    PredictTaskIn,
    PredictionResponse,
)
from src.serializers import serialize_model, serialize_prediction
from src.services import (
    create_prediction_task,
    get_prediction_by_task_id,
    list_ml_models,
)


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
    response_model=PredictTaskAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def run_prediction_endpoint(
    payload: PredictTaskIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = [row.model_dump() for row in payload.rows] if payload.rows else None

    task = create_prediction_task(
        session=db,
        user_id=current_user.id,
        model_name=payload.model,
        features=payload.features,
        rows=rows,
    )

    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "total_rows": task.total_rows,
    }


@router.get(
    "/predict/{task_id}",
    response_model=PredictionResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def get_prediction_status_endpoint(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = get_prediction_by_task_id(db, task_id)

    if task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа к этой задаче")

    return serialize_prediction(task)