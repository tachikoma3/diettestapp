import pandas as pd
import pytest

from src.calories import add_calories, estimate_calories


def test_met_calorie_formula():
    assert estimate_calories(3.5, 60, 60) == pytest.approx(3.675)


def test_calorie_enrichment_does_not_change_input():
    frame = pd.DataFrame({"activity_type": ["walking"], "duration": [600]})
    result = add_calories(frame, 60)
    assert result.loc[0, "estimated_calories_kcal"] > 0
    assert "estimated_calories_kcal" not in frame
