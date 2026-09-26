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
from src.device_sync import (
    DeviceParserFactory,
    convert_device_activities_to_gps_format,
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
    "Google Maps Timeline、iPhone HealthKit（JSON/XML）、Android Google Fit、"
    "Garminウォッチから運動量データを分析し、"
    "Azure OpenAIで活動内容を要約します。"
)

st.caption(
    "個人データはセッション内で処理し、"
    "GitHubへ保存しません。"
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


# ========== サイドバー設定 ==========
with st.sidebar:
    st.header("📁 入力と設定")

    # データソース選択
    data_source = st.radio(
        "データソースを選択",
        [
            "Google Maps Timeline",
            "iPhone HealthKit",
            "Android Google Fit",
            "Garmin",
            "サンプルデータ",
        ],
        index=0,
    )

    uploaded_file = None
    use_sample = False

    if data_source == "サンプルデータ":
        use_sample = True
    else:
        if data_source == "Google Maps Timeline":
            uploaded_file = st.file_uploader(
                "Timeline JSONをアップロード",
                type=["json", "txt"],
            )
        elif data_source == "iPhone HealthKit":
            uploaded_file = st.file_uploader(
                "HealthKit JSON/XMLをアップロード",
                type=["json", "xml", "txt" ],
                key="healthkit_upload",
            )
        elif data_source == "Android Google Fit":
            uploaded_file = st.file_uploader(
                "Google Fit JSONをアップロード",
                type=["json", "txt"],
                key="googlefit_upload",
            )
        elif data_source == "Garmin":
            uploaded_file = st.file_uploader(
                "Garmin CSVをアップロード",
                type=["csv", "txt"],
                key="garmin_upload",
            )

    st.divider()

    st.subheader("⚙️ 個人設定")

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



# ========== データ読み込み処理 ==========

if uploaded_file is None and not use_sample:
    st.info(
        f"📤 {data_source} のファイルをアップロードするか、"
        "サンプルデータを選択してください。"
    )
    st.stop()


try:
    if use_sample:
        # --------------------------------------------------
        # サンプルデータを読み込む
        # --------------------------------------------------
        payload = load_sample_data()
        parsed_data = parse_timeline_json(payload)

    elif data_source == "Google Maps Timeline":
        # --------------------------------------------------
        # Google Maps Timeline
        #
        # JSON / TXT に対応。
        # TXTでも中身がJSON形式なら自動的にJSONとして解析する。
        # --------------------------------------------------
        file_content = uploaded_file.read().decode("utf-8")

        try:
            # JSONとして解析
            payload = json.loads(file_content)

        except json.JSONDecodeError:
            # JSONとして解析できない場合は
            # テキストとしてそのまま渡す
            payload = file_content

        parsed_data = parse_timeline_json(payload)

    elif data_source == "iPhone HealthKit":
        # --------------------------------------------------
        # Apple Health / HealthKit
        #
        # export.xml に対応。
        #
        # Apple HealthのエクスポートデータはXML形式のため、
        # JSONとして解析せず、そのままHealthKitパーサーへ渡す。
        #
        # TXTとして保存されたXMLデータにも対応するため、
        # 拡張子ではなくファイル内容をそのまま読み込む。
        # --------------------------------------------------
        file_content = uploaded_file.read()

        parser = DeviceParserFactory.get_parser("healthkit")

        # HealthKit XMLを解析
        activities = parser.parse_export(file_content)

        # アプリ内部で使用するGPS形式へ変換
        converted = convert_device_activities_to_gps_format(
            activities
        )

        # 共通データ形式へ変換
        parsed_data = parse_timeline_json(converted)

    elif data_source == "Android Google Fit":
        # --------------------------------------------------
        # Android Google Fit
        #
        # JSON / TXT に対応。
        # --------------------------------------------------
        file_content = uploaded_file.read().decode("utf-8")

        try:
            # JSONとして解析
            payload = json.loads(file_content)

        except json.JSONDecodeError:
            # JSONではない場合はテキストとして保持
            payload = file_content

        parser = DeviceParserFactory.get_parser("googlefit")

        activities = parser.parse_export(payload)

        converted = convert_device_activities_to_gps_format(
            activities
        )

        parsed_data = parse_timeline_json(converted)

    elif data_source == "Garmin":
        # --------------------------------------------------
        # Garmin
        #
        # CSV / TXT に対応。
        # --------------------------------------------------
        file_content = uploaded_file.read().decode("utf-8")

        parser = DeviceParserFactory.get_parser("garmin")

        activities = parser.parse_export(file_content)

        converted = convert_device_activities_to_gps_format(
            activities
        )

        parsed_data = parse_timeline_json(converted)


except (
    json.JSONDecodeError,
    UnicodeDecodeError,
    TypeError,
    ValueError,
    FileNotFoundError,
) as error:

    # --------------------------------------------------
    # ファイル読み込みエラー
    # --------------------------------------------------
    st.error(
        f"❌ {data_source} の読み込みに失敗しました。"
        "ファイル形式を確認してください。"
    )

    st.code(str(error))
    st.stop()


# ========== GPSデータ準備 ==========

data = prepare_gps_data(parsed_data)


# ========== データ存在チェック ==========

if data.empty:
    st.warning(
        "⚠️ 解析できるデータがありません。"
        "必須項目を含むファイルを選択してください。"
    )
    st.stop()


# ========== 利用可能な日付を取得 ==========

available_dates = sorted(
    data["date"].dropna().unique()
)


# ========== 分析対象日を選択 ==========

selected_date = st.selectbox(
    "分析対象日",
    available_dates,
    format_func=str,
)


# ========== 選択日のデータを抽出 ==========

day_data = data[
    data["date"] == selected_date
].copy()


# ========== 1日のデータを分析 ==========

summary = analyze_day(
    day_data,
    stride_m=stride_m,
    weight_kg=weight_kg,
)



# ========== KPI表示 ==========
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
    "ℹ️ 歩数・カロリー・速度はデバイスまたはGPSから算出した推定値です。"
    "実測値や医療情報ではありません。"
)


# ========== グラフ・詳細表示 ==========
left, right = st.columns([1, 2])

with left:
    st.subheader("🚗 移動手段別集計")
    st.dataframe(
        summary["mode_summary"],
        use_container_width=True,
        hide_index=True,
    )

    st.write(
        "📍 単純平均速度: "
        f"{summary['simple_average_speed_kmh']:.2f} km/h"
    )

    st.write(
        "⏱️ 総距離 ÷ 総移動時間: "
        f"{summary['average_speed_kmh']:.2f} km/h"
    )


with right:
    st.subheader("🗺️ 移動軌跡マップ")

    from src.visualization import create_map

    st.pydeck_chart(
        create_map(day_data),
        use_container_width=True,
    )


# ========== 詳細データ ==========
st.subheader("📋 詳細データ")

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
    file_name=f"activity_{selected_date}.csv",
    mime="text/csv",
)


# ========== AI活動分析 ==========
st.subheader("🤖 AI活動分析（Azure OpenAI）")

st.write(
    "GPS座標やデバイス生データではなく、"
    "距離・時間・速度・移動手段などの"
    "**集計値のみ** をAzure OpenAIへ送信します。"
)

if st.button("🚀 AI活動分析を実行", type="primary"):
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
            "❌ Azure OpenAIの利用に失敗しました。"
            "Secretsの設定を確認してください。"
        )
        st.code(str(error))


# ========== 注意事項 ==========
with st.expander("ℹ️ 注意事項・推定値について"):
    st.markdown(
        """
        ### データソースについて
        - **Google Maps Timeline**: GPS座標から算出
        - **iPhone HealthKit**: Workoutデータから算出（JSON/XML両対応）
        - **Android Google Fit**: Fitアクティビティから算出
        - **Garmin**: スマートウォッチセンサーから算出

        ### 推定値について
        - 推定歩数は歩行距離 ÷ 歩幅で算出しています
        - 推定消費カロリーはMETs、体重、時間から算出しています
        - 推定値は参考情報であり、実測値ではありません
        - 医療診断や健康状態の判定には使用しません

        ### プライバシー
        - アップロードしたデータはセッション内で処理されます
        - GitHubリポジトリには保存されません
        - APIキーはソースコードに書かず、Streamlit Secretsで管理してください

        ### 対応フォーマット
        - **Google Maps Timeline**: JSON形式
        - **iPhone HealthKit**: JSON形式またはXML形式（自動判別）
        - **Android Google Fit**: Google FitエクスポートJSON
        - **Garmin**: CSVエクスポート（列名の順序や言語は自動検出）
        """
    )
