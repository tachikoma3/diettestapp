import pandas as pd
import pytest

from src.steps import estimate_steps, steps_from_distance


def test_steps_from_walking_distance_and_stride():
    frame = pd.DataFrame({"activity_type": ["walking", "driving"], "distance": [700, 1000]})
    assert estimate_steps(frame, 0.7) == 1000
    assert steps_from_distance(100, 0.5) == 200


def test_stride_must_be_positive():
    with pytest.raises(ValueError):
        steps_from_distance(10, 0)
