"""Streamlit front end for the Personal Activity Analyzer."""

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

st.set_page_config(
    page_title="Diet Test App | Activity Analyzer",
    page_icon="🚶",
    layout="wide",
    initial_sidebar_state="expanded",
)


CUSTOM_CSS = """
<style>
    .hero {
        padding: 2.5rem 2.75rem;
        border-radius: 1.25rem;
        background: linear-gradient(135deg, #163b35 0%, #2f7662 100%);
        color: white;
        margin-bottom: 1.5rem;
    }
    .hero h1 { margin: 0; font-size: 2.6rem; }
    .hero p { margin: .65rem 0 0; color: #e1f3ec; font-size: 1.05rem; }
    .eyebrow { text-transform: uppercase; letter-spacing: .16em; font-size: .75rem; font-weight: 700; color: #8dd4b9; }
    [data-testid="stMetric"] { border: 1px solid #dce9e3; border-radius: .8rem; padding: .8rem; background: #fbfdfc; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def _sample_path() -> Path:
    return Path(__file__).parent / "data" / "sample_timeline.json"


def _process(payload: object, stride: float, weight: float) -> pd.DataFrame:
    frame = preprocess_timeline(parse_timeline_json(payload))
    frame = normalize_movement(frame)
    frame = add_segment_distances(frame)
    frame = add_speed_columns(frame)
    frame = add_steps(frame, stride)
    return add_calories(frame, weight)


def render_home() -> None:
    st.markdown(
        """
        <div class="hero">
          <div class="eyebrow">Diet Test App / Personal Health</div>
          <h1>Personal Activity Analyzer</h1>
          <p>Google Maps TimelineのJSONから、歩数・距離・速度・消費カロリーを見える化します。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.subheader("自分の活動を、ひとつの画面で確認")
    st.write(
        "Timeline JSONは外部サービスへ送信せず、このStreamlitセッション内で解析します。"
        "左のメニューからActivity Analyzerを開き、ファイルをアップロードしてください。"
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("解析対象", "Timeline JSON")
    col2.metric("主な指標", "4項目")
    col3.metric("地図表示", "PyDeck")
    st.info("まずはサンプルデータで画面を確認できます。実データはGitHubへ保存しないでください。")


def render_about() -> None:
    st.markdown('<div class="eyebrow">About</div>', unsafe_allow_html=True)
    st.title("このアプリについて")
    st.write(
        "Personal Activity Analyzerは、ユーザー自身がエクスポートした位置履歴を"
        "ローカルまたはStreamlit Community Cloud上で解析するMVPです。"
    )
    st.subheader("プライバシー")
    st.write(
        "アップロードしたTimelineはGitHubや外部APIへ保存・送信しません。"
        "ただし、公開URLで運用する場合はアクセス制御やデータ保持方針を確認してください。"
    )
    st.subheader("推定値について")
    st.write("歩数・カロリー・速度はGPS、歩幅、体重、METに基づく推定値です。医療用途には使用しないでください。")


def render_analyzer() -> None:
    st.markdown('<div class="eyebrow">Activity</div>', unsafe_allow_html=True)
    st.title("Activity Analyzer")
    st.caption("Timeline JSONをアップロードして、活動量と移動軌跡を確認します。")

    uploaded = st.sidebar.file_uploader("Timeline JSONを選択", type=["json"])
    use_sample = st.sidebar.checkbox("サンプルデータを使う", value=uploaded is None)

    try:
        if uploaded is not None and not use_sample:
            payload = load_timeline(uploaded)
        elif use_sample:
            payload = load_timeline(_sample_path())
        else:
            st.info("JSONファイルをアップロードしてください。")
            return
        data = _process(payload, stride=st.sidebar.number_input("歩幅（m）", min_value=0.3, max_value=1.5, value=0.70, step=0.01), weight=st.sidebar.number_input("体重（kg）", min_value=20.0, max_value=200.0, value=65.0, step=0.5))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        st.error(f"JSONを読み込めませんでした（形式または必須項目を確認してください）: {error}")
        return

    if data.empty:
        st.warning("解析できる位置情報がありません。latitude / longitude / timestampを確認してください。")
        return

    data["date"] = data["timestamp"].dt.date
    available_dates = sorted(data["date"].dropna().unique())
    if not available_dates:
        st.warning("日付情報が見つからないため、分析対象日を選べません。Timeline JSONの時刻データを確認してください。")
        return

    selected_date = st.sidebar.selectbox("分析対象日", available_dates, index=len(available_dates) - 1)
    period = st.sidebar.selectbox("表示期間", ["選択日のみ", "全期間"])
    activities = sorted(data["activity_type"].dropna().unique().tolist())
    if not activities:
        st.warning("移動手段の情報が見つからないため、フィルターを適用できません。")
        return

    selected = st.sidebar.multiselect("移動手段フィルター", activities, default=activities)
    period_data = data if period == "全期間" else data[data["date"] == selected_date]
    filtered = filter_activities(period_data, selected)
    if filtered.empty:
        st.warning("選択した条件に合うデータがありません。フィルター条件を変えてください。")
        return

    distance = filtered["distance"].fillna(0).clip(lower=0).sum()
    duration = filtered["duration"].fillna(0).clip(lower=0).sum()
    average_kmh = (distance / duration * 3.6) if duration else 0.0
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("総移動距離", f"{distance / 1000:,.2f} km")
    col2.metric("歩数（推定）", f"{int(filtered['estimated_steps'].sum()):,}")
    col3.metric("消費カロリー（推定）", f"{filtered['estimated_calories_kcal'].sum():,.0f} kcal")
    col4.metric("平均速度", f"{average_kmh:.2f} km/h")

    st.subheader("Movement Map")
    st.pydeck_chart(create_map(filtered), use_container_width=True)
    st.subheader("Activity Summary")
    st.write(f"対象: {selected_date} / 表示: {period} / 総移動時間: {duration / 60:.1f} 分")
    st.dataframe(
        pd.DataFrame([{
            "date": selected_date,
            "distance_km": distance / 1000,
            "estimated_steps": int(filtered["estimated_steps"].sum()),
            "estimated_calories_kcal": filtered["estimated_calories_kcal"].sum(),
            "average_speed_kmh": average_kmh,
        }]),
        use_container_width=True,
        hide_index=True,
    )
    with st.expander("Detailed Location Data"):
        st.dataframe(filtered, use_container_width=True, hide_index=True)
    st.download_button(
        "CSVをダウンロード",
        data=filtered.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"activity_{selected_date}.csv",
        mime="text/csv",
    )
    st.caption("推定値は歩幅・体重・METに基づく目安です。医療や運動指導の用途には利用しないでください。")


with st.sidebar:
    st.markdown("## Diet Test App")
    page = st.radio("MENU", ["HOME", "ACTIVITY ANALYZER", "ABOUT"], index=0)
    st.divider()

if page == "HOME":
    render_home()
elif page == "ACTIVITY ANALYZER":
    render_analyzer()
else:
    render_about()
