"""Azure OpenAI summaries based on aggregate activity data only."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd


def summarize_for_ai(frame: pd.DataFrame) -> dict[str, object]:
    """Create a coordinate-free summary for the language model."""
    distance = pd.to_numeric(frame.get("distance", 0), errors="coerce").fillna(0).clip(lower=0)
    duration = pd.to_numeric(frame.get("duration", 0), errors="coerce").fillna(0).clip(lower=0)
    steps = pd.to_numeric(frame.get("estimated_steps", 0), errors="coerce").fillna(0)
    calories = pd.to_numeric(frame.get("estimated_calories_kcal", 0), errors="coerce").fillna(0)
    activities = frame.get("activity_type", pd.Series(dtype="object")).fillna("unknown")
    return {
        "record_count": int(len(frame)),
        "distance_km": round(float(distance.sum()) / 1000, 2),
        "duration_minutes": round(float(duration.sum()) / 60, 1),
        "estimated_steps": int(steps.sum()),
        "estimated_calories_kcal": round(float(calories.sum()), 1),
        "average_speed_kmh": round(float(distance.sum() / duration.sum() * 3.6), 2) if duration.sum() else 0.0,
        "activity_record_counts": {str(key): int(value) for key, value in activities.value_counts().items()},
    }


def generate_activity_summary(summary: Mapping[str, object], secrets: Mapping[str, str]) -> str:
    """Generate a Japanese activity explanation using the Azure OpenAI SDK."""
    from openai import AzureOpenAI

    client = AzureOpenAI(
        api_key=secrets["AZURE_OPENAI_API_KEY"],
        azure_endpoint=secrets["AZURE_OPENAI_ENDPOINT"],
        api_version=secrets.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    )
    response = client.chat.completions.create(
        model=secrets["AZURE_OPENAI_DEPLOYMENT"],
        temperature=0.4,
        messages=[
            {"role": "system", "content": "GPS活動データの説明アシスタントです。医療診断や過度な運動・食事指示はせず、推定値であることを明示し、日本語で簡潔に説明してください。"},
            {"role": "user", "content": "次の集計済みデータだけを使い、活動量、移動手段の特徴、行動パターンを3〜5項目で説明してください。GPS座標は含まれていません。\n" + str(dict(summary))},
        ],
    )
    return response.choices[0].message.content or "AIから要約を取得できませんでした。"
