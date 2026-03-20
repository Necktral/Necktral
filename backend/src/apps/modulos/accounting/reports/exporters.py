from __future__ import annotations

import csv
import io
import json
from typing import Any

SUPPORTED_EXPORT_FORMATS = {"json", "csv"}


def serialize_report_results(*, payload: dict[str, Any], export_format: str) -> tuple[bytes, str]:
    fmt = str(export_format or "").strip().lower()
    if fmt not in SUPPORTED_EXPORT_FORMATS:
        raise ValueError(f"unsupported export format: {fmt}")

    if fmt == "json":
        return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"), "application/json"

    results = payload.get("results")
    if not isinstance(results, list):
        rows: list[dict[str, Any]] = []
    else:
        rows = [dict(item) for item in results if isinstance(item, dict)]

    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(str(key))

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames or ["result"])
    writer.writeheader()
    if fieldnames:
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    csv_body = buf.getvalue().encode("utf-8")
    return csv_body, "text/csv"

