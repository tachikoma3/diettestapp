import pandas as pd

from src.distance import add_segment_distances, haversine_distance


def test_haversine_one_degree_latitude():
    assert 111_000 < haversine_distance(0, 0, 1, 0) < 112_000


def test_segment_distances_are_non_destructive():
    frame = pd.DataFrame({"latitude": [0, 1], "longitude": [0, 0], "distance": [None, None]})
    result = add_segment_distances(frame)
    assert result.loc[1, "calculated_distance"] > 111_000
    assert frame["distance"].isna().all()
