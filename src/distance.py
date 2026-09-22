"""Distance calculations using the Haversine formula."""

from __future__ import annotations

import numpy as np
import pandas as pd

EARTH_RADIUS_METERS = 6_371_000.0


def haversine_distance(
    latitude_1: float | np.ndarray,
    longitude_1: float | np.ndarray,
    latitude_2: float | np.ndarray,
    longitude_2: float | np.ndarray,
) -> float | np.ndarray:
    """Return great-circle distance in meters for scalar or array inputs."""
    lat1, lon1, lat2, lon2 = map(np.asarray, (latitude_1, longitude_1, latitude_2, longitude_2))
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
    a = np.sin(delta_lat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(delta_lon / 2) ** 2
    distance = 2 * EARTH_RADIUS_METERS * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    return float(distance) if distance.ndim == 0 else distance


def segment_distances(frame: pd.DataFrame) -> pd.Series:
    """Calculate point-to-point distances, with zero for the first point."""
    lat = pd.to_numeric(frame["latitude"], errors="coerce")
    lon = pd.to_numeric(frame["longitude"], errors="coerce")
    values = np.full(len(frame), np.nan, dtype=float)
    if len(frame):
        values[0] = 0.0
    if len(frame) > 1:
        valid = lat.notna().to_numpy()[1:] & lon.notna().to_numpy()[1:] & lat.notna().to_numpy()[:-1] & lon.notna().to_numpy()[:-1]
        calculated = haversine_distance(
            lat.to_numpy()[:-1], lon.to_numpy()[:-1], lat.to_numpy()[1:], lon.to_numpy()[1:]
        )
        values[1:] = np.where(valid, calculated, np.nan)
    return pd.Series(values, index=frame.index, name="calculated_distance")


def add_segment_distances(frame: pd.DataFrame, overwrite: bool = False) -> pd.DataFrame:
    result = frame.copy(deep=True)
    calculated = segment_distances(result)
    if "distance" not in result or overwrite:
        result["distance"] = calculated
    else:
        result["distance"] = pd.to_numeric(result["distance"], errors="coerce").fillna(calculated)
    result["calculated_distance"] = calculated
    return result


def calculate_distance(latitude_1: float, longitude_1: float, latitude_2: float, longitude_2: float) -> float:
    """Calculate the Haversine distance between two points in meters."""
    return float(haversine_distance(latitude_1, longitude_1, latitude_2, longitude_2))


def segment_distance(frame: pd.DataFrame) -> pd.Series:
    """Compatibility API for point-to-point segment distances."""
    return segment_distances(frame)


def total_distance(frame: pd.DataFrame) -> float:
    """Return the sum of non-negative segment distances in meters."""
    raw = frame["distance"] if "distance" in frame else pd.Series(dtype=float)
    values = pd.to_numeric(raw, errors="coerce").fillna(0).clip(lower=0)
    return float(values.sum())


def daily_distance(frame: pd.DataFrame) -> pd.Series:
    """Return total distance grouped by UTC calendar date."""
    if "timestamp" not in frame:
        return pd.Series(dtype=float, name="distance")
    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    raw = frame["distance"] if "distance" in frame else pd.Series(0.0, index=frame.index)
    values = pd.to_numeric(raw, errors="coerce").fillna(0).clip(lower=0)
    return values.groupby(timestamps.dt.date).sum().rename("distance")


haversine = haversine_distance
