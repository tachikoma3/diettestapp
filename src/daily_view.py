"""HealthKit の日別集計をStreamlitで表示する.

src/daily_view.py として配置する想定。
GPS(座標)が無いデータ向けの画面で、地図は出さない。
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st

from src.daily_ai import generate_daily_summary, summarize_daily_for_ai

_MAX_AI_CALLS_PER_SESSION = 5
_SECRET_KEYS = (
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
)

_LABELS = {
    "steps": "歩数",
    "distance_km": "距離 (km)",
    "active_kcal": "活動エネルギー (kcal)",
    "flights": "上った階数",
    "walking_speed_kmh": "歩行速度 (km/h)",
    "step_length_cm": "歩幅 (cm)",
    "exercise_min": "運動時間 (分)",
    "stand_hours": "スタンド (時間)",
}


def _read_secrets() -> dict[str, str]:
    """Streamlit Secrets から Azure OpenAI の設定を読む(無ければ空)."""
    values: dict[str, str] = {}
    try:
        for key in _SECRET_KEYS:
            if key in st.secrets:
                values[key] = st.secrets[key]
    except Exception:  # secrets.toml が無い場合など
        return {}
    return values


def _render_ai_section(
    frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> None:
    """選択期間の集計値をAzure OpenAIで要約する."""
    st.subheader("🤖 AI活動分析(Azure OpenAI)")
    st.write(
        "日別の生データやデバイス名は送らず、選択期間の"
        "**集計値のみ** をAzure OpenAIへ送信します。"
    )

    ai_input = summarize_daily_for_ai(frame, start, end)
    with st.expander("送信される内容を確認"):
        st.json(ai_input)

    calls = st.session_state.get("daily_ai_calls", 0)
    if st.button(
        "🚀 AI活動分析を実行",
        type="primary",
        disabled=calls >= _MAX_AI_CALLS_PER_SESSION,
    ):
        st.session_state["daily_ai_calls"] = calls + 1
        with st.spinner("Azure OpenAIで要約しています..."):
            try:
                text = generate_daily_summary(ai_input, _read_secrets())
                st.session_state["daily_ai_result"] = {
                    "period": (str(start.date()), str(end.date())),
                    "text": text,
                }
            except RuntimeError as error:
                st.session_state.pop("daily_ai_result", None)
                st.error(f"❌ {error}")

    if calls >= _MAX_AI_CALLS_PER_SESSION:
        st.info("このセッションでのAI分析の回数上限に達しました。")

    # 再実行(期間変更など)で結果が消えないよう session_state に保持する
    result = st.session_state.get("daily_ai_result")
    if result:
        if result["period"] == (str(start.date()), str(end.date())):
            st.markdown(result["text"])
        else:
            st.caption(
                "表示中の要約は別の期間のものです。"
                "この期間を分析するにはボタンを押してください。"
            )


def render_daily_dashboard(daily: pd.DataFrame) -> None:
    """日別DataFrame(healthkit_daily.COLUMNS)から画面を描画する."""
    if daily.empty:
        st.warning("⚠️ 日別に集計できるデータがありません。")
        return

    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    for column in _LABELS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    last_day = frame["date"].max().date()
    first_day = frame["date"].min().date()
    default_start = max(first_day, last_day - timedelta(days=89))

    picked = st.date_input(
        "表示期間",
        value=(default_start, last_day),
        min_value=first_day,
        max_value=last_day,
    )
    if not isinstance(picked, tuple) or len(picked) != 2:
        st.info("期間の開始日と終了日を選んでください。")
        return

    start, end = picked
    period = frame[
        (frame["date"] >= pd.Timestamp(start))
        & (frame["date"] <= pd.Timestamp(end))
    ].set_index("date")

    st.subheader(f"📊 {start} 〜 {end}")

    with_steps = period["steps"].dropna()
    columns = st.columns(4)
    columns[0].metric(
        "平均歩数 / 日",
        f"{with_steps.mean():,.0f} 歩" if len(with_steps) else "—",
    )
    columns[1].metric("合計距離", f"{period['distance_km'].sum():,.1f} km")
    columns[2].metric(
        "平均活動エネルギー / 日",
        f"{period['active_kcal'].mean():,.0f} kcal"
        if period["active_kcal"].notna().any()
        else "—",
    )
    columns[3].metric("記録のある日数", f"{len(with_steps)} 日")

    st.caption(
        "ℹ️ iPhone・Apple Watch・他アプリの記録が重なる日は、"
        "合計値が最大のソースを採用しています(二重計上を避ける近似)。"
        "記録の無い日は欠損として扱い、0歩とは区別しています。"
    )

    st.subheader("👣 歩数の推移")
    chart = pd.DataFrame(
        {
            "歩数": period["steps"],
            "7日移動平均": period["steps"].rolling(7, min_periods=3).mean(),
        }
    )
    st.line_chart(chart)

    st.subheader("🔥 活動エネルギーと距離")
    left, right = st.columns(2)
    left.line_chart(period[["active_kcal"]].rename(columns=_LABELS))
    right.line_chart(period[["distance_km"]].rename(columns=_LABELS))

    st.subheader("🗓️ 月別平均")
    monthly = (
        period[["steps", "distance_km", "active_kcal", "exercise_min"]]
        .resample("MS")
        .mean()
        .round(1)
        .rename(columns=_LABELS)
    )
    monthly.index = monthly.index.strftime("%Y-%m")
    st.dataframe(monthly)

    st.subheader("📋 日別データ")
    table = period.reset_index().rename(columns=_LABELS)
    table["date"] = table["date"].dt.date
    st.dataframe(table, hide_index=True)

    st.download_button(
        "📥 CSVをダウンロード",
        data=table.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"health_daily_{start}_{end}.csv",
        mime="text/csv",
    )

    _render_ai_section(frame, pd.Timestamp(start), pd.Timestamp(end))
