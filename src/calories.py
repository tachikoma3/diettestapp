"""Estimated calories from activity MET values."""

from __future__ import annotations

import pandas as pd

MET_VALUES = {
    "walking": 3.5,
    "running": 8.0,
    "cycling": 7.5,
    "driving": 1.5,
    "transit": 1.5,
    "still": 1.2,
    "unknown": 1.5,
}


def met_for_activity(activity_type: object) -> float:
    text = str(activity_type or "").strip().lower()
    for activity, met in MET_VALUES.items():
        if activity in text:
            return met
    if any(token in text for token in ("walk", "徒歩", "歩行")):
        return MET_VALUES["walking"]
    if any(token in text for token in ("run", "走")):
        return MET_VALUES["running"]
    if any(token in text for token in ("cycle", "bike", "自転車")):
        return MET_VALUES["cycling"]
    return MET_VALUES["unknown"]


def estimate_calories(met: float, weight_kg: float, duration_seconds: float) -> float:
    """Standard kcal estimate: MET × 3.5 × kg / 200 × minutes."""
    if weight_kg < 0 or duration_seconds < 0:
        raise ValueError("weight and duration must not be negative")
    return float(met * 3.5 * weight_kg / 200 * (duration_seconds / 60))


def add_calories(frame: pd.DataFrame, weight_kg: float = 65.0) -> pd.DataFrame:
    if weight_kg < 0:
        raise ValueError("weight_kg must not be negative")
    result = frame.copy(deep=True)
    durations = (
        pd.to_numeric(result["duration"], errors="coerce").fillna(0).clip(lower=0)
        if "duration" in result
        else pd.Series(0.0, index=result.index)
    )
    result["met"] = result.get("activity_type", pd.Series("unknown", index=result.index)).map(met_for_activity)
    result["estimated_calories_kcal"] = [
        estimate_calories(met, weight_kg, duration) for met, duration in zip(result["met"], durations)
    ]
    return result


calculate_calories = estimate_calories
