import pandas as pd

from src.parser import NORMALIZED_COLUMNS, parse_timeline_json, preprocess_timeline


def test_parser_handles_nested_google_style_and_e7_coordinates():
    data = {"timelineObjects": [{"activitySegment": {
        "startTime": "2026-01-01T00:00:00Z",
        "endTime": "2026-01-01T00:01:00Z",
        "activityType": "WALKING",
        "startLocation": {"latitudeE7": 350000000, "longitudeE7": 1350000000},
    }}]}
    frame = parse_timeline_json(data)
    assert list(frame.columns) == NORMALIZED_COLUMNS
    assert frame.iloc[0].latitude == 35
    assert frame.iloc[0].duration == 60


def test_parser_empty_and_preprocessing_are_safe_and_non_destructive():
    frame = parse_timeline_json({"unexpected": [{"value": 1}]})
    assert frame.empty
    original = pd.DataFrame({"timestamp": ["2026-01-01"], "latitude": [35], "longitude": [135]})
    processed = preprocess_timeline(original)
    assert "quality_flags" in processed
    assert list(original.columns) == ["timestamp", "latitude", "longitude"]
