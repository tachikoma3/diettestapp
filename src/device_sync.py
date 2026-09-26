"""iPhone、Android、スマートウォッチから運動量データを取得."""

from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from typing import Any
from xml.etree import ElementTree as ET


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


class BaseDeviceParser(ABC):
    """全デバイスパーサーの基底クラス."""

    @staticmethod
    def _safe_float(value: str | float | None) -> float | None:
        """値をfloatに安全に変換."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_int(value: str | int | None) -> int | None:
        """値をintに安全に変換."""
        if value is None or value == "":
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _ms_to_iso(ms: int | str) -> str:
        """ミリ秒単位のUNIXタイムスタンプをISO 8601形式に変換."""
        try:
            return datetime.fromtimestamp(
                int(ms) / 1000,
                tz=timezone.utc,
            ).isoformat()
        except (ValueError, TypeError, OSError):
            return ""

    @abstractmethod
    def parse_export(self, payload: Any) -> list[ActivityData]:
        """エクスポートデータを解析（実装必須）."""
        pass


class HealthKitParser(BaseDeviceParser):
    """iPhoneのHealthKitエクスポートデータを解析（XML/JSON両対応）."""

    HEALTHKIT_ACTIVITY_MAPPING = {
        "HKWorkoutActivityTypeWalking": "walking",
        "HKWorkoutActivityTypeRunning": "running",
        "HKWorkoutActivityTypeCycling": "cycling",
        "HKWorkoutActivityTypeSwimming": "swimming",
        "HKWorkoutActivityTypeHiking": "hiking",
        "HKWorkoutActivityTypeFitnessWalking": "walking",
        "HKWorkoutActivityTypeOtherActivity": "other",
        "HKWorkoutActivityTypeTrailRunning": "running",
    }

    UNIT_MAPPING = {
        "km": 1000,
        "m": 1,
        "mi": 1609.34,
        "kcal": 1,
        "cal": 0.001,
        "min": 60,
        "h": 3600,
        "count": 1,
    }

    def parse_export(self, payload: Any) -> list[ActivityData]:
        """HealthKit XML/JSONを自動判別して解析."""
        if isinstance(payload, str):
            return self._parse_xml(payload)
        if isinstance(payload, dict):
            return self._parse_json(payload)
        return []

    def _parse_xml(self, xml_content: str) -> list[ActivityData]:
        """HealthKit XML形式を解析."""
        activities = []

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return activities

        for workout_elem in root.findall(".//Workout"):
            try:
                activity = self._parse_workout_element(workout_elem)
                if activity:
                    activities.append(activity)
            except Exception:
                continue

        return activities

    def _parse_json(self, payload: dict[str, Any]) -> list[ActivityData]:
        """HealthKit JSON形式を解析."""
        activities = []
        data = payload.get("data", {})
        workouts = data.get("HKWorkoutTypeIdentifier", [])

        for workout in workouts:
            try:
                activity = self._parse_workout_dict(workout)
                if activity:
                    activities.append(activity)
            except Exception:
                continue

        return activities

    def _parse_workout_element(self, elem: ET.Element) -> ActivityData | None:
        """XMLのWorkoutエレメントを解析."""
        try:
            timestamp = elem.get("startDate") or elem.get("creationDate") or ""
            hk_type = elem.get("workoutActivityType", "")
            activity_type = self.HEALTHKIT_ACTIVITY_MAPPING.get(
                hk_type, "other"
            )

            duration_str = elem.get("duration", "0")
            duration_unit = elem.get("durationUnit", "s").lower()
            duration_s = self._convert_time_to_seconds(
                float(duration_str or 0), duration_unit
            )

            distance_m = self._parse_distance_from_xml(elem)
            calories = self._parse_calories_from_xml(elem)
            heart_rate = (
                self._safe_int(elem.get("averageHeartRate"))
                if elem.get("averageHeartRate")
                else None
            )

            return ActivityData(
                timestamp=timestamp,
                activity_type=activity_type,
                duration_seconds=duration_s,
                distance_meters=distance_m,
                calories=calories,
                heart_rate=heart_rate,
                raw_data={k: v for k, v in elem.attrib.items()},
            )
        except (ValueError, TypeError, KeyError):
            return None

    def _parse_workout_dict(self, workout: dict[str, Any]) -> ActivityData | None:
        """JSONのワークアウトデータを解析."""
        try:
            timestamp = workout.get(
                "startDate", workout.get("creationDate", "")
            )
            hk_type = workout.get("workoutActivityType", "")
            activity_type = self.HEALTHKIT_ACTIVITY_MAPPING.get(
                hk_type, "other"
            )

            duration_s = self._safe_float(
                workout.get("duration") or 0
            ) or 0.0

            distance_km = self._safe_float(workout.get("totalDistance"))
            distance_m = (
                distance_km * 1000 if distance_km and distance_km > 0
                else None
            )

            calories = self._safe_float(workout.get("totalEnergyBurned"))
            heart_rate = self._safe_int(workout.get("averageHeartRate"))

            return ActivityData(
                timestamp=timestamp,
                activity_type=activity_type,
                duration_seconds=duration_s,
                distance_meters=distance_m,
                calories=calories,
                heart_rate=heart_rate,
                raw_data=workout,
            )
        except (ValueError, TypeError, KeyError):
            return None

    def _parse_distance_from_xml(self, elem: ET.Element) -> float | None:
        """XML Workoutエレメントから距離を抽出."""
        distance_str = elem.get("totalDistance")
        if distance_str is None:
            return None

        try:
            distance_value = float(distance_str)
            distance_unit = elem.get("totalDistanceUnit", "km").lower()
            multiplier = self.UNIT_MAPPING.get(distance_unit, 1000)
            distance_m = distance_value * multiplier
            return distance_m if distance_m > 0 else None
        except (ValueError, TypeError):
            return None

    def _parse_calories_from_xml(self, elem: ET.Element) -> float | None:
        """XML Workoutエレメントからカロリーを抽出."""
        calories_str = elem.get("totalEnergyBurned")
        if calories_str is None:
            return None

        try:
            calories_value = float(calories_str)
            calories_unit = elem.get("totalEnergyBurnedUnit", "kcal").lower()
            if calories_unit == "cal":
                calories_value *= 0.001
            return calories_value if calories_value > 0 else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _convert_time_to_seconds(value: float, unit: str) -> float:
        """時間値を秒に変換."""
        unit_map = {
            "s": 1,
            "sec": 1,
            "m": 60,
            "min": 60,
            "h": 3600,
            "hour": 3600,
        }
        multiplier = unit_map.get(unit.lower(), 1)
        return value * multiplier


class GoogleFitParser(BaseDeviceParser):
    """AndroidのGoogle Fitエクスポートデータを解析."""

    GOOGLEFIT_ACTIVITY_MAPPING = {
        7: "walking",
        8: "running",
        1: "cycling",
        9: "hiking",
        17: "swimming",
        0: "other",
    }

    def parse_export(self, payload: dict[str, Any]) -> list[ActivityData]:
        """Google FitのJSON形式を解析."""
        activities = []
        buckets = payload.get("bucket", [])

        for bucket in buckets:
            try:
                activity = self._parse_bucket(bucket)
                if activity:
                    activities.append(activity)
            except Exception:
                continue

        return activities

    def _parse_bucket(self, bucket: dict[str, Any]) -> ActivityData | None:
        """バケットデータを解析."""
        try:
            start_ms = int(bucket.get("startTimeMillis", 0))
            end_ms = int(bucket.get("endTimeMillis", 0))
            duration_s = (end_ms - start_ms) / 1000

            if duration_s <= 0:
                return None

            parsed_data = {
                "activity_type": "other",
                "distance_meters": None,
                "calories": None,
                "steps": None,
            }

            datasets = bucket.get("dataset", [])
            for dataset in datasets:
                self._parse_dataset(dataset, parsed_data)

            return ActivityData(
                timestamp=self._ms_to_iso(start_ms),
                activity_type=parsed_data["activity_type"],
                duration_seconds=duration_s,
                distance_meters=parsed_data["distance_meters"],
                steps=parsed_data["steps"],
                calories=parsed_data["calories"],
                raw_data=bucket,
            )
        except (ValueError, TypeError, KeyError):
            return None

    def _parse_dataset(
        self,
        dataset: dict[str, Any],
        parsed_data: dict[str, Any],
    ) -> None:
        """個別のデータセットを解析."""
        data_type = dataset.get("dataSource", {}).get(
            "dataType", ""
        ).lower()
        points = dataset.get("point", [])

        for point in points:
            values = point.get("value", [])
            if not values:
                continue

            if "activity" in data_type:
                try:
                    activity_id = int(values[0].get("intVal", 0))
                    parsed_data["activity_type"] = (
                        self.GOOGLEFIT_ACTIVITY_MAPPING.get(
                            activity_id, "other"
                        )
                    )
                except (ValueError, TypeError, IndexError):
                    pass

            elif "distance" in data_type:
                try:
                    parsed_data["distance_meters"] = float(
                        values[0].get("fpVal", 0)
                    )
                except (ValueError, TypeError, IndexError):
                    pass

            elif "calories" in data_type:
                try:
                    parsed_data["calories"] = float(
                        values[0].get("fpVal", 0)
                    )
                except (ValueError, TypeError, IndexError):
                    pass

            elif "steps" in data_type:
                try:
                    parsed_data["steps"] = int(
                        values[0].get("intVal", 0)
                    )
                except (ValueError, TypeError, IndexError):
                    pass


class GarminParser(BaseDeviceParser):
    """Garminスマートウォッチのエクスポートデータを解析."""

    GARMIN_ACTIVITY_MAPPING = {
        "walking": "walking",
        "running": "running",
        "cycling": "cycling",
        "swimming": "swimming",
        "hiking": "hiking",
        "trail running": "running",
        "indoor cycling": "cycling",
    }

    HEADER_VARIANTS = {
        "date": ["Date", "date", "日付"],
        "type": ["Type", "type", "活動種別"],
        "distance": ["Distance (km)", "distance", "距離（km）"],
        "duration": ["Duration (h:mm:ss)", "duration", "時間"],
        "calories": ["Calories", "calories", "カロリー"],
    }

    def parse_export(self, csv_content: str) -> list[ActivityData]:
        """GarminのCSV形式を解析."""
        activities = []

        try:
            reader = csv.DictReader(StringIO(csv_content))
            headers = reader.fieldnames or []
            header_map = self._detect_headers(headers)

            for row in reader:
                if not row or not row.get(header_map.get("type")):
                    continue

                try:
                    activity = self._parse_row(row, header_map)
                    if activity:
                        activities.append(activity)
                except Exception:
                    continue

        except Exception:
            pass

        return activities

    def _detect_headers(
        self, headers: list[str]
    ) -> dict[str, str]:
        """CSVヘッダーを自動検出."""
        header_map = {}

        for field, variants in self.HEADER_VARIANTS.items():
            for header in headers:
                if header in variants or any(
                    v.lower() == header.lower() for v in variants
                ):
                    header_map[field] = header
                    break

        return header_map

    def _parse_row(
        self,
        row: dict[str, str],
        header_map: dict[str, str],
    ) -> ActivityData | None:
        """CSVの1行を解析."""
        try:
            duration_s = self._parse_duration(
                row.get(
                    header_map.get("duration", "Duration (h:mm:ss)"),
                    "0:00:00",
                )
            )

            distance_km = self._safe_float(
                row.get(header_map.get("distance", "Distance (km)"))
            )
            distance_m = (
                distance_km * 1000 if distance_km and distance_km > 0
                else None
            )

            activity_type_str = row.get(
                header_map.get("type", "Type"), ""
            ).lower()

            return ActivityData(
                timestamp=row.get(header_map.get("date", "Date"), ""),
                activity_type=self.GARMIN_ACTIVITY_MAPPING.get(
                    activity_type_str, "other"
                ),
                duration_seconds=duration_s,
                distance_meters=distance_m,
                calories=self._safe_float(
                    row.get(header_map.get("calories", "Calories"))
                ),
                raw_data=dict(row),
            )
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_duration(duration_str: str) -> float:
        """h:mm:ss形式の時間文字列を秒に変換."""
        try:
            parts = duration_str.split(":")
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                return float(hours * 3600 + minutes * 60 + seconds)
            return 0.0
        except (ValueError, TypeError, IndexError):
            return 0.0


class DeviceParserFactory:
    """デバイスパーサーを生成するファクトリー."""

    _parsers: dict[str, type[BaseDeviceParser]] = {
        "healthkit": HealthKitParser,
        "googlefit": GoogleFitParser,
        "garmin": GarminParser,
    }

    @classmethod
    def get_parser(cls, device_type: str) -> BaseDeviceParser:
        """指定デバイスのパーサーを取得."""
        parser_class = cls._parsers.get(device_type.lower())
        if parser_class is None:
            raise ValueError(f"Unknown device type: {device_type}")
        return parser_class()


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
