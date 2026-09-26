"""iPhone、Android、スマートウォッチから運動量データを取得."""

from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from typing import Any
from xml.etree import ElementTree as ET


# ============================================================
# 共通データモデル
# ============================================================

@dataclass
class ActivityData:
    """各デバイスから取得した共通の運動量データ."""

    timestamp: str
    activity_type: str
    duration_seconds: float

    # GPS情報
    latitude: float | None = None
    longitude: float | None = None

    # 運動量データ
    distance_meters: float | None = None
    steps: int | None = None
    calories: float | None = None
    heart_rate: int | None = None

    # 元データ
    raw_data: dict[str, Any] | None = None


# ============================================================
# 基底Parser
# ============================================================

class BaseDeviceParser(ABC):
    """全デバイスParserの基底クラス."""

    @staticmethod
    def _safe_float(
        value: str | float | int | None,
    ) -> float | None:
        """値をfloatに安全に変換."""

        if value is None or value == "":
            return None

        try:
            return float(value)

        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_int(
        value: str | int | float | None,
    ) -> int | None:
        """値をintに安全に変換."""

        if value is None or value == "":
            return None

        try:
            return int(float(value))

        except (ValueError, TypeError):
            return None

    @staticmethod
    def _ms_to_iso(
        ms: int | str,
    ) -> str:
        """ミリ秒UNIXタイムスタンプをISO 8601へ変換."""

        try:
            return datetime.fromtimestamp(
                int(ms) / 1000,
                tz=timezone.utc,
            ).isoformat()

        except (
            ValueError,
            TypeError,
            OSError,
        ):
            return ""

    @abstractmethod
    def parse_export(
        self,
        payload: Any,
    ) -> list[ActivityData]:
        """エクスポートデータを解析."""

        raise NotImplementedError


# ============================================================
# Apple Health / HealthKit
# ============================================================

class HealthKitParser(BaseDeviceParser):
    """iPhone HealthKitエクスポートデータを解析."""

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

    def parse_export(
        self,
        payload: Any,
    ) -> list[ActivityData]:
        """
        HealthKit XML / JSONを自動判別して解析.

        Streamlitのuploaded_file.read()はbytesを返すため、
        bytesにも対応する。
        """

        if isinstance(payload, bytes):

            try:
                payload = payload.decode(
                    "utf-8-sig"
                )

            except UnicodeDecodeError:

                payload = payload.decode(
                    "utf-8",
                    errors="replace",
                )

        if isinstance(payload, str):

            content = payload.lstrip()

            # JSONの場合
            if (
                content.startswith("{")
                or content.startswith("[")
            ):
                try:
                    return self._parse_json(
                        json.loads(content)
                    )

                except json.JSONDecodeError:
                    pass

            # Apple Health標準のexport.xml
            return self._parse_xml(
                content
            )

        if isinstance(payload, dict):

            return self._parse_json(
                payload
            )

        return []

    # --------------------------------------------------------
    # XML
    # --------------------------------------------------------

    def _parse_xml(
        self,
        xml_content: str,
    ) -> list[ActivityData]:
        """Apple Health export.xmlを解析."""

        activities: list[ActivityData] = []

        try:

            root = ET.fromstring(
                xml_content
            )

        except ET.ParseError:

            return activities

        # ----------------------------------------------------
        # Workout
        # ----------------------------------------------------

        for workout_elem in root.findall(
            ".//Workout"
        ):

            try:

                activity = (
                    self._parse_workout_element(
                        workout_elem
                    )
                )

                if activity:
                    activities.append(
                        activity
                    )

            except Exception:
                continue

        # ----------------------------------------------------
        # HealthKit Record
        #
        # 歩数・距離・心拍数・消費カロリーなど
        # ----------------------------------------------------

        for record_elem in root.findall(
            ".//Record"
        ):

            try:

                activity = (
                    self._parse_record_element(
                        record_elem
                    )
                )

                if activity:
                    activities.append(
                        activity
                    )

            except Exception:
                continue

        return activities

    # --------------------------------------------------------
    # Workout
    # --------------------------------------------------------

    def _parse_workout_element(
        self,
        elem: ET.Element,
    ) -> ActivityData | None:
        """XMLのWorkoutを解析."""

        try:

            timestamp = (
                elem.get("startDate")
                or elem.get("creationDate")
                or ""
            )

            hk_type = elem.get(
                "workoutActivityType",
                "",
            )

            activity_type = (
                self.HEALTHKIT_ACTIVITY_MAPPING.get(
                    hk_type,
                    "other",
                )
            )

            duration_str = elem.get(
                "duration",
                "0",
            )

            duration_unit = elem.get(
                "durationUnit",
                "s",
            ).lower()

            duration_s = (
                self._convert_time_to_seconds(
                    float(
                        duration_str or 0
                    ),
                    duration_unit,
                )
            )

            distance_m = (
                self._parse_distance_from_xml(
                    elem
                )
            )

            calories = (
                self._parse_calories_from_xml(
                    elem
                )
            )

            heart_rate = (
                self._safe_int(
                    elem.get(
                        "averageHeartRate"
                    )
                )
            )

            return ActivityData(
                timestamp=timestamp,
                activity_type=activity_type,
                duration_seconds=duration_s,
                distance_meters=distance_m,
                calories=calories,
                heart_rate=heart_rate,
                raw_data={
                    key: value
                    for key, value
                    in elem.attrib.items()
                },
            )

        except (
            ValueError,
            TypeError,
            KeyError,
        ):

            return None

    # --------------------------------------------------------
    # HealthKit Record
    # --------------------------------------------------------

    def _parse_record_element(
        self,
        elem: ET.Element,
    ) -> ActivityData | None:
        """Apple HealthのRecordを解析."""

        record_type = elem.get(
            "type",
            "",
        )

        timestamp = (
            elem.get("startDate")
            or elem.get("creationDate")
            or ""
        )

        value = self._safe_float(
            elem.get("value")
        )

        if value is None:
            return None

        unit = (
            elem.get("unit")
            or ""
        ).lower()

        # --------------------------------------------
        # 歩数
        # --------------------------------------------

        if record_type == (
            "HKQuantityTypeIdentifierStepCount"
        ):

            return ActivityData(
                timestamp=timestamp,
                activity_type="walking",
                duration_seconds=(
                    self._calculate_duration(
                        elem.get("startDate"),
                        elem.get("endDate"),
                    )
                ),
                steps=int(value),
                raw_data=dict(
                    elem.attrib
                ),
            )

        # --------------------------------------------
        # 歩行・ランニング距離
        # --------------------------------------------

        if record_type == (
            "HKQuantityTypeIdentifierDistanceWalkingRunning"
        ):

            distance_m = (
                self._convert_distance(
                    value,
                    unit,
                )
            )

            return ActivityData(
                timestamp=timestamp,
                activity_type="walking",
                duration_seconds=(
                    self._calculate_duration(
                        elem.get("startDate"),
                        elem.get("endDate"),
                    )
                ),
                distance_meters=distance_m,
                raw_data=dict(
                    elem.attrib
                ),
            )

        # --------------------------------------------
        # 心拍数
        # --------------------------------------------

        if record_type == (
            "HKQuantityTypeIdentifierHeartRate"
        ):

            return ActivityData(
                timestamp=timestamp,
                activity_type="heart_rate",
                duration_seconds=(
                    self._calculate_duration(
                        elem.get("startDate"),
                        elem.get("endDate"),
                    )
                ),
                heart_rate=int(value),
                raw_data=dict(
                    elem.attrib
                ),
            )

        # --------------------------------------------
        # アクティブエネルギー
        # --------------------------------------------

        if record_type == (
            "HKQuantityTypeIdentifierActiveEnergyBurned"
        ):

            calories = value

            if unit in (
                "cal",
                "calorie",
                "calories",
            ):
                calories *= 0.001

            return ActivityData(
                timestamp=timestamp,
                activity_type="active_energy",
                duration_seconds=(
                    self._calculate_duration(
                        elem.get("startDate"),
                        elem.get("endDate"),
                    )
                ),
                calories=calories,
                raw_data=dict(
                    elem.attrib
                ),
            )

        return None

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    def _parse_json(
        self,
        payload: dict[str, Any],
    ) -> list[ActivityData]:
        """HealthKit JSONを解析."""

        activities: list[ActivityData] = []

        data = payload.get(
            "data",
            {},
        )

        workouts = data.get(
            "HKWorkoutTypeIdentifier",
            [],
        )

        for workout in workouts:

            try:

                activity = (
                    self._parse_workout_dict(
                        workout
                    )
                )

                if activity:
                    activities.append(
                        activity
                    )

            except Exception:
                continue

        return activities

    def _parse_workout_dict(
        self,
        workout: dict[str, Any],
    ) -> ActivityData | None:
        """JSONのWorkoutを解析."""

        try:

            timestamp = workout.get(
                "startDate",
                workout.get(
                    "creationDate",
                    "",
                ),
            )

            hk_type = workout.get(
                "workoutActivityType",
                "",
            )

            activity_type = (
                self.HEALTHKIT_ACTIVITY_MAPPING.get(
                    hk_type,
                    "other",
                )
            )

            duration_s = (
                self._safe_float(
                    workout.get(
                        "duration"
                    )
                )
                or 0.0
            )

            distance_km = (
                self._safe_float(
                    workout.get(
                        "totalDistance"
                    )
                )
            )

            distance_m = (
                distance_km * 1000
                if distance_km
                and distance_km > 0
                else None
            )

            calories = (
                self._safe_float(
                    workout.get(
                        "totalEnergyBurned"
                    )
                )
            )

            heart_rate = (
                self._safe_int(
                    workout.get(
                        "averageHeartRate"
                    )
                )
            )

            return ActivityData(
                timestamp=timestamp,
                activity_type=activity_type,
                duration_seconds=duration_s,
                distance_meters=distance_m,
                calories=calories,
                heart_rate=heart_rate,
                raw_data=workout,
            )

        except (
            ValueError,
            TypeError,
            KeyError,
        ):

            return None

    # --------------------------------------------------------
    # 補助処理
    # --------------------------------------------------------

    def _parse_distance_from_xml(
        self,
        elem: ET.Element,
    ) -> float | None:
        """Workoutから距離を取得."""

        distance_str = elem.get(
            "totalDistance"
        )

        if distance_str is None:
            return None

        try:

            distance_value = float(
                distance_str
            )

            distance_unit = elem.get(
                "totalDistanceUnit",
                "km",
            ).lower()

            multiplier = (
                self.UNIT_MAPPING.get(
                    distance_unit,
                    1000,
                )
            )

            distance_m = (
                distance_value
                * multiplier
            )

            return (
                distance_m
                if distance_m > 0
                else None
            )

        except (
            ValueError,
            TypeError,
        ):

            return None

    def _parse_calories_from_xml(
        self,
        elem: ET.Element,
    ) -> float | None:
        """Workoutから消費カロリーを取得."""

        calories_str = elem.get(
            "totalEnergyBurned"
        )

        if calories_str is None:
            return None

        try:

            calories_value = float(
                calories_str
            )

            calories_unit = elem.get(
                "totalEnergyBurnedUnit",
                "kcal",
            ).lower()

            if calories_unit == "cal":
                calories_value *= 0.001

            return (
                calories_value
                if calories_value > 0
                else None
            )

        except (
            ValueError,
            TypeError,
        ):

            return None

    @staticmethod
    def _convert_time_to_seconds(
        value: float,
        unit: str,
    ) -> float:
        """時間を秒へ変換."""

        unit_map = {
            "s": 1,
            "sec": 1,
            "m": 60,
            "min": 60,
            "h": 3600,
            "hour": 3600,
        }

        return value * unit_map.get(
            unit.lower(),
            1,
        )

    @staticmethod
    def _convert_distance(
        value: float,
        unit: str,
    ) -> float:
        """距離をメートルへ変換."""

        unit = unit.lower()

        if unit == "km":
            return value * 1000

        if unit == "mi":
            return value * 1609.34

        if unit == "m":
            return value

        return value

    @staticmethod
    def _calculate_duration(
        start_date: str | None,
        end_date: str | None,
    ) -> float:

        if not start_date or not end_date:
            return 0.0

        try:

            start = datetime.fromisoformat(
                start_date.replace(
                    "Z",
                    "+00:00",
                )
            )

            end = datetime.fromisoformat(
                end_date.replace(
                    "Z",
                    "+00:00",
                )
            )

            return max(
                0.0,
                (
                    end - start
                ).total_seconds(),
            )

        except (
            ValueError,
            TypeError,
        ):

            return 0.0


# ============================================================
# Google Fit
# ============================================================

class GoogleFitParser(BaseDeviceParser):
    """Android Google Fitエクスポートデータを解析."""

    GOOGLEFIT_ACTIVITY_MAPPING = {
        7: "walking",
        8: "running",
        1: "cycling",
        9: "hiking",
        17: "swimming",
        0: "other",
    }

    def parse_export(
        self,
        payload: Any,
    ) -> list[ActivityData]:
        """Google Fit JSONを解析."""

        if isinstance(payload, bytes):

            payload = payload.decode(
                "utf-8-sig"
            )

        if isinstance(payload, str):

            try:
                payload = json.loads(
                    payload
                )

            except json.JSONDecodeError:
                return []

        if not isinstance(
            payload,
            dict,
        ):
            return []

        activities = []

        buckets = payload.get(
            "bucket",
            [],
        )

        for bucket in buckets:

            try:

                activity = (
                    self._parse_bucket(
                        bucket
                    )
                )

                if activity:
                    activities.append(
                        activity
                    )

            except Exception:
                continue

        return activities

    def _parse_bucket(
        self,
        bucket: dict[str, Any],
    ) -> ActivityData | None:
        """Google Fitのバケットを解析."""

        try:

            start_ms = int(
                bucket.get(
                    "startTimeMillis",
                    0,
                )
            )

            end_ms = int(
                bucket.get(
                    "endTimeMillis",
                    0,
                )
            )

            duration_s = (
                end_ms - start_ms
            ) / 1000

            if duration_s <= 0:
                return None

            parsed_data = {
                "activity_type": "other",
                "distance_meters": None,
                "calories": None,
                "steps": None,
            }

            datasets = bucket.get(
                "dataset",
                [],
            )

            for dataset in datasets:

                self._parse_dataset(
                    dataset,
                    parsed_data,
                )

            return ActivityData(
                timestamp=self._ms_to_iso(
                    start_ms
                ),
                activity_type=(
                    parsed_data[
                        "activity_type"
                    ]
                ),
                duration_seconds=duration_s,
                distance_meters=(
                    parsed_data[
                        "distance_meters"
                    ]
                ),
                steps=(
                    parsed_data["steps"]
                ),
                calories=(
                    parsed_data["calories"]
                ),
                raw_data=bucket,
            )

        except (
            ValueError,
            TypeError,
            KeyError,
        ):

            return None

    def _parse_dataset(
        self,
        dataset: dict[str, Any],
        parsed_data: dict[str, Any],
    ) -> None:
        """Google Fitデータセットを解析."""

        data_source = dataset.get(
            "dataSource",
            {},
        )

        data_type = data_source.get(
            "dataType",
            "",
        ).lower()

        points = dataset.get(
            "point",
            [],
        )

        for point in points:

            values = point.get(
                "value",
                [],
            )

            if not values:
                continue

            value = values[0]

            if "activity" in data_type:

                try:

                    activity_id = int(
                        value.get(
                            "intVal",
                            0,
                        )
                    )

                    parsed_data[
                        "activity_type"
                    ] = (
                        self.GOOGLEFIT_ACTIVITY_MAPPING.get(
                            activity_id,
                            "other",
                        )
                    )

                except (
                    ValueError,
                    TypeError,
                    IndexError,
                ):
                    pass

            elif "distance" in data_type:

                try:

                    parsed_data[
                        "distance_meters"
                    ] = float(
                        value.get(
                            "fpVal",
                            0,
                        )
                    )

                except (
                    ValueError,
                    TypeError,
                    IndexError,
                ):
                    pass

            elif "calories" in data_type:

                try:

                    parsed_data[
                        "calories"
                    ] = float(
                        value.get(
                            "fpVal",
                            0,
                        )
                    )

                except (
                    ValueError,
                    TypeError,
                    IndexError,
                ):
                    pass

            elif "steps" in data_type:

                try:

                    parsed_data[
                        "steps"
                    ] = int(
                        value.get(
                            "intVal",
                            0,
                        )
                    )

                except (
                    ValueError,
                    TypeError,
                    IndexError,
                ):
                    pass


# ============================================================
# Garmin
# ============================================================

class GarminParser(BaseDeviceParser):
    """GarminスマートウォッチのCSVデータを解析."""

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
        "date": [
            "Date",
            "date",
            "日付",
        ],
        "type": [
            "Type",
            "type",
            "活動種別",
        ],
        "distance": [
            "Distance (km)",
            "distance",
            "距離（km）",
        ],
        "duration": [
            "Duration (h:mm:ss)",
            "duration",
            "時間",
        ],
        "calories": [
            "Calories",
            "calories",
            "カロリー",
        ],
        "latitude": [
            "Latitude",
            "latitude",
            "lat",
            "緯度",
        ],
        "longitude": [
            "Longitude",
            "longitude",
            "lon",
            "lng",
            "経度",
        ],
        "steps": [
            "Steps",
            "steps",
            "step_count",
            "歩数",
        ],
        "heart_rate": [
            "Heart Rate",
            "heart_rate",
            "HeartRate",
            "HR",
            "心拍数",
        ],
    }

    def parse_export(
        self,
        csv_content: str | bytes,
    ) -> list[ActivityData]:
        """Garmin CSVを解析."""

        if isinstance(
            csv_content,
            bytes,
        ):

            csv_content = (
                csv_content.decode(
                    "utf-8-sig"
                )
            )

        activities = []

        try:

            reader = csv.DictReader(
                StringIO(
                    csv_content
                )
            )

            headers = (
                reader.fieldnames
                or []
            )

            header_map = (
                self._detect_headers(
                    headers
                )
            )

            for row in reader:

                if not row:
                    continue

                if not row.get(
                    header_map.get(
                        "type",
                        "Type",
                    )
                ):
                    continue

                try:

                    activity = (
                        self._parse_row(
                            row,
                            header_map,
                        )
                    )

                    if activity:
                        activities.append(
                            activity
                        )

                except Exception:
                    continue

        except Exception:
            pass

        return activities

    def _detect_headers(
        self,
        headers: list[str],
    ) -> dict[str, str]:
        """CSVヘッダーを自動検出."""

        header_map = {}

        for field, variants in (
            self.HEADER_VARIANTS.items()
        ):

            for header in headers:

                if header in variants:

                    header_map[
                        field
                    ] = header

                    break

                if any(
                    variant.lower()
                    == header.lower()
                    for variant
                    in variants
                ):

                    header_map[
                        field
                    ] = header

                    break

        return header_map

    def _parse_row(
        self,
        row: dict[str, str],
        header_map: dict[str, str],
    ) -> ActivityData | None:
        """Garmin CSVの1行を解析."""

        try:

            duration_s = (
                self._parse_duration(
                    row.get(
                        header_map.get(
                            "duration",
                            "Duration (h:mm:ss)",
                        ),
                        "0:00:00",
                    )
                )
            )

            distance_km = (
                self._safe_float(
                    row.get(
                        header_map.get(
                            "distance",
                            "Distance (km)",
                        )
                    )
                )
            )

            distance_m = (
                distance_km * 1000
                if distance_km
                and distance_km > 0
                else None
            )

            activity_type_str = (
                row.get(
                    header_map.get(
                        "type",
                        "Type",
                    ),
                    "",
                )
                .lower()
                .strip()
            )

            latitude = (
                self._safe_float(
                    row.get(
                        header_map.get(
                            "latitude",
                            "Latitude",
                        )
                    )
                )
            )

            longitude = (
                self._safe_float(
                    row.get(
                        header_map.get(
                            "longitude",
                            "Longitude",
                        )
                    )
                )
            )

            steps = (
                self._safe_int(
                    row.get(
                        header_map.get(
                            "steps",
                            "Steps",
                        )
                    )
                )
            )

            heart_rate = (
                self._safe_int(
                    row.get(
                        header_map.get(
                            "heart_rate",
                            "Heart Rate",
                        )
                    )
                )
            )

            timestamp = row.get(
                header_map.get(
                    "date",
                    "Date",
                ),
                "",
            )

            return ActivityData(
                timestamp=timestamp,
                activity_type=(
                    self.GARMIN_ACTIVITY_MAPPING.get(
                        activity_type_str,
                        "other",
                    )
                ),
                duration_seconds=duration_s,
                latitude=latitude,
                longitude=longitude,
                distance_meters=distance_m,
                steps=steps,
                heart_rate=heart_rate,
                calories=self._safe_float(
                    row.get(
                        header_map.get(
                            "calories",
                            "Calories",
                        )
                    )
                ),
                raw_data=dict(row),
            )

        except (
            ValueError,
            TypeError,
        ):

            return None

    @staticmethod
    def _parse_duration(
        duration_str: str,
    ) -> float:
        """h:mm:ss形式を秒へ変換."""

        try:

            parts = duration_str.split(
                ":"
            )

            if len(parts) == 3:

                hours = int(
                    parts[0]
                )

                minutes = int(
                    parts[1]
                )

                seconds = int(
                    parts[2]
                )

                return float(
                    hours * 3600
                    + minutes * 60
                    + seconds
                )

            return 0.0

        except (
            ValueError,
            TypeError,
            IndexError,
        ):

            return 0.0


# ============================================================
# Parser Factory
# ============================================================

class DeviceParserFactory:
    """デバイスParserを生成するFactory."""

    _parsers: dict[
        str,
        type[BaseDeviceParser],
    ] = {
        "healthkit": HealthKitParser,
        "googlefit": GoogleFitParser,
        "garmin": GarminParser,
    }

    @classmethod
    def get_parser(
        cls,
        device_type: str,
    ) -> BaseDeviceParser:
        """指定されたデバイスのParserを取得."""

        parser_class = cls._parsers.get(
            device_type.lower()
        )

        if parser_class is None:

            raise ValueError(
                f"Unknown device type: {device_type}"
            )

        return parser_class()


# ============================================================
# 共通データ変換
# ============================================================

def convert_device_activities_to_gps_format(
    activities: list[ActivityData],
) -> dict[str, Any]:
    """
    各デバイスのActivityDataを、
    既存のparse_timeline_json()で処理できる
    Google Maps Timeline互換形式へ変換する。

    GPS座標を持っているデータはlatitude / longitudeを保持する。

    GPS座標を持たないデータはNoneのままにする。
    架空のGPS座標は生成しない。
    """

    timeline_items = []

    for activity in activities:

        # ----------------------------------------------------
        # 共通形式へ変換
        # ----------------------------------------------------

        item = {
            "timestamp": activity.timestamp,
            "activityType": activity.activity_type,
            "duration": activity.duration_seconds,
            "distance": activity.distance_meters,
            "steps": activity.steps,
            "calories": activity.calories,
            "heartRate": activity.heart_rate,
            "source": "device_sync",
        }

        # ----------------------------------------------------
        # GPS座標が存在する場合のみ追加
        # ----------------------------------------------------

        if (
            activity.latitude
            is not None
            and activity.longitude
            is not None
        ):

            item["latitude"] = (
                activity.latitude
            )

            item["longitude"] = (
                activity.longitude
            )

        # ----------------------------------------------------
        # 元データが存在する場合
        # ----------------------------------------------------

        if activity.raw_data:

            item["rawData"] = (
                activity.raw_data
            )

        timeline_items.append(
            {
                "activity": item
            }
        )

    return {
        "timelineObjects": timeline_items
    }

