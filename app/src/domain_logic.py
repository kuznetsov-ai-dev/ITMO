from typing import Any


def validate_task_features(
    features: dict[str, Any] | Any,
) -> tuple[dict[str, float], list[dict[str, str]]]:
    if not isinstance(features, dict):
        return {}, [
            {
                "field_name": "features",
                "text": "features должен быть объектом",
            }
        ]

    if not features:
        return {}, [
            {
                "field_name": "features",
                "text": "features не должен быть пустым",
            }
        ]

    normalized_features: dict[str, float] = {}
    errors: list[dict[str, str]] = []

    for key, value in features.items():
        if not isinstance(key, str) or not key.strip():
            errors.append(
                {
                    "field_name": "features",
                    "text": "ключ признака должен быть непустой строкой",
                }
            )
            continue

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(
                {
                    "field_name": key,
                    "text": "значение признака должно быть числом",
                }
            )
            continue

        normalized_features[key.strip()] = float(value)

    return normalized_features, errors


def _validate_value_feature(
    model_name: str,
    features: dict[str, float],
) -> list[dict[str, str]]:
    if "value" not in features:
        return [
            {
                "field_name": "value",
                "text": f"для модели {model_name} обязателен признак value",
            }
        ]
    return []


def predict_simple_quality_model(features: dict[str, float]) -> dict[str, Any]:
    value = round(features["value"], 2)
    return {
        "prediction": "хорошо" if value >= 10 else "плохо",
        "value": value,
        "threshold": 10.0,
    }


def predict_simple_fast_model(features: dict[str, float]) -> dict[str, Any]:
    value = round(features["value"], 2)
    return {
        "prediction": "хорошо" if value >= 5 else "плохо",
        "value": value,
        "threshold": 5.0,
    }


def run_model_prediction(
    model_name: str,
    features: dict[str, float],
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    errors = _validate_value_feature(model_name=model_name, features=features)
    if errors:
        return None, errors

    if model_name == "simple-quality-model":
        return predict_simple_quality_model(features), []

    if model_name == "simple-fast-model":
        return predict_simple_fast_model(features), []

    return None, [
        {
            "field_name": "model",
            "text": f"для модели {model_name} не реализована логика предикта",
        }
    ]