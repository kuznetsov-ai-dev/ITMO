from decimal import Decimal

from src.models import BalanceTransaction, MLModel, PredictionRequest, User


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "login": user.login,
        "email": user.email,
        "role": user.role.value,
        "balance": str(user.balance.amount if user.balance else Decimal("0.00")),
        "created_at": user.created_at,
    }


def serialize_model(model: MLModel) -> dict:
    return {
        "id": model.id,
        "name": model.name,
        "description": model.description,
        "price": str(model.price),
        "is_active": model.is_active,
        "created_at": model.created_at,
    }


def serialize_transaction(tx: BalanceTransaction) -> dict:
    return {
        "id": tx.id,
        "user_id": tx.user_id,
        "amount": str(tx.amount),
        "transaction_type": tx.transaction_type.value,
        "description": tx.description,
        "ml_request_id": tx.ml_request_id,
        "created_at": tx.created_at,
    }


def serialize_prediction(item: PredictionRequest) -> dict:
    return {
        "id": item.id,
        "task_id": item.task_id,
        "user_id": item.user_id,
        "model_id": item.model_id,
        "model_name": item.ml_model.name if item.ml_model else None,
        "status": item.status.value,
        "worker_id": item.worker_id,
        "charged_amount": str(item.charged_amount),
        "total_rows": item.total_rows,
        "valid_rows": item.valid_rows,
        "invalid_rows": item.invalid_rows,
        "created_at": item.created_at,
        "finished_at": item.finished_at,
        "result_payload": item.result_payload,
    }