"""Azure OpenAIによる活動サマリー生成."""

from __future__ import annotations

from collections.abc import Mapping


# Azure OpenAI の接続設定。APIキーはStreamlit Secretsで管理する。
DEFAULT_AZURE_OPENAI_ENDPOINT = "https://gps-activity.openai.azure.com/"
DEFAULT_AZURE_OPENAI_DEPLOYMENT = "gpt-4.1-mini"
DEFAULT_AZURE_OPENAI_API_VERSION = "2024-12-01-preview"


def summarize_for_ai(
    frame,
    summary: Mapping[str, object],
) -> dict[str, object]:
    """GPS座標を除外し、集計値だけをAIへ渡す."""
    mode_summary = summary.get("mode_summary")

    return {
        "total_distance_km": round(
            float(summary.get("total_distance_km", 0)),
            2,
        ),
        "moving_minutes": round(
            float(summary.get("moving_minutes", 0)),
            1,
        ),
        "average_speed_kmh": round(
            float(summary.get("average_speed_kmh", 0)),
            2,
        ),
        "estimated_steps": round(
            float(summary.get("estimated_steps", 0))
        ),
        "estimated_calories_kcal": round(
            float(summary.get("estimated_calories_kcal", 0))
        ),
        "movement_modes": (
            mode_summary.to_dict(orient="records")
            if mode_summary is not None
            else []
        ),
    }


def generate_activity_summary(
    summary: Mapping[str, object],
    secrets: Mapping[str, str],
) -> str:
    """Azure OpenAIへ集計値だけを送信して要約を生成する."""
    from openai import AzureOpenAI

    required_keys = [
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT",
    ]

    missing_keys = [
        key for key in required_keys
        if not secrets.get(key)
    ]

    if missing_keys:
        raise ValueError(
            "Azure OpenAIのSecretsが未設定です: "
            + ", ".join(missing_keys)
        )

    client = AzureOpenAI(
        api_key=secrets["AZURE_OPENAI_API_KEY"],
        azure_endpoint=secrets["AZURE_OPENAI_ENDPOINT"],
        api_version=secrets.get(
            "AZURE_OPENAI_API_VERSION",
            DEFAULT_AZURE_OPENAI_API_VERSION,
        ),
    )

    response = client.chat.completions.create(
        model=secrets["AZURE_OPENAI_DEPLOYMENT"],
        max_completion_tokens=700,
        temperature=1.0,
        messages=[
            {
                "role": "system",
                "content": (
                    "あなたはGPS活動データの説明アシスタントです。"
                    "推定値であることを明記してください。"
                    "医療診断や健康状態の断定はしないでください。"
                    "日本語で分かりやすく説明してください。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "次の集計済みデータだけを使って、"
                    "活動量、移動手段、行動パターンを説明してください。"
                    "GPS座標や個人情報は含まれていません。\n"
                    f"{dict(summary)}"
                ),
            },
        ],
    )

    return (
        response.choices[0].message.content
        or "AIから要約が返されませんでした。"
    )
