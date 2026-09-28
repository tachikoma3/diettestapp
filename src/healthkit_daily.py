"""Apple Health の export.xml を日別に集計する.

Workout や GPS ルートを含まないエクスポートでも、
Record(歩数・距離・消費エネルギーなど)と ActivitySummary から
日別のKPIを作れる。

- iterparse によるストリーム解析なので、100MBを超える export.xml でも
  メモリを使いすぎない。
- export.xml は <!DOCTYPE HealthData [...]> の内部DTDを含む。
  defusedxml は forbid_dtd=False(既定)のまま使うこと。
  forbid_dtd=True にすると正規のAppleエクスポートが拒否される。
  外部エンティティ・エンティティ展開は forbid_entities=True(既定)で防げる。
- iPhone / Apple Watch / 他アプリの記録が重なる日は二重計上を避けるため、
  日ごと・指標ごとに「合計値が最大のソース」を採用する(近似)。

src/healthkit_daily.py として配置する想定。
"""

from __future__ import annotations

from collections import defaultdict
from typing import BinaryIO

import pandas as pd
from defusedxml.ElementTree import iterparse

_PREFIX = "HKQuantityTypeIdentifier"

# 合計する指標: type名 -> (列名, 変換前単位 -> 変換係数)
_SUM_METRICS = {
    f"{_PREFIX}StepCount": ("steps", {"count": 1.0}),
    f"{_PREFIX}DistanceWalkingRunning": (
        "distance_km",
        {"km": 1.0, "m": 0.001, "mi": 1.609344},
    ),
    f"{_PREFIX}ActiveEnergyBurned": (
        "active_kcal",
        {"kcal": 1.0, "Cal": 1.0, "kJ": 0.239006},
    ),
    f"{_PREFIX}FlightsClimbed": ("flights", {"count": 1.0}),
}

# 平均する指標
_MEAN_METRICS = {
    f"{_PREFIX}WalkingSpeed": ("walking_speed_kmh", {"km/hr": 1.0, "km/h": 1.0, "m/s": 3.6}),
    f"{_PREFIX}WalkingStepLength": ("step_length_cm", {"cm": 1.0, "m": 100.0}),
}

COLUMNS = [
    "date",
    "steps",
    "distance_km",
    "active_kcal",
    "flights",
    "walking_speed_kmh",
    "step_length_cm",
    "exercise_min",
    "stand_hours",
]


def _best_source_sum(per_source: dict[str, float]) -> float:
    """ソースごとの合計のうち最大のものを返す(二重計上の回避)."""
    return max(per_source.values()) if per_source else 0.0


def parse_healthkit_daily(source: str | BinaryIO) -> pd.DataFrame:
    """export.xml(パスまたはファイルオブジェクト)を日別DataFrameにする."""
    # (指標名, 日付) -> {ソース名: 合計}
    sums: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    # (指標名, 日付) -> {ソース名: [合計, 件数]}
    means: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(lambda: [0.0, 0.0])
    )
    summary: dict[str, dict[str, float]] = {}

    for _, element in iterparse(source, events=("end",)):
        tag = element.tag

        if tag == "Record":
            record_type = element.get("type")
            if record_type in _SUM_METRICS or record_type in _MEAN_METRICS:
                try:
                    value = float(element.get("value"))
                except (TypeError, ValueError):
                    element.clear()
                    continue

                day = (element.get("startDate") or "")[:10]
                name_ = element.get("sourceName") or "unknown"
                unit = element.get("unit")

                if record_type in _SUM_METRICS:
                    column, factors = _SUM_METRICS[record_type]
                    sums[(column, day)][name_] += value * factors.get(unit, 1.0)
                else:
                    column, factors = _MEAN_METRICS[record_type]
                    acc = means[(column, day)][name_]
                    acc[0] += value * factors.get(unit, 1.0)
                    acc[1] += 1
            element.clear()

        elif tag == "ActivitySummary":
            day = element.get("dateComponents")
            if day:
                summary[day] = {
                    "exercise_min": float(element.get("appleExerciseTime") or 0),
                    "stand_hours": float(element.get("appleStandHours") or 0),
                }
            element.clear()

    rows: dict[str, dict[str, float]] = defaultdict(dict)

    for (column, day), per_source in sums.items():
        if day:
            rows[day][column] = _best_source_sum(per_source)

    for (column, day), per_source in means.items():
        if not day:
            continue
        # 件数が最も多いソースの平均を採用
        total, count = max(per_source.values(), key=lambda pair: pair[1])
        if count:
            rows[day][column] = total / count

    for day, values in summary.items():
        rows[day].update(values)

    if not rows:
        return pd.DataFrame(columns=COLUMNS)

    frame = pd.DataFrame.from_dict(rows, orient="index")
    frame.index.name = "date"
    frame = frame.reset_index()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
    frame = frame.dropna(subset=["date"]).sort_values("date")

    for column in COLUMNS[1:]:
        if column not in frame.columns:
            frame[column] = pd.NA

    return frame[COLUMNS].reset_index(drop=True)
