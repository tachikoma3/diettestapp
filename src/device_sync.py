"""iPhone、Android、スマートウォッチから運動量データを取得."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ActivityData:
    """デバイスから取得した運動量データ."""
    timestamp: str
    activity_type: str
    duration_seconds: float
    distance_meters: float | None = None
    steps: int | None = None
    calories: float | None = None
    heart_rate: int | None = None
    raw_data: dict[str, Any] | None = None


class HealthKitParser:
    """iPhoneのHealthKitエクスポートデータを解析."""

    @staticmethod
    def parse_export_json(
        payload: dict[str, Any],
    ) -> list[ActivityData]:
        """HealthKitのJSON形式（エクスポート）を解析.
        
        Expected format:
        {
            "data": {
                "HKWorkoutTypeIdentifier": [...],
                "HKQuantityTypeIdentifier...": [...]
            }
        }
        """
        activities = []

        # Workoutデータを処理
        data = payload.get("data", {})
        workouts = data.get("HKWorkoutTypeIdentifier", [])

        for workout in workouts:
            try:
                activities.append(
                    ActivityData(
                        timestamp=workout.get(
                            "startDate",
                            workout.get("creationDate", ""),
                        ),
                        activity_type=HealthKitParser._map_workout_type(
                            workout.get("workoutActivityType", "")
                        ),
                        duration_seconds=float(
                            workout.get("duration", 0) or 0
                        ),
                        distance_meters=HealthKitParser._get_distance(
                            workout
                        ),
                        calories=HealthKitParser._get_calories(workout),
                        heart_rate=HealthKitParser._get_heart_rate(
                            workout
                        ),
                        raw_data=workout,
                    )
                )
            except (ValueError, TypeError, KeyError):
                continue

        return activities

    @staticmethod
    def _map_workout_type(hk_type: str) -> str:
        """HealthKitのWorkoutタイプをアプリの活動種別にマッピング."""
        mapping = {
            "HKWorkoutActivityTypeWalking": "walking",
            "HKWorkoutActivityTypeRunning": "running",
            "HKWorkoutActivityTypeCycling": "cycling",
            "HKWorkoutActivityTypeSwimming": "swimming",
            "HKWorkoutActivityTypeHiking": "hiking",
            "HKWorkoutActivityTypeFitnessWalking": "walking",
            "HKWorkoutActivityTypeOtherActivity": "other",
        }
        return mapping.get(hk_type, "other")

    @staticmethod
    def _get_distance(
        workout: dict[str, Any],
    ) -> float | None:
        """Workoutから距離をメートル単位で取得."""
        distance = workout.get("totalDistance")
        if distance is None:
            return None
        try:
            distance_m = float(distance) * 1000  # km to m
            return distance_m if distance_m > 0 else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _get_calories(
        workout: dict[str, Any],
    ) -> float | None:
        """Workoutから消費カロリーを取得."""
        calories = workout.get("totalEnergyBurned")
        if calories is None:
            return None
        try:
            return float(calories)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _get_heart_rate(
        workout: dict[str, Any],
    ) -> int | None:
        """Workoutから平均心拍数を取得."""
        hr = workout.get("averageHeartRate")
        if hr is None:
            return None
        try:
            return int(float(hr))
        except (ValueError, TypeError):
            return None


class GoogleFitParser:
    """AndroidのGoogle Fitエクスポートデータを解析."""

    @staticmethod
    def parse_export_json(
        payload: dict[str, Any],
    ) -> list[ActivityData]:
        """Google FitのJSON形式を解析.
        
        Expected format:
        {
            "bucket": [
                {
                    "startTimeMillis": "...",
                    "endTimeMillis": "...",
                    "dataset": [
                        {
                            "point": [
                                {
                                    "value": [...]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        """
        activities = []

        buckets = payload.get("bucket", [])
        for bucket in buckets:
            try:
                start_ms = int(
                    bucket.get("startTimeMillis", 0)
                )
                end_ms = int(bucket.get("endTimeMillis", 0))
                duration_s = (end_ms - start_ms) / 1000

                if duration_s <= 0:
                    continue

                datasets = bucket.get("dataset", [])
                activity_type = "other"
                distance_m = None
                calories = None
                steps = None

                for dataset in datasets:
                    points = (
                        dataset.get("point", [])
                    )
                    for point in points:
                        values = point.get("value", [])
                        if not values:
                            continue

                        data_type = dataset.get(
                            "dataSource", {}
                        ).get("dataType", "")

                        if "activity" in data_type.lower():
                            activity_type = (
                                GoogleFitParser._map_activity_type(
                                    int(values[0].get("intVal", 0))
                                )
                            )
                        elif "distance" in data_type.lower():
                            try:
                                distance_m = float(
                                    values[0].get("fpVal", 0)
                                )
                            except (ValueError, TypeError):
                                pass
                        elif "calories" in data_type.lower():
                            try:
                                calories = float(
                                    values[0].get("fpVal", 0)
                                )
                            except (ValueError, TypeError):
                                pass
                        elif "steps" in data_type.lower():
                            try:
                                steps = int(
                                    values[0].get("intVal", 0)
                                )
                            except (ValueError, TypeError):
                                pass

                activities.append(
                    ActivityData(
                        timestamp=GoogleFitParser._ms_to_iso(
                            start_ms
                        ),
                        activity_type=activity_type,
                        duration_seconds=duration_s,
                        distance_meters=distance_m,
                        steps=steps,
                        calories=calories,
                        raw_data=bucket,
                    )
                )
            except (ValueError, TypeError, KeyError):
                continue

        return activities

    @staticmethod
    def _map_activity_type(
        google_fit_type: int,
    ) -> str:
        """Google Fitのアクティビティタイプをマッピング."""
        mapping = {
            7: "walking",
            8: "running",
            1: "cycling",
            9: "hiking",
            17: "swimming",
            0: "other",
        }
        return mapping.get(google_fit_type, "other")

    @staticmethod
    def _ms_to_iso(ms: int) -> str:
        """ミリ秒単位のUNIXタイムスタンプをISO 8601形式に変換."""
        from datetime import datetime, timezone
        return datetime.fromtimestamp(
            ms / 1000,
            tz=timezone.utc,
        ).isoformat()


class GarminParser:
    """Garminスマートウォッチのエクスポートデータを解析."""

    @staticmethod
    def parse_export_csv(
        csv_content: str,
    ) -> list[ActivityData]:
        """GarminのCSV形式（アクティビティログ）を解析.
        
        Expected format:
        Date,Type,Distance (km),Duration (h:mm:ss),Calories,...
        """
        import csv
        from io import StringIO

        activities = []

        try:
            reader = csv.DictReader(
                StringIO(csv_content)
            )
            for row in reader:
                if not row or not row.get("Type"):
                    continue

                try:
                    duration_str = row.get(
                        "Duration (h:mm:ss)",
                        "0:00:00",
                    )
                    duration_s = (
                        GarminParser._parse_duration(
                            duration_str
                        )
                    )

                    distance_str = row.get(
                        "Distance (km)",
                        "0",
                    )
                    distance_m = (
                        float(distance_str) * 1000
                        if distance_str
                        else None
                    )

                    activities.append(
                        ActivityData(
                            timestamp=row.get(
                                "Date", ""
                            ),
                            activity_type=GarminParser._map_activity_type(
                                row.get("Type", "").lower()
                            ),
                            duration_seconds=duration_s,
                            distance_meters=distance_m,
                            calories=GarminParser._safe_float(
                                row.get("Calories")
                            ),
                            raw_data=dict(row),
                        )
                    )
                except (ValueError, TypeError):
                    continue

        except Exception:
            pass

        return activities

    @staticmethod
    def _parse_duration(duration_str: str) -> float:
        """h:mm:ss形式の時間文字列を秒に変換."""
        parts = duration_str.split(":")
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        return 0.0

    @staticmethod
    def _map_activity_type(
        garmin_type: str,
    ) -> str:
        """Garminのアクティビティタイプをマッピング."""
        mapping = {
            "walking": "walking",
            "running": "running",
            "cycling": "cycling",
            "swimming": "swimming",
            "hiking": "hiking",
            "trail running": "running",
            "indoor cycling": "cycling",
        }
        return mapping.get(garmin_type, "other")

    @staticmethod
    def _safe_float(value: str | None) -> float | None:
        """文字列をfloatに安全に変換."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


def convert_device_activities_to_gps_format(
    activities: list[ActivityData],
) -> dict[str, Any]:
    """デバイスのアクティビティデータをGPS TimelineのJSON形式に変換.
    
    この形式はparse_timeline_json()で処理できます。
    """
    timeline_items = []

    for activity in activities:
        timeline_items.append(
            {
                "timestamp": activity.timestamp,
                "activityType": activity.activity_type,
                "duration": activity.duration_seconds,
                "distance": activity.distance_meters,
                "steps": activity.steps,
                "calories": activity.calories,
                "heartRate": activity.heart_rate,
                "source": "device_sync",
            }
        )

    return {
        "timelineObjects": [
            {"activity": item}
            for item in timeline_items
        ]
    }
