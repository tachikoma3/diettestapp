"""PyDeck visualizations for the timeline map."""

from __future__ import annotations

import pandas as pd
import pydeck as pdk


def create_map(frame: pd.DataFrame, zoom: float = 11) -> pdk.Deck:
    visible = frame.dropna(subset=["latitude", "longitude"]).copy()
    if visible.empty:
        visible = pd.DataFrame({"latitude": [35.1234], "longitude": [139.5678], "activity_type": ["データなし"]})
    points = pdk.Layer(
        "ScatterplotLayer",
        data=visible,
        get_position="[longitude, latitude]",
        get_radius=35,
        get_fill_color="[40, 120, 220, 180]",
        pickable=True,
        auto_highlight=True,
    )
    path_data = (
        visible.sort_values("timestamp")
        .groupby("activity_type", dropna=False, sort=False)
        .apply(
            lambda group: {
                "activity_type": group["activity_type"].iloc[0],
                "path": group[["longitude", "latitude"]].values.tolist(),
            },
            include_groups=False,
        )
        .tolist()
    )
    paths = pdk.Layer(
        "PathLayer",
        data=path_data,
        get_path="path",
        get_width=5,
        get_color="[40, 120, 220, 190]",
        width_min_pixels=2,
        pickable=True,
    )
    view_state = pdk.ViewState(
        latitude=float(visible["latitude"].mean()),
        longitude=float(visible["longitude"].mean()),
        zoom=zoom,
        pitch=0,
    )
    return pdk.Deck(
        layers=[paths, points],
        initial_view_state=view_state,
        tooltip={"html": "<b>{activity_type}</b><br/>時刻: {timestamp}", "style": {"backgroundColor": "#222"}},
        map_style=None,
    )


def filter_activities(frame: pd.DataFrame, activities: list[str]) -> pd.DataFrame:
    if not activities or "activity_type" not in frame:
        return frame.copy(deep=True)
    return frame[frame["activity_type"].isin(activities)].copy()
