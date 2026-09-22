"""GPS Activity AnalyzerのStreamlit画面."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from src.activity_analyzer import analyze_day
from src.ai_analyzer import (
    generate_activity_summary,
    summarize_for_ai,
)
from src.gps_processor import prepare_gps_data
from src.parser import parse_timeline_json


st.set_page_config(
    page_title="GPS Activity Analyzer",
    page_icon="🗺️",
    layout="wide",
)

st.title("🗺️ GPS Activity Analyzer")
st.write(
    "Google Maps TimelineをPythonで分析し、"
    "Azure OpenAIで活動内容を要約します。"
)

st.caption(
    "個人GPSデータはセッション内で処理し、"
    "GitHubへ保存しません。"
)


with st.sidebar:
    st.header("入力と設定")

    uploaded_file = st.file_uploader(
        "Timeline JSONをアップロード",
        type=["json"],
    )

    use_sample = st.checkbox(
        "架空のサンプルデータを使う",
        value=uploaded_file is None,
    )

    stride_m = st.number_input(
        "歩幅（m）",
        min_value=0.30,
        max_value=1.50,
        value=0.70,
        step=0.01,
    )

    weight_kg = st.number_input(
        "体重（kg）",
        min_value=20.0,
        max_value=200.0,
        value=65.0,
        step=0.5,
    )


def load_sample_data():
    """架空サンプルJSONを読み込む."""
    path = (
        Path(__file__).parent
        / "data"
        / "sample_timeline.json"
    )

    if not path.exists():
        raise FileNotFoundError(
            "data/sample_timeline.jsonが見つかりません。"
        )

    return json.loads(
        path.read_text(encoding="utf-8")
    )


if uploaded_file is None and not use_sample:
    st.info(
        "JSONをアップロードするか、"
        "サンプルデータを選択してください。"
    )
    st.stop()


try:
    if use_sample:
        payload = load_sample_data()
    else:
        payload = uploaded_file.read()

    parsed_data = parse_timeline_json(payload)

except (
    json.JSONDecodeError,
    UnicodeDecodeError,
    TypeError,
    ValueError,
    FileNotFoundError,
) as error:
    st.error(
        "JSONの読み込みに失敗しました。"
        "Google Maps TimelineのJSON形式を確認してください。"
    )
    st.code(str(error))
    st.stop()


data = prepare_gps_data(parsed_data)

if data.empty:
    st.warning(
        "解析できるGPSデータがありません。"
        "日時・緯度・経度を含むJSONを選択してください。"
    )
    st.stop()


available_dates = sorted(
    data["date"].dropna().unique()
)

selected_date = st.selectbox(
    "分析対象日",
    available_dates,
    format_func=str,
)

day_data = data[
    data["date"] == selected_date
].copy()

summary = analyze_day(
    day_data,
    stride_m=stride_m,
    weight_kg=weight_kg,
)


st.subheader(f"📊 {selected_date} のKPI")

columns = st.columns(5)

columns[0].metric(
    "推定歩数",
    f"{summary['estimated_steps']:,.0f} 歩",
)

columns[1].metric(
    "総移動距離",
    f"{summary['total_distance_km']:.2f} km",
)

columns[2].metric(
    "平均移動速度",
    f"{summary['average_speed_kmh']:.2f} km/h",
)

columns[3].metric(
    "推定消費カロリー",
    f"{summary['estimated_calories_kcal']:.0f} kcal",
)

columns[4].metric(
    "移動時間",
    f"{summary['moving_minutes']:.1f} 分",
)

st.caption(
    "歩数・カロリー・速度はGPSから算出した推定値です。"
    "実測値や医療情報ではありません。"
)


left, right = st.columns([1, 2])

with left:
    st.subheader("移動手段別集計")
    st.dataframe(
        summary["mode_summary"],
        use_container_width=True,
        hide_index=True,
    )

    st.write(
        "単純平均速度: "
        f"{summary['simple_average_speed_kmh']:.2f} km/h"
    )

    st.write(
        "総距離 ÷ 総移動時間: "
        f"{summary['average_speed_kmh']:.2f} km/h"
    )


with right:
    st.subheader("移動軌跡マップ")

    from src.visualization import create_map

    st.pydeck_chart(
        create_map(day_data),
        use_container_width=True,
    )


st.subheader("詳細データ")

display_columns = [
    "timestamp",
    "latitude",
    "longitude",
    "distance_m",
    "speed_kmh",
    "activity_type",
    "duration_s",
]

display_data = day_data[
    [
        column
        for column in display_columns
        if column in day_data.columns
    ]
]

st.dataframe(
    display_data,
    use_container_width=True,
    hide_index=True,
)


csv_data = display_data.to_csv(
    index=False
).encode("utf-8-sig")

st.download_button(
    "📥 CSVをダウンロード",
    data=csv_data,
    file_name=f"gps_activity_{selected_date}.csv",
    mime="text/csv",
)


st.subheader("🤖 AI活動分析（Azure OpenAI）")

st.write(
    "GPS座標そのものではなく、"
    "距離・時間・速度・移動手段などの"
    "集計値だけをAzure OpenAIへ送信します。"
)

if st.button("AI活動分析を実行", type="primary"):
    try:
        secret_values = {
            key: st.secrets[key]
            for key in [
                "AZURE_OPENAI_API_KEY",
                "AZURE_OPENAI_ENDPOINT",
                "AZURE_OPENAI_DEPLOYMENT",
                "AZURE_OPENAI_API_VERSION",
            ]
            if key in st.secrets
        }

        ai_summary = summarize_for_ai(
            day_data,
            summary,
        )

        result = generate_activity_summary(
            ai_summary,
            secret_values,
        )

        st.markdown(result)

    except Exception as error:
        st.error(
            "Azure OpenAIの利用に失敗しました。"
            "Secretsの設定を確認してください。"
        )
        st.code(str(error))


with st.expander("注意事項・推定値について"):
    st.markdown(
        """
        - 推定歩数は歩行距離 ÷ 歩幅で算出しています。
        - 推定消費カロリーはMETs、体重、時間から算出しています。
        - 推定値は参考情報であり、実測値ではありません。
        - 医療診断や健康状態の判定には使用しません。
        - APIキーはソースコードに書かず、Streamlit Secretsで管理してください。
        """
    )
