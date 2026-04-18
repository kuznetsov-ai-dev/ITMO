import csv
import io
import json
from typing import Any


def _convert_scalar(value: Any) -> Any:
    if value is None:
        return ""

    if isinstance(value, (int, float)):
        return value

    text = str(value).strip()

    if text == "":
        return ""

    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"

    try:
        if any(symbol in text for symbol in [".", ",", "e", "E"]):
            return float(text.replace(",", "."))
        return int(text)
    except ValueError:
        return text


def parse_features_json(raw_text: str) -> list[dict[str, Any]]:
    payload = json.loads(raw_text)

    if not isinstance(payload, dict):
        raise ValueError("JSON для одной записи должен быть объектом")

    return [
        {
            "row_id": "row-1",
            "features": payload,
        }
    ]


def parse_rows_json(raw_text: str) -> list[dict[str, Any]]:
    payload = json.loads(raw_text)

    if isinstance(payload, dict):
        return [
            {
                "row_id": "row-1",
                "features": payload,
            }
        ]

    if not isinstance(payload, list):
        raise ValueError("JSON списка должен быть массивом")

    rows: list[dict[str, Any]] = []

    for index, item in enumerate(payload, start=1):
        if isinstance(item, dict) and "features" in item:
            row_id = item.get("row_id") or f"row-{index}"
            rows.append(
                {
                    "row_id": str(row_id),
                    "features": item.get("features"),
                }
            )
        else:
            rows.append(
                {
                    "row_id": f"row-{index}",
                    "features": item,
                }
            )

    return rows


def parse_csv_rows(content: bytes) -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise ValueError("CSV-файл пустой или не содержит заголовков")

    rows: list[dict[str, Any]] = []

    for index, row in enumerate(reader, start=1):
        features = {key: _convert_scalar(value) for key, value in row.items()}
        rows.append(
            {
                "row_id": f"csv-{index}",
                "features": features,
            }
        )

    if not rows:
        raise ValueError("CSV-файл не содержит строк данных")

    return rows