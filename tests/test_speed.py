import pandas as pd

from src.speed import add_speed_columns, average_speeds, calculate_speed


def test_speed_and_distinct_average_definitions():
    assert calculate_speed(100, 10) == 10
    summary = average_speeds(pd.DataFrame({
        "distance": [100, 900], "duration": [10, 90], "speed": [8, 12]
    }))
    assert summary["distance_weighted_average_mps"] == 10
    assert summary["observed_arithmetic_mean_mps"] == 10
    assert "calculated_speed" in add_speed_columns(pd.DataFrame({"distance": [100], "duration": [10]}))
