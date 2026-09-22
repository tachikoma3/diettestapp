"""GPSデータの前処理と速度計算."""

from __future__ import annotations

import pandas as pd

from src.distance import add_segment_distances
from src.movement import normalize_movement


def prepare_gps_data(frame: pd.DataFrame) -> pd.DataFrame:
    """GPSデータを時系列に整理し、距離・時間・速度を追加する."""
    result = frame.copy(deep=True)

    if result.empty:
        return result

    result["timestamp"] = pd.to_datetime(
        result["timestamp"],
        utc=True,
        errors="coerce",
    )

    result["latitude"] = pd.to_numeric(result["latitude"], errors="coerce")
    result["longitude"] = pd.to_numeric(result["longitude"], errors="coerce")

    result = result.dropna(
        subset=["timestamp", "latitude", "longitude"]
    )

    result = result.drop_duplicates(
        subset=["timestamp", "latitude", "longitude"]
    )

    result = result.sort_values(
        "timestamp",
        kind="stable",
    ).reset_index(drop=True)

    # 徒歩、車、電車などの分類を正規化
    result = normalize_movement(result)

    # 緯度経度から区間距離を計算
    result = add_segment_distances(result, overwrite=False)

    elapsed_seconds = (
        result["timestamp"]
        .diff()
        .dt.total_seconds()
        .fillna(0)
        .clip(lower=0)
    )

    result["duration_s"] = (
        pd.to_numeric(result["duration"], errors="coerce")
        .fillna(elapsed_seconds)
        .clip(lower=0)
    )

    result["distance_m"] = (
        pd.to_numeric(result["distance"], errors="coerce")
        .fillna(0)
        .clip(lower=0)
    )

    result["speed_mps"] = (
        result["distance_m"]
        .div(result["duration_s"].replace(0, pd.NA))
        .fillna(0)
    )

    result["speed_kmh"] = result["speed_mps"] * 3.6
    result["date"] = result["timestamp"].dt.date

    return result
