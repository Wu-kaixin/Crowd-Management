"""JSON serialization helpers shared by evaluation and experiment runners."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np


def jsonable(value: Any) -> Any:
    """Convert nested values into JSON-serializable Python objects.

    Non-finite floats become ``None`` so formal records remain legal JSON.
    """
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write_json(path: Path | str, value: Any) -> None:
    """Write ``value`` as pretty-printed UTF-8 JSON with a trailing newline."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(jsonable(value), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_records_csv(path: Path | str, records: list[dict[str, Any]]) -> None:
    """Write homogeneous dict records as CSV (empty file when no rows)."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        destination.write_text("", encoding="utf-8")
        return
    fieldnames = list(records[0].keys())
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({key: jsonable(record.get(key)) for key in fieldnames})
