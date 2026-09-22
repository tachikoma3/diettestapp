"""Activity label normalization."""

from __future__ import annotations

import pandas as pd


def normalize_activity_type(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text or text in {"nan", "none", "unknown"}:
        return "unknown"
    if any(token in text for token in ("walk", "徒歩", "歩行", "hike", "ハイキング")):
        return "walking"
    if any(token in text for token in ("run", "走")):
        return "running"
    if any(token in text for token in ("cycl", "bike", "自転車")):
        return "cycling"
    if any(token in text for token in ("drive", "car", "車")):
        return "driving"
    if any(token in text for token in ("transit", "train", "bus", "rail", "電車", "バス")):
        return "transit"
    if any(token in text for token in ("still", "stationary", "静止", "停止")):
        return "still"
    return text


def normalize_movement(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy(deep=True)
    source = result.get("activity_type", pd.Series("unknown", index=result.index))
    result["activity_type"] = source.map(normalize_activity_type)
    result["movement_category"] = result["activity_type"].where(
        ~result["activity_type"].isin(["still", "unknown"]), "stationary"
    )
    return result


normalize_activity = normalize_activity_type
