"""Speed calculations with explicit instantaneous and average measures."""

from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_speed(distance_m: float, duration_s: float) -> float:
    """Return speed in m/s; zero is returned for missing/non-positive duration."""
    try:
        distance, duration = float(distance_m), float(duration_s)
    except (TypeError, ValueError):
        return 0.0
    return distance / duration if distance >= 0 and duration > 0 else 0.0


def instantaneous_speeds(frame: pd.DataFrame) -> pd.Series:
    distance = pd.to_numeric(frame["distance"], errors="coerce")
    duration = pd.to_numeric(frame["duration"], errors="coerce")
    return (distance / duration.where(duration > 0)).rename("calculated_speed")


def average_speeds(frame: pd.DataFrame) -> dict[str, float]:
    """Distinguish distance-weighted average from arithmetic observed mean."""
    distance = pd.to_numeric(frame["distance"], errors="coerce")
    duration = pd.to_numeric(frame["duration"], errors="coerce")
    observed = (
        pd.to_numeric(frame["speed"], errors="coerce")
        if "speed" in frame
        else pd.Series(np.nan, index=frame.index, dtype=float)
    )
    valid_duration = duration > 0
    total_distance = distance[valid_duration].sum(min_count=1)
    total_duration = duration[valid_duration].sum(min_count=1)
    weighted = float(total_distance / total_duration) if total_duration and not pd.isna(total_duration) else 0.0
    observed_mean = float(observed.dropna().mean()) if observed.notna().any() else 0.0
    return {
        "distance_weighted_average_mps": weighted,
        "observed_arithmetic_mean_mps": observed_mean,
    }


def calculate_average_speed(distance_m: float, duration_s: float, unit: str = "m/s") -> float:
    """Calculate total-distance/total-time speed in m/s or km/h."""
    speed_mps = calculate_speed(distance_m, duration_s)
    if unit.lower() in {"km/h", "kmh", "kph"}:
        return speed_mps * 3.6
    if unit.lower() in {"m/s", "mps"}:
        return speed_mps
    raise ValueError("unit must be 'm/s' or 'km/h'")


def add_speed_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy(deep=True)
    result["calculated_speed"] = instantaneous_speeds(result)
    result["speed_source"] = np.where(
        pd.to_numeric(result.get("speed"), errors="coerce").notna() if "speed" in result else False,
        "observed",
        "calculated",
    )
    summary = average_speeds(result)
    result.attrs["speed_summary"] = summary
    return result


# Descriptive aliases useful to callers.
calculate_instantaneous_speed = calculate_speed
calculate_average_speeds = average_speeds
