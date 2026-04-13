from typing import Any


def validate_prediction_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    good_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        if "value" not in row:
            errors.append(
                {
                    "row_num": index,
                    "field_name": "value",
                    "text": "нет такого поля",
                }
            )
            continue

        if not isinstance(row["value"], (int, float)):
            errors.append(
                {
                    "row_num": index,
                    "field_name": "value",
                    "text": "тут должно быть число",
                }
            )
            continue

        good_rows.append(row)

    return good_rows, errors


def predict_with_simple_model(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for row in rows:
        new_row = row.copy()
        value = row.get("value", 0)
        new_row["answer"] = "хорошо" if value >= 10 else "плохо"
        result.append(new_row)

    return result