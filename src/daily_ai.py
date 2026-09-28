"""HealthKit 日別集計をAzure OpenAIで要約する.

src/daily_ai.py として配置する想定。

- 送るのは選択期間の「集計値のみ」。日別の生データ、デバイス名、
  ソース名は送らない。
- 既存の Streamlit Secrets(AZURE_OPENAI_*)をそのまま使う。
- 標準の requests だけで呼ぶので、追加パッケージは不要。
- エラー文にはエンドポイントやAPIキーを含めない。
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import requests

_REQUIRED_KEYS = (
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT",
)
_DEFAULT_API_VERSION = "2024-10-21"
_WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

_SYSTEM_PROMPT = (
    "あなたは日々の活動量データを分かりやすく要約するアシスタントです。"
    "与えられるのはスマートフォン・ウォッチの記録から集計した数値だけです。"
    "数値は機器の推定を含み、記録のない日は欠損です(0ではありません)。"
    "医療的な診断・治療・健康状態の判定はしないでください。"
    "データにない事実を作らず、断定しすぎず、簡潔な日本語で答えてください。"
)

_USER_TEMPLATE = """次の集計値から、この期間の活動内容を要約してください。

{payload}

次の形式で、全体で400〜600字程度にまとめてください。
1. 概要(2〜3文)
2. 傾向と気づき(箇条書き3点まで。前の期間との比較、曜日差、月ごとの変化など)
3. 無理のない範囲での提案(1〜2点)
4. データについての注意(記録の欠けなど、あれば1文)
"""


def _clean(value: Any, digits: int = 1):
    """NaN を None にし、丸めた数値を返す."""
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def _period_stats(df: pd.DataFrame) -> dict[str, Any]:
    steps = df["steps"].dropna()
    stats: dict[str, Any] = {
        "days_with_data": int(len(steps)),
        "steps_mean": _clean(steps.mean(), 0) if len(steps) else None,
        "steps_median": _clean(steps.median(), 0) if len(steps) else None,
        "distance_km_total": _clean(df["distance_km"].sum()),
        "active_kcal_mean": _clean(df["active_kcal"].mean(), 0),
    }
    # 運動時間・スタンド時間は、全日0ならデータ未取得の可能性が高いので送らない
    for column in ("exercise_min", "stand_hours"):
        if df[column].fillna(0).sum() > 0:
            stats[f"{column}_mean"] = _clean(df[column].mean())
    return stats


def summarize_daily_for_ai(
    frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> dict[str, Any]:
    """AIへ送る集計値(dict)を作る. frame は数値化済みの日別DataFrame."""
    data = frame.copy()
    data["date"] = pd.to_datetime(data["date"])

    days = (end - start).days + 1
    period = data[(data["date"] >= start) & (data["date"] <= end)]

    prev_end = start - pd.Timedelta(days=1)
    prev_start = prev_end - pd.Timedelta(days=days - 1)
    previous = data[(data["date"] >= prev_start) & (data["date"] <= prev_end)]

    summary: dict[str, Any] = {
        "period": f"{start.date()} 〜 {end.date()}",
        "days_in_period": days,
        "missing_days": days - int(period["steps"].notna().sum()),
        "current": _period_stats(period),
    }

    steps = period.dropna(subset=["steps"])
    if not steps.empty:
        best = steps.loc[steps["steps"].idxmax()]
        worst = steps.loc[steps["steps"].idxmin()]
        summary["best_day"] = {
            "date": str(best["date"].date()),
            "steps": _clean(best["steps"], 0),
        }
        summary["lowest_day"] = {
            "date": str(worst["date"].date()),
            "steps": _clean(worst["steps"], 0),
        }

        by_weekday = steps.groupby(steps["date"].dt.dayofweek)["steps"].mean()
        summary["steps_mean_by_weekday"] = {
            _WEEKDAYS[int(i)]: _clean(v, 0) for i, v in by_weekday.items()
        }

        by_month = steps.groupby(steps["date"].dt.strftime("%Y-%m"))["steps"].mean()
        summary["steps_mean_by_month"] = {
            month: _clean(v, 0) for month, v in by_month.tail(6).items()
        }

    if previous["steps"].notna().any():
        prev_stats = _period_stats(previous)
        summary["previous_period"] = prev_stats
        current_mean = summary["current"]["steps_mean"]
        prev_mean = prev_stats["steps_mean"]
        if current_mean is not None and prev_mean:
            summary["steps_mean_change_pct"] = _clean(
                (current_mean - prev_mean) / prev_mean * 100
            )

    return summary


def _error_message(response: requests.Response) -> str:
    """APIのエラー本文から、キーやURLを含まない短い説明を作る."""
    detail = ""
    try:
        detail = str(response.json().get("error", {}).get("message", ""))
    except ValueError:
        pass
    detail = detail.replace("\n", " ")[:200]
    return f"Azure OpenAIがエラーを返しました(HTTP {response.status_code})。{detail}"


def generate_daily_summary(
    summary: dict[str, Any], secrets: dict[str, str], *, timeout: int = 60
) -> str:
    """集計値をAzure OpenAIへ送り、要約テキストを返す."""
    missing = [key for key in _REQUIRED_KEYS if not secrets.get(key)]
    if missing:
        raise RuntimeError(
            "Streamlit Secretsに次の項目がありません: " + ", ".join(missing)
        )

    endpoint = str(secrets["AZURE_OPENAI_ENDPOINT"]).rstrip("/")
    deployment = secrets["AZURE_OPENAI_DEPLOYMENT"]
    api_version = secrets.get("AZURE_OPENAI_API_VERSION") or _DEFAULT_API_VERSION

    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    body = {
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _USER_TEMPLATE.format(payload=payload)},
        ]
    }

    try:
        response = requests.post(
            f"{endpoint}/openai/deployments/{deployment}/chat/completions",
            params={"api-version": api_version},
            headers={
                "api-key": secrets["AZURE_OPENAI_API_KEY"],
                "Content-Type": "application/json",
            },
            json=body,
            timeout=timeout,
        )
    except requests.Timeout as error:
        raise RuntimeError("Azure OpenAIの応答がタイムアウトしました。") from error
    except requests.RequestException as error:
        raise RuntimeError(
            "Azure OpenAIに接続できませんでした。エンドポイントを確認してください。"
        ) from error

    if response.status_code != 200:
        raise RuntimeError(_error_message(response))

    try:
        text = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise RuntimeError("Azure OpenAIの応答を読み取れませんでした。") from error

    if not text:
        raise RuntimeError(
            "応答が空でした(コンテンツフィルターなどで止まった可能性があります)。"
        )
    return text.strip()
