"""Walking step estimates."""

from __future__ import annotations

import pandas as pd


def steps_from_distance(distance_m: float, stride_length_m: float = 0.70) -> int:
    if stride_length_m <= 0:
        raise ValueError("stride_length_m must be greater than zero")
    try:
        distance = float(distance_m)
    except (TypeError, ValueError):
        return 0
    return max(0, round(distance / stride_length_m)) if distance >= 0 else 0


def is_walking(activity_type: object) -> bool:
    text = str(activity_type or "").strip().lower()
    return any(token in text for token in ("walk", "walking", "徒歩", "歩行", "hike", "ハイキング"))


def walking_distance(frame: pd.DataFrame) -> float:
    activity = frame["activity_type"].map(is_walking) if "activity_type" in frame else pd.Series(False, index=frame.index)
    distance = (
        pd.to_numeric(frame["distance"], errors="coerce").fillna(0)
        if "distance" in frame
        else pd.Series(0.0, index=frame.index)
    )
    return float(distance[activity].clip(lower=0).sum())


def estimate_steps(frame: pd.DataFrame, stride_length_m: float = 0.70) -> int:
    return steps_from_distance(walking_distance(frame), stride_length_m)


def add_steps(frame: pd.DataFrame, stride_length_m: float = 0.70) -> pd.DataFrame:
    if stride_length_m <= 0:
        raise ValueError("stride_length_m must be greater than zero")
    result = frame.copy(deep=True)
    result["estimated_steps"] = 0
    walking = result["activity_type"].map(is_walking) if "activity_type" in result else pd.Series(False, index=result.index)
    distances = (
        pd.to_numeric(result["distance"], errors="coerce").fillna(0).clip(lower=0)
        if "distance" in result
        else pd.Series(0.0, index=result.index)
    )
    result.loc[walking, "estimated_steps"] = (distances[walking] / stride_length_m).round().astype(int)
    return result


calculate_steps = steps_from_distance
