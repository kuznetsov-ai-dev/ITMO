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

        if not isinstance(value, (int, float)):
            errors.append(
                {
                    "field_name": key,
                    "text": "значение признака должно быть числом",
                }
            )
            continue

        normalized_features[key.strip()] = float(value)

    return normalized_features, errors


def predict_demo_model(features: dict[str, float]) -> float:
    return round(sum(features.values()), 2)