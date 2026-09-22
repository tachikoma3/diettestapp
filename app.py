"""Japanese Streamlit MVP for private timeline activity analysis."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.calories import add_calories
from src.distance import add_segment_distances
from src.movement import normalize_movement
from src.parser import load_timeline, parse_timeline_json, preprocess_timeline
from src.speed import add_speed_columns
from src.steps import add_steps
from src.visualization import create_map, filter_activities

st.set_page_config(page_title="Personal Activity Analyzer", page_icon="🚶", layout="wide")
st.title("Personal Activity Analyzer")
st.caption("アップロードした位置履歴を端末内で解析します。データは保存・送信されません。")


def _sample_path() -> Path:
    return Path(__file__).parent / "data" / "sample_timeline.json"


def _process(payload: object, stride: float, weight: float) -> pd.DataFrame:
    frame = preprocess_timeline(parse_timeline_json(payload))
    frame = normalize_movement(frame)
    frame = add_segment_distances(frame)
    frame = add_speed_columns(frame)
    frame = add_steps(frame, stride)
    return add_calories(frame, weight)


uploaded = st.sidebar.file_uploader("Timeline JSONを選択", type=["json"])
use_sample = st.sidebar.checkbox("サンプルデータを使う", value=uploaded is None)
stride = st.sidebar.number_input("歩幅（m）", min_value=0.3, max_value=1.5, value=0.70, step=0.01)
weight = st.sidebar.number_input("体重（kg）", min_value=20.0, max_value=200.0, value=65.0, step=0.5)

try:
    if uploaded is not None and not use_sample:
        payload = load_timeline(uploaded)
    elif use_sample:
        payload = load_timeline(_sample_path())
    else:
        st.info("JSONファイルをアップロードしてください。")
        st.stop()
    data = _process(payload, stride, weight)
except (ValueError, TypeError, json.JSONDecodeError) as error:
    st.error(f"JSONを読み込めませんでした（形式または必須項目を確認してください）: {error}")
    st.stop()

if data.empty:
    st.warning("解析できる位置情報がありません。latitude / longitude / timestamp を確認してください。")
    st.stop()

data["date"] = data["timestamp"].dt.date
available_dates = sorted(data["date"].dropna().unique())
selected_date = st.sidebar.selectbox("分析対象日", available_dates, index=len(available_dates) - 1)
period = st.sidebar.selectbox("表示期間", ["選択日のみ", "全期間"])
activities = sorted(data["activity_type"].dropna().unique().tolist())
selected = st.sidebar.multiselect("移動手段フィルター", activities, default=activities)
period_data = data if period == "全期間" else data[data["date"] == selected_date]
filtered = filter_activities(period_data, selected)

col1, col2, col3, col4 = st.columns(4)
col2.metric("歩数（推定）", f"{int(filtered['estimated_steps'].sum()):,}")
col3.metric("消費カロリー（推定）", f"{filtered['estimated_calories_kcal'].sum():,.0f} kcal")
col1.metric("総移動距離", f"{filtered['distance'].fillna(0).sum() / 1000:,.2f} km")
summary = filtered.attrs.get("speed_summary", {})
distance = filtered["distance"].fillna(0).clip(lower=0).sum()
duration = filtered["duration"].fillna(0).clip(lower=0).sum()
average_kmh = (distance / duration * 3.6) if duration else 0.0
col4.metric("平均速度", f"{average_kmh:.2f} km/h")

st.subheader("Today's Activity Map")
st.pydeck_chart(create_map(filtered), use_container_width=True)
st.subheader("Movement Summary")
st.write(
    f"対象: {selected_date} / 表示: {period} / "
    f"総移動時間: {duration / 60:.1f} 分 / "
    f"観測速度の単純平均: {summary.get('observed_arithmetic_mean_mps', 0) * 3.6:.2f} km/h"
)
st.subheader("Daily Statistics")
st.dataframe(
    pd.DataFrame(
        [{"date": selected_date, "distance_km": distance / 1000,
          "estimated_steps": int(filtered["estimated_steps"].sum()),
          "estimated_calories_kcal": filtered["estimated_calories_kcal"].sum(),
          "average_speed_kmh": average_kmh}]
    ),
    use_container_width=True,
    hide_index=True,
)
st.subheader("Detailed Location Data")
st.dataframe(filtered, use_container_width=True, hide_index=True)
st.download_button(
    "CSVをダウンロード",
    data=filtered.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"activity_{selected_date}.csv",
    mime="text/csv",
)
st.caption("推定値は歩幅・体重・METに基づく目安です。医療や運動指導の用途には利用しないでください。")
st.caption("カロリー計算: MET × 3.5 × 体重(kg) ÷ 200 × 時間(分)。歩数は徒歩距離 ÷ 歩幅です。")
