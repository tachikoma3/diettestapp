"""一日の活動量を分析するモジュール."""

from __future__ import annotations

import pandas as pd


WALKING_MODES = {"walking", "running"}

MET_BY_MODE = {
    "walking": 3.5,
    "running": 7.0,
    "cycling": 6.8,
    "driving": 1.5,
    "transit": 1.5,
    "still": 1.2,
    "unknown": 1.5,
}


def classify_activity_mode(value: object) -> str:
    """移動手段を標準的な分類名へ変換する."""
    text = str(value or "").strip().lower()

    if not text or text in {"nan", "none", "unknown"}:
        return "unknown"

    if any(word in text for word in ["walk", "徒歩", "歩行"]):
        return "walking"

    if any(word in text for word in ["run", "running", "走"]):
        return "running"

    if any(word in text for word in ["bike", "cycle", "自転車"]):
        return "cycling"

    if any(word in text for word in ["drive", "car", "車"]):
        return "driving"

    if any(
        word in text
        for word in ["train", "bus", "rail", "transit", "電車", "バス"]
    ):
        return "transit"

    if any(word in text for word in ["still", "stationary", "静止"]):
        return "still"

    return "unknown"


def analyze_day(
    frame: pd.DataFrame,
    stride_m: float = 0.70,
    weight_kg: float = 65.0,
) -> dict[str, object]:
    """選択された一日の活動指標を計算する."""
    if frame.empty:
        return {
            "total_distance_km": 0.0,
            "moving_minutes": 0.0,
            "average_speed_kmh": 0.0,
            "simple_average_speed_kmh": 0.0,
            "estimated_steps": 0.0,
            "estimated_calories_kcal": 0.0,
            "mode_summary": pd.DataFrame(),
        }

    data = frame.copy()

    data["movement_mode"] = data["activity_type"].map(
        classify_activity_mode
    )

    distance = (
        pd.to_numeric(data["distance_m"], errors="coerce")
        .fillna(0)
        .clip(lower=0)
    )

    duration = (
        pd.to_numeric(data["duration_s"], errors="coerce")
        .fillna(0)
        .clip(lower=0)
    )

    walking_distance = distance[
        data["movement_mode"].isin(WALKING_MODES)
    ].sum()

    total_distance = float(distance.sum())
    total_duration = float(duration.sum())

    speed_values = (
        pd.to_numeric(data["speed_kmh"], errors="coerce")
        .replace([float("inf"), -float("inf")], pd.NA)
        .dropna()
    )

    calories = 0.0

    for mode, seconds in zip(data["movement_mode"], duration):
        met = MET_BY_MODE.get(str(mode), 1.5)
        calories += met * weight_kg * float(seconds) / 3600

    mode_summary = (
        pd.DataFrame(
            {
                "movement_mode": data["movement_mode"],
                "distance_m": distance,
                "duration_s": duration,
            }
        )
        .groupby("movement_mode")
        .agg(
            distance_km=("distance_m", lambda x: x.sum() / 1000),
            duration_min=("duration_s", lambda x: x.sum() / 60),
            records=("movement_mode", "size"),
        )
        .reset_index()
    )

    total_mode_distance = mode_summary["distance_km"].sum()

    if total_mode_distance:
        mode_summary["share_percent"] = (
            mode_summary["distance_km"]
            / total_mode_distance
            * 100
        ).round(1)
    else:
        mode_summary["share_percent"] = 0.0

    return {
        "total_distance_km": total_distance / 1000,
        "moving_minutes": total_duration / 60,
        "average_speed_kmh": (
            total_distance / total_duration * 3.6
            if total_duration
            else 0.0
        ),
        "simple_average_speed_kmh": (
            float(speed_values.mean())
            if len(speed_values)
            else 0.0
        ),
        "estimated_steps": walking_distance / max(stride_m, 0.01),
        "estimated_calories_kcal": calories,
        "mode_summary": mode_summary,
    }
