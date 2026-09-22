"""PyDeckによる移動軌跡表示."""

from __future__ import annotations

import pandas as pd
import pydeck as pdk


COLORS = {
    "walking": [30, 150, 80],
    "running": [220, 80, 80],
    "cycling": [240, 160, 30],
    "driving": [70, 100, 220],
    "transit": [150, 70, 180],
    "still": [120, 120, 120],
    "unknown": [40, 140, 180],
}


def create_map(
    frame: pd.DataFrame,
    zoom: float = 11,
) -> pdk.Deck:
    """地点と移動手段別の経路を地図に表示する."""
    visible = frame.dropna(
        subset=["latitude", "longitude"]
    ).copy()

    if visible.empty:
        return pdk.Deck(
            layers=[],
            initial_view_state=pdk.ViewState(
                latitude=35.0,
                longitude=139.0,
                zoom=zoom,
            ),
        )

    visible["movement_mode"] = (
        visible["activity_type"]
        .fillna("unknown")
        .astype(str)
    )

    path_records = []

    for mode, group in visible.groupby(
        "movement_mode",
        sort=False,
    ):
        if len(group) > 1:
            path_records.append(
                {
                    "movement_mode": mode,
                    "path": group[
                        ["longitude", "latitude"]
                    ].values.tolist(),
                    "color": COLORS.get(
                        mode,
                        COLORS["unknown"],
                    ),
                }
            )

    point_layer = pdk.Layer(
        "ScatterplotLayer",
        data=visible,
        get_position="[longitude, latitude]",
        get_radius=35,
        get_fill_color="[40, 140, 220, 180]",
        pickable=True,
    )

    layers = [point_layer]

    if path_records:
        path_layer = pdk.Layer(
            "PathLayer",
            data=path_records,
            get_path="path",
            get_color="color",
            get_width=5,
            width_min_pixels=2,
            pickable=True,
        )
        layers.insert(0, path_layer)

    return pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=float(visible["latitude"].mean()),
            longitude=float(visible["longitude"].mean()),
            zoom=zoom,
        ),
        tooltip={
            "html": (
                "<b>{movement_mode}</b>"
                "<br/>{timestamp}"
            ),
        },
        map_style=None,
    )
