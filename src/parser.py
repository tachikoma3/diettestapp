"""Robust parsing and non-destructive preprocessing for timeline JSON data."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

NORMALIZED_COLUMNS = [
    "timestamp",
    "latitude",
    "longitude",
    "activity_type",
    "speed",
    "distance",
    "duration",
]


def load_timeline(source: Any) -> Any:
    """Load JSON from a path, uploaded file, bytes, or an already parsed object."""
    if hasattr(source, "getvalue"):
        source = source.getvalue()
    if isinstance(source, (bytes, bytearray)):
        return json.loads(source)
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.is_file():
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        return json.loads(source)
    return source

_TIMESTAMP_KEYS = (
    "timestamp",
    "time",
    "datetime",
    "date",
    "startTime",
    "start_time",
    "startTimestamp",
    "start_timestamp",
)
_END_TIMESTAMP_KEYS = (
    "endTime",
    "end_time",
    "endTimestamp",
    "end_timestamp",
)


def _number(value: Any) -> float | None:
    """Return a finite float, accepting numeric strings and JSON numbers."""
    if value is None or isinstance(value, bool):
        return None
    try:
        value = str(value).strip().replace(",", "")
        if not value:
            return None
        result = float(value)
        return result if np.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _find_value(record: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    lowered = {str(k).lower(): v for k, v in record.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _timestamp(value: Any) -> pd.Timestamp | pd.NaT:
    if value is None:
        return pd.NaT
    numeric = _number(value)
    if numeric is not None:
        # Numeric timestamps in exports are epoch seconds or milliseconds.
        unit = "ms" if abs(numeric) > 10_000_000_000 else "s"
        return pd.to_datetime(numeric, unit=unit, utc=True, errors="coerce")
    return pd.to_datetime(value, utc=True, errors="coerce")


def _coordinate(record: dict[str, Any]) -> tuple[float | None, float | None]:
    """Extract coordinates from common representations, including E7 values."""
    lat = _find_value(record, ("latitude", "lat", "latitudeE7", "latE7"))
    lon = _find_value(record, ("longitude", "lon", "lng", "longitudeE7", "lonE7"))

    if lat is None or lon is None:
        for key in (
            "location",
            "startLocation",
            "endLocation",
            "coordinate",
            "coordinates",
            "latLng",
            "lat_lng",
            "placeLocation",
            "point",
            "geo",
        ):
            nested = record.get(key)
            if isinstance(nested, dict):
                nested_lat, nested_lon = _coordinate(nested)
                if nested_lat is not None and nested_lon is not None:
                    return nested_lat, nested_lon
            elif isinstance(nested, (list, tuple)) and len(nested) >= 2:
                first, second = _number(nested[0]), _number(nested[1])
                if first is not None and second is not None:
                    return first, second
            elif isinstance(nested, str):
                match = re.search(r"(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)", nested)
                if match:
                    return float(match.group(1)), float(match.group(2))
        # Timeline exports place coordinates under vendor-specific wrappers
        # such as visit.topCandidate.placeLocation. Walk nested objects as a
        # fallback rather than depending on one schema name.
        for nested in record.values():
            if isinstance(nested, dict):
                nested_lat, nested_lon = _coordinate(nested)
                if nested_lat is not None and nested_lon is not None:
                    return nested_lat, nested_lon

    lat_num, lon_num = _number(lat), _number(lon)
    if lat_num is not None and abs(lat_num) > 90:
        lat_num /= 10_000_000
    if lon_num is not None and abs(lon_num) > 180:
        lon_num /= 10_000_000
    if lat_num is not None and not -90 <= lat_num <= 90:
        lat_num = None
    if lon_num is not None and not -180 <= lon_num <= 180:
        lon_num = None
    return lat_num, lon_num


def _activity(record: dict[str, Any], inherited: str | None) -> str | None:
    value = _find_value(
        record,
        ("activity_type", "activityType", "activity", "motion", "mode", "semanticType"),
    )
    if isinstance(value, dict):
        value = _find_value(value, ("type", "activityType", "name"))
    if isinstance(value, list) and value:
        first = value[0]
        value = first.get("type", first.get("activityType")) if isinstance(first, dict) else first
    if value is None:
        for nested in record.values():
            if isinstance(nested, dict):
                nested_value = _activity(nested, None)
                if nested_value is not None:
                    value = nested_value
                    break
    if value is None:
        value = inherited
    if value is None:
        return None
    return str(value)


def _measurement(record: dict[str, Any], kind: str) -> float | None:
    if kind == "speed":
        value = _find_value(record, ("speed", "speedMps", "speedMetersPerSecond", "velocity"))
        if value is not None:
            return _number(value)
        value = _find_value(record, ("speedKph", "speedKmH", "speedKmh"))
        return None if _number(value) is None else _number(value) / 3.6
    if kind == "distance":
        value = _find_value(record, ("distance", "distanceMeters", "meters", "distance_m"))
        if value is not None:
            return _number(value)
        value = _find_value(record, ("distanceKm", "distance_km"))
        return None if _number(value) is None else _number(value) * 1000
    value = _find_value(record, ("duration", "durationSeconds", "duration_s"))
    if value is not None:
        return _number(value)
    value = _find_value(record, ("durationMinutes", "duration_min"))
    return None if _number(value) is None else _number(value) * 60


def _walk(value: Any, inherited_activity: str | None = None) -> Iterable[dict[str, Any]]:
    """Yield records without relying on a particular vendor's nesting shape."""
    if isinstance(value, list):
        for item in value:
            yield from _walk(item, inherited_activity)
        return
    if not isinstance(value, dict):
        return

    activity = _activity(value, inherited_activity)
    lat, lon = _coordinate(value)
    start_raw = _find_value(value, _TIMESTAMP_KEYS)
    end_raw = _find_value(value, _END_TIMESTAMP_KEYS)
    timestamp = _timestamp(start_raw)
    duration = _measurement(value, "duration")
    if duration is None and start_raw is not None and end_raw is not None:
        start, end = _timestamp(start_raw), _timestamp(end_raw)
        if not pd.isna(start) and not pd.isna(end):
            duration = max(0.0, (end - start).total_seconds())

    has_measurement = any(
        item is not None
        for item in (lat, lon, activity, _measurement(value, "speed"), _measurement(value, "distance"), duration)
    )
    if not pd.isna(timestamp) and has_measurement:
        yield {
            "timestamp": timestamp,
            "latitude": lat,
            "longitude": lon,
            "activity_type": activity,
            "speed": _measurement(value, "speed"),
            "distance": _measurement(value, "distance"),
            "duration": duration,
        }

    for key, child in value.items():
        # Avoid treating scalar metadata as records; nested objects and arrays
        # are still visited, regardless of their key name.
        if isinstance(child, (dict, list)):
            yield from _walk(child, activity)


def parse_timeline_json(data: Any) -> pd.DataFrame:
    """Parse a JSON object/list into the stable normalized dataframe schema."""
    data = load_timeline(data)
    rows = list(_walk(data))
    frame = pd.DataFrame(rows, columns=NORMALIZED_COLUMNS)
    if frame.empty:
        return pd.DataFrame({column: pd.Series(dtype="object") for column in NORMALIZED_COLUMNS})
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    for column in ("latitude", "longitude", "speed", "distance", "duration"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values("timestamp", kind="stable").reset_index(drop=True)


def load_timeline_json(path: str | Path) -> pd.DataFrame:
    with Path(path).open("r", encoding="utf-8") as handle:
        return parse_timeline_json(json.load(handle))


def parse_segments(data: Any) -> list[dict[str, Any]]:
    """Return raw segment-like records discovered without assuming vendor keys."""
    return list(_walk(load_timeline(data)))


def extract_locations(data: Any) -> pd.DataFrame:
    """Extract location rows while retaining the normalized schema."""
    frame = parse_timeline_json(data)
    return frame.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)


def extract_activities(data: Any) -> pd.DataFrame:
    """Extract rows containing an activity label."""
    frame = parse_timeline_json(data)
    return frame[frame["activity_type"].notna()].reset_index(drop=True)


def normalize_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names and scalar types without mutating the input."""
    result = frame.copy(deep=True)
    for column in NORMALIZED_COLUMNS:
        if column not in result:
            result[column] = pd.NA
    result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True, errors="coerce")
    for column in ("latitude", "longitude", "speed", "distance", "duration"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result[NORMALIZED_COLUMNS].sort_values("timestamp", kind="stable").reset_index(drop=True)


def preprocess_timeline(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with quality flags; the caller's dataframe is untouched."""
    result = frame.copy(deep=True)
    for column in NORMALIZED_COLUMNS:
        if column not in result:
            result[column] = pd.NA
    result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True, errors="coerce")
    result["valid_coordinate"] = (
        pd.to_numeric(result["latitude"], errors="coerce").between(-90, 90)
        & pd.to_numeric(result["longitude"], errors="coerce").between(-180, 180)
    )
    result["has_duration"] = pd.to_numeric(result["duration"], errors="coerce").ge(0)
    result["has_distance"] = pd.to_numeric(result["distance"], errors="coerce").ge(0)
    result["has_speed"] = pd.to_numeric(result["speed"], errors="coerce").ge(0)
    result["is_duplicate"] = result.duplicated(
        subset=["timestamp", "latitude", "longitude"], keep="first"
    )
    result["gps_jump"] = False
    result["abnormal_speed"] = False
    if len(result) > 1:
        from src.distance import segment_distances

        segment = segment_distances(result)
        elapsed = result["timestamp"].diff().dt.total_seconds()
        derived_speed = segment / elapsed
        result["gps_jump"] = segment.gt(5000) & elapsed.between(0, 300, inclusive="both")
        result["abnormal_speed"] = derived_speed.gt(55)
    activity = result["activity_type"].fillna("").astype(str).str.strip()
    result["is_movement"] = ~activity.str.lower().isin({"", "still", "stationary", "unknown", "nan"})
    result["quality_flags"] = np.select(
        [
            result["timestamp"].isna(),
            ~result["valid_coordinate"],
            result["has_duration"] == False,  # noqa: E712
            result["is_duplicate"],
            result["gps_jump"],
            result["abnormal_speed"],
        ],
        [
            "missing_timestamp",
            "invalid_coordinate",
            "missing_duration",
            "duplicate",
            "gps_jump",
            "abnormal_speed",
        ],
        default="",
    )
    return result
